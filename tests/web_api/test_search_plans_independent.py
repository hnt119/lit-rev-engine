"""Independent localhost HTTP checks with synthetic discovery and XML/model mocks."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import socket
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.mvp.adapters.search_diagnostics import PubMedSearchDiagnostics
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.contracts import Paper, SearchPreview, WorkspaceHandle
from src.mvp.search_plan_contracts import CreateSearchPlanRequest, SearchPlanDraft, SearchPlanningCapability, SearchPlanningResult
from src.mvp.service import MVPService
from src.web_api.app import create_app

RAW = ' \r\n("gut microbiome"[tiab]) AND women[tiab]  \r\n'


class Discovery:
    def __init__(self):
        self.calls, self.block = [], False
        self.entered, self.release = threading.Event(), threading.Event()

    def search(self, request):
        self.calls.append(request)
        if self.block:
            self.entered.set()
            assert self.release.wait(timeout=6)
        return SearchPreview(query=request.query, date_from=request.date_from, date_to=request.date_to, sort=request.sort,
            papers=[Paper(pmid="111", title="SYNTHETIC HTTP search fixture", abstract="Fixture abstract.")],
            total_reported=10, fetched_count=1, ordered_identifiers=["111"], truncated=True,
            mode="live", provider="synthetic-no-live-call")

    def prepare(self, paper):
        raise AssertionError("Search-plan HTTP tests must not prepare sources")


class DiagnosticTransport:
    def __init__(self):
        self.calls, self.block = [], False
        self.entered, self.release = threading.Event(), threading.Event()

    def request(self, endpoint, params):
        self.calls.append((endpoint, dict(params)))
        assert endpoint == "pubmed_search"
        if self.block:
            self.entered.set()
            assert self.release.wait(timeout=6)
        return b"<eSearchResult><Count>10</Count><RetMax>1</RetMax><RetStart>0</RetStart><IdList><Id>111</Id></IdList><QueryTranslation>MOCK provider translation</QueryTranslation><WarningList><QuotedPhraseNotFound>fixture phrase</QuotedPhraseNotFound></WarningList></eSearchResult>"


class Planner:
    def __init__(self):
        self.calls, self.block = [], False
        self.entered, self.release = threading.Event(), threading.Event()

    def capability(self):
        return SearchPlanningCapability(enabled=True, model_profile={"model": "MOCK HTTP fixture", "revision": "1"})

    def propose(self, question, **kwargs):
        self.calls.append((question, kwargs))
        if self.block:
            self.entered.set()
            assert self.release.wait(timeout=6)
        return SearchPlanningResult(draft=SearchPlanDraft(original_question=question),
            question_sha256=sha256(question.encode()).hexdigest(), model_profile=self.capability().model_profile,
            response_sha256="d" * 64, elapsed_seconds=.001)


def browser(app):
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    csrf = client.get("/api/v1/session").json()["csrf_token"]
    client.headers.update({"Origin": "http://127.0.0.1:3000", "X-CSRF-Token": csrf})
    return client


@pytest.fixture
def case(tmp_path, monkeypatch):
    monkeypatch.setenv("MVP_MAP_ENABLED", "0")
    monkeypatch.setenv("MVP_PROPOSALS_ENABLED", "0")
    monkeypatch.setenv("MVP_SEARCH_PLANNER_ENABLED", "0")
    monkeypatch.delenv("NCBI_EMAIL", raising=False)
    def denied(*args, **kwargs):
        pytest.fail("Search-plan HTTP test attempted an external provider call")
    monkeypatch.setattr(socket, "create_connection", denied)
    provider, transport, planner = Discovery(), DiagnosticTransport(), Planner()
    engine = MVPService(SQLiteWorkspaceStorage(tmp_path / "research.sqlite3"), provider, provider)
    diagnostics = PubMedSearchDiagnostics(email="fixture@example.org", transport=transport)
    app = create_app(tmp_path, services={"live": engine, "saved_example": engine}, search_diagnostics=diagnostics, search_planner=planner)
    client = browser(app)
    made = client.post("/api/v1/workspaces", json={"request_id": "workspace", "mode": "live"})
    made.raise_for_status()
    return SimpleNamespace(path=tmp_path, app=app, client=client, root="/api/v1/workspaces/" + made.json()["id"],
        engine=engine, provider=provider, transport=transport, planner=planner, diagnostics=diagnostics)


def create(case, key="create", raw=RAW):
    response = case.client.post(case.root + "/search-plans", json={"request_id": key, "draft": {
        "original_question": "Human-authored question about women originating from Asia", "input_mode": "manual_strategy",
        "manual_strategy": raw, "date_filter": {"date_from": "2010-01-01", "date_to": "2025-12-31"}, "sort": "pub_date"}})
    response.raise_for_status()
    return response.json()


def route(case, view):
    return case.root + "/search-plans/" + view["revision"]["plan_id"]


def candidate(view, key):
    revision = view["revision"]
    value = revision["compiled"]["candidates"][0]
    return {"request_id": key, "expected_revision_id": revision["revision_id"], "candidate_id": value["id"], "candidate_sha256": value["candidate_sha256"]}


def update(case, view, key="update"):
    draft = {**view["revision"]["draft"], "manual_strategy": RAW + " AND diet[tiab]"}
    response = case.client.put(route(case, view), json={"request_id": key, "expected_revision_id": view["revision"]["revision_id"], "draft": draft})
    response.raise_for_status()
    return response.json()


def test_complete_explicit_workflow_reopens_and_exports_planning_provenance(case):
    legacy = case.client.get(case.root + "/exports", params={"format": "json"})
    legacy.raise_for_status()
    assert legacy.json()["schema_version"] == "mvp.audit-bundle.v1"
    view = create(case)
    path = route(case, view)
    assert view["revision"]["draft"]["manual_strategy"].encode() == RAW.encode()
    assert create(case) == view
    incomplete = case.client.post(path + "/approve", json=candidate(view, "incomplete"))
    assert incomplete.status_code == 422 and incomplete.json()["error"]["code"] == "search_approval_incomplete"
    approval = case.client.post(path + "/approve", json={**candidate(view, "approve"), "acknowledge_unparsed_strategy": True})
    approval.raise_for_status()
    assert approval.json()["meaning"] == "researcher_intent_approval_not_mesh_validation"
    checked = case.client.post(path + "/diagnose", json=candidate(view, "diagnose"))
    checked.raise_for_status()
    receipt = checked.json()["receipt"]
    assert receipt["query"] == RAW and receipt["reported_count"] == 10 and receipt["query_translation"] == "MOCK provider translation"
    assert receipt["messages"][0]["code"] == "QuotedPhraseNotFound" and receipt["meaning"] == "diagnostic_not_capture_relevance_or_recall"
    assert case.provider.calls == []
    proposed = case.client.post(path + "/propose", json={"request_id": "propose", "expected_revision_id": view["revision"]["revision_id"],
        "original_question": view["revision"]["draft"]["original_question"]})
    proposed.raise_for_status()
    assert case.client.get(path).json()["revision"] == view["revision"]
    request = {**candidate(view, "execute"), "approval_id": approval.json()["id"], "max_results": 30}
    executed = case.client.post(path + "/execute", json=request)
    executed.raise_for_status()
    assert case.client.post(path + "/execute", json=request).json() == executed.json() and len(case.provider.calls) == 1
    assert case.provider.calls[0].query == RAW and case.provider.calls[0].sort == "pub_date"
    reopened_app = create_app(case.path, services={"live": case.engine}, search_diagnostics=case.diagnostics, search_planner=case.planner)
    reopened = TestClient(reopened_app, base_url="http://127.0.0.1:8765")
    reopened.cookies.update(case.client.cookies)
    saved = reopened.get(path)
    saved.raise_for_status()
    assert saved.json()["revision"] == view["revision"] and len(saved.json()["executions"]) == len(saved.json()["proposals"]) == 1
    exported = reopened.get(case.root + "/exports", params={"format": "json"})
    exported.raise_for_status()
    audit = exported.json()
    assert audit["schema_version"] == "mvp.research-input-audit-bundle.v3"
    planning = audit["search_planning"]
    assert planning["schema_version"] == "mvp.search-planning-audit.v2"
    assert planning["plans"][0]["revisions"][0]["draft"]["manual_strategy"] == RAW
    assert {item["kind"] for item in planning["plans"][0]["receipts"]} == {"approval", "diagnostic", "proposal", "execution"}
    assert all(operation["status"] == "succeeded" for operation in planning["operations"])
    assert all(private not in exported.text for private in ['"token"', '"csrf"'])
    assert reopened.get(case.root + "/exports", params={"format": "csv"}).status_code == 200


def test_reads_edits_imports_and_invalid_requests_never_trigger_provider_or_model(case):
    view = create(case)
    path = route(case, view)
    for url in [case.root, case.root + "/search-plans", path, case.root + "/search-plan-capabilities", "/api/v1/capabilities"]:
        assert case.client.get(url).status_code == 200
    edited = update(case, view)
    assert edited["revision"]["revision"] == 2
    imported = case.client.post(case.root + "/imports/identifiers", content=b"doi:10.1234/explicit-upload\n",
        headers={"Content-Type": "application/octet-stream", "X-Request-ID": "upload"})
    imported.raise_for_status()
    assert imported.json()["pending_count"] == 1
    invalid = case.client.post(case.root + "/search-plans", json={"request_id": "invalid", "draft": {"original_question": "question", "unrecognized": "field"}})
    assert invalid.status_code == 422
    assert case.provider.calls == case.transport.calls == case.planner.calls == []


def test_session_csrf_cross_workspace_and_json_boundary_apply_to_every_planning_action(case):
    view = create(case)
    path = route(case, view)
    other = browser(case.app)
    assert other.get(path).status_code == 404
    for action in ["approve", "diagnose", "execute", "propose"]:
        body = candidate(view, "unauthorized-" + action)
        if action == "execute": body["approval_id"] = "unavailable"
        if action == "propose": body = {"request_id": "unauthorized", "expected_revision_id": view["revision"]["revision_id"], "original_question": view["revision"]["draft"]["original_question"]}
        assert other.post(path + "/" + action, json=body).status_code == 404
        assert case.client.post(path + "/" + action, json=body, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    made = case.client.post("/api/v1/workspaces", json={"request_id": "second", "mode": "live"})
    made.raise_for_status()
    assert case.client.get("/api/v1/workspaces/" + made.json()["id"] + "/search-plans/" + view["revision"]["plan_id"]).status_code == 404
    oversized = case.client.post(case.root + "/search-plans", content=json.dumps({"padding": "x" * (1024 * 1024)}), headers={"Content-Type": "application/json"})
    assert oversized.status_code == 413 and case.provider.calls == case.transport.calls == case.planner.calls == []


def test_revision_candidate_and_approval_cas_and_request_id_conflicts_are_http_conflicts(case):
    view = create(case)
    path = route(case, view)
    approved = case.client.post(path + "/approve", json={**candidate(view, "approve"), "acknowledge_unparsed_strategy": True})
    approved.raise_for_status()
    edited = update(case, view)
    stale = case.client.put(path, json={"request_id": "stale", "expected_revision_id": view["revision"]["revision_id"], "draft": view["revision"]["draft"]})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "stale_search_plan"
    mismatch = case.client.post(path + "/diagnose", json={**candidate(edited, "mismatch"), "candidate_sha256": "0" * 64})
    assert mismatch.status_code == 409 and mismatch.json()["error"]["code"] == "stale_search_candidate"
    invalid_approval = case.client.post(path + "/execute", json={**candidate(edited, "execute"), "approval_id": approved.json()["id"]})
    assert invalid_approval.status_code == 409 and invalid_approval.json()["error"]["code"] == "stale_search_approval"
    conflicting = case.client.post(case.root + "/search-plans", json={"request_id": "create", "draft": {**view["revision"]["draft"], "manual_strategy": RAW + " "}})
    assert conflicting.status_code == 409 and case.provider.calls == case.transport.calls == case.planner.calls == []


@pytest.mark.parametrize("action", ["edit", "delete"])
def test_late_http_diagnostic_cannot_publish_after_editor_revision_or_deletion(case, action):
    view = create(case)
    path = route(case, view)
    case.transport.block = True
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(case.client.post, path + "/diagnose", json=candidate(view, "slow"))
        assert case.transport.entered.wait(timeout=2)
        try:
            if action == "edit":
                edited = pool.submit(update, case, view).result(timeout=1)
                assert edited["revision"]["revision"] == 2
            else:
                assert pool.submit(case.client.delete, case.root).result(timeout=1).status_code == 200
        finally:
            case.transport.release.set()
        result = pending.result(timeout=3)
    assert result.status_code == (409 if action == "edit" else 404), result.text
    if action == "edit":
        assert case.client.get(path).json()["diagnostics"] == []
    else:
        assert case.client.get(path).status_code == 404
    assert len(case.transport.calls) == 1 and case.provider.calls == []


def test_inflight_http_idempotency_is_reserved_before_diagnostic_transport(case):
    view = create(case)
    path, request = route(case, view) + "/diagnose", candidate(view, "slow")
    case.transport.block = True
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(case.client.post, path, json=request)
        assert case.transport.entered.wait(timeout=2)
        try:
            duplicate = pool.submit(case.client.post, path, json=request).result(timeout=1)
            assert duplicate.status_code == 503 and duplicate.json()["error"]["code"] == "search_plan_call_pending"
            assert len(case.transport.calls) == 1
        finally:
            case.transport.release.set()
        result = pending.result(timeout=3)
    result.raise_for_status()
    replay = case.client.post(path, json=request)
    assert replay.json() == result.json() and len(case.transport.calls) == 1


def tombstone_without_clearing_research(case):
    registry = case.app.state.registry
    workspace_id = case.root.rsplit("/", 1)[-1]
    with registry.lifecycle_guard(workspace_id), registry.connection() as db:
        db.execute("INSERT INTO web_tombstones(workspace_id,deleted_at) VALUES(?,?)", (workspace_id, "2026-10-22T00:00:00+00:00"))


@pytest.mark.parametrize("kind", ["diagnose", "propose", "execute"])
def test_interrupted_delete_tombstone_blocks_captured_handle_late_publication(case, kind):
    view = create(case)
    path = route(case, view)
    request = candidate(view, "tombstoned-call")
    target = case.transport if kind == "diagnose" else case.planner if kind == "propose" else case.provider
    if kind == "propose":
        request = {"request_id": "tombstoned-call", "expected_revision_id": view["revision"]["revision_id"],
            "original_question": view["revision"]["draft"]["original_question"]}
    if kind == "execute":
        approval = case.client.post(path + "/approve", json={**candidate(view, "approve"), "acknowledge_unparsed_strategy": True})
        approval.raise_for_status()
        request["approval_id"] = approval.json()["id"]
    with case.engine._storage._connection() as db:
        before = db.execute("SELECT snapshot FROM mvp_workspaces").fetchone()[0]
    target.block = True
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(case.client.post, path + "/" + kind, json=request)
        assert target.entered.wait(timeout=2)
        try:
            pool.submit(tombstone_without_clearing_research, case).result(timeout=1)
        finally:
            target.release.set()
        response = pending.result(timeout=3)
    assert response.status_code == 404 and response.json()["error"]["code"] == "workspace_access_denied", response.text
    with case.engine._storage._connection() as db:
        assert db.execute("SELECT snapshot FROM mvp_workspaces").fetchone()[0] == before
        assert db.execute("SELECT COUNT(*) FROM mvp_search_plan_events WHERE kind IN ('diagnostic','proposal','execution')").fetchone()[0] == 0
    assert len(target.calls) == 1 and case.client.get(path).status_code == 404


def test_cached_domain_service_handle_cannot_create_after_interrupted_delete(case):
    view = create(case)
    registry = case.app.state.registry
    with registry.connection() as db:
        row = db.execute("SELECT workspace_id,capability FROM web_workspaces").fetchone()
        handle = WorkspaceHandle(workspace_id=row["workspace_id"], token=row["capability"])
    service = case.app.state.search_plans_for("live")
    tombstone_without_clearing_research(case)
    from src.mvp.ports import MvpError
    with pytest.raises(MvpError) as deleted:
        service.create(handle, CreateSearchPlanRequest(request_id="captured-before-delete", draft=SearchPlanDraft.model_validate(view["revision"]["draft"])))
    assert deleted.value.code == "workspace_access_denied"
    with case.engine._storage._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM mvp_workspaces").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM mvp_search_plans").fetchone()[0] == 1
