"""GitHub Trending data ingester for TechPulse.

Fetches recently-starred repositories from the GitHub Search API,
retrieves each repo's README for substantive content, computes
SHA-256 content hash for deduplication, and stores raw documents.

Uses the official GitHub REST API (no auth required for basic use):
  GET https://api.github.com/search/repositories
  GET https://api.github.com/repos/{owner}/{repo}/readme
"""

import base64
import hashlib
import logging
from datetime import datetime, timedelta, timezone

from src.ingestion._http import get_http_session
from src.db.connection import get_connection, put_connection
from src.config import settings
from src.preprocessing.chunker import normalize_text
from src.storage import write_raw
from src.queue import send_document_message
from src.observability import record_ingestion

logger = logging.getLogger(__name__)

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"


def _github_headers() -> dict:
    """Build request headers, including auth token when available."""
    headers = {"Accept": "application/vnd.github+json"}
    token = settings.GITHUB_TOKEN
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

# Broad tech topics aligned with TechPulse emerging technology scope
DEFAULT_QUERIES = [
    "machine learning",
    "large language model",
    "deep learning",
    "web framework",
    "devops",
    "cloud native",
    "distributed systems",
    "database",
    "rust programming",
    "developer tools",
]

# Cap README to avoid storing huge files
MAX_README_CHARS = 5000


def compute_content_hash(full_name: str, description: str, created_at: str) -> str:
    """SHA-256 hash over canonicalized fields for idempotent dedup."""
    canonical = f"{full_name.strip().lower()}|{(description or '').strip().lower()}|{created_at.strip()}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _week_ago_iso() -> str:
    """Return ISO date string for 7 days ago (for 'created' filter)."""
    return (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")


def _fetch_readme(full_name: str) -> str:
    """Fetch the README content for a repo. Returns empty string on failure."""
    try:
        resp = get_http_session().get(
            f"https://api.github.com/repos/{full_name}/readme",
            headers=_github_headers(),
            timeout=10,
        )
        if resp.status_code != 200:
            return ""
        data = resp.json()
        content_b64 = data.get("content", "")
        if not content_b64:
            return ""
        readme_text = base64.b64decode(content_b64).decode("utf-8", errors="replace")
        return readme_text[:MAX_README_CHARS]
    except Exception:
        logger.debug("Could not fetch README for %s", full_name, exc_info=True)
        return ""


def fetch_trending_repos(
    queries: list[str] | None = None,
    per_page: int = 30,
    min_stars: int = 5,
) -> list[dict]:
    """Fetch recently-created, high-star repos with README content."""
    if queries is None:
        queries = DEFAULT_QUERIES

    since = _week_ago_iso()
    seen_ids: set[int] = set()
    repos: list[dict] = []

    for query in queries:
        q = f"{query} created:>{since} stars:>={min_stars}"
        try:
            resp = get_http_session().get(
                GITHUB_SEARCH_URL,
                params={"q": q, "sort": "stars", "order": "desc", "per_page": per_page},
                headers=_github_headers(),
                timeout=15,
            )
            resp.raise_for_status()
        except Exception:
            logger.warning("GitHub search failed for query '%s', skipping", query, exc_info=True)
            continue

        items = resp.json().get("items", [])
        for repo in items:
            repo_id = repo.get("id")
            if repo_id in seen_ids:
                continue
            seen_ids.add(repo_id)

            full_name = repo.get("full_name", "")
            description = repo.get("description") or ""
            html_url = repo.get("html_url", "")
            created = repo.get("created_at", "")
            language = repo.get("language") or ""
            stars = repo.get("stargazers_count", 0)
            topics = repo.get("topics", [])

            # Fetch README for substantive content
            readme = _fetch_readme(full_name)

            # Build content: description header + README body
            header_parts = [description]
            if language:
                header_parts.append(f"Language: {language}")
            if topics:
                header_parts.append(f"Topics: {', '.join(topics)}")
            header_parts.append(f"Stars: {stars}")
            header = " | ".join(header_parts)

            if readme:
                content = f"{header}\n\n{readme}"
            else:
                content = header

            published_date = created[:10] if created else (
                datetime.now(timezone.utc).strftime("%Y-%m-%d")
            )

            repos.append({
                "source": "github",
                "title": full_name,
                "content": content,
                "url": html_url,
                "published_at": published_date,
                "content_hash": compute_content_hash(full_name, description, created),
            })

    logger.info("Fetched %d trending repos from GitHub (%d queries)", len(repos), len(queries))
    return repos


def ingest_repos(repos: list[dict]) -> int:
    """Insert repos into the database, skipping duplicates."""
    conn = get_connection()
    inserted = 0
    try:
        with conn.cursor() as cur:
            for r in repos:
                r["title"] = normalize_text(r["title"])
                r["content"] = normalize_text(r["content"])
                cur.execute(
                    """
                    INSERT INTO documents (source, title, content, url, published_at, content_hash, state)
                    VALUES (%s, %s, %s, %s, %s, %s, 'RAW')
                    ON CONFLICT (content_hash) DO NOTHING
                    RETURNING id
                    """,
                    (r["source"], r["title"], r["content"], r["url"], r["published_at"], r["content_hash"]),
                )
                if cur.rowcount > 0:
                    inserted += 1
                    doc_id = cur.fetchone()[0]
                    s3_key = write_raw(r)
                    send_document_message(doc_id, s3_key, r["source"])
        conn.commit()
    finally:
        put_connection(conn)

    record_ingestion("github", inserted)
    logger.info("Inserted %d new repos (%d duplicates skipped)", inserted, len(repos) - inserted)
    return inserted


def run():
    """Main entry point for GitHub Trending ingestion."""
    repos = fetch_trending_repos()
    return ingest_repos(repos)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
