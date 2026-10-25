"""Collection queue units; integration/publication is evaluated independently."""
from types import SimpleNamespace

import pytest

from src.mvp.adapters.collection_preparation_storage import CollectionPreparationStore
from src.mvp.adapters.collection_storage import CollectionStore
from src.mvp.adapters.europe_pmc import fallback_source
from src.mvp.adapters.preparation_storage import PreparationStore
from src.mvp.adapters.saved_examples import SavedExampleProvider
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.collection_contracts import ImportCommitRequest
from src.mvp.collection_preparation_contracts import CollectionPreparationJobRequest
from src.mvp.collection_preparation_jobs import CollectionPreparationJobService
from src.mvp.collections import CollectionService
from src.mvp.contracts import CreateWorkspaceRequest, SearchPreview, SearchRequest, Paper, digest
from src.mvp.ports import MvpError, ProviderFailure
from src.mvp.preparation_contracts import PreparationJobRequest
from src.mvp.preparation_jobs import PreparationJobService, PreparationWorker
from src.mvp.service import MVPService
from src.mvp.workspace_ui import WorkspaceUIStore


class OfflineProvider:
    def search(self, request):
        paper = Paper(title='Existing search record', pmid='123', abstract='Search abstract.')
        return SearchPreview(query=request.query, papers=[paper], ordered_identifiers=[paper.id],
            total_reported=1, fetched_count=1, provider='software-fixture', mode='test', truncated=False)

    def prepare(self, paper):
        raise ProviderFailure('offline_fixture', 'No live source request was made.')


def case_for(tmp_path, max_jobs=20, payload=None):
    provider = OfflineProvider()
    engine = MVPService(SQLiteWorkspaceStorage(tmp_path / 'research.sqlite3'), provider, provider)
    registry = WorkspaceUIStore(tmp_path / 'registry.sqlite3')
    _, session = registry.session()
    handle = registry.create_workspace(session['token_hash'], 'create', {'mode': 'saved_example'},
        lambda reserved: engine.create_reserved_workspace(reserved, CreateWorkspaceRequest()))
    collections = CollectionService(engine, CollectionStore(engine._storage))
    imported = collections.upload(handle, payload or b'Title,DOI,Abstract Note\nImported title,10.1234/imported,Imported source text.\n', 'csv', 'upload', filename='sources.csv')
    rows = collections.import_rows(handle, imported.id).rows
    collection = collections.commit_import(handle, imported.id, ImportCommitRequest(request_id='commit',
        expected_revision=1, name='Imported records', accepted_row_ids=[row.id for row in rows]))
    store = CollectionPreparationStore(engine._storage, max_jobs=max_jobs)
    legacy_store = PreparationStore(engine._storage, max_jobs=max_jobs)
    jobs = CollectionPreparationJobService(registry, lambda mode: engine, lambda mode: store, lambda mode: collections)
    legacy = PreparationJobService(registry, lambda mode: engine, lambda mode: legacy_store)
    request = CollectionPreparationJobRequest(request_id='prepare', collection_ref=collection.origin,
        paper_ids=[collections.papers(handle, collection.id).papers[0].id],
        expected_source_revision=0)
    return SimpleNamespace(engine=engine, registry=registry, handle=handle, collections=collections,
        imported=imported, collection=collection, store=store, legacy_store=legacy_store,
        jobs=jobs, legacy=legacy, request=request)


def test_collection_input_and_tables_do_not_fabricate_search_ids(tmp_path):
    case = case_for(tmp_path)
    submitted = case.jobs.submit('saved_example', case.handle, case.request)
    assert submitted.job.collection_ref == case.collection.origin
    assert not case.engine.get_workspace(case.handle).searches
    with case.store.connection() as db:
        columns = {row[1] for row in db.execute('PRAGMA table_info(collection_preparation_jobs)')}
    assert 'collection_id' in columns and 'search_id' not in columns
    job = case.store.claim('test-owner')
    captured = case.store.input(job)
    assert captured.collection_ref == case.collection.origin
    assert captured.members[0].origins[0].file_sha256 == case.imported.file_sha256
    assert captured.paper_ids == [paper.id for paper in captured.papers]
    assert case.jobs.submit('saved_example', case.handle, case.request).reused


def test_collection_retained_abstract_uses_exact_import_origin(tmp_path):
    case = case_for(tmp_path)
    case.jobs.submit('saved_example', case.handle, case.request)
    job = case.store.claim('test-owner')
    captured = case.store.input(job)
    source = case.jobs.prepare(case.engine, captured.papers[0], captured)
    assert source.provider == 'imported_abstract'
    metadata = source.parser_metadata
    assert metadata['collection_ref'] == case.collection.origin.model_dump(mode='json')
    assert metadata['metadata_version_id'] == captured.members[0].metadata_version.id
    assert metadata['metadata_snapshot_sha256'] == digest(captured.members[0].metadata_version.model_dump(mode='json'))
    assert metadata['member_origins'][0]['file_sha256'] == case.imported.file_sha256
    assert metadata['member_origins'][0]['row_number'] == 1


def test_actual_europe_pmc_retained_citation_fallback_keeps_import_origin(tmp_path):
    case = case_for(tmp_path)
    case.jobs.submit('saved_example', case.handle, case.request)
    captured = case.store.input(case.store.claim('test-owner'))
    case.engine._sources.prepare = lambda paper: fallback_source(paper, 'permission_unresolved',
        'Software fixture: full text not retained.', provider='europe_pmc')
    source = case.jobs.prepare(case.engine, captured.papers[0], captured)
    assert source.provider == 'imported_abstract'
    assert source.parser_metadata['retrieval_attempt_provider'] == 'europe_pmc'
    assert source.parser_metadata['member_origins'][0]['row_number'] == 1


def test_legacy_and_collection_domains_share_total_job_limit(tmp_path):
    case = case_for(tmp_path, max_jobs=1)
    case.jobs.submit('saved_example', case.handle, case.request)
    search = case.engine.search_literature(case.handle, SearchRequest(request_id='search', query='fixture'))
    with pytest.raises(MvpError) as error:
        case.legacy.submit('saved_example', case.handle, PreparationJobRequest(request_id='legacy',
            search_id=search.id, paper_ids=[search.papers[0].id], expected_source_revision=0))
    assert error.value.code == 'preparation_storage_limit'
    assert len(case.store.listing(case.handle.workspace_id).jobs) == 1
    assert case.legacy_store.listing(case.handle.workspace_id).jobs == []


def test_one_os_owner_lock_covers_both_domains(tmp_path):
    case = case_for(tmp_path)
    shared = PreparationWorker(case.legacy, modes=('saved_example',), additional_domains=(case.jobs,))
    contender = PreparationWorker(case.jobs, modes=('saved_example',))
    try:
        assert shared._acquire()
        assert len(shared._descriptors) == 1 and len(shared._owned_stores) == 2
        assert not contender._acquire()
    finally:
        shared.stop()
        contender.stop()


def test_public_saved_source_exact_identity_rebind_preserves_legacy_content():
    provider = SavedExampleProvider()
    actual = provider.search(SearchRequest(request_id='source', query='not executed', max_results=1)).papers[0]
    old = provider.prepare(actual)
    imported = actual.model_copy(update={'id': 'imported-report-occurrence'})
    rebound = provider.prepare_collection_paper(imported)
    assert rebound.status == 'full_text_retrieved' and rebound.paper_id == imported.id
    assert rebound.id != old.id
    for key in ('blocks', 'source_sha256', 'blocks_sha256', 'license', 'retained_content_utf8', 'source_identifiers', 'parser_id'):
        assert getattr(rebound, key) == getattr(old, key)
    assert provider.prepare(actual) == old
    assert provider.prepare(imported).status == 'identity_mismatch'
    pmid_only = imported.model_copy(update={'doi': None, 'pmcid': None})
    assert provider.prepare_collection_paper(pmid_only).status == 'full_text_retrieved'


def test_public_saved_source_rejects_conflicting_or_unknown_ids_without_title_search():
    provider = SavedExampleProvider()
    papers = provider.search(SearchRequest(request_id='source', query='not executed', max_results=2)).papers
    contradiction = papers[0].model_copy(update={'id': 'imported', 'pmid': papers[1].pmid})
    assert provider.prepare_collection_paper(contradiction).status == 'identity_mismatch'
    unknown = papers[0].model_copy(update={'id': 'unknown', 'pmid': '999999999', 'doi': None, 'pmcid': None})
    assert provider.prepare_collection_paper(unknown).status == 'identity_mismatch'
    no_ids = papers[0].model_copy(update={'id': 'title-only', 'pmid': None, 'doi': None, 'pmcid': None})
    assert provider.prepare_collection_paper(no_ids).source_type == 'abstract'
    assert provider.prepare_collection_paper(no_ids).status == 'abstract_only'
    assert provider.prepare_collection_paper(no_ids.model_copy(update={'abstract': ''})).status == 'no_usable_text'


def test_collection_title_only_citation_uses_imported_abstract_with_real_saved_provider(tmp_path):
    case = case_for(tmp_path, payload=b'Title,Abstract Note\nTitle only report,Imported text only.\n')
    case.engine._sources = SavedExampleProvider()
    case.jobs.submit('saved_example', case.handle, case.request)
    captured = case.store.input(case.store.claim('test-owner'))
    source = case.jobs.prepare(case.engine, captured.papers[0], captured)
    assert source.status == 'abstract_only' and source.source_type == 'abstract'
    assert source.provider == 'imported_abstract'
    assert source.parser_metadata['retrieval_attempt_provider'] == 'europe_pmc_saved_example'
