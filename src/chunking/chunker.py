from typing import Dict, List


def chunk_text(
    text: str,
    chunk_size: int = 300,
    overlap: int = 50,
) -> List[Dict]:
    """
    Split text into overlapping word-based chunks.

    Args:
        text: Text to split.
        chunk_size: Maximum words per chunk.
        overlap: Number of words shared between adjacent chunks.

    Returns:
        List of chunk dictionaries.
    """

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0.")

    if overlap < 0:
        raise ValueError("overlap cannot be negative.")

    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size.")

    words = text.split()

    if not words:
        return []

    chunks = []
    start = 0
    chunk_id = 0

    while start < len(words):
        end = min(start + chunk_size, len(words))

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
        start += chunk_size - overlap

    return chunks