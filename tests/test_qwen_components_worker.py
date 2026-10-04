"""CPU-fake worker evidence: encoding, complete matrices, bounds and durability."""

from copy import deepcopy
import gc
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import socket
import subprocess
import sys
from types import ModuleType, SimpleNamespace
import weakref

import pytest

from src.review_components import core


ROOT = Path(__file__).resolve().parents[1]
PREFIX = '<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
SUFFIX = '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'
INSTRUCTION = 'Retrieve source passages relevant to the research question.'


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("Worker test attempted network"))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bundle(tmp_path, *, blocks=27, spans=1, extra_span=False, questions=None):
    root = tmp_path / "upload"; root.mkdir()
    for name, original in {"component_core.py": ROOT / "src/review_components/core.py", "qwen_kaggle_environment.py": ROOT / "tools/qwen_kaggle_environment.py", "qwen_components_kaggle_runner.py": ROOT / "tools/qwen_components_kaggle_runner.py"}.items():
        (root / name).write_bytes(original.read_bytes())
    if questions is None:
        questions = [{"id": "q", "query": "needle_b24", "components": [{"id": "population", "query": "needle_b25"}, {"id": "outcome", "query": "needle_b26"}]}]
    candidates, representations = [], []
    for index in range(blocks):
        parts = [f"needle_b{index}"] + [f"part{part}" for part in range(1, spans + (extra_span and index == 0))]
        text = " ".join(parts)
        candidate = {"passage": {"project_id": "synthetic-project", "document_id": "synthetic-document", "anchor": {"block_id": f"block:{index}", "start": 0, "end": len(text), "quote": text}}, "tie": [0, index, 0, 0]}
        candidates.append(candidate)
        start = 0
        for part in parts:
            end = start + len(part)
            rid = core.digest({"document_id": "synthetic-document", "block_id": f"block:{index}", "start": start, "end": end, "text": part})
            representations.append({"id": rid, "block_index": index, "start": start, "end": end, "text": part})
            start = end + 1
    files = {name: {"sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(), "size_bytes": (root / name).stat().st_size} for name in core.EXECUTION_FILES}
    manifest = [{"document_id": "synthetic-document", "version": 1}]
    job = {"schema_version": 1, "kind": "qwen-components-job-v1", "project_id": "synthetic-project", "scope": "included", "top_k": 5, "candidate_k": 20, "profile": deepcopy(core.PROFILE), "profile_sha256": core.digest(core.PROFILE), "source_manifest": manifest, "source_snapshot_sha256": core.digest(manifest), "candidates": candidates, "representations": representations, "questions": core.normalize_questions(questions), "query_rows": core.query_rows(candidates, questions), "execution_files": files}
    sha = core.digest(job)
    path = root / "job.json"; path.write_text(core.canonical({"payload": job, "payload_sha256": sha}))
    worker = load(root / "qwen_components_kaggle_runner.py", "independent_component_worker")
    return root, path, sha, job, worker


class Tensor:
    def __init__(self, values, events): self.values, self.events = values, events
    def __getitem__(self, selectors):
        selectors = selectors if isinstance(selectors, tuple) else (selectors,)
        def at(value, indices):
            if not indices: return value
            index, remaining = indices[0], indices[1:]
            return [at(item, remaining) for item in value[index]] if isinstance(index, slice) else at(value[index], remaining)
        return Tensor(at(self.values, selectors), self.events)
    def float(self): self.events.append(("float32",)); return self
    def cpu(self): self.events.append(("cpu",)); return self
    def tolist(self): return deepcopy(self.values)
    def item(self): return self.values


def fake_models(monkeypatch, *, fail_phase=None, overlong=False, stop_at_reranker=False):
    events, encodings, model_references = [], [], []
    torch = ModuleType("torch")
    torch.float16, torch.long = "float16", "long"
    torch.manual_seed = lambda value: events.append(("seed", value))
    torch.cuda = SimpleNamespace(set_device=lambda value: events.append(("device", value)), reset_peak_memory_stats=lambda value: events.append(("reset_peak", value)), synchronize=lambda: events.append(("synchronize",)), empty_cache=lambda: events.append(("empty_cache",)), max_memory_allocated=lambda value: 123456)
    def tensor(values, **kwargs):
        assert kwargs == {"dtype": "long", "device": "cuda:0"}
        events.append(("input", deepcopy(values)))
        return Tensor(values, events)
    torch.tensor = tensor
    torch.ones = lambda shape, **kwargs: Tensor([[1] * shape[1]], events)
    class Inference:
        def __enter__(self): events.append(("inference",)); return self
        def __exit__(self, *args): return False
    torch.inference_mode = Inference
    def normalize(values, *, p, dim):
        assert p == 2 and dim == 1 and events[-1] == ("float32",)
        events.append(("normalize", deepcopy(values.values)))
        return Tensor([[v / math.hypot(*row) for v in row] for row in values.values], events)
    torch.nn = SimpleNamespace(functional=SimpleNamespace(normalize=normalize))
    torch.stack = lambda values: Tensor([value.values for value in values], events)
    def softmax(values, *, dim):
        assert dim == 0 and events[-1] == ("float32",)
        events.append(("yes_no_logits", deepcopy(values.values)))
        numbers = [math.exp(value - max(values.values)) for value in values.values]
        return Tensor([value / sum(numbers) for value in numbers], events)
    torch.softmax = softmax
    transformers = ModuleType("transformers")
    class Tokenizer:
        def __init__(self, phase): self.phase = phase
        def encode(self, text, *, add_special_tokens):
            encodings.append((self.phase, text, add_special_tokens))
            values = [ord(value) for value in text]
            if overlong and self.phase == "embedding": values = [1] * 8191
            return [900001, *values, 900002] if add_special_tokens else values
        def convert_tokens_to_ids(self, text): return {"no": 3, "yes": 7}[text]
    class Model:
        def __init__(self, phase): self.phase, self.calls = phase, 0
        def to(self, device): assert device == "cuda:0"; return self
        def eval(self): events.append(("eval", self.phase)); return self
        def __call__(self, **kwargs):
            self.calls += 1
            assert kwargs["use_cache"] is False and len(kwargs["input_ids"].values) == 1
            assert kwargs["attention_mask"].values == [[1] * len(kwargs["input_ids"].values[0])]
            if fail_phase == self.phase and self.calls == 2: raise RuntimeError("Invented model interruption")
            if self.phase == "embedding":
                assert set(kwargs) == {"input_ids", "attention_mask", "use_cache"}
                first = [100.0] + [0.0] * 2559
                last = [3.0, 4.0] + [0.0] * 2558
                return SimpleNamespace(last_hidden_state=Tensor([[first, last]], events))
            assert kwargs["logits_to_keep"] == 1
            logits = [1000.0] * 20
            logits[3], logits[7] = 0.0, math.log(3)
            return SimpleNamespace(logits=Tensor([[logits]], events))
        def __del__(self): events.append(("unloaded", self.phase))
    def tokenizer_factory(name, **kwargs):
        phase = "embedding" if name.endswith("Embedding-4B") else "reranker"
        revision = "5cf2132abc99cad020ac570b19d031efec650f2b" if phase == "embedding" else "22e683669bc0f0bd69640a1354a6d0aebcfeede5"
        assert kwargs == {"revision": revision, "padding_side": "left", "trust_remote_code": False, "token": False}
        events.append(("tokenizer_load", phase)); return Tokenizer(phase)
    def model_factory(name, **kwargs):
        phase = "embedding" if name.endswith("Embedding-4B") else "reranker"
        revision = "5cf2132abc99cad020ac570b19d031efec650f2b" if phase == "embedding" else "22e683669bc0f0bd69640a1354a6d0aebcfeede5"
        assert kwargs == {"revision": revision, "torch_dtype": "float16", "attn_implementation": "sdpa", "use_safetensors": True, "trust_remote_code": False, "token": False}
        if phase == "reranker":
            gc.collect()
            assert all(reference() is None for reference in model_references)
            assert ("unloaded", "embedding") in events and ("empty_cache",) in events
            if stop_at_reranker: raise RuntimeError("Reranker load boundary reached")
        assert events[0] == ("preflight",)
        model = Model(phase); model_references.append(weakref.ref(model))
        events.append(("model_load", phase)); return model
    transformers.AutoTokenizer = SimpleNamespace(from_pretrained=tokenizer_factory)
    transformers.AutoModel = transformers.AutoModelForCausalLM = SimpleNamespace(from_pretrained=model_factory)
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    return torch, events, encodings


def configure(tmp_path, monkeypatch, worker, *, fail_phase=None, overlong=False, stop_at_reranker=False):
    torch, events, encodings = fake_models(monkeypatch, fail_phase=fail_phase, overlong=overlong, stop_at_reranker=stop_at_reranker)
    overlay = tmp_path / "overlay"; overlay.mkdir()
    report = tmp_path / "installer.json"; report.write_text('{"install": []}')
    outputs = {name: tmp_path / (name + ".json") for name in ("output", "checkpoint", "audit")}
    original_bootstrap = worker._bootstrap
    def bootstrap(*args):
        loaded_core, helper, job = original_bootstrap(*args)
        def audit(*args, **kwargs):
            assert kwargs["active_requirements"] == core.ACTIVE_REQUIREMENTS
            events.append(("preflight",))
            return {"schema_version": 1, "recipe": core.PROFILE["environment_recipe"], "overlay_path": str(overlay.resolve()), "base_python": str(Path(sys.executable).resolve()), "installer_report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(), "execution_files": job["execution_files"], "packages": {}, "torch": {"version": "2.6.0+cu124", "location": "/synthetic/base/torch/__init__.py", "cuda_version": "12.4", "device": "cuda:0", "gpu_name": "CPU fake CUDA GPU", "device_count": 1, "total_memory_bytes": 16 * 1024**3, "smoke_passed": True}, "python_version": "3.12.7", "setup_seconds": kwargs["setup_seconds"], "requirements_passed": True}
        helper.audit_environment = audit
        return loaded_core, helper, job
    monkeypatch.setattr(worker, "_bootstrap", bootstrap)
    counter = iter(number / 10 for number in range(100000))
    monkeypatch.setattr(worker.time, "monotonic", lambda: next(counter))
    return overlay, report, outputs, events, encodings


def run(worker, root, job_path, sha, overlay, report, outputs):
    return worker.run_job(job_path, job_sha256=sha, core_path=root / "component_core.py", environment_helper_path=root / "qwen_kaggle_environment.py", overlay_path=overlay, installer_report_path=report, output_path=outputs["output"], checkpoint_path=outputs["checkpoint"], environment_audit_path=outputs["audit"], setup_seconds=1.5)


def test_complete_ordered_worker_matrix_overlap_reuse_encoding_pooling_scores_and_hash(tmp_path, monkeypatch, capsys):
    root, path, sha, job, worker = bundle(tmp_path)
    overlay, report, outputs, events, encodings = configure(tmp_path, monkeypatch, worker)
    summary = run(worker, root, path, sha, overlay, report, outputs)
    envelope = core.read_artifact(outputs["output"]); payload = envelope["payload"]
    assert envelope["payload_sha256"] == core.digest(payload) == summary["results_sha256"]
    assert payload["job_sha256"] == sha and payload["execution_files"] == job["execution_files"]
    assert [row["id"] for row in payload["document_embeddings"]] == [row["id"] for row in job["representations"]]
    assert [(row["question_id"], row["component_id"]) for row in payload["query_embeddings"]] == [("q", None), ("q", "population"), ("q", "outcome")]
    for row in payload["document_embeddings"] + payload["query_embeddings"]:
        assert row["vector"] == [.6, .8] + [0.0] * 2558
    # Equal dense vectors yield stable source order. One lexical-only late block
    # enters each query hybrid; shared source0 counts in both component reservations.
    target = [0, 25, 26, *range(1, 18)]
    whole = [0, 24, *range(1, 19)]
    union = list(dict.fromkeys([*target, *whole]))
    repids = {row["block_index"]: row["id"] for row in job["representations"]}
    expected_pairs = [("q", None, repids[index]) for index in union]
    expected_pairs += [("q", name, repids[index]) for name in ("population", "outcome") for index in target]
    actual_pairs = [(row["question_id"], row["component_id"], row["representation_id"]) for row in payload["score_rows"]]
    assert actual_pairs == expected_pairs and len(actual_pairs) == len(set(actual_pairs)) == 62
    assert set(whole).intersection(target) == {0, *range(1, 18)}
    assert all(row["score"] == pytest.approx(.75, rel=1e-12) for row in payload["score_rows"])
    assert all(values == [0.0, math.log(3)] for event, *rest in events if event == "yes_no_logits" for values in rest)
    encoded_sources = [row["text"] for row in job["representations"]]
    encoded_queries = [f"Instruct: {INSTRUCTION}\nQuery: {row['query']}" for row in job["query_rows"]]
    embedding_inputs = [text for phase, text, special in encodings if phase == "embedding" and special]
    assert embedding_inputs == encoded_sources + encoded_queries
    assert [row["tokens"] for row in payload["document_embeddings"]] == [len(text) + 2 for text in encoded_sources]
    assert [row["tokens"] for row in payload["query_embeddings"]] == [len(text) + 2 for text in encoded_queries]
    query_texts = {(row["question_id"], row["component_id"]): row["query"] for row in job["query_rows"]}
    reptexts = {row["id"]: row["text"] for row in job["representations"]}
    expected_rerank = []
    for row in payload["score_rows"]:
        body = f"<Instruct>: {INSTRUCTION}\n<Query>: {query_texts[(row['question_id'], row['component_id'])]}\n<Document>: {reptexts[row['representation_id']]}"
        expected_rerank += [PREFIX, body, SUFFIX]
        assert row["tokens"] == len(PREFIX) + len(body) + len(SUFFIX)
    assert [text for phase, text, special in encodings if phase == "reranker"] == expected_rerank
    assert all(not special for phase, text, special in encodings if phase == "reranker")
    assert events.index(("unloaded", "embedding")) < events.index(("model_load", "reranker")) < events.index(("unloaded", "reranker"))
    runtime = payload["runtime"]
    assert runtime["max_input_tokens"] == max(row["tokens"] for row in payload["document_embeddings"] + payload["query_embeddings"] + payload["score_rows"])
    assert runtime["truncated"] is False and runtime["paid_inference_calls"] == 0 and runtime["peak_vram_bytes"] == 123456
    assert runtime["model_revisions"] == {"embedding": "5cf2132abc99cad020ac570b19d031efec650f2b", "reranker": "22e683669bc0f0bd69640a1354a6d0aebcfeede5"}
    assert set(runtime["elapsed_seconds"]) == {"embedding_load", "embedding_inference", "reranker_load", "reranker_inference", "total"}
    assert all(value > 0 for value in runtime["elapsed_seconds"].values())
    checkpoint = core.read_artifact(outputs["checkpoint"])["payload"]
    assert checkpoint["phase"] == "complete" and checkpoint["document_embeddings"] == payload["document_embeddings"] and checkpoint["query_embeddings"] == payload["query_embeddings"] and checkpoint["score_rows"] == payload["score_rows"]
    assert core.read_artifact(outputs["audit"])["payload"] == payload["environment_audit"]
    printed = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert printed == summary and summary["distinct_rerank_pairs"] == 62


@pytest.mark.parametrize("rerank,total", [(False, 8192), (False, 8193), (True, 8192), (True, 8193)])
def test_complete_token_boundary_counts_formatted_prefix_body_suffix_without_truncation(monkeypatch, rerank, total):
    root_events = []
    fake_torch = SimpleNamespace(long="long", tensor=lambda values, **kwargs: (values, kwargs), ones=lambda shape, **kwargs: (shape, kwargs))
    overhead = len(PREFIX) + len(SUFFIX) if rerank else 2
    body = "x" * (total - overhead)
    class Tokenizer:
        def encode(self, text, *, add_special_tokens):
            root_events.append((text, add_special_tokens))
            return [0] * (len(text) + (2 if add_special_tokens else 0))
    runner = load(ROOT / "tools/qwen_components_kaggle_runner.py", "token_evaluation")
    if total > 8192:
        with pytest.raises(ValueError, match="token count|overlong"): runner.tokenize(core, Tokenizer(), body, fake_torch, rerank=rerank)
    else:
        tensors, count = runner.tokenize(core, Tokenizer(), body, fake_torch, rerank=rerank)
        assert count == total and len(tensors["input_ids"][0][0]) == total
        assert tensors["input_ids"][1] == {"dtype": "long", "device": "cuda:0"}
        assert tensors["attention_mask"] == ((1, total), {"dtype": "long", "device": "cuda:0"})
    expected_encodings = [(PREFIX, False), (body, False), (SUFFIX, False)] if rerank else [(body, True)]
    assert root_events == expected_encodings


@pytest.mark.parametrize("extra_span,expected_pairs", [(False, 4000), (True, 4100)])
def test_actual_multispan_pair_bound_checked_after_embedding_unload_before_reranker(tmp_path, monkeypatch, extra_span, expected_pairs):
    questions = [{"id": f"q{number}", "query": "needle", "components": [{"id": name, "query": "needle"} for name in ("population", "outcome", "reference")]} for number in range(25)]
    root, path, sha, job, worker = bundle(tmp_path, blocks=20, spans=2, extra_span=extra_span, questions=questions)
    assert len(job["representations"]) * len(job["query_rows"]) == expected_pairs
    overlay, report, outputs, events, encodings = configure(tmp_path, monkeypatch, worker, stop_at_reranker=True)
    checkpoints = []; real_write = worker._write
    def checkpoint(core_module, output, payload, *, checkpoint=False):
        if checkpoint:
            checkpoints.append((payload["phase"], len(payload["document_embeddings"]), len(payload["query_embeddings"]), len(payload["score_rows"])))
        else: real_write(core_module, output, payload)
    monkeypatch.setattr(worker, "_write", checkpoint)
    error = ValueError if extra_span else RuntimeError
    match = "4000 distinct" if extra_span else "Reranker load boundary"
    with pytest.raises(error, match=match): run(worker, root, path, sha, overlay, report, outputs)
    assert ("unloaded", "embedding") in events and not any(event == ("model_load", "reranker") for event in events)
    assert checkpoints[-1][:3] == (("embedding_queries", 41, 100) if extra_span else ("pairs_validated", 40, 100))
    assert not outputs["output"].exists() and outputs["audit"].exists()


@pytest.mark.parametrize("phase", ["embedding", "reranker"])
def test_interruption_preserves_last_real_checkpoint_audit_and_no_partial_result(tmp_path, monkeypatch, phase):
    root, path, sha, job, worker = bundle(tmp_path, blocks=3, questions=[{"id": "q", "query": "needle"}])
    overlay, report, outputs, events, encodings = configure(tmp_path, monkeypatch, worker, fail_phase=phase)
    with pytest.raises(RuntimeError, match="Invented model interruption"): run(worker, root, path, sha, overlay, report, outputs)
    checkpoint = core.read_artifact(outputs["checkpoint"])["payload"]
    assert checkpoint["job_sha256"] == sha and checkpoint["profile_sha256"] == job["profile_sha256"]
    assert checkpoint["phase"] == ("embedding_sources" if phase == "embedding" else "reranking")
    assert len(checkpoint["document_embeddings"]) == (1 if phase == "embedding" else 3)
    assert len(checkpoint["score_rows"]) == (0 if phase == "embedding" else 1)
    assert ("unloaded", phase) in events and outputs["audit"].exists() and not outputs["output"].exists()


def test_overlong_embedding_rejects_before_inference_or_reranker_and_preserves_audit(tmp_path, monkeypatch):
    root, path, sha, job, worker = bundle(tmp_path, blocks=1, questions=[{"id": "q", "query": "needle"}])
    overlay, report, outputs, events, encodings = configure(tmp_path, monkeypatch, worker, overlong=True)
    with pytest.raises(ValueError, match="token count|overlong"): run(worker, root, path, sha, overlay, report, outputs)
    assert not any(event[0] == "normalize" or event == ("model_load", "reranker") for event in events)
    assert outputs["audit"].exists() and not outputs["output"].exists() and not outputs["checkpoint"].exists()


@pytest.mark.parametrize("name", ["component_core.py", "qwen_kaggle_environment.py", "qwen_components_kaggle_runner.py"])
def test_worker_hashes_all_executable_bytes_before_loading_any_core_or_helper(tmp_path, monkeypatch, name):
    root, path, sha, job, worker = bundle(tmp_path, blocks=1, questions=[{"id": "q", "query": "needle"}])
    (root / name).write_bytes((root / name).read_bytes() + b"\n# changed executable\n")
    monkeypatch.setattr(worker.importlib.util, "spec_from_file_location", lambda *a, **k: pytest.fail("Worker loaded code before completing executable checks"))
    with pytest.raises(ValueError, match="Executable bytes differ"):
        worker._bootstrap(path, sha, root / "component_core.py", root / "qwen_kaggle_environment.py")


@pytest.mark.parametrize("defect", ["trusted_hash", "payload_hash", "duplicate_key", "nonfinite", "outside_path"])
def test_invalid_job_or_bundle_fails_before_helper_core_or_model_loading(tmp_path, monkeypatch, defect):
    root, path, sha, job, worker = bundle(tmp_path, blocks=1, questions=[{"id": "q", "query": "needle"}])
    helper = root / "qwen_kaggle_environment.py"
    if defect == "trusted_hash": sha = "0" * 64
    elif defect == "payload_hash": path.write_text(path.read_text().replace(sha, "0" * 64))
    elif defect == "duplicate_key": path.write_text('{"payload":{},"payload":{},"payload_sha256":"x"}')
    elif defect == "nonfinite": path.write_text('{"payload":{"bad":NaN},"payload_sha256":"x"}')
    elif defect == "outside_path":
        helper = tmp_path / "qwen_kaggle_environment.py"; helper.write_bytes((root / helper.name).read_bytes())
    monkeypatch.setattr(worker.importlib.util, "spec_from_file_location", lambda *a, **k: pytest.fail("Invalid job loaded executable code"))
    with pytest.raises(ValueError): worker._bootstrap(path, sha, root / "component_core.py", helper)


@pytest.mark.parametrize("name", ["output", "checkpoint", "audit"])
def test_worker_preserves_existing_artifact_before_bootstrap(tmp_path, monkeypatch, name):
    root, path, sha, job, worker = bundle(tmp_path, blocks=1, questions=[{"id": "q", "query": "needle"}])
    outputs = {key: tmp_path / (key + ".json") for key in ("output", "checkpoint", "audit")}
    outputs[name].write_bytes(b"immutable original")
    monkeypatch.setattr(worker, "_bootstrap", lambda *a, **k: pytest.fail("Existing artifact triggered execution"))
    with pytest.raises(ValueError, match="Preserve existing"):
        run(worker, root, path, sha, tmp_path / "overlay", tmp_path / "installer.json", outputs)
    assert outputs[name].read_bytes() == b"immutable original"


def test_atomic_checkpoint_replacement_rejects_foreign_job_and_immutable_result(tmp_path):
    runner = load(ROOT / "tools/qwen_components_kaggle_runner.py", "atomic_artifact_evaluation")
    path = tmp_path / "checkpoint.json"
    payload = {"kind": "qwen-components-checkpoint-v1", "job_sha256": "a" * 64, "profile_sha256": core.digest(core.PROFILE), "phase": "embedding_sources"}
    runner._write(core, path, payload, checkpoint=True)
    runner._write(core, path, {**payload, "phase": "embedding_queries"}, checkpoint=True)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="another job"): runner._write(core, path, {**payload, "job_sha256": "b" * 64}, checkpoint=True)
    assert path.read_bytes() == before
    with pytest.raises(ValueError, match="immutable"): runner._write(core, path, {"result": "new"})
    assert path.read_bytes() == before and list(tmp_path.glob(".qwen-components-*")) == []


def test_fresh_worker_module_import_has_no_torch_models_network_or_ledger_dependency(tmp_path):
    code = """
import importlib.abc,importlib.util,socket,sys
blocked={'torch','transformers','src.review','src.review_components.ledger','dotenv','src.settings'}
class Guard(importlib.abc.MetaPathFinder):
 def find_spec(self,name,path=None,target=None):
  if any(name==item or name.startswith(item+'.') for item in blocked): raise AssertionError('Forbidden dependency '+name)
sys.meta_path.insert(0,Guard())
def denied(*a,**k): raise AssertionError('Worker import attempted network')
socket.create_connection=denied
spec=importlib.util.spec_from_file_location('worker',sys.argv[1]); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
assert not blocked.intersection(sys.modules)
print('stdlib import only')
"""
    result = subprocess.run([sys.executable, "-I", "-c", code, str(ROOT / "tools/qwen_components_kaggle_runner.py")], cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and result.stdout == "stdlib import only\n" and result.stderr == ""
