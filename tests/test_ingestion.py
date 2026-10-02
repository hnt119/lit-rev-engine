import json

import fitz
import pytest

import main as pipeline
from src.chunking.chunker import chunk_text
from src.settings import Settings
from src.vectorstore.chroma_store import VectorStore


class FakeEmbedder:
    def chunk_text(self, text, chunk_size, overlap):
        return chunk_text(text, chunk_size=chunk_size, overlap=overlap)

    def embed_chunks(self, chunks):
        return [{**chunk, "embedding": [1.0, 0.0]} for chunk in chunks]


def make_pdf(path, pages):
    with fitz.open() as doc:
        for text in pages:
            doc.new_page().insert_text((72, 72), text)
        doc.save(path)


def test_fresh_ingestion_is_repeatable_and_retains_provenance(monkeypatch, tmp_path):
    config = Settings(
        data_directory=tmp_path / "data", embedding_model="test-model",
        chunk_size=10, chunk_overlap=2, max_search_results=7,
        chroma_collection="test_chunks",
    )
    pdf_dir = config.data_directory / "pdfs"
    pdf_dir.mkdir(parents=True)
    pdf = pdf_dir / "2501.12345v1.pdf"
    make_pdf(pdf, ["Introduction\nFirst page evidence.", "Results\nSecond page evidence."])
    paper = {
        "title": "Example study", "authors": ["A Researcher"], "published": "2025-01-01",
        "entry_id": "https://arxiv.org/abs/2501.12345v1",
        "pdf_url": "https://arxiv.org/pdf/2501.12345v1",
    }
    def search(query, max_results):
        assert query == "medical topic" and max_results == 7
        return [paper]
    monkeypatch.setattr(pipeline, "search_arxiv", search)
    monkeypatch.setattr(pipeline, "download_many", lambda *a, **kw: [str(pdf)])
    store = VectorStore(
        str(config.chroma_path), collection_name=config.chroma_collection,
        model_name=config.embedding_model,
    )
    result = pipeline.ingest(" medical topic ", config, FakeEmbedder(), store)
    assert result == {"papers": 1, "chunks": 2}
    embedded = json.loads((config.data_directory / "embeddings/chunks_embedded.json").read_text())
    assert embedded[0]["title"] == paper["title"]
    assert embedded[0]["authors"] == "A Researcher"
    assert [chunk["page_number"] for chunk in embedded] == [1, 2]
    assert embedded[0]["entry_id"] == paper["entry_id"]
    make_pdf(pdf, ["Results\nUpdated evidence."])
    pipeline.ingest("medical topic", config, FakeEmbedder(), store)
    assert store.count() == 1
    assert "Updated evidence" in store.query([1.0, 0.0])[0]["text"]


def test_failed_or_empty_pdfs_do_not_load_model_or_change_index(monkeypatch, tmp_path):
    config = Settings(data_directory=tmp_path / "data")
    papers = [{
        "entry_id": f"https://arxiv.org/abs/{identifier}",
        "pdf_url": "https://example.com/paper.pdf", "title": identifier,
    } for identifier in ["broken", "empty"]]
    monkeypatch.setattr(pipeline, "search_arxiv", lambda *a, **kw: papers)
    monkeypatch.setattr(pipeline, "download_many", lambda *a, **kw: ["broken.pdf", "empty.pdf"])
    def parse(path):
        if path == "broken.pdf":
            raise ValueError("invalid PDF")
        return {"text": "", "pages": []}
    monkeypatch.setattr(pipeline, "parse_pdf", parse)
    monkeypatch.setattr(pipeline, "Embedder", lambda **kw: pytest.fail("model loaded"))
    monkeypatch.setattr(pipeline, "VectorStore", lambda **kw: pytest.fail("index modified"))
    assert pipeline.ingest("topic", config) == {"papers": 0, "chunks": 0}


def test_empty_search_does_not_download_or_embed(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "search_arxiv", lambda *a, **kw: [])
    monkeypatch.setattr(pipeline, "download_many", lambda *a, **kw: pytest.fail("download called"))
    assert pipeline.ingest("topic", Settings(data_directory=tmp_path)) == {"papers": 0, "chunks": 0}


def test_empty_query_is_rejected_before_search(monkeypatch):
    monkeypatch.setattr(pipeline, "search_arxiv", lambda *a, **kw: pytest.fail("search called"))
    with pytest.raises(ValueError, match="empty"):
        pipeline.ingest("   ")
