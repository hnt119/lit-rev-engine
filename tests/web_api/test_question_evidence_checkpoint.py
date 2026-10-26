"""Independent A/B HTTP acceptance over explicit synthetic software sources.

No live discovery, trained model, participant judgment or scientific gold is
used. Human-state enum values below exercise authorization/rules mechanically.
"""
import csv
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import io
import json
import socket
import threading
from types import SimpleNamespace
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.contracts import Block, Paper, PreparedSource, SearchPreview
from src.mvp.proposal_contracts import ProposalGenerationResult
from src.mvp.service import MVPService
from src.web_api.app import COOKIE_NAME, create_app

BASE, ORIGIN = "http://127.0.0.1:8765", "http://127.0.0.1:3000"
DIMENSIONS = ("population", "recruitment_geography", "specimen", "design", "focus")
FIELDS = [{"id": key, "label": key, "subquestion": "SOFTWARE cohort sample methods outcome"} for key in DIMENSIONS]
REF_KEYS = {"source_id", "source_version", "source_sha256", "blocks_sha256", "block_id", "start", "end"}


class MockProposal:
    enabled = True
    profile = {"provider": "synthetic-offline-mock", "model": "none", "revision": "software-v1"}

    def __init__(self): self.calls = 0

    def generate(self, packet, *, timeout_seconds):
        self.calls += 1
        evidence = {item.evidence_id: item.reference for item in packet.evidence}
        return ProposalGenerationResult(output_text=json.dumps({"cells": [
            {"field_id": field.field_id, "value": "SYNTHETIC unreviewed value", "references": [
                {"evidence_id": field.evidence_ids[0], "quote": evidence[field.evidence_ids[0]].quote}
            ] if field.evidence_ids else [], "reason": "Mock output only; support is unassessed.",
             "missing_information": "", "context_scope": "retrieved_context_only"}
            for field in packet.fields]}))


class SyntheticSources:
    def __init__(self):
        self.search_calls = self.source_calls = 0
        self.papers = [Paper(id="software-multisite", title="=SOFTWARE_FORMULA()", abstract="Synthetic metadata only."),
            Paper(id="software-abstract", title="SOFTWARE abstract scope", abstract="Synthetic limited abstract."),
            Paper(id="software-empty", title="SOFTWARE unavailable record")]
        texts = ["SYNTHETIC SOFTWARE DATA. Cohort A sampled skin; cohort B sampled stool. Methods and outcome links are separate. 亚洲 🧬 No scientific findings.",
                 "SYNTHETIC ABSTRACT ONLY. A cohort provided a saliva sample. Full methods and outcome linkage are not supplied.", ""]
        self.sources = {}
        for number, (paper, text) in enumerate(zip(self.papers, texts)):
            blocks = [Block(id="text:1", ordinal=1, text=text, locator={"type": "text_block", "ordinal": 1})] if text else []
            self.sources[paper.id] = PreparedSource(paper_id=paper.id,
                status=("full_text_retrieved", "abstract_only", "no_usable_text")[number],
                source_type=("full_text", "abstract", "none")[number], provider="synthetic-software-fixture",
                source_url="", version="software-v1", source_sha256=sha256(text.encode()).hexdigest() if text else "",
                parser_id="lit-rev-engine.source.v1.txt", blocks=blocks,
                license="Synthetic software fixture only; no real research data" if number == 0 else None)

    def search(self, request):
        self.search_calls += 1
        return SearchPreview(query=request.query, mode="test", provider="synthetic-software-fixture",
            total_reported=3, fetched_count=3, truncated=False, papers=self.papers)

    def prepare(self, paper):
        self.source_calls += 1
        return self.sources[paper.id]


def browser(app, cookie=None):
    client = TestClient(app, base_url=BASE)
    if cookie: client.cookies.set(COOKIE_NAME, cookie)
    token = client.get("/api/v1/session").json()["csrf_token"]
    client.headers.update({"Origin": ORIGIN, "X-CSRF-Token": token})
    return client


@pytest.fixture
def case(tmp_path, monkeypatch):
    for name in ("MVP_MAP_ENABLED", "MVP_PROPOSALS_ENABLED", "MVP_SEARCH_PLANNER_ENABLED"):
        monkeypatch.setenv(name, "0")
    monkeypatch.delenv("NCBI_EMAIL", raising=False)
    monkeypatch.delenv("MVP_DEPLOYMENT_MODE", raising=False)
    def denied(*args, **kwargs): pytest.fail("Offline evidence-view check attempted networking")
    monkeypatch.setattr(socket, "create_connection", denied)
    provider, adapter = SyntheticSources(), MockProposal()
    engine = MVPService(SQLiteWorkspaceStorage(tmp_path / "research.sqlite3"), provider, provider)
    app = create_app(tmp_path, services={"saved_example": engine}, proposal_adapter=adapter)
    client = browser(app)
    created = client.post("/api/v1/workspaces", json={"request_id": "workspace", "mode": "saved_example",
        "question": "SOFTWARE 3 reports by 5 fields; not a human evaluation"})
    created.raise_for_status()
    root = "/api/v1/workspaces/" + created.json()["id"]
    search = client.post(root + "/searches", json={"request_id": "search", "query": "software"})
    search.raise_for_status()
    papers = [paper["id"] for paper in search.json()["papers"]]
    prep = client.post(root + "/source-preparations", json={"request_id": "prepare", "search_id": search.json()["id"], "paper_ids": papers})
    prep.raise_for_status()
    body = {"request_id": "board", "question": "Synthetic source-scoped comparison", "preparation_id": prep.json()["id"],
        "paper_ids": papers, "fields": FIELDS}
    response = client.post(root + "/boards", json=body)
    response.raise_for_status()
    board = response.json()
    path = root + "/boards/" + board["definition"]["board_id"]
    return SimpleNamespace(app=app, client=client, root=root, board=path, view=board,
        revision=board["definition"]["revision_id"], papers=papers, prep=prep.json(), body=body,
        provider=provider, adapter=adapter, directory=tmp_path, engine=engine)


def endpoint(case, suffix): return case.board + "/evidence-views/" + suffix


def call(case, suffix, body=None, *, method="POST", status=200, client=None):
    result = (client or case.client).request(method, endpoint(case, suffix), params={"revision_id": case.revision}, json=body)
    assert result.status_code == status, result.text
    return result.json()


def bind(case, dimension="specimen", key=None, head=None):
    return call(case, "dimensions", {"request_id": key or "bind-" + dimension, "expected_head_id": head,
        "dimension_id": dimension, "field_id": dimension, "label": dimension,
        "definition": "SOFTWARE definition; report-level cooccurrence only"})


def submit(case, paper, field="specimen", *, key="submission", head=None, value="SOFTWARE manually reviewed marker"):
    selected = []
    if paper != "software-empty":
        retrieved = case.client.post(case.board + "/candidates", json={"request_id": key + "-candidates",
            "expected_revision_id": case.revision, "paper_id": paper, "field_id": field, "top_k": 3})
        retrieved.raise_for_status()
        reference = retrieved.json()["candidates"][0]["reference"]
        inspected = case.client.get(case.board + "/references/" + reference["id"] + "/context")
        inspected.raise_for_status()
        assert inspected.json()["reference"] == reference
        selected = [{k: reference[k] for k in REF_KEYS}]
    path = case.board + "/drafts/" + paper + "/" + field
    prior = case.client.get(path).json()
    data = {"value": value if selected else None, "references": selected, "inspected_ranges": selected,
        "semantic_assessment": "human_supported" if selected else "unassessed",
        "scope_result": "value_found" if selected else "not_assessed",
        "reason": "SYNTHETIC software transition, not actual human/scientific validation.",
        "missing_information": "" if selected else "No source was supplied in this synthetic task scope."}
    saved = case.client.put(path, json={"expected_revision_id": case.revision, "version": prior["version"],
        "expected_cell_head_id": head, "data": data})
    saved.raise_for_status()
    submitted = case.client.post(case.board + "/cell-revisions", json={"request_id": key,
        "expected_revision_id": case.revision, "paper_id": paper, "field_id": field, "draft_version": saved.json()["version"], "supersedes_id": head})
    submitted.raise_for_status()
    return submitted.json()


def classify(case, dimension, submission, values, *, key="classify", head=None):
    return call(case, "attributes", {"request_id": key, "expected_head_id": head,
        "dimension_revision_id": dimension["id"], "paper_id": submission["paper_id"],
        "origin_kind": "cell", "origin_id": submission["id"], "values": values,
        "value_state": "value" if values else "unknown", "review_state": "confirmed" if values else "unreviewed",
        "reason": "SYNTHETIC typed normalization; no real research conclusion"})


def test_three_report_five_field_scoped_workflow_reopens_without_inference(case):
    assert len(case.view["cells"]) == 15
    definitions = {key: bind(case, key) for key in DIMENSIONS}
    for paper in case.papers:
        for field in DIMENSIONS:
            cell = submit(case, paper, field, key=paper + field)
            classify(case, definitions[field], cell, ["software-" + field] if cell["references"] else [], key="attr-" + paper + field)
    result = call(case, "query", {"columns": list(DIMENSIONS)})
    assert result["unique_report_count"] == 3
    assert [p["availability"] for p in result["profiles"]["papers"]] == ["full_text", "abstract", "none"]
    assert result["profiles"]["scope"] == "report_cooccurrence_only_not_same_cohort"
    audit = case.client.get(case.board + "/exports?format=json&history=true").json()
    assert len(audit["table"]) == 15 and len(audit["cell_revisions"]) == 15
    reopened = browser(create_app(case.directory, services={"saved_example": case.engine}, proposal_adapter=case.adapter), case.client.cookies.get(COOKIE_NAME))
    assert call(case, "query", {"columns": list(DIMENSIONS)}, client=reopened) == result
    assert case.provider.search_calls == 1 and case.provider.source_calls == 3
    assert case.adapter.calls == 0


def test_views_and_classification_never_rewrite_research_board_or_cell_receipts(case):
    dimension = bind(case)
    cell = submit(case, case.papers[0])
    before = case.client.get(case.board + "/exports?format=json&history=true").content
    research = case.client.get(case.root).content
    classified = classify(case, dimension, cell, ["skin", "stool"])
    config = {"columns": ["specimen"], "group_by": "specimen", "filters": [{"dimension": "specimen", "values": ["skin", "stool"]}]}
    saved = call(case, "saved", {"request_id": "save-view", "version": 0, "name": "Software methods", "config": config})
    query = call(case, "query", config)
    assert query["paper_ids"] == [case.papers[0]] and query["unique_report_count"] == 1
    assert query["group_occurrences"] == 2 and set(query["groups"]) == {"skin", "stool"}
    assert " OR " in query["filter_summary"]
    assert call(case, "saved", method="GET")[0]["id"] == saved["id"]
    assert case.client.get(case.board + "/exports?format=json&history=true").content == before
    assert case.client.get(case.root).content == research
    assert classified["scope"] == "report_cooccurrence_only"
    assert case.provider.search_calls == 1 and case.provider.source_calls == 3 and case.adapter.calls == 0


def test_wrong_paper_field_or_foreign_origin_cannot_confer_confirmed_attributes(case):
    dim = bind(case)
    cell = submit(case, case.papers[0])
    wrong_field = submit(case, case.papers[0], "design", key="other-field")
    payload = {"request_id": "wrong-paper", "dimension_revision_id": dim["id"], "paper_id": case.papers[1],
        "origin_kind": "cell", "origin_id": cell["id"], "values": ["skin"], "review_state": "confirmed", "reason": "software"}
    assert call(case, "attributes", payload, status=409)["error"]["code"] == "stale_attribute_origin"
    payload.update(request_id="wrong-field", paper_id=case.papers[0], origin_id=wrong_field["id"])
    call(case, "attributes", payload, status=409)
    payload.update(request_id="unknown-origin", origin_id="foreign-cell-id")
    call(case, "attributes", payload, status=422)
    payload.update(request_id="injected-reference", origin_id=cell["id"], references=[{"source_id": "foreign"}])
    call(case, "attributes", payload, status=422)
    profiles = call(case, "profiles", method="GET")
    assert all(a["revision"] is None for p in profiles["papers"] for a in p["attributes"])


def test_old_cell_or_definition_revision_becomes_outdated_without_silent_reclassification(case):
    dim = bind(case)
    cell = submit(case, case.papers[0])
    original = classify(case, dim, cell, ["skin"])
    replacement = submit(case, case.papers[0], key="revision", head=cell["id"], value="SOFTWARE corrected value")
    profiles = call(case, "profiles", method="GET")
    attr = next(a for a in profiles["papers"][0]["attributes"] if a["dimension_id"] == "specimen")
    assert attr["state"] == "outdated" and attr["revision"]["id"] == original["id"]
    assert call(case, "query", {"filters": [{"dimension": "specimen", "values": ["skin"]}]})["paper_ids"] == []
    assert case.client.get(case.board + "/cells/" + case.papers[0] + "/specimen/history").status_code == 200
    new_dim = bind(case, key="new-definition", head=dim["id"])
    assert new_dim["supersedes_id"] == dim["id"]
    # Source-backed text is retained, while an explicit current reclassification is required.
    assert replacement["references"] and case.adapter.calls == 0


def test_dimension_attribute_and_saved_view_cas_preserve_prior_revisions(case):
    dim = bind(case)
    call(case, "dimensions", {"request_id": "conflict", "dimension_id": "specimen", "field_id": "specimen",
        "label": "other", "definition": "another tab"}, status=409)
    cell = submit(case, case.papers[0])
    first = classify(case, dim, cell, ["skin"])
    payload = {"request_id": "attr-conflict", "dimension_revision_id": dim["id"], "paper_id": case.papers[0],
        "origin_kind": "cell", "origin_id": cell["id"], "values": ["stool"], "review_state": "confirmed", "reason": "software"}
    call(case, "attributes", payload, status=409)
    request = {"request_id": "view1", "version": 0, "name": "Software overview", "config": {"columns": ["specimen"]}}
    saved = call(case, "saved", request)
    updated = call(case, "saved/" + saved["id"], {**request, "request_id": "view2", "version": 1, "name": "Software corrected view"}, method="PUT")
    assert updated["id"] == saved["id"] and updated["version"] == 2
    call(case, "saved/" + saved["id"], {**request, "request_id": "view-stale", "version": 1}, method="PUT", status=409)
    assert call(case, "saved", method="GET") == [updated]
    profiles = call(case, "profiles", method="GET")
    assert next(a for a in profiles["papers"][0]["attributes"] if a["dimension_id"] == "specimen")["revision"]["id"] == first["id"]


def test_confirmed_facets_exclude_unreviewed_proposals_and_dismissal_stales_them(case):
    dim = bind(case)
    response = case.client.post(case.board + "/proposal-runs", json={"request_id": "mock-proposal",
        "expected_revision_id": case.revision, "paper_ids": [case.papers[0]], "field_ids": ["specimen"]})
    response.raise_for_status()
    proposals = case.client.get(case.board + "/proposals", params={"revision_id": case.revision}).json()["items"]
    proposal = proposals[0]
    payload = {"request_id": "proposal-attribute", "dimension_revision_id": dim["id"], "paper_id": case.papers[0],
        "origin_kind": "proposal", "origin_id": proposal["id"], "values": ["model-suggestion"],
        "review_state": "unreviewed", "reason": "Mock suggestion is not researcher-confirmed."}
    call(case, "attributes", {**payload, "request_id": "proposal-confirmed", "review_state": "confirmed"}, status=422)
    call(case, "attributes", payload)
    config = {"filters": [{"dimension": "specimen", "values": ["model-suggestion"]}]}
    assert call(case, "query", config)["paper_ids"] == []
    assert call(case, "query", {**config, "include_unreviewed": True})["paper_ids"] == [case.papers[0]]
    dismissed = case.client.post(case.board + "/proposals/" + proposal["id"] + "/dismiss", json={"request_id": "dismiss",
        "expected_revision_id": case.revision, "reason": "Mock dismissal"})
    dismissed.raise_for_status()
    assert call(case, "query", {**config, "include_unreviewed": True})["paper_ids"] == []
    assert all(cell["head"] is None for cell in case.client.get(case.board).json()["cells"])
    assert case.adapter.calls == 1


def test_unknown_multifacets_and_filtered_export_have_exact_order_and_formula_safety(case):
    specimen, design = bind(case), bind(case, "design")
    for index, paper in enumerate(case.papers[:2]):
        a = submit(case, paper, key="s" + str(index))
        b = submit(case, paper, "design", key="d" + str(index))
        classify(case, specimen, a, ["skin", "stool"] if index == 0 else ["saliva"], key="as" + str(index))
        classify(case, design, b, ["software-design"], key="ad" + str(index))
    unknown = call(case, "query", {"filters": [{"dimension": "specimen", "values": ["unknown"]}]})
    assert unknown["paper_ids"] == [case.papers[2]]
    config = {"columns": ["specimen", "design"], "sort_by": "report_order", "descending": True,
        "filters": [{"dimension": "specimen", "values": ["skin", "saliva"]}, {"dimension": "design", "values": ["software-design"]}]}
    filtered = call(case, "query", config)
    assert filtered["paper_ids"] == case.papers[1::-1]
    result = case.client.post(endpoint(case, "exports"), params={"revision_id": case.revision, "format": "json"}, json=config)
    result.raise_for_status()
    exported = result.json()["view"]
    assert exported["paper_ids"] == filtered["paper_ids"]
    assert {p["paper_id"] for p in exported["profiles"]["papers"]} == set(filtered["paper_ids"])
    csv_result = case.client.post(endpoint(case, "exports"), params={"revision_id": case.revision, "format": "csv"}, json=config)
    csv_result.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(csv_result.text)))
    assert [row["paper_id"] for row in rows] == filtered["paper_ids"]
    assert rows[1]["paper_title"] == "'=SOFTWARE_FORMULA()"
    assert "report" in result.json()["meaning"].lower()


def test_view_endpoints_keep_session_origin_csrf_scope_and_deletion_authority(case):
    foreign = browser(case.app)
    call(case, "profiles", method="GET", status=404, client=foreign)
    call(case, "query", {}, status=404, client=foreign)
    for missing in ("Origin", "X-CSRF-Token"):
        client = browser(case.app, case.client.cookies.get(COOKIE_NAME))
        client.headers.pop(missing)
        call(case, "saved", {"request_id": missing, "version": 0, "name": "forbidden", "config": {}}, status=403, client=client)
    saved = call(case, "saved", {"request_id": "view", "version": 0, "name": "retained", "config": {}})
    scope = "board-view:" + case.view["definition"]["board_id"] + ":" + case.revision
    draft_path = case.root + "/drafts/" + quote(scope, safe="")
    draft = {"schema_version": "mvp.evidence-view-draft.v1", "board_id": case.view["definition"]["board_id"],
        "board_revision_id": case.revision, "view_id": saved["id"], "base_view_version": 0, "config": {"columns": ["specimen"]}}
    put = case.client.put(draft_path, json={"version": 0, "expected_assessment_head": None, "data": draft})
    put.raise_for_status()
    conflict = case.client.put(draft_path, json={"version": 0, "expected_assessment_head": None, "data": {**draft, "config": {}}})
    assert conflict.status_code == 409
    assert put.json()["data"]["config"]["columns"] == ["specimen"]
    assert case.client.get(draft_path).json()["data"] == put.json()["data"]
    deleted = case.client.delete(case.root)
    deleted.raise_for_status()
    call(case, "profiles", method="GET", status=404)
    call(case, "saved", method="GET", status=404)


def test_new_source_preparation_does_not_rebind_existing_attributes_or_history(case):
    dimension = bind(case)
    cell = submit(case, case.papers[0])
    classification = classify(case, dimension, cell, ["skin"])
    definition_before = case.client.get(case.board).json()["definition"]
    history_path = case.board + "/cells/" + case.papers[0] + "/specimen/history"
    history_before = case.client.get(history_path).json()
    prepared = case.client.post(case.root + "/source-preparations", json={"request_id": "new-source-preparation",
        "search_id": case.prep["search_id"], "paper_ids": case.papers})
    prepared.raise_for_status()
    assert prepared.json()["id"] != case.prep["id"]
    profiles = call(case, "profiles", method="GET")
    assert profiles["freshness"] == "historical"
    item = next(a for a in profiles["papers"][0]["attributes"] if a["dimension_id"] == "specimen")
    assert item["state"] == "outdated" and item["revision"]["id"] == classification["id"]
    assert case.client.get(case.board).json()["definition"] == definition_before
    assert case.client.get(history_path).json() == history_before
    call(case, "attributes", {"request_id": "stale-source-write", "expected_head_id": classification["id"],
        "dimension_revision_id": dimension["id"], "paper_id": case.papers[0], "origin_kind": "cell",
        "origin_id": cell["id"], "values": ["stool"], "review_state": "confirmed", "reason": "software"}, status=409)
    assert case.adapter.calls == 0


def test_readable_strategy_keeps_exact_query_with_safe_markdown_fence_and_no_io(case):
    raw = "  (microbiome[tiab] OR saliva[tiab])\r\nAND women[tiab]\r\n```<script>SOFTWARE</script>  "
    original_question = "SOFTWARE <script>untrusted question</script> 亚洲 🧬"
    made = case.client.post(case.root + "/search-plans", json={"request_id": "raw-plan", "draft": {
        "original_question": original_question, "input_mode": "manual_strategy", "manual_strategy": raw}})
    made.raise_for_status()
    view = made.json()
    path = case.root + "/search-plans/" + view["revision"]["plan_id"]
    before = case.client.get(path).content
    params = {"revision_id": view["revision"]["revision_id"], "candidate_id": "manual_strategy", "format": "json"}
    projected = case.client.get(path + "/strategy-export", params=params)
    projected.raise_for_status()
    value = projected.json()
    assert value["query"] == raw and value["query_sha256"] == sha256(raw.encode()).hexdigest()
    assert value["capture"] is None and value["diagnostic"] is None and value["approval_status"] == "not_approved"
    markdown = case.client.get(path + "/strategy-export", params={**params, "format": "markdown"})
    markdown.raise_for_status()
    assert "````text\n" + raw + "\n````" in markdown.text
    assert "&lt;script&gt;untrusted question&lt;/script&gt;" in markdown.text
    assert case.client.get(path).content == before
    assert case.provider.search_calls == 1 and case.provider.source_calls == 3 and case.adapter.calls == 0
    foreign = browser(case.app)
    assert foreign.get(path + "/strategy-export", params=params).status_code == 404


def test_researcher_terminology_notes_cannot_promote_approval_to_verified_mesh(case):
    question = "SOFTWARE microbiomes across sample sites in women"
    draft = {"original_question": question, "concepts": [{"id": "site", "label": "Microbiome site", "role": "topic",
        "requirement": "required", "retrieval_use": "query", "terms": [{"id": "mesh", "text": "Microbiota",
        "field": "mesh", "origin": "terminology", "state": "approved"}]}], "variants": [{"id": "broad",
        "label": "Broad discovery", "kind": "broad", "expression": {"op": "concept_ref", "concept_id": "site"}}]}
    response = case.client.post(case.root + "/search-plans", json={"request_id": "guided-plan", "draft": draft})
    response.raise_for_status()
    view = response.json()
    path = case.root + "/search-plans/" + view["revision"]["plan_id"]
    assert view["revision"]["compiled"]["terminology_status"] == "no_server_mesh_registry"
    assert view["revision"]["compiled"]["candidates"][0]["status"] == "blocked"
    metadata = {"term_notes": [{"concept_id": "site", "term_id": "mesh", "note": "Researcher reference, not verified here.",
        "authority_reference": "https://www.ncbi.nlm.nih.gov/mesh/"}], "extraction_questions": [
        {"id": "specimen", "question": "Which specimen sites were sampled?", "source_span": {"start": 9, "end": 20, "text": "WRONG SPAN"}}]}
    # A mismatching code-point binding is rejected, not normalized or silently repaired.
    payload = {"request_id": "bad-span", "expected_revision_id": view["revision"]["revision_id"], "expected_version": 0, "metadata": metadata}
    assert case.client.put(path + "/metadata", json=payload).status_code == 422
    metadata["extraction_questions"][0]["source_span"] = None
    payload["request_id"] = "notes"
    saved = case.client.put(path + "/metadata", json=payload)
    saved.raise_for_status()
    assert saved.json()["terminology_verification"] == "unavailable"
    assert saved.json()["term_bindings"][0]["state"] == "approved" and saved.json()["term_bindings"][0]["verification"] == "unavailable"
    assert case.client.get(path).json() == view
    assert case.provider.search_calls == 1 and case.adapter.calls == 0


def test_profile_form_draft_retains_unfinished_inputs_and_historical_get_is_read_only(case):
    paper = case.papers[0]
    scope = "board-profile:" + case.view["definition"]["board_id"] + ":" + case.revision + ":" + paper.encode().hex()
    path = case.root + "/drafts/" + quote(scope, safe="")
    data = {"schema_version": "mvp.evidence-profile-draft.v1", "board_id": case.view["definition"]["board_id"],
        "board_revision_id": case.revision, "paper_id": paper, "dimension_id": "specimen", "field_id": "specimen",
        "baseline_initialized": False, "base_dimension_head_id": None, "base_attribute_head_id": None, "origin_cell_head_id": None,
        "definition": "", "values": ["", "unfinished software input 亚洲"], "value_state": "value",
        "confirm": False, "origin": "cell", "reason": ""}
    saved = case.client.put(path, json={"version": 0, "expected_assessment_head": None, "data": data})
    saved.raise_for_status()
    assert saved.json()["data"] == data
    assert all(cell["head"] is None for cell in case.client.get(case.board).json()["cells"])
    reopened = browser(create_app(case.directory, services={"saved_example": case.engine}, proposal_adapter=case.adapter), case.client.cookies.get(COOKIE_NAME))
    assert reopened.get(path).json() == saved.json()
    conflict = reopened.put(path, json={"version": 0, "expected_assessment_head": None, "data": {**data, "reason": "other tab"}})
    assert conflict.status_code == 409
    wrong = reopened.put(path, json={"version": 1, "expected_assessment_head": None, "data": {**data, "paper_id": case.papers[1]}})
    assert wrong.status_code == 422
    assert browser(case.app).get(path).status_code == 404
    prepared = case.client.post(case.root + "/source-preparations", json={"request_id": "replacement-for-profile",
        "search_id": case.prep["search_id"], "paper_ids": case.papers})
    prepared.raise_for_status()
    assert reopened.get(path).json() == saved.json()
    rejected = reopened.put(path, json={"version": 1, "expected_assessment_head": None, "data": {**data, "reason": "historical change"}})
    assert rejected.status_code == 409
    assert reopened.get(path).json() == saved.json()
    assert case.adapter.calls == 0


def test_attribute_and_saved_view_histories_preserve_exact_versions_and_owned_sources(case):
    dimension = bind(case)
    cell = submit(case, case.papers[0])
    first = classify(case, dimension, cell, ["skin"])
    second = classify(case, dimension, cell, ["skin", "stool"], key="explicit-revision", head=first["id"])
    response = case.client.get(endpoint(case, "attributes/history"), params={"revision_id": case.revision,
        "paper_id": case.papers[0], "dimension_id": "specimen", "offset": 0, "limit": 1})
    response.raise_for_status()
    assert response.json()["total"] == 2 and response.json()["items"] == [second]
    assert response.json()["dimension_definitions"] == [dimension]
    older = case.client.get(endpoint(case, "attributes/history"), params={"revision_id": case.revision,
        "paper_id": case.papers[0], "dimension_id": "specimen", "offset": 1, "limit": 1}).json()
    assert older["items"] == [first]
    assert first["references"] == second["references"]
    assert first["references"][0]["paper_id"] == case.papers[0]
    one = call(case, "saved", {"request_id": "history-view1", "version": 0, "name": "software one", "config": {}})
    two = call(case, "saved/" + one["id"], {"request_id": "history-view2", "version": 1, "name": "software two",
        "config": {"filters": [{"dimension": "specimen", "values": ["unknown"]}]}}, method="PUT")
    assert one["revision_id"] != two["revision_id"]
    history = call(case, "saved/" + one["id"] + "/history", method="GET")
    assert history["items"] == [two, one]
    assert one["paper_ids"] == case.papers and two["paper_ids"] == case.papers[1:]
    assert one["basis_sha256"] == two["basis_sha256"]
    call(case, "saved/" + one["id"] + "/history", method="GET", client=browser(case.app), status=404)
    assert case.provider.search_calls == 1 and case.provider.source_calls == 3 and case.adapter.calls == 0


def test_reopened_named_view_draft_keeps_exact_baseline_and_cannot_absorb_other_tab(case):
    first = call(case, "saved", {"request_id": "baseline-one", "version": 0, "name": "software baseline", "config": {}})
    scope = "board-view:" + case.view["definition"]["board_id"] + ":" + case.revision
    path = case.root + "/drafts/" + quote(scope, safe="")
    draft = {"schema_version": "mvp.evidence-view-draft.v1", "board_id": case.view["definition"]["board_id"],
        "board_revision_id": case.revision, "view_id": first["id"], "base_view_version": 1,
        "config": {"columns": ["specimen"], "filters": []}}
    saved = case.client.put(path, json={"version": 0, "expected_assessment_head": None, "data": draft})
    saved.raise_for_status()
    second = call(case, "saved/" + first["id"], {"request_id": "other-tab", "version": 1,
        "name": "other software tab", "config": {"columns": ["design"]}}, method="PUT")
    reopened = browser(create_app(case.directory, services={"saved_example": case.engine}, proposal_adapter=case.adapter), case.client.cookies.get(COOKIE_NAME))
    assert saved.json()["data"]["base_view_version"] == 1
    assert saved.json()["data"]["config"]["columns"] == ["specimen"]
    assert reopened.get(path).json()["data"] == saved.json()["data"]
    call(case, "saved/" + first["id"], {"request_id": "stale-form-publish", "version": draft["base_view_version"],
        "name": "stale software edit", "config": draft["config"]}, method="PUT", status=409, client=reopened)
    # A forged non-existent history baseline is rejected; existing history remains intact.
    forged = reopened.put(path, json={"version": 1, "expected_assessment_head": None, "data": {**draft, "base_view_version": 99}})
    assert forged.status_code == 422
    assert call(case, "saved", method="GET") == [second]
    assert saved.json()["data"]["base_view_version"] == 1
    assert saved.json()["data"]["config"]["columns"] == ["specimen"]
    assert reopened.get(path).json()["data"] == saved.json()["data"]


def test_unfinished_search_design_draft_is_durable_but_cannot_be_published(case):
    response = case.client.post(case.root + "/search-plans", json={"request_id": "partial-notes-plan", "draft": {
        "original_question": "SOFTWARE all microbiome sample types", "input_mode": "manual_strategy", "manual_strategy": "microbiome"}})
    response.raise_for_status()
    revision = response.json()["revision"]
    plan_path = case.root + "/search-plans/" + revision["plan_id"]
    scope = "search-plan-metadata:" + revision["plan_id"] + ":" + revision["revision_id"]
    path = case.root + "/drafts/" + quote(scope, safe="")
    metadata = {"extraction_questions": [{"id": "unfinished", "question": "", "source_span": None}],
        "term_notes": [], "external_searches": [{"id": "partial-external", "database": "MEDLINE", "platform": "", "query": "",
        "executed_on": None, "reported_count": None, "limits_note": "partly typed", "collection_ref": None}]}
    data = {"plan_id": revision["plan_id"], "revision_id": revision["revision_id"], "base_metadata_version": 0, "metadata": metadata}
    saved = case.client.put(path, json={"version": 0, "expected_assessment_head": "0", "data": data})
    saved.raise_for_status()
    assert saved.json()["data"] == data
    published = case.client.put(plan_path + "/metadata", json={"request_id": "reject-unfinished", "expected_revision_id": revision["revision_id"],
        "expected_version": 0, "metadata": metadata})
    assert published.status_code == 422
    assert case.client.get(plan_path + "/metadata").json()["version"] == 0
    reopened = browser(create_app(case.directory, services={"saved_example": case.engine}, proposal_adapter=case.adapter), case.client.cookies.get(COOKIE_NAME))
    assert reopened.get(path).json()["data"] == data
    assert browser(case.app).get(path).status_code == 404
    assert case.adapter.calls == 0 and case.provider.search_calls == 1


def test_profile_draft_baselines_survive_remote_revisions_until_explicit_rebase(case):
    dimension = bind(case)
    cell = submit(case, case.papers[0])
    first = classify(case, dimension, cell, ["skin"])
    paper = case.papers[0]
    scope = "board-profile:" + case.view["definition"]["board_id"] + ":" + case.revision + ":" + paper.encode().hex()
    path = case.root + "/drafts/" + quote(scope, safe="")
    data = {"schema_version": "mvp.evidence-profile-draft.v1", "board_id": case.view["definition"]["board_id"],
        "board_revision_id": case.revision, "paper_id": paper, "dimension_id": "specimen", "field_id": "specimen",
        "baseline_initialized": True, "base_dimension_head_id": dimension["id"], "base_attribute_head_id": first["id"],
        "origin_cell_head_id": cell["id"], "definition": dimension["definition"], "values": ["unfinished old form"],
        "value_state": "value", "confirm": False, "origin": "cell", "reason": "Retained synthetic form"}
    saved = case.client.put(path, json={"version": 0, "expected_assessment_head": None, "data": data})
    saved.raise_for_status()
    second = classify(case, dimension, cell, ["stool"], key="other-classification", head=first["id"])
    newer_dimension = bind(case, key="other-dimension", head=dimension["id"])
    reopened = browser(create_app(case.directory, services={"saved_example": case.engine}, proposal_adapter=case.adapter), case.client.cookies.get(COOKIE_NAME))
    assert reopened.get(path).json()["data"] == data
    call(case, "attributes", {"request_id": "old-form-publish", "expected_head_id": data["base_attribute_head_id"],
        "dimension_revision_id": data["base_dimension_head_id"], "paper_id": paper, "origin_kind": "cell",
        "origin_id": data["origin_cell_head_id"], "values": ["unfinished old form"], "review_state": "unreviewed", "reason": "software"}, status=409, client=reopened)
    call(case, "dimensions", {"request_id": "old-dimension-publish", "expected_head_id": data["base_dimension_head_id"],
        "dimension_id": "specimen", "field_id": "specimen", "label": "old", "definition": "Old retained draft"}, status=409, client=reopened)
    # Baselines are owned history identities, never arbitrary IDs from a URL/form.
    bad = reopened.put(path, json={"version": 1, "expected_assessment_head": None, "data": {**data, "base_attribute_head_id": "foreign"}})
    assert bad.status_code == 422 and reopened.get(path).json()["data"] == data
    assert second["supersedes_id"] == first["id"] and newer_dimension["supersedes_id"] == dimension["id"]


def test_current_view_exports_actual_visible_cells_only_without_drafts_or_hidden_attributes(case):
    dimension = bind(case)
    cell = submit(case, case.papers[0], value="SOFTWARE visible scientific cell value")
    classify(case, dimension, cell, ["HIDDEN_TYPED_CLASSIFICATION"])
    draft_path = case.board + "/drafts/" + case.papers[0] + "/specimen"
    old = case.client.get(draft_path).json()
    draft = case.client.put(draft_path, json={"version": old["version"], "expected_revision_id": case.revision,
        "expected_cell_head_id": cell["id"], "data": {"value": "PRIVATE_UNSUBMITTED_DRAFT_MARKER"}})
    draft.raise_for_status()
    config = {"columns": ["field:specimen"], "filters": [{"dimension": "specimen", "values": ["HIDDEN_TYPED_CLASSIFICATION"]}]}
    response = case.client.post(endpoint(case, "exports"), params={"revision_id": case.revision, "format": "json"}, json=config)
    response.raise_for_status()
    value = response.json()
    assert [r["paper_id"] for r in value["rows"]] == [case.papers[0]]
    visible = value["rows"][0]["visible_values"]
    assert set(visible) == {"field:specimen"}
    assert visible["field:specimen"]["state"] == "submitted"
    head = visible["field:specimen"]["head"]
    assert head["id"] == cell["id"] and head["value"] == cell["value"] and head["semantic_assessment"] == cell["semantic_assessment"]
    assert head["references"][0]["source_sha256"] == cell["references"][0]["source_sha256"]
    assert value["view"]["profiles"]["papers"][0]["attributes"] == []
    assert value["view"]["profiles"]["dimensions"] == []
    assert "PRIVATE_UNSUBMITTED_DRAFT_MARKER" not in response.text
    assert "HIDDEN_TYPED_CLASSIFICATION" not in json.dumps(value["rows"])
    assert value["scope"]["source_manifest_sha256"] == case.view["definition"]["source_manifest_sha256"]
    csv_result = case.client.post(endpoint(case, "exports"), params={"revision_id": case.revision, "format": "csv"}, json=config)
    csv_result.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(csv_result.text)))
    assert len(rows) == 1 and json.loads(rows[0]["visible_values"]) == visible
    full = case.client.get(case.board + "/exports?format=json&history=true").json()
    assert len(full["table"]) == 15 and len(full["cell_revisions"]) == 1


def test_current_view_export_reads_profiles_and_cells_in_one_snapshot_during_edit(case, monkeypatch):
    cell = submit(case, case.papers[0], value="SOFTWARE before concurrent edit")
    service = case.app.state.evidence_views
    entered, release, edit_started = threading.Event(), threading.Event(), threading.Event()
    original_query, original_view = service._query, case.app.state.boards._view
    reads = []
    def capture_view(state, db, definition):
        if len(reads) < 2: reads.append((db, db.in_transaction))
        return original_view(state, db, definition)
    def pause(profiles, config):
        value = original_query(profiles, config)
        entered.set()
        assert release.wait(timeout=5), "Bounded snapshot test did not release its own export"
        return value
    monkeypatch.setattr(case.app.state.boards, "_view", capture_view)
    monkeypatch.setattr(service, "_query", pause)
    exporting = browser(case.app, case.client.cookies.get(COOKIE_NAME))
    def export():
        result = exporting.post(endpoint(case, "exports"), params={"revision_id": case.revision, "format": "json"}, json={"columns": ["field:specimen"]})
        result.raise_for_status()
        return result.json()
    def edit():
        edit_started.set()
        return submit(case, case.papers[0], key="concurrent-revision", head=cell["id"], value="SOFTWARE after concurrent edit")
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(export)
        try:
            assert entered.wait(timeout=5)
            editing = pool.submit(edit)
            assert edit_started.wait(timeout=5)
        finally: release.set()
        value = pending.result(timeout=10)
        revised = editing.result(timeout=10)
    assert len(reads) == 2 and reads[0][0] is reads[1][0] and all(in_transaction for _, in_transaction in reads)
    exported = next(row for row in value["rows"] if row["paper_id"] == case.papers[0])["visible_values"]["field:specimen"]["head"]
    assert exported["id"] == cell["id"] and exported["value"] == "SOFTWARE before concurrent edit"
    assert revised["id"] != cell["id"] and revised["value"] == "SOFTWARE after concurrent edit"
