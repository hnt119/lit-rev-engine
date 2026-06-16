from src.retrieval.semantic_search import SemanticSearcher

searcher = SemanticSearcher()

query = input("Research question: ")

results = searcher.search(query)

print()

for i, result in enumerate(results, start=1):

    print("=" * 80)
    print(f"Result {i}")
    print(f"Paper: {result['paper_id']}")
    print(f"Chunk: {result['chunk_id']}")
    print(f"Distance: {result['distance']:.4f}")
    print()
    print(result["text"][:500])
    print()