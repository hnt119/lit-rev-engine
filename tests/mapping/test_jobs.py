"""Deterministic synthetic software fixtures; no model/provider network calls."""
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import threading

import pytest
from fastapi.testclient import TestClient
from src.mvp.adapters.map_storage import MapStore
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.contracts import Paper, SearchPreview, digest
from src.mvp.map_jobs import MapWorker
from src.mvp.mapping import (CreateMapRequest, EmbeddedPaper, EmbeddingProfile,
                             build_artifact, counts, representations, validate_vector)
from src.mvp.ports import MvpError
from src.mvp.service import MVPService
from src.web_api.app import COOKIE_NAME, create_app

P = "/api/v1"

class SyntheticDiscovery:
    def __init__(self, count=3):
        self.calls = 0
        self.papers = [Paper(pmid=str(1000 + index), title=f"SOFTWARE TEST paper {index}", abstract=f"Synthetic software metadata {index}.") for index in range(count)]
    def search(self, request):
        self.calls += 1
        return SearchPreview(query=request.query, papers=self.papers, total_reported=len(self.papers), fetched_count=len(self.papers), ordered_identifiers=[item.pmid for item in self.papers], truncated=False, mode="test", provider="software-test-fixture")

class FixtureEmbedder:
    profile = EmbeddingProfile(model="SOFTWARE TEST VECTORS", model_revision="software-test-only", tokenizer_revision="software-test-only", dimension=3, runtime_versions={"fixture": "synthetic vectors; not actual model inference"})
    def __init__(self, entered=None, release=None):
        self.calls, self.entered, self.release = 0, entered, release
    def readiness(self):
        return True, "Synthetic software test adapter; not a real model."
    def embed(self, representation, checkpoint):
        self.calls += 1
        checkpoint()
        if self.entered:
            self.entered.set()
            assert self.release.wait(timeout=5)
            checkpoint()
        index = int(representation.paper_id.removeprefix("pmid:")) - 1000
        vector = validate_vector([1.0, float(index), float(index % 2)], 3)
        return EmbeddedPaper(paper_id=representation.paper_id, input_sha256=representation.input_sha256, representation=representation.representation, vector=vector, window_token_weights=[1], token_count=1)


def setup(tmp_path, count=3, embedder=None):
    provider = SyntheticDiscovery(count)
    service = MVPService(SQLiteWorkspaceStorage(tmp_path / "workspaces.sqlite3"), provider, None)
    app = create_app(tmp_path, services={"saved_example": service}, map_embedder=embedder or FixtureEmbedder())
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    csrf = client.get(P + "/session").json()["csrf_token"]
    client.headers.update({"Origin": "http://127.0.0.1:3000", "X-CSRF-Token": csrf})
    workspace = client.post(P + "/workspaces", json={"request_id": "create", "question": "SYNTHETIC SOFTWARE TEST"}).json()
    base = P + "/workspaces/" + workspace["id"]
    search = client.post(base + "/searches", json={"request_id": "search", "query": "SYNTHETIC SOFTWARE TEST"}).json()
    return app, client, base, search, provider


def submit(client, base, search, request_id="map", rebuild=False):
    response = client.post(base + "/maps", json={"request_id": request_id, "search_id": search["id"], "rebuild": rebuild})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("count", [0, 1, 2, 3])
def test_job_builds_saved_map_then_reads_without_refitting(tmp_path, count):
    app, client, base, search, provider = setup(tmp_path, count)
    submission = submit(client, base, search)
    assert submission["job"]["status"] == "queued"
    assert app.state.map_worker.run_once()
    job = client.get(base + "/jobs/" + submission["job"]["id"]).json()
    assert job["status"] == "succeeded", job
    view = client.get(base + "/maps/" + job["map_id"])
    assert view.status_code == 200, view.text
    body = view.json()
    assert body["counts"]["embedded_papers"] == count
    assert len(body["artifact"]["coordinates_by_paper_id"]) == count
    assert body["artifact"]["embedding_profile"]["model"] == "SOFTWARE TEST VECTORS"
    def contains_raw_vector(value):
        if isinstance(value, dict):
            return "vector" in value or any(contains_raw_vector(item) for item in value.values())
        return isinstance(value, list) and any(contains_raw_vector(item) for item in value)
    assert not contains_raw_vector(body)
    before = body["artifact"]["coordinate_sha256"]
    calls = app.state.maps.embedder.calls
    for _ in range(3):
        assert client.get(base + "/maps?search_id=" + search["id"]).json()["maps"][0]["map_id"] == job["map_id"]
        assert client.get(base + "/maps/" + job["map_id"]).json()["artifact"]["coordinate_sha256"] == before
    assert provider.calls == 1 and app.state.maps.embedder.calls == calls
    assert not app.state.map_worker.run_once()
    again = submit(client, base, search, "new request key")
    assert again["reused"] and again["job"]["id"] == job["id"]
    rebuild = submit(client, base, search, "explicit rebuild", rebuild=True)
    assert rebuild["job"]["map_id"] != job["map_id"]
    assert app.state.map_worker.run_once()
    assert app.state.maps.embedder.calls == calls  # persisted vectors reused
    assert len(client.get(base + "/maps?search_id=" + search["id"]).json()["maps"]) == 2


def test_restart_reads_same_map_id_coordinates_and_original_space_neighbors(tmp_path):
    app, client, base, search, _ = setup(tmp_path)
    job = submit(client, base, search)["job"]
    app.state.map_worker.run_once()
    first = client.get(base + "/maps/" + job["map_id"]).json()
    neighbor = client.get(base + "/maps/" + job["map_id"] + "/neighbors/pmid:1000").json()
    assert neighbor["neighbors"][0]["paper_id"] == "pmid:1001"
    assert neighbor["neighbors"][0]["cosine_similarity"] > neighbor["neighbors"][1]["cosine_similarity"]
    restarted = TestClient(create_app(tmp_path, map_embedder=FixtureEmbedder()), base_url="http://127.0.0.1:8765")
    restarted.cookies.set(COOKIE_NAME, client.cookies.get(COOKIE_NAME))
    assert restarted.get(base + "/maps/" + job["map_id"]).json() == first
    assert restarted.get(base + "/maps/" + job["map_id"] + "/neighbors/pmid:1000").json() == neighbor


def test_map_requests_are_idempotent_and_selection_drafts_do_not_submit(tmp_path):
    app, client, base, search, provider = setup(tmp_path)
    first = submit(client, base, search)
    assert submit(client, base, search)["job"]["id"] == first["job"]["id"]
    assert client.post(base + "/maps", json={"request_id": "map", "search_id": search["id"], "rebuild": True}).status_code == 409
    client.put(base + "/drafts/selection:" + search["id"], json={"version": 0, "data": {"selected_paper_ids": ["pmid:1001"]}}).raise_for_status()
    state = client.get(base).json()
    assert state["source_revision"] == 0 and not state["preparations"] and not state["runs"]
    assert provider.calls == 1 and len(client.get(base + "/maps?search_id=" + search["id"]).json()["jobs"]) == 1


def test_cancel_queued_and_running_jobs_never_publish(tmp_path):
    entered, release = threading.Event(), threading.Event()
    app, client, base, search, _ = setup(tmp_path, embedder=FixtureEmbedder(entered, release))
    queued = submit(client, base, search)
    cancel = client.post(base + "/jobs/" + queued["job"]["id"] + "/cancel", json={})
    assert cancel.json()["status"] == "cancelled" and not app.state.map_worker.run_once()
    running = submit(client, base, search, "new", rebuild=True)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(app.state.map_worker.run_once)
        assert entered.wait(timeout=5)
        assert client.post(base + "/jobs/" + running["job"]["id"] + "/cancel", json={}).json()["status"] == "cancel_requested"
        release.set()
        future.result(timeout=5)
    assert client.get(base + "/jobs/" + running["job"]["id"]).json()["status"] == "cancelled"
    assert client.get(base + "/maps?search_id=" + search["id"]).json()["maps"] == []


def test_compute_does_not_hold_research_lock_and_delete_rejects_late_result(tmp_path):
    entered, release = threading.Event(), threading.Event()
    app, client, base, search, _ = setup(tmp_path, embedder=FixtureEmbedder(entered, release))
    submission = submit(client, base, search)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(app.state.map_worker.run_once)
        assert entered.wait(timeout=5)
        # Draft save takes the existing research lock and completes during compute.
        client.put(base + "/drafts/discover", json={"version": 0, "data": {"question": "retained synthetic draft"}}).raise_for_status()
        assert client.delete(base).status_code == 200
        release.set()
        future.result(timeout=5)
    with app.state.maps.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM paper_maps").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM paper_map_jobs").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM paper_embeddings").fetchone()[0] == 0
    assert client.get(base + "/jobs/" + submission["job"]["id"]).status_code == 404


def test_map_and_job_session_isolation(tmp_path):
    app, client, base, search, _ = setup(tmp_path)
    job = submit(client, base, search)["job"]
    app.state.map_worker.run_once()
    other = TestClient(app, base_url="http://127.0.0.1:8765")
    csrf = other.get(P + "/session").json()["csrf_token"]
    other.headers.update({"Origin": "http://127.0.0.1:3000", "X-CSRF-Token": csrf})
    for route in (base + "/maps?search_id=" + search["id"], base + "/maps/" + job["map_id"], base + "/jobs/" + job["id"], base + "/maps/" + job["map_id"] + "/neighbors/pmid:1000"):
        assert other.get(route).status_code == 404
    assert other.post(base + "/maps", json={"request_id": "guess", "search_id": search["id"]}).status_code == 404
    assert other.post(base + "/jobs/" + job["id"] + "/cancel", json={}).status_code == 404


def test_missing_optional_setup_keeps_evidence_workflow_available(tmp_path):
    from src.mvp.adapters.paper_embeddings import LocalPaperEmbedder
    app = create_app(tmp_path, map_embedder=LocalPaperEmbedder(enabled=False))
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    csrf = client.get(P + "/session").json()["csrf_token"]
    client.headers.update({"Origin": "http://127.0.0.1:3000", "X-CSRF-Token": csrf})
    assert not client.get(P + "/capabilities").json()["map"]["ready"]
    workspace = client.post(P + "/workspaces", json={"request_id": "create"}).json()
    base = P + "/workspaces/" + workspace["id"]
    search = client.post(base + "/searches", json={"request_id": "search", "query": "offline sample"}).json()
    assert client.post(base + "/maps", json={"request_id": "map", "search_id": search["id"]}).status_code == 422
    assert client.get(base + "/searches/" + search["id"] + "/papers").status_code == 200


def test_request_quota_rolls_back_even_when_reusing_one_logical_job(tmp_path):
    app, client, base, search, _ = setup(tmp_path)
    store = app.state.maps.store
    store.max_requests = 2
    first = submit(client, base, search, "one")
    submit(client, base, search, "two")
    response = client.post(base + "/maps", json={"request_id": "three", "search_id": search["id"]})
    assert response.status_code == 422 and response.json()["error"]["code"] == "map_storage_limit"
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM paper_map_jobs").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM paper_map_requests").fetchone()[0] == 2
    assert client.get(base + "/jobs/" + first["job"]["id"]).json()["status"] == "queued"


def test_expired_attempt_recovery_bounded_retries_and_late_owner_rejection(tmp_path):
    app, client, base, search, _ = setup(tmp_path)
    submission = submit(client, base, search)
    store = app.state.maps.store
    first = store.claim("old-owner")
    assert first["attempt"] == 1
    with store.connection() as db:
        db.execute("UPDATE paper_map_jobs SET lease_expires='2000-01-01T00:00:00+00:00'")
    second = store.claim("new-owner")
    assert second["attempt"] == 2 and second["interrupted_count"] == 1
    with pytest.raises(MvpError):
        store.checkpoint(first)
    store.finish_failure(first, MvpError("old", "old worker failure must not win"))
    assert store.job(first["workspace_id"], first["id"]).status == "running"
    store.recover()
    assert store.job(first["workspace_id"], first["id"]).status == "failed"
    assert not store.claim("third-owner")
    assert store.job(first["workspace_id"], first["id"]).attempt == 2


def test_single_worker_lock_and_cooperative_restart_recovery(tmp_path):
    app, client, base, search, _ = setup(tmp_path)
    submission = submit(client, base, search)
    store = app.state.maps.store
    interrupted = store.claim("dead-process-owner")
    worker = app.state.map_worker
    assert worker._acquire()
    try:
        assert store.job(interrupted["workspace_id"], interrupted["id"]).status == "queued"
        assert not MapWorker(app.state.maps)._acquire()
        assert worker.run_once()
        result = client.get(base + "/jobs/" + submission["job"]["id"]).json()
        assert result["status"] == "succeeded" and result["interrupted_count"] == 1
    finally:
        worker._release()


def test_invalid_per_paper_vector_is_excluded_without_invented_position(tmp_path):
    class Invalid(FixtureEmbedder):
        def embed(self, representation, checkpoint):
            item = super().embed(representation, checkpoint)
            return item.model_copy(update={"vector": [0.0, 0.0, 0.0]}) if representation.paper_id == "pmid:1001" else item
    app, client, base, search, _ = setup(tmp_path, embedder=Invalid())
    job = submit(client, base, search)["job"]
    app.state.map_worker.run_once()
    result = client.get(base + "/maps/" + job["map_id"]).json()
    assert result["counts"]["embedded_papers"] == 2 and result["counts"]["excluded_papers"] == 1
    assert "pmid:1001" not in result["artifact"]["coordinates_by_paper_id"]
    assert result["artifact"]["excluded_papers_with_reasons"][0]["code"] == "embedding_zero_norm"


def pending_artifact(app, client, base, search):
    submission = submit(client, base, search)
    store = app.state.maps.store
    job = store.claim("publication-test-owner")
    preview = SearchPreview.model_validate(search)
    profile = app.state.maps.embedder.profile
    items = [store.put_embedding(job["workspace_id"], profile, app.state.maps.embedder.embed(item, lambda: None)) for item in representations(preview)]
    artifact, items = build_artifact(job["workspace_id"], preview, profile, items, [], job["map_id"])
    return store, job, artifact, items, counts(preview, artifact)


@pytest.mark.parametrize("tamper", ["three_dimensions", "nonfinite", "missing_paper", "wrong_input_hash", "wrong_profile_hash", "wrong_status", "duplicate_exclusion", "wrong_counts"])
def test_publication_rejects_tampered_artifact_atomically(tmp_path, tamper):
    from src.mvp.mapping import ExcludedPaper
    app, client, base, search, _ = setup(tmp_path)
    store, job, artifact, embedded, map_counts = pending_artifact(app, client, base, search)
    if tamper in {"three_dimensions", "nonfinite"}:
        coordinates = dict(artifact.coordinates_by_paper_id)
        coordinates[artifact.ordered_paper_ids[0]] = [0.0, 1.0, 2.0] if tamper == "three_dimensions" else [float("nan"), 0.0]
        artifact = artifact.model_copy(update={"coordinates_by_paper_id": coordinates, "coordinate_sha256": "invalid" if tamper == "nonfinite" else digest(coordinates)})
    elif tamper == "missing_paper":
        artifact = artifact.model_copy(update={"ordered_paper_ids": artifact.ordered_paper_ids[:-1]})
    elif tamper == "wrong_input_hash":
        artifact = artifact.model_copy(update={"paper_input_hashes": {}})
    elif tamper == "wrong_profile_hash":
        artifact = artifact.model_copy(update={"embedding_profile_sha256": "wrong"})
    elif tamper == "wrong_status":
        artifact = artifact.model_copy(update={"status": "empty"})
    elif tamper == "duplicate_exclusion":
        excluded = ExcludedPaper(paper_id="pmid:1000", code="software_test", reason="synthetic test")
        artifact = artifact.model_copy(update={"excluded_papers_with_reasons": [excluded, excluded]})
    else:
        map_counts = map_counts.model_copy(update={"embedded_papers": 999})
    with pytest.raises(MvpError) as error:
        store.publish(job, artifact, embedded, map_counts)
    assert error.value.code == "map_integrity"
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM paper_maps").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM paper_map_vectors").fetchone()[0] == 0
    assert store.job(job["workspace_id"], job["id"]).status == "running"


def test_cancel_between_checkpoint_and_publication_finishes_cancelled(tmp_path):
    app, client, base, search, _ = setup(tmp_path)
    store, job, artifact, embedded, map_counts = pending_artifact(app, client, base, search)
    store.cancel(job["workspace_id"], job["id"])
    with pytest.raises(MvpError) as error:
        store.publish(job, artifact, embedded, map_counts)
    store.finish_failure(job, error.value)
    assert store.job(job["workspace_id"], job["id"]).status == "cancelled"
    assert store.listing(job["workspace_id"], job["search_id"]).maps == []


def test_payload_quota_rolls_back_links_artifact_and_job_publication(tmp_path):
    app, client, base, search, _ = setup(tmp_path)
    store, job, artifact, embedded, map_counts = pending_artifact(app, client, base, search)
    store.max_workspace_bytes = 1
    with pytest.raises(MvpError) as error:
        store.publish(job, artifact, embedded, map_counts)
    assert error.value.code == "map_storage_limit"
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM paper_maps").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM paper_map_vectors").fetchone()[0] == 0
    assert store.job(job["workspace_id"], job["id"]).status == "running"


def test_map_artifacts_do_not_change_research_snapshots_requests_or_exports(tmp_path):
    app, client, base, search, _ = setup(tmp_path)
    mode, handle = app.state.registry.get_bound_handle_for_worker(base.rsplit("/", 1)[-1])
    engine = app.state.services[mode]
    original = engine.get_workspace(handle).model_dump_json()
    with sqlite3.connect(tmp_path / "workspaces.sqlite3") as db:
        request_count = db.execute("SELECT COUNT(*) FROM mvp_requests").fetchone()[0]
    submit(client, base, search)
    app.state.map_worker.run_once()
    assert engine.get_workspace(handle).model_dump_json() == original
    with sqlite3.connect(tmp_path / "workspaces.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM mvp_requests").fetchone()[0] == request_count
    audit = client.get(base + "/exports?format=json").json()
    assert audit["schema_version"] == "mvp.audit-bundle.v1"
    assert "maps" not in audit["workspace"] and "vectors" not in audit["workspace"]
