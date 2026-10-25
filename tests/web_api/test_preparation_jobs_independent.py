"""Independent preparation HTTP contracts; mocked sources, real local stores."""
from concurrent.futures import ThreadPoolExecutor
import json
import socket
import threading

import pytest
from fastapi.testclient import TestClient

from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.contracts import Block, Paper, PreparedSource, SearchPreview
from src.mvp.service import MVPService
from src.web_api.app import COOKIE_NAME, create_app


class SyntheticProvider:
    def __init__(self):
        self.papers = [Paper(pmid=str(710000 + index), title=f"SOFTWARE HTTP JOB RECORD {index}",
            abstract=f"SOFTWARE_RETAINED_BODY_SENTINEL_{index} synthetic microbiome evidence.") for index in range(31)]
        self.calls, self.block = [], False
        self.entered, self.release = threading.Event(), threading.Event()

    def search(self, request):
        return SearchPreview(query=request.query, papers=self.papers, total_reported=31, fetched_count=31,
            ordered_identifiers=[paper.id for paper in self.papers], truncated=False, mode="test", provider="synthetic-http-job")

    def prepare(self, paper):
        self.calls.append(paper.id)
        if self.block and len(self.calls) == 1:
            self.entered.set()
            assert self.release.wait(timeout=8)
        return PreparedSource(paper_id=paper.id, status="abstract_only", source_type="abstract",
            provider="synthetic-http-job", source_url="", blocks=[Block(id="abstract:1", ordinal=1,
                text=paper.abstract, locator={"type": "abstract"})])


@pytest.fixture
def http_case(tmp_path, monkeypatch):
    monkeypatch.setenv("MVP_MAP_ENABLED", "0")
    monkeypatch.setenv("MVP_PROPOSALS_ENABLED", "0")
    monkeypatch.delenv("NCBI_EMAIL", raising=False)
    def denied(*args, **kwargs):
        pytest.fail("Preparation HTTP tests attempted provider network access")
    monkeypatch.setattr(socket, "create_connection", denied)
    provider = SyntheticProvider()
    engine = MVPService(SQLiteWorkspaceStorage(tmp_path / "research.sqlite3"), provider, provider)
    app = create_app(tmp_path, services={"saved_example": engine})
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    csrf = client.get("/api/v1/session").json()["csrf_token"]
    client.headers.update({"Origin": "http://127.0.0.1:3000", "X-CSRF-Token": csrf})
    created = client.post("/api/v1/workspaces", json={"request_id": "workspace", "mode": "saved_example"})
    created.raise_for_status()
    root = "/api/v1/workspaces/" + created.json()["id"]
    searched = client.post(root + "/searches", json={"request_id": "search", "query": "synthetic", "max_results": 50})
    searched.raise_for_status()
    return app, client, root, searched.json(), provider, engine, tmp_path


def payload(search, count=3, key="job"):
    return {"request_id": key, "search_id": search["id"], "paper_ids": [paper["id"] for paper in search["papers"][:count]],
        "expected_source_revision": 0, "expected_preparation_id": None}


@pytest.mark.parametrize("count", [1, 10, 11, 29, 30])
def test_http_durable_job_accepts_thirty_and_publishes_only_after_worker(http_case, count):
    app, client, root, search, provider, _, _ = http_case
    before = client.get(root).json()
    submitted = client.post(root + "/preparation-jobs", json=payload(search, count))
    assert submitted.status_code == 202, submitted.text
    job = submitted.json()["job"]
    assert job["status"] == "queued" and job["progress_total"] == count
    assert client.get(root).json() == before
    assert provider.calls == []
    assert client.get("/api/v1/capabilities").json()["preparation_jobs_ready"] is False, "This fixture deliberately drives the worker without application lifespan"
    assert app.state.preparation_worker.run_once()
    finished = client.get(root + "/preparation-jobs/" + job["id"])
    assert finished.status_code == 200, finished.text
    result = finished.json()
    assert result["status"] == "succeeded" and result["progress_completed"] == count
    summary = client.get(root).json()
    assert summary["current_preparation_id"] == result["result_preparation_id"]
    assert summary["source_revision"] == result["result_source_revision"] == 1
    assert provider.calls == payload(search, count)["paper_ids"]
    for projected in (result, client.get(root + "/preparation-jobs").json()):
        serialized = json.dumps(projected)
        assert "SOFTWARE_RETAINED_BODY_SENTINEL" not in serialized
        assert "retained_content_utf8" not in serialized and '"blocks"' not in serialized
        assert '"capability"' not in serialized and '"token"' not in serialized
    replay = client.post(root + "/preparation-jobs", json=payload(search, count))
    assert replay.status_code == 202 and replay.json()["reused"]
    assert replay.json()["job"]["id"] == job["id"]
    assert len(client.get(root).json()["preparations"]) == 1


@pytest.mark.parametrize("bad", ["zero", "thirty-one", "duplicate", "foreign", "wrong-search", "stale-revision"])
def test_invalid_job_inputs_do_not_mutate_or_fetch(http_case, bad):
    _, client, root, search, provider, _, _ = http_case
    body = payload(search)
    if bad == "zero": body["paper_ids"] = []
    elif bad == "thirty-one": body["paper_ids"] = [paper["id"] for paper in search["papers"]]
    elif bad == "duplicate": body["paper_ids"] = [body["paper_ids"][0]] * 2
    elif bad == "foreign": body["paper_ids"] = ["not-in-this-search"]
    elif bad == "wrong-search": body["search_id"] = "other-search"
    else: body["expected_source_revision"] = 99
    before = client.get(root).json()
    response = client.post(root + "/preparation-jobs", json=body)
    assert response.status_code in (404, 409, 422), response.text
    assert client.get(root).json() == before
    assert client.get(root + "/preparation-jobs").json()["jobs"] == []
    assert provider.calls == []


def test_job_input_fingerprint_and_cancelled_replay_are_stable(http_case):
    _, client, root, search, provider, _, _ = http_case
    body = payload(search)
    submitted = client.post(root + "/preparation-jobs", json=body)
    assert submitted.status_code == 202, submitted.text
    job = submitted.json()["job"]
    changed = client.post(root + "/preparation-jobs", json={**body, "paper_ids": list(reversed(body["paper_ids"]))})
    assert changed.status_code == 409 and changed.json()["error"]["code"] == "idempotency_conflict"
    cancelled = client.post(root + "/preparation-jobs/" + job["id"] + "/cancel", json={})
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    replay = client.post(root + "/preparation-jobs", json=body)
    assert replay.status_code == 202 and replay.json()["job"]["status"] == "cancelled"
    assert replay.json()["job"]["id"] == job["id"]
    assert provider.calls == [] and client.get(root).json()["source_revision"] == 0


def test_all_job_routes_require_workspace_session_and_csrf(http_case):
    app, first, root, search, _, _, _ = http_case
    submitted = first.post(root + "/preparation-jobs", json=payload(search))
    assert submitted.status_code == 202, submitted.text
    job = submitted.json()["job"]
    job_url = root + "/preparation-jobs/" + job["id"]
    other = TestClient(app, base_url="http://127.0.0.1:8765")
    csrf = other.get("/api/v1/session").json()["csrf_token"]
    other.headers.update({"Origin": "http://127.0.0.1:3000", "X-CSRF-Token": csrf})
    for url in (root + "/preparation-jobs", job_url):
        assert other.get(url).status_code == 404
    assert other.post(root + "/preparation-jobs", json=payload(search)).status_code == 404
    assert other.post(job_url + "/cancel", json={}).status_code == 404
    assert first.post(job_url + "/cancel", json={}, headers={"X-CSRF-Token": "invalid"}).status_code == 403
    assert first.post(root + "/preparation-jobs", json=payload(search), headers={"Origin": "https://example.invalid"}).status_code == 403
    assert first.get(job_url).json()["status"] == "queued"


def test_jobs_reopen_after_app_restart_with_original_cookie(http_case):
    app, client, root, search, provider, engine, path = http_case
    submitted = client.post(root + "/preparation-jobs", json=payload(search))
    assert submitted.status_code == 202, submitted.text
    job = submitted.json()["job"]
    restarted = TestClient(create_app(path, services={"saved_example": engine}), base_url="http://127.0.0.1:8765")
    restarted.cookies.set(COOKIE_NAME, client.cookies.get(COOKIE_NAME))
    assert restarted.get(root + "/preparation-jobs/" + job["id"]).json() == job
    assert app.state.preparation_worker.run_once()
    assert restarted.get(root + "/preparation-jobs/" + job["id"]).json()["status"] == "succeeded"
    assert provider.calls == payload(search)["paper_ids"]


def test_preparation_readiness_tracks_actual_lifespan_worker_ownership(http_case):
    _, client, _, _, provider, _, _ = http_case
    assert client.get("/api/v1/capabilities").json()["preparation_jobs_ready"] is False
    with client:
        assert client.get("/api/v1/capabilities").json()["preparation_jobs_ready"] is True
    assert client.get("/api/v1/capabilities").json()["preparation_jobs_ready"] is False
    assert provider.calls == []


def test_cancelling_inflight_http_job_keeps_old_current_and_durable_draft(http_case):
    app, client, root, search, provider, _, _ = http_case
    old = client.post(root + "/source-preparations", json={"request_id": "old", "search_id": search["id"],
        "paper_ids": [search["papers"][0]["id"]]})
    old.raise_for_status()
    provider.calls.clear()
    provider.block = True
    submitted = client.post(root + "/preparation-jobs", json={**payload(search), "expected_source_revision": 1,
        "expected_preparation_id": old.json()["id"]})
    assert submitted.status_code == 202, submitted.text
    job = submitted.json()["job"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        work = pool.submit(app.state.preparation_worker.run_once)
        assert provider.entered.wait(timeout=3)
        try:
            # This write takes the same workspace guard used by normal drafts.
            saved = pool.submit(client.put, root + "/drafts/discover", json={"version": 0, "data": {"query": "durable query"}}).result(timeout=2)
            assert saved.status_code == 200, saved.text
            assert client.get(root).json()["current_preparation_id"] == old.json()["id"]
            cancelled = client.post(root + "/preparation-jobs/" + job["id"] + "/cancel", json={})
            assert cancelled.status_code == 200, cancelled.text
        finally:
            provider.release.set()
            assert work.result(timeout=5)
    assert client.get(root + "/preparation-jobs/" + job["id"]).json()["status"] == "cancelled"
    assert client.get(root).json()["current_preparation_id"] == old.json()["id"]
    assert client.get(root + "/drafts/discover").json()["data"]["query"] == "durable query"
