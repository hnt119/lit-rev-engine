from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

import chromadb

from src.settings import settings


LEGACY_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


class VectorStore:
    def __init__(
        self,
        persist_dir: Optional[str] = None,
        collection_name: str = settings.chroma_collection,
        model_name: str = settings.embedding_model,
    ):
        directory = Path(persist_dir) if persist_dir is not None else settings.chroma_path
        self.client = chromadb.PersistentClient(path=str(directory))
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=None,
            metadata={"embedding_model": model_name},
        )
        metadata = self.collection.metadata or {}
        recorded_model = metadata.get("embedding_model")
        if recorded_model is not None and recorded_model != model_name:
            raise ValueError(
                f"Collection uses {recorded_model}, but {model_name} was requested. "
                "Choose a new collection and reindex when changing embedding models."
            )
        if recorded_model is None:
            if self.collection.count() and model_name != LEGACY_EMBEDDING_MODEL:
                raise ValueError(
                    "Legacy collection has no model metadata. Use the original BGE "
                    "model or choose a new collection and reindex."
                )
            self.collection.modify(metadata={**metadata, "embedding_model": model_name})

    def add_chunks(self, chunks: List[Dict]) -> int:
        """Upsert complete paper chunk sets, then remove obsolete chunks."""
        if not chunks:
            return 0
        groups = defaultdict(list)
        seen_ids = set()
        for chunk in chunks:
            identifier = f"{chunk['paper_id']}_{chunk['chunk_id']}"
            if identifier in seen_ids:
                raise ValueError(f"Duplicate chunk ID in input: {identifier}")
            seen_ids.add(identifier)
            groups[chunk["paper_id"]].append(chunk)

        batch_size = self.client.get_max_batch_size()
        for paper, paper_chunks in groups.items():
            previous_ids = set(
                self.collection.get(where={"paper_id": paper}, include=[])["ids"]
            )
            ids = [f"{paper}_{chunk['chunk_id']}" for chunk in paper_chunks]
            for start in range(0, len(paper_chunks), batch_size):
                batch = paper_chunks[start:start + batch_size]
                metadatas = [
                    {
                        key: value for key, value in chunk.items()
                        if key not in {"embedding", "text"}
                        and isinstance(value, (str, int, float, bool))
                    }
                    for chunk in batch
                ]
                self.collection.upsert(
                    ids=ids[start:start + batch_size],
                    embeddings=[chunk["embedding"] for chunk in batch],
                    documents=[chunk["text"] for chunk in batch],
                    metadatas=metadatas,
                )
            stale_ids = sorted(previous_ids - set(ids))
            for start in range(0, len(stale_ids), batch_size):
                self.collection.delete(ids=stale_ids[start:start + batch_size])
        return len(chunks)

    def count(self) -> int:
        return self.collection.count()

    def query(self, query_embedding, k: int = settings.top_k) -> List[Dict]:
        if not isinstance(k, int) or isinstance(k, bool) or k <= 0:
            raise ValueError("k must be a positive integer.")
        count = self.collection.count()
        if count == 0:
            return []
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(k, count),
            include=["documents", "metadatas", "distances"],
        )
        return [
            {**meta, "distance": distance, "text": doc}
            for doc, meta, distance in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ]
