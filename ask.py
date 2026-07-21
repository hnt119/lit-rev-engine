from src.rag.rag_assistant import RAGAssistant


def print_sources(sources) -> None:
    print("\nRetrieved evidence\n")

    for index, source in enumerate(sources, start=1):
        print(
            f"[Source {index}] "
            f"Paper: {source['paper_id']} | "
            f"Chunk: {source['chunk_id']} | "
            f"Distance: {source['distance']:.4f}"
        )


def main() -> None:
    try:
        assistant = RAGAssistant()

        question = input("Research question: ").strip()

        if not question:
            print("Please enter a research question.")
            return

        result = assistant.answer(question)

        print("\nAnswer\n")
        print(result["answer"])

        if result["sources"]:
            print_sources(result["sources"])

    except ValueError as exc:
        print(f"\nConfiguration error: {exc}")

    except RuntimeError as exc:
        print(f"\nAPI error: {exc}")

    except KeyboardInterrupt:
        print("\nCancelled.")


if __name__ == "__main__":
    main()