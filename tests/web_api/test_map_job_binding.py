"""Proposed PR25 regression. Synthetic vectors and bytes; no real model execution."""
from copy import deepcopy
from hashlib import sha256
import json
import math
import socket

import pytest
from fastapi.testclient import TestClient

from src.mvp.adapters.paper_embeddings import LocalPaperEmbedder
from src.mvp.contracts import digest
from src.mvp.mapping import EmbeddedPaper, EmbeddingProfile, validate_vector
from src.mvp.ports import MvpError
from src.web_api.app import COOKIE_NAME, create_app
import src.web_api.map_setup_routes as setup_routes

P = '/api/v1'


class GatedSyntheticAdapter(LocalPaperEmbedder):
    """Mimic enablement/cache gate and cached profile; do not load a model."""
    calls = []

    def readiness(self):
        if not self.enabled or not (self.cache_dir / 'synthetic-pinned-bytes').is_file():
            return False, 'Synthetic adapter disabled or synthetic cache missing'
        return True, 'Synthetic adapter ready'

    def _file_hashes(self):
        # Complete, bounded synthetic identity, not a real BGE manifest/file check.
        return {'synthetic-pinned-bytes': sha256((self.cache_dir / 'synthetic-pinned-bytes').read_bytes()).hexdigest()}

    @property
    def profile(self):
        if self._profile is None:
            ready, reason = self.readiness()
            if not ready:
                raise MvpError('map_setup_required', reason)
            self._profile = EmbeddingProfile(model='SYNTHETIC ONLY', model_revision='fixture-a',
                tokenizer_revision='fixture-a', dimension=3, files_sha256=self._file_hashes(),
                runtime_versions={'fixture': 'no real model'})
        return self._profile

    def embed(self, representation, checkpoint):
        ready, reason = self.readiness()
        if not ready:
            raise MvpError('map_setup_required', reason)
        if self._file_hashes() != self.profile.files_sha256:
            raise MvpError('embedding_profile_changed', 'Synthetic bytes changed')
        self.calls.append((str(self.cache_dir), representation.paper_id, representation.input_sha256))
        checkpoint()
        value = int(representation.input_sha256[:8], 16)
        return EmbeddedPaper(paper_id=representation.paper_id, input_sha256=representation.input_sha256,
            representation=representation.representation,
            vector=validate_vector([1., (value % 997) / 997, ((value // 997) % 991) / 991], 3),
            window_token_weights=[1], token_count=1)


def client_for(app, cookie=None):
    client = TestClient(app, base_url='http://127.0.0.1:8765')
    if cookie:
        client.cookies.set(COOKIE_NAME, cookie)
    token = client.get(P + '/session').json()['csrf_token']
    client.headers.update({'Origin': 'http://127.0.0.1:3000', 'X-CSRF-Token': token})
    return client


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def save(client, *, enabled, cache):
    old = ok(client.get(P + '/settings'))
    preferences = deepcopy(old['preferences'])
    preferences['maps'].update(enabled=enabled, cache_dir=str(cache))
    return ok(client.put(P + '/settings', json={'expected_revision': old['revision'], 'preferences': preferences}))


def install_adapter(app, monkeypatch):
    app.state.map_setup.factory = GatedSyntheticAdapter
    app.state.map_setup._adapters.clear()
    # Deterministic single worker steps; no background thread races the queued job.
    monkeypatch.setattr(app.state.map_worker, 'start', lambda **kwargs: False)


def db_binding(app, domain, job_id):
    store = app.state.maps.store if domain == 'search' else app.state.collection_maps.store
    columns = ('id', 'workspace_id', 'map_id', 'logical_key', 'profile_json',
               'search_id', 'search_json', 'adapter_config_json') if domain == 'search' else (
               'id', 'workspace_id', 'map_id', 'logical_key', 'profile_json',
               'collection_id', 'collection_snapshot_sha256', 'input_json', 'input_sha256', 'adapter_config_json')
    with store.connection() as db:
        row = db.execute('SELECT * FROM ' + store.job_table + ' WHERE id=?', (job_id,)).fetchone()
    assert row is not None
    return {key: row[key] for key in columns}


def create_collection(client, root):
    payload = (b'Title,DOI,Abstract Note\n'
               b'Synthetic A,10.1234/reg-a,Synthetic text A\n'
               b'Synthetic B,10.1234/reg-b,Synthetic text B\n'
               b'Synthetic C,10.1234/reg-c,Synthetic text C\n')
    imported = ok(client.post(root + '/imports/csv', content=payload,
        headers={'Content-Type': 'application/octet-stream', 'X-Request-ID': 'upload',
                 'X-Import-Filename': 'synthetic.csv'}))
    rows = ok(client.get(root + '/imports/' + imported['id'] + '/rows'))['rows']
    return ok(client.post(root + '/imports/' + imported['id'] + '/commit', json={
        'request_id': 'commit', 'expected_revision': imported['revision'],
        'name': 'Synthetic collection', 'accepted_row_ids': [row['id'] for row in rows]}))


@pytest.mark.parametrize('domain', ['search', 'collection'])
@pytest.mark.parametrize('new_setting', ['disabled', 'missing_cache'])
@pytest.mark.parametrize('restart', [False, True], ids=['same-process-control', 'restart'])
def test_accepted_adapter_survives_future_preference_change(tmp_path, monkeypatch, domain, new_setting, restart):
    pytest.importorskip('numpy', reason='Synthetic vectors use the existing local projection implementation')
    attempts = []
    def deny(*args, **kwargs):
        attempts.append(True)
        raise AssertionError('Synthetic regression must not use the network')
    monkeypatch.setattr(socket.socket, 'connect', deny)
    monkeypatch.setattr(socket, 'create_connection', deny)
    monkeypatch.setenv('MVP_MAP_ENABLED', '0')
    monkeypatch.setattr(setup_routes, 'runtime_status', lambda: dict(state='available',
        versions=setup_routes.EXPECTED_VERSIONS, missing=[], incompatible=[],
        message='Synthetic runtime', check_scope='metadata_only_not_execution'))
    GatedSyntheticAdapter.calls = []
    directory, cache_a, cache_b = tmp_path / 'app', tmp_path / 'cache-a', tmp_path / 'absent-b'
    cache_a.mkdir()
    (cache_a / 'synthetic-pinned-bytes').write_bytes(b'synthetic adapter A, not model weights')
    app = create_app(directory)
    install_adapter(app, monkeypatch)
    client = client_for(app)
    reopened = None
    stranger = None
    try:
        save(client, enabled=True, cache=cache_a)
        work = ok(client.post(P + '/workspaces', json={'request_id': 'workspace',
                  'question': 'Synthetic restart regression', 'mode': 'saved_example'}))
        root = P + '/workspaces/' + work['id']
        if domain == 'search':
            search = ok(client.post(root + '/searches', json={'request_id': 'search',
                        'query': 'Synthetic public fixture', 'max_results': 3}))
            request = {'request_id': 'accepted-map', 'search_id': search['id']}
            expected_ids = [paper['id'] for paper in search['papers']]
            submit_url, jobs, map_url = root + '/maps', root + '/jobs/', root + '/maps/'
        else:
            collection = create_collection(client, root)
            expected_ids = [paper['id'] for paper in ok(client.get(root + '/collections/' + collection['id'] + '/papers'))['papers']]
            request = {'request_id': 'accepted-map', 'collection_ref': collection['origin']}
            submit_url, jobs, map_url = root + '/collection-maps', root + '/collection-map-jobs/', root + '/collection-maps/'
        accepted = ok(client.post(submit_url, json=request))['job']
        assert accepted['status'] == 'queued' and not GatedSyntheticAdapter.calls
        before = db_binding(app, domain, accepted['id'])
        assert str(cache_a) not in json.dumps(accepted)
        assert str(cache_a) not in client.get(jobs + accepted['id']).text
        stranger = client_for(app)
        assert stranger.get(jobs + accepted['id']).status_code == 404
        assert stranger.post(submit_url, json=request).status_code == 404
        assert stranger.post(jobs + accepted['id'] + '/cancel').status_code == 404
        assert client.post(jobs + accepted['id'] + '/cancel', headers={'X-CSRF-Token': 'invalid'}).status_code == 403
        assert ok(client.get(jobs + accepted['id']))['status'] == 'queued'
        enabled = new_setting != 'disabled'
        selected_cache = cache_a if new_setting == 'disabled' else cache_b
        changed = save(client, enabled=enabled, cache=selected_cache)
        def assert_future_settings():
            current = ok(client.get(P + '/settings'))
            assert current['revision'] == changed['revision']
            assert current['preferences']['maps'] == changed['preferences']['maps']
            assert current['preferences']['maps']['enabled'] is enabled
            assert current['preferences']['maps']['cache_dir'] == str(selected_cache)
        def reject_new(key):
            response = client.post(submit_url, json={**request, 'request_id': key})
            assert response.status_code == 422, response.text
            assert response.json()['error']['code'] == 'map_setup_required'
        assert_future_settings()
        reject_new('fresh-before-reconstruction')
        assert db_binding(app, domain, accepted['id']) == before
        cookie = client.cookies.get(COOKIE_NAME)
        if restart:
            app.state.map_worker.stop()
            assert app.state.map_worker._thread is None
            client.close()
            reopened = create_app(directory)
            install_adapter(reopened, monkeypatch)
            app = reopened
            client = client_for(app, cookie)
            assert db_binding(app, domain, accepted['id']) == before
        assert_future_settings()
        reject_new('fresh-after-reconstruction')
        worker = app.state.map_worker
        assert worker._acquire()  # the production OS ownership/recovery gate
        try:
            assert worker.run_once()
        finally:
            worker.stop()
        result = ok(client.get(jobs + accepted['id']))
        assert_future_settings()
        reject_new('fresh-after-processing')
        # Intended policy: accepted A remains bound across restart. At c7005dc,
        # restarted cases are source-inferred to fail here with map_setup_required.
        assert result['id'] == accepted['id'] and result['map_id'] == accepted['map_id']
        assert result['status'] == 'succeeded', result
        assert db_binding(app, domain, accepted['id']) == before
        view = ok(client.get(map_url + accepted['map_id']))
        artifact, counts = view['artifact'], view['counts']
        assert str(cache_a) not in json.dumps(view)
        assert artifact['map_id'] == accepted['map_id'] and artifact['workspace_id'] == work['id']
        assert len(expected_ids) == 3 and len(set(expected_ids)) == 3
        assert artifact['ordered_paper_ids'] == expected_ids
        assert set(artifact['paper_input_hashes']) == set(expected_ids)
        coordinates = artifact['coordinates_by_paper_id']
        assert set(coordinates) == set(expected_ids)
        assert all(len(pair) == 2 and all(type(x) in (int, float) and math.isfinite(x) for x in pair)
                   for pair in coordinates.values())
        assert artifact['status'] == 'ready' and artifact['excluded_papers_with_reasons'] == []
        assert counts == {'provider_reported': search['total_reported'] if domain == 'search' else None,
                          'fetched_records': search['fetched_count'] if domain == 'search' else None,
                          'distinct_records': 3, 'embedded_papers': 3, 'excluded_papers': 0, 'map_points': 3}
        assert artifact['embedding_profile'] == json.loads(before['profile_json'])
        assert artifact['embedding_profile_sha256'] == digest(artifact['embedding_profile'])
        assert artifact['coordinate_sha256'] == digest(coordinates)
        if domain == 'search':
            assert artifact['search_id'] == search['id'] == before['search_id']
            assert artifact['search_snapshot_sha256'] == digest(search)
        else:
            assert artifact['collection_ref'] == collection['origin']
            assert before['collection_id'] == collection['id']
            assert before['collection_snapshot_sha256'] == collection['origin']['collection_snapshot_sha256']
        assert artifact['embedding_profile']['files_sha256'] == {
            'synthetic-pinned-bytes': sha256((cache_a / 'synthetic-pinned-bytes').read_bytes()).hexdigest()}
        assert len(GatedSyntheticAdapter.calls) == 3
        assert all(path == str(cache_a) and artifact['paper_input_hashes'][paper] == input_hash
                   for path, paper, input_hash in GatedSyntheticAdapter.calls)
        assert stranger.get(map_url + accepted['map_id']).status_code == 404
        assert not worker.run_once() and not attempts
    finally:
        app.state.map_worker.stop()
        assert app.state.map_worker._thread is None or not app.state.map_worker._thread.is_alive()
        if stranger is not None:
            stranger.close()
        client.close()


@pytest.mark.parametrize('domain', ['search', 'collection'])
def test_replay_and_reuse_do_not_replace_private_binding(tmp_path, monkeypatch, domain):
    monkeypatch.setattr(setup_routes, 'runtime_status', lambda: dict(state='available', versions={}, missing=[], incompatible=[], message='synthetic'))
    app = create_app(tmp_path / 'app')
    install_adapter(app, monkeypatch)
    client = client_for(app)
    try:
        a, b = tmp_path / 'a', tmp_path / 'b'
        for cache in (a, b):
            cache.mkdir()
            (cache / 'synthetic-pinned-bytes').write_bytes(b'identical synthetic bytes')
        save(client, enabled=True, cache=a)
        work = ok(client.post(P + '/workspaces', json={'request_id': 'w', 'question': 'Synthetic', 'mode': 'saved_example'}))
        root = P + '/workspaces/' + work['id']
        if domain == 'search':
            search = ok(client.post(root + '/searches', json={'request_id': 's', 'query': 'fixture', 'max_results': 3}))
            url, request = root + '/maps', {'request_id': 'map', 'search_id': search['id']}
        else:
            collection = create_collection(client, root)
            url, request = root + '/collection-maps', {'request_id': 'map', 'collection_ref': collection['origin']}
        first = ok(client.post(url, json=request))
        before = db_binding(app, domain, first['job']['id'])
        save(client, enabled=True, cache=b)
        assert ok(client.post(url, json=request))['job']['id'] == first['job']['id']
        assert ok(client.post(url, json={**request, 'request_id': 'reuse'}))['job']['id'] == first['job']['id']
        assert db_binding(app, domain, first['job']['id']) == before
        assert json.loads(before['adapter_config_json'])['binding']['cache_dir'] == str(a)
    finally:
        app.state.map_worker.stop()
        client.close()


def test_legacy_and_corrupt_bindings_fail_closed(tmp_path):
    from src.mvp.contracts import canonical, digest
    from src.mvp.ports import MvpError
    setup = setup_routes.MapSetup(None, None, None, embedder_factory=GatedSyntheticAdapter)
    for raw in (None, '{', canonical({'binding': {'version': 1, 'enabled': True, 'cache_dir': str(tmp_path)}, 'sha256': '0' * 64}),
                canonical({'binding': {'version': 2, 'enabled': True, 'cache_dir': str(tmp_path)}, 'sha256': digest({'version': 2, 'enabled': True, 'cache_dir': str(tmp_path)})})):
        with pytest.raises(MvpError) as error:
            setup.for_job({'adapter_config_json': raw})
        assert error.value.code == 'map_setup_required'
        assert str(tmp_path) not in error.value.message


def test_legacy_database_migration_preserves_rows_and_supports_shared_quotas(tmp_path):
    from src.mvp.adapters.map_storage import MapStore
    from src.mvp.adapters.collection_map_storage import CollectionMapStore
    path = tmp_path / 'maps.sqlite3'
    paper = MapStore(path)
    CollectionMapStore(path)
    with paper.connection() as db:
        db.execute("INSERT INTO paper_map_deleted VALUES ('old-workspace')")
        db.execute("""INSERT INTO paper_map_jobs(id,workspace_id,search_id,map_id,logical_key,search_json,profile_json,status,progress_total,created_at,updated_at) VALUES ('job','kept','search','map','key','{}','{}','queued',3,'2020','2020')""")
        before = paper.view(db.execute("SELECT * FROM paper_map_jobs WHERE id='job'").fetchone()).model_dump()
        db.execute('ALTER TABLE paper_map_jobs DROP COLUMN adapter_config_json')
        db.execute('ALTER TABLE collection_map_jobs DROP COLUMN adapter_config_json')
    paper = MapStore(path)
    # The paper store may be opened alone before collection schema migration.
    with paper.transaction() as db:
        paper._limits(db, 'other-workspace')
        assert db.execute("SELECT 1 FROM paper_map_deleted WHERE workspace_id='old-workspace'").fetchone()
    collection = CollectionMapStore(path)
    with collection.connection() as db:
        assert paper.view(db.execute("SELECT * FROM paper_map_jobs WHERE id='job'").fetchone()).model_dump() == before
        assert db.execute("SELECT adapter_config_json FROM paper_map_jobs WHERE id='job'").fetchone()[0] is None
        for table in ('paper_map_jobs', 'collection_map_jobs'):
            assert 'adapter_config_json' in {row['name'] for row in db.execute(f'PRAGMA table_info({table})')}
