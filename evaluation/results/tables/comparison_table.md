# Baseline vs Hybrid Comparison — 06 April 2026

| Metric              | Baseline | Hybrid | Delta  |
|---------------------|----------|--------|--------|
| Queries per mode    | 50       | 50     |        |
| Mean Latency (s)    | 1.189    | 2.138  | +0.949 |
| P95 Latency (s)     | 1.727    | 2.707  | +0.980 |
| Citation Grounding  | 0.940    | 0.920  | -0.020 |
| Faithfulness        | 0.653    | 0.747  | +0.094 |
| Answer Relevancy    | 0.879    | 0.834  | -0.045 |
| Context Precision   | 0.761    | 0.880  | +0.119 |
| Composite Score     | 0.788    | 0.830  | +0.042 |

> Run date: 06 April 2026 · 100 RAGAS samples (50 baseline + 50 hybrid) · judge: Groq llama-3.3-70b-versatile · 0 NaN values
>
> Composite = 0.35×Faithfulness + 0.25×Answer Relevancy + 0.20×Context Precision + 0.20×Citation Grounding
>
> Latency Wilcoxon p ≈ 0 (Cohen's d = −0.84, large effect) · Context Precision Wilcoxon p = 0.001
