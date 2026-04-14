# TechPulse Frontend

React 19 + Vite SPA for TechPulse. Provides a search interface for querying the hybrid RAG system and a dashboard with RAGAS evaluation metrics.

## Development

```bash
npm install
npm run dev          # http://localhost:5173 (proxies /api → localhost:8000)
```

## Production Build

```bash
npm run build        # outputs to dist/
```

## Docker (via Compose)

The frontend runs as part of `docker compose up` on **port 3000** (nginx).

## Environment Variables

| Variable | Default | Description |
|:---------|:--------|:------------|
| `VITE_API_URL` | `/api` | Backend API base URL (set at build time for AWS) |

## Key Components

- **App.jsx** — Search UI with baseline/hybrid mode toggle and source filtering
- **Dashboard.jsx** — RAGAS metrics radar chart, latency comparison, pipeline overview
