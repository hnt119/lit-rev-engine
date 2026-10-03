"""Independent synthetic Qwen cloud acceptance; no live model-quality claim."""

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
from urllib.error import HTTPError, URLError
from xml.sax.saxutils import escape

import pytest

from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.store import ReviewStore
from src.review.qwen import QwenClient, QwenProfile, parse_embeddings, parse_scores, read_json
from src.review.cloud_retrieval import search_sources_cloud


POPULATION = "At 12 months, the randomized adult cohort (ages 18–64 years; n=120) was assessed using the prespecified intention-to-treat analysis."
DISTRACTOR = "At 6 weeks, 24 volunteers in a separate uncontrolled feasibility sample improved by 9.9 units. This was not the randomized 12-month result."
SAFETY_SINGLE = "In the adult safety subset (n=36), zero severe adverse events occurred by 12 months."
PEDIATRIC_NULL = "No participants younger than 18 years were recruited; no pediatric subgroup estimate is reported."
OUTCOME_NULL = "Work productivity was not collected; the effectiveness outcome was symptom score only."
SAFETY_DENOMINATOR = "The 12-month safety evaluation used 36 adult participants."
SAFETY_COUNT = "The 12-month safety evaluation recorded zero severe adverse events."
QUESTIONS = {
    "paired": "What was the randomized adult cohort's between-group symptom change at 12 months and its 95% confidence interval?",
    "alternative": "How many severe adverse events occurred in the adult safety subset by 12 months, and what was its denominator?",
    "pediatric": "What was the between-group symptom change among children younger than 18 years?",
    "productivity": "What was the intervention effect on work productivity?",
}
ROOT = Path(__file__).resolve().parents[1]


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def fingerprint(store):
    return hashlib.sha256("\n".join(store._connection.iterdump()).encode()).hexdigest()


@pytest.fixture(autouse=True)
def forbid_live_dependencies(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Independent Qwen acceptance attempted a live connection or real sleep")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr("time.sleep", denied)


def add_report(store, project, title, text="included literal source", *, eligible=True):
    store.import_records(project, SearchRunSpec("Independent Qwen synthetic input"), [BibliographicRecord(title=title)])
    record = store.list_records(project)[-1]["id"]
    if eligible:
        store.record_decision(project, record, "title_abstract", "include", "Synthetic screener")
        store.set_full_text_status(project, record, "retrieved", "Synthetic custodian")
        store.record_decision(project, record, "full_text", "include", "Synthetic screener")
    doc = store.attach_document(project, record, text.encode(), "txt", "Synthetic custodian", "Independently authored exact bytes")
    return record, doc


@pytest.fixture
def synthetic_review(tmp_path):
    with ReviewStore(tmp_path / "qwen-acceptance.sqlite3") as store:
        project = store.create_project("Independent cloud acceptance", "systematic", "Do cloud candidates preserve exact source support?")["id"]
        record, _ = add_report(store, project, "Independent synthetic adult trial")
        paragraphs = [DISTRACTOR, SAFETY_SINGLE, PEDIATRIC_NULL, OUTCOME_NULL, SAFETY_DENOMINATOR, SAFETY_COUNT]
        body = "<sec><p>" + escape(POPULATION) + "</p>"
        body += '<table-wrap><label>Table 1</label><caption><p>Symptom change at 12 months</p></caption><table><thead><tr><th>Group</th><th>n</th><th>Change</th></tr></thead><tbody><tr><td>Intervention</td><td>60</td><td>−4.2</td></tr><tr><td>Comparator</td><td>60</td><td>−1.1</td></tr><tr><td>Between-group difference (95% CI)</td><td>120</td><td>−3.1 (−4.8 to −1.4)</td></tr></tbody></table></table-wrap>'
        body += "".join("<p>" + escape(text) + "</p>" for text in paragraphs) + "</sec>"
        document = store.attach_document(project, record, ("<article><body>" + body + "</body></article>").encode(), "jats_xml", "Synthetic custodian", "Independent support and null truth")
        blocks = store.get_source_blocks(project, document["id"])
        assert len(blocks) == 8
        named = {}
        for name, text in {"population": POPULATION, "distractor": DISTRACTOR, "safety_single": SAFETY_SINGLE, "pediatric_null": PEDIATRIC_NULL, "outcome_null": OUTCOME_NULL, "safety_denominator": SAFETY_DENOMINATOR, "safety_count": SAFETY_COUNT}.items():
            named[name] = next(block for block in blocks if block["text"] == text)
        named["estimate"] = next(block for block in blocks if block["locator"].get("tag") == "table-wrap")
        assert "−3.1 (−4.8 to −1.4)" in named["estimate"]["text"]
        yield store, project, record, document, named


def own_candidate(project, record, document, block, rank=1):
    return {"project_id": project, "record_id": record, "document_id": document["id"], "document_version": document["version"], "source_sha256": document["source_sha256"], "blocks_sha256": document["blocks_sha256"], "parser_id": document["parser_id"], "anchor": {"block_id": block["id"], "start": 0, "end": len(block["text"]), "quote": block["text"]}, "locator": deepcopy(block["locator"]), "rank": rank, "score": 1 / rank}


def complete_own_support(trace, document, blocks, alternatives, top_k=5):
    """Independent OR-of-AND metric; ranking context never supplies support."""
    if not alternatives:
        return None
    covered = set()
    for name, block in blocks.items():
        for candidate in trace["passages"][:top_k]:
            anchor = candidate["anchor"]
            if (candidate["document_id"] == document["id"] and candidate["source_sha256"] == document["source_sha256"]
                    and candidate["document_version"] == document["version"] and anchor["block_id"] == block["id"]
                    and anchor["start"] == 0 and anchor["end"] == len(block["text"]) and anchor["quote"] == block["text"]):
                covered.add(name)
                break
    return any(set(alternative) <= covered for alternative in alternatives)


def assert_exact_cloud_trace(store, project, trace, *, scope="included"):
    assert trace["schema_version"] == 1 and trace["status"] == "candidate_passages"
    assert trace["project_id"] == project and trace["scope"] == scope
    assert trace["source_snapshot_sha256"] == digest(trace["source_manifest"])
    active = {row["id"]: row for row in store.list_documents(project) if row["active"]}
    records = {row["id"]: row for row in store.list_records(project)}
    links = {row["record_id"]: row for row in store.list_study_links(project)}
    selected = {row["document_id"]: row for row in trace["source_manifest"]}
    expected = {did for did, doc in active.items() if scope == "all_attached" or (records[doc["record_id"]]["title_abstract_state"] == "include" and records[doc["record_id"]]["full_text_status"] == "retrieved" and records[doc["record_id"]]["full_text_state"] == "include")}
    assert set(selected) == expected
    seen = set()
    for rank, candidate in enumerate(trace["passages"], 1):
        assert candidate["rank"] == rank and type(candidate["score"]) in (int, float) and math.isfinite(candidate["score"])
        assert candidate["project_id"] == project and candidate["document_id"] in selected
        manifest = selected[candidate["document_id"]]
        doc = active[candidate["document_id"]]
        assert candidate["record_id"] == doc["record_id"] == manifest["record_id"]
        assert candidate["document_version"] == doc["version"] == manifest["version"]
        for field in ("source_sha256", "blocks_sha256", "parser_id"):
            assert candidate[field] == manifest[field] == doc[field]
        for field in ("full_text_state", "study_link_state", "study_ids"):
            expected_value = records[doc["record_id"]][field] if field == "full_text_state" else links[doc["record_id"]]["state" if field == "study_link_state" else field]
            assert candidate[field] == manifest[field] == expected_value
        blocks = {block["id"]: block for block in store.get_source_blocks(project, doc["id"])}
        anchor = candidate["anchor"]
        block = blocks[anchor["block_id"]]
        assert type(anchor["start"]) is type(anchor["end"]) is int
        assert anchor == {"block_id": block["id"], "start": 0, "end": len(block["text"]), "quote": block["text"]}
        assert candidate["locator"] == block["locator"]
        identity = doc["id"], block["id"]
        assert identity not in seen
        seen.add(identity)
        for context in candidate.get("scoring_context", []):
            contextual = blocks[context["anchor"]["block_id"]]
            ca = context["anchor"]
            assert type(ca["start"]) is type(ca["end"]) is int
            assert 0 <= ca["start"] < ca["end"] <= len(contextual["text"])
            assert ca["quote"] == contextual["text"][ca["start"]:ca["end"]]
            assert context["locator"] == contextual["locator"]
    assert not {"answer", "answerable", "finding", "verified"}.intersection(trace)


def test_independent_support_truth_requires_companion_own_block_and_preserves_alternatives(synthetic_review):
    store, project, record, document, blocks = synthetic_review
    estimate = own_candidate(project, record, document, blocks["estimate"])
    estimate["scoring_context"] = [{"anchor": own_candidate(project, record, document, blocks["population"])["anchor"], "locator": blocks["population"]["locator"]}]
    paired = [["population", "estimate"]]
    assert complete_own_support({"passages": [estimate]}, document, blocks, paired) is False
    assert complete_own_support({"passages": [estimate, own_candidate(project, record, document, blocks["population"], 2)]}, document, blocks, paired) is True
    alternatives = [["safety_single"], ["safety_denominator", "safety_count"]]
    assert complete_own_support({"passages": [own_candidate(project, record, document, blocks["safety_single"])]}, document, blocks, alternatives) is True
    assert complete_own_support({"passages": [own_candidate(project, record, document, blocks["safety_denominator"])]}, document, blocks, alternatives) is False
    assert complete_own_support({"passages": [own_candidate(project, record, document, blocks["safety_denominator"]), own_candidate(project, record, document, blocks["safety_count"], 2)]}, document, blocks, alternatives) is True
    assert complete_own_support({"passages": [estimate]}, document, blocks, []) is None


def embedding_response(vector=None):
    return {"embeddings": [vector if vector is not None else [3.0, 4.0] + [0.0] * 30], "input_tokens": 2, "inference_status": {"status": "succeeded", "cost": 0.0}}


def score_response(scores=None):
    return {"scores": [0.25, 0.75] if scores is None else scores, "input_tokens": 4, "inference_status": {"status": "succeeded", "cost": 0.0}}


def test_native_requests_bind_single_document_query_instruction_and_pair_order(monkeypatch):
    profile = QwenProfile(dimension=32)
    client = QwenClient(profile, "offline-qwen-acceptance-credential")
    calls = []
    def fake_post(url, request):
        calls.append((url, deepcopy(request)))
        return (score_response() if "documents" in request else embedding_response()), 0.01
    monkeypatch.setattr(client, "_post", fake_post)
    document = "  Straße α café 🧪.\r\nExact source.  "
    encoded = client.embed_documents([document])
    assert encoded["request"] == {"inputs": [document], "custom_instruction": "", "normalize": False, "dimensions": 32, "service_tier": "default", "fail_fast": True}
    assert encoded["values"] == [[0.6, 0.8] + [0.0] * 30]
    query = "  randomized adult estimate?  "
    encoded_query = client.embed_query(query)
    assert encoded_query["request"]["inputs"] == ["Instruct: " + profile.query_instruction + "\nQuery: " + query]
    assert encoded_query["request"]["custom_instruction"] == ""
    ranked = client.rerank(query, [document, "second exact document"])
    assert ranked["request"] == {"queries": [query, query], "documents": [document, "second exact document"], "instruction": profile.rerank_instruction, "service_tier": "default", "fail_fast": True}
    assert ranked["values"] == [0.25, 0.75]
    assert len(calls) == 3
    assert calls[0][0] == calls[1][0] == profile.embedding_url and calls[2][0] == profile.reranker_url
    assert "offline-qwen-acceptance-credential" not in json.dumps([encoded, encoded_query, ranked])
    assert profile.metadata()["embedding_revision"] is profile.metadata()["reranker_revision"] is None
    with pytest.raises(ValueError):
        client.embed_documents([document, document])
    assert len(calls) == 3


@pytest.mark.parametrize("defect", ["count", "dimension", "nan", "inf", "bool", "zero", "model", "tokens_missing", "tokens_bool", "status_failed", "status_unknown", "cost_nan", "cost_negative"])
def test_embedding_response_schema_fails_closed(defect):
    response = embedding_response()
    if defect == "count": response["embeddings"].append(response["embeddings"][0])
    elif defect == "dimension": response["embeddings"][0].pop()
    elif defect == "nan": response["embeddings"][0][0] = float("nan")
    elif defect == "inf": response["embeddings"][0][0] = float("inf")
    elif defect == "bool": response["embeddings"][0][0] = True
    elif defect == "zero": response["embeddings"][0] = [0.0] * 32
    elif defect == "model": response["model"] = "Qwen/Qwen3-Embedding-8B"
    elif defect == "tokens_missing": response.pop("input_tokens")
    elif defect == "tokens_bool": response["input_tokens"] = True
    elif defect == "status_failed": response["inference_status"]["status"] = "failed"
    elif defect == "status_unknown": response["inference_status"]["status"] = "unknown"
    elif defect == "cost_nan": response["inference_status"]["cost"] = float("nan")
    elif defect == "cost_negative": response["inference_status"]["cost"] = -0.01
    with pytest.raises(ValueError):
        parse_embeddings(QwenProfile(dimension=32), response, 1)


@pytest.mark.parametrize("defect", ["count", "nan", "inf", "bool", "negative", "above_one", "model", "tokens_missing", "status_queued", "cost_bool"])
def test_reranker_response_schema_fails_closed(defect):
    response = score_response()
    if defect == "count": response["scores"].pop()
    elif defect == "nan": response["scores"][0] = float("nan")
    elif defect == "inf": response["scores"][0] = float("inf")
    elif defect == "bool": response["scores"][0] = False
    elif defect == "negative": response["scores"][0] = -0.01
    elif defect == "above_one": response["scores"][0] = 1.01
    elif defect == "model": response["model"] = "different-reranker"
    elif defect == "tokens_missing": response.pop("input_tokens")
    elif defect == "status_queued": response["inference_status"]["status"] = "queued"
    elif defect == "cost_bool": response["inference_status"]["cost"] = False
    with pytest.raises(ValueError):
        parse_scores(QwenProfile(dimension=32), response, 2)


@pytest.mark.parametrize("text", ['{"scores":[0.1],"scores":[0.9]}', '{"score":NaN}', '{"score":Infinity}', '{"score":-Infinity}'])
def test_raw_json_duplicate_keys_and_nonfinite_numbers_rejected(text):
    with pytest.raises(ValueError): read_json(text)


@pytest.mark.parametrize("failure", [TimeoutError("offline-qwen-acceptance-credential"), URLError("offline-qwen-acceptance-credential"), HTTPError("https://example.test", 401, "offline-qwen-acceptance-credential", {}, None)])
def test_provider_unavailable_and_auth_failure_no_retry_or_credential_leak(failure):
    client = QwenClient(QwenProfile(dimension=32), "offline-qwen-acceptance-credential")
    class FailingOpener:
        count = 0
        def open(self, request, timeout):
            self.count += 1
            raise failure
    opener = FailingOpener()
    client._opener = opener
    with pytest.raises(ValueError) as caught:
        client.embed_query("literal query")
    assert opener.count == 1 and "offline-qwen-acceptance-credential" not in str(caught.value)


def test_final_formatted_query_and_document_byte_budgets_reject_before_provider(monkeypatch):
    profile = QwenProfile(dimension=32, max_query_bytes=128, max_document_bytes=64)
    client = QwenClient(profile, "offline-qwen-acceptance-credential")
    def denied(*args, **kwargs): pytest.fail("Overlength input reached provider")
    monkeypatch.setattr(client, "_post", denied)
    with pytest.raises(ValueError): client.embed_query("q" * 128)
    with pytest.raises(ValueError): client.embed_documents(["🧪" * 17])
    with pytest.raises(ValueError): client.rerank("query", ["🧪" * 17])


def ideal_score(query, text):
    if query == QUESTIONS["paired"]:
        return 0.99 if POPULATION in text else 0.98 if "−3.1" in text else 0.1
    if query == QUESTIONS["alternative"]:
        return 0.99 if SAFETY_SINGLE in text else 0.98 if SAFETY_DENOMINATOR in text else 0.97 if SAFETY_COUNT in text else 0.1
    if query == QUESTIONS["pediatric"]:
        return 0.99 if PEDIATRIC_NULL in text else 0.98 if "−3.1" in text else 0.1
    if query == QUESTIONS["productivity"]:
        return 0.99 if OUTCOME_NULL in text else 0.98 if "−3.1" in text else 0.1
    return 0.5


def scripted_client(monkeypatch, profile, store=None, *, score=ideal_score, after_call=None):
    client = QwenClient(profile, "offline-qwen-acceptance-credential")
    calls = []
    def post(url, request):
        if store is not None:
            assert not store._connection.in_transaction, "Provider call held a ledger snapshot/transaction open"
        calls.append((url, deepcopy(request)))
        if "documents" in request:
            stage = "rerank"
            response = score_response([score(query, text) for query, text in zip(request["queries"], request["documents"], strict=True)])
        else:
            assert len(request["inputs"]) == 1
            stage = "query" if request["inputs"][0].startswith("Instruct: ") else "document"
            response = embedding_response([1.0] + [0.0] * (profile.dimension - 1))
        if after_call is not None:
            after_call(stage)
        return response, 0.01
    monkeypatch.setattr(client, "_post", post)
    return client, calls


@pytest.mark.parametrize("mode", ["qwen_rerank", "qwen_hybrid"])
def test_scripted_ablation_complete_own_support_null_candidates_and_read_only(synthetic_review, monkeypatch, mode):
    store, project, record, document, blocks = synthetic_review
    profile = QwenProfile(dimension=32)
    client, calls = scripted_client(monkeypatch, profile, store)
    baseline = store.search_sources(project, QUESTIONS["paired"], method="bm25_context_blocks")
    before = fingerprint(store)
    traces = {name: search_sources_cloud(store, project, query, mode=mode, profile=profile, client=client) for name, query in QUESTIONS.items()}
    for trace in traces.values():
        assert_exact_cloud_trace(store, project, trace)
        assert trace["method"] == mode and trace["answerability"] == "not_assessed" and trace["verification"] == "human_review_required"
    assert complete_own_support(traces["paired"], document, blocks, [["population", "estimate"]]) is True
    assert complete_own_support(traces["alternative"], document, blocks, [["safety_single"], ["safety_denominator", "safety_count"]]) is True
    for null, context in [("pediatric", "pediatric_null"), ("productivity", "outcome_null")]:
        trace = traces[null]
        assert complete_own_support(trace, document, blocks, []) is None
        assert trace["passages"] and trace["passages"][0]["anchor"]["block_id"] == blocks[context]["id"]
        assert any(row["anchor"]["block_id"] == blocks["estimate"]["id"] for row in trace["passages"])
    assert fingerprint(store) == before and store.list_evidence(project) == store.list_evidence_reviews(project) == []
    assert store.search_sources(project, QUESTIONS["paired"], method="bm25_context_blocks") == baseline
    if mode == "qwen_rerank": assert all("documents" in request for _, request in calls)
    else: assert any("inputs" in request for _, request in calls)


def test_missing_own_companion_stays_incomplete_despite_context_or_pool_support(synthetic_review, monkeypatch, tmp_path):
    store, project, record, document, blocks = synthetic_review
    profile = QwenProfile(dimension=32)
    client, _ = scripted_client(monkeypatch, profile, store, score=lambda query, text: 0.99 if "−3.1" in text else 0.1)
    receipt = tmp_path / "limited-final.json"
    trace = search_sources_cloud(store, project, QUESTIONS["paired"], profile=profile, client=client, top_k=1, candidate_k=20, receipt_path=receipt)
    assert trace["candidate_pool_size"] == 8
    assert trace["passages"][0]["anchor"]["block_id"] == blocks["estimate"]["id"]
    assert trace["passages"][0]["scoring_context"][0]["anchor"]["block_id"] == blocks["population"]["id"]
    assert complete_own_support(trace, document, blocks, [["population", "estimate"]]) is False
    pool_ids = set(json.loads(receipt.read_text())["payload"]["pool_representation_ids"])
    reps = json.loads(receipt.read_text())["payload"]["binding"]["index_binding"]["representations"]
    assert {rep["block_index"] for rep in reps if rep["id"] in pool_ids} == set(range(8))
    restricted = search_sources_cloud(store, project, QUESTIONS["paired"], mode="qwen_rerank", profile=profile, client=client, top_k=1, candidate_k=1)
    assert restricted["candidate_pool_size"] == 1
    assert complete_own_support(restricted, document, blocks, [["population", "estimate"]]) is False


def test_index_cache_receipt_replay_reconstructs_without_network(synthetic_review, monkeypatch, tmp_path):
    store, project, record, document, blocks = synthetic_review
    profile = QwenProfile(dimension=32)
    client, calls = scripted_client(monkeypatch, profile, store)
    index, receipt = tmp_path / "index.json", tmp_path / "receipt.json"
    before = fingerprint(store)
    live = search_sources_cloud(store, project, QUESTIONS["paired"], profile=profile, client=client, index_path=index, receipt_path=receipt)
    assert len(calls) == live["provider_calls"] == 10
    calls.clear()
    cached = search_sources_cloud(store, project, QUESTIONS["paired"], profile=profile, client=client, index_path=index)
    assert len(calls) == cached["provider_calls"] == 2
    assert all("documents" in request or request["inputs"][0].startswith("Instruct: ") for _, request in calls)
    assert cached["passages"] == live["passages"] and cached["receipt_sha256"] == live["receipt_sha256"]
    def denied(*args, **kwargs): pytest.fail("Replay attempted provider construction")
    monkeypatch.setattr("src.review.cloud_retrieval.QwenClient", denied)
    replay = search_sources_cloud(store, project, QUESTIONS["paired"], profile=profile, replay_path=receipt, replay_sha256=live["receipt_sha256"])
    assert replay["execution"] == "replay" and replay["receipt_sha256"] == live["receipt_sha256"]
    assert replay["provider_calls"] == 0 and replay["recorded_provider_calls"] == 10
    assert live["observed_usage"] == {"input_tokens": 22, "reported_cost_usd": 0.0, "elapsed_seconds": pytest.approx(0.1)}
    assert cached["observed_usage"] == {"input_tokens": 6, "reported_cost_usd": 0.0, "elapsed_seconds": pytest.approx(0.02)}
    assert replay["observed_usage"] == {"input_tokens": 0, "reported_cost_usd": 0, "elapsed_seconds": 0}
    assert replay["passages"] == live["passages"] and fingerprint(store) == before
    assert_exact_cloud_trace(store, project, replay)
    assert "offline-qwen-acceptance-credential" not in receipt.read_text() + index.read_text()


@pytest.mark.parametrize("defect", ["result", "request", "response", "pool", "representation", "source", "query_call"])
def test_replay_recomputes_and_rejects_partial_receipt_tampering(synthetic_review, monkeypatch, tmp_path, defect):
    store, project, record, document, blocks = synthetic_review
    profile = QwenProfile(dimension=32)
    client, _ = scripted_client(monkeypatch, profile, store)
    receipt = tmp_path / "original.json"
    original = search_sources_cloud(store, project, QUESTIONS["paired"], profile=profile, client=client, receipt_path=receipt)
    envelope = json.loads(receipt.read_text())
    payload = envelope["payload"]
    if defect == "result": payload["result"]["passages"][0]["anchor"]["quote"] = "fabricated quotation"
    elif defect == "request": payload["rerank_calls"][0]["request"]["documents"].reverse()
    elif defect == "response": payload["rerank_calls"][0]["response"]["scores"][0] = 0.333
    elif defect == "pool": payload["pool_representation_ids"].pop()
    elif defect == "representation": payload["binding"]["index_binding"]["representations"][0]["text"] = "fabricated model representation"
    elif defect == "source": payload["binding"]["index_binding"]["source_manifest"][0]["source_sha256"] = "0" * 64
    elif defect == "query_call": payload["query_call"]["request"]["inputs"][0] = "Different query"
    envelope["payload_sha256"] = digest(payload)
    tampered = tmp_path / (defect + ".json")
    tampered.write_text(json.dumps(envelope, ensure_ascii=False))
    before = fingerprint(store)
    # Original trusted digest defeats even a rewritten envelope checksum.
    with pytest.raises(ValueError):
        search_sources_cloud(store, project, QUESTIONS["paired"], profile=profile, replay_path=tampered, replay_sha256=original["receipt_sha256"])
    # A newly supplied digest still cannot hide inconsistent recorded inputs/results.
    with pytest.raises(ValueError):
        search_sources_cloud(store, project, QUESTIONS["paired"], profile=profile, replay_path=tampered, replay_sha256=envelope["payload_sha256"])
    assert fingerprint(store) == before


@pytest.mark.parametrize("changed", ["query", "scope", "mode", "top_k", "candidate_k", "profile", "missing_digest"])
def test_replay_is_bound_to_query_scope_mode_limits_profile_and_trusted_digest(synthetic_review, monkeypatch, tmp_path, changed):
    store, project, record, document, blocks = synthetic_review
    profile = QwenProfile(dimension=32)
    client, _ = scripted_client(monkeypatch, profile, store)
    receipt = tmp_path / "bound.json"
    trace = search_sources_cloud(store, project, QUESTIONS["paired"], profile=profile, client=client, receipt_path=receipt)
    args = dict(profile=profile, replay_path=receipt, replay_sha256=trace["receipt_sha256"])
    query = QUESTIONS["paired"]
    if changed == "query": query += "?"
    elif changed == "scope": args["scope"] = "all_attached"
    elif changed == "mode": args["mode"] = "qwen_rerank"
    elif changed == "top_k": args["top_k"] = 4
    elif changed == "candidate_k": args["candidate_k"] = 19
    elif changed == "profile": args["profile"] = replace(profile, query_instruction="Different recorded instruction")
    elif changed == "missing_digest": args.pop("replay_sha256")
    with pytest.raises(ValueError): search_sources_cloud(store, project, query, **args)


@pytest.mark.parametrize("stage", ["document", "query", "rerank"])
@pytest.mark.parametrize("change", ["source", "screening", "linkage", "scope_addition"])
def test_source_scope_linkage_changes_during_each_provider_stage_reject_publication(synthetic_review, monkeypatch, tmp_path, stage, change):
    store, project, record, document, blocks = synthetic_review
    profile = QwenProfile(dimension=32)
    database = store._connection.execute("PRAGMA database_list").fetchone()[2]
    changed = []
    def concurrent(actual_stage):
        if actual_stage != stage or changed:
            return
        with ReviewStore(database) as writer:
            if change == "source": writer.attach_document(project, record, b"Changed source", "txt", "Concurrent custodian", "Explicit new version")
            elif change == "screening": writer.record_decision(project, record, "full_text", "exclude", "Concurrent screener", "Changed eligibility")
            elif change == "linkage":
                study = writer.create_study(project, "Concurrent manual study", "Concurrent linker", "Explicit linkage")["id"]
                writer.record_study_links(project, record, [study], "Concurrent linker", "Changed linkage projection")
            elif change == "scope_addition": add_report(writer, project, "New included report")
        changed.append(actual_stage)
    client, calls = scripted_client(monkeypatch, profile, store, after_call=concurrent)
    index, receipt = tmp_path / "stale-index.json", tmp_path / "stale-receipt.json"
    with pytest.raises(ValueError, match="snapshot changed"):
        search_sources_cloud(store, project, QUESTIONS["paired"], profile=profile, client=client, index_path=index, receipt_path=receipt)
    assert changed == [stage] and not index.exists() and not receipt.exists()
    assert not store.list_evidence(project) and not store.list_evidence_reviews(project)


def test_project_scope_active_version_isolation_and_selected_integrity(synthetic_review, monkeypatch, tmp_path):
    store, project, record, document, blocks = synthetic_review
    foreign = store.create_project("Foreign cloud project", "systematic", "Other sources?")["id"]
    _, foreign_doc = add_report(store, foreign, "Foreign should never be sent", "foreign secret source")
    excluded, excluded_doc = add_report(store, project, "Excluded source", "excluded own source")
    store.record_decision(project, excluded, "full_text", "exclude", "Synthetic screener", "Out of included scope")
    _, pending_doc = add_report(store, project, "Pending source", "pending own source", eligible=False)
    profile = QwenProfile(dimension=32)
    client, calls = scripted_client(monkeypatch, profile, store)
    before = fingerprint(store)
    included = search_sources_cloud(store, project, QUESTIONS["paired"], profile=profile, client=client)
    assert_exact_cloud_trace(store, project, included)
    assert {row["document_id"] for row in included["source_manifest"]} == {document["id"]}
    serialized = json.dumps(calls)
    assert "foreign secret source" not in serialized and "excluded own source" not in serialized and "pending own source" not in serialized
    calls.clear()
    attached = search_sources_cloud(store, project, QUESTIONS["paired"], profile=profile, client=client, scope="all_attached", top_k=10)
    assert_exact_cloud_trace(store, project, attached, scope="all_attached")
    assert {row["document_id"] for row in attached["source_manifest"]} == {document["id"], excluded_doc["id"], pending_doc["id"]}
    assert foreign_doc["id"] not in {row["document_id"] for row in attached["passages"]}
    assert fingerprint(store) == before
    store._connection.execute("UPDATE source_documents SET content=? WHERE id=?", (b"Corrupt selected bytes", document["id"]))
    store._connection.commit()
    calls.clear()
    with pytest.raises(ValueError): search_sources_cloud(store, project, "the and", profile=profile, client=client)
    assert calls == []


def test_long_unicode_scoring_spans_preserve_full_padded_source_and_limits(monkeypatch, tmp_path):
    with ReviewStore(tmp_path / "unicode.sqlite3") as store:
        project = store.create_project("Unicode cloud spans", "scoping", "Exact bounds?")["id"]
        text = "  \r\n" + "🧪 α café Straße " * 40 + "\r\n\t  "
        record, document = add_report(store, project, "Long padded Unicode", text)
        profile = QwenProfile(dimension=32, max_document_bytes=64)
        client, calls = scripted_client(monkeypatch, profile, store)
        receipt = tmp_path / "unicode.json"
        before = fingerprint(store)
        trace = search_sources_cloud(store, project, "Straße café", profile=profile, client=client, receipt_path=receipt)
        assert_exact_cloud_trace(store, project, trace)
        assert trace["passages"][0]["anchor"]["quote"] == text
        reps = json.loads(receipt.read_text())["payload"]["binding"]["index_binding"]["representations"]
        assert len(reps) > 1
        assert "".join(rep["text"] for rep in reps) == text
        for rep in reps:
            assert rep["text"] == text[rep["start"]:rep["end"]] and len(rep["text"].encode()) <= 64
        assert fingerprint(store) == before
        calls.clear()
        with pytest.raises(ValueError, match="representations"):
            search_sources_cloud(store, project, "Straße", profile=replace(profile, max_representations=1), client=client)
        assert calls == []


@pytest.mark.parametrize("change", ["profile", "source", "zero_vector"])
def test_stale_or_corrupt_index_rejects_without_hidden_rebuild(synthetic_review, monkeypatch, tmp_path, change):
    store, project, record, document, blocks = synthetic_review
    profile = QwenProfile(dimension=32)
    client, calls = scripted_client(monkeypatch, profile, store)
    index = tmp_path / "stored-index.json"
    search_sources_cloud(store, project, QUESTIONS["paired"], profile=profile, client=client, index_path=index)
    if change == "profile":
        profile = replace(profile, dimension=64)
        client, calls = scripted_client(monkeypatch, profile, store)
    elif change == "source": store.attach_document(project, record, b"New source", "txt", "Synthetic custodian", "Explicit replacement")
    elif change == "zero_vector":
        envelope = json.loads(index.read_text())
        envelope["payload"]["document_calls"][0]["response"]["embeddings"][0] = [0.0] * 32
        envelope["payload_sha256"] = digest(envelope["payload"])
        index.write_text(json.dumps(envelope))
    calls.clear()
    before = fingerprint(store)
    with pytest.raises(ValueError): search_sources_cloud(store, project, QUESTIONS["paired"], profile=profile, client=client, index_path=index)
    assert calls == [] and fingerprint(store) == before
    rebuilt = search_sources_cloud(store, project, QUESTIONS["paired"], profile=profile, client=client, index_path=index, rebuild_index=True)
    assert calls and rebuilt["provider_calls"] == len(calls)
    assert_exact_cloud_trace(store, project, rebuilt)
    assert fingerprint(store) == before


@pytest.mark.parametrize("destination", ["database", "wal", "same_artifact", "existing_receipt"])
def test_output_collisions_fail_before_provider_and_preserve_ledger(synthetic_review, monkeypatch, tmp_path, destination):
    store, project, record, document, blocks = synthetic_review
    profile = QwenProfile(dimension=32)
    client, calls = scripted_client(monkeypatch, profile, store)
    database = store._connection.execute("PRAGMA database_list").fetchone()[2]
    args = {}
    if destination == "database": args["receipt_path"] = database
    elif destination == "wal": args["receipt_path"] = database + "-wal"
    elif destination == "same_artifact": args.update(index_path=tmp_path / "same.json", receipt_path=tmp_path / "same.json")
    elif destination == "existing_receipt":
        receipt = tmp_path / "preserved.json"
        receipt.write_text("Preserved existing output")
        args["receipt_path"] = receipt
    before = fingerprint(store)
    with pytest.raises(ValueError): search_sources_cloud(store, project, QUESTIONS["paired"], profile=profile, client=client, **args)
    assert calls == [] and fingerprint(store) == before
    if destination == "existing_receipt": assert receipt.read_text() == "Preserved existing output"


@pytest.mark.parametrize("change", ["source", "screening", "linkage"])
def test_replay_rejects_current_state_changes_without_network(synthetic_review, monkeypatch, tmp_path, change):
    store, project, record, document, blocks = synthetic_review
    profile = QwenProfile(dimension=32)
    client, _ = scripted_client(monkeypatch, profile, store)
    receipt = tmp_path / "before-state-change.json"
    trace = search_sources_cloud(store, project, QUESTIONS["paired"], profile=profile, client=client, receipt_path=receipt)
    if change == "source": store.attach_document(project, record, b"New current source", "txt", "Synthetic custodian", "Explicit replacement")
    elif change == "screening": store.record_decision(project, record, "full_text", "exclude", "Synthetic screener", "Current scope changed")
    elif change == "linkage":
        study = store.create_study(project, "New manual link", "Synthetic linker", "Explicit linkage")["id"]
        store.record_study_links(project, record, [study], "Synthetic linker", "Current provenance changed")
    before = fingerprint(store)
    def denied(*args, **kwargs): pytest.fail("Stale replay attempted provider construction")
    monkeypatch.setattr("src.review.cloud_retrieval.QwenClient", denied)
    with pytest.raises(ValueError):
        search_sources_cloud(store, project, QUESTIONS["paired"], profile=profile, replay_path=receipt, replay_sha256=trace["receipt_sha256"])
    assert fingerprint(store) == before


@pytest.mark.parametrize("mode,stage", [("qwen_hybrid", "document"), ("qwen_hybrid", "query"), ("qwen_hybrid", "rerank"), ("qwen_rerank", "rerank")])
def test_malformed_provider_stage_fails_without_fallback_or_artifacts(synthetic_review, monkeypatch, tmp_path, mode, stage):
    store, project, record, document, blocks = synthetic_review
    profile = QwenProfile(dimension=32)
    client, calls = scripted_client(monkeypatch, profile, store)
    method = {"document": "embed_documents", "query": "embed_query", "rerank": "rerank"}[stage]
    def malformed(*args, **kwargs):
        raise ValueError("Provider schema rejected")
    monkeypatch.setattr(client, method, malformed)
    index, receipt = tmp_path / "failed-index.json", tmp_path / "failed-receipt.json"
    before = fingerprint(store)
    args = dict(mode=mode, profile=profile, client=client, receipt_path=receipt)
    if mode == "qwen_hybrid": args["index_path"] = index
    with pytest.raises(ValueError, match="Provider schema rejected"):
        search_sources_cloud(store, project, QUESTIONS["paired"], **args)
    assert not index.exists() and not receipt.exists() and fingerprint(store) == before


def guarded_cli(tmp_path, *arguments):
    environment = os.environ.copy()
    for name in ("DEEPINFRA_API_KEY", "QWEN_EMBEDDING_URL", "QWEN_RERANKER_URL", "NCBI_EMAIL", "NCBI_API_KEY", "AGNES_API_KEY"):
        environment.pop(name, None)
    environment.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    script = """
import importlib.abc,runpy,socket,sys,time
root=sys.argv[1]
sys.path.insert(0,root)
blocked={'torch','transformers','chromadb','sentence_transformers','src.settings','dotenv'}
class Guard(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if any(fullname==name or fullname.startswith(name+'.') for name in blocked): raise AssertionError('Forbidden dependency '+fullname)
sys.meta_path.insert(0,Guard())
def denied(*args,**kwargs): raise AssertionError('CLI attempted network or sleep')
socket.create_connection=denied
time.sleep=denied
import src.review.cloud_retrieval as cloud
cloud.api_key_from_env=lambda: ''
sys.argv=[root+'/review.py',*sys.argv[2:]]
runpy.run_path(root+'/review.py',run_name='__main__')
"""
    return subprocess.run([sys.executable, "-c", script, str(ROOT), *map(str, arguments)], cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=10)


def test_review_entrypoint_offline_replay_and_lexical_delegation_without_local_models(synthetic_review, monkeypatch, tmp_path):
    store, project, record, document, blocks = synthetic_review
    # The command-line profile uses the genuine default dimension; this replay needs no vectors.
    profile = QwenProfile()
    client, _ = scripted_client(monkeypatch, profile, store)
    receipt = tmp_path / "cli-replay.json"
    original = search_sources_cloud(store, project, QUESTIONS["paired"], mode="qwen_rerank", profile=profile, client=client, receipt_path=receipt)
    database = store._connection.execute("PRAGMA database_list").fetchone()[2]
    before = fingerprint(store)
    arguments = ["--db", database, "retrieve-qwen", project, "--query", QUESTIONS["paired"], "--mode", "qwen_rerank", "--replay", receipt, "--replay-sha256", original["receipt_sha256"]]
    result = guarded_cli(tmp_path, *arguments)
    assert result.returncode == 0 and result.stderr == "", result.stderr
    replay = json.loads(result.stdout)
    assert replay["passages"] == original["passages"] and replay["execution"] == "replay" and replay["provider_calls"] == 0
    assert_exact_cloud_trace(store, project, replay)
    for malformed in (arguments[:-2], [*arguments[:-1], "0" * 64]):
        rejected = guarded_cli(tmp_path, *malformed)
        assert rejected.returncode == 1 and rejected.stderr.startswith("review: ") and rejected.stdout == "" and "Traceback" not in rejected.stderr
    baseline = store.search_sources(project, "retrieve-qwen")
    delegated = guarded_cli(tmp_path, "--db=" + database, "retrieve-sources", project, "--query", "retrieve-qwen")
    assert delegated.returncode == 0 and delegated.stderr == "" and json.loads(delegated.stdout) == baseline
    assert fingerprint(store) == before


def test_review_entrypoint_missing_live_credentials_fails_cleanly(synthetic_review, tmp_path):
    store, project, record, document, blocks = synthetic_review
    database = store._connection.execute("PRAGMA database_list").fetchone()[2]
    receipt = tmp_path / "no-live-credentials.json"
    before = fingerprint(store)
    result = guarded_cli(tmp_path, "--db", database, "retrieve-qwen", project, "--query", QUESTIONS["paired"], "--mode", "qwen_rerank", "--receipt", receipt)
    assert result.returncode == 1 and "DEEPINFRA_API_KEY" in result.stderr and result.stdout == "" and "Traceback" not in result.stderr
    assert not receipt.exists() and fingerprint(store) == before
