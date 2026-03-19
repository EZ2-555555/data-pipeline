"""Baseline and hybrid retrieval for TechPulse.

Baseline: pure cosine similarity over full corpus.
Hybrid: metadata filter → cosine search → reranking-lite.
"""

import logging
import math
from datetime import datetime, timedelta, timezone

from src.db.connection import get_connection, put_connection
from src.embedding.embedder import embed_query
from src.config import settings

logger = logging.getLogger(__name__)

# Minimum cosine similarity to include a result (filters pure noise, ~0.15 = random text)
MIN_SIMILARITY = 0.15


def baseline_retrieve(query: str, top_k: int | None = None) -> list[dict]:
    """Vector-only retrieval over the full indexed corpus."""
    top_k = top_k or settings.TOP_K
    query_emb = embed_query(query)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id, c.chunk_text, d.title, d.source, d.url, d.published_at,
                       1 - (c.embedding <=> %s::vector) AS similarity
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE d.state = 'INDEXED'
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s
                """,
                (query_emb, query_emb, top_k),
            )
            rows = cur.fetchall()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_connection(conn)

    return [
        {
            "chunk_id": r[0],
            "chunk_text": r[1],
            "title": r[2],
            "source": r[3],
            "url": r[4],
            "published_at": r[5],
            "similarity": float(r[6]),
            "score": float(r[6]),  # final score = similarity for baseline
        }
        for r in rows
        if float(r[6]) >= MIN_SIMILARITY
    ]


def _compute_keyword_overlap(query: str, text: str) -> float:
    """Simple keyword overlap ratio between query and chunk."""
    query_tokens = set(query.lower().split())
    text_tokens = set(text.lower().split())
    if not query_tokens:
        return 0.0
    return len(query_tokens & text_tokens) / len(query_tokens)


def _compute_recency_weight(published_at: datetime, lam: float) -> float:
    """Exponential recency decay: e^(-lambda * age_days)."""
    if published_at is None:
        return 0.0
    now = datetime.now(timezone.utc)
    # DB stores DATE; convert to datetime if needed
    if not isinstance(published_at, datetime):
        published_at = datetime(published_at.year, published_at.month, published_at.day, tzinfo=timezone.utc)
    elif published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    age_days = (now - published_at).days
    return math.exp(-lam * max(age_days, 0))


def hybrid_retrieve(
    query: str,
    top_k: int | None = None,
    recency_days: int = 180,
    alpha: float | None = None,
    beta: float | None = None,
    gamma: float | None = None,
    sources: list[str] | None = None,
) -> list[dict]:
    """Hybrid retrieval: metadata filter → vector search → reranking-lite.

    Args:
        alpha/beta/gamma: Override reranking weights. Defaults to settings values.
        sources: Optional list of source types to filter by (e.g. ['arxiv', 'hn']).
    """
    top_k = top_k or settings.TOP_K
    query_emb = embed_query(query)

    # Fetch more candidates than top_k for reranking
    candidate_limit = top_k * 4

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Stage 1+2: Metadata filter + vector similarity on filtered set
            base_sql = """
                SELECT c.id, c.chunk_text, d.title, d.source, d.url, d.published_at,
                       1 - (c.embedding <=> %s::vector) AS similarity
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE d.state = 'INDEXED'
                  AND d.published_at >= CURRENT_DATE - %s
            """
            params: list = [query_emb, timedelta(days=recency_days)]

            if sources:
                placeholders = ",".join(["%s"] * len(sources))
                base_sql += f"  AND d.source IN ({placeholders})\n"
                params.extend(sources)

            base_sql += "ORDER BY c.embedding <=> %s::vector\nLIMIT %s"
            params.extend([query_emb, candidate_limit])

            cur.execute(base_sql, params)
            rows = cur.fetchall()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_connection(conn)

    # Stage 3: Reranking-lite
    alpha = alpha if alpha is not None else settings.RERANK_ALPHA
    beta = beta if beta is not None else settings.RERANK_BETA
    gamma = gamma if gamma is not None else settings.RERANK_GAMMA
    lam = settings.RECENCY_LAMBDA

    candidates = []
    for r in rows:
        sim = float(r[6])
        kw_overlap = _compute_keyword_overlap(query, r[1])
        recency = _compute_recency_weight(r[5], lam)
        score = alpha * sim + beta * kw_overlap + gamma * recency

        candidates.append({
            "chunk_id": r[0],
            "chunk_text": r[1],
            "title": r[2],
            "source": r[3],
            "url": r[4],
            "published_at": r[5],
            "similarity": sim,
            "keyword_overlap": kw_overlap,
            "recency_weight": recency,
            "score": score,
        })

    # Filter low-similarity noise, sort by final score, take top_k
    candidates = [c for c in candidates if c["similarity"] >= MIN_SIMILARITY]
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:top_k]
