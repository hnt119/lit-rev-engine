"""Offline application safety tests with synthetic vectors, not quality evidence."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import socket
import pytest
from fastapi.testclient import TestClient
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.contracts import Block, Paper, PreparedSource, SearchPreview
from src.mvp.service import MVPService
from src.mvp.ports import MvpError
from src.mvp.hybrid_contracts import QWEN_PROFILE,MEDCPT_PROFILE
from src.web_api.app import create_app

class SyntheticSources:
    def __init__(self):
        self.papers=[Paper(pmid=str(930000+i),title='Synthetic title '+str(i),abstract='') for i in range(3)]
    def search(self,request):
        return SearchPreview(query=request.query,papers=self.papers,total_reported=3,fetched_count=3,ordered_identifiers=[v.id for v in self.papers],truncated=False,mode='test',provider='synthetic')
    def prepare(self,paper):
        i=self.papers.index(paper)
        text=['🧬 e\u0301 cohort mean 35 years. Does not increase survival. Semantic paraphrase endpoint.',
              'Wrong cohort of children only. Semantic near match.',
              'Lexical survival comparison with unavailable dose.'][i]
        return PreparedSource(paper_id=paper.id,status='abstract_only',source_type='abstract',provider='synthetic',source_url='',blocks=[Block(id='abstract',ordinal=1,text=text,locator={'type':'abstract'})])

class FakeAdapter:
    dimension=2;dense_metric='inner_product'
    def __init__(self,profile):self.profile_id=profile;self.manifest={'fixture':'offline-only', 'profile_id':profile};self.calls=[];self.hook=None;self.failure=False
    def validate_query(self,query):
        if len(query.split())>64:raise MvpError('query_budget','Explicitly shorten the question; no silent truncation.')
    def fits_document(self,title,text):return len(title)+len(text)<800
    def encode_queries(self,queries):self.calls.append(('query',list(queries)));return [[1.,0.] for _ in queries]
    def encode_documents(self,documents):
        self.calls.append(('documents',list(documents)))
        if self.hook:self.hook('index')
        return [[-0.5,float(i)/100] for i,_ in enumerate(documents)]
    def rerank(self,query,documents):
        self.calls.append(('rerank',list(documents)))
        if self.failure:raise MvpError('model_runtime_failed','Synthetic runtime failure; no fallback.')
        if self.hook:self.hook('rerank')
        return [-1.-i for i,_ in enumerate(documents)]
    def runtime_metadata(self):return {'device':'cpu','dtype':'float32','fixture':'offline-only'}

class FakePacks:
    def __init__(self,root):self.root=root;self.adapters={p:FakeAdapter(p) for p in (QWEN_PROFILE,MEDCPT_PROFILE)};self.installed=True
    def manifest(self,profile):return deepcopy(self.adapters[profile].manifest)
    def adapter(self,profile,device='cpu'):
        if not self.installed:raise MvpError('pack_missing','Explicitly install the selected optional pack.')
        return self.adapters[profile]
    def status(self,profile):return {'profile_id':profile,'installed':self.installed,'state':'runtime_test_needed'}
    def capabilities(self):return [self.status(p) for p in self.adapters]
    def remove(self,profile):self.installed=False
    def install(self,profile):self.installed=True;return self.status(profile)
    def cancel(self,profile):pass
    def check_runtime(self,profile,device='cpu'):return {'fixture':'mock execution only'}

@pytest.fixture
def flow(tmp_path,monkeypatch):
    monkeypatch.setattr(socket,'create_connection',lambda *a,**kw:pytest.fail('No external network allowed'))
    sources=SyntheticSources();engine=MVPService(SQLiteWorkspaceStorage(tmp_path/'research.sqlite3'),sources,sources)
    packs=FakePacks(tmp_path/'external-cache')
    app=create_app(tmp_path/'app-data',services={'saved_example':engine},retrieval_packs=packs)
    client=TestClient(app,base_url='http://127.0.0.1:8765')
    csrf=client.get('/api/v1/session').json()['csrf_token'];client.headers.update({'Origin':'http://127.0.0.1:3000','X-CSRF-Token':csrf})
    workspace=client.post('/api/v1/workspaces',json={'request_id':'workspace','mode':'saved_example'}).json();base='/api/v1/workspaces/'+workspace['id']
    search=client.post(base+'/searches',json={'request_id':'search','query':'synthetic'}).json()
    prep=client.post(base+'/source-preparations',json={'request_id':'prep','search_id':search['id'],'paper_ids':[v.id for v in sources.papers]}).json()
    payload={'request_id':'index','profile_id':QWEN_PROFILE,'device':'cpu','expected_preparation_id':prep['id'],'expected_source_revision':prep['source_revision'],'board_context':None}
    return SimpleNamespace(app=app,client=client,base=base,payload=payload,packs=packs,sources=sources,prep=prep,engine=engine,workspace=workspace,root=tmp_path)

def post(case,path,payload):
    result=case.client.post(case.base+path,json=payload)
    assert result.status_code==200,result.text
    return result.json()

def search(case,key='run',**updates):return post(case,'/hybrid-runs',{**case.payload,'request_id':key,'question':'Unmatched paraphrase','top_k':5,**updates})

def board(case):
    request={'request_id':'board','schema_version':'mvp.board-profile-request.v2','retrieval_profile_id':QWEN_PROFILE,'question':'Cohort comparison','preparation_id':case.prep['id'],'paper_ids':[case.sources.papers[0].id], 'fields':[{'id':'age','label':'Age','subquestion':'participant age'}]}
    definition=post(case,'/boards',request)['definition'];path=case.base+'/boards/'+definition['board_id']
    scope={'board_id':definition['board_id'],'board_revision_id':definition['revision_id'],'paper_id':case.sources.papers[0].id,'field_id':'age'}
    return definition,path,scope

def test_settings_reads_saves_never_load_models_or_change_other_sections(flow):
    c=flow;before=c.client.get('/api/v1/settings').json();assert c.client.get('/api/v1/settings/retrieval').status_code==200
    preferences=deepcopy(before['preferences']);preferences['retrieval']['profile_id']=MEDCPT_PROFILE
    saved=c.client.put('/api/v1/settings',json={'expected_revision':before['revision'],'preferences':preferences});assert saved.status_code==200
    assert saved.json()['preferences']['ai']==before['preferences']['ai']
    assert saved.json()['preferences']['maps']==before['preferences']['maps']
    assert saved.json()['preferences']['pubmed']==before['preferences']['pubmed']
    assert all(not a.calls for a in c.packs.adapters.values())

def test_search_requires_explicit_index_and_never_falls_back(flow):
    c=flow;response=c.client.post(c.base+'/hybrid-runs',json={**c.payload,'question':'paraphrase','top_k':5})
    assert response.status_code==422 and response.json()['error']['code']=='retrieval_index_missing'
    assert c.packs.adapters[QWEN_PROFILE].calls==[]
    post(c,'/hybrid-index',c.payload);c.packs.adapters[QWEN_PROFILE].failure=True
    response=c.client.post(c.base+'/hybrid-runs',json={**c.payload,'request_id':'fail','question':'paraphrase','top_k':5})
    assert response.status_code==422 and response.json()['error']['code']=='model_runtime_failed'
    assert c.client.get(c.base).json()['runs']==[]
    assert c.client.get(c.base+'/hybrid-runs').json()['runs']==[]

def test_negative_dense_only_results_are_versioned_and_exact_with_saved_history(flow):
    c=flow;post(c,'/hybrid-index',c.payload);run=search(c)
    result=run['result'];assert result['schema_version']=='mvp.hybrid-retrieval.v1'
    assert result['candidates'] and all(v['score']<0 for v in result['candidates'])
    assert any(v['branch_membership']==['dense'] and v['stages'][0]['bm25']['score'] is None for v in result['candidates'])
    candidate=next(v for v in result['candidates'] if v['reference']['paper_id']==c.sources.papers[0].id)
    context=c.client.get(c.base+'/hybrid-runs/'+run['id']+'/candidates/'+candidate['candidate_id']+'/context');assert context.status_code==200,context.text
    assert context.json()['reference']['quote']==candidate['reference']['quote']
    assert '🧬' in context.json()['reference']['quote'] and 'e\u0301' in context.json()['reference']['quote']
    c.packs.remove(QWEN_PROFILE)
    assert c.client.get(c.base+'/hybrid-runs/'+run['id']).json()==run
    assert c.client.get(c.base+'/hybrid-exports').json()['runs']==[run]
    assert c.client.get(c.base).json()['runs']==[]

def test_saved_request_replays_without_second_model_execution_and_conflicts_on_change(flow):
    c=flow;post(c,'/hybrid-index',c.payload);run=search(c);calls=deepcopy(c.packs.adapters[QWEN_PROFILE].calls)
    assert search(c)==run and c.packs.adapters[QWEN_PROFILE].calls==calls
    response=c.client.post(c.base+'/hybrid-runs',json={**c.payload,'request_id':'run','question':'different','top_k':5})
    assert response.status_code==409 and response.json()['error']['code']=='idempotency_conflict'

def test_board_cell_scope_is_applied_before_document_encoding_and_round_trip_works(flow):
    c=flow;definition,path,scope=board(c)
    post(c,'/hybrid-index',{**c.payload,'board_context':scope})
    docs=[docs for kind,docs in c.packs.adapters[QWEN_PROFILE].calls if kind=='documents']
    assert docs and all('Wrong cohort' not in text and 'unavailable dose' not in text for batch in docs for title,text in batch)
    request={'request_id':'cell-candidates','expected_revision_id':definition['revision_id'],'paper_id':scope['paper_id'],'field_id':scope['field_id'],'top_k':3}
    response=c.client.post(path+'/candidates',json=request);assert response.status_code==200,response.text
    candidates=response.json();assert candidates['schema_version']=='mvp.board-candidates.hybrid.v1'
    assert candidates['result']['requested_count']==3
    assert {v['reference']['paper_id'] for v in candidates['result']['candidates']}=={scope['paper_id']}
    reference=candidates['result']['candidates'][0]['reference']
    context=c.client.get(path+'/references/'+reference['id']+'/context',params={'revision_id':definition['revision_id']})
    assert context.status_code==200,context.text
    assert context.json()['reference']==reference
    exported=c.client.get(path+'/exports?format=json').json();assert exported['candidate_runs']==[candidates]
    c.packs.remove(QWEN_PROFILE)
    assert c.client.post(path+'/candidates',json=request).json()==candidates

def test_board_passage_to_source_to_cell_binding(flow):
    c=flow;definition,path,scope=board(c);post(c,'/hybrid-index',{**c.payload,'board_context':scope})
    run=search(c,board_context=scope)
    candidate=run['result']['candidates'][0]
    returned=c.client.get(path+'/passage-source-context',params={'revision_id':definition['revision_id'],'paper_id':scope['paper_id'],'field_id':'age','run_id':run['id'],'passage_id':candidate['candidate_id']})
    assert returned.status_code==200,returned.text
    assert returned.json()['reference']['quote']==candidate['reference']['quote']
    wrong={**scope,'paper_id':c.sources.papers[1].id}
    response=c.client.get(path+'/passage-source-context',params={'revision_id':definition['revision_id'],'paper_id':wrong['paper_id'],'field_id':'age','run_id':run['id'],'passage_id':candidate['candidate_id']})
    assert response.status_code==422

def test_overbudget_query_has_no_query_or_reranker_execution(flow):
    c=flow;post(c,'/hybrid-index',c.payload);calls=deepcopy(c.packs.adapters[QWEN_PROFILE].calls)
    response=c.client.post(c.base+'/hybrid-runs',json={**c.payload,'request_id':'long','question':'word '*65,'top_k':5})
    assert response.status_code==422 and response.json()['error']['code']=='query_budget'
    assert c.packs.adapters[QWEN_PROFILE].calls==calls

def test_corrupt_index_is_rejected_without_model_search(flow):
    c=flow;post(c,'/hybrid-index',c.payload)
    path=next((c.packs.root/'indexes').rglob('*.json'));path.write_text('{}')
    response=c.client.post(c.base+'/hybrid-runs',json={**c.payload,'request_id':'corrupt','question':'paraphrase','top_k':5})
    assert response.status_code==422 and response.json()['error']['code']=='retrieval_index_corrupt'
    assert not any(kind=='query' for kind,_ in c.packs.adapters[QWEN_PROFILE].calls)

def test_workspace_deletion_during_encoding_fences_late_index_publication(flow):
    c=flow
    c.packs.adapters[QWEN_PROFILE].hook=lambda stage:c.client.delete(c.base) if stage=='index' else None
    response=c.client.post(c.base+'/hybrid-index',json=c.payload)
    assert response.status_code in {404,422,503},response.text
    assert not list((c.packs.root/'indexes').rglob('*.json'))

def test_source_change_during_rerank_has_no_late_run(flow):
    c=flow;post(c,'/hybrid-index',c.payload)
    def change(stage):
        if stage=='rerank':
            result=c.client.post(c.base+'/source-preparations',json={'request_id':'new-prep','search_id':c.prep['search_id'],'paper_ids':[c.sources.papers[1].id]})
            assert result.status_code==200,result.text
    c.packs.adapters[QWEN_PROFILE].hook=change
    response=c.client.post(c.base+'/hybrid-runs',json={**c.payload,'request_id':'stale','question':'paraphrase','top_k':5})
    assert response.status_code==409,response.text
    assert c.client.get(c.base+'/hybrid-runs').json()['runs']==[]

def test_explicit_index_retry_is_idempotent_and_changed_key_input_is_rejected(flow):
    c=flow;first=post(c,'/hybrid-index',c.payload);calls=deepcopy(c.packs.adapters[QWEN_PROFILE].calls)
    assert post(c,'/hybrid-index',c.payload)==first
    assert c.packs.adapters[QWEN_PROFILE].calls==calls
    response=c.client.post(c.base+'/hybrid-index',json={**c.payload,'profile_id':MEDCPT_PROFILE})
    assert response.status_code==409 and response.json()['error']['code']=='idempotency_conflict'

def test_job_identifiers_are_owned_by_workspace_without_cross_workspace_replacement(flow):
    runtime=flow.app.state.hybrid_retrieval
    with runtime.operation('workspace-a','same-request','index','fingerprint-a'):pass
    with runtime.operation('workspace-b','same-request','index','fingerprint-b'):pass
    assert runtime.job('workspace-a','same-request')['state']=='completed'
    assert runtime.job('workspace-b','same-request')['state']=='completed'
