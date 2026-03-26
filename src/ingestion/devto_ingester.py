"""DEV.to data ingester for TechPulse.

Fetches recent articles from the DEV.to public API, computes SHA-256
content hash for deduplication, and stores raw documents in the database.

API docs: https://developers.forem.com/api/v1
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

DEVTO_API_URL = "https://dev.to/api/articles"


def compute_content_hash(title: str, body: str, published_at: str) -> str:
    """SHA-256 hash over canonicalized fields for idempotent dedup."""
    canonical = f"{title.strip().lower()}|{body.strip().lower()}|{published_at.strip()}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _fetch_article_body(article_id: int) -> str:
    """Fetch full article body_markdown from DEV.to single-article endpoint."""
    try:
        resp = get_http_session().get(
            f"{DEVTO_API_URL}/{article_id}",
            headers={"Accept": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("body_markdown", "") or ""
    except Exception:
        logger.debug("Failed to fetch body for article %d", article_id)
        return ""


def fetch_articles_by_tag(tag: str, per_page: int = 30) -> list[dict]:
    """Fetch recent articles for a single tag from DEV.to."""
    resp = get_http_session().get(
        DEVTO_API_URL,
        params={"tag": tag, "per_page": per_page, "top": 7},
        headers={"Accept": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_devto_articles(
    tags: list[str] | None = None,
    per_page: int | None = None,
) -> list[dict]:
    """Fetch recent tech articles from DEV.to across multiple tags."""
    if tags is None:
        tags = settings.DEVTO_TAGS.split(",")
    if per_page is None:
        per_page = settings.DEVTO_PER_PAGE

    seen_ids: set[int] = set()
    articles: list[dict] = []

    for tag in tags:
        try:
            raw = fetch_articles_by_tag(tag, per_page)
        except Exception:
            logger.warning("Failed to fetch DEV.to tag '%s', skipping", tag, exc_info=True)
            continue

        for item in raw:
            article_id = item.get("id")
            if article_id in seen_ids:
                continue
            seen_ids.add(article_id)

            title = item.get("title", "")
            description = item.get("description", "")
            url = item.get("url", "")
            published = item.get("published_at", "")

            # Fetch full article body for richer chunks
            body = _fetch_article_body(article_id) if article_id else ""
            # Cap body at 8000 chars to avoid oversized documents
            content = body[:8000] if body else (description if description else title)

            published_date = published[:10] if published else (
                datetime.now(timezone.utc).strftime("%Y-%m-%d")
            )

            articles.append({
                "source": "devto",
                "title": title,
                "content": content,
                "url": url,
                "published_at": published_date,
                "content_hash": compute_content_hash(title, content, published),
            })

    logger.info("Fetched %d articles from DEV.to (%d tags)", len(articles), len(tags))
    return articles


def ingest_articles(articles: list[dict]) -> int:
    """Insert articles into the database, skipping duplicates."""
    conn = get_connection()
    inserted = 0
    try:
        with conn.cursor() as cur:
            for a in articles:
                a["title"] = normalize_text(a["title"])
                a["content"] = normalize_text(a["content"])
                cur.execute(
                    """
                    INSERT INTO documents (source, title, content, url, published_at, content_hash, state)
                    VALUES (%s, %s, %s, %s, %s, %s, 'RAW')
                    ON CONFLICT DO NOTHING
                    RETURNING id
                    """,
                    (a["source"], a["title"], a["content"], a["url"], a["published_at"], a["content_hash"]),
                )
                if cur.rowcount > 0:
                    inserted += 1
                    doc_id = cur.fetchone()[0]
                    s3_key = write_raw(a)
                    send_document_message(doc_id, s3_key, a["source"])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_connection(conn)

    record_ingestion("devto", inserted)
    logger.info("Inserted %d new articles (%d duplicates skipped)", inserted, len(articles) - inserted)
    return inserted


def run():
    """Main entry point for DEV.to ingestion."""
    articles = fetch_devto_articles()
    return ingest_articles(articles)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
