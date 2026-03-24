# TechPulse — Infrastructure

AWS serverless infrastructure for TechPulse deployed via **GitHub Actions + SAM**.

Lambda functions use **ECR container images** (not zip packages) to accommodate `fastembed` + `onnxruntime` (~150–200 MB), which exceeds Lambda's 250 MB unzipped zip limit. Container images support up to 10 GB.

## Templates

| Template | Target | Database | Status |
|----------|--------|----------|--------|
| `template-freetier.yaml` | AWS Free Tier (personal account) | RDS PostgreSQL 16 (`db.t3.micro`) | **Active — used by CI/CD** |
| `template.yaml` | Production | Aurora Serverless v2 + pgvector | Reference only |

> The active template uses **Groq** (`llama-3.1-8b-instant`) as the primary LLM backend with a four-tier fallback chain: Groq → Bedrock → Ollama → HuggingFace. A `GROQ_API_KEY` secret must be set in the deployed environment.

## Architecture (Free Tier)

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
CloudWatch alarms ─── SNS topic ─── email (AlertEmail)
```

## Resources Deployed

| Resource | Name | Purpose |
|----------|------|---------|
| ECR | `techpulse-lambda` | Container images for all Lambda functions |
| IAM Role | `techpulse-dev-lambda-role` | Execution role for all Lambda functions |
| RDS PostgreSQL | `techpulse-dev-db` | Vector + relational store |
| S3 data bucket | `techpulse-dev-data-<account-id>` | Medallion data lake |
| S3 frontend bucket | `techpulse-dev-frontend-<account-id>` | Static website hosting |
| SQS queue | `techpulse-dev-ingestion` | Decoupled ingestion pipeline |
| SQS DLQ | `techpulse-dev-ingestion-dlq` | Failed message replay |
| Lambda | `techpulse-dev-ingestion` | Fetches from 5 sources every 6h (container image) |
| Lambda | `techpulse-dev-preprocess` | Chunks + embeds via SQS trigger (container image) |
| Lambda | `techpulse-dev-rag-api` | FastAPI RAG endpoint (container image) |
| Lambda | `techpulse-dev-healthcheck` | Pings health every 5 min (container image) |
| API Gateway | HTTP API | Public HTTPS endpoint |
| CloudWatch | 3 alarms | RAG errors, ingestion errors, DLQ depth |
| SNS | `techpulse-dev-alerts` | Email notifications |

## AWS Free Tier limits (what's covered)

| Service | Free Tier allowance |
|---------|-------------------|
| RDS `db.t3.micro` | 750 hrs/month for 12 months |
| RDS storage | 20 GB gp2 |
| Lambda | 1M requests + 400,000 GB-seconds/month (permanent) |
| S3 | 5 GB storage, 20K GET, 2K PUT/month for 12 months |
| SQS | 1M requests/month (permanent) |
| API Gateway | 1M HTTP API calls/month for 12 months |
| CloudWatch | 10 custom metrics, 3 alarms (permanent) |

> **After 12 months**, RDS, S3 and API Gateway move to paid tiers. Monitor usage in the AWS Billing console.

## Deployment via GitHub Actions (recommended)

Deployment triggers automatically on push to `main`. All secrets must be set in GitHub → Settings → Environments → dev.

### Required Secrets

| Secret | Description |
|--------|-------------|
| `AWS_ACCESS_KEY_ID` | From AWS Console → IAM → Users → your user → Security credentials |
| `AWS_SECRET_ACCESS_KEY` | Same as above — permanent credentials, no rotation needed |
| `DB_USERNAME` | PostgreSQL master username (e.g. `postgres`) |
| `DB_PASSWORD` | PostgreSQL master password (min 8 chars) |
| `HF_API_TOKEN` | HuggingFace token from huggingface.co/settings/tokens |
| `DEFAULT_VPC_ID` | AWS Console → VPC → Your VPCs |
| `DEFAULT_SUBNET_A` | AWS Console → VPC → Subnets (any public subnet) |
| `DEFAULT_SUBNET_B` | Different subnet, different AZ from A |
| `ALERT_EMAIL` | Email for SNS alarm notifications |
| `HF_MODEL_ID` | *(optional)* Defaults to `mistralai/Mistral-7B-Instruct-v0.2` |
| `BEDROCK_MODEL_ID` | *(optional)* Defaults to `amazon.nova-micro-v1:0` — any Bedrock model ID works (uses Converse API) |
| `DB_ALLOWED_CIDR` | *(optional)* Your IP/32 — defaults to `0.0.0.0/0` if not set |

> **Note:** `AWS_SESSION_TOKEN` is **not needed** for Free Tier personal accounts. Leave it empty or unset in your GitHub environment.

### Stack Outputs

After deploy, find these in AWS Console → CloudFormation → `techpulse-dev` → Outputs:

| Output | Description |
|--------|-------------|
| `ApiUrl` | Backend API: `https://<id>.execute-api.us-east-1.amazonaws.com/dev` |
| `FrontendUrl` | React app: `http://techpulse-dev-frontend-<account>.s3-website-us-east-1.amazonaws.com` |
| `PostgresEndpoint` | RDS host for direct DB connections |
| `IngestionQueueUrl` | SQS queue URL |
| `DLQUrl` | Dead letter queue URL |
| `LambdaRoleArn` | IAM role used by all Lambda functions |

## Manual SAM Deployment

Only needed for testing outside CI. Ensure AWS credentials are configured first (`aws configure`).

**Step 1 — Build and push the container image to ECR:**

```bash
# Get your account ID and region
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=us-east-1

# Create ECR repo (idempotent)
aws ecr describe-repositories --repository-names techpulse-lambda --region $REGION 2>/dev/null \
  || aws ecr create-repository --repository-name techpulse-lambda --region $REGION

# Login to ECR
aws ecr get-login-password --region $REGION \
  | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com

# Build and push
IMAGE_URI=$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/techpulse-lambda:latest
docker build -f Dockerfile.lambda -t $IMAGE_URI .
docker push $IMAGE_URI
```

**Step 2 — Deploy with SAM:**

```bash
sam deploy \
  --template-file infra/template-freetier.yaml \
  --stack-name techpulse-dev \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND CAPABILITY_NAMED_IAM \
  --region us-east-1 \
  --resolve-s3 \
  --parameter-overrides \
    Stage=dev \
    ECRImageUri=$IMAGE_URI \
    DBMasterUsername=postgres \
    DBMasterPassword=yourpassword \
    HFApiToken=hf_your_token \
    DefaultVpcId=vpc-xxxxxxxx \
    DefaultSubnetA=subnet-xxxxxxxx \
    DefaultSubnetB=subnet-yyyyyyyy \
    AlertEmail=your@email.com
```

## Key Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `Stage` | `dev` | Environment name (used in all resource names) |
| `ECRImageUri` | — | Full ECR image URI with tag (e.g. `123456789012.dkr.ecr.us-east-1.amazonaws.com/techpulse-lambda:abc1234`) |
| `DBMasterUsername` | `postgres` | RDS master username |
| `DBMasterPassword` | — | RDS master password (min 8 chars) |
| `LLMBackend` | `bedrock` | `bedrock` (default) / `huggingface` / `ollama` |
| `HFApiToken` | — | HuggingFace Inference API token |
| `HFModelId` | `mistralai/Mistral-7B-Instruct-v0.2` | HuggingFace model ID |
| `DefaultVpcId` | — | Default VPC ID |
| `DefaultSubnetA/B` | — | Two subnets in different AZs |
| `DBAllowedCidrIp` | `0.0.0.0/0` | CIDR allowed to reach RDS on port 5432 — set to your IP/32 |
| `AlertEmail` | — | Email for SNS notifications (optional) |

## Project Structure

```
infra/
├── template-freetier.yaml   # Active SAM template (Free Tier — container images, RDS db.t3.micro, IAM role created)
├── template.yaml            # Production SAM template (Aurora Serverless v2) — reference only
├── samconfig-freetier.toml  # SAM config for Free Tier manual deploys
├── README.md                # This file
└── cdk/                     # CDK reference implementation (not used in CI/CD)
    ├── app.py
    ├── cdk.json
    ├── pyproject.toml
    └── stacks/
        ├── network_stack.py
        ├── storage_stack.py
        ├── database_stack.py
        ├── compute_stack.py
        └── observability_stack.py
```
