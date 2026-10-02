from src.embeddings.embedder import Embedder
from src.settings import Settings, settings
from src.vectorstore.chroma_store import VectorStore


class SemanticSearcher:
    def __init__(self, embedder=None, store=None, config: Settings = settings):
        self.config = config
        self.embedder = embedder
        self.store = store if store is not None else VectorStore(
            persist_dir=str(config.chroma_path),
            collection_name=config.chroma_collection,
            model_name=config.embedding_model,
        )

    def search(self, query: str, top_k=None):
        query = query.strip()
        if not query:
            raise ValueError("Query cannot be empty.")
        limit = self.config.top_k if top_k is None else top_k
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise ValueError("top_k must be a positive integer.")
        if self.store.count() == 0:
            return []
        if self.embedder is None:
            self.embedder = Embedder(model_name=self.config.embedding_model)
        return self.store.query(self.embedder.embed_query(query), k=limit)
