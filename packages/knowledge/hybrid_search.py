import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Optional

import psycopg
from google import genai
from google.genai import types
from pydantic import BaseModel
from sentence_transformers import CrossEncoder

# Lazy-loaded model to prevent instantiation overhead when not searching
_cross_encoder = None


class RetrievalResult(BaseModel):
    chunk_id: str
    runbook_id: str
    service: str
    heading_path: list[str]
    content: str
    dense_rank: int | None
    fts_rank: int | None
    rrf_score: float
    rerank_score: float


@dataclass
class _Candidate:
    chunk_id: str
    runbook_id: str
    service: str
    heading_path: list[str]
    content: str
    dense_rank: Optional[int] = None
    fts_rank: Optional[int] = None


def get_postgres_connection():
    return psycopg.connect(
        os.environ.get(
            "DATABASE_URL",
            "postgresql://callops:callops_dev@localhost:5432/callops",
        )
    )


def search_runbooks(
    query: str, top_k: int = 3, min_rerank_score: float = -8.5
) -> list[RetrievalResult]:
    """
    Search runbooks using a Retrieve-and-Rerank hybrid pipeline.

    Stage 1:
      a) Fetch Top-10 using pgvector (Dense Semantic Search).
      b) Fetch Top-10 using tsvector (Sparse Lexical Search).
      c) Merge ranks using Reciprocal Rank Fusion (RRF, k=60).
    Stage 2:
      a) Rerank Top-5 fused candidates using MS-MARCO Cross-Encoder.
      b) Apply refusal gate (`min_rerank_score`) to reject out-of-domain queries.
    """
    global _cross_encoder
    if _cross_encoder is None:
        # Load lightweight Cross-Encoder. MS-MARCO outputs raw negative logits.
        _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

    # 1. Compute query embedding vector
    client = genai.Client()
    response = client.models.embed_content(
        model="gemini-embedding-001",
        contents=query,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=768,
        ),
    )
    if not response.embeddings or not response.embeddings[0].values:
        raise ValueError("Failed to retrieve embeddings from model")
    query_vector = response.embeddings[0].values

    candidates: dict[str, _Candidate] = {}

    with get_postgres_connection() as conn, conn.cursor() as cur:
        # 2. Fetch top 10 dense candidates (pgvector cosine distance)
        cur.execute(
            """
            SELECT rc.id, rc.runbook_id, r.service, rc.heading_path, rc.content,
                   (rc.embedding <=> %s::vector(768)) AS dist
            FROM runbook_chunks rc
            JOIN runbooks r ON rc.runbook_id = r.id
            ORDER BY dist ASC
            LIMIT 10;
            """,
            (f"[{','.join(str(f) for f in query_vector)}]",),
        )

        dense_rows = cur.fetchall()
        for rank, row in enumerate(dense_rows, start=1):
            chunk_id, runbook_id, service, heading_path, content, _dist = row
            candidates[chunk_id] = _Candidate(
                chunk_id=chunk_id,
                runbook_id=runbook_id,
                service=service,
                heading_path=heading_path,
                content=content,
                dense_rank=rank,
            )

        # 3. Fetch top 10 sparse FTS candidates (Postgres plainto_tsquery)
        cur.execute(
            """
            SELECT rc.id, rc.runbook_id, r.service, rc.heading_path, rc.content,
                   ts_rank_cd(rc.fts, plainto_tsquery('english', %s)) AS rank
            FROM runbook_chunks rc
            JOIN runbooks r ON rc.runbook_id = r.id
            WHERE rc.fts @@ plainto_tsquery('english', %s)
            ORDER BY rank DESC
            LIMIT 10;
            """,
            (query, query),
        )

        fts_rows = cur.fetchall()
        for rank, row in enumerate(fts_rows, start=1):
            chunk_id, runbook_id, service, heading_path, content, _ts_rank = row
            if chunk_id in candidates:
                candidates[chunk_id].fts_rank = rank
            else:
                candidates[chunk_id] = _Candidate(
                    chunk_id=chunk_id,
                    runbook_id=runbook_id,
                    service=service,
                    heading_path=heading_path,
                    content=content,
                    fts_rank=rank,
                )

    if not candidates:
        return []

    # 4. Merge using Reciprocal Rank Fusion (RRF)
    k_rrf = 60
    fused_scores = {}
    for chunk_id, c in candidates.items():
        score = 0.0
        if c.dense_rank is not None:
            score += 1.0 / (k_rrf + c.dense_rank)
        if c.fts_rank is not None:
            score += 1.0 / (k_rrf + c.fts_rank)
        fused_scores[chunk_id] = score

    # Sort and take top 5 fused candidates for reranking
    sorted_fused = sorted(
        fused_scores.items(), key=lambda item: item[1], reverse=True
    )
    top_5_fused = sorted_fused[:5]

    # 5. Score using MS-MARCO Cross-Encoder
    cross_encoder_inputs = []
    candidates_to_rerank = []
    
    for chunk_id, _ in top_5_fused:
        c = candidates[chunk_id]
        breadcrumb = " > ".join(c.heading_path)
        enriched_input = f"Service: {c.service} | Path: {breadcrumb} | {c.content}"
        cross_encoder_inputs.append([query, enriched_input])
        candidates_to_rerank.append(c)

    # Output is a NumPy array of raw logits
    rerank_scores = _cross_encoder.predict(cross_encoder_inputs)
    
    # 6. Build final results and apply refusal gate
    final_results = []
    for i, c in enumerate(candidates_to_rerank):
        rrf_score = fused_scores[c.chunk_id]
        rerank_score = float(rerank_scores[i])
        
        final_results.append(
            RetrievalResult(
                chunk_id=c.chunk_id,
                runbook_id=c.runbook_id,
                service=c.service,
                heading_path=c.heading_path,
                content=c.content,
                dense_rank=c.dense_rank,
                fts_rank=c.fts_rank,
                rrf_score=rrf_score,
                rerank_score=rerank_score,
            )
        )

    # Sort descending by rerank score
    final_results.sort(key=lambda x: x.rerank_score, reverse=True)

    # Refusal gate check on the absolute best candidate
    if final_results[0].rerank_score < min_rerank_score:
        return []

    return final_results[:top_k]
