"""Tests for ingestion modules — hashing, fetching, and ingesting."""

from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from src.ingestion.arxiv_ingester import compute_content_hash as arxiv_hash
from src.ingestion.devto_ingester import compute_content_hash as devto_hash
from src.ingestion.github_ingester import compute_content_hash as github_hash
from src.ingestion.hn_ingester import compute_content_hash as hn_hash
from src.ingestion.rss_ingester import (
    compute_content_hash as rss_hash,
    _strip_html,
    _parse_published,
    fetch_rss_articles,
    ingest_articles,
)


def test_arxiv_hash_deterministic():
    h1 = arxiv_hash("Title A", "Abstract A", "2026-01-01")
    h2 = arxiv_hash("Title A", "Abstract A", "2026-01-01")
    assert h1 == h2


def test_arxiv_hash_case_insensitive():
    h1 = arxiv_hash("Title A", "Abstract A", "2026-01-01")
    h2 = arxiv_hash("TITLE A", "ABSTRACT A", "2026-01-01")
    assert h1 == h2


def test_arxiv_hash_different_content():
    h1 = arxiv_hash("Title A", "Abstract A", "2026-01-01")
    h2 = arxiv_hash("Title B", "Abstract B", "2026-01-02")
    assert h1 != h2


def test_hn_hash_deterministic():
    h1 = hn_hash("Story", "https://example.com", 1700000000)
    h2 = hn_hash("Story", "https://example.com", 1700000000)
    assert h1 == h2


def test_hn_hash_different_content():
    h1 = hn_hash("Story A", "https://a.com", 1700000000)
    h2 = hn_hash("Story B", "https://b.com", 1700000001)
    assert h1 != h2


def test_devto_hash_deterministic():
    h1 = devto_hash("My Article", "A description", "2026-03-16")
    h2 = devto_hash("My Article", "A description", "2026-03-16")
    assert h1 == h2


def test_devto_hash_case_insensitive():
    h1 = devto_hash("My Article", "A description", "2026-03-16")
    h2 = devto_hash("MY ARTICLE", "A DESCRIPTION", "2026-03-16")
    assert h1 == h2


def test_devto_hash_different_content():
    h1 = devto_hash("Article A", "Desc A", "2026-03-16")
    h2 = devto_hash("Article B", "Desc B", "2026-03-17")
    assert h1 != h2


def test_github_hash_deterministic():
    h1 = github_hash("owner/repo", "A cool ML project", "2026-03-10T00:00:00Z")
    h2 = github_hash("owner/repo", "A cool ML project", "2026-03-10T00:00:00Z")
    assert h1 == h2


def test_github_hash_case_insensitive():
    h1 = github_hash("Owner/Repo", "A Cool ML Project", "2026-03-10T00:00:00Z")
    h2 = github_hash("owner/repo", "a cool ml project", "2026-03-10T00:00:00Z")
    assert h1 == h2


def test_github_hash_different_content():
    h1 = github_hash("owner/repo-a", "Desc A", "2026-03-10T00:00:00Z")
    h2 = github_hash("owner/repo-b", "Desc B", "2026-03-11T00:00:00Z")
    assert h1 != h2


def test_rss_hash_deterministic():
    h1 = rss_hash("Breaking: New AI Chip", "Summary of the article", "https://example.com/article")
    h2 = rss_hash("Breaking: New AI Chip", "Summary of the article", "https://example.com/article")
    assert h1 == h2


def test_rss_hash_case_insensitive():
    h1 = rss_hash("Breaking: New AI Chip", "Summary text", "https://example.com/article")
    h2 = rss_hash("BREAKING: NEW AI CHIP", "SUMMARY TEXT", "HTTPS://EXAMPLE.COM/ARTICLE")
    assert h1 == h2


def test_rss_hash_different_content():
    h1 = rss_hash("Article A", "Summary A", "https://example.com/a")
    h2 = rss_hash("Article B", "Summary B", "https://example.com/b")
    assert h1 != h2


# ---------------------------------------------------------------------------
# RSS ingester — _strip_html
# ---------------------------------------------------------------------------

def test_strip_html_removes_tags():
    assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"


def test_strip_html_plain_text():
    assert _strip_html("No HTML here") == "No HTML here"


def test_strip_html_collapses_whitespace():
    assert _strip_html("<div>  too   many   spaces  </div>") == "too many spaces"


# ---------------------------------------------------------------------------
# RSS ingester — _parse_published
# ---------------------------------------------------------------------------

def test_parse_published_from_published_parsed():
    entry = {"published_parsed": (2026, 3, 15, 12, 0, 0, 0, 0, 0)}
    assert _parse_published(entry) == "2026-03-15"


def test_parse_published_from_updated_parsed():
    entry = {"updated_parsed": (2026, 1, 10, 8, 30, 0, 0, 0, 0)}
    assert _parse_published(entry) == "2026-01-10"


def test_parse_published_fallback_to_today():
    entry = {}
    result = _parse_published(entry)
    assert result == datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# RSS ingester — fetch_rss_articles
# ---------------------------------------------------------------------------

@patch("src.ingestion.rss_ingester.feedparser")
def test_fetch_rss_articles_basic(mock_fp):
    mock_fp.parse.return_value = MagicMock(
        bozo=False,
        entries=[
            {
                "link": "https://example.com/art1",
                "title": "AI Breakthrough",
                "summary": "<p>A new model.</p>",
                "published_parsed": (2026, 3, 15, 0, 0, 0, 0, 0, 0),
            },
        ],
        feed={"title": "TechFeed"},
    )
    articles = fetch_rss_articles(feeds=["https://example.com/rss"])
    assert len(articles) == 1
    assert articles[0]["source"] == "rss"
    assert articles[0]["title"] == "[TechFeed] AI Breakthrough"
    assert articles[0]["url"] == "https://example.com/art1"


@patch("src.ingestion.rss_ingester.feedparser")
def test_fetch_rss_articles_deduplicates_by_link(mock_fp):
    entry = {
        "link": "https://example.com/same",
        "title": "Duplicate",
        "summary": "Desc",
        "published_parsed": (2026, 1, 1, 0, 0, 0, 0, 0, 0),
    }
    mock_fp.parse.return_value = MagicMock(
        bozo=False,
        entries=[entry, entry],
        feed={"title": "Feed"},
    )
    articles = fetch_rss_articles(feeds=["https://example.com/rss"])
    assert len(articles) == 1


@patch("src.ingestion.rss_ingester.feedparser")
def test_fetch_rss_articles_skips_bozo_no_entries(mock_fp):
    mock_fp.parse.return_value = MagicMock(
        bozo=True,
        entries=[],
        feed={"title": "BadFeed"},
    )
    articles = fetch_rss_articles(feeds=["https://bad.com/rss"])
    assert articles == []


# ---------------------------------------------------------------------------
# RSS ingester — ingest_articles
# ---------------------------------------------------------------------------

@patch("src.ingestion.rss_ingester.record_ingestion")
@patch("src.ingestion.rss_ingester.send_document_message")
@patch("src.ingestion.rss_ingester.write_raw", return_value="raw/rss/key.json")
@patch("src.ingestion.rss_ingester.put_connection")
@patch("src.ingestion.rss_ingester.get_connection")
def test_ingest_rss_articles(mock_get_conn, mock_put_conn, mock_write_raw, mock_send, mock_record):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.rowcount = 1
    mock_cursor.fetchone.return_value = (42,)
    mock_cursor.__enter__ = lambda s: s
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cursor
    mock_get_conn.return_value = mock_conn

    articles = [{
        "source": "rss",
        "title": "Test Article",
        "content": "Some content",
        "url": "https://example.com/art",
        "published_at": "2026-03-15",
        "content_hash": "abc123",
    }]

    result = ingest_articles(articles)
    assert result == 1
    mock_conn.commit.assert_called_once()
    mock_write_raw.assert_called_once()
    mock_send.assert_called_once_with(42, "raw/rss/key.json", "rss")
    mock_record.assert_called_once_with("rss", 1)
