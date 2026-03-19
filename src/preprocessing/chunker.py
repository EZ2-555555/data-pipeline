"""Text preprocessing and chunking for TechPulse.

Handles HTML stripping, normalization, and token-based chunking
with configurable window size and overlap.
"""

import html
import re
import logging

import tiktoken

from src.config import settings

logger = logging.getLogger(__name__)

# Use cl100k_base tokenizer (GPT-4 / general purpose)
_encoder = tiktoken.get_encoding("cl100k_base")


def normalize_text(text: str) -> str:
    """Strip HTML, code blocks, URLs, markdown, emojis, and normalize whitespace."""
    # Unescape HTML entities
    text = html.unescape(text)
    # Remove HTML comments (before tag removal so <!-- --> don't leave residue)
    text = re.sub(r"<!--[\s\S]*?-->", " ", text)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Remove fenced code blocks (```lang ... ```)
    text = re.sub(r"```[\s\S]*?```", " ", text)
    # Remove inline code (`...`)
    text = re.sub(r"`[^`]+`", " ", text)
    # Remove markdown image/link syntax: ![alt](url) or [text](url)
    text = re.sub(r"!?\[[^\]]*\]\([^)]*\)", " ", text)
    # Remove URLs (http/https/ftp)
    text = re.sub(r"https?://\S+|ftp://\S+", " ", text)
    # Remove markdown headings (## ...), bold/italic markers
    text = re.sub(r"#{1,6}\s*", " ", text)
    text = re.sub(r"\*{1,3}|_{1,3}", "", text)
    # Remove markdown strikethrough (~~text~~)
    text = re.sub(r"~~(.*?)~~", r"\1", text)
    # Remove markdown horizontal rules (--- or ***)
    text = re.sub(r"^[\-\*_]{3,}\s*$", " ", text, flags=re.MULTILINE)
    # Remove markdown blockquote markers
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    # Remove emojis and pictographic symbols
    text = re.sub(
        r"["
        r"\U0001F600-\U0001F64F"  # emoticons
        r"\U0001F300-\U0001F5FF"  # misc symbols & pictographs
        r"\U0001F680-\U0001F6FF"  # transport & map
        r"\U0001F900-\U0001F9FF"  # supplemental symbols
        r"\U0001FA00-\U0001FAFF"  # symbols extended-A
        r"\U0001F1E0-\U0001F1FF"  # flags (regional indicators)
        r"\U00002600-\U000027BF"  # misc symbols & dingbats
        r"\U0000FE00-\U0000FE0F"  # variation selectors
        r"]+",
        " ", text,
    )
    # Remove Unicode control characters, zero-width chars, BOM
    text = re.sub(
        r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f"
        r"\u200b-\u200f\u2028-\u202f\ufeff\u2060-\u2069]",
        "", text,
    )
    # Collapse repeated punctuation (e.g. !!! → !, ??? → ?)
    text = re.sub(r"([!?.]){3,}", r"\1", text)
    # Normalize unicode whitespace
    text = text.replace("\xa0", " ")
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[str]:
    """Split text into token-based chunks with overlap.

    Args:
        text: Normalized input text.
        chunk_size: Tokens per chunk (default from settings).
        overlap: Token overlap between chunks (default from settings).

    Returns:
        List of chunk strings.
    """
    if chunk_size is None:
        chunk_size = settings.CHUNK_SIZE_TOKENS
    if overlap is None:
        overlap = settings.CHUNK_OVERLAP_TOKENS

    tokens = _encoder.encode(text)

    if len(tokens) <= chunk_size:
        return [text.strip()]

    chunks = []
    start = 0
    while start < len(tokens):
        end = start + chunk_size
        chunk_tokens = tokens[start:end]
        chunk_str = _encoder.decode(chunk_tokens)
        chunks.append(chunk_str)

        start += chunk_size - overlap

    return chunks
