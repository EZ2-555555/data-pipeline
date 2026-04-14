import { useState, useEffect } from "react";
import "./App.css";
import Dashboard from "./Dashboard";

const API_BASE = import.meta.env.VITE_API_URL || "/api";

const EXAMPLE_QUERIES = [
  "What are the latest trends in quantum computing?",
  "How is Rust being adopted in systems programming?",
  "What recent advances have been made in LLM fine-tuning?",
  "What are emerging best practices for MLOps pipelines?",
  "How are vector databases used in production RAG systems?",
  "What new techniques improve cross-encoder reranking?",
];

const SOURCE_BADGES = {
  arxiv: { label: "ArXiv", bg: "linear-gradient(135deg, #b31b1b, #e74c3c)" },
  hn: { label: "HN", bg: "linear-gradient(135deg, #ff6600, #ff9248)" },
  devto: { label: "DEV.to", bg: "linear-gradient(135deg, #3b49df, #6366f1)" },
  github: { label: "GitHub", bg: "linear-gradient(135deg, #24292e, #586069)" },
  rss: { label: "RSS", bg: "linear-gradient(135deg, #ee802f, #f5a623)" },
};

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

/* ── Floating Tech Icons (SVG-based) ── */
function FloatingTechIcons() {
  const icons = [
    { d: "M9 3v2m6-2v2M9 19v2m6-2v2M3 9h2m-2 6h2m14-6h2m-2 6h2M7 7h10v10H7z", x: "8%", y: "15%", delay: "0s", dur: "14s", size: 28 },
    { d: "M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z", x: "85%", y: "22%", delay: "2s", dur: "18s", size: 32 },
    { d: "M16 18l6-6-6-6M8 6l-6 6 6 6", x: "12%", y: "65%", delay: "4s", dur: "16s", size: 24 },
    { d: "M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4", x: "90%", y: "70%", delay: "1s", dur: "15s", size: 26 },
    { d: "M12 2a4 4 0 014 4c0 1.1-.45 2.1-1.17 2.83L12 12l-2.83-3.17A4 4 0 0112 2zm-6 8a3 3 0 013 3v1l3 3-3 3v1a3 3 0 11-3-3v-1L3 14l3-3v-1zm12 0a3 3 0 00-3 3v1l-3 3 3 3v1a3 3 0 103-3v-1l3-3-3-3v-1z", x: "50%", y: "8%", delay: "3s", dur: "20s", size: 30 },
    { d: "M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.858 15.355-5.858 21.213 0", x: "78%", y: "45%", delay: "5s", dur: "17s", size: 22 },
    { d: "M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z", x: "25%", y: "82%", delay: "6s", dur: "19s", size: 24 },
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

export default function App() {
  const [page, setPage] = useState("dashboard");
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState("hybrid");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [heroIn, setHeroIn] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setHeroIn(true), 60);
    return () => clearTimeout(t);
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await fetch(`${API_BASE}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query.trim(), mode }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  if (page === "dashboard") {
    return (
      <div className="page-anim" key="dashboard">
        <Dashboard onGoToApp={() => setPage("main")} />
      </div>
    );
  }

  return (
    <div className="page-anim main-page" key="main">
      <div className="app">
        <AuroraBg />
        <FloatingTechIcons />

        <header className="header" style={{ opacity: heroIn ? 1 : 0, transform: heroIn ? "translateY(0)" : "translateY(20px)", transition: "all .7s .1s cubic-bezier(.21,1.02,.55,1)" }}>
          <h1 className="brand">TechPulse</h1>
          <p className="tagline">
            A Real-Time Hybrid RAG System for Emerging Technology Intelligence
          </p>
          <button className="about-btn" onClick={() => setPage("dashboard")}>
            About Project ↗
          </button>
        </header>

        <main className="main-content" style={{ opacity: heroIn ? 1 : 0, transform: heroIn ? "translateY(0)" : "translateY(24px)", transition: "all .7s .25s cubic-bezier(.21,1.02,.55,1)" }}>
          <form className="search-card" onSubmit={handleSubmit}>
            <label className="search-label" htmlFor="query-input">
              Ask about emerging technology
            </label>
            <div className="search-row">
              <input
                id="query-input"
                className="search-input"
                type="text"
                placeholder="e.g. What are the latest trends in quantum computing?"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                disabled={loading}
              />
              <button
                className="submit-btn"
                type="submit"
                disabled={loading || !query.trim()}
              >
                {loading ? (
                  <span className="spinner" />
                ) : (
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="5" y1="12" x2="19" y2="12" />
                    <polyline points="12 5 19 12 12 19" />
                  </svg>
                )}
              </button>
            </div>
            <div className="mode-toggle">
              <button
                type="button"
                className={`mode-btn ${mode === "baseline" ? "active" : ""}`}
                onClick={() => setMode("baseline")}
              >Baseline</button>
              <button
                type="button"
                className={`mode-btn ${mode === "hybrid" ? "active" : ""}`}
                onClick={() => setMode("hybrid")}
              >Hybrid</button>
            </div>
          </form>

          {error && <div className="error-card">Error: {error}</div>}

          {loading && (
            <div className="loading-indicator">
              <div className="typing-dots"><span /><span /><span /></div>
              <p>Searching sources &amp; generating answer...</p>
            </div>
          )}

          {!result && !loading && !error && (
            <div className="examples-section" style={{ opacity: heroIn ? 1 : 0, transition: "opacity .7s .5s" }}>
              <p className="examples-title">Try asking about:</p>
              <div className="examples-grid">
                {EXAMPLE_QUERIES.map((eq, i) => (
                  <button
                    key={i}
                    className="example-card"
                    onClick={() => setQuery(eq)}
                    style={{ animationDelay: `${0.4 + i * 0.08}s` }}
                  >{eq}</button>
                ))}
              </div>
            </div>
          )}

          {result && (
            <div className="result-card">
              <div className="answer-header">
                <h2>Answer</h2>
                <span className="mode-badge">{result.mode}</span>
              </div>
              <div className="answer-text">{result.answer}</div>

              {result.llm_error && (
                <div className="error-card" style={{ marginTop: "0.5rem", fontSize: "0.85rem" }}>
                  LLM backend error: {result.llm_error}
                </div>
              )}

              {result.sources?.length > 0 && (
                <div className="sources-section">
                  <h3>Sources ({result.sources.length})</h3>
                  <ul className="sources-list">
                    {result.sources.map((s, i) => {
                      const badge = SOURCE_BADGES[s.source] || { label: s.source, bg: "#777" };
                      return (
                        <li key={i} className="source-item" style={{ animationDelay: `${0.1 + i * 0.06}s` }}>
                          <span className="source-badge" style={{ background: badge.bg }}>
                            {badge.label}
                          </span>
                          <a href={s.url} target="_blank" rel="noopener noreferrer" className="source-title">
                            {s.title}
                          </a>
                          <span className="source-score">
                            {(s.score * 100).toFixed(1)}%
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
            </div>
          )}
        </main>

        <footer className="footer">
          <div className="team">
            <p className="team-member">Aye Khin Khin Hpone (Yolanda Lim) &middot; st125970</p>
            <p className="team-member">Dechathon Niamsa-Ard &middot; st126235</p>
          </div>
          <p className="course">AT82.9002 Selected Topics: Data Engineering &amp; MLOps</p>
        </footer>
      </div>
    </div>
  );
}
