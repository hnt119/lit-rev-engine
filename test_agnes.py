from src.llm.agnes_generator import AgnesGenerator


def main() -> None:
    generator = AgnesGenerator()

    messages = [
        {
            "role": "system",
            "content": "You are a concise academic research assistant.",
        },
        {
            "role": "user",
            "content": (
                "Explain retrieval-augmented generation in three sentences."
            ),
        },
    ]

    answer = generator.generate(
        messages,
        max_tokens=1000,
        temperature=0.2,
    )

    print("\nAgnes response:\n")
    print(answer)


if __name__ == "__main__":
    main()
