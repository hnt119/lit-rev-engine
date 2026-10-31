"""Offline investigation acceptance: immutable origins and explicit human actions."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from types import SimpleNamespace
import json
import socket
import threading

import pytest
from fastapi.testclient import TestClient
from src.mvp.adapters.saved_examples import SavedExampleProvider
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.contracts import Paper, SearchPreview
from src.mvp.service import MVPService
from src.mvp.search_plan_contracts import QueryDiagnosticReceipt
from src.web_api.app import create_app

BASE = 'http://127.0.0.1:8765'
ORIGIN = 'http://127.0.0.1:3000'
QUERY = '  women[tiab] AND microbiome[tiab]\r\n'

class Discovery:
    def __init__(self):
        self.calls = []
        self.fail = False
        self.block = False
        self.entered, self.release = threading.Event(), threading.Event()
        self.transform = lambda result: result
    def search(self, request):
        self.calls.append(request)
        if self.block:
            self.entered.set()
            assert self.release.wait(10)
        if self.fail:
            raise RuntimeError('PRIVATE_PROVIDER_SECRET_SENTINEL')
        papers = [Paper(pmid='111', title='Synthetic candidate', doi='10.1234/a'),
                  Paper(pmid='111', title='Duplicate candidate', doi='10.1234/a'),
                  Paper(pmid='222', title='Distinct PubMed report', doi='10.1234/a')]
        return self.transform(SearchPreview(query=request.query, date_from=request.date_from, date_to=request.date_to,
            sort=request.sort, total_reported=99, fetched_count=3, ordered_identifiers=['111', '111', '222'],
            papers=papers, truncated=True, mode='live', provider='synthetic-offline'))

class Diagnostics:
    enabled, reason = True, 'Offline mock'
    def __init__(self): self.calls = []
    def check(self, query, **kwargs):
        self.calls.append(query)
        return QueryDiagnosticReceipt(query=query, query_sha256=sha256(query.encode()).hexdigest(),
            date_from=kwargs['date_from'], date_to=kwargs['date_to'], sort=kwargs['sort'], status='succeeded',
            reported_count=99, sample_pmids=['111'], calls=1, truncated_sample=True)

def browser(app):
    client = TestClient(app, base_url=BASE)
    csrf = client.get('/api/v1/session').json()['csrf_token']
    client.headers.update({'Origin': ORIGIN, 'X-CSRF-Token': csrf})
    return client

def ok(response):
    assert response.status_code == 200, response.text
    return response.json()

@pytest.fixture
def case(tmp_path, monkeypatch):
    monkeypatch.setenv('MVP_MAP_ENABLED', '0')
    monkeypatch.setenv('MVP_PROPOSALS_ENABLED', '0')
    monkeypatch.setenv('MVP_SEARCH_PLANNER_ENABLED', '0')
    monkeypatch.delenv('NCBI_EMAIL', raising=False)
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: pytest.fail('Unexpected external network'))
    saved, provider, diagnostics = SavedExampleProvider(), Discovery(), Diagnostics()
    engine = MVPService(SQLiteWorkspaceStorage(tmp_path/'research.sqlite3'), saved, saved)
    app = create_app(tmp_path, services={'live': engine, 'saved_example': engine}, search_diagnostics=diagnostics)
    client = browser(app)
    def workspace(mode='live', request_id='workspace'):
        return '/api/v1/workspaces/'+ok(client.post('/api/v1/workspaces', json={'request_id':request_id,'mode':mode,'question':'Original research question'}))['id']
    root = workspace()
    search = ok(client.post(root+'/searches', json={'request_id':'search','query':'saved example','max_results':30}))
    prep = ok(client.post(root+'/source-preparations', json={'request_id':'prep','search_id':search['id'],'paper_ids':[search['papers'][0]['id']]}))
    board = ok(client.post(root+'/boards', json={'request_id':'board','question':'Original board question','preparation_id':prep['id'],
        'paper_ids':prep['selected_paper_ids'],'fields':[{'id':'field','label':'Population','subquestion':'What population was inspected?'}]}))
    engine._discovery = provider
    return SimpleNamespace(app=app, client=client, root=root, board=board, provider=provider, diagnostics=diagnostics,
        path=tmp_path, engine=engine, workspace=workspace)

def create(case, **changes):
    d = case.board['definition']
    request = {'request_id':'investigate','board_id':d['board_id'],'expected_board_revision_id':d['revision_id'],
        'paper_id':d['paper_ids'][0],'field_id':'field','expected_cell_head_id':None,'expected_draft_version':0,
        'local_draft':{'value':'Unsaved local notes'},'reason':'Need related literature to investigate this question.'}
    request.update(changes)
    return case.client.post(case.root+'/investigations', json=request)

def path(case, view): return case.root+'/investigations/'+view['origin']['id']

def save(case, view, key='save', query=QUERY):
    return ok(case.client.put(path(case,view)+'/plan', json={'request_id':key,'expected_revision_id':view['plan']['revision']['revision_id'],
        'draft':{'original_question':'Researcher follow-up question','input_mode':'manual_strategy','manual_strategy':query}}))

def candidate(view, key):
    r=view['plan']['revision']; c=r['compiled']['candidates'][0]
    return {'request_id':key,'expected_revision_id':r['revision_id'],'candidate_id':c['id'],'candidate_sha256':c['candidate_sha256']}

def approve(case, view):
    view=ok(case.client.post(path(case,view)+'/approve', json={**candidate(view,'approve'),'acknowledge_unparsed_strategy':True}))
    request={**candidate(view,'execute'),'approval_id':view['plan']['approvals'][0]['id'],'max_results':30}
    return view, request

def original(case):
    d=case.board['definition']; board=case.root+'/boards/'+d['board_id']
    with case.engine._storage._connection() as db:
        snapshot=db.execute('SELECT snapshot FROM mvp_workspaces WHERE id=?',(case.root.rsplit('/',1)[-1],)).fetchone()[0]
    return snapshot, ok(case.client.get(board)), ok(case.client.get(board+'/drafts/'+d['paper_ids'][0]+'/field'))

def test_complete_workflow_reopen_export_and_immutable_original(case):
    before=original(case)
    view=ok(create(case)); assert ok(create(case))==view
    assert view['origin']['local_draft']['value']=='Unsaved local notes'
    assert view['origin']['board']==case.board['definition']
    assert view['origin']['draft']['version']==0 and view['origin']['cell'] is None
    view=save(case,view)
    assert view['plan']['revision']['compiled']['candidates'][0]['query']==QUERY
    view,request=approve(case,view)
    diagnosed=ok(case.client.post(path(case,view)+'/diagnose',json=candidate(view,'diagnose')))
    assert len(diagnosed['plan']['diagnostics'])==1
    view=ok(case.client.post(path(case,view)+'/execute',json=request))
    assert ok(case.client.post(path(case,view)+'/execute',json=request))==view
    assert len(case.provider.calls)==1 and len(case.diagnostics.calls)==1
    candidates=view['executions'][0]['candidates']
    assert [c['paper']['pmid'] for c in candidates]==['111','222']
    assert view['executions'][0]['search']['fetched_count']==3
    for version,decision in enumerate(['shortlist','dismiss','unassessed'],1):
        body={'request_id':'decision'+str(version),'candidate_id':candidates[0]['id'],'expected_version':version-1,'decision':decision,'note':'Researcher note'}
        view=ok(case.client.post(path(case,view)+'/decisions',json=body))
        assert ok(case.client.post(path(case,view)+'/decisions',json=body))==view
    assert len(view['decisions'])==3
    assert original(case)==before
    old=case.board['definition']; source=old['sources'][0]
    context=case.client.get(case.root+'/boards/'+old['board_id']+'/sources/'+source['source_id']+'/blocks',params={'revision_id':old['revision_id'],'limit':1})
    assert context.status_code==200, context.text
    view=save(case,view,'edit','different[tiab]')
    assert view['plan']['approvals']==[] and len(view['executions'])==1
    export=ok(case.client.get(path(case,view)+'/export'))
    audit=json.loads(export['json_text'])
    assert len(audit['plan_history'])==3
    assert any(v['approvals'] for v in audit['plan_history'])
    assert QUERY in export['json_text'].replace('\\r','\r').replace('\\n','\n')
    assert 'not proof of a research gap' in export['markdown_text']
    reopened=TestClient(create_app(case.path,services={'live':case.engine},search_diagnostics=case.diagnostics),base_url=BASE)
    reopened.cookies.update(case.client.cookies)
    assert ok(reopened.get(path(case,view)))==view
    assert len(ok(case.client.get(case.root+'/investigations'))['investigations'])==1
    assert original(case)==before

def test_query_change_invalidation_and_generic_execution_escape(case):
    view,request=approve(case,save(case,ok(create(case))))
    generic=case.root+'/search-plans/'+view['origin']['plan_id']
    response=case.client.post(generic+'/execute',json=request)
    assert response.status_code>=400 and response.json()['error']['code']=='investigation_execution_scope'
    edited=save(case,view,'change')
    assert edited['plan']['approvals']==[]
    assert case.client.post(path(case,view)+'/execute',json=request).status_code>=400
    mixed={**candidate(edited,'mixed'),'approval_id':request['approval_id'],'max_results':30}
    assert case.client.post(path(case,view)+'/execute',json=mixed).json()['error']['code']=='stale_search_approval'
    assert case.provider.calls==[]
    assert case.client.post(generic+'/propose',json={'request_id':'proposal','expected_revision_id':edited['plan']['revision']['revision_id'],'original_question':'Researcher follow-up question'}).status_code>=400

def test_stale_origin_is_rejected_without_plan_or_board_changes(case):
    for changed in [{'expected_draft_version':1},{'expected_cell_head_id':'foreign'},{'expected_board_revision_id':'foreign'},{'paper_id':'foreign'},{'field_id':'foreign'}]:
        assert create(case,**changed).status_code>=400
    assert ok(case.client.get(case.root+'/investigations'))['investigations']==[]
    assert case.provider.calls==[]

def test_provider_failure_replay_and_safe_audit(case):
    view,request=approve(case,save(case,ok(create(case))))
    case.provider.fail=True
    response=case.client.post(path(case,view)+'/execute',json=request)
    assert response.status_code>=400
    assert case.client.post(path(case,view)+'/execute',json=request).json()==response.json()
    assert len(case.provider.calls)==1
    reopened=ok(case.client.get(path(case,view)))
    assert reopened['executions']==[] and len(reopened['failures'])==1
    export=ok(case.client.get(path(case,view)+'/export'))
    assert 'PRIVATE_PROVIDER_SECRET_SENTINEL' not in json.dumps(export)

def test_request_reuse_changed_payload_and_stale_candidate_decision(case):
    view=ok(create(case))
    assert create(case,reason='Changed reason').json()['error']['code']=='idempotency_conflict'
    view,request=approve(case,save(case,view))
    view=ok(case.client.post(path(case,view)+'/execute',json=request))
    assert case.client.post(path(case,view)+'/execute',json={**request,'max_results':10}).json()['error']['code']=='idempotency_conflict'
    key=view['executions'][0]['candidates'][0]['id']
    body={'request_id':'decide','candidate_id':key,'expected_version':0,'decision':'shortlist'}
    ok(case.client.post(path(case,view)+'/decisions',json=body))
    assert case.client.post(path(case,view)+'/decisions',json={**body,'request_id':'stale','decision':'dismiss'}).json()['error']['code']=='stale_investigation_decision'
    assert case.client.post(path(case,view)+'/decisions',json={**body,'request_id':'foreign','candidate_id':'unknown'}).status_code>=400

def test_saved_example_no_provider_calls_through_any_route(case):
    # Convert only this synthetic registry fixture's mode; same retained origin.
    with case.app.state.registry.connection() as db:
        db.execute("UPDATE web_workspaces SET mode='saved_example' WHERE workspace_id=?",(case.root.rsplit('/',1)[-1],))
    view,request=approve(case,save(case,ok(create(case))))
    assert not view['capabilities']['diagnostics_enabled'] and not view['capabilities']['execution_enabled']
    for suffix,body in [('execute',request),('diagnose',candidate(view,'diagnostic'))]:
        assert case.client.post(path(case,view)+'/'+suffix,json=body).status_code>=400
        assert case.client.post(case.root+'/search-plans/'+view['origin']['plan_id']+'/'+suffix,json=body).status_code>=400
    assert case.provider.calls==[] and case.diagnostics.calls==[]

def test_cross_session_workspace_isolation_and_csrf(case):
    view=ok(create(case)); stranger=browser(case.app)
    for tail in ['', '/export']:
        assert stranger.get(path(case,view)+tail).status_code==404
    other=case.workspace(request_id='other')
    assert case.client.get(other+'/investigations/'+view['origin']['id']).status_code==404
    assert case.client.post(other+'/investigations',json={'request_id':'foreign','board_id':case.board['definition']['board_id'],
        'expected_board_revision_id':case.board['definition']['revision_id'],'paper_id':case.board['definition']['paper_ids'][0],
        'field_id':'field','expected_draft_version':0,'reason':'reason'}).status_code>=400
    case.client.headers.pop('X-CSRF-Token')
    assert create(case,request_id='csrf').status_code==403

def test_concurrent_edit_fences_late_provider_result(case):
    view,request=approve(case,save(case,ok(create(case))))
    before=original(case); case.provider.block=True
    with ThreadPoolExecutor() as pool:
        future=pool.submit(case.client.post,path(case,view)+'/execute',json=request)
        assert case.provider.entered.wait(5)
        repeat=case.client.post(path(case,view)+'/execute',json=request)
        assert repeat.json()['error']['code']=='search_plan_call_pending'
        save(case,view,'while-provider','changed[tiab]')
        case.provider.release.set()
        assert future.result(10).status_code>=400
    assert ok(case.client.get(path(case,view)))['executions']==[]
    assert len(case.provider.calls)==1 and original(case)==before

@pytest.mark.parametrize('kind',['duplicate_id','mismatch','limit'])
def test_invalid_provider_output_is_not_published(case,kind):
    view,request=approve(case,save(case,ok(create(case))))
    def change(result):
        if kind=='duplicate_id':
            return result.model_copy(update={'papers':[Paper(id='same',pmid='111',title='A'),Paper(id='same',pmid='222',title='B')]})
        if kind=='mismatch': return result.model_copy(update={'query':'wrong'})
        return result.model_copy(update={'fetched_count':31})
    case.provider.transform=change
    assert case.client.post(path(case,view)+'/execute',json=request).status_code>=400
    assert ok(case.client.get(path(case,view)))['executions']==[]

def test_exact_submitted_cell_saved_draft_and_historical_references_survive(case):
    d=case.board['definition']; board=case.root+'/boards/'+d['board_id']; paper=d['paper_ids'][0]
    candidate=ok(case.client.post(board+'/candidates',json={'request_id':'passage','expected_revision_id':d['revision_id'],'paper_id':paper,'field_id':'field'}))['candidates'][0]['reference']
    ref={k:candidate[k] for k in ['source_id','source_version','source_sha256','blocks_sha256','block_id','start','end']}
    draft_path=board+'/drafts/'+paper+'/field'
    data={'value':'Partial original answer','references':[ref],'inspected_ranges':[ref],'semantic_assessment':'partial','scope_result':'value_found','missing_information':'Still uncertain','reason':'Scoped interpretation'}
    ok(case.client.put(draft_path,json={'expected_revision_id':d['revision_id'],'version':0,'data':data}))
    cell=ok(case.client.post(board+'/cell-revisions',json={'request_id':'submit','expected_revision_id':d['revision_id'],'paper_id':paper,'field_id':'field','draft_version':1}))
    saved=ok(case.client.put(draft_path,json={'expected_revision_id':d['revision_id'],'version':0,'expected_cell_head_id':cell['id'],'data':{**data,'value':'Retained next draft'}}))
    before=original(case)
    view=ok(create(case,expected_cell_head_id=cell['id'],expected_draft_version=1,local_draft={**data,'value':'Local next draft'}))
    assert view['origin']['cell']==cell and view['origin']['draft']==saved
    view,request=approve(case,save(case,view))
    ok(case.client.post(path(case,view)+'/execute',json=request))
    assert original(case)==before
    context=ok(case.client.get(board+'/references/'+cell['references'][0]['id']+'/context',params={'revision_id':d['revision_id']}))
    assert context['reference']['quote']==cell['references'][0]['quote']
    export=json.loads(ok(case.client.get(path(case,view)+'/export'))['json_text'])
    assert export['investigation']['origin']['cell']==cell
    assert any(op['request_id']=='execute' and op['status']=='succeeded' for op in export['operations'])

def test_export_separates_captured_drafts_and_preserves_literal_provenance(case):
    d=case.board['definition']; board=case.root+'/boards/'+d['board_id']; paper=d['paper_ids'][0]
    candidate=ok(case.client.post(board+'/candidates',json={'request_id':'passage','expected_revision_id':d['revision_id'],'paper_id':paper,'field_id':'field'}))['candidates'][0]['reference']
    ref={k:candidate[k] for k in ['source_id','source_version','source_sha256','blocks_sha256','block_id','start','end']}
    saved_data={'value':None,'references':[ref], 'semantic_assessment':'partial', 'scope_result':'not_found_in_inspected_material',
        'reason':'Saved 雪 ~~~~ reason', 'missing_information':'Saved missing'}
    local_data={'value':'', 'inspected_ranges':[ref], 'semantic_assessment':'unsupported', 'scope_result':'value_found',
        'reason':'Local 🧪 ~~~~~ reason', 'missing_information':'Local missing'}
    saved=ok(case.client.put(board+'/drafts/'+paper+'/field',json={'expected_revision_id':d['revision_id'],'version':0,'data':saved_data}))
    view=ok(create(case,expected_draft_version=1,local_draft=local_data))
    before=original(case)
    first=ok(case.client.get(path(case,view)+'/export'))
    second=ok(case.client.get(path(case,view)+'/export'))
    assert first['json_text']==second['json_text']
    audit=json.loads(first['json_text'])
    assert audit['investigation']['origin']['draft']==saved
    assert audit['investigation']['origin']['local_draft']==view['origin']['local_draft']
    assert original(case)==before
    markdown=first['markdown_text']
    saved_section=markdown.split('Saved draft snapshot (unsubmitted; captured at investigation creation):')[1].split('Local editor snapshot')[0]
    local_section=markdown.split('Local editor snapshot (unsubmitted; captured at investigation creation):')[1].split('## Search plan')[0]
    assert 'Value: null' in saved_section and 'Value: ""' in local_section
    assert 'Saved 雪 ~~~~ reason' in saved_section and 'Local 🧪 ~~~~~ reason' in local_section
    assert 'Semantic assessment: partial' in saved_section and 'Scope result: not_found_in_inspected_material' in saved_section
    assert 'Semantic assessment: unsupported' in local_section and 'Scope result: value_found' in local_section
    assert 'Missing information: Saved missing' in saved_section and 'Missing information: Local missing' in local_section
    for section in (saved_section,local_section):
        assert 'Producer: manual' in section
        for key in ('source_id','source_version','source_sha256','blocks_sha256','block_id'):
            assert ref[key] in section
        assert f"half-open Unicode code-point range: [{ref['start']}, {ref['end']})" in section
    assert 'Attached references:\n  Source:' in saved_section and 'Inspected ranges:\n  None' in saved_section
    assert 'Attached references:\n  None' in local_section and 'Inspected ranges:\n  Source:' in local_section
    assert markdown.splitlines()[2]=='~~~~~~text' and markdown.splitlines()[-1]=='~~~~~~'


def test_export_explicitly_marks_absent_draft_snapshots(case):
    view=ok(create(case,local_draft=None))
    markdown=ok(case.client.get(path(case,view)+'/export'))['markdown_text']
    assert 'Saved draft snapshot (unsubmitted; captured at investigation creation):\nAbsent' in markdown
    assert 'Local editor snapshot (unsubmitted; captured at investigation creation):\nAbsent' in markdown


def test_foreign_local_draft_anchors_rejected_without_creating_plan(case):
    bad={'source_id':'foreign','source_version':'1','source_sha256':'a'*64,'blocks_sha256':'b'*64,'block_id':'foreign','start':0,'end':1}
    for key in ['references','inspected_ranges']:
        assert create(case,local_draft={key:[bad]}).status_code>=400
    assert ok(case.client.get(case.root+'/investigations'))['investigations']==[]

def test_prefill_only_exact_owned_approved_revision_and_no_implicit_calls(case):
    seed=ok(case.client.post(case.root+'/search-plans',json={'request_id':'seed','draft':{'original_question':'Seed question','input_mode':'manual_strategy','manual_strategy':QUERY}}))
    revision=seed['revision']; c=revision['compiled']['candidates'][0]
    args={'seed_plan_id':revision['plan_id'],'seed_revision_id':revision['revision_id']}
    assert create(case,**args).json()['error']['code']=='investigation_seed_unapproved'
    approval=ok(case.client.post(case.root+'/search-plans/'+revision['plan_id']+'/approve',json={'request_id':'seed-approve','expected_revision_id':revision['revision_id'],'candidate_id':c['id'],'candidate_sha256':c['candidate_sha256'],'acknowledge_unparsed_strategy':True}))
    view=ok(create(case,**args))
    assert view['plan']['revision']['draft']==revision['draft']
    assert view['origin']['seed_approval_ids']==[approval['id']]
    assert view['plan']['approvals']==[]
    assert case.provider.calls==[] and case.diagnostics.calls==[]

def test_delete_workspace_fences_late_result_and_cascades_records(case):
    view,request=approve(case,save(case,ok(create(case))))
    case.provider.block=True
    with ThreadPoolExecutor() as pool:
        future=pool.submit(case.client.post,path(case,view)+'/execute',json=request)
        assert case.provider.entered.wait(5)
        response=case.client.delete(case.root)
        assert response.status_code==200,response.text
        case.provider.release.set()
        assert future.result(10).status_code>=400
    assert case.client.get(path(case,view)).status_code==404
    with case.engine._storage._connection() as db:
        assert db.execute('SELECT COUNT(*) FROM mvp_investigations').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM mvp_investigation_previews').fetchone()[0]==0

def test_export_snapshot_contains_every_execution_approved_revision(case,monkeypatch):
    from concurrent.futures import TimeoutError
    from src.mvp.search_plans import SearchPlanService
    view,request=approve(case,save(case,ok(create(case))))
    original_read=SearchPlanService.view_in_transaction
    entered,release,writer_started=threading.Event(),threading.Event(),threading.Event()
    def read_under_snapshot(self,db,workspace_id,plan_id,revision_id=None):
        snapshot=original_read(self,db,workspace_id,plan_id,revision_id)
        if plan_id==view['origin']['plan_id'] and not entered.is_set():
            entered.set()
            assert release.wait(5)
        return snapshot
    def other_tab():
        writer_started.set()
        newer=save(case,view,'other-tab','newer[tiab]')
        approved=ok(case.client.post(path(case,newer)+'/approve',json={**candidate(newer,'other-approve'),'acknowledge_unparsed_strategy':True}))
        return ok(case.client.post(path(case,newer)+'/execute',json={**candidate(newer,'other-execute'),'approval_id':approved['plan']['approvals'][0]['id'],'max_results':30}))
    monkeypatch.setattr(SearchPlanService,'view_in_transaction',read_under_snapshot)
    with ThreadPoolExecutor(max_workers=2) as pool:
        exporting=pool.submit(case.client.get,path(case,view)+'/export')
        assert entered.wait(3)
        writer=pool.submit(other_tab)
        assert writer_started.wait(3)
        try:
            with pytest.raises(TimeoutError): writer.result(.05)
        finally:
            release.set()
        audit=json.loads(ok(exporting.result(8))['json_text'])
        after=writer.result(8)
    assert audit['investigation']['executions']==[] and len(after['executions'])==1
    latest=json.loads(ok(case.client.get(path(case,view)+'/export'))['json_text'])
    revisions={item['revision']['revision_id'] for item in latest['plan_history']}
    assert all(item['execution']['revision_id'] in revisions for item in latest['investigation']['executions'])

def test_storage_budget_rejected_before_external_call(case,monkeypatch):
    from src.mvp.adapters import search_plan_storage
    view,request=approve(case,save(case,ok(create(case))))
    before=original(case)
    monkeypatch.setattr(search_plan_storage,'MAX_PLAN_AUXILIARY_BYTES',1)
    response=case.client.post(path(case,view)+'/execute',json=request)
    assert response.json()['error']['code']=='search_plan_storage_limit'
    assert case.provider.calls==[] and original(case)==before

def test_current_session_disabled_pubmed_setting_overrides_provider(case):
    view,request=approve(case,save(case,ok(create(case))))
    settings=ok(case.client.get('/api/v1/settings'))
    ok(case.client.put('/api/v1/settings',json={'expected_revision':settings['revision'],'preferences':settings['preferences']}))
    response=case.client.post(path(case,view)+'/execute',json=request)
    assert response.status_code>=400 and response.json()['error']['code']=='live_not_configured'
    diagnostic=case.client.post(path(case,view)+'/diagnose',json=candidate(view,'diagnostic'))
    assert diagnostic.status_code>=400
    assert case.provider.calls==[] and case.diagnostics.calls==[]

def test_resolved_cell_requires_actual_unresolved_draft_not_mere_presence(case):
    d=case.board['definition']; board=case.root+'/boards/'+d['board_id']; paper=d['paper_ids'][0]
    candidate=ok(case.client.post(board+'/candidates',json={'request_id':'passage','expected_revision_id':d['revision_id'],'paper_id':paper,'field_id':'field'}))['candidates'][0]['reference']
    ref={k:candidate[k] for k in ['source_id','source_version','source_sha256','blocks_sha256','block_id','start','end']}
    data={'value':'Original supported answer','references':[ref],'inspected_ranges':[ref],'semantic_assessment':'human_supported','scope_result':'value_found','reason':'Researcher supported'}
    draft_path=board+'/drafts/'+paper+'/field'
    ok(case.client.put(draft_path,json={'expected_revision_id':d['revision_id'],'version':0,'data':data}))
    cell=ok(case.client.post(board+'/cell-revisions',json={'request_id':'submit','expected_revision_id':d['revision_id'],'paper_id':paper,'field_id':'field','draft_version':1}))
    for local in [None, {}, data]:
        response=create(case,expected_cell_head_id=cell['id'],local_draft=local)
        assert response.json()['error']['code']=='investigation_origin_resolved'
    ok(case.client.put(draft_path,json={'expected_revision_id':d['revision_id'],'version':0,'expected_cell_head_id':cell['id'],'data':{}}))
    assert create(case,expected_cell_head_id=cell['id'],expected_draft_version=1,local_draft={}).json()['error']['code']=='investigation_origin_resolved'
    view=ok(create(case,expected_cell_head_id=cell['id'],expected_draft_version=1,local_draft={'value':'Unresolved new draft question'}))
    assert view['origin']['cell']==cell
