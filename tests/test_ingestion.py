"""Tests for SHA-256 content hashing (deduplication)."""

from src.ingestion.arxiv_ingester import compute_content_hash as arxiv_hash
from src.ingestion.devto_ingester import compute_content_hash as devto_hash
from src.ingestion.github_ingester import compute_content_hash as github_hash
from src.ingestion.hn_ingester import compute_content_hash as hn_hash
from src.ingestion.rss_ingester import compute_content_hash as rss_hash


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
