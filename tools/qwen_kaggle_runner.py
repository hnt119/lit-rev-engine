"""Standalone, finite Qwen job runner; import is safe without CUDA/model packages.

Upload this file and an exported job to a private Kaggle input dataset. Run only
with a CUDA GPU and the declared dependencies. No inference provider or API key
is used, and no review-engine checkout or ledger is required in the notebook.
"""

import argparse
from collections import Counter
from copy import deepcopy
import gc
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import tempfile
import time


PROFILE = {
    "schema_version": 1, "provider_contract": "kaggle-cuda-qwen4b-v1",
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
    "pooling": "last-attended-token", "normalization": "float32-l2", "distance": "cosine",
    "fusion": "RRF-k60;max-span-cosine-per-block;stable-source-order-v1",
    "block_score": "maximum-representation-relevance",
    "max_document_bytes": 6000, "max_query_bytes": 2000, "max_representations": 1000,
    "max_queries": 100, "max_tokens": 8192, "batch_size": 1, "dtype": "float16",
    "attention_implementation": "sdpa",
    "length_policy": "count-complete-tokenized-input;reject-overlength;no-truncation",
    "packages": {"transformers": "4.51.3", "tokenizers": "0.21.1",
                 "safetensors": "0.5.3", "huggingface-hub": "0.30.2"},
}
_STOP_WORDS = frozenset("a an and are as at be been by did do does for from had has have how in is it its of on or that the their there these this to was were what when where which who with would".split())
RERANK_PREFIX = '<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
RERANK_SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"


def canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, UnicodeError):
        raise ValueError("Job data must be finite valid JSON") from None


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def read_artifact(path):
    path = Path(path)
    if path.stat().st_size > 100 * 1024 * 1024:
        raise ValueError("Artifact exceeds 100 MiB")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    try:
        envelope = json.loads(path.read_bytes(), object_pairs_hook=pairs,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
        canonical(envelope)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ValueError("Invalid artifact JSON") from None
    if not isinstance(envelope, dict) or set(envelope) != {"payload", "payload_sha256"} or envelope["payload_sha256"] != digest(envelope["payload"]):
        raise ValueError("Artifact checksum mismatch")
    return envelope


def _write(path, payload, *, replace_checkpoint=False):
    path = Path(path)
    encoded = canonical({"payload": payload, "payload_sha256": digest(payload)}).encode("utf-8")
    if len(encoded) > 100 * 1024 * 1024:
        raise ValueError("Artifact exceeds 100 MiB")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".qwen-kaggle-", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        if replace_checkpoint:
            if path.is_symlink():
                raise ValueError("Checkpoint cannot be a symlink")
            held = read_artifact(path)["payload"]
            if held.get("kind") != "qwen-kaggle-checkpoint-v1" or held.get("job_sha256") != payload.get("job_sha256") or held.get("profile_sha256") != payload.get("profile_sha256"):
                raise ValueError("Checkpoint belongs to a different job")
            temporary.replace(path)
        else:
            try:
                os.link(temporary, path)
            except FileExistsError:
                raise ValueError("Output already exists; choose a new immutable output path") from None
    finally:
        temporary.unlink(missing_ok=True)


def _terms(text):
    return [word for word in re.findall(r"\w+", text.casefold()) if word not in _STOP_WORDS]


def lexical_order(candidates, query, limit):
    terms = []
    for row in candidates:
        passage = row["passage"]
        words = Counter(_terms(passage["anchor"]["quote"]))
        for context in passage.get("scoring_context", []):
            words.update(_terms(context["anchor"]["quote"]))
        terms.append(words)
    count = len(terms)
    average = sum(sum(words.values()) for words in terms) / count
    document_frequency = Counter(term for words in terms for term in words)
    ranked = []
    for index, words in enumerate(terms):
        score = 0.0
        for term in sorted(set(_terms(query))):
            frequency = words.get(term, 0)
            if frequency:
                idf = math.log(1 + (count - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
                score += idf * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * sum(words.values()) / average))
        if score > 0:
            ranked.append((score, index))
    ranked.sort(key=lambda row: (-row[0], candidates[row[1]]["tie"]))
    return [index for _, index in ranked[:limit]]


def validate_job(envelope, expected_sha256):
    if not isinstance(expected_sha256, str) or envelope["payload_sha256"] != expected_sha256:
        raise ValueError("Use the trusted job SHA-256 returned by the local export")
    job = envelope["payload"]
    fields = {"schema_version", "kind", "project_id", "scope", "top_k", "candidate_k", "profile", "profile_sha256",
              "source_manifest", "source_snapshot_sha256", "candidates", "representations", "queries"}
    if not isinstance(job, dict) or set(job) != fields or type(job["schema_version"]) is not int or job["schema_version"] != 1 or job["kind"] != "qwen-kaggle-job-v1":
        raise ValueError("Unsupported Kaggle job schema")
    if digest(job["profile"]) != digest(PROFILE) or job["profile_sha256"] != digest(PROFILE):
        raise ValueError("Job profile differs from the fixed, validated Qwen profile")
    if job["scope"] not in {"included", "all_attached"} or type(job["top_k"]) is not int or type(job["candidate_k"]) is not int or not 1 <= job["top_k"] <= job["candidate_k"] <= 100:
        raise ValueError("Job scope or ranking bounds are invalid")
    if not isinstance(job["source_manifest"], list) or not job["source_manifest"] or digest(job["source_manifest"]) != job["source_snapshot_sha256"]:
        raise ValueError("Job source manifest checksum mismatch")
    candidates, reps, queries = job["candidates"], job["representations"], job["queries"]
    if not isinstance(candidates, list) or not candidates or not isinstance(reps, list) or not 1 <= len(reps) <= PROFILE["max_representations"]:
        raise ValueError("Job requires a bounded nonempty source snapshot")
    for row in candidates:
        if not isinstance(row, dict) or set(row) != {"passage", "tie"} or not isinstance(row["tie"], list) or len(row["tie"]) != 4 or any(type(value) is not int or value < 0 for value in row["tie"]):
            raise ValueError("Job candidate ordering is malformed")
        passage = row["passage"]
        if not isinstance(passage, dict) or passage.get("project_id") != job["project_id"] or not isinstance(passage.get("anchor"), dict):
            raise ValueError("Job candidate project or anchor mismatch")
        anchor = passage["anchor"]
        if (set(anchor) != {"block_id", "start", "end", "quote"} or not isinstance(anchor["quote"], str)
                or not anchor["quote"].strip() or type(anchor["start"]) is not int or anchor["start"] != 0
                or type(anchor["end"]) is not int or anchor["end"] != len(anchor["quote"])):
            raise ValueError("Job candidate must retain its complete canonical own block")
    seen = set()
    for rep in reps:
        if not isinstance(rep, dict) or set(rep) != {"id", "block_index", "start", "end", "text"} or type(rep["block_index"]) is not int or not 0 <= rep["block_index"] < len(candidates):
            raise ValueError("Job representation schema or block reference mismatch")
        passage = candidates[rep["block_index"]]["passage"]
        if (type(rep["start"]) is not int or type(rep["end"]) is not int or not 0 <= rep["start"] < rep["end"] <= len(passage["anchor"]["quote"])
                or rep["text"] != passage["anchor"]["quote"][rep["start"]:rep["end"]]
                or len(rep["text"].encode("utf-8")) > PROFILE["max_document_bytes"] or not rep["text"].strip()):
            raise ValueError("Job representation is not an exact bounded within-block span")
        expected = digest({"document_id": passage["document_id"], "block_id": passage["anchor"]["block_id"],
                           "start": rep["start"], "end": rep["end"], "text": rep["text"]})
        if rep["id"] != expected or rep["id"] in seen:
            raise ValueError("Job representation ID mismatch or duplicate")
        seen.add(rep["id"])
    if not isinstance(queries, list) or not 1 <= len(queries) <= PROFILE["max_queries"]:
        raise ValueError("Job query count is invalid")
    seen = set()
    for row in queries:
        if not isinstance(row, dict) or set(row) != {"id", "query", "lexical_block_indices"} or not isinstance(row["id"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", row["id"]) or row["id"] in seen:
            raise ValueError("Job query IDs/schema are invalid; only id/query may be exported")
        seen.add(row["id"])
        if not isinstance(row["query"], str) or not row["query"].strip() or len(row["query"].encode("utf-8")) > PROFILE["max_query_bytes"]:
            raise ValueError("Job query exceeds the input bound")
        if canonical(row["lexical_block_indices"]) != canonical(lexical_order(candidates, row["query"], job["candidate_k"])):
            raise ValueError("Job lexical ordering contradicts the source snapshot")
    return job


def hybrid_pool(job, query, document_vectors, query_vector):
    dense = {}
    for rep, vector in zip(job["representations"], document_vectors, strict=True):
        score = sum(a * b for a, b in zip(query_vector, vector, strict=True))
        if not math.isfinite(score):
            raise ValueError("Dense similarity is nonfinite")
        block = rep["block_index"]
        dense[block] = max(dense.get(block, -math.inf), score)
    dense_order = sorted(dense, key=lambda index: (-dense[index], job["candidates"][index]["tie"]))[:job["candidate_k"]]
    fused = {}
    for ordering in (query["lexical_block_indices"], dense_order):
        for rank, index in enumerate(ordering, 1):
            fused[index] = fused.get(index, 0.0) + 1 / (60 + rank)
    blocks = sorted(fused, key=lambda index: (-fused[index], job["candidates"][index]["tie"]))[:job["candidate_k"]]
    return [rep for index in blocks for rep in job["representations"] if rep["block_index"] == index]


def embedding_query(query):
    return f"Instruct: {PROFILE['query_instruction']}\nQuery: {query}"


def rerank_body(query, document):
    return f"<Instruct>: {PROFILE['rerank_instruction']}\n<Query>: {query}\n<Document>: {document}"


def _tokenize(tokenizer, text, torch, *, rerank=False):
    if rerank:
        ids = (tokenizer.encode(RERANK_PREFIX, add_special_tokens=False)
               + tokenizer.encode(text, add_special_tokens=False)
               + tokenizer.encode(RERANK_SUFFIX, add_special_tokens=False))
    else:
        ids = tokenizer.encode(text, add_special_tokens=True)
    if not 1 <= len(ids) <= PROFILE["max_tokens"]:
        raise ValueError("Complete tokenized input exceeds 8192 tokens; no input was truncated")
    return {"input_ids": torch.tensor([ids], dtype=torch.long, device="cuda:0"),
            "attention_mask": torch.ones((1, len(ids)), dtype=torch.long, device="cuda:0")}, len(ids)


def run_job(job_path, *, job_sha256, output_path, checkpoint_path):
    """Execute once; checkpoint intermediate embeddings, but never silently resume."""
    paths = [Path(path) for path in (job_path, output_path, checkpoint_path)]
    if len({path.resolve() for path in paths}) != 3:
        raise ValueError("Job, output and checkpoint paths must be distinct")
    for path in paths[1:]:
        if os.path.lexists(path):
            raise ValueError("Output/checkpoint already exists; preserve it and choose new paths")
    envelope = read_artifact(job_path)
    job = validate_job(envelope, job_sha256)
    started = time.monotonic()
    # Import only after the fixed job and immutable output paths have been checked.
    import torch
    if not torch.cuda.is_available():
        raise ValueError("A Kaggle CUDA GPU is required; no CPU/Mac or paid fallback is available")
    from transformers import AutoModel, AutoModelForCausalLM, AutoTokenizer
    packages = {name: importlib.metadata.version(name) for name in PROFILE["packages"]}
    if packages != PROFILE["packages"]:
        raise ValueError("Install the exact notebook dependency versions before running")
    torch.manual_seed(0)
    torch.cuda.set_device(0)
    torch.cuda.reset_peak_memory_stats(0)
    stages = {"embedding_load": 0.0, "embedding_inference": 0.0, "reranker_load": 0.0, "reranker_inference": 0.0}
    documents, queries = [], []
    properties = torch.cuda.get_device_properties(0)

    def checkpoint(phase):
        payload = {"schema_version": 1, "kind": "qwen-kaggle-checkpoint-v1", "job_sha256": job_sha256,
                   "profile_sha256": job["profile_sha256"], "phase": phase,
                   "document_embeddings": documents, "query_results": queries,
                   "elapsed_seconds": {**stages, "total": time.monotonic() - started}}
        _write(checkpoint_path, payload, replace_checkpoint=Path(checkpoint_path).exists())

    begin = time.monotonic()
    tokenizer = AutoTokenizer.from_pretrained(PROFILE["embedding_model"], revision=PROFILE["embedding_revision"], padding_side="left", trust_remote_code=False, token=False)
    model = AutoModel.from_pretrained(PROFILE["embedding_model"], revision=PROFILE["embedding_revision"],
                                     torch_dtype=torch.float16, attn_implementation="sdpa", use_safetensors=True,
                                     trust_remote_code=False, token=False).to("cuda:0").eval()
    torch.cuda.synchronize()
    stages["embedding_load"] = time.monotonic() - begin

    def embed(text):
        inputs, count = _tokenize(tokenizer, text, torch)
        with torch.inference_mode():
            hidden = model(**inputs, use_cache=False).last_hidden_state
            # Single input, no padding: the last token is the last attended token.
            vector = torch.nn.functional.normalize(hidden[:, -1, :].float(), p=2, dim=1)[0].cpu().tolist()
        if len(vector) != PROFILE["dimension"] or any(not math.isfinite(value) for value in vector) or abs(math.hypot(*vector) - 1.0) > 0.0001:
            raise ValueError("Model returned an invalid normalized embedding")
        return vector, count

    try:
        for rep in job["representations"]:
            begin = time.monotonic()
            vector, count = embed(rep["text"])
            torch.cuda.synchronize()
            stages["embedding_inference"] += time.monotonic() - begin
            documents.append({"id": rep["id"], "vector": vector, "tokens": count})
            checkpoint("embedding")
        for query in job["queries"]:
            begin = time.monotonic()
            vector, count = embed(embedding_query(query["query"]))
            torch.cuda.synchronize()
            stages["embedding_inference"] += time.monotonic() - begin
            pool = hybrid_pool(job, query, [row["vector"] for row in documents], vector)
            queries.append({"id": query["id"], "vector": vector, "tokens": count,
                            "pool_representation_ids": [rep["id"] for rep in pool], "rerank_scores": []})
            checkpoint("embedding")
    finally:
        del model, tokenizer
        gc.collect()
        torch.cuda.empty_cache()
    begin = time.monotonic()
    tokenizer = AutoTokenizer.from_pretrained(PROFILE["reranker_model"], revision=PROFILE["reranker_revision"], padding_side="left", trust_remote_code=False, token=False)
    model = AutoModelForCausalLM.from_pretrained(PROFILE["reranker_model"], revision=PROFILE["reranker_revision"],
                                              torch_dtype=torch.float16, attn_implementation="sdpa", use_safetensors=True,
                                              trust_remote_code=False, token=False).to("cuda:0").eval()
    torch.cuda.synchronize()
    stages["reranker_load"] = time.monotonic() - begin
    yes, no = tokenizer.convert_tokens_to_ids("yes"), tokenizer.convert_tokens_to_ids("no")
    if type(yes) is not int or type(no) is not int or yes == no or yes < 0 or no < 0:
        raise ValueError("Reranker yes/no token IDs are invalid")
    representations = {rep["id"]: rep for rep in job["representations"]}
    try:
        for query, row in zip(job["queries"], queries, strict=True):
            for identifier in row["pool_representation_ids"]:
                begin = time.monotonic()
                rep = representations[identifier]
                inputs, count = _tokenize(tokenizer, rerank_body(query["query"], rep["text"]), torch, rerank=True)
                with torch.inference_mode():
                    logits = model(**inputs, use_cache=False, logits_to_keep=1).logits[0, -1, :]
                    score = torch.softmax(torch.stack([logits[no], logits[yes]]).float(), dim=0)[1].item()
                if not math.isfinite(score) or not 0 <= score <= 1:
                    raise ValueError("Model returned an invalid relevance probability")
                torch.cuda.synchronize()
                stages["reranker_inference"] += time.monotonic() - begin
                row["rerank_scores"].append({"id": identifier, "score": score, "tokens": count})
                checkpoint("reranking")
    finally:
        del model, tokenizer
        gc.collect()
        torch.cuda.empty_cache()
    counts = [row["tokens"] for row in documents] + [row["tokens"] for row in queries] + [score["tokens"] for row in queries for score in row["rerank_scores"]]
    runtime = {"backend": "kaggle-cuda-transformers", "device": "cuda:0", "gpu_name": properties.name,
               "device_count": torch.cuda.device_count(), "total_memory_bytes": properties.total_memory,
               "cuda_version": torch.version.cuda,
               "dtype": "float16", "attention_implementation": "sdpa",
               "packages": {**packages, "torch": torch.__version__, "python": platform.python_version()},
               "model_revisions": {"embedding": PROFILE["embedding_revision"], "reranker": PROFILE["reranker_revision"]},
               "elapsed_seconds": {**stages, "total": time.monotonic() - started},
               "peak_vram_bytes": torch.cuda.max_memory_allocated(0), "max_input_tokens": max(counts),
               "truncated": False, "paid_inference_calls": 0}
    result = {"schema_version": 1, "kind": "qwen-kaggle-results-v1", "job_sha256": job_sha256,
              "profile_sha256": job["profile_sha256"], "document_embeddings": documents,
              "query_results": queries, "runtime": runtime}
    checkpoint("complete")
    _write(output_path, result)
    return {"output_path": str(output_path), "results_sha256": digest(result), "runtime": runtime}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True)
    parser.add_argument("--job-sha256", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--checkpoint", required=True)
    args = parser.parse_args(argv)
    print(canonical(run_job(args.job, job_sha256=args.job_sha256, output_path=args.output, checkpoint_path=args.checkpoint)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
