from sentence_transformers import SentenceTransformer
from typing import List, Dict


class Embedder:
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        self.model = SentenceTransformer(model_name)

    def embed_query(self, query: str):
        """
        Embed a user query.
        """
        return self.model.encode(query).tolist()

    def embed_texts(self, texts: List[str]):
        """
        Convert list of texts → embeddings
        """
        return self.model.encode(texts, show_progress_bar=True)

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