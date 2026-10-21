"""Thirty real saved reports + frozen model map without inference or networking.

This verifies loading/binding the checked public artifact, not model quality or
live retrieval. Scientific relevance and human-review utility are not scored.
"""
from hashlib import sha256
import json
import math
from pathlib import Path
import shutil
import socket
import subprocess
import sys

from fastapi.testclient import TestClient
import pytest

from src.mvp.adapters.saved_examples import SavedExampleProvider
from src.mvp.adapters.transport import BoundedTransport
from src.mvp.contracts import SearchRequest, digest
from src.mvp.mapping import BGE_REVISION
from src.mvp.ports import MvpError
from src.web_api.app import COOKIE_NAME, create_app


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "examples/mvp/offline_microbiome_30_v1"
P = "/api/v1"
BASE = "http://127.0.0.1:8765"
ORIGIN = "http://127.0.0.1:3000"


class UnavailableEmbedder:
    """A saved map must be usable when numerical/model setup is unavailable."""
    calls = 0

    def readiness(self):
        return False, "TEST: model dependencies and weights are unavailable"

    @property
    def profile(self):
        pytest.fail("Loading a saved map must not inspect the active model profile")

    def embed(self, *args, **kwargs):
        self.calls += 1
        pytest.fail("Loading a saved map must not execute model inference")


@pytest.fixture(autouse=True)
def no_provider_network_or_projection(monkeypatch):
    import src.mvp.mapping as mapping
    def forbidden(*args, **kwargs):
        pytest.fail("Offline map loading must not call providers, networking, or projection")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(BoundedTransport, "request", forbidden)
    monkeypatch.setattr(mapping, "projection", forbidden)


def client_for(app, *, cookie=None):
    client = TestClient(app, base_url=BASE)
    if cookie:
        client.cookies.set(COOKIE_NAME, cookie)
    session = client.get(P + "/session")
    assert session.status_code == 200, session.text
    client.headers.update({"Origin": ORIGIN, "X-CSRF-Token": session.json()["csrf_token"]})
    return client


def setup(tmp_path, *, services=None):
    embedder = UnavailableEmbedder()
    app = create_app(tmp_path, services=services, map_embedder=embedder)
    return app, client_for(app), embedder


def workspace(client, key="create-offline-thirty"):
    response = client.post(P + "/workspaces", json={
        "request_id": key, "question": "Explore the retained microbiome reports", "mode": "saved_example"})
    assert response.status_code == 200, response.text
    return response.json()


def search(client, work, *, key="search-offline-thirty", cap=30):
    response = client.post(f'{P}/workspaces/{work["id"]}/searches', json={
        "request_id": key, "query": "UNEXECUTED USER QUERY", "max_results": cap,
        "research_question": "Explore the retained microbiome reports"})
    assert response.status_code == 200, response.text
    return response.json()


def map_for(client, work, search_result):
    root = f'{P}/workspaces/{work["id"]}'
    listing = client.get(root + "/maps", params={"search_id": search_result["id"]})
    assert listing.status_code == 200, listing.text
    listing = listing.json()
    assert listing["jobs"] == [], "Artifact import must not invent a completed inference job"
    assert len(listing["maps"]) == 1
    result = client.get(root + "/maps/" + listing["maps"][0]["map_id"])
    assert result.status_code == 200, result.text
    return result.json()


def test_explicit_offline_search_installs_thirty_point_map_with_real_input_bindings(tmp_path):
    app, client, embedder = setup(tmp_path)
    work = workspace(client)
    assert client.get(P + "/capabilities").json()["map"]["ready"] is False
    # Creating/opening an empty workspace does not fabricate a research search.
    assert client.get(f'{P}/workspaces/{work["id"]}').json()["searches"] == []
    result = search(client, work)
    mapped = map_for(client, work, result)
    artifact, counts = mapped["artifact"], mapped["counts"]
    assert len(result["papers"]) == result["fetched_count"] == 30
    identifiers = [paper["id"] for paper in result["papers"]]
    assert artifact["workspace_id"] == work["id"]
    assert artifact["search_id"] == result["id"]
    assert artifact["search_snapshot_sha256"] == digest(result)
    assert artifact["ordered_paper_ids"] == identifiers
    assert set(artifact["coordinates_by_paper_id"]) == set(identifiers)
    assert artifact["coordinate_sha256"] == digest(artifact["coordinates_by_paper_id"])
    assert artifact["embedding_profile_sha256"] == digest(artifact["embedding_profile"])
    assert artifact["embedding_profile"]["model"] == "BAAI/bge-small-en-v1.5"
    assert artifact["embedding_profile"]["model_revision"] == BGE_REVISION
    assert artifact["embedding_profile"]["tokenizer_revision"] == BGE_REVISION
    assert artifact["embedding_profile"]["dimension"] == 384
    assert artifact["embedding_profile"]["local_files_only"] is True
    assert artifact["embedding_profile"]["trust_remote_code"] is False
    assert artifact["status"] == "ready" and artifact["projection_method"] == "umap_cosine_v1"
    assert artifact["excluded_papers_with_reasons"] == []
    assert counts == {"provider_reported": result["total_reported"], "fetched_records": 30,
                      "distinct_records": 30, "embedded_papers": 30, "excluded_papers": 0, "map_points": 30}
    for paper in result["papers"]:
        text = "title: " + paper["title"].strip() + "\nabstract: " + paper["abstract"].strip()
        assert artifact["paper_input_hashes"][paper["id"]] == digest({"template": "paper-title-abstract-v1", "text": text})
        assert artifact["representation_by_paper_id"][paper["id"]] == "title_abstract"
        assert len(artifact["coordinates_by_paper_id"][paper["id"]]) == 2
        assert all(math.isfinite(value) for value in artifact["coordinates_by_paper_id"][paper["id"]])
    vectors = app.state.maps.store.vectors(work["id"], artifact["map_id"])
    assert set(vectors) == set(identifiers)
    assert all(len(vector) == 384 and math.isclose(math.hypot(*vector), 1, abs_tol=1e-9) for vector in vectors.values())
    vector_manifest = [{"paper_id": identifier, "input_sha256": artifact["paper_input_hashes"][identifier],
                        "vector_sha256": digest(vectors[identifier])} for identifier in identifiers]
    assert artifact["embedding_set_sha256"] == digest(vector_manifest)
    assert embedder.calls == 0


def test_saved_map_reopens_idempotently_without_refit_and_uses_retained_vector_neighbors(tmp_path):
    app, client, embedder = setup(tmp_path)
    work, original_cookie = workspace(client), client.cookies.get(COOKIE_NAME)
    result = search(client, work)
    mapped = map_for(client, work, result)
    artifact = mapped["artifact"]
    summary_before = client.get(f'{P}/workspaces/{work["id"]}').json()
    assert search(client, work) == result
    assert map_for(client, work, result) == mapped
    reopened = client_for(create_app(tmp_path, map_embedder=UnavailableEmbedder()), cookie=original_cookie)
    assert reopened.get(f'{P}/workspaces/{work["id"]}').json() == summary_before
    assert map_for(reopened, work, result) == mapped
    identifier = artifact["ordered_paper_ids"][0]
    neighbors = reopened.get(f'{P}/workspaces/{work["id"]}/maps/{artifact["map_id"]}/neighbors/{identifier}')
    assert neighbors.status_code == 200, neighbors.text
    items = neighbors.json()["neighbors"]
    assert len(items) == 5 and all(item["paper_id"] != identifier for item in items)
    assert len({item["paper_id"] for item in items}) == 5
    assert all(-1.000000001 <= item["cosine_similarity"] <= 1.000000001 for item in items)
    assert [item["cosine_similarity"] for item in items] == sorted([item["cosine_similarity"] for item in items], reverse=True)
    assert client.get(f'{P}/workspaces/{work["id"]}').json() == summary_before
    assert map_for(client, work, result) == mapped
    assert embedder.calls == 0


def test_each_saved_search_and_workspace_gets_its_own_map_binding(tmp_path):
    _, client, _ = setup(tmp_path)
    first = workspace(client)
    result = search(client, first)
    first_map = map_for(client, first, result)["artifact"]
    next_result = search(client, first, key="second-recorded-search")
    next_map = map_for(client, first, next_result)["artifact"]
    second = workspace(client, key="another-workspace")
    second_result = search(client, second)
    second_map = map_for(client, second, second_result)["artifact"]
    assert len({first_map["map_id"], next_map["map_id"], second_map["map_id"]}) == 3
    assert next_map["search_id"] == next_result["id"] != result["id"]
    assert next_map["search_snapshot_sha256"] == digest(next_result) != first_map["search_snapshot_sha256"]
    assert second_map["workspace_id"] == second["id"] != first["id"]
    assert first_map["coordinate_sha256"] == next_map["coordinate_sha256"] == second_map["coordinate_sha256"]
    assert first_map["coordinates_by_paper_id"] == next_map["coordinates_by_paper_id"] == second_map["coordinates_by_paper_id"]
    assert client.get(f'{P}/workspaces/{second["id"]}/maps/{first_map["map_id"]}').status_code == 404
    assert client.get(f'{P}/workspaces/{first["id"]}/maps', params={"search_id": second_result["id"]}).status_code == 404


def test_saved_map_remains_session_scoped_and_deleted_with_workspace(tmp_path):
    app, client, _ = setup(tmp_path)
    work = workspace(client)
    result = search(client, work)
    artifact = map_for(client, work, result)["artifact"]
    other = client_for(app)
    root = f'{P}/workspaces/{work["id"]}'
    for path in (root + "/maps?search_id=" + result["id"],
                 root + "/maps/" + artifact["map_id"],
                 root + "/maps/" + artifact["map_id"] + "/neighbors/" + artifact["ordered_paper_ids"][0]):
        assert other.get(path).status_code == 404
    assert client.delete(root).status_code == 200
    assert client.get(root + "/maps/" + artifact["map_id"]).status_code == 404
    with app.state.maps.store.connection() as db:
        assert db.execute("SELECT count(*) FROM paper_maps WHERE workspace_id=?", (work["id"],)).fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM paper_embeddings WHERE workspace_id=?", (work["id"],)).fetchone()[0] == 0


def test_small_capped_offline_search_does_not_receive_misbound_thirty_point_seed(tmp_path):
    _, client, _ = setup(tmp_path)
    work = workspace(client)
    result = search(client, work, cap=10)
    listing = client.get(f'{P}/workspaces/{work["id"]}/maps', params={"search_id": result["id"]})
    assert result["fetched_count"] == 10 and listing.status_code == 200
    assert listing.json() == {"maps": [], "jobs": []}


def test_existing_source_and_evidence_workflow_still_uses_permitted_sources(tmp_path):
    _, client, _ = setup(tmp_path)
    work = workspace(client)
    result = search(client, work)
    root = f'{P}/workspaces/{work["id"]}'
    selected = [item["id"] for item in result["papers"][:10]]
    response = client.post(root + "/source-preparations", json={
        "request_id": "ten-permitted-sources", "search_id": result["id"], "paper_ids": selected})
    assert response.status_code == 200, response.text
    prepared = response.json()
    assert len(prepared["sources"]) == 10
    assert {item["paper_id"] for item in prepared["sources"]} == set(selected)
    assert all(item["source_type"] == "full_text" and item["status"] == "full_text_retrieved"
               and item["license"] for item in prepared["sources"])
    response = client.post(root + "/evidence-runs", json={
        "request_id": "saved-source-evidence", "question": "gut microbiota women",
        "expected_preparation_id": prepared["id"], "expected_source_revision": prepared["source_revision"]})
    assert response.status_code == 200, response.text
    run = response.json()
    assert 1 <= len(run["passages"]) <= 5
    for passage in run["passages"]:
        context = client.get(root + f'/runs/{run["id"]}/passages/{passage["id"]}/context').json()
        anchor = passage["anchor"]
        assert context["block"]["text"][anchor["start"]:anchor["end"]] == anchor["quote"]


def test_seed_rejects_changed_saved_paper_input_instead_of_refitting():
    from src.mvp.adapters.saved_example_map import SavedExampleMap
    seed = SavedExampleMap()
    original = SavedExampleProvider().search(SearchRequest(request_id="seed-binding", query="ignored"))
    assert seed.matches(original)
    paper = original.papers[0].model_copy(update={"abstract": original.papers[0].abstract + " CHANGED INPUT"})
    changed = original.model_copy(update={"papers": [paper, *original.papers[1:]]})
    assert not seed.matches(changed)
    with pytest.raises(MvpError):
        seed.rebind("different-workspace", changed, "different-map")


@pytest.mark.parametrize("filename_key,hash_key", [("preview_file", "preview_sha256"),
                                                   ("artifact_file", "artifact_sha256"),
                                                   ("embeddings_file", "embeddings_sha256")])
def test_seed_bundle_tamper_fails_closed(tmp_path, filename_key, hash_key):
    from src.mvp.adapters.saved_example_map import SavedExampleMap
    root = tmp_path / "pack"
    shutil.copytree(PACK, root)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    seed = manifest["semantic_map"]
    path = root / seed[filename_key]
    path.write_bytes(path.read_bytes() + b"\n")
    assert sha256(path.read_bytes()).hexdigest() != seed[hash_key]
    with pytest.raises(MvpError):
        SavedExampleMap(fixture_dir=root)


@pytest.mark.parametrize("mutation", ["input_hash", "profile_revision", "token_coverage", "coordinate_membership"])
def test_rehashed_but_semantically_invalid_seed_bundle_is_rejected(tmp_path, mutation):
    """File digests alone do not establish a map's exact publication binding."""
    from src.mvp.adapters.saved_example_map import SavedExampleMap
    root = tmp_path / "pack"
    shutil.copytree(PACK, root)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    seed = manifest["semantic_map"]
    key = "embeddings" if mutation == "token_coverage" else "artifact"
    path = root / seed[key + "_file"]
    payload = json.loads(path.read_bytes())
    if mutation == "input_hash":
        identifier = payload["ordered_paper_ids"][0]
        payload["paper_input_hashes"][identifier] = "0" * 64
    elif mutation == "profile_revision":
        payload["embedding_profile"]["model_revision"] = "unpinned-software-mutation"
        payload["embedding_profile_sha256"] = digest(payload["embedding_profile"])
    elif mutation == "token_coverage":
        payload[0]["token_count"] += 1
    else:
        payload["coordinates_by_paper_id"].pop(payload["ordered_paper_ids"][0])
        payload["coordinate_sha256"] = digest(payload["coordinates_by_paper_id"])
    path.write_text(json.dumps(payload), encoding="utf-8")
    seed[key + "_sha256"] = sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(MvpError):
        SavedExampleMap(fixture_dir=root)


def test_saved_map_runtime_imports_no_optional_numerical_or_model_packages(tmp_path):
    script = r'''
import importlib.abc
import socket
import sys
class NoNumericalRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".", 1)[0] in {"numpy", "torch", "transformers", "sentence_transformers", "umap", "sklearn"}:
            raise AssertionError("Optional runtime imported while loading saved map: " + fullname)
sys.meta_path.insert(0, NoNumericalRuntime())
def forbidden(*args, **kwargs):
    raise AssertionError("Network called while loading saved map")
socket.create_connection = forbidden
socket.socket.connect = forbidden
from fastapi.testclient import TestClient
from src.web_api.app import create_app
app = create_app(sys.argv[1])
with TestClient(app, base_url="http://127.0.0.1:8765") as client:
    session = client.get("/api/v1/session").json()
    client.headers.update({"Origin":"http://127.0.0.1:3000", "X-CSRF-Token":session["csrf_token"]})
    work = client.post("/api/v1/workspaces", json={"request_id":"create", "mode":"saved_example"})
    assert work.status_code == 200, work.text
    root = "/api/v1/workspaces/" + work.json()["id"]
    search = client.post(root + "/searches", json={"request_id":"search", "query":"ignored", "max_results":30})
    assert search.status_code == 200, search.text
    listing = client.get(root + "/maps", params={"search_id":search.json()["id"]}).json()
    assert len(listing["maps"]) == 1 and listing["jobs"] == [], listing
    mapped = client.get(root + "/maps/" + listing["maps"][0]["map_id"])
    assert mapped.status_code == 200 and mapped.json()["counts"]["map_points"] == 30, mapped.text
print("saved map loaded without optional packages, network, or inference")
'''
    import os
    environment = dict(os.environ, MVP_MAP_ENABLED="0")
    completed = subprocess.run([sys.executable, "-c", script, str(tmp_path / "minimal-runtime")],
                               cwd=ROOT, env=environment, text=True, capture_output=True, timeout=60)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "saved map loaded without optional packages" in completed.stdout
