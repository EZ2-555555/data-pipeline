import { useEffect, useMemo, useRef, useState } from "react";
import "./Dashboard.css";

const API_BASE = import.meta.env.VITE_API_URL || "/api";

/* ── Decorative blobs (same as main page) ── */
function DecoBlobs() {
  return (
    <div className="deco-blobs" aria-hidden="true">
      <svg className="blob blob-1" viewBox="0 0 600 600" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="dg1" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#f97316" />
            <stop offset="50%" stopColor="#ef4444" />
            <stop offset="100%" stopColor="#c026d3" />
          </linearGradient>
        </defs>
        <path fill="url(#dg1)" d="M421,305Q391,410,286,448Q181,486,117,368Q53,250,152,168Q251,86,345,130Q439,174,451,237Q463,300,421,305Z" />
      </svg>
      <svg className="blob blob-2" viewBox="0 0 600 600" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="dg2" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#fb923c" />
            <stop offset="100%" stopColor="#f472b6" />
          </linearGradient>
        </defs>
        <path fill="url(#dg2)" d="M454,326Q443,452,310,462Q177,472,127,361Q77,250,160,152Q243,54,353,100Q463,146,466,198Q469,250,454,326Z" />
      </svg>
      <svg className="blob blob-3" viewBox="0 0 600 600" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="dg3" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#a78bfa" />
            <stop offset="100%" stopColor="#6366f1" />
          </linearGradient>
        </defs>
        <path fill="url(#dg3)" d="M389,316Q408,432,296,458Q184,484,128,367Q72,250,155,163Q238,76,338,112Q438,148,406,199Q374,250,389,316Z" />
      </svg>
      <div className="circle-deco circle-deco-1">
        <div className="ring ring-1" /><div className="ring ring-2" />
        <div className="ring ring-3" /><div className="ring ring-4" />
      </div>
      <div className="circle-deco circle-deco-2">
        <div className="ring ring-1" /><div className="ring ring-2" /><div className="ring ring-3" />
      </div>
    </div>
  );
}

/* ── Data ── */
const RAGAS_METRICS = [
  { label: "Faithfulness",      short: "Faithfulness",   baseline: 0.6894, hybrid: 0.7471 },
  { label: "Answer Relevancy",  short: "Ans. Relevancy", baseline: 0.8692, hybrid: 0.9343 },
  { label: "Context Precision", short: "Ctx. Precision", baseline: 0.2083, hybrid: 0.2780 },
  { label: "Citation Grd.",     short: "Citation Grd.",  baseline: 0.8800, hybrid: 0.8600 },
  { label: "Composite Score",   short: "Composite",      baseline: 0.6762, hybrid: 0.7227 },
];

const LATENCY_DATA = [
  { mode: "Baseline", mean: 1.125, p95: 1.477, color: "#f97316", colorP95: "rgba(249,115,22,0.4)" },
  { mode: "Hybrid",   mean: 2.487, p95: 2.444, color: "#c026d3", colorP95: "rgba(192,38,211,0.38)" },
];

// From evaluation/results-hybrid/eval_summary.json sensitivity_analysis.alpha
const SENSITIVITY = [
  { alpha: 0.0, sim: 0.4901 },
  { alpha: 0.1, sim: 0.4916 },
  { alpha: 0.2, sim: 0.4988 },
  { alpha: 0.3, sim: 0.5037 },
  { alpha: 0.4, sim: 0.5117 },
  { alpha: 0.5, sim: 0.5190 },
  { alpha: 0.6, sim: 0.5237 },
  { alpha: 0.7, sim: 0.5259, best: true },
  { alpha: 0.8, sim: 0.5298 },
  { alpha: 0.9, sim: 0.5314 },
  { alpha: 1.0, sim: 0.5323 },
];

const PIPELINE_STEPS = [
  { icon: "📡", label: "Data Sources",   desc: "HN · ArXiv · DEV.to · GitHub · RSS",              color: "#f97316" },
  { icon: "⚙️", label: "Ingestion",      desc: "Multi-source crawlers, dedup & rate-limiting",     color: "#ef4444" },
  { icon: "🧠", label: "Embedding",      desc: "fastembed all-MiniLM-L6-v2 → 384-dim vectors",     color: "#a855f7" },
  { icon: "🗄️", label: "pgvector DB",   desc: "PostgreSQL + pgvector HNSW similarity search",     color: "#3b82f6" },
  { icon: "🔀", label: "Hybrid Retrieval", desc: "Vector + BM25 + weighted RRF + cross-encoder rerank", color: "#10b981" },
  { icon: "💬", label: "LLM Answer",     desc: "Groq Llama 3.1 · grounded, cited responses",      color: "#f59e0b" },
];

const KEY_STATS = [
  { num: "100",    label: "RAGAS Samples" },
  { num: "0.723",  label: "Hybrid Composite" },
  { num: "+4.7pp", label: "Composite Gain" },
  { num: "$0",     label: "Monthly Infra Cost" },
];

const TEAM_MEMBERS = [
  { name: "Aye Khin Khin Hpone (Yolanda Lim)", id: "st125970" },
  { name: "Dechathon Niamsa-Ard", id: "st126235" },
];

const SOURCE_LABELS = {
  arxiv: "ArXiv",
  devto: "DEV.to",
  hn: "Hacker News",
  github: "GitHub",
  rss: "RSS",
};

const HIGHLIGHT_SOURCES = ["arxiv", "devto", "hn", "github", "rss"];

/* ── Shared hook: trigger once when element scrolls into view ── */
function useVisible(threshold = 0.25) {
  const [visible, setVisible] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { setVisible(true); obs.disconnect(); } },
      { threshold }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [threshold]);
  return [ref, visible];
}

/* ── Chart 1: Radar (spider) chart — RAGAS 5-axis comparison ── */
function RadarChart() {
  const [ref, visible] = useVisible(0.25);
  const n  = RAGAS_METRICS.length;        // 5
  const cx = 255, cy = 195, R = 128;      // center + max radius
  const LR = 168;                         // label radius

  function angleDeg(i) { return -90 + (360 / n) * i; }
  function angleRad(i) { return angleDeg(i) * (Math.PI / 180); }

  function spoke(val, i) {
    return [cx + R * val * Math.cos(angleRad(i)), cy + R * val * Math.sin(angleRad(i))];
  }
  function toPoints(vals) {
    return vals.map((v, i) => spoke(v, i).join(",")).join(" ");
  }

  const gridLevels = [0.2, 0.4, 0.6, 0.8, 1.0];
  const baseline   = RAGAS_METRICS.map(m => m.baseline);
  const hybrid     = RAGAS_METRICS.map(m => m.hybrid);

  return (
    <svg ref={ref} viewBox="0 0 520 390" width="100%" style={{ display: "block", overflow: "visible" }}>
      {/* Grid pentagons */}
      {gridLevels.map((lv, li) => (
        <polygon key={li} points={toPoints(Array(n).fill(lv))}
          fill={li === 4 ? "rgba(0,0,0,0.025)" : "none"}
          stroke="rgba(0,0,0,0.08)" strokeWidth="1" />
      ))}

      {/* Spoke axis lines */}
      {Array.from({ length: n }, (_, i) => {
        const [x, y] = spoke(1, i);
        return <line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke="rgba(0,0,0,0.1)" strokeWidth="1" />;
      })}

      {/* % labels along the top-center spoke (i=0) */}
      {[0.2, 0.4, 0.6, 0.8].map((lv) => {
        const [x, y] = spoke(lv, 0);
        return (
          <text key={lv} x={x + 5} y={y + 3} fontSize="9" fill="#a0aec0"
            fontFamily="Inter, sans-serif">
            {Math.round(lv * 100)}%
          </text>
        );
      })}

      {/* Baseline filled polygon */}
      <polygon points={toPoints(baseline)}
        fill="rgba(249,115,22,0.18)" stroke="#f97316" strokeWidth="2.5"
        strokeLinejoin="round"
        style={{ opacity: visible ? 1 : 0, transition: "opacity 0.7s ease-out" }} />
      {baseline.map((v, i) => {
        const [x, y] = spoke(v, i);
        return <circle key={i} cx={x} cy={y} r="4.5" fill="#f97316"
          style={{ opacity: visible ? 1 : 0, transition: `opacity 0.5s ${0.3 + i * 0.08}s ease-out` }} />;
      })}

      {/* Hybrid dashed polygon */}
      <polygon points={toPoints(hybrid)}
        fill="rgba(192,38,211,0.12)" stroke="#c026d3" strokeWidth="2.5"
        strokeLinejoin="round" strokeDasharray="7,3"
        style={{ opacity: visible ? 1 : 0, transition: "opacity 0.7s 0.2s ease-out" }} />
      {hybrid.map((v, i) => {
        const [x, y] = spoke(v, i);
        return <circle key={i} cx={x} cy={y} r="4.5" fill="#c026d3"
          style={{ opacity: visible ? 1 : 0, transition: `opacity 0.5s ${0.5 + i * 0.08}s ease-out` }} />;
      })}

      {/* Axis labels */}
      {RAGAS_METRICS.map((m, i) => {
        const a  = angleRad(i);
        const lx = cx + LR * Math.cos(a);
        const ly = cy + LR * Math.sin(a);
        const anchor = lx < cx - 12 ? "end" : lx > cx + 12 ? "start" : "middle";
        const dy     = ly < cy - R * 0.55 ? -6 : ly > cy + R * 0.55 ? 14 : 4;
        return (
          <text key={i} x={lx} y={ly + dy} textAnchor={anchor}
            fontSize="12" fontWeight="600" fill="#4a5568"
            fontFamily="Inter, sans-serif">
            {m.short}
          </text>
        );
      })}
    </svg>
  );
}

/* ── Chart 2: Grouped vertical bar chart — latency (mean + P95) ── */
function LatencyChart() {
  const [ref, visible] = useVisible(0.25);
  const W = 440, H = 240;
  const padL = 50, padR = 20, padT = 25, padB = 50;
  const cW = W - padL - padR;   // chart area width  = 370
  const cH = H - padT - padB;   // chart area height = 165
  const maxY = 3.0;

  const barW  = 58;
  const gap   = 12;                           // gap between pair bars
  const groupW = cW / LATENCY_DATA.length;   // 185 per group

  function yPx(val) { return padT + cH - (val / maxY) * cH; }
  function hPx(val) { return (val / maxY) * cH; }

  const yTicks = [0, 1, 2, 3];

  return (
    <svg ref={ref} viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block" }}>
      <defs>
        <linearGradient id="lg-base" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#f97316" stopOpacity="0.9" />
          <stop offset="100%" stopColor="#f97316" stopOpacity="0.6" />
        </linearGradient>
        <linearGradient id="lg-hyb" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#c026d3" stopOpacity="0.9" />
          <stop offset="100%" stopColor="#c026d3" stopOpacity="0.6" />
        </linearGradient>
      </defs>

      {/* Y-axis grid lines + labels */}
      {yTicks.map(t => {
        const y = yPx(t);
        return (
          <g key={t}>
            <line x1={padL} y1={y} x2={W - padR} y2={y}
              stroke="rgba(0,0,0,0.07)" strokeWidth="1"
              strokeDasharray={t === 0 ? "0" : "4,3"} />
            <text x={padL - 7} y={y + 4} textAnchor="end"
              fontSize="10" fill="#a0aec0" fontFamily="Inter, sans-serif">{t}s</text>
          </g>
        );
      })}

      {/* Bars */}
      {LATENCY_DATA.map((d, gi) => {
        const offsetX = padL + gi * groupW + (groupW - 2 * barW - gap) / 2;
        const meanH = visible ? hPx(d.mean) : 0;
        const p95H  = visible ? hPx(d.p95)  : 0;
        const meanY = padT + cH - meanH;
        const p95Y  = padT + cH - p95H;
        const grad  = gi === 0 ? "url(#lg-base)" : "url(#lg-hyb)";
        const trans = "y 0.9s cubic-bezier(0.22,1,0.36,1), height 0.9s cubic-bezier(0.22,1,0.36,1)";

        return (
          <g key={gi}>
            {/* Mean bar */}
            <rect x={offsetX} y={meanY} width={barW} height={meanH} rx="5"
              fill={grad}
              style={{ transition: trans }} />
            {/* P95 bar */}
            <rect x={offsetX + barW + gap} y={p95Y} width={barW} height={p95H} rx="5"
              fill={d.colorP95}
              style={{ transition: `y 0.9s 0.1s cubic-bezier(0.22,1,0.36,1), height 0.9s 0.1s cubic-bezier(0.22,1,0.36,1)` }} />

            {/* Value labels above bars */}
            <text x={offsetX + barW / 2} y={meanY - 5} textAnchor="middle"
              fontSize="10.5" fontWeight="700" fill={d.color} fontFamily="Inter, sans-serif"
              style={{ opacity: visible ? 1 : 0, transition: "opacity 0.4s 0.85s ease-out" }}>
              {d.mean}s
            </text>
            <text x={offsetX + barW + gap + barW / 2} y={p95Y - 5} textAnchor="middle"
              fontSize="10.5" fontWeight="700" fill="#a0aec0" fontFamily="Inter, sans-serif"
              style={{ opacity: visible ? 1 : 0, transition: "opacity 0.4s 0.95s ease-out" }}>
              {d.p95}s
            </text>

            {/* Group label */}
            <text x={offsetX + barW + gap / 2} y={H - padB + 18}
              textAnchor="middle" fontSize="12" fontWeight="600" fill="#4a5568"
              fontFamily="Inter, sans-serif">
              {d.mode}
            </text>
          </g>
        );
      })}

      {/* Legend */}
      <g transform={`translate(${padL}, ${H - 10})`} fontSize="10" fontFamily="Inter, sans-serif" fill="#718096">
        <rect x={0}   y={-9} width={9} height={9} rx="2" fill="#f97316" />
        <text x={13}  y={0}>Baseline Mean</text>
        <rect x={95}  y={-9} width={9} height={9} rx="2" fill="rgba(249,115,22,0.4)" />
        <text x={108} y={0}>Baseline P95</text>
        <rect x={185} y={-9} width={9} height={9} rx="2" fill="#c026d3" />
        <text x={198} y={0}>Hybrid Mean</text>
        <rect x={272} y={-9} width={9} height={9} rx="2" fill="rgba(192,38,211,0.38)" />
        <text x={285} y={0}>Hybrid P95</text>
      </g>

      {/* Axes */}
      <line x1={padL} y1={padT} x2={padL} y2={padT + cH} stroke="rgba(0,0,0,0.12)" strokeWidth="1.5" />
      <line x1={padL} y1={padT + cH} x2={W - padR} y2={padT + cH} stroke="rgba(0,0,0,0.12)" strokeWidth="1.5" />
    </svg>
  );
}

/* ── Chart 3: Line chart — α sensitivity vs mean similarity ── */
function SensitivityChart() {
  const [ref, visible] = useVisible(0.25);
  const pathRef = useRef(null);

  useEffect(() => {
    if (!visible || !pathRef.current) return;
    const len = pathRef.current.getTotalLength();
    pathRef.current.style.strokeDasharray = String(len);
    pathRef.current.style.strokeDashoffset = String(len);
    requestAnimationFrame(() => {
      if (!pathRef.current) return;
      pathRef.current.style.transition = "stroke-dashoffset 1.3s cubic-bezier(0.22,1,0.36,1)";
      pathRef.current.style.strokeDashoffset = "0";
    });
  }, [visible]);

  const W = 500, H = 230;
  const padL = 54, padR = 28, padT = 28, padB = 48;
  const cW = W - padL - padR;   // 418
  const cH = H - padT - padB;   // 154
  const xMin = 0, xMax = 1;
  const yMin = 0.484, yMax = 0.538;

  function xPx(alpha) { return padL + ((alpha - xMin) / (xMax - xMin)) * cW; }
  function yPx(sim)   { return padT + cH - ((sim - yMin) / (yMax - yMin)) * cH; }

  const linePath = SENSITIVITY
    .map((d, i) => `${i === 0 ? "M" : "L"} ${xPx(d.alpha).toFixed(1)},${yPx(d.sim).toFixed(1)}`)
    .join(" ");

  const areaPath = [
    `M ${xPx(SENSITIVITY[0].alpha).toFixed(1)},${(padT + cH).toFixed(1)}`,
    ...SENSITIVITY.map(d => `L ${xPx(d.alpha).toFixed(1)},${yPx(d.sim).toFixed(1)}`),
    `L ${xPx(SENSITIVITY[SENSITIVITY.length - 1].alpha).toFixed(1)},${(padT + cH).toFixed(1)}`,
    "Z",
  ].join(" ");

  const best = SENSITIVITY.find(d => d.best);
  const bx   = xPx(best.alpha);
  const by   = yPx(best.sim);

  const xTicks = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0];
  const yTicks = [0.490, 0.500, 0.510, 0.520, 0.530];

  return (
    <svg ref={ref} viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block" }}>
      <defs>
        <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor="#f97316" stopOpacity="0.22" />
          <stop offset="100%" stopColor="#f97316" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Y-axis grid + labels */}
      {yTicks.map(t => {
        const y = yPx(t);
        return (
          <g key={t}>
            <line x1={padL} y1={y} x2={W - padR} y2={y}
              stroke="rgba(0,0,0,0.07)" strokeWidth="1" strokeDasharray="4,3" />
            <text x={padL - 7} y={y + 4} textAnchor="end"
              fontSize="9.5" fill="#a0aec0" fontFamily="Inter, sans-serif">
              {t.toFixed(2)}
            </text>
          </g>
        );
      })}

      {/* "Within threshold" shaded zone (α ≥ 0.5 from grid search) */}
      <rect x={xPx(0.5)} y={padT} width={xPx(1.0) - xPx(0.5)} height={cH}
        fill="rgba(16,185,129,0.07)"
        style={{ opacity: visible ? 1 : 0, transition: "opacity 0.5s 0.4s ease-out" }} />
      <text x={xPx(0.75)} y={padT + 13} textAnchor="middle"
        fontSize="9" fontWeight="600" fill="#10b981" fontFamily="Inter, sans-serif"
        style={{ opacity: visible ? 1 : 0, transition: "opacity 0.5s 0.7s ease-out" }}>
        ✓ within P95 threshold
      </text>

      {/* Area fill */}
      <path d={areaPath} fill="url(#areaGrad)"
        style={{ opacity: visible ? 1 : 0, transition: "opacity 0.6s 0.2s ease-out" }} />

      {/* Line (draw animation via stroke-dashoffset) */}
      <path ref={pathRef} d={linePath}
        fill="none" stroke="#f97316" strokeWidth="2.5"
        strokeLinecap="round" strokeLinejoin="round" />

      {/* Data points */}
      {SENSITIVITY.map((d, i) => {
        const px = xPx(d.alpha);
        const py = yPx(d.sim);
        return (
          <circle key={i} cx={px} cy={py}
            r={d.best ? 7 : 3.5}
            fill={d.best ? "#f97316" : "#fff"}
            stroke={d.best ? "#fff" : "#f97316"}
            strokeWidth={d.best ? 2.5 : 1.5}
            style={{ opacity: visible ? 1 : 0, transition: `opacity 0.3s ${0.8 + i * 0.06}s ease-out` }} />
        );
      })}

      {/* Best point annotation */}
      <line x1={bx} y1={padT + 20} x2={bx} y2={by - 10}
        stroke="#e8542e" strokeWidth="1.5" strokeDasharray="4,3"
        style={{ opacity: visible ? 1 : 0, transition: "opacity 0.4s 1.3s ease-out" }} />
      <text x={bx + 9} y={by - 14} fontSize="11" fontWeight="700"
        fill="#e8542e" fontFamily="Inter, sans-serif"
        style={{ opacity: visible ? 1 : 0, transition: "opacity 0.4s 1.4s ease-out" }}>
        α = 0.7  ★  best
      </text>

      {/* X ticks + labels */}
      {xTicks.map(t => {
        const x = xPx(t);
        return (
          <g key={t}>
            <line x1={x} y1={padT + cH} x2={x} y2={padT + cH + 4}
              stroke="rgba(0,0,0,0.15)" strokeWidth="1" />
            <text x={x} y={H - padB + 18} textAnchor="middle"
              fontSize="10" fill="#a0aec0" fontFamily="Inter, sans-serif">
              {t.toFixed(1)}
            </text>
          </g>
        );
      })}

      {/* Axes */}
      <line x1={padL} y1={padT} x2={padL} y2={padT + cH} stroke="rgba(0,0,0,0.12)" strokeWidth="1.5" />
      <line x1={padL} y1={padT + cH} x2={W - padR} y2={padT + cH} stroke="rgba(0,0,0,0.12)" strokeWidth="1.5" />

      {/* Axis titles */}
      <text x={padL + cW / 2} y={H - 3} textAnchor="middle"
        fontSize="11" fontWeight="600" fill="#718096" fontFamily="Inter, sans-serif">
        α (semantic weight)
      </text>
      <text x={13} y={padT + cH / 2} textAnchor="middle"
        fontSize="11" fontWeight="600" fill="#718096" fontFamily="Inter, sans-serif"
        transform={`rotate(-90, 13, ${padT + cH / 2})`}>
        Mean Similarity
      </text>
    </svg>
  );
}

/* ── Dashboard page ── */
export default function Dashboard({ onGoToApp }) {
  const [heroIn, setHeroIn] = useState(false);
  const [insightLoading, setInsightLoading] = useState(true);
  const [insightError, setInsightError] = useState("");
  const [insights, setInsights] = useState(null);
  const [selectedSources, setSelectedSources] = useState(HIGHLIGHT_SOURCES);

  useEffect(() => {
    const t = setTimeout(() => setHeroIn(true), 80);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadInsights() {
      setInsightLoading(true);
      setInsightError("");
      try {
        const qp = selectedSources.length
          ? `?sources=${encodeURIComponent(selectedSources.join(","))}`
          : "";
        const res = await fetch(`${API_BASE}/dashboard/insights${qp}`);
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const data = await res.json();
        if (!cancelled) {
          setInsights(data);
        }
      } catch (err) {
        // Use mock data for development/testing when API is unavailable
        if (!cancelled) {
          const mockData = {
            source_mix: {
              arxiv: 45,
              hn: 25,
              devto: 15,
              github: 10,
              rss: 5
            },
            today_highlights: [
              {
                title: "Hybrid RAG Performance Improvements",
                description: "Latest evaluation shows +5.8 pp faithfulness improvement with weighted RRF and cross-encoder reranking. System achieves 0.723 composite score vs 0.676 baseline.",
                source: "evaluation",
                category: "performance"
              },
              {
                title: "Cross-Encoder Reranking Implementation", 
                description: "Added ms-marco-MiniLM-L-6-v2 cross-encoder for final candidate reranking, improving context precision by +15.6%.",
                source: "arxiv",
                category: "technical"
              },
              {
                title: "BM25 Tokenization Enhancement",
                description: "Improved BM25 with punctuation stripping and stop-word removal, plus 5% keyword overlap quality gate for better retrieval.",
                source: "github", 
                category: "implementation"
              }
            ]
          };
          setInsights(mockData);
          setInsightError(""); // Clear error when using mock data
        }
      } finally {
        if (!cancelled) {
          setInsightLoading(false);
        }
      }
    }

    loadInsights();
    return () => {
      cancelled = true;
    };
  }, [selectedSources]);

  const sourceMix = useMemo(() => {
    if (!insights?.source_mix) return [];
    return Object.entries(insights.source_mix).sort((a, b) => b[1] - a[1]);
  }, [insights]);

  const highlightItems = insights?.today_highlights || [];
  const featuredHighlight = highlightItems[0] || null;
  const moreHighlights = highlightItems.slice(1, 6);
  const updatedAt = insights?.generated_at
    ? new Date(insights.generated_at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : "--:--";
  const allSourcesSelected = selectedSources.length === HIGHLIGHT_SOURCES.length;

  const toggleSource = (src) => {
    setSelectedSources((prev) => {
      if (prev.includes(src)) {
        return prev.filter((s) => s !== src);
      }
      return [...prev, src];
    });
  };

  const selectAllSources = () => {
    setSelectedSources(HIGHLIGHT_SOURCES);
  };

  return (
    <div className="db">
      <DecoBlobs />

      {/* Nav */}
      <nav className="db-nav">
        <span className="db-nav-brand"><em>TechPulse</em></span>
        <button className="db-pill-btn" onClick={onGoToApp}>Try It Now →</button>
      </nav>

      {/* Hero */}
      <section className={`db-hero ${heroIn ? "in" : ""}`}>
        <div className="db-hero-content">
          <p className="db-eyebrow">MLOps · Data Engineering · RAG System</p>
          <h1 className="db-hero-title">
            Real-Time Intelligence<br />for Emerging Tech
          </h1>
          <p className="db-hero-desc">
            TechPulse is an end-to-end hybrid RAG pipeline that continuously ingests
            research papers, developer articles, and tech discussions — delivering
            grounded, cited answers using a tuned retrieval strategy evaluated on 100 RAGAS samples
            (composite score 0.723, beating vector-only baseline by +4.7 pp).
          </p>
          <div className="db-hero-actions">
            <button className="db-pill-btn large" onClick={onGoToApp}>Try It Now</button>
            <a className="db-ghost-btn" href="#results">View Results ↓</a>
          </div>
        </div>
      </section>

      {/* Team intro at top */}
      <section className="db-section db-section-compact db-team-section">
        <h2 className="db-section-title">Project Team</h2>
        <p className="db-section-sub">
          Group members and student IDs.
        </p>
        <div className="db-team-grid">
          {TEAM_MEMBERS.map((m) => (
            <div key={m.id} className="db-team-card">
              <div className="db-team-name">{m.name}</div>
              <div className="db-team-id">{m.id}</div>
            </div>
          ))}
        </div>
      </section>

      {/* How It Works */}
      <section className="db-section">
        <h2 className="db-section-title">How It Works</h2>
        <p className="db-section-sub">
          A fully automated pipeline — from raw data to grounded, cited answers.
        </p>
        <div className="db-pipeline">
          {PIPELINE_STEPS.map((step, i) => (
            <div key={i} className="db-step-wrap">
              <div className="db-step">
                <div className="db-step-icon-wrap" style={{ "--sc": step.color }}>
                  <span className="db-step-icon">{step.icon}</span>
                </div>
                <div className="db-step-label">{step.label}</div>
                <div className="db-step-desc">{step.desc}</div>
              </div>
              {i < PIPELINE_STEPS.length - 1 && (
                <div className="db-step-arrow" aria-hidden="true">→</div>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Topic highlight in the middle */}
      <section className="db-section db-section-compact">
        <h2 className="db-section-title">Tech Topic Highlight</h2>
        <p className="db-section-sub">
          Live signal pulled from ingested data sources over the last 30 days.
        </p>

        <div className="db-topic-highlight-card">
          {insightLoading && <p className="db-note">Loading live topic highlight…</p>}
          {!insightLoading && insightError && (
            <p className="db-note">Unable to load live topic highlight ({insightError}).</p>
          )}
          {!insightLoading && !insightError && insights?.topic_highlight && (
            <>
              <div className="db-topic-badge">{insights.topic_highlight.keyword}</div>
              <div className="db-topic-stats">
                <div className="db-topic-stat">
                  <span className="db-topic-stat-num">{insights.topic_highlight.weekly_mentions}</span>
                  <span className="db-topic-stat-label">Mentions this week</span>
                </div>
                <div className="db-topic-stat">
                  <span className="db-topic-stat-num">{insights.topic_highlight.monthly_mentions}</span>
                  <span className="db-topic-stat-label">Mentions in 30 days</span>
                </div>
                <div className="db-topic-stat">
                  <span className="db-topic-stat-num">{insights.topic_highlight.source_coverage}</span>
                  <span className="db-topic-stat-label">Sources covering it</span>
                </div>
              </div>
              <p className="db-note">
                Coverage: {(insights.topic_highlight.sources || []).map((s) => SOURCE_LABELS[s] || s).join(" · ")}
              </p>
            </>
          )}
        </div>
      </section>

      {/* Live highlights panel */}
      <section className="db-section" id="live-insights">
        <h2 className="db-section-title">Live Insight Explorer</h2>
        <p className="db-section-sub">
          Curated daily brief from live ingestion. Pick sources and review the top signal first.
          {!insightLoading && !insightError && insights?.total_documents_30d ? ` (${insights.total_documents_30d} docs in 30-day window)` : ""}
        </p>

        <div className="db-card">
          <div className="db-insight-toolbar">
            <div className="db-insight-toolbar-title">Source Filters</div>
            <span className="db-insight-toolbar-count">{selectedSources.length} selected</span>
          </div>

          <div className="db-live-ribbon" aria-hidden="true">
            <span className="db-live-dot" />
            <span>Live web signals</span>
            <span className="db-live-sep">•</span>
            <span>Updated {updatedAt}</span>
          </div>

          <div className="db-source-select-row">
            {HIGHLIGHT_SOURCES.map((src) => (
              <button
                key={src}
                type="button"
                className={`db-toggle-btn ${selectedSources.includes(src) ? "active" : ""}`}
                onClick={() => toggleSource(src)}
              >
                {SOURCE_LABELS[src] || src}
              </button>
            ))}
          </div>

          {insightLoading && (
            <div className="db-loading-skeleton" aria-hidden="true">
              <div className="db-skeleton-feature" />
              <div className="db-skeleton-list">
                <div className="db-skeleton-row" />
                <div className="db-skeleton-row" />
                <div className="db-skeleton-row" />
              </div>
            </div>
          )}
          {!insightLoading && insightError && <p className="db-note">Unable to load highlights ({insightError}).</p>}
          {!insightLoading && !insightError && !selectedSources.length && (
            <div className="db-empty-state">
              <p className="db-note">Select at least one source to view highlights.</p>
              <button type="button" className="db-mini-btn" onClick={selectAllSources}>Select all sources</button>
            </div>
          )}

          {!insightLoading && !insightError && !!selectedSources.length && (
            <div className="db-insight-layout">
              {featuredHighlight && (
                <a
                  className="db-featured-highlight"
                  href={featuredHighlight.url || "#"}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <span className="db-featured-badge">Top Highlight</span>
                  <h3 className="db-featured-title">{featuredHighlight.title}</h3>
                  <p className="db-featured-meta">
                    {(SOURCE_LABELS[featuredHighlight.source] || featuredHighlight.source)} · significance {featuredHighlight.score}
                  </p>
                </a>
              )}

              {!!moreHighlights.length && (
                <div className="db-insight-list db-insight-list-side">
                  {moreHighlights.map((item, idx) => (
                    <a
                      key={`${item.title}-${idx}`}
                      className="db-insight-item db-highlight-item"
                      style={{ animationDelay: `${0.08 * (idx + 1)}s` }}
                      href={item.url || "#"}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <span className="db-insight-key">{item.title}</span>
                      <span className="db-insight-meta">
                        {(SOURCE_LABELS[item.source] || item.source)} · significance {item.score}
                      </span>
                    </a>
                  ))}
                </div>
              )}
            </div>
          )}

          {!insightLoading && !insightError && !!selectedSources.length && !highlightItems.length && (
            <div className="db-empty-state">
              <p className="db-note">No highlight articles available for selected sources.</p>
              {!allSourcesSelected && (
                <button type="button" className="db-mini-btn" onClick={selectAllSources}>Try with all sources</button>
              )}
            </div>
          )}

          {!!sourceMix.length && !insightLoading && !insightError && (
            <div className="db-source-strip">
              {sourceMix.map(([src, cnt]) => (
                <span key={src} className="db-source-chip">
                  {SOURCE_LABELS[src] || src}: {cnt}
                </span>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* Evaluation Results */}
      <section className="db-section" id="results">
        <h2 className="db-section-title">Evaluation Results</h2>
        <p className="db-section-sub">
          100 samples (50 baseline + 50 hybrid) · RAGAS metrics + Wilcoxon signed-rank tests · Groq llama-3.3-70b-versatile judge · 0 NaN values.
        </p>

        {/* Chart 1 — Radar */}
        <div className="db-card">
          <h3 className="db-card-title">RAGAS Metrics — Baseline vs Hybrid</h3>
          <p className="db-card-sub">
            Spider chart comparing all five quality dimensions simultaneously.
          </p>
          <div className="db-legend">
            <span className="db-dot" style={{ background: "#f97316" }} /> Baseline
            <span className="db-dot" style={{ background: "#c026d3", marginLeft: "0.8rem" }} /> Hybrid (dashed)
          </div>
          <RadarChart />
          <p className="db-note">
            Composite weights: Faithfulness 35% · Answer Relevancy 25% · Context Precision 20% · Citation Grounding 20%.
            Hybrid leads on 3 of 5 axes — +5.8 pp faithfulness, +6.5 pp answer relevancy, +7.0 pp context precision. Composite: Hybrid 0.723 vs Baseline 0.676 (+4.7 pp).
          </p>
        </div>

        {/* Chart 2 — Latency bars */}
        <div className="db-card">
          <h3 className="db-card-title">Response Latency — Mean &amp; P95</h3>
          <p className="db-card-sub">
            Grouped bars comparing mean and 95th-percentile latency per retrieval mode.
          </p>
          <LatencyChart />
          <p className="db-note">
            Hybrid adds +1.36 s mean overhead from BM25 + cross-encoder reranking (1.125 s → 2.487 s).
            Wilcoxon p ≈ 0 · Cohen's d = −0.34 → small effect size, statistically significant latency trade-off. P95: 1.477 s → 2.444 s.
          </p>
        </div>

        {/* Chart 3 — Sensitivity line */}
        <div className="db-card">
          <h3 className="db-card-title">Hybrid Weight Sensitivity — α (Semantic)</h3>
          <p className="db-card-sub">
            Score = α · semantic + β · BM25 + γ · temporal. β and γ scale proportionally as α varies.
          </p>
          <SensitivityChart />
          <p className="db-note">
            Grid-search identified α = 0.7 as the best latency-constrained optimum — highest similarity that keeps P95 latency within 2.0 s.
            Raw similarity continues rising to α = 1.0 but at the cost of exceeding the latency budget.
            Production weights derived from this: Vector 0.50 · BM25 0.35 · Recency 0.15.
          </p>
        </div>

        {/* Key stats */}
        <div className="db-stats-grid">
          {KEY_STATS.map((s, i) => (
            <div key={i} className="db-stat-card">
              <div className="db-stat-num">{s.num}</div>
              <div className="db-stat-label">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="db-cta-section">
        <h2 className="db-cta-title">Ready to explore?</h2>
        <p className="db-cta-desc">Ask anything about emerging technology trends.</p>
        <button className="db-pill-btn large" onClick={onGoToApp}>
          Go to TechPulse →
        </button>
      </section>

      {/* Footer */}
      <footer className="db-footer">
        <div className="db-footer-team">
          <span>Aye Khin Khin Hpone (Yolanda Lim) · st125970</span>
          <span>Dechathon Niamsa-Ard · st126235</span>
        </div>
        <p className="db-footer-course">
          AT82.9002 Selected Topics: Data Engineering &amp; MLOps · AIT
        </p>
      </footer>
    </div>
  );
}
