import importlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import ask
import query
from src.embeddings.embedder import Embedder
from src.llm.agnes_generator import AgnesGenerator
from src.retrieval.semantic_search import SemanticSearcher
from src.settings import PROJECT_ROOT, Settings


def generator_with_response(content, finish_reason="stop", choices=True):
    response = SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=content), finish_reason=finish_reason,
    )] if choices else [])
    generator = AgnesGenerator.__new__(AgnesGenerator)
    generator.model = "test-model"
    generator.client = SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=Mock(return_value=response)),
    ))
    return generator


@pytest.mark.parametrize("content, reason, choices, message", [
    ("Partial answer [Source 1]", "length", True, "partial answer"),
    ("   ", "stop", True, "empty"),
    (None, "stop", True, "empty"),
    (None, "stop", False, "no completion"),
])
def test_generation_rejects_unusable_or_truncated_response(content, reason, choices, message):
    with pytest.raises(RuntimeError, match=message):
        generator_with_response(content, reason, choices).generate([])


def test_generator_strips_valid_response():
    assert generator_with_response(" Answer [Source 1]. ").generate([]) == "Answer [Source 1]."


def test_empty_embedding_batch_does_not_call_model():
    embedder = Embedder.__new__(Embedder)
    embedder.model = SimpleNamespace(encode=Mock(side_effect=AssertionError("model called")))
    assert embedder.embed_chunks([]) == []


def test_embedder_rejects_oversized_input_before_encoding():
    embedder = Embedder.__new__(Embedder)
    embedder.model = SimpleNamespace(
        tokenizer=SimpleNamespace(encode=lambda text, **kw: list(range(len(text.split()) + 2))),
        max_seq_length=4, encode=Mock(),
    )
    with pytest.raises(ValueError, match="embedding limit"):
        embedder.embed_query("one two three")
    with pytest.raises(ValueError, match="embedding limit"):
        embedder.embed_chunks([{"text": "one two three"}])
    embedder.model.encode.assert_not_called()


def test_empty_index_does_not_load_embedding_model(monkeypatch):
    store = SimpleNamespace(count=lambda: 0)
    monkeypatch.setattr(
        "src.retrieval.semantic_search.Embedder", lambda **kw: pytest.fail("model loaded"),
    )
    assert SemanticSearcher(store=store).search("Question") == []


def test_query_import_has_no_prompt_or_model_side_effects(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("prompt at import"))
    importlib.reload(query)


@pytest.mark.parametrize("module", [ask, query])
def test_cli_empty_question_is_checked_before_initialization(module, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *a: "   ")
    constructor = "RAGAssistant" if module is ask else "SemanticSearcher"
    monkeypatch.setattr(module, constructor, lambda: pytest.fail("constructed for empty question"))
    assert module.main() == 1


def test_data_paths_are_independent_of_working_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config = Settings()
    assert config.data_directory == PROJECT_ROOT / "data"
    assert config.chroma_path == PROJECT_ROOT / "data/chroma"
    assert "secret" not in repr(Settings(agnes_api_key="secret"))


@pytest.mark.parametrize("kwargs", [
    {"chunk_overlap": 300}, {"chunk_size": 0}, {"top_k": 0},
    {"max_source_distance": float("nan")}, {"temperature": -1},
])
def test_settings_validate_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs)
