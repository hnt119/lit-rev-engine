"""Independent board HTTP boundary checks; public offline sources only.

These exercise authorization, persistence and mechanical state transitions. They
do not execute PubMed, an embedding model, extraction or usefulness assessment.
"""
import json
import socket

import pytest
from fastapi.testclient import TestClient

from src.web_api.app import COOKIE_NAME, create_app

BASE = "http://127.0.0.1:8765"
ORIGIN = "http://127.0.0.1:3000"
P = "/api/v1"


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Independent board HTTP check attempted network access")
    monkeypatch.setattr(socket, "create_connection", denied)


@pytest.fixture
def board_api(tmp_path):
    app = create_app(tmp_path)
    client = TestClient(app, base_url=BASE)
    session = client.get(P + "/session").json()
    client.headers.update({"Origin": ORIGIN, "X-CSRF-Token": session["csrf_token"]})
    workspace = client.post(P + "/workspaces", json={"request_id": "board-workspace",
        "mode": "saved_example", "question": "SYNTHETIC SOFTWARE INSPECTION QUESTION"}).json()
    root = f'{P}/workspaces/{workspace["id"]}'
    search = client.post(root + "/searches", json={"request_id": "search", "query": "saved public example",
                                                   "max_results": 30}).json()
    prep_response = client.post(root + "/source-preparations", json={"request_id": "prepare",
        "search_id": search["id"], "paper_ids": [paper["id"] for paper in search["papers"][:3]]})
    assert prep_response.status_code == 200, prep_response.text
    prep = prep_response.json()
    request = {"request_id": "board", "question": "SYNTHETIC board question",
        "preparation_id": prep["id"], "paper_ids": prep["selected_paper_ids"], "fields": [
            {"id": "population", "label": "Population", "subquestion": "women population"},
            {"id": "diet", "label": "Diet", "subquestion": "diet food questionnaire"},
            {"id": "fertility", "label": "Fertility", "subquestion": "fertility ovarian reserve"}]}
    response = client.post(root + "/boards", json=request)
    assert response.status_code == 200, response.text
    view = response.json()
    board = root + "/boards/" + view["definition"]["board_id"]
    return app, client, root, board, view, prep, request


def _draft_request(view, *, value="SYNTHETIC unsent human text", version=0, head=None):
    return {"expected_revision_id": view["definition"]["revision_id"], "version": version,
            "expected_cell_head_id": head, "data": {"value": value}}


def _candidate_request(view, request_id="candidates"):
    return {"request_id": request_id, "expected_revision_id": view["definition"]["revision_id"],
        "paper_id": view["definition"]["paper_ids"][0], "field_id": "population", "top_k": 3}


def test_board_routes_do_not_expose_another_sessions_data(board_api):
    app, first, root, board, view, prep, request = board_api
    candidate = first.post(board + "/candidates", json=_candidate_request(view))
    assert candidate.status_code == 200, candidate.text
    reference = candidate.json()["candidates"][0]["reference"]
    other = TestClient(app, base_url=BASE)
    csrf = other.get(P + "/session").json()["csrf_token"]
    other.headers.update({"Origin": ORIGIN, "X-CSRF-Token": csrf})
    paper = view["definition"]["paper_ids"][0]
    draft = board + f"/drafts/{paper}/population"
    for path in [root + "/boards", board, draft,
                 board + f"/cells/{paper}/population/history",
                 board + f'/sources/{prep["sources"][0]["id"]}/blocks',
                 board + f'/references/{reference["id"]}/context', board + "/exports?format=json"]:
        result = other.get(path)
        assert result.status_code == 404, (path, result.text)
    for path, body in [(root + "/boards", request), (board + "/candidates", _candidate_request(view)),
                       (board + "/revisions", {**request, "request_id": "revised",
                        "expected_revision_id": view["definition"]["revision_id"]}),
                       (board + "/cell-revisions", {"request_id": "s", "paper_id": paper,
                        "field_id": "population", "expected_revision_id": view["definition"]["revision_id"],
                        "draft_version": 1})]:
        assert other.post(path, json=body).status_code == 404, path
    assert other.put(draft, json=_draft_request(view)).status_code == 404
    assert first.get(board).json() == view


@pytest.mark.parametrize("missing", ["Origin", "X-CSRF-Token"])
def test_board_writes_require_existing_exact_origin_and_csrf(board_api, missing):
    _, client, root, board, view, _, request = board_api
    paper = view["definition"]["paper_ids"][0]
    client.headers.pop(missing)
    for path, body in [(root + "/boards", {**request, "request_id": "other"}),
                       (board + "/candidates", _candidate_request(view)),
                       (board + "/revisions", {**request, "request_id": "r",
                        "expected_revision_id": view["definition"]["revision_id"]}),
                       (board + "/cell-revisions", {"request_id": "s", "paper_id": paper,
                        "field_id": "population", "expected_revision_id": view["definition"]["revision_id"],
                        "draft_version": 1})]:
        assert client.post(path, json=body).status_code == 403, path
    assert client.put(board + f"/drafts/{paper}/population", json=_draft_request(view)).status_code == 403


def test_gets_are_read_only_and_compact_then_draft_submission_reopens(board_api, tmp_path):
    app, client, root, board, view, prep, request = board_api
    legacy_before = client.get(root + "/exports?format=json").json()
    with app.state.boards.store.connection() as db:
        before_counts = {table: db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
            for table in ("board_candidates", "board_cells", "board_drafts", "board_requests")}
    paper = view["definition"]["paper_ids"][0]
    draft_path = board + f"/drafts/{paper}/population"
    for _ in range(2):
        assert client.get(board).json() == view
        assert client.get(root + "/boards").json()["boards"]
        assert client.get(draft_path).json()["version"] == 0
        assert client.get(board + f"/cells/{paper}/population/history").json()["total"] == 0
        inspection = client.get(board + f'/sources/{prep["sources"][0]["id"]}/blocks?limit=1')
        assert inspection.status_code == 200, inspection.text
        assert len(inspection.json()["blocks"]) == 1
    with app.state.boards.store.connection() as db:
        assert before_counts == {table: db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                                  for table in before_counts}
    encoded = json.dumps(view)
    assert "retained_content_utf8" not in encoded and '"blocks"' not in encoded
    assert "web_sessions" not in encoded and "csrf_token" not in encoded
    saved = client.put(draft_path, json=_draft_request(view))
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == 1
    assert client.put(draft_path, json=_draft_request(view, value="Stale overwrite")).status_code == 409
    assert client.get(draft_path).json()["data"]["value"] == "SYNTHETIC unsent human text"
    submitted_request = {"request_id": "submit", "expected_revision_id": view["definition"]["revision_id"],
        "paper_id": paper, "field_id": "population", "draft_version": 1}
    submitted = client.post(board + "/cell-revisions", json=submitted_request)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["semantic_assessment"] == "unassessed"
    assert client.post(board + "/cell-revisions", json=submitted_request).json() == submitted.json()
    legacy_after = client.get(root + "/exports?format=json").json()
    assert {key: value for key, value in legacy_after.items() if key != "exported_at"} == {
        key: value for key, value in legacy_before.items() if key != "exported_at"}
    restarted = TestClient(create_app(tmp_path), base_url=BASE)
    restarted.cookies.set(COOKIE_NAME, client.cookies.get(COOKIE_NAME))
    restarted.get(P + "/session").raise_for_status()
    reopened = restarted.get(board)
    assert reopened.status_code == 200
    heads = [cell["head"] for cell in reopened.json()["cells"] if cell["head"]]
    assert len(heads) == 1
    assert heads[0]["id"] == submitted.json()["id"]
    assert heads[0]["value"] == submitted.json()["value"]
    assert heads[0]["semantic_assessment"] == "unassessed"
    history = restarted.get(board + f"/cells/{paper}/population/history").json()
    assert history["items"] == [submitted.json()]
    exported = restarted.get(board + "/exports?format=json&history=true")
    assert exported.status_code == 200
    assert exported.json()["schema_version"] == "mvp.board-audit.v1"
    assert "attachment" in exported.headers["content-disposition"]


def test_deleted_board_rejects_late_http_writes_and_remains_tombstoned(board_api):
    app, client, root, board, view, _, request = board_api
    paper = view["definition"]["paper_ids"][0]
    draft = board + f"/drafts/{paper}/population"
    assert client.put(draft, json=_draft_request(view)).status_code == 200
    assert client.delete(root).status_code == 200
    assert client.get(board).status_code == 404
    assert client.put(draft, json=_draft_request(view, version=1)).status_code == 404
    assert client.post(root + "/boards", json={**request, "request_id": "late"}).status_code == 404
    assert client.post(board + "/candidates", json=_candidate_request(view)).status_code == 404
    with app.state.boards.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM evidence_boards").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM board_drafts").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM board_deleted").fetchone()[0] == 1


def test_interrupted_sidecar_cleanup_stays_inaccessible_and_explicit_delete_retry_finishes(board_api, monkeypatch):
    app, client, root, board, view, _, _ = board_api
    original = app.state.boards.delete_workspace
    def interrupted(identifier):
        raise RuntimeError("SYNTHETIC interruption before board-sidecar cleanup")
    monkeypatch.setattr(app.state.boards, "delete_workspace", interrupted)
    with pytest.raises(RuntimeError, match="SYNTHETIC interruption"):
        client.delete(root)
    assert client.get(board).status_code == 404
    assert client.post(board + "/candidates", json=_candidate_request(view)).status_code == 404
    with app.state.boards.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM evidence_boards").fetchone()[0] == 1
    monkeypatch.setattr(app.state.boards, "delete_workspace", original)
    assert client.delete(root).status_code == 200
    assert client.delete(root).status_code == 200
    with app.state.boards.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM evidence_boards").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM board_deleted").fetchone()[0] == 1
