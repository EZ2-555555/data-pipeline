"""RSS/Atom feed ingester for TechPulse.

Fetches articles from curated tech news RSS feeds, computes SHA-256
content hash for deduplication, and stores raw documents in the database.

Uses feedparser for robust RSS/Atom parsing across all major outlets.
"""

import hashlib
import logging
import re
from datetime import datetime, timezone

import feedparser

from src.db.connection import get_connection, put_connection
from src.preprocessing.chunker import normalize_text
from src.storage import write_raw
from src.queue import send_document_message
from src.observability import record_ingestion

logger = logging.getLogger(__name__)

# Curated tech news feeds — stable, permanent URLs, no auth required
DEFAULT_FEEDS = [
    # Major tech news outlets
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://www.theverge.com/rss/index.xml",
    "https://techcrunch.com/feed/",
    "https://www.wired.com/feed/rss",
    # Engineering & deep-tech
    "https://spectrum.ieee.org/feeds/feed.rss",
    "https://thenewstack.io/feed/",
    "https://blog.pragmaticengineer.com/rss/",
    # InfoSec
    "https://www.bleepingcomputer.com/feed/",
    "https://krebsonsecurity.com/feed/",
    # AI / ML specific
    "https://news.mit.edu/topic/mitartificial-intelligence2-rss.xml",
]

FEED_TIMEOUT = 20  # seconds

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    clean = _HTML_TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", clean).strip()


def compute_content_hash(title: str, summary: str, link: str) -> str:
    """SHA-256 hash over canonicalized fields for idempotent dedup.

    Uses link (URL) as an identity anchor since RSS GUIDs can be
    inconsistent across feeds.
    """
    canonical = f"{title.strip().lower()}|{summary.strip().lower()}|{link.strip().lower()}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _parse_published(entry: dict) -> str:
    """Extract a YYYY-MM-DD date from an RSS entry."""
    for field in ("published_parsed", "updated_parsed"):
        parsed = entry.get(field)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc).strftime("%Y-%m-%d")
            except Exception:
                pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def fetch_rss_articles(feeds: list[str] | None = None) -> list[dict]:
    """Fetch and normalize articles from all configured RSS feeds."""
    if feeds is None:
        feeds = DEFAULT_FEEDS

    seen_links: set[str] = set()
    articles: list[dict] = []

    for feed_url in feeds:
        try:
            parsed = feedparser.parse(feed_url, request_headers={"User-Agent": "TechPulse/1.0"})
        except Exception:
            logger.warning("Failed to parse feed '%s', skipping", feed_url, exc_info=True)
            continue

        if parsed.bozo and not parsed.entries:
            logger.warning("Feed '%s' returned no entries (bozo=%s)", feed_url, parsed.bozo_exception)
            continue

        feed_name = parsed.feed.get("title", feed_url)

        for entry in parsed.entries:
            link = entry.get("link", "")
            if not link or link in seen_links:
                continue
            seen_links.add(link)

            title = entry.get("title", "").strip()
            summary = _strip_html(entry.get("summary", ""))
            if not title:
                continue

            content = summary if summary else title
            published_date = _parse_published(entry)

            articles.append({
                "source": "rss",
                "title": f"[{feed_name}] {title}",
                "content": content,
                "url": link,
                "published_at": published_date,
                "content_hash": compute_content_hash(title, summary, link),
            })

    logger.info("Fetched %d articles from %d RSS feeds", len(articles), len(feeds))
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
                    ON CONFLICT (content_hash) DO NOTHING
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
    finally:
        put_connection(conn)

    record_ingestion("rss", inserted)
    logger.info("Inserted %d new articles (%d duplicates skipped)", inserted, len(articles) - inserted)
    return inserted


def run():
    """Main entry point for RSS ingestion."""
    articles = fetch_rss_articles()
    return ingest_articles(articles)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
