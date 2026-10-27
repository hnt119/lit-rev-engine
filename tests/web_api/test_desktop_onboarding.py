"""Desktop welcome progress boundaries; all provider/model work is forbidden."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import socket
import stat

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from src.mvp.ports import MvpError
from src.web_api.app import create_app
from src.web_api.runtime_settings import RuntimeSettings, SettingsPut, DesktopOnboardingPut
from src.web_api.settings_routes import configured_adapter, engine_for

OWNER = 'a' * 64
OTHER = 'b' * 64
KEY = 'SYNTHETIC-onboarding-marker-never-real'


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Welcome progress must not contact a provider or download a model')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    for key in ('MVP_MAP_ENABLED', 'MVP_SEARCH_PLANNER_ENABLED', 'MVP_PROPOSALS_ENABLED'):
        monkeypatch.setenv(key, '0')
    monkeypatch.delenv('NCBI_EMAIL', raising=False)
    monkeypatch.delenv('MVP_DEPLOYMENT_MODE', raising=False)


def progress(revision=0, step='sources', completed=False):
    return DesktopOnboardingPut(expected_revision=revision, step=step, completed=completed)


def config(settings):
    value = settings.get(OWNER)
    pref = deepcopy(value['preferences'])
    pref['ai'].update(provider='openai', model='fixture-only', model_revision='fixture.v1', planning_enabled=True)
    return SettingsPut(expected_revision=value['revision'], preferences=pref, ai_api_key=KEY)


def client(app):
    result = TestClient(app, base_url='http://127.0.0.1:8765')
    csrf = result.get('/api/v1/session').json()['csrf_token']
    result.headers.update({'Origin': 'http://127.0.0.1:3000', 'X-CSRF-Token': csrf})
    return result


def test_read_is_non_mutating_and_first_progress_does_not_activate_operator_settings(tmp_path):
    settings = RuntimeSettings(tmp_path)
    before = settings.get(OWNER)
    assert settings.get_onboarding(OWNER) == {'schema_version':'desktop-onboarding.v1', 'revision':0, 'step':'welcome', 'completed':False}
    assert list(settings.directory.iterdir()) == []
    value = settings.put_onboarding(OWNER, progress())
    assert value['revision'] == 1 and value['step'] == 'sources'
    assert settings.get(OWNER) == before
    assert settings.snapshot(OWNER)[0]['configured'] is False
    operator = object()
    assert engine_for(settings, OWNER, 'live', operator) is operator
    assert configured_adapter(settings, OWNER, 'planning')[0] is None
    assert settings.get_onboarding(OTHER)['revision'] == 0
    restarted = RuntimeSettings(tmp_path)
    assert restarted.get_onboarding(OWNER) == value
    assert restarted.get(OWNER) == before


def test_interleaved_configuration_and_progress_keep_separate_revisions_keys_and_consent(tmp_path):
    settings = RuntimeSettings(tmp_path)
    saved = settings.put(OWNER, config(settings))
    permit = settings.prepare(OWNER, saved['revision'], {'request':'fixture'}, {})
    first = settings.put_onboarding(OWNER, progress())
    assert settings.get(OWNER) == saved
    settings.consume(OWNER, saved['revision'], permit['consent_id'], {'request':'fixture'})
    updated = settings.put(OWNER, config(settings))
    assert settings.get_onboarding(OWNER) == first
    later = settings.put_onboarding(OWNER, progress(first['revision'], 'retrieval'))
    assert settings.get(OWNER) == updated
    assert settings.snapshot(OWNER)[1]['ai_api_key'] == KEY
    restarted = RuntimeSettings(tmp_path)
    assert restarted.get_onboarding(OWNER) == later
    assert restarted.get(OWNER)['credentials']['ai_api_key'] is False
    for path in settings.directory.iterdir():
        assert KEY.encode() not in path.read_bytes()
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_conflicting_windows_do_not_overwrite_progress_or_configuration(tmp_path):
    settings = RuntimeSettings(tmp_path)
    saved = settings.put(OWNER, config(settings))
    def write(step):
        try:
            return settings.put_onboarding(OWNER, progress(step=step))
        except MvpError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ['sources', 'retrieval']))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert results.count('stale_onboarding') == 1
    assert settings.get(OWNER) == saved
    retained = settings.get_onboarding(OWNER)
    with pytest.raises(MvpError, match='another window'):
        settings.put_onboarding(OWNER, progress())
    assert settings.get_onboarding(OWNER) == retained


def test_completion_is_not_reset_by_reopening_optional_steps(tmp_path):
    settings = RuntimeSettings(tmp_path)
    with pytest.raises(MvpError, match='final step'):
        settings.put_onboarding(OWNER, progress(step='ai', completed=True))
    complete = settings.put_onboarding(OWNER, progress(step='ready', completed=True))
    reopened = settings.put_onboarding(OWNER, progress(complete['revision'], 'retrieval'))
    assert reopened['completed'] is True and reopened['step'] == 'retrieval'
    assert RuntimeSettings(tmp_path).get_onboarding(OWNER) == reopened
    assert settings.get(OWNER)['configured'] is False


@pytest.mark.parametrize('data', [
    {'expected_revision':True, 'step':'sources', 'completed':False},
    {'expected_revision':0, 'step':'../../private', 'completed':False},
    {'expected_revision':0, 'step':'ai', 'completed':'true'},
    {'expected_revision':0, 'step':'ai', 'completed':False, 'api_key':KEY},
    {'expected_revision':0, 'step':'ai', 'completed':False, 'question':'private research'},
])
def test_progress_contract_rejects_credentials_text_and_unbounded_fields(data):
    with pytest.raises(ValidationError):
        DesktopOnboardingPut.model_validate(data)


def test_failed_atomic_write_preserves_prior_record_and_memory_keys(tmp_path, monkeypatch):
    settings = RuntimeSettings(tmp_path)
    saved = settings.put(OWNER, config(settings))
    old = settings.put_onboarding(OWNER, progress())
    path = settings.directory / (OWNER + '.json')
    before = path.read_bytes()
    def fail(*args):
        raise OSError('synthetic write interruption')
    monkeypatch.setattr('src.web_api.runtime_settings.atomic_replace', fail)
    with pytest.raises(OSError, match='interruption'):
        settings.put_onboarding(OWNER, progress(old['revision'], 'ai'))
    assert path.read_bytes() == before
    assert settings.get(OWNER) == saved
    assert settings.get_onboarding(OWNER) == old
    assert len(list(settings.directory.iterdir())) == 1


def test_legacy_settings_record_is_not_rewritten_and_keeps_its_projection(tmp_path):
    settings = RuntimeSettings(tmp_path)
    saved = settings.put(OWNER, config(settings))
    path = settings.directory / (OWNER + '.json')
    before = path.read_bytes()
    assert 'onboarding' not in json.loads(before)
    assert settings.get_onboarding(OWNER)['revision'] == 0
    assert settings.get(OWNER) == saved and path.read_bytes() == before
    settings.put_onboarding(OWNER, progress())
    assert settings.get(OWNER) == saved
    bad = json.loads(path.read_text())
    bad['onboarding']['credential'] = KEY
    path.write_text(json.dumps(bad))
    with pytest.raises(MvpError, match='invalid'):
        settings.get_onboarding(OWNER)
    assert settings.get(OWNER) == saved
    assert settings.snapshot(OWNER)[0]['configured'] is True
    with pytest.raises(MvpError, match='invalid'):
        settings.put_onboarding(OWNER, progress(1, 'ai'))


def test_desktop_only_session_origin_csrf_restart_and_export_boundaries(tmp_path, monkeypatch):
    monkeypatch.setenv('LITREV_DESKTOP_RUNTIME_MODE', 'managed')
    app = create_app(tmp_path)
    browser = client(app)
    assert browser.get('/api/v1/capabilities').json()['desktop_onboarding_ready'] is True
    uri = '/api/v1/settings/onboarding'
    assert TestClient(app, base_url='http://127.0.0.1:8765').get(uri).status_code == 404
    request = progress(step='ready', completed=True).model_dump()
    assert browser.put(uri, json=request, headers={'Origin':'https://untrusted.invalid'}).status_code == 403
    assert browser.put(uri, json=request, headers={'X-CSRF-Token':'wrong'}).status_code == 403
    response = browser.put(uri, json=request)
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    assert browser.put(uri, json=request).status_code == 409
    assert client(app).get(uri).json()['completed'] is False
    workspace = browser.post('/api/v1/workspaces', json={'request_id':'onboarding-export-fixture', 'mode':'saved_example'}).json()
    exported = browser.get('/api/v1/workspaces/'+workspace['id']+'/exports?format=json')
    assert exported.status_code == 200 and 'desktop-onboarding' not in exported.text
    reopened = TestClient(create_app(tmp_path), base_url='http://127.0.0.1:8765')
    reopened.cookies.update(browser.cookies)
    assert reopened.get(uri).json() == response.json()


def test_source_browser_never_gets_desktop_gate_or_progress_mutation(tmp_path, monkeypatch):
    monkeypatch.delenv('LITREV_DESKTOP_RUNTIME_MODE', raising=False)
    app = create_app(tmp_path)
    browser = client(app)
    assert browser.get('/api/v1/capabilities').json()['desktop_onboarding_ready'] is False
    assert browser.get('/api/v1/settings/onboarding').status_code == 404
    assert browser.put('/api/v1/settings/onboarding', json=progress().model_dump()).status_code == 404
    assert not list(app.state.runtime_settings.directory.iterdir())
