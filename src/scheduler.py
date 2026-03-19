"""Scheduled ingestion + processing for TechPulse.

Runs HN + DEV.to ingestion every 30 minutes and ArXiv every 12 hours.
After each ingestion cycle, processes any RAW documents through
the chunk+embed pipeline.

Run with: python -m src.scheduler
"""

import logging
import time
from datetime import datetime, timezone

from src.db.init_schema import init_schema
from src.config import settings
from src.ingestion.arxiv_ingester import run as ingest_arxiv
from src.ingestion.devto_ingester import run as ingest_devto
from src.ingestion.github_ingester import run as ingest_github
from src.ingestion.hn_ingester import run as ingest_hn
from src.ingestion.rss_ingester import run as ingest_rss
from src.pipeline.run_pipeline import run as run_pipeline, process_sqs_batch
from src.observability import record_pipeline_error
from src.observability.drift import run_drift_check

logger = logging.getLogger(__name__)

# Intervals in seconds
HN_INTERVAL = 30 * 60        # 30 minutes
ARXIV_INTERVAL = 12 * 60 * 60  # 12 hours


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def run_cycle(run_arxiv: bool = True):
    """Run one ingestion + pipeline cycle."""
    logger.info("[%s] Starting ingestion cycle (arxiv=%s)", _now(), run_arxiv)

    # Always fetch HN (near real-time)
    try:
        hn_count = ingest_hn()
        logger.info("HN ingestion: %d new stories", hn_count)
    except Exception:
        logger.error("HN ingestion failed", exc_info=True)

    # Always fetch DEV.to (same cadence as HN)
    try:
        devto_count = ingest_devto()
        logger.info("DEV.to ingestion: %d new articles", devto_count)
    except Exception:
        logger.error("DEV.to ingestion failed", exc_info=True)

    # Always fetch GitHub Trending
    try:
        github_count = ingest_github()
        logger.info("GitHub Trending: %d new repos", github_count)
    except Exception:
        logger.error("GitHub Trending ingestion failed", exc_info=True)

    # Always fetch RSS tech news
    try:
        rss_count = ingest_rss()
        logger.info("RSS news: %d new articles", rss_count)
    except Exception:
        logger.error("RSS ingestion failed", exc_info=True)

    # ArXiv only on the longer interval
    if run_arxiv:
        try:
            arxiv_count = ingest_arxiv()
            logger.info("ArXiv ingestion: %d new papers", arxiv_count)
        except Exception:
            logger.error("ArXiv ingestion failed", exc_info=True)

    # Process any new RAW documents → chunks + embeddings
    # When SQS is enabled, ingesters already sent messages; drain the queue.
    # Otherwise fall back to the DB-polling pipeline.
    try:
        if settings.SQS_ENABLED:
            total_processed = 0
            while True:
                batch = process_sqs_batch()
                if batch == 0:
                    break
                total_processed += batch
            logger.info("SQS consumer: %d documents processed", total_processed)
        else:
            chunks = run_pipeline()
            logger.info("Pipeline: %d new chunks created", chunks)
    except Exception:
        record_pipeline_error("scheduler_pipeline")
        logger.error("Pipeline failed", exc_info=True)

    # Drift detection (runs alongside ArXiv, ~every 12h)
    if run_arxiv:
        try:
            drift_result = run_drift_check()
            if drift_result["alert_triggered"]:
                logger.warning("Drift alert triggered — quality degradation detected")
        except Exception:
            logger.error("Drift check failed", exc_info=True)

    logger.info("[%s] Cycle complete.", _now())


def main():
    """Main scheduler loop."""
    logger.info("TechPulse scheduler started. HN every %dm, ArXiv every %dh",
                HN_INTERVAL // 60, ARXIV_INTERVAL // 3600)

    # Ensure database schema exists
    init_schema()

    # Run both immediately on startup
    run_cycle(run_arxiv=True)

    last_hn = time.monotonic()
    last_arxiv = time.monotonic()

    while True:
        time.sleep(60)  # check every minute

        now = time.monotonic()

        if now - last_hn >= HN_INTERVAL:
            run_arxiv = now - last_arxiv >= ARXIV_INTERVAL
            run_cycle(run_arxiv=run_arxiv)
            last_hn = now
            if run_arxiv:
                last_arxiv = now


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    main()
