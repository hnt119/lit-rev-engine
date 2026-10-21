"""Invalid optional model settings cannot disable the manual workspace."""
from fastapi.testclient import TestClient
from src.web_api.app import create_app


def test_invalid_optional_generation_configuration_keeps_manual_workspace_available(tmp_path, monkeypatch):
    monkeypatch.setenv('MVP_PROPOSALS_ENABLED', '1')
    monkeypatch.setenv('MVP_PROPOSALS_URL', 'https://remote.invalid/v1/chat/completions')
    monkeypatch.setenv('MVP_PROPOSALS_MODEL', 'software-model')
    monkeypatch.setenv('MVP_PROPOSALS_MODEL_REVISION', 'software-revision')
    app = create_app(tmp_path)
    assert app.state.proposals.capabilities().enabled is False
    assert app.state.proposal_configuration_error
    client = TestClient(app, base_url='http://127.0.0.1:8765')
    csrf = client.get('/api/v1/session').json()['csrf_token']
    client.headers.update({'Origin': 'http://127.0.0.1:3000', 'X-CSRF-Token': csrf})
    response = client.post('/api/v1/workspaces', json={
        'request_id': 'manual-still-available', 'mode': 'saved_example', 'question': 'Software configuration check'})
    assert response.status_code == 200
    assert client.get('/api/v1/workspaces/' + response.json()['id']).status_code == 200
