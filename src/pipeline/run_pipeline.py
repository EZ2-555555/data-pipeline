"""Chunk + embed pipeline for TechPulse.

Reads RAW documents, chunks them, generates embeddings,
inserts into the chunks table, and marks documents as INDEXED.

Supports two modes:
  1. Poll-DB mode (default) — fetches all RAW docs from the database.
  2. SQS-consumer mode — processes messages from the ingestion queue.

Run with: python -m src.pipeline.run_pipeline
Backfill: python -m src.pipeline.run_pipeline --backfill-normalize
"""

import logging

from src.db.connection import get_connection, put_connection
from src.preprocessing.chunker import normalize_text, chunk_text
from src.embedding.embedder import embed_texts
from src.storage import write_processed, write_embeddings
from src.observability import record_pipeline_chunks, record_pipeline_error, timed_metric

logger = logging.getLogger(__name__)


def fetch_raw_documents() -> list[dict]:
    """Fetch all documents with state='RAW'."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, title, content, source, content_hash, published_at "
                "FROM documents WHERE state = 'RAW'"
            )
            rows = cur.fetchall()
    finally:
        put_connection(conn)
    return [
        {
            "id": r[0], "title": r[1], "content": r[2],
            "source": r[3], "content_hash": r[4], "published_at": str(r[5]) if r[5] else None,
        }
        for r in rows
    ]


def process_and_store(documents: list[dict]) -> int:
    """Chunk, embed, and store all documents. Returns total chunks inserted."""
    if not documents:
        logger.info("No RAW documents to process.")
        return 0

    total_chunks = 0
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for doc in documents:
                # Combine title + content for richer chunks
                raw_text = f"{doc['title']}. {doc['content'] or ''}"
                normalized = normalize_text(raw_text)

                if not normalized.strip():
                    # Mark empty docs as INDEXED so we don't retry them
                    cur.execute(
                        "UPDATE documents SET state = 'INDEXED' WHERE id = %s",
                        (doc["id"],),
                    )
                    continue

                chunks = chunk_text(normalized)
                if not chunks:
                    cur.execute(
                        "UPDATE documents SET state = 'INDEXED' WHERE id = %s",
                        (doc["id"],),
                    )
                    continue

                # ---- State transition: RAW → PROCESSED ----
                source = doc.get("source", "unknown")
                content_hash = doc.get("content_hash", "")
                date_str = doc.get("published_at")
                if content_hash:
                    write_processed(source, content_hash, chunks, date_str)
                cur.execute(
                    "UPDATE documents SET state = 'PROCESSED' WHERE id = %s",
                    (doc["id"],),
                )

                # ---- State transition: PROCESSED → EMBEDDED ----
                try:
                    embeddings = embed_texts(chunks)
                except Exception:
                    logger.error(
                        "Embedding failed for doc %d — reverting to RAW for retry",
                        doc["id"], exc_info=True,
                    )
                    record_pipeline_error("embed_texts")
                    cur.execute(
                        "UPDATE documents SET state = 'RAW' WHERE id = %s",
                        (doc["id"],),
                    )
                    continue

                for idx, (chunk_str, emb) in enumerate(zip(chunks, embeddings)):
                    cur.execute(
                        """
                        INSERT INTO chunks (document_id, chunk_index, chunk_text, embedding)
                        VALUES (%s, %s, %s, %s::vector)
                        """,
                        (doc["id"], idx, chunk_str, emb),
                    )
                cur.execute(
                    "UPDATE documents SET state = 'EMBEDDED' WHERE id = %s",
                    (doc["id"],),
                )

                # ---- State transition: EMBEDDED → INDEXED ----
                if content_hash:
                    write_embeddings(source, content_hash, len(chunks), date_str)
                cur.execute(
                    "UPDATE documents SET state = 'INDEXED', content = %s WHERE id = %s",
                    (normalized, doc["id"]),
                )

                total_chunks += len(chunks)
                logger.info(
                    "Doc %d: %d chunks embedded and stored.", doc["id"], len(chunks)
                )

        conn.commit()
    except Exception:
        conn.rollback()
        record_pipeline_error("process_and_store")
        raise
    finally:
        put_connection(conn)

    record_pipeline_chunks(total_chunks)
    return total_chunks


def run():
    """Main entry point: fetch RAW docs → chunk → embed → store."""
    with timed_metric("PipelineLatency"):
        docs = fetch_raw_documents()
        logger.info("Found %d RAW documents to process.", len(docs))
        total = process_and_store(docs)
    logger.info("Pipeline complete. %d total chunks created.", total)
    return total


def process_sqs_batch() -> int:
    """Process a batch of messages from the SQS ingestion queue.

    For each message, fetches the document from DB by ID, runs it
    through the pipeline, and deletes the SQS message on success.
    Returns the number of documents processed.
    """
    from src.queue import receive_messages, delete_message

    messages = receive_messages(max_messages=5, wait_seconds=5)
    if not messages:
        return 0

    processed = 0
    for msg in messages:
        doc_id = msg["body"].get("document_id")
        if doc_id is None:
            logger.warning("SQS message %s missing document_id, deleting", msg.get("message_id", "?"))
            delete_message(msg["receipt_handle"])
            continue

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, title, content, source, content_hash, published_at "
                    "FROM documents WHERE id = %s AND state = 'RAW'",
                    (doc_id,),
                )
                row = cur.fetchone()
        finally:
            put_connection(conn)

        if not row:
            # Already processed or doesn't exist — delete the message
            delete_message(msg["receipt_handle"])
            continue

        doc = {
            "id": row[0], "title": row[1], "content": row[2],
            "source": row[3], "content_hash": row[4],
            "published_at": str(row[5]) if row[5] else None,
        }

        try:
            chunks = process_and_store([doc])
            delete_message(msg["receipt_handle"])
            processed += 1
            logger.info("SQS doc %d processed (%d chunks)", doc_id, chunks)
        except Exception:
            record_pipeline_error("sqs_consumer")
            logger.error("Failed to process SQS doc %d", doc_id, exc_info=True)

    return processed


# ---------------------------------------------------------------------------
# Lambda handlers (used by SAM / CDK deployments)
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    """AWS Lambda entry point for scheduled ingestion."""
    from src.db.init_schema import init_schema
    from src.ingestion.hn_ingester import run as ingest_hn
    from src.ingestion.arxiv_ingester import run as ingest_arxiv
    from src.ingestion.devto_ingester import run as ingest_devto
    from src.ingestion.github_ingester import run as ingest_github
    from src.ingestion.rss_ingester import run as ingest_rss

    from src.config import settings as _settings
    init_schema()
    counts = {}
    for name, fn in [("hn", ingest_hn), ("arxiv", ingest_arxiv),
                     ("devto", ingest_devto), ("github", ingest_github),
                     ("rss", ingest_rss)]:
        try:
            counts[name] = fn()
        except Exception:
            logger.error("%s ingestion failed", name, exc_info=True)
            counts[name] = -1
    # Skip DB-poll pipeline when SQS is enabled — the preprocess_handler
    # Lambda will process documents via SQS messages instead.
    total = 0
    if not _settings.SQS_ENABLED:
        total = run()
    return {"ingested": counts, "chunks_created": total}


def preprocess_handler(event, context):
    """AWS Lambda entry point triggered by SQS messages.

    When Lambda is triggered by SQS (EventSourceMapping), messages are
    delivered in event['Records'] — we must NOT poll SQS ourselves.
    Returns batchItemFailures for partial-batch error reporting.
    """
    import json as _json
    from src.db.init_schema import init_schema
    
    # Initialize schema with fallback error handling
    try:
        init_schema()
    except Exception as e:
        logger.error(
            "Failed to initialize database schema: %s. "
            "Ensure pgvector extension is installed on your RDS instance. "
            "Continuing with caution...",
            e,
        )
        # Don't fail the entire Lambda — this may be a transient issue
        # The connection will fail below if schema is truly missing

    records = event.get("Records", [])
    if not records:
        # Fallback: direct invocation (e.g., manual testing)
        processed = process_sqs_batch()
        return {"processed": processed}

    batch_item_failures = []
    processed = 0

    for record in records:
        msg_id = record.get("messageId", "")
        try:
            body = _json.loads(record["body"])
            doc_id = body.get("document_id")
            if doc_id is None:
                logger.warning("SQS record %s missing document_id, skipping", msg_id)
                continue

            conn = get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, title, content, source, content_hash, published_at "
                        "FROM documents WHERE id = %s AND state = 'RAW'",
                        (doc_id,),
                    )
                    row = cur.fetchone()
            finally:
                put_connection(conn)

            if not row:
                continue  # Already processed or missing

            doc = {
                "id": row[0], "title": row[1], "content": row[2],
                "source": row[3], "content_hash": row[4],
                "published_at": str(row[5]) if row[5] else None,
            }
            process_and_store([doc])
            processed += 1
        except Exception:
            logger.error("Failed to process SQS record %s", msg_id, exc_info=True)
            record_pipeline_error("sqs_lambda")
            batch_item_failures.append({"itemIdentifier": msg_id})

    logger.info("preprocess_handler: %d/%d records processed", processed, len(records))
    return {"batchItemFailures": batch_item_failures}


# ---------------------------------------------------------------------------
# One-off backfill: normalize title + content for ALL existing documents
# ---------------------------------------------------------------------------

def backfill_normalize() -> int:
    """Re-normalize title and content for every document already in the DB.

    Safe to re-run: idempotent (normalize_text is deterministic).
    Run with: python -m src.pipeline.run_pipeline --backfill-normalize
    """
    conn = get_connection()
    updated = 0
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, title, content FROM documents")
            rows = cur.fetchall()
            for doc_id, title, content in rows:
                clean_title = normalize_text(title or "")
                clean_content = normalize_text(content or "")
                cur.execute(
                    "UPDATE documents SET title = %s, content = %s WHERE id = %s",
                    (clean_title, clean_content, doc_id),
                )
                updated += 1
        conn.commit()
        logger.info("Backfill complete: normalized %d documents.", updated)
    except Exception:
        conn.rollback()
        raise
    finally:
        put_connection(conn)
    return updated


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    if "--backfill-normalize" in sys.argv:
        backfill_normalize()
    else:
        run()
