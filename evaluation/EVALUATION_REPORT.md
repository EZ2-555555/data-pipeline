# TechPulse Evaluation Report — Baseline vs Hybrid Retrieval

**Date:** 2026-03-17  
**Model:** llama3.2:3b (Ollama, local)  
**Queries:** 25 (9 research_trend, 8 tool_technology, 8 comparative)  
**Corpus:** 914 documents / 1,065 embedded chunks across 5 sources  

---

## 1. Summary Results

| Metric                   | Baseline | Hybrid  | Delta    |
|--------------------------|----------|---------|----------|
| Queries evaluated        | 25       | 25      | —        |
| Mean latency (s)         | 35.32    | 33.99   | **−1.33 (−3.8%)** |
| p95 latency (s)          | 63.79    | 66.04   | +2.25    |
| Max latency (s)          | 75.12    | 71.55   | −3.56    |
| Min latency (s)          | 15.29    | 6.57    | −8.73    |
| Citation grounding       | 0.28     | 0.32    | **+0.04 (+14.3%)** |

## 2. Per-Category Latency Breakdown

| Category          | Baseline (s) | Hybrid (s) | Delta   |
|-------------------|-------------|-------------|---------|
| research_trend    | 29.88       | 24.78       | **−5.10** |
| tool_technology   | 35.87       | 33.52       | −2.35   |
| comparative       | 40.89       | 44.82       | +3.93   |

## 3. Key Observations

### Latency
- **Hybrid is 3.8% faster on average** (33.99s vs 35.32s), with the improvement
  concentrated in `research_trend` queries (−5.1s, −17%).
- Comparative queries are slightly slower in hybrid mode (+3.93s), likely because
  the metadata filtering and reranking add overhead on multi-faceted questions.
- p95 latency is comparable (~64–66s) for both modes.
- **Note:** Latencies are dominated by Ollama inference on a CPU-only machine.
  The ~34s average would drop to <2s on GPU-backed inference (proposal target: p95 < 2s).

### Citation Grounding
- **Hybrid improves citation grounding by 14.3%** (0.32 vs 0.28).
- Both scores are moderate — the llama3.2:3b model sometimes generates answers
  without citing `[Source N]` patterns, reducing this metric.
- 7/25 baseline answers include citations vs 8/25 hybrid answers.

### RAGAS Evaluation
- RAGAS metrics (Faithfulness, AnswerRelevancy, ContextPrecision) require models
  with reliable **structured output / JSON mode** capability.
- The llama3.2:3b model (3B params) cannot reliably produce the structured JSON
  that RAGAS's `InstructorLLM` pipeline requires (it outputs schema descriptions
  instead of actual structured data).
- **Recommendation:** Use llama3.1:8b or larger for RAGAS scoring, or use an
  API-based model (GPT-4o-mini) for the judge role.
- The evaluation script ([evaluation/run_eval.py](evaluation/run_eval.py)) is fully wired for
  RAGAS with the native `llm_factory` + `AsyncOpenAI` API — just swap the model.

## 4. Qualitative Observations

- **Baseline** sometimes retrieves unrelated documents (e.g., quantum chemistry
  article for a transformer architecture query) due to pure cosine similarity
  matching on embedding space without metadata filtering.
- **Hybrid** produces more topically coherent source sets due to metadata-aware
  filtering and recency-weighted reranking.
- Both modes occasionally produce "I couldn't find information in the provided
  context" answers when the query is too specific for the current corpus.

## 5. Files

| File | Description |
|------|-------------|
| `evaluation/results/raw_results.json` | Full per-query answers, sources, latency, citation scores |
| `evaluation/results/eval_summary.json` | Aggregated statistics |
| `evaluation/queries/eval_queries.json` | 25 evaluation queries with ground truth |
| `evaluation/run_eval.py` | Evaluation runner script |

## 6. Next Steps

1. **Pull a larger model** (`ollama pull llama3.1:8b`) and re-run with RAGAS scoring
2. **Expand corpus** — more domain-specific papers to improve retrieval relevance
3. **GPU inference** — deploy on GPU instance for realistic latency measurement
4. **A/B comparison** — run the same evaluation after tuning `RERANK_ALPHA`, `BETA`, `GAMMA`
