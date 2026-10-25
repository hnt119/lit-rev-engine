"""Independent full HTTP consent/race checks using synthetic cloud responses."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import socket
from threading import Event

import pytest
from fastapi.testclient import TestClient

from src.mvp.contracts import canonical
from src.mvp.ports import MvpError
from src.mvp.search_plan_contracts import SearchPlanDraft
from src.web_api.app import create_app

KEY = 'SYNTHETIC-http-consent-key-no-account'
MODEL = 'synthetic-explicit-model'
QUESTION = 'Synthetic women microbiome research question?'


def browser(app):
    client = TestClient(app, base_url='http://127.0.0.1:8765')
    csrf = client.get('/api/v1/session').json()['csrf_token']
    client.headers.update({'Origin':'http://127.0.0.1:3000','X-CSRF-Token':csrf})
    return client


def save_settings(client, provider='openai', key=KEY):
    value = client.get('/api/v1/settings').json()
    preferences = deepcopy(value['preferences'])
    preferences['ai'].update(provider=provider,model=MODEL,model_revision='synthetic-profile.v1',planning_enabled=True)
    body = {'expected_revision':value['revision'],'preferences':preferences}
    if key is not None: body['ai_api_key'] = key
    result = client.put('/api/v1/settings',json=body)
    assert result.status_code == 200, result.text
    return result.json()


@pytest.fixture
def flow(tmp_path, monkeypatch):
    for name in ('MVP_PROPOSALS_ENABLED','MVP_SEARCH_PLANNER_ENABLED','MVP_MAP_ENABLED'):
        monkeypatch.setenv(name,'0')
    monkeypatch.delenv('NCBI_EMAIL',raising=False)
    monkeypatch.setattr(socket,'create_connection',lambda *a,**kw: pytest.fail('External networking is forbidden'))
    app = create_app(tmp_path)
    client = browser(app)
    saved = save_settings(client)
    workspace = client.post('/api/v1/workspaces',json={'request_id':'consent-w','mode':'live'}).json()
    root = '/api/v1/workspaces/' + workspace['id']
    plan = client.post(root + '/search-plans',json={'request_id':'consent-plan','draft':{
        'original_question':QUESTION}})
    assert plan.status_code == 200, plan.text
    plan = plan.json()['revision']
    path = root + '/search-plans/' + plan['plan_id']
    request = {'request_id':'consent-generation','original_question':QUESTION,
        'expected_revision_id':plan['revision_id'],'settings_revision':saved['revision']}
    calls, entered, release = [], Event(), Event()
    state = {'failure':False,'block':False}
    def mocked(self, body, timeout_seconds):
        value = json.loads(body)
        calls.append({'provider':self.provider,'body':value,'key':self._key,'timeout':timeout_seconds})
        entered.set()
        if state['block']: assert release.wait(timeout=8)
        if state['failure']: raise MvpError('proposal_provider_failure','Synthetic failure; no fallback')
        return canonical({'model':MODEL,'choices':[{'finish_reason':'stop','message':{'role':'assistant',
            'content':canonical(SearchPlanDraft(original_question=QUESTION).model_dump(mode='json'))}}],
            'usage':{'prompt_tokens':100,'completion_tokens':50,'total_tokens':150}}).encode()
    monkeypatch.setattr('src.mvp.adapters.cloud_generation.CloudJSONTransport.request',mocked)
    from types import SimpleNamespace
    return SimpleNamespace(app=app,client=client,root=root,path=path,request=request,calls=calls,
        entered=entered,release=release,state=state,tmp=tmp_path)


def prepare(flow, request=None):
    result = flow.client.post(flow.path + '/prepare-generation',json=request or flow.request)
    assert result.status_code == 200, result.text
    return result.json()


def test_no_call_without_one_run_consent_prepare_has_no_call_and_replay_cannot_bill(flow):
    denied = flow.client.post(flow.path + '/propose',json=flow.request)
    assert denied.status_code == 422 and flow.calls == []
    consent = prepare(flow)
    assert consent['provider'] == 'openai' and consent['model'] == MODEL
    assert consent['max_calls'] == 1 and consent['input_bytes'] > 0
    assert consent['data_types'] == ['research question'] and 'charged' in consent['cost_estimate']
    assert KEY not in canonical(consent) and QUESTION not in canonical(consent)
    assert flow.calls == []
    request = {**flow.request,'consent_id':consent['consent_id']}
    result = flow.client.post(flow.path + '/propose',json=request)
    assert result.status_code == 200, result.text
    assert len(flow.calls) == 1
    replay = flow.client.post(flow.path + '/propose',json=request)
    assert replay.status_code in {200,422,409} and len(flow.calls) == 1
    exported = flow.client.get(flow.root + '/exports?format=json')
    assert exported.status_code == 200 and KEY not in exported.text
    assert result.json()['result']['usage']['total_tokens'] == 150


def test_modified_input_and_other_session_cannot_reuse_consent(flow):
    consent = prepare(flow)
    changed = {**flow.request,'consent_id':consent['consent_id'],'original_question':QUESTION + ' altered'}
    assert flow.client.post(flow.path + '/propose',json=changed).status_code in {409,422}
    changed = {**flow.request,'consent_id':consent['consent_id'],'request_id':'another-request'}
    assert flow.client.post(flow.path + '/propose',json=changed).status_code == 422
    second = browser(flow.app)
    save_settings(second,provider='deepseek',key='SYNTHETIC-second-owner-key')
    assert second.post(flow.path + '/propose',json={**flow.request,'consent_id':consent['consent_id']}).status_code == 404
    assert flow.calls == []


def test_failure_consumes_authorization_and_never_falls_back(flow):
    consent = prepare(flow)
    flow.state['failure'] = True
    request = {**flow.request,'consent_id':consent['consent_id']}
    first = flow.client.post(flow.path + '/propose',json=request)
    assert first.status_code != 200
    second = flow.client.post(flow.path + '/propose',json=request)
    assert second.status_code != 200
    assert len(flow.calls) == 1 and flow.calls[0]['provider'] == 'openai'
    assert KEY not in first.text and KEY not in second.text


def test_changing_settings_while_waiting_does_not_block_save_and_rejects_publication(flow):
    consent = prepare(flow)
    flow.state['block'] = True
    request = {**flow.request,'consent_id':consent['consent_id']}
    with ThreadPoolExecutor(max_workers=2) as executor:
        future = executor.submit(flow.client.post,flow.path + '/propose',json=request)
        assert flow.entered.wait(timeout=4)
        saved = save_settings(flow.client,provider='deepseek',key='SYNTHETIC-new-provider-key')
        assert saved['revision'] == 2
        flow.release.set()
        result = future.result(timeout=6)
    assert result.status_code in {409,422}, result.text
    assert len(flow.calls) == 1 and flow.calls[0]['provider'] == 'openai'
    view = flow.client.get(flow.path).json()
    assert view['proposals'] == []


def test_workspace_deletion_during_generation_cannot_publish_or_recreate(flow):
    consent = prepare(flow)
    flow.state['block'] = True
    request = {**flow.request,'consent_id':consent['consent_id']}
    with ThreadPoolExecutor(max_workers=2) as executor:
        future = executor.submit(flow.client.post,flow.path + '/propose',json=request)
        assert flow.entered.wait(timeout=4)
        removed = flow.client.delete(flow.root)
        flow.release.set()
        assert removed.status_code == 200 and removed.json() == {'cleared':True}, removed.text
        result = future.result(timeout=6)
    assert result.status_code != 200
    assert flow.client.get(flow.root).status_code == 404
    assert len(flow.calls) == 1
