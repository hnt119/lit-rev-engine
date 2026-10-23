"""Real retained-source passage capacity, without provider/model execution."""
import hashlib
import json
import os
from pathlib import Path
import socket
import time

from fastapi.testclient import TestClient

from src.mvp.adapters.retrieval import LexicalRetrieval
from src.mvp.adapters.saved_examples import SavedExampleProvider
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.service import MVPService
from src.web_api.app import create_app


class CountingRetrieval:
    def __init__(self):
        self.inner = LexicalRetrieval()
        self.method, self.parameters, self.calls = self.inner.method, self.inner.parameters, []

    def search(self, question, sources, run_id, top_k=5):
        self.calls.append(top_k)
        return self.inner.search(question, sources, run_id, top_k)


def test_public_thirty_source_passage_limits_replay_and_exact_anchors(tmp_path, monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('Passage audit attempted network access')
    monkeypatch.setattr(socket, 'create_connection', denied)
    for key in tuple(os.environ):
        if key.startswith(('NCBI_', 'MVP_PROPOSALS_', 'MVP_SEARCH_PLANNER_')):
            monkeypatch.delenv(key, raising=False)
    for key in ('MVP_PROPOSALS_ENABLED', 'MVP_SEARCH_PLANNER_ENABLED', 'MVP_MAP_ENABLED'):
        monkeypatch.setenv(key, '0')
    provider, retrieval = SavedExampleProvider(), CountingRetrieval()
    engine = MVPService(SQLiteWorkspaceStorage(tmp_path / 'workspaces.sqlite3'), provider, provider, retrieval)
    app = create_app(tmp_path, services={'saved_example': engine})
    client = TestClient(app, base_url='http://127.0.0.1:8765')
    csrf = client.get('/api/v1/session').json()['csrf_token']
    client.headers.update({'Origin': 'http://127.0.0.1:3000', 'X-CSRF-Token': csrf})
    started = time.monotonic()

    def call(method, path, body=None, status=200):
        result = client.request(method, path, json=body) if body is not None else client.request(method, path)
        assert result.status_code == status, (result.status_code, result.text[:200])
        return result

    try:
        workspace = call('POST', '/api/v1/workspaces', {'request_id': 'passages-workspace',
            'mode': 'saved_example', 'question': 'SOFTWARE TEST passage capacity'}).json()
        root = '/api/v1/workspaces/' + workspace['id']
        search = call('POST', root + '/searches', {'request_id': 'passages-search',
            'query': 'saved public sources', 'max_results': 30}).json()
        paper_ids = [paper['id'] for paper in search['papers']]
        job = call('POST', root + '/preparation-jobs', {'request_id': 'passages-prepare',
            'search_id': search['id'], 'paper_ids': paper_ids, 'expected_source_revision': 0,
            'expected_preparation_id': None}, status=202).json()['job']
        assert app.state.preparation_worker.run_once()
        job = call('GET', root + '/preparation-jobs/' + job['id']).json()
        assert job['status'] == 'succeeded'
        preparation_id = job['result_preparation_id']; revision = job['result_source_revision']
        source_map = {source.id: source for source in provider._sources.values()}
        originals, results, requests = [], [], []
        for count in (5, 17, 10, 20, 30):
            request = {'request_id': 'passages-' + str(count), 'question': 'diet women microbiome',
                       'top_k': count, 'expected_preparation_id': preparation_id,
                       'expected_source_revision': revision}
            run = call('POST', root + '/evidence-runs', request).json()
            assert run['preparation_id'] == preparation_id and run['source_revision'] == revision
            assert run['parameters']['top_k'] == count
            assert run['parameters']['returned_count'] == len(run['passages']) == count
            anchors = []
            for passage in run['passages']:
                source = source_map[passage['source_id']]
                block = next(block for block in source.blocks if block.id == passage['anchor']['block_id'])
                anchor = passage['anchor']; assert block.text[anchor['start']:anchor['end']] == anchor['quote']
                anchors.append((source.id, block.id, anchor['start'], anchor['end']))
            assert len(anchors) == len(set(anchors))
            if count == 5:
                original = run; originals = anchors
            else:
                assert anchors[:5] == originals
            requests.append(request); results.append({'requested': count, 'returned': len(anchors),
                'matched': run['matched_passages'], 'indexed': run['indexed_passages']})
        assert retrieval.calls == [5, 17, 10, 20, 30]
        assert call('GET', root + '/runs/' + original['id']).json()['run'] == original
        assert retrieval.calls == [5, 17, 10, 20, 30]
        assert call('POST', root + '/evidence-runs', requests[-1]).json() == run
        assert retrieval.calls == [5, 17, 10, 20, 30]
        before = hashlib.sha256((tmp_path / 'workspaces.sqlite3').read_bytes()).hexdigest()
        call('POST', root + '/evidence-runs', {**requests[0], 'request_id': 'passages-invalid', 'top_k': 31}, status=422)
        assert hashlib.sha256((tmp_path / 'workspaces.sqlite3').read_bytes()).hexdigest() == before
        call('POST', root + '/evidence-runs', {**requests[-1], 'request_id': 'passages-5', 'top_k': 30}, status=409)
        assert hashlib.sha256((tmp_path / 'workspaces.sqlite3').read_bytes()).hexdigest() == before
        assert retrieval.calls == [5, 17, 10, 20, 30]
        report = {'completed': True, 'public_prepared_sources': 30, 'results': results,
                  'retrieval_calls': retrieval.calls, 'original_five_unchanged': True,
                  'canonical_anchor_integrity': True, 'unique_anchors_per_run': True,
                  'chosen_preparation_retained': True, 'no_reretrieval_on_read_or_replay': True,
                  'reject31_and_changed_fingerprint_rollback': True,
                  'live_network_calls': 0, 'model_calls': 0,
                  'scope': 'Result capacity and immutable provenance; no retrieval-quality or completeness claim.',
                  'elapsed_seconds': round(time.monotonic() - started, 3)}
        target = Path(os.environ.get('LRE_USABILITY_PASSAGE_REPORT', str(tmp_path / 'passages-report.json')))
        target.parent.mkdir(parents=True, exist_ok=True); target.write_text(json.dumps(report, indent=2) + '\n')
    finally:
        client.close()
