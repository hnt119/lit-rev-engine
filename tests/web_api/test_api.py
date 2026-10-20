"""Offline HTTP acceptance. No PubMed, paid inference, or model download."""
import json
import os
import sqlite3
import subprocess
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from src.mvp.adapters.saved_examples import SavedExampleProvider
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.service import MVPService
from src.mvp.workspace_ui import WorkspaceUIStore
from src.mvp.ports import MvpError
from src.web_api.app import COOKIE_NAME, create_app

BASE = "http://127.0.0.1:8765"
ORIGIN = "http://127.0.0.1:3000"
P = "/api/v1"


def api(tmp_path, *, services=None):
    app = create_app(tmp_path, services=services)
    client = TestClient(app, base_url=BASE)
    session = client.get(P + "/session")
    assert session.status_code == 200
    client.headers.update({"Origin": ORIGIN, "X-CSRF-Token": session.json()["csrf_token"]})
    return app, client


def create(client, request_id="create", question="microbiome"):
    result = client.post(P + "/workspaces", json={"request_id": request_id, "question": question, "mode": "saved_example"})
    assert result.status_code == 200, result.text
    return result.json()


def search(client, workspace, request_id="search"):
    result = client.post(f'{P}/workspaces/{workspace["id"]}/searches', json={"request_id": request_id, "query": "recorded saved example", "research_question": "microbiome", "max_results": 30})
    assert result.status_code == 200, result.text
    return result.json()


def prepared(client, workspace, preview, request_id="prepare"):
    result = client.post(f'{P}/workspaces/{workspace["id"]}/source-preparations', json={"request_id": request_id, "search_id": preview["id"], "paper_ids": [item["id"] for item in preview["papers"]]})
    assert result.status_code == 200, result.text
    return result.json()


def evidence(client, workspace, preparation):
    result = client.post(f'{P}/workspaces/{workspace["id"]}/evidence-runs', json={"request_id": "run", "question": "microbiome diversity", "expected_preparation_id": preparation["id"], "expected_source_revision": preparation["source_revision"]})
    assert result.status_code == 200, result.text
    return result.json()


def test_offline_workflow_small_views_and_unchanged_exports(tmp_path):
    app, client = api(tmp_path)
    workspace = create(client)
    preview = search(client, workspace)
    preparation = prepared(client, workspace, preview)
    run = evidence(client, workspace, preparation)
    assert preview["mode"] == "saved_example"
    assert preview["schema_version"] == "mvp.exploratory-preview.v1"
    assert preview["query"] != "recorded saved example"
    assert len(run["passages"]) <= 5 and run["passages"]
    assert client.get(f'{P}/workspaces/{workspace["id"]}/searches/{preview["id"]}/papers').json() == preview
    assert client.get(f'{P}/workspaces/{workspace["id"]}/source-preparations/{preparation["id"]}').json() == preparation
    assert "blocks" not in preparation["sources"][0]
    assert "retained_content_utf8" not in preparation["sources"][0]
    view = client.get(f'{P}/workspaces/{workspace["id"]}/runs/{run["id"]}').json()
    assert view["current"] and view["assessment_head"] is None
    passage = run["passages"][0]
    context = client.get(f'{P}/workspaces/{workspace["id"]}/runs/{run["id"]}/passages/{passage["id"]}/context?limit=2').json()
    assert len(context["blocks"]) == 2 and context["next_offset"] == 2
    assert context["block"]["text"][passage["anchor"]["start"]:passage["anchor"]["end"]] == passage["anchor"]["quote"]
    assessment = client.post(f'{P}/workspaces/{workspace["id"]}/assessments', json={"request_id": "assessment", "run_id": run["id"], "feedback": "SYNTHETIC SOFTWARE TEST JUDGMENT"})
    assert assessment.status_code == 200
    assert assessment.json()["bundle"]["status"] == "not_assessed"
    revised = client.post(f'{P}/workspaces/{workspace["id"]}/assessments', json={"request_id": "revision", "run_id": run["id"], "supersedes_id": assessment.json()["id"], "feedback": "SYNTHETIC SOFTWARE TEST REVISION"})
    assert revised.status_code == 200
    summary = client.get(f'{P}/workspaces/{workspace["id"]}').json()
    assert summary["assessments"][-1]["supersedes_id"] == assessment.json()["id"]
    assert "sources" not in summary and "passages" not in json.dumps(summary)
    assert all("abstract" not in item for item in summary["searches"])
    for format in ("csv", "json"):
        exported = client.get(f'{P}/workspaces/{workspace["id"]}/exports?format={format}')
        assert exported.status_code == 200 and "attachment" in exported.headers["content-disposition"]
        assert "web_sessions" not in exported.text and "csrf_token" not in exported.text
        if format == "json":
            assert exported.json()["schema_version"] == "mvp.audit-bundle.v1"
    assert client.get(P + "/workspaces").json()["workspaces"][0]["id"] == workspace["id"]


def test_reopening_after_new_clients_and_app_restart_same_ids(tmp_path):
    app, client = api(tmp_path)
    workspace = create(client)
    preview = search(client, workspace)
    cookie = client.cookies.get(COOKIE_NAME)
    csrf = client.headers["X-CSRF-Token"]
    client.put(f'{P}/workspaces/{workspace["id"]}/drafts/discover', json={"version": 0, "data": {"question": "persisted question", "query": "persisted query"}}).raise_for_status()
    for _ in range(2):
        restarted = TestClient(create_app(tmp_path), base_url=BASE)
        restarted.cookies.set(COOKIE_NAME, cookie)
        restored_session = restarted.get(P + "/session")
        assert restored_session.json()["csrf_token"] == csrf
        saved = restarted.get(P + "/workspaces").json()["workspaces"]
        assert len(saved) == 1 and saved[0]["id"] == workspace["id"]
        assert saved[0]["searches"][0]["id"] == preview["id"]
        draft = restarted.get(f'{P}/workspaces/{workspace["id"]}/drafts/discover').json()
        assert draft["data"]["query"] == "persisted query" and draft["version"] == 1


def test_session_isolation_every_resource_class(tmp_path):
    app, first = api(tmp_path)
    workspace = create(first)
    preview = search(first, workspace)
    preparation = prepared(first, workspace, preview)
    run = evidence(first, workspace, preparation)
    second = TestClient(app, base_url=BASE)
    csrf = second.get(P + "/session").json()["csrf_token"]
    second.headers.update({"Origin": ORIGIN, "X-CSRF-Token": csrf})
    assert second.get(P + "/workspaces").json() == {"workspaces": []}
    w = f'{P}/workspaces/{workspace["id"]}'
    for route in (w, w + f'/searches/{preview["id"]}/papers', w + f'/source-preparations/{preparation["id"]}', w + f'/runs/{run["id"]}', w + '/drafts/discover', w + '/exports', w + f'/runs/{run["id"]}/passages/{run["passages"][0]["id"]}/context'):
        assert second.get(route).status_code == 404, route
    assert second.put(w + "/drafts/discover", json={"version": 0, "data": {}}).status_code == 404
    assert second.post(w + "/searches", json={"request_id": "x", "query": "x"}).status_code == 404
    assert second.post(w + "/assessments", json={"request_id": "x", "run_id": run["id"]}).status_code == 404
    assert second.delete(w).status_code == 404


def test_cookie_and_credentials_private_not_browser_payloads(tmp_path):
    app, client = api(tmp_path)
    cookie_header = client.get(P + "/session").headers["set-cookie"]
    assert "HttpOnly" in cookie_header and "SameSite=strict" in cookie_header and "Max-Age=" in cookie_header
    workspace = create(client)
    registry = app.state.registry
    with registry.connection() as db:
        secret = db.execute("SELECT capability FROM web_workspaces").fetchone()[0]
        hashed = db.execute("SELECT token_hash FROM web_sessions").fetchone()[0]
    assert hashed != client.cookies.get(COOKIE_NAME)
    assert secret not in json.dumps(workspace)
    assert secret not in client.get(P + "/workspaces").text
    assert secret not in client.get(f'{P}/workspaces/{workspace["id"]}/exports?format=json').text
    assert secret not in json.dumps(app.openapi())
    assert os.stat(registry.path).st_mode & 0o777 == 0o600
    assert os.stat(tmp_path).st_mode & 0o777 == 0o700
    https_app = create_app(tmp_path / "https", allowed_origin="https://127.0.0.1:3000")
    assert "Secure" in TestClient(https_app, base_url=BASE).get(P + "/session").headers["set-cookie"]


@pytest.mark.parametrize("headers", [{"Host": "evil.example"}, {"Origin": "http://evil.example"}, {"Origin": "null"}])
def test_exact_host_origin_rejected(tmp_path, headers):
    _, client = api(tmp_path)
    assert client.get(P + "/workspaces", headers=headers).status_code == 403


def test_mutations_require_origin_csrf_and_bounded_json(tmp_path):
    _, client = api(tmp_path)
    request = {"request_id": "create"}
    for header in ("Origin", "X-CSRF-Token"):
        previous = client.headers.pop(header)
        assert client.post(P + "/workspaces", json=request).status_code == 403
        client.headers[header] = previous
    assert client.post(P + "/workspaces", json=request, headers={"Content-Length": "2000000"}).status_code == 413
    assert client.post(P + "/workspaces", content="x" * (1024 * 1024 + 1)).status_code == 413
    assert client.get(P + "/capabilities").headers["cache-control"] == "no-store"


def test_expired_and_cleared_cookies_do_not_recover_by_uuid(tmp_path):
    app, client = api(tmp_path)
    workspace = create(client)
    with app.state.registry.connection() as db:
        db.execute("UPDATE web_sessions SET expires_at='2000-01-01T00:00:00+00:00'")
    assert client.get(f'{P}/workspaces/{workspace["id"]}').status_code == 404
    client.get(P + "/session").raise_for_status()
    assert client.get(P + "/workspaces").json() == {"workspaces": []}
    client.cookies.clear()
    assert client.get(P + "/workspaces").status_code == 404


def test_idempotency_and_validation_before_provider_calls(tmp_path):
    _, client = api(tmp_path)
    workspace = create(client)
    assert create(client)["id"] == workspace["id"]
    assert client.post(P + "/workspaces", json={"request_id": "create", "question": "changed"}).status_code == 409
    assert client.post(P + "/workspaces", json={"request_id": "create", "question": "microbiome", "mode": "live"}).status_code == 409
    preview = search(client, workspace)
    assert search(client, workspace)["id"] == preview["id"]
    path = f'{P}/workspaces/{workspace["id"]}/searches'
    assert client.post(path, json={"request_id": "search", "query": "changed"}).status_code == 409
    for maximum in (0, 51, True, 30.5):
        assert client.post(path, json={"request_id": "bad", "query": "x", "max_results": maximum}).status_code == 422
    assert len(client.get(f'{P}/workspaces/{workspace["id"]}').json()["searches"]) == 1


def test_draft_cas_scope_and_assessment_head(tmp_path):
    _, client = api(tmp_path)
    workspace = create(client)
    base = f'{P}/workspaces/{workspace["id"]}'
    assert client.get(base + "/drafts/discover").json()["version"] == 0
    saved = client.put(base + "/drafts/discover", json={"version": 0, "data": {"question": "draft only"}})
    assert saved.status_code == 200 and saved.json()["version"] == 1
    assert client.put(base + "/drafts/discover", json={"version": 0, "data": {"question": "stale"}}).status_code == 409
    assert client.get(base + "/drafts/discover").json()["data"]["question"] == "draft only"
    assert client.get(base).json()["assessments"] == []
    assert client.get(base + "/drafts/selection:unknown").status_code == 404
    assert client.put(base + "/drafts/anything", json={"version": 0, "data": {}}).status_code == 422
    preview = search(client, workspace)
    preparation = prepared(client, workspace, preview)
    run = evidence(client, workspace, preparation)
    scope = base + f'/drafts/assessment:{run["id"]}'
    assert client.put(scope, json={"version": 0, "data": {"feedback": "synthetic draft"}}).status_code == 200
    assessment = client.post(base + "/assessments", json={"request_id": "a", "run_id": run["id"]}).json()
    stale = client.put(scope, json={"version": 1, "data": {"feedback": "stale draft"}})
    assert stale.status_code == 409
    assert client.get(scope).json()["data"]["feedback"] == "synthetic draft"
    assert client.put(scope, json={"version": 1, "expected_assessment_head": assessment["id"], "data": {"feedback": "explicit revision draft"}}).status_code == 200


def test_source_history_and_stale_preparation(tmp_path):
    _, client = api(tmp_path)
    workspace = create(client)
    preview = search(client, workspace)
    first = prepared(client, workspace, preview)
    run = evidence(client, workspace, first)
    second = prepared(client, workspace, preview, "new preparation")
    base = f'{P}/workspaces/{workspace["id"]}'
    old_request = {"request_id": "new-run", "question": "microbiome", "expected_preparation_id": first["id"], "expected_source_revision": first["source_revision"]}
    assert client.post(base + "/evidence-runs", json=old_request).status_code == 409
    assert len(client.get(base).json()["runs"]) == 1
    path = base + f'/runs/{run["id"]}/passages/{run["passages"][0]["id"]}/context'
    assert client.get(path).status_code == 409
    historical = client.get(path + "?archived=true&offset=2&limit=2")
    assert historical.status_code == 200
    assert historical.json()["archived"] and not historical.json()["current"]
    assert historical.json()["source"]["source_sha256"] == first["sources"][0]["source_sha256"]
    assert client.post(base + "/assessments", json={"request_id": "stale assessment", "run_id": run["id"]}).status_code == 409


def test_delete_clears_auxiliary_and_rejects_late_worker(tmp_path):
    app, client = api(tmp_path)
    workspace = create(client)
    base = f'{P}/workspaces/{workspace["id"]}'
    client.put(base + "/drafts/discover", json={"version": 0, "data": {"question": "do not resurrect"}}).raise_for_status()
    assert client.delete(base).status_code == 200
    assert client.get(base).status_code == 404
    assert client.get(P + "/workspaces").json() == {"workspaces": []}
    assert app.state.registry.is_deleted(workspace["id"])
    assert client.post(P + "/workspaces", json={"request_id": "create", "question": "microbiome", "mode": "saved_example"}).status_code == 404
    assert client.get(P + "/workspaces").json() == {"workspaces": []}
    with pytest.raises(MvpError):
        app.state.registry.get_bound_handle_for_worker(workspace["id"])
    with pytest.raises(MvpError):
        app.state.registry.put_draft(workspace["id"], "discover", version=0, data={})
    with app.state.registry.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM web_drafts").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM web_workspaces").fetchone()[0] == 0


def test_private_registry_rejects_symlinks(tmp_path):
    target = tmp_path / "target"
    target.write_text("untouched")
    link = tmp_path / "registry.sqlite3"
    link.symlink_to(target)
    with pytest.raises(ValueError):
        WorkspaceUIStore(link)
    assert target.read_text() == "untouched"
    directory = tmp_path / "symlink-dir"
    directory.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        WorkspaceUIStore(directory / "registry.sqlite3")


def test_draft_limits_rollback_and_concurrent_cas(tmp_path):
    store = WorkspaceUIStore(tmp_path / "ui.sqlite3", max_draft_bytes=100, max_workspace_draft_bytes=140, max_drafts=2)
    store.put_draft("workspace", "first", version=0, data={"value": "a" * 60})
    with pytest.raises(MvpError):
        store.put_draft("workspace", "first", version=1, data={"value": "x" * 101})
    assert store.draft("workspace", "first")["version"] == 1
    with pytest.raises(MvpError):
        store.put_draft("workspace", "second", version=0, data={"value": "b" * 70})
    assert store.draft("workspace", "second")["version"] == 0
    def attempt(value):
        try:
            store.put_draft("workspace", "first", version=1, data={"value": value})
            return "saved"
        except MvpError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, ("a", "b"))) == ["saved", "stale_draft"]


def test_delete_failure_preserves_access_and_draft(tmp_path):
    app, client = api(tmp_path)
    workspace = create(client)
    registry = app.state.registry
    cookie = client.cookies.get(COOKIE_NAME)
    session = registry.resolve_session(cookie)
    registry.put_draft(workspace["id"], "discover", version=0, data={"draft": "retained"})
    def fail(mode, handle):
        raise MvpError("clear_failed", "Synthetic clear failure")
    with pytest.raises(MvpError):
        registry.delete_workspace(session["token_hash"], workspace["id"], fail)
    assert not registry.is_deleted(workspace["id"])
    assert client.get(f'{P}/workspaces/{workspace["id"]}').status_code == 200
    assert registry.draft(workspace["id"], "discover")["data"] == {"draft": "retained"}


def test_additive_registry_backup_and_baseline_storage_reader(tmp_path):
    app, client = api(tmp_path / "original")
    workspace = create(client)
    preview = search(client, workspace)
    preparation = prepared(client, workspace, preview)
    run = evidence(client, workspace, preparation)
    client.post(f'{P}/workspaces/{workspace["id"]}/assessments', json={"request_id": "test", "run_id": run["id"], "feedback": "SYNTHETIC SOFTWARE TEST"}).raise_for_status()
    mode, handle = app.state.registry.get_bound_handle_for_worker(workspace["id"])
    source_db = tmp_path / "original/workspaces.sqlite3"
    backup_dir = tmp_path / "restored-copy"
    backup_dir.mkdir(mode=0o700)
    backup_db = backup_dir / "workspaces.sqlite3"
    with sqlite3.connect(source_db) as original, sqlite3.connect(backup_db) as backup:
        original.backup(backup)
    before = SQLiteWorkspaceStorage(source_db).read(handle)
    # Execute only the baseline's storage reader in its original package context.
    source = subprocess.check_output(["git", "show", "8df5993:src/mvp/adapters/storage.py"], text=True)
    namespace = {"__name__": "src.mvp.adapters.baseline_storage", "__package__": "src.mvp.adapters"}
    exec(compile(source, "<baseline-storage>", "exec"), namespace)
    restored = namespace["SQLiteWorkspaceStorage"](backup_db).read(handle)
    assert restored.id == before.id
    assert restored.model_dump_json() == before.model_dump_json()
    assert restored.sources[0].source_sha256 == preparation["sources"][0]["source_sha256"]
    assert restored.assessments[-1].feedback == "SYNTHETIC SOFTWARE TEST"
    # Adding web state did not change legacy schema or audit schema.
    with sqlite3.connect(source_db) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == {"mvp_workspaces", "mvp_requests"}


def test_failed_registry_reservation_does_not_create_domain_orphan(tmp_path):
    app, client = api(tmp_path)
    with app.state.registry.connection() as db:
        db.executescript("CREATE TRIGGER fail_binding BEFORE INSERT ON web_workspaces BEGIN SELECT RAISE(ABORT, 'SYNTHETIC REGISTRY WRITE FAILURE'); END;")
    with pytest.raises(sqlite3.IntegrityError):
        create(client)
    assert not (tmp_path / "workspaces.sqlite3").exists()
    with app.state.registry.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM web_create_requests").fetchone()[0] == 0
        db.execute("DROP TRIGGER fail_binding")
    create(client)
    with sqlite3.connect(tmp_path / "workspaces.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM mvp_workspaces").fetchone()[0] == 1


def test_concurrent_deletes_do_not_remove_successful_tombstone(tmp_path):
    app, client = api(tmp_path)
    workspace = create(client)
    store = app.state.registry
    session = store.resolve_session(client.cookies.get(COOKIE_NAME))
    clears = []
    def attempt(_):
        store.delete_workspace(session["token_hash"], workspace["id"], lambda mode, handle: clears.append(handle.workspace_id))
        return "deleted"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(attempt, (0, 1))) == ["deleted", "deleted"]
    assert clears == [workspace["id"]] and store.is_deleted(workspace["id"])
    with pytest.raises(MvpError):
        store.put_draft(workspace["id"], "discover", version=0, data={})


def test_pending_creation_reservation_survives_publication_failure_and_restart(tmp_path):
    app, client = api(tmp_path)
    with app.state.registry.connection() as db:
        db.executescript("CREATE TRIGGER fail_ready BEFORE UPDATE ON web_workspaces WHEN NEW.ready=1 BEGIN SELECT RAISE(ABORT, 'SYNTHETIC PUBLICATION FAILURE'); END;")
    with pytest.raises(sqlite3.IntegrityError):
        create(client)
    with app.state.registry.connection() as db:
        reserved = db.execute("SELECT workspace_id,ready FROM web_workspaces").fetchone()
        assert reserved["ready"] == 0
        db.execute("DROP TRIGGER fail_ready")
    with sqlite3.connect(tmp_path / "workspaces.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM mvp_workspaces").fetchone()[0] == 1
    assert client.get(P + "/workspaces").json() == {"workspaces": []}
    assert client.get(f'{P}/workspaces/{reserved["workspace_id"]}').status_code == 404
    restarted = TestClient(create_app(tmp_path), base_url=BASE)
    restarted.cookies.set(COOKIE_NAME, client.cookies.get(COOKIE_NAME))
    restarted.headers.update({"Origin": ORIGIN, "X-CSRF-Token": client.headers["X-CSRF-Token"]})
    assert create(restarted)["id"] == reserved["workspace_id"]
    with sqlite3.connect(tmp_path / "workspaces.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM mvp_workspaces").fetchone()[0] == 1


def test_assessment_and_draft_head_share_workspace_serialization(tmp_path):
    import threading
    from src.mvp.contracts import SaveAssessmentRequest
    app, client = api(tmp_path)
    workspace = create(client)
    preview = search(client, workspace)
    preparation = prepared(client, workspace, preview)
    run = evidence(client, workspace, preparation)
    registry = app.state.registry
    mode, handle = registry.get_bound_handle_for_worker(workspace["id"])
    engine = app.state.services[mode]
    entered, release = threading.Event(), threading.Event()
    original_put = registry.put_draft
    def slow_put(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return original_put(*args, **kwargs)
    registry.put_draft = slow_put
    path = f'{P}/workspaces/{workspace["id"]}/drafts/assessment:{run["id"]}'
    with ThreadPoolExecutor(max_workers=2) as pool:
        draft_future = pool.submit(client.put, path, json={"version": 0, "data": {"feedback": "synthetic draft"}})
        assert entered.wait(timeout=5)
        assessment_future = pool.submit(engine.save_assessment, handle, SaveAssessmentRequest(request_id="parallel assessment", run_id=run["id"], feedback="SYNTHETIC CONCURRENT TEST"))
        assert not assessment_future.done()
        release.set()
        assert draft_future.result(timeout=5).status_code == 200
        assessment = assessment_future.result(timeout=5)
    registry.put_draft = original_put
    # The draft linearized first; a later stale autosave cannot overwrite it.
    stale = client.put(path, json={"version": 1, "data": {"feedback": "stale autosave"}})
    assert stale.status_code == 409
    assert registry.draft(workspace["id"], "assessment:" + run["id"])["version"] == 1
    assert engine.get_workspace(handle).current_assessment_ids[run["id"]] == assessment.id


@pytest.mark.parametrize("crash_after_clear", [False, True])
def test_interrupted_deletion_is_retryable_after_process_restart(tmp_path, crash_after_clear):
    import sys
    app, client = api(tmp_path)
    workspace = create(client)
    session = app.state.registry.resolve_session(client.cookies.get(COOKIE_NAME))
    code = '''
import json, os, sys
from pathlib import Path
from src.mvp.workspace_ui import WorkspaceUIStore
from src.mvp.bootstrap import build_service
payload=json.load(sys.stdin)
store=WorkspaceUIStore(Path(payload["directory"]) / "web-credentials.sqlite3")
def clear(mode,handle):
    if payload["after_clear"]:
        build_service(mode, payload["directory"]).clear_workspace_if_present(handle)
    os._exit(71)
store.delete_workspace(payload["session_hash"],payload["workspace_id"],clear)
'''
    child = subprocess.run([sys.executable, "-c", code], input=json.dumps({"directory": str(tmp_path), "session_hash": session["token_hash"], "workspace_id": workspace["id"], "after_clear": crash_after_clear}), text=True, capture_output=True, timeout=10)
    assert child.returncode == 71, child.stderr
    assert app.state.registry.is_deleted(workspace["id"])
    # Access remains blocked, but the owning browser retains an explicit retry.
    restarted = TestClient(create_app(tmp_path), base_url=BASE)
    restarted.cookies.set(COOKIE_NAME, client.cookies.get(COOKIE_NAME))
    restarted.headers.update({"Origin": ORIGIN, "X-CSRF-Token": client.headers["X-CSRF-Token"]})
    path = f'{P}/workspaces/{workspace["id"]}'
    assert restarted.get(path).status_code == 404
    assert restarted.delete(path).status_code == 200
    assert restarted.delete(path).status_code == 200
    with app.state.registry.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM web_workspaces").fetchone()[0] == 0
    with sqlite3.connect(tmp_path / "workspaces.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM mvp_workspaces").fetchone()[0] == 0


@pytest.mark.parametrize("crash_after_create", [False, True])
def test_interrupted_creation_reuses_reserved_id_after_process_restart(tmp_path, crash_after_create):
    import sys
    app, client = api(tmp_path)
    session = app.state.registry.resolve_session(client.cookies.get(COOKIE_NAME))
    payload = {"request_id": "interrupted-create", "question": "microbiome", "mode": "saved_example"}
    code = '''
import json, os, sys
from pathlib import Path
from src.mvp.workspace_ui import WorkspaceUIStore
from src.mvp.bootstrap import build_service
from src.mvp.contracts import CreateWorkspaceRequest
payload=json.load(sys.stdin)
store=WorkspaceUIStore(Path(payload["directory"]) / "web-credentials.sqlite3")
def create(handle):
    if payload["after_create"]:
        build_service("saved_example",payload["directory"]).create_reserved_workspace(handle,CreateWorkspaceRequest(question="microbiome"))
    os._exit(72)
request=payload["request"]
store.create_workspace(payload["session_hash"],request["request_id"],request,create)
'''
    child = subprocess.run([sys.executable, "-c", code], input=json.dumps({"directory": str(tmp_path), "session_hash": session["token_hash"], "request": payload, "after_create": crash_after_create}), text=True, capture_output=True, timeout=10)
    assert child.returncode == 72, child.stderr
    with app.state.registry.connection() as db:
        reserved = db.execute("SELECT workspace_id,ready FROM web_workspaces").fetchone()
        assert reserved["ready"] == 0
    assert client.get(P + "/workspaces").json() == {"workspaces": []}
    restarted = TestClient(create_app(tmp_path), base_url=BASE)
    restarted.cookies.set(COOKIE_NAME, client.cookies.get(COOKIE_NAME))
    restarted.headers.update({"Origin": ORIGIN, "X-CSRF-Token": client.headers["X-CSRF-Token"]})
    result = restarted.post(P + "/workspaces", json=payload)
    assert result.status_code == 200
    assert result.json()["id"] == reserved["workspace_id"]
    with sqlite3.connect(tmp_path / "workspaces.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM mvp_workspaces").fetchone()[0] == 1


def test_concurrent_creation_retry_and_delete_cannot_recreate_orphan(tmp_path):
    import threading
    from src.mvp.contracts import CreateWorkspaceRequest
    app, client = api(tmp_path)
    store = app.state.registry
    session = store.resolve_session(client.cookies.get(COOKIE_NAME))
    engine = app.state.services.setdefault("saved_example", __import__("src.mvp.bootstrap", fromlist=["build_service"]).build_service("saved_example", tmp_path))
    entered, release = threading.Event(), threading.Event()
    payload = {"request_id": "same", "question": "microbiome", "mode": "saved_example"}
    def slow_create(handle):
        entered.set()
        assert release.wait(timeout=5)
        return engine.create_reserved_workspace(handle, CreateWorkspaceRequest(question="microbiome"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(store.create_workspace, session["token_hash"], "same", payload, slow_create)
        assert entered.wait(timeout=5)
        second = pool.submit(store.create_workspace, session["token_hash"], "same", payload, lambda handle: engine.create_reserved_workspace(handle, CreateWorkspaceRequest(question="microbiome")))
        release.set()
        one, two = first.result(timeout=5), second.result(timeout=5)
    assert one == two
    store.delete_workspace(session["token_hash"], one.workspace_id, lambda mode, handle: engine.clear_workspace_if_present(handle))
    with pytest.raises(MvpError):
        store.create_workspace(session["token_hash"], "same", payload, lambda handle: engine.create_reserved_workspace(handle, CreateWorkspaceRequest()))
    with sqlite3.connect(tmp_path / "workspaces.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM mvp_workspaces").fetchone()[0] == 0
