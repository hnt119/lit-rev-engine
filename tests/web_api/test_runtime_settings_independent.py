"""Independent offline settings ownership/consent checks; no provider calls."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
import socket
import stat

import pytest
from fastapi.testclient import TestClient

from src.mvp.ports import MvpError
from src.web_api.app import create_app
from src.web_api.runtime_settings import RuntimeSettings, SettingsPut

OWNER_A = 'a' * 64
OWNER_B = 'b' * 64
KEY_A = 'SYNTHETIC-owner-a-key-never-a-real-secret'
KEY_NCBI = 'SYNTHETIC-ncbi-key-never-real'


@pytest.fixture
def no_external(monkeypatch):
    calls = []
    def deny(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError('Independent settings checks must never contact an external provider')
    monkeypatch.setattr(socket, 'create_connection', deny)
    return calls


def payload(settings, owner=OWNER_A, *, provider='none', ai_key=None, include_key=False):
    current = settings.get(owner)
    preferences = deepcopy(current['preferences'])
    preferences['pubmed'] = {'enabled': True, 'email': 'synthetic@example.invalid'}
    preferences['ai'].update(provider=provider, model='fixture-model' if provider != 'none' else '',
        model_revision='fixture-profile.v1' if provider != 'none' else '', planning_enabled=provider != 'none')
    result = {'expected_revision': current['revision'], 'preferences': preferences}
    if include_key:
        result['ai_api_key'] = ai_key
    return result


def test_save_and_read_have_no_outbound_or_process_environment_mutation(tmp_path, no_external):
    before = dict(os.environ)
    settings = RuntimeSettings(tmp_path)
    result = settings.put(OWNER_A, SettingsPut.model_validate(payload(settings)))
    assert result['preferences']['pubmed']['enabled'] is True
    assert result['credentials']['ncbi_api_key'] is False
    assert result['status']['pubmed']['state'] == 'Not tested'
    assert settings.get(OWNER_A) == result
    assert no_external == []
    assert dict(os.environ) == before


def test_credentials_are_session_scoped_redacted_and_never_written(tmp_path, no_external):
    settings = RuntimeSettings(tmp_path)
    request = payload(settings, provider='openai', ai_key=KEY_A, include_key=True)
    request['ncbi_api_key'] = KEY_NCBI
    result = settings.put(OWNER_A, SettingsPut.model_validate(request))
    assert result['credentials'] == {'ai_api_key': True, 'ncbi_api_key': True}
    assert KEY_A not in str(result) and KEY_NCBI not in str(result)
    second = settings.get(OWNER_B)
    assert second['revision'] == 0 and not any(second['credentials'].values())
    assert settings.snapshot(OWNER_B)[1] == {}
    files = [path for path in tmp_path.rglob('*') if path.is_file()]
    assert files
    for path in files:
        assert KEY_A.encode() not in path.read_bytes() and KEY_NCBI.encode() not in path.read_bytes()
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert no_external == []


def test_restart_preserves_preferences_but_clears_all_keys_and_tests(tmp_path, no_external):
    settings = RuntimeSettings(tmp_path)
    value = settings.put(OWNER_A, SettingsPut.model_validate(payload(settings, provider='deepseek', ai_key=KEY_A, include_key=True)))
    settings.record_test(OWNER_A, value['revision'], 'ai', True)
    restarted = RuntimeSettings(tmp_path)
    result = restarted.get(OWNER_A)
    assert result['preferences'] == value['preferences']
    assert result['revision'] == value['revision']
    assert not any(result['credentials'].values())
    assert result['status']['ai']['state'] != 'Last test succeeded'
    assert restarted.snapshot(OWNER_A)[1] == {}


def test_omission_retains_key_removal_and_provider_switch_clear_it(tmp_path, no_external):
    settings = RuntimeSettings(tmp_path)
    settings.put(OWNER_A, SettingsPut.model_validate(payload(settings, provider='openai', ai_key=KEY_A, include_key=True)))
    settings.put(OWNER_A, SettingsPut.model_validate(payload(settings, provider='openai')))
    assert settings.get(OWNER_A)['credentials']['ai_api_key'] is True
    settings.put(OWNER_A, SettingsPut.model_validate(payload(settings, provider='openai', include_key=True)))
    assert settings.get(OWNER_A)['credentials']['ai_api_key'] is False
    settings.put(OWNER_A, SettingsPut.model_validate(payload(settings, provider='openai', ai_key=KEY_A, include_key=True)))
    settings.put(OWNER_A, SettingsPut.model_validate(payload(settings, provider='deepseek')))
    assert settings.get(OWNER_A)['credentials']['ai_api_key'] is False


def test_two_tab_cas_and_snapshot_does_not_mutate_inflight_copy(tmp_path, no_external):
    settings = RuntimeSettings(tmp_path)
    request = SettingsPut.model_validate(payload(settings, provider='openai', ai_key=KEY_A, include_key=True))
    settings.put(OWNER_A, request)
    snap, keys = settings.snapshot(OWNER_A)
    duplicate = settings.get(OWNER_A)
    with pytest.raises(MvpError, match='another tab'):
        settings.put(OWNER_A, request)
    assert settings.get(OWNER_A) == duplicate
    settings.put(OWNER_A, SettingsPut.model_validate(payload(settings, provider='none')))
    assert snap['preferences']['ai']['provider'] == 'openai' and keys['ai_api_key'] == KEY_A
    assert settings.snapshot(OWNER_A)[1].get('ai_api_key') is None
    with pytest.raises(MvpError):
        settings.assert_current(OWNER_A, snap['revision'])


def test_consent_is_exact_session_revision_payload_and_single_attempt(tmp_path, no_external):
    settings = RuntimeSettings(tmp_path)
    result = settings.put(OWNER_A, SettingsPut.model_validate(payload(settings, provider='openai', ai_key=KEY_A, include_key=True)))
    binding = {'request_id': 'synthetic-op', 'workspace': 'synthetic-workspace', 'question_hash': 'c' * 64}
    disclosure = {'provider': 'openai', 'model': 'fixture-model', 'input_bytes': 99, 'cost_status': 'unknown'}
    consent = settings.prepare(OWNER_A, result['revision'], binding, disclosure)
    assert no_external == []
    assert KEY_A not in str(consent)
    for owner, bound in [(OWNER_B, binding), (OWNER_A, {**binding, 'request_id': 'different'})]:
        with pytest.raises(MvpError):
            settings.consume(owner, result['revision'], consent['consent_id'], bound)
    settings.consume(OWNER_A, result['revision'], consent['consent_id'], binding)
    with pytest.raises(MvpError):
        settings.consume(OWNER_A, result['revision'], consent['consent_id'], binding)


def test_consent_expiry_and_changed_settings_are_fail_closed(tmp_path, no_external):
    time = [datetime(2026, 10, 25, tzinfo=timezone.utc)]
    settings = RuntimeSettings(tmp_path, clock=lambda: time[0])
    result = settings.put(OWNER_A, SettingsPut.model_validate(payload(settings)))
    consent = settings.prepare(OWNER_A, result['revision'], {'id': 'expires'}, {})
    time[0] += timedelta(minutes=6)
    with pytest.raises(MvpError):
        settings.consume(OWNER_A, result['revision'], consent['consent_id'], {'id': 'expires'})
    consent = settings.prepare(OWNER_A, result['revision'], {'id': 'stale'}, {})
    settings.put(OWNER_A, SettingsPut.model_validate(payload(settings)))
    with pytest.raises(MvpError):
        settings.consume(OWNER_A, result['revision'], consent['consent_id'], {'id': 'stale'})


def test_global_generation_slot_rejects_overlapping_session_work(tmp_path, no_external):
    settings = RuntimeSettings(tmp_path)
    with settings.generation_slot():
        with pytest.raises(MvpError):
            with settings.generation_slot():
                pytest.fail('A second concurrent operation acquired the shared slot')
    with settings.generation_slot():
        pass


@pytest.mark.parametrize('owner', ['../other', '', 'A' * 64, 'a' * 63, 'a' * 65])
def test_owner_paths_never_accept_caller_paths(tmp_path, owner, no_external):
    settings = RuntimeSettings(tmp_path)
    with pytest.raises(MvpError):
        settings.get(owner)


def test_settings_symlinks_and_unsafe_modes_rejected(tmp_path, no_external):
    outside = tmp_path / 'outside'
    outside.mkdir()
    linked = tmp_path / 'linked'
    linked.mkdir()
    (linked / 'session-settings').symlink_to(outside)
    with pytest.raises(MvpError):
        RuntimeSettings(linked)
    (tmp_path / 'owned').mkdir()
    settings = RuntimeSettings(tmp_path / 'owned')
    settings.put(OWNER_A, SettingsPut.model_validate(payload(settings)))
    path = settings.directory / (OWNER_A + '.json')
    path.chmod(0o644)
    with pytest.raises(MvpError):
        settings.get(OWNER_A)


def browser(app):
    client = TestClient(app, base_url='http://127.0.0.1:8765')
    csrf = client.get('/api/v1/session').json()['csrf_token']
    client.headers.update({'Origin':'http://127.0.0.1:3000', 'X-CSRF-Token':csrf})
    return client


def http_payload(client, *, provider='none', key=None):
    value = client.get('/api/v1/settings').json()
    preferences = deepcopy(value['preferences'])
    preferences['pubmed'] = {'enabled':True,'email':'synthetic@example.invalid'}
    preferences['ai'].update(provider=provider, model=MODEL if provider != 'none' else '',
        model_revision='synthetic-profile.v1' if provider != 'none' else '', planning_enabled=provider != 'none')
    return {'expected_revision':value['revision'], 'preferences':preferences,
        **({'ai_api_key':key} if key is not None else {})}


MODEL = 'synthetic-exact-model'


def test_http_settings_require_session_origin_and_csrf_and_never_echo_keys(tmp_path, monkeypatch, no_external):
    for name in ('MVP_PROPOSALS_ENABLED','MVP_SEARCH_PLANNER_ENABLED','MVP_MAP_ENABLED'):
        monkeypatch.setenv(name, '0')
    monkeypatch.delenv('NCBI_EMAIL', raising=False)
    app = create_app(tmp_path)
    client = browser(app)
    request = http_payload(client, provider='openai', key=KEY_A)
    unauthenticated = TestClient(app, base_url='http://127.0.0.1:8765')
    assert unauthenticated.get('/api/v1/settings').status_code == 404
    assert client.put('/api/v1/settings',json=request,headers={'Origin':'https://untrusted.invalid'}).status_code == 403
    assert client.put('/api/v1/settings',json=request,headers={'X-CSRF-Token':'wrong'}).status_code == 403
    result = client.put('/api/v1/settings',json=request)
    assert result.status_code == 200, result.text
    assert KEY_A not in result.text
    assert result.headers['cache-control'] == 'no-store'
    assert result.json()['credentials']['ai_api_key'] is True
    second = browser(app)
    assert second.get('/api/v1/settings').json()['credentials']['ai_api_key'] is False
    malformed = {**request,'expected_revision':1,'ai_api_key':KEY_A + 'x' * 600}
    error = client.put('/api/v1/settings',json=malformed)
    assert error.status_code == 422 and KEY_A not in error.text
    assert no_external == []


def test_http_settings_conflicts_restart_and_secret_free_research_export(tmp_path, monkeypatch, no_external):
    for name in ('MVP_PROPOSALS_ENABLED','MVP_SEARCH_PLANNER_ENABLED','MVP_MAP_ENABLED'):
        monkeypatch.setenv(name, '0')
    monkeypatch.delenv('NCBI_EMAIL', raising=False)
    app = create_app(tmp_path)
    client = browser(app)
    request = http_payload(client, provider='deepseek', key=KEY_A)
    first = client.put('/api/v1/settings',json=request)
    assert first.status_code == 200, first.text
    assert client.put('/api/v1/settings',json=request).status_code == 409
    workspace = client.post('/api/v1/workspaces',json={'request_id':'private-settings-independence','mode':'saved_example'}).json()
    exported = client.get('/api/v1/workspaces/' + workspace['id'] + '/exports?format=json')
    assert exported.status_code == 200
    assert KEY_A not in exported.text and 'session-settings' not in exported.text
    reopened = TestClient(create_app(tmp_path), base_url='http://127.0.0.1:8765')
    reopened.cookies.update(client.cookies)
    value = reopened.get('/api/v1/settings')
    assert value.status_code == 200 and value.json()['revision'] == 1
    assert value.json()['credentials']['ai_api_key'] is False
    for path in tmp_path.rglob('*'):
        if path.is_file(): assert KEY_A.encode() not in path.read_bytes()
    assert no_external == []


def test_explicit_pubmed_connection_test_uses_contact_without_optional_key(tmp_path, monkeypatch, no_external):
    monkeypatch.setenv('MVP_PROPOSALS_ENABLED','0')
    monkeypatch.setenv('MVP_SEARCH_PLANNER_ENABLED','0')
    monkeypatch.delenv('NCBI_EMAIL', raising=False)
    calls = []
    class Diagnostic:
        def __init__(self, **kwargs): calls.append(('configuration',kwargs))
        def check(self, query):
            calls.append(('query',query))
            from types import SimpleNamespace
            return SimpleNamespace(status='succeeded')
    monkeypatch.setattr('src.mvp.adapters.search_diagnostics.PubMedSearchDiagnostics',Diagnostic)
    app, client = create_app(tmp_path), None
    client = browser(app)
    value = client.put('/api/v1/settings',json=http_payload(client))
    assert value.status_code == 200, value.text
    assert calls == []
    result = client.post('/api/v1/settings/test-pubmed',json={'expected_revision':value.json()['revision']})
    assert result.status_code == 200, result.text
    assert result.json()['status']['pubmed']['state'] == 'Last test succeeded'
    assert calls == [('configuration',{'email':'synthetic@example.invalid','api_key':None}),('query','1[uid]')]
    assert no_external == []


def test_optional_runtime_metadata_preserves_historical_capture_and_receipt_bytes():
    # These complete old-schema dictionaries intentionally omit new optional
    # metadata. Historical snapshot hashes must survive loading and exporting.
    from src.mvp.contracts import SearchPreview, canonical, digest
    from src.mvp.search_plan_contracts import SearchPlanExecution
    preview = {'schema_version':'mvp.exploratory-preview.v1','id':'old-preview','query':'old exact query',
        'research_question':None,'query_translation':None,'searched_at':'2026-01-01T00:00:00+00:00',
        'sort':'relevance','date_from':None,'date_to':None,'total_reported':1,'fetched_count':1,
        'ordered_identifiers':['123'],'papers':[],'warnings':[],'truncated':False,
        'provider':'pubmed','mode':'live','errors':[]}
    reloaded = SearchPreview.model_validate(preview)
    assert canonical(reloaded.model_dump(mode='json')) == canonical(preview)
    assert digest(reloaded.model_dump(mode='json')) == digest(preview)
    receipt = {'schema_version':'mvp.planned-search-execution.v2','id':'old-execution','plan_id':'old-plan','revision_id':'old-revision','candidate_id':'old-candidate',
        'candidate_sha256':'a' * 64,'approval_id':'old-approval','search_id':'old-preview',
        'search_snapshot_sha256':digest(preview),'created_at':'2026-01-01T00:00:00+00:00'}
    reopened = SearchPlanExecution.model_validate(receipt)
    assert canonical(reopened.model_dump(mode='json')) == canonical(receipt)
    updated = reloaded.model_copy(update={'requested_max_results':30,
        'configuration_profile':{'provider':'pubmed','settings_revision':2}}).model_dump(mode='json')
    assert updated['requested_max_results'] == 30
    assert updated['configuration_profile']['settings_revision'] == 2
