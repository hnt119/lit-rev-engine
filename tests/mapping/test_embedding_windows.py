"""Synthetic tokenizer/model checks; never load weights or download artifacts."""
import json
import math
import pytest
from src.mvp.adapters.paper_embeddings import LocalPaperEmbedder
from src.mvp.mapping import EmbeddingProfile, PaperRepresentation


def test_full_token_id_windows_are_covered_once_and_weighted():
    torch = pytest.importorskip("torch")
    class Processor:
        def __getstate__(self):
            return json.dumps({"single": [{"SpecialToken": {"id": "[CLS]", "type_id": 0}}, {"Sequence": {"id": "A", "type_id": 0}}, {"SpecialToken": {"id": "[SEP]", "type_id": 0}}]}).encode()
    class Tokenizer:
        cls_token_id, sep_token_id = 101, 102
        backend_tokenizer = type("Backend", (), {"post_processor": Processor()})()
        def encode(self, text, **kwargs):
            assert kwargs["truncation"] is False and kwargs["add_special_tokens"] is False
            return list(range(1, 1201))
        def num_special_tokens_to_add(self, **kwargs):
            return 2
    class SyntheticModel:
        tokenizer = Tokenizer()
        def __init__(self):
            self.calls = []
        def eval(self):
            return self
        def __call__(self, features):
            values = features["input_ids"][0].tolist()
            assert values[0] == 101 and values[-1] == 102
            assert torch.all(features["attention_mask"] == 1)
            assert torch.all(features["token_type_ids"] == 0)
            self.calls.append(values[1:-1])
            return {"sentence_embedding": torch.tensor([[1.0, float(len(self.calls)), 1.0]])}
    model = SyntheticModel()
    adapter = LocalPaperEmbedder(enabled=False)
    adapter._profile = EmbeddingProfile(dimension=3, runtime_versions={"fixture": "SOFTWARE TEST ONLY"})
    adapter._load = lambda: model
    item = adapter.embed(PaperRepresentation(paper_id="software-test", input_text="synthetic input", input_sha256="fixture", representation="title_abstract"), lambda: None)
    assert [token for window in model.calls for token in window] == list(range(1, 1201))
    assert item.window_token_weights == [510, 510, 180]
    assert item.token_count == 1200 and len(model.calls) == 3
    assert math.isclose(math.hypot(*item.vector), 1.0)


def test_profile_records_file_hashes_and_rejects_changes_before_model_load(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    from src.mvp.adapters.paper_embeddings import REQUIRED_FILES
    from src.mvp.mapping import BGE_REVISION
    from src.mvp.ports import MvpError
    snapshot = tmp_path / "models--BAAI--bge-small-en-v1.5" / "snapshots" / BGE_REVISION
    snapshot.mkdir(parents=True)
    for name in REQUIRED_FILES:
        target = snapshot / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("SOFTWARE TEST FILE " + name)
    adapter = LocalPaperEmbedder(enabled=True, cache_dir=tmp_path)
    adapter._versions = {"fixture": "software-test-only"}
    profile = adapter.profile
    assert set(profile.files_sha256) == set(REQUIRED_FILES)
    (snapshot / "config.json").write_text("MODIFIED SOFTWARE TEST FILE")
    def forbidden(*args, **kwargs):
        pytest.fail("A changed snapshot must fail before model construction")
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=forbidden))
    with pytest.raises(MvpError) as error:
        adapter._load()
    assert error.value.code == "embedding_profile_changed"


def test_snapshot_rejects_reference_outside_its_model_repository(tmp_path):
    from src.mvp.adapters.paper_embeddings import REQUIRED_FILES
    from src.mvp.mapping import BGE_REVISION
    from src.mvp.ports import MvpError
    snapshot = tmp_path / "models--BAAI--bge-small-en-v1.5" / "snapshots" / BGE_REVISION
    snapshot.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("SOFTWARE TEST OUTSIDE FILE")
    for name in REQUIRED_FILES:
        target = snapshot / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("SOFTWARE TEST FILE")
    (snapshot / "config.json").unlink()
    (snapshot / "config.json").symlink_to(outside)
    adapter = LocalPaperEmbedder(enabled=True, cache_dir=tmp_path)
    adapter._versions = {"fixture": "software-test-only"}
    with pytest.raises(MvpError):
        _ = adapter.profile
