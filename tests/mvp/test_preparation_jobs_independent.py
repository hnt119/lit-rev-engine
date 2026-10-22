"""Independent preparation-worker failures and an offline 30-full-text check.

Synthetic barrier tests exercise actual SQLite locks and publication. The public
saved corpus is checked local material, not a fresh provider/model evaluation.
"""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import csv
import io
import json
import socket
import sqlite3
import threading

import pytest
from pydantic import ValidationError

from src.mvp.adapters.preparation_storage import PreparationStore, preparation_auxiliary_bytes
from src.mvp.adapters.saved_examples import SavedExampleProvider
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.contracts import (Block, CreateWorkspaceRequest, Paper, PreparedSource, PrepareSourcesRequest,
    RetrieveEvidenceRequest, SearchPreview, SearchRequest, SourceContextRequest, digest)
from src.mvp.preparation_contracts import PreparationJobRequest
from src.mvp.preparation_jobs import PreparationJobService, PreparationWorker
from src.mvp.ports import MvpError, ProviderFailure
from src.mvp.service import MVPService
from src.mvp.workspace_ui import WorkspaceUIStore


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Preparation acceptance attempted network access")
    monkeypatch.setattr(socket, "create_connection", denied)


class SyntheticProvider:
    def __init__(self, count=3):
        self.papers = [Paper(pmid=str(610000 + index), title=f"SOFTWARE PREPARATION RECORD {index}",
            abstract=f"Synthetic microbiome diversity evidence for record {index}.") for index in range(count)]
        self.calls = []
        self.entered, self.release = threading.Event(), threading.Event()
        self.block_on_call = None
        self.fail_ids, self.unavailable_ids = set(), set()

    def search(self, request):
        return SearchPreview(query=request.query, papers=self.papers, total_reported=len(self.papers),
            fetched_count=len(self.papers), ordered_identifiers=[paper.id for paper in self.papers],
            truncated=False, provider="synthetic-preparation", mode="test")

    def prepare(self, paper):
        self.calls.append(paper.id)
        if len(self.calls) == self.block_on_call:
            self.entered.set()
            assert self.release.wait(timeout=8), "Synthetic provider was not released"
        if paper.id in self.fail_ids:
            raise ProviderFailure("fixture_timeout", "Synthetic bounded source timeout", True)
        if paper.id in self.unavailable_ids:
            return PreparedSource(paper_id=paper.id, status="no_usable_text", source_type="none",
                provider="synthetic-preparation", source_url="", warnings=["Synthetic unavailable source"])
        block = Block(id="abstract:1", ordinal=1, text=paper.abstract, locator={"type": "abstract", "ordinal": 1})
        checksum = digest([block.model_dump(mode="json")])
        return PreparedSource(paper_id=paper.id, status="abstract_only", source_type="abstract",
            provider="synthetic-preparation", source_url="", source_identifiers={"pmid": paper.pmid},
            source_sha256=checksum, blocks_sha256=checksum, parser_id="synthetic.preparation.v1",
            parser_metadata={"source_hash_basis": "canonical-block-json-v1; original source bytes not retained"}, blocks=[block])


def case_for(path, provider=None):
    provider = provider or SyntheticProvider()
    storage = SQLiteWorkspaceStorage(path / "research.sqlite3")
    engine = MVPService(storage, provider, provider)
    registry = WorkspaceUIStore(path / "registry.sqlite3")
    _, session = registry.session()
    handle = registry.create_workspace(session["token_hash"], "create", {"mode": "saved_example"},
        lambda reserved: engine.create_reserved_workspace(reserved, CreateWorkspaceRequest(question="Synthetic software check")))
    search = engine.search_literature(handle, SearchRequest(request_id="search", query="microbiome", max_results=50))
    store = PreparationStore(storage)
    jobs = PreparationJobService(registry, lambda mode: engine, lambda mode: store)
    worker = PreparationWorker(jobs, modes=("saved_example",), heartbeat_seconds=.05, lease_seconds=5)
    return SimpleNamespace(path=path, provider=provider, storage=storage, engine=engine, registry=registry,
        session=session, handle=handle, search=search, store=store, jobs=jobs, worker=worker)


def request_for(case, key="job", paper_ids=None):
    state = case.engine.get_workspace(case.handle)
    return PreparationJobRequest(request_id=key, search_id=case.search.id,
        paper_ids=paper_ids if paper_ids is not None else [paper.id for paper in case.search.papers],
        expected_source_revision=state.source_revision,
        expected_preparation_id=state.preparations[-1].id if state.preparations else None)


def submit(case, request=None):
    return case.jobs.submit("saved_example", case.handle, request or request_for(case)).job


def view(case, job):
    return case.jobs.job("saved_example", case.handle, job.id)


@pytest.mark.parametrize("count", [1, 10, 11, 29, 30])
def test_preparation_jobs_publish_exact_order_through_thirty(tmp_path, count):
    case = case_for(tmp_path, SyntheticProvider(count))
    ids = list(reversed([paper.id for paper in case.search.papers]))
    job = submit(case, request_for(case, paper_ids=ids))
    assert job.status == "queued" and case.provider.calls == []
    assert job.selected_paper_ids == ids and job.progress_total == count
    assert case.worker.run_once()
    finished = view(case, job)
    state = case.engine.get_workspace(case.handle)
    assert finished.status == "succeeded" and finished.progress_completed == count
    assert finished.result_preparation_id == state.preparations[-1].id
    assert finished.result_source_revision == state.source_revision == 1
    assert [outcome.paper_id for outcome in finished.outcomes] == ids
    assert all(outcome.outcome == "abstract_only" for outcome in finished.outcomes)
    assert state.selected_paper_ids == [source.paper_id for source in state.sources] == ids
    assert case.provider.calls == ids
    assert not case.worker.run_once()


@pytest.mark.parametrize("ids", [[], [str(index) for index in range(31)], ["same", "same"]])
def test_invalid_job_selection_is_rejected_before_submission(ids):
    with pytest.raises(ValidationError):
        PreparationJobRequest(request_id="invalid", search_id="saved", paper_ids=ids, expected_source_revision=0)


def test_job_idempotency_and_owned_search_input_are_immutable(tmp_path):
    case = case_for(tmp_path)
    request = request_for(case)
    first = case.jobs.submit("saved_example", case.handle, request)
    second = case.jobs.submit("saved_example", case.handle, request)
    assert second.reused and second.job.id == first.job.id
    assert case.provider.calls == []
    with pytest.raises(MvpError) as changed:
        case.jobs.submit("saved_example", case.handle, request.model_copy(update={"paper_ids": list(reversed(request.paper_ids))}))
    assert changed.value.code == "idempotency_conflict"
    with pytest.raises(MvpError):
        submit(case, request_for(case, "foreign", ["not-in-this-search"]))
    with pytest.raises(MvpError):
        submit(case, request.model_copy(update={"request_id": "wrong-revision", "expected_source_revision": 99}))
    # Changing only a durable selection draft must not retarget a running input.
    case.registry.put_draft(case.handle.workspace_id, "selection:" + case.search.id,
        version=0, data={"selected_paper_ids": [request.paper_ids[-1]]})
    assert case.worker.run_once()
    assert case.engine.get_workspace(case.handle).selected_paper_ids == request.paper_ids
    completed = case.jobs.submit("saved_example", case.handle, request)
    assert completed.reused and completed.job.id == first.job.id
    assert len(case.engine.get_workspace(case.handle).preparations) == 1
    assert len(case.provider.calls) == 3


def test_slow_provider_holds_no_workspace_lock_and_keeps_old_current(tmp_path):
    case = case_for(tmp_path)
    old = case.engine.prepare_sources(case.handle, PrepareSourcesRequest(request_id="old", search_id=case.search.id,
        paper_ids=[case.search.papers[0].id]))
    case.provider.block_on_call = len(case.provider.calls) + 1
    job = submit(case)
    with ThreadPoolExecutor(max_workers=3) as pool:
        work = pool.submit(case.worker.run_once)
        assert case.provider.entered.wait(timeout=3)
        try:
            def guarded_read_and_draft():
                return case.engine.with_workspace_state(case.handle, lambda state: (state.source_revision,
                    case.registry.put_draft(case.handle.workspace_id, "discover", version=0, data={"query": "retained draft"})))
            revision, draft = pool.submit(guarded_read_and_draft).result(timeout=2)
            assert revision == old.source_revision and draft["data"]["query"] == "retained draft"
            state = case.engine.get_workspace(case.handle)
            assert state.preparations[-1].id == old.id and state.sources == old.sources
            progress = view(case, job)
            assert progress.status == "running" and progress.active_paper_id == case.search.papers[0].id
        finally:
            case.provider.release.set()
            assert work.result(timeout=5)
    assert view(case, job).status == "succeeded"


def test_progress_listing_and_cancel_do_not_wait_for_a_legacy_workspace_flock(tmp_path):
    case = case_for(tmp_path)
    job = submit(case)
    before = case.engine.get_workspace(case.handle).model_dump_json()
    entered, release = threading.Event(), threading.Event()
    def hold_workspace(state):
        entered.set()
        assert release.wait(timeout=6)
    with ThreadPoolExecutor(max_workers=2) as pool:
        held = pool.submit(case.engine.with_workspace_state, case.handle, hold_workspace)
        assert entered.wait(timeout=2)
        try:
            current = pool.submit(case.jobs.job, "saved_example", case.handle, job.id).result(timeout=1)
            assert current.status == "queued"
            listed = pool.submit(case.jobs.listing, "saved_example", case.handle, case.search.id).result(timeout=1)
            assert [item.id for item in listed.jobs] == [job.id]
            cancelled = pool.submit(case.jobs.cancel, "saved_example", case.handle, job.id).result(timeout=1)
            assert cancelled.status == "cancelled"
        finally:
            release.set()
            held.result(timeout=2)
    assert case.engine.get_workspace(case.handle).model_dump_json() == before
    assert case.provider.calls == []
    assert not case.worker.run_once()


@pytest.mark.parametrize("mutation", ["cancel", "new-revision", "delete"])
def test_inflight_job_cannot_publish_after_cancellation_staleness_or_deletion(tmp_path, mutation):
    case = case_for(tmp_path)
    case.provider.block_on_call = 1
    job = submit(case)
    with ThreadPoolExecutor(max_workers=2) as pool:
        work = pool.submit(case.worker.run_once)
        assert case.provider.entered.wait(timeout=3)
        try:
            if mutation == "cancel":
                case.jobs.cancel("saved_example", case.handle, job.id)
            elif mutation == "new-revision":
                newer = case.engine.prepare_sources(case.handle, PrepareSourcesRequest(request_id="newer", search_id=case.search.id,
                    paper_ids=[case.search.papers[-1].id]))
            else:
                case.registry.delete_workspace(case.session["token_hash"], case.handle.workspace_id,
                    lambda mode, handle: case.engine.clear_workspace_if_present(handle), case.jobs.delete_workspace)
        finally:
            case.provider.release.set()
            assert work.result(timeout=5)
    if mutation == "delete":
        with pytest.raises(MvpError):
            view(case, job)
        assert case.registry.is_deleted(case.handle.workspace_id)
        with sqlite3.connect(case.storage._path) as db:
            assert db.execute("SELECT COUNT(*) FROM mvp_workspaces").fetchone()[0] == 0
    else:
        state = case.engine.get_workspace(case.handle)
        if mutation == "cancel":
            assert state.source_revision == 0 and state.preparations == []
            assert view(case, job).status == "cancelled"
        else:
            assert state.preparations[-1].id == newer.id and state.source_revision == newer.source_revision
            assert len(state.preparations) == 1
            assert view(case, job).status == "stale", view(case, job).model_dump(mode="json")


def test_restarted_attempt_reuses_staged_success_and_old_owner_cannot_write(tmp_path):
    case = case_for(tmp_path)
    job = submit(case)
    attempt = case.store.claim("first-owner", lease_seconds=5)
    assert attempt is not None
    first_source = case.provider.prepare(case.search.papers[0])
    case.store.stage(attempt, first_source)
    # Simulate the old provider process dying; recover is normally called only
    # after its OS worker lock has been acquired by the replacement process.
    case.store.recover()
    with pytest.raises(MvpError):
        case.store.stage(attempt, first_source)
    assert case.worker.run_once()
    recovered = view(case, job)
    assert recovered.status == "succeeded" and recovered.attempt == 2 and recovered.interrupted_count == 1
    assert Counter(case.provider.calls) == Counter(paper.id for paper in case.search.papers)
    assert recovered.progress_completed == 3


def test_expired_attempt_cannot_stage_or_publish_over_its_replacement(tmp_path):
    case = case_for(tmp_path)
    job = submit(case)
    old = case.store.claim("expired-owner", lease_seconds=5)
    with sqlite3.connect(case.storage._path) as db:
        db.execute("UPDATE preparation_jobs SET lease_expires='2000-01-01T00:00:00+00:00' WHERE id=?", (job.id,))
    source = case.provider.prepare(case.search.papers[0])
    with pytest.raises(MvpError):
        case.store.stage(old, source)
    # Recovery follows replacement ownership, rather than letting an arbitrary
    # concurrent worker steal a merely slow process's provider calls.
    case.store.recover()
    assert case.worker.run_once()
    current = case.engine.get_workspace(case.handle)
    assert view(case, job).status == "succeeded" and view(case, job).attempt == 2
    with case.storage._connection() as db:
        with pytest.raises(MvpError):
            case.store.publication_guard(old)(db, {}, False)
    assert case.engine.get_workspace(case.handle).model_dump_json() == current.model_dump_json()


def test_corrupted_staging_is_not_reused_or_published_after_recovery(tmp_path):
    case = case_for(tmp_path)
    job = submit(case)
    attempt = case.store.claim("interrupted-owner", lease_seconds=5)
    case.store.stage(attempt, case.provider.prepare(case.search.papers[0]))
    with sqlite3.connect(case.storage._path) as db:
        db.execute("UPDATE preparation_stages SET payload_json=replace(payload_json,'Synthetic microbiome','TAMPERED microbiome') WHERE job_id=?", (job.id,))
    case.store.recover()
    assert case.worker.run_once()
    assert case.engine.get_workspace(case.handle).source_revision == 0
    assert case.engine.get_workspace(case.handle).preparations == []
    assert len(case.provider.calls) == 1, "Corrupted staged evidence must fail closed before new provider work"
    with pytest.raises(MvpError):
        case.store.staged(attempt)


def test_repeated_restarts_have_a_finite_attempt_budget(tmp_path):
    case = case_for(tmp_path)
    job = submit(case)
    for index in range(3):
        attempt = case.store.claim(f"interrupted-owner-{index}")
        assert attempt is not None and attempt["attempt"] == index + 1
        case.store.recover()
    final = view(case, job)
    assert final.status == "failed" and final.attempt == final.max_attempts == 3
    assert final.error.code == "preparation_attempt_limit"
    assert not case.worker.run_once() and case.provider.calls == []
    assert case.engine.get_workspace(case.handle).preparations == []


def test_elapsed_runtime_limit_blocks_staging_and_publication(tmp_path):
    case = case_for(tmp_path)
    case.store.max_runtime_seconds = .01
    case.provider.block_on_call = 1
    job = submit(case)
    with ThreadPoolExecutor(max_workers=1) as pool:
        work = pool.submit(case.worker.run_once)
        assert case.provider.entered.wait(timeout=3)
        threading.Event().wait(.02)
        case.provider.release.set()
        assert work.result(timeout=5)
    final = view(case, job)
    assert final.status == "failed" and final.progress_completed == 0
    assert final.error.code == "preparation_runtime_limit"
    assert case.engine.get_workspace(case.handle).source_revision == 0


def _publish_staged(case, attempt, sources):
    captured = case.store.input(attempt)
    with case.registry.lifecycle_guard(case.handle.workspace_id):
        return case.engine.publish_preparation_job(handle=case.handle, job_id=attempt["id"],
            expected_source_revision=captured.expected_source_revision, expected_preparation_id=captured.expected_preparation_id,
            search_id=captured.search_id, search_snapshot_sha256=captured.search_snapshot_sha256,
            paper_ids=captured.paper_ids, sources=sources, commit_guard=case.store.publication_guard(attempt))


def test_publication_charges_elapsed_lock_wait_even_with_an_unexpired_lease(tmp_path):
    case = case_for(tmp_path)
    old = case.engine.prepare_sources(case.handle, PrepareSourcesRequest(request_id="old", search_id=case.search.id,
        paper_ids=[case.search.papers[0].id]))
    case.store.max_runtime_seconds = 10
    job = submit(case)
    attempt = case.store.claim("active-owner", lease_seconds=90)
    sources = [case.provider.prepare(paper) for paper in case.search.papers]
    for source in sources:
        case.store.stage(attempt, source, elapsed_seconds=2)
    now = datetime.now(timezone.utc)
    with sqlite3.connect(case.storage._path) as db:
        db.execute("UPDATE preparation_jobs SET updated_at=?,lease_expires=? WHERE id=?",
            ((now - timedelta(seconds=20)).isoformat(), (now + timedelta(seconds=90)).isoformat(), job.id))
    before = case.engine.get_workspace(case.handle).model_dump_json()
    with pytest.raises(MvpError) as failure:
        _publish_staged(case, attempt, sources)
    assert failure.value.code == "preparation_runtime_limit"
    # Match the worker's failure receipt after the atomic publication rolls back.
    case.store.finish_failure(attempt, failure.value)
    assert case.engine.get_workspace(case.handle).model_dump_json() == before
    assert case.engine.get_workspace(case.handle).preparations[-1].id == old.id
    final = view(case, job)
    assert final.status == "failed" and final.error.code == "preparation_runtime_limit"
    assert final.progress_completed == 3 and final.result_preparation_id is None
    with sqlite3.connect(case.storage._path) as db:
        assert db.execute("SELECT COUNT(*) FROM mvp_requests WHERE operation='prepare_job_v1'").fetchone()[0] == 0


def test_success_records_final_elapsed_and_historical_replay_does_not_reage_it(tmp_path):
    case = case_for(tmp_path)
    case.store.max_runtime_seconds = 10
    job = submit(case)
    attempt = case.store.claim("active-owner", lease_seconds=90)
    sources = [case.provider.prepare(paper) for paper in case.search.papers]
    for source in sources:
        case.store.stage(attempt, source, elapsed_seconds=2)
    with sqlite3.connect(case.storage._path) as db:
        db.execute("UPDATE preparation_jobs SET updated_at=? WHERE id=?",
            ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), job.id))
    published = _publish_staged(case, attempt, sources)
    completed = view(case, job)
    assert completed.status == "succeeded" and 3 <= completed.elapsed_seconds < 10
    newer = case.engine.prepare_sources(case.handle, PrepareSourcesRequest(request_id="newer", search_id=case.search.id,
        paper_ids=[case.search.papers[-1].id]))
    with sqlite3.connect(case.storage._path) as db:
        db.execute("UPDATE preparation_jobs SET updated_at='2000-01-01T00:00:00+00:00' WHERE id=?", (job.id,))
    before = case.engine.get_workspace(case.handle).model_dump_json()
    assert _publish_staged(case, attempt, sources) == published
    assert view(case, job).elapsed_seconds == completed.elapsed_seconds
    assert case.engine.get_workspace(case.handle).model_dump_json() == before
    assert case.engine.get_workspace(case.handle).preparations[-1].id == newer.id


def test_stopping_a_slow_provider_retains_os_ownership_until_thread_exits(tmp_path):
    case = case_for(tmp_path)
    case.provider.block_on_call = 1
    submit(case)
    replacement = PreparationWorker(case.jobs, modes=("saved_example",), heartbeat_seconds=.05, lease_seconds=5)
    try:
        assert case.worker.start()
        assert case.provider.entered.wait(timeout=3)
        assert replacement.start() is False
        case.worker.stop()
        assert case.worker._thread.is_alive()
        assert replacement.start() is False, "A stopping but active provider thread still owns its process lock"
        case.provider.release.set()
        case.worker._thread.join(timeout=3)
        assert not case.worker._thread.is_alive()
        assert replacement.start()
    finally:
        case.provider.release.set()
        case.worker.stop()
        replacement.stop()


def test_per_paper_failures_and_unavailable_sources_do_not_erase_success(tmp_path):
    provider = SyntheticProvider(3)
    provider.fail_ids.add(provider.papers[1].id)
    provider.unavailable_ids.add(provider.papers[2].id)
    case = case_for(tmp_path, provider)
    job = submit(case)
    assert case.worker.run_once()
    final = view(case, job)
    state = case.engine.get_workspace(case.handle)
    assert final.status == "succeeded" and final.progress_completed == 3
    assert [outcome.outcome for outcome in final.outcomes] == ["abstract_only", "failed", "unavailable"]
    assert final.outcomes[1].error is not None and final.outcomes[1].error.code == "fixture_timeout"
    assert state.sources[0].blocks and state.sources[1].source_type == "abstract" and state.sources[2].source_type == "none"
    assert len(state.preparations[-1].errors) == 1


def test_domain_publication_failure_rolls_back_job_success_and_sources_together(tmp_path):
    case = case_for(tmp_path)
    before = case.engine.get_workspace(case.handle).model_dump_json()
    job = submit(case)
    with sqlite3.connect(case.storage._path) as db:
        db.execute("CREATE TRIGGER fail_preparation_publication BEFORE UPDATE ON mvp_workspaces BEGIN SELECT RAISE(ABORT, 'SYNTHETIC PUBLICATION FAILURE'); END")
    assert case.worker.run_once()
    assert case.engine.get_workspace(case.handle).model_dump_json() == before
    failed = view(case, job)
    assert failed.status == "failed" and failed.result_preparation_id is None and failed.result_source_revision is None
    assert failed.progress_completed == 3
    with sqlite3.connect(case.storage._path) as db:
        assert db.execute("SELECT COUNT(*) FROM mvp_requests WHERE operation LIKE '%prepar%'").fetchone()[0] == 0


def test_quota_failure_preserves_the_previous_preparation(tmp_path):
    case = case_for(tmp_path)
    old = case.engine.prepare_sources(case.handle, PrepareSourcesRequest(request_id="old", search_id=case.search.id,
        paper_ids=[case.search.papers[0].id]))
    before = case.engine.get_workspace(case.handle).model_dump_json()
    job = submit(case)
    case.storage._max_workspace_bytes = 1
    assert case.worker.run_once()
    assert case.engine.get_workspace(case.handle).model_dump_json() == before
    final = view(case, job)
    assert final.status == "failed" and final.result_preparation_id is None
    assert case.engine.get_workspace(case.handle).preparations[-1].id == old.id


def test_public_thirty_fulltexts_refresh_and_reopen_fit_retained_quota(tmp_path):
    case = case_for(tmp_path, SavedExampleProvider())
    assert len(case.search.papers) == 30
    before = case.engine.prepare_sources(case.handle, PrepareSourcesRequest(request_id="one-paper-baseline", search_id=case.search.id,
        paper_ids=[case.search.papers[0].id]))
    old_run = case.engine.retrieve_evidence(case.handle, RetrieveEvidenceRequest(request_id="old-run", question="microbiome diversity"))
    assert old_run.passages
    reference = SourceContextRequest(run_id=old_run.id, passage_id=old_run.passages[0].id)
    original_context = case.engine.get_source_context(case.handle, reference)
    measured = []
    for key in ("thirty-initial", "thirty-refresh"):
        job = submit(case, request_for(case, key))
        assert case.worker.run_once()
        final = view(case, job)
        assert final.status == "succeeded", final.model_dump(mode="json")
        state = case.engine.get_workspace(case.handle)
        assert len(state.sources) == 30 and all(source.source_type == "full_text" for source in state.sources)
        assert all(source.license and source.retained_content_utf8 for source in state.sources)
        for _ in range(3):
            reopened = SQLiteWorkspaceStorage(case.storage._path).read(case.handle)
            assert reopened.model_dump_json() == state.model_dump_json()
        with sqlite3.connect(case.storage._path) as db:
            snapshot_bytes = db.execute("SELECT length(CAST(snapshot AS BLOB)) FROM mvp_workspaces WHERE id=?", (case.handle.workspace_id,)).fetchone()[0]
            request_bytes = db.execute("SELECT COALESCE(SUM(length(CAST(result AS BLOB))),0) FROM mvp_requests WHERE workspace_id=?", (case.handle.workspace_id,)).fetchone()[0]
            page_size = db.execute("PRAGMA page_size").fetchone()[0]
            page_count = db.execute("PRAGMA page_count").fetchone()[0]
            auxiliary_bytes = preparation_auxiliary_bytes(db, case.handle.workspace_id)
        measured.append({"phase": key, "source_bytes": sum(len(source.model_dump_json().encode()) for source in state.sources),
            "snapshot_bytes": snapshot_bytes, "request_result_bytes": request_bytes, "auxiliary_bytes": auxiliary_bytes,
            "sqlite_allocated_bytes": page_size * page_count})
        assert snapshot_bytes + request_bytes + auxiliary_bytes <= 64 * 1024 * 1024
        assert auxiliary_bytes <= 32 * 1024 * 1024
        assert case.storage._max_workspace_bytes == 64 * 1024 * 1024
        assert case.engine.get_historical_source_context(case.handle, reference).model_dump_json() == original_context.model_dump_json()
    assert len(state.preparations) == 3 and state.preparations[0] == before
    assert state.source_revision == 3
    exported = case.engine.export_workspace(case.handle)
    audit = json.loads(exported.json_text)
    assert audit["schema_version"] == "mvp.audit-bundle.v1"
    assert len(audit["workspace"]["sources"]) == 30
    assert audit["workspace"]["preparations"][-1]["selected_paper_ids"] == [paper.id for paper in case.search.papers]
    assert old_run.passages[0].anchor.quote in [row["quotation"] for row in csv.DictReader(io.StringIO(exported.csv_text))]
    print("PREPARATION_OFFLINE_30_FOOTPRINT=" + json.dumps(measured, sort_keys=True))
