import math

import pytest

from src.rag.rag_assistant import RAGAssistant


class FakeSearcher:
    def __init__(self, sources=None):
        self.sources = sources if sources is not None else [{
            "paper_id": "2501.12345", "chunk_id": 4, "distance": 0.12,
            "text": "The study was limited by a small sample size and lacked external validation.",
            "title": "Example study", "page_number": 3,
        }]

    def search(self, query, top_k):
        return self.sources[:top_k]


class FakeGenerator:
    def __init__(self, response=None):
        self.called = False
        self.response = response or "The study had a small sample size [Source 1]."

    def generate(self, messages, **kwargs):
        self.called = True
        assert "[Source 1" in messages[1]["content"]
        return self.response


def test_rag_keeps_short_evidence_and_formats_source_locations():
    generator = FakeGenerator()
    assistant = RAGAssistant(searcher=FakeSearcher(), generator=generator)
    result = assistant.answer("What were the study limitations?", top_k=3)
    assert "[Source 1]" in result["answer"]
    assert result["sources"][0]["page_number"] == 3
    context = assistant._format_context(result["sources"])
    assert "Example study" in context and "PDF page=3" in context


def test_rag_respects_explicit_length_filter_without_calling_generator():
    generator = FakeGenerator()
    assistant = RAGAssistant(
        searcher=FakeSearcher(), generator=generator, min_source_words=80,
    )
    result = assistant.answer("Study limitations?")
    assert result["sources"] == []
    assert "No usable passages" in result["answer"]
    assert not generator.called


def test_no_sources_does_not_require_api_key(monkeypatch):
    monkeypatch.setattr(
        "src.rag.rag_assistant.AgnesGenerator",
        lambda **kw: pytest.fail("generator constructed without evidence"),
    )
    result = RAGAssistant(searcher=FakeSearcher([])).answer("Missing evidence?")
    assert result["sources"] == []


def test_rag_honors_top_k_without_three_source_cap():
    sources = [{
        "paper_id": f"paper-{i}", "chunk_id": 0, "distance": 0.1,
        "text": "Short but useful evidence.",
    } for i in range(5)]
    result = RAGAssistant(
        searcher=FakeSearcher(sources), generator=FakeGenerator(),
    ).answer("Compare studies", top_k=5)
    assert len(result["sources"]) == 5


@pytest.mark.parametrize("distance", [100.0, math.inf, math.nan])
def test_rag_filters_distance_without_calling_generator(distance):
    sources = FakeSearcher().sources
    sources[0]["distance"] = distance
    generator = FakeGenerator()
    result = RAGAssistant(
        searcher=FakeSearcher(sources), generator=generator, max_source_distance=0.5,
    ).answer("Study limitations?")
    assert not result["sources"]
    assert not generator.called


@pytest.mark.parametrize("answer", [
    "Invented result [Source 99].", "Uncited result.",
    "Invented result [Source 0].", "Result [Source 1, Source 2].",
    "Valid label [Source 1] but malformed [Source2].",
    "Valid label [Source 1] but unfinished [Source 2",
])
def test_rag_rejects_invalid_or_missing_citations(answer):
    with pytest.raises(RuntimeError, match="citation"):
        RAGAssistant(
            searcher=FakeSearcher(), generator=FakeGenerator(answer),
        ).answer("Study limitations?")


def test_rag_accepts_explicit_abstention():
    result = RAGAssistant(
        searcher=FakeSearcher(), generator=FakeGenerator("INSUFFICIENT_EVIDENCE"),
    ).answer("Unsupported question?")
    assert "enough evidence" in result["answer"]


def test_rag_rejects_empty_question():
    with pytest.raises(ValueError, match="empty"):
        RAGAssistant(searcher=FakeSearcher()).answer("   ")


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_rag_rejects_invalid_top_k(limit):
    with pytest.raises(ValueError, match="positive integer"):
        RAGAssistant(searcher=FakeSearcher()).answer("Question", top_k=limit)
