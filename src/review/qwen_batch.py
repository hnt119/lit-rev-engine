"""Offline export/import boundary for finite Qwen GPU jobs on Kaggle.

This module never imports a model library or accesses a credential. Returned
passages remain candidates and never create screening or evidence ledger events.
"""

from copy import deepcopy
import math
import os
from pathlib import Path
import re
import tempfile

from .cloud_retrieval import _capture, _check_current, _pool, _read, _representations, _write
from .qwen import canonical, digest, read_json, validate_text
from .retrieval import _score, _snapshot_hash, _tokens


DEFAULT_PROFILE = {
    "schema_version": 1,
    "provider_contract": "kaggle-cuda-qwen4b-v1",
    "embedding_model": "Qwen/Qwen3-Embedding-4B",
    "embedding_revision": "5cf2132abc99cad020ac570b19d031efec650f2b",
    "reranker_model": "Qwen/Qwen3-Reranker-4B",
    "reranker_revision": "22e683669bc0f0bd69640a1354a6d0aebcfeede5",
    "dimension": 2560,
    "query_instruction": "Retrieve source passages relevant to the research question.",
    "rerank_instruction": "Retrieve source passages relevant to the research question.",
    "query_encoding": "Instruct: {instruction}\nQuery: {query}",
    "document_encoding": "unprefixed-within-block-utf8-spans-v1",
    "rerank_encoding": "qwen-author-prefix-body-suffix-v1",
    "pooling": "last-attended-token",
    "normalization": "float32-l2",
    "distance": "cosine",
    "fusion": "RRF-k60;max-span-cosine-per-block;stable-source-order-v1",
    "block_score": "maximum-representation-relevance",
    "max_document_bytes": 6000,
    "max_query_bytes": 2000,
    "max_representations": 1000,
    "max_queries": 100,
    "max_tokens": 8192,
    "batch_size": 1,
    "dtype": "float16",
    "attention_implementation": "sdpa",
    "length_policy": "count-complete-tokenized-input;reject-overlength;no-truncation",
    "packages": {"transformers": "4.51.3", "tokenizers": "0.21.1",
                 "safetensors": "0.5.3", "huggingface-hub": "0.30.2"},
}
PROFILE = DEFAULT_PROFILE


class _RepresentationLimits:
    max_document_bytes = DEFAULT_PROFILE["max_document_bytes"]
    max_representations = DEFAULT_PROFILE["max_representations"]


def _queries(queries):
    if not isinstance(queries, list) or not 1 <= len(queries) <= DEFAULT_PROFILE["max_queries"]:
        raise ValueError("Kaggle job requires 1 to 100 queries")
    clean, seen = [], set()
    for row in queries:
        if not isinstance(row, dict) or set(row) != {"id", "query"}:
            raise ValueError("Each Kaggle query must contain only id and query; do not export gold answers")
        identifier = row["id"]
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", identifier) or identifier in seen:
            raise ValueError("Kaggle query ids must be unique safe strings")
        validate_text(row["query"], DEFAULT_PROFILE["max_query_bytes"], "query")
        seen.add(identifier)
        clean.append(dict(row))
    return clean


def _artifact_paths(store, *paths):
    resolved = [Path(path).resolve() for path in paths if path is not None]
    if len(set(resolved)) != len(resolved):
        raise ValueError("Kaggle job, results and receipt paths must be distinct")
    protected = set()
    for row in store._connection.execute("PRAGMA database_list"):
        if row[2]:
            database = Path(row[2]).resolve()
            protected.update((database, Path(str(database) + "-wal"), Path(str(database) + "-shm")))
    for path in paths:
        if path is None:
            continue
        path = Path(path)
        if path.resolve() in protected:
            raise ValueError("Kaggle artifacts cannot overwrite or read the ledger or its WAL files")
        if path.exists() and any(held.exists() and os.path.samefile(path, held) for held in protected):
            raise ValueError("Kaggle artifact is a hard link to the ledger or its WAL files")


def _write_new(path, payload):
    """Publish once, including under racing writers; never follow an output link."""
    path = Path(path)
    if os.path.lexists(path):
        raise ValueError("Kaggle artifacts are immutable; choose a new output path")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".qwen-batch-", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        _write(temporary, payload)
        try:
            os.link(temporary, path)
        except FileExistsError:
            raise ValueError("Kaggle artifacts are immutable; choose a new output path") from None
    finally:
        temporary.unlink(missing_ok=True)


def _build_job(store, project_id, queries, scope, top_k, candidate_k):
    if store._connection.in_transaction:
        raise ValueError("Kaggle export/import cannot run inside an existing ledger transaction")
    queries = _queries(queries)
    if scope not in {"included", "all_attached"}:
        raise ValueError("Kaggle scope must be included or all_attached")
    if type(top_k) is not int or type(candidate_k) is not int or not 1 <= top_k <= candidate_k <= 100:
        raise ValueError("Kaggle limits must satisfy 1 <= top_k <= candidate_k <= 100")
    manifest, candidates = _capture(store, project_id, scope)
    reps = _representations(candidates, _RepresentationLimits())
    if not reps:
        raise ValueError("Kaggle job has no eligible source passages")
    positions = {id(candidate): index for index, candidate in enumerate(candidates)}
    decorated = [{**row, "lexical_block_indices": [positions[id(candidate)] for _, candidate in
                  _score(candidates, sorted(set(_tokens(row["query"]))), "bm25_context_blocks")[:candidate_k]]}
                 for row in queries]
    payload = {"schema_version": 1, "kind": "qwen-kaggle-job-v1", "project_id": project_id,
               "scope": scope, "top_k": top_k, "candidate_k": candidate_k,
               "profile": deepcopy(DEFAULT_PROFILE), "profile_sha256": digest(DEFAULT_PROFILE),
               "source_manifest": manifest, "source_snapshot_sha256": _snapshot_hash(manifest),
               "candidates": [{"passage": row["passage"], "tie": list(row["tie"])} for row in candidates],
               "representations": reps, "queries": decorated}
    # Match the bytes that cross the notebook boundary; never retain tuples or Counter objects.
    return read_json(canonical(payload)), manifest, candidates


def export_job(store, project_id, queries, *, output_path, scope="included", top_k=5, candidate_k=20):
    """Export only queries and selected source passages, with no gold or credentials."""
    _artifact_paths(store, output_path)
    if os.path.lexists(output_path):
        raise ValueError("Kaggle jobs are immutable; choose a new output path")
    payload, manifest, candidates = _build_job(store, project_id, queries, scope, top_k, candidate_k)
    _check_current(store, project_id, scope, manifest, candidates)
    _write_new(output_path, payload)
    return {"payload": payload, "payload_sha256": digest(payload)}


def _vector(value):
    if not isinstance(value, list) or len(value) != DEFAULT_PROFILE["dimension"]:
        raise ValueError("Kaggle embedding dimension mismatch")
    if any(type(number) not in (int, float) or not math.isfinite(number) for number in value):
        raise ValueError("Kaggle embeddings must contain finite numbers")
    if abs(math.hypot(*value) - 1.0) > 0.0001:
        raise ValueError("Kaggle embeddings must be nonzero unit vectors")
    return value


def _tokens_used(value):
    if type(value) is not int or not 1 <= value <= DEFAULT_PROFILE["max_tokens"]:
        raise ValueError("Kaggle token count is missing or exceeds the no-truncation bound")
    return value


def _runtime(runtime, token_counts):
    fields = {"backend", "device", "gpu_name", "device_count", "total_memory_bytes", "cuda_version", "dtype",
              "attention_implementation", "packages", "model_revisions", "elapsed_seconds",
              "peak_vram_bytes", "max_input_tokens", "truncated", "paid_inference_calls"}
    if not isinstance(runtime, dict) or set(runtime) != fields:
        raise ValueError("Kaggle runtime metadata is incomplete")
    if (runtime["backend"] != "kaggle-cuda-transformers" or runtime["device"] != "cuda:0"
            or runtime["dtype"] != "float16" or runtime["attention_implementation"] != "sdpa"
            or runtime["truncated"] is not False or type(runtime["paid_inference_calls"]) is not int
            or runtime["paid_inference_calls"] != 0):
        raise ValueError("Kaggle result requires the declared CUDA runtime and zero paid inference calls")
    if not isinstance(runtime["gpu_name"], str) or not runtime["gpu_name"].strip():
        raise ValueError("Kaggle runtime must identify the GPU")
    if not isinstance(runtime["cuda_version"], str) or not runtime["cuda_version"].strip():
        raise ValueError("Kaggle runtime must identify its CUDA version")
    for name in ("device_count", "total_memory_bytes", "peak_vram_bytes"):
        if type(runtime[name]) is not int or runtime[name] <= 0:
            raise ValueError("Kaggle runtime GPU memory/device metadata is invalid")
    if runtime["peak_vram_bytes"] > runtime["total_memory_bytes"]:
        raise ValueError("Kaggle peak GPU memory exceeds device memory")
    packages = runtime["packages"]
    if not isinstance(packages, dict) or set(packages) != set(DEFAULT_PROFILE["packages"]) | {"torch", "python"}:
        raise ValueError("Kaggle runtime package versions are incomplete")
    if any(packages[name] != version for name, version in DEFAULT_PROFILE["packages"].items()):
        raise ValueError("Kaggle runtime package versions differ from the pinned profile")
    if any(not isinstance(packages[name], str) or not packages[name].strip() for name in ("torch", "python")):
        raise ValueError("Kaggle runtime requires the actual Torch and Python versions")
    if runtime["model_revisions"] != {"embedding": DEFAULT_PROFILE["embedding_revision"],
                                      "reranker": DEFAULT_PROFILE["reranker_revision"]}:
        raise ValueError("Kaggle runtime model revisions differ from the pinned profile")
    elapsed = runtime["elapsed_seconds"]
    if not isinstance(elapsed, dict) or set(elapsed) != {"total", "embedding_load", "embedding_inference", "reranker_load", "reranker_inference"}:
        raise ValueError("Kaggle runtime elapsed stages are incomplete")
    if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in elapsed.values()):
        raise ValueError("Kaggle runtime elapsed times must be finite and nonnegative")
    if elapsed["total"] <= 0 or elapsed["total"] + 0.000001 < sum(value for name, value in elapsed.items() if name != "total"):
        raise ValueError("Kaggle total runtime contradicts its recorded stages")
    if type(runtime["max_input_tokens"]) is not int or runtime["max_input_tokens"] != max(token_counts):
        raise ValueError("Kaggle maximum token count contradicts recorded inputs")


def import_results(store, project_id, *, job_path, job_sha256, results_path,
                   results_sha256=None, receipt_path=None):
    """Reconstruct candidates from returned numbers; reject any stale local source."""
    if store._connection.in_transaction:
        raise ValueError("Kaggle export/import cannot run inside an existing ledger transaction")
    _artifact_paths(store, job_path, results_path, receipt_path)
    if receipt_path is not None and os.path.lexists(receipt_path):
        raise ValueError("Kaggle receipts are immutable; choose a new output path")
    job_envelope, result_envelope = _read(job_path), _read(results_path)
    if not isinstance(job_sha256, str) or job_envelope["payload_sha256"] != job_sha256:
        raise ValueError("Kaggle import requires the trusted original job_sha256")
    if results_sha256 is not None and result_envelope["payload_sha256"] != results_sha256:
        raise ValueError("Kaggle results differ from the trusted results_sha256")
    job = job_envelope["payload"]
    job_fields = {"schema_version", "kind", "project_id", "scope", "top_k", "candidate_k", "profile",
                  "profile_sha256", "source_manifest", "source_snapshot_sha256", "candidates", "representations", "queries"}
    if not isinstance(job, dict) or set(job) != job_fields or type(job["schema_version"]) is not int or job["schema_version"] != 1 or job["kind"] != "qwen-kaggle-job-v1":
        raise ValueError("Kaggle job schema mismatch")
    if digest(job["profile"]) != digest(DEFAULT_PROFILE) or job["profile_sha256"] != digest(DEFAULT_PROFILE) or job["project_id"] != project_id:
        raise ValueError("Kaggle job project or pinned profile mismatch")
    if not isinstance(job["queries"], list) or any(not isinstance(row, dict) or set(row) != {"id", "query", "lexical_block_indices"} for row in job["queries"]):
        raise ValueError("Kaggle job query schema mismatch")
    current, manifest, candidates = _build_job(store, project_id, [{"id": row["id"], "query": row["query"]} for row in job["queries"]],
                                               job["scope"], job["top_k"], job["candidate_k"])
    if canonical(current) != canonical(job):
        raise ValueError("Kaggle job source, eligibility, query or candidate snapshot is stale or inconsistent")
    results = result_envelope["payload"]
    if (not isinstance(results, dict) or set(results) != {"schema_version", "kind", "job_sha256", "profile_sha256", "document_embeddings", "query_results", "runtime"}
            or type(results["schema_version"]) is not int or results["schema_version"] != 1 or results["kind"] != "qwen-kaggle-results-v1"
            or results["job_sha256"] != job_sha256 or results["profile_sha256"] != job["profile_sha256"]):
        raise ValueError("Kaggle result job/profile binding mismatch")
    reps, document_rows = job["representations"], results["document_embeddings"]
    if not isinstance(document_rows, list) or len(document_rows) != len(reps):
        raise ValueError("Kaggle document embedding count mismatch")
    vectors, counts = [], []
    for rep, row in zip(reps, document_rows, strict=True):
        if not isinstance(row, dict) or set(row) != {"id", "vector", "tokens"} or row["id"] != rep["id"]:
            raise ValueError("Kaggle document embedding IDs or order mismatch")
        vectors.append(_vector(row["vector"]))
        counts.append(_tokens_used(row["tokens"]))
    query_rows = results["query_results"]
    if not isinstance(query_rows, list) or len(query_rows) != len(job["queries"]):
        raise ValueError("Kaggle query result count mismatch")
    traces = []
    for query, row in zip(job["queries"], query_rows, strict=True):
        if not isinstance(row, dict) or set(row) != {"id", "vector", "tokens", "pool_representation_ids", "rerank_scores"} or row["id"] != query["id"]:
            raise ValueError("Kaggle query IDs or order mismatch")
        vector = _vector(row["vector"])
        counts.append(_tokens_used(row["tokens"]))
        pool = _pool(candidates, query["query"], "qwen_hybrid", job["candidate_k"], reps, vectors, vector)
        pool_reps = [rep for index in pool for rep in reps if rep["block_index"] == index]
        if row["pool_representation_ids"] != [rep["id"] for rep in pool_reps]:
            raise ValueError("Kaggle candidate pool contradicts locally recomputed RRF")
        scores = row["rerank_scores"]
        if not isinstance(scores, list) or len(scores) != len(pool_reps):
            raise ValueError("Kaggle rerank score count mismatch")
        block_scores = {}
        for rep, score in zip(pool_reps, scores, strict=True):
            if not isinstance(score, dict) or set(score) != {"id", "score", "tokens"} or score["id"] != rep["id"]:
                raise ValueError("Kaggle rerank representation IDs or order mismatch")
            number = score["score"]
            if type(number) not in (int, float) or not math.isfinite(number) or not 0 <= number <= 1:
                raise ValueError("Kaggle rerank relevance must be a finite probability")
            counts.append(_tokens_used(score["tokens"]))
            block = rep["block_index"]
            block_scores[block] = max(block_scores.get(block, -math.inf), number)
        order = sorted(block_scores, key=lambda index: (-block_scores[index], candidates[index]["tie"]))
        traces.append({"schema_version": 1, "status": "candidate_passages", "project_id": project_id,
                       "query_id": query["id"], "query": query["query"], "method": "qwen_kaggle_hybrid",
                       "method_version": "lit-rev-engine.project-retrieval.kaggle-qwen.v1.qwen_hybrid",
                       "parameters": {"profile_sha256": job["profile_sha256"], "candidate_k": job["candidate_k"],
                                      "fusion": DEFAULT_PROFILE["fusion"], "block_score": DEFAULT_PROFILE["block_score"]},
                       "scope": job["scope"], "top_k": job["top_k"], "source_manifest": manifest,
                       "source_snapshot_sha256": job["source_snapshot_sha256"], "indexed_passages": len(candidates),
                       "matched_passages": len(order), "candidate_pool_size": len(pool), "profile": deepcopy(DEFAULT_PROFILE),
                       "answerability": "not_assessed", "verification": "human_review_required",
                       "execution": "offline_import", "job_sha256": job_sha256,
                       "results_sha256": result_envelope["payload_sha256"],
                       "passages": [{"rank": rank, "score": block_scores[index], **candidates[index]["passage"]}
                                    for rank, index in enumerate(order[:job["top_k"]], 1)]})
    _runtime(results["runtime"], counts)
    result = {"schema_version": 1, "status": "candidate_passages", "job_sha256": job_sha256,
              "results_sha256": result_envelope["payload_sha256"], "profile": deepcopy(DEFAULT_PROFILE),
              "runtime": deepcopy(results["runtime"]), "traces": traces}
    _check_current(store, project_id, job["scope"], manifest, candidates)
    if receipt_path is not None:
        receipt = {"schema_version": 1, "kind": "qwen-kaggle-receipt-v1", "job": job_envelope,
                   "results": result_envelope, "recomputed": result}
        _write_new(receipt_path, receipt)
        result["receipt_sha256"] = digest(receipt)
    return result
