"""LLM backend abstraction for TechPulse.

Supports Groq, Bedrock, Ollama, and HuggingFace Inference API.
Controlled by the LLM_BACKEND environment variable.
"""

import logging
import time

import requests

try:
    import boto3
except ImportError:
    boto3 = None

from src.config import settings

logger = logging.getLogger(__name__)

# Retry configuration for Ollama / HuggingFace
MAX_RETRIES = 4
BACKOFF_BASE_S = 3.0  # exponential: 3s, 6s, 12s, 24s


# Fallback order: primary → next tier → last tier
_FALLBACK_CHAIN = {
    "groq": ["bedrock", "ollama", "huggingface"],
    "bedrock": ["groq", "ollama", "huggingface"],
    "ollama": ["groq", "huggingface"],
    "huggingface": ["groq", "ollama"],
}

_BACKENDS = {
    "groq": lambda p, t: _generate_groq(p, t),
    "ollama": lambda p, t: _generate_ollama(p, t),
    "bedrock": lambda p, t: _generate_bedrock(p, t),
    "huggingface": lambda p, t: _generate_huggingface(p, t),
}


def generate(prompt: str, max_tokens: int | None = None) -> str:
    """Route generation to the configured backend with automatic fallback."""
    if max_tokens is None:
        max_tokens = settings.LLM_MAX_TOKENS
    primary = settings.LLM_BACKEND

    if primary not in _BACKENDS:
        raise ValueError(f"Unknown LLM_BACKEND: {primary}")

    chain = [primary] + _FALLBACK_CHAIN.get(primary, [])
    errors: dict[str, str] = {}

    for backend in chain:
        try:
            return _BACKENDS[backend](prompt, max_tokens)
        except Exception as exc:
            errors[backend] = str(exc)
            logger.warning("Backend '%s' failed (%s), trying next fallback", backend, exc)

    error_summary = "; ".join(f"{b}: {e}" for b, e in errors.items())
    raise RuntimeError(f"All LLM backends failed — {error_summary}")


def _generate_ollama(prompt: str, max_tokens: int) -> str:
    """Call local Ollama instance with retry/backoff."""
    last_exc: Exception | None = None
    for attempt in range(1 + MAX_RETRIES):
        try:
            resp = requests.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": settings.OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": max_tokens, "temperature": 0.2, "num_ctx": 4096},
                },
                timeout=300,
            )
            resp.raise_for_status()
            return resp.json()["response"]
        except (requests.RequestException, KeyError) as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                delay = BACKOFF_BASE_S * (2 ** attempt)
                logger.warning("Ollama attempt %d failed (%s), retrying in %.1fs", attempt + 1, exc, delay)
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]


def _generate_groq(prompt: str, max_tokens: int) -> str:
    """Call Groq API (OpenAI-compatible)."""
    api_key = settings.GROQ_API_KEY
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required for the 'groq' backend")

    last_exc: Exception | None = None
    for attempt in range(1 + MAX_RETRIES):
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": settings.GROQ_MODEL_ID,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0.2,
                },
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except (requests.RequestException, KeyError, IndexError) as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                delay = BACKOFF_BASE_S * (2 ** attempt)
                logger.warning("Groq attempt %d failed (%s), retrying in %.1fs", attempt + 1, exc, delay)
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]


def _generate_bedrock(prompt: str, max_tokens: int) -> str:
    """Call Amazon Bedrock using the model-agnostic Converse API."""
    if boto3 is None:
        raise RuntimeError("boto3 is required for the 'bedrock' backend")

    client = boto3.client("bedrock-runtime", region_name=settings.AWS_REGION)
    response = client.converse(
        modelId=settings.BEDROCK_MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0.2},
    )
    return response["output"]["message"]["content"][0]["text"]


def _generate_huggingface(prompt: str, max_tokens: int) -> str:
    """Call HuggingFace Inference API (router) with retry/backoff."""
    last_exc: Exception | None = None
    for attempt in range(1 + MAX_RETRIES):
        try:
            resp = requests.post(
                f"https://router.huggingface.co/hf-inference/models/{settings.HF_MODEL_ID}/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.HF_API_TOKEN}", "Content-Type": "application/json"},
                json={
                    "model": settings.HF_MODEL_ID,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0.2,
                },
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except (requests.RequestException, KeyError, IndexError) as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                delay = BACKOFF_BASE_S * (2 ** attempt)
                logger.warning("HuggingFace attempt %d failed (%s), retrying in %.1fs", attempt + 1, exc, delay)
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]
