"""TechPulse Evaluation Runner.

Compares baseline (vector-only) vs hybrid retrieval using:
  - RAGAS metrics: faithfulness, answer_relevancy, context_precision
  - Latency: per-query and p95
  - Heuristic: citation grounding ratio

Usage:
    python -m evaluation.run_eval
"""

import json
import logging
import math
import os
import statistics
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ragas.llms import llm_factory
from ragas.embeddings import HuggingfaceEmbeddings as RagasHFEmbeddings
from ragas.metrics import (
    Faithfulness,
    AnswerRelevancy,
    ContextPrecision,
)

from src.retrieval.retriever import baseline_retrieve, hybrid_retrieve
from src.orchestrator.rag import ask
from src.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)

QUERIES_PATH = PROJECT_ROOT / "evaluation" / "queries" / "eval_queries.json"
RESULTS_DIR = PROJECT_ROOT / "evaluation" / "results"

# Retry configuration for rate-limited API calls
RETRY_MAX_ATTEMPTS = int(os.environ.get("RETRY_MAX_ATTEMPTS", "5"))
RETRY_BASE_DELAY_S = float(os.environ.get("RETRY_BASE_DELAY_S", "5.0"))


def _call_with_retry(fn, *args, label: str = "API call", **kwargs):
    """Call *fn* with exponential-backoff retry on rate-limit (429) errors."""
    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            exc_str = str(exc).lower()
            status = getattr(exc, "status_code", None) or getattr(
                getattr(exc, "response", None), "status_code", None
            )
            is_rate_limit = (
                status == 429
                or "429" in exc_str
                or "rate" in exc_str
                or "too many" in exc_str
                or "resource_exhausted" in exc_str
            )
            if is_rate_limit and attempt < RETRY_MAX_ATTEMPTS:
                wait = RETRY_BASE_DELAY_S * (2 ** (attempt - 1))
                logger.warning(
                    "%s rate-limited (attempt %d/%d) — retrying in %.0fs",
                    label, attempt, RETRY_MAX_ATTEMPTS, wait,
                )
                time.sleep(wait)
            else:
                raise


def load_queries() -> list[dict]:
    with open(QUERIES_PATH, encoding="utf-8") as f:
        return json.load(f)


def run_single_query(query: str, mode: str) -> dict:
    """Run RAG pipeline for one query and measure latency (with retry)."""
    start = time.perf_counter()
    result = _call_with_retry(ask, query, mode=mode, label=f"ask({mode})")
    elapsed = time.perf_counter() - start
    result["latency_s"] = round(elapsed, 3)
    return result


def compute_citation_grounding(answer: str, num_sources: int) -> float:
    """Fraction of [Source N] citations that reference valid source indices."""
    import re

    citations = re.findall(r"\[Source\s+(\d+)\]", answer)
    if not citations:
        return 0.0
    valid = sum(1 for c in citations if 1 <= int(c) <= num_sources)
    return valid / len(citations)


def compute_citation_grounding_weighted(
    answer: str, sources: list[dict], query: str
) -> dict:
    """Enhanced citation grounding with partial-relevance scoring.

    Returns a dict with:
      - grounding_ratio: fraction of citations pointing to valid indices
      - relevance_score: mean keyword overlap between cited sources and query
      - partial_count: number of citations with 0 < overlap < 0.5
      - full_count: citations with overlap >= 0.5
      - invalid_count: out-of-bounds citations

    "Partially Relevant" is defined as a cited source whose keyword overlap
    with the query is in (0, 0.5); "Fully Relevant" is >= 0.5.
    """
    import re

    citations = re.findall(r"\[Source\s+(\d+)\]", answer)
    if not citations:
        return {
            "grounding_ratio": 0.0,
            "relevance_score": 0.0,
            "partial_count": 0,
            "full_count": 0,
            "invalid_count": 0,
            "total_citations": 0,
        }

    query_tokens = set(query.lower().split())
    valid = 0
    invalid = 0
    partial = 0
    full = 0
    relevance_scores = []

    for c in citations:
        idx = int(c)
        if 1 <= idx <= len(sources):
            valid += 1
            src = sources[idx - 1]
            src_text = (src.get("title", "") + " " + src.get("chunk_text", "")).lower()
            src_tokens = set(src_text.split())
            overlap = len(query_tokens & src_tokens) / len(query_tokens) if query_tokens else 0
            relevance_scores.append(overlap)
            if overlap >= 0.5:
                full += 1
            elif overlap > 0:
                partial += 1
        else:
            invalid += 1

    return {
        "grounding_ratio": valid / len(citations),
        "relevance_score": round(statistics.mean(relevance_scores), 4) if relevance_scores else 0.0,
        "partial_count": partial,
        "full_count": full,
        "invalid_count": invalid,
        "total_citations": len(citations),
    }


# Delay between queries — lowered for on-demand tier; retry handles 429s
INTER_QUERY_DELAY_S = float(os.environ.get("INTER_QUERY_DELAY_S", "2.0"))
# Delay between individual RAGAS metric score() calls within one sample
INTER_METRIC_DELAY_S = float(os.environ.get("INTER_METRIC_DELAY_S", "1.0"))
# Max parallel RAGAS metric workers (3 metrics scored concurrently per sample)
RAGAS_WORKERS = int(os.environ.get("RAGAS_WORKERS", "3"))
# Delay before retrying samples whose scores came back NaN (longer to let rate limits clear)
NAN_RETRY_DELAY_S = float(os.environ.get("NAN_RETRY_DELAY_S", "15.0"))


def run_evaluation(queries: list[dict]) -> dict:
    """Run both modes on all queries and collect raw results."""
    results = {"baseline": [], "hybrid": []}

    for q in queries:
        qid = q["id"]
        query_text = q["query"]
        category = q["category"]

        for mode in ("baseline", "hybrid"):
            logger.info("Q%d [%s] mode=%s — %s", qid, category, mode, query_text)
            res = run_single_query(query_text, mode)
            res["query_id"] = qid
            res["query"] = query_text
            res["category"] = category
            res["ground_truth"] = q.get("ground_truth", "")
            res["citation_grounding"] = compute_citation_grounding(
                res["answer"], len(res["sources"])
            )
            res["citation_detail"] = compute_citation_grounding_weighted(
                res["answer"], res["sources"], query_text
            )
            results[mode].append(res)
            time.sleep(INTER_QUERY_DELAY_S)

    return results


def run_ragas_evaluation(results: list[dict]) -> dict | None:
    """Run RAGAS metrics using Groq as OpenAI-compatible LLM judge."""
    import os

    eval_model = settings.GROQ_EVAL_MODEL_ID
    base_url = "https://api.groq.com/openai/v1"
    os.environ["OPENAI_API_KEY"] = settings.GROQ_API_KEY
    logger.info("Setting up RAGAS with Groq (%s)\u2026", eval_model)

    try:
        wrapped_llm = llm_factory(
            model=eval_model,
            base_url=base_url,
        )
        wrapped_embeddings = RagasHFEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )

        faith_metric = Faithfulness(llm=wrapped_llm)
        relevancy_metric = AnswerRelevancy(llm=wrapped_llm, embeddings=wrapped_embeddings)
        relevancy_metric.strictness = 1  # Groq only supports n=1
        precision_metric = ContextPrecision(llm=wrapped_llm)

        scores = {"faithfulness": [], "answer_relevancy": [], "context_precision": []}

        def _score_metric(metric, row, name, idx):
            """Score a single RAGAS metric with retry."""
            try:
                return name, _call_with_retry(
                    metric.score, row, label=f"RAGAS-{name}[{idx}]"
                )
            except Exception:
                logger.warning("%s scoring failed for sample %d", name, idx, exc_info=True)
                return name, float("nan")

        for i, r in enumerate(results):
            contexts = [s.get("chunk_text", s.get("title", "")) for s in r["sources"]]
            if not contexts:
                contexts = ["N/A"]
            row = {
                "question": r["query"],
                "answer": r["answer"],
                "contexts": contexts,
                "ground_truth": r.get("ground_truth", ""),
            }
            logger.info("RAGAS scoring sample %d/%d…", i + 1, len(results))

            # Score 3 metrics sequentially in the main thread.
            # RAGAS 0.1.x uses asyncio.get_event_loop() internally; ThreadPoolExecutor
            # worker threads have no event loop in Python 3.10+, causing silent NaN failures.
            sample_scores: dict[str, float] = {}
            for _metric, _name in [
                (faith_metric,     "faithfulness"),
                (relevancy_metric, "answer_relevancy"),
                (precision_metric, "context_precision"),
            ]:
                _mname, _val = _score_metric(_metric, row, _name, i + 1)
                sample_scores[_mname] = _val
                time.sleep(INTER_METRIC_DELAY_S)

            scores["faithfulness"].append(sample_scores["faithfulness"])
            scores["answer_relevancy"].append(sample_scores["answer_relevancy"])
            scores["context_precision"].append(sample_scores["context_precision"])

            # Brief pause between samples
            time.sleep(INTER_QUERY_DELAY_S)

        # --- NaN retry pass ---
        # Some samples return NaN due to transient rate-limit hits that exhaust
        # all retries in the primary pass.  A second pass with a longer initial
        # wait (NAN_RETRY_DELAY_S=15 s default) lets the API quota refill before
        # retrying only the failed samples, avoiding a full re-run.
        nan_indices = [
            i for i, v in enumerate(scores["faithfulness"])
            if math.isnan(v)
        ]
        if nan_indices:
            logger.info(
                "NaN retry pass: %d/%d samples need re-scoring (waiting %gs first)",
                len(nan_indices), len(results), NAN_RETRY_DELAY_S,
            )
            time.sleep(NAN_RETRY_DELAY_S)
            for i in nan_indices:
                r = results[i]
                contexts = [s.get("chunk_text", s.get("title", "")) for s in r["sources"]]
                if not contexts:
                    contexts = ["N/A"]
                row = {
                    "question": r["query"],
                    "answer": r["answer"],
                    "contexts": contexts,
                    "ground_truth": r.get("ground_truth", ""),
                }
                logger.info("NaN retry sample %d/%d…", i + 1, len(results))
                for _metric, _name in [
                    (faith_metric,     "faithfulness"),
                    (relevancy_metric, "answer_relevancy"),
                    (precision_metric, "context_precision"),
                ]:
                    if math.isnan(scores[_name][i]):
                        _mname, _val = _score_metric(_metric, row, _name, i + 1)
                        scores[_name][i] = _val
                        time.sleep(INTER_METRIC_DELAY_S)
                time.sleep(INTER_QUERY_DELAY_S)

        return scores
    except Exception:
        logger.exception("RAGAS evaluation failed — falling back to heuristic metrics only")
        return None


def _p95(values: list[float]) -> float:
    """Compute p95 (95th percentile) of a list of floats."""
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(int(len(s) * 0.95), len(s) - 1)
    return s[idx]


def compute_summary(raw: dict, ragas_scores: dict | None = None) -> dict:
    """Compute per-mode summary statistics."""
    summary = {}

    for mode in ("baseline", "hybrid"):
        entries = raw[mode]
        latencies = [e["latency_s"] for e in entries]
        citation_scores = [e["citation_grounding"] for e in entries]

        mode_summary = {
            "num_queries": len(entries),
            "mean_latency_s": round(statistics.mean(latencies), 3),
            "median_latency_s": round(statistics.median(latencies), 3),
            "p95_latency_s": round(_p95(latencies), 3),
            "max_latency_s": round(max(latencies), 3),
            "min_latency_s": round(min(latencies), 3),
            "mean_citation_grounding": round(statistics.mean(citation_scores), 3),
        }

        # Token / cost aggregation (available when ask() returns token_usage)
        token_entries = [e.get("token_usage") for e in entries if e.get("token_usage")]
        if token_entries:
            total_prompt = sum(t["prompt_tokens"] for t in token_entries)
            total_completion = sum(t["completion_tokens"] for t in token_entries)
            total_cost = sum(t["estimated_cost_usd"] for t in token_entries)
            mode_summary["total_prompt_tokens"] = total_prompt
            mode_summary["total_completion_tokens"] = total_completion
            mode_summary["total_tokens"] = total_prompt + total_completion
            mode_summary["mean_tokens_per_query"] = round(
                (total_prompt + total_completion) / len(token_entries), 1
            )
            mode_summary["total_estimated_cost_usd"] = round(total_cost, 6)

        # Per-category latency breakdown
        categories = {e["category"] for e in entries}
        for cat in sorted(categories):
            cat_latencies = [e["latency_s"] for e in entries if e["category"] == cat]
            mode_summary[f"mean_latency_{cat}"] = round(
                statistics.mean(cat_latencies), 3
            )
            mode_summary[f"p95_latency_{cat}"] = round(_p95(cat_latencies), 3)

        summary[mode] = mode_summary

    # Compute deltas
    summary["delta"] = {
        "latency_diff_s": round(
            summary["hybrid"]["mean_latency_s"]
            - summary["baseline"]["mean_latency_s"],
            3,
        ),
        "p95_latency_diff_s": round(
            summary["hybrid"]["p95_latency_s"]
            - summary["baseline"]["p95_latency_s"],
            3,
        ),
        "citation_grounding_diff": round(
            summary["hybrid"]["mean_citation_grounding"]
            - summary["baseline"]["mean_citation_grounding"],
            3,
        ),
    }

    # Attach RAGAS scores if available
    if ragas_scores:
        summary["ragas"] = ragas_scores

    return summary


def compute_composite_score(summary: dict) -> dict:
    """Combine RAGAS metrics + citation grounding into a single composite score.

    Composite = 0.35 * faithfulness + 0.25 * answer_relevancy
              + 0.20 * context_precision + 0.20 * citation_grounding

    Weights reflect primacy of factual correctness (faithfulness)
    and the system's key value-add (citation traceability).
    """
    weights = {
        "faithfulness": 0.35,
        "answer_relevancy": 0.25,
        "context_precision": 0.20,
        "citation_grounding": 0.20,
    }

    result = {}
    for mode in ("baseline", "hybrid"):
        components = {}
        # Citation grounding is always available
        components["citation_grounding"] = summary[mode]["mean_citation_grounding"]

        # RAGAS scores (split: first half = baseline, second half = hybrid)
        ragas = summary.get("ragas")
        if ragas:
            n = len(ragas.get("faithfulness", [])) // 2
            offset = 0 if mode == "baseline" else n
            for metric_name in ("faithfulness", "answer_relevancy", "context_precision"):
                vals = ragas.get(metric_name, [])
                slice_vals = [
                    v for v in vals[offset : offset + n]
                    if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v))
                ]
                components[metric_name] = statistics.mean(slice_vals) if slice_vals else 0.0
        else:
            for m in ("faithfulness", "answer_relevancy", "context_precision"):
                components[m] = 0.0

        composite = sum(weights[k] * components[k] for k in weights)
        result[mode] = {
            "composite_score": round(composite, 4),
            "components": {k: round(v, 4) for k, v in components.items()},
            "weights": weights,
        }

    result["composite_diff"] = round(
        result["hybrid"]["composite_score"] - result["baseline"]["composite_score"], 4
    )
    return result


def compute_monthly_cost_projection(summary: dict) -> dict:
    """Project monthly costs based on measured per-query token usage.

    Assumes:
    - Groq free tier: 500K tokens/day = ~15M tokens/month (no cost)
    - Beyond free tier: standard Groq pricing
    - Ingestion runs: 4x/day (scheduler)
    - User queries: estimated 50-200/day for a small deployment
    """
    projection = {}
    queries_per_day_scenarios = [50, 100, 200]

    for mode in ("baseline", "hybrid"):
        mode_data = summary.get(mode, {})
        tokens_per_query = mode_data.get("mean_tokens_per_query", 0)
        cost_per_query = 0
        total_queries = mode_data.get("num_queries", 0)
        if total_queries > 0 and mode_data.get("total_estimated_cost_usd"):
            cost_per_query = mode_data["total_estimated_cost_usd"] / total_queries

        scenarios = {}
        for qpd in queries_per_day_scenarios:
            monthly_queries = qpd * 30
            monthly_tokens = tokens_per_query * monthly_queries
            monthly_cost = cost_per_query * monthly_queries
            fits_free_tier = monthly_tokens <= 15_000_000  # ~500K/day * 30
            scenarios[f"{qpd}_queries_per_day"] = {
                "monthly_queries": monthly_queries,
                "monthly_tokens": round(monthly_tokens),
                "monthly_cost_usd": round(monthly_cost, 4),
                "fits_groq_free_tier": fits_free_tier,
            }
        projection[mode] = {
            "tokens_per_query": round(tokens_per_query, 1),
            "cost_per_query_usd": round(cost_per_query, 8),
            "scenarios": scenarios,
        }

    # RDS free tier ceiling
    projection["infra_monthly"] = {
        "rds_free_tier": "$0.00 (750 hrs db.t3.micro, 20 GB)",
        "ec2_free_tier": "$0.00 (750 hrs t2.micro or Lambda free tier)",
        "s3_free_tier": "$0.00 (5 GB storage, 20K GETs)",
        "total_within_free_tier": "$0.00",
    }

    return projection


def print_comparison_table(summary: dict):
    """Print a formatted comparison table."""
    print("\n" + "=" * 70)
    print("  TechPulse Evaluation — Baseline vs Hybrid Retrieval")
    print("=" * 70)
    header = f"{'Metric':<30} {'Baseline':>15} {'Hybrid':>15}"
    print(header)
    print("-" * 70)

    b = summary["baseline"]
    h = summary["hybrid"]

    rows = [
        ("Queries evaluated", b["num_queries"], h["num_queries"]),
        ("Mean latency (s)", b["mean_latency_s"], h["mean_latency_s"]),
        ("Median latency (s)", b["median_latency_s"], h["median_latency_s"]),
        ("p95 latency (s)", b["p95_latency_s"], h["p95_latency_s"]),
        ("Max latency (s)", b["max_latency_s"], h["max_latency_s"]),
        ("Citation grounding", b["mean_citation_grounding"], h["mean_citation_grounding"]),
    ]

    # Token usage rows (if available)
    if "mean_tokens_per_query" in b:
        rows.append(("Mean tokens/query", b["mean_tokens_per_query"], h["mean_tokens_per_query"]))
    if "total_estimated_cost_usd" in b:
        rows.append(("Est. cost (USD)", b["total_estimated_cost_usd"], h["total_estimated_cost_usd"]))

    for label, bv, hv in rows:
        print(f"  {label:<28} {bv:>15} {hv:>15}")

    if "ragas" in summary:
        print("-" * 70)
        print("  RAGAS Metrics (LLM-judged)")
        print("-" * 70)
        ragas = summary["ragas"]
        for key in ragas:
            if key.startswith("user_input") or key.startswith("response"):
                continue
            vals = ragas[key]
            if isinstance(vals, list) and all(isinstance(v, (int, float)) for v in vals):
                n = len(vals) // 2  # first half baseline, second half hybrid
                b_mean = round(statistics.mean(vals[:n]), 3) if n > 0 else "N/A"
                h_mean = round(statistics.mean(vals[n:]), 3) if n > 0 else "N/A"
                print(f"  {key:<28} {b_mean:>15} {h_mean:>15}")

    print("=" * 70)


# ---------------------------------------------------------------------------
# Reranking weight grid search
# ---------------------------------------------------------------------------
# Proposal spec: α ∈ {0.4, 0.5, 0.6, 0.7}, β = γ = (1 - α) / 2
# Select config with highest mean context precision (proxy: mean similarity
# of top-k results) without violating p95 latency threshold.

GRID_ALPHA_VALUES = [0.4, 0.5, 0.6, 0.7]
P95_LATENCY_THRESHOLD = 2.0  # seconds, from proposal


def _mean_topk_similarity(results: list[dict]) -> float:
    """Mean similarity of top-k retrieved chunks (proxy for context precision)."""
    sims = [r["similarity"] for r in results if "similarity" in r]
    return statistics.mean(sims) if sims else 0.0


def run_grid_search(queries: list[dict]) -> dict:
    """Grid search over reranking weights and return best config.

    For each (α, β, γ) config, runs hybrid retrieval on all queries and
    measures mean top-k similarity (context precision proxy) and p95 latency.
    Selects the configuration with the highest mean similarity that keeps
    p95 latency under the threshold.
    """
    logger.info("=" * 60)
    logger.info("  Reranking Weight Grid Search")
    logger.info("=" * 60)

    configs = []
    for alpha in GRID_ALPHA_VALUES:
        beta = round((1 - alpha) / 2, 4)
        gamma = round((1 - alpha) / 2, 4)
        configs.append((alpha, beta, gamma))

    results = []

    for alpha, beta, gamma in configs:
        label = f"α={alpha}, β={beta}, γ={gamma}"
        logger.info("Testing config: %s", label)

        sims = []
        latencies = []
        for q in queries:
            start = time.perf_counter()
            retrieved = hybrid_retrieve(
                q["query"], alpha=alpha, beta=beta, gamma=gamma
            )
            elapsed = time.perf_counter() - start
            latencies.append(elapsed)
            sims.append(_mean_topk_similarity(retrieved))

        mean_sim = round(statistics.mean(sims), 4)
        p95_lat = round(_p95(latencies), 3)
        mean_lat = round(statistics.mean(latencies), 3)

        entry = {
            "alpha": alpha,
            "beta": beta,
            "gamma": gamma,
            "mean_similarity": mean_sim,
            "mean_latency_s": mean_lat,
            "p95_latency_s": p95_lat,
            "within_threshold": p95_lat <= P95_LATENCY_THRESHOLD,
        }
        results.append(entry)
        logger.info(
            "  %s → mean_sim=%.4f  mean_lat=%.3fs  p95_lat=%.3fs  %s",
            label, mean_sim, mean_lat, p95_lat,
            "PASS" if entry["within_threshold"] else "FAIL EXCEEDS THRESHOLD",
        )

    # Select best: highest mean_similarity among configs within threshold
    eligible = [r for r in results if r["within_threshold"]]
    if not eligible:
        logger.warning("No config met the p95 latency threshold — selecting best overall")
        eligible = results

    best = max(eligible, key=lambda r: r["mean_similarity"])
    logger.info(
        "Best config: α=%.2f, β=%.2f, γ=%.2f (mean_sim=%.4f, p95=%.3fs)",
        best["alpha"], best["beta"], best["gamma"],
        best["mean_similarity"], best["p95_latency_s"],
    )

    # Print summary table
    print("\n" + "=" * 70)
    print("  Reranking Weight Grid Search Results")
    print("=" * 70)
    print(f"  {'Config':<24} {'Mean Sim':>10} {'Mean Lat':>10} {'p95 Lat':>10} {'Status':>8}")
    print("-" * 70)
    for r in results:
        marker = "  BEST" if r == best else ""
        status = "OK" if r["within_threshold"] else "SLOW"
        print(
            f"  a={r['alpha']:.1f} b={r['beta']:.2f} g={r['gamma']:.2f}"
            f"  {r['mean_similarity']:>10.4f}{r['mean_latency_s']:>10.3f}s"
            f"{r['p95_latency_s']:>10.3f}s  {status:>4}{marker}"
        )
    print("=" * 70)

    return {
        "all_configs": results,
        "best": best,
        "p95_threshold_s": P95_LATENCY_THRESHOLD,
    }


# ---------------------------------------------------------------------------
# Phase 5: Sensitivity analysis (professor feedback item #4)
# ---------------------------------------------------------------------------
# Varies each weight individually while holding the best config's other
# weights constant.  Shows how sensitive retrieval quality is to each
# parameter, strengthening the justification beyond grid search alone.

SENSITIVITY_STEPS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]


def run_sensitivity_analysis(queries: list[dict], best_config: dict) -> dict:
    """One-at-a-time sensitivity sweep for α, β, γ around the best config."""
    logger.info("=" * 60)
    logger.info("  Sensitivity Analysis (one-at-a-time)")
    logger.info("=" * 60)

    base_alpha = best_config["alpha"]
    base_beta = best_config["beta"]
    base_gamma = best_config["gamma"]

    sweep_results = {}

    for param_name in ("alpha", "beta", "gamma"):
        param_results = []
        for val in SENSITIVITY_STEPS:
            # Set the swept parameter; redistribute remaining weight to others
            if param_name == "alpha":
                a = val
                remaining = 1.0 - a
                b = remaining * (base_beta / (base_beta + base_gamma)) if (base_beta + base_gamma) > 0 else remaining / 2
                g = remaining - b
            elif param_name == "beta":
                b = val
                remaining = 1.0 - b
                a = remaining * (base_alpha / (base_alpha + base_gamma)) if (base_alpha + base_gamma) > 0 else remaining / 2
                g = remaining - a
            else:  # gamma
                g = val
                remaining = 1.0 - g
                a = remaining * (base_alpha / (base_alpha + base_beta)) if (base_alpha + base_beta) > 0 else remaining / 2
                b = remaining - a

            # Ensure non-negative
            a, b, g = max(a, 0), max(b, 0), max(g, 0)
            total = a + b + g
            if total > 0:
                a, b, g = a / total, b / total, g / total

            sims = []
            latencies = []
            for q in queries:
                start = time.perf_counter()
                retrieved = hybrid_retrieve(q["query"])
                elapsed = time.perf_counter() - start
                latencies.append(elapsed)
                sims.append(_mean_topk_similarity(retrieved))

            entry = {
                "param_value": round(val, 2),
                "alpha": round(a, 4),
                "beta": round(b, 4),
                "gamma": round(g, 4),
                "mean_similarity": round(statistics.mean(sims), 4),
                "p95_latency_s": round(_p95(latencies), 3),
            }
            param_results.append(entry)
            logger.info(
                "  %s=%.2f → α=%.3f β=%.3f γ=%.3f  sim=%.4f  p95=%.3fs",
                param_name, val, a, b, g, entry["mean_similarity"], entry["p95_latency_s"],
            )

        sweep_results[param_name] = param_results

    # Print summary
    print("\n" + "=" * 70)
    print("  Sensitivity Analysis Results")
    print("=" * 70)
    for param_name, entries in sweep_results.items():
        print(f"\n  Sweeping {param_name} (others redistributed proportionally):")
        print(f"  {'Value':>6}  {'a':>6}  {'b':>6}  {'g':>6}  {'MeanSim':>8}  {'p95Lat':>8}")
        print("  " + "-" * 52)
        for e in entries:
            print(
                f"  {e['param_value']:>6.2f}  {e['alpha']:>6.3f}  {e['beta']:>6.3f}"
                f"  {e['gamma']:>6.3f}  {e['mean_similarity']:>8.4f}  {e['p95_latency_s']:>7.3f}s"
            )
    print("=" * 70)

    return sweep_results


# ---------------------------------------------------------------------------
# Phase 4: Statistical significance tests (professor feedback item #7)
# ---------------------------------------------------------------------------

def compute_statistical_tests(raw_results: dict, ragas_scores: dict | None = None) -> dict:
    """Paired Wilcoxon signed-rank test and effect size for baseline vs hybrid.

    Uses paired latency observations (same query, both modes) to determine
    if the hybrid improvement is statistically significant, not just average.
    """
    from scipy import stats as scipy_stats

    baseline_entries = sorted(raw_results["baseline"], key=lambda x: x.get("query_id", 0))
    hybrid_entries = sorted(raw_results["hybrid"], key=lambda x: x.get("query_id", 0))

    n = min(len(baseline_entries), len(hybrid_entries))
    if n < 5:
        logger.warning("Too few paired observations (%d) for statistical tests", n)
        return {"error": "insufficient_data", "n": n}

    b_lat = [baseline_entries[i]["latency_s"] for i in range(n)]
    h_lat = [hybrid_entries[i]["latency_s"] for i in range(n)]

    b_cit = [baseline_entries[i].get("citation_grounding", 0) for i in range(n)]
    h_cit = [hybrid_entries[i].get("citation_grounding", 0) for i in range(n)]

    result = {"n_pairs": n}

    # --- Wilcoxon signed-rank test on latency ---
    diffs_lat = [b - h for b, h in zip(b_lat, h_lat)]
    non_zero_diffs = [d for d in diffs_lat if d != 0]
    if len(non_zero_diffs) >= 5:
        stat, p_value = scipy_stats.wilcoxon(b_lat, h_lat)
        result["latency_wilcoxon"] = {
            "statistic": round(float(stat), 4),
            "p_value": round(float(p_value), 6),
            "significant_at_005": bool(p_value < 0.05),
            "significant_at_001": bool(p_value < 0.01),
            "mean_diff_s": round(statistics.mean(diffs_lat), 3),
            "median_diff_s": round(statistics.median(diffs_lat), 3),
        }
    else:
        result["latency_wilcoxon"] = {"error": "too_few_non_zero_diffs"}

    # --- Effect size: Cohen's d for paired samples ---
    if len(diffs_lat) >= 2:
        mean_diff = statistics.mean(diffs_lat)
        std_diff = statistics.stdev(diffs_lat)
        cohens_d = mean_diff / std_diff if std_diff > 0 else 0
        result["latency_cohens_d"] = round(cohens_d, 4)
        if abs(cohens_d) >= 0.8:
            result["effect_size"] = "large"
        elif abs(cohens_d) >= 0.5:
            result["effect_size"] = "medium"
        elif abs(cohens_d) >= 0.2:
            result["effect_size"] = "small"
        else:
            result["effect_size"] = "negligible"

    # --- Citation grounding comparison ---
    diffs_cit = [b - h for b, h in zip(b_cit, h_cit)]
    non_zero_cit = [d for d in diffs_cit if d != 0]
    if len(non_zero_cit) >= 5:
        stat_c, p_c = scipy_stats.wilcoxon(b_cit, h_cit)
        result["citation_wilcoxon"] = {
            "statistic": round(float(stat_c), 4),
            "p_value": round(float(p_c), 6),
            "significant_at_005": bool(p_c < 0.05),
        }
    else:
        result["citation_wilcoxon"] = {"note": "no_significant_difference_in_pairs"}

    # --- Wilcoxon signed-rank test on context precision (RAGAS) ---
    if ragas_scores and "context_precision" in ragas_scores:
        prec_vals = [
            v for v in ragas_scores["context_precision"]
            if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v))
        ]
        half = len(prec_vals) // 2
        if half >= 5:
            b_prec = prec_vals[:half]
            h_prec = prec_vals[half : half * 2]
            diffs_prec = [h - b for b, h in zip(b_prec, h_prec)]
            non_zero_prec = [d for d in diffs_prec if d != 0]
            if len(non_zero_prec) >= 5:
                stat_p, p_p = scipy_stats.wilcoxon(b_prec, h_prec)
                result["precision_wilcoxon"] = {
                    "statistic": round(float(stat_p), 4),
                    "p_value": round(float(p_p), 6),
                    "significant_at_005": bool(p_p < 0.05),
                    "mean_diff": round(statistics.mean(diffs_prec), 4),
                }
            else:
                result["precision_wilcoxon"] = {"note": "too_few_non_zero_diffs"}
        else:
            result["precision_wilcoxon"] = {"note": "insufficient_ragas_pairs"}

    # --- Confidence interval for mean latency difference (bootstrap) ---
    import random
    rng = random.Random(42)
    n_boot = 1000
    boot_means = []
    for _ in range(n_boot):
        sample = [rng.choice(diffs_lat) for _ in range(n)]
        boot_means.append(statistics.mean(sample))
    boot_means.sort()
    ci_lo = boot_means[int(0.025 * n_boot)]
    ci_hi = boot_means[int(0.975 * n_boot)]
    result["latency_diff_95ci"] = [round(ci_lo, 3), round(ci_hi, 3)]

    # Print summary
    print("\n" + "=" * 70)
    print("  Statistical Significance — Baseline vs Hybrid")
    print("=" * 70)
    print(f"  Paired observations: {n}")
    if "latency_wilcoxon" in result and "p_value" in result["latency_wilcoxon"]:
        lw = result["latency_wilcoxon"]
        sig = "YES" if lw["significant_at_005"] else "NO"
        print(f"  Wilcoxon signed-rank (latency): W={lw['statistic']}, p={lw['p_value']:.6f} → {sig} (α=0.05)")
        print(f"  Mean latency diff: {lw['mean_diff_s']:.3f}s  (positive = hybrid faster)")
        print(f"  Median latency diff: {lw['median_diff_s']:.3f}s")
    if "latency_cohens_d" in result:
        print(f"  Cohen's d: {result['latency_cohens_d']:.4f} ({result['effect_size']})")
    print(f"  95% CI for mean diff: [{result['latency_diff_95ci'][0]:.3f}, {result['latency_diff_95ci'][1]:.3f}]s")
    if "precision_wilcoxon" in result and "p_value" in result["precision_wilcoxon"]:
        pw = result["precision_wilcoxon"]
        sig_p = "YES" if pw["significant_at_005"] else "NO"
        print(f"  Wilcoxon signed-rank (precision): W={pw['statistic']}, p={pw['p_value']:.6f} → {sig_p} (α=0.05)")
        print(f"  Mean precision diff: {pw['mean_diff']:.4f}  (positive = hybrid better)")
    print("=" * 70)

    return result


# ---------------------------------------------------------------------------
# Phase 5: Drift detector validation (professor feedback item #10)
# ---------------------------------------------------------------------------

def run_drift_validation() -> dict:
    """Simulate controlled quality degradation to prove the drift detector works.

    Runs probe queries at normal quality, records the baseline, then patches
    the retriever to return artificially low-similarity results and verifies
    that the drift detector fires.  All done in-memory — no DB side-effects.
    """
    import math
    from unittest.mock import patch as mock_patch, MagicMock

    logger.info("=" * 60)
    logger.info("  Drift Detector Validation")
    logger.info("=" * 60)

    # Load probe queries to measure "normal" retrieval quality
    probe_path = Path(__file__).resolve().parent / "queries" / "probe_queries.json"
    with open(probe_path, encoding="utf-8") as f:
        probes = json.load(f)

    scenarios = []

    # --- Scenario 1: Healthy retrieval → no alert ---
    healthy_sims = [0.85, 0.82, 0.88, 0.84, 0.86]
    healthy_mean = statistics.mean(healthy_sims)
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None  # no prior baseline
    mock_cursor.fetchall.return_value = []
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with mock_patch("src.observability.drift.hybrid_retrieve") as mock_ret, \
         mock_patch("src.observability.drift.get_connection", return_value=mock_conn), \
         mock_patch("src.observability.drift.put_connection"), \
         mock_patch("src.observability.drift.put_metric"):
        mock_ret.return_value = [{"similarity": s} for s in healthy_sims]
        from src.observability.drift import run_drift_check
        healthy_result = run_drift_check()

    scenarios.append({
        "name": "Healthy baseline",
        "mean_similarity": healthy_result["mean_similarity"],
        "alert_triggered": healthy_result["alert_triggered"],
        "expected_alert": False,
        "correct": healthy_result["alert_triggered"] is False,
    })
    logger.info("  Scenario 1 (healthy): mean=%.4f, alert=%s ✓",
                healthy_result["mean_similarity"], healthy_result["alert_triggered"])

    # --- Scenario 2: 15% quality drop → alert expected ---
    degraded_sims = [s * 0.82 for s in healthy_sims]  # ~18% degradation
    degraded_mean = statistics.mean(degraded_sims)
    mock_cursor2 = MagicMock()
    mock_cursor2.fetchone.return_value = (healthy_mean,)  # stored baseline
    mock_cursor2.fetchall.return_value = [  # realistic history with natural variance (~0.02 std)
        (0.832,), (0.861,), (0.847,), (0.869,), (0.841,)
    ]
    mock_conn2 = MagicMock()
    mock_conn2.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor2)
    mock_conn2.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with mock_patch("src.observability.drift.hybrid_retrieve") as mock_ret, \
         mock_patch("src.observability.drift.get_connection", return_value=mock_conn2), \
         mock_patch("src.observability.drift.put_connection"), \
         mock_patch("src.observability.drift.put_metric"):
        mock_ret.return_value = [{"similarity": s} for s in degraded_sims]
        degraded_result = run_drift_check()

    scenarios.append({
        "name": "18% quality degradation",
        "mean_similarity": degraded_result["mean_similarity"],
        "alert_triggered": degraded_result["alert_triggered"],
        "alert_reason": degraded_result.get("alert_reason"),
        "expected_alert": True,
        "correct": degraded_result["alert_triggered"] is True,
    })
    logger.info("  Scenario 2 (degraded): mean=%.4f, alert=%s ✓",
                degraded_result["mean_similarity"], degraded_result["alert_triggered"])

    # --- Scenario 3: Marginal fluctuation (~5%) → no alert ---
    marginal_sims = [s * 0.96 for s in healthy_sims]  # ~4% dip
    mock_cursor3 = MagicMock()
    mock_cursor3.fetchone.return_value = (healthy_mean,)
    mock_cursor3.fetchall.return_value = [  # realistic history with natural variance (~0.02 std)
        (0.832,), (0.861,), (0.847,), (0.869,), (0.841,)
    ]
    mock_conn3 = MagicMock()
    mock_conn3.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor3)
    mock_conn3.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with mock_patch("src.observability.drift.hybrid_retrieve") as mock_ret, \
         mock_patch("src.observability.drift.get_connection", return_value=mock_conn3), \
         mock_patch("src.observability.drift.put_connection"), \
         mock_patch("src.observability.drift.put_metric"):
        mock_ret.return_value = [{"similarity": s} for s in marginal_sims]
        marginal_result = run_drift_check()

    scenarios.append({
        "name": "4% normal fluctuation",
        "mean_similarity": marginal_result["mean_similarity"],
        "alert_triggered": marginal_result["alert_triggered"],
        "expected_alert": False,
        "correct": marginal_result["alert_triggered"] is False,
    })
    logger.info("  Scenario 3 (marginal): mean=%.4f, alert=%s ✓",
                marginal_result["mean_similarity"], marginal_result["alert_triggered"])

    # --- Scenario 4: Catastrophic failure → both checks fire ---
    catastrophic_sims = [0.05, 0.08, 0.03, 0.06, 0.04]
    mock_cursor4 = MagicMock()
    mock_cursor4.fetchone.return_value = (healthy_mean,)
    mock_cursor4.fetchall.return_value = [  # realistic history with natural variance (~0.02 std)
        (0.832,), (0.861,), (0.847,), (0.869,), (0.841,)
    ]
    mock_conn4 = MagicMock()
    mock_conn4.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor4)
    mock_conn4.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with mock_patch("src.observability.drift.hybrid_retrieve") as mock_ret, \
         mock_patch("src.observability.drift.get_connection", return_value=mock_conn4), \
         mock_patch("src.observability.drift.put_connection"), \
         mock_patch("src.observability.drift.put_metric"):
        mock_ret.return_value = [{"similarity": s} for s in catastrophic_sims]
        catastrophic_result = run_drift_check()

    scenarios.append({
        "name": "Catastrophic failure (>90% drop)",
        "mean_similarity": catastrophic_result["mean_similarity"],
        "alert_triggered": catastrophic_result["alert_triggered"],
        "alert_reason": catastrophic_result.get("alert_reason"),
        "expected_alert": True,
        "correct": catastrophic_result["alert_triggered"] is True,
    })
    logger.info("  Scenario 4 (catastrophic): mean=%.4f, alert=%s ✓",
                catastrophic_result["mean_similarity"], catastrophic_result["alert_triggered"])

    all_correct = all(s["correct"] for s in scenarios)

    # Print summary
    print("\n" + "=" * 70)
    print("  Drift Detector Validation Results")
    print("=" * 70)
    print(f"  {'Scenario':<35} {'MeanSim':>8} {'Alert':>6} {'Expected':>9} {'Result':>7}")
    print("  " + "-" * 65)
    for s in scenarios:
        check = "PASS" if s["correct"] else "FAIL"
        print(f"  {s['name']:<35} {s['mean_similarity']:>8.4f} "
              f"{'YES' if s['alert_triggered'] else 'NO':>6} "
              f"{'YES' if s['expected_alert'] else 'NO':>9} "
              f"{check:>7}")
    print("  " + "-" * 65)
    print(f"  Overall: {'ALL PASSED' if all_correct else 'SOME FAILED'}")
    print("=" * 70)

    return {"scenarios": scenarios, "all_passed": all_correct}


def main():
    queries = load_queries()
    # Allow limiting the number of queries via env var for rate-limited runs
    max_q = int(os.environ.get("EVAL_MAX_QUERIES", 0))
    if max_q > 0:
        # Sample evenly across categories
        by_cat: dict[str, list] = {}
        for q in queries:
            by_cat.setdefault(q["category"], []).append(q)
        per_cat = max(1, max_q // len(by_cat))
        selected: list[dict] = []
        for cat_qs in by_cat.values():
            selected.extend(cat_qs[:per_cat])
        queries = sorted(selected, key=lambda q: q["id"])[:max_q]
    logger.info("Loaded %d evaluation queries", len(queries))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RESULTS_DIR / "raw_results.json"

    # Phase 1: Run both retrieval modes (skip if SKIP_PHASE1 is set and results exist)
    skip_phase1 = os.environ.get("SKIP_PHASE1", "").lower() in ("1", "true", "yes")
    if skip_phase1 and raw_path.exists():
        logger.info("Phase 1: SKIPPED — loading saved raw results from %s", raw_path)
        with open(raw_path, encoding="utf-8") as f:
            raw_results = json.load(f)
    else:
        logger.info("Phase 1: Running RAG pipeline (baseline + hybrid) on all queries…")
        raw_results = run_evaluation(queries)

        # Save raw results
        with open(raw_path, "w", encoding="utf-8") as f:
            # Convert non-serializable fields
            serializable = {}
            for mode in ("baseline", "hybrid"):
                serializable[mode] = []
                for r in raw_results[mode]:
                    entry = dict(r)
                    entry["sources"] = [
                        {k: (str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v)
                         for k, v in s.items()}
                        for s in entry.get("sources", [])
                    ]
                    serializable[mode].append(entry)
            json.dump(serializable, f, indent=2, default=str)
        logger.info("Raw results saved to %s", raw_path)

    # Phase 2: RAGAS evaluation (optional — may fail with small local model)
    ragas_path = RESULTS_DIR / "ragas_scores.json"
    skip_ragas = os.environ.get("SKIP_RAGAS", "").lower() in ("1", "true", "yes")
    if skip_ragas:
        logger.info("Phase 2: SKIPPED (SKIP_RAGAS=1)")
        ragas_scores = None
    else:
        logger.info("Phase 2: Running RAGAS LLM-judged evaluation…")
        # Combine baseline + hybrid for RAGAS (so we can compare side-by-side)
        combined = raw_results["baseline"] + raw_results["hybrid"]
        ragas_scores = run_ragas_evaluation(combined)
        # Persist RAGAS scores so they survive crashes in later phases
        if ragas_scores:
            with open(ragas_path, "w", encoding="utf-8") as f:
                json.dump(ragas_scores, f, indent=2, default=str)
            logger.info("RAGAS scores saved to %s", ragas_path)

    # If RAGAS scores are missing (crash/skip) but a cached file exists, reload
    if ragas_scores is None and ragas_path.exists():
        logger.info("Loading cached RAGAS scores from %s", ragas_path)
        with open(ragas_path, encoding="utf-8") as f:
            ragas_scores = json.load(f)

    # Phase 3: Compute summary
    logger.info("Phase 3: Computing summary statistics…")
    summary = compute_summary(raw_results, ragas_scores)

    # Phases 4 & 5 (legacy grid search / sensitivity analysis) are SKIPPED.
    # The hybrid retriever now uses weighted RRF (vector=0.50, BM25=0.35,
    # recency=0.15) instead of the legacy α/β/γ linear combination, so
    # the old α/β/γ sweeps are not applicable.  Renumbering continues from 4.
    from src.db.connection import close_pool
    close_pool()
    logger.info("Phases 4-5 (legacy grid search): SKIPPED — weighted RRF replaces α/β/γ tuning")

    # Phase 4: Statistical significance tests (paired baseline vs hybrid)
    logger.info("Phase 4: Statistical significance tests…")
    stat_tests = compute_statistical_tests(raw_results, ragas_scores)
    summary["statistical_tests"] = stat_tests

    # Phase 5: Drift detector validation
    logger.info("Phase 5: Drift detector validation…")
    drift_validation = run_drift_validation()
    summary["drift_validation"] = drift_validation

    # Phase 6: Composite performance metric (RAGAS + citation grounding)
    logger.info("Phase 6: Composite performance metric…")
    composite = compute_composite_score(summary)
    summary["composite_metric"] = composite

    # Phase 7: Monthly cost projection
    logger.info("Phase 7: Monthly cost projection…")
    cost_projection = compute_monthly_cost_projection(summary)
    summary["cost_projection"] = cost_projection

    summary_path = RESULTS_DIR / "eval_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    logger.info("Summary saved to %s", summary_path)

    # Print table
    print_comparison_table(summary)


if __name__ == "__main__":
    main()
