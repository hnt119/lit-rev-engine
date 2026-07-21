from typing import Dict, List, Optional

from src.llm.agnes_generator import AgnesGenerator
from src.retrieval.semantic_search import SemanticSearcher
from src.settings import settings


class RAGAssistant:
    def __init__(
        self,
        searcher: Optional[SemanticSearcher] = None,
        generator: Optional[AgnesGenerator] = None,
    ):
        self.searcher = searcher or SemanticSearcher()
        self.generator = generator or AgnesGenerator()

    @staticmethod
    def _format_context(results: List[Dict]) -> str:
        """
        Convert retrieved chunks into clearly labelled source passages.
        """

        context_blocks = []

        for index, result in enumerate(results, start=1):
            source_header = (
                f"[Source {index} | "
                f"paper_id={result['paper_id']} | "
                f"chunk_id={result['chunk_id']}]"
            )

            context_blocks.append(
                f"{source_header}\n{result['text']}"
            )

        return "\n\n".join(context_blocks)

    def answer(
        self,
        question: str,
        top_k: int = settings.top_k,
    ) -> Dict:
        if not question.strip():
            raise ValueError("Question cannot be empty.")

        sources = self.searcher.search(
            query=question,
            top_k=top_k,
        )

        sources = [
             source
             for source in sources
             if len(source["text"].split()) >= 80
]
        
        sources = sources[:3]

        if not sources:
            return {
                "answer": (
                    "No relevant evidence was found in the indexed papers."
                ),
                "sources": [],
            }

        context = self._format_context(sources)

        messages = [
            {
                "role": "system",
                "content": (
                    "Answer only from the supplied sources. "
                    "Cite every claim using [Source 1], [Source 2], etc. "
                    "If evidence is insufficient, say so. "
                    "Do not describe your reasoning process."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Question:\n{question}\n\n"
                    f"Sources:\n{context}\n\n"
                    "Give a concise answer in no more than 250 words. "
                    "State the main limitations and any uncertainty."
                ),
            },
        ]

        answer = self.generator.generate(messages)

        return {
            "answer": answer,
            "sources": sources,
        }