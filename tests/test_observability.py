"""Tests for src/observability — metrics, health checks, and drift detection."""

from unittest.mock import MagicMock, patch
import pytest


# ===================================================================
# observability/__init__.py — metrics & health
# ===================================================================

# ---------------------------------------------------------------------------
# _get_cw_client
# ---------------------------------------------------------------------------

@patch("src.observability.settings")
def test_get_cw_client_disabled(mock_settings):
    mock_settings.CLOUDWATCH_ENABLED = False
    from src.observability import _get_cw_client
    assert _get_cw_client() is None


# ---------------------------------------------------------------------------
# put_metric
# ---------------------------------------------------------------------------

@patch("src.observability._get_cw_client", return_value=None)
def test_put_metric_no_client(mock_cw):
    from src.observability import put_metric
    put_metric("TestMetric", 42.0, "Count")


@patch("src.observability._get_cw_client")
def test_put_metric_with_client(mock_cw):
    mock_client = MagicMock()
    mock_cw.return_value = mock_client

    from src.observability import put_metric
    put_metric("TestMetric", 5.0, "Count", {"Source": "hn"})

    mock_client.put_metric_data.assert_called_once()
    call_kwargs = mock_client.put_metric_data.call_args[1]
    metric_data = call_kwargs["MetricData"][0]
    assert metric_data["MetricName"] == "TestMetric"
    assert metric_data["Value"] == 5.0


@patch("src.observability._get_cw_client")
def test_put_metric_no_dimensions(mock_cw):
    mock_client = MagicMock()
    mock_cw.return_value = mock_client

    from src.observability import put_metric
    put_metric("PipelineChunks", 10, "Count")

    call_kwargs = mock_client.put_metric_data.call_args[1]
    assert call_kwargs["MetricData"][0]["Dimensions"] == []


# ---------------------------------------------------------------------------
# Convenience recorders
# ---------------------------------------------------------------------------

@patch("src.observability.put_metric")
def test_record_ingestion(mock_put):
    from src.observability import record_ingestion
    record_ingestion("arxiv", 15)
    mock_put.assert_called_once_with("IngestionCount", 15, "Count", {"Source": "arxiv"})


@patch("src.observability.put_metric")
def test_record_pipeline_chunks(mock_put):
    from src.observability import record_pipeline_chunks
    record_pipeline_chunks(50)
    mock_put.assert_called_once_with("PipelineChunks", 50, "Count")


@patch("src.observability.put_metric")
def test_record_pipeline_error(mock_put):
    from src.observability import record_pipeline_error
    record_pipeline_error("test_error")
    mock_put.assert_called_once_with("PipelineErrors", 1, "Count", {"ErrorType": "test_error"})


@patch("src.observability.put_metric")
def test_record_api_latency(mock_put):
    from src.observability import record_api_latency
    record_api_latency(0.123)
    mock_put.assert_called_once_with("ApiLatency", 0.123, "Seconds")


@patch("src.observability.put_metric")
def test_record_hallucination_flag(mock_put):
    from src.observability import record_hallucination_flag
    record_hallucination_flag()
    mock_put.assert_called_once_with("HallucinationFlags", 1, "Count")


# ---------------------------------------------------------------------------
# timed_metric
# ---------------------------------------------------------------------------

@patch("src.observability.put_metric")
def test_timed_metric(mock_put):
    from src.observability import timed_metric

    with timed_metric("TestLatency"):
        pass

    mock_put.assert_called_once()
    call_args = mock_put.call_args
    assert call_args[0][0] == "TestLatency"
    assert call_args[0][2] == "Seconds"
    assert call_args[0][1] >= 0


@patch("src.observability.put_metric")
def test_timed_metric_records_on_exception(mock_put):
    from src.observability import timed_metric
    with pytest.raises(ValueError):
        with timed_metric("ErrorLatency"):
            raise ValueError("boom")
    mock_put.assert_called_once()


# ---------------------------------------------------------------------------
# deep_health_check  (local imports: get_connection, put_connection, generate)
# ---------------------------------------------------------------------------

@patch("src.observability.settings")
@patch("src.orchestrator.llm_backends.generate", return_value="OK")
@patch("src.db.connection.put_connection")
@patch("src.db.connection.get_connection")
def test_deep_health_check_db_ok(mock_get_conn, mock_put_conn, mock_generate, mock_settings):
    mock_settings.S3_ENABLED = False
    mock_settings.SQS_ENABLED = False
    mock_settings.LLM_BACKEND = "ollama"

    mock_cursor = MagicMock()
    mock_cursor.fetchone.side_effect = [(100,), (500,)]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_get_conn.return_value = mock_conn

    from src.observability import deep_health_check
    result = deep_health_check()

    assert result["status"] == "ok"
    assert result["checks"]["database"]["documents"] == 100
    assert result["checks"]["database"]["chunks"] == 500
    assert result["checks"]["s3"]["status"] == "skipped"
    assert result["checks"]["sqs"]["status"] == "skipped"


@patch("src.observability.settings")
@patch("src.orchestrator.llm_backends.generate", return_value="OK")
@patch("src.db.connection.get_connection", side_effect=Exception("DB down"))
def test_deep_health_check_db_error(mock_get_conn, mock_generate, mock_settings):
    mock_settings.S3_ENABLED = False
    mock_settings.SQS_ENABLED = False
    mock_settings.LLM_BACKEND = "ollama"

    from src.observability import deep_health_check
    result = deep_health_check()

    assert result["status"] == "degraded"
    assert result["checks"]["database"]["status"] == "error"


@patch("src.observability.settings")
@patch("src.orchestrator.llm_backends.generate", side_effect=Exception("LLM timeout"))
@patch("src.db.connection.put_connection")
@patch("src.db.connection.get_connection")
def test_deep_health_check_llm_error(mock_get_conn, mock_put_conn, mock_generate, mock_settings):
    mock_settings.S3_ENABLED = False
    mock_settings.SQS_ENABLED = False
    mock_settings.LLM_BACKEND = "ollama"

    mock_cursor = MagicMock()
    mock_cursor.fetchone.side_effect = [(1,), (10,), (50,)]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_get_conn.return_value = mock_conn

    from src.observability import deep_health_check
    result = deep_health_check()

    assert result["status"] == "degraded"
    assert result["checks"]["llm"]["status"] == "error"


# ===================================================================
# observability/drift.py — drift detection
# ===================================================================

# ---------------------------------------------------------------------------
# _load_probes
# ---------------------------------------------------------------------------

def test_load_probes():
    probe_data = [{"query": "test query 1"}, {"query": "test query 2"}]
    with patch("src.observability.drift.open",
               return_value=MagicMock(__enter__=MagicMock(return_value=MagicMock()),
                                      __exit__=MagicMock(return_value=False))):
        with patch("src.observability.drift.json.load", return_value=probe_data):
            from src.observability.drift import _load_probes
            probes = _load_probes()
    assert len(probes) == 2


# ---------------------------------------------------------------------------
# _get_latest_baseline
# ---------------------------------------------------------------------------

def test_get_latest_baseline_exists():
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (0.85,)
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    from src.observability.drift import _get_latest_baseline
    result = _get_latest_baseline(mock_conn)
    assert result == 0.85


def test_get_latest_baseline_none():
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    from src.observability.drift import _get_latest_baseline
    result = _get_latest_baseline(mock_conn)
    assert result is None


# ---------------------------------------------------------------------------
# _get_baseline_history
# ---------------------------------------------------------------------------

def test_get_baseline_history():
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [(0.8,), (0.82,), (0.79,)]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    from src.observability.drift import _get_baseline_history
    result = _get_baseline_history(mock_conn, n=10)
    assert result == [0.8, 0.82, 0.79]


# ---------------------------------------------------------------------------
# _record_run
# ---------------------------------------------------------------------------

def test_record_run():
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    from src.observability.drift import _record_run
    _record_run(mock_conn, 0.85, 0.03, 10, False)

    mock_cursor.execute.assert_called_once()
    mock_conn.commit.assert_called_once()


# ---------------------------------------------------------------------------
# run_drift_check
# ---------------------------------------------------------------------------

@patch("src.observability.drift.put_metric")
@patch("src.observability.drift.put_connection")
@patch("src.observability.drift.get_connection")
@patch("src.observability.drift.hybrid_retrieve")
@patch("src.observability.drift._load_probes")
def test_run_drift_check_no_baseline(mock_probes, mock_retrieve,
                                      mock_get_conn, mock_put_conn, mock_metric):
    mock_probes.return_value = [{"query": "q1"}, {"query": "q2"}]
    mock_retrieve.return_value = [{"similarity": 0.9}, {"similarity": 0.8}]

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None  # no baseline
    mock_cursor.fetchall.return_value = []
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_get_conn.return_value = mock_conn

    from src.observability.drift import run_drift_check
    result = run_drift_check()

    assert result["alert_triggered"] is False
    assert result["num_probes"] == 2
    assert result["mean_similarity"] > 0


@patch("src.observability.drift.put_metric")
@patch("src.observability.drift.put_connection")
@patch("src.observability.drift.get_connection")
@patch("src.observability.drift.hybrid_retrieve")
@patch("src.observability.drift._load_probes")
def test_run_drift_check_alert_triggered(mock_probes, mock_retrieve,
                                          mock_get_conn, mock_put_conn, mock_metric):
    mock_probes.return_value = [{"query": "q1"}]
    mock_retrieve.return_value = [{"similarity": 0.3}]

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (0.9,)  # baseline much higher
    mock_cursor.fetchall.return_value = [(0.9,), (0.88,), (0.91,)]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_get_conn.return_value = mock_conn

    from src.observability.drift import run_drift_check
    result = run_drift_check()

    assert result["alert_triggered"] is True


@patch("src.observability.drift.put_metric")
@patch("src.observability.drift.put_connection")
@patch("src.observability.drift.get_connection")
@patch("src.observability.drift.hybrid_retrieve")
@patch("src.observability.drift._load_probes")
def test_run_drift_check_empty_results(mock_probes, mock_retrieve,
                                        mock_get_conn, mock_put_conn, mock_metric):
    mock_probes.return_value = [{"query": "q1"}]
    mock_retrieve.return_value = []

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None
    mock_cursor.fetchall.return_value = []
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_get_conn.return_value = mock_conn

    from src.observability.drift import run_drift_check
    result = run_drift_check()

    assert result["mean_similarity"] == 0.0


# ---------------------------------------------------------------------------
# Drift simulation scenarios — professor feedback item #10
# ---------------------------------------------------------------------------

@patch("src.observability.drift.put_metric")
@patch("src.observability.drift.put_connection")
@patch("src.observability.drift.get_connection")
@patch("src.observability.drift.hybrid_retrieve")
@patch("src.observability.drift._load_probes")
def test_drift_gradual_degradation_detected(mock_probes, mock_retrieve,
                                             mock_get_conn, mock_put_conn, mock_metric):
    """Simulate gradual quality degradation: baseline=0.85, current=0.70 → 17.6% drop → alert."""
    mock_probes.return_value = [{"query": "q1"}, {"query": "q2"}, {"query": "q3"}]
    # Each query returns results with low similarity (degraded embedding index)
    mock_retrieve.return_value = [{"similarity": 0.68}, {"similarity": 0.72}]

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (0.85,)  # stored baseline is healthy
    # History for Shewhart: stable around 0.85
    mock_cursor.fetchall.return_value = [(0.86,), (0.84,), (0.85,), (0.83,), (0.87,)]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_get_conn.return_value = mock_conn

    from src.observability.drift import run_drift_check
    result = run_drift_check()

    assert result["alert_triggered"] is True
    assert "relative drop" in (result.get("alert_reason") or "")
    assert result["mean_similarity"] < 0.85


@patch("src.observability.drift.put_metric")
@patch("src.observability.drift.put_connection")
@patch("src.observability.drift.get_connection")
@patch("src.observability.drift.hybrid_retrieve")
@patch("src.observability.drift._load_probes")
def test_drift_normal_fluctuation_no_false_alarm(mock_probes, mock_retrieve,
                                                  mock_get_conn, mock_put_conn, mock_metric):
    """Normal ±3% fluctuation around baseline should NOT trigger alert."""
    mock_probes.return_value = [{"query": "q1"}, {"query": "q2"}]
    # Slightly below baseline but within 10% threshold
    mock_retrieve.return_value = [{"similarity": 0.82}, {"similarity": 0.80}]

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (0.85,)  # baseline
    # History for Shewhart: stable around 0.85
    mock_cursor.fetchall.return_value = [(0.86,), (0.84,), (0.85,), (0.83,), (0.87,)]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_get_conn.return_value = mock_conn

    from src.observability.drift import run_drift_check
    result = run_drift_check()

    assert result["alert_triggered"] is False


@patch("src.observability.drift.put_metric")
@patch("src.observability.drift.put_connection")
@patch("src.observability.drift.get_connection")
@patch("src.observability.drift.hybrid_retrieve")
@patch("src.observability.drift._load_probes")
def test_drift_shewhart_breach_detected(mock_probes, mock_retrieve,
                                         mock_get_conn, mock_put_conn, mock_metric):
    """Value within 10% threshold but below Shewhart 3σ LCL should trigger alert."""
    mock_probes.return_value = [{"query": "q1"}, {"query": "q2"}]
    # Tight history: mean=0.85, std≈0.01 → LCL≈0.82
    # current≈0.78 → within 10% (8.2% drop) but below LCL
    mock_retrieve.return_value = [{"similarity": 0.77}, {"similarity": 0.79}]

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (0.85,)
    # Very tight history (low variance) → tight control limits
    mock_cursor.fetchall.return_value = [(0.85,), (0.85,), (0.86,), (0.84,), (0.85,)]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_get_conn.return_value = mock_conn

    from src.observability.drift import run_drift_check
    result = run_drift_check()

    assert result["alert_triggered"] is True
    assert "Shewhart" in (result.get("alert_reason") or "")


@patch("src.observability.drift.put_metric")
@patch("src.observability.drift.put_connection")
@patch("src.observability.drift.get_connection")
@patch("src.observability.drift.hybrid_retrieve")
@patch("src.observability.drift._load_probes")
def test_drift_first_run_establishes_baseline(mock_probes, mock_retrieve,
                                               mock_get_conn, mock_put_conn, mock_metric):
    """First run with no baseline should record without triggering alert."""
    mock_probes.return_value = [{"query": "q1"}, {"query": "q2"}, {"query": "q3"}]
    mock_retrieve.return_value = [{"similarity": 0.82}, {"similarity": 0.88}]

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None  # no prior baseline
    mock_cursor.fetchall.return_value = []    # no history
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_get_conn.return_value = mock_conn

    from src.observability.drift import run_drift_check
    result = run_drift_check()

    assert result["alert_triggered"] is False
    assert result["baseline"] is None
    assert result["mean_similarity"] > 0
    # Confirm it recorded the run
    mock_conn.commit.assert_called_once()


@patch("src.observability.drift.put_metric")
@patch("src.observability.drift.put_connection")
@patch("src.observability.drift.get_connection")
@patch("src.observability.drift.hybrid_retrieve")
@patch("src.observability.drift._load_probes")
def test_drift_catastrophic_drop_all_signals_fire(mock_probes, mock_retrieve,
                                                   mock_get_conn, mock_put_conn, mock_metric):
    """Catastrophic quality drop (0.85 → 0.1) triggers both threshold AND Shewhart."""
    mock_probes.return_value = [{"query": "q1"}, {"query": "q2"}]
    mock_retrieve.return_value = [{"similarity": 0.08}, {"similarity": 0.12}]

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (0.85,)
    mock_cursor.fetchall.return_value = [(0.85,), (0.84,), (0.86,), (0.83,), (0.87,)]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_get_conn.return_value = mock_conn

    from src.observability.drift import run_drift_check
    result = run_drift_check()

    assert result["alert_triggered"] is True
    reason = result.get("alert_reason") or ""
    assert "relative drop" in reason
    assert "Shewhart" in reason
    # Verify CloudWatch alert metric was pushed
    mock_metric.assert_any_call("DriftAlert", 1, "Count")
