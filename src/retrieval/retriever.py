"""Baseline and hybrid retrieval for TechPulse.

Baseline: pure cosine similarity over full corpus.
Hybrid: parallel vector + full-corpus BM25 search, fused via RRF.
"""

import logging
import math
import time
from datetime import datetime, timedelta, timezone

from rank_bm25 import BM25Okapi

from src.db.connection import get_connection, put_connection
from src.embedding.embedder import embed_query
from src.config import settings

logger = logging.getLogger(__name__)

# Minimum cosine similarity to include a result (filters pure noise, ~0.15 = random text)
MIN_SIMILARITY = 0.15

# ---------------------------------------------------------------------------
# Module-level BM25 index — built once over the full corpus, reused across
# all queries so that IDF statistics are computed correctly.
# ---------------------------------------------------------------------------
_bm25_index: "BM25Okapi | None" = None
_bm25_chunk_ids: list = []
_bm25_chunk_data: list[dict] = []
_bm25_id_to_index: dict[int, int] = {}
_bm25_built_at: float = 0.0


def _get_bm25_index():
    """Build BM25 index over the full indexed corpus (cached, refreshed every 30 min)."""
    global _bm25_index, _bm25_chunk_ids, _bm25_chunk_data, _bm25_id_to_index, _bm25_built_at
    # Rebuild every 30 minutes to capture newly ingested documents
    if _bm25_index is not None and (time.time() - _bm25_built_at) < 1800:
        return _bm25_index, _bm25_chunk_ids, _bm25_chunk_data

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id, c.chunk_text, d.title, d.source, d.url, d.published_at
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE d.state = 'INDEXED'
                ORDER BY c.id
                """
            )
            rows = cur.fetchall()
    finally:
        put_connection(conn)

    _bm25_chunk_data = [
        {
            "chunk_id": r[0],
            "chunk_text": r[1],
            "title": r[2],
            "source": r[3],
            "url": r[4],
            "published_at": r[5],
        }
        for r in rows
    ]
    tokenized = [d["chunk_text"].lower().split() for d in _bm25_chunk_data]
    _bm25_index = BM25Okapi(tokenized)
    _bm25_chunk_ids = [d["chunk_id"] for d in _bm25_chunk_data]
    _bm25_id_to_index = {d["chunk_id"]: i for i, d in enumerate(_bm25_chunk_data)}
    _bm25_built_at = time.time()
    logger.info("BM25 index built over %d chunks", len(_bm25_chunk_data))
    return _bm25_index, _bm25_chunk_ids, _bm25_chunk_data


def invalidate_bm25_cache():
    """Clear the cached BM25 index (call after ingesting new documents)."""
    global _bm25_index, _bm25_chunk_ids, _bm25_chunk_data, _bm25_id_to_index, _bm25_built_at
    _bm25_index = None
    _bm25_chunk_ids = []
    _bm25_chunk_data = []
    _bm25_id_to_index = {}
    _bm25_built_at = 0.0


def _deduplicate_by_url(results: list[dict]) -> list[dict]:
    """Keep only the highest-scoring result per unique URL (document).

    When multiple chunks from the same document are retrieved, the user
    sees duplicate sources. This collapses them, keeping the chunk with
    the highest ``score``.
    """
    best: dict[str, dict] = {}
    for r in results:
        url = r.get("url") or r.get("chunk_id")  # fallback if url is None
        if url not in best or r["score"] > best[url]["score"]:
            best[url] = r
    # Preserve original score ordering
    return sorted(best.values(), key=lambda x: x["score"], reverse=True)


def baseline_retrieve(query: str, top_k: int | None = None) -> list[dict]:
    """Vector-only retrieval over the full indexed corpus."""
    top_k = top_k or settings.TOP_K
    query_emb = embed_query(query)

    # Fetch extra candidates so deduplication still yields top_k unique docs
    candidate_limit = top_k * 4

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
                (query_emb, query_emb, candidate_limit),
            )
            rows = cur.fetchall()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_connection(conn)

    candidates = [
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

    return _deduplicate_by_url(candidates)[:top_k]


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


def _get_age_days(published_at) -> int:
    """Return the age of a document in days (9999 if None so unknowns sort last)."""
    if published_at is None:
        return 9999
    now = datetime.now(timezone.utc)
    if not isinstance(published_at, datetime):
        published_at = datetime(published_at.year, published_at.month, published_at.day, tzinfo=timezone.utc)
    elif published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    return max((now - published_at).days, 0)


def _execute_retrieval_query(query_emb, recency_days, sources, candidate_limit,
                              _max_retries=2):
    """Execute the retrieval SQL with automatic reconnection on stale connections."""
    import psycopg2
    for attempt in range(_max_retries + 1):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                base_sql = """
                    SELECT c.id, c.chunk_text, d.title, d.source, d.url, d.published_at,
                           1 - (c.embedding <=> %s::vector) AS similarity
                    FROM chunks c
                    JOIN documents d ON c.document_id = d.id
                    WHERE d.state = 'INDEXED'
                      AND (d.published_at IS NULL
                           OR d.published_at >= CURRENT_DATE - %s)
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
            put_connection(conn)
            return rows
        except (psycopg2.InterfaceError, psycopg2.OperationalError) as exc:
            logger.warning("DB connection error (attempt %d/%d): %s",
                           attempt + 1, _max_retries + 1, exc)
            # Discard the broken connection and reset the pool
            try:
                put_connection(conn)
            except Exception:
                pass
            from src.db.connection import close_pool
            close_pool()
            if attempt == _max_retries:
                raise
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            put_connection(conn)
            raise


def hybrid_retrieve(
    query: str,
    top_k: int | None = None,
    recency_days: int = 180,
    sources: list[str] | None = None,
) -> list[dict]:
    """Hybrid retrieval: parallel vector + full-corpus BM25 search, fused via RRF.

    Retrieves candidates independently from two systems:
      1. Vector search (semantic similarity via pgvector)
      2. BM25 search (keyword relevance over full corpus — correct IDF)
    Then fuses rankings using Reciprocal Rank Fusion (Cormack et al., SIGIR 2009).
    No weight tuning required — RRF is parameter-free and scale-invariant.
    """
    K = 60  # RRF constant (standard value from the original paper)
    top_k = top_k or settings.TOP_K
    query_emb = embed_query(query)
    candidate_limit = top_k * 4

    # --- Signal 1: Vector search (pgvector cosine similarity) ---
    rows = _execute_retrieval_query(
        query_emb, recency_days, sources, candidate_limit
    )
    vector_candidates: dict[int, dict] = {}
    for r in rows:
        sim = float(r[6])
        if sim < MIN_SIMILARITY:
            continue
        vector_candidates[r[0]] = {
            "chunk_id": r[0],
            "chunk_text": r[1],
            "title": r[2],
            "source": r[3],
            "url": r[4],
            "published_at": r[5],
            "similarity": sim,
            "age_days": _get_age_days(r[5]),
        }

    # --- Signal 2: BM25 search over the FULL corpus ---
    bm25_index, _, bm25_data = _get_bm25_index()
    bm25_scores = bm25_index.get_scores(query.lower().split())
    bm25_top_indices = sorted(
        range(len(bm25_scores)), key=lambda i: -bm25_scores[i]
    )[:candidate_limit]
    bm25_candidates: dict[int, dict] = {}
    for i in bm25_top_indices:
        if bm25_scores[i] <= 0:
            continue
        d = bm25_data[i]
        # Apply the same source/recency filters as the vector search
        if sources and d.get("source") not in sources:
            continue
        age = _get_age_days(d["published_at"])
        if age != 9999 and age > recency_days:  # 9999 = NULL date, always pass
            continue
        bm25_candidates[d["chunk_id"]] = {
            **d,
            "similarity": 0.0,
            "age_days": age,
        }

    # --- Merge: union of both candidate sets ---
    all_ids = list(set(vector_candidates) | set(bm25_candidates))
    logger.info(
        "BM25 candidates: %d, Vector candidates: %d, Union: %d",
        len(bm25_candidates), len(vector_candidates), len(all_ids),
    )
    if not all_ids:
        return []

    merged: dict[int, dict] = {}
    for cid in all_ids:
        merged[cid] = vector_candidates.get(cid) or bm25_candidates[cid]

    # --- Build three independent rankings ---
    vector_ranking = sorted(
        all_ids,
        key=lambda cid: vector_candidates.get(cid, {}).get("similarity", 0.0),
        reverse=True,
    )
    bm25_ranking = sorted(
        all_ids,
        key=lambda cid: bm25_scores[_bm25_id_to_index[cid]]
        if cid in _bm25_id_to_index
        else 0.0,
        reverse=True,
    )
    recency_ranking = sorted(
        all_ids, key=lambda cid: merged[cid]["age_days"]
    )

    # --- Reciprocal Rank Fusion ---
    rrf: dict[int, float] = {}
    for rank, cid in enumerate(vector_ranking):
        rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (K + rank + 1)
    for rank, cid in enumerate(bm25_ranking):
        rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (K + rank + 1)
    for rank, cid in enumerate(recency_ranking):
        rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (K + rank + 1)

    for cid in merged:
        merged[cid]["score"] = rrf.get(cid, 0.0)

    candidates = list(merged.values())
    return _deduplicate_by_url(candidates)[:top_k]
