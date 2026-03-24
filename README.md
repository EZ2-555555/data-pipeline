# TechPulse

**A Real-Time Hybrid Retrieval-Augmented Generation System for Emerging Technology Intelligence**

## Team

| Name | Student ID |
|------|-----------|
| Aye Khin Khin Hpone (Yolanda Lim) | st125970 |
| Dechathon Niamsa-Ard | st126235 |

> **AT82.9002** Selected Topic: Data Engineering and MLOps — Asian Institute of Technology, 2026

---

## Overview

TechPulse is a Hybrid RAG system that continuously ingests emerging technology content from **five data sources**, embeds it into a pgvector-powered PostgreSQL database, and serves grounded, citation-backed answers through a React frontend.

The system **runs locally via Docker Compose** and is **deployed to AWS via GitHub Actions + SAM** (ECR container images, RDS PostgreSQL, Lambda, API Gateway, EventBridge, S3, SQS, CloudWatch).

### Data Sources

| Source | Type | Frequency | Content |
|--------|------|-----------|---------|
| ArXiv API | Scholarly | Every 6 hours | AI/ML/NLP research papers |
| Hacker News API | Industry signal | Every 6 hours | Trending tech discussions |
| DEV.to API | Practitioner | Every 6 hours | Developer blog articles |
| GitHub Trending | Open-source | Every 6 hours | Trending repos + README |
| RSS Feeds | Tech news | Every 6 hours | TechCrunch, Ars Technica, The Verge, IEEE Spectrum, etc. |

### Key Features

- **SHA-256 content-addressed deduplication** across all ingesters
- **S3 medallion data lake** — raw / processed / embeddings tiers (local fallback for dev)
- **SQS-decoupled pipeline** — ingesters produce messages, pipeline consumes asynchronously
- **MiniLM semantic embeddings** via fastembed (all-MiniLM-L6-v2, 384-dim, ONNX Runtime — no PyTorch needed)
- **HNSW vector index** — fast approximate nearest-neighbour search (works on empty tables)
- **3-stage hybrid retrieval**: metadata filter → cosine similarity → recency-aware reranking
- **Reranking weight grid search** — automated α/β/γ optimisation via evaluation framework
- **Multi-backend LLM support**: Groq (primary, free tier) / Amazon Bedrock / HuggingFace Inference API / Ollama (local) — automatic fallback chain with configurable `LLM_MAX_TOKENS`
- **Container-image Lambda deployment** — bypasses the 250 MB zip limit (fastembed + ONNX Runtime ~200 MB); up to 10 GB via ECR
- **LLM retry with exponential backoff** — 2 retries on failures (2s → 4s); automatic retrieval-only fallback when LLM is unavailable
- **Source-type filtering** — `/ask` accepts optional `sources` parameter (e.g. `["arxiv", "hn"]`)
- **Per-query token & cost tracking** — prompt + completion token counts via tiktoken; estimated USD cost per query
- **Retrieval quality drift detection** — probe queries tracked in `drift_baselines` table; >10% drop triggers CloudWatch alert
- **3-layer hallucination verification** — prompt-level, RAGAS faithfulness, citation grounding check
- **Structured citation format** — every claim cites `[Source N]`; ungrounded responses are flagged and abstained
- **Budget guard (programmatic halt)** — LLM invocation skipped when monthly spend >= `MONTHLY_BUDGET_USD`
- **4-state document lifecycle** — RAW → PROCESSED → EMBEDDED → INDEXED with per-state DB updates
- **Connection pooling** — `ThreadedConnectionPool` (1–10 connections) with graceful shutdown
- **HTTP retry with back-off** — shared `requests.Session` with 3 retries on 429/5xx across all ingesters
- **API rate limiting** — `slowapi` at 10 requests/minute per IP on `/ask`
- **CloudWatch custom metrics** — ingestion count, pipeline latency, API latency, hallucination flags
- **Deep health checks** — `/health` verifies DB, S3, and SQS connectivity with structured response
- **25 evaluation queries** across 3 categories with RAGAS automated scoring + p95 latency

### Reranking Formula

```
Score_i = α × CosineSim_i + β × KeywordOverlap_i + γ × e^(−λ × age_days)
```

Default weights: α = 0.6, β = 0.2, γ = 0.2, λ = 0.01

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              Docker Compose (local)                             │
│                                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────┐  ┌────────┐│
│  │PostgreSQL│  │ pgAdmin  │  │ FastAPI  │  │  React   │  │Schedu-│  │Local-  ││
│  │+pgvector │  │   GUI    │  │   API    │  │ Frontend │  │ ler   │  │Stack   ││
│  │  :5432   │  │  :5050   │  │  :8000   │  │  :3000   │  │       │  │ :4566  ││
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └───────┘  └────────┘│
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Pipeline Flow

```
Sources (ArXiv, HN, DEV.to, GitHub, RSS)
    │
    ▼
Ingestion (fetch + SHA-256 dedup → DB + S3 raw tier + SQS message)
    │
    ├──── SQS Queue (decouples ingestion from embedding)
    │
    ▼
Pipeline (normalise → chunk [RAW→PROCESSED] → MiniLM embed [→EMBEDDED] → S3 + DB [→INDEXED])
    │
    ▼
Retrieval (metadata filter → cosine search → reranking-lite → top-k)
    │
    ▼
RAG Orchestrator (budget guard → build context → structured prompt → LLM [retry] → hallucination check → token cost)
    │
    ▼
FastAPI (/ask + /health + /drift) → CloudWatch metrics → React Frontend
```

### AWS Architecture (Free Tier)

```
┌─────────────┐     ┌────────────────┐     ┌──────────────────┐
│  EventBridge │────▶│  Ingestion λ   │────▶│  S3 (medallion)  │
│  (6-hour)    │     │  (5 sources)   │     │  raw/<source>/   │
└─────────────┘     └────────┬───────┘     │  processed/      │
                             │             └──────────────────┘
                             ▼
                     ┌───────────────┐
                     │   SQS Queue   │──DLQ──▶ Dead Letter Queue
                     └───────┬───────┘
                             ▼
                     ┌───────────────┐     ┌───────────────────────┐
                     │ Preprocess λ  │────▶│ RDS PostgreSQL 16      │
                     │ (chunk+embed) │     │ db.t3.micro + pgvector │
                     └───────────────┘     └────────┬──────────────┘
                                                    │
┌──────────────┐     ┌───────────────┐              │
│  React SPA   │────▶│ API Gateway   │────▶┌────────▼──────────┐
│  (S3 hosted) │     │ (HTTP API)    │     │  RAG API λ        │
└──────────────┘     └───────────────┘     │  (ECR container)   │
                                           │  Groq / Bedrock    │
                                           └───────────────────┘
CloudWatch alarms ─── SNS alerts
```

![AWS Architecture](aws_techpulse.png)

---

## Quick Start (Local)

### Prerequisites

- Docker & Docker Compose
- (Optional) [Ollama](https://ollama.ai) running locally for LLM generation

### 1. Start all services

```bash
docker compose up -d
```

This launches **6 containers**:

| Container | Port | Purpose |
|-----------|------|----------|
| `techpulse-db` | 5432 | PostgreSQL 16 + pgvector |
| `techpulse-pgadmin` | 5050 | Database GUI |
| `techpulse-localstack` | 4566 | Local S3 + SQS (AWS emulation) |
| `techpulse-api` | 8000 | FastAPI backend (`/health`, `/ask`) |
| `techpulse-frontend` | 3000 | React UI (nginx) |
| `techpulse-scheduler` | — | Continuous ingestion + chunking + embedding |

The **scheduler** automatically initialises the database schema on first run, then fetches data from all 5 sources on a loop.

### 2. Use the app

- **Frontend**: http://localhost:3000
- **API Swagger**: http://localhost:8000/docs
- **pgAdmin**: http://localhost:5050 — login `admin@techpulse.dev` / `admin`

### 3. Query via API

```bash
# Health check
curl http://localhost:8000/health

# Ask a question (hybrid mode)
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "What are recent approaches to efficient transformer architectures?", "mode": "hybrid"}'
```

---

## AWS Deployment (Free Tier)

Deployment is fully automated via **GitHub Actions** on every push to `main`.

### Required GitHub Secrets

Go to your repo → **Settings → Environments → dev → Secrets** and add all of the following:

| Secret | Where to find it | Notes |
|--------|-----------------|-------|
| `AWS_ACCESS_KEY_ID` | AWS Console → IAM → Users → your user → Security credentials | Permanent — no rotation needed |
| `AWS_SECRET_ACCESS_KEY` | Same as above | Permanent — no rotation needed |
| `DB_USERNAME` | Your choice | e.g. `postgres` |
| `DB_PASSWORD` | Your choice | Min 8 characters |
| `GROQ_API_KEY` | [console.groq.com/keys](https://console.groq.com/keys) | Starts with `gsk_...` — **required** (primary LLM backend) |
| `DEFAULT_VPC_ID` | AWS Console → VPC → Your VPCs | e.g. `vpc-xxxxxxxx` |
| `DEFAULT_SUBNET_A` | AWS Console → VPC → Subnets | Pick any public subnet |
| `DEFAULT_SUBNET_B` | AWS Console → VPC → Subnets | Different AZ from A |
| `ALERT_EMAIL` | Your email address | SNS alert notifications |
| `GROQ_MODEL_ID` | Optional | Defaults to `llama-3.1-8b-instant` |
| `HF_API_TOKEN` | Optional | Only needed if `LLM_BACKEND=huggingface` |
| `DB_ALLOWED_CIDR` | Optional — your IP from [checkip.amazonaws.com](https://checkip.amazonaws.com) | e.g. `203.150.1.2/32` — defaults to `0.0.0.0/0` if not set |

> **Note:** `AWS_SESSION_TOKEN` is **not required** for Free Tier personal accounts. Leave it empty or unset.

### CI/CD Pipeline

```
push to main
    │
    ├── Stage 1 (parallel):
    │   ├── lint-and-test
    │   │   ├── ruff check src/ tests/
    │   │   └── pytest --cov=src --cov-fail-under=60
    │   └── sam-validate
    │       ├── sam validate infra/template-freetier.yaml
    │       └── sam validate infra/template.yaml
    │
    ├── Stage 2 (main branch only):
    │   └── sam-deploy:
    │       ├── Create ECR repo (idempotent)
    │       ├── ECR login
    │       ├── docker build -f Dockerfile.lambda → push (tagged with git SHA)
    │       └── sam deploy --parameter-overrides ECRImageUri=<image> LLMBackend=groq ...
    │
    ├── Stage 2b (after SAM deploy):
    │   └── build-frontend:
    │       ├── Fetch ApiUrl from CloudFormation outputs
    │       ├── npm ci → VITE_API_URL=$ApiUrl npm run build
    │       └── aws s3 sync dist/ → S3 static website
```

> **Why container images?** `fastembed` depends on `onnxruntime` (~150–200 MB on Linux x86_64),
> which pushes zip deployments past Lambda's 250 MB unzipped limit. Container images support up
> to 10 GB, solving this entirely.

### After Deploy

Once deployed, find your live URLs in AWS Console → **CloudFormation → `techpulse-dev` → Outputs**:

| Output | Description |
|--------|-------------|
| `ApiUrl` | Backend API endpoint |
| `FrontendUrl` | React frontend (S3 static website) |
| `PostgresEndpoint` | RDS database host |

**Trigger first ingestion manually** (don't wait 6 hours):
AWS Console → Lambda → `techpulse-dev-ingestion` → Test → send `{}`

---

## Local Development (without Docker)

```bash
python -m venv .venv
source .venv/bin/activate        # Linux / Mac
# .venv\Scripts\activate         # Windows
pip install -r requirements.txt
```

```bash
python -m src.db.init_schema        # Create tables
python -m src.ingestion.hn_ingester # Fetch HN stories
python -m src.pipeline.run_pipeline # Chunk + embed RAW docs
uvicorn src.api.main:app --reload   # Start API on :8000
```

---

## Project Structure

```
data-pipeline/
├── docker-compose.yml                # 6 services: db, pgadmin, localstack, api, frontend, scheduler
├── Dockerfile                        # Python image for api + scheduler (local Docker Compose)
├── Dockerfile.lambda                 # Lambda container image (ECR) — bypasses 250 MB zip limit
├── requirements.txt
├── requirements-lambda.txt           # Lightweight deps for Lambda (fastembed, psycopg2, fastapi, etc.)
├── .github/workflows/ci.yml          # GitHub Actions CI/CD (lint → test → ECR build/push → SAM deploy)
├── src/
│   ├── config.py                     # Centralised env-var settings (DB, AWS, S3, SQS, CW)
│   ├── scheduler.py                  # Continuous ingestion loop (SQS consumer or DB-poll)
│   ├── api/
│   │   └── main.py                   # FastAPI app (/health, /ask, /drift) + Lambda handlers
│   ├── db/
│   │   ├── connection.py             # ThreadedConnectionPool + pgvector adapter
│   │   └── init_schema.py            # Schema: documents + chunks + drift_baselines + HNSW index
│   ├── ingestion/
│   │   ├── _http.py                  # Shared requests.Session with retry/back-off
│   │   ├── arxiv_ingester.py
│   │   ├── hn_ingester.py
│   │   ├── devto_ingester.py
│   │   ├── github_ingester.py
│   │   └── rss_ingester.py
│   ├── preprocessing/
│   │   └── chunker.py                # Text normalisation + tiktoken chunking
│   ├── embedding/
│   │   └── embedder.py               # fastembed all-MiniLM-L6-v2 (384-dim, ONNX Runtime)
│   ├── storage/
│   │   └── __init__.py               # S3 medallion layer (raw/processed/embeddings)
│   ├── queue/
│   │   └── __init__.py               # SQS producer/consumer
│   ├── observability/
│   │   ├── __init__.py               # CloudWatch metrics + deep health checks
│   │   └── drift.py                  # Retrieval quality drift detection
│   ├── pipeline/
│   │   └── run_pipeline.py           # RAW → PROCESSED → EMBEDDED → INDEXED
│   ├── retrieval/
│   │   └── retriever.py              # Baseline (vector-only) + Hybrid (3-stage, grid search)
│   └── orchestrator/
│       ├── rag.py                    # Retrieve → prompt → generate → hallucination check
│       └── llm_backends.py           # Groq / Bedrock / HuggingFace / Ollama — fallback chain router
├── frontend/
│   ├── Dockerfile                    # Multi-stage: node build → nginx serve
│   ├── nginx.conf                    # SPA routing + /api/ proxy to backend
│   ├── package.json                  # Vite + React 19
│   └── src/
│       ├── App.jsx
│       └── App.css
├── evaluation/
│   ├── run_eval.py                   # RAGAS + latency + citation grounding + grid search
│   └── queries/
│       ├── eval_queries.json         # 25 queries (3 categories)
│       └── probe_queries.json        # 20 probe queries for drift detection
├── tests/                            # 192 tests (15 test files, 60%+ coverage)
│   ├── test_api.py
│   ├── test_db.py
│   ├── test_embedder.py
│   ├── test_http.py
│   ├── test_ingestion.py
│   ├── test_llm_backends.py
│   ├── test_observability.py
│   ├── test_pipeline.py
│   ├── test_preprocessing.py
│   ├── test_queue.py
│   ├── test_rag.py
│   ├── test_retriever.py
│   ├── test_scheduler.py
│   ├── test_storage.py
│   └── test_sync_to_aws.py
└── infra/
    ├── template-freetier.yaml        # SAM template — active deployment (Free Tier, container images, RDS db.t3.micro)
    ├── template.yaml                 # SAM template — production reference (Aurora Serverless v2)
    ├── samconfig-freetier.toml       # SAM config for Free Tier manual deploys
    └── README.md
```

## Configuration

All settings via environment variables (`.env` or Docker Compose `environment` block):

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | `localhost` | PostgreSQL host (`db` in Docker) |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `techpulse` | Database name |
| `DB_USER` | `postgres` | Database user |
| `DB_PASSWORD` | `dev` | Database password |
| `LLM_BACKEND` | `groq` | `groq` (default on AWS) / `bedrock` / `huggingface` / `ollama` (local) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `OLLAMA_MODEL` | `llama3.2:3b` | Model for generation |
| `GROQ_API_KEY` | — | Groq API key (required when `LLM_BACKEND=groq`) |
| `GROQ_MODEL_ID` | `llama-3.1-8b-instant` | Groq model ID |
| `GROQ_EVAL_MODEL_ID` | `llama-3.3-70b-versatile` | Larger Groq model used as RAGAS evaluation judge |
| `BEDROCK_MODEL_ID` | `amazon.nova-micro-v1:0` | Bedrock model ID — any model supported by the Converse API works |
| `HF_API_TOKEN` | — | HuggingFace API token (when `LLM_BACKEND=huggingface`) |
| `HF_MODEL_ID` | `mistralai/Mistral-7B-Instruct-v0.2` | HuggingFace model ID |
| `LLM_MAX_TOKENS` | `300` | Max tokens for LLM generation |
| `ALLOWED_ORIGINS` | `*` | Comma-separated CORS origins |
| `TOP_K` | `8` | Retrieval results count |
| `CHUNK_SIZE_TOKENS` | `500` | Tokens per chunk |
| `CHUNK_OVERLAP_TOKENS` | `50` | Overlap between chunks |
| `RERANK_ALPHA` | `0.6` | Cosine similarity weight |
| `RERANK_BETA` | `0.2` | Keyword overlap weight |
| `RERANK_GAMMA` | `0.2` | Recency decay weight |
| `RECENCY_LAMBDA` | `0.01` | Exponential decay rate |
| `S3_ENABLED` | `false` | Enable S3 medallion data lake |
| `S3_BUCKET_NAME` | `techpulse-data` | S3 bucket name |
| `SQS_ENABLED` | `false` | Enable SQS ingestion queue |
| `SQS_QUEUE_URL` | — | SQS queue URL |
| `CLOUDWATCH_ENABLED` | `false` | Enable CloudWatch metric publishing |
| `CITATION_GROUNDING_THRESHOLD` | `0.5` | Min citation ratio before flagging (AWS); `0.0` locally |
| `BUDGET_HALT_ENABLED` | `false` | Enable budget guard (`true` on AWS) |
| `MONTHLY_BUDGET_USD` | `15` | Monthly cost threshold |
| `STAGE` | `dev` | CloudWatch namespace suffix (`TechPulse/<stage>`) |

## Evaluation

The evaluation framework compares **baseline (vector-only)** vs **hybrid retrieval** across:

- **RAGAS metrics**: faithfulness, answer relevancy, context precision (judged by Groq `llama-3.3-70b-versatile`)
- **Latency**: per-query, mean, and p95 end-to-end
- **Citation grounding**: ratio of valid `[Source N]` references
- **Token / cost per query**: prompt + completion tokens; estimated USD cost
- **Weight grid search**: automated α/β/γ optimisation (α ∈ {0.4, 0.5, 0.6, 0.7})
- **Source diversity**: per-source retrieval distribution analysis

```bash
python -m evaluation.run_eval
```

Results are written to `evaluation/results/` as JSON.

## Tests & CI

```bash
ruff check src/ tests/                                          # lint
pytest tests/ -v --cov=src --cov-report=term-missing           # unit tests + coverage
```

CI enforces a **minimum 60% coverage** threshold — the build fails if coverage drops below this.

---

## Roadmap

- [x] 5-source data ingestion pipeline (ArXiv, HN, DEV.to, GitHub, RSS)
- [x] SHA-256 deduplication across all ingesters
- [x] Token-based chunking + fastembed MiniLM embedding (ONNX — no PyTorch)
- [x] Hybrid retrieval with 3-stage reranking + grid search
- [x] Multi-backend LLM support (Groq (primary) / Bedrock / HuggingFace / Ollama) with automatic fallback
- [x] FastAPI backend with deep `/health`, `/ask`, `/drift` endpoints
- [x] React frontend (Vite) with source badges and mode selection
- [x] Docker Compose (6 services: db, pgadmin, localstack, api, frontend, scheduler)
- [x] RAGAS evaluation framework (25 queries, 3 categories, p95 latency)
- [x] S3 medallion data lake (raw / processed tiers)
- [x] SQS decoupling between ingestion and embedding pipeline
- [x] CloudWatch custom metrics + deep health checks
- [x] 3-layer hallucination verification (prompt + RAGAS + citation grounding)
- [x] Retrieval quality drift detection (probe queries + `/drift` API)
- [x] AWS IaC — SAM template for Free Tier (RDS db.t3.micro) + production (Aurora Serverless v2)
- [x] GitHub Actions CI/CD — lint → test (60% coverage gate) → SAM validate → SAM deploy → S3 frontend upload
- [x] Frontend auto-deploy to S3 via CI/CD (Vite build + S3 sync)
- [x] Lambda `health_handler` proper response format (statusCode + body)
- [x] pgvector extension error detection with actionable log message
- [x] `DBAllowedCidrIp` and `HFModelId` configurable via GitHub secrets
- [x] Container-image Lambda deployment via ECR (fixes 250 MB zip limit caused by fastembed/onnxruntime)
- [x] Groq free-tier LLM backend (llama-3.1-8b-instant) — replaces Bedrock on educational AWS accounts
- [x] Automatic LLM fallback chain (groq → bedrock → ollama → huggingface)
- [x] Bedrock Converse API (model-agnostic) for future migration
- [ ] Migrate local data to AWS RDS after first deploy
- [ ] RAGAS evaluation run on live AWS deployment
- [ ] Source diversity analysis — investigate and mitigate corpus skew toward any single source (e.g. DEV.to)
- [ ] CloudFront HTTPS — add CloudFront distribution for S3 frontend to serve over HTTPS
