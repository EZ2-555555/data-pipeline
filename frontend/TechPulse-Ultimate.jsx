import { useState, useEffect, useRef, useMemo } from "react";

/* ═══════════════════════════════════════════════════════════
   TechPulse — ULTIMATE Enhanced Edition
   ═══════════════════════════════════════════════════════════ */

// ── Data ──
const RAGAS_METRICS = [
  { label: "Faithfulness", short: "Faithfulness", baseline: 0.6894, hybrid: 0.7471 },
  { label: "Answer Relevancy", short: "Ans. Relevancy", baseline: 0.8692, hybrid: 0.9343 },
  { label: "Context Precision", short: "Ctx. Precision", baseline: 0.2083, hybrid: 0.278 },
  { label: "Citation Grd.", short: "Citation Grd.", baseline: 0.88, hybrid: 0.86 },
  { label: "Composite Score", short: "Composite", baseline: 0.6762, hybrid: 0.7227 },
];
const LATENCY_DATA = [
  { mode: "Baseline", mean: 1.125, p95: 1.477, color: "#f97316", colorP95: "rgba(249,115,22,0.4)" },
  { mode: "Hybrid", mean: 2.487, p95: 2.444, color: "#c026d3", colorP95: "rgba(192,38,211,0.38)" },
];
const SENSITIVITY = [
  { alpha: 0.0, sim: 0.4901 }, { alpha: 0.1, sim: 0.4916 }, { alpha: 0.2, sim: 0.4988 },
  { alpha: 0.3, sim: 0.5037 }, { alpha: 0.4, sim: 0.5117 }, { alpha: 0.5, sim: 0.519 },
  { alpha: 0.6, sim: 0.5237 }, { alpha: 0.7, sim: 0.5259, best: true },
  { alpha: 0.8, sim: 0.5298 }, { alpha: 0.9, sim: 0.5314 }, { alpha: 1.0, sim: 0.5323 },
];
const PIPELINE_STEPS = [
  { icon: "📡", label: "Data Sources", desc: "HN · ArXiv · DEV.to · GitHub · RSS", color: "#f97316" },
  { icon: "⚙️", label: "Ingestion", desc: "Multi-source crawlers, dedup & rate-limiting", color: "#ef4444" },
  { icon: "🧠", label: "Embedding", desc: "fastembed all-MiniLM-L6-v2 → 384-dim vectors", color: "#a855f7" },
  { icon: "🗄️", label: "pgvector DB", desc: "PostgreSQL + pgvector HNSW similarity search", color: "#3b82f6" },
  { icon: "🔀", label: "Hybrid Retrieval", desc: "Vector + BM25 + weighted RRF + cross-encoder rerank", color: "#10b981" },
  { icon: "💬", label: "LLM Answer", desc: "Groq Llama 3.1 · grounded, cited responses", color: "#f59e0b" },
];
const KEY_STATS = [
  { num: "100", label: "RAGAS Samples" },
  { num: "0.723", label: "Hybrid Composite" },
  { num: "+4.7pp", label: "Composite Gain" },
  { num: "$0", label: "Monthly Infra Cost" },
];
const EXAMPLE_QUERIES = [
  "What are the latest trends in quantum computing?",
  "How is Rust being adopted in systems programming?",
  "What recent advances have been made in LLM fine-tuning?",
  "What are emerging best practices for MLOps pipelines?",
];
const TEAM_MEMBERS = [
  { name: "Aye Khin Khin Hpone (Yolanda Lim)", id: "st125970" },
  { name: "Dechathon Niamsa-Ard", id: "st126235" },
];
const SOURCE_LABELS = { arxiv: "ArXiv", devto: "DEV.to", hn: "Hacker News", github: "GitHub", rss: "RSS" };
const HIGHLIGHT_SOURCES = ["arxiv", "devto", "hn", "github", "rss"];
const SOURCE_BADGES = {
  arxiv: { label: "ArXiv", bg: "linear-gradient(135deg, #b31b1b, #e74c3c)" },
  hn: { label: "HN", bg: "linear-gradient(135deg, #ff6600, #ff9248)" },
  devto: { label: "DEV.to", bg: "linear-gradient(135deg, #3b49df, #6366f1)" },
  github: { label: "GitHub", bg: "linear-gradient(135deg, #24292e, #586069)" },
  rss: { label: "RSS", bg: "linear-gradient(135deg, #ee802f, #f5a623)" },
};
const MOCK_HIGHLIGHTS = [
  { title: "Hybrid RAG Performance Improvements", source: "arxiv", score: 0.94, url: "#" },
  { title: "Cross-Encoder Reranking Implementation", source: "github", score: 0.89, url: "#" },
  { title: "BM25 Tokenization Enhancement", source: "hn", score: 0.85, url: "#" },
  { title: "Vector Search HNSW Tuning", source: "devto", score: 0.82, url: "#" },
  { title: "Temporal Decay for Document Freshness", source: "rss", score: 0.78, url: "#" },
];

// ── Hooks ──
function useVisible(threshold = 0.18) {
  const [vis, setVis] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const obs = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setVis(true); obs.disconnect(); } }, { threshold });
    obs.observe(el); return () => obs.disconnect();
  }, [threshold]);
  return [ref, vis];
}

function AnimatedNumber({ value, duration = 1200 }) {
  const [display, setDisplay] = useState("0");
  const [ref, vis] = useVisible(0.3);
  useEffect(() => {
    if (!vis) return;
    const isFloat = value.includes(".");
    const isPlus = value.startsWith("+");
    const clean = value.replace(/[^0-9.]/g, "");
    const target = parseFloat(clean);
    if (isNaN(target)) { setDisplay(value); return; }
    const start = performance.now();
    const step = (now) => {
      const t = Math.min((now - start) / duration, 1);
      const ease = 1 - Math.pow(1 - t, 3);
      const cur = target * ease;
      let formatted = isFloat ? cur.toFixed(value.split(".")[1]?.replace(/[^0-9]/g,"").length || 1) : String(Math.round(cur));
      if (isPlus) formatted = "+" + formatted;
      if (value.endsWith("pp")) formatted += "pp";
      setDisplay(formatted);
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }, [vis, value, duration]);
  return <span ref={ref}>{display}</span>;
}

// ── Floating Tech Icons (SVG-based, no emoji) ──
function FloatingTechIcons() {
  const icons = [
    // CPU/Chip
    { d: "M9 3v2m6-2v2M9 19v2m6-2v2M3 9h2m-2 6h2m14-6h2m-2 6h2M7 7h10v10H7z", x: "8%", y: "15%", delay: "0s", dur: "14s", size: 28 },
    // Cloud
    { d: "M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z", x: "85%", y: "22%", delay: "2s", dur: "18s", size: 32 },
    // Code brackets
    { d: "M16 18l6-6-6-6M8 6l-6 6 6 6", x: "12%", y: "65%", delay: "4s", dur: "16s", size: 24 },
    // Database
    { d: "M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4", x: "90%", y: "70%", delay: "1s", dur: "15s", size: 26 },
    // Neural network / brain
    { d: "M12 2a4 4 0 014 4c0 1.1-.45 2.1-1.17 2.83L12 12l-2.83-3.17A4 4 0 0112 2zm-6 8a3 3 0 013 3v1l3 3-3 3v1a3 3 0 11-3-3v-1L3 14l3-3v-1zm12 0a3 3 0 00-3 3v1l-3 3 3 3v1a3 3 0 103-3v-1l3-3-3-3v-1z", x: "50%", y: "8%", delay: "3s", dur: "20s", size: 30 },
    // Wifi/signal
    { d: "M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.858 15.355-5.858 21.213 0", x: "78%", y: "45%", delay: "5s", dur: "17s", size: 22 },
    // Lock/security
    { d: "M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z", x: "25%", y: "82%", delay: "6s", dur: "19s", size: 24 },
    // Lightning/bolt
    { d: "M13 10V3L4 14h7v7l9-11h-7z", x: "65%", y: "85%", delay: "1.5s", dur: "13s", size: 26 },
    // Globe
    { d: "M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9", x: "38%", y: "40%", delay: "3.5s", dur: "21s", size: 20 },
    // Terminal
    { d: "M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z", x: "55%", y: "55%", delay: "7s", dur: "16s", size: 22 },
  ];
  return (
    <div className="tp-floating-icons" aria-hidden="true">
      {icons.map((ic, i) => (
        <svg key={i} className="tp-float-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"
          style={{ left: ic.x, top: ic.y, width: ic.size, height: ic.size, animationDelay: ic.delay, animationDuration: ic.dur }}>
          <path d={ic.d} />
        </svg>
      ))}
    </div>
  );
}

// ── Blobs (MUCH more visible — higher opacity, bigger scale, more movement) ──
function DecoBlobs({ prefix = "b" }) {
  return (
    <div className="tp-deco-blobs" aria-hidden="true">
      <svg className="tp-blob tp-blob-1" viewBox="0 0 600 600"><defs>
        <linearGradient id={`${prefix}g1`} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#f97316" /><stop offset="50%" stopColor="#ef4444" /><stop offset="100%" stopColor="#c026d3" />
        </linearGradient></defs>
        <path fill={`url(#${prefix}g1)`} d="M421,305Q391,410,286,448Q181,486,117,368Q53,250,152,168Q251,86,345,130Q439,174,451,237Q463,300,421,305Z" />
      </svg>
      <svg className="tp-blob tp-blob-2" viewBox="0 0 600 600"><defs>
        <linearGradient id={`${prefix}g2`} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#fb923c" /><stop offset="100%" stopColor="#f472b6" />
        </linearGradient></defs>
        <path fill={`url(#${prefix}g2)`} d="M454,326Q443,452,310,462Q177,472,127,361Q77,250,160,152Q243,54,353,100Q463,146,466,198Q469,250,454,326Z" />
      </svg>
      <svg className="tp-blob tp-blob-3" viewBox="0 0 600 600"><defs>
        <linearGradient id={`${prefix}g3`} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#a78bfa" /><stop offset="100%" stopColor="#6366f1" />
        </linearGradient></defs>
        <path fill={`url(#${prefix}g3)`} d="M389,316Q408,432,296,458Q184,484,128,367Q72,250,155,163Q238,76,338,112Q438,148,406,199Q374,250,389,316Z" />
      </svg>
      <svg className="tp-blob tp-blob-4" viewBox="0 0 600 600"><defs>
        <linearGradient id={`${prefix}g4`} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#f97316" stopOpacity="0.6" /><stop offset="100%" stopColor="#a78bfa" stopOpacity="0.4" />
        </linearGradient></defs>
        <path fill={`url(#${prefix}g4)`} d="M454,326Q443,452,310,462Q177,472,127,361Q77,250,160,152Q243,54,353,100Q463,146,466,198Q469,250,454,326Z" />
      </svg>
      <svg className="tp-blob tp-blob-5" viewBox="0 0 600 600"><defs>
        <linearGradient id={`${prefix}g5`} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#ef4444" stopOpacity="0.5" /><stop offset="100%" stopColor="#f472b6" stopOpacity="0.3" />
        </linearGradient></defs>
        <path fill={`url(#${prefix}g5)`} d="M421,305Q391,410,286,448Q181,486,117,368Q53,250,152,168Q251,86,345,130Q439,174,451,237Q463,300,421,305Z" />
      </svg>
      <div className="tp-circle-deco tp-cd1"><div className="tp-ring tp-r1"/><div className="tp-ring tp-r2"/><div className="tp-ring tp-r3"/><div className="tp-ring tp-r4"/></div>
      <div className="tp-circle-deco tp-cd2"><div className="tp-ring tp-r1"/><div className="tp-ring tp-r2"/><div className="tp-ring tp-r3"/></div>
      <div className="tp-circle-deco tp-cd3"><div className="tp-ring tp-r1"/><div className="tp-ring tp-r2"/></div>
    </div>
  );
}

// ── Gradient Divider ──
function GradientDivider() {
  return <div className="tp-grad-divider" />;
}

// ── Charts ──
function RadarChart() {
  const [ref, vis] = useVisible(0.2);
  const n=5,cx=255,cy=195,R=128,LR=168;
  const ar=(i)=>(-90+(360/n)*i)*(Math.PI/180);
  const sp=(v,i)=>[cx+R*v*Math.cos(ar(i)),cy+R*v*Math.sin(ar(i))];
  const toP=(vals)=>vals.map((v,i)=>sp(v,i).join(",")).join(" ");
  const bl=RAGAS_METRICS.map(m=>m.baseline), hy=RAGAS_METRICS.map(m=>m.hybrid);
  return (
    <svg ref={ref} viewBox="0 0 520 390" width="100%" style={{display:"block",overflow:"visible"}}>
      <defs>
        <linearGradient id="rGB" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stopColor="#f97316" stopOpacity="0.28"/><stop offset="100%" stopColor="#ef4444" stopOpacity="0.1"/></linearGradient>
        <linearGradient id="rGH" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stopColor="#c026d3" stopOpacity="0.22"/><stop offset="100%" stopColor="#6366f1" stopOpacity="0.08"/></linearGradient>
        <filter id="glow"><feGaussianBlur stdDeviation="3" result="g"/><feMerge><feMergeNode in="g"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
      </defs>
      {[0.2,0.4,0.6,0.8,1.0].map((lv,li)=><polygon key={li} points={toP(Array(n).fill(lv))} fill={li===4?"rgba(0,0,0,0.02)":"none"} stroke="rgba(0,0,0,0.06)" strokeWidth="1"/>)}
      {Array.from({length:n},(_,i)=>{const[x,y]=sp(1,i);return<line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke="rgba(0,0,0,0.06)" strokeWidth="1"/>;})}
      {[0.2,0.4,0.6,0.8].map(lv=>{const[x,y]=sp(lv,0);return<text key={lv} x={x+5} y={y+3} fontSize="9" fill="#a0aec0" fontFamily="Inter,sans-serif">{Math.round(lv*100)}%</text>;})}
      <polygon points={toP(bl)} fill="url(#rGB)" stroke="#f97316" strokeWidth="2.5" strokeLinejoin="round" filter="url(#glow)" style={{opacity:vis?1:0,transition:"opacity 0.8s ease"}}/>
      {bl.map((v,i)=>{const[x,y]=sp(v,i);return<circle key={`b${i}`} cx={x} cy={y} r="5.5" fill="#f97316" stroke="#fff" strokeWidth="2" style={{opacity:vis?1:0,transform:vis?"scale(1)":"scale(0)",transformOrigin:`${x}px ${y}px`,transition:`all 0.5s ${0.3+i*0.1}s cubic-bezier(.21,1.02,.55,1)`}}/>;})}
      <polygon points={toP(hy)} fill="url(#rGH)" stroke="#c026d3" strokeWidth="2.5" strokeLinejoin="round" strokeDasharray="7,3" filter="url(#glow)" style={{opacity:vis?1:0,transition:"opacity 0.8s 0.2s ease"}}/>
      {hy.map((v,i)=>{const[x,y]=sp(v,i);return<circle key={`h${i}`} cx={x} cy={y} r="5.5" fill="#c026d3" stroke="#fff" strokeWidth="2" style={{opacity:vis?1:0,transform:vis?"scale(1)":"scale(0)",transformOrigin:`${x}px ${y}px`,transition:`all 0.5s ${0.5+i*0.1}s cubic-bezier(.21,1.02,.55,1)`}}/>;})}
      {RAGAS_METRICS.map((m,i)=>{const a=ar(i),lx=cx+LR*Math.cos(a),ly=cy+LR*Math.sin(a);const anchor=lx<cx-12?"end":lx>cx+12?"start":"middle";const dy=ly<cy-R*0.55?-6:ly>cy+R*0.55?14:4;return<text key={i} x={lx} y={ly+dy} textAnchor={anchor} fontSize="11.5" fontWeight="600" fill="#4a5568" fontFamily="Inter,sans-serif">{m.short}</text>;})}
    </svg>
  );
}

function LatencyChart() {
  const [ref,vis]=useVisible(0.2);
  const W=440,H=240,pL=50,pR=20,pT=25,pB=50,cH=H-pT-pB,maxY=3;
  const yPx=v=>pT+cH-(v/maxY)*cH, hPx=v=>(v/maxY)*cH, barW=58,gap=12,groupW=(W-pL-pR)/2;
  return (
    <svg ref={ref} viewBox={`0 0 ${W} ${H}`} width="100%" style={{display:"block"}}>
      <defs>
        <linearGradient id="lB" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#f97316"/><stop offset="100%" stopColor="#ef4444" stopOpacity="0.7"/></linearGradient>
        <linearGradient id="lH" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#c026d3"/><stop offset="100%" stopColor="#6366f1" stopOpacity="0.7"/></linearGradient>
        <linearGradient id="lBp" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#f97316" stopOpacity="0.45"/><stop offset="100%" stopColor="#f97316" stopOpacity="0.15"/></linearGradient>
        <linearGradient id="lHp" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#c026d3" stopOpacity="0.4"/><stop offset="100%" stopColor="#c026d3" stopOpacity="0.12"/></linearGradient>
        <filter id="barGlow"><feGaussianBlur stdDeviation="2" result="g"/><feMerge><feMergeNode in="g"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
      </defs>
      {[0,1,2,3].map(t=><g key={t}><line x1={pL} y1={yPx(t)} x2={W-pR} y2={yPx(t)} stroke="rgba(0,0,0,0.06)" strokeWidth="1" strokeDasharray={t===0?"0":"4,3"}/><text x={pL-7} y={yPx(t)+4} textAnchor="end" fontSize="10" fill="#a0aec0" fontFamily="Inter,sans-serif">{t}s</text></g>)}
      {LATENCY_DATA.map((d,gi)=>{const offX=pL+gi*groupW+(groupW-2*barW-gap)/2;const mH=vis?hPx(d.mean):0,pH=vis?hPx(d.p95):0;const mY=pT+cH-mH,pY=pT+cH-pH;return(
        <g key={gi}>
          <rect x={offX} y={mY} width={barW} height={mH} rx="6" fill={gi===0?"url(#lB)":"url(#lH)"} filter="url(#barGlow)" style={{transition:"y 1s cubic-bezier(.21,1.02,.55,1),height 1s cubic-bezier(.21,1.02,.55,1)"}}/>
          <rect x={offX+barW+gap} y={pY} width={barW} height={pH} rx="6" fill={gi===0?"url(#lBp)":"url(#lHp)"} style={{transition:"y 1s .1s cubic-bezier(.21,1.02,.55,1),height 1s .1s cubic-bezier(.21,1.02,.55,1)"}}/>
          <text x={offX+barW/2} y={mY-6} textAnchor="middle" fontSize="10.5" fontWeight="700" fill={d.color} fontFamily="Inter,sans-serif" style={{opacity:vis?1:0,transition:"opacity .4s .9s"}}>{d.mean}s</text>
          <text x={offX+barW+gap+barW/2} y={pY-6} textAnchor="middle" fontSize="10.5" fontWeight="700" fill="#a0aec0" fontFamily="Inter,sans-serif" style={{opacity:vis?1:0,transition:"opacity .4s 1s"}}>{d.p95}s</text>
          <text x={offX+barW+gap/2} y={H-pB+18} textAnchor="middle" fontSize="12" fontWeight="600" fill="#4a5568" fontFamily="Inter,sans-serif">{d.mode}</text>
        </g>);})}
      <g transform={`translate(${pL},${H-10})`} fontSize="10" fontFamily="Inter,sans-serif" fill="#718096">
        <rect x={0} y={-9} width={9} height={9} rx="2" fill="#f97316"/><text x={13} y={0}>Base Mean</text>
        <rect x={88} y={-9} width={9} height={9} rx="2" fill="rgba(249,115,22,0.4)"/><text x={101} y={0}>Base P95</text>
        <rect x={168} y={-9} width={9} height={9} rx="2" fill="#c026d3"/><text x={181} y={0}>Hybrid Mean</text>
        <rect x={265} y={-9} width={9} height={9} rx="2" fill="rgba(192,38,211,0.38)"/><text x={278} y={0}>Hybrid P95</text>
      </g>
      <line x1={pL} y1={pT} x2={pL} y2={pT+cH} stroke="rgba(0,0,0,0.1)" strokeWidth="1.5"/>
      <line x1={pL} y1={pT+cH} x2={W-pR} y2={pT+cH} stroke="rgba(0,0,0,0.1)" strokeWidth="1.5"/>
    </svg>
  );
}

function SensitivityChart() {
  const [ref,vis]=useVisible(0.2); const pathRef=useRef(null);
  useEffect(()=>{if(!vis||!pathRef.current)return;const len=pathRef.current.getTotalLength();pathRef.current.style.strokeDasharray=String(len);pathRef.current.style.strokeDashoffset=String(len);requestAnimationFrame(()=>{if(!pathRef.current)return;pathRef.current.style.transition="stroke-dashoffset 1.4s cubic-bezier(.21,1.02,.55,1)";pathRef.current.style.strokeDashoffset="0";});},[vis]);
  const W=500,H=230,pL=54,pR=28,pT=28,pB=48,cW=W-pL-pR,cH=H-pT-pB,yMin=0.484,yMax=0.538;
  const xPx=a=>pL+(a/1)*cW, yPx=s=>pT+cH-((s-yMin)/(yMax-yMin))*cH;
  const lP=SENSITIVITY.map((d,i)=>`${i===0?"M":"L"} ${xPx(d.alpha).toFixed(1)},${yPx(d.sim).toFixed(1)}`).join(" ");
  const aP=[`M ${xPx(0).toFixed(1)},${(pT+cH).toFixed(1)}`,...SENSITIVITY.map(d=>`L ${xPx(d.alpha).toFixed(1)},${yPx(d.sim).toFixed(1)}`),`L ${xPx(1).toFixed(1)},${(pT+cH).toFixed(1)}`,"Z"].join(" ");
  const best=SENSITIVITY.find(d=>d.best), bx=xPx(best.alpha), by=yPx(best.sim);
  return (
    <svg ref={ref} viewBox={`0 0 ${W} ${H}`} width="100%" style={{display:"block"}}>
      <defs>
        <linearGradient id="aG" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#f97316" stopOpacity="0.28"/><stop offset="100%" stopColor="#c026d3" stopOpacity="0"/></linearGradient>
        <linearGradient id="lG" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stopColor="#f97316"/><stop offset="50%" stopColor="#ef4444"/><stop offset="100%" stopColor="#c026d3"/></linearGradient>
      </defs>
      {[0.49,0.5,0.51,0.52,0.53].map(t=><g key={t}><line x1={pL} y1={yPx(t)} x2={W-pR} y2={yPx(t)} stroke="rgba(0,0,0,0.06)" strokeWidth="1" strokeDasharray="4,3"/><text x={pL-7} y={yPx(t)+4} textAnchor="end" fontSize="9.5" fill="#a0aec0" fontFamily="Inter,sans-serif">{t.toFixed(2)}</text></g>)}
      <rect x={xPx(0.5)} y={pT} width={xPx(1)-xPx(0.5)} height={cH} fill="rgba(16,185,129,0.06)" style={{opacity:vis?1:0,transition:"opacity .5s .4s"}}/>
      <text x={xPx(0.75)} y={pT+13} textAnchor="middle" fontSize="9" fontWeight="600" fill="#10b981" fontFamily="Inter,sans-serif" style={{opacity:vis?1:0,transition:"opacity .5s .7s"}}>✓ within P95 threshold</text>
      <path d={aP} fill="url(#aG)" style={{opacity:vis?1:0,transition:"opacity .6s .2s"}}/>
      <path ref={pathRef} d={lP} fill="none" stroke="url(#lG)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
      {SENSITIVITY.map((d,i)=><circle key={i} cx={xPx(d.alpha)} cy={yPx(d.sim)} r={d.best?7:4} fill={d.best?"#f97316":"#fff"} stroke={d.best?"#fff":"#f97316"} strokeWidth={d.best?2.5:1.5} style={{opacity:vis?1:0,transform:vis?"scale(1)":"scale(0)",transformOrigin:`${xPx(d.alpha)}px ${yPx(d.sim)}px`,transition:`all .4s ${0.8+i*0.06}s cubic-bezier(.21,1.02,.55,1)`}}/>)}
      <line x1={bx} y1={pT+20} x2={bx} y2={by-10} stroke="#e8542e" strokeWidth="1.5" strokeDasharray="4,3" style={{opacity:vis?1:0,transition:"opacity .4s 1.3s"}}/>
      <text x={bx+9} y={by-14} fontSize="11" fontWeight="700" fill="#e8542e" fontFamily="Inter,sans-serif" style={{opacity:vis?1:0,transition:"opacity .4s 1.4s"}}>α = 0.7  ★  best</text>
      {[0,0.2,0.4,0.6,0.8,1].map(t=><g key={t}><line x1={xPx(t)} y1={pT+cH} x2={xPx(t)} y2={pT+cH+4} stroke="rgba(0,0,0,0.12)" strokeWidth="1"/><text x={xPx(t)} y={H-pB+18} textAnchor="middle" fontSize="10" fill="#a0aec0" fontFamily="Inter,sans-serif">{t.toFixed(1)}</text></g>)}
      <line x1={pL} y1={pT} x2={pL} y2={pT+cH} stroke="rgba(0,0,0,0.1)" strokeWidth="1.5"/>
      <line x1={pL} y1={pT+cH} x2={W-pR} y2={pT+cH} stroke="rgba(0,0,0,0.1)" strokeWidth="1.5"/>
      <text x={pL+cW/2} y={H-3} textAnchor="middle" fontSize="11" fontWeight="600" fill="#718096" fontFamily="Inter,sans-serif">α (semantic weight)</text>
      <text x={13} y={pT+cH/2} textAnchor="middle" fontSize="11" fontWeight="600" fill="#718096" fontFamily="Inter,sans-serif" transform={`rotate(-90,13,${pT+cH/2})`}>Mean Similarity</text>
    </svg>
  );
}

// ── Search Page ──
function SearchPage({ onGoToDashboard }) {
  const [query,setQuery]=useState(""); const [mode,setMode]=useState("hybrid"); const [result,setResult]=useState(null); const [loading,setLoading]=useState(false); const [error,setError]=useState(null); const [heroIn,setHeroIn]=useState(false);
  useEffect(()=>{setTimeout(()=>setHeroIn(true),60);},[]);
  const handleSubmit=(e)=>{e.preventDefault();if(!query.trim())return;setLoading(true);setError(null);setResult(null);
    setTimeout(()=>{setResult({mode,answer:`Based on analysis of recent sources across ArXiv, Hacker News, and developer blogs, here's what we found regarding "${query}":\n\nThe field has seen significant advances in the past quarter, with key developments in efficiency optimization, scalable architectures, and practical deployment strategies. Multiple research groups have published concurrent findings suggesting a convergence toward hybrid approaches.\n\nNotably, the community consensus points toward iterative refinement being more effective than one-shot approaches, with measurable improvements in both accuracy and latency metrics.`,
      sources:[{source:"arxiv",title:"Advances in Hybrid Retrieval Systems for Real-Time Applications",url:"#",score:0.94},{source:"hn",title:"Discussion: Production RAG at Scale — Lessons Learned",url:"#",score:0.87},{source:"devto",title:"Building Efficient Vector Pipelines with pgvector",url:"#",score:0.82},{source:"github",title:"cross-encoder/ms-marco-MiniLM-L-6-v2 benchmark results",url:"#",score:0.79}]});setLoading(false);},1800);};

  return (
    <div className="tp-app">
      <DecoBlobs prefix="s"/>
      <FloatingTechIcons/>
      <header className="tp-header" style={{opacity:heroIn?1:0,transform:heroIn?"translateY(0)":"translateY(20px)",transition:"all .7s .1s cubic-bezier(.21,1.02,.55,1)"}}>
        <h1 className="tp-brand">TechPulse</h1>
        <p className="tp-tagline">A Real-Time Hybrid RAG System for Emerging Technology Intelligence</p>
        <button className="tp-about-btn" onClick={onGoToDashboard}>About Project ↗</button>
      </header>
      <main className="tp-main" style={{opacity:heroIn?1:0,transform:heroIn?"translateY(0)":"translateY(24px)",transition:"all .7s .25s cubic-bezier(.21,1.02,.55,1)"}}>
        <div className="tp-search-card">
          <form onSubmit={handleSubmit}>
            <label className="tp-search-label" htmlFor="q">Ask about emerging technology</label>
            <div className="tp-search-row">
              <input id="q" className="tp-search-input" type="text" placeholder="e.g. What are the latest trends in quantum computing?" value={query} onChange={e=>setQuery(e.target.value)} disabled={loading}/>
              <button className="tp-submit-btn" type="submit" disabled={loading||!query.trim()}>
                {loading?<span className="tp-spinner"/>:<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>}
              </button>
            </div>
            <div className="tp-mode-toggle">
              {["baseline","hybrid"].map(m=><button key={m} type="button" className={`tp-mode-btn ${mode===m?"active":""}`} onClick={()=>setMode(m)}>{m.charAt(0).toUpperCase()+m.slice(1)}</button>)}
            </div>
          </form>
        </div>
        {error&&<div className="tp-error-card">Error: {error}</div>}
        {loading&&<div className="tp-loading-indicator"><div className="tp-typing-dots"><span/><span/><span/></div><p>Searching sources & generating answer...</p></div>}
        {!result&&!loading&&!error&&(
          <div className="tp-examples" style={{opacity:heroIn?1:0,transition:"opacity .7s .5s"}}>
            <p className="tp-examples-title">Try asking about:</p>
            <div className="tp-examples-grid">
              {EXAMPLE_QUERIES.map((eq,i)=><button key={i} className="tp-example-card" onClick={()=>setQuery(eq)} style={{animationDelay:`${0.4+i*0.08}s`}}>{eq}</button>)}
            </div>
          </div>
        )}
        {result&&(
          <div className="tp-result-card">
            <div className="tp-answer-header"><h2>Answer</h2><span className="tp-mode-badge">{result.mode}</span></div>
            <div className="tp-answer-text">{result.answer}</div>
            {result.sources?.length>0&&(
              <div className="tp-sources-section"><h3>Sources ({result.sources.length})</h3>
                <ul className="tp-sources-list">{result.sources.map((s,i)=>{const badge=SOURCE_BADGES[s.source]||{label:s.source,bg:"#777"};return(
                  <li key={i} className="tp-source-item" style={{animationDelay:`${0.1+i*0.06}s`}}>
                    <span className="tp-source-badge" style={{background:badge.bg}}>{badge.label}</span>
                    <a href={s.url} target="_blank" rel="noopener noreferrer" className="tp-source-title">{s.title}</a>
                    <span className="tp-source-score">{(s.score*100).toFixed(1)}%</span>
                  </li>);})}</ul>
              </div>
            )}
          </div>
        )}
      </main>
      <footer className="tp-footer">
        <div className="tp-team">{TEAM_MEMBERS.map(m=><p key={m.id} className="tp-team-member">{m.name} · {m.id}</p>)}</div>
        <p className="tp-course">AT82.9002 Selected Topics: Data Engineering & MLOps</p>
      </footer>
    </div>
  );
}

// ── Dashboard ──
function DashboardPage({ onGoToApp }) {
  const [heroIn,setHeroIn]=useState(false); const [selectedSources,setSelectedSources]=useState([...HIGHLIGHT_SOURCES]); const [pipeRef,pipeVis]=useVisible(0.15);
  useEffect(()=>{setTimeout(()=>setHeroIn(true),80);},[]);
  const highlightItems=useMemo(()=>MOCK_HIGHLIGHTS.filter(h=>selectedSources.includes(h.source)),[selectedSources]);
  const featuredHighlight=highlightItems[0]||null, moreHighlights=highlightItems.slice(1,6);
  const sourceMix=useMemo(()=>Object.entries({arxiv:45,hn:25,devto:15,github:10,rss:5}).sort((a,b)=>b[1]-a[1]),[]);
  const toggleSource=(src)=>setSelectedSources(p=>p.includes(src)?p.filter(s=>s!==src):[...p,src]);

  return (
    <div className="tp-db">
      <DecoBlobs prefix="d"/>
      <FloatingTechIcons/>
      <nav className="tp-db-nav"><span className="tp-db-nav-brand"><em>TechPulse</em></span><button className="tp-pill-btn" onClick={onGoToApp}>Try It Now →</button></nav>

      <section className="tp-db-hero" style={{opacity:heroIn?1:0,transform:heroIn?"translateY(0)":"translateY(24px)",transition:"all .8s cubic-bezier(.21,1.02,.55,1)"}}>
        <div className="tp-db-hero-content">
          <p className="tp-eyebrow">MLOps · Data Engineering · RAG System</p>
          <h1 className="tp-db-hero-title">Real-time technology intelligence,<br/>grounded in sources</h1>
          <p className="tp-db-hero-desc">Continuously ingests research and industry signals to produce grounded, citation-backed answers using a tuned hybrid retrieval pipeline.</p>
          <div className="tp-db-hero-actions"><button className="tp-pill-btn large" onClick={onGoToApp}>Try It Now</button><a className="tp-ghost-btn" href="#results">View Results ↓</a></div>
        </div>
      </section>

      <section className="tp-db-section" style={{borderTop:"none"}}>
        <h2 className="tp-db-section-title">Project Team</h2>
        <p className="tp-db-section-sub">Group members and student IDs.</p>
        <div className="tp-team-grid">{TEAM_MEMBERS.map(m=><div key={m.id} className="tp-team-card"><div className="tp-team-card-name">{m.name}</div><div className="tp-team-card-id">{m.id}</div></div>)}</div>
      </section>

      <GradientDivider/>

      <section className="tp-db-section" style={{borderTop:"none"}}>
        <h2 className="tp-db-section-title tp-gradient-text">How It Works</h2>
        <p className="tp-db-section-sub">A fully automated pipeline — from raw data to grounded, cited answers.</p>
        <div className="tp-pipeline" ref={pipeRef}>
          {PIPELINE_STEPS.map((step,i)=>(
            <div key={i} className="tp-step-wrap" style={{opacity:pipeVis?1:0,transform:pipeVis?"translateY(0) scale(1)":"translateY(24px) scale(0.95)",transition:`all .6s ${0.1+i*0.09}s cubic-bezier(.21,1.02,.55,1)`}}>
              <div className="tp-step">
                <div className="tp-step-icon-wrap"><span className="tp-step-icon">{step.icon}</span></div>
                <div className="tp-step-label">{step.label}</div>
                <div className="tp-step-desc">{step.desc}</div>
              </div>
              {i<PIPELINE_STEPS.length-1&&<div className="tp-step-arrow">→</div>}
            </div>
          ))}
        </div>
      </section>

      <GradientDivider/>

      <section className="tp-db-section" id="live-insights" style={{borderTop:"none"}}>
        <h2 className="tp-db-section-title tp-gradient-text">Live Insight Explorer</h2>
        <p className="tp-db-section-sub">Curated daily brief from live ingestion. Pick sources and review the top signal.</p>
        <div className="tp-db-card tp-glow-card">
          <div className="tp-insight-toolbar"><div className="tp-insight-toolbar-title">Source Filters</div><span className="tp-insight-toolbar-count">{selectedSources.length} selected</span></div>
          <div className="tp-live-ribbon"><span className="tp-live-dot"/><span>Live web signals</span><span className="tp-live-sep">•</span><span>Updated --:--</span></div>
          <div className="tp-source-select-row">{HIGHLIGHT_SOURCES.map(src=><button key={src} type="button" className={`tp-toggle-btn ${selectedSources.includes(src)?"active":""}`} onClick={()=>toggleSource(src)}>{SOURCE_LABELS[src]||src}</button>)}</div>
          {selectedSources.length>0&&(
            <div className="tp-insight-layout">
              {featuredHighlight&&<a className="tp-featured-highlight" href="#" target="_blank" rel="noopener noreferrer"><span className="tp-featured-badge">Top Highlight</span><h3 className="tp-featured-title">{featuredHighlight.title}</h3><p className="tp-featured-meta">{SOURCE_LABELS[featuredHighlight.source]} · significance {featuredHighlight.score}</p></a>}
              {moreHighlights.length>0&&<div className="tp-insight-list-side">{moreHighlights.map((item,idx)=><a key={idx} className="tp-highlight-item" href="#" style={{animationDelay:`${0.08*(idx+1)}s`}}><span className="tp-insight-key">{item.title}</span><span className="tp-insight-meta">{SOURCE_LABELS[item.source]} · significance {item.score}</span></a>)}</div>}
            </div>
          )}
          {selectedSources.length===0&&<div className="tp-empty-state"><p className="tp-note">Select at least one source to view highlights.</p><button type="button" className="tp-mini-btn" onClick={()=>setSelectedSources([...HIGHLIGHT_SOURCES])}>Select all sources</button></div>}
          {sourceMix.length>0&&<div className="tp-source-strip">{sourceMix.map(([src,cnt])=><span key={src} className="tp-source-chip">{SOURCE_LABELS[src]||src}: {cnt}</span>)}</div>}
        </div>
      </section>

      <GradientDivider/>

      <section className="tp-db-section" id="results" style={{borderTop:"none"}}>
        <h2 className="tp-db-section-title tp-gradient-text">Evaluation Results</h2>
        <p className="tp-db-section-sub">100 samples (50 baseline + 50 hybrid) · RAGAS metrics + Wilcoxon signed-rank tests · Groq llama-3.3-70b-versatile judge · 0 NaN values.</p>
        <div className="tp-db-card"><h3 className="tp-db-card-title">RAGAS Metrics — Baseline vs Hybrid</h3><p className="tp-db-card-sub">Spider chart comparing all five quality dimensions.</p>
          <div className="tp-legend"><span className="tp-dot" style={{background:"#f97316"}}/> Baseline <span className="tp-dot" style={{background:"#c026d3",marginLeft:"0.8rem"}}/> Hybrid (dashed)</div>
          <RadarChart/><p className="tp-note">Composite weights: Faithfulness 35% · Answer Relevancy 25% · Context Precision 20% · Citation Grounding 20%. Hybrid leads on 3 of 5 axes — +5.8 pp faithfulness, +6.5 pp answer relevancy, +7.0 pp context precision. Composite: Hybrid 0.723 vs Baseline 0.676 (+4.7 pp).</p>
        </div>
        <div className="tp-db-card"><h3 className="tp-db-card-title">Response Latency — Mean & P95</h3><p className="tp-db-card-sub">Grouped bars comparing mean and 95th-percentile latency per retrieval mode.</p>
          <LatencyChart/><p className="tp-note">Hybrid adds +1.36 s mean overhead from BM25 + cross-encoder reranking (1.125 s → 2.487 s). Wilcoxon p ≈ 0 · Cohen's d = −0.34 → small effect size, statistically significant latency trade-off.</p>
        </div>
        <div className="tp-db-card"><h3 className="tp-db-card-title">Hybrid Weight Sensitivity — α (Semantic)</h3><p className="tp-db-card-sub">Score = α · semantic + β · BM25 + γ · temporal. β and γ scale proportionally.</p>
          <SensitivityChart/><p className="tp-note">Grid-search identified α = 0.7 as best latency-constrained optimum. Production weights: Vector 0.50 · BM25 0.35 · Recency 0.15.</p>
        </div>
        <div className="tp-stats-grid">{KEY_STATS.map((s,i)=><div key={i} className="tp-stat-card"><div className="tp-stat-num"><AnimatedNumber value={s.num}/></div><div className="tp-stat-label">{s.label}</div></div>)}</div>
      </section>

      <section className="tp-cta-section">
        <h2 className="tp-cta-title">Ready to explore?</h2>
        <p className="tp-cta-desc">Ask anything about emerging technology trends.</p>
        <button className="tp-pill-btn large" onClick={onGoToApp}>Go to TechPulse →</button>
      </section>
      <footer className="tp-db-footer"><div className="tp-db-footer-team">{TEAM_MEMBERS.map(m=><span key={m.id}>{m.name} · {m.id}</span>)}</div><p className="tp-db-footer-course">AT82.9002 Selected Topics: Data Engineering & MLOps · AIT</p></footer>
    </div>
  );
}

// ── Root ──
export default function App() {
  const [page,setPage]=useState("dashboard");
  return (<>
    <style>{`
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;1,700&family=Inter:wght@400;500;600;700&display=swap');
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:linear-gradient(160deg,#dce8d2 0%,#e5eddb 40%,#eef2e6 100%);color:#1a1a1a;min-height:100vh;overflow-x:hidden;-webkit-font-smoothing:antialiased}

/* Animated gradient top bar */
body::before{content:'';position:fixed;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,#f97316,#ef4444,#c026d3,#6366f1,#10b981,#f97316);background-size:300% 100%;animation:gradShift 5s linear infinite;z-index:10000}
@keyframes gradShift{0%{background-position:0% 50%}100%{background-position:300% 50%}}

::-webkit-scrollbar{width:6px}::-webkit-scrollbar-track{background:transparent}::-webkit-scrollbar-thumb{background:rgba(0,0,0,0.1);border-radius:3px}

/* ═══ BLOBS — MUCH MORE VISIBLE ═══ */
.tp-deco-blobs{position:fixed;inset:0;pointer-events:none;z-index:0;overflow:hidden}
.tp-blob{position:absolute}
.tp-blob-1{width:620px;height:620px;bottom:-100px;right:-80px;opacity:0.75;animation:bf1 16s ease-in-out infinite}
.tp-blob-2{width:480px;height:480px;bottom:-30px;right:80px;opacity:0.65;animation:bf2 20s ease-in-out infinite}
.tp-blob-3{width:280px;height:280px;top:-20px;left:-30px;opacity:0.55;animation:bf3 18s ease-in-out infinite}
.tp-blob-4{width:400px;height:400px;top:8%;right:2%;opacity:0.35;animation:bf4 24s ease-in-out infinite}
.tp-blob-5{width:320px;height:320px;top:50%;left:-60px;opacity:0.3;animation:bf5 22s ease-in-out infinite}
@keyframes bf1{0%,100%{transform:translate(0,0) rotate(0) scale(1)}25%{transform:translate(-30px,-40px) rotate(6deg) scale(1.05)}50%{transform:translate(15px,-20px) rotate(-4deg) scale(0.98)}75%{transform:translate(-10px,15px) rotate(3deg) scale(1.03)}}
@keyframes bf2{0%,100%{transform:translate(0,0) rotate(0) scale(1)}33%{transform:translate(35px,-35px) rotate(-7deg) scale(1.06)}66%{transform:translate(-20px,25px) rotate(5deg) scale(0.97)}}
@keyframes bf3{0%,100%{transform:translate(0,0) scale(1) rotate(0)}40%{transform:translate(20px,25px) scale(1.15) rotate(4deg)}70%{transform:translate(-10px,10px) scale(1.05) rotate(-3deg)}}
@keyframes bf4{0%,100%{transform:translate(0,0) scale(1) rotate(0)}30%{transform:translate(-25px,20px) scale(1.08) rotate(5deg)}60%{transform:translate(15px,-15px) scale(0.95) rotate(-3deg)}}
@keyframes bf5{0%,100%{transform:translate(0,0) scale(1)}50%{transform:translate(30px,-20px) scale(1.1)}}

/* Concentric circles with pulse */
.tp-circle-deco{position:absolute;border-radius:50%}
.tp-cd1{width:280px;height:280px;bottom:30px;right:10px;animation:circPulse 8s ease-in-out infinite}
.tp-cd2{width:160px;height:160px;bottom:220px;right:280px;animation:circPulse 10s ease-in-out infinite 2s}
.tp-cd3{width:120px;height:120px;top:12%;left:6%;animation:circPulse 12s ease-in-out infinite 4s}
@keyframes circPulse{0%,100%{transform:scale(1);opacity:1}50%{transform:scale(1.08);opacity:0.7}}
.tp-ring{position:absolute;border-radius:50%;border:2px solid rgba(255,255,255,0.6);top:50%;left:50%;transform:translate(-50%,-50%)}
.tp-cd1 .tp-r1{width:100%;height:100%}.tp-cd1 .tp-r2{width:75%;height:75%}.tp-cd1 .tp-r3{width:50%;height:50%}.tp-cd1 .tp-r4{width:25%;height:25%}
.tp-cd2 .tp-r1{width:100%;height:100%}.tp-cd2 .tp-r2{width:66%;height:66%}.tp-cd2 .tp-r3{width:33%;height:33%}
.tp-cd3 .tp-r1{width:100%;height:100%}.tp-cd3 .tp-r2{width:55%;height:55%}

/* ═══ FLOATING TECH ICONS ═══ */
.tp-floating-icons{position:fixed;inset:0;pointer-events:none;z-index:1;overflow:hidden}
.tp-float-icon{position:absolute;color:rgba(0,0,0,0.06);animation:techFloat linear infinite;will-change:transform}
@keyframes techFloat{0%{transform:translateY(0) rotate(0deg);opacity:0.04}25%{transform:translateY(-18px) rotate(8deg);opacity:0.08}50%{transform:translateY(-5px) rotate(-5deg);opacity:0.05}75%{transform:translateY(-22px) rotate(10deg);opacity:0.09}100%{transform:translateY(0) rotate(0deg);opacity:0.04}}

/* ═══ GRADIENT DIVIDER ═══ */
.tp-grad-divider{max-width:900px;margin:0 auto;height:2px;background:linear-gradient(90deg,transparent 0%,#f97316 20%,#ef4444 40%,#c026d3 60%,#6366f1 80%,transparent 100%);opacity:0.35;border-radius:2px}

/* ═══ GRADIENT TEXT ═══ */
.tp-gradient-text{background:linear-gradient(135deg,#f97316,#ef4444,#c026d3);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}

/* ═══ SEARCH PAGE ═══ */
.tp-app{position:relative;max-width:860px;margin:0 auto;padding:2.5rem 2rem 1.5rem;min-height:100vh;display:flex;flex-direction:column}
.tp-header{position:relative;z-index:2;text-align:center;margin-bottom:2.5rem}
.tp-brand{font-family:"Playfair Display",Georgia,serif;font-style:italic;font-weight:700;font-size:3.4rem;line-height:1.1;background:linear-gradient(135deg,#1a1a1a 0%,#4a5568 40%,#1a1a1a 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.tp-tagline{font-size:.95rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:#4a5568;margin-top:.5rem;max-width:480px;margin-inline:auto;line-height:1.5}
.tp-about-btn{margin-top:1rem;padding:.45rem 1.2rem;background:transparent;border:1.5px solid rgba(0,0,0,0.12);border-radius:999px;font-size:.8rem;font-weight:600;font-family:inherit;color:#4a5568;cursor:pointer;transition:all .3s}
.tp-about-btn:hover{border-color:#e8542e;color:#e8542e;background:rgba(232,84,46,0.05);transform:translateY(-1px);box-shadow:0 4px 12px rgba(232,84,46,0.15)}

.tp-main{position:relative;z-index:2;flex:1}
.tp-search-card{background:rgba(255,255,255,0.75);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);border:1px solid rgba(0,0,0,0.08);border-radius:20px;padding:1.8rem;box-shadow:0 4px 24px rgba(0,0,0,0.04);transition:all .3s;position:relative;overflow:hidden}
.tp-search-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,#f97316,#ef4444,#c026d3);border-radius:20px 20px 0 0;opacity:0;transition:opacity .3s}
.tp-search-card:hover::before{opacity:1}
.tp-search-card:hover{box-shadow:0 8px 36px rgba(0,0,0,0.07);transform:translateY(-2px)}
.tp-search-label{display:block;font-size:.8rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:#718096;margin-bottom:.75rem}
.tp-search-row{display:flex;gap:.6rem}
.tp-search-input{flex:1;padding:.85rem 1.1rem;font-size:1rem;font-family:inherit;background:#fff;border:1.5px solid rgba(0,0,0,0.1);border-radius:14px;color:#1a1a1a;outline:none;transition:all .25s}
.tp-search-input:focus{border-color:#e8542e;box-shadow:0 0 0 3px rgba(232,84,46,0.12),0 4px 16px rgba(232,84,46,0.08)}
.tp-search-input::placeholder{color:#a0aec0}
.tp-submit-btn{width:48px;height:48px;flex-shrink:0;display:flex;align-items:center;justify-content:center;border:none;border-radius:14px;background:linear-gradient(135deg,#f97316,#ef4444,#c026d3);color:white;cursor:pointer;transition:all .25s;position:relative;overflow:hidden}
.tp-submit-btn::after{content:'';position:absolute;inset:0;background:linear-gradient(135deg,rgba(255,255,255,0.2),transparent);opacity:0;transition:opacity .2s}
.tp-submit-btn:hover:not(:disabled){transform:scale(1.08);box-shadow:0 4px 20px rgba(239,68,68,0.35)}
.tp-submit-btn:hover:not(:disabled)::after{opacity:1}
.tp-submit-btn:disabled{opacity:.4;cursor:not-allowed}
.tp-spinner{width:18px;height:18px;border:2.5px solid rgba(255,255,255,0.3);border-top-color:white;border-radius:50%;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}

.tp-mode-toggle{display:flex;gap:.4rem;margin-top:.9rem}
.tp-mode-btn{padding:.45rem 1.2rem;font-size:.82rem;font-weight:600;font-family:inherit;border:1.5px solid rgba(0,0,0,0.1);border-radius:10px;background:#fff;color:#718096;cursor:pointer;transition:all .25s}
.tp-mode-btn:hover{border-color:#e8542e;color:#e8542e;transform:translateY(-1px)}
.tp-mode-btn.active{background:linear-gradient(135deg,#f97316,#ef4444,#c026d3);border-color:transparent;color:white;box-shadow:0 3px 14px rgba(239,68,68,0.25)}

.tp-error-card{margin-top:1.2rem;padding:.9rem 1.1rem;background:rgba(220,38,38,0.08);border:1.5px solid rgba(220,38,38,0.3);border-radius:14px;color:#dc2626;font-size:.9rem;font-weight:500}

/* Loading indicator with typing dots */
.tp-loading-indicator{margin-top:1.5rem;display:flex;align-items:center;gap:12px;padding:1rem 1.4rem;background:rgba(255,255,255,0.7);backdrop-filter:blur(16px);border:1px solid rgba(0,0,0,0.06);border-radius:16px;animation:fadeSlideUp .4s ease}
.tp-loading-indicator p{font-size:.88rem;color:#718096;font-weight:500}
.tp-typing-dots{display:flex;gap:4px}
.tp-typing-dots span{width:8px;height:8px;border-radius:50%;background:linear-gradient(135deg,#f97316,#c026d3);animation:typingBounce 1.4s ease-in-out infinite}
.tp-typing-dots span:nth-child(2){animation-delay:.15s}
.tp-typing-dots span:nth-child(3){animation-delay:.3s}
@keyframes typingBounce{0%,60%,100%{transform:translateY(0);opacity:.4}30%{transform:translateY(-8px);opacity:1}}

.tp-examples{margin-top:1.5rem;text-align:center}
.tp-examples-title{font-size:.95rem;color:#718096;margin-bottom:.8rem}
.tp-examples-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.7rem}
.tp-example-card{padding:.85rem 1rem;background:rgba(255,255,255,0.72);backdrop-filter:blur(12px);border:1px solid rgba(0,0,0,0.08);border-radius:14px;font-size:.88rem;color:#4a5568;cursor:pointer;transition:all .25s;text-align:left;font-family:inherit;opacity:0;animation:fadeSlideUp .5s ease forwards;position:relative;overflow:hidden}
.tp-example-card::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:linear-gradient(180deg,#f97316,#c026d3);opacity:0;transition:opacity .2s;border-radius:14px 0 0 14px}
.tp-example-card:hover{border-color:rgba(232,84,46,0.3);box-shadow:0 4px 16px rgba(232,84,46,0.12);transform:translateY(-2px)}
.tp-example-card:hover::before{opacity:1}

.tp-result-card{margin-top:1.5rem;background:rgba(255,255,255,0.75);backdrop-filter:blur(16px);border:1px solid rgba(0,0,0,0.08);border-radius:20px;padding:1.8rem;box-shadow:0 4px 24px rgba(0,0,0,0.04);animation:slideUp .45s cubic-bezier(.21,1.02,.55,1);position:relative;overflow:hidden}
.tp-result-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,#f97316,#ef4444,#c026d3)}
@keyframes slideUp{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}
@keyframes fadeSlideUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
.tp-answer-header{display:flex;align-items:center;gap:.6rem;margin-bottom:.75rem}
.tp-answer-header h2{font-size:1rem;font-weight:700;color:#1a1a1a}
.tp-mode-badge{padding:.2rem .7rem;font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.04em;background:linear-gradient(135deg,#f97316,#ef4444,#c026d3);color:white;border-radius:999px}
.tp-answer-text{line-height:1.75;font-size:.95rem;color:#4a5568;white-space:pre-wrap}
.tp-sources-section{margin-top:1.5rem;padding-top:1.2rem;border-top:1px solid rgba(0,0,0,0.08)}
.tp-sources-section h3{font-size:.82rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#718096;margin-bottom:.7rem}
.tp-sources-list{list-style:none;display:flex;flex-direction:column;gap:.45rem}
.tp-source-item{display:flex;align-items:center;gap:.6rem;padding:.6rem .85rem;background:#fff;border:1px solid rgba(0,0,0,0.08);border-radius:12px;font-size:.85rem;transition:all .25s;opacity:0;animation:fadeSlideUp .4s ease forwards}
.tp-source-item:hover{box-shadow:0 4px 16px rgba(0,0,0,0.07);transform:translateX(4px)}
.tp-source-badge{display:inline-block;padding:.2rem .6rem;font-size:.65rem;font-weight:700;color:white;border-radius:6px;flex-shrink:0;text-transform:uppercase;letter-spacing:.03em}
.tp-source-title{color:#1a1a1a;text-decoration:none;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500;transition:color .2s}
.tp-source-title:hover{color:#e8542e;text-decoration:underline}
.tp-source-score{color:#718096;font-size:.78rem;font-weight:600;flex-shrink:0}
.tp-footer{position:relative;z-index:2;text-align:center;margin-top:3rem;padding-top:1.5rem;border-top:1px solid rgba(0,0,0,0.06)}
.tp-team{display:flex;justify-content:center;gap:2rem;flex-wrap:wrap}
.tp-team-member{font-size:.82rem;font-weight:600;color:#4a5568}
.tp-course{margin-top:.5rem;font-size:.75rem;font-weight:500;text-transform:uppercase;letter-spacing:.08em;color:#718096}

/* ═══ DASHBOARD ═══ */
.tp-db{position:relative;min-height:100vh;overflow-x:hidden}
.tp-db-nav{position:sticky;top:3px;z-index:200;display:flex;align-items:center;justify-content:space-between;padding:1rem 3rem;background:rgba(220,232,210,0.78);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);border-bottom:1px solid rgba(0,0,0,0.06)}
.tp-db-nav-brand{font-family:"Playfair Display",Georgia,serif;font-size:1.5rem;font-weight:700;color:#1a1a1a}
.tp-pill-btn{padding:.55rem 1.35rem;background:linear-gradient(135deg,#f97316,#ef4444,#c026d3);color:#fff;border:none;border-radius:14px;font-size:.88rem;font-weight:600;font-family:inherit;cursor:pointer;transition:all .25s;box-shadow:0 2px 12px rgba(239,68,68,0.2);position:relative;overflow:hidden}
.tp-pill-btn::after{content:'';position:absolute;inset:0;background:linear-gradient(135deg,rgba(255,255,255,0.2),transparent);opacity:0;transition:opacity .2s}
.tp-pill-btn:hover{transform:translateY(-2px) scale(1.03);box-shadow:0 6px 28px rgba(239,68,68,0.35)}
.tp-pill-btn:hover::after{opacity:1}
.tp-pill-btn.large{padding:.85rem 2rem;font-size:1rem;border-radius:16px}
.tp-ghost-btn{display:inline-block;padding:.85rem 2rem;background:rgba(255,255,255,0.6);color:#4a5568;border:1.5px solid rgba(0,0,0,0.1);border-radius:16px;font-size:1rem;font-weight:500;font-family:inherit;cursor:pointer;text-decoration:none;transition:all .25s;backdrop-filter:blur(8px)}
.tp-ghost-btn:hover{border-color:#e8542e;color:#e8542e;background:rgba(255,255,255,0.8);transform:translateY(-1px);box-shadow:0 4px 16px rgba(232,84,46,0.1)}

.tp-db-hero{position:relative;z-index:2;min-height:80vh;display:flex;align-items:center;justify-content:center;padding:5rem 2rem 4rem;text-align:center}
.tp-db-hero-content{max-width:800px}
.tp-eyebrow{font-size:.8rem;font-weight:600;text-transform:uppercase;letter-spacing:.1em;color:#718096;margin-bottom:1.2rem}
.tp-db-hero-title{font-family:"Playfair Display",Georgia,serif;font-style:italic;font-size:clamp(2.4rem,5.5vw,4.5rem);font-weight:700;line-height:1.1;margin-bottom:1.4rem;background:linear-gradient(135deg,#1a1a1a 0%,#4a5568 35%,#1a1a1a 70%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.tp-db-hero-desc{font-size:1rem;line-height:1.8;color:#4a5568;max-width:600px;margin:0 auto 2.5rem}
.tp-db-hero-actions{display:flex;gap:1rem;justify-content:center;flex-wrap:wrap}

.tp-db-section{position:relative;z-index:2;max-width:900px;margin:0 auto;padding:4rem 2rem;border-top:1px solid rgba(0,0,0,0.06)}
.tp-db-section-title{font-family:"Playfair Display",Georgia,serif;font-size:clamp(1.6rem,3vw,2.2rem);font-weight:700;text-align:center;color:#1a1a1a;margin-bottom:.6rem}
.tp-db-section-sub{text-align:center;color:#718096;font-size:.9rem;margin-bottom:2.5rem;max-width:520px;margin-inline:auto;line-height:1.6}

.tp-team-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:1rem}
.tp-team-card{background:rgba(255,255,255,0.75);backdrop-filter:blur(14px);border:1px solid rgba(0,0,0,0.08);border-radius:16px;padding:1rem 1.15rem;box-shadow:0 2px 12px rgba(0,0,0,0.05);transition:all .3s;position:relative;overflow:hidden}
.tp-team-card::before{content:'';position:absolute;bottom:0;left:0;right:0;height:3px;background:linear-gradient(90deg,#f97316,#ef4444,#c026d3);opacity:0;transition:opacity .3s}
.tp-team-card:hover{box-shadow:0 8px 28px rgba(0,0,0,0.08);transform:translateY(-3px)}
.tp-team-card:hover::before{opacity:1}
.tp-team-card-name{font-size:.92rem;font-weight:700;color:#1a1a1a}
.tp-team-card-id{margin-top:.25rem;font-size:.78rem;color:#718096;font-weight:600;letter-spacing:.03em}

.tp-pipeline{display:flex;align-items:flex-start;justify-content:center;flex-wrap:wrap}
.tp-step-wrap{display:flex;align-items:flex-start}
.tp-step{display:flex;flex-direction:column;align-items:center;text-align:center;width:130px;padding:0 .4rem}
.tp-step-icon-wrap{width:64px;height:64px;border-radius:18px;background:rgba(255,255,255,0.75);border:1px solid rgba(0,0,0,0.08);backdrop-filter:blur(12px);display:flex;align-items:center;justify-content:center;margin-bottom:.75rem;box-shadow:0 2px 12px rgba(0,0,0,0.06);transition:all .3s;position:relative;overflow:hidden}
.tp-step-icon-wrap::before{content:'';position:absolute;inset:0;background:linear-gradient(135deg,rgba(249,115,22,0.08),rgba(192,38,211,0.08));opacity:0;transition:opacity .3s}
.tp-step-icon-wrap:hover{transform:translateY(-4px) scale(1.06);box-shadow:0 8px 28px rgba(0,0,0,0.1)}
.tp-step-icon-wrap:hover::before{opacity:1}
.tp-step-icon{font-size:1.7rem;line-height:1}
.tp-step-label{font-size:.78rem;font-weight:700;color:#1a1a1a;margin-bottom:.3rem}
.tp-step-desc{font-size:.68rem;color:#718096;line-height:1.45}
.tp-step-arrow{font-size:1.1rem;color:rgba(0,0,0,0.2);padding:0 .1rem;margin-top:20px;flex-shrink:0;animation:arrowPulse 2s ease-in-out infinite}
@keyframes arrowPulse{0%,100%{opacity:.2;transform:translateX(0)}50%{opacity:.5;transform:translateX(4px)}}

/* Glass cards with glow variant */
.tp-db-card{background:rgba(255,255,255,0.75);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);border:1px solid rgba(0,0,0,0.08);border-radius:20px;padding:1.8rem;margin-bottom:1.2rem;box-shadow:0 4px 24px rgba(0,0,0,0.04);transition:all .3s}
.tp-db-card:hover{box-shadow:0 8px 36px rgba(0,0,0,0.07);transform:translateY(-1px)}
.tp-glow-card{position:relative}
.tp-glow-card::before{content:'';position:absolute;inset:-1px;border-radius:21px;background:linear-gradient(135deg,rgba(249,115,22,0.2),rgba(239,68,68,0.15),rgba(192,38,211,0.2));z-index:-1;filter:blur(8px);opacity:0;transition:opacity .4s}
.tp-glow-card:hover::before{opacity:1}
.tp-db-card-title{font-size:.95rem;font-weight:700;color:#1a1a1a;margin-bottom:.4rem}
.tp-db-card-sub{font-size:.78rem;color:#718096;margin-bottom:1.3rem;font-family:"Courier New",monospace}
.tp-legend{display:flex;gap:1.4rem;align-items:center;font-size:.8rem;color:#4a5568;margin-bottom:1.4rem}
.tp-dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:.3rem;vertical-align:middle}
.tp-note{margin-top:1rem;font-size:.75rem;color:#718096;font-style:italic;line-height:1.6}

/* Insight explorer */
.tp-insight-toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:.65rem}
.tp-insight-toolbar-title{font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;color:#718096;font-weight:700}
.tp-insight-toolbar-count{font-size:.72rem;font-weight:700;color:#4a5568;background:rgba(255,255,255,0.62);border:1px solid rgba(0,0,0,0.08);border-radius:999px;padding:.2rem .6rem}
.tp-live-ribbon{display:inline-flex;align-items:center;gap:.5rem;font-size:.7rem;font-weight:700;letter-spacing:.03em;color:#5b6470;padding:.26rem .62rem;border-radius:999px;border:1px solid rgba(0,0,0,0.08);background:rgba(255,255,255,0.64);margin-bottom:.75rem}
.tp-live-dot{width:8px;height:8px;border-radius:999px;background:#22c55e;animation:livePulse 1.8s ease-out infinite}
.tp-live-sep{opacity:.55}
@keyframes livePulse{0%{box-shadow:0 0 0 0 rgba(34,197,94,0.55)}100%{box-shadow:0 0 0 10px rgba(34,197,94,0)}}
.tp-source-select-row{display:flex;gap:.55rem;flex-wrap:wrap;margin-bottom:1rem}
.tp-toggle-btn{border:1px solid rgba(0,0,0,0.12);background:rgba(255,255,255,0.72);color:#4a5568;border-radius:999px;padding:.45rem .9rem;font-size:.76rem;font-weight:600;cursor:pointer;transition:all .25s;font-family:inherit}
.tp-toggle-btn:hover{border-color:rgba(232,84,46,0.35);color:#e8542e;transform:translateY(-1px)}
.tp-toggle-btn:active{transform:scale(.96)}
.tp-toggle-btn.active{background:linear-gradient(135deg,#f97316,#ef4444,#c026d3);color:#fff;border-color:transparent;box-shadow:0 2px 10px rgba(239,68,68,0.2)}
.tp-insight-layout{display:grid;grid-template-columns:1.2fr 1fr;gap:.9rem}
.tp-featured-highlight{display:block;padding:1.2rem;border-radius:16px;background:linear-gradient(145deg,rgba(255,255,255,0.85),rgba(255,255,255,0.6));border:1px solid rgba(0,0,0,0.08);text-decoration:none;color:inherit;min-height:155px;position:relative;overflow:hidden;transition:all .3s}
.tp-featured-highlight::before{content:"";position:absolute;inset:-120% auto auto -40%;width:70%;height:260%;background:linear-gradient(120deg,rgba(255,255,255,0),rgba(255,255,255,0.5),rgba(255,255,255,0));transform:rotate(12deg);animation:cardSweep 5.4s ease-in-out infinite;pointer-events:none}
.tp-featured-highlight:hover{border-color:rgba(232,84,46,0.35);transform:translateY(-2px);box-shadow:0 12px 28px rgba(0,0,0,0.07)}
@keyframes cardSweep{0%,72%,100%{transform:translateX(-120%) rotate(12deg)}82%,92%{transform:translateX(240%) rotate(12deg)}}
.tp-featured-badge{display:inline-block;font-size:.66rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;padding:.18rem .55rem;border-radius:999px;background:linear-gradient(135deg,rgba(249,115,22,0.15),rgba(192,38,211,0.1));color:#b45309}
.tp-featured-title{margin-top:.65rem;margin-bottom:.45rem;font-family:"Playfair Display",Georgia,serif;font-size:1.2rem;line-height:1.32;color:#1a1a1a}
.tp-featured-meta{font-size:.78rem;color:#718096}
.tp-insight-list-side{display:flex;flex-direction:column;gap:.55rem}
.tp-highlight-item{display:flex;align-items:center;justify-content:space-between;gap:.8rem;padding:.7rem .8rem;border-radius:12px;background:rgba(255,255,255,0.5);border:1px solid rgba(0,0,0,0.06);color:inherit;text-decoration:none;opacity:0;transform:translateY(8px);animation:riseIn .55s ease forwards;transition:all .25s}
.tp-highlight-item:hover{border-color:rgba(232,84,46,0.35);background:rgba(255,255,255,0.75);transform:translateY(-1px)}
@keyframes riseIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
.tp-insight-key{font-size:.84rem;font-weight:700;color:#1a1a1a}
.tp-insight-meta{font-size:.75rem;color:#718096}
.tp-empty-state{display:flex;flex-direction:column;align-items:flex-start;gap:.55rem}
.tp-mini-btn{border:1px solid rgba(0,0,0,0.14);background:rgba(255,255,255,0.78);color:#4a5568;border-radius:999px;padding:.32rem .75rem;font-size:.72rem;font-weight:700;cursor:pointer;transition:all .2s;font-family:inherit}
.tp-mini-btn:hover{border-color:rgba(232,84,46,0.38);color:#e8542e}
.tp-source-strip{margin-top:1rem;display:flex;flex-wrap:wrap;gap:.45rem}
.tp-source-chip{display:inline-flex;align-items:center;padding:.25rem .6rem;border-radius:999px;background:rgba(255,255,255,0.72);border:1px solid rgba(0,0,0,0.1);font-size:.7rem;font-weight:600;color:#4a5568;transition:all .2s}
.tp-source-chip:hover{transform:translateY(-1px);border-color:rgba(232,84,46,0.35)}
.tp-source-chip:nth-child(odd){animation:chipDrift 3.8s ease-in-out infinite}
.tp-source-chip:nth-child(even){animation:chipDrift 4.4s ease-in-out infinite reverse}
@keyframes chipDrift{0%,100%{transform:translateY(0)}50%{transform:translateY(-2px)}}

/* Stats with animated numbers */
.tp-stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:1rem;margin-top:1.2rem}
.tp-stat-card{background:rgba(255,255,255,0.75);backdrop-filter:blur(16px);border:1px solid rgba(0,0,0,0.08);border-radius:20px;padding:1.6rem 1.2rem;text-align:center;box-shadow:0 2px 12px rgba(0,0,0,0.04);transition:all .3s;position:relative;overflow:hidden}
.tp-stat-card::after{content:'';position:absolute;bottom:0;left:0;right:0;height:3px;background:linear-gradient(90deg,#f97316,#ef4444,#c026d3);transform:scaleX(0);transition:transform .4s;transform-origin:left}
.tp-stat-card:hover{box-shadow:0 8px 28px rgba(0,0,0,0.08);transform:translateY(-3px)}
.tp-stat-card:hover::after{transform:scaleX(1)}
.tp-stat-num{font-family:"Playfair Display",Georgia,serif;font-size:2rem;font-weight:700;background:linear-gradient(135deg,#f97316,#ef4444,#c026d3);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;line-height:1.1;margin-bottom:.45rem}
.tp-stat-label{font-size:.75rem;color:#718096;font-weight:600;text-transform:uppercase;letter-spacing:.05em}

.tp-cta-section{position:relative;z-index:2;text-align:center;padding:4.5rem 2rem;border-top:1px solid rgba(0,0,0,0.06)}
.tp-cta-title{font-family:"Playfair Display",Georgia,serif;font-style:italic;font-size:clamp(1.8rem,3.5vw,2.6rem);font-weight:700;color:#1a1a1a;margin-bottom:.7rem}
.tp-cta-desc{color:#718096;font-size:.95rem;margin-bottom:2rem}
.tp-db-footer{position:relative;z-index:2;text-align:center;padding:1.8rem 2rem;border-top:1px solid rgba(0,0,0,0.06)}
.tp-db-footer-team{display:flex;justify-content:center;gap:2rem;flex-wrap:wrap;margin-bottom:.5rem;font-size:.82rem;font-weight:600;color:#4a5568}
.tp-db-footer-course{font-size:.72rem;text-transform:uppercase;letter-spacing:.08em;color:#718096}

@media(max-width:768px){.tp-db-nav{padding:.9rem 1.2rem}.tp-pipeline{overflow-x:auto;flex-wrap:nowrap;justify-content:flex-start;padding-bottom:1rem}.tp-step{width:110px}.tp-db-card{padding:1.2rem;border-radius:16px}.tp-insight-layout{grid-template-columns:1fr}.tp-db-footer-team{flex-direction:column;gap:.3rem}.tp-blob-1{width:400px;height:400px}.tp-blob-2{width:300px;height:300px}.tp-cd2,.tp-cd3{display:none}.tp-float-icon{display:none}}
@media(max-width:640px){.tp-app{padding:1.5rem 1rem 1rem}.tp-brand{font-size:2.4rem}.tp-tagline{font-size:.82rem}.tp-search-card,.tp-result-card{padding:1.2rem;border-radius:16px}.tp-team{flex-direction:column;gap:.3rem}.tp-db-section{padding:3rem 1rem}.tp-stats-grid{grid-template-columns:repeat(2,1fr)}}

.tp-page-anim{animation:pageIn .4s cubic-bezier(.21,1.02,.55,1)}
@keyframes pageIn{from{opacity:0}to{opacity:1}}
    `}</style>
    <div className="tp-page-anim" key={page}>
      {page==="dashboard"?<DashboardPage onGoToApp={()=>setPage("main")}/>:<SearchPage onGoToDashboard={()=>setPage("dashboard")}/>}
    </div>
  </>);
}


