"""Independent populated-board capacity checks over retained public sources.

Synthetic unassessed values exercise storage and API behavior. Their references
have mechanical integrity only; this is not scientific or human validation.
"""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import time

from fastapi.testclient import TestClient

from src.mvp.adapters.saved_examples import SavedExampleProvider
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.service import MVPService
from src.web_api.app import create_app

BASE = 'http://127.0.0.1:8765'
ORIGIN = 'http://127.0.0.1:3000'
PREFIX = '/api/v1'
TABLES = ('evidence_boards', 'board_definitions', 'board_cells', 'board_heads',
          'board_drafts', 'board_candidates', 'board_requests', 'proposal_runs',
          'cell_proposals', 'proposal_events', 'proposal_actions')


def table_snapshot(store, workspace_id):
    result = {}
    with store.connection() as db:
        for table in TABLES:
            rows = [list(row) for row in db.execute(
                'SELECT * FROM ' + table + ' WHERE workspace_id=? ORDER BY rowid', (workspace_id,))]
            raw = json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode()
            result[table] = {'rows': len(rows), 'sha256': hashlib.sha256(raw).hexdigest()}
    return result


def storage_measurement(store, workspace_id):
    result = {}; total = 0
    with store.connection() as db:
        for table in TABLES:
            rows = list(db.execute('SELECT * FROM ' + table + ' WHERE workspace_id=?', (workspace_id,)))
            measured = sum(sum(len(str(value).encode()) for value in row if value is not None) + 256 for row in rows)
            result[table] = {'rows': len(rows), 'quota_bytes': measured}; total += measured
    return {'quota_bytes': total, 'quota_limit_bytes': store.max_workspace_bytes,
            'sqlite_file_bytes': store.path.stat().st_size, 'tables': result}


def test_populated_thirty_by_six_roundtrip_revisions_and_atomic_quotas(tmp_path, monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('Capacity audit attempted external network access')
    monkeypatch.setattr(socket, 'create_connection', denied)
    for key in tuple(os.environ):
        if key.startswith(('NCBI_', 'MVP_PROPOSALS_', 'MVP_SEARCH_PLANNER_')):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('MVP_PROPOSALS_ENABLED', '0')
    monkeypatch.setenv('MVP_SEARCH_PLANNER_ENABLED', '0')
    monkeypatch.setenv('MVP_MAP_ENABLED', '0')
    started = time.monotonic(); report = {'completed': False, 'boundary': 'public offline sources; synthetic unassessed values; network denied'}
    report_path = Path(os.environ.get('LRE_USABILITY_CAPACITY_REPORT', str(tmp_path / 'capacity-report.json')))
    provider = SavedExampleProvider()
    engine = MVPService(SQLiteWorkspaceStorage(tmp_path / 'workspaces.sqlite3'), provider, provider)
    app = create_app(tmp_path, services={'saved_example': engine})
    client = TestClient(app, base_url=BASE)
    csrf = client.get(PREFIX + '/session').json()['csrf_token']
    client.headers.update({'Origin': ORIGIN, 'X-CSRF-Token': csrf})
    largest_body = 0

    def call(method, path, body=None, expected=200):
        nonlocal largest_body
        result = client.request(method, path, json=body) if body is not None else client.request(method, path)
        if body is not None:
            largest_body = max(largest_body, len(result.request.content))
        assert result.status_code == expected, (method, path, result.status_code, result.text[:300])
        return result

    try:
        workspace = call('POST', PREFIX + '/workspaces', {'request_id': 'capacity-workspace',
            'mode': 'saved_example', 'question': 'SOFTWARE CAPACITY TEST: no scientific assessment'}).json()
        root = PREFIX + '/workspaces/' + workspace['id']
        search = call('POST', root + '/searches', {'request_id': 'capacity-search',
            'query': 'public saved example', 'max_results': 30}).json()
        ids = [paper['id'] for paper in search['papers']]
        assert len(ids) == len(set(ids)) == 30
        job = call('POST', root + '/preparation-jobs', {'request_id': 'capacity-preparation',
            'search_id': search['id'], 'paper_ids': ids, 'expected_source_revision': 0,
            'expected_preparation_id': None}, expected=202).json()['job']
        assert app.state.preparation_worker.run_once()
        job = call('GET', root + '/preparation-jobs/' + job['id']).json()
        assert job['status'] == 'succeeded'
        preparation = call('GET', root + '/source-preparations/' + job['result_preparation_id']).json()
        assert preparation['selected_paper_ids'] == ids and len(preparation['sources']) == 30
        assert all(source['source_type'] == 'full_text' for source in preparation['sources'])
        fields = [{'id': 'field-' + str(i), 'label': 'Software field ' + str(i),
                   'subquestion': 'SOFTWARE CAPACITY TEST field ' + str(i)} for i in range(6)]
        request = {'request_id': 'capacity-board', 'preparation_id': preparation['id'],
                   'question': workspace['question'], 'paper_ids': ids, 'fields': fields}
        view = call('POST', root + '/boards', request).json()
        definition = view['definition']; revision = definition['revision_id']
        board = root + '/boards/' + definition['board_id']
        assert len(view['cells']) == 180 and all(cell['head'] is None for cell in view['cells'])
        store = app.state.boards.store
        before = table_snapshot(store, workspace['id'])
        for invalid in ({**request, 'request_id': 'over-papers', 'paper_ids': [*ids, 'extra-paper']},
                        {**request, 'request_id': 'over-fields', 'fields': [*fields, {**fields[0], 'id': 'field-6'}]}):
            call('POST', root + '/boards', invalid, expected=422)
        assert table_snapshot(store, workspace['id']) == before
        references = {}
        for binding in definition['sources']:
            inspection = call('GET', board + '/sources/' + binding['source_id'] + '/blocks').json()
            reference = inspection['blocks'][0]['reference']
            reference = {key: reference[key] for key in ('source_id', 'source_version', 'source_sha256',
                         'blocks_sha256', 'block_id', 'start', 'end')}
            reference['end'] = min(reference['end'], reference['start'] + 256)
            references[binding['paper_id']] = reference
        heads = {}; submit_bytes = []; draft_bytes = []
        for generation in (1, 2):
            for position, paper_id in enumerate(ids):
                for field in fields:
                    key = (paper_id, field['id']); reference = references[paper_id]
                    data = {'value': ('SOFTWARE TEST unassessed capacity value ' * 8) + f'{position}/{field["id"]}/v{generation}',
                            'references': [reference], 'inspected_ranges': [reference],
                            'semantic_assessment': 'unassessed', 'scope_result': 'value_found',
                            'reason': 'Synthetic storage fixture; no human or scientific validation.'}
                    draft_response = call('PUT', board + '/drafts/' + paper_id + '/' + field['id'],
                        {'expected_revision_id': revision, 'version': 0, 'expected_cell_head_id': heads.get(key), 'data': data})
                    draft_bytes.append(len(draft_response.request.content))
                    submit = {'request_id': f'capacity-cell-{generation}-{position}-{field["id"]}',
                              'expected_revision_id': revision, 'paper_id': paper_id, 'field_id': field['id'],
                              'draft_version': draft_response.json()['version'], 'supersedes_id': heads.get(key)}
                    saved = call('POST', board + '/cell-revisions', submit)
                    submit_bytes.append(len(saved.request.content)); cell = saved.json()
                    assert len(cell['references']) == len(cell['inspected_ranges']) == 1
                    assert cell['semantic_assessment'] == 'unassessed' and cell['supersedes_id'] == heads.get(key)
                    heads[key] = cell['id']
        populated = call('GET', board)
        assert len(populated.json()['cells']) == 180 and all(cell['head'] is not None for cell in populated.json()['cells'])
        measured = storage_measurement(store, workspace['id'])
        assert measured['tables']['board_cells']['rows'] == 360
        assert measured['tables']['board_requests']['rows'] == 361
        assert measured['tables']['board_heads']['rows'] == 180 and measured['tables']['board_drafts']['rows'] == 0
        assert measured['tables']['board_candidates']['rows'] == 0
        assert all(measured['tables'][table]['rows'] == 0 for table in ('proposal_runs', 'cell_proposals', 'proposal_events', 'proposal_actions'))
        audit_response = call('GET', board + '/exports?format=json&history=true')
        audit = audit_response.json()
        assert len(audit['table']) == 180 and len(audit['cell_revisions']) == 360
        csv_response = call('GET', board + '/exports?format=csv')
        assert len(list(csv.DictReader(io.StringIO(csv_response.text)))) == 180
        history = call('GET', board + '/cells/' + ids[0] + '/field-0/history').json()
        assert history['total'] == 2
        reopened_client = TestClient(create_app(tmp_path, services={'saved_example': engine}), base_url=BASE)
        reopened_client.cookies.update(client.cookies); reopened_client.headers.update(client.headers)
        reopened = reopened_client.get(board)
        assert reopened.status_code == 200 and reopened.json() == populated.json()
        reopened_client.close()
        legacy = call('POST', root + '/boards', {**request, 'request_id': 'legacy-ten', 'paper_ids': ids[:10]}).json()
        assert legacy['definition']['schema_version'] == 'mvp.board-definition.v1'
        assert len(legacy['definition']['paper_ids']) == 10 and len(legacy['cells']) == 60
        assert call('GET', root + '/boards/' + legacy['definition']['board_id']).json() == legacy
        revised = call('POST', board + '/revisions', {**request, 'request_id': 'capacity-definition-revision',
                       'expected_revision_id': revision}).json()
        assert revised['definition']['parent_revision_id'] == revision and len(revised['cells']) == 180
        assert all(cell['head'] is None for cell in revised['cells'])
        historical = call('GET', board + '?revision_id=' + revision).json()
        assert historical['freshness'] == 'historical' and sum(cell['head'] is not None for cell in historical['cells']) == 180
        before = table_snapshot(store, workspace['id']); quota = store.max_workspace_bytes
        store.max_workspace_bytes = 1
        call('PUT', board + '/drafts/' + ids[0] + '/field-0', {'expected_revision_id': revised['definition']['revision_id'],
             'version': 0, 'expected_cell_head_id': None, 'data': {'value': 'SOFTWARE TEST forced quota failure'}}, expected=422)
        store.max_workspace_bytes = quota
        assert table_snapshot(store, workspace['id']) == before
        before = table_snapshot(store, workspace['id']); maximum_requests = store.max_requests
        store.max_requests = before['board_requests']['rows']
        call('POST', root + '/boards', {**request, 'request_id': 'capacity-forced-request-quota'}, expected=422)
        store.max_requests = maximum_requests
        assert table_snapshot(store, workspace['id']) == before
        report.update(completed=True, papers=30, fields=6, populated_cells=180, cell_revisions=360,
            source_preparation={'papers': 30, 'full_text': 30, 'mode': 'SavedExampleProvider; local retained licensed XML'},
            semantic_assessment='all synthetic cells unassessed', cells_after_reopen=180, legacy_v1_papers=10,
            representative_cell={'value_characters_approx': 330, 'references': 1, 'inspected_ranges': 1, 'max_excerpt_characters': 256},
            legacy_v1_fixture='current serialization using unchanged legacy definition schema',
            limitation='Representative populated capacity; simultaneous maxima of every value/reference/revision bound remain subject to unchanged32MiB quota',
            rejected_papers=31, rejected_fields=7, atomic_quota_rollbacks=['workspace_bytes', 'request_count'],
            populated_storage=measured, final_storage=storage_measurement(store, workspace['id']),
            maximum_mutation_request_bytes=largest_body, max_draft_request_bytes=max(draft_bytes),
            max_cell_submit_request_bytes=max(submit_bytes), populated_view_response_bytes=len(populated.content),
            json_history_export_bytes=len(audit_response.content), csv_export_bytes=len(csv_response.content),
            live_network_calls=0, model_calls=0, automatic_candidate_requests=0,
            elapsed_seconds=round(time.monotonic() - started, 3))
    finally:
        client.close(); report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
