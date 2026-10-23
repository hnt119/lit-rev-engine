"""Bounded manual passage counts over synthetic retained sources, entirely offline."""
from copy import deepcopy
import json
import socket
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.mvp.adapters.retrieval import LexicalRetrieval
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.board_contracts import BoardCandidatesRequest
from src.mvp.contracts import Block, Paper, PreparedSource, SearchPreview, canonical
from src.mvp.proposal_contracts import ProposalCapability
from src.mvp.service import MVPService
from src.web_api.app import create_app


class LocalSources:
    def __init__(self):
        self.search_calls, self.prepare_calls = 0, 0
        self.paper = Paper(pmid='970001', title='SYNTHETIC PASSAGE CAPACITY', abstract='Synthetic microbiome text.')

    def search(self, request):
        self.search_calls += 1
        return SearchPreview(query=request.query, papers=[self.paper], total_reported=1, fetched_count=1,
            ordered_identifiers=[self.paper.id], truncated=False, mode='test', provider='synthetic-passage-capacity')

    def prepare(self, paper):
        self.prepare_calls += 1
        return PreparedSource(paper_id=paper.id, status='full_text_retrieved', source_type='full_text', license='Synthetic software fixture',
            provider='synthetic-passage-capacity', source_url='', blocks=[Block(id=f'body:{index}', ordinal=index,
                text=f'SYNTHETIC passage {index}. Microbiome diversity data in this retained block.',
                locator={'type': 'body', 'section': str(index)}) for index in range(1, 46)])


class CountingRetrieval(LexicalRetrieval):
    def __init__(self):
        self.calls = []

    def search(self, question, sources, run_id, top_k=5):
        self.calls.append(top_k)
        return super().search(question, sources, run_id, top_k)


@pytest.fixture
def passage_case(tmp_path, monkeypatch):
    for name in ('MVP_MAP_ENABLED', 'MVP_PROPOSALS_ENABLED', 'MVP_SEARCH_PLANNER_ENABLED'):
        monkeypatch.setenv(name, '0')
    monkeypatch.delenv('NCBI_EMAIL', raising=False)
    monkeypatch.setattr(socket, 'create_connection', lambda *args, **kwargs: pytest.fail('Passage tests attempted external networking'))
    provider, retrieval = LocalSources(), CountingRetrieval()
    engine = MVPService(SQLiteWorkspaceStorage(tmp_path / 'research.sqlite3'), provider, provider, retrieval)
    app = create_app(tmp_path, services={'saved_example': engine})
    client = TestClient(app, base_url='http://127.0.0.1:8765')
    csrf = client.get('/api/v1/session').json()['csrf_token']
    client.headers.update({'Origin': 'http://127.0.0.1:3000', 'X-CSRF-Token': csrf})
    created = client.post('/api/v1/workspaces', json={'request_id': 'workspace', 'mode': 'saved_example'})
    created.raise_for_status()
    root = '/api/v1/workspaces/' + created.json()['id']
    searched = client.post(root + '/searches', json={'request_id': 'search', 'query': 'synthetic'})
    searched.raise_for_status()
    prepared = client.post(root + '/source-preparations', json={'request_id': 'prepare', 'search_id': searched.json()['id'],
        'paper_ids': [provider.paper.id]})
    prepared.raise_for_status()
    assert prepared.json()['sources'][0]['source_type'] == 'full_text'
    assert prepared.json()['sources'][0]['block_count'] == 45
    return SimpleNamespace(app=app, client=client, engine=engine, root=root, provider=provider, retrieval=retrieval,
        preparation=prepared.json(), workspace_id=created.json()['id'])


def retrieve(case, top_k=5, *, key='run', question='microbiome diversity'):
    return case.client.post(case.root + '/evidence-runs', json={'request_id': key, 'question': question, 'top_k': top_k,
        'expected_source_revision': case.preparation['source_revision'], 'expected_preparation_id': case.preparation['id']})


@pytest.mark.parametrize('count', range(1, 31))
def test_every_manual_count_and_legacy_one_to_four_have_exact_immutable_receipts(passage_case, count):
    case = passage_case
    parameters = deepcopy(case.retrieval.parameters)
    result = retrieve(case, count)
    assert result.status_code == 200, result.text
    run = result.json()
    assert run['parameters']['top_k'] == run['parameters']['returned_count'] == len(run['passages']) == count
    assert run['preparation_id'] == case.preparation['id'] and run['source_revision'] == case.preparation['source_revision']
    assert [passage['rank'] for passage in run['passages']] == list(range(1, count + 1))
    assert len({(passage['source_id'], passage['anchor']['block_id'], passage['anchor']['start'], passage['anchor']['end'])
        for passage in run['passages']}) == count
    assert case.retrieval.calls == [count]
    assert case.retrieval.parameters == parameters and 'top_k' not in parameters and 'returned_count' not in parameters
    reopened = case.client.get(case.root + '/runs/' + run['id'])
    assert reopened.json()['run'] == run
    assert case.provider.search_calls == case.provider.prepare_calls == 1


@pytest.mark.parametrize('count', [31, 0, -1, True, 7.5, '10'])
def test_bad_count_is_rejected_before_mutation_or_ranking(passage_case, count):
    case = passage_case
    before = case.client.get(case.root).json()
    rejected = retrieve(case, count)
    assert rejected.status_code == 422
    assert case.retrieval.calls == [] and case.client.get(case.root).json() == before


def test_limit_is_in_existing_fingerprint_and_old_runs_are_not_retargeted(passage_case):
    case = passage_case
    first = retrieve(case, 5)
    assert first.status_code == 200
    original = canonical(first.json())
    assert retrieve(case, 5).json() == first.json() and case.retrieval.calls == [5]
    conflict = retrieve(case, 30)
    assert conflict.status_code == 409 and conflict.json()['error']['code'] == 'idempotency_conflict'
    assert case.retrieval.calls == [5]
    next_run = retrieve(case, 17, key='different-limit')
    assert next_run.status_code == 200
    assert canonical(case.client.get(case.root + '/runs/' + first.json()['id']).json()['run']) == original
    assert [passage['anchor'] for passage in next_run.json()['passages'][:5]] == [passage['anchor'] for passage in first.json()['passages']]
    assert case.retrieval.calls == [5, 17]


@pytest.mark.parametrize('question,actual', [('microbiome', 30), ('unmatchableterm', 0)])
def test_returned_receipt_never_pads_or_invents_matches(passage_case, question, actual):
    case = passage_case
    result = retrieve(case, 30, question=question)
    assert result.status_code == 200
    assert result.json()['parameters']['returned_count'] == len(result.json()['passages']) == actual
    if actual == 0:
        assert result.json()['matched_passages'] == 0


def test_fewer_available_matches_return_fewer_than_requested(passage_case):
    case = passage_case
    # Only one retained block contains this explicit rare term.
    result = retrieve(case, 30, question='45')
    assert result.status_code == 200
    run = result.json()
    assert run['parameters']['top_k'] == 30
    assert run['parameters']['returned_count'] == run['matched_passages'] == len(run['passages']) == 1


def test_actual_legacy_run_parameters_remain_exact_after_new_retrieval(passage_case):
    case = passage_case
    run = retrieve(case).json()
    # Simulate a retained pre-expansion artifact in this isolated temporary DB.
    # New receipt keys are absent; loading and later writes must not inject them.
    with case.engine._storage._connection() as db:
        raw = json.loads(db.execute('SELECT snapshot FROM mvp_workspaces WHERE id=?', (case.workspace_id,)).fetchone()[0])
        legacy = deepcopy(raw['runs'][0])
        legacy['parameters'].pop('top_k')
        legacy['parameters'].pop('returned_count')
        raw['runs'][0] = legacy
        db.execute('UPDATE mvp_workspaces SET snapshot=? WHERE id=?', (canonical(raw), case.workspace_id))
    before = canonical(legacy)
    assert canonical(case.client.get(case.root + '/runs/' + run['id']).json()['run']) == before
    newer = retrieve(case, 30, key='new-receipt')
    assert newer.status_code == 200
    with case.engine._storage._connection() as db:
        current = json.loads(db.execute('SELECT snapshot FROM mvp_workspaces WHERE id=?', (case.workspace_id,)).fetchone()[0])
    assert canonical(current['runs'][0]) == before
    assert newer.json()['parameters']['top_k'] == 30


def test_thirty_judgment_rows_fit_but_large_notes_retain_existing_draft_quota(passage_case):
    case = passage_case
    run = retrieve(case, 30).json()
    path = case.root + '/drafts/assessment:' + run['id']
    body = {'passages': [{'passage_id': passage['id'], 'decision': 'unreviewed', 'notes': ''} for passage in run['passages']],
        'bundle': {'status': 'not_assessed', 'reason': '', 'missing_information': '', 'supporting_passage_ids': [], 'contradiction': False},
        'feedback': '', 'supersedes_id': None, 'editing': True}
    saved = case.client.put(path, json={'version': 0, 'data': body})
    assert saved.status_code == 200
    oversized = deepcopy(body)
    for judgment in oversized['passages']:
        judgment['notes'] = 'x' * 3000
    rejected = case.client.put(path, json={'version': 1, 'data': oversized})
    assert rejected.status_code == 422 and rejected.json()['error']['code'] == 'draft_limit'
    assert case.client.get(path).json() == saved.json()
    with pytest.raises(ValidationError):
        BoardCandidatesRequest(request_id='candidate', expected_revision_id='revision', paper_id='paper', field_id='field', top_k=4)
    capability = ProposalCapability()
    assert (capability.max_papers, capability.max_cells, capability.max_calls) == (3, 9, 3)
