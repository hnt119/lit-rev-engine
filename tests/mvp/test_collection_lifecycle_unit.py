"""Interrupted web deletion cannot admit late import/resolution publication."""
from concurrent.futures import ThreadPoolExecutor
import threading
from types import SimpleNamespace

import pytest

from src.mvp.adapters.collection_storage import CollectionStore
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.collection_contracts import ImportCommitRequest, ImportResolveRequest
from src.mvp.collections import CollectionService
from src.mvp.contracts import now
from src.mvp.import_contracts import ResolutionBatch, ResolutionReceipt
from src.mvp.ports import MvpError
from src.mvp.service import MVPService
from src.mvp.workspace_ui import WorkspaceUIStore


class NeverProviders:
    def search(self, request):
        raise AssertionError('No live search allowed')

    def prepare(self, paper):
        raise AssertionError('No source request allowed')


class BlockingResolver:
    def __init__(self):
        self.entered, self.release = threading.Event(), threading.Event()

    def resolve(self, inputs):
        self.entered.set()
        assert self.release.wait(4)
        return ResolutionBatch(items=[ResolutionReceipt(row_id=item.row_id, status='unresolved', provider='none',
            requested_identifiers={key: value for key in ('doi', 'pmid', 'pmcid') if (value := getattr(item, key))},
            retrieved_at=now()) for item in inputs], elapsed_seconds=.01, calls=0)


@pytest.fixture
def case(tmp_path):
    root = tmp_path.resolve()
    engine = MVPService(SQLiteWorkspaceStorage(root / 'research.sqlite3'), NeverProviders(), NeverProviders())
    handle = engine.create_workspace()
    registry = WorkspaceUIStore(root / 'credentials.sqlite3')
    registry.register_local_handle_for_worker('saved_example', handle, engine.get_workspace)
    resolver = BlockingResolver()
    service = CollectionService(engine, CollectionStore(engine._storage), resolver=resolver, registry=registry)
    return SimpleNamespace(engine=engine, handle=handle, registry=registry, service=service, resolver=resolver)


def tombstone(case):
    with case.registry.connection() as db:
        db.execute('INSERT INTO web_tombstones VALUES(?,?)', (case.handle.workspace_id, now()))


def imported(case):
    return case.service.upload(case.handle, b'Title,DOI\nPublic fixture,10.1234/fixture\n', 'csv', 'upload')


def test_tombstone_rejects_captured_handle_mutations_and_reads(case):
    with case.registry.lifecycle_guard(case.handle.workspace_id):
        tombstone(case)
    with pytest.raises(MvpError) as error:
        imported(case)
    assert error.value.code == 'unknown_workspace'
    with pytest.raises(MvpError):
        case.service.imports(case.handle)
    with case.service.store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM mvp_ingestion_imports').fetchone()[0] == 0


def test_collection_read_under_existing_worker_guard_does_not_reenter_flock(case):
    value = imported(case)
    rows = case.service.import_rows(case.handle, value.id)
    collection = case.service.commit_import(case.handle, value.id, ImportCommitRequest(
        request_id='commit', expected_revision=value.revision, name='Public fixture',
        accepted_row_ids=[rows.rows[0].id]))
    with case.registry.lifecycle_guard(case.handle.workspace_id):
        resolved = case.engine.with_workspace_state(case.handle,
            lambda state: case.service.resolve_collection(case.handle, collection.origin))
    assert resolved.summary.id == collection.id


def test_late_metadata_receipt_cannot_publish_after_tombstone_and_fetch_holds_no_guard(case):
    value = imported(case)
    rows = case.service.import_rows(case.handle, value.id)
    request = ImportResolveRequest(request_id='resolve', expected_revision=value.revision, row_ids=[rows.rows[0].id])
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(case.service.resolve_metadata, case.handle, value.id, request)
        assert case.resolver.entered.wait(2)
        # This would block if provider work retained the lifecycle/workspace locks.
        with case.registry.lifecycle_guard(case.handle.workspace_id):
            case.engine.with_workspace_state(case.handle, lambda state: state.id)
            tombstone(case)
        case.resolver.release.set()
        with pytest.raises(MvpError) as error:
            future.result(timeout=3)
    assert error.value.code == 'unknown_workspace'
    assert case.service.store.summary(case.handle.workspace_id, value.id).revision == value.revision
    assert case.service.store.document(case.handle.workspace_id, value.id).rows[0].resolution_receipts == []


def test_upload_that_finishes_parsing_after_tombstone_cannot_publish(case, monkeypatch):
    from src.mvp import collections
    entered, release = threading.Event(), threading.Event()
    original = collections.parse_import_bytes

    def parse(*args, **kwargs):
        result = original(*args, **kwargs)
        entered.set()
        assert release.wait(4)
        return result

    monkeypatch.setattr(collections, 'parse_import_bytes', parse)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(imported, case)
        assert entered.wait(2)
        with case.registry.lifecycle_guard(case.handle.workspace_id):
            tombstone(case)
        release.set()
        with pytest.raises(MvpError) as error:
            future.result(timeout=3)
    assert error.value.code == 'unknown_workspace'
    with case.service.store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM mvp_ingestion_imports').fetchone()[0] == 0
