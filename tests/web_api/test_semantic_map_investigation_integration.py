"""Combined investigation/map software journeys on disposable synthetic research.

Providers, runtime metadata and embedding vectors are mocked. The existing local
PCA implementation is real; this file makes no BGE, PubMed or quality claim.
"""
import json
import socket

import pytest

from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.collection_contracts import CollectionMember
from src.mvp.contracts import digest
from src.mvp.ports import MvpError
from src.mvp.service import MVPService
from src.web_api.app import COOKIE_NAME, create_app
from tests.web_api.test_investigation_research import (
    case, commit, handoff_request, inspect, investigated, note_request, prepare,
    retrieve, raw_snapshot, browser, ok,
)
from tests.web_api.test_map_setup_independent import (
    SyntheticEmbedder, available, client_for, save as save_map_settings, snapshot,
)
import src.web_api.map_setup_routes as map_setup


@pytest.fixture(autouse=True)
def isolated_optional_caches(tmp_path, monkeypatch):
    monkeypatch.setenv('LITREV_RETRIEVAL_CACHE', str(tmp_path / 'unused-retrieval-cache'))
    monkeypatch.setenv('HF_HUB_CACHE', str(tmp_path / 'unused-map-cache'))


def workspace_export(client, root):
    # Export time changes on every download; all retained content must agree.
    return {key: value for key, value in ok(client.get(root + '/exports?format=json')).items() if key != 'exported_at'}


def configure_maps(case, monkeypatch, cache, adapter=SyntheticEmbedder):
    """Reuse setup mocks; use the real settings, collection map and worker APIs."""
    pytest.importorskip('numpy', reason='These mocked-embedding journeys use actual local PCA')
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('Forbidden external connection'))
    monkeypatch.setattr(map_setup, 'runtime_status', available)
    if not cache.exists():
        snapshot(cache)
    saved = ok(save_map_settings(case.c, cache_dir=cache))
    setup = case.app.state.map_setup
    setup.factory = adapter
    setup._adapters.clear()
    # Deterministic worker stepping is the existing map-test convention. No
    # additional worker, launcher, provider or research engine is introduced.
    monkeypatch.setattr(case.app.state.map_worker, 'start', lambda **kwargs: False)
    ready = ok(case.c.get('/api/v1/settings/maps'))
    assert ready['settings_revision'] == saved['revision'] and ready['ready']
    assert ready['configuration']['cache_dir'] == str(cache)
    assert ready['computation']['state'] == 'not_tested'
    return saved


def submit_map(case, handoff, key='map-handoff'):
    return ok(case.c.post(case.root + '/collection-maps', json={
        'request_id': key, 'collection_ref': handoff['collection']['origin'],
    }))


def finish_map(case, submitted):
    assert case.app.state.map_worker.run_once()
    job = ok(case.c.get(case.root + '/collection-map-jobs/' + submitted['job']['id']))
    return job


def test_investigation_handoff_maps_then_attributed_note_and_expanded_board_preserve_original(case, monkeypatch):
    investigated(case)
    original_snapshot = raw_snapshot(case)
    original_board = ok(case.c.get(case.board))
    original_export = ok(case.c.get(case.board + '/exports?format=json'))
    original_preparation = ok(case.c.get(case.root + '/source-preparations/' + case.definition['preparation_id']))
    handoff = commit(case, handoff_request(case, all_candidates=True))
    collection_path = case.root + '/collections/' + handoff['collection']['id']
    collection = ok(case.c.get(collection_path))
    papers = ok(case.c.get(collection_path + '/papers'))['papers']
    configure_maps(case, monkeypatch, case.path / 'synthetic-map-cache')
    calls = case.provider.calls
    submitted = submit_map(case, handoff)
    assert submitted['job']['collection_ref'] == handoff['collection']['origin']
    assert submitted['job']['status'] == 'queued'
    job = finish_map(case, submitted)
    assert job['status'] == 'succeeded', job
    view = ok(case.c.get(case.root + '/collection-maps/' + job['map_id']))
    artifact = view['artifact']
    assert artifact['collection_ref'] == handoff['collection']['origin']
    assert artifact['ordered_paper_ids'] == [paper['id'] for paper in papers]
    assert set(artifact['coordinates_by_paper_id']) == {'paper-one', 'candidate-b', 'candidate-c'}
    assert artifact['embedding_profile']['model'] == 'SYNTHETIC SOFTWARE TEST'
    execution = case.view['executions'][0]['execution']
    for paper in papers:
        member = ok(case.c.get(collection_path + '/paper', params={'paper_id': paper['id']}))['member']
        canonical_member = CollectionMember.model_validate(member).model_dump(mode='json')
        assert artifact['member_snapshot_hashes'][paper['id']] == digest(canonical_member)
        if paper['id'] != 'paper-one':
            origin = next(origin for origin in member['origins'] if origin['kind'] == 'investigation_candidate')
            assert origin['execution_id'] == execution['id']
            assert origin['approval_id'] == execution['approval_id']
            assert origin['original_cell_revision_id'] == case.original_cell['id']
    assert ok(case.c.get(collection_path)) == collection
    assert raw_snapshot(case) == original_snapshot
    assert ok(case.c.get(case.board)) == original_board
    assert case.provider.calls == calls
    # Exact-input replay and reopening do not refit, reselect or execute search.
    embedded = len(SyntheticEmbedder.calls)
    assert submit_map(case, handoff)['job']['id'] == job['id']
    assert ok(case.c.get(case.root + '/collection-maps/' + job['map_id'])) == view
    assert len(SyntheticEmbedder.calls) == embedded and not case.app.state.map_worker.run_once()

    preparation = prepare(case)
    retrieve(case)
    inspection = inspect(case)
    note = ok(case.c.post(case.ipath + '/notes', json=note_request(case)))
    assert inspection['reference']['paper_id'] == note['inspection']['source_paper']['id'] == 'candidate-b'
    assert note['original_paper_id'] == 'paper-one'
    assert note['meaning'] == 'related_paper_evidence_not_original_paper_finding'
    derived = ok(case.c.post(case.root + '/boards', json={
        'request_id': 'expanded-after-map', 'preparation_id': preparation['id'],
        'paper_ids': preparation['selected_paper_ids'], 'question': 'Synthetic expanded comparison',
        'fields': [{'id': 'population', 'label': 'Population', 'subquestion': 'Which population was studied?'}],
    }))
    assert derived['definition']['collection_ref'] == artifact['collection_ref']
    assert all(cell['head'] is None for cell in derived['cells'])
    retained = ok(case.c.get(case.board))
    assert retained['freshness'] == 'historical'
    assert retained['definition'] == original_board['definition'] and retained['cells'] == original_board['cells']
    assert ok(case.c.get(case.root + '/source-preparations/' + case.definition['preparation_id'])) == original_preparation
    after_export = ok(case.c.get(case.board + '/exports?format=json'))
    for key in ('definitions', 'cell_revisions', 'candidate_runs'):
        assert after_export[key] == original_export[key]
    assert [{key: value for key, value in row.items() if key != 'freshness'} for row in after_export['table']] == [
        {key: value for key, value in row.items() if key != 'freshness'} for row in original_export['table']]
    assert ok(case.c.get(case.root + '/collection-maps/' + job['map_id'])) == view
    audit = json.loads(ok(case.c.get(case.ipath + '/export'))['json_text'])
    assert audit['research']['notes'][0]['inspection']['source_paper']['id'] == 'candidate-b'
    assert case.transport.calls == 0


def test_optional_map_failure_retry_and_restart_keep_core_and_exact_session_collection_bindings(case, monkeypatch):
    investigated(case)
    handoff = commit(case)
    original = raw_snapshot(case)
    board_before = ok(case.c.get(case.board))
    export_before = workspace_export(case.c, case.root)
    calls = case.provider.calls
    cache = case.path / 'synthetic-map-cache'
    class FailingEmbedder(SyntheticEmbedder):
        def embed(self, representation, checkpoint):
            raise MvpError('embedding_profile_mismatch', 'Synthetic optional map failure; no fallback')
    saved = configure_maps(case, monkeypatch, cache, adapter=FailingEmbedder)
    submitted = submit_map(case, handoff, 'explicit-failing-map')
    failed = finish_map(case, submitted)
    assert failed['status'] == 'failed' and failed['error']['code'] == 'embedding_profile_mismatch'
    assert submit_map(case, handoff, 'explicit-failing-map')['job'] == failed
    assert not case.app.state.map_worker.run_once()
    assert raw_snapshot(case) == original and ok(case.c.get(case.board)) == board_before
    assert workspace_export(case.c, case.root) == export_before
    assert ok(case.c.get(case.ipath + '/research'))['handoffs'][0] == handoff
    assert ok(case.c.get('/api/v1/settings/retrieval'))['core_lexical_available'] is True
    # Correcting the optional adapter requires a separate, explicit calculation.
    case.app.state.map_setup.factory = SyntheticEmbedder
    case.app.state.map_setup._adapters.clear()
    retried = submit_map(case, handoff, 'explicit-retry-map')
    assert retried['job']['id'] != failed['id']
    completed = finish_map(case, retried)
    assert completed['status'] == 'succeeded', completed
    saved_map = ok(case.c.get(case.root + '/collection-maps/' + completed['map_id']))
    retained_research = ok(case.c.get(case.ipath + '/research'))
    assert saved_map['artifact']['collection_ref'] == handoff['collection']['origin']
    assert raw_snapshot(case) == original and case.provider.calls == calls
    case.app.state.map_worker.stop()

    engine = MVPService(SQLiteWorkspaceStorage(case.path / 'research.sqlite3'), case.provider, case.provider)
    app = create_app(case.path, services={'live': engine, 'saved_example': engine}, search_diagnostics=case.diagnostics)
    reopened = client_for(app, case.c.cookies.get(COOKIE_NAME))
    before_reopen = len(SyntheticEmbedder.calls)
    assert ok(reopened.get(case.root + '/collection-maps/' + completed['map_id'])) == saved_map
    assert ok(reopened.get(case.ipath + '/research')) == retained_research
    status = ok(reopened.get('/api/v1/settings/maps'))
    assert status['settings_revision'] == saved['revision']
    assert status['configuration']['enabled'] is True and status['configuration']['cache_dir'] == str(cache)
    assert workspace_export(reopened, case.root) == export_before
    stranger = browser(app)
    assert ok(stranger.get('/api/v1/settings/maps'))['configuration']['enabled'] is False
    assert stranger.get(case.root + '/collection-maps/' + completed['map_id']).status_code == 404
    assert stranger.post(case.root + '/collection-maps', json={
        'request_id': 'not-my-collection', 'collection_ref': handoff['collection']['origin'],
    }).status_code == 404
    assert len(SyntheticEmbedder.calls) == before_reopen and case.provider.calls == calls
    assert raw_snapshot(case) == original and case.transport.calls == 0
