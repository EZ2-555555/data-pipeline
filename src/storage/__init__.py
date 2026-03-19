"""S3 medallion storage layer for TechPulse.

Writes data to a three-tier S3 layout:
  raw/<source>/YYYY-MM-DD/<content_hash>.json      — raw ingested docs
  processed/<source>/YYYY-MM-DD/<content_hash>.json — chunked + normalised
  embeddings/<source>/YYYY-MM-DD/<content_hash>.json — embedding metadata

Falls back to a local directory when S3 is unavailable (local dev).
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from src.config import settings

logger = logging.getLogger(__name__)

# Local fallback directory (used when S3 is disabled / unavailable)
_LOCAL_LAKE = Path(os.getenv("LOCAL_LAKE_DIR", "data_lake"))


def _get_s3_client():
    """Return a boto3 S3 client, or None when running without AWS."""
    if not settings.S3_ENABLED:
        return None
    try:
        import boto3

        kwargs = {"region_name": settings.AWS_REGION}
        endpoint = os.getenv("S3_ENDPOINT_URL")  # LocalStack / MinIO
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        return boto3.client("s3", **kwargs)
    except Exception:
        logger.debug("S3 client unavailable — using local fallback")
        return None


def _s3_key(tier: str, source: str, content_hash: str, date_str: str | None = None) -> str:
    """Build a medallion-layout S3 key."""
    date_str = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{tier}/{source}/{date_str}/{content_hash}.json"


def _write_local(key: str, payload: dict) -> str:
    """Fallback: write JSON to a local directory mirroring the S3 layout."""
    path = (_LOCAL_LAKE / key).resolve()
    if not str(path).startswith(str(_LOCAL_LAKE.resolve())):
        raise ValueError(f"Path traversal detected in key: {key}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, default=str), encoding="utf-8")
    logger.debug("Local lake write: %s", path)
    return key


def _read_local(key: str) -> dict | None:
    """Fallback: read JSON from the local data lake."""
    path = (_LOCAL_LAKE / key).resolve()
    if not str(path).startswith(str(_LOCAL_LAKE.resolve())):
        raise ValueError(f"Path traversal detected in key: {key}")
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_raw(document: dict) -> str:
    """Persist a raw ingested document to the raw/ tier.

    Args:
        document: Dict with at least 'source', 'content_hash', and 'published_at'.

    Returns:
        The S3 key (or local path) where the document was written.
    """
    key = _s3_key(
        "raw",
        document["source"],
        document["content_hash"],
        document.get("published_at"),
    )
    client = _get_s3_client()
    if client:
        client.put_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=key,
            Body=json.dumps(document, default=str).encode("utf-8"),
            ContentType="application/json",
        )
        logger.debug("S3 raw write: s3://%s/%s", settings.S3_BUCKET_NAME, key)
        return key
    return _write_local(key, document)


def write_processed(source: str, content_hash: str, chunks: list[str], date_str: str | None = None) -> str:
    """Persist chunked + normalised text to the processed/ tier."""
    key = _s3_key("processed", source, content_hash, date_str)
    payload = {"content_hash": content_hash, "source": source, "chunks": chunks}
    client = _get_s3_client()
    if client:
        client.put_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=key,
            Body=json.dumps(payload, default=str).encode("utf-8"),
            ContentType="application/json",
        )
        logger.debug("S3 processed write: s3://%s/%s", settings.S3_BUCKET_NAME, key)
        return key
    return _write_local(key, payload)


def write_embeddings(source: str, content_hash: str, chunk_count: int, date_str: str | None = None) -> str:
    """Persist embedding metadata to the embeddings/ tier."""
    key = _s3_key("embeddings", source, content_hash, date_str)
    payload = {
        "content_hash": content_hash,
        "source": source,
        "chunk_count": chunk_count,
        "indexed_at": datetime.now(timezone.utc).isoformat(),
    }
    client = _get_s3_client()
    if client:
        client.put_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=key,
            Body=json.dumps(payload, default=str).encode("utf-8"),
            ContentType="application/json",
        )
        logger.debug("S3 embeddings write: s3://%s/%s", settings.S3_BUCKET_NAME, key)
        return key
    return _write_local(key, payload)


def read_raw(key: str) -> dict | None:
    """Read a raw document from S3 (or local fallback)."""
    client = _get_s3_client()
    if client:
        try:
            resp = client.get_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
            return json.loads(resp["Body"].read().decode("utf-8"))
        except client.exceptions.NoSuchKey:
            return None
    return _read_local(key)
