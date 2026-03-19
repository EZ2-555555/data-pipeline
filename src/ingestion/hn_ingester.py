"""Hacker News data ingester for TechPulse.

Fetches top stories from the HN Firebase API, computes SHA-256
content hash for deduplication, and stores raw documents.
"""

import hashlib
import logging
from datetime import datetime, timezone

from src.ingestion._http import get_http_session
from src.db.connection import get_connection, put_connection
from src.config import settings
from src.preprocessing.chunker import normalize_text
from src.storage import write_raw
from src.queue import send_document_message
from src.observability import record_ingestion

logger = logging.getLogger(__name__)

HN_BASE_URL = "https://hacker-news.firebaseio.com/v0"


def compute_content_hash(title: str, url: str, timestamp: int) -> str:
    """SHA-256 hash over canonicalized fields for idempotent dedup."""
    canonical = f"{title.strip().lower()}|{url.strip().lower()}|{timestamp}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fetch_top_story_ids(limit: int = 50) -> list[int]:
    """Fetch top story IDs from HN."""
    resp = get_http_session().get(f"{HN_BASE_URL}/topstories.json", timeout=15)
    resp.raise_for_status()
    ids = resp.json()
    return ids[:limit]


def fetch_story(story_id: int) -> dict | None:
    """Fetch a single story by ID."""
    resp = get_http_session().get(f"{HN_BASE_URL}/item/{story_id}.json", timeout=10)
    resp.raise_for_status()
    item = resp.json()
    if item is None or item.get("type") != "story":
        return None
    return item


def fetch_hn_stories(limit: int = 50) -> list[dict]:
    """Fetch recent top stories from Hacker News."""
    story_ids = fetch_top_story_ids(limit)
    stories = []

    for sid in story_ids:
        try:
            item = fetch_story(sid)
            if item is None:
                continue

            title = item.get("title", "")
            url = item.get("url", "")
            timestamp = item.get("time", 0)
            text = item.get("text", "")  # self-post text
            published_at = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")

            stories.append({
                "source": "hn",
                "title": title,
                "content": text if text else title,
                "url": url,
                "published_at": published_at,
                "content_hash": compute_content_hash(title, url, timestamp),
            })
        except Exception:
            logger.warning("Failed to fetch story %d, skipping", sid, exc_info=True)
            continue

    logger.info("Fetched %d stories from Hacker News", len(stories))
    return stories


def ingest_stories(stories: list[dict]) -> int:
    """Insert stories into the database, skipping duplicates."""
    conn = get_connection()
    inserted = 0
    try:
        with conn.cursor() as cur:
            for s in stories:
                s["title"] = normalize_text(s["title"])
                s["content"] = normalize_text(s["content"])
                cur.execute(
                    """
                    INSERT INTO documents (source, title, content, url, published_at, content_hash, state)
                    VALUES (%s, %s, %s, %s, %s, %s, 'RAW')
                    ON CONFLICT (content_hash) DO NOTHING
                    RETURNING id
                    """,
                    (s["source"], s["title"], s["content"], s["url"], s["published_at"], s["content_hash"]),
                )
                if cur.rowcount > 0:
                    inserted += 1
                    doc_id = cur.fetchone()[0]
                    # Write to S3 raw tier
                    s3_key = write_raw(s)
                    # Send SQS message for async processing
                    send_document_message(doc_id, s3_key, s["source"])
        conn.commit()
    finally:
        put_connection(conn)

    record_ingestion("hn", inserted)
    logger.info("Inserted %d new stories (%d duplicates skipped)", inserted, len(stories) - inserted)
    return inserted


def run():
    """Main entry point for HN ingestion."""
    stories = fetch_hn_stories(limit=settings.HN_FETCH_LIMIT)
    return ingest_stories(stories)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
