<div align="center">

# TechPulse

### A Real-Time Hybrid RAG System for Emerging Technology Intelligence

[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React 19](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16+pgvector-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![AWS SAM](https://img.shields.io/badge/AWS-SAM%20Free%20Tier-FF9900?logo=amazonaws&logoColor=white)](https://aws.amazon.com/serverless/sam/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Tests](https://img.shields.io/badge/Tests-208%20passed-brightgreen?logo=pytest&logoColor=white)](tests/)

---

**AT82.9002** Selected Topic: Data Engineering and MLOps — Asian Institute of Technology, 2026

| Name | Student ID |
|:-----|:-----------|
| Aye Khin Khin Hpone (Yolanda Lim) | st125970 |
| Dechathon Niamsa-Ard | st126235 |

---

### Live Deployment

**Frontend:** [TechPulse Live Demo](http://techpulse-dev-frontend-939514668437.s3-website-us-east-1.amazonaws.com/)

Running on AWS Free Tier

</div>

---

## System Overview

<div align="center">


<table>
<tr>
<td><img src="aws_techpulse.png" width="420" alt="AWS Architecture"></td>
</tr>
</table>

<table>
<tr>
<td align="center"><strong>Landing Page</strong></td>
<td align="center"><strong>Search Interface</strong></td>
</tr>
<tr>
<td><img src="Final Report/chapters/img/techpulse-overviewpage.png" width="420" alt="Landing Page"></td>
<td><img src="Final Report/chapters/img/rag_overview.png" width="420" alt="Search Interface"></td>
</tr>
</table>

<table>
<tr>
<td align="center"><strong>Hybrid Retrieval</strong></td>
<td align="center"><strong>Baseline Retrieval</strong></td>
</tr>
<tr>
<td><img src="Final Report/chapters/img/hybridmodel.png" width="420" alt="Hybrid Retrieval"></td>
<td><img src="Final Report/chapters/img/baseline.png" width="420" alt="Baseline Retrieval"></td>
</tr>
</table>

<table>
<tr>
<td align="center"><strong>Step-by-Step RAG Loading</strong></td>
<td align="center"><strong>Model Comparison</strong></td>
</tr>
<tr>
<td><img src="Final Report/chapters/img/stepbysteploading_rag.png" width="420" alt="RAG Loading"></td>
<td><img src="Final Report/chapters/img/compare model.png" width="420" alt="Model Comparison"></td>
</tr>
</table>

<table>
<tr>
<td align="center"><strong>Trending Topics Dashboard</strong></td>
<td align="center"><strong>Analytics and Live Insights</strong></td>
</tr>
<tr>
<td><img src="Final Report/chapters/img/techtopichighlight.png" width="420" alt="Trending Topics"></td>
<td><img src="Final Report/chapters/img/analytics_liveinsight.png" width="420" alt="Analytics"></td>
</tr>
</table>

<table>
<tr>
<td align="center"><strong>Evaluation Results (RAGAS)</strong></td>
<td align="center"><strong>Evaluation Results (Latency)</strong></td>
</tr>
<tr>
<td><img src="Final Report/chapters/img/evalresult_1.png" width="420" alt="Evaluation Results 1"></td>
<td><img src="Final Report/chapters/img/evalresult_2.png" width="420" alt="Evaluation Results 2"></td>
</tr>
</table>

</div>

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Quick Start (Local)](#quick-start-local)
- [AWS Deployment (Free Tier)](#aws-deployment-free-tier)
- [Local Development (without Docker)](#local-development-without-docker)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [Evaluation](#evaluation)
- [Tests and CI](#tests-and-ci)
- [Roadmap](#roadmap)

---

## Overview

TechPulse is a Hybrid RAG system that continuously ingests emerging technology content from **five data sources**, embeds it into a pgvector-powered PostgreSQL database, and serves grounded, citation-backed answers through a React frontend.

The system runs locally via Docker Compose and is deployed to AWS via GitHub Actions + SAM (ECR container images, RDS PostgreSQL, Lambda, API Gateway, EventBridge, S3, SQS, CloudWatch).

### Data Sources

| Source | Type | Frequency (local) | Content |
|:-------|:-----|:-------------------|:--------|
| ArXiv API | Scholarly | Every 12 hours | AI/ML/NLP research papers |
| Hacker News API | Industry signal | Every 30 minutes | Trending tech discussions |
| DEV.to API | Practitioner | Every 30 minutes | Developer blog articles |
| GitHub Trending | Open-source | Every 30 minutes | Trending repos + README |
| RSS Feeds | Tech news | Every 30 minutes | TechCrunch, Ars Technica, The Verge, IEEE Spectrum, etc. |

> On AWS, a single EventBridge rule triggers the ingestion Lambda every **6 hours**, executing all five sources in one invocation (~4 invocations/day).

### Key Features

<table>
<tr><td>

**Ingestion and Processing**
- SHA-256 content-addressed deduplication
- S3 medallion data lake (raw / processed / embeddings)
- SQS-decoupled pipeline (async produce / consume)
- 4-state document lifecycle: RAW, PROCESSED, EMBEDDED, INDEXED
- HTTP retry with back-off (3 retries on 429/5xx)

</td><td>

**Retrieval and Ranking**
- MiniLM semantic embeddings (all-MiniLM-L6-v2, 384-dim, ONNX)
- HNSW vector index for fast ANN search
- 5-stage hybrid retrieval: metadata filter, vector + BM25, weighted RRF, cross-encoder reranking
- Reciprocal Rank Fusion (weighted RRF: vector 0.50, BM25 0.35, recency 0.15)
- Source-type filtering on `/ask`

</td></tr>
<tr><td>

**Generation and Safety**
- Multi-backend LLM fallback chain (Groq, Bedrock, Ollama, HuggingFace)
- Zero per-backend retries; single-fallback chain stays within 30s API Gateway limit
- 3-layer hallucination verification
- Structured `[Source N]` citations with grounding check
- Budget guard halts when monthly spend reaches threshold

</td><td>

**Ops and Observability**
- Container-image Lambda (up to 10 GB via ECR)
- 8 CloudWatch custom metrics + 3 alarms
- Deep health checks (DB, S3, SQS, LLM)
- Retrieval quality drift detection (dual-criteria: 10% threshold + Shewhart 3-sigma)
- Per-query token and cost tracking via tiktoken
- API rate limiting (`/ask` 10 req/min, `/drift` 2 req/min per IP)
- Connection pooling (1-25 connections)

</td></tr>
</table>

### Retrieval Fusion (Weighted RRF)

The hybrid retrieval pipeline fuses three independent ranking signals using **Weighted Reciprocal Rank Fusion** (based on Cormack et al., SIGIR 2009):

```
RRF(d) = sum  w_r / (K + rank_r(d))    for r in {vector, BM25, recency}
```

| Signal | Weight | Rationale |
|:-------|:-------|:----------|
| Vector (semantic) | 0.50 | Dominant signal -- preserves faithfulness |
| BM25 (keyword) | 0.35 | Keyword coverage for lexical matches |
| Recency | 0.15 | Weak signal -- prevents thin fresh content from outranking richer articles |

> K = 60 (standard constant). Weights were selected through empirical ablation across candidate configurations, optimising the composite RAGAS score under latency constraints. An earlier design-phase equal-weight RRF was superseded because recency at 33% promoted newly-published but thin content, lowering faithfulness and citation grounding.

---

## Architecture

### Local (Docker Compose)

```
+---------------------------------------------------------------------------------+
|                              Docker Compose (local)                             |
|                                                                                 |
|  +----------+  +----------+  +----------+  +----------+  +-------+  +--------+ |
|  |PostgreSQL|  | pgAdmin  |  | FastAPI  |  |  React   |  |Schedu-|  |Local-  | |
|  |+pgvector |  |   GUI    |  |   API    |  | Frontend |  | ler   |  |Stack   | |
|  |  :5432   |  |  :5050   |  |  :8000   |  |  :3000   |  |       |  | :4566  | |
|  +----------+  +----------+  +----------+  +----------+  +-------+  +--------+ |
+---------------------------------------------------------------------------------+
```

### Pipeline Flow

```
Sources (ArXiv, HN, DEV.to, GitHub, RSS)
    |
    v
Ingestion (fetch + SHA-256 dedup -> DB + S3 raw tier + SQS message)
    |
    +---- SQS Queue (decouples ingestion from embedding)
    |
    v
Pipeline (normalise -> chunk [RAW->PROCESSED] -> MiniLM embed [->EMBEDDED] -> S3 + DB [->INDEXED])
    |
    v
Retrieval (metadata filter -> vector + BM25 -> weighted RRF -> cross-encoder reranking -> top-k)
    |
    v
RAG Orchestrator (budget guard -> build context -> structured prompt -> LLM [fallback chain] -> hallucination check -> token cost)
    |
    v
FastAPI (/ask + /health + /drift) -> CloudWatch metrics -> React Frontend
```

### AWS Architecture (Free Tier)

<div align="center">
<img src="aws_techpulse.png" width="700" alt="AWS Architecture Diagram">
</div>

```
+-------------+     +----------------+     +------------------+
| EventBridge |---->| Ingestion fn   |---->| S3 (medallion)   |
| (6-hour)    |     | (5 sources)    |     | raw/<source>/    |
+-------------+     +-------+--------+     | processed/       |
                            |              +------------------+
                            v
                    +---------------+
                    |   SQS Queue   |--DLQ--> Dead Letter Queue
                    +-------+-------+
                            v
                    +---------------+     +-----------------------+
                    | Preprocess fn |---->| RDS PostgreSQL 16     |
                    | (chunk+embed) |     | db.t3.micro + pgvector|
                    +---------------+     +--------+--------------+
                                                   |
+---------------+   +---------------+              |
| React SPA     |-->| API Gateway   |---->+--------v----------+
| (S3 hosted)   |   | (HTTP API)    |     | RAG API fn        |
+---------------+   +---------------+     | (ECR container)   |
                                          | Groq / Bedrock    |
                                          +-------------------+
CloudWatch alarms --- SNS alerts
```

---

## Quick Start (Local)

### Prerequisites

- Docker and Docker Compose
- (Optional) [Ollama](https://ollama.ai) running locally for LLM generation

### 1. Start all services

```bash
docker compose up -d
```

This launches **6 containers**:

| Container | Port | Purpose |
|:----------|:-----|:--------|
| `techpulse-db` | 5432 | PostgreSQL 16 + pgvector |
| `techpulse-pgadmin` | 5050 | Database GUI |
| `techpulse-localstack` | 4566 | Local S3 + SQS (AWS emulation) |
| `techpulse-api` | 8000 | FastAPI backend (`/health`, `/ask`) |
| `techpulse-frontend` | 3000 | React UI (nginx) |
| `techpulse-scheduler` | -- | Continuous ingestion + chunking + embedding |

> The scheduler automatically initialises the database schema on first run, then fetches data from all 5 sources on a loop.

### 2. Use the app

| Service | URL |
|:--------|:----|
| Frontend | http://localhost:3000 |
| API Swagger | http://localhost:8000/docs |
| pgAdmin | http://localhost:5050 (login `admin@techpulse.dev` / `admin`) |

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

Go to your repo, then Settings, Environments, dev, Secrets and add:

<details>
<summary><strong>Required secrets</strong></summary>

| Secret | Where to find it | Notes |
|:-------|:-----------------|:------|
| `AWS_ACCESS_KEY_ID` | IAM, Users, Security credentials | Permanent |
| `AWS_SECRET_ACCESS_KEY` | Same as above | Permanent |
| `DB_USERNAME` | Your choice | e.g. `postgres` |
| `DB_PASSWORD` | Your choice | Min 8 characters |
| `GROQ_API_KEY` | [console.groq.com/keys](https://console.groq.com/keys) | Starts with `gsk_...` -- required (primary LLM) |
| `DEFAULT_VPC_ID` | VPC, Your VPCs | e.g. `vpc-xxxxxxxx` |
| `DEFAULT_SUBNET_A` | VPC, Subnets | Any public subnet |
| `DEFAULT_SUBNET_B` | VPC, Subnets | Different AZ from A |
| `ALERT_EMAIL` | Your email address | SNS alert notifications |

</details>

<details>
<summary><strong>Optional secrets</strong></summary>

| Secret | Notes |
|:-------|:------|
| `GROQ_MODEL_ID` | Defaults to `llama-3.1-8b-instant` |
| `HF_API_TOKEN` | Only needed if `LLM_BACKEND=huggingface` |
| `DB_ALLOWED_CIDR` | Your IP (e.g. `203.150.1.2/32`); defaults to `0.0.0.0/0` |

> `AWS_SESSION_TOKEN` is not required for Free Tier personal accounts.

</details>

### CI/CD Pipeline

```
push to main
    |
    +-- Stage 1 (parallel):
    |   +-- lint-and-test
    |   |   +-- ruff check src/ tests/
    |   |   +-- pytest --cov=src --cov-fail-under=60
    |   +-- sam-validate
    |       +-- sam validate infra/template-freetier.yaml
    |       +-- sam validate infra/template.yaml
    |
    +-- Stage 2 (main branch only):
    |   +-- sam-deploy:
    |       +-- Create ECR repo (idempotent)
    |       +-- ECR login
    |       +-- docker build -f Dockerfile.lambda -> push (tagged with git SHA)
    |       +-- sam deploy --parameter-overrides ECRImageUri=<image> LLMBackend=groq ...
    |
    +-- Stage 2b (after SAM deploy):
        +-- build-frontend:
            +-- Fetch ApiUrl from CloudFormation outputs
            +-- npm ci -> VITE_API_URL=$ApiUrl npm run build
            +-- aws s3 sync dist/ -> S3 static website
```

> **Why container images?** `fastembed` depends on `onnxruntime` (~150-200 MB on Linux x86_64), which pushes zip deployments past Lambda's 250 MB unzipped limit. Container images support up to 10 GB, solving this entirely.

### After Deploy

Find your live URLs in AWS Console, CloudFormation, `techpulse-dev`, Outputs:

| Output | Description |
|:-------|:------------|
| `ApiUrl` | Backend API endpoint |
| `FrontendUrl` | React frontend (S3 static website) |
| `PostgresEndpoint` | RDS database host |

> Trigger first ingestion manually (do not wait 6 hours): AWS Console, Lambda, `techpulse-dev-ingestion`, Test, send `{}`

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

<details>
<summary>Click to expand full tree</summary>

```
data-pipeline/
|-- docker-compose.yml                # 6 services: db, pgadmin, localstack, api, frontend, scheduler
|-- Dockerfile                        # Python image for api + scheduler (local Docker Compose)
|-- Dockerfile.lambda                 # Lambda container image (ECR) -- bypasses 250 MB zip limit
|-- requirements.txt
|-- requirements-lambda.txt           # Lightweight deps for Lambda (fastembed, psycopg2, fastapi, etc.)
|-- .github/workflows/ci.yml          # GitHub Actions CI/CD (lint -> test -> ECR build/push -> SAM deploy)
|
|-- src/
|   |-- config.py                     # Centralised env-var settings (DB, AWS, S3, SQS, CW)
|   |-- scheduler.py                  # Continuous ingestion loop (SQS consumer or DB-poll)
|   |-- sync_to_aws.py                # Local DB + S3 -> AWS data migration utility
|   |-- api/
|   |   +-- main.py                   # FastAPI app (/health, /ask, /drift, /dashboard/insights) + Lambda handlers
|   |-- db/
|   |   |-- connection.py             # ThreadedConnectionPool + pgvector adapter
|   |   +-- init_schema.py            # Schema: documents + chunks + drift_baselines + HNSW index
|   |-- ingestion/
|   |   |-- _http.py                  # Shared requests.Session with retry/back-off
|   |   |-- arxiv_ingester.py
|   |   |-- hn_ingester.py
|   |   |-- devto_ingester.py
|   |   |-- github_ingester.py
|   |   +-- rss_ingester.py
|   |-- preprocessing/
|   |   +-- chunker.py                # Text normalisation + tiktoken chunking
|   |-- embedding/
|   |   +-- embedder.py               # fastembed all-MiniLM-L6-v2 (384-dim, ONNX Runtime)
|   |-- storage/
|   |   +-- __init__.py               # S3 medallion layer (raw/processed/embeddings)
|   |-- queue/
|   |   +-- __init__.py               # SQS producer/consumer
|   |-- observability/
|   |   |-- __init__.py               # CloudWatch metrics + deep health checks
|   |   +-- drift.py                  # Retrieval quality drift detection
|   |-- pipeline/
|   |   +-- run_pipeline.py           # RAW -> PROCESSED -> EMBEDDED -> INDEXED
|   |-- retrieval/
|   |   +-- retriever.py              # Baseline (vector-only) + Hybrid (5-stage, BM25 + weighted RRF + cross-encoder)
|   +-- orchestrator/
|       |-- rag.py                    # Retrieve -> prompt -> generate -> hallucination check
|       +-- llm_backends.py           # Groq / Bedrock / HuggingFace / Ollama -- fallback chain router
|
|-- frontend/
|   |-- Dockerfile                    # Multi-stage: node build -> nginx serve
|   |-- nginx.conf                    # SPA routing + /api/ proxy to backend
|   |-- TechPulse-Ultimate.jsx        # Dashboard component (trending topics, eval results, analytics)
|   |-- package.json                  # Vite + React 19
|   +-- src/
|       |-- App.jsx
|       |-- App.css
|       |-- Dashboard.jsx
|       |-- Dashboard.css
|       |-- main.jsx
|       +-- index.css
|
|-- evaluation/
|   |-- run_eval.py                   # 9-phase evaluation pipeline (7 active, 2 skipped)
|   +-- queries/
|       |-- eval_queries.json         # 50 queries (3 categories)
|       +-- probe_queries.json        # 20 probe queries for drift detection
|
|-- tests/                            # 208 tests across 15 modules
|   |-- test_api.py          test_ingestion.py      test_queue.py
|   |-- test_db.py           test_llm_backends.py   test_rag.py
|   |-- test_embedder.py     test_observability.py  test_retriever.py
|   |-- test_http.py         test_pipeline.py       test_scheduler.py
|   |                        test_preprocessing.py  test_storage.py
|   +--                                             test_sync_to_aws.py
|
+-- infra/
    |-- template-freetier.yaml        # SAM -- Free Tier (container images, RDS db.t3.micro)
    |-- template.yaml                 # SAM -- production reference (Aurora Serverless v2)
    |-- samconfig-freetier.toml
    +-- README.md
```

</details>

---

## Configuration

All settings via environment variables (`.env` or Docker Compose `environment` block):

<details>
<summary><strong>Database</strong></summary>

| Variable | Default | Description |
|:---------|:--------|:------------|
| `DB_HOST` | `localhost` | PostgreSQL host (`db` in Docker) |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `techpulse` | Database name |
| `DB_USER` | `postgres` | Database user |
| `DB_PASSWORD` | *(required)* | Database password |

</details>

<details>
<summary><strong>LLM Backends</strong></summary>

| Variable | Default | Description |
|:---------|:--------|:------------|
| `LLM_BACKEND` | `ollama` | `ollama` (local) / `groq` (AWS) / `bedrock` / `huggingface` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `OLLAMA_MODEL` | `llama3.2:3b` | Ollama model for generation |
| `GROQ_API_KEY` | -- | Groq API key (required when `LLM_BACKEND=groq`) |
| `GROQ_MODEL_ID` | `llama-3.1-8b-instant` | Groq model ID |
| `GROQ_EVAL_MODEL_ID` | `llama-3.3-70b-versatile` | Larger Groq model used as RAGAS judge |
| `BEDROCK_MODEL_ID` | `amazon.nova-micro-v1:0` | Any model supported by Converse API |
| `HF_API_TOKEN` | -- | HuggingFace API token |
| `HF_MODEL_ID` | `mistralai/Mistral-7B-Instruct-v0.2` | HuggingFace model ID |
| `LLM_MAX_TOKENS` | `300` | Max tokens for LLM generation |

</details>

<details>
<summary><strong>Retrieval and Reranking</strong></summary>

| Variable | Default | Description |
|:---------|:--------|:------------|
| `TOP_K` | `5` | Number of retrieval results |
| `CHUNK_SIZE_TOKENS` | `500` | Tokens per chunk |
| `CHUNK_OVERLAP_TOKENS` | `50` | Overlap between chunks |

</details>

<details>
<summary><strong>AWS and Infrastructure</strong></summary>

| Variable | Default | Description |
|:---------|:--------|:------------|
| `S3_ENABLED` | `false` | Enable S3 medallion data lake |
| `S3_BUCKET_NAME` | `techpulse-data` | S3 bucket name |
| `SQS_ENABLED` | `false` | Enable SQS ingestion queue |
| `SQS_QUEUE_URL` | -- | SQS queue URL |
| `CLOUDWATCH_ENABLED` | `false` | Enable CloudWatch metric publishing |
| `CITATION_GROUNDING_THRESHOLD` | `0.0` | Min citation ratio before flagging |
| `BUDGET_HALT_ENABLED` | `false` | Enable budget guard (`true` on AWS) |
| `MONTHLY_BUDGET_USD` | `15` | Monthly cost threshold |
| `ALLOWED_ORIGINS` | `*` | Comma-separated CORS origins |
| `STAGE` | `dev` | CloudWatch namespace suffix (`TechPulse/<stage>`) |

</details>

---

## Evaluation

The evaluation framework implements a **9-phase pipeline** (7 active, 2 skipped) comparing baseline (vector-only) vs hybrid retrieval:

| Phase | Name | Description |
|:-----:|:-----|:------------|
| 1 | RAG Query Execution | 50 queries x 2 modes = 100 RAGAS samples (baseline + hybrid) with per-query latency |
| 2 | RAGAS LLM-Judged Scoring | Faithfulness, answer relevancy, context precision |
| 3 | Summary Statistics | Mean, median, p95, citation grounding, token costs per mode |
| 4 | ~~Grid Search~~ _(skipped)_ | Legacy alpha/beta/gamma sweep -- superseded by weighted RRF with fixed weights |
| 5 | ~~Sensitivity Analysis~~ _(skipped)_ | Legacy one-at-a-time sweep -- superseded by weighted RRF |
| 6 | Statistical Tests | Wilcoxon signed-rank, Cohen's d effect size, bootstrap 95% CI |
| 7 | Drift Validation | 4 simulated scenarios (normal, Shewhart breach, catastrophic) |
| 8 | Composite Metric | 0.35 x Faithfulness + 0.25 x Relevancy + 0.20 x Precision + 0.20 x CitationGrounding |
| 9 | Cost Projection | Monthly cost for 50/100/200 queries/day vs free-tier ceilings |

**Key Results:**

| Metric | Baseline | Hybrid | Delta |
|:-------|:---------|:-------|:------|
| Composite Score | 0.676 | 0.723 | +0.047 |
| Faithfulness | 0.689 | 0.747 | +0.058 |
| Answer Relevancy | 0.869 | 0.934 | +0.065 |
| Context Precision | 0.208 | 0.278 | +0.070 |
| Citation Grounding | 0.880 | 0.860 | -0.020 |
| Mean Latency | 1.13 s | 2.49 s | +1.36 s |
| p95 Latency | 1.48 s | 2.44 s | +0.96 s |
| Cost (100 q/day) | $0.32/mo | $0.33/mo | +$0.01 |

> Wilcoxon signed-rank p = 0.073 (context precision), Cohen's d = -0.337 (latency, small effect), 95% CI [-2.56, -0.72] s.

```bash
python -m evaluation.run_eval
```

Results are written to `evaluation/results/` as JSON.

---

## Tests and CI

```bash
ruff check src/ tests/                                          # lint
pytest tests/ -v --cov=src --cov-report=term-missing           # unit tests + coverage
```

208 tests across 15 modules. CI enforces a minimum 60% coverage threshold.

---

## Roadmap

### Completed

- [x] 5-source data ingestion pipeline (ArXiv, HN, DEV.to, GitHub, RSS) with SHA-256 deduplication
- [x] Token-based chunking + fastembed MiniLM embedding (ONNX, no PyTorch)
- [x] Hybrid retrieval: pgvector + BM25 + weighted RRF + cross-encoder reranking (ms-marco-MiniLM-L-6-v2)
- [x] Multi-backend LLM fallback chain (Groq, Bedrock, Ollama, HuggingFace)
- [x] FastAPI backend (`/health`, `/ask`, `/drift`, `/dashboard/insights`) + React frontend (Vite)
- [x] Docker Compose (6 services) + container-image Lambda deployment via ECR
- [x] S3 medallion data lake + SQS-decoupled ingestion pipeline
- [x] 3-layer hallucination verification + retrieval quality drift detection
- [x] 8 CloudWatch custom metrics + deep health checks + 3 alarms
- [x] RAGAS evaluation framework: 100 samples, 9-phase pipeline, statistical tests -- hybrid composite 0.723 vs baseline 0.676 (+4.7 pp)
- [x] AWS IaC via SAM (Free Tier + production templates)
- [x] GitHub Actions CI/CD: lint, test, SAM validate, deploy, S3 frontend upload
- [x] 208 unit tests across 15 modules