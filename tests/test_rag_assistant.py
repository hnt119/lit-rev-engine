from src.rag.rag_assistant import RAGAssistant


class FakeSearcher:
    def search(self, query: str, top_k: int):
        return [
            {
                "paper_id": "2501.12345",
                "chunk_id": 4,
                "distance": 0.12,
                "text": (
                    "The study was limited by a small sample size "
                    "and lacked external validation."
                ),
            }
        ]


class FakeGenerator:
    def generate(self, messages):
        assert "small sample size" in messages[1]["content"]
        return (
            "The study was limited by its small sample size and "
            "lack of external validation [Source 1]."
        )


def test_rag_assistant_retrieves_and_generates():
    assistant = RAGAssistant(
        searcher=FakeSearcher(),
        generator=FakeGenerator(),
    )

    result = assistant.answer(
        "What were the study limitations?",
        top_k=3,
    )

    assert "[Source 1]" in result["answer"]
    assert len(result["sources"]) == 1


def test_rag_assistant_rejects_empty_question():
    assistant = RAGAssistant(
        searcher=FakeSearcher(),
        generator=FakeGenerator(),
    )

    try:
        assistant.answer("   ")
        assert False, "Expected ValueError"
    except ValueError:
        assert True