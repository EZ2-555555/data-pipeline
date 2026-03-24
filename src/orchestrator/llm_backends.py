"""LLM backend abstraction for TechPulse.

Supports Bedrock, Ollama, and HuggingFace Inference API.
Controlled by the LLM_BACKEND environment variable.
"""

import json
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
MAX_RETRIES = 2
BACKOFF_BASE_S = 2.0  # exponential: 2s, 4s


# Fallback order: primary → next tier → last tier
_FALLBACK_CHAIN = {
    "bedrock": ["ollama", "huggingface"],
    "ollama": ["huggingface"],
    "huggingface": ["ollama"],
}

_BACKENDS = {
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


def _generate_bedrock(prompt: str, max_tokens: int) -> str:
    """Call Amazon Bedrock."""
    if boto3 is None:
        raise RuntimeError("boto3 is required for the 'bedrock' backend")

    client = boto3.client("bedrock-runtime", region_name=settings.AWS_REGION)
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    })
    response = client.invoke_model(
        modelId=settings.BEDROCK_MODEL_ID,
        body=body,
        contentType="application/json",
        accept="application/json",
    )
    result = json.loads(response["body"].read())
    return result["content"][0]["text"]


def _generate_huggingface(prompt: str, max_tokens: int) -> str:
    """Call HuggingFace Inference API with retry/backoff."""
    last_exc: Exception | None = None
    for attempt in range(1 + MAX_RETRIES):
        try:
            resp = requests.post(
                f"https://api-inference.huggingface.co/models/{settings.HF_MODEL_ID}",
                headers={"Authorization": f"Bearer {settings.HF_API_TOKEN}"},
                json={
                    "inputs": prompt,
                    "parameters": {"max_new_tokens": max_tokens, "temperature": 0.2, "return_full_text": False},
                },
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()[0]["generated_text"]
        except (requests.RequestException, KeyError, IndexError) as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                delay = BACKOFF_BASE_S * (2 ** attempt)
                logger.warning("HuggingFace attempt %d failed (%s), retrying in %.1fs", attempt + 1, exc, delay)
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]
