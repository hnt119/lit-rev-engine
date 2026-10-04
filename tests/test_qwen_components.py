"""Independent component-contract checks. CPU fakes do not measure Qwen quality."""

from collections import Counter
from copy import deepcopy
import builtins
import hashlib
import json
import math
from pathlib import Path
import re
import socket
import subprocess
import sys
from xml.sax.saxutils import escape

import pytest

from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.store import ReviewStore
from src.review_components import core, ledger


ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = [
    {"id": "q-a", "query": "adult randomized symptom result",
     "components": [{"id": "population", "query": "adult randomized reference recruitment"},
                    {"id": "outcome", "query": "symptom result confidence interval"}]},
    {"id": "q_a", "query": "unicode safety sample",
     "components": [{"id": "population", "query": "safety sample reference"},
                    {"id": "outcome", "query": "unicode adverse events"},
                    {"id": "period", "query": "recruitment period duration"}]},
    {"id": "whole", "query": "xyzzy flibbertigibbet"},
]
TEXTS = [f"Source {i:02}: " + (
    "adult randomized reference recruitment period duration" if i % 3 == 0 else
    "symptom result confidence interval adult" if i % 3 == 1 else
    "unicode safety sample adverse events Straße α café 🧪") for i in range(36)]
STOP = set("a an and are as at be been by did do does for from had has have how in is it its of on or that the their there these this to was were what when where which who with would".split())


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def envelope(payload):
    return {"payload": payload, "payload_sha256": digest(payload)}


def save(path, payload):
    wrapped = envelope(payload)
    Path(path).write_text(json.dumps(wrapped, ensure_ascii=False, allow_nan=False))
    return wrapped


def fingerprint(store):
    return digest(list(store._connection.iterdump()))


def unit(index, dimension=2560):
    vector = [0.0] * dimension
    vector[index % 4] = 1.0
    return vector


def lexical(candidates, text):
    def terms(value):
        return [v for v in re.findall(r"\w+", value.casefold()) if v not in STOP]
    docs = [Counter(terms(row["passage"]["anchor"]["quote"]) +
                    [v for context in row["passage"].get("scoring_context", [])
                     for v in terms(context["anchor"]["quote"])]) for row in candidates]
    if not docs:
        return []
    average = sum(sum(doc.values()) for doc in docs) / len(docs)
    frequencies = Counter(v for doc in docs for v in doc)
    output = []
    for index, doc in enumerate(docs):
        score = 0.0
        for term in sorted(set(terms(text))):
            if doc.get(term, 0):
                inverse = math.log(1 + (len(docs) - frequencies[term] + .5) / (frequencies[term] + .5))
                score += inverse * doc[term] * 2.2 / (doc[term] + 1.2 * (.25 + .75 * sum(doc.values()) / average))
        if score > 0:
            output.append((index, score))
    return sorted(output, key=lambda row: (-row[1], candidates[row[0]]["tie"]))


def fused(candidates, orders):
    scores = {}
    for ordering in orders:
        for rank, index in enumerate(ordering, 1):
            scores[index] = scores.get(index, 0) + 1 / (60 + rank)
    return sorted(scores, key=lambda i: (-scores[i], candidates[i]["tie"]))


def allocate(candidates, orders):
    # Shared reservations count for each component, without replacement.
    reserved = list(dict.fromkeys(i for order in orders[1:] for i in order[:2]))
    return (reserved + [i for i in fused(candidates, orders) if i not in reserved])[:20]


def plans(job, documents, queries):
    output, pairs, cursor = [], [], 0
    for question in job["questions"]:
        orders = []
        for _ in range(1 + len(question["components"])):
            row, query = job["query_rows"][cursor], queries[cursor]
            cursor += 1
            dense = {}
            for rep, vector in zip(job["representations"], documents, strict=True):
                cosine = sum(a * b for a, b in zip(vector, query, strict=True))
                index = rep["block_index"]
                dense[index] = max(dense.get(index, -math.inf), cosine)
            dense_order = sorted(dense, key=lambda i: (-dense[i], job["candidates"][i]["tie"]))[:20]
            own_lexical = [i for i, _ in lexical(job["candidates"], row["query"])[:20]]
            assert row["lexical_block_indices"] == own_lexical
            orders.append(fused(job["candidates"], [own_lexical, dense_order])[:20])
        target = allocate(job["candidates"], orders)
        def representation_ids(indices):
            return [r["id"] for i in indices for r in job["representations"] if r["block_index"] == i]
        target_ids, whole_ids = representation_ids(target), representation_ids(orders[0])
        union = list(dict.fromkeys(target_ids + whole_ids))
        for component_id, ids in [(None, union), *[(c["id"], target_ids) for c in question["components"]]]:
            pairs.extend({"question_id": question["id"], "component_id": component_id,
                          "representation_id": rid} for rid in ids)
        output.append({"question_id": question["id"], "orders": orders, "target": target,
                       "whole": orders[0], "target_ids": target_ids, "whole_ids": whole_ids, "union": union})
    return output, pairs


def selection(candidates, pool, scoremaps):
    chosen = []
    for scores in scoremaps[1:]:
        if pool:
            best = min(pool, key=lambda i: (-scores[i], candidates[i]["tie"]))
            if best not in chosen:
                chosen.append(best)
    whole = sorted(pool, key=lambda i: (-scoremaps[0][i], candidates[i]["tie"]))
    return (chosen + [i for i in whole if i not in chosen])[:5]


def runtime():
    return {"backend": "kaggle-cuda-transformers", "device": "cuda:0", "gpu_name": "Synthetic CPU test claim",
            "device_count": 1, "total_memory_bytes": 16_000_000_000, "dtype": "float16", "cuda_version": "12.4",
            "attention_implementation": "sdpa", "packages": {**core.PROFILE["packages"], "torch": "test", "python": "3.12.7"},
            "model_revisions": {"embedding": core.PROFILE["embedding_revision"], "reranker": core.PROFILE["reranker_revision"]},
            "elapsed_seconds": {"total": 1.0, "embedding_load": .1, "embedding_inference": .1, "reranker_load": .1, "reranker_inference": .1},
            "peak_vram_bytes": 1000, "max_input_tokens": 24, "truncated": False, "paid_inference_calls": 0}


def audit(job, active_runtime):
    from packaging.requirements import Requirement
    versions = {"filelock": "3.17.0", "huggingface-hub": "0.30.2", "numpy": "2.2.3", "packaging": "24.2", "pyyaml": "6.0.2",
                "regex": "2024.11.6", "requests": "2.32.3", "tokenizers": "0.21.1", "safetensors": "0.5.3", "tqdm": "4.67.1",
                "fsspec": "2025.2.0", "typing-extensions": "4.12.2"}
    def requirements(name):
        result = []
        for raw in core.ACTIVE_REQUIREMENTS[name]:
            dep = Requirement(raw).name
            result.append({"name": dep, "requirement": raw, "version": versions[dep],
                           "location": "/kaggle/temp/overlay/" + dep.replace("-", "_") if dep in core.PROFILE["packages"] else "/usr/lib/" + dep.replace("-", "_")})
        return result
    return {"schema_version": 1, "recipe": core.PROFILE["environment_recipe"], "overlay_path": "/kaggle/temp/overlay",
            "base_python": "/usr/bin/python3", "installer_report_sha256": "a" * 64, "execution_files": job["execution_files"],
            "packages": {name: {"version": version, "location": "/kaggle/temp/overlay/" + name.replace("-", "_"),
                                 "requirements": requirements(name)} for name, version in core.PROFILE["packages"].items()},
            "torch": {"version": "test", "location": "/usr/lib/torch", "cuda_version": "12.4", "device": "cuda:0",
                      "gpu_name": active_runtime["gpu_name"], "device_count": 1, "total_memory_bytes": 16_000_000_000, "smoke_passed": True},
            "python_version": "3.12.7", "setup_seconds": .2, "requirements_passed": True}


def synthetic_results(wrapped):
    job = wrapped["payload"]
    docs = [unit(rep["block_index"]) for rep in job["representations"]]
    queries = [unit(i) for i in range(len(job["query_rows"]))]
    _, pairs = plans(job, docs, queries)
    # Deliberate probability ties and different component maxima.
    lookup = {rep["id"]: rep["block_index"] for rep in job["representations"]}
    def score(pair):
        index = lookup[pair["representation_id"]]
        if pair["component_id"] is None:
            return .95 if index >= 15 else .1
        return .99 if index in (0, 1) else .2
    active_runtime = runtime()
    return {"schema_version": 1, "kind": "qwen-components-results-v1", "job_sha256": wrapped["payload_sha256"],
            "profile_sha256": job["profile_sha256"], "execution_files": deepcopy(job["execution_files"]),
            "document_embeddings": [{"id": rep["id"], "vector": vector, "tokens": 12} for rep, vector in zip(job["representations"], docs, strict=True)],
            "query_embeddings": [{"question_id": row["question_id"], "component_id": row["component_id"], "vector": vector, "tokens": 8}
                                 for row, vector in zip(job["query_rows"], queries, strict=True)],
            "score_rows": [{**pair, "score": score(pair), "tokens": 24} for pair in pairs],
            "runtime": active_runtime, "environment_audit": audit(job, active_runtime)}


@pytest.fixture(autouse=True)
def no_network_credentials(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Component acceptance attempted network, paid inference or credential loading")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr("src.review.qwen.api_key_from_env", denied)
    monkeypatch.setattr("src.review.qwen.QwenClient.__init__", denied)


def add_source(store, project, title, texts, *, included=True):
    store.import_records(project, SearchRunSpec("Synthetic component acceptance"), [BibliographicRecord(title=title)])
    record = store.list_records(project)[-1]["id"]
    if included:
        store.record_decision(project, record, "title_abstract", "include", "CPU fixture curator")
        store.set_full_text_status(project, record, "retrieved", "CPU fixture curator")
        store.record_decision(project, record, "full_text", "include", "CPU fixture curator")
    xml = ("<article><body><sec><title>Methods</title>" + "".join("<p>" + escape(text) + "</p>" for text in texts) + "</sec></body></article>").encode()
    return record, store.attach_document(project, record, xml, "jats_xml", "CPU fixture curator", "Authored test bytes")


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    # Helper fakes permit independent cycle-one adapter tests before cloud files exist.
    helpers = {}
    for name in core.EXECUTION_FILES:
        path = tmp_path / name
        path.write_bytes((ROOT / "src/review_components/core.py").read_bytes() if name == "component_core.py" else b"# synthetic CPU helper; never executed\n")
        helpers[name] = path
    monkeypatch.setattr(ledger, "execution_paths", lambda: helpers)
    with ReviewStore(tmp_path / "review.sqlite3") as store:
        project = store.create_project("Synthetic component acceptance", "systematic", "Exact reproducible evidence candidates")["id"]
        record, document = add_source(store, project, "Included test", TEXTS)
        excluded, extra = add_source(store, project, "Unscreened test", ["unrelated adults result 999"], included=False)
        yield store, project, record, document, excluded, extra


def export(corpus, tmp_path, questions=QUESTIONS, **kwargs):
    store, project, *_ = corpus
    path = tmp_path / "job.json"
    wrapped = ledger.export_job(store, project, questions, output_path=path, **kwargs)
    assert wrapped == json.loads(path.read_text())
    return path, wrapped


def imported(corpus, tmp_path, *, wrapped=None, payload=None, receipt=None):
    store, project, *_ = corpus
    if wrapped is None:
        job_path, wrapped = export(corpus, tmp_path)
    else:
        job_path = tmp_path / "job.json"
        job_path.write_text(json.dumps(wrapped, ensure_ascii=False))
    payload = synthetic_results(wrapped) if payload is None else payload
    result_path = tmp_path / "results.json"
    returned = save(result_path, payload)
    outcome = ledger.import_results(store, project, job_path=job_path, job_sha256=wrapped["payload_sha256"],
                                    results_path=result_path, results_sha256=returned["payload_sha256"], receipt_path=receipt)
    return outcome, wrapped, returned


def test_export_immutable_full_snapshot_structural_ids_and_lexical_oracle(corpus, tmp_path):
    store, project, _, document, *_ = corpus
    before = fingerprint(store)
    path, wrapped = export(corpus, tmp_path)
    job = wrapped["payload"]
    assert job["questions"][-1]["components"] == []
    assert len(job["query_rows"]) == 8 and job["top_k"] == 5 and job["candidate_k"] == 20
    assert job["source_snapshot_sha256"] == digest(job["source_manifest"])
    assert {r["document_id"] for r in job["source_manifest"]} == {document["id"]}
    for row in job["query_rows"]:
        assert row["lexical_block_indices"] == [i for i, _ in lexical(job["candidates"], row["query"])[:20]]
    assert core.validate_job(wrapped, wrapped["payload_sha256"]) == job
    assert fingerprint(store) == before
    with pytest.raises(ValueError):
        ledger.export_job(store, project, QUESTIONS, output_path=path)


def test_global_math_pair_union_maxspan_component_reuse_and_readonly_replay(corpus, tmp_path):
    store, project, *_ = corpus
    before = fingerprint(store)
    result, wrapped, returned = imported(corpus, tmp_path)
    job, payload = wrapped["payload"], returned["payload"]
    expected, pairs = plans(job, [r["vector"] for r in payload["document_embeddings"]], [r["vector"] for r in payload["query_embeddings"]])
    assert len({(p["question_id"], p["component_id"], p["representation_id"]) for p in pairs}) == len(pairs)
    actual = core.compute(job, [r["vector"] for r in payload["document_embeddings"]], [r["vector"] for r in payload["query_embeddings"]])
    assert actual["pair_inputs"] == pairs
    score_lookup = {(r["question_id"], r["component_id"], r["representation_id"]): r["score"] for r in payload["score_rows"]}
    for q, plan, actual_plan, trace, diagnostic in zip(job["questions"], expected, actual["plans"], result["traces"], result["diagnostics"], strict=True):
        assert actual_plan["target_block_indices"] == plan["target"]
        assert actual_plan["whole_block_indices"] == plan["whole"]
        assert len(plan["target"]) <= 20 and len(trace["passages"]) == 5
        ids = [None, *[c["id"] for c in q["components"]]]
        maps = [{i: max(score_lookup[(q["id"], cid, rep["id"])] for rep in job["representations"] if rep["block_index"] == i)
                 for i in plan["target"]} for cid in ids]
        chosen = selection(job["candidates"], plan["target"], maps)
        assert diagnostic["target_selected_block_indices"] == chosen
        assert [r["anchor"] for r in trace["passages"]] == [job["candidates"][i]["passage"]["anchor"] for i in chosen]
        assert trace["answerability"] == trace["support_completeness"] == "not_assessed"
        assert trace["verification"] == "human_review_required"
        groups = [rank for group in trace["source_groups"] for rank in group["passage_ranks"]]
        assert sorted(groups) == list(range(1, len(chosen) + 1))
        for row, index in zip(trace["passages"], chosen, strict=True):
            assert row["score"] == maps[0][index] == row["query_scores"]["whole"]
            assert row["anchor"]["quote"] == job["candidates"][index]["passage"]["anchor"]["quote"]
    assert set(result["comparators"]) == {"whole_qwen", "whole_lexical", "component_lexical"}
    whole = result["comparators"]["whole_qwen"]
    for q, plan, trace in zip(job["questions"], expected, whole, strict=True):
        scores = {i: max(score_lookup[(q["id"], None, rep["id"])] for rep in job["representations"] if rep["block_index"] == i) for i in plan["whole"]}
        selected = selection(job["candidates"], plan["whole"], [scores])
        assert [r["anchor"] for r in trace["passages"]] == [job["candidates"][i]["passage"]["anchor"] for i in selected]
    replay = ledger.import_results(store, project, job_path=tmp_path / "job.json", job_sha256=wrapped["payload_sha256"],
                                   results_path=tmp_path / "results.json", results_sha256=returned["payload_sha256"])
    assert result == replay and fingerprint(store) == before


def test_shared_pool_reservations_are_not_refilled_and_final_order_is_not_whole_score_order():
    candidates = [{"tie": [1, 1, i, 1]} for i in range(35)]
    orders = [list(range(10, 30)), [0, 1, *range(10, 28)], [0, 1, *range(11, 29)]]
    actual = core.allocate(candidates, orders, ["a", "b"])
    assert actual["block_indices"] == allocate(candidates, orders)
    assert actual["block_indices"][:2] == [0, 1]
    assert len(actual["reasons"][0]["reasons"]) == 2
    whole = {i: i / 35 for i in actual["block_indices"]}
    comp = {i: .9 if i == 0 else .1 for i in actual["block_indices"]}
    selected = core.select(candidates, actual["block_indices"], [whole, comp, comp], ["a", "b"])
    assert selected["block_indices"] == selection(candidates, actual["block_indices"], [whole, comp, comp])
    assert len(selected["reasons"][0]["reasons"]) == 2 and selected["block_indices"][0] == 0
    assert whole[selected["block_indices"][0]] < whole[selected["block_indices"][1]]
    assert core.select(candidates, [], [{}, {}, {}], ["a", "b"])["missing_components"] == ["a", "b"]


def test_lexical_comparators_match_original_bm25_scores_and_describe_actual_order(corpus, tmp_path):
    store, project, *_ = corpus
    _, wrapped = export(corpus, tmp_path)
    job = wrapped["payload"]
    compared = ledger.lexical_comparators(store, project, QUESTIONS)
    for q, whole, component in zip(job["questions"], compared["whole_lexical"], compared["component_lexical"], strict=True):
        old = store.search_sources(project, q["query"], method="bm25_context_blocks", top_k=20)
        own = core.lexical_scores(job["candidates"], q["query"])
        assert [job["candidates"][row["block_index"]]["passage"]["anchor"] for row in own[:20]] == [r["anchor"] for r in old["passages"]]
        assert [r["score"] for r in own[:20]] == [r["score"] for r in old["passages"]]
        assert [r["score"] for r in whole["passages"]] == [r["score"] for r in old["passages"][:5]]
        assert whole["display_order"] == "whole-query-score-descending"
        assert "component" not in whole["parameters"]["selection"]
        assert component["display_order"] == "component-reservations-then-whole-query-fill"


@pytest.mark.parametrize("defect", ["empty", "four", "one", "bad_id", "duplicate_q", "duplicate_c", "unexpected", "gold", "bad_query", "byte_limit", "count_limit", "components_not_list", "bool_id"])
def test_question_contract_rejects_ambiguous_or_unbounded_inputs(defect):
    questions = deepcopy(QUESTIONS)
    if defect == "empty": questions = []
    elif defect == "four": questions[0]["components"] *= 2
    elif defect == "one": questions[0]["components"].pop()
    elif defect == "bad_id": questions[0]["id"] = "../q"
    elif defect == "duplicate_q": questions[1]["id"] = questions[0]["id"]
    elif defect == "duplicate_c": questions[0]["components"][1]["id"] = "population"
    elif defect == "unexpected": questions[0]["x"] = 1
    elif defect == "gold": questions[0]["components"][0]["answer"] = "120"
    elif defect == "bad_query": questions[0]["query"] = "  "
    elif defect == "byte_limit": questions[0]["query"] = "🧪" * 501
    elif defect == "count_limit": questions = [{"id": f"q{i}", "query": "test"} for i in range(26)]
    elif defect == "components_not_list": questions[0]["components"] = None
    elif defect == "bool_id": questions[0]["components"][0]["id"] = True
    with pytest.raises(ValueError): core.normalize_questions(questions)


@pytest.mark.parametrize("defect", ["doc_missing", "doc_duplicate", "doc_order", "doc_extra", "dimension", "zero", "nonunit", "nonfinite", "bool_vector", "query_missing", "query_order", "query_collision", "score_missing", "score_duplicate", "score_order", "score_extra", "score_wrong_component", "score_wrong_question", "score_range", "score_bool", "tokens_bool", "tokens_zero", "tokens_max", "schema_bool", "unknown", "helper", "profile", "job_hash"])
def test_complete_matrix_identity_shape_numeric_and_bindings_fail_closed(corpus, tmp_path, defect):
    _, wrapped = export(corpus, tmp_path)
    payload = synthetic_results(wrapped)
    if defect == "doc_missing": payload["document_embeddings"].pop()
    elif defect == "doc_duplicate": payload["document_embeddings"][1] = deepcopy(payload["document_embeddings"][0])
    elif defect == "doc_order": payload["document_embeddings"].reverse()
    elif defect == "doc_extra": payload["document_embeddings"][0]["x"] = 1
    elif defect == "dimension": payload["document_embeddings"][0]["vector"].pop()
    elif defect == "zero": payload["document_embeddings"][0]["vector"] = [0.] * 2560
    elif defect == "nonunit": payload["document_embeddings"][0]["vector"][0] = 2.
    elif defect == "nonfinite": payload["document_embeddings"][0]["vector"][0] = math.inf
    elif defect == "bool_vector": payload["document_embeddings"][0]["vector"][0] = True
    elif defect == "query_missing": payload["query_embeddings"].pop()
    elif defect == "query_order": payload["query_embeddings"].reverse()
    elif defect == "query_collision": payload["query_embeddings"][1]["component_id"] = None
    elif defect == "score_missing": payload["score_rows"].pop()
    elif defect == "score_duplicate": payload["score_rows"][1] = deepcopy(payload["score_rows"][0])
    elif defect == "score_order": payload["score_rows"].reverse()
    elif defect == "score_extra": payload["score_rows"][0]["x"] = 1
    elif defect == "score_wrong_component": payload["score_rows"][0]["component_id"] = "population"
    elif defect == "score_wrong_question": payload["score_rows"][0]["question_id"] = "q_a"
    elif defect == "score_range": payload["score_rows"][0]["score"] = 1.01
    elif defect == "score_bool": payload["score_rows"][0]["score"] = True
    elif defect == "tokens_bool": payload["score_rows"][0]["tokens"] = True
    elif defect == "tokens_zero": payload["score_rows"][0]["tokens"] = 0
    elif defect == "tokens_max": payload["score_rows"][0]["tokens"] = 8193
    elif defect == "schema_bool": payload["schema_version"] = True
    elif defect == "unknown": payload["x"] = 1
    elif defect == "helper": payload["execution_files"]["component_core.py"]["sha256"] = "0" * 64
    elif defect == "profile": payload["profile_sha256"] = "0" * 64
    elif defect == "job_hash": payload["job_sha256"] = "0" * 64
    with pytest.raises(ValueError): core.validate_results(wrapped["payload"], payload, wrapped["payload_sha256"])


@pytest.mark.parametrize("defect", ["false_schema", "requirements_false", "recipe", "helper", "package_version", "package_outside", "package_parent_escape", "relative_location", "torch_inside", "torch_mismatch", "cuda_mismatch", "python_mismatch", "smoke_false", "setup_bool", "setup_nonfinite", "report_hash"])
def test_environment_audit_rejects_missing_or_contradictory_runtime_claims(corpus, tmp_path, defect):
    _, wrapped = export(corpus, tmp_path)
    active_runtime = runtime()
    value = audit(wrapped["payload"], active_runtime)
    if defect == "false_schema": value["schema_version"] = True
    elif defect == "requirements_false": value["requirements_passed"] = False
    elif defect == "recipe": value["recipe"] = "global-pip-upgrade"
    elif defect == "helper": value["execution_files"] = {}
    elif defect == "package_version": value["packages"]["transformers"]["version"] = "latest"
    elif defect == "package_outside": value["packages"]["transformers"]["location"] = "/usr/lib/transformers"
    elif defect == "package_parent_escape": value["packages"]["transformers"]["location"] = "/kaggle/temp/overlay/../outside/transformers"
    elif defect == "relative_location": value["packages"]["transformers"]["location"] = "kaggle/temp/overlay/transformers"
    elif defect == "torch_inside": value["torch"]["location"] = "/kaggle/temp/overlay/torch"
    elif defect == "torch_mismatch": value["torch"]["version"] = "other"
    elif defect == "cuda_mismatch": value["torch"]["cuda_version"] = "other"
    elif defect == "python_mismatch": value["python_version"] = "other"
    elif defect == "smoke_false": value["torch"]["smoke_passed"] = False
    elif defect == "setup_bool": value["setup_seconds"] = True
    elif defect == "setup_nonfinite": value["setup_seconds"] = math.inf
    elif defect == "report_hash": value["installer_report_sha256"] = "x" * 64
    with pytest.raises(ValueError): ledger.validate_environment_audit(value, active_runtime, wrapped["payload"]["execution_files"])


def test_zero_components_matches_historical_whole_rule(corpus, tmp_path):
    from src.review.cloud_retrieval import _capture, _pool
    _, wrapped = export(corpus, tmp_path, [{"id": "whole", "query": "adult randomized symptom result"}])
    job = wrapped["payload"]
    doc_vectors = [unit(r["block_index"]) for r in job["representations"]]
    query_vector = unit(0)
    whole = core.compute(job, doc_vectors, [query_vector])["plans"][0]
    _, captured = _capture(corpus[0], corpus[1], "included")
    expected_pool = _pool(captured, job["questions"][0]["query"], "qwen_hybrid", 20, job["representations"], doc_vectors, query_vector)
    expected_ids = [rep["id"] for index in expected_pool for rep in job["representations"] if rep["block_index"] == index]
    assert whole["target_block_indices"] == whole["whole_block_indices"] == expected_pool
    assert whole["target_representation_ids"] == whole["whole_union_representation_ids"] == expected_ids


@pytest.mark.parametrize("defect", ["source_bytes", "eligibility", "active_version", "job_query", "job_profile", "job_helper", "trusted_job", "trusted_results", "transaction", "empty"])
def test_stale_source_job_and_trusted_hash_rejection_never_writes_receipt(corpus, tmp_path, defect):
    store, project, record, document, *_ = corpus
    job_path, wrapped = export(corpus, tmp_path)
    result_path = tmp_path / "results.json"
    returned = save(result_path, synthetic_results(wrapped))
    args = dict(job_path=job_path, job_sha256=wrapped["payload_sha256"], results_path=result_path,
                results_sha256=returned["payload_sha256"], receipt_path=tmp_path / "receipt.json")
    if defect == "source_bytes": store._connection.execute("UPDATE source_documents SET source_sha256 = ? WHERE id = ?", ("0" * 64, document["id"])); store._connection.commit()
    elif defect == "eligibility": store.record_decision(project, record, "full_text", "exclude", "CPU fixture curator", "Different eligibility")
    elif defect == "active_version": store.attach_document(project, record, b"<article><body><p>new version</p></body></article>", "jats_xml", "CPU fixture curator", "Changed source")
    elif defect in {"job_query", "job_profile", "job_helper"}:
        job = deepcopy(wrapped["payload"])
        if defect == "job_query": job["questions"][0]["query"] += " amended"
        elif defect == "job_profile": job["profile"]["schema_version"] = True
        else: job["execution_files"]["component_core.py"]["sha256"] = "0" * 64
        changed = save(job_path, job)
        args["job_sha256"] = changed["payload_sha256"]
    elif defect == "trusted_job": args["job_sha256"] = "0" * 64
    elif defect == "trusted_results": args["results_sha256"] = "0" * 64
    elif defect == "transaction": store._connection.execute("BEGIN")
    elif defect == "empty": args["project_id"] = store.create_project("Empty", "systematic", "Nothing attached")["id"]
    before = fingerprint(store)
    if defect == "empty": selected_project = args.pop("project_id")
    else: selected_project = project
    with pytest.raises((ValueError, OSError)):
        ledger.import_results(store, selected_project, **args)
    assert fingerprint(store) == before and not (tmp_path / "receipt.json").exists()


@pytest.mark.parametrize("target", ["db", "wal", "shm", "job", "results", "existing", "symlink", "hardlink"])
def test_receipt_paths_are_protected_and_immutable(corpus, tmp_path, target):
    store, project, *_ = corpus
    job_path, wrapped = export(corpus, tmp_path)
    result_path = tmp_path / "results.json"
    returned = save(result_path, synthetic_results(wrapped))
    db = Path(store._connection.execute("PRAGMA database_list").fetchone()[2])
    if target == "db": receipt = db
    elif target == "wal": receipt = Path(str(db) + "-wal")
    elif target == "shm": receipt = Path(str(db) + "-shm")
    elif target == "job": receipt = job_path
    elif target == "results": receipt = result_path
    else:
        receipt = tmp_path / "receipt.json"
        if target == "existing": receipt.write_text("first attempt preserved")
        elif target == "symlink": receipt.symlink_to(db)
        else: receipt.hardlink_to(db)
    before = fingerprint(store)
    with pytest.raises(ValueError): ledger.import_results(store, project, job_path=job_path, job_sha256=wrapped["payload_sha256"],
        results_path=result_path, results_sha256=returned["payload_sha256"], receipt_path=receipt)
    assert fingerprint(store) == before


def test_long_unicode_own_spans_max_cosine_and_max_score_no_source_join(corpus, tmp_path):
    store, project, *_ = corpus
    _, document = add_source(store, project, "Long Unicode", ["🧪α Straße café " * 800])
    outcome, wrapped, returned = imported(corpus, tmp_path)
    reps = [r for r in wrapped["payload"]["representations"] if wrapped["payload"]["candidates"][r["block_index"]]["passage"]["document_id"] == document["id"]]
    assert len(reps) > 1
    text = store.get_source_blocks(project, document["id"])[0]["text"]
    assert "".join(r["text"] for r in reps) == text
    assert all(len(r["text"].encode()) <= 6000 for r in reps)
    assert reps[0]["start"] == 0 and reps[-1]["end"] == len(text)
    assert all(a["end"] == b["start"] for a, b in zip(reps, reps[1:]))
    assert outcome["distinct_rerank_pairs"] == len(returned["payload"]["score_rows"])


def test_pair_bound_counts_every_span_and_comparator_before_reranker(monkeypatch):
    # Smaller numeric dimension here exercises only the independent pair bound.
    monkeypatch.setitem(core.PROFILE, "dimension", 2)
    questions = core.normalize_questions([{"id": f"q{i}", "query": "sample", "components": [{"id": "a", "query": "sample"}, {"id": "b", "query": "sample"}]} for i in range(2)])
    candidates = [{"tie": [1, 1, 1, 1], "passage": {"anchor": {"quote": "sample"}}}]
    job = {"candidates": candidates, "representations": [{"id": str(i), "block_index": 0} for i in range(700)],
           "questions": questions, "query_rows": core.query_rows(candidates, questions)}
    with pytest.raises(ValueError, match="4000"):
        core.compute(job, [[1., 0.]] * 700, [[1., 0.]] * 6)


def test_max_span_cosine_and_probability_do_not_average_or_use_first_span():
    candidates = [{"tie": [1, 1, i, 1]} for i in range(2)]
    reps = [{"id": "a-first", "block_index": 0}, {"id": "a-second", "block_index": 0}, {"id": "b", "block_index": 1}]
    job = {"candidates": candidates, "representations": reps}
    # First span and mean would both lose to the competing block; max must win.
    assert core.hybrid_order(job, {"lexical_block_indices": []}, [[0., 1.], [1., 0.], [.6, .8]], [1., 0.]) == [0, 1]
    plan = {"question_id": "q", "target_block_indices": [0, 1], "whole_block_indices": [0, 1]}
    scores = {("q", None, "a-first"): .1, ("q", None, "a-second"): .9, ("q", None, "b"): .8}
    maximum = core.aggregate(job, plan, scores, None)
    assert maximum == {0: .9, 1: .8}
    assert core.select(candidates, [0, 1], [maximum], [])["block_indices"] == [0, 1]


def test_duplicate_and_nonfinite_json_rejected_without_model_imports():
    for value in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'):
        with pytest.raises(ValueError): core.read_json(value)
    script = "import builtins; old=builtins.__import__;\ndef guard(n,*a,**k):\n if n.split('.')[0] in {'torch','transformers','sentence_transformers'}: raise AssertionError(n)\n return old(n,*a,**k)\nbuiltins.__import__=guard\nimport src.review_components\nimport review_components\n"
    completed = subprocess.run([sys.executable, "-c", script], cwd=ROOT, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
