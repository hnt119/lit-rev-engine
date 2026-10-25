"""Independent HTTP bounds/CAS checks using wholly synthetic metadata."""
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.contracts import Block, Paper, PreparedSource, SearchPreview
from src.mvp.service import MVPService
from src.web_api.app import create_app


class SyntheticProvider:
    def __init__(self):
        self.papers = [Paper(pmid=str(520000 + index), title=f"SOFTWARE HTTP LIMITS RECORD {index}",
                             abstract="Synthetic metadata for an independent HTTP check.") for index in range(31)]
        self.source_calls = []

    def search(self, request):
        return SearchPreview(query=request.query, papers=self.papers, fetched_count=31, total_reported=31,
            ordered_identifiers=[paper.id for paper in self.papers], provider="synthetic-http-test", mode="test", truncated=False)

    def prepare(self, paper):
        self.source_calls.append(paper.id)
        return PreparedSource(paper_id=paper.id, status="abstract_only", source_type="abstract",
            provider="synthetic-http-test", source_url="", source_identifiers={"pmid": paper.pmid},
            blocks=[Block(id="abstract:1", ordinal=1, text=paper.abstract, locator={"type": "abstract"})])


@pytest.fixture
def selection_case(tmp_path, monkeypatch):
    monkeypatch.setenv("MVP_MAP_ENABLED", "0")
    monkeypatch.setenv("MVP_PROPOSALS_ENABLED", "0")
    provider = SyntheticProvider()
    engine = MVPService(SQLiteWorkspaceStorage(tmp_path / "workspace.sqlite3"), provider, provider)
    app = create_app(tmp_path, services={"saved_example": engine})
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    csrf = client.get("/api/v1/session").json()["csrf_token"]
    client.headers.update({"Origin": "http://127.0.0.1:3000", "X-CSRF-Token": csrf})
    workspace = client.post("/api/v1/workspaces", json={"request_id": "workspace", "mode": "saved_example"}).json()
    root = "/api/v1/workspaces/" + workspace["id"]
    searched = client.post(root + "/searches", json={"request_id": "search", "query": "synthetic", "max_results": 50})
    searched.raise_for_status()
    preview = searched.json()
    draft = root + "/drafts/" + quote("selection:" + preview["id"], safe="")
    return client, root, preview, draft, provider


def test_capability_reports_distinct_selection_sync_and_board_limits(selection_case):
    client, *_ = selection_case
    data = client.get("/api/v1/capabilities").json()
    assert data["limits"]["max_sources"] == data["limits"]["max_prepared_sources"] == 30
    assert data["limits"]["max_synchronous_prepared_sources"] == 10
    assert data["limits"]["max_results"] == 50
    assert data["boards"]["max_papers"] == data["limits"]["max_board_papers"] == 30
    assert data["boards"]["max_fields"] == data["limits"]["max_board_fields"] == 6
    assert data["boards"]["max_cells"] == data["limits"]["max_board_cells"] == 180
    assert isinstance(data["preparation_jobs_ready"], bool)


@pytest.mark.parametrize("count", [0, 1, 10, 11, 29, 30])
def test_selection_drafts_accept_only_owned_unique_records_without_preparing(selection_case, count):
    client, root, preview, draft, provider = selection_case
    ids = [paper["id"] for paper in preview["papers"][:count]]
    result = client.put(draft, json={"version": 0, "data": {"selected_paper_ids": ids}})
    assert result.status_code == 200, result.text
    assert result.json()["data"]["selected_paper_ids"] == ids
    assert client.get(draft).json() == result.json()
    assert client.get(root).json()["current_preparation_id"] is None
    assert provider.source_calls == []


@pytest.mark.parametrize("invalid", ["31", "duplicate", "foreign", "wrong-type", "unknown-key"])
def test_rejected_selection_preserves_the_existing_thirty_and_version(selection_case, invalid):
    client, _, preview, draft, provider = selection_case
    ids = [paper["id"] for paper in preview["papers"][:30]]
    saved = client.put(draft, json={"version": 0, "data": {"selected_paper_ids": ids}})
    saved.raise_for_status()
    value = {"selected_paper_ids": ids}
    if invalid == "31":
        value = {"selected_paper_ids": [paper["id"] for paper in preview["papers"]]}
    elif invalid == "duplicate":
        value = {"selected_paper_ids": [ids[0], ids[0]]}
    elif invalid == "foreign":
        value = {"selected_paper_ids": ["not-a-member-of-this-search"]}
    elif invalid == "wrong-type":
        value = {"selected_paper_ids": "not-a-list"}
    else:
        value = {"selected_paper_ids": ids, "silently_ignored_field": True}
    rejected = client.put(draft, json={"version": saved.json()["version"], "data": value})
    assert rejected.status_code in (400, 422), rejected.text
    assert client.get(draft).json() == saved.json()
    assert provider.source_calls == []


def test_concurrent_thirty_selection_drafts_use_existing_cas(selection_case):
    client, _, preview, draft, _ = selection_case
    ids = [paper["id"] for paper in preview["papers"][:30]]
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(client.put, draft, json={"version": 0, "data": {"selected_paper_ids": order}})
                 for order in (ids, list(reversed(ids)))]
        results = [task.result(timeout=10) for task in tasks]
    assert sorted(result.status_code for result in results) == [200, 409]
    winner = next(result.json() for result in results if result.status_code == 200)
    assert client.get(draft).json() == winner


def test_legacy_http_cannot_start_eleven_provider_calls(selection_case):
    client, root, preview, _, provider = selection_case
    prior = client.get(root).json()
    result = client.post(root + "/source-preparations", json={"request_id": "eleven", "search_id": preview["id"],
        "paper_ids": [paper["id"] for paper in preview["papers"][:11]]})
    assert result.status_code in (409, 422), result.text
    assert result.json()["error"]["code"] == "preparation_job_required"
    assert client.get(root).json() == prior
    assert provider.source_calls == []
