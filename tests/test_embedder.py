"""Tests for src/embedding/embedder.py — fastembed-based embeddings."""

from unittest.mock import MagicMock, patch
import numpy as np


# ---------------------------------------------------------------------------
# get_model
# ---------------------------------------------------------------------------

@patch("src.embedding.embedder.TextEmbedding")
def test_get_model_creates_singleton(mock_cls):
    import src.embedding.embedder as emb_mod
    emb_mod._model = None  # reset singleton

    mock_instance = MagicMock()
    mock_cls.return_value = mock_instance

    result = emb_mod.get_model()
    assert result == mock_instance
    mock_cls.assert_called_once_with(model_name="sentence-transformers/all-MiniLM-L6-v2")


def test_get_model_reuses_existing():
    import src.embedding.embedder as emb_mod
    existing = MagicMock()
    emb_mod._model = existing

    result = emb_mod.get_model()
    assert result == existing


# ---------------------------------------------------------------------------
# embed_texts
# ---------------------------------------------------------------------------

@patch("src.embedding.embedder.get_model")
def test_embed_texts(mock_get_model):
    mock_model = MagicMock()
    mock_model.embed.return_value = iter([
        np.array([0.1, 0.2, 0.3]),
        np.array([0.4, 0.5, 0.6]),
    ])
    mock_get_model.return_value = mock_model

    from src.embedding.embedder import embed_texts
    result = embed_texts(["hello", "world"])

    assert len(result) == 2
    assert result[0] == [0.1, 0.2, 0.3]
    assert result[1] == [0.4, 0.5, 0.6]
    mock_model.embed.assert_called_once_with(["hello", "world"])


# ---------------------------------------------------------------------------
# embed_query
# ---------------------------------------------------------------------------

@patch("src.embedding.embedder.embed_texts", return_value=[[0.1, 0.2, 0.3]])
def test_embed_query(mock_embed):
    from src.embedding.embedder import embed_query
    result = embed_query("test query")
    assert result == [0.1, 0.2, 0.3]
    mock_embed.assert_called_once_with(["test query"])
