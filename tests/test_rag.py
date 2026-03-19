"""Tests for the RAG orchestrator (citation grounding, prompt building)."""

from src.orchestrator.rag import _check_citation_grounding, _build_context_block


class TestCitationGrounding:
    def test_fully_cited(self):
        answer = "AI is great [Source 1]. ML is a subset [Source 2]."
        result = _check_citation_grounding(answer, num_sources=2)
        assert result["grounded"] is True
        assert result["citation_ratio"] == 1.0
        assert result["flagged"] is False

    def test_no_citations(self):
        answer = "AI is great. ML is a subset."
        result = _check_citation_grounding(answer, num_sources=2)
        assert result["citation_ratio"] == 0.0

    def test_invalid_source_ref(self):
        answer = "AI is great [Source 99]."
        result = _check_citation_grounding(answer, num_sources=2)
        assert result["flagged"] is True
        assert 99 in result["invalid_source_refs"]

    def test_empty_answer(self):
        result = _check_citation_grounding("", num_sources=1)
        assert result["grounded"] is False
        assert result["flagged"] is True

    def test_partial_citation(self):
        answer = "First claim [Source 1]. Second claim. Third claim [Source 2]."
        result = _check_citation_grounding(answer, num_sources=2)
        assert result["cited_sentences"] == 2
        assert result["total_sentences"] == 3


class TestBuildContextBlock:
    def test_formats_sources(self):
        results = [
            {"title": "Paper A", "source": "arxiv", "chunk_text": "Some text."},
            {"title": "Repo B", "source": "github", "chunk_text": "More text."},
        ]
        block = _build_context_block(results)
        assert "[Source 1] Paper A (ARXIV)" in block
        assert "[Source 2] Repo B (GITHUB)" in block
        assert "Some text." in block

    def test_empty_results(self):
        assert _build_context_block([]) == ""
