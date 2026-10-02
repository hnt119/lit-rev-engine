import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    data_directory: Path = PROJECT_ROOT / "data"

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
    chroma_directory: Optional[Path] = None
    chroma_collection: str = "research_chunks"

    # Optional, corpus-calibrated L2 distance cutoff. None disables filtering.
    max_source_distance: Optional[float] = None

    # Agnes AI
    agnes_api_key: str = field(default=os.getenv("AGNES_API_KEY", ""), repr=False)
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

    @property
    def chroma_path(self) -> Path:
        return (
            Path(self.chroma_directory)
            if self.chroma_directory is not None
            else Path(self.data_directory) / "chroma"
        )

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in (self.max_search_results, self.top_k, self.chunk_size, self.max_tokens)
        ):
            raise ValueError("Search, chunk, retrieval and generation limits must be positive integers.")
        if (
            not isinstance(self.chunk_overlap, int)
            or isinstance(self.chunk_overlap, bool)
            or not 0 <= self.chunk_overlap < self.chunk_size
        ):
            raise ValueError("Chunk overlap must be nonnegative and smaller than chunk size.")
        if not self.embedding_model.strip() or not self.chroma_collection.strip():
            raise ValueError("Embedding model and collection name cannot be empty.")
        if self.max_source_distance is not None and (
            not math.isfinite(self.max_source_distance) or self.max_source_distance < 0
        ):
            raise ValueError("Source distance cutoff must be finite and nonnegative.")
        if not math.isfinite(self.temperature) or not 0 <= self.temperature <= 2:
            raise ValueError("Temperature must be between 0 and 2.")


settings = Settings()
