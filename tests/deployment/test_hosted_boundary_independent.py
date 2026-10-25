"""Independent hosted-boundary acceptance over new, disposable state only.

Configuration/network gates are software checks, not provider/model evidence or
an assessment of the scientific utility of the literature review workflow.
"""
import hashlib
from pathlib import Path
import socket

import pytest

from src.web_api.deployment import DeploymentConfig


def configured(directory):
    return {
        'MVP_DEPLOYMENT_MODE': 'hosted', 'MVP_HOSTED_INGRESS': 'render',
        'MVP_PUBLIC_ORIGIN': 'https://litrev.example.test',
        'MVP_API_HOST': '127.0.0.1:8765',
        'MVP_API_ORIGIN': 'http://127.0.0.1:8765',
        'MVP_PERSISTENT_ROOT': str(directory),
        'MVP_WEB_DATA_DIR': str(directory / 'litrev'),
        'MVP_HOSTED_INVITE_SHA256': hashlib.sha256(b'INDEPENDENT SOFTWARE TEST INVITE').hexdigest(),
        'MVP_PROPOSALS_ENABLED': '0', 'MVP_SEARCH_PLANNER_ENABLED': '0', 'MVP_MAP_ENABLED': '0',
    }


@pytest.mark.parametrize('value', [
    '', 'http://litrev.example.test', 'https://*.example.test',
    'https://litrev.example.test/', 'https://litrev.example.test/path',
    'https://litrev.example.test?workspace=secret', 'https://litrev.example.test#x',
    'https://user:password@litrev.example.test', 'https://litrev.example.test:443',
    'https://localhost', 'https://127.0.0.1', 'https://EXAMPLE.TEST',
    'https://litrev.example.test:0', 'https://litrev.example.test:65536',
])
def test_exact_public_https_origin_is_mandatory(tmp_path, value):
    values = configured(tmp_path); values['MVP_PUBLIC_ORIGIN'] = value
    with pytest.raises(ValueError):
        DeploymentConfig.from_environment(values)
    assert not (tmp_path / 'litrev').exists(), 'Invalid config must fail before private state creation'


@pytest.mark.parametrize('setting', [
    'MVP_PUBLIC_ORIGIN', 'MVP_HOSTED_INGRESS', 'MVP_API_HOST', 'MVP_API_ORIGIN',
    'MVP_PERSISTENT_ROOT', 'MVP_WEB_DATA_DIR', 'MVP_HOSTED_INVITE_SHA256',
])
def test_hosted_settings_fail_closed_individually(tmp_path, setting):
    values = configured(tmp_path); values.pop(setting)
    with pytest.raises(ValueError):
        DeploymentConfig.from_environment(values)
    assert not (tmp_path / 'litrev').exists()


@pytest.mark.parametrize('setting', ['MVP_PROPOSALS_ENABLED', 'MVP_SEARCH_PLANNER_ENABLED', 'MVP_MAP_ENABLED'])
def test_hosted_mode_does_not_silently_enable_model_execution(tmp_path, setting):
    values = configured(tmp_path); values[setting] = '1'
    with pytest.raises(ValueError):
        DeploymentConfig.from_environment(values)


def test_hosted_upstream_remains_literal_internal_loopback(tmp_path):
    values = configured(tmp_path)
    for host, origin in [('0.0.0.0:8765', 'http://0.0.0.0:8765'),
                         ('127.0.0.1:8766', 'http://127.0.0.1:8766'),
                         ('api.example.test', 'https://api.example.test')]:
        with pytest.raises(ValueError):
            DeploymentConfig.from_environment({**values, 'MVP_API_HOST': host, 'MVP_API_ORIGIN': origin})
    assert DeploymentConfig.from_environment(values).api_origin == 'http://127.0.0.1:8765'


def test_hosted_storage_needs_real_mount_and_private_descendant(tmp_path):
    values = configured(tmp_path)
    for target in [str(tmp_path), str(tmp_path.parent / 'elsewhere'), 'relative/path', str(tmp_path / 'a' / '..' / 'litrev')]:
        with pytest.raises(ValueError):
            DeploymentConfig.from_environment({**values, 'MVP_WEB_DATA_DIR': target})
    # A writable ordinary directory is deliberately insufficient in hosted mode.
    with pytest.raises(ValueError):
        DeploymentConfig.from_environment(values).validate_storage()
    assert not (tmp_path / 'litrev').exists()


def test_local_default_stays_exact_loopback_and_does_not_require_admission(tmp_path):
    config = DeploymentConfig.from_environment({'MVP_WEB_DATA_DIR': str(tmp_path / 'local')})
    assert not config.hosted
    assert config.public_origin == 'http://127.0.0.1:3000'
    assert config.invite_sha256 is None
    for origin in ['https://litrev.example.test', 'http://127.0.0.1:3000/path']:
        with pytest.raises(ValueError):
            DeploymentConfig.from_environment({'MVP_WEB_ORIGIN': origin})

from fastapi.testclient import TestClient
from src.web_api.app import create_app
from src.web_api.hosted_admission import (
    ADMISSION_COOKIE, ADMISSION_SECONDS, HOSTED_SESSION_COOKIE,
)

BASE = 'https://127.0.0.1:8765'
PUBLIC = 'https://litrev.example.test'
P = '/api/v1'
INVITE = 'INDEPENDENT SOFTWARE TEST INVITE 0123456789'


@pytest.fixture
def hosted_case(tmp_path, monkeypatch):
    for name in tuple(__import__('os').environ):
        if name.startswith(('NCBI_', 'MVP_PROPOSALS_', 'MVP_SEARCH_PLANNER_', 'MVP_MAP_')):
            monkeypatch.delenv(name, raising=False)
    for name in ('MVP_PROPOSALS_ENABLED', 'MVP_SEARCH_PLANNER_ENABLED', 'MVP_MAP_ENABLED'):
        monkeypatch.setenv(name, '0')
    def denied(*args, **kwargs):
        pytest.fail('Independent hosted HTTP checks attempted network/provider access')
    monkeypatch.setattr(socket, 'create_connection', denied)
    monkeypatch.setattr(socket.socket, 'connect', denied)
    # Unit/in-process HTTP tests deliberately simulate only the mount predicate;
    # the separate real-container smoke must exercise an actual mounted volume.
    monkeypatch.setattr('src.web_api.deployment.os.path.ismount', lambda p: Path(p) == tmp_path)
    values = configured(tmp_path)
    values['MVP_HOSTED_INVITE_SHA256'] = hashlib.sha256(INVITE.encode()).hexdigest()
    config = DeploymentConfig.from_environment(values)
    app = create_app(deployment=config)
    client = TestClient(app, base_url=BASE)
    client.headers.update({'Origin': PUBLIC})
    yield app, client, config
    client.close()


def admit(client, code=INVITE):
    reply = client.post(P + '/admission/login', json={'code': code})
    assert reply.status_code == 200, reply.text
    csrf = client.get(P + '/session')
    assert csrf.status_code == 200, csrf.text
    client.headers['X-CSRF-Token'] = csrf.json()['csrf_token']
    return reply


def create_public_case(app, first):
    admit(first)
    created = first.post(P + '/workspaces', json={'request_id': 'independent-hosted', 'mode': 'saved_example',
        'question': 'SOFTWARE TEST - no human or scientific assessment'})
    assert created.status_code == 200, created.text
    root = P + '/workspaces/' + created.json()['id']
    preview = first.post(root + '/searches', json={'request_id': 'public-search', 'query': 'public retained sources', 'max_results': 30})
    assert preview.status_code == 200, preview.text
    search = preview.json()
    ids = [item['id'] for item in search['papers'][:3]]
    prep_reply = first.post(root + '/source-preparations', json={'request_id': 'public-prepare', 'search_id': search['id'], 'paper_ids': ids})
    assert prep_reply.status_code == 200, prep_reply.text
    prep = prep_reply.json()
    board_reply = first.post(root + '/boards', json={'request_id': 'public-board', 'preparation_id': prep['id'],
        'paper_ids': ids, 'fields': [{'id': 'field', 'label': 'Field', 'subquestion': 'microbiome diet'}],
        'question': 'SOFTWARE TEST'})
    assert board_reply.status_code == 200, board_reply.text
    view = board_reply.json()
    return root, search, prep, view


def test_hosted_admission_covers_session_capabilities_and_unknown_research_routes(hosted_case):
    app, client, _ = hosted_case
    status = client.get(P + '/admission/status')
    assert status.json() == {'mode': 'hosted', 'admitted': False}
    for route in (P + '/session', P + '/capabilities', P + '/workspaces',
                  P + '/workspaces/guessed/exports?format=json', P + '/unknown-resource'):
        response = client.get(route)
        assert response.status_code == 401, route
        assert 'no-store' in response.headers['Cache-Control']
    assert client.post(P + '/workspaces', json={'request_id': 'blocked'}).status_code == 401
    with app.state.registry.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM web_sessions').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM web_workspaces').fetchone()[0] == 0


def test_hosted_invite_and_session_cookies_are_separate_private_host_only(hosted_case):
    app, client, _ = hosted_case
    login = admit(client)
    for response, name in [(login, ADMISSION_COOKIE), (client.get(P + '/session'), HOSTED_SESSION_COOKIE)]:
        header = response.headers['set-cookie']
        assert name + '=' in header
        assert 'Secure' in header and 'HttpOnly' in header and 'SameSite=strict' in header
        assert 'Path=/' in header and 'Domain=' not in header
    assert client.cookies.get(ADMISSION_COOKIE) != client.cookies.get(HOSTED_SESSION_COOKIE)
    with app.state.admission.connection() as db:
        rows = [dict(row) for row in db.execute('SELECT * FROM admission_grants')]
    serialized = __import__('json').dumps(rows)
    assert INVITE not in serialized and client.cookies.get(ADMISSION_COOKIE) not in serialized
    assert app.state.admission.path.stat().st_mode & 0o777 == 0o600
    assert app.state.registry.path.stat().st_mode & 0o777 == 0o600


def test_login_origin_host_and_forwarded_headers_cannot_replace_policy(hosted_case):
    _, client, _ = hosted_case
    body = {'code': INVITE}
    for headers in ({'Origin': 'https://attacker.example'}, {'Origin': ''},
                    {'Host': 'attacker.example', 'X-Forwarded-Host': '127.0.0.1:8765', 'X-Forwarded-Proto': 'https'},
                    {'Origin': 'http://litrev.example.test', 'X-Forwarded-Proto': 'https'}):
        result = client.post(P + '/admission/login', json=body, headers=headers)
        assert result.status_code == 403
        assert INVITE not in result.text
    assert client.get(P + '/admission/status').json()['admitted'] is False


def test_shared_admission_does_not_grant_other_browser_workspace_or_exports(hosted_case):
    app, first, _ = hosted_case
    root, search, prep, view = create_public_case(app, first)
    second = TestClient(app, base_url=BASE); second.headers['Origin'] = PUBLIC
    admit(second)
    assert second.cookies.get(HOSTED_SESSION_COOKIE) != first.cookies.get(HOSTED_SESSION_COOKIE)
    board = root + '/boards/' + view['definition']['board_id']
    paper = view['definition']['paper_ids'][0]
    map_id = first.get(root + '/maps', params={'search_id': search['id']}).json()['maps'][0]['map_id']
    paths = [root, root + '/searches/' + search['id'] + '/papers', root + '/source-preparations/' + prep['id'],
             root + '/drafts/discover', root + '/exports?format=json', root + '/exports?format=csv',
             root + '/maps/' + map_id, board, board + '/exports?format=json&history=true',
             board + '/exports?format=csv', board + '/drafts/' + paper + '/field',
             board + '/sources/' + view['definition']['sources'][0]['source_id'] + '/blocks']
    for path in paths:
        response = second.get(path)
        assert response.status_code == 404, (path, response.text)
        assert 'no-store' in response.headers['Cache-Control']
        assert 'retained_content_utf8' not in response.text
    assert second.put(root + '/drafts/discover', json={'version': 0, 'data': {'query': 'foreign'}}).status_code == 404
    assert second.delete(root).status_code == 404
    assert second.get(P + '/workspaces').json() == {'workspaces': []}
    assert first.get(root).status_code == 200
    assert first.put(root + '/drafts/discover', json={'version': 0, 'data': {}}, headers={'X-CSRF-Token': 'wrong'}).status_code == 403
    second.close()


def test_admission_expiry_logout_and_rotation_revoke_grant_without_sharing_research(hosted_case):
    app, first, config = hosted_case
    admit(first)
    cookie = first.cookies.get(ADMISSION_COOKIE)
    now = app.state.admission.clock()
    app.state.admission.clock = lambda: now + ADMISSION_SECONDS + 1
    assert first.get(P + '/capabilities').status_code == 401
    assert first.get(P + '/admission/status').json()['admitted'] is False
    app.state.admission.clock = lambda: now
    assert first.get(P + '/capabilities').status_code == 200
    assert first.post(P + '/admission/logout', json={}).status_code == 200
    assert app.state.admission.resolve(cookie) is None
    assert first.get(P + '/capabilities').status_code == 401
    admit(first)
    app.state.admission.invite_sha256 = hashlib.sha256(b'rotated independent invite').hexdigest()
    assert first.get(P + '/capabilities').status_code == 401


def test_hosted_login_attempts_are_bounded_globally_without_forwarded_ip_identity(hosted_case, monkeypatch):
    import src.web_api.hosted_admission as admission
    app, client, _ = hosted_case
    monkeypatch.setattr(admission, 'MAX_LOGIN_ATTEMPTS', 3)
    for index in range(3):
        response = client.post(P + '/admission/login', json={'code': 'WRONG SOFTWARE TEST CODE 0123456789'},
            headers={'X-Forwarded-For': '192.0.2.' + str(index)})
        assert response.status_code == 401
    assert client.post(P + '/admission/login', json={'code': INVITE}).status_code == 429
    with app.state.admission.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM admission_grants').fetchone()[0] == 0


def test_hosted_usage_budgets_persist_and_manual_cells_are_not_model_jobs(hosted_case, monkeypatch):
    import src.web_api.hosted_admission as admission
    app, client, config = hosted_case
    admit(client)
    with app.state.admission.connection() as db:
        db.execute('UPDATE admission_grants SET requests=0,jobs=0')
    monkeypatch.setattr(admission, 'MAX_REQUESTS', 2)
    assert client.get(P + '/capabilities').status_code == 200
    assert client.get(P + '/workspaces').status_code == 200
    restarted = TestClient(create_app(deployment=config), base_url=BASE)
    restarted.cookies.update(client.cookies); restarted.headers.update(client.headers)
    assert restarted.get(P + '/workspaces').status_code == 429
    restarted.close()
    assert admission.expensive_request('POST', P + '/workspaces/x/preparation-jobs')
    assert admission.expensive_request('POST', P + '/workspaces/x/boards/y/candidates')
    assert not admission.expensive_request('PUT', P + '/workspaces/x/boards/y/drafts/paper/field')
    assert not admission.expensive_request('POST', P + '/workspaces/x/boards/y/cell-revisions')


def test_hosted_preparation_lease_recovery_and_deleted_workspace_fence(hosted_case):
    """Simulated abandoned lease; actual retained-source stage, no process-kill claim."""
    from src.mvp.ports import MvpError
    app, client, config = hosted_case
    root, search, preparation, _ = create_public_case(app, client)
    ids = preparation['selected_paper_ids']; workspace_id = root.rsplit('/', 1)[1]
    submitted = client.post(root + '/preparation-jobs', json={'request_id': 'lease-recovery',
        'search_id': search['id'], 'paper_ids': ids, 'expected_source_revision': 1,
        'expected_preparation_id': preparation['id']})
    assert submitted.status_code == 202, submitted.text
    job_id = submitted.json()['job']['id']
    store = app.state.preparation_jobs.store_for('saved_example')
    old_lease = store.claim('INDEPENDENT-ABANDONED-TEST-OWNER')
    captured = store.input(old_lease)
    mode, handle = app.state.registry.get_bound_handle_for_worker(workspace_id)
    engine = app.state.preparation_jobs.service_for(mode)
    source = app.state.preparation_jobs.prepare(engine, captured.papers[0], captured)
    store.stage(old_lease, source)
    saved = client.put(root + '/drafts/discover', json={'version': 0,
        'data': {'query': 'durable draft while source preparation is interrupted'}})
    assert saved.status_code == 200
    recovered_app = create_app(deployment=config)
    recovered = TestClient(recovered_app, base_url=BASE)
    recovered.cookies.update(client.cookies); recovered.headers.update(client.headers)
    worker = recovered_app.state.preparation_worker
    assert worker._acquire(), 'A fresh worker must own the private store before lease recovery'
    try:
        assert worker.run_once()
        result = recovered.get(root + '/preparation-jobs/' + job_id)
        assert result.status_code == 200, result.text
        assert result.json()['status'] == 'succeeded'
        assert result.json()['attempt'] == 2 and result.json()['interrupted_count'] == 1
        assert result.json()['progress_completed'] == 3
        assert recovered.get(root + '/drafts/discover').json() == saved.json()
        with pytest.raises(MvpError):
            store.stage(old_lease, source)
        current = recovered.get(root).json()
        queued = recovered.post(root + '/preparation-jobs', json={'request_id': 'delete-fence',
            'search_id': search['id'], 'paper_ids': ids, 'expected_source_revision': current['source_revision'],
            'expected_preparation_id': current['current_preparation_id']})
        assert queued.status_code == 202, queued.text
        claimed = store.claim('INDEPENDENT-DELETED-TEST-OWNER')
        assert claimed is not None
        assert recovered.delete(root).status_code == 200
        worker._process(store, claimed)
        assert recovered.get(root).status_code == 404
        assert recovered.get(root + '/preparation-jobs/' + queued.json()['job']['id']).status_code == 404
        assert recovered.get(P + '/workspaces').json() == {'workspaces': []}
        assert worker.run_once() is False
    finally:
        worker._release(); recovered.close()
