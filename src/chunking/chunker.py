from typing import Callable, Dict, List, Optional

from src.settings import settings


def chunk_text(
    text: str,
    chunk_size: int = settings.chunk_size,
    overlap: int = settings.chunk_overlap,
    *,
    token_counter: Optional[Callable[[str], int]] = None,
    max_tokens: Optional[int] = None,
) -> List[Dict]:
    """
    Split text into overlapping chunks, optionally bounded by tokenizer length.

    Args:
        text: Text to split.
        chunk_size: Maximum words per chunk.
        overlap: Number of words shared between adjacent chunks.
        token_counter: Counts tokens including the model's special tokens.
        max_tokens: Maximum encoded length; requires token_counter.

    Returns:
        List of chunk dictionaries.
    """

    if not isinstance(chunk_size, int) or isinstance(chunk_size, bool) or chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0.")

    if not isinstance(overlap, int) or isinstance(overlap, bool) or overlap < 0:
        raise ValueError("overlap cannot be negative.")

    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size.")

    if (token_counter is None) != (max_tokens is None):
        raise ValueError("token_counter and max_tokens must be supplied together.")
    if max_tokens is not None and (
        not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens <= 0
    ):
        raise ValueError("max_tokens must be a positive integer.")

    words = text.split()

    if not words:
        return []

    chunks = []
    start = 0
    chunk_id = 0

    while start < len(words):
        end = min(start + chunk_size, len(words))

        if token_counter is not None:
            # Find the largest word window that fits without changing source text.
            low, high = start + 1, end
            if token_counter(words[start]) > max_tokens:
                raise ValueError(f"Word at offset {start} exceeds the model token limit.")
            while low < high:
                middle = (low + high + 1) // 2
                if token_counter(" ".join(words[start:middle])) <= max_tokens:
                    low = middle
                else:
                    high = middle - 1
            end = low

        chunks.append(
            {
                "chunk_id": chunk_id,
                "start_word": start,
                "end_word": end,
                "text": " ".join(words[start:end]),
            }
        )

        if end == len(words):
            break

        chunk_id += 1
        # Token-limited windows may be shorter than the requested overlap.
        start = max(start + 1, end - overlap)

    return chunks
