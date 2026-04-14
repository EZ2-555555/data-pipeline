"""Tests for the FastAPI application endpoints."""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    """GET /health returns a JSON response with status field."""
    with patch("src.api.main.deep_health_check", return_value={"status": "ok", "checks": {}}):
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_ask_endpoint_missing_query(client):
    """POST /ask with empty body returns 422."""
    resp = client.post("/ask", json={})
    assert resp.status_code == 422


def test_ask_endpoint_invalid_mode(client):
    """POST /ask with invalid mode returns 422."""
    resp = client.post("/ask", json={"query": "test", "mode": "invalid"})
    assert resp.status_code == 422


def test_ask_endpoint_success(client):
    """POST /ask with valid payload returns answer dict."""
    mock_result = {
        "answer": "Test answer [Source 1]",
        "sources": [{"title": "t", "url": "http://x", "source": "hn", "score": 0.9}],
        "mode": "hybrid",
        "hallucination_check": {"flagged": False},
    }
    with patch("src.api.main.ask", return_value=mock_result):
        resp = client.post("/ask", json={"query": "What is AI?", "mode": "hybrid"})
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert data["mode"] == "hybrid"


def test_ask_query_too_long(client):
    """POST /ask with query exceeding max_length returns 422."""
    resp = client.post("/ask", json={"query": "x" * 2001, "mode": "hybrid"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /dashboard/insights
# ---------------------------------------------------------------------------

def _make_row(source, title, content, url, days_ago=0):
    """Helper: build a DB row tuple for dashboard_insights mocking."""
    pub = date.today() - timedelta(days=days_ago)
    return (source, title, content, url, pub)


SAMPLE_ROWS = [
    _make_row("arxiv", "Attention Is All You Need", "transformer architecture self-attention mechanism", "http://arxiv/1", 1),
    _make_row("hn", "Show HN: Transformer CLI", "transformer command line tool rust performance", "http://hn/1", 2),
    _make_row("devto", "Getting Started with Transformers", "transformer tutorial python huggingface", "http://devto/1", 3),
    _make_row("github", "transformer-lib v2", "transformer library release notes", "http://gh/1", 5),
]


def _patch_db(rows):
    """Context manager that patches get_connection/put_connection with *rows*."""
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = rows
    mock_cur.__enter__ = lambda s: s
    mock_cur.__exit__ = MagicMock(return_value=False)
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    return patch("src.api.main.get_connection", return_value=mock_conn), patch("src.api.main.put_connection")


def test_dashboard_insights_empty(client):
    """GET /dashboard/insights returns skeleton when no documents."""
    p1, p2 = _patch_db([])
    with p1, p2:
        resp = client.get("/dashboard/insights")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_documents_30d"] == 0
    assert data["top_keywords_week"] == []
    assert data["today_highlights"] == []


def test_dashboard_insights_with_docs(client):
    """GET /dashboard/insights returns expected keys with sample rows."""
    p1, p2 = _patch_db(SAMPLE_ROWS)
    with p1, p2:
        resp = client.get("/dashboard/insights?days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_documents_30d"] == len(SAMPLE_ROWS)
    assert "source_mix" in data
    assert "top_keywords_week" in data
    assert "cross_source_buzz" in data
    assert "research_practice_gap" in data
    assert "topic_timeline" in data
    assert "today_highlights" in data
    assert isinstance(data["top_keywords_week"], list)


def test_dashboard_insights_source_filter(client):
    """GET /dashboard/insights?sources=arxiv returns only arxiv docs."""
    p1, p2 = _patch_db(SAMPLE_ROWS)
    with p1, p2:
        resp = client.get("/dashboard/insights?sources=arxiv")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_documents_30d"] == 1


def test_dashboard_insights_invalid_source(client):
    """GET /dashboard/insights?sources=badname returns 422."""
    p1, p2 = _patch_db([])
    with p1, p2:
        resp = client.get("/dashboard/insights?sources=badname")
    assert resp.status_code == 422
