"""Independent immutable-ingestion checks over synthetic local workspaces."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import csv
import io
import socket
import threading

import pytest

from src.mvp.adapters.collection_storage import CollectionStore
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.collection_contracts import (CollectionInputRef, CollectionSourceSelection, CombineCollectionsRequest,
    ImportCommitRequest, ImportEditRowRequest, ImportMappingRequest, ImportResolveRequest)
from src.mvp.collections import CollectionService
from src.mvp.contracts import Paper, SearchPreview, SearchRequest, WorkspaceHandle, digest
from src.mvp.import_contracts import CitationMetadata, ResolutionBatch, ResolutionReceipt
from src.mvp.ports import MvpError
from src.mvp.service import MVPService


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Collection tests attempted external network access")
    monkeypatch.setattr(socket, "create_connection", denied)


def csv_bytes(headers, rows):
    text = io.StringIO(newline="")
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return text.getvalue().encode()


class LocalProviders:
    def __init__(self):
        self.search_calls, self.source_calls = 0, 0
        self.papers = [Paper(pmid=str(810000 + index), title=f"SYNTHETIC SAVED SEARCH {index}",
            abstract="Supplied saved-search abstract.") for index in range(2)]

    def search(self, request):
        self.search_calls += 1
        return SearchPreview(query=request.query, papers=self.papers, total_reported=100, fetched_count=2,
            ordered_identifiers=[paper.id for paper in self.papers], truncated=True, mode="test", provider="synthetic-discovery")

    def prepare(self, paper):
        self.source_calls += 1
        raise AssertionError("C1 ingestion must not prepare sources")


class StubResolver:
    def __init__(self, status="resolved"):
        self.calls = []
        self.status = status
        self.entered, self.release = threading.Event(), threading.Event()
        self.block = False
        self.transform = None

    def resolve(self, inputs, **kwargs):
        self.calls.append([item.model_dump(mode="json") for item in inputs])
        if self.block:
            self.entered.set()
            assert self.release.wait(timeout=6)
        receipts = []
        for item in inputs:
            requested = {key: getattr(item, key) for key in ("doi", "pmid", "pmcid") if getattr(item, key)}
            returned = dict(requested)
            if self.status == "conflict":
                returned["doi"] = "10.1234/wrong-report"
            metadata = CitationMetadata(title="Resolved metadata title", doi=returned.get("doi"), pmid=returned.get("pmid"),
                pmcid=returned.get("pmcid"), abstract="Resolved provider abstract.") if self.status != "unresolved" else None
            receipts.append(ResolutionReceipt(row_id=item.row_id, status=self.status, provider="crossref" if self.status != "unresolved" else "none",
                requested_identifiers=requested, returned_identifiers=returned if metadata else {}, metadata=metadata,
                response_sha256="a" * 64 if metadata else None, retrieved_at="2026-10-22T00:00:00+00:00", abstract_origin="crossref" if metadata else None))
        batch = ResolutionBatch(items=receipts, elapsed_seconds=.01, calls=len(inputs))
        return self.transform(batch) if self.transform else batch


@pytest.fixture
def case(tmp_path):
    provider = LocalProviders()
    engine = MVPService(SQLiteWorkspaceStorage(tmp_path / "research.sqlite3"), provider, provider)
    handle = engine.create_workspace()
    search = engine.search_literature(handle, SearchRequest(request_id="saved-search", query="synthetic saved strategy"))
    resolver = StubResolver()
    store = CollectionStore(engine._storage)
    service = CollectionService(engine, store, resolver=resolver)
    return SimpleNamespace(path=tmp_path, provider=provider, engine=engine, handle=handle, search=search,
        resolver=resolver, store=store, service=service)


def upload(case, rows, headers=("Title", "DOI", "Abstract Note"), key="upload"):
    return case.service.upload(case.handle, csv_bytes(headers, rows), "csv", key, filename="citations.csv")


def rows_of(case, imported):
    return case.service.import_rows(case.handle, imported.id, limit=50).rows


def commit(case, imported, rows=None, key="commit", **kwargs):
    accepted = [row.id for row in rows_of(case, imported)] if rows is None else rows
    return case.service.commit_import(case.handle, imported.id, ImportCommitRequest(request_id=key,
        expected_revision=imported.revision, name="Synthetic imported collection", accepted_row_ids=accepted, **kwargs))


def test_import_commit_preserves_exact_origin_unknown_search_metadata_and_legacy_state(case):
    before = case.engine.get_workspace(case.handle).model_dump_json()
    imported = upload(case, [["Imported paper", "10.1234/imported", "Imported abstract."]])
    assert imported.row_count == imported.ready_count == 1 and case.resolver.calls == []
    saved = commit(case, imported)
    assert saved.kind == "import" and saved.member_count == 1 and saved.origin.kind == "collection"
    assert saved.origin.collection_id == saved.id
    assert all(value is None for value in saved.search_metadata.model_dump().values())
    page = case.service.papers(case.handle, saved.id)
    detail = case.service.paper(case.handle, saved.id, page.papers[0].id)
    member = detail.member
    assert member.paper.title == "Imported paper" and member.paper.abstract == "Imported abstract."
    assert member.metadata_version.abstract_provider == "imported_abstract"
    origin = member.origins[0]
    assert origin.kind == "import_row" and origin.import_id == imported.id and origin.row_number == 1
    assert origin.file_sha256 == imported.file_sha256 and origin.supplied_metadata_sha256
    assert origin.search_id is None
    assert case.engine.get_workspace(case.handle).model_dump_json() == before
    assert case.provider.search_calls == 1 and case.provider.source_calls == 0 and case.resolver.calls == []


def test_upload_commit_and_edit_requests_are_idempotent_and_cas_preserves_edits(case):
    payload = csv_bytes(["Title", "DOI"], [["First supplied title", "10.1234/cas"]])
    first = case.service.upload(case.handle, payload, "csv", "same-upload")
    assert case.service.upload(case.handle, payload, "csv", "same-upload").id == first.id
    with pytest.raises(MvpError):
        case.service.upload(case.handle, payload + b"\n", "csv", "same-upload")
    row = rows_of(case, first)[0]
    request = ImportEditRowRequest(request_id="edit", expected_revision=first.revision, row_id=row.id,
        metadata=row.metadata.model_copy(update={"title": "Explicit human metadata edit"}))
    edited = case.service.edit_row(case.handle, first.id, request)
    assert case.service.edit_row(case.handle, first.id, request).revision == edited.revision
    with pytest.raises(MvpError):
        case.service.edit_row(case.handle, first.id, request.model_copy(update={"request_id": "stale-edit"}))
    assert rows_of(case, edited)[0].metadata.title == "Explicit human metadata edit"
    saved = commit(case, edited, [row.id])
    assert commit(case, edited, [row.id]).id == saved.id
    assert case.service.papers(case.handle, saved.id).papers[0].title == "Explicit human metadata edit"


def test_doi_only_requires_explicit_resolution_and_does_not_fabricate_a_title(case):
    imported = case.service.upload(case.handle, b"doi:10.1234/pending\n", "identifiers", "identifiers")
    pending = rows_of(case, imported)[0]
    assert pending.status == "pending" and pending.metadata.title == "" and case.resolver.calls == []
    with pytest.raises(MvpError):
        commit(case, imported)
    resolved = case.service.resolve_metadata(case.handle, imported.id, ImportResolveRequest(request_id="resolve",
        expected_revision=imported.revision, row_ids=[pending.id]))
    result = rows_of(case, resolved)[0]
    assert result.metadata.title == "Resolved metadata title" and result.supplied_metadata.title == ""
    assert result.resolution_receipts[0].provider == "crossref"
    saved = commit(case, resolved)
    detail = case.service.paper(case.handle, saved.id, case.service.papers(case.handle, saved.id).papers[0].id)
    assert detail.member.metadata_version.abstract_provider == "crossref"
    assert any(origin.kind == "resolved_identifier" for origin in detail.member.origins)
    assert len(case.resolver.calls) == 1


@pytest.mark.parametrize("status", ["unresolved", "conflict"])
def test_failed_or_conflicting_resolution_never_creates_an_accepted_identity(case, status):
    case.resolver.status = status
    imported = case.service.upload(case.handle, b"10.1234/pending\n", "identifiers", "identifiers")
    row = rows_of(case, imported)[0]
    resolved = case.service.resolve_metadata(case.handle, imported.id, ImportResolveRequest(request_id="resolve",
        expected_revision=imported.revision, row_ids=[row.id]))
    current = rows_of(case, resolved)[0]
    assert current.supplied_metadata.doi == "10.1234/pending"
    assert current.metadata.doi == "10.1234/pending"
    assert current.status in {"pending", "conflict"}
    with pytest.raises(MvpError):
        commit(case, resolved)
    assert case.service.listing(case.handle).collections[0].kind == "saved_search"


def test_resolution_wait_has_no_workspace_lock_and_cannot_publish_over_an_edit(case):
    imported = case.service.upload(case.handle, b"10.1234/slow\n", "identifiers", "slow")
    row = rows_of(case, imported)[0]
    case.resolver.block = True
    request = ImportResolveRequest(request_id="resolve", expected_revision=imported.revision, row_ids=[row.id])
    with ThreadPoolExecutor(max_workers=2) as pool:
        work = pool.submit(case.service.resolve_metadata, case.handle, imported.id, request)
        assert case.resolver.entered.wait(timeout=2)
        try:
            edit = ImportEditRowRequest(request_id="human-edit", expected_revision=imported.revision, row_id=row.id,
                metadata=row.metadata.model_copy(update={"title": "Preserve this concurrent human title"}))
            edited = pool.submit(case.service.edit_row, case.handle, imported.id, edit).result(timeout=2)
        finally:
            case.resolver.release.set()
        with pytest.raises(MvpError):
            work.result(timeout=3)
    assert rows_of(case, edited)[0].metadata.title == "Preserve this concurrent human title"


def test_exact_duplicate_merge_is_reviewed_and_retains_both_origin_occurrences(case):
    imported = upload(case, [["Same supplied report", "10.1234/same", "Same abstract."],
                            ["Same supplied report", "https://doi.org/10.1234/SAME", "Same abstract."]])
    assert imported.row_count == 2 and imported.duplicate_groups
    with pytest.raises(MvpError):
        commit(case, imported)
    saved = commit(case, imported, duplicate_policy="merge_exact")
    assert saved.member_count == 1
    member = case.service.paper(case.handle, saved.id, case.service.papers(case.handle, saved.id).papers[0].id).member
    assert {origin.row_number for origin in member.origins if origin.kind == "import_row"} == {1, 2}


def test_top_level_row_overflow_cannot_be_committed_as_a_truncated_success(case):
    with pytest.raises(MvpError) as failure:
        upload(case, [[f"Synthetic {index}"] for index in range(501)], headers=("Title",))
    assert failure.value.code == "import_parse_error"
    assert case.service.imports(case.handle).imports == []


def test_conflicting_identifiers_need_an_explicit_keep_separate_decision(case):
    imported = upload(case, [["Report one", "10.1234/conflicted", "830001"],
                            ["Report two", "10.1234/conflicted", "830002"]], headers=("Title", "DOI", "PMID"))
    group = next(group for group in imported.duplicate_groups if group.kind == "identifier_conflict")
    with pytest.raises(MvpError):
        commit(case, imported, duplicate_policy="merge_exact")
    saved = commit(case, imported, duplicate_policy="merge_exact", conflict_decisions={group.id: "keep_separate"})
    papers = case.service.papers(case.handle, saved.id).papers
    assert saved.member_count == 2 and {paper.pmid for paper in papers} == {"830001", "830002"}
    assert len({paper.id for paper in papers}) == 2


def test_complete_remapping_does_not_reinstate_omitted_fields_or_change_old_members(case):
    imported = upload(case, [["First supplied title", "Alternate supplied title", "10.1234/remapping"]],
        headers=("Unmapped Title", "Other Title", "DOI"))
    assert rows_of(case, imported)[0].status == "pending"
    mapped = case.service.remap(case.handle, imported.id, ImportMappingRequest(request_id="map-one", expected_revision=imported.revision,
        mapping={"title": "Unmapped Title", "doi": "DOI"}))
    original = commit(case, mapped)
    first_paper = case.service.papers(case.handle, original.id).papers[0]
    assert first_paper.title == "First supplied title" and first_paper.doi == "10.1234/remapping"
    remapped = case.service.remap(case.handle, imported.id, ImportMappingRequest(request_id="map-two", expected_revision=mapped.revision,
        mapping={"title": "Other Title"}))
    current = rows_of(case, remapped)[0]
    assert current.metadata.title == "Alternate supplied title" and current.metadata.doi is None
    assert case.service.papers(case.handle, original.id).papers[0] == first_paper


@pytest.mark.parametrize("bad_receipt", ["missing_requested_identifier", "mismatching_metadata_identity", "unconfirmed_extra_metadata_identifier"])
def test_service_rejects_incomplete_or_internally_mismatching_resolved_receipts(case, bad_receipt):
    imported = upload(case, [["", "10.1234/pending", "830001"]], headers=("Title", "DOI", "PMID"))
    row = rows_of(case, imported)[0]
    def transform(batch):
        receipt = batch.items[0]
        if bad_receipt == "missing_requested_identifier":
            receipt = receipt.model_copy(update={"returned_identifiers": {"doi": "10.1234/pending"}})
        elif bad_receipt == "mismatching_metadata_identity":
            receipt = receipt.model_copy(update={"metadata": receipt.metadata.model_copy(update={"doi": "10.1234/other-report"})})
        else:
            receipt = receipt.model_copy(update={"metadata": receipt.metadata.model_copy(update={"pmcid": "PMC99999"})})
        return batch.model_copy(update={"items": [receipt]})
    case.resolver.transform = transform
    resolved = case.service.resolve_metadata(case.handle, imported.id, ImportResolveRequest(request_id="resolve-bad",
        expected_revision=imported.revision, row_ids=[row.id]))
    current = rows_of(case, resolved)[0]
    assert current.metadata.title == "" and current.metadata.doi == "10.1234/pending"
    assert current.status in {"pending", "conflict"}


def test_deletion_while_resolving_cannot_resurrect_the_import_or_workspace(case):
    imported = case.service.upload(case.handle, b"10.1234/deletion\n", "identifiers", "deletion")
    row = rows_of(case, imported)[0]
    case.resolver.block = True
    with ThreadPoolExecutor(max_workers=2) as pool:
        work = pool.submit(case.service.resolve_metadata, case.handle, imported.id, ImportResolveRequest(request_id="resolve-deleted",
            expected_revision=imported.revision, row_ids=[row.id]))
        assert case.resolver.entered.wait(timeout=2)
        try:
            pool.submit(case.engine.clear_workspace, case.handle).result(timeout=2)
        finally:
            case.resolver.release.set()
        with pytest.raises(MvpError):
            work.result(timeout=3)
    with pytest.raises(MvpError):
        case.service.imports(case.handle)
    with case.engine._storage._connection() as db:
        for table in ("mvp_ingestion_imports", "mvp_ingestion_versions", "mvp_collections", "mvp_ingestion_requests"):
            assert db.execute(f"SELECT COUNT(*) FROM {table} WHERE workspace_id=?", (case.handle.workspace_id,)).fetchone()[0] == 0


def test_import_capacity_rejection_rolls_back_all_new_rows_and_preserves_existing(case, monkeypatch):
    from src.mvp.adapters import collection_storage
    first = upload(case, [["First import", "10.1234/first", "First abstract."]])
    before = case.service.import_summary(case.handle, first.id).model_dump_json()
    monkeypatch.setattr(collection_storage, "MAX_IMPORTS", 1)
    with pytest.raises(MvpError) as failure:
        upload(case, [["Second import", "10.1234/second", "Second abstract."]], key="over-capacity")
    assert failure.value.code == "import_storage_limit"
    assert len(case.service.imports(case.handle).imports) == 1
    assert case.service.import_summary(case.handle, first.id).model_dump_json() == before


def test_committed_members_are_immutable_after_later_import_edits_and_combinations(case):
    imported = upload(case, [["Original title", "10.1234/immutable", "Original abstract."]])
    original = commit(case, imported)
    original_paper = case.service.papers(case.handle, original.id).papers[0]
    original_detail = case.service.paper(case.handle, original.id, original_paper.id).model_dump_json()
    row = rows_of(case, imported)[0]
    edited = case.service.edit_row(case.handle, imported.id, ImportEditRowRequest(request_id="edit-after-commit",
        expected_revision=imported.revision, row_id=row.id, metadata=row.metadata.model_copy(update={"title": "New human metadata revision"})))
    later = commit(case, edited, key="new-commit")
    assert later.id != original.id
    assert case.service.paper(case.handle, original.id, original_paper.id).model_dump_json() == original_detail
    before = case.engine.get_workspace(case.handle).model_dump_json()
    saved_search = next(item for item in case.service.listing(case.handle).collections if item.kind == "saved_search")
    assert saved_search.origin.search_id == case.search.id and saved_search.origin.search_snapshot_sha256 == digest(case.search.model_dump(mode="json"))
    combined = case.service.combine(case.handle, CombineCollectionsRequest(request_id="combine", name="Explicit combined inputs",
        sources=[CollectionSourceSelection(origin=saved_search.origin, paper_ids=[case.search.papers[0].id]),
                 CollectionSourceSelection(origin=original.origin)]))
    assert combined.kind == "combined" and combined.member_count == 2
    assert all(value is None for value in combined.search_metadata.model_dump().values())
    assert case.engine.get_workspace(case.handle).model_dump_json() == before
    assert case.service.paper(case.handle, original.id, original_paper.id).model_dump_json() == original_detail
    with pytest.raises(MvpError):
        case.service.resolve_collection(case.handle, CollectionInputRef(collection_id=original.id, collection_snapshot_sha256="0" * 64))


def test_large_collection_lists_all_records_with_pagination_and_stable_reopening(case):
    imported = upload(case, [[f"Synthetic record {index:03}"] for index in range(500)], headers=("Title",))
    ids = []
    for offset in range(0, 500, 50):
        page = case.service.import_rows(case.handle, imported.id, offset=offset, limit=50)
        assert page.total == 500
        ids.extend(row.id for row in page.rows)
    assert len(set(ids)) == 500
    saved = commit(case, imported, ids)
    found = []
    for offset in range(0, 500, 50):
        page = case.service.papers(case.handle, saved.id, offset=offset, limit=50)
        assert page.total == 500
        found.extend(paper.id for paper in page.papers)
    assert len(set(found)) == 500
    reopened_engine = MVPService(SQLiteWorkspaceStorage(case.engine._storage._path), case.provider, case.provider)
    reopened = CollectionService(reopened_engine, CollectionStore(reopened_engine._storage), resolver=case.resolver)
    assert reopened.papers(case.handle, saved.id, offset=450, limit=50) == case.service.papers(case.handle, saved.id, offset=450, limit=50)
    assert reopened.listing(case.handle).max_map_papers == 50 and reopened.listing(case.handle).max_prepared_sources == 30


def test_every_domain_resource_requires_the_actual_workspace_capability(case):
    imported = upload(case, [["Owned paper", "10.1234/owned", "Abstract."]])
    saved = commit(case, imported)
    bad = WorkspaceHandle(workspace_id=case.handle.workspace_id, token="incorrect-capability")
    operations = [lambda: case.service.imports(bad), lambda: case.service.import_summary(bad, imported.id),
        lambda: case.service.import_rows(bad, imported.id), lambda: case.service.listing(bad),
        lambda: case.service.papers(bad, saved.id), lambda: case.service.upload(bad, b"Title\nForeign\n", "csv", "foreign")]
    for operation in operations:
        with pytest.raises(MvpError):
            operation()
