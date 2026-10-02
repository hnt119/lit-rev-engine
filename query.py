from src.retrieval.semantic_search import SemanticSearcher


def print_source(source, index: int) -> None:
    print(f"[Source {index}] {source.get('title') or source['paper_id']}")
    print(
        f"Paper: {source['paper_id']} | Chunk: {source['chunk_id']} | "
        f"Distance: {source['distance']:.4f}"
    )
    if source.get("page_number") is not None:
        print(f"PDF page: {source['page_number']} | File: {source.get('pdf_path', '')}")
    else:
        print("Page metadata unavailable; re-ingest this paper to add source locations.")
    if source.get("entry_id"):
        print(f"Paper URL: {source['entry_id']}")
    print(source["text"])
    print()


def main() -> int:
    try:
        question = input("Research question: ").strip()
        if not question:
            print("Please enter a research question.")
            return 1
        results = SemanticSearcher().search(question)
        if not results:
            print("No indexed passages were found. Run python main.py first.")
        for index, result in enumerate(results, start=1):
            print_source(result, index)
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except Exception as exc:
        print(f"Retrieval failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
