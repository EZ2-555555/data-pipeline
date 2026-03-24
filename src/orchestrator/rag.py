"""RAG orchestrator for TechPulse.

Combines retrieval results with a structured prompt and dispatches
to the configured LLM backend (Bedrock / Ollama / HuggingFace).

Implements a three-layer hallucination verification strategy:
  Layer 1 — Prompt-level: system instruction enforces evidence grounding.
  Layer 2 — Evaluation-layer: RAGAS faithfulness (see evaluation/run_eval.py).
  Layer 3 — Output-layer: citation traceability check (this module).
"""

import logging
import re

import tiktoken

try:
    import boto3
except ImportError:
    boto3 = None

from src.retrieval.retriever import baseline_retrieve, hybrid_retrieve
from src.orchestrator.llm_backends import generate
from src.config import settings

logger = logging.getLogger(__name__)

# Tokenizer for cost estimation (cl100k_base is a reasonable proxy)
_ENC = tiktoken.get_encoding("cl100k_base")

# ---------------------------------------------------------------------------
# Hallucination verification config
# ---------------------------------------------------------------------------
# Minimum ratio of sentences that must contain a [Source N] citation.
# Responses below this threshold are flagged as potentially hallucinated.
# Default 0.0 for local dev (small models can't reliably cite); set higher
# (e.g. 0.5) in production with capable models.
# NOTE: Read dynamically via settings.CITATION_GROUNDING_THRESHOLD at call
# time so env-var changes are picked up without process restart.
# Regex matching citation tags the model is instructed to produce.
_CITATION_RE = re.compile(r"\[Source\s+\d+\]")

SYSTEM_PROMPT = """You are TechPulse, a technology intelligence assistant powered by a real-time corpus of research papers, developer articles, GitHub projects, and tech news.

RULES:
1. Answer using the provided context documents as your primary evidence.
2. For each specific claim, cite the source in [Source N] format.
3. If the context documents cover related or adjacent topics, synthesize insights from them and clearly note what is directly evidenced vs. inferred.
4. Only say you cannot answer if NO context documents are even tangentially relevant.
5. Keep answers concise but substantive — prefer 3-5 key insights with citations.
6. Do NOT speculate beyond what the documents support."""

ABSTENTION_MESSAGE = (
    "The system could not produce a sufficiently grounded response for this query. "
    "Please try rephrasing or narrowing your question."
)

BUDGET_HALT_MESSAGE = (
    "The system has temporarily paused generative responses because the monthly "
    "cost threshold has been reached. Retrieval-only results are shown below."
)

LLM_FALLBACK_MESSAGE = (
    "The language model is temporarily unavailable. "
    "Below are the most relevant sources retrieved for your query."
)


# ---------------------------------------------------------------------------
# Budget guard — programmatic halt when monthly cost >= threshold
# ---------------------------------------------------------------------------
def _check_budget_exceeded() -> bool:
    """Query AWS Cost Explorer for current month spend.

    Returns True if actual spend >= MONTHLY_BUDGET_USD, halting LLM
    invocation to prevent cost overruns.  Disabled when
    BUDGET_HALT_ENABLED is false (default for local dev).
    """
    if not settings.BUDGET_HALT_ENABLED:
        return False
    if boto3 is None:
        logger.debug("boto3 not available — skipping budget check")
        return False
    try:
        from datetime import date as _date, timedelta
        ce = boto3.client("ce", region_name=settings.AWS_REGION)
        today = _date.today()
        start = today.replace(day=1).isoformat()
        end = (today + timedelta(days=1)).isoformat()
        resp = ce.get_cost_and_usage(
            TimePeriod={"Start": start, "End": end},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
        )
        amount = float(
            resp["ResultsByTime"][0]["Total"]["UnblendedCost"]["Amount"]
        )
        if amount >= settings.MONTHLY_BUDGET_USD:
            logger.warning(
                "Budget guard triggered: $%.2f spent >= $%.2f limit",
                amount, settings.MONTHLY_BUDGET_USD,
            )
            return True
    except Exception as exc:
        logger.debug("Budget check unavailable (%s), proceeding.", exc)
    return False


# ---------------------------------------------------------------------------
# Layer 3: Citation traceability check
# ---------------------------------------------------------------------------
def _check_citation_grounding(answer: str, num_sources: int) -> dict:
    """Verify that the generated answer is grounded via citation traceability.

    Splits the answer into sentences and checks what fraction contain a
    valid [Source N] reference (where N ≤ num_sources).  Returns a dict
    with grounding metadata used for downstream flagging.
    """
    # Split on sentence-ending punctuation (keep it simple / robust)
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', answer) if s.strip()]
    if not sentences:
        return {"grounded": False, "citation_ratio": 0.0, "flagged": True}

    cited_count = 0
    for sent in sentences:
        if _CITATION_RE.search(sent):
            cited_count += 1

    citation_ratio = cited_count / len(sentences)
    threshold = settings.CITATION_GROUNDING_THRESHOLD
    flagged = citation_ratio < threshold

    # Also check for hallucinated source indices (e.g. [Source 12] when only 5 sources)
    all_cited_ids = [int(m) for m in re.findall(r"\[Source\s+(\d+)\]", answer)]
    invalid_refs = [sid for sid in all_cited_ids if sid < 1 or sid > num_sources]

    if invalid_refs:
        flagged = True
        logger.warning(
            "Hallucination flag: answer references non-existent sources %s (max=%d)",
            invalid_refs, num_sources,
        )

    return {
        "grounded": not flagged,
        "citation_ratio": round(citation_ratio, 3),
        "total_sentences": len(sentences),
        "cited_sentences": cited_count,
        "invalid_source_refs": invalid_refs,
        "flagged": flagged,
    }


def _build_context_block(results: list[dict]) -> str:
    """Format retrieved chunks into a numbered context block."""
    parts = []
    for i, r in enumerate(results, 1):
        source_label = f"[Source {i}] {r['title']} ({r['source'].upper()})"
        parts.append(f"{source_label}\n{r['chunk_text']}\n")
    return "\n".join(parts)


def _build_prompt(query: str, context: str) -> str:
    """Assemble the full structured prompt."""
    return f"""SYSTEM:
{SYSTEM_PROMPT}

CONTEXT:
{context}

QUESTION:
{query}

INSTRUCTION:
Provide a concise answer and cite supporting sources using [Source N] format."""


def _count_tokens(text: str) -> int:
    """Count tokens using tiktoken (cl100k_base encoding)."""
    return len(_ENC.encode(text))


def _estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate per-query cost in USD. Ollama / HF = $0 (self-hosted / free tier)."""
    backend = settings.LLM_BACKEND
    if backend in ("ollama", "huggingface"):
        return 0.0
    # Amazon Nova Micro pricing (rough: $0.035 / 1M input, $0.14 / 1M output)
    return (prompt_tokens * 0.035 + completion_tokens * 0.14) / 1_000_000


def ask(query: str, mode: str = "hybrid", sources: list[str] | None = None) -> dict:
    """Run the full RAG pipeline: retrieve → prompt → generate.

    Args:
        query: User's natural language question.
        mode: 'baseline' for vector-only, 'hybrid' for full pipeline.
        sources: Optional list of source types to filter (e.g. ['arxiv', 'hn']).

    Returns:
        Dict with 'answer', 'sources', 'mode', and 'hallucination_check'.
        If citation grounding fails, the answer is replaced with an
        abstention message and 'hallucination_check.flagged' is True.
    """
    if mode == "baseline":
        results = baseline_retrieve(query)
    else:
        results = hybrid_retrieve(query, sources=sources)

    if not results:
        return {
            "answer": "Insufficient evidence to answer this question.",
            "sources": [],
            "mode": mode,
            "hallucination_check": {"grounded": True, "flagged": False},
        }

    context = _build_context_block(results)

    # Budget guard: halt LLM invocation when cost threshold reached
    if _check_budget_exceeded():
        return {
            "answer": BUDGET_HALT_MESSAGE,
            "sources": [{"title": r["title"], "source": r["source"], "url": r.get("url", "")} for r in results],
            "mode": mode,
            "budget_halted": True,
            "hallucination_check": {"grounded": True, "flagged": False},
        }

    prompt = _build_prompt(query, context)

    # Graceful degradation: if LLM fails after retries, return retrieval-only
    try:
        answer = generate(prompt)
    except Exception as exc:
        logger.error("LLM generation failed (%s), falling back to retrieval-only", exc)
        return {
            "answer": LLM_FALLBACK_MESSAGE,
            "sources": [{"title": r["title"], "source": r["source"], "url": r.get("url", ""), "score": r["score"]} for r in results],
            "mode": mode,
            "llm_fallback": True,
            "llm_error": str(exc),
            "hallucination_check": {"grounded": True, "flagged": False},
        }

    # Layer 3: Citation traceability verification
    check = _check_citation_grounding(answer, num_sources=len(results))

    if check["flagged"]:
        logger.warning(
            "Hallucination flag: citation_ratio=%.2f (threshold=%.2f), "
            "invalid_refs=%s — returning abstention",
            check["citation_ratio"],
            settings.CITATION_GROUNDING_THRESHOLD,
            check.get("invalid_source_refs", []),
        )
        # Preserve the original answer for logging / evaluation, but serve
        # the abstention message to the user.
        check["original_answer"] = answer
        answer = ABSTENTION_MESSAGE

    # Token usage tracking
    prompt_tokens = _count_tokens(prompt)
    completion_tokens = _count_tokens(answer)
    token_usage = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "estimated_cost_usd": _estimate_cost(prompt_tokens, completion_tokens),
    }

    return {
        "answer": answer,
        "sources": [
            {"title": r["title"], "source": r["source"], "url": r["url"], "score": r["score"]}
            for r in results
        ],
        "mode": mode,
        "hallucination_check": check,
        "token_usage": token_usage,
    }
