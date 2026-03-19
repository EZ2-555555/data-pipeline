"""Tests for src/scheduler.py — run_cycle logic and helper functions."""

from unittest.mock import patch

from src.scheduler import _now, run_cycle


# ---------------------------------------------------------------------------
# _now()
# ---------------------------------------------------------------------------

def test_now_returns_string():
    result = _now()
    assert isinstance(result, str)
    assert "UTC" in result


def test_now_format():
    result = _now()
    # Should match YYYY-MM-DD HH:MM:SS UTC
    import re
    assert re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC", result)


# ---------------------------------------------------------------------------
# run_cycle — happy path
# ---------------------------------------------------------------------------

@patch("src.scheduler.run_drift_check", return_value={"alert_triggered": False})
@patch("src.scheduler.run_pipeline", return_value=10)
@patch("src.scheduler.ingest_rss", return_value=3)
@patch("src.scheduler.ingest_github", return_value=2)
@patch("src.scheduler.ingest_devto", return_value=5)
@patch("src.scheduler.ingest_hn", return_value=8)
@patch("src.scheduler.settings")
def test_run_cycle_all_success(mock_settings, mock_hn, mock_devto, mock_github,
                                mock_rss, mock_pipeline, mock_drift):
    mock_settings.SQS_ENABLED = False
    run_cycle(run_arxiv=False)
    mock_hn.assert_called_once()
    mock_devto.assert_called_once()
    mock_github.assert_called_once()
    mock_rss.assert_called_once()
    mock_pipeline.assert_called_once()


@patch("src.scheduler.run_drift_check", return_value={"alert_triggered": False})
@patch("src.scheduler.ingest_arxiv", return_value=15)
@patch("src.scheduler.run_pipeline", return_value=10)
@patch("src.scheduler.ingest_rss", return_value=3)
@patch("src.scheduler.ingest_github", return_value=2)
@patch("src.scheduler.ingest_devto", return_value=5)
@patch("src.scheduler.ingest_hn", return_value=8)
@patch("src.scheduler.settings")
def test_run_cycle_with_arxiv(mock_settings, mock_hn, mock_devto, mock_github,
                               mock_rss, mock_pipeline, mock_arxiv, mock_drift):
    mock_settings.SQS_ENABLED = False
    run_cycle(run_arxiv=True)
    mock_arxiv.assert_called_once()
    mock_drift.assert_called_once()


@patch("src.scheduler.run_drift_check", return_value={"alert_triggered": False})
@patch("src.scheduler.ingest_arxiv", return_value=0)
@patch("src.scheduler.run_pipeline", return_value=0)
@patch("src.scheduler.ingest_rss", return_value=0)
@patch("src.scheduler.ingest_github", return_value=0)
@patch("src.scheduler.ingest_devto", return_value=0)
@patch("src.scheduler.ingest_hn", return_value=0)
@patch("src.scheduler.settings")
def test_run_cycle_arxiv_skipped_when_false(mock_settings, mock_hn, mock_devto,
                                             mock_github, mock_rss, mock_pipeline,
                                             mock_arxiv, mock_drift):
    mock_settings.SQS_ENABLED = False
    run_cycle(run_arxiv=False)
    mock_arxiv.assert_not_called()
    mock_drift.assert_not_called()


# ---------------------------------------------------------------------------
# run_cycle — individual ingester failures are isolated
# ---------------------------------------------------------------------------

@patch("src.scheduler.run_drift_check", return_value={"alert_triggered": False})
@patch("src.scheduler.run_pipeline", return_value=0)
@patch("src.scheduler.ingest_rss", return_value=0)
@patch("src.scheduler.ingest_github", return_value=0)
@patch("src.scheduler.ingest_devto", return_value=0)
@patch("src.scheduler.ingest_hn", side_effect=RuntimeError("HN down"))
@patch("src.scheduler.settings")
def test_run_cycle_hn_failure_does_not_stop_others(mock_settings, mock_hn, mock_devto,
                                                    mock_github, mock_rss, mock_pipeline,
                                                    mock_drift):
    mock_settings.SQS_ENABLED = False
    run_cycle(run_arxiv=False)  # should not raise
    mock_devto.assert_called_once()
    mock_github.assert_called_once()
    mock_rss.assert_called_once()
    mock_pipeline.assert_called_once()


@patch("src.scheduler.run_drift_check", return_value={"alert_triggered": False})
@patch("src.scheduler.run_pipeline", return_value=0)
@patch("src.scheduler.ingest_rss", return_value=0)
@patch("src.scheduler.ingest_github", return_value=0)
@patch("src.scheduler.ingest_devto", side_effect=Exception("DEV.to error"))
@patch("src.scheduler.ingest_hn", return_value=0)
@patch("src.scheduler.settings")
def test_run_cycle_devto_failure_isolated(mock_settings, mock_hn, mock_devto,
                                          mock_github, mock_rss, mock_pipeline,
                                          mock_drift):
    mock_settings.SQS_ENABLED = False
    run_cycle(run_arxiv=False)
    mock_github.assert_called_once()
    mock_rss.assert_called_once()


@patch("src.scheduler.run_drift_check", return_value={"alert_triggered": False})
@patch("src.scheduler.run_pipeline", return_value=0)
@patch("src.scheduler.ingest_rss", side_effect=Exception("RSS down"))
@patch("src.scheduler.ingest_github", return_value=0)
@patch("src.scheduler.ingest_devto", return_value=0)
@patch("src.scheduler.ingest_hn", return_value=0)
@patch("src.scheduler.settings")
def test_run_cycle_rss_failure_isolated(mock_settings, mock_hn, mock_devto,
                                         mock_github, mock_rss, mock_pipeline,
                                         mock_drift):
    mock_settings.SQS_ENABLED = False
    run_cycle(run_arxiv=False)
    mock_pipeline.assert_called_once()


@patch("src.scheduler.run_drift_check", return_value={"alert_triggered": False})
@patch("src.scheduler.ingest_arxiv", side_effect=Exception("ArXiv timeout"))
@patch("src.scheduler.run_pipeline", return_value=0)
@patch("src.scheduler.ingest_rss", return_value=0)
@patch("src.scheduler.ingest_github", return_value=0)
@patch("src.scheduler.ingest_devto", return_value=0)
@patch("src.scheduler.ingest_hn", return_value=0)
@patch("src.scheduler.settings")
def test_run_cycle_arxiv_failure_isolated(mock_settings, mock_hn, mock_devto,
                                           mock_github, mock_rss, mock_pipeline,
                                           mock_arxiv, mock_drift):
    mock_settings.SQS_ENABLED = False
    run_cycle(run_arxiv=True)  # should not raise
    mock_drift.assert_called_once()


# ---------------------------------------------------------------------------
# run_cycle — pipeline modes
# ---------------------------------------------------------------------------

@patch("src.scheduler.run_drift_check", return_value={"alert_triggered": False})
@patch("src.scheduler.process_sqs_batch", side_effect=[3, 2, 0])
@patch("src.scheduler.ingest_rss", return_value=0)
@patch("src.scheduler.ingest_github", return_value=0)
@patch("src.scheduler.ingest_devto", return_value=0)
@patch("src.scheduler.ingest_hn", return_value=0)
@patch("src.scheduler.settings")
def test_run_cycle_sqs_mode_drains_queue(mock_settings, mock_hn, mock_devto,
                                          mock_github, mock_rss, mock_sqs, mock_drift):
    mock_settings.SQS_ENABLED = True
    run_cycle(run_arxiv=False)
    assert mock_sqs.call_count == 3  # called until 0 returned


@patch("src.scheduler.run_drift_check", return_value={"alert_triggered": False})
@patch("src.scheduler.process_sqs_batch", return_value=0)
@patch("src.scheduler.ingest_rss", return_value=0)
@patch("src.scheduler.ingest_github", return_value=0)
@patch("src.scheduler.ingest_devto", return_value=0)
@patch("src.scheduler.ingest_hn", return_value=0)
@patch("src.scheduler.settings")
def test_run_cycle_sqs_mode_empty_queue(mock_settings, mock_hn, mock_devto,
                                         mock_github, mock_rss, mock_sqs, mock_drift):
    mock_settings.SQS_ENABLED = True
    run_cycle(run_arxiv=False)
    assert mock_sqs.call_count == 1  # one call returns 0, loop exits


@patch("src.scheduler.record_pipeline_error")
@patch("src.scheduler.run_drift_check", return_value={"alert_triggered": False})
@patch("src.scheduler.run_pipeline", side_effect=Exception("DB error"))
@patch("src.scheduler.ingest_rss", return_value=0)
@patch("src.scheduler.ingest_github", return_value=0)
@patch("src.scheduler.ingest_devto", return_value=0)
@patch("src.scheduler.ingest_hn", return_value=0)
@patch("src.scheduler.settings")
def test_run_cycle_pipeline_failure_records_error(mock_settings, mock_hn, mock_devto,
                                                   mock_github, mock_rss, mock_pipeline,
                                                   mock_drift, mock_error):
    mock_settings.SQS_ENABLED = False
    run_cycle(run_arxiv=False)  # should not raise
    mock_error.assert_called_once_with("scheduler_pipeline")


# ---------------------------------------------------------------------------
# run_cycle — drift check behaviour
# ---------------------------------------------------------------------------

@patch("src.scheduler.run_drift_check", return_value={"alert_triggered": True})
@patch("src.scheduler.ingest_arxiv", return_value=0)
@patch("src.scheduler.run_pipeline", return_value=0)
@patch("src.scheduler.ingest_rss", return_value=0)
@patch("src.scheduler.ingest_github", return_value=0)
@patch("src.scheduler.ingest_devto", return_value=0)
@patch("src.scheduler.ingest_hn", return_value=0)
@patch("src.scheduler.settings")
def test_run_cycle_drift_alert_triggered(mock_settings, mock_hn, mock_devto,
                                          mock_github, mock_rss, mock_pipeline,
                                          mock_arxiv, mock_drift):
    mock_settings.SQS_ENABLED = False
    run_cycle(run_arxiv=True)  # should not raise even with alert
    mock_drift.assert_called_once()


@patch("src.scheduler.run_drift_check", side_effect=Exception("drift error"))
@patch("src.scheduler.ingest_arxiv", return_value=0)
@patch("src.scheduler.run_pipeline", return_value=0)
@patch("src.scheduler.ingest_rss", return_value=0)
@patch("src.scheduler.ingest_github", return_value=0)
@patch("src.scheduler.ingest_devto", return_value=0)
@patch("src.scheduler.ingest_hn", return_value=0)
@patch("src.scheduler.settings")
def test_run_cycle_drift_failure_isolated(mock_settings, mock_hn, mock_devto,
                                           mock_github, mock_rss, mock_pipeline,
                                           mock_arxiv, mock_drift):
    mock_settings.SQS_ENABLED = False
    run_cycle(run_arxiv=True)  # should not raise
