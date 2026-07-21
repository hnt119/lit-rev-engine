import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    # Search
    max_search_results: int = 5

    # Chunking
    chunk_size: int = 300
    chunk_overlap: int = 50

    # Embeddings
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    # Retrieval
    top_k: int = 5

    # Vector database
    chroma_directory: str = "data/chroma"
    chroma_collection: str = "research_chunks"

    # Agnes AI
    agnes_api_key: str = os.getenv("AGNES_API_KEY", "")
    agnes_base_url: str = os.getenv(
        "AGNES_BASE_URL",
        "https://apihub.agnes-ai.com/v1",
    )
    agnes_model: str = os.getenv(
        "AGNES_MODEL",
        "agnes-2.0-flash",
    )

    # Generation
    max_tokens: int = 5000
    temperature: float = 0.2


settings = Settings()