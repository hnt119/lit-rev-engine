from src.embeddings.embedder import Embedder
from src.vectorstore.chroma_store import VectorStore


class SemanticSearcher:

    def __init__(self):
        self.embedder = Embedder()
        self.store = VectorStore()

    def search(self, query: str, top_k: int = 5):

        query_embedding = self.embedder.embed_query(query)

        return self.store.query(
            query_embedding,
            k=top_k
        )