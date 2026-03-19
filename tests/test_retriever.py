"""Tests for the retrieval module."""

from datetime import datetime, timezone

import pytest

from src.retrieval.retriever import (
    _compute_keyword_overlap,
    _compute_recency_weight,
)


class TestKeywordOverlap:
    def test_full_overlap(self):
        assert _compute_keyword_overlap("hello world", "hello world foo bar") == 1.0

    def test_partial_overlap(self):
        score = _compute_keyword_overlap("hello world", "hello foo")
        assert score == pytest.approx(0.5)

    def test_no_overlap(self):
        assert _compute_keyword_overlap("hello", "goodbye") == 0.0

    def test_empty_query(self):
        assert _compute_keyword_overlap("", "some text") == 0.0

    def test_case_insensitive(self):
        assert _compute_keyword_overlap("Hello World", "hello world") == 1.0


class TestRecencyWeight:
    def test_recent_date_high_weight(self):
        recent = datetime.now(timezone.utc)
        weight = _compute_recency_weight(recent, 0.01)
        assert weight > 0.99

    def test_old_date_low_weight(self):
        from datetime import timedelta
        old = datetime.now(timezone.utc) - timedelta(days=365)
        weight = _compute_recency_weight(old, 0.01)
        assert weight < 0.05

    def test_none_date_returns_zero(self):
        assert _compute_recency_weight(None, 0.01) == 0.0

    def test_date_object(self):
        """date (not datetime) objects should also work."""
        from datetime import date
        today = date.today()
        weight = _compute_recency_weight(today, 0.01)
        assert weight > 0.99
