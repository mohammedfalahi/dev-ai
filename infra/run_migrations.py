import os
import sys
import time
from pathlib import Path
import psycopg

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "callops")
POSTGRES_USER = os.getenv("POSTGRES_USER", "callops")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "callops_dev")

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def wait_for_postgres(conn_info: str, max_retries: int = 30, delay: float = 1.0) -> psycopg.Connection:
    print(f"Connecting to Postgres at {POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}...")
    for attempt in range(1, max_retries + 1):
        try:
            conn = psycopg.connect(conn_info, autocommit=True)
            print(f"Successfully connected to PostgreSQL (attempt {attempt}).")
            return conn
        except psycopg.OperationalError as e:
            if attempt == max_retries:
                print(f"Failed to connect to PostgreSQL after {max_retries} attempts.")
                raise e
            print(f"PostgreSQL not ready yet (attempt {attempt}/{max_retries}). Retrying in {delay}s...")
            time.sleep(delay)
    raise RuntimeError("Could not connect to PostgreSQL.")


def run_migrations():
    conn_info = (
        f"host={POSTGRES_HOST} port={POSTGRES_PORT} dbname={POSTGRES_DB} "
        f"user={POSTGRES_USER} password={POSTGRES_PASSWORD}"
    )

    with wait_for_postgres(conn_info) as conn:
        migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        if not migration_files:
            print("No migration files found in", MIGRATIONS_DIR)
            return

        for migration_file in migration_files:
            print(f"\nExecuting migration: {migration_file.name}...")
            sql_content = migration_file.read_text(encoding="utf-8")
            with conn.cursor() as cur:
                cur.execute(sql_content)
            print(f"Successfully applied {migration_file.name}")

        # Verification
        with conn.cursor() as cur:
            # Check installed extensions
            cur.execute("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';")
            ext = cur.fetchone()
            if ext:
                print(f"\n[Verification] Extension '{ext[0]}' version {ext[1]} is active.")
            else:
                print("\n[Warning] pgvector extension was not found!")

            # Check created tables
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                ORDER BY table_name;
                """
            )
            tables = [row[0] for row in cur.fetchall()]
            print(f"[Verification] Created tables ({len(tables)}): {', '.join(tables)}")

            # Check runbook_chunks columns
            cur.execute(
                """
                SELECT column_name, data_type, is_generated
                FROM information_schema.columns
                WHERE table_name = 'runbook_chunks'
                ORDER BY ordinal_position;
                """
            )
            columns = cur.fetchall()
            print("\n[Verification] 'runbook_chunks' schema:")
            for col in columns:
                print(f"  - {col[0]}: {col[1]} (generated: {col[2]})")

            # Check indexes on runbook_chunks
            cur.execute(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = 'runbook_chunks';
                """
            )
            indexes = cur.fetchall()
            print("\n[Verification] 'runbook_chunks' indexes:")
            for idx in indexes:
                print(f"  - {idx[0]}: {idx[1]}")


if __name__ == "__main__":
    try:
        run_migrations()
        print("\nAll migrations executed and verified successfully.")
    except Exception as err:
        print(f"\nMigration failed: {err}", file=sys.stderr)
        sys.exit(1)
