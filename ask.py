from query import print_source
from src.rag.rag_assistant import RAGAssistant


def print_sources(sources) -> None:
    print("\nRetrieved evidence\n")
    for index, source in enumerate(sources, start=1):
        print_source(source, index)


def main() -> int:
    try:
        question = input("Research question: ").strip()
        if not question:
            print("Please enter a research question.")
            return 1
        result = RAGAssistant().answer(question)
        print(f"\nAnswer\n\n{result['answer']}")
        if result["sources"]:
            print_sources(result["sources"])
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except Exception as exc:
        print(f"Answer generation failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
