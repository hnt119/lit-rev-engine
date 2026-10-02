import pytest

from src.chunking.chunker import chunk_text


def count_tokens(text):
    # Simulate biomedical words that each consume several subword tokens.
    return 2 + sum(len(word) for word in text.split())


def test_token_bounded_chunks_preserve_all_words_and_offsets():
    words = [f"word{index}" for index in range(30)]
    chunks = chunk_text(
        " ".join(words), chunk_size=15, overlap=4,
        token_counter=count_tokens, max_tokens=35,
    )
    covered = set()
    for chunk in chunks:
        assert count_tokens(chunk["text"]) <= 35
        assert chunk["text"].split() == words[chunk["start_word"]:chunk["end_word"]]
        covered.update(range(chunk["start_word"], chunk["end_word"]))
    assert covered == set(range(len(words)))
    assert chunks[-1]["end_word"] == len(words)


def test_token_limit_shorter_than_overlap_still_advances():
    chunks = chunk_text(
        "alpha bravo delta", chunk_size=10, overlap=8,
        token_counter=count_tokens, max_tokens=7,
    )
    assert [chunk["text"] for chunk in chunks] == ["alpha", "bravo", "delta"]


def test_single_word_over_limit_is_rejected_instead_of_truncated():
    with pytest.raises(ValueError, match="exceeds"):
        chunk_text("enormous", token_counter=count_tokens, max_tokens=4)


@pytest.mark.parametrize("kwargs", [
    {"max_tokens": 10},
    {"token_counter": count_tokens},
    {"token_counter": count_tokens, "max_tokens": 0},
])
def test_token_configuration_is_validated(kwargs):
    with pytest.raises(ValueError):
        chunk_text("example", **kwargs)
