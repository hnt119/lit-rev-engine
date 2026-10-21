"""Independent proposal HTTP boundaries with a mock and public offline sources.

No model, provider, cloud endpoint or scientific usefulness validation occurs.
"""
import json
import socket

from fastapi.testclient import TestClient
import pytest

from src.mvp.proposal_contracts import ProposalGenerationResult, ProposalUsage
from src.web_api.app import COOKIE_NAME, create_app

BASE, ORIGIN, P = "http://127.0.0.1:8765", "http://127.0.0.1:3000", "/api/v1"


class HttpMockGenerator:
    enabled = True
    profile = {"provider": "synthetic-http-mock", "model": "mock", "revision": "v1"}

    def __init__(self):
        self.calls = []

    def generate(self, packet, *, timeout_seconds):
        self.calls.append(packet)
        by_id = {item.evidence_id: item for item in packet.evidence}
        cells = []
        for field in packet.fields:
            identifier = field.evidence_ids[0] if field.evidence_ids else None
            cells.append({"field_id": field.field_id,
                "value": "SYNTHETIC proposal requires review" if identifier else None,
                "references": [{"evidence_id": identifier, "quote": by_id[identifier].reference.quote}]
                    if identifier else [],
                "reason": "Mock-only software result; no entailment assertion",
                "missing_information": "Not supplied in retrieved context" if not identifier else "",
                "context_scope": "retrieved_context_only"})
        return ProposalGenerationResult(output_text=json.dumps({"cells": cells}),
            usage=ProposalUsage(input_tokens=10, output_tokens=10, total_tokens=20, measured=True))


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Independent proposal HTTP check attempted network access")
    monkeypatch.setattr(socket, "create_connection", denied)


@pytest.fixture
def proposal_api(tmp_path):
    adapter = HttpMockGenerator()
    app = create_app(tmp_path, proposal_adapter=adapter)
    client = TestClient(app, base_url=BASE)
    session = client.get(P + "/session").json()
    client.headers.update({"Origin": ORIGIN, "X-CSRF-Token": session["csrf_token"]})
    workspace_response = client.post(P + "/workspaces", json={"request_id": "workspace",
        "mode": "saved_example", "question": "SYNTHETIC public source software example"})
    assert workspace_response.status_code == 200, workspace_response.text
    root = f'{P}/workspaces/{workspace_response.json()["id"]}'
    search = client.post(root + "/searches", json={"request_id": "search", "query": "saved example",
                                                   "max_results": 30}).json()
    prep = client.post(root + "/source-preparations", json={"request_id": "prepare", "search_id": search["id"],
        "paper_ids": [paper["id"] for paper in search["papers"][:3]]}).json()
    response = client.post(root + "/boards", json={"request_id": "board", "preparation_id": prep["id"],
        "question": "SYNTHETIC software question", "paper_ids": prep["selected_paper_ids"],
        "fields": [{"id": "population", "label": "Population", "subquestion": "women population microbiome"}]})
    assert response.status_code == 200, response.text
    view = response.json()
    board = root + "/boards/" + view["definition"]["board_id"]
    request = {"request_id": "proposal-run", "expected_revision_id": view["definition"]["revision_id"],
        "paper_ids": view["definition"]["paper_ids"][:1], "field_ids": ["population"]}
    return app, client, root, board, view, adapter, request


def _run(case):
    _, client, _, board, _, _, request = case
    response = client.post(board + "/proposal-runs", json=request)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["state"] == "succeeded", result
    return result


def test_generation_is_disabled_in_unconfigured_app_and_no_read_calls_adapter(proposal_api, tmp_path):
    app, client, root, board, view, adapter, request = proposal_api
    revision = view["definition"]["revision_id"]
    for path in [board + "/proposal-capabilities", board + f"/proposals?revision_id={revision}",
                 board + f"/proposal-audit?revision_id={revision}"]:
        assert client.get(path).status_code == 200
    assert adapter.calls == []
    disabled = TestClient(create_app(tmp_path), base_url=BASE)
    disabled.cookies.set(COOKIE_NAME, client.cookies.get(COOKIE_NAME))
    session = disabled.get(P + "/session").json()
    disabled.headers.update({"Origin": ORIGIN, "X-CSRF-Token": session["csrf_token"]})
    capability = disabled.get(board + "/proposal-capabilities").json()
    assert capability["enabled"] is False and capability["paid_calls"] is False
    assert disabled.post(board + "/proposal-runs", json=request).status_code == 422
    assert adapter.calls == []


def test_proposal_resources_keep_session_ownership_boundary(proposal_api):
    app, client, root, board, view, adapter, request = proposal_api
    run = _run(proposal_api)
    proposal = run["proposals"][0]
    other = TestClient(app, base_url=BASE)
    csrf = other.get(P + "/session").json()["csrf_token"]
    other.headers.update({"Origin": ORIGIN, "X-CSRF-Token": csrf})
    revision = view["definition"]["revision_id"]
    paths = [board + "/proposal-capabilities", board + "/proposal-runs/" + run["id"],
             board + f"/proposals?revision_id={revision}", board + f"/proposal-audit?revision_id={revision}"]
    if proposal["references"]:
        paths.append(board + f'/proposals/{proposal["id"]}/references/{proposal["references"][0]["id"]}/context')
    for path in paths:
        assert other.get(path).status_code == 404, path
    for path, body in [(board + "/proposal-runs", request),
        (board + f'/proposals/{proposal["id"]}/dismiss', {"request_id": "dismiss", "expected_revision_id": revision}),
        (board + f'/proposals/{proposal["id"]}/adopt', {"request_id": "adopt", "expected_revision_id": revision,
            "draft_version": 0, "value": "Edited value", "reason": "Software check"})]:
        assert other.post(path, json=body).status_code == 404, path
    assert len(adapter.calls) == 1


@pytest.mark.parametrize("header", ["Origin", "X-CSRF-Token"])
def test_generation_adopt_dismiss_require_origin_and_csrf(proposal_api, header):
    app, client, root, board, view, adapter, request = proposal_api
    run = _run(proposal_api)
    proposal = run["proposals"][0]
    revision = view["definition"]["revision_id"]
    client.headers.pop(header)
    for path, body in [(board + "/proposal-runs", {**request, "request_id": "other-run"}),
        (board + f'/proposals/{proposal["id"]}/dismiss', {"request_id": "dismiss", "expected_revision_id": revision}),
        (board + f'/proposals/{proposal["id"]}/adopt', {"request_id": "adopt", "expected_revision_id": revision,
            "draft_version": 0, "value": "Edited value", "reason": "Software check"})]:
        assert client.post(path, json=body).status_code == 403, path
    assert len(adapter.calls) == 1


def test_reviewable_proposal_survives_restart_and_cannot_submit_without_manual_inspection(proposal_api, tmp_path):
    app, client, root, board, view, adapter, request = proposal_api
    original_export = client.get(root + "/exports?format=json").json()
    run = _run(proposal_api)
    assert len(adapter.calls) == 1
    assert client.post(board + "/proposal-runs", json=request).json() == run
    assert len(adapter.calls) == 1
    proposal = run["proposals"][0]
    assert proposal["references"], "The public source fixture must yield retained candidates"
    reference = proposal["references"][0]
    exact = client.get(board + f'/proposals/{proposal["id"]}/references/{reference["id"]}/context')
    assert exact.status_code == 200 and exact.json()["reference"] == reference
    path = board + f'/proposals/{proposal["id"]}/adopt'
    adopt_request = {"request_id": "adopt", "expected_revision_id": view["definition"]["revision_id"],
        "draft_version": 0, "value": "SYNTHETIC edited suggestion", "reason": "Software walkthrough; needs human review"}
    # The model/client cannot claim inspection or support through adoption.
    assert client.post(path, json={**adopt_request, "semantic_assessment": "human_supported"}).status_code == 422
    adopted = client.post(path, json=adopt_request)
    assert adopted.status_code == 200, adopted.text
    draft = adopted.json()
    assert draft["data"]["semantic_assessment"] == "unassessed"
    assert draft["data"]["inspected_ranges"] == [] and draft["data"]["scope_result"] == "not_assessed"
    submitted = client.post(board + "/cell-revisions", json={"request_id": "cannot-submit",
        "expected_revision_id": draft["board_revision_id"], "paper_id": draft["paper_id"],
        "field_id": draft["field_id"], "draft_version": draft["version"]})
    assert submitted.status_code == 422
    restarted = TestClient(create_app(tmp_path), base_url=BASE)
    restarted.cookies.set(COOKIE_NAME, client.cookies.get(COOKIE_NAME))
    assert restarted.get(P + "/session").status_code == 200
    listing = restarted.get(board + "/proposals?revision_id=" + draft["board_revision_id"])
    assert listing.status_code == 200 and listing.json()["items"][0]["status"] == "adopted"
    assert restarted.get(board + f'/drafts/{draft["paper_id"]}/{draft["field_id"]}').json() == draft
    audit = restarted.get(board + "/proposal-audit?revision_id=" + draft["board_revision_id"])
    assert audit.status_code == 200 and audit.json()["schema_version"] == "mvp.proposal-audit.v1"
    assert "attachment" in audit.headers["content-disposition"]
    assert restarted.get(board).json()["cells"][0]["head"] is None
    after_export = restarted.get(root + "/exports?format=json").json()
    assert {k: v for k, v in after_export.items() if k != "exported_at"} == {
        k: v for k, v in original_export.items() if k != "exported_at"}


def test_deleted_workspace_clears_proposal_state_and_rejects_replay(proposal_api):
    app, client, root, board, view, adapter, request = proposal_api
    run = _run(proposal_api)
    assert client.delete(root).status_code == 200
    assert client.get(board + "/proposal-runs/" + run["id"]).status_code == 404
    assert client.post(board + "/proposal-runs", json=request).status_code == 404
    with app.state.boards.store.connection() as db:
        for table in ("proposal_runs", "cell_proposals", "proposal_events", "proposal_actions"):
            assert db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0
    assert len(adapter.calls) == 1
