from src.search.arxiv_search import search_arxiv
from src.download.pdf_downloader import download_many
from src.parser.pdf_parser import parse_pdf
from src.chunking.chunker import chunk_text
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

        all_chunks.append({
            "pdf_path": pdf_path,
            "chunks": chunks
        })

    # Save parsed data
    with open("data/processed/all_parsed.json", "w") as f:
        json.dump(all_parsed, f, indent=2)

    # Save chunk data
    with open("data/chunks/all_chunks.json", "w") as f:
        json.dump(all_chunks, f, indent=2)

    print(f"\nDone. Parsed {len(paths)} papers.")


if __name__ == "__main__":
    main()