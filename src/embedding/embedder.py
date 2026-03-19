"""MiniLM embedding generator for TechPulse.

Loads the sentence-transformer model and provides batch
embedding functionality for document chunks.
"""

import logging

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

_model = None


def get_model() -> SentenceTransformer:
    """Lazy-load the embedding model (singleton)."""
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", MODEL_NAME)
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a list of text strings.

    Returns:
        List of 384-dim float vectors.
    """
    model = get_model()
    embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
    return embeddings.tolist()


def embed_query(query: str) -> list[float]:
    """Embed a single query string."""
    return embed_texts([query])[0]
