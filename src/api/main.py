"""FastAPI application for TechPulse (also deployable as Lambda via Mangum)."""

import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from mangum import Mangum

from src.orchestrator.rag import ask
from src.db.init_schema import init_schema
from src.db.connection import close_pool
from src.observability import deep_health_check, record_api_latency, record_hallucination_flag
from src.observability.drift import run_drift_check

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_schema()
    yield
    close_pool()


limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="TechPulse API", version="0.1.0", lifespan=lifespan)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Please slow down."})

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="Your technology question")
    mode: str = Field("hybrid", pattern=r"^(baseline|hybrid)$", description="Retrieval mode")
    sources: list[str] | None = Field(None, description="Filter by source types, e.g. ['arxiv','hn']")


@app.get("/health")
def health_check():
    return deep_health_check()


@app.post("/drift")
@limiter.limit("2/minute")
def drift_endpoint(request: Request):
    """Run retrieval quality drift check on demand."""
    return run_drift_check()


@app.post("/ask")
@limiter.limit("10/minute")
def ask_endpoint(req: AskRequest, request: Request):
    logger.info("Received /ask query=%s mode=%s", req.query[:50], req.mode)
    start = time.perf_counter()
    try:
        result = ask(query=req.query, mode=req.mode, sources=req.sources)
        latency = time.perf_counter() - start
        record_api_latency(latency)
        # Track hallucination flags
        if result.get("hallucination_check", {}).get("flagged"):
            record_hallucination_flag()
        return result
    except Exception:
        logger.exception("Error in /ask endpoint")
        raise


# ---------------------------------------------------------------------------
# Lambda handlers (used by SAM / CDK deployments via Mangum)
# ---------------------------------------------------------------------------
handler = Mangum(app)


def health_handler(event, context):
    """Standalone Lambda handler for scheduled health checks."""
    import json
    result = deep_health_check()
    status_code = 200 if result.get("status") == "ok" else 503
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(result),
    }
