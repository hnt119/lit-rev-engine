from src.search.arxiv_search import search_arxiv
from src.download.pdf_downloader import download_many
from src.parser.pdf_parser import parse_pdf
import json


def main():
    query = input("Enter keyword query: ")

    # Step 1: Search
    papers = search_arxiv(query, max_results=5)

    print(f"\nFound {len(papers)} papers\n")

    for i, paper in enumerate(papers):
        print(f"{i + 1}. {paper['title']}")

    # Step 2: Save metadata
    with open("data/raw/arxiv_results.json", "w") as f:
        json.dump(papers, f, indent=2)

    # Step 3: Download PDFs
    print("\nDownloading PDFs...\n")
    paths = download_many(papers)

    print("\nDownloaded files:")
    for path in paths:
        print(path)

    # Step 4: Parse the first PDF
    if paths:
        print("\nParsing first PDF...\n")

        parsed = parse_pdf(paths[0])

        with open("data/processed/sample_parsed.json", "w") as f:
            json.dump(parsed, f, indent=2)

        print("Parsed text saved.")
    

if __name__ == "__main__":
    main()