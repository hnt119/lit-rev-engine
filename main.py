from src.search.arxiv_search import search_arxiv
from src.download.pdf_downloader import download_many
import json


def main():
    query = input("Enter keyword query: ")

    papers = search_arxiv(query, max_results=5)

    print(f"\nFound {len(papers)} papers\n")

    for i, p in enumerate(papers):
        print(f"{i+1}. {p['title']}")

    # Save metadata
    with open("data/raw/arxiv_results.json", "w") as f:
        json.dump(papers, f, indent=2)

    # Download PDFs
    print("\nDownloading PDFs...\n")
    paths = download_many(papers)

    print("\nDownloaded files:")
    for p in paths:
        print(p)


if __name__ == "__main__":
    main()