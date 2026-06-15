from src.search.arxiv_search import search_arxiv
import json


def main():
    query = input("Enter keyword query: ")

    results = search_arxiv(query, max_results=5)

    print("\nFound papers:\n")

    for i, paper in enumerate(results):
        print(f"{i+1}. {paper['title']}")
        print(f"   Authors: {', '.join(paper['authors'])}")
        print(f"   Published: {paper['published']}")
        print(f"   PDF: {paper['pdf_url']}\n")

    # Save to file
    with open("data/raw/arxiv_results.json", "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()