"""Tests for src/db — connection pool and schema initialization."""

from unittest.mock import MagicMock, patch
import pytest


# ===================================================================
# connection.py
# ===================================================================

# ---------------------------------------------------------------------------
# _get_pool
# ---------------------------------------------------------------------------

@patch("src.db.connection.settings")
@patch("src.db.connection.pool.ThreadedConnectionPool")
def test_get_pool_creates_pool(mock_pool_cls, mock_settings):
    mock_settings.DB_HOST = "localhost"
    mock_settings.DB_PORT = 5432
    mock_settings.DB_NAME = "techpulse"
    mock_settings.DB_USER = "user"
    mock_settings.DB_PASSWORD = "pass"

    # Reset the global singleton
    import src.db.connection as conn_mod
    conn_mod._pool = None

    mock_pool_instance = MagicMock()
    mock_pool_instance.closed = False
    mock_pool_cls.return_value = mock_pool_instance

    result = conn_mod._get_pool()
    assert result == mock_pool_instance
    mock_pool_cls.assert_called_once()


@patch("src.db.connection.settings")
@patch("src.db.connection.pool.ThreadedConnectionPool")
def test_get_pool_reuses_existing(mock_pool_cls, mock_settings):
    import src.db.connection as conn_mod

    mock_pool_instance = MagicMock()
    mock_pool_instance.closed = False
    conn_mod._pool = mock_pool_instance

    result = conn_mod._get_pool()
    assert result == mock_pool_instance
    mock_pool_cls.assert_not_called()


# ---------------------------------------------------------------------------
# get_connection
# ---------------------------------------------------------------------------

@patch("src.db.connection._get_pool")
def test_get_connection(mock_get_pool):
    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_get_pool.return_value = mock_pool

    with patch("src.db.connection.register_vector", create=True):
        from src.db.connection import get_connection
        conn = get_connection()
    assert conn == mock_conn


@patch("src.db.connection._get_pool")
def test_get_connection_pgvector_skip(mock_get_pool):
    """pgvector registration failure should not prevent returning conn."""
    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_get_pool.return_value = mock_pool

    # Make pgvector import fail
    with patch.dict("sys.modules", {"pgvector": None, "pgvector.psycopg2": None}):
        from src.db.connection import get_connection
        conn = get_connection()
    assert conn == mock_conn


# ---------------------------------------------------------------------------
# put_connection
# ---------------------------------------------------------------------------

@patch("src.db.connection._get_pool")
def test_put_connection(mock_get_pool):
    mock_pool = MagicMock()
    mock_get_pool.return_value = mock_pool
    mock_conn = MagicMock()

    from src.db.connection import put_connection
    put_connection(mock_conn)
    mock_pool.putconn.assert_called_once_with(mock_conn)


# ---------------------------------------------------------------------------
# close_pool
# ---------------------------------------------------------------------------

def test_close_pool():
    import src.db.connection as conn_mod
    mock_pool = MagicMock()
    mock_pool.closed = False
    conn_mod._pool = mock_pool

    conn_mod.close_pool()

    mock_pool.closeall.assert_called_once()
    assert conn_mod._pool is None


def test_close_pool_already_none():
    import src.db.connection as conn_mod
    conn_mod._pool = None
    # Should not raise
    conn_mod.close_pool()


# ===================================================================
# init_schema.py
# ===================================================================

@patch("src.db.init_schema.put_connection")
@patch("src.db.init_schema.get_connection")
def test_init_schema_success(mock_get_conn, mock_put_conn):
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_get_conn.return_value = mock_conn

    from src.db.init_schema import init_schema
    init_schema()

    mock_cursor.execute.assert_called_once()
    mock_conn.commit.assert_called_once()
    mock_put_conn.assert_called_once_with(mock_conn)


@patch("src.db.init_schema.put_connection")
@patch("src.db.init_schema.get_connection")
def test_init_schema_pgvector_error(mock_get_conn, mock_put_conn):
    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = Exception("vector extension not available")
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_get_conn.return_value = mock_conn

    from src.db.init_schema import init_schema
    with pytest.raises(Exception, match="vector"):
        init_schema()

    mock_put_conn.assert_called_once()
