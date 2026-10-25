"""Navigation is a bounded UI hint, never a research assessment or evidence record."""
from copy import deepcopy
from urllib.parse import quote
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from src.mvp.cell_editor_contracts import BoardEditorViewDraft
from test_board_passage_flow import flow


def target(c, board=None, revision=None):
    scope = 'board-editor:' + (board or c.scope['board_id']) + ':' + (revision or c.scope['board_revision_id'])
    return c.root + '/drafts/' + quote(scope, safe='')


def data(c, **updates):
    value = {'schema_version': 'mvp.board-editor-view.v1', 'board_id': c.scope['board_id'],
        'board_revision_id': c.scope['board_revision_id'], 'cells': [
            {'paper_id': c.definition['paper_ids'][0], 'field_id': 'diet:field', 'step': 'comment'}]}
    value.update(updates)
    return value


def save(c, value=None, version=0, **extra):
    return c.client.put(target(c), json={'version': version, 'data': value or data(c), **extra})


def test_editor_positions_roundtrip_without_scientific_or_retrieval_side_effects(flow):
    c = flow
    before = c.client.get(c.board + '/exports?format=json').json()
    counts = (c.sources.search_calls, c.sources.prepare_calls, len(c.ranker.corpora))
    assert c.client.get(target(c)).json()['version'] == 0
    result = save(c)
    assert result.status_code == 200, result.text
    assert result.json()['data'] == data(c)
    assert result.json()['version'] == 1
    assert c.client.get(target(c)).json() == result.json()
    assert c.client.get(c.board + '/exports?format=json').json() == before
    assert counts == (c.sources.search_calls, c.sources.prepare_calls, len(c.ranker.corpora))
    assert all(cell['head'] is None for cell in c.client.get(c.board).json()['cells'])


def test_navigation_cas_never_overwrites_other_tab_or_cell_drafts(flow):
    c = flow
    assert save(c).status_code == 200
    earlier = c.client.get(target(c)).json()
    changed = data(c); changed['cells'][0]['step'] = 'review'
    assert save(c, changed).status_code == 409
    assert c.client.get(target(c)).json() == earlier
    result = save(c, changed, version=1)
    assert result.status_code == 200 and result.json()['version'] == 2


@pytest.mark.parametrize('bad', ['unknown_paper', 'unknown_field', 'duplicate', 'unknown_step',
    'other_board', 'other_revision', 'scientific_fields', 'notes'])
def test_navigation_rejects_foreign_unbounded_or_scientific_data(flow, bad):
    c = flow; value = data(c)
    if bad == 'unknown_paper': value['cells'][0]['paper_id'] = 'foreign:paper'
    if bad == 'unknown_field': value['cells'][0]['field_id'] = 'foreign'
    if bad == 'duplicate': value['cells'] *= 2
    if bad == 'unknown_step': value['cells'][0]['step'] = 'human_supported'
    if bad == 'other_board': value['board_id'] = 'different'
    if bad == 'other_revision': value['board_revision_id'] = 'different'
    if bad == 'scientific_fields': value['semantic_assessment'] = 'human_supported'
    if bad == 'notes': value['cells'][0]['notes'] = 'synthetic unsubmitted research comment must stay in cell draft'
    result = save(c, value)
    assert result.status_code in {400, 404, 409, 422}, result.text
    assert c.client.get(target(c)).json()['version'] == 0


def test_navigation_cannot_set_assessment_head_or_cross_workspace_auth(flow):
    c = flow
    assert save(c, expected_assessment_head='foreign-assessment').status_code == 422
    other = TestClient(c.app, base_url='http://127.0.0.1:8765')
    session = other.get('/api/v1/session').json()
    other.headers.update({'Origin': 'http://127.0.0.1:3000', 'X-CSRF-Token': session['csrf_token']})
    assert other.get(target(c)).status_code in {403, 404}
    assert other.put(target(c), json={'version': 0, 'data': data(c)}).status_code in {403, 404}
    assert c.client.get(target(c)).json()['version'] == 0


def test_historical_navigation_remains_readable_but_cannot_mutate(flow):
    c = flow
    assert save(c).status_code == 200
    payload = {**c.request, 'request_id': 'editor-new-definition',
        'expected_revision_id': c.scope['board_revision_id'], 'question': 'Revised question'}
    result = c.client.post(c.board + '/revisions', json=payload)
    assert result.status_code == 200, result.text
    assert c.client.get(target(c)).json()['version'] == 1
    assert save(c, version=1).status_code == 409


def test_missing_source_cell_can_remember_only_navigation_without_fabricating_inspection(flow):
    c = flow; value = data(c)
    value['cells'][0]['paper_id'] = c.definition['paper_ids'][-1]
    value['cells'][0]['step'] = 'review'
    assert save(c, value).status_code == 200
    assert all(cell['head'] is None for cell in c.client.get(c.board).json()['cells'])


def test_contract_supports_thirty_by_six_hints_in_one_bounded_scope():
    value = {'board_id': 'board', 'board_revision_id': 'revision', 'cells': [
        {'paper_id': f'paper-{paper}', 'field_id': f'field-{field}', 'step': 'evidence'}
        for paper in range(30) for field in range(6)]}
    assert len(BoardEditorViewDraft.model_validate(value).cells) == 180
    value['cells'].append({'paper_id': 'extra', 'field_id': 'extra', 'step': 'review'})
    with pytest.raises(ValidationError): BoardEditorViewDraft.model_validate(value)
