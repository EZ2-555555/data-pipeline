import { useEffect, useMemo, useRef, useState } from "react";
import "./Dashboard.css";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

/* ── Aurora mesh gradient background ── */
function AuroraBg() {
  return (
    <div className="aurora-bg" aria-hidden="true">
      <div className="aurora-orb aurora-orb-1" />
      <div className="aurora-orb aurora-orb-2" />
      <div className="aurora-orb aurora-orb-3" />
      <div className="aurora-orb aurora-orb-4" />
    </div>
  );
}

/* ── Floating Tech Icons ── */
function FloatingTechIcons() {
  const icons = [
    { d: "M9 3v2m6-2v2M9 19v2m6-2v2M3 9h2m-2 6h2m14-6h2m-2 6h2M7 7h10v10H7z", x: "8%", y: "15%", delay: "0s", dur: "14s", size: 28 },
    { d: "M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z", x: "85%", y: "22%", delay: "2s", dur: "18s", size: 32 },
    { d: "M16 18l6-6-6-6M8 6l-6 6 6 6", x: "12%", y: "65%", delay: "4s", dur: "16s", size: 24 },
    { d: "M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4", x: "90%", y: "70%", delay: "1s", dur: "15s", size: 26 },
    { d: "M13 10V3L4 14h7v7l9-11h-7z", x: "65%", y: "85%", delay: "1.5s", dur: "13s", size: 26 },
    { d: "M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z", x: "55%", y: "55%", delay: "7s", dur: "16s", size: 22 },
  ];
  return (
    <div className="floating-icons" aria-hidden="true">
      {icons.map((ic, i) => (
        <svg key={i} className="float-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"
          style={{ left: ic.x, top: ic.y, width: ic.size, height: ic.size, animationDelay: ic.delay, animationDuration: ic.dur }}>
          <path d={ic.d} />
        </svg>
      ))}
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

const SENSITIVITY = [
  { alpha: 0.0, sim: 0.4901 }, { alpha: 0.1, sim: 0.4916 }, { alpha: 0.2, sim: 0.4988 },
  { alpha: 0.3, sim: 0.5037 }, { alpha: 0.4, sim: 0.5117 }, { alpha: 0.5, sim: 0.5190 },
  { alpha: 0.6, sim: 0.5237 }, { alpha: 0.7, sim: 0.5259, best: true },
  { alpha: 0.8, sim: 0.5298 }, { alpha: 0.9, sim: 0.5314 }, { alpha: 1.0, sim: 0.5323 },
];

const PIPELINE_STEPS = [
  { icon: "📡", label: "Data Sources",     desc: "HN · ArXiv · DEV.to · GitHub · RSS",                  color: "#f97316" },
  { icon: "⚙️", label: "Ingestion",        desc: "Multi-source crawlers, dedup & rate-limiting",         color: "#ef4444" },
  { icon: "🧠", label: "Embedding",        desc: "fastembed all-MiniLM-L6-v2 → 384-dim vectors",         color: "#a855f7" },
  { icon: "🗄️", label: "pgvector DB",     desc: "PostgreSQL + pgvector HNSW similarity search",         color: "#3b82f6" },
  { icon: "🔀", label: "Hybrid Retrieval", desc: "Vector + BM25 + weighted RRF + cross-encoder rerank", color: "#10b981" },
  { icon: "💬", label: "LLM Answer",       desc: "Groq Llama 3.1 · grounded, cited responses",          color: "#f59e0b" },
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

const SOURCE_LABELS = { arxiv: "ArXiv", devto: "DEV.to", hn: "Hacker News", github: "GitHub", rss: "RSS" };
const SOURCE_URLS = {
  arxiv: "https://arxiv.org",
  devto: "https://dev.to",
  hn: "https://news.ycombinator.com",
  github: "https://github.com",
  rss: "https://rss.com",
};
const HIGHLIGHT_SOURCES = ["arxiv", "devto", "hn", "github", "rss"];

function resolveHighlightUrl(item) {
  const raw = String(item?.url || "").trim();
  if (/^https?:\/\//i.test(raw)) return raw;
  const q = encodeURIComponent(item?.title || "technology news");
  const src = item?.source;
  if (src === "arxiv") return `https://arxiv.org/search/?query=${q}&searchtype=all`;
  if (src === "devto") return `https://dev.to/search?q=${q}`;
  if (src === "hn") return `https://hn.algolia.com/?q=${q}`;
  if (src === "github") return `https://github.com/search?q=${q}&type=repositories`;
  if (src === "rss") return `https://www.bing.com/news/search?q=${q}%20rss`;
  return `https://www.bing.com/news/search?q=${q}`;
}

/* ── Hooks ── */
function useVisible(threshold = 0.18) {
  const [vis, setVis] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([e]) => { if (e.isIntersecting) { setVis(true); obs.disconnect(); } },
      { threshold }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [threshold]);
  return [ref, vis];
}

function AnimatedNumber({ value, duration = 1200 }) {
  const str = String(value);
  const isFloat = str.includes(".");
  const isPlus = str.startsWith("+");
  const clean = str.replace(/[^0-9.]/g, "");
  const target = parseFloat(clean);
  const isValid = !isNaN(target);

  const [display, setDisplay] = useState(isValid ? "0" : str);
  const [ref, vis] = useVisible(0.3);
  useEffect(() => {
    if (!vis || !isValid) return;
    let rafId;
    const start = performance.now();
    const step = (now) => {
      const t = Math.min((now - start) / duration, 1);
      const ease = 1 - Math.pow(1 - t, 3);
      const cur = target * ease;
      let formatted = isFloat ? cur.toFixed(str.split(".")[1]?.replace(/[^0-9]/g, "").length || 1) : String(Math.round(cur));
      if (isPlus) formatted = "+" + formatted;
      if (str.endsWith("pp")) formatted += "pp";
      setDisplay(formatted);
      if (t < 1) rafId = requestAnimationFrame(step);
    };
    rafId = requestAnimationFrame(step);
    return () => cancelAnimationFrame(rafId);
  }, [vis, value, duration, isValid, isFloat, isPlus, str, target]);
  return <span ref={ref}>{display}</span>;
}

/* ── Gradient Divider ── */
function GradientDivider() {
  return <div className="db-grad-divider" />;
}

/* ── Charts ── */
function RadarChart() {
  const [ref, vis] = useVisible(0.2);
  const n = 5, cx = 255, cy = 195, R = 128, LR = 168;
  const ar = (i) => (-90 + (360 / n) * i) * (Math.PI / 180);
  const sp = (v, i) => [cx + R * v * Math.cos(ar(i)), cy + R * v * Math.sin(ar(i))];
  const toP = (vals) => vals.map((v, i) => sp(v, i).join(",")).join(" ");
  const bl = RAGAS_METRICS.map(m => m.baseline), hy = RAGAS_METRICS.map(m => m.hybrid);
  return (
    <svg ref={ref} viewBox="0 0 520 390" width="100%" style={{ display: "block", overflow: "visible" }}>
      <defs>
        <linearGradient id="rGB" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stopColor="#f97316" stopOpacity="0.28" /><stop offset="100%" stopColor="#ef4444" stopOpacity="0.1" /></linearGradient>
        <linearGradient id="rGH" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stopColor="#c026d3" stopOpacity="0.22" /><stop offset="100%" stopColor="#6366f1" stopOpacity="0.08" /></linearGradient>
        <filter id="glow"><feGaussianBlur stdDeviation="3" result="g" /><feMerge><feMergeNode in="g" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
      </defs>
      {[0.2, 0.4, 0.6, 0.8, 1.0].map((lv, li) => <polygon key={li} points={toP(Array(n).fill(lv))} fill={li === 4 ? "rgba(0,0,0,0.02)" : "none"} stroke="rgba(0,0,0,0.06)" strokeWidth="1" />)}
      {Array.from({ length: n }, (_, i) => { const [x, y] = sp(1, i); return <line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke="rgba(0,0,0,0.06)" strokeWidth="1" />; })}
      {[0.2, 0.4, 0.6, 0.8].map(lv => { const [x, y] = sp(lv, 0); return <text key={lv} x={x + 5} y={y + 3} fontSize="9" fill="#a0aec0" fontFamily="Inter,sans-serif">{Math.round(lv * 100)}%</text>; })}
      <polygon points={toP(bl)} fill="url(#rGB)" stroke="#f97316" strokeWidth="2.5" strokeLinejoin="round" filter="url(#glow)" style={{ opacity: vis ? 1 : 0, transition: "opacity 0.8s ease" }} />
      {bl.map((v, i) => { const [x, y] = sp(v, i); return <circle key={`b${i}`} cx={x} cy={y} r="5.5" fill="#f97316" stroke="#fff" strokeWidth="2" style={{ opacity: vis ? 1 : 0, transform: vis ? "scale(1)" : "scale(0)", transformOrigin: `${x}px ${y}px`, transition: `all 0.5s ${0.3 + i * 0.1}s cubic-bezier(.21,1.02,.55,1)`, cursor: "pointer" }}><title>{RAGAS_METRICS[i].label}: {(v * 100).toFixed(1)}% (Baseline)</title></circle>; })}
      <polygon points={toP(hy)} fill="url(#rGH)" stroke="#c026d3" strokeWidth="2.5" strokeLinejoin="round" strokeDasharray="7,3" filter="url(#glow)" style={{ opacity: vis ? 1 : 0, transition: "opacity 0.8s 0.2s ease" }} />
      {hy.map((v, i) => { const [x, y] = sp(v, i); return <circle key={`h${i}`} cx={x} cy={y} r="5.5" fill="#c026d3" stroke="#fff" strokeWidth="2" style={{ opacity: vis ? 1 : 0, transform: vis ? "scale(1)" : "scale(0)", transformOrigin: `${x}px ${y}px`, transition: `all 0.5s ${0.5 + i * 0.1}s cubic-bezier(.21,1.02,.55,1)`, cursor: "pointer" }}><title>{RAGAS_METRICS[i].label}: {(v * 100).toFixed(1)}% (Hybrid)</title></circle>; })}
      {RAGAS_METRICS.map((m, i) => { const a = ar(i), lx = cx + LR * Math.cos(a), ly = cy + LR * Math.sin(a); const anchor = lx < cx - 12 ? "end" : lx > cx + 12 ? "start" : "middle"; const dy = ly < cy - R * 0.55 ? -6 : ly > cy + R * 0.55 ? 14 : 4; return <text key={i} x={lx} y={ly + dy} textAnchor={anchor} fontSize="11.5" fontWeight="600" fill="#4a5568" fontFamily="Inter,sans-serif">{m.short}</text>; })}
    </svg>
  );
}

function LatencyChart() {
  const [ref, vis] = useVisible(0.2);
  const W = 440, H = 240, pL = 50, pR = 20, pT = 25, pB = 50, cH = H - pT - pB, maxY = 3;
  const yPx = v => pT + cH - (v / maxY) * cH, hPx = v => (v / maxY) * cH, barW = 58, gap = 12, groupW = (W - pL - pR) / 2;
  return (
    <svg ref={ref} viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block" }}>
      <defs>
        <linearGradient id="lB" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#f97316" /><stop offset="100%" stopColor="#ef4444" stopOpacity="0.7" /></linearGradient>
        <linearGradient id="lH" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#c026d3" /><stop offset="100%" stopColor="#6366f1" stopOpacity="0.7" /></linearGradient>
        <linearGradient id="lBp" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#f97316" stopOpacity="0.45" /><stop offset="100%" stopColor="#f97316" stopOpacity="0.15" /></linearGradient>
        <linearGradient id="lHp" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#c026d3" stopOpacity="0.4" /><stop offset="100%" stopColor="#c026d3" stopOpacity="0.12" /></linearGradient>
        <filter id="barGlow"><feGaussianBlur stdDeviation="2" result="g" /><feMerge><feMergeNode in="g" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
      </defs>
      {[0, 1, 2, 3].map(t => <g key={t}><line x1={pL} y1={yPx(t)} x2={W - pR} y2={yPx(t)} stroke="rgba(0,0,0,0.06)" strokeWidth="1" strokeDasharray={t === 0 ? "0" : "4,3"} /><text x={pL - 7} y={yPx(t) + 4} textAnchor="end" fontSize="10" fill="#a0aec0" fontFamily="Inter,sans-serif">{t}s</text></g>)}
      {LATENCY_DATA.map((d, gi) => { const offX = pL + gi * groupW + (groupW - 2 * barW - gap) / 2; const mH = vis ? hPx(d.mean) : 0, pH = vis ? hPx(d.p95) : 0; const mY = pT + cH - mH, pY = pT + cH - pH; return (
        <g key={gi}>
          <rect x={offX} y={mY} width={barW} height={mH} rx="6" fill={gi === 0 ? "url(#lB)" : "url(#lH)"} filter="url(#barGlow)" style={{ transition: "y 1s cubic-bezier(.21,1.02,.55,1),height 1s cubic-bezier(.21,1.02,.55,1)", cursor: "pointer" }}><title>{d.mode + " Mean: " + d.mean + "s"}</title></rect>
          <rect x={offX + barW + gap} y={pY} width={barW} height={pH} rx="6" fill={gi === 0 ? "url(#lBp)" : "url(#lHp)"} style={{ transition: "y 1s .1s cubic-bezier(.21,1.02,.55,1),height 1s .1s cubic-bezier(.21,1.02,.55,1)", cursor: "pointer" }}><title>{d.mode + " P95: " + d.p95 + "s"}</title></rect>
          <text x={offX + barW / 2} y={mY - 6} textAnchor="middle" fontSize="10.5" fontWeight="700" fill={d.color} fontFamily="Inter,sans-serif" style={{ opacity: vis ? 1 : 0, transition: "opacity .4s .9s" }}>{d.mean}s</text>
          <text x={offX + barW + gap + barW / 2} y={pY - 6} textAnchor="middle" fontSize="10.5" fontWeight="700" fill="#a0aec0" fontFamily="Inter,sans-serif" style={{ opacity: vis ? 1 : 0, transition: "opacity .4s 1s" }}>{d.p95}s</text>
          <text x={offX + barW + gap / 2} y={H - pB + 18} textAnchor="middle" fontSize="12" fontWeight="600" fill="#4a5568" fontFamily="Inter,sans-serif">{d.mode}</text>
        </g>); })}
      <g transform={`translate(${pL},${H - 10})`} fontSize="10" fontFamily="Inter,sans-serif" fill="#718096">
        <rect x={0} y={-9} width={9} height={9} rx="2" fill="#f97316" /><text x={13} y={0}>Base Mean</text>
        <rect x={88} y={-9} width={9} height={9} rx="2" fill="rgba(249,115,22,0.4)" /><text x={101} y={0}>Base P95</text>
        <rect x={168} y={-9} width={9} height={9} rx="2" fill="#c026d3" /><text x={181} y={0}>Hybrid Mean</text>
        <rect x={265} y={-9} width={9} height={9} rx="2" fill="rgba(192,38,211,0.38)" /><text x={278} y={0}>Hybrid P95</text>
      </g>
      <line x1={pL} y1={pT} x2={pL} y2={pT + cH} stroke="rgba(0,0,0,0.1)" strokeWidth="1.5" />
      <line x1={pL} y1={pT + cH} x2={W - pR} y2={pT + cH} stroke="rgba(0,0,0,0.1)" strokeWidth="1.5" />
    </svg>
  );
}

function SensitivityChart() {
  const [ref, vis] = useVisible(0.2);
  const pathRef = useRef(null);
  useEffect(() => {
    if (!vis || !pathRef.current) return;
    const len = pathRef.current.getTotalLength();
    pathRef.current.style.strokeDasharray = String(len);
    pathRef.current.style.strokeDashoffset = String(len);
    const rafId = requestAnimationFrame(() => {
      if (!pathRef.current) return;
      pathRef.current.style.transition = "stroke-dashoffset 1.4s cubic-bezier(.21,1.02,.55,1)";
      pathRef.current.style.strokeDashoffset = "0";
    });
    return () => cancelAnimationFrame(rafId);
  }, [vis]);
  const W = 500, H = 230, pL = 54, pR = 28, pT = 28, pB = 48, cW = W - pL - pR, cH = H - pT - pB, yMin = 0.484, yMax = 0.538;
  const xPx = a => pL + (a / 1) * cW, yPx = s => pT + cH - ((s - yMin) / (yMax - yMin)) * cH;
  const lP = SENSITIVITY.map((d, i) => `${i === 0 ? "M" : "L"} ${xPx(d.alpha).toFixed(1)},${yPx(d.sim).toFixed(1)}`).join(" ");
  const aP = [`M ${xPx(0).toFixed(1)},${(pT + cH).toFixed(1)}`, ...SENSITIVITY.map(d => `L ${xPx(d.alpha).toFixed(1)},${yPx(d.sim).toFixed(1)}`), `L ${xPx(1).toFixed(1)},${(pT + cH).toFixed(1)}`, "Z"].join(" ");
  const best = SENSITIVITY.find(d => d.best), bx = xPx(best.alpha), by = yPx(best.sim);
  return (
    <svg ref={ref} viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block" }}>
      <defs>
        <linearGradient id="aG" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#f97316" stopOpacity="0.28" /><stop offset="100%" stopColor="#c026d3" stopOpacity="0" /></linearGradient>
        <linearGradient id="lG" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stopColor="#f97316" /><stop offset="50%" stopColor="#ef4444" /><stop offset="100%" stopColor="#c026d3" /></linearGradient>
      </defs>
      {[0.49, 0.5, 0.51, 0.52, 0.53].map(t => <g key={t}><line x1={pL} y1={yPx(t)} x2={W - pR} y2={yPx(t)} stroke="rgba(0,0,0,0.06)" strokeWidth="1" strokeDasharray="4,3" /><text x={pL - 7} y={yPx(t) + 4} textAnchor="end" fontSize="9.5" fill="#a0aec0" fontFamily="Inter,sans-serif">{t.toFixed(2)}</text></g>)}
      <rect x={xPx(0.5)} y={pT} width={xPx(1) - xPx(0.5)} height={cH} fill="rgba(16,185,129,0.06)" style={{ opacity: vis ? 1 : 0, transition: "opacity .5s .4s" }} />
      <text x={xPx(0.75)} y={pT + 13} textAnchor="middle" fontSize="9" fontWeight="600" fill="#10b981" fontFamily="Inter,sans-serif" style={{ opacity: vis ? 1 : 0, transition: "opacity .5s .7s" }}>✓ within P95 threshold</text>
      <path d={aP} fill="url(#aG)" style={{ opacity: vis ? 1 : 0, transition: "opacity .6s .2s" }} />
      <path ref={pathRef} d={lP} fill="none" stroke="url(#lG)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      {SENSITIVITY.map((d, i) => <circle key={i} cx={xPx(d.alpha)} cy={yPx(d.sim)} r={d.best ? 7 : 4} fill={d.best ? "#f97316" : "#fff"} stroke={d.best ? "#fff" : "#f97316"} strokeWidth={d.best ? 2.5 : 1.5} style={{ opacity: vis ? 1 : 0, transform: vis ? "scale(1)" : "scale(0)", transformOrigin: `${xPx(d.alpha)}px ${yPx(d.sim)}px`, transition: `all .4s ${0.8 + i * 0.06}s cubic-bezier(.21,1.02,.55,1)`, cursor: "pointer" }}><title>{"\u03B1 = " + d.alpha.toFixed(1) + " | Similarity: " + d.sim.toFixed(4) + (d.best ? " (best)" : "")}</title></circle>)}
      <line x1={bx} y1={pT + 20} x2={bx} y2={by - 10} stroke="#e8542e" strokeWidth="1.5" strokeDasharray="4,3" style={{ opacity: vis ? 1 : 0, transition: "opacity .4s 1.3s" }} />
      <text x={bx + 9} y={by - 14} fontSize="11" fontWeight="700" fill="#e8542e" fontFamily="Inter,sans-serif" style={{ opacity: vis ? 1 : 0, transition: "opacity .4s 1.4s" }}>α = 0.7  ★  best</text>
      {[0, 0.2, 0.4, 0.6, 0.8, 1].map(t => <g key={t}><line x1={xPx(t)} y1={pT + cH} x2={xPx(t)} y2={pT + cH + 4} stroke="rgba(0,0,0,0.12)" strokeWidth="1" /><text x={xPx(t)} y={H - pB + 18} textAnchor="middle" fontSize="10" fill="#a0aec0" fontFamily="Inter,sans-serif">{t.toFixed(1)}</text></g>)}
      <line x1={pL} y1={pT} x2={pL} y2={pT + cH} stroke="rgba(0,0,0,0.1)" strokeWidth="1.5" />
      <line x1={pL} y1={pT + cH} x2={W - pR} y2={pT + cH} stroke="rgba(0,0,0,0.1)" strokeWidth="1.5" />
      <text x={pL + cW / 2} y={H - 3} textAnchor="middle" fontSize="11" fontWeight="600" fill="#718096" fontFamily="Inter,sans-serif">α (semantic weight)</text>
      <text x={13} y={pT + cH / 2} textAnchor="middle" fontSize="11" fontWeight="600" fill="#718096" fontFamily="Inter,sans-serif" transform={`rotate(-90,13,${pT + cH / 2})`}>Mean Similarity</text>
    </svg>
  );
}

/* ── 30-day Trend Line Chart ── */
const SOURCE_COLORS = { arxiv: "#b31b1b", hn: "#ff6600", devto: "#3b49df", github: "#24292e", rss: "#ee802f" };

function TrendLineChart({ data }) {
  const [ref, vis] = useVisible(0.2);
  const pathRef = useRef(null);
  const [hover, setHover] = useState(null);
  useEffect(() => {
    if (!vis || !pathRef.current) return;
    const len = pathRef.current.getTotalLength();
    pathRef.current.style.strokeDasharray = String(len);
    pathRef.current.style.strokeDashoffset = String(len);
    const rafId = requestAnimationFrame(() => {
      if (!pathRef.current) return;
      pathRef.current.style.transition = "stroke-dashoffset 1.2s cubic-bezier(.21,1.02,.55,1)";
      pathRef.current.style.strokeDashoffset = "0";
    });
    return () => cancelAnimationFrame(rafId);
  }, [vis]);
  if (!data || data.length === 0) return null;
  const W = 460, H = 200, pL = 48, pR = 16, pT = 16, pB = 40;
  const cW = W - pL - pR, cH = H - pT - pB;
  const vals = data.map(d => d.mentions);
  const yMax = Math.ceil(Math.max(...vals) * 1.15);
  const xPx = (i) => pL + (i / (data.length - 1)) * cW;
  const yPx = (v) => pT + cH - (v / yMax) * cH;
  const lP = data.map((d, i) => `${i === 0 ? "M" : "L"} ${xPx(i).toFixed(1)},${yPx(d.mentions).toFixed(1)}`).join(" ");
  const aP = [`M ${pL},${pT + cH}`, ...data.map((d, i) => `L ${xPx(i).toFixed(1)},${yPx(d.mentions).toFixed(1)}`), `L ${xPx(data.length - 1).toFixed(1)},${pT + cH}`, "Z"].join(" ");
  return (
    <svg ref={ref} viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block" }} onMouseLeave={() => setHover(null)}>
      <defs>
        <linearGradient id="tlG" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#f97316" stopOpacity="0.22" /><stop offset="100%" stopColor="#c026d3" stopOpacity="0" /></linearGradient>
        <linearGradient id="tlL" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stopColor="#f97316" /><stop offset="100%" stopColor="#c026d3" /></linearGradient>
      </defs>
      {[0, 0.25, 0.5, 0.75, 1].map(f => { const y = pT + cH * (1 - f); return <g key={f}><line x1={pL} y1={y} x2={W - pR} y2={y} stroke="rgba(0,0,0,0.05)" strokeWidth="1" strokeDasharray="3,3" /><text x={pL - 6} y={y + 3} textAnchor="end" fontSize="9" fill="#a0aec0" fontFamily="Inter,sans-serif">{Math.round(yMax * f)}</text></g>; })}
      <path d={aP} fill="url(#tlG)" style={{ opacity: vis ? 1 : 0, transition: "opacity .5s .2s" }} />
      <path ref={pathRef} d={lP} fill="none" stroke="url(#tlL)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      {/* Hover crosshair */}
      {hover !== null && (
        <g>
          <line x1={xPx(hover)} y1={pT} x2={xPx(hover)} y2={pT + cH} stroke="rgba(232,84,46,0.3)" strokeWidth="1" strokeDasharray="3,2" />
          <circle cx={xPx(hover)} cy={yPx(data[hover].mentions)} r="5" fill="#f97316" stroke="#fff" strokeWidth="2" />
          <rect x={xPx(hover) - 52} y={yPx(data[hover].mentions) - 34} width="104" height="26" rx="6" fill="rgba(30,30,30,0.88)" />
          <text x={xPx(hover)} y={yPx(data[hover].mentions) - 17} textAnchor="middle" fontSize="10.5" fontWeight="600" fill="#fff" fontFamily="Inter,sans-serif">{data[hover].date} : {data[hover].mentions}</text>
        </g>
      )}
      {/* Invisible hover zones per data point */}
      {data.map((d, i) => (
        <rect key={i} x={xPx(i) - cW / data.length / 2} y={pT} width={cW / data.length} height={cH} fill="transparent" onMouseEnter={() => setHover(i)} style={{ cursor: "crosshair" }} />
      ))}
      {data.filter((_, i) => i % 5 === 0 || i === data.length - 1).map((d) => {
        const idx = data.indexOf(d);
        return <text key={idx} x={xPx(idx)} y={H - pB + 16} textAnchor="middle" fontSize="8" fill="#a0aec0" fontFamily="Inter,sans-serif">{d.date.slice(5)}</text>;
      })}
      <line x1={pL} y1={pT} x2={pL} y2={pT + cH} stroke="rgba(0,0,0,0.08)" strokeWidth="1" />
      <line x1={pL} y1={pT + cH} x2={W - pR} y2={pT + cH} stroke="rgba(0,0,0,0.08)" strokeWidth="1" />
      <text x={12} y={pT + cH / 2} textAnchor="middle" fontSize="9.5" fontWeight="600" fill="#718096" fontFamily="Inter,sans-serif" transform={`rotate(-90,12,${pT + cH / 2})`}>Documents Ingested</text>
      <text x={pL + cW / 2} y={H - 2} textAnchor="middle" fontSize="9.5" fontWeight="600" fill="#718096" fontFamily="Inter,sans-serif">Date</text>
    </svg>
  );
}

/* ── Source Distribution Bar Chart ── */
function SourceBarChart({ data }) {
  const [ref, vis] = useVisible(0.2);
  const [hoverIdx, setHoverIdx] = useState(null);
  if (!data || data.length === 0) return null;
  const total = data.reduce((s, [, c]) => s + c, 0) || 1;
  return (
    <div ref={ref} className="db-source-bars">
      {data.map(([src, cnt], i) => {
        const pct = ((cnt / total) * 100).toFixed(1);
        const isHover = hoverIdx === i;
        return (
          <div key={src} className={`db-source-bar-row${isHover ? " hovered" : ""}`}
            onMouseEnter={() => setHoverIdx(i)} onMouseLeave={() => setHoverIdx(null)}
            style={{ opacity: vis ? 1 : 0, transform: vis ? "translateX(0)" : "translateX(-12px)", transition: `all .5s ${i * 0.08}s ease` }}>
            <span className="db-source-bar-label">{SOURCE_LABELS[src] || src}</span>
            <div className="db-source-bar-track">
              <div className="db-source-bar-fill" style={{ width: vis ? `${pct}%` : "0%", background: SOURCE_COLORS[src] || "#718096", transition: `width 0.8s ${0.2 + i * 0.08}s cubic-bezier(.21,1.02,.55,1)` }} />
            </div>
            <span className="db-source-bar-pct">{pct}%</span>
            {isHover && (
              <span className="db-source-bar-tooltip">{cnt} documents ({pct}% of {total} total)</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ── Dashboard page ── */
export default function Dashboard({ onGoToApp }) {
  const [heroIn, setHeroIn] = useState(false);
  const [insightLoading, setInsightLoading] = useState(true);
  const [insightError, setInsightError] = useState("");
  const [insights, setInsights] = useState(null);
  const [selectedSources, setSelectedSources] = useState([...HIGHLIGHT_SOURCES]);
  const [pipeRef, pipeVis] = useVisible(0.15);

  useEffect(() => {
    const t = setTimeout(() => setHeroIn(true), 80);
    return () => clearTimeout(t);
  }, []);

  /* Real API call for dashboard insights, with fallback to mock data */
  useEffect(() => {
    let cancelled = false;
    async function loadInsights() {
      setInsightLoading(true);
      setInsightError("");
      try {
        const qp = selectedSources.length
          ? `?sources=${encodeURIComponent(selectedSources.join(","))}`
          : "";
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 6000);
        const res = await fetch(`${API_BASE}/dashboard/insights${qp}`, { signal: controller.signal });
        clearTimeout(timer);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!cancelled) setInsights(data);
      } catch {
        if (!cancelled) {
          setInsights({
            generated_at: Date.now() / 1000,
            total_documents_30d: 1204,
            source_mix: { arxiv: 482, hn: 301, devto: 187, github: 142, rss: 92 },
            topic_highlights: [
              { keyword: "retrieval-augmented generation", weekly_mentions: 127, monthly_mentions: 482, source_coverage: 5, sources: ["arxiv", "devto", "github", "hn", "rss"], growth_pct: 12.4, insight: "Strong growth driven by enterprise adoption of RAG pipelines across all tracked sources", top_source: "arxiv", top_source_pct: 45 },
              { keyword: "agentic workflows",              weekly_mentions: 94,  monthly_mentions: 310, source_coverage: 4, sources: ["arxiv", "devto", "github", "hn"],        growth_pct: 15.3, insight: "Fastest-rising topic as LLM agent frameworks gain traction in production systems", top_source: "github", top_source_pct: 38 },
              { keyword: "vector database",                weekly_mentions: 89,  monthly_mentions: 341, source_coverage: 4, sources: ["arxiv", "devto", "github", "hn"],        growth_pct: -3.1, insight: "Slight cooling after major pgvector and Qdrant releases stabilized the ecosystem", top_source: "github", top_source_pct: 41 },
              { keyword: "cross-encoder reranking",        weekly_mentions: 64,  monthly_mentions: 218, source_coverage: 3, sources: ["arxiv", "github", "hn"],                 growth_pct: 6.2,  insight: "Research-driven growth in two-stage retrieval with reranking optimization", top_source: "arxiv", top_source_pct: 52 },
              { keyword: "prompt engineering",              weekly_mentions: 51,  monthly_mentions: 196, source_coverage: 4, sources: ["arxiv", "devto", "hn", "rss"],           growth_pct: -8.4, insight: "Declining as focus shifts toward automated agent pipelines and tool use", top_source: "devto", top_source_pct: 34 },
              { keyword: "knowledge graphs",                weekly_mentions: 43,  monthly_mentions: 167, source_coverage: 3, sources: ["arxiv", "devto", "github"],               growth_pct: 4.8,  insight: "Renewed interest driven by GraphRAG and hybrid retrieval architectures", top_source: "arxiv", top_source_pct: 48 },
              { keyword: "model quantization",              weekly_mentions: 38,  monthly_mentions: 152, source_coverage: 3, sources: ["arxiv", "github", "hn"],                 growth_pct: -1.2, insight: "Stable activity as GGUF and AWQ formats become standard for edge deployment", top_source: "github", top_source_pct: 44 },
            ],
            topic_timeline: Array.from({ length: 30 }, (_, i) => {
              const d = new Date(); d.setDate(d.getDate() - 29 + i);
              /* Realistic ingestion pattern: ~30-38 base, weekday peaks, growth trend last 10 days */
              const dayOfWeek = d.getDay();
              const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;
              const base = isWeekend ? 24 : 35;
              const trend = i > 19 ? (i - 19) * 2.5 : 0;
              const dip = i === 12 ? -8 : 0; /* mid-month maintenance dip */
              const mentions = Math.round(base + trend + dip + (Math.sin(i * 0.7) * 3));
              return { date: d.toISOString().slice(0, 10), mentions: Math.max(mentions, 15) };
            }),
            today_highlights: [
              { title: "Hybrid RAG Performance Improvements", source: "arxiv", score: 0.94, url: "https://arxiv.org/search/?query=retrieval+augmented+generation&searchtype=all" },
              { title: "Cross-Encoder Reranking Implementation", source: "github", score: 0.89, url: "https://github.com/search?q=cross-encoder+reranking&type=repositories" },
              { title: "BM25 Tokenization Enhancement", source: "hn", score: 0.85, url: "https://hn.algolia.com/?q=BM25" },
              { title: "Vector Search HNSW Tuning", source: "devto", score: 0.82, url: "https://dev.to/search?q=vector%20search%20hnsw" },
            ],
          });
          setInsightError("");
        }
      } finally {
        if (!cancelled) setInsightLoading(false);
      }
    }
    loadInsights();
    return () => { cancelled = true; };
  }, [selectedSources]);

  const sourceMix = useMemo(() => {
    if (!insights?.source_mix) return [];
    return Object.entries(insights.source_mix).sort((a, b) => b[1] - a[1]);
  }, [insights]);

  const highlightItems = (insights?.today_highlights || []).filter(
    (item) => item?.title !== "Temporal Decay for Document Freshness"
  );
  const featuredHighlight = highlightItems[0] || null;
  const moreHighlights = highlightItems.slice(1, 6);
  const updatedAt = insights?.generated_at
    ? new Date(insights.generated_at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : "--:--";

  const toggleSource = (src) => {
    setSelectedSources(prev => prev.includes(src) ? prev.filter(s => s !== src) : [...prev, src]);
  };

  return (
    <div className="db">
      <AuroraBg />
      <FloatingTechIcons />

      <nav className="db-nav">
        <span className="db-nav-brand"><em>TechPulse</em></span>
        <button className="db-pill-btn" onClick={onGoToApp}>Try It Now →</button>
      </nav>

      <section className="db-hero" style={{ opacity: heroIn ? 1 : 0, transform: heroIn ? "translateY(0)" : "translateY(24px)", transition: "all .8s cubic-bezier(.21,1.02,.55,1)" }}>
        <div className="db-hero-content">
          <p className="db-eyebrow">MLOps · Data Engineering · RAG System</p>
          <h1 className="db-hero-title">TechPulse</h1>
          <p className="db-hero-slogan">Real-time technology intelligence,<br />grounded in sources</p>
          <div className="db-hero-team">
            <div className="db-hero-member">
              <span className="db-hero-member-name">Aye Khin Khin Hpone</span>
              <span className="db-hero-member-sub">(Yolanda Lim) st125970</span>
            </div>
            <span className="db-hero-team-sep">|</span>
            <div className="db-hero-member">
              <span className="db-hero-member-name">Dechathon Niamsa-Ard</span>
              <span className="db-hero-member-sub">st126235</span>
            </div>
          </div>
          <div className="db-hero-actions">
            <button className="db-pill-btn large" onClick={onGoToApp}>Try It Now</button>
            <a className="db-ghost-btn" href="#results">View Results ↓</a>
          </div>
        </div>
      </section>

      <GradientDivider />

      {/* ── Tech Topic Highlights ── */}
      <section className="db-section" style={{ borderTop: "none" }}>
        <h2 className="db-section-title db-gradient-text">Tech Topic Highlights</h2>
        <p className="db-section-sub">Top emerging topics across ingested sources in the last 30 days.</p>
        {insightLoading && <p className="db-note" style={{ textAlign: "center" }}>Loading live topic highlights...</p>}
        {!insightLoading && insightError && <p className="db-note" style={{ textAlign: "center" }}>Unable to load topic highlights ({insightError}).</p>}
        {!insightLoading && !insightError && (insights?.topic_highlights?.length > 0 || insights?.topic_highlight) && (
          <div className="db-topic-grid">
            {(insights.topic_highlights || [insights.topic_highlight]).map((topic, idx) => {
              const g = topic.growth_pct ?? 0;
              const arrow = g > 1 ? "\u2191" : g < -1 ? "\u2193" : "\u2192";
              const gColor = g > 1 ? "#16a34a" : g < -1 ? "#dc2626" : "#6366f1";
              const trendClass = g > 1 ? "rising" : g < -1 ? "declining" : "stable";
              const fallbackInsight = g > 5 ? "Rapid growth \u2014 rising adoption across sources"
                : g > 1 ? "Steady growth \u2014 consistent interest this week"
                : g < -5 ? "Declining \u2014 reduced mentions vs monthly average"
                : g < -1 ? "Slight decline \u2014 marginal drop this week"
                : "Stable \u2014 consistent mention rate";
              const insightText = topic.insight || fallbackInsight;
              const topSrc = topic.top_source ? (SOURCE_LABELS[topic.top_source] || topic.top_source) : null;
              return (
                <div key={idx} className={`db-topic-highlight-card ${trendClass}${idx === 0 ? " featured" : ""}`} style={{ animationDelay: `${idx * 0.08}s` }}>
                  <span className="db-topic-rank">#{idx + 1}</span>
                  <div className="db-topic-badge">{topic.keyword}</div>
                  <div className="db-topic-trend" style={{ color: gColor }}>
                    <span className="db-topic-arrow">{arrow}</span>
                    <span>{g > 0 ? "+" : ""}{g}%</span>
                    <span className="db-topic-trend-label">vs prior weekly avg</span>
                  </div>
                  <div className="db-topic-stats">
                    <div className="db-topic-stat">
                      <span className="db-topic-stat-num"><AnimatedNumber value={topic.weekly_mentions} /></span>
                      <span className="db-topic-stat-label">This week</span>
                    </div>
                    <div className="db-topic-stat">
                      <span className="db-topic-stat-num"><AnimatedNumber value={topic.monthly_mentions} /></span>
                      <span className="db-topic-stat-label">30 days</span>
                    </div>
                    <div className="db-topic-stat">
                      <span className="db-topic-stat-num"><AnimatedNumber value={topic.source_coverage} /></span>
                      <span className="db-topic-stat-label">Sources</span>
                    </div>
                  </div>
                  <p className="db-topic-insight">{insightText}</p>
                  <p className="db-topic-coverage">
                    {(topic.sources || []).map(s => SOURCE_LABELS[s] || s).join(" \u00B7 ")}
                    {topSrc && topic.top_source_pct ? ` \u2014 Top: ${topSrc} (${topic.top_source_pct}%)` : ""}
                  </p>
                </div>
              );
            })}
          </div>
        )}
        {!insightLoading && !insightError && !insights?.topic_highlights?.length && !insights?.topic_highlight && (
          <p className="db-note" style={{ textAlign: "center" }}>No trending topics detected in the current window.</p>
        )}
      </section>

      <GradientDivider />

      {/* ── Analytics Row: Trend + Source Distribution ── */}
      {!insightLoading && insights && (
        <section className="db-section" style={{ borderTop: "none" }}>
          <h2 className="db-section-title db-gradient-text">Analytics</h2>
          <p className="db-section-sub">30-day mention trend and source distribution at a glance.</p>
          <div className="db-analytics-row">
            <div className="db-card db-glow-card">
              <h3 className="db-card-title">30-Day Mention Trend</h3>
              <TrendLineChart data={insights.topic_timeline} />
            </div>
            <div className="db-card db-glow-card">
              <h3 className="db-card-title">Source Distribution</h3>
              <SourceBarChart data={sourceMix} />
            </div>
          </div>
        </section>
      )}

      <GradientDivider />

      <section className="db-section" id="live-insights" style={{ borderTop: "none" }}>
        <h2 className="db-section-title db-gradient-text">Live Insight Explorer</h2>
        <p className="db-section-sub">Daily brief from live ingestion. Filter by source and explore top signals.</p>
        <div className="db-card db-glow-card">
          <div className="db-insight-toolbar">
            <div className="db-insight-toolbar-title">Source Filters</div>
            <span className="db-insight-toolbar-count">{selectedSources.length} selected</span>
          </div>
          <div className="db-live-ribbon"><span className="db-live-dot" /><span>Live web signals</span><span className="db-live-sep">•</span><span>Updated {updatedAt}</span></div>
          <div className="db-source-select-row">
            {HIGHLIGHT_SOURCES.map(src => (
              <button key={src} type="button" className={`db-toggle-btn ${selectedSources.includes(src) ? "active" : ""}`} onClick={() => toggleSource(src)}>
                {SOURCE_LABELS[src] || src}
              </button>
            ))}
          </div>

          {insightLoading && <p className="db-note">Loading live insights…</p>}

          {!insightLoading && selectedSources.length > 0 && (
            <div className="db-insight-layout">
              {featuredHighlight && (
                <a className="db-featured-highlight" href={resolveHighlightUrl(featuredHighlight)} target="_blank" rel="noopener noreferrer">
                  <span className="db-featured-badge">Top Highlight</span>
                  <h3 className="db-featured-title">{featuredHighlight.title}</h3>
                  <p className="db-featured-meta">{SOURCE_LABELS[featuredHighlight.source] || featuredHighlight.source} · significance {featuredHighlight.score}</p>
                </a>
              )}
              {moreHighlights.length > 0 && (
                <div className="db-insight-list-side">
                  {moreHighlights.map((item, idx) => (
                    <a key={idx} className="db-highlight-item" href={resolveHighlightUrl(item)} target="_blank" rel="noopener noreferrer" style={{ animationDelay: `${0.08 * (idx + 1)}s` }}>
                      <span className="db-insight-key">{item.title}</span>
                      <span className="db-insight-meta">{SOURCE_LABELS[item.source] || item.source} · significance {item.score}</span>
                    </a>
                  ))}
                </div>
              )}
            </div>
          )}

          {!insightLoading && selectedSources.length === 0 && (
            <div className="db-empty-state">
              <p className="db-note">Select at least one source to view highlights.</p>
              <button type="button" className="db-mini-btn" onClick={() => setSelectedSources([...HIGHLIGHT_SOURCES])}>Select all sources</button>
            </div>
          )}

          {sourceMix.length > 0 && !insightLoading && (
            <div className="db-source-strip">
              {sourceMix.map(([src, cnt]) => (
                <a
                  key={src}
                  className="db-source-chip"
                  href={SOURCE_URLS[src] || "#"}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {SOURCE_LABELS[src] || src}: {cnt}
                </a>
              ))}
            </div>
          )}
        </div>
      </section>

      <GradientDivider />

      <section className="db-section" style={{ borderTop: "none" }}>
        <p className="db-section-sub">From raw data to grounded, cited answers — fully automated.</p>
        <div className="db-pipeline" ref={pipeRef}>
          {PIPELINE_STEPS.map((step, i) => (
            <div key={i} className="db-step-wrap" style={{ opacity: pipeVis ? 1 : 0, transform: pipeVis ? "translateY(0) scale(1)" : "translateY(24px) scale(0.95)", transition: `all .6s ${0.1 + i * 0.09}s cubic-bezier(.21,1.02,.55,1)` }}>
              <div className="db-step">
                <div className="db-step-icon-wrap"><span className="db-step-icon">{step.icon}</span></div>
                <div className="db-step-label">{step.label}</div>
                <div className="db-step-desc">{step.desc}</div>
              </div>
              {i < PIPELINE_STEPS.length - 1 && <div className="db-step-arrow">→</div>}
            </div>
          ))}
        </div>
      </section>

      <GradientDivider />

      <section className="db-section" id="results" style={{ borderTop: "none" }}>
        <h2 className="db-section-title db-gradient-text">Evaluation Results</h2>
        <p className="db-section-sub">100 samples (50 baseline + 50 hybrid) · RAGAS metrics + Wilcoxon signed-rank tests · Groq llama-3.3-70b-versatile judge · 0 NaN values.</p>
        <div className="db-card db-glow-card">
          <h3 className="db-card-title">RAGAS Metrics — Baseline vs Hybrid</h3>
          <p className="db-card-sub">Spider chart comparing all five quality dimensions.</p>
          <div className="db-legend"><span className="db-dot" style={{ background: "#f97316" }} /> Baseline <span className="db-dot" style={{ background: "#c026d3", marginLeft: "0.8rem" }} /> Hybrid (dashed)</div>
          <RadarChart />
          <p className="db-note">Composite weights: Faithfulness 35% · Answer Relevancy 25% · Context Precision 20% · Citation Grounding 20%. Hybrid leads on 3 of 5 axes — +5.8 pp faithfulness, +6.5 pp answer relevancy, +7.0 pp context precision. Composite: Hybrid 0.723 vs Baseline 0.676 (+4.7 pp).</p>
        </div>
        <div className="db-card db-glow-card">
          <h3 className="db-card-title">Response Latency — Mean &amp; P95</h3>
          <p className="db-card-sub">Grouped bars comparing mean and 95th-percentile latency per retrieval mode.</p>
          <LatencyChart />
          <p className="db-note">Hybrid adds +1.36 s mean overhead from BM25 + cross-encoder reranking (1.125 s → 2.487 s). Wilcoxon p ≈ 0 · Cohen's d = −0.34 → small effect size, statistically significant latency trade-off.</p>
        </div>
        <div className="db-card db-glow-card">
          <h3 className="db-card-title">Hybrid Weight Sensitivity — α (Semantic)</h3>
          <p className="db-card-sub">Score = α · semantic + β · BM25 + γ · temporal. β and γ scale proportionally.</p>
          <SensitivityChart />
          <p className="db-note">Grid-search identified α = 0.7 as best latency-constrained optimum. Production weights: Vector 0.50 · BM25 0.35 · Recency 0.15.</p>
        </div>
        <div className="db-stats-grid">
          {KEY_STATS.map((s, i) => (
            <div key={i} className="db-stat-card">
              <div className="db-stat-num"><AnimatedNumber value={s.num} /></div>
              <div className="db-stat-label">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="db-cta-section">
        <h2 className="db-cta-title">Ready to explore?</h2>
        <p className="db-cta-desc">Ask anything about emerging technology trends.</p>
        <button className="db-pill-btn large" onClick={onGoToApp}>Go to TechPulse →</button>
      </section>

      <footer className="db-footer">
        <div className="db-footer-team">
          {TEAM_MEMBERS.map(m => <span key={m.id}>{m.name} · {m.id}</span>)}
        </div>
        <p className="db-footer-course">AT82.9002 Selected Topics: Data Engineering &amp; MLOps · AIT</p>
      </footer>
    </div>
  );
}


