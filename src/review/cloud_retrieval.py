"""Optional Qwen candidate ranking over immutable, locally validated source blocks."""

from copy import deepcopy
import math
import os
from pathlib import Path
import tempfile

from .qwen import (QwenClient, QwenProfile, api_key_from_env, canonical, digest, embedding_request,
                   parse_embeddings, parse_scores, read_json, rerank_request, validate_text)
from .retrieval import _candidates, _score, _snapshot_hash, _tokens


def _capture(store, project_id, scope):
    with store._snapshot():
        store._project(project_id)
        return _candidates(store, project_id, scope, "bm25_context_blocks")


def _check_current(store, project_id, scope, manifest, candidates):
    current_manifest, current_candidates = _capture(store, project_id, scope)
    if current_manifest != manifest or [c["passage"] for c in current_candidates] != [c["passage"] for c in candidates]:
        raise ValueError("Qwen source or eligibility snapshot changed during inference; discard this result")


def _representations(candidates, profile):
    reps = []
    for block_index, candidate in enumerate(candidates):
        text = candidate["passage"]["anchor"]["quote"]
        start, size = 0, 0
        for end, character in enumerate(text):
            width = len(character.encode("utf-8"))
            if size + width > profile.max_document_bytes:
                if text[start:end].strip():
                    reps.append({"block_index": block_index, "start": start, "end": end, "text": text[start:end]})
                start, size = end, 0
            size += width
        if text[start:].strip():
            reps.append({"block_index": block_index, "start": start, "end": len(text), "text": text[start:]})
    if len(reps) > profile.max_representations:
        raise ValueError("Qwen source representations exceed the configured bound; narrow the project or increase a validated limit")
    for rep in reps:
        passage = candidates[rep["block_index"]]["passage"]
        rep["id"] = digest({"document_id": passage["document_id"], "block_id": passage["anchor"]["block_id"],
                            "start": rep["start"], "end": rep["end"], "text": rep["text"]})
    return reps


def _checked_call(call, request, profile, *, embedding):
    if not isinstance(call, dict) or call.get("request") != request:
        raise ValueError("Qwen call request does not match the recorded inputs")
    elapsed = call.get("elapsed_seconds")
    if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError("Qwen call elapsed time must be finite and nonnegative")
    response = call.get("response")
    canonical(response)
    values = (parse_embeddings(profile, response, len(request["inputs"])) if embedding
              else parse_scores(profile, response, len(request["documents"])))
    if "values" in call and call["values"] != values:
        raise ValueError("Qwen parsed values contradict the original provider response")
    return {"request": deepcopy(request), "response": deepcopy(response), "elapsed_seconds": elapsed}, values


def _envelope(payload):
    return {"payload": payload, "payload_sha256": digest(payload)}


def _read(path):
    path = Path(path)
    if path.stat().st_size > 100 * 1024 * 1024:
        raise ValueError("Qwen artifact exceeds its 100 MiB bound")
    envelope = read_json(path.read_bytes())
    if not isinstance(envelope, dict) or set(envelope) != {"payload", "payload_sha256"} or envelope["payload_sha256"] != digest(envelope["payload"]):
        raise ValueError("Qwen artifact checksum mismatch")
    return envelope


def _write(path, payload):
    path = Path(path)
    content = canonical(_envelope(payload)).encode("utf-8")
    if len(content) > 100 * 1024 * 1024:
        raise ValueError("Qwen artifact exceeds its 100 MiB bound")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".qwen-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _paths(store, index_path, receipt_path, replay_path):
    paths = [Path(p).resolve() for p in (index_path, receipt_path, replay_path) if p is not None]
    if len(paths) != len(set(paths)):
        raise ValueError("Qwen index, receipt and replay paths must be distinct")
    protected = set()
    for row in store._connection.execute("PRAGMA database_list"):
        if row[2]:
            database = Path(row[2]).resolve()
            protected.update((database, Path(str(database) + "-wal"), Path(str(database) + "-shm")))
    if any(path in protected for path in paths):
        raise ValueError("Qwen artifact paths cannot overwrite the review ledger or its WAL files")
    if receipt_path is not None and Path(receipt_path).exists():
        raise ValueError("Qwen receipts are immutable; choose a new output path")
    if index_path is not None and Path(index_path).exists():
        payload = _read(index_path)["payload"]
        if not isinstance(payload, dict) or "document_calls" not in payload:
            raise ValueError("Qwen index path contains a different artifact")


def _index_binding(project_id, scope, manifest, reps, profile):
    return {"schema_version": 1, "project_id": project_id, "scope": scope,
            "source_manifest": manifest, "source_snapshot_sha256": _snapshot_hash(manifest),
            "profile": profile.metadata(), "profile_sha256": digest(profile.metadata()), "representations": reps}


def _index_vectors(index, binding, profile):
    if not isinstance(index, dict) or set(index) != set(binding) | {"document_calls"} or any(index.get(key) != value for key, value in binding.items()):
        raise ValueError("Qwen index is stale or incompatible; explicitly rebuild it")
    calls = index["document_calls"]
    if not isinstance(calls, list) or len(calls) != len(binding["representations"]):
        raise ValueError("Qwen index document call count mismatch")
    vectors = []
    for rep, call in zip(binding["representations"], calls, strict=True):
        _, values = _checked_call(call, embedding_request(profile, [rep["text"]]), profile, embedding=True)
        vectors.extend(values)
    return vectors


def _pool(candidates, query, mode, candidate_k, reps, vectors, query_vector):
    lexical = _score(candidates, sorted(set(_tokens(query))), "bm25_context_blocks")
    positions = {id(candidate): index for index, candidate in enumerate(candidates)}
    lexical_ids = [positions[id(candidate)] for _, candidate in lexical[:candidate_k]]
    if mode == "qwen_rerank":
        return lexical_ids
    dense = {}
    for rep, vector in zip(reps, vectors, strict=True):
        score = sum(a * b for a, b in zip(query_vector, vector, strict=True))
        if not math.isfinite(score):
            raise ValueError("Qwen cosine score is nonfinite")
        block = rep["block_index"]
        dense[block] = max(dense.get(block, -math.inf), score)
    dense_ids = sorted(dense, key=lambda index: (-dense[index], candidates[index]["tie"]))[:candidate_k]
    fused = {}
    for ordering in (lexical_ids, dense_ids):
        for rank, index in enumerate(ordering, 1):
            fused[index] = fused.get(index, 0.0) + 1 / (60 + rank)
    return sorted(fused, key=lambda index: (-fused[index], candidates[index]["tie"]))[:candidate_k]


def search_sources_cloud(store, project_id, query, *, mode="qwen_hybrid", top_k=5, candidate_k=20,
                         scope="included", profile=None, client=None, index_path=None, rebuild_index=False,
                         receipt_path=None, replay_path=None, replay_sha256=None):
    """Read-only candidate retrieval; network calls cannot verify or write evidence."""
    profile = QwenProfile.from_env() if profile is None else profile
    if not isinstance(profile, QwenProfile):
        raise ValueError("Cloud retrieval requires a QwenProfile")
    validate_text(query, profile.max_query_bytes, "query")
    if mode == "qwen_hybrid":
        profile.format_query(query)
    if mode not in {"qwen_hybrid", "qwen_rerank"} or type(top_k) is not int or type(candidate_k) is not int or not 1 <= top_k <= candidate_k <= 100:
        raise ValueError("Qwen mode/limits must satisfy 1 <= top_k <= candidate_k <= 100")
    if scope not in {"included", "all_attached"}:
        raise ValueError("Qwen scope must be included or all_attached")
    if type(rebuild_index) is not bool:
        raise ValueError("Qwen rebuild_index must be a boolean")
    if store._connection.in_transaction:
        raise ValueError("Qwen inference cannot run inside an existing ledger transaction")
    if replay_path is not None and (client is not None or rebuild_index or index_path is not None or receipt_path is not None):
        raise ValueError("Qwen replay cannot use a live client, index or output path")
    if replay_path is None and replay_sha256 is not None:
        raise ValueError("Qwen replay checksum requires a replay file")
    if mode == "qwen_rerank" and (index_path is not None or rebuild_index):
        raise ValueError("The rerank-only method does not use an embedding index")
    _paths(store, index_path, receipt_path, replay_path)
    manifest, candidates = _capture(store, project_id, scope)
    reps = _representations(candidates, profile)
    binding = _index_binding(project_id, scope, manifest, reps, profile)
    request_binding = {"schema_version": 1, "project_id": project_id, "query": query, "scope": scope,
                       "mode": mode, "top_k": top_k, "candidate_k": candidate_k,
                       "index_binding": binding, "fusion": "RRF-k60;max-span-cosine-per-block;stable-source-order-v1"}
    saved = None
    if replay_path is not None:
        envelope = _read(replay_path)
        if not isinstance(replay_sha256, str) or envelope["payload_sha256"] != replay_sha256:
            raise ValueError("Qwen replay requires the trusted receipt_sha256 from the original trace")
        saved = envelope["payload"]
        if not isinstance(saved, dict) or saved.get("binding") != request_binding:
            raise ValueError("Qwen replay query, profile, parameters or source snapshot differs")
    elif candidates and client is None:
        client = QwenClient(profile, api_key_from_env())
    if client is not None and getattr(client, "profile", profile) != profile:
        raise ValueError("Qwen client profile differs from the retrieval profile")

    index, vectors, query_call, query_vector = None, [], None, None
    new_index = False
    if mode == "qwen_hybrid" and reps:
        if saved is not None:
            index = saved.get("index")
        elif index_path is not None and Path(index_path).exists() and not rebuild_index:
            index = _read(index_path)["payload"]
        else:
            calls = []
            for rep in reps:
                call = client.embed_documents([rep["text"]])
                validated, _ = _checked_call(call, embedding_request(profile, [rep["text"]]), profile, embedding=True)
                calls.append(validated)
                _check_current(store, project_id, scope, manifest, candidates)
            index = {**binding, "document_calls": calls}
            new_index = True
        vectors = _index_vectors(index, binding, profile)
        call = saved.get("query_call") if saved is not None else client.embed_query(query)
        query_call, values = _checked_call(call, embedding_request(profile, [profile.format_query(query)]), profile, embedding=True)
        query_vector = values[0]
        _check_current(store, project_id, scope, manifest, candidates)
    pool = _pool(candidates, query, mode, candidate_k, reps, vectors, query_vector)
    pool_reps = [rep for index in pool for rep in reps if rep["block_index"] == index]
    if saved is not None and saved.get("pool_representation_ids") != [rep["id"] for rep in pool_reps]:
        raise ValueError("Qwen replay candidate pool differs")
    rerank_calls, block_scores = [], {}
    batches = [pool_reps[start:start + profile.batch_size] for start in range(0, len(pool_reps), profile.batch_size)]
    if saved is not None and (not isinstance(saved.get("rerank_calls"), list) or len(saved["rerank_calls"]) != len(batches)):
        raise ValueError("Qwen replay rerank call count differs")
    for number, batch in enumerate(batches):
        texts = [rep["text"] for rep in batch]
        call = saved["rerank_calls"][number] if saved is not None else client.rerank(query, texts)
        validated, scores = _checked_call(call, rerank_request(profile, query, texts), profile, embedding=False)
        rerank_calls.append(validated)
        for rep, score in zip(batch, scores, strict=True):
            block = rep["block_index"]
            block_scores[block] = max(block_scores.get(block, -math.inf), score)
        _check_current(store, project_id, scope, manifest, candidates)
    order = sorted(block_scores, key=lambda index: (-block_scores[index], candidates[index]["tie"]))
    result = {"schema_version": 1, "status": "candidate_passages", "project_id": project_id, "query": query,
              "method": mode, "method_version": "lit-rev-engine.project-retrieval.cloud-qwen.v1." + mode,
              "parameters": {"profile_sha256": digest(profile.metadata()), "candidate_k": candidate_k,
                             "fusion": request_binding["fusion"], "block_score": "maximum-representation-relevance"},
              "scope": scope, "top_k": top_k, "source_manifest": manifest,
              "source_snapshot_sha256": _snapshot_hash(manifest), "indexed_passages": len(candidates),
              "matched_passages": len(order), "candidate_pool_size": len(pool), "profile": profile.metadata(),
              "answerability": "not_assessed", "verification": "human_review_required",
              "passages": [{"rank": rank, "score": block_scores[index], **candidates[index]["passage"]}
                           for rank, index in enumerate(order[:top_k], 1)]}
    payload = {"binding": request_binding, "index": index, "query_call": query_call,
               "pool_representation_ids": [rep["id"] for rep in pool_reps], "rerank_calls": rerank_calls,
               "result": result}
    if saved is not None and saved != payload:
        raise ValueError("Qwen receipt result or recorded calls contradict recomputed retrieval")
    _check_current(store, project_id, scope, manifest, candidates)
    key = getattr(client, "_api_key", None)
    if key and key in canonical(payload):
        raise ValueError("Qwen artifact contains the configured credential")
    if new_index and index_path is not None:
        _write(index_path, index)
    if receipt_path is not None:
        _write(receipt_path, payload)
    recorded_calls = (index["document_calls"] if index is not None else []) + ([query_call] if query_call else []) + rerank_calls
    actual_calls = [] if saved is not None else (index["document_calls"] if index is not None and new_index else []) + ([query_call] if query_call else []) + rerank_calls
    costs = [call["response"].get("inference_status", {}).get("cost") for call in actual_calls]
    return {**result, "receipt_sha256": digest(payload), "execution": "replay" if saved is not None else "live",
            "provider_calls": len(actual_calls), "recorded_provider_calls": len(recorded_calls),
            "observed_usage": {"input_tokens": sum(call["response"]["input_tokens"] for call in actual_calls),
                               "reported_cost_usd": sum(costs) if all(cost is not None for cost in costs) else None,
                               "elapsed_seconds": sum(call["elapsed_seconds"] for call in actual_calls)}}
