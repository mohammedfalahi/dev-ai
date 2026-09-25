import os
from pathlib import Path

import psycopg
from google import genai
from google.genai import types

from packages.knowledge.chunker import extract_runbooks_and_chunks

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "callops")
POSTGRES_USER = os.getenv("POSTGRES_USER", "callops")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "callops_dev")


def get_postgres_connection() -> psycopg.Connection:
    """Connect to local Postgres using project environment settings."""
    conn_info = (
        f"host={POSTGRES_HOST} port={POSTGRES_PORT} dbname={POSTGRES_DB} "
        f"user={POSTGRES_USER} password={POSTGRES_PASSWORD}"
    )
    return psycopg.connect(conn_info, autocommit=False)


def generate_batch_embeddings(
    texts: list[str],
    client: genai.Client | None = None,
    batch_size: int = 30,
) -> list[list[float]]:
    """Batch-embed texts using gemini-embedding-001 with 768 MRL dimensions and RETRIEVAL_DOCUMENT task."""
    if not texts:
        return []

    if client is None:
        client = genai.Client()

    embeddings: list[list[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = client.models.embed_content(
            model="gemini-embedding-001",
            contents=batch,
            config=types.EmbedContentConfig(
                output_dimensionality=768,
                task_type="RETRIEVAL_DOCUMENT",
            ),
        )
        if not response.embeddings:
            raise RuntimeError(
                f"No embeddings returned for batch starting at index {i}"
            )

        for item in response.embeddings:
            if not item.values:
                raise RuntimeError("Empty embedding values returned from Gemini API")
            embeddings.append(list(item.values))

    return embeddings


def ingest_runbooks(
    file_path: str | Path,
    client: genai.Client | None = None,
    conn: psycopg.Connection | None = None,
    batch_size: int = 30,
) -> dict[str, int]:
    """Ingest markdown runbooks into PostgreSQL + pgvector.

    1. Parses runbook metadata and chunks from file_path.
    2. Batch-embeds each chunk's search_text using gemini-embedding-001.
    3. Idempotently upserts runbooks and runbook_chunks in a single atomic transaction.
    """
    path = Path(file_path)
    runbooks, chunks = extract_runbooks_and_chunks(path)

    if not runbooks:
        return {"runbooks_inserted": 0, "chunks_inserted": 0}

    # Generate embeddings for each chunk's search_text
    search_texts = [chunk.search_text for chunk in chunks]
    embeddings = generate_batch_embeddings(
        search_texts, client=client, batch_size=batch_size
    )

    if len(embeddings) != len(chunks):
        raise ValueError(
            f"Embedding count mismatch: expected {len(chunks)}, got {len(embeddings)}"
        )

    should_close_conn = False
    if conn is None:
        conn = get_postgres_connection()
        should_close_conn = True

    try:
        # Atomic transaction boundary
        with conn.transaction(), conn.cursor() as cur:
            # 1. Upsert runbooks
            for rb in runbooks:
                cur.execute(
                    """
                    INSERT INTO runbooks (id, title, service, tags, source_url, last_verified_at, owner)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title,
                        service = EXCLUDED.service,
                        tags = EXCLUDED.tags,
                        source_url = EXCLUDED.source_url,
                        last_verified_at = EXCLUDED.last_verified_at,
                        owner = EXCLUDED.owner;
                    """,
                    (
                        rb["id"],
                        rb["title"],
                        rb["service"],
                        rb["tags"],
                        rb["source_url"],
                        rb["last_verified_at"],
                        rb["owner"],
                    ),
                )

            # 2. Upsert runbook_chunks with vector(768)
            for chunk, emb in zip(chunks, embeddings, strict=True):
                cur.execute(
                    """
                    INSERT INTO runbook_chunks (id, runbook_id, heading_path, content, token_count, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s::vector(768))
                    ON CONFLICT (id) DO UPDATE SET
                        runbook_id = EXCLUDED.runbook_id,
                        heading_path = EXCLUDED.heading_path,
                        content = EXCLUDED.content,
                        token_count = EXCLUDED.token_count,
                        embedding = EXCLUDED.embedding;
                    """,
                    (
                        chunk.chunk_id,
                        chunk.runbook_id,
                        chunk.heading_path,
                        chunk.content,
                        chunk.token_count,
                        str(emb),
                    ),
                )

        return {
            "runbooks_inserted": len(runbooks),
            "chunks_inserted": len(chunks),
        }

    finally:
        if should_close_conn:
            conn.close()


if __name__ == "__main__":
    import sys

    target_file = Path("data/generated/runbooks.md")
    if len(sys.argv) > 1:
        target_file = Path(sys.argv[1])

    print(f"Ingesting runbooks from {target_file} into PostgreSQL...")
    stats = ingest_runbooks(target_file)
    print(
        f"Ingestion complete: {stats['runbooks_inserted']} runbooks and "
        f"{stats['chunks_inserted']} chunks upserted successfully."
    )
