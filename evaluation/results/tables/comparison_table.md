# Baseline vs Hybrid Comparison — 06 April 2026

| Metric              | Baseline | Hybrid | Delta  |
|---------------------|----------|--------|--------|
| Queries per mode    | 50       | 50     |        |
| Mean Latency (s)    | 1.125    | 2.487  | +1.362 |
| P95 Latency (s)     | 1.477    | 2.444  | +0.967 |
| Citation Grounding  | 0.880    | 0.860  | -0.020 |
| Faithfulness        | 0.689    | 0.747  | +0.058 |
| Answer Relevancy    | 0.869    | 0.934  | +0.065 |
| Context Precision   | 0.208    | 0.278  | +0.070 |
| Composite Score     | 0.676    | 0.723  | +0.047 |

> Run date: 06 April 2026 · 100 RAGAS samples (50 baseline + 50 hybrid) · judge: Groq llama-3.3-70b-versatile · 0 NaN values
>
> Composite = 0.35×Faithfulness + 0.25×Answer Relevancy + 0.20×Context Precision + 0.20×Citation Grounding
>
> Latency Wilcoxon p ≈ 0 (Cohen's d = −0.34, small effect) · Context Precision Wilcoxon p = 0.073 (not significant at α = 0.05)
