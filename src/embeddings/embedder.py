from typing import List, Dict

from sentence_transformers import SentenceTransformer

from src.chunking.chunker import chunk_text
from src.settings import settings


class Embedder:
    def __init__(self, model_name: str = settings.embedding_model):
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def count_tokens(self, text: str) -> int:
        return len(self.model.tokenizer.encode(
            text, add_special_tokens=True, truncation=False, verbose=False
        ))

    def chunk_text(
        self,
        text: str,
        chunk_size: int = settings.chunk_size,
        overlap: int = settings.chunk_overlap,
    ) -> List[Dict]:
        return chunk_text(
            text,
            chunk_size=chunk_size,
            overlap=overlap,
            token_counter=self.count_tokens,
            max_tokens=self.model.max_seq_length,
        )

    def _validate_lengths(self, texts: List[str]) -> None:
        for index, text in enumerate(texts):
            if self.count_tokens(text) > self.model.max_seq_length:
                raise ValueError(
                    f"Text {index} exceeds the {self.model.max_seq_length}-token "
                    "embedding limit. Use Embedder.chunk_text() for documents "
                    "or shorten the research question."
                )

    def embed_query(self, query: str):
        """
        Embed a user query.
        """
        if not query.strip():
            raise ValueError("Query cannot be empty.")
        self._validate_lengths([query])
        return self.model.encode(query, normalize_embeddings=True).tolist()

    def embed_texts(self, texts: List[str]):
        """
        Convert list of texts → embeddings
        """
        if not texts:
            return []
        self._validate_lengths(texts)
        return self.model.encode(
            texts, show_progress_bar=True, normalize_embeddings=True
        )

    def embed_chunks(self, chunks: List[Dict]):
        """
        Add embeddings to chunk objects
        """

        texts = [c["text"] for c in chunks]
        embeddings = self.embed_texts(texts)

        enriched = []

        for chunk, emb in zip(chunks, embeddings):
            enriched.append({
                **chunk,
                "embedding": emb.tolist()
            })

        return enriched
