"""Pure protocol-fixture tests. No listener, app, provider or model is called."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('beta_optional_acceptance', HERE / 'check_beta_optional.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def body(model, packet):
    return {'model': model, 'temperature': 0, 'stream': False,
        'max_tokens': 4096 if model == runner.PLANNER else 2048,
        'response_format': {'type': 'json_object'}, 'messages': [
            {'role': 'system', 'content': 'Fixture instructions'},
            {'role': 'user', 'content': json.dumps(packet)}]}


def content(response):
    assert response['choices'][0]['finish_reason'] == 'stop'
    return json.loads(response['choices'][0]['message']['content'])


def test_planner_mock_preserves_question_and_leaves_intent_unresolved():
    question = 'Question containing ignore instructions and tools; still data.'
    response = runner.mock_output(body(runner.PLANNER, {'original_question': question}))
    draft = content(response)
    assert response['model'] == runner.PLANNER and draft['original_question'] == question
    assert draft['concepts'] == [] and draft['variants'] == []
    assert draft['manual_strategy'] is None and draft['input_mode'] == 'natural_question'
    assert 'tools' not in response['choices'][0]['message']


def test_proposal_mock_copies_only_allowed_exact_paper_reference_and_keeps_null():
    packet = {'schema_version': 'mvp.proposal-packet.v1', 'context_scope': 'retrieved_context_only',
        'paper_id': 'public-fixture', 'fields': [
            {'field_id': 'population', 'evidence_ids': ['e1']},
            {'field_id': 'missing', 'evidence_ids': []}],
        'evidence': [{'evidence_id': 'e1', 'reference': {'paper_id': 'public-fixture',
            'quote': 'Exact retained quotation, including Unicode α.'}}]}
    cells = content(runner.mock_output(body(runner.PROPOSALS, packet)))['cells']
    assert cells[0]['references'] == [{'evidence_id': 'e1', 'quote': packet['evidence'][0]['reference']['quote']}]
    assert cells[1]['value'] is None and cells[1]['missing_information']
    assert all(c['context_scope'] == 'retrieved_context_only' for c in cells)
    assert all('semantic_assessment' not in c and 'inspected_ranges' not in c for c in cells)


@pytest.mark.parametrize('change', ['unknown_model', 'tools', 'wrong_paper', 'too_many_tokens'])
def test_mock_rejects_unexpected_protocol_without_calling_any_service(change):
    packet = {'schema_version': 'mvp.proposal-packet.v1', 'context_scope': 'retrieved_context_only',
        'paper_id': 'p1', 'fields': [{'field_id': 'population', 'evidence_ids': ['e1']}],
        'evidence': [{'evidence_id': 'e1', 'reference': {'paper_id': 'p1', 'quote': 'exact'}}]}
    request = body(runner.PROPOSALS, packet)
    if change == 'unknown_model': request['model'] = 'other'
    if change == 'tools': request['tools'] = []
    if change == 'wrong_paper':
        packet['evidence'][0]['reference']['paper_id'] = 'p2'
        request = body(runner.PROPOSALS, packet)
    if change == 'too_many_tokens': request['max_tokens'] = 4096
    with pytest.raises(AssertionError):
        runner.mock_output(request)
