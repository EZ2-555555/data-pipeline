"""MiniLM embedding generator for TechPulse.

Uses fastembed (ONNX Runtime) for lightweight, local embeddings.
Deployed via container image to bypass Lambda's 250 MB zip limit.
Model is pre-downloaded at Docker build time (see Dockerfile.lambda).
"""

import logging
import os
import threading

from fastembed import TextEmbedding

logger = logging.getLogger(__name__)

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

_model: TextEmbedding | None = None
_model_lock = threading.Lock()


def get_model() -> TextEmbedding:
    """Lazy-load the embedding model (singleton)."""
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            logger.info("Loading embedding model: %s", MODEL_NAME)
            cache_dir = os.environ.get("FASTEMBED_CACHE_PATH")
            kwargs = {"model_name": MODEL_NAME}
            if cache_dir:
                kwargs["cache_dir"] = cache_dir
            _model = TextEmbedding(**kwargs)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a list of text strings.

    Returns:
        List of 384-dim float vectors.
    """
    import signal
    
    def timeout_handler(signum, frame):
        raise TimeoutError("Embedding operation exceeded 60-second timeout")
    
    # Set timeout (disabled on Windows; use signal.alarm only on Unix)
    old_handler = None
    if hasattr(signal, 'SIGALRM'):
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(60)
    
    try:
        model = get_model()
        embeddings = list(model.embed(texts))
        return [e.tolist() for e in embeddings]
    finally:
        if hasattr(signal, 'SIGALRM') and old_handler is not None:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)


def embed_query(query: str) -> list[float]:
    """Embed a single query string."""
    return embed_texts([query])[0]
