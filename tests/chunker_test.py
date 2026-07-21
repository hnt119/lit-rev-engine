from src.chunking.chunker import chunk_text
import pytest


def test_chunk_text_rejects_overlap_equal_to_chunk_size():
    with pytest.raises(ValueError):
        chunk_text(
            "some sample text",
            chunk_size=10,
            overlap=10,
        )


def test_chunk_text_rejects_overlap_larger_than_chunk_size():
    with pytest.raises(ValueError):
        chunk_text(
            "some sample text",
            chunk_size=10,
            overlap=11,
        )


def test_chunk_text_rejects_zero_chunk_size():
    with pytest.raises(ValueError):
        chunk_text(
            "some sample text",
            chunk_size=0,
            overlap=0,
        )


def test_chunk_text_creates_expected_chunks():
    text = " ".join(f"word{i}" for i in range(20))

    chunks = chunk_text(
        text,
        chunk_size=10,
        overlap=2,
    )

    assert len(chunks) == 3

    assert chunks[0]["chunk_id"] == 0
    assert chunks[0]["start_word"] == 0
    assert chunks[0]["end_word"] == 10

    assert chunks[1]["chunk_id"] == 1
    assert chunks[1]["start_word"] == 8
    assert chunks[1]["end_word"] == 18

    assert chunks[2]["chunk_id"] == 2
    assert chunks[2]["start_word"] == 16
    assert chunks[2]["end_word"] == 20


def test_chunk_text_preserves_overlap():
    text = " ".join(f"word{i}" for i in range(20))

    chunks = chunk_text(
        text,
        chunk_size=10,
        overlap=2,
    )

    first_chunk_words = chunks[0]["text"].split()
    second_chunk_words = chunks[1]["text"].split()

    assert first_chunk_words[-2:] == second_chunk_words[:2]


def test_chunk_text_empty_input():
    chunks = chunk_text("")

    assert chunks == []


def test_chunk_text_smaller_than_chunk_size():
    text = "one two three four five"

    chunks = chunk_text(
        text,
        chunk_size=10,
        overlap=2,
    )

    assert len(chunks) == 1
    assert chunks[0]["text"] == text