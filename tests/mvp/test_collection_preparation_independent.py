"""Independent collection queue/provenance checks; synthetic retained metadata."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import csv
import io
import socket
import threading

import pytest
from pydantic import ValidationError

from src.mvp.adapters.collection_preparation_storage import CollectionPreparationStore
from src.mvp.adapters.collection_storage import CollectionStore
from src.mvp.adapters.europe_pmc import fallback_source
from src.mvp.adapters.preparation_storage import PreparationStore
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.collection_contracts import ImportCommitRequest, ImportEditRowRequest
from src.mvp.collection_preparation_contracts import CollectionPreparationJobRequest
from src.mvp.collection_preparation_jobs import CollectionPreparationJobService
from src.mvp.collections import CollectionService
from src.mvp.contracts import Block, CreateWorkspaceRequest, Paper, PreparedSource, PrepareSourcesRequest, SearchPreview, SearchRequest
from src.mvp.preparation_contracts import PreparationJobRequest
from src.mvp.preparation_jobs import PreparationJobService, PreparationWorker
from src.mvp.ports import MvpError, ProviderFailure
from src.mvp.service import MVPService
from src.mvp.workspace_ui import WorkspaceUIStore
from src.mvp.workspace_versions import original_workspace_bytes


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Collection preparation attempted provider network access")
    monkeypatch.setattr(socket, "create_connection", denied)


class LocalProvider:
    def __init__(self):
        self.paper = Paper(pmid="840001", title="SYNTHETIC LEGACY SEARCH PAPER", abstract="Legacy microbiome evidence.")
        self.calls = []
        self.entered, self.release = threading.Event(), threading.Event()
        self.block = False
        self.failure = False
        self.use_actual_fallback = False

    def search(self, request):
        return SearchPreview(query=request.query, papers=[self.paper], fetched_count=1, total_reported=1,
            ordered_identifiers=[self.paper.id], provider="synthetic-legacy", mode="test", truncated=False)

    def prepare(self, paper):
        self.calls.append(paper.id)
        if self.block and paper.id != self.paper.id:
            self.entered.set()
            assert self.release.wait(timeout=8)
        if self.failure:
            raise ProviderFailure("synthetic_unavailable", "Synthetic provider failure", True)
        if self.use_actual_fallback:
            return fallback_source(paper, "abstract_only" if paper.abstract else "no_usable_text",
                "Synthetic test: retained citation only; no provider request was made.", provider="europe_pmc")
        return PreparedSource(paper_id=paper.id, status="abstract_only" if paper.abstract else "no_usable_text",
            source_type="abstract" if paper.abstract else "none", provider="pubmed_abstract", source_url="",
            source_identifiers={key: value for key, value in (("doi", paper.doi), ("pmid", paper.pmid)) if value},
            blocks=[Block(id="abstract:1", ordinal=1, text=paper.abstract, locator={"type": "abstract"})] if paper.abstract else [])


def make_case(path, count=3):
    provider = LocalProvider()
    storage = SQLiteWorkspaceStorage(path / "research.sqlite3")
    engine = MVPService(storage, provider, provider)
    registry = WorkspaceUIStore(path / "registry.sqlite3")
    _, session = registry.session()
    handle = registry.create_workspace(session["token_hash"], "workspace", {"mode": "saved_example"},
        lambda reserved: engine.create_reserved_workspace(reserved, CreateWorkspaceRequest(question="Synthetic collection workflow")))
    search = engine.search_literature(handle, SearchRequest(request_id="search", query="Original synthetic strategy"))
    collections = CollectionService(engine, CollectionStore(storage))
    text = io.StringIO(newline="")
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(["Title", "DOI", "Abstract Note"])
    for index in range(count):
        writer.writerow([f"Synthetic imported report {index}", f"10.1234/collection-{index}" if index else "",
            f"Imported microbiome diversity evidence for report {index}." if index != 2 else ""])
    imported = collections.upload(handle, text.getvalue().encode(), "csv", "upload", filename="synthetic.csv")
    rows = collections.import_rows(handle, imported.id, limit=50).rows
    summary = collections.commit_import(handle, imported.id, ImportCommitRequest(request_id="commit", expected_revision=imported.revision,
        name="Synthetic imported collection", accepted_row_ids=[row.id for row in rows]))
    store, old_store = CollectionPreparationStore(storage), PreparationStore(storage)
    jobs = CollectionPreparationJobService(registry, lambda mode: engine, lambda mode: store, lambda mode: collections)
    legacy_jobs = PreparationJobService(registry, lambda mode: engine, lambda mode: old_store)
    worker = PreparationWorker(jobs, modes=("saved_example",), heartbeat_seconds=.05, lease_seconds=5)
    return SimpleNamespace(path=path, provider=provider, storage=storage, engine=engine, registry=registry, handle=handle,
        session=session, search=search, collections=collections, imported=imported, collection=summary,
        rows=rows, store=store, old_store=old_store, jobs=jobs, legacy_jobs=legacy_jobs, worker=worker)


def request_for(case, key="collection-job", ids=None):
    state = case.engine.get_workspace(case.handle)
    return CollectionPreparationJobRequest(request_id=key, collection_ref=case.collection.origin,
        paper_ids=ids if ids is not None else [paper.id for paper in case.collections.papers(case.handle, case.collection.id, limit=50).papers],
        expected_source_revision=state.source_revision, expected_preparation_id=state.preparations[-1].id if state.preparations else None)


def job_view(case, identifier):
    return case.jobs.job("saved_example", case.handle, identifier)


@pytest.mark.parametrize("ids", [[], [str(index) for index in range(31)], ["duplicate", "duplicate"]])
def test_collection_selection_rejects_empty_duplicate_or_over_thirty_inputs(ids):
    with pytest.raises(ValidationError):
        CollectionPreparationJobRequest(request_id="invalid", collection_ref={"kind": "collection", "collection_id": "snapshot",
            "collection_snapshot_sha256": "a" * 64}, paper_ids=ids, expected_source_revision=0)


@pytest.mark.parametrize("count", [1, 30])
def test_collection_jobs_preserve_order_input_provenance_and_original_search_history(tmp_path, count):
    case = make_case(tmp_path, count)
    case.provider.use_actual_fallback = count == 30
    history = [search.model_dump_json() for search in case.engine.get_workspace(case.handle).searches]
    with case.storage._connection() as db:
        original_payload = db.execute("SELECT snapshot FROM mvp_workspaces WHERE id=?", (case.handle.workspace_id,)).fetchone()[0].encode()
    assert original_workspace_bytes(case.storage, case.handle) is None
    ids = list(reversed(request_for(case).paper_ids))
    request = request_for(case, ids=ids)
    submission = case.jobs.submit("saved_example", case.handle, request)
    assert submission.job.status == "queued" and case.provider.calls == []
    assert case.jobs.submit("saved_example", case.handle, request).reused
    assert case.worker.run_once()
    result = job_view(case, submission.job.id)
    assert result.status == "succeeded", result.model_dump_json()
    state = case.engine.get_workspace(case.handle)
    prepared = state.preparations[-1]
    assert prepared.schema_version == "mvp.collection-preparation.v2" and prepared.search_id is None
    assert prepared.collection_ref == case.collection.origin and prepared.selected_paper_ids == ids
    assert [source.paper_id for source in prepared.sources] == ids == case.provider.calls
    assert [search.model_dump_json() for search in state.searches] == history
    assert all(source.provider == "imported_abstract" for source in prepared.sources)
    if count == 30:
        unavailable = [source for source in prepared.sources if source.source_type == "none"]
        assert len(unavailable) == 1 and unavailable[0].blocks == []
        assert any(outcome.outcome == "unavailable" for outcome in result.outcomes)
    for source in prepared.sources:
        origin = source.parser_metadata
        assert origin["collection_ref"] == case.collection.origin.model_dump(mode="json")
        assert origin["metadata_version_id"] and origin["metadata_snapshot_sha256"]
        assert origin["member_origins"][0]["kind"] == "import_row"
        assert origin["retrieval_attempt_provider"] == ("europe_pmc" if count == 30 else "pubmed_abstract")
    reopened = MVPService(SQLiteWorkspaceStorage(case.storage._path), case.provider, case.provider)
    assert reopened.get_workspace(case.handle).preparations[-1] == prepared
    assert original_workspace_bytes(reopened._storage, case.handle) == original_payload


def test_newly_fetched_provider_abstract_is_not_relabelled_as_a_file_abstract(tmp_path, monkeypatch):
    case = make_case(tmp_path, 1)
    case.jobs.submit("saved_example", case.handle, request_for(case))
    captured = case.store.input(case.store.claim("provenance-check"))
    paper = captured.papers[0]
    fresh_paper = paper.model_copy(update={"abstract": "Synthetic freshly fetched provider abstract."})
    source = fallback_source(fresh_paper, "abstract_only", "Synthetic fresh response; no network.", provider="europe_pmc",
        abstract_provenance={"origin": "europe_pmc_core_abstract"})
    monkeypatch.setattr(case.provider, "prepare", lambda selected: source)
    prepared = case.jobs.prepare(case.engine, paper, captured)
    assert prepared.provider == "europe_pmc" and prepared.parser_metadata["origin"] == "europe_pmc_core_abstract"
    assert "member_origins" not in prepared.parser_metadata
    assert prepared.blocks[0].text == fresh_paper.abstract


@pytest.mark.parametrize("invalid", ["foreign_paper", "foreign_digest", "stale_revision"])
def test_collection_input_ownership_and_cas_reject_before_fetching(tmp_path, invalid):
    case = make_case(tmp_path)
    request = request_for(case)
    if invalid == "foreign_paper": request = request.model_copy(update={"paper_ids": [case.search.papers[0].id]})
    elif invalid == "foreign_digest": request = request.model_copy(update={"collection_ref": request.collection_ref.model_copy(update={"collection_snapshot_sha256": "0" * 64})})
    else: request = request.model_copy(update={"expected_source_revision": 99})
    before = case.engine.get_workspace(case.handle).model_dump_json()
    with pytest.raises(MvpError):
        case.jobs.submit("saved_example", case.handle, request)
    assert case.provider.calls == [] and case.jobs.listing("saved_example", case.handle).jobs == []
    assert case.engine.get_workspace(case.handle).model_dump_json() == before


def test_new_import_metadata_revision_does_not_retarget_an_older_queued_collection(tmp_path):
    case = make_case(tmp_path)
    job = case.jobs.submit("saved_example", case.handle, request_for(case)).job
    row = case.rows[0]
    edited = case.collections.edit_row(case.handle, case.imported.id, ImportEditRowRequest(request_id="later-edit", expected_revision=case.imported.revision,
        row_id=row.id, metadata=row.metadata.model_copy(update={"title": "A later title", "abstract": "A later abstract must not replace this queued input."})))
    case.collections.commit_import(case.handle, case.imported.id, ImportCommitRequest(request_id="later-commit", expected_revision=edited.revision,
        name="Later collection revision", accepted_row_ids=[item.id for item in case.rows]))
    assert case.worker.run_once()
    assert job_view(case, job.id).status == "succeeded"
    prepared = case.engine.get_workspace(case.handle).preparations[-1]
    assert prepared.collection_ref == case.collection.origin
    assert any("Imported microbiome diversity evidence for report 0." in block.text for source in prepared.sources for block in source.blocks)
    assert all("later abstract" not in block.text for source in prepared.sources for block in source.blocks)


def test_validated_staging_restarts_without_fetching_an_already_retained_paper(tmp_path):
    case = make_case(tmp_path)
    job = case.jobs.submit("saved_example", case.handle, request_for(case)).job
    attempt = case.store.claim("synthetic-dead-worker", lease_seconds=90)
    captured = case.store.input(attempt)
    case.store.stage(attempt, case.jobs.prepare(case.engine, captured.papers[0], captured))
    assert case.provider.calls == captured.paper_ids[:1]
    case.store.recover()  # The test deliberately simulates an abruptly exited owner.
    assert case.worker.run_once()
    finished = job_view(case, job.id)
    assert finished.status == "succeeded" and finished.attempt == 2 and finished.interrupted_count == 1
    assert case.provider.calls == captured.paper_ids


def test_cancelled_collection_fetch_keeps_the_previous_legacy_preparation(tmp_path):
    case = make_case(tmp_path)
    old = case.engine.prepare_sources(case.handle, PrepareSourcesRequest(request_id="legacy-prepare", search_id=case.search.id,
        paper_ids=[case.search.papers[0].id]))
    before = case.engine.get_workspace(case.handle).model_dump_json()
    case.provider.block = True
    job = case.jobs.submit("saved_example", case.handle, request_for(case)).job
    with ThreadPoolExecutor(max_workers=2) as pool:
        work = pool.submit(case.worker.run_once)
        assert case.provider.entered.wait(timeout=2)
        try:
            cancelled = pool.submit(case.jobs.cancel, "saved_example", case.handle, job.id).result(timeout=2)
            assert cancelled.status == "cancel_requested"
        finally:
            case.provider.release.set()
        assert work.result(timeout=3)
    assert job_view(case, job.id).status == "cancelled"
    assert case.engine.get_workspace(case.handle).model_dump_json() == before
    assert case.engine.get_workspace(case.handle).preparations[-1] == old


def test_new_legacy_preparation_makes_an_inflight_collection_job_stale(tmp_path):
    case = make_case(tmp_path)
    case.provider.block = True
    job = case.jobs.submit("saved_example", case.handle, request_for(case)).job
    with ThreadPoolExecutor(max_workers=2) as pool:
        work = pool.submit(case.worker.run_once)
        assert case.provider.entered.wait(timeout=2)
        try:
            replacement = pool.submit(case.engine.prepare_sources, case.handle, PrepareSourcesRequest(request_id="legacy-replacement",
                search_id=case.search.id, paper_ids=[case.search.papers[0].id])).result(timeout=2)
            before = case.engine.get_workspace(case.handle).model_dump_json()
        finally:
            case.provider.release.set()
        assert work.result(timeout=3)
    assert job_view(case, job.id).status == "stale"
    assert case.engine.get_workspace(case.handle).model_dump_json() == before
    assert case.engine.get_workspace(case.handle).preparations[-1] == replacement
    assert original_workspace_bytes(case.storage, case.handle) is None


def test_deletion_during_collection_fetch_cannot_publish_or_resurrect_rows(tmp_path):
    case = make_case(tmp_path)
    case.provider.block = True
    case.jobs.submit("saved_example", case.handle, request_for(case))
    with ThreadPoolExecutor(max_workers=2) as pool:
        work = pool.submit(case.worker.run_once)
        assert case.provider.entered.wait(timeout=2)
        try:
            pool.submit(case.engine.clear_workspace, case.handle).result(timeout=2)
        finally:
            case.provider.release.set()
        assert work.result(timeout=3)
    with pytest.raises(MvpError):
        case.engine.get_workspace(case.handle)
    with case.storage._connection() as db:
        for table in ("collection_preparation_jobs", "collection_preparation_requests", "collection_preparation_stages"):
            assert db.execute(f"SELECT COUNT(*) FROM {table} WHERE workspace_id=?", (case.handle.workspace_id,)).fetchone()[0] == 0


def test_two_queue_domains_share_one_production_os_owner_per_database(tmp_path):
    case = make_case(tmp_path)
    mixed = PreparationWorker(case.legacy_jobs, additional_domains=(case.jobs,), modes=("saved_example",),
        heartbeat_seconds=.05, lease_seconds=5)
    collection_only = PreparationWorker(case.jobs, modes=("saved_example",), heartbeat_seconds=.05, lease_seconds=5)
    try:
        assert mixed.start()
        assert len(mixed._descriptors) == 1 and len(mixed._owned_stores) == 2
        assert not collection_only.start()
        mixed.stop()
        assert collection_only.start()
    finally:
        mixed.stop()
        collection_only.stop()
    assert case.provider.calls == []


def test_legacy_and_collection_jobs_share_the_total_job_budget(tmp_path):
    case = make_case(tmp_path)
    case.old_store.max_jobs = case.store.max_jobs = 2
    legacy = PreparationJobRequest(request_id="legacy-one", search_id=case.search.id,
        paper_ids=[case.search.papers[0].id], expected_source_revision=0)
    case.legacy_jobs.submit("saved_example", case.handle, legacy)
    case.jobs.submit("saved_example", case.handle, request_for(case))
    with pytest.raises(MvpError):
        case.legacy_jobs.submit("saved_example", case.handle, legacy.model_copy(update={"request_id": "legacy-too-many"}))
    assert len(case.legacy_jobs.listing("saved_example", case.handle).jobs) == len(case.jobs.listing("saved_example", case.handle).jobs) == 1
    assert case.provider.calls == []


def test_failed_atomic_publication_keeps_legacy_current_and_never_records_success(tmp_path, monkeypatch):
    case = make_case(tmp_path)
    old = case.engine.prepare_sources(case.handle, PrepareSourcesRequest(request_id="legacy-prepare", search_id=case.search.id,
        paper_ids=[case.search.papers[0].id]))
    before = case.engine.get_workspace(case.handle).model_dump_json()
    job = case.jobs.submit("saved_example", case.handle, request_for(case)).job
    publish = case.engine.publish_collection_preparation_job
    publications = []
    def observed_publication(**kwargs):
        publications.append(kwargs["job_id"])
        return publish(**kwargs)
    monkeypatch.setattr(case.engine, "publish_collection_preparation_job", observed_publication)
    with case.storage._connection() as db:
        db.execute("CREATE TRIGGER synthetic_collection_failure BEFORE UPDATE ON mvp_workspaces BEGIN SELECT RAISE(ABORT, 'SYNTHETIC COLLECTION FAILURE'); END")
    assert case.worker.run_once()
    assert publications == [job.id], "The failure must actually reach the guarded publication transaction"
    finished = job_view(case, job.id)
    assert finished.status == "failed" and finished.result_preparation_id is None
    assert case.engine.get_workspace(case.handle).model_dump_json() == before
    assert case.engine.get_workspace(case.handle).preparations[-1] == old
