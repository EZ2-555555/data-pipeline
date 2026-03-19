"""Shared HTTP session with automatic retry for all ingesters."""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_session: requests.Session | None = None


def get_http_session() -> requests.Session:
    """Return a module-level session with retry/back-off configured."""
    global _session
    if _session is None:
        _session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        _session.mount("https://", adapter)
        _session.mount("http://", adapter)
    return _session
