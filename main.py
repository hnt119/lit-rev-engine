import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Dict

from src.download.pdf_downloader import download_many, paper_id
from src.embeddings.embedder import Embedder
from src.parser.pdf_parser import parse_pdf
from src.search.arxiv_search import search_arxiv
from src.settings import Settings, settings
from src.vectorstore.chroma_store import VectorStore


def save_json(path: Path, data) -> None:
    """Create parent directories and replace each snapshot only after writing it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def ingest(query: str, config: Settings = settings, embedder=None, store=None) -> Dict:
    query = query.strip()
    if not query:
        raise ValueError("Search query cannot be empty.")
    data_dir = Path(config.data_directory)
    papers = search_arxiv(query, max_results=config.max_search_results)
    print(f"Found {len(papers)} papers.")
    save_json(data_dir / "raw" / "arxiv_results.json", papers)
    if not papers:
        return {"papers": 0, "chunks": 0}

    by_id = {paper_id(paper): paper for paper in papers}
    paths = download_many(papers, save_dir=str(data_dir / "pdfs"))
    all_parsed, all_chunks = [], []
    for pdf_path in dict.fromkeys(paths):
        print(f"Processing: {pdf_path}")
        try:
            parsed = parse_pdf(pdf_path)
        except Exception as exc:
            # PDF libraries have several format-specific exception types.
            print(f"Failed to parse {pdf_path}: {exc}")
            continue
        if not parsed["text"].strip():
            print(f"Skipped {pdf_path}: no extractable text (OCR may be required).")
            continue
        if embedder is None:
            embedder = Embedder(model_name=config.embedding_model)
        identifier = Path(pdf_path).stem
        paper = by_id[identifier]
        all_parsed.append({**parsed, "paper_id": identifier, "metadata": paper})
        chunk_id = 0
        for page in parsed["pages"]:
            chunks = embedder.chunk_text(
                page["text"], chunk_size=config.chunk_size, overlap=config.chunk_overlap
            )
            for chunk in chunks:
                all_chunks.append({
                    **chunk,
                    "paper_id": identifier,
                    "chunk_id": chunk_id,
                    "page_number": page["page_number"],
                    "title": paper["title"],
                    "authors": "; ".join(paper.get("authors", [])),
                    "published": paper.get("published", ""),
                    "entry_id": paper["entry_id"],
                    "pdf_url": paper["pdf_url"],
                    "pdf_path": str(pdf_path),
                })
                chunk_id += 1

    save_json(data_dir / "processed" / "all_parsed.json", all_parsed)
    save_json(data_dir / "chunks" / "all_chunks.json", all_chunks)
    if not all_chunks:
        print("No usable text was found; the existing vector index was preserved.")
        return {"papers": 0, "chunks": 0}

    embedded_chunks = embedder.embed_chunks(all_chunks)
    save_json(data_dir / "embeddings" / "chunks_embedded.json", embedded_chunks)
    if store is None:
        store = VectorStore(
            persist_dir=str(config.chroma_path),
            collection_name=config.chroma_collection,
            model_name=config.embedding_model,
        )
    store.add_chunks(embedded_chunks)
    print(f"Indexed {len(all_parsed)} papers and {len(embedded_chunks)} chunks.")
    return {"papers": len(all_parsed), "chunks": len(embedded_chunks)}


def main() -> int:
    try:
        ingest(input("Enter keyword query: "))
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except Exception as exc:
        print(f"Ingestion failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
