from src.search.arxiv_search import search_arxiv
from src.download.pdf_downloader import download_many
from src.parser.pdf_parser import parse_pdf
from src.chunking.chunker import chunk_text
from src.embeddings.embedder import Embedder
from src.vectorstore.chroma_store import VectorStore
import json
import os


def main():
    query = input("Enter keyword query: ")

    # Step 1: Search
    papers = search_arxiv(query, max_results=5)

    print(f"\nFound {len(papers)} papers\n")

    for i, paper in enumerate(papers):
        print(f"{i + 1}. {paper['title']}")

    # Step 2: Save metadata
    os.makedirs("data/raw", exist_ok=True)
    with open("data/raw/arxiv_results.json", "w") as f:
        json.dump(papers, f, indent=2)

    # Step 3: Download PDFs
    print("\nDownloading PDFs...\n")
    paths = download_many(papers)

    print("\nDownloaded files:")
    for path in paths:
        print(path)

    # Step 4 + 5: Parse + Chunk ALL PDFs
    os.makedirs("data/processed", exist_ok=True)
    os.makedirs("data/chunks", exist_ok=True)

    all_parsed = []
    all_chunks = []

    for pdf_path in paths:
        print(f"\nProcessing: {pdf_path}")

        # Parse
        parsed = parse_pdf(pdf_path)
        all_parsed.append(parsed)

        # Chunk
        chunks = chunk_text(parsed["text"])

        paper_id = pdf_path.split("/")[-1].replace(".pdf", "")

        for c in chunks:
            all_chunks.append({
                "paper_id": paper_id,
                "chunk_id": c["chunk_id"],
                "text": c["text"]
            })
    
    print("\nEmbedding chunks...\n")

    embedder = Embedder()
    embedded_chunks = embedder.embed_chunks(all_chunks)

    # Save parsed data
    with open("data/processed/all_parsed.json", "w") as f:
        json.dump(all_parsed, f, indent=2)
    
    print(f"\nDone. Parsed {len(paths)} papers.")

    # Save chunk data
    with open("data/chunks/all_chunks.json", "w") as f:
        json.dump(all_chunks, f, indent=2)
    
    # Save embedded chunks
    with open("data/embeddings/chunks_embedded.json", "w") as f:
        json.dump(embedded_chunks, f, indent=2)

    print(f"Embedded {len(embedded_chunks)} chunks")

    print("\nStoring embeddings in vector DB...\n")

    store = VectorStore()
    store.add_chunks(embedded_chunks)

    print("Stored in ChromaDB")

if __name__ == "__main__":
    main()