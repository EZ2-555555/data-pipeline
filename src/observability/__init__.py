"""CloudWatch custom metrics, health checks, and budget helpers for TechPulse.

Publishes custom metrics to the TechPulse/<stage> namespace:
  - IngestionCount   (source dimension)
  - PipelineChunks
  - PipelineLatency  (seconds)
  - PipelineErrors
  - ApiLatency       (seconds)
  - HallucinationFlags

Falls back to logging-only when CloudWatch is unavailable (local dev).
"""

import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from src.config import settings

logger = logging.getLogger(__name__)

_NAMESPACE = f"TechPulse/{os.getenv('STAGE', 'dev')}"


def _get_cw_client():
    """Return a boto3 CloudWatch client, or None in local dev."""
    if not settings.CLOUDWATCH_ENABLED:
        return None
    try:
        import boto3

        kwargs = {"region_name": settings.AWS_REGION}
        endpoint = os.getenv("CLOUDWATCH_ENDPOINT_URL")
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        return boto3.client("cloudwatch", **kwargs)
    except Exception:
        logger.debug("CloudWatch client unavailable — metrics logged only")
        return None


# ---------------------------------------------------------------------------
# Metric publishing
# ---------------------------------------------------------------------------

def put_metric(name: str, value: float, unit: str = "Count", dimensions: dict | None = None) -> None:
    """Publish a single custom metric to CloudWatch (or log it locally)."""
    dims = [{"Name": k, "Value": str(v)} for k, v in (dimensions or {}).items()]

    logger.info("METRIC %s=%s %s %s", name, value, unit, dimensions or "")

    client = _get_cw_client()
    if not client:
        return

    client.put_metric_data(
        Namespace=_NAMESPACE,
        MetricData=[
            {
                "MetricName": name,
                "Value": value,
                "Unit": unit,
                "Dimensions": dims,
                "Timestamp": datetime.now(timezone.utc),
            }
        ],
    )


def record_ingestion(source: str, count: int) -> None:
    """Record how many documents were ingested from a source."""
    put_metric("IngestionCount", count, "Count", {"Source": source})


def record_pipeline_chunks(count: int) -> None:
    """Record chunks created in a pipeline run."""
    put_metric("PipelineChunks", count, "Count")


def record_pipeline_error(error_type: str = "General") -> None:
    """Increment pipeline error counter."""
    put_metric("PipelineErrors", 1, "Count", {"ErrorType": error_type})


def record_api_latency(latency_s: float) -> None:
    """Record API request latency."""
    put_metric("ApiLatency", latency_s, "Seconds")


def record_hallucination_flag() -> None:
    """Increment hallucination flag counter."""
    put_metric("HallucinationFlags", 1, "Count")


@contextmanager
def timed_metric(metric_name: str, unit: str = "Seconds", dimensions: dict | None = None):
    """Context manager that publishes elapsed time as a CloudWatch metric."""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        put_metric(metric_name, elapsed, unit, dimensions)


# ---------------------------------------------------------------------------
# Health check (deep — tests DB connectivity)
# ---------------------------------------------------------------------------

def deep_health_check() -> dict:
    """Run a deep health check verifying DB connectivity and basic stats.

    Returns a dict suitable for JSON response.
    """
    from src.db.connection import get_connection, put_connection

    result = {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {},
    }

    # DB connectivity
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.execute("SELECT COUNT(*) FROM documents")
                doc_count = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM chunks")
                chunk_count = cur.fetchone()[0]
            result["checks"]["database"] = {
                "status": "ok",
                "documents": doc_count,
                "chunks": chunk_count,
            }
        finally:
            put_connection(conn)
    except Exception as exc:
        result["status"] = "degraded"
        result["checks"]["database"] = {"status": "error", "detail": str(exc)}

    # S3 reachability (quick head-bucket)
    try:
        if settings.S3_ENABLED:
            import boto3

            s3_kwargs = {"region_name": settings.AWS_REGION}
            s3_endpoint = os.getenv("S3_ENDPOINT_URL")
            if s3_endpoint:
                s3_kwargs["endpoint_url"] = s3_endpoint
            s3 = boto3.client("s3", **s3_kwargs)
            s3.head_bucket(Bucket=settings.S3_BUCKET_NAME)
            result["checks"]["s3"] = {"status": "ok", "bucket": settings.S3_BUCKET_NAME}
        else:
            result["checks"]["s3"] = {"status": "skipped", "reason": "S3_ENABLED=false"}
    except Exception as exc:
        result["checks"]["s3"] = {"status": "error", "detail": str(exc)}

    # SQS reachability
    try:
        if settings.SQS_ENABLED and settings.SQS_QUEUE_URL:
            import boto3

            sqs_kwargs = {"region_name": settings.AWS_REGION}
            sqs_endpoint = os.getenv("SQS_ENDPOINT_URL")
            if sqs_endpoint:
                sqs_kwargs["endpoint_url"] = sqs_endpoint
            sqs = boto3.client("sqs", **sqs_kwargs)
            attrs = sqs.get_queue_attributes(
                QueueUrl=settings.SQS_QUEUE_URL,
                AttributeNames=["ApproximateNumberOfMessages"],
            )
            result["checks"]["sqs"] = {
                "status": "ok",
                "approximate_messages": attrs["Attributes"].get(
                    "ApproximateNumberOfMessages", "N/A"
                ),
            }
        else:
            result["checks"]["sqs"] = {"status": "skipped", "reason": "SQS_ENABLED=false"}
    except Exception as exc:
        result["checks"]["sqs"] = {"status": "error", "detail": str(exc)}

    # LLM backend reachability
    try:
        from src.orchestrator.llm_backends import generate

        backend = settings.LLM_BACKEND
        test_resp = generate("Respond with OK.", max_tokens=5)
        result["checks"]["llm"] = {
            "status": "ok",
            "backend": backend,
            "probe_response": test_resp[:60],
        }
    except Exception as exc:
        result["status"] = "degraded"
        result["checks"]["llm"] = {
            "status": "error",
            "backend": settings.LLM_BACKEND,
            "detail": str(exc),
        }

    return result
