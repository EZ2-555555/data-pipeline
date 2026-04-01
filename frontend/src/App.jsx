import { useState } from "react";
import "./App.css";
import Dashboard from "./Dashboard";

const API_BASE = import.meta.env.VITE_API_URL || "/api";

const EXAMPLE_QUERIES = [
  "What are the latest trends in quantum computing?",
  "How is Rust being adopted in systems programming?",
  "What recent advances have been made in LLM fine-tuning?",
  "What are emerging best practices for MLOps pipelines?",
];

const SOURCE_BADGES = {
  arxiv: { label: "ArXiv", bg: "linear-gradient(135deg, #b31b1b, #e74c3c)" },
  hn: { label: "HN", bg: "linear-gradient(135deg, #ff6600, #ff9248)" },
  devto: { label: "DEV.to", bg: "linear-gradient(135deg, #3b49df, #6366f1)" },
  github: { label: "GitHub", bg: "linear-gradient(135deg, #24292e, #586069)" },
  rss: { label: "RSS", bg: "linear-gradient(135deg, #ee802f, #f5a623)" },
};

/* Decorative blobs rendered as SVG */
function DecoBlobs() {
  return (
    <div className="deco-blobs" aria-hidden="true">
      {/* Large coral/orange blob */}
      <svg className="blob blob-1" viewBox="0 0 600 600" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="g1" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#f97316" />
            <stop offset="50%" stopColor="#ef4444" />
            <stop offset="100%" stopColor="#c026d3" />
          </linearGradient>
        </defs>
        <path fill="url(#g1)" d="M421,305Q391,410,286,448Q181,486,117,368Q53,250,152,168Q251,86,345,130Q439,174,451,237Q463,300,421,305Z" />
      </svg>
      {/* Smaller pink/purple blob */}
      <svg className="blob blob-2" viewBox="0 0 600 600" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="g2" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#fb923c" />
            <stop offset="100%" stopColor="#f472b6" />
          </linearGradient>
        </defs>
        <path fill="url(#g2)" d="M454,326Q443,452,310,462Q177,472,127,361Q77,250,160,152Q243,54,353,100Q463,146,466,198Q469,250,454,326Z" />
      </svg>
      {/* Top-left small accent blob */}
      <svg className="blob blob-3" viewBox="0 0 600 600" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="g3" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#a78bfa" />
            <stop offset="100%" stopColor="#6366f1" />
          </linearGradient>
        </defs>
        <path fill="url(#g3)" d="M389,316Q408,432,296,458Q184,484,128,367Q72,250,155,163Q238,76,338,112Q438,148,406,199Q374,250,389,316Z" />
      </svg>
      {/* White concentric circle decorations */}
      <div className="circle-deco circle-deco-1">
        <div className="ring ring-1" />
        <div className="ring ring-2" />
        <div className="ring ring-3" />
        <div className="ring ring-4" />
      </div>
      <div className="circle-deco circle-deco-2">
        <div className="ring ring-1" />
        <div className="ring ring-2" />
        <div className="ring ring-3" />
      </div>
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
    return <Dashboard onGoToApp={() => setPage("main")} />;
  }

  return (
    <div className="app">
      <DecoBlobs />

      <header className="header">
        <h1 className="brand">TechPulse</h1>
        <p className="tagline">
          A Real-Time Hybrid RAG System for Emerging Technology Intelligence
        </p>
        <button
          className="about-btn"
          onClick={() => setPage("dashboard")}
        >
          About Project ↗
        </button>
      </header>

      <main className="main-content">
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
            >
              Baseline
            </button>
            <button
              type="button"
              className={`mode-btn ${mode === "hybrid" ? "active" : ""}`}
              onClick={() => setMode("hybrid")}
            >
              Hybrid
            </button>
          </div>
        </form>

        {error && <div className="error-card">Error: {error}</div>}

        {!result && !loading && !error && (
          <div className="examples-section">
            <p className="examples-title">Try asking about:</p>
            <div className="examples-grid">
              {EXAMPLE_QUERIES.map((eq, i) => (
                <button
                  key={i}
                  className="example-card"
                  onClick={() => {
                    setQuery(eq);
                  }}
                >
                  {eq}
                </button>
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
                    const badge = SOURCE_BADGES[s.source] || {
                      label: s.source,
                      bg: "#777",
                    };
                    return (
                      <li key={i} className="source-item">
                        <span
                          className="source-badge"
                          style={{ background: badge.bg }}
                        >
                          {badge.label}
                        </span>
                        <a
                          href={s.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="source-title"
                        >
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
  );
}
