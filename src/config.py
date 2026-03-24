"""Centralized configuration loaded from environment / .env file."""

import os
from dotenv import load_dotenv

load_dotenv()


class _Settings:
    """Read-only settings from environment variables."""

    @property
    def DB_HOST(self) -> str:
        return os.getenv("DB_HOST", "localhost")

    @property
    def DB_PORT(self) -> int:
        return int(os.getenv("DB_PORT", "5432"))

    @property
    def DB_NAME(self) -> str:
        return os.getenv("DB_NAME", "techpulse")

    @property
    def DB_USER(self) -> str:
        return os.getenv("DB_USER", "postgres")

    @property
    def DB_PASSWORD(self) -> str:
        val = os.getenv("DB_PASSWORD")
        if not val:
            raise EnvironmentError("DB_PASSWORD environment variable is required")
        return val

    @property
    def AWS_REGION(self) -> str:
        return os.getenv("AWS_REGION", "ap-southeast-1")

    @property
    def S3_BUCKET_NAME(self) -> str:
        return os.getenv("S3_BUCKET_NAME", "techpulse-data")

    @property
    def LLM_BACKEND(self) -> str:
        return os.getenv("LLM_BACKEND", "ollama")

    @property
    def OLLAMA_BASE_URL(self) -> str:
        return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    @property
    def OLLAMA_MODEL(self) -> str:
        return os.getenv("OLLAMA_MODEL", "llama3.2:3b")

    @property
    def BEDROCK_MODEL_ID(self) -> str:
        return os.getenv("BEDROCK_MODEL_ID", "amazon.nova-micro-v1:0")

    @property
    def HF_API_TOKEN(self) -> str:
        return os.getenv("HF_API_TOKEN", "")

    @property
    def HF_MODEL_ID(self) -> str:
        return os.getenv("HF_MODEL_ID", "mistralai/Mistral-7B-Instruct-v0.2")

    @property
    def GROQ_API_KEY(self) -> str:
        return os.getenv("GROQ_API_KEY", "")

    @property
    def GROQ_MODEL_ID(self) -> str:
        return os.getenv("GROQ_MODEL_ID", "llama-3.1-8b-instant")

    @property
    def GROQ_EVAL_MODEL_ID(self) -> str:
        """Larger model used as RAGAS LLM judge (free on Groq)."""
        return os.getenv("GROQ_EVAL_MODEL_ID", "llama-3.3-70b-versatile")

    @property
    def GEMINI_API_KEY(self) -> str:
        return os.getenv("GEMINI_API_KEY", "")

    @property
    def GITHUB_TOKEN(self) -> str:
        return os.getenv("GITHUB_TOKEN", "")

    @property
    def ARXIV_CATEGORIES(self) -> str:
        return os.getenv("ARXIV_CATEGORIES", "cs.AI,cs.LG,cs.CL,cs.IR,cs.SE")

    @property
    def ARXIV_MAX_RESULTS(self) -> int:
        return int(os.getenv("ARXIV_MAX_RESULTS", "100"))

    @property
    def HN_FETCH_LIMIT(self) -> int:
        return int(os.getenv("HN_FETCH_LIMIT", "50"))

    @property
    def TOP_K(self) -> int:
        return int(os.getenv("TOP_K", "5"))

    @property
    def CHUNK_SIZE_TOKENS(self) -> int:
        return int(os.getenv("CHUNK_SIZE_TOKENS", "500"))

    @property
    def CHUNK_OVERLAP_TOKENS(self) -> int:
        return int(os.getenv("CHUNK_OVERLAP_TOKENS", "50"))

    @property
    def RERANK_ALPHA(self) -> float:
        return float(os.getenv("RERANK_ALPHA", "0.6"))

    @property
    def RERANK_BETA(self) -> float:
        return float(os.getenv("RERANK_BETA", "0.2"))

    @property
    def RERANK_GAMMA(self) -> float:
        return float(os.getenv("RERANK_GAMMA", "0.2"))

    @property
    def RECENCY_LAMBDA(self) -> float:
        return float(os.getenv("RECENCY_LAMBDA", "0.01"))

    @property
    def DEVTO_TAGS(self) -> str:
        return os.getenv("DEVTO_TAGS", "machinelearning,ai,python,programming,devops,mlops,webdev,cloud,javascript,opensource,security,database,docker,kubernetes,react,node,rust,golang,datascience,blockchain,api")

    @property
    def DEVTO_PER_PAGE(self) -> int:
        return int(os.getenv("DEVTO_PER_PAGE", "30"))

    @property
    def S3_ENABLED(self) -> bool:
        return os.getenv("S3_ENABLED", "false").lower() in ("1", "true")

    @property
    def SQS_ENABLED(self) -> bool:
        return os.getenv("SQS_ENABLED", "false").lower() in ("1", "true")

    @property
    def SQS_QUEUE_URL(self) -> str:
        return os.getenv("SQS_QUEUE_URL", "")

    @property
    def CLOUDWATCH_ENABLED(self) -> bool:
        return os.getenv("CLOUDWATCH_ENABLED", "false").lower() in ("1", "true")

    @property
    def CITATION_GROUNDING_THRESHOLD(self) -> float:
        return float(os.getenv("CITATION_GROUNDING_THRESHOLD", "0.0"))

    @property
    def LLM_MAX_TOKENS(self) -> int:
        return int(os.getenv("LLM_MAX_TOKENS", "300"))

    @property
    def MONTHLY_BUDGET_USD(self) -> float:
        return float(os.getenv("MONTHLY_BUDGET_USD", "15"))

    @property
    def BUDGET_HALT_ENABLED(self) -> bool:
        return os.getenv("BUDGET_HALT_ENABLED", "false").lower() in ("1", "true")


settings = _Settings()


def _validate_settings() -> None:
    total = settings.RERANK_ALPHA + settings.RERANK_BETA + settings.RERANK_GAMMA
    if abs(total - 1.0) > 1e-6:
        raise ValueError(
            f"RERANK_ALPHA + RERANK_BETA + RERANK_GAMMA must sum to 1.0, got {total:.4f}. "
            f"Current values: RERANK_ALPHA={settings.RERANK_ALPHA}, "
            f"RERANK_BETA={settings.RERANK_BETA}, RERANK_GAMMA={settings.RERANK_GAMMA}"
        )


_validate_settings()
