"""Baseline and hybrid retrieval for TechPulse.

Baseline: pure cosine similarity over full corpus.
Hybrid: parallel vector + full-corpus BM25 search, fused via weighted RRF.
"""

import logging
import math
import re
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
# Weighted RRF signal weights (positive values; need not sum to 1.0).
# Semantic vector dominates; recency is a weak signal in the tech domain.
# Weights chosen from ablation: vector 0.50, BM25 0.35, recency 0.15.
# See Ma et al., TREC 2022 — asymmetric weighting outperforms uniform RRF.
# ---------------------------------------------------------------------------
VECTOR_RRF_WEIGHT  = 0.50
BM25_RRF_WEIGHT    = 0.35
RECENCY_RRF_WEIGHT = 0.15

# Minimum keyword overlap for BM25-only candidates (not found by vector search).
# At 5%, at least 1 in 20 query tokens must appear in the chunk.
BM25_ONLY_MIN_OVERLAP = 0.05

# ---------------------------------------------------------------------------
# BM25 tokenizer — used for both corpus indexing and query tokenization so
# that term vocabularies are consistent.
# ---------------------------------------------------------------------------
_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "of", "in", "on", "at", "to",
    "for", "with", "by", "from", "as", "it", "its", "this", "that",
    "these", "those", "and", "or", "not", "but",
})


def _tokenize(text: str) -> list[str]:
    """Normalize, strip punctuation, remove stopwords, filter single-char tokens.

    Improves BM25 term matching over the naive .lower().split() baseline.
    Based on: Robertson & Zaragoza (2009); Formal et al. SPLADE (2021).
    """
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return [tok for tok in text.split() if len(tok) > 1 and tok not in _STOP_WORDS]


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
    tokenized = [_tokenize(d["chunk_text"]) for d in _bm25_chunk_data]
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


# ---------------------------------------------------------------------------
# Cross-encoder reranker — ms-marco-MiniLM-L-6-v2.
# Loaded lazily on first hybrid_retrieve call; cached for the process lifetime.
# A cross-encoder scores (query, passage) pairs jointly, giving much more
# accurate relevance estimates than dot-product similarity at the cost of
# O(n) forward passes.  Applied after RRF fusion to re-order the final
# candidate set before URL deduplication.
# ---------------------------------------------------------------------------
_cross_encoder = None  # None = unloaded; False = unavailable (load failed)


def _get_cross_encoder():
    """Lazy-load the cross-encoder model; returns None if unavailable."""
    global _cross_encoder
    if _cross_encoder is None:
        try:
            from sentence_transformers import CrossEncoder  # noqa: PLC0415
            _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            logger.info("Cross-encoder loaded: cross-encoder/ms-marco-MiniLM-L-6-v2")
        except Exception as exc:  # pragma: no cover
            logger.warning("Cross-encoder unavailable (%s); hybrid reranking skipped", exc)
            _cross_encoder = False  # sentinel: skip on future calls
    return _cross_encoder if _cross_encoder is not False else None


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
    """Keyword overlap ratio; uses same tokenizer as BM25 for consistency."""
    query_tokens = set(_tokenize(query))
    text_tokens = set(_tokenize(text))
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
    import psycopg2.pool as _pg_pool
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
        except (psycopg2.InterfaceError, psycopg2.OperationalError,
                _pg_pool.PoolError) as exc:
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
    _deadline: float | None = None,
) -> list[dict]:
    """Hybrid retrieval: parallel vector + full-corpus BM25 search, fused via weighted RRF.

    Retrieves candidates independently from two systems:
      1. Vector search (semantic similarity via pgvector)
      2. BM25 search (keyword relevance over full corpus — correct IDF)
    Then fuses rankings using Weighted Reciprocal Rank Fusion.

    Improvements over uniform RRF:
      - Weighted RRF: vector dominates (0.50), BM25 secondary (0.35), recency weak (0.15)
      - Improved BM25 tokenization: punctuation-stripped, stopword-filtered
      - BM25-only quality gate: keyword overlap >= 5% required for non-vector candidates
      - Asymmetric candidate limits: wider vector pool (8x), conservative BM25 (4x)
      - Post-fusion p25 gate: bottom 25% by score dropped before URL deduplication

    References:
      - Ma et al., TREC Deep Learning Track (2022) — weighted dense/sparse fusion
      - Robertson & Zaragoza (2009) — BM25 tokenization
      - Formal et al., SPLADE (2021) — sparse tokenization quality
      - Karpukhin et al., DPR (2020) — hard-negative/quality filtering
      - Zou et al. (2022) — post-fusion score thresholding
    """
    K = 60  # RRF constant (standard value from the original paper)
    top_k = top_k or settings.TOP_K
    query_emb = embed_query(query)

    # Asymmetric candidate limits: wider vector pool for better dedup coverage,
    # conservative BM25 to limit noise injection.
    vector_candidate_limit = top_k * 8
    bm25_candidate_limit   = top_k * 4

    # --- Signal 1: Vector search (pgvector cosine similarity) ---
    rows = _execute_retrieval_query(
        query_emb, recency_days, sources, vector_candidate_limit
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
    bm25_scores = bm25_index.get_scores(_tokenize(query))
    bm25_top_indices = sorted(
        range(len(bm25_scores)), key=lambda i: -bm25_scores[i]
    )[:bm25_candidate_limit]
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
        # Quality gate: BM25-only candidates must have minimum keyword overlap.
        # Chunks already in vector results always pass (high semantic quality).
        # Inspired by: Karpukhin et al. DPR (2020) hard-negative filtering.
        if d["chunk_id"] not in vector_candidates:
            overlap = _compute_keyword_overlap(query, d["chunk_text"])
            if overlap < BM25_ONLY_MIN_OVERLAP:
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

    # --- Weighted Reciprocal Rank Fusion ---
    # Vector dominates (0.50); BM25 secondary (0.35); recency weak (0.15).
    # Reduces noise from recency-promoted thin content vs uniform 1/3 weighting.
    # Based on: Ma et al., TREC 2022; Lin, ECIR 2021.
    rrf: dict[int, float] = {}
    for rank, cid in enumerate(vector_ranking):
        rrf[cid] = rrf.get(cid, 0.0) + VECTOR_RRF_WEIGHT / (K + rank + 1)
    for rank, cid in enumerate(bm25_ranking):
        rrf[cid] = rrf.get(cid, 0.0) + BM25_RRF_WEIGHT / (K + rank + 1)
    for rank, cid in enumerate(recency_ranking):
        rrf[cid] = rrf.get(cid, 0.0) + RECENCY_RRF_WEIGHT / (K + rank + 1)

    for cid in merged:
        merged[cid]["score"] = rrf.get(cid, 0.0)

    # --- Post-fusion score gate: drop bottom 25% before URL deduplication ---
    # Removes marginal candidates that survived earlier filters but still rank
    # poorly after fusion. Inspired by: Zou et al. (2022) score thresholding.
    all_candidates = list(merged.values())
    if len(all_candidates) > top_k:
        scores = [c["score"] for c in all_candidates]
        p25_threshold = sorted(scores)[len(scores) // 4]
        all_candidates = [c for c in all_candidates if c["score"] >= p25_threshold]

    # --- Cross-encoder reranking ---
    # Skip if running low on time (Lambda cold-start budget) or model unavailable.
    remaining = (_deadline - time.time()) if _deadline else 999
    ce = _get_cross_encoder() if remaining > 5 else None
    if ce is None and _deadline and remaining <= 5:
        logger.info("Cross-encoder skipped — only %.1fs remaining before deadline", remaining)
    if ce is not None and all_candidates:
        ce_inputs = [(query, c["chunk_text"]) for c in all_candidates]
        ce_scores = ce.predict(ce_inputs)
        for cand, ce_score in zip(all_candidates, ce_scores):
            # Sigmoid converts logits to 0-1 probabilities for display.
            cand["score"] = 1.0 / (1.0 + math.exp(-float(ce_score)))
        all_candidates.sort(key=lambda c: c["score"], reverse=True)
    elif all_candidates:
        # Normalize RRF scores to 0-1 via min-max so the frontend can display
        # them as meaningful relevance percentages.
        scores = [c["score"] for c in all_candidates]
        min_s, max_s = min(scores), max(scores)
        if max_s > min_s:
            for c in all_candidates:
                c["score"] = (c["score"] - min_s) / (max_s - min_s)
        else:
            for c in all_candidates:
                c["score"] = 1.0

    return _deduplicate_by_url(all_candidates)[:top_k]
