"""Independent free batch acceptance. Synthetic vectors prove plumbing, not Qwen quality."""

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import socket
import subprocess
import sys
from xml.sax.saxutils import escape

import pytest

from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.store import ReviewStore
from src.review import qwen_batch as batch
from tools import qwen_kaggle_runner as runner


ROOT = Path(__file__).resolve().parents[1]
TEXTS = [
    "Adults n=120 were randomized and assessed at 12 months.",
    "The symptom difference was −3.1 (95% CI −4.8 to −1.4) at 12 months.",
    "Severe adverse events were zero in the adult safety subset n=36.",
    "A distinct uncontrolled feasibility sample had 24 volunteers at 6 weeks.",
    "No pediatric participants were recruited and no pediatric estimate exists.",
    "Work productivity was not collected; symptom score was the only outcome.",
    "Exact Unicode: Straße α café 🧪. These source bytes remain unchanged.",
]
QUERIES = [{"id": "paired", "query": "randomized adults symptom difference 12 months confidence interval"},
           {"id": "safety", "query": "adult safety severe adverse events denominator"},
           {"id": "no-lexical-match", "query": "xyzzy flibbertigibbet"}]


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def envelope(payload):
    return {"payload": payload, "payload_sha256": digest(payload)}


def write_artifact(path, payload):
    wrapped = envelope(payload)
    Path(path).write_text(json.dumps(wrapped, ensure_ascii=False, allow_nan=False))
    return wrapped


def fingerprint(store):
    return hashlib.sha256("\n".join(store._connection.iterdump()).encode()).hexdigest()


@pytest.fixture(autouse=True)
def forbid_inference_network_and_credentials(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Batch acceptance attempted a live connection, inference, or credential load")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr("src.review.qwen.api_key_from_env", denied)
    monkeypatch.setattr("src.review.qwen.QwenClient.__init__", denied)


def add_source(store, project, title, paragraphs, *, included=True):
    store.import_records(project, SearchRunSpec("Independent batch acceptance"), [BibliographicRecord(title=title)])
    record = store.list_records(project)[-1]["id"]
    if included:
        store.record_decision(project, record, "title_abstract", "include", "Synthetic curator")
        store.set_full_text_status(project, record, "retrieved", "Synthetic curator")
        store.record_decision(project, record, "full_text", "include", "Synthetic curator")
    source = ("<article><body><sec>" + "".join("<p>" + escape(text) + "</p>" for text in paragraphs)
              + "</sec></body></article>").encode()
    document = store.attach_document(project, record, source, "jats_xml", "Synthetic curator", "Exact authored bytes")
    return record, document


@pytest.fixture
def corpus(tmp_path):
    with ReviewStore(tmp_path / "independent-batch.sqlite3") as store:
        project = store.create_project("Independent batch acceptance", "systematic", "Exact reproducible candidates?")["id"]
        record, document = add_source(store, project, "Independent adult source", TEXTS)
        excluded, excluded_document = add_source(store, project, "Unscreened distinct source", ["Adults symptom difference 999 at 12 months."] , included=False)
        yield store, project, record, document, excluded, excluded_document


def export(corpus, tmp_path, **kwargs):
    store, project, *_ = corpus
    path = tmp_path / "job.json"
    wrapped = batch.export_job(store, project, QUERIES, output_path=path, **kwargs)
    assert wrapped == json.loads(path.read_text())
    assert wrapped["payload_sha256"] == digest(wrapped["payload"])
    return path, wrapped


def unit_vector(index, dimension=2560):
    vector = [0.0] * dimension
    vector[index % 3] = 1.0
    return vector


def independent_pool(job, question, docs, query_vector):
    """RRF independently, without invoking implementation ranking helpers."""
    dense = {}
    for rep, row in zip(job["representations"], docs, strict=True):
        value = sum(a * b for a, b in zip(row["vector"], query_vector, strict=True))
        dense[rep["block_index"]] = max(dense.get(rep["block_index"], -math.inf), value)
    dense_ids = sorted(dense, key=lambda index: (-dense[index], job["candidates"][index]["tie"]))[:job["candidate_k"]]
    scores = {}
    for ordering in (question["lexical_block_indices"], dense_ids):
        for rank, index in enumerate(ordering, 1):
            scores[index] = scores.get(index, 0.0) + 1 / (60 + rank)
    pool = sorted(scores, key=lambda index: (-scores[index], job["candidates"][index]["tie"]))[:job["candidate_k"]]
    return pool, [rep["id"] for index in pool for rep in job["representations"] if rep["block_index"] == index]


def runtime():
    # Filled from the public result schema, never from an actual GPU execution.
    return {"backend": "kaggle-cuda-transformers", "device": "cuda:0", "gpu_name": "Synthetic fixture GPU",
            "device_count": 1, "total_memory_bytes": 16_000_000_000, "dtype": "float16", "cuda_version": "12.4",
            "attention_implementation": "sdpa",
            "packages": {"transformers": "4.51.3", "tokenizers": "0.21.1", "safetensors": "0.5.3",
                         "huggingface-hub": "0.30.2", "torch": "synthetic-test", "python": "3.12.7"},
            "model_revisions": {"embedding": "5cf2132abc99cad020ac570b19d031efec650f2b",
                                "reranker": "22e683669bc0f0bd69640a1354a6d0aebcfeede5"},
            "elapsed_seconds": {"total": 1.0, "embedding_load": 0.1, "embedding_inference": 0.1,
                                "reranker_load": 0.1, "reranker_inference": 0.1},
            "peak_vram_bytes": 1000, "max_input_tokens": 24, "truncated": False, "paid_inference_calls": 0}


def synthetic_results(wrapped):
    job = wrapped["payload"]
    docs = [{"id": rep["id"], "vector": unit_vector(rep["block_index"]), "tokens": 12}
            for rep in job["representations"]]
    rows = []
    for number, query in enumerate(job["queries"]):
        vector = unit_vector(number)
        _, ids = independent_pool(job, query, docs, vector)
        # Equal score deliberately exercises final source-order ties.
        rows.append({"id": query["id"], "vector": vector, "tokens": 8,
                     "pool_representation_ids": ids,
                     "rerank_scores": [{"id": rid, "score": 0.5, "tokens": 24} for rid in ids]})
    return {"schema_version": 1, "kind": "qwen-kaggle-results-v1", "job_sha256": wrapped["payload_sha256"],
            "profile_sha256": job["profile_sha256"], "document_embeddings": docs,
            "query_results": rows, "runtime": runtime()}


def import_fake(corpus, tmp_path, *, job=None, result=None, expected_results=True, receipt_path=None):
    store, project, *_ = corpus
    if job is None:
        job_path, job = export(corpus, tmp_path)
    else:
        job_path = tmp_path / "job.json"
        job_path.write_text(json.dumps(job, ensure_ascii=False, allow_nan=False))
    result = synthetic_results(job) if result is None else result
    results_path = tmp_path / "results.json"
    wrapped_results = write_artifact(results_path, result)
    args = {"job_path": job_path, "job_sha256": job["payload_sha256"], "results_path": results_path,
            "receipt_path": receipt_path}
    if expected_results:
        args["results_sha256"] = wrapped_results["payload_sha256"]
    return batch.import_results(store, project, **args), job, wrapped_results


def test_export_pins_exact_sources_models_queries_and_preserves_database(corpus, tmp_path):
    store, project, record, document, excluded, excluded_document = corpus
    before = fingerprint(store)
    path, wrapped = export(corpus, tmp_path)
    job = wrapped["payload"]
    assert job["kind"] == "qwen-kaggle-job-v1" and job["schema_version"] == 1
    assert job["profile_sha256"] == digest(job["profile"])
    assert job["source_snapshot_sha256"] == digest(job["source_manifest"])
    assert {row["document_id"] for row in job["source_manifest"]} == {document["id"]}
    assert {row["passage"]["document_id"] for row in job["candidates"]} == {document["id"]}
    assert len(job["candidates"]) == len(TEXTS)
    for query in job["queries"]:
        reference = store.search_sources(project, query["query"], method="bm25_context_blocks", top_k=job["candidate_k"])
        indices = {row["passage"]["anchor"]["block_id"]: index for index, row in enumerate(job["candidates"])}
        assert query["lexical_block_indices"] == [indices[row["anchor"]["block_id"]] for row in reference["passages"]]
    assert "5cf2132abc99cad020ac570b19d031efec650f2b" in json.dumps(job["profile"])
    assert "22e683669bc0f0bd69640a1354a6d0aebcfeede5" in json.dumps(job["profile"])
    assert "deepinfra" not in json.dumps(job).casefold()
    assert fingerprint(store) == before and not store._connection.in_transaction


def test_import_recomputes_hybrid_pool_rank_ties_exact_own_anchors_and_replays_without_writes(corpus, tmp_path):
    store, project, *_ = corpus
    before = fingerprint(store)
    imported, wrapped, results = import_fake(corpus, tmp_path)
    job, result = wrapped["payload"], results["payload"]
    assert imported["job_sha256"] == wrapped["payload_sha256"]
    assert imported["results_sha256"] == results["payload_sha256"]
    assert imported["status"] == "candidate_passages"
    assert len(imported["traces"]) == len(QUERIES)
    for trace, question, output in zip(imported["traces"], job["queries"], result["query_results"], strict=True):
        pool, _ = independent_pool(job, question, result["document_embeddings"], output["vector"])
        expected = sorted(pool, key=lambda index: job["candidates"][index]["tie"])[:job["top_k"]]
        assert trace["query"] == question["query"] and trace["source_manifest"] == job["source_manifest"]
        assert trace["source_snapshot_sha256"] == job["source_snapshot_sha256"]
        assert trace["answerability"] == "not_assessed" and trace["verification"] == "human_review_required"
        assert [(row["anchor"], row["locator"], row["document_id"]) for row in trace["passages"]] == [
            (job["candidates"][index]["passage"]["anchor"], job["candidates"][index]["passage"]["locator"], job["candidates"][index]["passage"]["document_id"]) for index in expected]
        assert [row["rank"] for row in trace["passages"]] == list(range(1, len(expected) + 1))
        assert all(row["score"] == 0.5 for row in trace["passages"])
        assert not {"answer", "answerable", "finding", "verified"}.intersection(trace)
    replay = batch.import_results(store, project, job_path=tmp_path / "job.json", job_sha256=wrapped["payload_sha256"],
                                  results_path=tmp_path / "results.json", results_sha256=results["payload_sha256"])
    assert replay == imported and fingerprint(store) == before


@pytest.mark.parametrize("invalid", [[], [{"id": "same", "query": "one"}, {"id": "same", "query": "two"}],
    [{"id": "", "query": "one"}], [{"id": "../escape", "query": "one"}], [{"id": "q", "query": " "}],
    [{"id": "q", "query": 9}], [{"id": "q", "query": "one", "unexpected": True}],
    [{"id": True, "query": "one"}], [{"query": "one"}]])
def test_export_rejects_bad_query_contract(corpus, tmp_path, invalid):
    store, project, *_ = corpus
    before = fingerprint(store)
    with pytest.raises(ValueError):
        batch.export_job(store, project, invalid, output_path=tmp_path / "bad-job.json")
    assert not (tmp_path / "bad-job.json").exists() and fingerprint(store) == before


@pytest.mark.parametrize("kwargs", [{"top_k": True}, {"top_k": 0}, {"candidate_k": 101},
                                     {"top_k": 6, "candidate_k": 5}, {"scope": "other"}])
def test_export_rejects_bad_scope_and_bounds(corpus, tmp_path, kwargs):
    store, project, *_ = corpus
    with pytest.raises(ValueError):
        batch.export_job(store, project, QUERIES, output_path=tmp_path / "bad-job.json", **kwargs)
    assert not (tmp_path / "bad-job.json").exists()


def test_export_all_attached_scope_is_explicit_and_empty_corpus_fails(corpus, tmp_path):
    store, project, _, document, _, excluded_document = corpus
    _, wrapped = export(corpus, tmp_path, scope="all_attached")
    assert {row["document_id"] for row in wrapped["payload"]["source_manifest"]} == {document["id"], excluded_document["id"]}
    empty = store.create_project("No sources", "scoping", "No source available?")["id"]
    with pytest.raises(ValueError):
        batch.export_job(store, empty, QUERIES, output_path=tmp_path / "empty.json")
    assert not (tmp_path / "empty.json").exists()


@pytest.mark.parametrize("target", ["ledger", "wal", "shm", "existing", "source", "symlink"])
def test_export_paths_cannot_overwrite_ledger_sidecars_or_any_existing_source(corpus, tmp_path, target):
    store, project, *_ = corpus
    database = tmp_path / "independent-batch.sqlite3"
    source = tmp_path / "retained-source.xml"
    source.write_bytes(b"<article>Keep this source</article>")
    existing = tmp_path / "existing.json"
    existing.write_text("retain this artifact")
    symlink = tmp_path / "alias.json"
    symlink.symlink_to(source)
    path = {"ledger": database, "wal": Path(str(database) + "-wal"), "shm": Path(str(database) + "-shm"),
            "existing": existing, "source": source, "symlink": symlink}[target]
    before = fingerprint(store)
    initial = path.read_bytes() if path.exists() else None
    with pytest.raises(ValueError):
        batch.export_job(store, project, QUERIES, output_path=path)
    assert (path.read_bytes() if path.exists() else None) == initial and fingerprint(store) == before


def test_export_same_snapshot_repeat_has_identical_digest_and_never_overwrites(corpus, tmp_path):
    store, project, *_ = corpus
    path, wrapped = export(corpus, tmp_path)
    repeat = batch.export_job(store, project, QUERIES, output_path=tmp_path / "copy-job.json")
    assert repeat == wrapped
    with pytest.raises(ValueError):
        batch.export_job(store, project, QUERIES, output_path=path)
    assert json.loads(path.read_text()) == wrapped


@pytest.mark.parametrize("defect", ["embedding_missing", "embedding_extra", "embedding_duplicate", "embedding_order",
    "embedding_dimension", "embedding_boolean", "embedding_zero", "embedding_nonunit", "embedding_id",
    "embedding_tokens_zero", "embedding_tokens_bool", "embedding_tokens_float", "embedding_tokens_overflow",
    "query_missing", "query_duplicate", "query_order", "query_vector_dimension", "query_nonunit", "query_boolean",
    "query_tokens_zero", "query_id", "pool_order", "pool_missing", "pool_duplicate", "pool_foreign",
    "scores_missing", "scores_extra", "scores_duplicate", "scores_order", "scores_foreign", "score_negative",
    "score_above_one", "score_boolean", "score_string", "score_tokens_bool", "score_tokens_overflow",
    "job_binding", "profile_binding", "kind", "schema_bool", "extra_field"])
def test_results_reject_schema_identity_order_shape_norm_tokens_and_pool_defects(corpus, tmp_path, defect):
    store, project, *_ = corpus
    job_path, wrapped = export(corpus, tmp_path)
    result = synthetic_results(wrapped)
    docs, queries = result["document_embeddings"], result["query_results"]
    q, scores = queries[0], queries[0]["rerank_scores"]
    if defect == "embedding_missing": docs.pop()
    elif defect == "embedding_extra": docs.append(deepcopy(docs[0]))
    elif defect == "embedding_duplicate": docs[1] = deepcopy(docs[0])
    elif defect == "embedding_order": docs.reverse()
    elif defect == "embedding_dimension": docs[0]["vector"].pop()
    elif defect == "embedding_boolean": docs[0]["vector"][0] = True
    elif defect == "embedding_zero": docs[0]["vector"] = [0.0] * 2560
    elif defect == "embedding_nonunit": docs[0]["vector"][0] = 0.5
    elif defect == "embedding_id": docs[0]["id"] = "foreign"
    elif defect == "embedding_tokens_zero": docs[0]["tokens"] = 0
    elif defect == "embedding_tokens_bool": docs[0]["tokens"] = True
    elif defect == "embedding_tokens_float": docs[0]["tokens"] = 1.0
    elif defect == "embedding_tokens_overflow": docs[0]["tokens"] = 8193
    elif defect == "query_missing": queries.pop()
    elif defect == "query_duplicate": queries[1] = deepcopy(q)
    elif defect == "query_order": queries.reverse()
    elif defect == "query_vector_dimension": q["vector"].pop()
    elif defect == "query_nonunit": q["vector"][0] = 2.0
    elif defect == "query_boolean": q["vector"][0] = True
    elif defect == "query_tokens_zero": q["tokens"] = 0
    elif defect == "query_id": q["id"] = "foreign"
    elif defect == "pool_order": q["pool_representation_ids"].reverse()
    elif defect == "pool_missing": q["pool_representation_ids"].pop()
    elif defect == "pool_duplicate": q["pool_representation_ids"][1] = q["pool_representation_ids"][0]
    elif defect == "pool_foreign": q["pool_representation_ids"][0] = "foreign"
    elif defect == "scores_missing": scores.pop()
    elif defect == "scores_extra": scores.append(deepcopy(scores[0]))
    elif defect == "scores_duplicate": scores[1] = deepcopy(scores[0])
    elif defect == "scores_order": scores.reverse()
    elif defect == "scores_foreign": scores[0]["id"] = "foreign"
    elif defect == "score_negative": scores[0]["score"] = -0.1
    elif defect == "score_above_one": scores[0]["score"] = 1.1
    elif defect == "score_boolean": scores[0]["score"] = True
    elif defect == "score_string": scores[0]["score"] = "0.5"
    elif defect == "score_tokens_bool": scores[0]["tokens"] = True
    elif defect == "score_tokens_overflow": scores[0]["tokens"] = 8193
    elif defect == "job_binding": result["job_sha256"] = "0" * 64
    elif defect == "profile_binding": result["profile_sha256"] = "0" * 64
    elif defect == "kind": result["kind"] = "qwen-paid-response"
    elif defect == "schema_bool": result["schema_version"] = True
    elif defect == "extra_field": result["answer"] = "Invented verified result"
    wrapped_result = write_artifact(tmp_path / "results.json", result)
    before = fingerprint(store)
    with pytest.raises(ValueError):
        batch.import_results(store, project, job_path=job_path, job_sha256=wrapped["payload_sha256"],
                             results_path=tmp_path / "results.json", results_sha256=wrapped_result["payload_sha256"],
                             receipt_path=tmp_path / "receipt.json")
    assert not (tmp_path / "receipt.json").exists() and fingerprint(store) == before


@pytest.mark.parametrize("defect", ["backend", "device", "gpu_empty", "dtype", "attention", "devices_bool",
    "memory_zero", "peak_negative", "peak_overflow", "revision", "package", "truncation", "truncation_bool",
    "paid_call", "paid_bool", "token_max_mismatch", "elapsed_negative", "elapsed_bool", "elapsed_total_zero",
    "elapsed_sum", "cuda_missing", "cuda_bool", "cuda_empty", "missing", "extra"])
def test_runtime_rejects_wrong_contract_truncation_paid_calls_and_impossible_measures(corpus, tmp_path, defect):
    _, wrapped = export(corpus, tmp_path)
    result = synthetic_results(wrapped)
    runtime = result["runtime"]
    if defect == "backend": runtime["backend"] = "deepinfra"
    elif defect == "device": runtime["device"] = "cpu"
    elif defect == "gpu_empty": runtime["gpu_name"] = ""
    elif defect == "dtype": runtime["dtype"] = "bfloat16"
    elif defect == "attention": runtime["attention_implementation"] = "flash_attention_2"
    elif defect == "devices_bool": runtime["device_count"] = True
    elif defect == "memory_zero": runtime["total_memory_bytes"] = 0
    elif defect == "peak_negative": runtime["peak_vram_bytes"] = -1
    elif defect == "peak_overflow": runtime["peak_vram_bytes"] = runtime["total_memory_bytes"] + 1
    elif defect == "revision": runtime["model_revisions"]["embedding"] = "main"
    elif defect == "package": runtime["packages"]["transformers"] = "latest"
    elif defect == "truncation": runtime["truncated"] = True
    elif defect == "truncation_bool": runtime["truncated"] = 0
    elif defect == "paid_call": runtime["paid_inference_calls"] = 1
    elif defect == "paid_bool": runtime["paid_inference_calls"] = False
    elif defect == "token_max_mismatch": runtime["max_input_tokens"] = 23
    elif defect == "elapsed_negative": runtime["elapsed_seconds"]["embedding_load"] = -1
    elif defect == "elapsed_bool": runtime["elapsed_seconds"]["total"] = True
    elif defect == "elapsed_total_zero": runtime["elapsed_seconds"]["total"] = 0.0
    elif defect == "elapsed_sum": runtime["elapsed_seconds"]["total"] = 0.1
    elif defect == "cuda_missing": runtime.pop("cuda_version")
    elif defect == "cuda_bool": runtime["cuda_version"] = True
    elif defect == "cuda_empty": runtime["cuda_version"] = ""
    elif defect == "missing": runtime.pop("packages")
    elif defect == "extra": runtime["answer"] = "verified"
    store, project, *_ = corpus
    artifact = write_artifact(tmp_path / "results.json", result)
    before = fingerprint(store)
    with pytest.raises(ValueError):
        batch.import_results(store, project, job_path=tmp_path / "job.json", job_sha256=wrapped["payload_sha256"],
                             results_path=tmp_path / "results.json", results_sha256=artifact["payload_sha256"])
    assert fingerprint(store) == before


@pytest.mark.parametrize("artifact_name", ["job", "results"])
@pytest.mark.parametrize("defect", ["checksum", "trusted_hash", "duplicate_json_key", "nonfinite", "extra_envelope"])
def test_artifact_integrity_and_strict_json_fail_closed(corpus, tmp_path, artifact_name, defect):
    store, project, *_ = corpus
    job_path, job = export(corpus, tmp_path)
    result_path = tmp_path / "results.json"
    results = write_artifact(result_path, synthetic_results(job))
    selected = job if artifact_name == "job" else results
    path = job_path if artifact_name == "job" else result_path
    args = {"job_path": job_path, "job_sha256": job["payload_sha256"], "results_path": result_path,
            "results_sha256": results["payload_sha256"]}
    if defect == "checksum":
        selected["payload_sha256"] = "0" * 64
        path.write_text(json.dumps(selected))
    elif defect == "trusted_hash": args["job_sha256" if artifact_name == "job" else "results_sha256"] = "0" * 64
    elif defect == "duplicate_json_key": path.write_text(path.read_text().replace('"payload":', '"payload":null,"payload":', 1))
    elif defect == "nonfinite": path.write_text(path.read_text().replace('"payload":', '"unsupported":NaN,"payload":', 1))
    elif defect == "extra_envelope":
        selected["unexpected"] = True
        path.write_text(json.dumps(selected))
    before = fingerprint(store)
    with pytest.raises(ValueError): batch.import_results(store, project, **args)
    assert fingerprint(store) == before


@pytest.mark.parametrize("mutation", ["replace_source", "full_text_exclude", "study_link", "source_addition", "record_title"])
def test_import_rejects_stale_source_eligibility_and_metadata_before_receipt(corpus, tmp_path, mutation):
    store, project, record, _, *_ = corpus
    job_path, job = export(corpus, tmp_path)
    result_path = tmp_path / "results.json"
    results = write_artifact(result_path, synthetic_results(job))
    if mutation == "replace_source":
        store.attach_document(project, record, b"Changed exact source.", "txt", "Synthetic curator", "New active version")
    elif mutation == "full_text_exclude": store.record_decision(project, record, "full_text", "exclude", "Second synthetic curator", "Changed eligibility")
    elif mutation == "study_link":
        study = store.create_study(project, "Synthetic study", "Synthetic curator", "New grouping")
        store.record_study_links(project, record, [study["id"]], "Synthetic curator", "Changed study mapping")
    elif mutation == "source_addition": add_source(store, project, "New eligible source", ["New exact source."])
    elif mutation == "record_title":
        payload = json.loads(store._connection.execute("SELECT payload FROM records WHERE id=?", (record,)).fetchone()[0])
        payload["title"] = "Altered canonical metadata"
        store._connection.execute("UPDATE records SET payload=? WHERE id=?", (json.dumps(payload), record))
        store._connection.commit()
    before = fingerprint(store)
    with pytest.raises(ValueError):
        batch.import_results(store, project, job_path=job_path, job_sha256=job["payload_sha256"], results_path=result_path,
                             results_sha256=results["payload_sha256"], receipt_path=tmp_path / "receipt.json")
    assert not (tmp_path / "receipt.json").exists() and fingerprint(store) == before


@pytest.mark.parametrize("target", ["ledger", "wal", "shm", "job", "results", "existing", "symlink"])
def test_import_receipt_paths_protect_ledger_artifacts_and_existing_files(corpus, tmp_path, target):
    store, project, *_ = corpus
    job_path, job = export(corpus, tmp_path)
    result_path = tmp_path / "results.json"
    result = write_artifact(result_path, synthetic_results(job))
    database = tmp_path / "independent-batch.sqlite3"
    existing = tmp_path / "retained-source.txt"
    existing.write_text("Never overwrite this source")
    symlink = tmp_path / "alias-result.json"
    symlink.symlink_to(result_path)
    receipt = {"ledger": database, "wal": Path(str(database) + "-wal"), "shm": Path(str(database) + "-shm"),
               "job": job_path, "results": result_path, "existing": existing, "symlink": symlink}[target]
    before = fingerprint(store)
    initial = receipt.read_bytes() if receipt.exists() else None
    with pytest.raises(ValueError):
        batch.import_results(store, project, job_path=job_path, job_sha256=job["payload_sha256"], results_path=result_path,
                             results_sha256=result["payload_sha256"], receipt_path=receipt)
    assert (receipt.read_bytes() if receipt.exists() else None) == initial and fingerprint(store) == before


def test_import_receipt_is_immutable_and_shared_replay_is_identical(corpus, tmp_path):
    store, project, *_ = corpus
    receipt = tmp_path / "receipt.json"
    imported, job, results = import_fake(corpus, tmp_path, receipt_path=receipt)
    saved = receipt.read_bytes()
    assert imported["receipt_sha256"] == json.loads(saved)["payload_sha256"]
    replay = batch.import_results(store, project, job_path=tmp_path / "job.json", job_sha256=job["payload_sha256"],
                                  results_path=tmp_path / "results.json", results_sha256=results["payload_sha256"])
    assert {key: value for key, value in imported.items() if key != "receipt_sha256"} == replay
    with pytest.raises(ValueError):
        batch.import_results(store, project, job_path=tmp_path / "job.json", job_sha256=job["payload_sha256"],
                             results_path=tmp_path / "results.json", results_sha256=results["payload_sha256"], receipt_path=receipt)
    assert receipt.read_bytes() == saved


def test_batch_rejects_an_open_ledger_transaction(corpus, tmp_path):
    store, project, *_ = corpus
    job_path, job = export(corpus, tmp_path)
    results = write_artifact(tmp_path / "results.json", synthetic_results(job))
    store._connection.execute("BEGIN")
    try:
        with pytest.raises(ValueError):
            batch.export_job(store, project, QUERIES, output_path=tmp_path / "second.json")
        with pytest.raises(ValueError):
            batch.import_results(store, project, job_path=job_path, job_sha256=job["payload_sha256"],
                                 results_path=tmp_path / "results.json", results_sha256=results["payload_sha256"])
    finally:
        store._connection.rollback()


def test_unicode_long_spans_are_bounded_and_results_return_full_own_source_blocks(tmp_path):
    with ReviewStore(tmp_path / "long.sqlite3") as store:
        project = store.create_project("Long Unicode source", "scoping", "Exact Unicode spans?")["id"]
        literal = "Σ 🧪 café Straße " * 1000
        record, document = add_source(store, project, "Long independent Unicode", [literal])
        corpus = (store, project, record, document, None, None)
        path, job = export(corpus, tmp_path)
        representations = job["payload"]["representations"]
        assert len(representations) > 1
        full = job["payload"]["candidates"][0]["passage"]["anchor"]["quote"]
        assert full == literal.strip()
        assert "".join(rep["text"] for rep in representations) == full
        for rep in representations:
            assert rep["text"] == full[rep["start"]:rep["end"]]
            assert len(rep["text"].encode()) <= 6000
            assert rep["block_index"] == 0
        result = write_artifact(tmp_path / "results.json", synthetic_results(job))
        imported = batch.import_results(store, project, job_path=path, job_sha256=job["payload_sha256"],
                                        results_path=tmp_path / "results.json", results_sha256=result["payload_sha256"])
        for trace in imported["traces"]:
            assert trace["passages"][0]["anchor"] == {"block_id": job["payload"]["candidates"][0]["passage"]["anchor"]["block_id"],
                                                        "start": 0, "end": len(full), "quote": full}


def test_cpu_batch_import_does_not_import_heavy_model_packages():
    completed = subprocess.run([sys.executable, "-c", "import sys; import src.review.qwen_batch; "
                                "assert 'torch' not in sys.modules; assert 'transformers' not in sys.modules; "
                                "assert 'sentence_transformers' not in sys.modules"], cwd=ROOT, text=True, capture_output=True)
    assert completed.returncode == 0, completed.stderr


def test_standalone_runner_profile_lexical_and_hybrid_ranks_match_independent_reference(corpus, tmp_path):
    _, wrapped = export(corpus, tmp_path)
    assert digest(runner.PROFILE) == digest(batch.PROFILE)
    assert runner.validate_job(wrapped, wrapped["payload_sha256"]) == wrapped["payload"]
    result = synthetic_results(wrapped)
    for query, row in zip(wrapped["payload"]["queries"], result["query_results"], strict=True):
        assert runner.lexical_order(wrapped["payload"]["candidates"], query["query"], 20) == query["lexical_block_indices"]
        _, pool = independent_pool(wrapped["payload"], query, result["document_embeddings"], row["vector"])
        remote = runner.hybrid_pool(wrapped["payload"], query, [doc["vector"] for doc in result["document_embeddings"]], row["vector"])
        assert [rep["id"] for rep in remote] == pool


@pytest.mark.parametrize("defect", ["profile_bool", "profile_revision", "schema_bool", "scope", "bound_bool", "manifest_hash",
    "tie_bool", "anchor_bool", "anchor_clipped", "representation_bool", "representation_text", "representation_id",
    "representation_duplicate", "query_duplicate", "query_answer", "lexical_bool", "lexical_order"])
def test_standalone_runner_rejects_malformed_job_before_any_model_import(corpus, tmp_path, defect):
    _, original = export(corpus, tmp_path)
    job = deepcopy(original["payload"])
    if defect == "profile_bool": job["profile"]["schema_version"] = True
    elif defect == "profile_revision": job["profile"]["embedding_revision"] = "main"
    elif defect == "schema_bool": job["schema_version"] = True
    elif defect == "scope": job["scope"] = "other"
    elif defect == "bound_bool": job["top_k"] = True
    elif defect == "manifest_hash": job["source_snapshot_sha256"] = "0" * 64
    elif defect == "tie_bool": job["candidates"][0]["tie"][0] = False
    elif defect == "anchor_bool": job["candidates"][0]["passage"]["anchor"]["start"] = False
    elif defect == "anchor_clipped": job["candidates"][0]["passage"]["anchor"]["end"] -= 1
    elif defect == "representation_bool": job["representations"][0]["block_index"] = False
    elif defect == "representation_text": job["representations"][0]["text"] = "Clipped or invented source"
    elif defect == "representation_id": job["representations"][0]["id"] = "foreign"
    elif defect == "representation_duplicate": job["representations"][1] = deepcopy(job["representations"][0])
    elif defect == "query_duplicate": job["queries"][1] = deepcopy(job["queries"][0])
    elif defect == "query_answer": job["queries"][0]["answer"] = "Do not export truth"
    elif defect == "lexical_bool": job["queries"][0]["lexical_block_indices"][0] = False
    elif defect == "lexical_order": job["queries"][0]["lexical_block_indices"].reverse()
    wrapped = envelope(job)
    with pytest.raises(ValueError): runner.validate_job(wrapped, wrapped["payload_sha256"])


class FakeTokenizer:
    def __init__(self): self.calls = []
    def encode(self, text, *, add_special_tokens):
        self.calls.append((text, add_special_tokens))
        values = [ord(character) for character in text]
        return [7] + values + [8] if add_special_tokens else values


class FakeTorch:
    long = "fake-long"
    def __init__(self): self.calls = []
    def tensor(self, value, **kwargs):
        self.calls.append(("tensor", value, kwargs))
        return value
    def ones(self, shape, **kwargs):
        self.calls.append(("ones", shape, kwargs))
        return [[1] * shape[1]]


def test_runner_tokenizes_exact_document_query_instruction_and_author_rerank_prefix_suffix():
    tokenizer, torch = FakeTokenizer(), FakeTorch()
    document = "  Exact Straße α café 🧪.\r\nKeep the source.  "
    query = "  symptom difference at 12 months?  "
    inputs, count = runner._tokenize(tokenizer, document, torch)
    assert tokenizer.calls == [(document, True)]
    assert inputs["input_ids"] == [[7] + [ord(character) for character in document] + [8]]
    assert inputs["attention_mask"] == [[1] * count]
    assert all(call[2]["device"] == "cuda:0" for call in torch.calls)
    assert runner.embedding_query(query) == "Instruct: Retrieve source passages relevant to the research question.\nQuery: " + query
    body = runner.rerank_body(query, document)
    assert body == "<Instruct>: Retrieve source passages relevant to the research question.\n<Query>: " + query + "\n<Document>: " + document
    tokenizer, torch = FakeTokenizer(), FakeTorch()
    inputs, count = runner._tokenize(tokenizer, body, torch, rerank=True)
    assert tokenizer.calls == [(runner.RERANK_PREFIX, False), (body, False), (runner.RERANK_SUFFIX, False)]
    assert inputs["input_ids"] == [[ord(character) for character in runner.RERANK_PREFIX + body + runner.RERANK_SUFFIX]]
    assert count == len(runner.RERANK_PREFIX + body + runner.RERANK_SUFFIX)
    assert 'answer can only be "yes" or "no"' in runner.RERANK_PREFIX
    assert runner.RERANK_SUFFIX.endswith("<think>\n\n</think>\n\n")


@pytest.mark.parametrize("rerank", [False, True])
def test_runner_rejects_complete_overlength_input_before_cuda_allocation(rerank):
    tokenizer, torch = FakeTokenizer(), FakeTorch()
    with pytest.raises(ValueError, match="no input was truncated"):
        runner._tokenize(tokenizer, "x" * 8192, torch, rerank=rerank)
    assert torch.calls == []


@pytest.mark.parametrize("target", ["existing_output", "existing_checkpoint", "job_output", "job_checkpoint", "output_checkpoint", "wrong_hash"])
def test_runner_path_and_binding_preflight_precedes_heavy_imports(corpus, tmp_path, monkeypatch, target):
    import builtins
    job_path, job = export(corpus, tmp_path)
    output, checkpoint = tmp_path / "gpu-output.json", tmp_path / "gpu-checkpoint.json"
    expected = job["payload_sha256"]
    if target == "existing_output": output.write_text("preserve output")
    elif target == "existing_checkpoint": checkpoint.write_text("preserve checkpoint")
    elif target == "job_output": output = job_path
    elif target == "job_checkpoint": checkpoint = job_path
    elif target == "output_checkpoint": checkpoint = output
    elif target == "wrong_hash": expected = "0" * 64
    original_import = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.split(".", 1)[0] in {"torch", "transformers", "sentence_transformers"}:
            pytest.fail("Runner imported model packages before fixed-input validation")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    before = job_path.read_bytes()
    with pytest.raises(ValueError):
        runner.run_job(job_path, job_sha256=expected, output_path=output, checkpoint_path=checkpoint)
    assert job_path.read_bytes() == before


def test_notebook_code_compiles_without_running_dependencies_and_keeps_model_weights_out_of_saved_outputs():
    notebook = json.loads((ROOT / "notebooks/qwen_kaggle.ipynb").read_text())
    assert notebook["nbformat"] == 4
    code = []
    for index, cell in enumerate(notebook["cells"]):
        if cell["cell_type"] == "code":
            assert cell["outputs"] == [] and cell["execution_count"] is None
            source = "".join(cell["source"])
            compile(source, "qwen_kaggle.ipynb cell " + str(index), "exec")
            code.append(source)
    joined = "\n".join(code)
    assert "'/kaggle/temp/huggingface'" in joined
    assert "PASTE_TRUSTED_LOCAL_EXPORT_SHA256_HERE" in joined
    assert "runner.run_job" in joined
    assert all(name not in joined for name in ("DEEPINFRA_API_KEY", "api.deepinfra.com", "HF_TOKEN"))
    completed = subprocess.run([sys.executable, "-c", "import sys; import tools.qwen_kaggle_runner; "
                                "assert 'torch' not in sys.modules; assert 'transformers' not in sys.modules"],
                               cwd=ROOT, text=True, capture_output=True)
    assert completed.returncode == 0, completed.stderr


def test_legacy_paid_cli_is_blocked_before_credentials_network_or_ledger_creation(monkeypatch, tmp_path, capsys):
    from src.review import qwen_cli
    monkeypatch.setenv("DEEPINFRA_API_KEY", "independent-configured-key-never-load")
    database = tmp_path / "must-not-create.sqlite3"
    assert qwen_cli.main(["--db", str(database), "retrieve-qwen", "unopened-project", "--query", "symptom difference"]) == 1
    output = capsys.readouterr()
    assert "Paid inference is disabled" in output.err
    assert "independent-configured-key-never-load" not in output.err
    assert not database.exists()


def test_batch_cli_export_import_and_normal_command_delegation_are_offline(corpus, tmp_path, capsys, monkeypatch):
    from src.review import qwen_cli
    store, project, *_ = corpus
    database = tmp_path / "independent-batch.sqlite3"
    queries = tmp_path / "queries.json"
    queries.write_text(json.dumps(QUERIES))
    job_path = tmp_path / "cli-job.json"
    before = fingerprint(store)
    assert qwen_cli.main(["--db", str(database), "qwen-export", project, "--queries", str(queries), "--job", str(job_path)]) == 0
    printed = capsys.readouterr()
    summary = json.loads(printed.out)
    job = json.loads(job_path.read_text())
    assert summary["job_sha256"] == job["payload_sha256"] and summary["status"] == "exported"
    assert all(text not in printed.out for text in TEXTS)
    results = write_artifact(tmp_path / "cli-results.json", synthetic_results(job))
    assert qwen_cli.main(["--db", str(database), "qwen-import", project, "--job", str(job_path),
                          "--job-sha256", job["payload_sha256"], "--results", str(tmp_path / "cli-results.json"),
                          "--results-sha256", results["payload_sha256"], "--receipt", str(tmp_path / "cli-receipt.json")]) == 0
    imported = json.loads(capsys.readouterr().out)
    assert len(imported["traces"]) == len(QUERIES)
    assert imported["status"] == "candidate_passages" and fingerprint(store) == before
    received = []
    monkeypatch.setattr(qwen_cli.ledger_cli, "main", lambda argv: received.append(argv) or 17)
    args = ["--db", str(database), "retrieve", project, "--query", "qwen-export"]
    assert qwen_cli.main(args) == 17 and received == [args]
