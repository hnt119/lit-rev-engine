import pytest

from src.vectorstore.chroma_store import VectorStore


def chunk(paper, identifier, text="evidence", page=1):
    return {
        "paper_id": paper, "chunk_id": identifier, "text": text,
        "embedding": [1.0, 0.0], "title": "Study title", "page_number": page,
    }


@pytest.fixture
def store(tmp_path):
    return VectorStore(str(tmp_path / "chroma"), model_name="test-model")


def test_reingestion_updates_chunks_removes_stale_and_preserves_other_papers(store, monkeypatch):
    monkeypatch.setattr(store.client, "get_max_batch_size", lambda: 1)
    store.add_chunks([chunk("paper-a", 0), chunk("paper-a", 1), chunk("paper-b", 0)])
    store.add_chunks([chunk("paper-a", 0, text="updated evidence", page=2)])
    assert store.count() == 2
    hits = store.query([1.0, 0.0], k=20)
    by_paper = {hit["paper_id"]: hit for hit in hits}
    assert by_paper["paper-a"]["text"] == "updated evidence"
    assert by_paper["paper-a"]["page_number"] == 2
    assert by_paper["paper-a"]["title"] == "Study title"
    assert "paper-b" in by_paper
    store.add_chunks([chunk("paper-a", 0, text="updated evidence", page=2)])
    assert store.count() == 2


def test_empty_ingestion_and_query_are_safe(store):
    assert store.add_chunks([]) == 0
    assert store.query([1.0, 0.0]) == []


@pytest.mark.parametrize("k", [0, -1, True, 1.5])
def test_invalid_retrieval_count_is_rejected(store, k):
    with pytest.raises(ValueError, match="positive integer"):
        store.query([1.0, 0.0], k=k)


def test_duplicate_input_is_rejected_before_writing(store):
    with pytest.raises(ValueError, match="Duplicate chunk ID"):
        store.add_chunks([chunk("paper-a", 0), chunk("paper-a", 0)])
    assert store.count() == 0


def test_changing_embedding_model_requires_separate_collection(tmp_path):
    path = str(tmp_path / "chroma")
    first = VectorStore(path, model_name="model-one")
    first.add_chunks([chunk("paper-a", 0)])
    with pytest.raises(ValueError, match="new collection"):
        VectorStore(path, model_name="model-two")
