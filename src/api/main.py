"""FastAPI application for TechPulse (also deployable as Lambda via Mangum)."""

from collections import Counter, defaultdict
from datetime import date, timedelta
import logging
import os
import re
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
from src.config import settings
from src.db.init_schema import init_schema
from src.db.connection import close_pool, get_connection, put_connection
from src.observability import deep_health_check, record_api_latency, record_hallucination_flag
from src.observability.drift import run_drift_check

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_schema()
    except Exception:
        logger.exception("init_schema failed — DB may be unreachable")
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

VALID_SOURCES = {"arxiv", "hn", "github", "devto", "rss"}
RESEARCH_SOURCES = {"arxiv"}
PRACTICE_SOURCES = {"devto", "hn"}
TOKEN_RE = re.compile(r"[a-z][a-z0-9+\-]{2,}")
STOPWORDS = {
    "about", "after", "also", "among", "analyzes", "analysis", "and", "are", "around", "been",
    "best", "between", "build", "data", "develop", "developers", "during", "from", "gets", "have",
    "helps", "how", "into", "its", "latest", "more", "new", "news", "open", "over", "paper",
    "papers", "post", "posts", "research", "results", "shows", "source", "study", "system", "than",
    "that", "the", "their", "these", "this", "through", "topic", "topics", "using", "what", "with",
    "your", "tech", "technology", "article", "articles",
}


def _extract_keywords(text: str, max_terms: int = 24) -> list[str]:
    """Extract normalized topical keywords from document text."""
    if not text:
        return []

    terms: list[str] = []
    seen: set[str] = set()
    for token in TOKEN_RE.findall(text.lower()):
        if token in STOPWORDS:
            continue
        if token.isdigit():
            continue
        if len(token) < 3 or len(token) > 32:
            continue
        norm = token[:-1] if token.endswith("s") and len(token) > 4 else token
        if norm in STOPWORDS or norm in seen:
            continue
        seen.add(norm)
        terms.append(norm)
        if len(terms) >= max_terms:
            break
    return terms


@app.get("/dashboard/insights")
def dashboard_insights(days: int = 30, sources: str | None = None):
    """Return dashboard insights computed from ingested document sources."""
    days = max(7, min(days, 60))
    selected_sources: set[str] = set()
    if sources:
        selected_sources = {s.strip().lower() for s in sources.split(",") if s.strip()}
        invalid = selected_sources - VALID_SOURCES
        if invalid:
            return JSONResponse(
                status_code=422,
                content={"detail": f"Invalid sources: {sorted(invalid)}. Valid: {sorted(VALID_SOURCES)}"},
            )
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT source, title, content, url, published_at
                FROM documents
                WHERE published_at IS NOT NULL
                  AND published_at >= CURRENT_DATE - %s
                ORDER BY published_at DESC
                """,
                (days,),
            )
            rows = cur.fetchall()
    finally:
        put_connection(conn)

    docs = [
        {
            "source": (r[0] or "unknown").lower(),
            "title": r[1] or "Untitled",
            "content": r[2] or "",
            "url": r[3] or "",
            "published_at": r[4],
        }
        for r in rows
    ]
    if selected_sources:
        docs = [d for d in docs if d["source"] in selected_sources]

    if not docs:
        return {
            "generated_at": time.time(),
            "window_days": days,
            "selected_sources": sorted(selected_sources),
            "total_documents_30d": 0,
            "source_mix": {},
            "topic_highlight": None,
            "top_keywords_week": [],
            "cross_source_buzz": [],
            "research_practice_gap": [],
            "topic_timeline": [],
            "today_highlights": [],
        }

    today = date.today()
    week_start = today - timedelta(days=7)
    latest_day = max(d["published_at"] for d in docs if d["published_at"])

    source_mix = Counter(d["source"] for d in docs)
    week_docs = [d for d in docs if d["published_at"] and d["published_at"] >= week_start]

    week_counter: Counter[str] = Counter()
    keyword_docs: defaultdict[str, int] = defaultdict(int)
    keyword_sources: defaultdict[str, set[str]] = defaultdict(set)
    source_keyword_docs: defaultdict[str, Counter[str]] = defaultdict(Counter)

    for d in docs:
        text = f"{d['title']} {d['content'][:700]}"
        kws = set(_extract_keywords(text, max_terms=32))
        for kw in kws:
            keyword_docs[kw] += 1
            keyword_sources[kw].add(d["source"])
            source_keyword_docs[d["source"]][kw] += 1

    for d in week_docs:
        text = f"{d['title']} {d['content'][:700]}"
        week_counter.update(_extract_keywords(text, max_terms=20))

    top_keywords_week = [
        {"keyword": k, "mentions": v}
        for k, v in week_counter.most_common(10)
    ]

    cross_source_buzz = []
    for kw, doc_count in keyword_docs.items():
        srcs = sorted(keyword_sources[kw])
        if len(srcs) >= 3:
            cross_source_buzz.append(
                {
                    "keyword": kw,
                    "mentions": doc_count,
                    "sources": srcs,
                }
            )
    cross_source_buzz.sort(key=lambda x: (-len(x["sources"]), -x["mentions"], x["keyword"]))
    cross_source_buzz = cross_source_buzz[:10]

    research_practice_gap = []
    candidate_keywords = set(source_keyword_docs.get("arxiv", {}).keys()) | set(source_keyword_docs.get("devto", {}).keys()) | set(source_keyword_docs.get("hn", {}).keys())
    for kw in candidate_keywords:
        research_n = sum(source_keyword_docs[src].get(kw, 0) for src in RESEARCH_SOURCES)
        practice_n = sum(source_keyword_docs[src].get(kw, 0) for src in PRACTICE_SOURCES)
        total = research_n + practice_n
        if total < 3:
            continue
        gap = research_n - practice_n
        if gap == 0:
            continue
        research_practice_gap.append(
            {
                "keyword": kw,
                "research_mentions": research_n,
                "practice_mentions": practice_n,
                "gap": gap,
                "direction": "Research-heavy" if gap > 0 else "Practice-heavy",
            }
        )
    research_practice_gap.sort(key=lambda x: (-abs(x["gap"]), -(x["research_mentions"] + x["practice_mentions"]), x["keyword"]))
    research_practice_gap = research_practice_gap[:8]

    highlight_keyword = None
    if cross_source_buzz:
        highlight_keyword = cross_source_buzz[0]["keyword"]
    elif top_keywords_week:
        highlight_keyword = top_keywords_week[0]["keyword"]

    topic_timeline: list[dict] = []
    if highlight_keyword:
        timeline_counts: defaultdict[str, int] = defaultdict(int)
        for d in docs:
            if highlight_keyword in set(_extract_keywords(f"{d['title']} {d['content'][:700]}", max_terms=32)):
                timeline_counts[d["published_at"].isoformat()] += 1

        start_day = today - timedelta(days=29)
        for i in range(30):
            day_key = (start_day + timedelta(days=i)).isoformat()
            topic_timeline.append({"date": day_key, "mentions": timeline_counts.get(day_key, 0)})

    highlights_pool = [d for d in docs if d["published_at"] == latest_day]
    if not highlights_pool:
        highlights_pool = docs[:15]

    week_keyword_set = {x["keyword"] for x in top_keywords_week[:6]}

    ranked_highlights = []
    for d in highlights_pool:
        base_text = f"{d['title']} {d['content'][:700]}"
        kws = _extract_keywords(base_text, max_terms=18)
        overlap_with_week = len(set(kws) & week_keyword_set)
        score = overlap_with_week * 2 + min(len(d["content"]), 2400) / 1200
        if d["source"] == "arxiv":
            score += 0.4
        ranked_highlights.append((score, overlap_with_week, d))

    ranked_highlights.sort(key=lambda x: (-x[0], -x[1], x[2]["title"]))
    selected_today: list[tuple[float, int, dict]] = []

    include_arxiv = not selected_sources or "arxiv" in selected_sources
    if include_arxiv:
        arxiv_today = [x for x in ranked_highlights if x[2]["source"] == "arxiv"]
        if arxiv_today:
            selected_today.append(arxiv_today[0])
        else:
            recent_arxiv = [
                d for d in docs
                if d["source"] == "arxiv" and d["published_at"] and d["published_at"] >= today - timedelta(days=7)
            ]
            ranked_recent_arxiv: list[tuple[float, int, dict]] = []
            for d in recent_arxiv:
                base_text = f"{d['title']} {d['content'][:700]}"
                kws = _extract_keywords(base_text, max_terms=18)
                overlap_with_week = len(set(kws) & week_keyword_set)
                score = overlap_with_week * 2 + min(len(d["content"]), 2400) / 1200 + 0.4
                ranked_recent_arxiv.append((score, overlap_with_week, d))
            ranked_recent_arxiv.sort(key=lambda x: (-x[0], -x[1], x[2]["title"]))
            if ranked_recent_arxiv:
                selected_today.append(ranked_recent_arxiv[0])

    used_urls = {x[2].get("url") for x in selected_today if x[2].get("url")}
    for row in ranked_highlights:
        if len(selected_today) >= 5:
            break
        row_url = row[2].get("url")
        if row_url and row_url in used_urls:
            continue
        selected_today.append(row)
        if row_url:
            used_urls.add(row_url)

    today_highlights = [
        {
            "title": d["title"],
            "source": d["source"],
            "url": d["url"],
            "published_at": d["published_at"].isoformat(),
            "score": round(score, 2),
        }
        for score, _, d in selected_today[:5]
    ]

    topic_highlight = None
    if highlight_keyword:
        topic_highlight = {
            "keyword": highlight_keyword,
            "weekly_mentions": week_counter.get(highlight_keyword, 0),
            "monthly_mentions": keyword_docs.get(highlight_keyword, 0),
            "source_coverage": len(keyword_sources.get(highlight_keyword, set())),
            "sources": sorted(keyword_sources.get(highlight_keyword, set())),
        }

    return {
        "generated_at": time.time(),
        "window_days": days,
        "selected_sources": sorted(selected_sources),
        "total_documents_30d": len(docs),
        "source_mix": dict(source_mix),
        "topic_highlight": topic_highlight,
        "top_keywords_week": top_keywords_week,
        "cross_source_buzz": cross_source_buzz,
        "research_practice_gap": research_practice_gap,
        "topic_timeline": topic_timeline,
        "today_highlights": today_highlights,
    }


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="Your technology question")
    mode: str = Field("hybrid", pattern=r"^(baseline|hybrid)$", description="Retrieval mode")
    sources: list[str] | None = Field(None, max_length=5, description="Filter by source types, e.g. ['arxiv','hn']")


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
    if req.sources:
        invalid = set(req.sources) - VALID_SOURCES
        if invalid:
            return JSONResponse(
                status_code=422,
                content={"detail": f"Invalid sources: {sorted(invalid)}. Valid: {sorted(VALID_SOURCES)}"},
            )
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
handler = Mangum(app, api_gateway_base_path=f"/{settings.STAGE}")


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
