"""Tests for the FastAPI application endpoints."""

from unittest.mock import patch

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
