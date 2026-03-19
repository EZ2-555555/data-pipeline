"""Retrieval quality drift detection for TechPulse.

Runs a fixed set of probe queries against the retriever, records mean
similarity over time, and flags when quality drops >10% from the
stored baseline.  Results are persisted in the drift_baselines table
and optionally pushed to CloudWatch.
"""

import json
import logging
import math
from pathlib import Path

from src.db.connection import get_connection, put_connection
from src.retrieval.retriever import hybrid_retrieve
from src.observability import put_metric

logger = logging.getLogger(__name__)

PROBE_PATH = Path(__file__).resolve().parent.parent.parent / "evaluation" / "queries" / "probe_queries.json"
DRIFT_THRESHOLD = 0.10  # 10% relative drop triggers alert


def _load_probes() -> list[dict]:
    with open(PROBE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _get_latest_baseline(conn) -> float | None:
    """Fetch the most recent non-alert mean similarity, or None if no history."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT mean_similarity FROM drift_baselines "
            "WHERE NOT alert_triggered "
            "ORDER BY run_date DESC LIMIT 1"
        )
        row = cur.fetchone()
    return float(row[0]) if row else None


def _get_baseline_history(conn, n: int = 10) -> list[float]:
    """Fetch the last *n* non-alert baseline mean similarities for SPC."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT mean_similarity FROM drift_baselines "
            "WHERE NOT alert_triggered "
            "ORDER BY run_date DESC LIMIT %s",
            (n,),
        )
        rows = cur.fetchall()
    return [float(r[0]) for r in rows]


def _record_run(conn, mean_sim: float, std_sim: float, num_probes: int, alert: bool):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO drift_baselines (mean_similarity, std_similarity, num_probes, alert_triggered) "
            "VALUES (%s, %s, %s, %s)",
            (mean_sim, std_sim, num_probes, alert),
        )
    conn.commit()


def run_drift_check() -> dict:
    """Execute probe queries, compare to baseline, and persist results.

    Returns a dict with current metrics and whether an alert was triggered.
    """
    probes = _load_probes()
    logger.info("Running drift check with %d probe queries", len(probes))

    sims: list[float] = []
    for p in probes:
        results = hybrid_retrieve(p["query"], top_k=5)
        if results:
            avg_sim = sum(r["similarity"] for r in results) / len(results)
            sims.append(avg_sim)
        else:
            sims.append(0.0)

    mean_sim = sum(sims) / len(sims) if sims else 0.0
    std_sim = math.sqrt(sum((s - mean_sim) ** 2 for s in sims) / len(sims)) if sims else 0.0

    conn = get_connection()
    try:
        baseline = _get_latest_baseline(conn)
        alert = False
        alert_reason = None

        if baseline is not None and baseline > 0:
            # --- Check 1: simple relative-drop threshold (10%) ---
            drop = (baseline - mean_sim) / baseline
            if drop > DRIFT_THRESHOLD:
                alert = True
                alert_reason = f"relative drop {drop:.1%}"
                logger.warning(
                    "Drift alert (threshold): mean similarity dropped %.1f%% (%.4f → %.4f, baseline %.4f)",
                    drop * 100, baseline, mean_sim, baseline,
                )

            # --- Check 2: Shewhart 3σ control limits ---
            history = _get_baseline_history(conn, n=10)
            if len(history) >= 3:
                hist_mean = sum(history) / len(history)
                hist_std = math.sqrt(
                    sum((h - hist_mean) ** 2 for h in history) / len(history)
                )
                lcl = hist_mean - 3 * hist_std  # lower control limit
                if mean_sim < lcl:
                    alert = True
                    alert_reason = (
                        alert_reason or ""
                    ) + f"; Shewhart 3σ breach (LCL={lcl:.4f}, value={mean_sim:.4f})"
                    logger.warning(
                        "Drift alert (Shewhart 3σ): mean %.4f below LCL %.4f "
                        "(hist_mean=%.4f, hist_std=%.4f)",
                        mean_sim, lcl, hist_mean, hist_std,
                    )

        _record_run(conn, mean_sim, std_sim, len(probes), alert)
    finally:
        put_connection(conn)

    # Push to CloudWatch (noop when CLOUDWATCH_ENABLED=false)
    put_metric("DriftMeanSimilarity", mean_sim, "None")
    if alert:
        put_metric("DriftAlert", 1, "Count")

    result = {
        "mean_similarity": round(mean_sim, 4),
        "std_similarity": round(std_sim, 4),
        "num_probes": len(probes),
        "baseline": round(baseline, 4) if baseline is not None else None,
        "alert_triggered": alert,
        "alert_reason": alert_reason,
    }
    logger.info("Drift check result: %s", result)
    return result
