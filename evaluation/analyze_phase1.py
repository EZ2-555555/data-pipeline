"""Quick analysis of Phase 1 raw results."""
import json, statistics

with open("evaluation/results/raw_results.json") as f:
    raw = json.load(f)

print("=" * 70)
print("  PHASE 1 RESULTS ANALYSIS — Baseline vs Hybrid")
print("=" * 70)

for mode in ("baseline", "hybrid"):
    entries = raw[mode]
    lats = [e["latency_s"] for e in entries]
    cites = [e["citation_grounding"] for e in entries]
    s = sorted(lats)
    p95 = s[min(int(len(s) * 0.95), len(s) - 1)]
    print(f"\n--- {mode.upper()} ({len(entries)} queries) ---")
    print(f"  Latency:  mean={statistics.mean(lats):.3f}s  median={statistics.median(lats):.3f}s  p95={p95:.3f}s  max={max(lats):.3f}s")
    print(f"  Citation: mean={statistics.mean(cites):.3f}")
    cats = {}
    for e in entries:
        cats.setdefault(e["category"], []).append(e)
    for cat in sorted(cats):
        cl = [e["latency_s"] for e in cats[cat]]
        cc = [e["citation_grounding"] for e in cats[cat]]
        print(f"    {cat}: lat={statistics.mean(cl):.3f}s  cite={statistics.mean(cc):.3f}  n={len(cats[cat])}")

b_lats = [e["latency_s"] for e in raw["baseline"]]
h_lats = [e["latency_s"] for e in raw["hybrid"]]
b_cites = [e["citation_grounding"] for e in raw["baseline"]]
h_cites = [e["citation_grounding"] for e in raw["hybrid"]]

lat_delta = statistics.mean(h_lats) - statistics.mean(b_lats)
cite_delta = statistics.mean(h_cites) - statistics.mean(b_cites)

print(f"\n--- DELTAS (hybrid - baseline) ---")
print(f"  Latency:  {lat_delta:+.3f}s")
print(f"  Citation: {cite_delta:+.3f}")

print(f"\n--- PER-QUERY COMPARISON ---")
for b, h in zip(raw["baseline"], raw["hybrid"]):
    q = b["query"][:55]
    d = h["latency_s"] - b["latency_s"]
    cd = h["citation_grounding"] - b["citation_grounding"]
    print(f"  {q:<55} lat:{d:+.3f}s  cite:{cd:+.3f}")

hf = sum(1 for b, h in zip(raw["baseline"], raw["hybrid"]) if h["latency_s"] < b["latency_s"])
hc = sum(1 for b, h in zip(raw["baseline"], raw["hybrid"]) if h["citation_grounding"] > b["citation_grounding"])
he = sum(1 for b, h in zip(raw["baseline"], raw["hybrid"]) if h["citation_grounding"] == b["citation_grounding"])
n = len(raw["baseline"])

lat_verdict = "hybrid slower" if lat_delta > 0 else "hybrid faster"
cite_verdict = "hybrid better" if cite_delta > 0 else ("baseline better" if cite_delta < 0 else "tied")

print(f"\n--- VERDICT ---")
print(f"  Hybrid faster:       {hf}/{n} queries")
print(f"  Hybrid better cite:  {hc}/{n} queries")
print(f"  Citation tied:       {he}/{n} queries")
print(f"  Mean latency delta:  {lat_delta:+.3f}s  ({lat_verdict})")
print(f"  Mean citation delta: {cite_delta:+.3f}  ({cite_verdict})")
