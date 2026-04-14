"""Cross-verify all evaluation data files for internal consistency."""
import json, statistics, math

# Load all data
ragas = json.load(open("evaluation/results/ragas_scores.json"))
summary = json.load(open("evaluation/results/eval_summary.json"))
raw = json.load(open("evaluation/results/raw_results.json"))

f = ragas["faithfulness"]
r = ragas["answer_relevancy"]
p = ragas["context_precision"]

print(f"ragas_scores.json: {len(f)} faithfulness, {len(r)} relevancy, {len(p)} precision")
print(f"raw_results.json:  {len(raw)} entries")
print()

# Check raw_results structure
baseline_raw = [x for x in raw if x.get("mode") == "baseline"]
hybrid_raw = [x for x in raw if x.get("mode") == "hybrid"]
print(f"raw_results: {len(baseline_raw)} baseline, {len(hybrid_raw)} hybrid")
print()

# NaN check
nan_f = sum(1 for v in f if math.isnan(v))
nan_r = sum(1 for v in r if math.isnan(v))
nan_p = sum(1 for v in p if math.isnan(v))
print(f"NaN counts: faith={nan_f}, relev={nan_r}, prec={nan_p}")
print()

# Split strategies
print("=== Strategy 1: First 50 = Baseline, Last 50 = Hybrid ===")
print(f"  Baseline Faith: {statistics.mean(f[:50]):.4f}  Hybrid Faith: {statistics.mean(f[50:]):.4f}")
print(f"  Baseline Relev: {statistics.mean(r[:50]):.4f}  Hybrid Relev: {statistics.mean(r[50:]):.4f}")
print(f"  Baseline Prec:  {statistics.mean(p[:50]):.4f}  Hybrid Prec:  {statistics.mean(p[50:]):.4f}")
print()

print("=== Strategy 2: Even = Baseline, Odd = Hybrid ===")
print(f"  Baseline Faith: {statistics.mean(f[::2]):.4f}  Hybrid Faith: {statistics.mean(f[1::2]):.4f}")
print(f"  Baseline Relev: {statistics.mean(r[::2]):.4f}  Hybrid Relev: {statistics.mean(r[1::2]):.4f}")
print(f"  Baseline Prec:  {statistics.mean(p[::2]):.4f}  Hybrid Prec:  {statistics.mean(p[1::2]):.4f}")
print()

# Check raw_results for latency consistency
if baseline_raw and hybrid_raw:
    b_lat = [x["latency_s"] for x in baseline_raw]
    h_lat = [x["latency_s"] for x in hybrid_raw]
    print("=== Latency from raw_results.json ===")
    print(f"  Baseline mean: {statistics.mean(b_lat):.3f}  (summary says: {summary['baseline']['mean_latency_s']})")
    print(f"  Hybrid   mean: {statistics.mean(h_lat):.3f}  (summary says: {summary['hybrid']['mean_latency_s']})")
    print()

# What the tables claim
print("=== CLAIMED (comparison_table.md) ===")
print("  B faith=0.653  H faith=0.747  delta=+0.094")
print("  B relev=0.879  H relev=0.834  delta=-0.045")
print("  B prec =0.761  H prec =0.880  delta=+0.119")
print("  B comp =0.788  H comp =0.830  delta=+0.042")
print()

print("=== CLAIMED (comparison_table.csv) ===")
print("  B faith=0.6894 H faith=0.7471 delta=+0.0577")
print("  B relev=0.8692 H relev=0.9343 delta=+0.0652")
print("  B prec =0.2083 H prec =0.2780 delta=+0.0697")
print()

# Compute composites from raw data using Strategy 1
b_cit = summary["baseline"]["mean_citation_grounding"]
h_cit = summary["hybrid"]["mean_citation_grounding"]
b_comp = 0.35*statistics.mean(f[:50]) + 0.25*statistics.mean(r[:50]) + 0.20*statistics.mean(p[:50]) + 0.20*b_cit
h_comp = 0.35*statistics.mean(f[50:]) + 0.25*statistics.mean(r[50:]) + 0.20*statistics.mean(p[50:]) + 0.20*h_cit
print(f"=== Computed Composite (Strategy 1) ===")
print(f"  Baseline: {b_comp:.4f}  Hybrid: {h_comp:.4f}  Delta: {h_comp-b_comp:+.4f}")

b_comp2 = 0.35*statistics.mean(f[::2]) + 0.25*statistics.mean(r[::2]) + 0.20*statistics.mean(p[::2]) + 0.20*b_cit
h_comp2 = 0.35*statistics.mean(f[1::2]) + 0.25*statistics.mean(r[1::2]) + 0.20*statistics.mean(p[1::2]) + 0.20*h_cit
print(f"=== Computed Composite (Strategy 2) ===")
print(f"  Baseline: {b_comp2:.4f}  Hybrid: {h_comp2:.4f}  Delta: {h_comp2-b_comp2:+.4f}")
