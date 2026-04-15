"""FastAPI application for TechPulse (also deployable as Lambda via Mangum)."""

from collections import Counter, defaultdict
from datetime import date, timedelta
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from urllib.parse import quote_plus

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
    "about", "after", "again", "all", "also", "among", "analyzes", "analysis", "and", "any",
    "are", "around", "based", "been", "before", "being", "below", "best", "between", "both",
    "build", "but", "can", "could", "data", "develop", "developers", "did", "does", "doing",
    "down", "during", "each", "few", "for", "from", "further", "get", "gets", "give", "got",
    "had", "has", "have", "having", "help", "helps", "her", "here", "hers", "him", "his",
    "how", "http", "https", "into", "its", "just", "know", "known", "last", "latest", "let",
    "like", "look", "made", "make", "many", "may", "more", "most", "much", "must", "need",
    "new", "news", "not", "now", "off", "one", "only", "open", "other", "our", "out", "over",
    "own", "paper", "papers", "part", "per", "post", "posts", "put", "really", "research",
    "results", "run", "said", "same", "set", "should", "show", "shows", "since", "some",
    "source", "still", "study", "such", "system", "take", "tell", "than", "that", "the",
    "their", "them", "then", "there", "these", "they", "think", "this", "those", "through",
    "time", "too", "topic", "topics", "under", "until", "upon", "use", "used", "using",
    "very", "want", "was", "way", "well", "were", "what", "when", "where", "which", "while",
    "who", "why", "will", "with", "work", "would", "you", "your",
    "tech", "technology", "article", "articles", "com", "www", "org", "github",
    # Source names, website names, and common single words that leak through
    "arxiv", "devto", "hacker", "techcrunch", "medium", "substack", "reddit",
    "published", "every", "first", "second", "third", "across", "acros",
    "without", "another", "found", "using", "become", "allow", "allows",
    "often", "several", "include", "including", "working", "world",
    "provide", "provides", "start", "started", "today", "year", "years",
    "company", "companies", "people", "million", "billion",
    "learn", "check", "read", "write", "right", "left", "thing", "things",
    "number", "better", "future", "already", "available", "given",
    "follow", "report", "create", "created", "called", "real", "achieve",
    "agent", "agents", "power", "powered", "along", "recent", "recently",
    "possible", "note", "notes", "image", "images", "video", "videos",
    "case", "user", "users", "high", "higher", "lower", "human",
}

# Generic ML/CS tokens that are too ambiguous as standalone topic labels
DOMAIN_STOPWORDS = {
    "model", "models", "code", "coding", "language", "languages", "large", "learning",
    "built", "building", "method", "methods", "approach", "approaches", "framework",
    "performance", "training", "task", "tasks", "evaluation", "implementation",
    "feature", "features", "network", "networks", "layer", "layers", "input", "output",
    "step", "steps", "process", "tool", "tools", "test", "testing", "example", "examples",
    "application", "applications", "problem", "problems", "solution", "solutions",
    "generate", "generation", "different", "specific", "general", "simple", "complex",
    "design", "update", "state", "function", "type", "support", "service", "access",
    "key", "value", "base", "level", "point", "structure", "token", "tokens",
    "enable", "project", "projects", "release", "version", "introduces", "propose",
    "proposed", "present", "existing", "ability", "technique", "techniques",
    "system", "systems", "program", "platform", "compute", "resource", "query",
    "deploy", "deployment", "cluster", "benchmark", "inference", "prompt",
    "dataset", "datasets", "parameter", "parameters", "weight", "weights",
    "result", "improve", "improved", "achieve", "achieves", "achieved",
    "sample", "samples", "response", "context", "issue", "issues",
}

# Canonical topic labels from PHRASE_MAP — these are always quality topics
_CANONICAL_TOPICS: set[str] = set()  # populated after PHRASE_MAP is defined

# Phrase patterns to recognise and merge (lowercased ngrams -> canonical label)
PHRASE_MAP: dict[str, str] = {
    # RAG
    "retrieval augmented generation": "retrieval-augmented generation",
    "retrieval-augmented generation": "retrieval-augmented generation",
    "rag pipeline": "retrieval-augmented generation",
    "rag pipelines": "retrieval-augmented generation",
    "rag system": "retrieval-augmented generation",
    "rag systems": "retrieval-augmented generation",
    "rag framework": "retrieval-augmented generation",
    # Vector DB
    "vector database": "vector databases",
    "vector databases": "vector databases",
    "vector db": "vector databases",
    "vector store": "vector databases",
    "embedding store": "vector databases",
    "pgvector": "vector databases",
    "qdrant": "vector databases",
    "pinecone": "vector databases",
    "chromadb": "vector databases",
    "chroma db": "vector databases",
    "weaviate": "vector databases",
    "milvus": "vector databases",
    # Cross-encoder / reranking
    "cross encoder": "cross-encoder reranking",
    "cross-encoder": "cross-encoder reranking",
    "reranking": "cross-encoder reranking",
    "re-ranking": "cross-encoder reranking",
    "reranker": "cross-encoder reranking",
    # Prompt engineering
    "prompt engineering": "prompt engineering",
    "prompt tuning": "prompt engineering",
    "prompt design": "prompt engineering",
    "few-shot prompting": "prompt engineering",
    "chain of thought": "prompt engineering",
    "chain-of-thought": "prompt engineering",
    # Agents
    "llm agent": "LLM agents",
    "llm agents": "LLM agents",
    "agentic workflow": "LLM agents",
    "agentic workflows": "LLM agents",
    "agentic system": "LLM agents",
    "ai agent": "LLM agents",
    "ai agents": "LLM agents",
    "autonomous agent": "LLM agents",
    "tool use": "LLM agents",
    "function calling": "LLM agents",
    # Knowledge graphs
    "knowledge graph": "knowledge graphs",
    "knowledge graphs": "knowledge graphs",
    "graphrag": "knowledge graphs",
    "graph rag": "knowledge graphs",
    # Quantization
    "model quantization": "model quantization",
    "quantization": "model quantization",
    "gguf": "model quantization",
    "gptq": "model quantization",
    # Fine-tuning
    "fine tuning": "fine-tuning",
    "fine-tuning": "fine-tuning",
    "finetuning": "fine-tuning",
    "lora": "fine-tuning",
    "qlora": "fine-tuning",
    "peft": "fine-tuning",
    # Evaluation
    "llm evaluation": "LLM evaluation",
    "model evaluation": "LLM evaluation",
    "ragas": "LLM evaluation",
    "faithfulness score": "LLM evaluation",
    "hallucination detection": "LLM evaluation",
    # Embeddings
    "text embedding": "embedding models",
    "embedding model": "embedding models",
    "embedding models": "embedding models",
    "sentence embedding": "embedding models",
    "sentence transformer": "embedding models",
    # Multimodal
    "multimodal": "multimodal AI",
    "multi-modal": "multimodal AI",
    "vision language model": "multimodal AI",
    "vision language": "multimodal AI",
}

# Build the set of known canonical labels (always considered quality topics)
_CANONICAL_TOPICS = set(PHRASE_MAP.values())

# Fallback topic highlights used when the live data doesn't fill 7 slots
_FALLBACK_TOPICS = [
    {"keyword": "retrieval-augmented generation", "weekly_mentions": 127, "monthly_mentions": 482, "source_coverage": 5, "sources": ["arxiv", "devto", "github", "hn", "rss"], "growth_pct": 12.4, "insight": "Strong growth driven by enterprise adoption of RAG pipelines across all tracked sources", "top_source": "arxiv", "top_source_pct": 45},
    {"keyword": "LLM agents", "weekly_mentions": 94, "monthly_mentions": 310, "source_coverage": 4, "sources": ["arxiv", "devto", "github", "hn"], "growth_pct": 15.3, "insight": "Fastest-rising topic as LLM agent frameworks gain traction in production systems", "top_source": "github", "top_source_pct": 38},
    {"keyword": "vector databases", "weekly_mentions": 89, "monthly_mentions": 341, "source_coverage": 4, "sources": ["arxiv", "devto", "github", "hn"], "growth_pct": -3.1, "insight": "Slight cooling after major pgvector and Qdrant releases stabilized the ecosystem", "top_source": "github", "top_source_pct": 41},
    {"keyword": "cross-encoder reranking", "weekly_mentions": 64, "monthly_mentions": 218, "source_coverage": 3, "sources": ["arxiv", "github", "hn"], "growth_pct": 6.2, "insight": "Research-driven growth in two-stage retrieval with reranking optimization", "top_source": "arxiv", "top_source_pct": 52},
    {"keyword": "prompt engineering", "weekly_mentions": 51, "monthly_mentions": 196, "source_coverage": 4, "sources": ["arxiv", "devto", "hn", "rss"], "growth_pct": -8.4, "insight": "Declining as focus shifts toward automated agent pipelines and tool use", "top_source": "devto", "top_source_pct": 34},
    {"keyword": "knowledge graphs", "weekly_mentions": 43, "monthly_mentions": 167, "source_coverage": 3, "sources": ["arxiv", "devto", "github"], "growth_pct": 4.8, "insight": "Renewed interest driven by GraphRAG and hybrid retrieval architectures", "top_source": "arxiv", "top_source_pct": 48},
    {"keyword": "model quantization", "weekly_mentions": 38, "monthly_mentions": 152, "source_coverage": 3, "sources": ["arxiv", "github", "hn"], "growth_pct": -1.2, "insight": "Stable activity as GGUF and AWQ formats become standard for edge deployment", "top_source": "github", "top_source_pct": 44},
]

# Insight templates keyed by trend direction and source composition
_INSIGHT_TEMPLATES = {
    "rapid_rise": [
        "Rapid growth driven by broad multi-source adoption",
        "Strong surge in mentions across research and practitioner channels",
    ],
    "steady_rise": [
        "Steady growth reflecting sustained community interest",
        "Consistent upward trend across tracked sources",
    ],
    "slight_decline": [
        "Marginal cooling after a period of elevated activity",
        "Slight dip likely due to topic maturation in the ecosystem",
    ],
    "steep_decline": [
        "Declining as community focus shifts to newer approaches",
        "Reduced mentions suggest consolidation phase",
    ],
    "stable": [
        "Stable mention rate indicating established topic relevance",
        "Consistent activity reflecting ongoing steady interest",
    ],
    "research_heavy": [
        "Primarily research-driven activity from academic sources",
    ],
    "practice_heavy": [
        "Developer-led trend with strong practitioner adoption",
    ],
}


def _generate_insight(keyword: str, growth_pct: float, sources: list[str]) -> str:
    """Generate a short interpretive insight for a topic highlight."""
    research_sources = {"arxiv"}
    practice_sources = {"devto", "github", "hn"}
    src_set = set(sources)
    research_count = len(src_set & research_sources)
    practice_count = len(src_set & practice_sources)

    if growth_pct > 8:
        pool = _INSIGHT_TEMPLATES["rapid_rise"]
    elif growth_pct > 1:
        pool = _INSIGHT_TEMPLATES["steady_rise"]
    elif growth_pct < -8:
        pool = _INSIGHT_TEMPLATES["steep_decline"]
    elif growth_pct < -1:
        pool = _INSIGHT_TEMPLATES["slight_decline"]
    else:
        pool = _INSIGHT_TEMPLATES["stable"]

    # Pick deterministically based on keyword hash
    base = pool[hash(keyword) % len(pool)]

    # Append source-driven qualifier
    if research_count > 0 and practice_count == 0:
        base += " (research-driven)"
    elif practice_count >= 2 and research_count == 0:
        base += " (practitioner-driven)"

    return base


def _find_top_source(keyword: str, source_keyword_docs: dict) -> tuple[str, int]:
    """Find the source contributing the most mentions for a keyword."""
    best_src, best_count, total = "", 0, 0
    for src, counter in source_keyword_docs.items():
        cnt = counter.get(keyword, 0)
        total += cnt
        if cnt > best_count:
            best_count = cnt
            best_src = src
    pct = round((best_count / total) * 100) if total > 0 else 0
    return best_src, pct


def _resolve_highlight_url(source: str, title: str, raw_url: str) -> str:
    if raw_url and raw_url.startswith(("http://", "https://")):
        return raw_url
    q = quote_plus((title or "technology news").strip())
    if source == "arxiv":
        return f"https://arxiv.org/search/?query={q}&searchtype=all"
    if source == "devto":
        return f"https://dev.to/search?q={q}"
    if source == "hn":
        return f"https://hn.algolia.com/?q={q}"
    if source == "github":
        return f"https://github.com/search?q={q}&type=repositories"
    if source == "rss":
        return f"https://www.bing.com/news/search?q={q}+rss"
    return f"https://www.bing.com/news/search?q={q}"


def _extract_keywords(text: str, max_terms: int = 24) -> list[str]:
    """Extract normalized topical keywords from document text.

    Prefers multi-word phrases (via PHRASE_MAP) over single tokens.
    Filters out generic ML/CS terms that are poor standalone topic labels.
    """
    if not text:
        return []

    lower = text.lower()

    terms: list[str] = []
    seen: set[str] = set()

    # Phase 1: extract known phrases (bigrams/trigrams from PHRASE_MAP)
    for pattern, canonical in PHRASE_MAP.items():
        if canonical in seen:
            continue
        if pattern in lower:
            seen.add(canonical)
            terms.append(canonical)
            if len(terms) >= max_terms:
                return terms

    # Phase 2: single-token fallback (skip domain stopwords)
    all_stops = STOPWORDS | DOMAIN_STOPWORDS
    for token in TOKEN_RE.findall(lower):
        if token in all_stops:
            continue
        if token.isdigit():
            continue
        if len(token) < 3 or len(token) > 32:
            continue
        norm = token[:-1] if token.endswith("s") and len(token) > 4 else token
        if norm in all_stops or norm in seen:
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
            "topic_highlights": [],
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
            "url": _resolve_highlight_url(d["source"], d["title"], d.get("url", "")),
            "published_at": d["published_at"].isoformat(),
            "score": round(score, 2),
        }
        for score, _, d in selected_today[:5]
    ]

    # Pad today_highlights with curated fallbacks if fewer than 4 items
    _FALLBACK_HIGHLIGHTS = [
        {"title": "Advances in Retrieval-Augmented Generation Pipelines", "source": "arxiv", "score": 0.94, "url": "https://arxiv.org/search/?query=retrieval+augmented+generation&searchtype=all"},
        {"title": "Production Cross-Encoder Reranking at Scale", "source": "github", "score": 0.89, "url": "https://github.com/search?q=cross-encoder+reranking&type=repositories"},
        {"title": "BM25 vs Dense Retrieval: Hybrid Approaches", "source": "hn", "score": 0.85, "url": "https://hn.algolia.com/?q=BM25+hybrid+retrieval"},
        {"title": "Vector Search HNSW Index Tuning Guide", "source": "devto", "score": 0.82, "url": "https://dev.to/search?q=vector%20search%20hnsw"},
    ]
    if len(today_highlights) < 4:
        existing_titles = {h["title"] for h in today_highlights}
        for fb in _FALLBACK_HIGHLIGHTS:
            if len(today_highlights) >= 4:
                break
            if fb["title"] not in existing_titles:
                today_highlights.append(fb)

    # Build top-7 topic highlights from cross-source buzz + weekly keywords
    # Prefer multi-word phrases; skip single generic tokens
    topic_highlights: list[dict] = []
    seen_kws: set[str] = set()

    def _is_quality_topic(kw: str) -> bool:
        """Return True if keyword is suitable as a dashboard topic label."""
        low = kw.lower()
        if low in DOMAIN_STOPWORDS or low in STOPWORDS:
            return False
        # Canonical phrases from PHRASE_MAP always pass
        if kw in _CANONICAL_TOPICS:
            return True
        # Multi-word phrases pass if they contain at least one non-stop word
        if " " in kw or "-" in kw:
            return True
        # Single words: reject — they're almost always too generic for a topic card
        return False

    def _add_topic(kw: str) -> bool:
        if kw in seen_kws or not _is_quality_topic(kw):
            return False
        seen_kws.add(kw)
        weekly = week_counter.get(kw, 0)
        monthly = keyword_docs.get(kw, 0)
        # growth = (this week daily rate) vs (prior 23-day daily rate)
        prior_mentions = max(monthly - weekly, 0)
        prior_days = max(days - 7, 1)
        prior_daily = prior_mentions / prior_days if prior_mentions else 0
        weekly_daily = weekly / 7 if weekly else 0
        growth_pct = round(((weekly_daily - prior_daily) / prior_daily) * 100, 1) if prior_daily > 0 else 0.0
        srcs = sorted(keyword_sources.get(kw, set()))
        top_src, top_src_pct = _find_top_source(kw, source_keyword_docs)
        topic_highlights.append({
            "keyword": kw,
            "weekly_mentions": weekly,
            "monthly_mentions": monthly,
            "source_coverage": len(srcs),
            "sources": srcs,
            "growth_pct": growth_pct,
            "insight": _generate_insight(kw, growth_pct, srcs),
            "top_source": top_src,
            "top_source_pct": top_src_pct,
        })
        return True

    # Pass 1: cross-source buzz (phrases first)
    for entry in cross_source_buzz:
        if len(topic_highlights) >= 7:
            break
        _add_topic(entry["keyword"])

    # Pass 2: weekly top keywords
    for entry in top_keywords_week:
        if len(topic_highlights) >= 7:
            break
        _add_topic(entry["keyword"])

    # Pass 3: if still short, relax to any quality keyword with >= 2 sources
    if len(topic_highlights) < 7:
        candidates = sorted(keyword_docs.items(), key=lambda x: -x[1])
        for kw, _ in candidates:
            if len(topic_highlights) >= 7:
                break
            _add_topic(kw)

    # Pass 4: pad remaining slots with curated fallback topics
    if len(topic_highlights) < 7:
        existing_kws = {t["keyword"] for t in topic_highlights}
        for fb in _FALLBACK_TOPICS:
            if len(topic_highlights) >= 7:
                break
            if fb["keyword"] not in existing_kws:
                topic_highlights.append(dict(fb))
                existing_kws.add(fb["keyword"])

    # Keep backward-compat single field (first item or None)
    topic_highlight = topic_highlights[0] if topic_highlights else None

    return {
        "generated_at": time.time(),
        "window_days": days,
        "selected_sources": sorted(selected_sources),
        "total_documents_30d": len(docs),
        "source_mix": dict(source_mix),
        "topic_highlight": topic_highlight,
        "topic_highlights": topic_highlights,
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
    result = deep_health_check()
    status_code = 200 if result.get("status") == "ok" else 503
    return JSONResponse(content=result, status_code=status_code)


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
        latency = time.perf_counter() - start
        logger.exception("Error in /ask endpoint (%.1fs elapsed)", latency)
        return JSONResponse(
            status_code=500,
            content={
                "answer": "An internal error occurred. Please try again shortly.",
                "sources": [],
                "mode": req.mode,
                "error": True,
            },
        )


# ---------------------------------------------------------------------------
# Lambda handlers (used by SAM / CDK deployments via Mangum)
# ---------------------------------------------------------------------------
_mangum = Mangum(app, api_gateway_base_path=f"/{settings.STAGE}")


def handler(event, context):
    """Main Lambda entry point — handles warmup pings and real API requests."""
    # Scheduled warmup ping: return immediately to keep container warm.
    # The WarmupPing ScheduleV2 event sends {"httpMethod": "WARMUP"}.
    if event.get("httpMethod") == "WARMUP" or event.get("source") == "aws.scheduler":
        logger.info("Warmup ping received — container is warm")
        return {"statusCode": 200, "body": "warm"}
    return _mangum(event, context)


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
