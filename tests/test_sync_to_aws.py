"""Tests for src/sync_to_aws.py — S3 data-lake sync and DB-to-RDS sync."""

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# sync_data_lake_to_s3
# ---------------------------------------------------------------------------

def test_sync_s3_empty_dir(tmp_path, monkeypatch):
    """No files → returns 0."""
    monkeypatch.setenv("LOCAL_LAKE_DIR", str(tmp_path))
    with patch("boto3.client"):
        from src.sync_to_aws import sync_data_lake_to_s3
        assert sync_data_lake_to_s3() == 0


def test_sync_s3_no_dir(tmp_path, monkeypatch):
    """Non-existent directory → returns 0."""
    monkeypatch.setenv("LOCAL_LAKE_DIR", str(tmp_path / "nope"))
    from src.sync_to_aws import sync_data_lake_to_s3
    assert sync_data_lake_to_s3() == 0


def test_sync_s3_uploads_files(tmp_path, monkeypatch):
    """Files are uploaded with correct S3 keys."""
    monkeypatch.setenv("LOCAL_LAKE_DIR", str(tmp_path))
    monkeypatch.setenv("S3_BUCKET_NAME", "test-bucket")
    monkeypatch.setenv("AWS_REGION", "us-east-1")

    # Create some local lake files
    (tmp_path / "raw" / "hn" / "2026-01-01").mkdir(parents=True)
    (tmp_path / "raw" / "hn" / "2026-01-01" / "hash1.json").write_text('{"title":"A"}')
    (tmp_path / "processed" / "hn" / "2026-01-01").mkdir(parents=True)
    (tmp_path / "processed" / "hn" / "2026-01-01" / "hash1.json").write_text('{"chunks":["c"]}')

    mock_s3 = MagicMock()
    with patch("boto3.client", return_value=mock_s3):
        from src.sync_to_aws import sync_data_lake_to_s3
        count = sync_data_lake_to_s3()

    assert count == 2
    assert mock_s3.upload_file.call_count == 2
    keys_uploaded = {c.kwargs["Key"] for c in mock_s3.upload_file.call_args_list}
    assert "raw/hn/2026-01-01/hash1.json" in keys_uploaded
    assert "processed/hn/2026-01-01/hash1.json" in keys_uploaded


def test_sync_s3_dry_run(tmp_path, monkeypatch):
    """Dry-run counts files but does NOT call upload_file."""
    monkeypatch.setenv("LOCAL_LAKE_DIR", str(tmp_path))
    (tmp_path / "raw" / "hn").mkdir(parents=True)
    (tmp_path / "raw" / "hn" / "a.json").write_text("{}")

    mock_s3 = MagicMock()
    with patch("boto3.client", return_value=mock_s3):
        from src.sync_to_aws import sync_data_lake_to_s3
        count = sync_data_lake_to_s3(dry_run=True)

    assert count == 1
    mock_s3.upload_file.assert_not_called()


# ---------------------------------------------------------------------------
# _get_remote_dsn
# ---------------------------------------------------------------------------

def test_get_remote_dsn_missing_host(monkeypatch):
    """Raises EnvironmentError when REMOTE_DB_HOST is unset."""
    monkeypatch.delenv("REMOTE_DB_HOST", raising=False)
    from src.sync_to_aws import _get_remote_dsn
    import pytest
    with pytest.raises(EnvironmentError, match="REMOTE_DB_HOST"):
        _get_remote_dsn()


def test_get_remote_dsn_values(monkeypatch):
    monkeypatch.setenv("REMOTE_DB_HOST", "rds.example.com")
    monkeypatch.setenv("REMOTE_DB_PORT", "5433")
    monkeypatch.setenv("REMOTE_DB_NAME", "mydb")
    monkeypatch.setenv("REMOTE_DB_USER", "admin")
    monkeypatch.setenv("REMOTE_DB_PASSWORD", "secret")
    from src.sync_to_aws import _get_remote_dsn
    dsn = _get_remote_dsn()
    assert dsn["host"] == "rds.example.com"
    assert dsn["port"] == 5433
    assert dsn["dbname"] == "mydb"


# ---------------------------------------------------------------------------
# sync_db_to_rds
# ---------------------------------------------------------------------------

@patch("src.sync_to_aws._get_remote_dsn", return_value={
    "host": "rds.example.com", "port": 5432, "dbname": "techpulse",
    "user": "postgres", "password": "pw",
})
@patch("src.db.connection.get_connection")
@patch("src.db.connection.put_connection")
def test_sync_db_dry_run(mock_put, mock_get, mock_dsn):
    """Dry-run reads local but does NOT connect to remote."""
    mock_cursor = MagicMock()
    mock_cursor.fetchall.side_effect = [
        [(1, "hn", "T", "C", "http://x", "2026-01-01", "abc", "RAW", "2026-01-01")],
        [(10, 1, 0, "chunk text", "[0.1,0.2]", "2026-01-01")],
    ]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_get.return_value = mock_conn

    from src.sync_to_aws import sync_db_to_rds
    result = sync_db_to_rds(dry_run=True)

    assert result == {"documents": 1, "chunks": 1}


@patch("psycopg2.connect")
@patch("src.sync_to_aws._get_remote_dsn", return_value={
    "host": "rds.example.com", "port": 5432, "dbname": "techpulse",
    "user": "postgres", "password": "pw",
})
@patch("src.db.connection.get_connection")
@patch("src.db.connection.put_connection")
def test_sync_db_upserts(mock_put, mock_get, mock_dsn, mock_pg_connect):
    """Full sync reads local and upserts to remote."""
    # Local cursor returns
    local_cursor = MagicMock()
    local_cursor.fetchall.side_effect = [
        [(1, "hn", "T", "C", "http://x", "2026-01-01", "abc123", "INDEXED", "2026-01-01")],
        [(10, 1, 0, "chunk text", "[0.1,0.2]", "2026-01-01")],
    ]
    local_conn = MagicMock()
    local_conn.cursor.return_value.__enter__ = MagicMock(return_value=local_cursor)
    local_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_get.return_value = local_conn

    # Remote cursor
    remote_cursor = MagicMock()
    remote_cursor.rowcount = 1
    # After upsert docs, fetch remote ID map
    remote_cursor.fetchall.side_effect = [
        [(42, "abc123")],  # remote id map
        [None],  # setval documents
        [None],  # setval chunks
    ]
    remote_conn = MagicMock()
    remote_conn.cursor.return_value.__enter__ = MagicMock(return_value=remote_cursor)
    remote_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_pg_connect.return_value = remote_conn

    from src.sync_to_aws import sync_db_to_rds
    result = sync_db_to_rds(dry_run=False)

    assert result["documents"] >= 0
    assert result["chunks"] >= 0
    remote_conn.commit.assert_called_once()
    remote_conn.close.assert_called_once()
