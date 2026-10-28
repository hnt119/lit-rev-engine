"""Independent adversarial offline HTTP evaluation over synthetic fixtures."""
import json
import socket
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.adapters.search_diagnostics import PubMedSearchDiagnostics
from src.mvp.contracts import Paper, SearchPreview, PreparedSource, Block
from src.mvp.service import MVPService
from src.web_api.app import create_app

class Provider:
    def __init__(self):
        self.calls = 0
        self.entered, self.release = threading.Event(), threading.Event()
        self.block = False
        self.error = None
        self.duplicate = False
    def search(self, request):
        self.calls += 1
        if self.block:
            self.entered.set()
            assert self.release.wait(8)
        if self.error:
            raise self.error
        papers = [Paper(id='paper-one', pmid='99001', title='Synthetic original', abstract='Women diet sample.')]
        if self.duplicate:
            papers += [Paper(id='paper-one', pmid='99002', title='Different synthetic report')]
        return SearchPreview(query=request.query, date_from=request.date_from, date_to=request.date_to, sort=request.sort,
            papers=papers, total_reported=len(papers), fetched_count=len(papers), truncated=False,
            provider='synthetic-offline', mode='test')
    def prepare(self, paper):
        return PreparedSource(paper_id=paper.id, status='abstract_only', source_type='abstract', provider='synthetic', source_url='',
            blocks=[Block(id='abstract', ordinal=1, text=paper.abstract, locator={'type':'abstract'})])

class Diagnostic:
    def __init__(self): self.calls = 0
    def request(self, endpoint, params):
        self.calls += 1
        return b'<eSearchResult><Count>0</Count><RetMax>0</RetMax><RetStart>0</RetStart><IdList/><QueryTranslation>synthetic</QueryTranslation></eSearchResult>'

def browser(app):
    c=TestClient(app,base_url='http://127.0.0.1:8765')
    c.headers.update({'Origin':'http://127.0.0.1:3000','X-CSRF-Token':c.get('/api/v1/session').json()['csrf_token']})
    return c

def ok(response):
    assert response.status_code == 200, response.text
    return response.json()

@pytest.fixture
def case(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, 'create_connection', lambda *a,**k:pytest.fail('Forbidden external network'))
    for key in ['MVP_MAP_ENABLED','MVP_PROPOSALS_ENABLED','MVP_SEARCH_PLANNER_ENABLED']:
        monkeypatch.setenv(key,'0')
    provider, transport = Provider(), Diagnostic()
    engine=MVPService(SQLiteWorkspaceStorage(tmp_path/'research.sqlite3'),provider,provider)
    diagnostics=PubMedSearchDiagnostics(email='fixture@example.org',transport=transport)
    app=create_app(tmp_path,services={'live':engine,'saved_example':engine},search_diagnostics=diagnostics)
    c=browser(app)
    return SimpleNamespace(app=app,c=c,engine=engine,provider=provider,transport=transport,diagnostics=diagnostics,path=tmp_path)

def board(case,mode='live',key='w'):
    w=ok(case.c.post('/api/v1/workspaces',json={'request_id':key,'mode':mode,'question':'Original workspace question'}))
    root='/api/v1/workspaces/'+w['id']
    search=ok(case.c.post(root+'/searches',json={'request_id':'s','query':'original'}))
    prep=ok(case.c.post(root+'/source-preparations',json={'request_id':'p','search_id':search['id'],'paper_ids':['paper-one']}))
    view=ok(case.c.post(root+'/boards',json={'request_id':'b','preparation_id':prep['id'],'paper_ids':['paper-one'],
        'question':'Original board question','fields':[{'id':'field','label':'Field','subquestion':'Original field question'}]}))
    d=view['definition'];case.root=root;case.board=root+'/boards/'+d['board_id'];case.definition=d
    return {'request_id':'investigate','board_id':d['board_id'],'expected_board_revision_id':d['revision_id'],
        'paper_id':'paper-one','field_id':'field','expected_draft_version':0,'reason':'Researcher question remains unresolved'}

def create(case, request=None):
    value=ok(case.c.post(case.root+'/investigations',json=request or case.request))
    case.ipath=case.root+'/investigations/'+value['origin']['id']
    return value

def save(case, view, query='women[tiab]',key='save'):
    return ok(case.c.put(case.ipath+'/plan',json={'request_id':key,'expected_revision_id':view['plan']['revision']['revision_id'],
        'draft':{'original_question':'Researcher follow-up question','input_mode':'manual_strategy','manual_strategy':query}}))

def candidate(view,key):
    r=view['plan']['revision']; c=r['compiled']['candidates'][0]
    return {'request_id':key,'expected_revision_id':r['revision_id'],'candidate_id':c['id'],'candidate_sha256':c['candidate_sha256']}

def approve(case, view,key='approve'):
    return ok(case.c.post(case.ipath+'/approve',json={**candidate(view,key),'acknowledge_unparsed_strategy':True}))

def execute_request(view,key='execute'):
    return {**candidate(view,key),'approval_id':view['plan']['approvals'][0]['id'],'max_results':5}

def ready(case,mode='live'):
    case.request=board(case,mode)
    return approve(case,save(case,create(case)))

def raw_snapshot(case):
    with case.engine._storage._connection() as db:
        return db.execute('SELECT snapshot FROM mvp_workspaces WHERE id=?',(case.root.split('/')[-1],)).fetchone()[0]

def test_complete_workflow_isolated_reopen_and_all_history(case):
    v=ready(case); before=raw_snapshot(case);board_before=ok(case.c.get(case.board+'/exports?format=json'))
    request=execute_request(v)
    done=ok(case.c.post(case.ipath+'/execute',json=request)); assert len(done['executions'])==1
    replay=ok(case.c.post(case.ipath+'/execute',json=request)); assert replay['executions']==done['executions']
    assert case.provider.calls==2
    item=done['executions'][0]['candidates'][0]
    decision={'request_id':'decision','candidate_id':item['id'],'expected_version':0,'decision':'shortlist','note':'Human only'}
    short=ok(case.c.post(case.ipath+'/decisions',json=decision)); assert short['executions'][0]['candidates'][0]['decision']=='shortlist'
    assert len(ok(case.c.post(case.ipath+'/decisions',json=decision))['decisions'])==1
    assert case.c.post(case.ipath+'/decisions',json={**decision,'request_id':'stale','decision':'dismiss'}).status_code==409
    second=save(case,short,'diet[tiab]','save-2')
    assert not second['plan']['approvals']
    assert case.c.post(case.ipath+'/execute',json={**candidate(second,'stale-approval'),'approval_id':request['approval_id']}).status_code==409
    assert raw_snapshot(case)==before and ok(case.c.get(case.board+'/exports?format=json'))==board_before
    export=ok(case.c.get(case.ipath+'/export')); audit=json.loads(export['json_text'])
    assert len(audit['plan_history'])==3 and audit['investigation']['decisions'][0]['decision']=='shortlist'
    app=create_app(case.path,services={'live':case.engine,'saved_example':case.engine},search_diagnostics=case.diagnostics)
    reopened=TestClient(app,base_url='http://127.0.0.1:8765');reopened.cookies.update(case.c.cookies)
    restored=ok(reopened.get(case.ipath));assert restored['origin']==v['origin'] and len(restored['executions'])==1

def test_saved_example_no_provider_or_diagnostic(case):
    v=ready(case,'saved_example');calls=case.provider.calls
    assert not v['capabilities']['diagnostics_enabled'] and not v['capabilities']['execution_enabled']
    for endpoint,request in [('diagnose',candidate(v,'diagnose')),('execute',execute_request(v))]:
        assert case.c.post(case.ipath+'/'+endpoint,json=request).status_code>=400
        plan=case.root+'/search-plans/'+v['origin']['plan_id']+'/'+endpoint
        assert case.c.post(plan,json=request).status_code>=400
    assert case.provider.calls==calls and case.transport.calls==0

def test_generic_execution_and_generation_cannot_bypass(case):
    v=ready(case);calls=case.provider.calls
    plan=case.root+'/search-plans/'+v['origin']['plan_id']
    assert case.c.post(plan+'/execute',json=execute_request(v)).status_code>=400
    assert case.c.post(plan+'/propose',json={'request_id':'gen','expected_revision_id':v['plan']['revision']['revision_id'],
        'original_question':v['plan']['revision']['draft']['original_question']}).status_code>=400
    assert case.provider.calls==calls

def test_stale_origin_and_exact_create_replay(case):
    request=board(case);first=create(case,request)
    path=case.board+'/drafts/paper-one/field'
    ok(case.c.put(path,json={'expected_revision_id':case.definition['revision_id'],'version':0,'data':{'value':'Saved later'}}))
    assert create(case,request)['origin']==first['origin']
    assert case.c.post(case.root+'/investigations',json={**request,'request_id':'new-stale'}).status_code==409
    assert case.c.post(case.root+'/investigations',json={**request,'reason':'Different same request'}).status_code==409

def test_ownership_csrf_and_readonly(case):
    v=ready(case);before=raw_snapshot(case);calls=case.provider.calls
    other=browser(case.app)
    for endpoint in [case.ipath,case.ipath+'/export',case.root+'/investigations']:
        assert other.get(endpoint).status_code==404
        ok(case.c.get(endpoint))
    assert other.post(case.ipath+'/execute',json=execute_request(v)).status_code==404
    c=browser(case.app); c.cookies.update(case.c.cookies);c.headers.pop('X-CSRF-Token')
    assert c.post(case.ipath+'/execute',json=execute_request(v)).status_code==403
    assert raw_snapshot(case)==before and case.provider.calls==calls and case.transport.calls==0

@pytest.mark.parametrize('kind',['exception','duplicate'])
def test_failure_replay_and_private_errors(case,kind):
    v=ready(case);before=raw_snapshot(case)
    if kind=='exception':case.provider.error=RuntimeError('api_key=PRIVATE_TEST_SENTINEL')
    else:case.provider.duplicate=True
    response=case.c.post(case.ipath+'/execute',json=execute_request(v));assert response.status_code>=400
    assert case.c.post(case.ipath+'/execute',json=execute_request(v)).status_code==response.status_code
    result=ok(case.c.get(case.ipath));assert len(result['failures'])==1 and not result['executions']
    assert 'PRIVATE_TEST_SENTINEL' not in json.dumps(result)+response.text
    assert case.provider.calls==2 and raw_snapshot(case)==before

@pytest.mark.parametrize('interruption',['revision','delete'])
def test_inflight_revision_and_deletion(case,interruption):
    v=ready(case);request=execute_request(v);case.provider.block=True
    with ThreadPoolExecutor(max_workers=2) as pool:
        future=pool.submit(case.c.post,case.ipath+'/execute',json=request)
        assert case.provider.entered.wait(2)
        duplicate=case.c.post(case.ipath+'/execute',json=request);assert duplicate.status_code==503
        if interruption=='revision':save(case,v,'changed[tiab]','concurrent')
        else:ok(case.c.delete(case.root))
        case.provider.release.set()
        response=future.result(5);assert response.status_code>=400
    assert case.provider.calls==2
    if interruption=='revision':
        assert not ok(case.c.get(case.ipath))['executions']
        assert case.c.post(case.ipath+'/execute',json=request).status_code>=400
    else:
        assert case.c.get(case.ipath).status_code==404
        with case.engine._storage._connection() as db:
            for table in ['mvp_investigations','mvp_investigation_previews','mvp_investigation_decisions']:
                assert db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0

def test_foreign_local_reference_rejected(case):
    request=board(case)
    request['local_draft']={'references':[{'source_id':'foreign-source','source_version':'v','source_sha256':'a'*64,
        'blocks_sha256':'b'*64,'block_id':'foreign-block','start':0,'end':3}]}
    assert case.c.post(case.root+'/investigations',json=request).status_code>=400

def test_exhausted_budget_rejects_before_provider(case,monkeypatch):
    from src.mvp.adapters import search_plan_storage as storage
    v=ready(case);before=raw_snapshot(case);calls=case.provider.calls
    monkeypatch.setattr(storage,'MAX_PLAN_AUXILIARY_BYTES',1)
    response=case.c.post(case.ipath+'/execute',json=execute_request(v))
    assert response.status_code>=400 and response.json()['error']['code']=='search_plan_storage_limit'
    assert case.provider.calls==calls and raw_snapshot(case)==before

def test_export_never_omits_approved_query_during_concurrent_revision(case,monkeypatch):
    from src.mvp.search_plans import SearchPlanService
    v=ready(case)
    original=SearchPlanService.view_in_transaction
    entered, release, writer_started=threading.Event(),threading.Event(),threading.Event()
    def read_under_snapshot(self,db,workspace_id,plan_id,revision_id=None):
        snapshot=original(self,db,workspace_id,plan_id,revision_id)
        if plan_id==v['origin']['plan_id'] and not entered.is_set():
            entered.set()
            assert release.wait(5)
        return snapshot
    def change_in_other_tab():
        writer_started.set()
        newer=approve(case,save(case,v,'newer[tiab]','other-tab-save'),'other-tab-approve')
        return ok(case.c.post(case.ipath+'/execute',json=execute_request(newer,'other-tab-execute')))
    monkeypatch.setattr(SearchPlanService,'view_in_transaction',read_under_snapshot)
    with ThreadPoolExecutor(max_workers=2) as pool:
        export=pool.submit(case.c.get,case.ipath+'/export')
        assert entered.wait(2)
        writer=pool.submit(change_in_other_tab)
        assert writer_started.wait(2)
        try:
            with pytest.raises(TimeoutError):writer.result(.05)
        finally:
            release.set()
        audit=json.loads(ok(export.result(5))['json_text'])
        after=writer.result(5)
    assert not audit['investigation']['executions'] and len(after['executions'])==1
    known={item['revision']['revision_id'] for item in audit['plan_history']}
    for result in audit['investigation']['executions']:
        assert result['execution']['revision_id'] in known
