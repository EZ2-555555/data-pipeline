"""Sync locally Docker-ingested data to AWS (S3 + RDS).

Usage:
    # Sync both data-lake files to S3 and local DB to RDS
    python -m src.sync_to_aws

    # Sync only the data-lake to S3
    python -m src.sync_to_aws --s3-only

    # Sync only the local DB to a remote RDS instance
    python -m src.sync_to_aws --db-only

    # Dry-run (list what would be uploaded)
    python -m src.sync_to_aws --dry-run

Environment variables:
    AWS_REGION            – target region (default: ap-southeast-1)
    S3_BUCKET_NAME        – target S3 bucket (default: techpulse-data)
    LOCAL_LAKE_DIR        – local data-lake directory (default: data_lake)
    REMOTE_DB_HOST        – RDS endpoint (required for DB sync)
    REMOTE_DB_PORT        – RDS port (default: 5432)
    REMOTE_DB_NAME        – RDS database name (default: techpulse)
    REMOTE_DB_USER        – RDS master username (default: postgres)
    REMOTE_DB_PASSWORD    – RDS password (required for DB sync)
"""

import argparse
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# S3 upload
# ---------------------------------------------------------------------------

def sync_data_lake_to_s3(dry_run: bool = False) -> int:
    """Walk the local data-lake directory and upload every JSON file to S3.

    Returns the number of files uploaded (or that would be uploaded in dry-run).
    """
    import boto3

    lake_dir = Path(os.getenv("LOCAL_LAKE_DIR", "data_lake"))
    bucket = os.getenv("S3_BUCKET_NAME", "techpulse-data")
    region = os.getenv("AWS_REGION", "ap-southeast-1")

    if not lake_dir.exists():
        logger.warning("Local data-lake directory '%s' does not exist — nothing to sync.", lake_dir)
        return 0

    s3 = boto3.client("s3", region_name=region)

    count = 0
    for file_path in sorted(lake_dir.rglob("*.json")):
        # Convert local path to S3 key (forward-slash, relative)
        key = file_path.relative_to(lake_dir).as_posix()

        if dry_run:
            logger.info("[dry-run] Would upload %s → s3://%s/%s", file_path, bucket, key)
        else:
            s3.upload_file(
                Filename=str(file_path),
                Bucket=bucket,
                Key=key,
                ExtraArgs={"ContentType": "application/json"},
            )
            logger.info("Uploaded %s → s3://%s/%s", file_path, bucket, key)
        count += 1

    logger.info("S3 sync complete: %d file(s) %s.", count, "would be uploaded" if dry_run else "uploaded")
    return count


# ---------------------------------------------------------------------------
# DB sync  (local Docker PG → remote RDS PG)
# ---------------------------------------------------------------------------

def _get_remote_dsn() -> dict:
    """Build connection kwargs for the remote RDS instance."""
    host = os.getenv("REMOTE_DB_HOST")
    if not host:
        raise EnvironmentError(
            "REMOTE_DB_HOST is not set. "
            "Set it to your RDS endpoint (e.g. techpulse-dev.xxxxxx.us-east-1.rds.amazonaws.com)."
        )
    return {
        "host": host,
        "port": int(os.getenv("REMOTE_DB_PORT", "5432")),
        "dbname": os.getenv("REMOTE_DB_NAME", "techpulse"),
        "user": os.getenv("REMOTE_DB_USER", "postgres"),
        "password": os.getenv("REMOTE_DB_PASSWORD", ""),
    }


def sync_db_to_rds(dry_run: bool = False) -> dict:
    """Copy documents & chunks from local Docker PostgreSQL to remote RDS.

    Uses an upsert strategy (INSERT … ON CONFLICT DO NOTHING) so the
    command is idempotent and safe to re-run.

    Returns a dict with counts: {"documents": N, "chunks": N}.
    """
    import psycopg2

    from src.db.connection import get_connection, put_connection

    remote_dsn = _get_remote_dsn()

    # --- read from local ---
    local_conn = get_connection()
    try:
        with local_conn.cursor() as cur:
            cur.execute(
                "SELECT id, source, title, content, url, published_at, "
                "content_hash, state, created_at FROM documents ORDER BY id"
            )
            documents = cur.fetchall()

            cur.execute(
                "SELECT id, document_id, chunk_index, chunk_text, "
                "embedding::text, created_at FROM chunks ORDER BY id"
            )
            chunks = cur.fetchall()
    finally:
        put_connection(local_conn)

    logger.info("Local DB: %d documents, %d chunks to sync.", len(documents), len(chunks))

    if dry_run:
        logger.info("[dry-run] Would upsert %d documents and %d chunks to RDS.", len(documents), len(chunks))
        return {"documents": len(documents), "chunks": len(chunks)}

    # --- write to remote ---
    remote_conn = psycopg2.connect(**remote_dsn)
    try:
        with remote_conn.cursor() as cur:
            # Ensure schema exists on remote
            from src.db.init_schema import SCHEMA_SQL
            cur.execute(SCHEMA_SQL)

            # Upsert documents
            doc_count = 0
            for row in documents:
                cur.execute(
                    """
                    INSERT INTO documents
                        (id, source, title, content, url, published_at,
                         content_hash, state, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (content_hash) DO NOTHING
                    """,
                    row,
                )
                doc_count += cur.rowcount

            # Build a map of local doc IDs → remote doc IDs (via content_hash)
            cur.execute("SELECT id, content_hash FROM documents")
            remote_id_map = {ch: rid for rid, ch in cur.fetchall()}

            # Upsert chunks (remap document_id to the remote ID)
            chunk_count = 0
            for row in chunks:
                cid, local_doc_id, chunk_index, chunk_text, embedding_text, created_at = row

                # Look up the content_hash for this local document_id
                local_hash = None
                for doc_row in documents:
                    if doc_row[0] == local_doc_id:
                        local_hash = doc_row[6]  # content_hash is index 6
                        break

                if local_hash is None or local_hash not in remote_id_map:
                    logger.warning("Skipping chunk %d — parent document not found on remote.", cid)
                    continue

                remote_doc_id = remote_id_map[local_hash]
                cur.execute(
                    """
                    INSERT INTO chunks
                        (document_id, chunk_index, chunk_text, embedding, created_at)
                    VALUES (%s, %s, %s, %s::vector, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (remote_doc_id, chunk_index, chunk_text, embedding_text, created_at),
                )
                chunk_count += cur.rowcount

            # Reset sequences so future inserts don't collide
            cur.execute("SELECT setval('documents_id_seq', (SELECT COALESCE(MAX(id),0) FROM documents))")
            cur.execute("SELECT setval('chunks_id_seq', (SELECT COALESCE(MAX(id),0) FROM chunks))")

        remote_conn.commit()
        logger.info("RDS sync complete: %d new documents, %d new chunks.", doc_count, chunk_count)
        return {"documents": doc_count, "chunks": chunk_count}
    except Exception:
        remote_conn.rollback()
        raise
    finally:
        remote_conn.close()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Sync locally Docker-ingested data to AWS (S3 + RDS)."
    )
    parser.add_argument("--s3-only", action="store_true", help="Sync only data-lake files to S3")
    parser.add_argument("--db-only", action="store_true", help="Sync only local DB to remote RDS")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be synced without doing it")
    args = parser.parse_args()

    do_s3 = not args.db_only
    do_db = not args.s3_only

    results = {}

    if do_s3:
        logger.info("=== Syncing data-lake to S3 ===")
        results["s3_files"] = sync_data_lake_to_s3(dry_run=args.dry_run)

    if do_db:
        logger.info("=== Syncing local DB to RDS ===")
        results["db"] = sync_db_to_rds(dry_run=args.dry_run)

    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    main()
