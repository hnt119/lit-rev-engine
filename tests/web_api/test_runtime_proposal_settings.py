"""Cloud wiring over retained public sources; all model output is synthetic."""
from copy import deepcopy
import json
import pytest

from src.mvp.contracts import canonical, digest, SearchPreview
from test_proposals_independent import proposal_api, offline_only


@pytest.mark.parametrize('provider', ['openai', 'deepseek'])
def test_session_cloud_board_round_trip_requires_exact_one_run_consent(proposal_api, monkeypatch, provider):
    _, client, root, board, view, legacy, request = proposal_api
    state = client.get('/api/v1/settings').json()
    preferences = deepcopy(state['preferences'])
    preferences['ai'].update(provider=provider, model='synthetic-model-snapshot', model_revision='mock-profile.v1', proposals_enabled=True)
    saved = client.put('/api/v1/settings', json={'expected_revision': 0, 'preferences': preferences,
        'ai_api_key': 'SYNTHETIC-session-key-not-a-real-account'})
    assert saved.status_code == 200, saved.text
    request = {**request, 'settings_revision': saved.json()['revision']}
    calls = []
    def mock_call(self, body, timeout_seconds):
        data = json.loads(body)
        packet = json.loads(data['messages'][-1]['content'])
        calls.append((self.provider, packet, timeout_seconds, data))
        evidence = {e['evidence_id']: e for e in packet['evidence']}
        cells = []
        for field in packet['fields']:
            identifiers = field['evidence_ids']
            cells.append({'field_id': field['field_id'], 'value': 'SYNTHETIC unsupported interpretation' if identifiers else None,
                'references': [{'evidence_id': identifiers[0], 'quote': evidence[identifiers[0]]['reference']['quote']}] if identifiers else [],
                'reason': 'Software fixture: exact words never establish scientific support',
                'missing_information': '' if identifiers else 'No evidence in the bounded retrieved context',
                'context_scope': 'retrieved_context_only'})
        return canonical({'model': 'synthetic-model-snapshot', 'choices': [{'finish_reason': 'stop', 'message': {
            'role': 'assistant', 'content': canonical({'cells': cells})}}], 'usage': {
            'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20}}).encode()
    monkeypatch.setattr('src.mvp.adapters.cloud_generation.CloudJSONTransport.request', mock_call)
    assert client.post(board + '/proposal-runs', json=request).status_code == 422
    assert calls == []
    prepared = client.post(board + '/prepare-generation', json=request)
    assert prepared.status_code == 200, prepared.text
    assert prepared.json()['max_calls'] == 1 and calls == [] and legacy.calls == []
    generated = client.post(board + '/proposal-runs', json={**request, 'consent_id': prepared.json()['consent_id']})
    assert generated.status_code == 200, generated.text
    run = generated.json()
    assert run['state'] == 'succeeded', run
    assert len(calls) == 1 and calls[0][0] == provider
    for suggestion in run['proposals']:
        assert suggestion['semantic_assessment'] == 'unassessed'
        assert suggestion['review_state'] == 'ai_suggestion_needs_review_not_independently_verified'
        assert suggestion['model_profile']['settings_revision'] == request['settings_revision']
    assert client.post(board + '/proposal-runs', json={**request, 'consent_id': prepared.json()['consent_id']}).status_code == 422
    assert len(calls) == 1
    exported = client.get(root + '/exports?format=json')
    assert exported.status_code == 200 and 'SYNTHETIC-session-key' not in exported.text
    # Generation neither submits nor changes the existing manual cell draft.
    current = client.get(board).json()
    assert current['cells'] == view['cells']


def test_historical_preview_without_new_metadata_preserves_serialization_digest():
    legacy = SearchPreview(query='historical query', total_reported=0, fetched_count=0,
                           truncated=False, searched_at='2026-01-01T00:00:00+00:00').model_dump(mode='json')
    assert 'requested_max_results' not in legacy and 'configuration_profile' not in legacy
    expected = digest(legacy)
    restored = SearchPreview.model_validate(legacy)
    assert digest(restored.model_dump(mode='json')) == expected
    future = restored.model_copy(update={'requested_max_results': 30, 'configuration_profile': {'settings_revision': 1}})
    assert future.model_dump(mode='json')['requested_max_results'] == 30
    assert 'requested_max_results' not in restored.model_dump(mode='json')
