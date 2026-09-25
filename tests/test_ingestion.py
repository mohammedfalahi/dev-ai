from pathlib import Path

from packages.knowledge.ingest import get_postgres_connection, ingest_runbooks

RUNBOOKS_FILE = Path("data/generated/runbooks.md")


def test_runbook_ingestion_and_postgres_verification():
    """Verify end-to-end ingestion of operational runbooks into PostgreSQL + pgvector."""
    assert RUNBOOKS_FILE.is_file(), f"Fixture file not found: {RUNBOOKS_FILE}"

    # 1. Execute ingestion function
    stats = ingest_runbooks(RUNBOOKS_FILE)
    assert stats["runbooks_inserted"] == 6, (
        f"Expected 6 runbooks, got {stats['runbooks_inserted']}"
    )
    assert stats["chunks_inserted"] > 0, "No chunks were ingested"

    total_chunks_first_run = stats["chunks_inserted"]

    with get_postgres_connection() as conn, conn.cursor() as cur:
        # 2. Assert SELECT count(*) FROM runbooks equals 6
        cur.execute("SELECT count(*) FROM runbooks;")
        runbook_count = cur.fetchone()[0]
        assert runbook_count == 6, (
            f"Expected 6 runbooks in database, found {runbook_count}"
        )

        # 3. Assert SELECT count(*) FROM runbook_chunks is greater than 0
        cur.execute("SELECT count(*) FROM runbook_chunks;")
        chunk_count = cur.fetchone()[0]
        assert chunk_count > 0, "Expected runbook_chunks count to be greater than 0"
        assert chunk_count == total_chunks_first_run

        # 4. Assert that embedding is non-null and vector_dims(embedding) is exactly 768
        cur.execute(
            """
                SELECT count(*)
                FROM runbook_chunks
                WHERE embedding IS NULL OR vector_dims(embedding) != 768;
                """
        )
        invalid_embeddings_count = cur.fetchone()[0]
        assert invalid_embeddings_count == 0, (
            f"Found {invalid_embeddings_count} rows with null or non-768 dimension embeddings"
        )

        # 5. Assert that fts (tsvector) is generated and populated for each row
        cur.execute(
            """
                SELECT count(*)
                FROM runbook_chunks
                WHERE fts IS NULL OR length(fts) = 0;
                """
        )
        empty_fts_count = cur.fetchone()[0]
        assert empty_fts_count == 0, (
            f"Found {empty_fts_count} rows with empty or ungenerated fts tsvector"
        )

        # Verify specific runbook IDs exist
        cur.execute("SELECT id, service, title FROM runbooks ORDER BY id;")
        db_runbooks = cur.fetchall()
        rb_ids = [r[0] for r in db_runbooks]
        expected_ids = [
            "RB-EDGE-001",
            "RB-K8S-001",
            "RB-PG-001",
            "RB-PG-002",
            "RB-REDIS-001",
            "RB-STRIPE-001",
        ]
        assert sorted(rb_ids) == expected_ids

    # 6. Verify Idempotency: running ingestion again must not duplicate records
    stats_repeat = ingest_runbooks(RUNBOOKS_FILE)
    assert stats_repeat["runbooks_inserted"] == 6
    assert stats_repeat["chunks_inserted"] == total_chunks_first_run

    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM runbooks;")
        assert cur.fetchone()[0] == 6
        cur.execute("SELECT count(*) FROM runbook_chunks;")
        assert cur.fetchone()[0] == total_chunks_first_run
