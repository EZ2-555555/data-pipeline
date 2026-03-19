"""Tests for src/storage/__init__.py — S3 medallion storage layer."""

import json
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# _s3_key
# ---------------------------------------------------------------------------

def test_s3_key_format():
    from src.storage import _s3_key
    key = _s3_key("raw", "arxiv", "abc123", "2026-01-15")
    assert key == "raw/arxiv/2026-01-15/abc123.json"


def test_s3_key_uses_today_when_no_date():
    from src.storage import _s3_key
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = _s3_key("processed", "hn", "xyz789")
    assert key == f"processed/hn/{today}/xyz789.json"


def test_s3_key_tiers():
    from src.storage import _s3_key
    for tier in ["raw", "processed", "embeddings"]:
        key = _s3_key(tier, "arxiv", "hash1", "2026-01-01")
        assert key.startswith(f"{tier}/")


# ---------------------------------------------------------------------------
# _write_local / _read_local
# ---------------------------------------------------------------------------

def test_write_local_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr("src.storage._LOCAL_LAKE", tmp_path)
    from src.storage import _write_local
    payload = {"foo": "bar", "num": 42}
    result = _write_local("raw/hn/2026-01-01/abc.json", payload)
    expected = tmp_path / "raw/hn/2026-01-01/abc.json"
    assert expected.exists()
    assert json.loads(expected.read_text()) == payload
    assert result == "raw/hn/2026-01-01/abc.json"


def test_write_local_creates_nested_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr("src.storage._LOCAL_LAKE", tmp_path)
    from src.storage import _write_local
    _write_local("a/b/c/d/hash.json", {"x": 1})
    assert (tmp_path / "a/b/c/d/hash.json").exists()


def test_read_local_existing(tmp_path, monkeypatch):
    monkeypatch.setattr("src.storage._LOCAL_LAKE", tmp_path)
    from src.storage import _write_local, _read_local
    payload = {"title": "Test", "source": "arxiv"}
    _write_local("raw/arxiv/2026-01-01/hash1.json", payload)
    result = _read_local("raw/arxiv/2026-01-01/hash1.json")
    assert result == payload


def test_read_local_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr("src.storage._LOCAL_LAKE", tmp_path)
    from src.storage import _read_local
    result = _read_local("raw/hn/2026-01-01/nonexistent.json")
    assert result is None


# ---------------------------------------------------------------------------
# _get_s3_client
# ---------------------------------------------------------------------------

def test_get_s3_client_returns_none_when_disabled():
    from src.storage import _get_s3_client
    with patch("src.storage.settings") as mock_settings:
        mock_settings.S3_ENABLED = False
        assert _get_s3_client() is None


def test_get_s3_client_returns_client_when_enabled():
    from src.storage import _get_s3_client
    mock_client = MagicMock()
    with patch("src.storage.settings") as mock_settings, \
         patch("boto3.client", return_value=mock_client):
        mock_settings.S3_ENABLED = True
        mock_settings.AWS_REGION = "us-east-1"
        client = _get_s3_client()
    assert client == mock_client


def test_get_s3_client_returns_none_on_import_error():
    from src.storage import _get_s3_client
    with patch("src.storage.settings") as mock_settings, \
         patch("boto3.client", side_effect=Exception("no boto3")):
        mock_settings.S3_ENABLED = True
        mock_settings.AWS_REGION = "us-east-1"
        result = _get_s3_client()
    assert result is None


# ---------------------------------------------------------------------------
# write_raw
# ---------------------------------------------------------------------------

def test_write_raw_local_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr("src.storage._LOCAL_LAKE", tmp_path)
    from src.storage import write_raw
    doc = {"source": "hn", "content_hash": "hash1", "published_at": "2026-01-01", "title": "Test"}
    with patch("src.storage._get_s3_client", return_value=None):
        key = write_raw(doc)
    assert "raw/hn" in key
    assert "hash1.json" in key


def test_write_raw_s3_path():
    mock_client = MagicMock()
    doc = {"source": "arxiv", "content_hash": "abc123", "published_at": "2026-01-15", "title": "AI Paper"}
    with patch("src.storage._get_s3_client", return_value=mock_client), \
         patch("src.storage.settings") as mock_settings:
        mock_settings.S3_BUCKET_NAME = "my-bucket"
        from src.storage import write_raw
        write_raw(doc)
    mock_client.put_object.assert_called_once()
    call_kwargs = mock_client.put_object.call_args[1]
    assert call_kwargs["Bucket"] == "my-bucket"
    assert "raw/arxiv" in call_kwargs["Key"]
    assert call_kwargs["ContentType"] == "application/json"


def test_write_raw_no_published_at(tmp_path, monkeypatch):
    monkeypatch.setattr("src.storage._LOCAL_LAKE", tmp_path)
    from src.storage import write_raw
    doc = {"source": "hn", "content_hash": "hash999"}
    with patch("src.storage._get_s3_client", return_value=None):
        key = write_raw(doc)
    assert "hash999.json" in key


# ---------------------------------------------------------------------------
# write_processed
# ---------------------------------------------------------------------------

def test_write_processed_local_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr("src.storage._LOCAL_LAKE", tmp_path)
    from src.storage import write_processed
    with patch("src.storage._get_s3_client", return_value=None):
        key = write_processed("hn", "hash2", ["chunk1", "chunk2"], "2026-01-01")
    assert "processed/hn" in key
    assert "hash2.json" in key
    written = json.loads((tmp_path / key).read_text())
    assert written["chunks"] == ["chunk1", "chunk2"]
    assert written["source"] == "hn"


def test_write_processed_s3_path():
    mock_client = MagicMock()
    with patch("src.storage._get_s3_client", return_value=mock_client), \
         patch("src.storage.settings") as mock_settings:
        mock_settings.S3_BUCKET_NAME = "my-bucket"
        from src.storage import write_processed
        write_processed("arxiv", "hashABC", ["a", "b"], "2026-02-01")
    mock_client.put_object.assert_called_once()
    call_kwargs = mock_client.put_object.call_args[1]
    assert "processed/arxiv" in call_kwargs["Key"]
    body = json.loads(call_kwargs["Body"].decode())
    assert body["chunks"] == ["a", "b"]


# ---------------------------------------------------------------------------
# write_embeddings
# ---------------------------------------------------------------------------

def test_write_embeddings_local_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr("src.storage._LOCAL_LAKE", tmp_path)
    from src.storage import write_embeddings
    with patch("src.storage._get_s3_client", return_value=None):
        key = write_embeddings("hn", "hash3", 5, "2026-01-01")
    assert "embeddings/hn" in key
    written = json.loads((tmp_path / key).read_text())
    assert written["chunk_count"] == 5
    assert "indexed_at" in written


def test_write_embeddings_s3_path():
    mock_client = MagicMock()
    with patch("src.storage._get_s3_client", return_value=mock_client), \
         patch("src.storage.settings") as mock_settings:
        mock_settings.S3_BUCKET_NAME = "my-bucket"
        from src.storage import write_embeddings
        write_embeddings("arxiv", "hashXYZ", 10, "2026-01-01")
    mock_client.put_object.assert_called_once()
    call_kwargs = mock_client.put_object.call_args[1]
    assert "embeddings/arxiv" in call_kwargs["Key"]
    body = json.loads(call_kwargs["Body"].decode())
    assert body["chunk_count"] == 10


# ---------------------------------------------------------------------------
# read_raw
# ---------------------------------------------------------------------------

def test_read_raw_local_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr("src.storage._LOCAL_LAKE", tmp_path)
    from src.storage import write_raw, read_raw
    doc = {"source": "hn", "content_hash": "readhash", "title": "Story"}
    with patch("src.storage._get_s3_client", return_value=None):
        key = write_raw(doc)
        result = read_raw(key)
    assert result["title"] == "Story"


def test_read_raw_local_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("src.storage._LOCAL_LAKE", tmp_path)
    from src.storage import read_raw
    with patch("src.storage._get_s3_client", return_value=None):
        result = read_raw("raw/hn/2026-01-01/nonexistent.json")
    assert result is None


def test_read_raw_s3_success():
    mock_client = MagicMock()
    payload = {"title": "S3 doc", "source": "arxiv"}
    mock_client.get_object.return_value = {
        "Body": MagicMock(read=MagicMock(return_value=json.dumps(payload).encode()))
    }
    with patch("src.storage._get_s3_client", return_value=mock_client), \
         patch("src.storage.settings") as mock_settings:
        mock_settings.S3_BUCKET_NAME = "my-bucket"
        from src.storage import read_raw
        result = read_raw("raw/arxiv/2026-01-01/somehash.json")
    assert result == payload


def test_read_raw_s3_missing_key():
    mock_client = MagicMock()
    mock_client.exceptions.NoSuchKey = Exception
    mock_client.get_object.side_effect = mock_client.exceptions.NoSuchKey("not found")
    with patch("src.storage._get_s3_client", return_value=mock_client), \
         patch("src.storage.settings") as mock_settings:
        mock_settings.S3_BUCKET_NAME = "my-bucket"
        from src.storage import read_raw
        result = read_raw("raw/hn/2026-01-01/missing.json")
    assert result is None
