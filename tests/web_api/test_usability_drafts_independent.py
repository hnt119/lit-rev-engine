"""Offline ownership/CAS checks for recoverable UI inputs, never live inference."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from types import SimpleNamespace
from urllib.parse import quote
from uuid import uuid4
import socket

import pytest
from fastapi.testclient import TestClient

from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.contracts import Block, Paper, PreparedSource, SearchPreview, canonical
from src.mvp.service import MVPService
from src.web_api.app import create_app


class LocalRecords:
    def __init__(self):
        self.search_calls, self.source_calls = 0, []
        self.papers = [Paper(pmid=str(950000 + index), title=f'SYNTHETIC UI RECORD {index}',
            abstract='Retained synthetic citation text.') for index in range(31)]

    def search(self, request):
        self.search_calls += 1
        return SearchPreview(query=request.query, papers=self.papers, total_reported=31, fetched_count=31,
            ordered_identifiers=[paper.id for paper in self.papers], truncated=False,
            mode='test', provider='synthetic-ui-draft')

    def prepare(self, paper):
        self.source_calls.append(paper.id)
        return PreparedSource(paper_id=paper.id, status='abstract_only', source_type='abstract',
            provider='synthetic-ui-draft', source_url='', blocks=[Block(id='abstract:1', ordinal=1,
                text=paper.abstract, locator={'type': 'abstract'})])


def browser(app):
    client = TestClient(app, base_url='http://127.0.0.1:8765')
    csrf = client.get('/api/v1/session').json()['csrf_token']
    client.headers.update({'Origin': 'http://127.0.0.1:3000', 'X-CSRF-Token': csrf})
    return client


@pytest.fixture
def case(tmp_path, monkeypatch):
    for name in ('MVP_MAP_ENABLED', 'MVP_PROPOSALS_ENABLED', 'MVP_SEARCH_PLANNER_ENABLED'):
        monkeypatch.setenv(name, '0')
    monkeypatch.delenv('NCBI_EMAIL', raising=False)
    def denied(*args, **kwargs):
        pytest.fail('UI draft boundary attempted external networking')
    monkeypatch.setattr(socket, 'create_connection', denied)
    provider = LocalRecords()
    engine = MVPService(SQLiteWorkspaceStorage(tmp_path / 'research.sqlite3'), provider, provider)
    app = create_app(tmp_path, services={'saved_example': engine})
    client = browser(app)
    created = client.post('/api/v1/workspaces', json={'request_id': 'workspace', 'mode': 'saved_example'})
    created.raise_for_status()
    root = '/api/v1/workspaces/' + created.json()['id']
    searched = client.post(root + '/searches', json={'request_id': 'search', 'query': 'fixture', 'max_results': 50})
    searched.raise_for_status()
    return SimpleNamespace(app=app, client=client, root=root, provider=provider, engine=engine,
        path=tmp_path, search=searched.json(), workspace_id=created.json()['id'])


def draft_path(case, scope):
    return case.root + '/drafts/' + quote(scope, safe='')


def editor(**changes):
    raw = {'original_question': '', 'manual_strategy': ' \r\nquoted strategy\r\n ',
        'concepts': [{'id': 'concept', 'label': '', 'terms': [{'id': 'term', 'text': ''}]}],
        'variants': [{'id': 'variant', 'label': '', 'expression': {'op': 'concept_ref', 'concept_id': None, 'children': []}}],
        'ambiguities': [{'id': 'ambiguity', 'message': '', 'concept_ids': ['missing']}],
        'date_filter': {'date_from': '', 'date_to': '2026-'}}
    return {'draft': raw, 'plan_id': None, 'base_revision_id': None, **changes}


def handoff(case, count=3, **changes):
    return {'question': 'Exact clicked question', 'origin': {'kind': 'search', 'search_id': case.search['id']},
        'selected_paper_ids': [paper['id'] for paper in case.search['papers'][:count]],
        'expected_source_revision': 0, 'expected_preparation_id': None,
        'job_id': None, 'preparation_id': None, **changes}


def save(case, path, value, version=0):
    return case.client.put(path, json={'version': version, 'data': value})


def search_job(case, value, key='job'):
    response = case.client.post(case.root + '/preparation-jobs', json={'request_id': key,
        'search_id': value['origin']['search_id'], 'paper_ids': value['selected_paper_ids'],
        'expected_source_revision': value['expected_source_revision'],
        'expected_preparation_id': value['expected_preparation_id']})
    assert response.status_code == 202, response.text
    return response.json()['job']


def test_incomplete_editor_is_exact_recoverable_data_and_never_compiles(case, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Saving editable UI data must not compile or run a planner')
    monkeypatch.setattr('src.mvp.search_plans.compile_search_plan', forbidden)
    before = case.client.get(case.root).json()
    path = draft_path(case, 'search-plan-editor:new')
    assert case.client.get(path).json()['version'] == 0
    value = editor()
    saved = save(case, path, value)
    assert saved.status_code == 200, saved.text
    assert saved.json()['data'] == value
    assert case.client.get(path).json() == saved.json()
    reopened = TestClient(create_app(case.path, services={'saved_example': case.engine}), base_url='http://127.0.0.1:8765')
    reopened.cookies.update(case.client.cookies)
    assert reopened.get(path).json() == saved.json()
    assert case.client.get(case.root).json() == before
    assert case.client.get(case.root + '/search-plans').json()['plans'] == []
    assert case.provider.search_calls == 1 and case.provider.source_calls == []


@pytest.mark.parametrize('bad', ['concepts', 'terms', 'variants', 'ambiguities', 'expression', 'depth', 'label', 'term', 'shape'])
def test_editor_bounds_reject_atomically_but_not_incomplete_intent(case, bad):
    path = draft_path(case, 'search-plan-editor:new')
    original = save(case, path, editor()).json()
    value = editor()
    raw = value['draft']
    if bad == 'concepts': raw['concepts'] *= 13
    elif bad == 'terms': raw['concepts'][0]['terms'] *= 9
    elif bad == 'variants': raw['variants'] *= 4
    elif bad == 'ambiguities': raw['ambiguities'] *= 21
    elif bad == 'expression':
        expression = {'children': []}
        for _ in range(8): expression = {'children': [expression]}
        raw['variants'][0]['expression'] = expression
    elif bad == 'depth':
        nested = {}
        for _ in range(25): nested = {'child': nested}
        raw['extra'] = nested
    elif bad == 'label': raw['concepts'][0]['label'] = 'x' * 201
    elif bad == 'term': raw['concepts'][0]['terms'][0]['text'] = 'x' * 1001
    else: raw['concepts'] = [False]
    rejected = save(case, path, value, 1)
    assert rejected.status_code == 422, rejected.text
    assert case.client.get(path).json() == original
    assert case.provider.source_calls == []


def test_editor_retains_existing_byte_quota_and_cas(case):
    path = draft_path(case, 'search-plan-editor:new')
    saved = save(case, path, editor()).json()
    oversized = editor(draft={str(index): 'x' * 19000 for index in range(4)})
    rejected = save(case, path, oversized, 1)
    assert rejected.status_code == 422 and rejected.json()['error']['code'] == 'draft_limit'
    assert case.client.get(path).json() == saved
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda question: save(case, path, editor(draft={'original_question': question}), 1), ['one', 'two']))
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert case.client.get(path).json() in [response.json() for response in responses if response.status_code == 200]


def test_additive_drafts_share_existing_workspace_byte_and_scope_quotas(case):
    store = case.app.state.registry
    editor_path = draft_path(case, 'search-plan-editor:new')
    selection_path = draft_path(case, 'comparison-handoff:' + str(uuid4()))
    original = save(case, editor_path, editor()).json()
    store.max_workspace_draft_bytes = len(canonical(editor()).encode('utf-8'))
    rejected = save(case, selection_path, handoff(case))
    assert rejected.status_code == 422 and rejected.json()['error']['code'] == 'draft_limit'
    assert case.client.get(editor_path).json() == original
    assert case.client.get(selection_path).json()['version'] == 0
    store.max_workspace_draft_bytes = 2 * 1024 * 1024
    store.max_drafts = 2
    assert save(case, selection_path, handoff(case)).status_code == 200
    extra_path = draft_path(case, 'comparison-handoff:' + str(uuid4()))
    rejected = save(case, extra_path, handoff(case))
    assert rejected.status_code == 422 and rejected.json()['error']['code'] == 'draft_limit'
    assert case.client.get(extra_path).json()['version'] == 0
    assert case.client.get(editor_path).json() == original


def create_plan(case, key='plan'):
    response = case.client.post(case.root + '/search-plans', json={'request_id': key,
        'draft': {'original_question': 'Fixture plan', 'input_mode': 'manual_strategy', 'manual_strategy': 'fixture[tiab]'}})
    response.raise_for_status()
    return response.json()['revision']


def test_editor_scope_and_historical_revision_must_belong_to_the_plan(case, monkeypatch):
    revision = create_plan(case)
    other = create_plan(case, 'other-plan')
    path = draft_path(case, 'search-plan-editor:' + revision['plan_id'])
    value = editor(plan_id=revision['plan_id'], base_revision_id=revision['revision_id'])
    newer = case.client.put(case.root + '/search-plans/' + revision['plan_id'], json={'request_id': 'update',
        'expected_revision_id': revision['revision_id'], 'draft': revision['draft']})
    newer.raise_for_status()
    monkeypatch.setattr('src.mvp.search_plans.compile_search_plan', lambda *args: pytest.fail('Draft ownership must not compile'))
    saved = save(case, path, value)
    assert saved.status_code == 200 and saved.json()['data'] == value
    assert case.client.get(path).json() == saved.json()
    assert save(case, path, {**value, 'base_revision_id': other['revision_id']}, 1).status_code == 404
    assert save(case, path, {**value, 'plan_id': other['plan_id']}, 1).status_code == 422
    assert save(case, draft_path(case, 'search-plan-editor:new'), value).status_code == 422
    assert case.client.get(draft_path(case, 'search-plan-editor:missing')).status_code == 404
    assert case.client.get(path).json() == saved.json()


def test_exact_handoff_is_persisted_before_job_then_attaches_acknowledged_result(case):
    path = draft_path(case, 'comparison-handoff:' + str(uuid4()))
    value = handoff(case, 30)
    before = case.client.get(case.root).json()
    saved = save(case, path, value)
    assert saved.status_code == 200 and saved.json()['data'] == value
    assert case.client.get(case.root).json() == before and case.provider.source_calls == []
    job = search_job(case, value)
    acknowledged = {**value, 'job_id': job['id']}
    saved = save(case, path, acknowledged, 1)
    assert saved.status_code == 200
    assert case.app.state.preparation_worker.run_once()
    result = case.client.get(case.root + '/preparation-jobs/' + job['id']).json()
    completed = {**acknowledged, 'preparation_id': result['result_preparation_id']}
    final = save(case, path, completed, 2)
    assert final.status_code == 200, final.text
    assert case.client.get(path).json() == final.json()
    assert case.provider.source_calls == value['selected_paper_ids']
    assert case.client.get(case.root + '/boards').json()['boards'] == []
    # New scope may reopen the acknowledged historical input after publication.
    assert save(case, draft_path(case, 'comparison-handoff:' + str(uuid4())), completed).status_code == 200


@pytest.mark.parametrize('bad', ['order', 'question', 'origin', 'revision', 'unknown-paper', 'duplicate', '31', 'job', 'preparation'])
def test_handoff_rejects_retargeting_and_unowned_or_mismatched_records(case, bad):
    path = draft_path(case, 'comparison-handoff:' + str(uuid4()))
    value = handoff(case)
    saved = save(case, path, value).json()
    changed = deepcopy(value)
    if bad == 'order': changed['selected_paper_ids'].reverse()
    elif bad == 'question': changed['question'] = 'Different question'
    elif bad == 'origin': changed['origin']['search_id'] = 'foreign-search'
    elif bad == 'revision': changed['expected_source_revision'] = 99
    elif bad == 'unknown-paper': changed['selected_paper_ids'] = ['foreign-paper']
    elif bad == 'duplicate': changed['selected_paper_ids'] *= 2
    elif bad == '31': changed['selected_paper_ids'] = [paper['id'] for paper in case.search['papers']]
    elif bad == 'job':
        changed['job_id'] = search_job(case, handoff(case, 2))['id']
    else: changed['preparation_id'] = 'foreign-preparation'
    rejected = save(case, path, changed, 1)
    assert rejected.status_code in (404, 422), rejected.text
    assert case.client.get(path).json() == saved
    assert case.provider.source_calls == []


def test_handoff_preparation_reuse_is_exact_and_acknowledged_ids_cannot_be_retargeted(case):
    value = handoff(case)
    job = search_job(case, value)
    assert case.app.state.preparation_worker.run_once()
    result = case.client.get(case.root + '/preparation-jobs/' + job['id']).json()
    prepared = {**value, 'job_id': job['id'], 'preparation_id': result['result_preparation_id']}
    path = draft_path(case, 'comparison-handoff:' + str(uuid4()))
    saved = save(case, path, prepared)
    assert saved.status_code == 200, saved.text
    assert save(case, path, {**prepared, 'job_id': None}, 1).status_code == 422
    assert save(case, path, {**prepared, 'preparation_id': None}, 1).status_code == 422
    # Reuse captures the exact current preparation as the starting revision.
    reused = {**value, 'expected_source_revision': result['result_source_revision'],
        'expected_preparation_id': result['result_preparation_id'], 'preparation_id': result['result_preparation_id']}
    assert save(case, draft_path(case, 'comparison-handoff:' + str(uuid4())), reused).status_code == 200
    # The synchronous compatibility route can acknowledge an exact current +1
    # publication with no job, while keeping all clicked fields unchanged.
    assert save(case, draft_path(case, 'comparison-handoff:' + str(uuid4())), {**value, 'preparation_id': result['result_preparation_id']}).status_code == 200
    stale = save(case, path, prepared, 0)
    assert stale.status_code == 409 and stale.json()['error']['code'] == 'stale_draft'


def imported_collection(case):
    uploaded = case.client.post(case.root + '/imports/csv', content=b'Title,Abstract Note\nImported A,Text A\nImported B,Text B\n',
        headers={'Content-Type': 'text/csv', 'X-Request-ID': 'import'})
    uploaded.raise_for_status()
    rows = case.client.get(case.root + '/imports/' + uploaded.json()['id'] + '/rows').json()['rows']
    committed = case.client.post(case.root + '/imports/' + uploaded.json()['id'] + '/commit', json={'request_id': 'commit',
        'expected_revision': uploaded.json()['revision'], 'name': 'Synthetic import', 'accepted_row_ids': [row['id'] for row in rows]})
    committed.raise_for_status()
    collection = committed.json()
    papers = case.client.get(case.root + '/collections/' + collection['id'] + '/papers').json()['papers']
    return collection, papers


def test_collection_handoff_binds_snapshot_and_exact_order_through_job_publication(case):
    collection, papers = imported_collection(case)
    value = handoff(case, origin=collection['origin'], selected_paper_ids=[paper['id'] for paper in reversed(papers)])
    path = draft_path(case, 'comparison-handoff:' + str(uuid4()))
    saved = save(case, path, value)
    assert saved.status_code == 200, saved.text
    job = case.client.post(case.root + '/collection-preparation-jobs', json={'request_id': 'collection-job',
        'collection_ref': value['origin'], 'paper_ids': value['selected_paper_ids'],
        'expected_source_revision': 0, 'expected_preparation_id': None}).json()['job']
    assert save(case, path, {**value, 'job_id': job['id']}, 1).status_code == 200
    assert case.app.state.preparation_worker.run_once()
    result = case.client.get(case.root + '/collection-preparation-jobs/' + job['id']).json()
    complete = {**value, 'job_id': job['id'], 'preparation_id': result['result_preparation_id']}
    final = save(case, path, complete, 2)
    assert final.status_code == 200, final.text
    assert case.client.get(path).json() == final.json()
    wrong = {**value, 'origin': {**value['origin'], 'collection_snapshot_sha256': 'f' * 64}}
    assert save(case, draft_path(case, 'comparison-handoff:' + str(uuid4())), wrong).status_code == 409
    wrong_papers = {**value, 'selected_paper_ids': [case.search['papers'][0]['id']]}
    assert save(case, draft_path(case, 'comparison-handoff:' + str(uuid4())), wrong_papers).status_code == 422


def test_additive_scopes_preserve_session_csrf_and_scope_boundaries(case):
    paths = [draft_path(case, 'search-plan-editor:new'), draft_path(case, 'comparison-handoff:' + str(uuid4()))]
    other = browser(case.app)
    for path, value in zip(paths, [editor(), handoff(case)]):
        assert other.get(path).status_code == 404
        assert other.put(path, json={'version': 0, 'data': value}).status_code == 404
        assert case.client.get(path).json()['version'] == 0
    for scope in ['search-plan-editor:', 'comparison-handoff:no-uuid', 'unknown-scope']:
        assert case.client.get(draft_path(case, scope)).status_code == 422
    case.client.headers.pop('X-CSRF-Token')
    assert save(case, paths[0], editor()).status_code == 403


def test_synchronous_handoff_acknowledges_only_exact_immediate_current_publication(case):
    value = handoff(case)
    path = draft_path(case, 'comparison-handoff:' + str(uuid4()))
    assert save(case, path, value).status_code == 200
    prepared = case.client.post(case.root + '/source-preparations', json={'request_id': 'synchronous',
        'search_id': value['origin']['search_id'], 'paper_ids': value['selected_paper_ids']})
    prepared.raise_for_status()
    acknowledged = {**value, 'preparation_id': prepared.json()['id']}
    saved = save(case, path, acknowledged, 1)
    assert saved.status_code == 200
    # A later publication cannot be substituted for the originally clicked base.
    newer = case.client.post(case.root + '/source-preparations', json={'request_id': 'later',
        'search_id': value['origin']['search_id'], 'paper_ids': value['selected_paper_ids']})
    newer.raise_for_status()
    assert case.client.get(path).json() == saved.json()
    assert save(case, path, acknowledged, 2).status_code == 200
    assert save(case, draft_path(case, 'comparison-handoff:' + str(uuid4())),
        {**value, 'preparation_id': newer.json()['id']}).status_code == 422
    assert save(case, draft_path(case, 'comparison-handoff:' + str(uuid4())), acknowledged).status_code == 422


def test_actual_other_workspace_plan_search_job_and_preparation_references_are_rejected(case):
    created = case.client.post('/api/v1/workspaces', json={'request_id': 'other-workspace', 'mode': 'saved_example'})
    created.raise_for_status()
    root = '/api/v1/workspaces/' + created.json()['id']
    searched = case.client.post(root + '/searches', json={'request_id': 'other-search', 'query': 'fixture', 'max_results': 50})
    searched.raise_for_status()
    search = searched.json()
    plan = case.client.post(root + '/search-plans', json={'request_id': 'other-plan', 'draft': {'original_question': 'Other plan'}})
    plan.raise_for_status()
    revision = plan.json()['revision']
    editor_path = draft_path(case, 'search-plan-editor:' + revision['plan_id'])
    assert case.client.get(editor_path).status_code == 404
    assert save(case, editor_path, editor(plan_id=revision['plan_id'], base_revision_id=revision['revision_id'])).status_code == 404
    job = case.client.post(root + '/preparation-jobs', json={'request_id': 'other-job', 'search_id': search['id'],
        'paper_ids': [paper['id'] for paper in search['papers'][:3]], 'expected_source_revision': 0, 'expected_preparation_id': None})
    assert job.status_code == 202
    assert case.app.state.preparation_worker.run_once()
    result = case.client.get(root + '/preparation-jobs/' + job.json()['job']['id']).json()
    for changes in [
        {'origin': {'kind': 'search', 'search_id': search['id']}},
        {'job_id': result['id']},
        {'preparation_id': result['result_preparation_id']},
        {'expected_source_revision': 1, 'expected_preparation_id': result['result_preparation_id']},
    ]:
        path = draft_path(case, 'comparison-handoff:' + str(uuid4()))
        assert save(case, path, handoff(case, **changes)).status_code == 404
        assert case.client.get(path).json()['version'] == 0


def test_import_intake_recovers_exact_text_without_importing_or_storing_file_bytes(case):
    path = draft_path(case, 'import-intake')
    value = {'format': 'identifiers', 'identifiers': ' \r\nPMID: 123\nunfinished DOI: 10.\r\n '}
    before = case.client.get(case.root + '/imports').json()
    saved = save(case, path, value)
    assert saved.status_code == 200 and saved.json()['data'] == value
    assert case.client.get(path).json() == saved.json()
    assert case.client.get(case.root + '/imports').json() == before
    assert case.provider.source_calls == []
    stale = save(case, path, {**value, 'identifiers': 'changed'}, 0)
    assert stale.status_code == 409 and stale.json()['error']['code'] == 'stale_draft'
    other = browser(case.app)
    assert other.get(path).status_code == 404
    assert other.put(path, json={'version': 0, 'data': value}).status_code == 404


@pytest.mark.parametrize('bad', ['format', 'text-bound', 'file-bytes', 'byte-quota'])
def test_import_intake_bounds_and_quota_fail_without_losing_saved_text(case, bad):
    path = draft_path(case, 'import-intake')
    value = {'format': 'csv', 'identifiers': ''}
    saved = save(case, path, value).json()
    if bad == 'format': value['format'] = 'pdf'
    elif bad == 'text-bound': value['identifiers'] = 'x' * 20001
    elif bad == 'file-bytes': value['bytes'] = [1, 2, 3]
    else: value['identifiers'] = '😀' * 20000
    rejected = save(case, path, value, 1)
    assert rejected.status_code == 422
    if bad == 'byte-quota': assert rejected.json()['error']['code'] == 'draft_limit'
    assert case.client.get(path).json() == saved
