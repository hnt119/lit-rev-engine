"""Shared standalone stdlib contract and math for component Qwen retrieval.

The identical bytes are uploaded as component_core.py. No ledger, credentials,
network or model library is imported here.
"""

from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re


PROFILE = {
    "schema_version": 1, "provider_contract": "kaggle-cuda-qwen4b-components-v1",
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
    "fusion": "per-query-BM25-dense-RRF-k60-top20;global-hybrid-RRF-k60-v1",
    "pool_allocation": "exact-first2-each-component-shared-counts;global-RRF-fill20-v1",
    "selection": "best1-each-component-shared-reuse;whole-score-fill5-v1",
    "block_score": "maximum-representation-relevance",
    "max_document_bytes": 6000, "max_query_bytes": 2000, "max_representations": 1000,
    "max_questions": 25, "max_queries": 100, "max_tokens": 8192, "batch_size": 1,
    "candidate_k": 20, "top_k": 5, "max_distinct_rerank_pairs": 4000,
    "dtype": "float16", "attention_implementation": "sdpa",
    "length_policy": "count-complete-tokenized-input;reject-overlength;no-truncation",
    "environment_recipe": "isolated-installer-no-deps-overlay;isolated-base-worker-v1",
    "packages": {"transformers": "4.51.3", "tokenizers": "0.21.1",
                 "safetensors": "0.5.3", "huggingface-hub": "0.30.2"},
}
EXECUTION_FILES = ("component_core.py", "qwen_kaggle_environment.py", "qwen_components_kaggle_runner.py")
ACTIVE_REQUIREMENTS = {
    "transformers": ["filelock", "huggingface-hub<1.0,>=0.30.0", "numpy>=1.17", "packaging>=20.0", "pyyaml>=5.1",
                     "regex!=2019.12.17", "requests", "tokenizers<0.22,>=0.21", "safetensors>=0.4.3", "tqdm>=4.27"],
    "tokenizers": ["huggingface-hub>=0.16.4,<1.0"], "safetensors": [],
    "huggingface-hub": ["filelock", "fsspec>=2023.5.0", "packaging>=20.9", "pyyaml>=5.1", "requests", "tqdm>=4.42.1", "typing-extensions>=3.7.4.3"],
}
_STOP = frozenset("a an and are as at be been by did do does for from had has have how in is it its of on or that the their there these this to was were what when where which who with would".split())
RERANK_PREFIX = '<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
RERANK_SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, UnicodeError):
        raise ValueError("Component data must be finite valid JSON") from None


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def read_json(content):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    try:
        value = json.loads(content, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
        canonical(value)
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ValueError("Invalid component JSON") from None


def read_artifact(path):
    path = Path(path)
    require(path.stat().st_size <= 100 * 1024 * 1024, "Component artifact exceeds 100 MiB")
    envelope = read_json(path.read_bytes())
    require(isinstance(envelope, dict) and set(envelope) == {"payload", "payload_sha256"}
            and envelope["payload_sha256"] == digest(envelope["payload"]), "Component artifact checksum mismatch")
    return envelope


def _id(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value) is not None


def _text(value):
    require(isinstance(value, str) and value.strip() and len(value.encode("utf-8")) <= PROFILE["max_query_bytes"], "Component query must be nonempty and at most 2000 UTF-8 bytes")


def normalize_questions(questions):
    require(isinstance(questions, list) and 1 <= len(questions) <= PROFILE["max_questions"], "Component job requires 1 to 25 questions")
    clean, seen, count = [], set(), 0
    for question in questions:
        require(isinstance(question, dict) and set(question) in ({"id", "query"}, {"id", "query", "components"}), "Questions allow only id, query and components; do not export gold")
        require(_id(question["id"]) and question["id"] not in seen, "Question IDs must be unique safe strings")
        seen.add(question["id"])
        _text(question["query"])
        components = question.get("components", [])
        require(isinstance(components, list) and len(components) in (0, 2, 3), "A question requires zero, two or three components")
        parts, names = [], set()
        for component in components:
            require(isinstance(component, dict) and set(component) == {"id", "query"}, "Components allow only id and query")
            require(_id(component["id"]) and component["id"] not in names, "Component IDs must be unique within a question")
            _text(component["query"])
            names.add(component["id"])
            parts.append(dict(component))
        clean.append({"id": question["id"], "query": question["query"], "components": parts})
        count += 1 + len(parts)
    require(count <= PROFILE["max_queries"], "Component job exceeds 100 encoded queries")
    return clean


def _terms(text):
    return [word for word in re.findall(r"\w+", text.casefold()) if word not in _STOP]


def lexical_scores(candidates, query):
    frequencies = []
    for candidate in candidates:
        passage = candidate["passage"]
        terms = Counter(_terms(passage["anchor"]["quote"]))
        for context in passage.get("scoring_context", []):
            terms.update(_terms(context["anchor"]["quote"]))
        frequencies.append(terms)
    if not frequencies:
        return []
    average = sum(sum(terms.values()) for terms in frequencies) / len(frequencies)
    df = Counter(term for terms in frequencies for term in terms)
    scores = []
    for index, terms in enumerate(frequencies):
        score = 0.0
        for term in sorted(set(_terms(query))):
            frequency = terms.get(term, 0)
            if frequency:
                idf = math.log(1 + (len(frequencies) - df[term] + 0.5) / (df[term] + 0.5))
                score += idf * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * sum(terms.values()) / average))
        if score > 0:
            scores.append({"block_index": index, "score": score})
    return sorted(scores, key=lambda row: (-row["score"], candidates[row["block_index"]]["tie"]))


def query_rows(candidates, questions):
    rows = []
    for question in normalize_questions(questions):
        for part in [{"id": None, "query": question["query"]}, *question["components"]]:
            rows.append({"question_id": question["id"], "component_id": part["id"], "query": part["query"],
                         "lexical_block_indices": [row["block_index"] for row in lexical_scores(candidates, part["query"])[:20]]})
    return rows


def validate_execution_files(files):
    require(isinstance(files, dict) and set(files) == set(EXECUTION_FILES), "Executable helper/core bindings are incomplete")
    for value in files.values():
        require(isinstance(value, dict) and set(value) == {"sha256", "size_bytes"}
                and isinstance(value["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", value["sha256"])
                and type(value["size_bytes"]) is int and 0 < value["size_bytes"] <= 1024 * 1024, "Invalid executable byte binding")


def validate_job(envelope, expected_sha256):
    require(isinstance(envelope, dict) and set(envelope) == {"payload", "payload_sha256"}
            and envelope["payload_sha256"] == digest(envelope["payload"])
            and isinstance(expected_sha256, str) and envelope["payload_sha256"] == expected_sha256, "Use the trusted original component job checksum")
    job = envelope["payload"]
    fields = {"schema_version", "kind", "project_id", "scope", "top_k", "candidate_k", "profile", "profile_sha256",
              "source_manifest", "source_snapshot_sha256", "candidates", "representations", "questions", "query_rows", "execution_files"}
    require(isinstance(job, dict) and set(job) == fields and type(job["schema_version"]) is int and job["schema_version"] == 1
            and job["kind"] == "qwen-components-job-v1", "Component job schema mismatch")
    require(digest(job["profile"]) == digest(PROFILE) and job["profile_sha256"] == digest(PROFILE), "Component job profile mismatch")
    require(type(job["top_k"]) is int and job["top_k"] == 5 and type(job["candidate_k"]) is int and job["candidate_k"] == 20
            and job["scope"] in {"included", "all_attached"}, "Component job has different fixed budgets or scope")
    validate_execution_files(job["execution_files"])
    require(isinstance(job["source_manifest"], list) and job["source_manifest"] and digest(job["source_manifest"]) == job["source_snapshot_sha256"], "Component source manifest checksum mismatch")
    candidates, reps = job["candidates"], job["representations"]
    require(isinstance(candidates, list) and candidates and isinstance(reps, list) and 1 <= len(reps) <= PROFILE["max_representations"], "Component job requires bounded eligible sources")
    for candidate in candidates:
        require(isinstance(candidate, dict) and set(candidate) == {"passage", "tie"} and isinstance(candidate["tie"], list)
                and len(candidate["tie"]) == 4 and all(type(number) is int and number >= 0 for number in candidate["tie"]), "Invalid component source tie")
        passage = candidate["passage"]
        require(isinstance(passage, dict) and passage.get("project_id") == job["project_id"] and isinstance(passage.get("anchor"), dict), "Invalid component source passage")
        anchor = passage["anchor"]
        require(set(anchor) == {"block_id", "start", "end", "quote"} and isinstance(anchor["quote"], str) and anchor["quote"].strip()
                and type(anchor["start"]) is int and anchor["start"] == 0 and type(anchor["end"]) is int and anchor["end"] == len(anchor["quote"]), "Component passage must retain its full own source block")
    seen = set()
    for rep in reps:
        require(isinstance(rep, dict) and set(rep) == {"id", "block_index", "start", "end", "text"}
                and type(rep["block_index"]) is int and 0 <= rep["block_index"] < len(candidates), "Invalid component representation")
        passage = candidates[rep["block_index"]]["passage"]
        require(type(rep["start"]) is int and type(rep["end"]) is int and 0 <= rep["start"] < rep["end"] <= len(passage["anchor"]["quote"])
                and rep["text"] == passage["anchor"]["quote"][rep["start"]:rep["end"]] and rep["text"].strip()
                and len(rep["text"].encode("utf-8")) <= PROFILE["max_document_bytes"], "Component representation is not an exact bounded own span")
        expected = digest({"document_id": passage["document_id"], "block_id": passage["anchor"]["block_id"], "start": rep["start"], "end": rep["end"], "text": rep["text"]})
        require(rep["id"] == expected and expected not in seen, "Component representation ID mismatch or duplicate")
        seen.add(expected)
    require(canonical(normalize_questions(job["questions"])) == canonical(job["questions"]), "Component questions are not normalized")
    require(canonical(query_rows(candidates, job["questions"])) == canonical(job["query_rows"]), "Component query ordering or lexical lists mismatch")
    return job


def unit_vector(value):
    require(isinstance(value, list) and len(value) == PROFILE["dimension"]
            and all(type(number) in (int, float) and math.isfinite(number) for number in value), "Invalid component embedding vector")
    require(abs(math.hypot(*value) - 1.0) <= 0.0001, "Component embedding must be a nonzero unit vector")
    return value


def token_count(value):
    require(type(value) is int and 1 <= value <= PROFILE["max_tokens"], "Invalid component token count or overlong input")
    return value


def rrf(candidates, lists):
    scores = {}
    for ordering in lists:
        for rank, index in enumerate(ordering, 1):
            scores[index] = scores.get(index, 0.0) + 1 / (60 + rank)
    return sorted(scores, key=lambda index: (-scores[index], candidates[index]["tie"]))


def hybrid_order(job, row, vectors, query_vector):
    dense = {}
    for rep, values in zip(job["representations"], vectors, strict=True):
        score = sum(a * b for a, b in zip(query_vector, values, strict=True))
        require(math.isfinite(score), "Component cosine is nonfinite")
        block = rep["block_index"]
        dense[block] = max(dense.get(block, -math.inf), score)
    dense_order = sorted(dense, key=lambda index: (-dense[index], job["candidates"][index]["tie"]))[:20]
    return rrf(job["candidates"], [row["lexical_block_indices"], dense_order])[:20]


def allocate(candidates, orders, component_ids):
    """Reserve exact first-two sets, counting shared blocks without refilling."""
    selected, reasons = [], {}
    for identifier, ordering in zip(component_ids, orders[1:], strict=True):
        for rank, index in enumerate(ordering[:2], 1):
            if index not in reasons:
                selected.append(index)
                reasons[index] = []
            reasons[index].append({"kind": "component_pool_reservation", "component_id": identifier, "rank": rank})
    for index in rrf(candidates, orders):
        if len(selected) >= 20:
            break
        if index not in reasons:
            selected.append(index)
            reasons[index] = [{"kind": "global_rrf_fill"}]
    return {"block_indices": selected, "reasons": [{"block_index": index, "reasons": reasons[index]} for index in selected]}


def compute(job, document_vectors, query_vectors):
    require(len(document_vectors) == len(job["representations"]) and len(query_vectors) == len(job["query_rows"]), "Component embedding matrix count mismatch")
    vectors = [unit_vector(value) for value in document_vectors]
    encoded = [unit_vector(value) for value in query_vectors]
    plans, pairs, cursor = [], [], 0
    for question in job["questions"]:
        count = 1 + len(question["components"])
        rows = job["query_rows"][cursor:cursor + count]
        orders = [hybrid_order(job, row, vectors, vector) for row, vector in zip(rows, encoded[cursor:cursor + count], strict=True)]
        cursor += count
        components = [row["id"] for row in question["components"]]
        allocation = allocate(job["candidates"], orders, components)
        target = allocation["block_indices"]
        def representations(indices):
            return [rep["id"] for index in indices for rep in job["representations"] if rep["block_index"] == index]
        target_reps, whole_reps = representations(target), representations(orders[0])
        union = list(dict.fromkeys([*target_reps, *whole_reps]))
        for identifier, identifiers in [(None, union), *[(identifier, target_reps) for identifier in components]]:
            pairs.extend({"question_id": question["id"], "component_id": identifier, "representation_id": rep_id} for rep_id in identifiers)
        plans.append({"question_id": question["id"], "hybrid_orders": [{"component_id": row["component_id"], "block_indices": order} for row, order in zip(rows, orders, strict=True)],
                      "target_block_indices": target, "target_pool_reasons": allocation["reasons"], "whole_block_indices": orders[0],
                      "target_representation_ids": target_reps, "whole_representation_ids": whole_reps, "whole_union_representation_ids": union})
    require(len(pairs) <= PROFILE["max_distinct_rerank_pairs"], "Component job exceeds 4000 distinct rerank pairs; export a smaller batch")
    return {"plans": plans, "pair_inputs": pairs}


def select(candidates, pool_blocks, query_scoremaps, component_ids):
    require(len(query_scoremaps) == 1 + len(component_ids), "Component block score matrix count mismatch")
    selected, reasons, missing = [], {}, []
    for identifier, scores in zip(component_ids, query_scoremaps[1:], strict=True):
        if not pool_blocks:
            missing.append(identifier)
            continue
        index = min(pool_blocks, key=lambda index: (-scores[index], candidates[index]["tie"]))
        if index not in reasons:
            selected.append(index)
            reasons[index] = []
        reasons[index].append({"kind": "component_selection", "component_id": identifier})
    for index in sorted(pool_blocks, key=lambda index: (-query_scoremaps[0][index], candidates[index]["tie"])):
        if len(selected) >= 5:
            break
        if index not in reasons:
            selected.append(index)
            reasons[index] = [{"kind": "whole_query_fill"}]
    return {"block_indices": selected, "reasons": [{"block_index": index, "reasons": reasons[index]} for index in selected], "missing_components": missing}


def validate_results(job, payload, job_sha256):
    fields = {"schema_version", "kind", "job_sha256", "profile_sha256", "execution_files", "document_embeddings", "query_embeddings", "score_rows", "runtime", "environment_audit"}
    require(isinstance(payload, dict) and set(payload) == fields and type(payload["schema_version"]) is int and payload["schema_version"] == 1
            and payload["kind"] == "qwen-components-results-v1" and payload["job_sha256"] == job_sha256
            and payload["profile_sha256"] == job["profile_sha256"] and canonical(payload["execution_files"]) == canonical(job["execution_files"]), "Component results schema or binding mismatch")
    documents, queries = payload["document_embeddings"], payload["query_embeddings"]
    require(isinstance(documents, list) and len(documents) == len(job["representations"])
            and isinstance(queries, list) and len(queries) == len(job["query_rows"]), "Component result embedding count mismatch")
    vectors, encoded, counts = [], [], []
    for rep, row in zip(job["representations"], documents, strict=True):
        require(isinstance(row, dict) and set(row) == {"id", "vector", "tokens"} and row["id"] == rep["id"], "Component document embedding ID/order mismatch")
        vectors.append(unit_vector(row["vector"]))
        counts.append(token_count(row["tokens"]))
    for expected, row in zip(job["query_rows"], queries, strict=True):
        require(isinstance(row, dict) and set(row) == {"question_id", "component_id", "vector", "tokens"}
                and row["question_id"] == expected["question_id"] and row["component_id"] == expected["component_id"], "Component query embedding ID/order mismatch")
        encoded.append(unit_vector(row["vector"]))
        counts.append(token_count(row["tokens"]))
    computed = compute(job, vectors, encoded)
    scores = payload["score_rows"]
    require(isinstance(scores, list) and len(scores) == len(computed["pair_inputs"]), "Component complete score matrix count mismatch")
    scoremaps = {}
    for expected, row in zip(computed["pair_inputs"], scores, strict=True):
        require(isinstance(row, dict) and set(row) == set(expected) | {"score", "tokens"}
                and all(row[key] == value for key, value in expected.items()), "Component score matrix identity/order mismatch")
        value = row["score"]
        require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1, "Component relevance must be a finite probability")
        counts.append(token_count(row["tokens"]))
        scoremaps[(row["question_id"], row["component_id"], row["representation_id"])] = value
    return {**computed, "scoremaps": scoremaps, "token_counts": counts}


def aggregate(job, plan, scoremaps, component_id, *, whole_reference=False):
    indices = plan["whole_block_indices"] if whole_reference else plan["target_block_indices"]
    result = {}
    for index in indices:
        result[index] = max(scoremaps[(plan["question_id"], component_id, rep["id"])] for rep in job["representations"] if rep["block_index"] == index)
    return result


def embedding_query(query):
    return f"Instruct: {PROFILE['query_instruction']}\nQuery: {query}"


def rerank_body(query, document):
    return f"<Instruct>: {PROFILE['rerank_instruction']}\n<Query>: {query}\n<Document>: {document}"
