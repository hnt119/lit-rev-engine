"""Retained public papers through imported preparation, review and exports.

These are offline software checks over checked source artifacts, not fresh
PubMed calls, model runs or scientific/human usefulness validation.
"""
from types import SimpleNamespace
from urllib.parse import quote
import csv
import io
import json
import socket

import pytest
from fastapi.testclient import TestClient

from src.mvp.mapping import EmbeddedPaper, EmbeddingProfile, validate_vector
from src.web_api.app import COOKIE_NAME, create_app

BASE, ORIGIN = "http://127.0.0.1:8765", "http://127.0.0.1:3000"
REFERENCE_KEYS = {"source_id", "source_version", "source_sha256", "blocks_sha256", "block_id", "start", "end"}
FIELDS = [{"id": "microbiome", "label": "Microbiome", "subquestion": "gut microbiota microbiome"},
          {"id": "population", "label": "Population", "subquestion": "participants women cohort population"},
          {"id": "diet", "label": "Diet", "subquestion": "diet dietary food"}]


class SoftwareVectors:
    profile = EmbeddingProfile(model="SOFTWARE TEST VECTORS", model_revision="synthetic-v1", tokenizer_revision="synthetic-v1",
        dimension=3, runtime_versions={"fixture": "synthetic vectors, not model inference"})

    def __init__(self):
        self.calls = []

    def readiness(self):
        return True, "Synthetic software fixture"

    def embed(self, representation, checkpoint):
        self.calls.append(representation.paper_id)
        checkpoint()
        value = int(representation.input_sha256[:8], 16)
        return EmbeddedPaper(paper_id=representation.paper_id, input_sha256=representation.input_sha256,
            representation=representation.representation, vector=validate_vector([1., value % 23, value % 19], 3),
            window_token_weights=[1], token_count=1)


def client_for(app, cookie=None):
    client = TestClient(app, base_url=BASE)
    if cookie:
        client.cookies.set(COOKIE_NAME, cookie)
    csrf = client.get("/api/v1/session").json()["csrf_token"]
    client.headers.update({"Origin": ORIGIN, "X-CSRF-Token": csrf})
    return client


@pytest.fixture
def workflow(tmp_path, monkeypatch):
    monkeypatch.setenv("MVP_MAP_ENABLED", "0")
    monkeypatch.setenv("MVP_PROPOSALS_ENABLED", "0")
    monkeypatch.delenv("NCBI_EMAIL", raising=False)
    def denied(*args, **kwargs):
        pytest.fail("Collection workflow attempted external provider/model networking")
    monkeypatch.setattr(socket, "create_connection", denied)
    embedder = SoftwareVectors()
    app = create_app(tmp_path, map_embedder=embedder)
    client = client_for(app)
    created = client.post("/api/v1/workspaces", json={"request_id": "workspace", "mode": "saved_example",
        "question": "SOFTWARE CHECK: retained microbiome sources"})
    created.raise_for_status()
    root = "/api/v1/workspaces/" + created.json()["id"]
    searched = client.post(root + "/searches", json={"request_id": "search", "query": "saved public example", "max_results": 30})
    searched.raise_for_status()
    search = searched.json()
    listed = client.get(root + "/maps", params={"search_id": search["id"]})
    listed.raise_for_status()
    legacy_map = client.get(root + "/maps/" + listed.json()["maps"][0]["map_id"]).json()
    text = io.StringIO(newline="")
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(["Title", "PMID", "DOI", "Abstract Note"])
    for paper in search["papers"][:2]:
        writer.writerow([paper["title"], paper["pmid"], paper["doi"], paper["abstract"]])
    writer.writerow(["SOFTWARE MISSING-TEXT RECORD", "", "", ""])
    imported = client.post(root + "/imports/csv", content=text.getvalue().encode(),
        headers={"Content-Type": "text/csv", "X-Request-ID": "import", "X-Import-Filename": "retained-public-citations.csv"})
    imported.raise_for_status()
    rows = client.get(root + "/imports/" + imported.json()["id"] + "/rows").json()["rows"]
    saved = client.post(root + "/imports/" + imported.json()["id"] + "/commit", json={"request_id": "commit",
        "expected_revision": imported.json()["revision"], "name": "Retained public papers and explicit missing text",
        "accepted_row_ids": [row["id"] for row in rows]})
    saved.raise_for_status()
    collection = saved.json()
    papers = client.get(root + "/collections/" + collection["id"] + "/papers").json()["papers"]
    return SimpleNamespace(app=app, client=client, root=root, path=tmp_path, search=search, legacy_map=legacy_map,
        collection=collection, papers=papers, embedder=embedder)


def collection_job(case, key="prepare"):
    state = case.client.get(case.root).json()
    request = {"request_id": key, "collection_ref": case.collection["origin"], "paper_ids": [paper["id"] for paper in case.papers],
        "expected_source_revision": state["source_revision"], "expected_preparation_id": state["current_preparation_id"]}
    response = case.client.post(case.root + "/collection-preparation-jobs", json=request)
    assert response.status_code == 202, response.text
    return response.json()["job"]


def finish_preparation(case, job):
    assert case.app.state.preparation_worker.run_once()
    response = case.client.get(case.root + "/collection-preparation-jobs/" + job["id"])
    response.raise_for_status()
    assert response.json()["status"] == "succeeded", response.text
    prepared = case.client.get(case.root + "/source-preparations/" + response.json()["result_preparation_id"])
    prepared.raise_for_status()
    return prepared.json()


def make_board(case, preparation, key="board"):
    response = case.client.post(case.root + "/boards", json={"request_id": key, "preparation_id": preparation["id"],
        "question": "SOFTWARE CHECK: microbiome, population and diet", "paper_ids": preparation["selected_paper_ids"], "fields": FIELDS})
    response.raise_for_status()
    view = response.json()
    return case.root + "/boards/" + view["definition"]["board_id"], view


def test_collection_board_passage_search_retains_origin_and_returns_exact_cell_source(workflow):
    case = workflow
    prepared = finish_preparation(case, collection_job(case))
    board, view = make_board(case, prepared)
    definition = view['definition']
    scope = {'board_id': definition['board_id'], 'board_revision_id': definition['revision_id'],
             'paper_id': definition['paper_ids'][0], 'field_id': 'microbiome'}
    params = {'revision_id': scope['board_revision_id'], 'paper_id': scope['paper_id'], 'field_id': scope['field_id']}
    context = case.client.get(board + '/passage-search-context', params=params)
    assert context.status_code == 200, context.text
    assert context.json()['paper_ids'] == [scope['paper_id']]
    response = case.client.post(case.root + '/evidence-runs', json={'request_id': 'collection-board-passages',
        'question': context.json()['question'], 'top_k': 10, 'expected_preparation_id': prepared['id'],
        'expected_source_revision': prepared['source_revision'], 'board_context': scope})
    assert response.status_code == 200, response.text
    run = response.json()
    assert run['schema_version'] == 'mvp.collection-lexical-evidence.v2'
    assert run['collection_ref'] == case.collection['origin'] and run['search_id'] is None
    assert run['passages'] and {passage['paper_id'] for passage in run['passages']} == {scope['paper_id']}
    before = case.client.get(board + '/exports?format=json').json()
    opened = case.client.get(board + '/passage-source-context', params={**params, 'run_id': run['id'],
        'passage_id': run['passages'][0]['id']})
    assert opened.status_code == 200, opened.text
    assert opened.json()['reference']['quote'] == run['passages'][0]['anchor']['quote'][:4000]
    assert case.client.get(board + '/exports?format=json').json() == before


def save_and_submit(case, board, view, paper_id, field_id, data, key):
    draft_url = board + "/drafts/" + quote(paper_id, safe="") + "/" + field_id
    draft = case.client.put(draft_url, json={"expected_revision_id": view["definition"]["revision_id"], "version": 0,
        "expected_cell_head_id": None, "data": data})
    draft.raise_for_status()
    pending = next(cell for cell in case.client.get(board).json()["cells"] if cell["paper_id"] == paper_id and cell["field_id"] == field_id)
    assert pending["head"] is None, "A durable draft must still need explicit researcher submission"
    submitted = case.client.post(board + "/cell-revisions", json={"request_id": key,
        "expected_revision_id": view["definition"]["revision_id"], "paper_id": paper_id, "field_id": field_id,
        "draft_version": draft.json()["version"]})
    assert submitted.status_code == 200, submitted.text
    return submitted.json()


def test_actual_retained_imports_prepare_retrieve_inspect_review_reopen_and_export(workflow):
    case = workflow
    prepared = finish_preparation(case, collection_job(case))
    assert prepared["collection_ref"] == case.collection["origin"] and prepared["search_id"] is None
    assert [source["source_type"] for source in prepared["sources"]] == ["full_text", "full_text", "none"]
    assert all(source["license"] for source in prepared["sources"][:2])
    run_response = case.client.post(case.root + "/evidence-runs", json={"request_id": "evidence", "question": "gut microbiota microbiome",
        "top_k": 5, "expected_preparation_id": prepared["id"], "expected_source_revision": prepared["source_revision"]})
    assert run_response.status_code == 200, run_response.text
    run = run_response.json()
    assert run["collection_ref"] == case.collection["origin"] and run["search_id"] is None and run["passages"]
    context = case.client.get(case.root + "/runs/" + run["id"] + "/passages/" + run["passages"][0]["id"] + "/context")
    context.raise_for_status()
    assert context.json()["source"]["source_type"] == "full_text"
    assert "retained_content_utf8" not in json.dumps(context.json())
    board, view = make_board(case, prepared)
    assert view["definition"]["schema_version"] != "mvp.board-definition.v1"
    assert view["definition"]["collection_ref"] == case.collection["origin"] and view["definition"]["search_id"] is None
    assert len(view["cells"]) == 9
    candidate_runs = {}
    for paper in case.papers:
        for field in FIELDS:
            response = case.client.post(board + "/candidates", json={"request_id": paper["id"] + field["id"],
                "expected_revision_id": view["definition"]["revision_id"], "paper_id": paper["id"], "field_id": field["id"], "top_k": 3})
            response.raise_for_status()
            candidate_runs[(paper["id"], field["id"])] = response.json()
    missing_id = case.papers[-1]["id"]
    assert all(candidate_runs[(missing_id, field["id"])]["returned_count"] == 0 for field in FIELDS)
    assert all(cell["head"] is None for cell in case.client.get(board).json()["cells"])
    candidate = candidate_runs[(case.papers[0]["id"], "microbiome")]["candidates"][0]
    reference = candidate["reference"]
    inspected = case.client.get(board + "/references/" + reference["id"] + "/context")
    inspected.raise_for_status()
    assert inspected.json()["reference"]["quote"] == reference["quote"]
    assert all(cell["head"] is None for cell in case.client.get(board).json()["cells"])
    selected = {key: reference[key] for key in REFERENCE_KEYS}
    submitted = save_and_submit(case, board, view, case.papers[0]["id"], "microbiome", {
        "value": "=SOFTWARE_TEST()", "references": [selected], "inspected_ranges": [selected],
        "semantic_assessment": "unassessed", "scope_result": "not_assessed"}, "submit-source-linked")
    assert submitted["reference_integrity"] == "checked" and submitted["semantic_assessment"] == "unassessed"
    assert submitted["review_state"] == "single_human_self_declared_not_independently_verified"
    unavailable = save_and_submit(case, board, view, missing_id, "diet", {"value": None,
        "missing_information": "No source text was retained for this record; whole-paper absence was not assessed.",
        "reason": "Source acquisition returned no usable text; no finding was inferred.",
        "semantic_assessment": "unassessed", "scope_result": "not_assessed"}, "submit-unavailable")
    assert unavailable["references"] == [] and unavailable["value"] is None
    reopened = client_for(create_app(case.path, map_embedder=case.embedder), case.client.cookies.get(COOKIE_NAME))
    heads = [cell["head"] for cell in reopened.get(board).json()["cells"] if cell["head"]]
    assert {head["id"] for head in heads} == {submitted["id"], unavailable["id"]}
    exported = reopened.get(board + "/exports", params={"format": "json", "history": True})
    exported.raise_for_status()
    audit = exported.json()
    assert audit["schema_version"] != "mvp.board-audit.v1" and audit["definitions"][0]["collection_ref"] == case.collection["origin"]
    assert any(row["value"] == "=SOFTWARE_TEST()" for row in audit["table"])
    exported_csv = reopened.get(board + "/exports", params={"format": "csv"})
    exported_csv.raise_for_status()
    csv_rows = list(csv.DictReader(io.StringIO(exported_csv.text)))
    assert len(csv_rows) == 9 and any(row["value"].startswith("'") for row in csv_rows if "SOFTWARE_TEST" in row["value"])
    bundle = reopened.get(case.root + "/exports", params={"format": "json"})
    bundle.raise_for_status()
    assert bundle.json()["schema_version"] != "mvp.audit-bundle.v1"
    assert case.client.get(case.root).json()["searches"][0]["id"] == case.search["id"]
    assert len(case.client.get(case.root).json()["searches"]) == 1
    assert case.client.get(case.root + "/maps/" + case.legacy_map["artifact"]["map_id"]).json() == case.legacy_map
    assert case.embedder.calls == [], "Loading the saved map and reviewing evidence must not run embeddings"


def test_collection_jobs_and_maps_keep_session_authority_csrf_and_deletion(workflow):
    case = workflow
    job = collection_job(case)
    map_response = case.client.post(case.root + "/collection-maps", json={"request_id": "map", "collection_ref": case.collection["origin"]})
    map_response.raise_for_status()
    mapping = map_response.json()["job"]
    other = client_for(case.app)
    for path in ("/collection-preparation-jobs", "/collection-preparation-jobs/" + job["id"], "/collection-maps",
                 "/collection-map-jobs/" + mapping["id"]):
        assert other.get(case.root + path).status_code == 404
    assert other.post(case.root + "/collection-preparation-jobs/" + job["id"] + "/cancel", json={}).status_code == 404
    assert case.client.post(case.root + "/collection-preparation-jobs/" + job["id"] + "/cancel", json={},
        headers={"X-CSRF-Token": "incorrect"}).status_code == 403
    assert case.client.post(case.root + "/collection-maps", json={"request_id": "csrf", "collection_ref": case.collection["origin"]},
        headers={"X-CSRF-Token": "incorrect"}).status_code == 403
    assert case.client.delete(case.root).status_code == 200
    assert case.client.get(case.root + "/collection-preparation-jobs/" + job["id"]).status_code == 404
    assert case.client.get(case.root + "/collection-map-jobs/" + mapping["id"]).status_code == 404
    for store in (case.app.state.maps.store, case.app.state.collection_maps.store):
        with store.connection() as db:
            assert db.execute(f"SELECT COUNT(*) FROM {store.job_table} WHERE workspace_id=?", (case.root.rsplit("/", 1)[1],)).fetchone()[0] == 0


def test_collection_map_in_http_uses_explicit_origin_and_keeps_saved_map_hashes(workflow):
    case = workflow
    original_searches = case.client.get(case.root).json()["searches"]
    response = case.client.post(case.root + "/collection-maps", json={"request_id": "fit", "collection_ref": case.collection["origin"]})
    response.raise_for_status()
    job = response.json()["job"]
    assert case.app.state.map_worker.run_once()
    finished = case.client.get(case.root + "/collection-map-jobs/" + job["id"]).json()
    assert finished["status"] == "succeeded", finished
    url = case.root + "/collection-maps/" + finished["map_id"]
    mapped = case.client.get(url).json()
    assert mapped["artifact"]["collection_ref"] == case.collection["origin"]
    assert mapped["counts"]["provider_reported"] is None and mapped["counts"]["fetched_records"] is None
    assert len(case.embedder.calls) == 3 and len(mapped["artifact"]["coordinates_by_paper_id"]) == 3
    case.client.get(case.root + "/collections/" + case.collection["id"] + "/papers", params={"filter": "missing"}).raise_for_status()
    assert case.client.get(url).json() == mapped and len(case.embedder.calls) == 3
    assert case.client.get(case.root + "/maps/" + case.legacy_map["artifact"]["map_id"]).json() == case.legacy_map
    assert case.client.get(case.root).json()["searches"] == original_searches


def test_legacy_run_board_cells_and_exact_historical_citations_survive_collection_preparation(workflow):
    case = workflow
    old = case.client.post(case.root + "/source-preparations", json={"request_id": "legacy-prepare", "search_id": case.search["id"],
        "paper_ids": [case.search["papers"][0]["id"]]})
    old.raise_for_status()
    prepared = old.json()
    response = case.client.post(case.root + "/evidence-runs", json={"request_id": "legacy-run", "question": "gut microbiota microbiome",
        "top_k": 3, "expected_preparation_id": prepared["id"], "expected_source_revision": prepared["source_revision"]})
    response.raise_for_status()
    legacy_run = response.json()
    context_url = case.root + "/runs/" + legacy_run["id"] + "/passages/" + legacy_run["passages"][0]["id"] + "/context"
    original_context = case.client.get(context_url).json()
    board, view = make_board(case, prepared, "legacy-board")
    assert view["definition"]["schema_version"] == "mvp.board-definition.v1"
    candidates = case.client.post(board + "/candidates", json={"request_id": "legacy-candidate", "expected_revision_id": view["definition"]["revision_id"],
        "paper_id": prepared["selected_paper_ids"][0], "field_id": "microbiome", "top_k": 3})
    candidates.raise_for_status()
    reference = candidates.json()["candidates"][0]["reference"]
    case.client.get(board + "/references/" + reference["id"] + "/context").raise_for_status()
    legacy_range = {key: reference[key] for key in REFERENCE_KEYS}
    submitted = save_and_submit(case, board, view, prepared["selected_paper_ids"][0], "microbiome", {
        "value": "Legacy manual software record", "references": [legacy_range], "inspected_ranges": [legacy_range],
        "semantic_assessment": "unassessed"}, "legacy-submit")
    old_audit = case.client.get(board + "/exports", params={"format": "json", "history": True}).json()
    assert old_audit["schema_version"] == "mvp.board-audit.v1"
    finish_preparation(case, collection_job(case, "new-collection-prepare"))
    assert case.client.get(context_url).status_code == 409
    archived = case.client.get(context_url, params={"archived": True})
    archived.raise_for_status()
    for key in ("passage", "paper", "source", "block", "blocks"):
        assert archived.json()[key] == original_context[key]
    reopened_run = case.client.get(case.root + "/runs/" + legacy_run["id"])
    reopened_run.raise_for_status()
    assert reopened_run.json()["run"] == legacy_run and reopened_run.json()["current"] is False
    historical = case.client.get(board)
    historical.raise_for_status()
    assert historical.json()["freshness"] == "historical" and historical.json()["definition"] == view["definition"]
    old_heads = [cell["head"] for cell in historical.json()["cells"] if cell["head"]]
    assert [head["id"] for head in old_heads] == [submitted["id"]]
    inspected = case.client.get(board + "/references/" + reference["id"] + "/context")
    inspected.raise_for_status()
    assert inspected.json()["reference"] == reference and inspected.json()["freshness"] == "historical"
    exported = case.client.get(board + "/exports", params={"format": "json", "history": True})
    exported.raise_for_status()
    assert exported.json()["schema_version"] == "mvp.board-audit.v1"
    for key in ("definitions", "cell_revisions", "candidate_runs"):
        assert exported.json()[key] == old_audit[key]
