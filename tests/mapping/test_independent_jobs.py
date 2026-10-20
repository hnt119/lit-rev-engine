"""Independent durable-worker failures using synthetic metadata/vectors only.

The subprocess tests terminate a real worker process during fake embedding.
No real embedding model, provider, network request, or scientific judgment is used.
"""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
import os
import socket
import sqlite3
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from src.mvp.adapters.map_storage import MapStore
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.contracts import (
    Block, CreateWorkspaceRequest, PreparedSource, PrepareSourcesRequest,
    RetrieveEvidenceRequest, SaveAssessmentRequest, SearchRequest, digest,
)
from src.mvp.map_jobs import MapWorker, PaperMapService
from src.mvp.mapping import CreateMapRequest, EmbeddedPaper, build_artifact, counts, representations
from src.mvp.ports import MvpError
from src.mvp.service import MVPService
from src.mvp.workspace_ui import WorkspaceUIStore
from test_independent import fixture_profile, preview


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Synthetic job acceptance attempted network access")
    monkeypatch.setattr(socket, "create_connection", denied)


class SyntheticProviders:
    searches = 0
    preparations = 0

    def search(self, request):
        self.searches += 1
        return preview(3)

    def prepare(self, paper):
        self.preparations += 1
        block = Block(id="abstract:1", ordinal=1, text=paper.abstract,
                      locator={"type": "abstract", "ordinal": 1})
        return PreparedSource(paper_id=paper.id, source_type="abstract", status="abstract_only",
                              provider="synthetic-job-fixture", source_url="",
                              blocks=[block], source_sha256=sha256(paper.abstract.encode()).hexdigest(),
                              blocks_sha256=digest([block.model_dump(mode="json")]),
                              parser_id="synthetic-job-fixture.v1")


class SyntheticEmbedder:
    profile = fixture_profile()

    def readiness(self):
        return True, "Synthetic software-test vector port; not a model"

    def embed(self, representation, checkpoint):
        checkpoint()
        number = int(representation.paper_id.rsplit("-", 1)[-1])
        return EmbeddedPaper(paper_id=representation.paper_id, input_sha256=representation.input_sha256,
                             representation=representation.representation, vector=[1., .2 + number, .3],
                             window_token_weights=[3], token_count=3)


class CrashEmbedder(SyntheticEmbedder):
    def embed(self, representation, checkpoint):
        os._exit(79)


def _worker_for_path(directory, crash=False):
    """Also called by the real subprocess, which reads the same private stores."""
    directory = Path(directory)
    registry = WorkspaceUIStore(directory / "registry.sqlite3")
    providers = SyntheticProviders()
    engine = MVPService(SQLiteWorkspaceStorage(directory / "research.sqlite3"), providers, providers)
    store = MapStore(directory / "maps.sqlite3")
    maps = PaperMapService(registry, lambda mode: engine, store, CrashEmbedder() if crash else SyntheticEmbedder())
    return MapWorker(maps, heartbeat_seconds=.05, lease_seconds=5)


@pytest.fixture
def job_workspace(tmp_path):
    pytest.importorskip("numpy", reason="Optional projection runtime for synthetic job tests")
    registry = WorkspaceUIStore(tmp_path / "registry.sqlite3")
    token, session = registry.session()
    providers = SyntheticProviders()
    engine = MVPService(SQLiteWorkspaceStorage(tmp_path / "research.sqlite3"), providers, providers)
    handle = registry.create_workspace(session["token_hash"], "synthetic-create",
        {"mode": "saved_example", "question": "SYNTHETIC metadata question"},
        lambda reserved: engine.create_reserved_workspace(reserved, CreateWorkspaceRequest(question="SYNTHETIC metadata question")))
    search = engine.search_literature(handle, SearchRequest(request_id="synthetic-search", query="metadata"))
    prepared = engine.prepare_sources(handle, PrepareSourcesRequest(request_id="synthetic-prepare", search_id=search.id,
                                                                    paper_ids=[paper.id for paper in search.papers]))
    run = engine.retrieve_evidence(handle, RetrieveEvidenceRequest(request_id="synthetic-run", question="metadata paragraph"))
    assert run.passages and prepared.sources
    store = MapStore(tmp_path / "maps.sqlite3")
    maps = PaperMapService(registry, lambda mode: engine, store, SyntheticEmbedder())
    submitted = maps.submit("saved_example", handle, CreateMapRequest(request_id="synthetic-map", search_id=search.id))
    return SimpleNamespace(root=tmp_path, registry=registry, token=token, session=session, providers=providers,
                           engine=engine, handle=handle, search=search, run=run, store=store, maps=maps, job=submitted.job)


def _prepared_artifact(state, job):
    profile = state.maps.embedder.profile
    rows = [state.store.put_embedding(state.handle.workspace_id, profile, state.maps.embedder.embed(row, lambda: None))
            for row in representations(state.search)]
    artifact, rows = build_artifact(state.handle.workspace_id, state.search, profile, rows, [], job["map_id"])
    return artifact, rows, counts(state.search, artifact)


def test_real_worker_process_crashes_recover_only_up_to_recorded_attempt_limit(job_workspace):
    state = job_workspace
    before = state.engine.get_workspace(state.handle)
    root = Path(__file__).resolve().parents[2]
    code = '''
import sys
sys.path.insert(0, str(__import__('pathlib').Path.cwd() / 'tests/mapping'))
from test_independent_jobs import _worker_for_path
worker = _worker_for_path(sys.argv[1], crash=True)
assert worker._acquire()
worker.run_once()
raise AssertionError('Synthetic crash port did not terminate the worker')
'''
    for attempt in (1, 2):
        child = subprocess.run([sys.executable, "-c", code, str(state.root)], cwd=root,
                               capture_output=True, text=True, timeout=15)
        assert child.returncode == 79, child.stderr
        interrupted = state.store.job(state.handle.workspace_id, state.job.id)
        assert interrupted.status == "running" and interrupted.attempt == attempt
        worker = MapWorker(state.maps)
        assert worker._acquire()  # The crashed process really released its OS lock.
        try:
            recovered = state.store.job(state.handle.workspace_id, state.job.id)
            assert recovered.interrupted_count == attempt
            assert recovered.status == ("queued" if attempt == 1 else "failed")
            if attempt == 2:
                assert not worker.run_once()
        finally:
            worker._release()
    assert not state.store.listing(state.handle.workspace_id, state.search.id).maps
    assert state.engine.get_workspace(state.handle) == before


def test_expired_attempt_cannot_finalize_failure_before_recovery(job_workspace):
    state = job_workspace
    old = state.store.claim("synthetic-old-owner", lease_seconds=.02)
    threading.Event().wait(.06)
    state.store.finish_failure(old, MvpError("synthetic_old_failure", "SOFTWARE TEST OLD FAILURE"))
    assert state.store.job(state.handle.workspace_id, state.job.id).status == "running"
    current = state.store.claim("synthetic-current-owner", lease_seconds=5)
    assert current and current["attempt"] == 2
    assert current["lease_owner"] != old["lease_owner"]


def test_old_attempt_cannot_publish_or_overwrite_a_new_lease(job_workspace):
    state = job_workspace
    old = state.store.claim("synthetic-old-owner", lease_seconds=.02)
    artifact, rows, tally = _prepared_artifact(state, old)
    threading.Event().wait(.06)
    current = state.store.claim("synthetic-current-owner", lease_seconds=5)
    assert current["attempt"] == old["attempt"] + 1
    with pytest.raises(MvpError, match="attempt"):
        state.store.publish(old, artifact, rows, tally)
    state.store.finish_failure(old, MvpError("synthetic_old_failure", "SOFTWARE TEST OLD FAILURE"))
    assert state.store.job(state.handle.workspace_id, state.job.id).status == "running"
    state.store.publish(current, artifact, rows, tally)
    assert state.store.job(state.handle.workspace_id, state.job.id).status == "succeeded"
    assert state.store.map(state.handle.workspace_id, artifact.map_id).artifact.coordinate_sha256 == artifact.coordinate_sha256


@pytest.mark.parametrize("action", ["cancel", "delete"])
def test_computing_map_does_not_block_evidence_save_and_late_work_is_rejected(job_workspace, action):
    state = job_workspace
    entered, release = threading.Event(), threading.Event()

    class BlockingEmbedder(SyntheticEmbedder):
        def embed(self, representation, checkpoint):
            entered.set()
            assert release.wait(5)
            checkpoint()
            return super().embed(representation, checkpoint)

    state.maps.embedder = BlockingEmbedder()
    worker = MapWorker(state.maps, heartbeat_seconds=.05, lease_seconds=5)
    assert worker._acquire()
    before = state.engine.get_workspace(state.handle)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            work = pool.submit(worker.run_once)
            assert entered.wait(5)
            def assess():
                current = state.engine.get_workspace(state.handle)
                assert current.sources == before.sources and current.runs == before.runs
                return state.engine.save_assessment(state.handle, SaveAssessmentRequest(
                    request_id="synthetic-during-map", run_id=state.run.id,
                    feedback="SYNTHETIC SOFTWARE TEST DURING MAP"))
            try:
                saved = pool.submit(assess).result(timeout=2)
                assert saved.feedback == "SYNTHETIC SOFTWARE TEST DURING MAP"
                if action == "cancel":
                    assert state.maps.cancel(state.handle, state.job.id).status == "cancel_requested"
                else:
                    state.registry.delete_workspace(state.session["token_hash"], state.handle.workspace_id,
                        lambda mode, handle: state.engine.clear_workspace_if_present(handle), state.maps.delete_workspace)
            finally:
                release.set()
            assert work.result(timeout=5)
    finally:
        release.set()
        worker._release()
    if action == "cancel":
        assert state.store.job(state.handle.workspace_id, state.job.id).status == "cancelled"
        assert not state.store.listing(state.handle.workspace_id, state.search.id).maps
        current = state.engine.get_workspace(state.handle)
        assert current.sources == before.sources and current.runs == before.runs
        assert current.assessments == [saved]
    else:
        assert state.registry.is_deleted(state.handle.workspace_id)
        with state.store.connection() as db:
            for table in ("paper_map_jobs", "paper_maps", "paper_embeddings", "paper_map_requests"):
                assert db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0
        with pytest.raises(MvpError):
            state.store.put_embedding(state.handle.workspace_id, state.maps.embedder.profile,
                                      SyntheticEmbedder().embed(representations(state.search)[0], lambda: None))
    assert state.providers.searches == 1 and state.providers.preparations == 3


def test_quiescent_backup_restores_registry_research_map_and_vector_hashes(job_workspace):
    state = job_workspace
    state.engine.save_assessment(state.handle, SaveAssessmentRequest(request_id="synthetic-backup-assessment",
        run_id=state.run.id, feedback="SYNTHETIC SOFTWARE TEST BACKUP"))
    worker = MapWorker(state.maps)
    assert worker._acquire()
    try:
        assert worker.run_once()
    finally:
        worker._release()
    before = state.engine.get_workspace(state.handle)
    completed = state.store.job(state.handle.workspace_id, state.job.id)
    assert completed.status == "succeeded"
    original_map = state.store.map(state.handle.workspace_id, completed.map_id)
    original_vectors = state.store.vectors(state.handle.workspace_id, completed.map_id)
    restored_root = state.root / "restored-copy"
    restored_root.mkdir(mode=0o700)
    # Quiescent SQLite backup, including the credential registry. No raw
    # capability is written to test output, URLs, or research exports.
    for name in ("registry.sqlite3", "research.sqlite3", "maps.sqlite3"):
        destination = restored_root / name
        destination.touch(mode=0o600)
        with sqlite3.connect(state.root / name) as source, sqlite3.connect(destination) as target:
            source.backup(target)
    registry = WorkspaceUIStore(restored_root / "registry.sqlite3")
    assert registry.resolve_session(state.token)["token_hash"] == state.session["token_hash"]
    mode, handle = registry.get_bound_handle_for_worker(state.handle.workspace_id)
    assert mode == "saved_example" and handle == state.handle
    restored = SQLiteWorkspaceStorage(restored_root / "research.sqlite3").read(handle)
    store = MapStore(restored_root / "maps.sqlite3")
    saved_map = store.map(handle.workspace_id, completed.map_id)
    assert restored.model_dump_json() == before.model_dump_json()
    assert [source.source_sha256 for source in restored.sources] == [source.source_sha256 for source in before.sources]
    assert digest([record.model_dump(mode="json") for record in restored.assessments]) == digest([record.model_dump(mode="json") for record in before.assessments])
    assert saved_map == original_map
    assert saved_map.artifact.coordinate_sha256 == original_map.artifact.coordinate_sha256
    assert saved_map.artifact.embedding_set_sha256 == original_map.artifact.embedding_set_sha256
    assert digest(store.vectors(handle.workspace_id, completed.map_id)) == digest(original_vectors)


def test_publication_quota_failure_rolls_back_every_artifact_link(job_workspace):
    state = job_workspace
    job = state.store.claim("synthetic-owner", lease_seconds=5)
    artifact, rows, tally = _prepared_artifact(state, job)
    state.store.max_maps = 0
    with pytest.raises(MvpError) as failure:
        state.store.publish(job, artifact, rows, tally)
    assert failure.value.code == "map_storage_limit"
    with state.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM paper_maps").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM paper_map_vectors").fetchone()[0] == 0
    assert state.store.job(state.handle.workspace_id, state.job.id).status == "running"
    state.store.finish_failure(job, failure.value)
    assert state.store.job(state.handle.workspace_id, state.job.id).status == "failed"
    assert state.engine.get_workspace(state.handle).sources
