"""Offline hosted boundary tests. No live providers, model, or private data."""
import hashlib
import json
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
import pytest

from src.web_api.app import COOKIE_NAME, create_app
from src.web_api.deployment import DeploymentConfig
from src.web_api.hosted_admission import (
    ADMISSION_COOKIE, ADMISSION_SECONDS, HOSTED_SESSION_COOKIE, AdmissionDenied,
    HostedAdmissionStore, MAX_ACTIVE_GRANTS, MAX_EXPENSIVE_JOBS,
    MAX_LOGIN_ATTEMPTS, MAX_REQUESTS, REQUEST_WINDOW_SECONDS,
    expensive_request,
)

CODE = "SYNTHETIC-TEST-ONLY-INVITATION-" + "a" * 32
PUBLIC = "https://research.example.test"
API = "https://127.0.0.1:8765"
PREFIX = "/api/v1"


def environment(tmp_path):
    return {"MVP_DEPLOYMENT_MODE": "hosted", "MVP_HOSTED_INGRESS": "render", "MVP_PUBLIC_ORIGIN": PUBLIC,
            "MVP_API_HOST": "127.0.0.1:8765", "MVP_API_ORIGIN": "http://127.0.0.1:8765",
            "MVP_PERSISTENT_ROOT": str(tmp_path), "MVP_WEB_DATA_DIR": str(tmp_path / "private"),
            "MVP_HOSTED_INVITE_SHA256": hashlib.sha256(CODE.encode()).hexdigest()}


def configured(tmp_path, monkeypatch):
    # Tests have a temporary directory, not a real Docker persistent mount.
    monkeypatch.setattr("src.web_api.deployment.os.path.ismount", lambda path: path == tmp_path)
    return DeploymentConfig.from_environment(environment(tmp_path))


def admitted(client):
    result = client.post(PREFIX + "/admission/login", json={"code": CODE}, headers={"Origin": PUBLIC})
    assert result.status_code == 200, result.text
    session = client.get(PREFIX + "/session")
    assert session.status_code == 200
    client.headers.update({"Origin": PUBLIC, "X-CSRF-Token": session.json()["csrf_token"]})
    return result


@pytest.mark.parametrize("setting,value", [
    ("MVP_PUBLIC_ORIGIN", "http://research.example.test"),
    ("MVP_PUBLIC_ORIGIN", "https://research.example.test/"),
    ("MVP_PUBLIC_ORIGIN", "https://research.example.test:443"),
    ("MVP_PUBLIC_ORIGIN", "https://user@research.example.test"),
    ("MVP_PUBLIC_ORIGIN", "https://RESEARCH.example.test"),
    ("MVP_PUBLIC_ORIGIN", "HTTPS://research.example.test"),
    ("MVP_PUBLIC_ORIGIN", " https://research.example.test"),
    ("MVP_PUBLIC_ORIGIN", "https://research.example.test-"),
    ("MVP_PUBLIC_ORIGIN", "https://research.example.test/?q=private"),
    ("MVP_PUBLIC_ORIGIN", "https://*.example.test"),
    ("MVP_PUBLIC_ORIGIN", "https://research..example.test"),
    ("MVP_PUBLIC_ORIGIN", "https://-research.example.test"),
    ("MVP_PUBLIC_ORIGIN", "https://research.example-.test"),
    ("MVP_PUBLIC_ORIGIN", "https://127.0.0.2"),
    ("MVP_PUBLIC_ORIGIN", "https://research.localhost"),
    ("MVP_HOSTED_INGRESS", "untrusted"),
    ("MVP_API_HOST", "0.0.0.0:8765"),
    ("MVP_API_ORIGIN", "http://localhost:8765"),
    ("MVP_API_ORIGIN", "https://external.test"),
    ("MVP_PERSISTENT_ROOT", "/"),
    ("MVP_WEB_DATA_DIR", "/tmp/other"),
    ("MVP_HOSTED_INVITE_SHA256", "not-a-hash"),
    ("MVP_PROPOSALS_ENABLED", "1"),
    ("MVP_SEARCH_PLANNER_ENABLED", "1"),
    ("MVP_MAP_ENABLED", "1"),
])
def test_hosted_invalid_configuration_is_fail_closed(tmp_path, setting, value):
    env = environment(tmp_path)
    env[setting] = value
    with pytest.raises(ValueError):
        DeploymentConfig.from_environment(env)


@pytest.mark.parametrize("setting", ["MVP_HOSTED_INGRESS", "MVP_PUBLIC_ORIGIN", "MVP_API_HOST", "MVP_API_ORIGIN",
    "MVP_PERSISTENT_ROOT", "MVP_WEB_DATA_DIR", "MVP_HOSTED_INVITE_SHA256"])
def test_missing_hosted_configuration_rejected(tmp_path, setting):
    env = environment(tmp_path)
    del env[setting]
    with pytest.raises(ValueError):
        DeploymentConfig.from_environment(env)


def test_real_mount_and_no_symlink_storage_required(tmp_path, monkeypatch):
    config = DeploymentConfig.from_environment(environment(tmp_path))
    monkeypatch.setattr("src.web_api.deployment.os.path.ismount", lambda path: False)
    with pytest.raises(ValueError):
        config.validate_storage()
    assert not config.data_dir.exists()
    monkeypatch.setattr("src.web_api.deployment.os.path.ismount", lambda path: True)
    (tmp_path / "private").symlink_to(tmp_path / "elsewhere")
    with pytest.raises(ValueError):
        config.validate_storage()


def test_local_mode_keeps_existing_cookie_and_origin_policy(tmp_path):
    client = TestClient(create_app(tmp_path), base_url="http://127.0.0.1:8765")
    status = client.get(PREFIX + "/admission/status")
    assert status.json() == {"mode": "local", "admitted": True}
    session = client.get(PREFIX + "/session")
    assert COOKIE_NAME in session.headers["set-cookie"]
    assert HOSTED_SESSION_COOKIE not in session.headers["set-cookie"]
    assert session.headers["cache-control"] == "no-store"
    assert client.get(PREFIX + "/session", headers={"Origin": PUBLIC}).status_code == 403
    with pytest.raises(ValueError):
        create_app(tmp_path / "wrong", allowed_origin=PUBLIC)


def test_admission_covers_every_api_route_before_session_issuance(tmp_path, monkeypatch):
    app = create_app(deployment=configured(tmp_path, monkeypatch))
    client = TestClient(app, base_url=API)
    for route in app.routes:
        path = route.path
        if not path.startswith(PREFIX) or "/admission/" in path:
            continue
        path = path.replace("{workspace_id}", "guessed-workspace")
        # Any unsubstituted path identifier is still denied by the common gate.
        for method in route.methods - {"HEAD", "OPTIONS"}:
            result = client.request(method, path, headers={"Origin": PUBLIC})
            assert result.status_code == 401, (method, path, result.text)
            assert "set-cookie" not in result.headers
            assert result.headers["cache-control"] == "no-store"
    with sqlite3.connect(app.state.registry.path) as db:
        assert db.execute("SELECT COUNT(*) FROM web_sessions").fetchone()[0] == 0
    assert client.get(PREFIX + "/admission/status").json() == {"mode": "hosted", "admitted": False}
    assert client.get("/healthz").json() == {"healthy": True}


def test_host_origin_csrf_secure_cookies_and_no_invitation_echo(tmp_path, monkeypatch):
    app = create_app(deployment=configured(tmp_path, monkeypatch))
    client = TestClient(app, base_url=API)
    assert client.post(PREFIX + "/admission/login", json={"code": CODE}).status_code == 403
    assert client.post(PREFIX + "/admission/login", json={"code": CODE}, headers={"Origin": "https://wrong.test"}).status_code == 403
    assert client.get(PREFIX + "/admission/status", headers={"Host": "research.example.test"}).status_code == 403
    assert client.get(PREFIX + "/session", headers={"X-Forwarded-Host": "research.example.test", "X-Forwarded-Proto": "https"}).status_code == 401
    login = admitted(client)
    for cookie in [login.headers["set-cookie"], client.get(PREFIX + "/session").headers["set-cookie"]]:
        assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/" in cookie
        assert "Domain=" not in cookie
    assert ADMISSION_COOKIE in client.cookies and HOSTED_SESSION_COOKIE in client.cookies
    assert CODE not in login.text and client.get(PREFIX + "/admission/status").json()["admitted"]
    result = client.post(PREFIX + "/workspaces", json={"request_id": "create", "question": "public synthetic fixture", "mode": "saved_example"}, headers={"X-CSRF-Token": "wrong"})
    assert result.status_code == 403
    assert result.headers["cache-control"] == "no-store"


def test_restart_rotation_logout_and_separate_workspace_ownership(tmp_path, monkeypatch):
    config = configured(tmp_path, monkeypatch)
    first = TestClient(create_app(deployment=config), base_url=API)
    second = TestClient(create_app(deployment=config), base_url=API)
    admitted(first)
    admitted(second)
    created = first.post(PREFIX + "/workspaces", json={"request_id": "create", "question": "public synthetic fixture", "mode": "saved_example"})
    assert created.status_code == 200, created.text
    path = PREFIX + "/workspaces/" + created.json()["id"]
    assert second.get(path).status_code == 404
    assert second.get(path + "/exports").status_code == 404
    assert second.delete(path).status_code == 404
    restarted = TestClient(create_app(deployment=config), base_url=API, cookies=first.cookies)
    assert restarted.get(path).status_code == 200
    assert restarted.get(path + "/exports?format=json").headers["cache-control"] == "no-store"
    assert first.post(PREFIX + "/admission/logout").status_code == 200
    assert first.get(path).status_code == 401
    assert HOSTED_SESSION_COOKIE in first.cookies
    admitted(first)
    assert first.get(path).status_code == 200
    # Independent browser admission and workspace session remain unaffected.
    assert second.get(PREFIX + "/session").status_code == 200
    rotated_env = environment(tmp_path)
    rotated_env["MVP_HOSTED_INVITE_SHA256"] = hashlib.sha256(b"rotated-synthetic-code").hexdigest()
    rotated = TestClient(create_app(deployment=DeploymentConfig.from_environment(rotated_env)), base_url=API, cookies=second.cookies)
    assert rotated.get(PREFIX + "/admission/status").json()["admitted"] is False
    assert rotated.get(PREFIX + "/session").status_code == 401


def test_expiry_login_and_active_grant_bounds_persist(tmp_path):
    clock = [1_000_000]
    store = HostedAdmissionStore(tmp_path / "admission.sqlite3", hashlib.sha256(CODE.encode()).hexdigest(), clock=lambda: clock[0])
    for _ in range(MAX_LOGIN_ATTEMPTS):
        store.login_attempt()
    with pytest.raises(AdmissionDenied) as failure:
        HostedAdmissionStore(store.path, store.invite_sha256, clock=lambda: clock[0]).login_attempt()
    assert failure.value.status == 429
    token, _ = store.issue(CODE)
    for _ in range(MAX_ACTIVE_GRANTS - 1):
        store.issue(CODE)
    with pytest.raises(AdmissionDenied) as failure:
        store.issue(CODE)
    assert failure.value.code == "admission_capacity"
    clock[0] += ADMISSION_SECONDS
    assert store.resolve(token) is None
    store.login_attempt()
    assert store.issue(CODE)[1] is not None
    assert CODE.encode() not in store.path.read_bytes()
    assert token.encode() not in store.path.read_bytes()


def test_request_and_expensive_budgets_survive_restart_and_reset(tmp_path):
    clock = [1_000_000]
    store = HostedAdmissionStore(tmp_path / "admission.sqlite3", hashlib.sha256(CODE.encode()).hexdigest(), clock=lambda: clock[0])
    token, _ = store.issue(CODE)
    for _ in range(MAX_EXPENSIVE_JOBS):
        store.consume(token, expensive=True)
    with pytest.raises(AdmissionDenied) as failure:
        store.consume(token, expensive=True)
    assert failure.value.code == "admission_usage_limit"
    # Manual cells are request-only and remain usable after job budget exhaustion.
    store.consume(token)
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE admission_grants SET requests=?", (MAX_REQUESTS,))
    restarted = HostedAdmissionStore(store.path, store.invite_sha256, clock=lambda: clock[0])
    with pytest.raises(AdmissionDenied):
        restarted.consume(token)
    clock[0] += REQUEST_WINDOW_SECONDS
    restarted.consume(token, expensive=True)
    assert expensive_request("POST", "/api/v1/workspaces/id/imports/csv")
    assert expensive_request("POST", "/api/v1/workspaces/id/imports/ris")
    assert not expensive_request("POST", "/api/v1/workspaces/id/boards/board/cell-revisions")


def test_hosted_capabilities_disable_model_and_new_map_worker(tmp_path, monkeypatch):
    app = create_app(deployment=configured(tmp_path, monkeypatch))
    with TestClient(app, base_url=API) as client:
        assert client.get("/readyz").status_code == 200
        admitted(client)
        capability = client.get(PREFIX + "/capabilities").json()
        assert capability["map"]["ready"] is False
        assert "Hosted map computation is disabled" in capability["map"]["reason"]
        assert app.state.map_worker._thread is None
        assert app.state.preparation_worker._thread.is_alive()
        created = client.post(PREFIX + "/workspaces", json={"request_id": "capability-test", "mode": "saved_example", "question": "public software fixture"})
        assert created.status_code == 200, created.text
        workspace = PREFIX + "/workspaces/" + created.json()["id"]
        planner = client.get(workspace + "/search-plan-capabilities").json()["planner"]
        assert planner["enabled"] is False and "unavailable in this hosted release" in planner["reason"]
        preview = client.post(workspace + "/searches", json={"request_id": "search", "query": "public saved example", "max_results": 30}).json()
        preparation = client.post(workspace + "/source-preparations", json={"request_id": "prepare", "search_id": preview["id"], "paper_ids": [preview["papers"][0]["id"]]}).json()
        board = client.post(workspace + "/boards", json={"request_id": "board", "question": "public software fixture", "preparation_id": preparation["id"], "paper_ids": preparation["selected_paper_ids"], "fields": [{"id": "population", "label": "Population", "subquestion": "study population"}]}).json()
        board_path = workspace + "/boards/" + board["definition"]["board_id"]
        for value in [client.get(board_path + "/proposal-capabilities").json(), client.get(board_path + "/proposals", params={"revision_id": board["definition"]["revision_id"]}).json()["capability"]]:
            assert value["enabled"] is False and "unavailable in this hosted release" in value["reason"]
    assert client.get("/readyz").status_code == 503


def test_hosted_errors_are_redacted_including_malformed_login(tmp_path, monkeypatch):
    app = create_app(deployment=configured(tmp_path, monkeypatch))
    client = TestClient(app, base_url=API)
    secret = "NEVER-ECHO-PRIVATE-DETAIL"
    result = client.post(PREFIX + "/admission/login", json={"code": CODE, secret: secret}, headers={"Origin": PUBLIC})
    assert result.status_code == 422 and secret not in result.text
    @app.get("/synthetic-failure")
    def fail():
        raise RuntimeError(secret)
    admitted(client)
    result = client.get("/synthetic-failure")
    assert result.status_code == 500 and secret not in result.text
    assert result.headers["cache-control"] == "no-store"
