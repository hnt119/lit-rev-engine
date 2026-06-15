from typing import List, Dict


def chunk_text(
    text: str,
    chunk_size: int = 300,
    overlap: int = 50
) -> List[Dict]:
    """
    Split text into overlapping chunks.

    chunk_size and overlap are measured in words.
    """

    words = text.split()

    chunks = []

    start = 0
    chunk_id = 0

    while start < len(words):

        end = min(start + chunk_size, len(words))

        chunk = " ".join(words[start:end])

        chunks.append({
            "chunk_id": chunk_id,
            "start_word": start,
            "end_word": end,
            "text": chunk
        })

        chunk_id += 1

        start += chunk_size - overlap

    return chunks