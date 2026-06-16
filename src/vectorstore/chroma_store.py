import chromadb
from typing import List, Dict


class VectorStore:
    def __init__(self, persist_dir: str = "data/chroma"):
        self.client = chromadb.PersistentClient(path=persist_dir)

        self.collection = self.client.get_or_create_collection(
            name="research_chunks"
        )

    def add_chunks(self, chunks: List[Dict]):
        """
        Store embeddings in vector DB
        """

        ids = []
        embeddings = []
        documents = []
        metadatas = []

        for i, chunk in enumerate(chunks):
            ids.append(f"{chunk['paper_id']}_{chunk['chunk_id']}")
            embeddings.append(chunk["embedding"])
            documents.append(chunk["text"])

            metadatas.append({
                "paper_id": chunk["paper_id"],
                "chunk_id": chunk["chunk_id"]
            })

        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )

    def query(self, query_embedding, k: int = 5):
        """
        Semantic search
        """

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=k
        )

        return results