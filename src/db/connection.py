"""Database connection utility for TechPulse."""

import logging
import threading

from psycopg2 import pool

from src.config import settings

logger = logging.getLogger(__name__)

_pool: pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> pool.ThreadedConnectionPool:
    """Lazily initialise a connection pool (singleton)."""
    global _pool
    if _pool is not None and not _pool.closed:
        return _pool
    with _pool_lock:
        if _pool is None or _pool.closed:
            _pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                host=settings.DB_HOST,
                port=settings.DB_PORT,
                dbname=settings.DB_NAME,
                user=settings.DB_USER,
                password=settings.DB_PASSWORD,
            )
            logger.info("Database connection pool created")
    return _pool


def get_connection():
    """Return a connection from the pool."""
    conn = _get_pool().getconn()
    try:
        from pgvector.psycopg2 import register_vector
        register_vector(conn)
    except Exception:
        logger.debug("pgvector registration skipped (extension not yet created)")
    return conn


def put_connection(conn):
    """Return a connection back to the pool."""
    _get_pool().putconn(conn)


def close_pool():
    """Close all pool connections (for graceful shutdown)."""
    global _pool
    if _pool is not None and not _pool.closed:
        _pool.closeall()
        _pool = None
        logger.info("Database connection pool closed")
