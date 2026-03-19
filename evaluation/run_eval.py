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
import os
import statistics
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ragas.llms import llm_factory
from ragas.embeddings import HuggingFaceEmbeddings as RagasHFEmbeddings
from ragas.metrics.collections import (
    Faithfulness,
    AnswerRelevancy,
    ContextPrecisionWithoutReference,
)
from openai import AsyncOpenAI

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


def load_queries() -> list[dict]:
    with open(QUERIES_PATH, encoding="utf-8") as f:
        return json.load(f)


def run_single_query(query: str, mode: str) -> dict:
    """Run RAG pipeline for one query and measure latency."""
    start = time.perf_counter()
    result = ask(query, mode=mode)
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
            results[mode].append(res)

    return results


def run_ragas_evaluation(results: list[dict]) -> dict | None:
    """Run RAGAS metrics using Ollama as the LLM judge (per-sample scoring)."""
    logger.info("Setting up RAGAS with Ollama (%s)…", settings.OLLAMA_MODEL)

    try:
        client = AsyncOpenAI(
            base_url=f"{settings.OLLAMA_BASE_URL}/v1",
            api_key="ollama",
        )
        wrapped_llm = llm_factory(
            settings.OLLAMA_MODEL, provider="openai", client=client
        )
        wrapped_embeddings = RagasHFEmbeddings(
            model="sentence-transformers/all-MiniLM-L6-v2"
        )

        faith_metric = Faithfulness(llm=wrapped_llm)
        relevancy_metric = AnswerRelevancy(llm=wrapped_llm, embeddings=wrapped_embeddings)
        precision_metric = ContextPrecisionWithoutReference(llm=wrapped_llm)

        scores = {"faithfulness": [], "answer_relevancy": [], "context_precision": []}

        for i, r in enumerate(results):
            contexts = [s.get("title", "") for s in r["sources"]]
            if not contexts:
                contexts = ["N/A"]
            kwargs = dict(
                user_input=r["query"],
                response=r["answer"],
                retrieved_contexts=contexts,
            )
            logger.info("RAGAS scoring sample %d/%d…", i + 1, len(results))
            try:
                f_result = faith_metric.score(**kwargs)
                scores["faithfulness"].append(f_result.value)
            except Exception:
                scores["faithfulness"].append(float("nan"))

            try:
                ar_result = relevancy_metric.score(**kwargs)
                scores["answer_relevancy"].append(ar_result.value)
            except Exception:
                scores["answer_relevancy"].append(float("nan"))

            try:
                cp_result = precision_metric.score(**kwargs)
                scores["context_precision"].append(cp_result.value)
            except Exception:
                scores["context_precision"].append(float("nan"))

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
            f"  α={r['alpha']:.1f} β={r['beta']:.2f} γ={r['gamma']:.2f}"
            f"  {r['mean_similarity']:>10.4f}{r['mean_latency_s']:>10.3f}s"
            f"{r['p95_latency_s']:>10.3f}s  {status:>4}{marker}"
        )
    print("=" * 70)

    return {
        "all_configs": results,
        "best": best,
        "p95_threshold_s": P95_LATENCY_THRESHOLD,
    }


def main():
    queries = load_queries()
    logger.info("Loaded %d evaluation queries", len(queries))

    # Phase 1: Run both retrieval modes
    logger.info("Phase 1: Running RAG pipeline (baseline + hybrid) on all queries…")
    raw_results = run_evaluation(queries)

    # Save raw results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RESULTS_DIR / "raw_results.json"
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
    logger.info("Phase 2: Running RAGAS LLM-judged evaluation…")
    # Combine baseline + hybrid for RAGAS (so we can compare side-by-side)
    combined = raw_results["baseline"] + raw_results["hybrid"]
    ragas_scores = run_ragas_evaluation(combined)

    # Phase 3: Compute summary
    logger.info("Phase 3: Computing summary statistics…")
    summary = compute_summary(raw_results, ragas_scores)

    # Phase 4: Reranking weight grid search
    logger.info("Phase 4: Reranking weight grid search…")
    grid_results = run_grid_search(queries)
    summary["grid_search"] = grid_results

    summary_path = RESULTS_DIR / "eval_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    logger.info("Summary saved to %s", summary_path)

    # Print table
    print_comparison_table(summary)


if __name__ == "__main__":
    main()
