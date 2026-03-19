"""Tests for src/embedding/embedder.py — embedding model abstraction."""

import sys
from unittest.mock import MagicMock, patch
import numpy as np


# ---------------------------------------------------------------------------
# get_model
# ---------------------------------------------------------------------------

def test_get_model_creates_singleton():
    # Create a fake sentence_transformers module so the lazy import works
    # even when the real package isn't installed (CI).
    fake_st = MagicMock()
    mock_cls = fake_st.SentenceTransformer
    mock_model = MagicMock()
    mock_cls.return_value = mock_model

    with patch.dict(sys.modules, {"sentence_transformers": fake_st}):
        import src.embedding.embedder as emb_mod
        emb_mod._model = None  # reset singleton

        result = emb_mod.get_model()
        assert result == mock_model
        mock_cls.assert_called_once_with("all-MiniLM-L6-v2")


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
    mock_model.encode.return_value = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
    mock_get_model.return_value = mock_model

    from src.embedding.embedder import embed_texts
    result = embed_texts(["hello", "world"])

    assert len(result) == 2
    assert result[0] == [0.1, 0.2, 0.3]
    mock_model.encode.assert_called_once_with(
        ["hello", "world"], show_progress_bar=False, normalize_embeddings=True
    )


# ---------------------------------------------------------------------------
# embed_query
# ---------------------------------------------------------------------------

@patch("src.embedding.embedder.embed_texts", return_value=[[0.1, 0.2, 0.3]])
def test_embed_query(mock_embed):
    from src.embedding.embedder import embed_query
    result = embed_query("test query")
    assert result == [0.1, 0.2, 0.3]
    mock_embed.assert_called_once_with(["test query"])
