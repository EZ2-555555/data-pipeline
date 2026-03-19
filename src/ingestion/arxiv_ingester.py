"""ArXiv data ingester for TechPulse.

Fetches papers from ArXiv API, computes SHA-256 content hash
for deduplication, and stores raw documents in the database.
"""

import hashlib
import logging

import defusedxml.ElementTree as ET

from src.ingestion._http import get_http_session
from src.db.connection import get_connection, put_connection
from src.config import settings
from src.preprocessing.chunker import normalize_text
from src.storage import write_raw
from src.queue import send_document_message
from src.observability import record_ingestion

logger = logging.getLogger(__name__)

ARXIV_API_URL = "https://export.arxiv.org/api/query"


def compute_content_hash(title: str, abstract: str, published: str) -> str:
    """SHA-256 hash over canonicalized fields for idempotent dedup."""
    canonical = f"{title.strip().lower()}|{abstract.strip().lower()}|{published.strip()}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fetch_arxiv_papers(categories: list[str], max_results: int = 100) -> list[dict]:
    """Fetch recent papers from ArXiv API."""
    cat_query = " OR ".join(f"cat:{c}" for c in categories)

    resp = get_http_session().get(
        ARXIV_API_URL,
        params={
            "search_query": cat_query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        },
        timeout=30,
    )
    resp.raise_for_status()

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        logger.error("Failed to parse ArXiv XML response")
        return []

    papers = []
    for entry in root.findall("atom:entry", ns):
        title = entry.findtext("atom:title", "", ns).strip().replace("\n", " ")
        abstract = entry.findtext("atom:summary", "", ns).strip().replace("\n", " ")
        published = entry.findtext("atom:published", "", ns).strip()
        link = entry.find("atom:id", ns)
        paper_url = link.text.strip() if link is not None else ""

        papers.append({
            "source": "arxiv",
            "title": title,
            "content": abstract,
            "url": paper_url,
            "published_at": published[:10],  # YYYY-MM-DD
            "content_hash": compute_content_hash(title, abstract, published),
        })

    logger.info("Fetched %d papers from ArXiv", len(papers))
    return papers


def ingest_papers(papers: list[dict]) -> int:
    """Insert papers into the database, skipping duplicates."""
    conn = get_connection()
    inserted = 0
    try:
        with conn.cursor() as cur:
            for p in papers:
                p["title"] = normalize_text(p["title"])
                p["content"] = normalize_text(p["content"])
                cur.execute(
                    """
                    INSERT INTO documents (source, title, content, url, published_at, content_hash, state)
                    VALUES (%s, %s, %s, %s, %s, %s, 'RAW')
                    ON CONFLICT (content_hash) DO NOTHING
                    RETURNING id
                    """,
                    (p["source"], p["title"], p["content"], p["url"], p["published_at"], p["content_hash"]),
                )
                if cur.rowcount > 0:
                    inserted += 1
                    doc_id = cur.fetchone()[0]
                    s3_key = write_raw(p)
                    send_document_message(doc_id, s3_key, p["source"])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_connection(conn)

    record_ingestion("arxiv", inserted)
    logger.info("Inserted %d new papers (%d duplicates skipped)", inserted, len(papers) - inserted)
    return inserted


def run():
    """Main entry point for ArXiv ingestion."""
    categories = settings.ARXIV_CATEGORIES.split(",")
    papers = fetch_arxiv_papers(categories, max_results=settings.ARXIV_MAX_RESULTS)
    return ingest_papers(papers)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
