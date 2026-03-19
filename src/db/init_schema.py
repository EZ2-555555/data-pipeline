"""Database schema initialization for TechPulse.

Run with: python -m src.db.init_schema
"""

import logging

from src.db.connection import get_connection, put_connection

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Documents table (raw ingested records)
CREATE TABLE IF NOT EXISTS documents (
    id            SERIAL PRIMARY KEY,
    source        VARCHAR(20) NOT NULL,
    title         TEXT NOT NULL,
    content       TEXT,
    url           TEXT,
    published_at  DATE,
    content_hash  CHAR(64) UNIQUE NOT NULL,
    state         VARCHAR(10) DEFAULT 'RAW',
    created_at    TIMESTAMP DEFAULT NOW()
);

-- Chunks table (preprocessed + embedded segments)
CREATE TABLE IF NOT EXISTS chunks (
    id            SERIAL PRIMARY KEY,
    document_id   INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index   INTEGER NOT NULL,
    chunk_text    TEXT NOT NULL,
    embedding     vector(384),
    created_at    TIMESTAMP DEFAULT NOW()
);

-- HNSW index for fast vector similarity search.
-- HNSW works well even on empty/small tables (unlike ivfflat which needs data for centroids).
CREATE INDEX IF NOT EXISTS idx_chunks_embedding
    ON chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

-- Index for metadata filtering
CREATE INDEX IF NOT EXISTS idx_documents_published
    ON documents (published_at DESC);

CREATE INDEX IF NOT EXISTS idx_documents_source
    ON documents (source);

CREATE INDEX IF NOT EXISTS idx_documents_state
    ON documents (state);

-- Drift detection baselines (probe query similarity over time)
CREATE TABLE IF NOT EXISTS drift_baselines (
    id              SERIAL PRIMARY KEY,
    run_date        TIMESTAMP DEFAULT NOW(),
    mean_similarity FLOAT NOT NULL,
    std_similarity  FLOAT NOT NULL,
    num_probes      INTEGER NOT NULL,
    alert_triggered BOOLEAN DEFAULT FALSE
);
"""


def init_schema():
    """Create all tables and indexes."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(SCHEMA_SQL)
            except Exception as exc:
                conn.rollback()
                if "vector" in str(exc).lower():
                    logger.error(
                        "pgvector extension is not available on this PostgreSQL instance. "
                        "Install it with: CREATE EXTENSION vector; "
                        "On AWS RDS, ensure you are using a supported instance type "
                        "and the extension is enabled. Error: %s",
                        exc,
                    )
                raise
        conn.commit()
        logger.info("Database schema initialized successfully.")
    finally:
        put_connection(conn)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_schema()
