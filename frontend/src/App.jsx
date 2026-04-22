import { useState, useEffect, useRef, useCallback } from "react";
import "./App.css";
import Dashboard from "./Dashboard";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

const EXAMPLE_QUERIES = [
  "How does retrieval-augmented generation improve LLM accuracy?",
  "What are the benefits of hybrid search combining BM25 and vector retrieval?",
  "How do cross-encoder rerankers improve search relevance?",
  "What is the role of pgvector in production RAG systems?",
  "How does weighted reciprocal rank fusion work in hybrid retrieval?",
  "What techniques reduce hallucination in LLM-generated answers?",
];

const SOURCE_BADGES = {
  arxiv: { label: "ArXiv", bg: "linear-gradient(135deg, #b31b1b, #e74c3c)" },
  hn: { label: "HN", bg: "linear-gradient(135deg, #ff6600, #ff9248)" },
  devto: { label: "DEV.to", bg: "linear-gradient(135deg, #3b49df, #6366f1)" },
  github: { label: "GitHub", bg: "linear-gradient(135deg, #24292e, #586069)" },
  rss: { label: "RSS", bg: "linear-gradient(135deg, #ee802f, #f5a623)" },
};

const LOADING_STAGES = [
  "Fetching relevant documents...",
  "Ranking evidence...",
  "Generating grounded answer...",
];

function waitWithAbort(ms, signal) {
  return new Promise((resolve, reject) => {
    const timeoutId = setTimeout(resolve, ms);
    if (!signal) return;
    const onAbort = () => {
      clearTimeout(timeoutId);
      const abortError = new Error("Request aborted");
      abortError.name = "AbortError";
      reject(abortError);
    };
    signal.addEventListener("abort", onAbort, { once: true });
    setTimeout(() => signal.removeEventListener("abort", onAbort), ms + 10);
  });
}

/* -- localStorage helpers -- */
function loadHistory() {
  try { return JSON.parse(localStorage.getItem("tp_history") || "[]"); } catch { return []; }
}
function saveHistory(h) {
  try { localStorage.setItem("tp_history", JSON.stringify(h.slice(0, 50))); } catch { /* noop */ }
}

/* -- Aurora mesh gradient background -- */
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

/* -- Floating Tech Icons -- */
function FloatingTechIcons() {
  const icons = [
    { d: "M9 3v2m6-2v2M9 19v2m6-2v2M3 9h2m-2 6h2m14-6h2m-2 6h2M7 7h10v10H7z", x: "8%", y: "15%", delay: "0s", dur: "14s", size: 28 },
    { d: "M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z", x: "85%", y: "22%", delay: "2s", dur: "18s", size: 32 },
    { d: "M16 18l6-6-6-6M8 6l-6 6 6 6", x: "12%", y: "65%", delay: "4s", dur: "16s", size: 24 },
    { d: "M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4", x: "90%", y: "70%", delay: "1s", dur: "15s", size: 26 },
    { d: "M13 10V3L4 14h7v7l9-11h-7z", x: "65%", y: "85%", delay: "1.5s", dur: "13s", size: 26 },
    { d: "M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9", x: "38%", y: "40%", delay: "3.5s", dur: "21s", size: 20 },
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

/* -- Inline SVG Icons -- */
const IconSend = () => <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>;
const IconStop = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>;
const IconRegen = () => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>;
const IconCompare = () => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="3" width="8" height="18" rx="1"/><rect x="14" y="3" width="8" height="18" rx="1"/></svg>;
const IconNew = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>;
const IconClear = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>;
const IconExternal = () => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>;
const IconSidebar = () => <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/></svg>;
const IconSearch = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>;
const IconDash = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>;
const IconBolt = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>;
const IconLab = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 3h6v7l5 8a2 2 0 01-1.7 3H5.7A2 2 0 014 18l5-8V3z"/><line x1="9" y1="3" x2="15" y2="3"/></svg>;

/* -- Source card with expandable snippet -- */
function SourceCard({ s, i }) {
  const badge = SOURCE_BADGES[s.source] || { label: s.source, bg: "#777" };
  const scorePct = (s.score * 100).toFixed(1);
  return (
    <li className="source-item" style={{ animationDelay: `${0.1 + i * 0.06}s` }}>
      <div className="source-item-main">
        <span className="source-badge" style={{ background: badge.bg }}>{badge.label}</span>
        <div className="source-info">
          <span className="source-title-text">{s.title}</span>
          {s.published_at && <span className="source-date">{new Date(s.published_at).toLocaleDateString()}</span>}
        </div>
        <div className="source-right">
          <div className="source-score-wrap">
            <div className="source-score-bar"><div className="source-score-fill" style={{ width: `${Math.min(scorePct, 100)}%` }} /></div>
            <span className="source-score">{scorePct}%</span>
          </div>
          <div className="source-btns">
            <a href={s.url} target="_blank" rel="noopener noreferrer" className="source-tiny-btn" aria-label="Open source" title="Open original"><IconExternal /></a>
          </div>
        </div>
      </div>
    </li>
  );
}

/* -- Compare panel overlay -- */
function ComparePanel({ query, resultA, resultB, onClose }) {
  return (
    <div className="compare-overlay" onClick={onClose}>
      <div className="compare-panel" onClick={e => e.stopPropagation()}>
        <div className="compare-header">
          <h2>Compare Modes</h2>
          <span className="compare-query">&ldquo;{query}&rdquo;</span>
          <button className="compare-close" onClick={onClose} aria-label="Close"><IconClear /></button>
        </div>
        <div className="compare-grid">
          {[resultA, resultB].map((r, idx) => (
            <div key={idx} className="compare-col">
              <div className="compare-col-header">
                <span className={`mode-badge ${idx === 0 ? "baseline" : "hybrid"}`}>{r ? r.mode : (idx === 0 ? "baseline" : "hybrid")}</span>
                {r && <span className="compare-src-count">{r.sources?.length || 0} sources</span>}
              </div>
              {r ? (
                <>
                  <p className="compare-answer">{r.answer}</p>
                  {r.sources?.length > 0 && (
                    <div className="compare-sources">
                      {r.sources.map((s, i) => {
                        const b = SOURCE_BADGES[s.source] || { label: s.source, bg: "#777" };
                        return (
                          <div key={i} className="compare-source-row">
                            <span className="source-badge small" style={{ background: b.bg }}>{b.label}</span>
                            <span className="compare-source-title">{s.title}</span>
                            <span className="source-score">{(s.score * 100).toFixed(1)}%</span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </>
              ) : (
                <div className="compare-loading"><div className="typing-dots"><span /><span /><span /></div><p>Loading...</p></div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* === MAIN APP === */
export default function App() {
  const [page, setPage] = useState("dashboard");
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState("hybrid");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingStage, setLoadingStage] = useState(0);
  const [error, setError] = useState(null);
  const [cancelled, setCancelled] = useState(false);
  const [retrying503, setRetrying503] = useState(false);
  const [heroIn, setHeroIn] = useState(false);
  const [history, setHistory] = useState(loadHistory);
  const [sidebarOpen, setSidebarOpen] = useState(() => {
    try { return localStorage.getItem("tp_sidebar") !== "false"; } catch { return true; }
  });
  const [comparing, setComparing] = useState(false);
  const [compareResults, setCompareResults] = useState([null, null]);

  const abortRef = useRef(null);
  const stageTimerRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => { const t = setTimeout(() => setHeroIn(true), 60); return () => clearTimeout(t); }, []);

  /* Persist sidebar state */
  useEffect(() => { try { localStorage.setItem("tp_sidebar", sidebarOpen); } catch { /* noop */ } }, [sidebarOpen]);

  /* Keyboard shortcuts */
  useEffect(() => {
    function onKey(e) {
      if (e.key === "Escape") {
        if (comparing) { setComparing(false); return; }
        if (loading) { handleStop(); return; }
      }
      if ((e.ctrlKey || e.metaKey) && e.key === ".") {
        e.preventDefault();
        setSidebarOpen(prev => !prev);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [comparing, loading]);

  function clearStageTimer() { if (stageTimerRef.current) { clearInterval(stageTimerRef.current); stageTimerRef.current = null; } }

  function startStageTimer() {
    setLoadingStage(0);
    clearStageTimer();
    let s = 0;
    stageTimerRef.current = setInterval(() => { s++; if (s < LOADING_STAGES.length) setLoadingStage(s); else clearStageTimer(); }, 2200);
  }

  async function doFetch(q, m, signal) {
    async function fetchAsk() {
      return fetch(`${API_BASE}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q.trim(), mode: m }),
        signal,
      });
    }

    let res;
    try {
      res = await fetchAsk();
      if (res.status === 503) {
        setRetrying503(true);
        await waitWithAbort(1200, signal);
        res = await fetchAsk();
      }
    } catch (err) {
      if (err.name === "AbortError") throw err;
      throw new Error("Unable to reach the API. Check your network connection or try again shortly.");
    } finally {
      setRetrying503(false);
    }
    if (!res.ok) {
      let detail = null;
      try {
        const body = await res.json();
        if (body && typeof body.detail === "string") detail = body.detail;
        else if (body && Array.isArray(body.detail) && body.detail.length > 0) detail = body.detail.map(e => e.msg || e.message || JSON.stringify(e)).join("; ");
        else if (body && typeof body.answer === "string") detail = body.answer;
      } catch { /* body was not JSON */ }

      if (res.status === 429) {
        throw new Error(detail || "Rate limit exceeded. Please wait a moment and try again.");
      }
      if (res.status >= 500) {
        throw new Error(detail || `The server is having trouble right now (HTTP ${res.status}). Please try again in a moment.`);
      }
      throw new Error(detail || `Request failed (HTTP ${res.status}). Please try again.`);
    }
    return res.json();
  }

  const handleSubmit = useCallback(async (e) => {
    if (e) e.preventDefault();
    if (!query.trim() || loading) return;

    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError(null);
    setResult(null);
    setCancelled(false);
    setRetrying503(false);
    startStageTimer();

    try {
      const data = await doFetch(query, mode, controller.signal);
      setResult(data);
      const entry = { id: Date.now(), query: query.trim(), mode, result: data, ts: new Date().toISOString(), status: "success" };
      const updated = [entry, ...history.filter(h => h.query !== query.trim())].slice(0, 50);
      setHistory(updated);
      saveHistory(updated);
    } catch (err) {
      if (err.name === "AbortError") {
        setCancelled(true);
      } else {
        setError(err.message);
        const entry = { id: Date.now(), query: query.trim(), mode, result: null, ts: new Date().toISOString(), status: "failed" };
        const updated = [entry, ...history].slice(0, 50);
        setHistory(updated);
        saveHistory(updated);
      }
    } finally {
      setLoading(false);
      clearStageTimer();
      abortRef.current = null;
    }
  }, [query, mode, loading, history]);

  function handleStop() { if (abortRef.current) abortRef.current.abort(); }

  function handleNewChat() {
    setQuery(""); setResult(null); setError(null); setCancelled(false); setComparing(false);
    setPage("main");
    if (loading) handleStop();
    inputRef.current?.focus();
  }

  function handleRegenerate() {
    if (!query.trim()) return;
    setResult(null); setError(null); setCancelled(false);
    setTimeout(() => { document.getElementById("search-form")?.requestSubmit(); }, 50);
  }

  async function handleCompare() {
    if (!query.trim()) return;
    setComparing(true);
    setCompareResults([null, null]);
    const controller = new AbortController();
    try {
      const [baseline, hybrid] = await Promise.all([
        doFetch(query, "baseline", controller.signal),
        doFetch(query, "hybrid", controller.signal),
      ]);
      setCompareResults([baseline, hybrid]);
    } catch {
      setCompareResults([
        { answer: "Failed to load", mode: "baseline", sources: [] },
        { answer: "Failed to load", mode: "hybrid", sources: [] },
      ]);
    }
  }

  function handleHistoryClick(h) {
    setQuery(h.query); setMode(h.mode); setPage("main");
    setError(null); setCancelled(false);
    setResult(h.result || null);
  }

  function handleClearHistory() { setHistory([]); saveHistory([]); }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (query.trim() && !loading) handleSubmit(); }
  }

  const isAbstained = result && (!result.answer || result.answer.toLowerCase().includes("could not") || result.answer.toLowerCase().includes("insufficient") || result.answer.toLowerCase().includes("no relevant") || (result.sources?.length === 0));
  const hasConversation = !!(result || loading || error || cancelled);

  return (
    <div className="app-shell">
      <AuroraBg />
      <FloatingTechIcons />

      {/* -- Sidebar -- */}
      <aside className={`sidebar ${sidebarOpen ? "open" : ""}`}>
        <div className="sb-top">
          <button className="sb-brand" onClick={handleNewChat} title="TechPulse Home">
            <span className="sb-logo">&diams;</span>
            <span className="sb-brand-text">TechPulse</span>
          </button>
          <button className="sb-toggle" onClick={() => setSidebarOpen(false)} title="Close sidebar (Ctrl+.)">
            <IconSidebar />
          </button>
        </div>

        <button className="sb-new-chat" onClick={handleNewChat}>
          <IconNew /> New chat
        </button>

        <nav className="sb-nav">
          <button className={`sb-nav-item ${page === "main" ? "active" : ""}`} onClick={() => setPage("main")}>
            <IconSearch /> Search
          </button>
          <button className={`sb-nav-item ${page === "dashboard" ? "active" : ""}`} onClick={() => setPage("dashboard")}>
            <IconDash /> Home
          </button>
        </nav>

        {history.length > 0 && (
          <div className="sb-recents">
            <div className="sb-section-head">
              <span className="sb-section-label">Recents</span>
              <button className="sb-clear" onClick={handleClearHistory}>Clear</button>
            </div>
            <ul className="sb-list">
              {history.slice(0, 20).map(h => (
                <li key={h.id} className="sb-item">
                  <button className="sb-item-btn" onClick={() => handleHistoryClick(h)} title={h.query}>{h.query}</button>
                </li>
              ))}
            </ul>
          </div>
        )}

      </aside>

      {/* Sidebar toggle when closed */}
      {!sidebarOpen && (
        <button className="sb-open-btn" onClick={() => setSidebarOpen(true)} title="Open sidebar (Ctrl+.)">
          <IconSidebar />
        </button>
      )}

      {/* -- Main Area -- */}
      <div className={`main-area ${sidebarOpen ? "with-sidebar" : ""}`}>
        {page === "dashboard" ? (
          <div className="page-anim dash-wrap">
            <Dashboard onGoToApp={() => setPage("main")} />
          </div>
        ) : (
          <div className="chat-page">
            {/* Center stage - vertically centers when no results */}
            <div className={`center-stage ${hasConversation ? "pushed" : ""}`}>
              {/* Greeting */}
              {!hasConversation && (
                <div className="greeting" style={{ opacity: heroIn ? 1 : 0, transform: heroIn ? "none" : "translateY(16px)", transition: "all .6s .1s cubic-bezier(.21,1.02,.55,1)" }}>
                  <h1 className="greeting-text"><span className="greeting-star">&diams;</span> TechPulse</h1>
                  <p className="greeting-sub">What would you like to explore?</p>
                  <p className="greeting-tagline">Real-Time Hybrid RAG for Emerging Technology Intelligence</p>
                </div>
              )}

              {/* Input card */}
              <form id="search-form" className="input-card" onSubmit={handleSubmit}>
                <div className="input-card-body">
                  <input
                    ref={inputRef}
                    className="chat-input"
                    type="text"
                    placeholder="Ask about emerging technology..."
                    value={query}
                    onChange={e => setQuery(e.target.value)}
                    onKeyDown={handleKeyDown}
                    disabled={loading}
                    maxLength={500}
                  />
                  {query && !loading && (
                    <button type="button" className="input-clear" onClick={() => { setQuery(""); inputRef.current?.focus(); }} title="Clear">
                      <IconClear />
                    </button>
                  )}
                </div>
                <div className="input-card-foot">
                  <div className="mode-chips">
                    <button type="button" className={`mode-chip ${mode === "baseline" ? "active" : ""}`} onClick={() => setMode("baseline")} disabled={loading}>
                      <IconBolt /> Baseline
                    </button>
                    <button type="button" className={`mode-chip ${mode === "hybrid" ? "active" : ""}`} onClick={() => setMode("hybrid")} disabled={loading}>
                      <IconLab /> Hybrid
                    </button>
                  </div>
                  <div className="input-actions">
                    {query.trim() && !loading && <span className="char-count">{query.length}/500</span>}
                    {loading ? (
                      <button type="button" className="send-btn stop" onClick={handleStop} title="Stop (Esc)"><IconStop /></button>
                    ) : (
                      <button type="submit" className="send-btn" disabled={!query.trim()} title="Send"><IconSend /></button>
                    )}
                  </div>
                </div>
              </form>

              {/* Example cards */}
              {!hasConversation && (
                <div className="example-grid" style={{ opacity: heroIn ? 1 : 0, transition: "opacity .6s .3s" }}>
                  {EXAMPLE_QUERIES.map((eq, i) => (
                    <button key={i} className="example-card" onClick={() => { setQuery(eq); inputRef.current?.focus(); }}>{eq}</button>
                  ))}
                </div>
              )}
            </div>

            {/* -- Results area -- */}
            {cancelled && !loading && !result && !error && (
              <div className="results-area">
                <div className="status-card cancelled">
                  <p>Request cancelled.</p>
                  <button className="retry-btn" onClick={handleSubmit}>Retry</button>
                </div>
              </div>
            )}

            {error && (
              <div className="results-area">
                <div className="error-card enhanced">
                  <div className="error-header-row">
                    <strong>Something went wrong</strong>
                    <span className="error-detail">{error}</span>
                  </div>
                  <div className="error-suggestions">
                    <p>Try:</p>
                    <ul>
                      <li>Checking your network connection</li>
                      <li>Narrowing the topic with specific keywords</li>
                      <li>Switching between Baseline and Hybrid modes</li>
                    </ul>
                  </div>
                  <button className="retry-btn" onClick={handleSubmit}>Retry</button>
                </div>
              </div>
            )}

            {loading && (
              <div className="results-area">
                <div className="loading-card">
                  <div className="loading-stages">
                    {LOADING_STAGES.map((stage, i) => (
                      <div key={i} className={`loading-stage ${i < loadingStage ? "done" : ""} ${i === loadingStage ? "active" : ""}`}>
                        <div className="stage-dot">{i < loadingStage ? "\u2713" : i === loadingStage ? <span className="spinner-sm" /> : (i + 1)}</div>
                        <span>{stage}</span>
                      </div>
                    ))}
                  </div>
                  {retrying503 && <p className="loading-retry-note">Temporary backend issue detected. Auto-retrying now...</p>}
                  <p className="loading-hint">Press <kbd>Esc</kbd> to cancel</p>
                </div>
              </div>
            )}

            {result && (
              <div className="results-area">
                <div className="result-card">
                  <div className="answer-header">
                    <div className="answer-header-left">
                      <h2>Answer</h2>
                      <span className={`mode-badge ${result.mode}`}>{result.mode}</span>
                      {result.sources?.length > 0 && <span className="answer-grounding">Grounded in {result.sources.length} sources</span>}
                    </div>
                    <div className="answer-actions">
                      <button className="action-btn" onClick={handleRegenerate} title="Regenerate"><IconRegen />Regenerate</button>
                      <button className="action-btn compare" onClick={handleCompare} title="Compare Baseline vs Hybrid"><IconCompare />Compare</button>
                    </div>
                  </div>

                  {isAbstained && (
                    <div className="abstention-hint">
                      <p><strong>Low confidence.</strong> Not enough strong evidence was found.</p>
                      <p>Try narrowing the topic or switching to {mode === "baseline" ? "Hybrid" : "Baseline"} mode.</p>
                    </div>
                  )}

                  <div className="answer-text">{result.answer}</div>

                  {result.llm_error && (
                    <div className="error-card" style={{ marginTop: "0.5rem", fontSize: "0.85rem" }}>LLM backend error: {result.llm_error}</div>
                  )}

                  {result.sources?.length > 0 && (
                    <div className="sources-section">
                      <h3>Sources ({result.sources.length})</h3>
                      <ul className="sources-list">
                        {result.sources.map((s, i) => <SourceCard key={i} s={s} i={i} />)}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            )}

            <footer className="chat-footer">
              <div className="footer-team">
                <p>Aye Khin Khin Hpone (Yolanda Lim) &middot; st125970</p>
                <p>Dechathon Niamsa-Ard &middot; st126235</p>
              </div>
              <p className="footer-course">AT82.9002 Selected Topics: Data Engineering &amp; MLOps</p>
            </footer>
          </div>
        )}
      </div>

      {/* Compare overlay */}
      {comparing && <ComparePanel query={query} resultA={compareResults[0]} resultB={compareResults[1]} onClose={() => setComparing(false)} />}
    </div>
  );
}
