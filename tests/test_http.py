"""Tests for src/ingestion/_http.py — shared HTTP session."""




def test_get_http_session_creates_session():
    import src.ingestion._http as http_mod
    http_mod._session = None  # reset singleton

    session = http_mod.get_http_session()
    assert session is not None
    # Should have retry adapters mounted
    assert "https://" in session.adapters
    assert "http://" in session.adapters


def test_get_http_session_reuses_singleton():
    import src.ingestion._http as http_mod
    http_mod._session = None  # reset

    s1 = http_mod.get_http_session()
    s2 = http_mod.get_http_session()
    assert s1 is s2


def test_get_http_session_retry_config():
    import src.ingestion._http as http_mod
    http_mod._session = None  # reset

    session = http_mod.get_http_session()
    adapter = session.get_adapter("https://example.com")
    retry = adapter.max_retries
    assert retry.total == 3
    assert retry.backoff_factor == 1
    assert 429 in retry.status_forcelist
