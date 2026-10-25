"""Offline mechanical board/passage round trips, not human usefulness evidence."""
import json
import signal
import socket
from types import SimpleNamespace
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from src.mvp.adapters.retrieval import LexicalRetrieval
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.contracts import Block, Paper, PreparedSource, SearchPreview, digest
from src.mvp.service import MVPService, _manifest
from src.web_api.app import COOKIE_NAME, create_app


class Sources:
    def __init__(self):
        self.search_calls = self.prepare_calls = 0
        self.papers = [Paper(pmid=str(980001+i), title=f'SYNTHETIC retained report {i}',
            abstract=('Women diet microbiome 😀. ' * 260 if i == 0 else
                      'Women dietary cohort microbiome.' if i < 3 else '')) for i in range(4)]

    def search(self, request):
        self.search_calls += 1
        return SearchPreview(query=request.query, papers=self.papers, total_reported=4, fetched_count=4,
            ordered_identifiers=[paper.id for paper in self.papers], truncated=False, mode='test', provider='synthetic')

    def prepare(self, paper):
        self.prepare_calls += 1
        i = self.papers.index(paper)
        if i in {0, 3}:
            return PreparedSource(paper_id=paper.id, status='abstract_only' if i == 0 else 'no_usable_text',
                source_type='abstract' if i == 0 else 'none', provider='synthetic', source_url='',
                blocks_sha256=digest([]) if i == 3 else '',
                blocks=[Block(id='abstract', ordinal=1, text=paper.abstract, locator={'type':'abstract'})] if i == 0 else [])
        return PreparedSource(paper_id=paper.id, status='full_text_retrieved', source_type='full_text',
            license='Synthetic software fixture', provider='synthetic', source_url='',
            blocks=[Block(id=f'body:{j}', ordinal=j, text=f'Women diet microbiome report {i} block {j}.',
                locator={'type':'body'}) for j in range(1,4 if i == 1 else 13)])


class Ranker(LexicalRetrieval):
    def __init__(self): self.corpora = []
    def search(self, question, sources, run_id, top_k=5):
        self.corpora.append([source.paper_id for source in sources])
        return super().search(question, sources, run_id, top_k)


@pytest.fixture
def flow(tmp_path, monkeypatch):
    for key in ('MVP_MAP_ENABLED', 'MVP_PROPOSALS_ENABLED', 'MVP_SEARCH_PLANNER_ENABLED'):
        monkeypatch.setenv(key, '0')
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **kw: pytest.fail('External networking is forbidden'))
    sources, ranker = Sources(), Ranker()
    engine = MVPService(SQLiteWorkspaceStorage(tmp_path/'research.sqlite3'), sources, sources, ranker)
    app = create_app(tmp_path, services={'saved_example':engine})
    client = TestClient(app, base_url='http://127.0.0.1:8765')
    csrf = client.get('/api/v1/session').json()['csrf_token']
    client.headers.update({'Origin':'http://127.0.0.1:3000','X-CSRF-Token':csrf})
    workspace = client.post('/api/v1/workspaces',json={'request_id':'w','mode':'saved_example'}).json()
    root = '/api/v1/workspaces/'+workspace['id']
    search = client.post(root+'/searches',json={'request_id':'s','query':'synthetic'}).json()
    prep = client.post(root+'/source-preparations',json={'request_id':'p','search_id':search['id'],
        'paper_ids':[paper.id for paper in sources.papers]}).json()
    request = {'request_id':'board','preparation_id':prep['id'],'question':'Women diet microbiome comparison',
        'paper_ids':[sources.papers[i].id for i in (0,1,3)], 'fields':[
            {'id':'diet:field','label':'Diet','subquestion':'women diet microbiome'},
            {'id':'missing','label':'Missing information','subquestion':'zzzznotretained'}]}
    response=client.post(root+'/boards',json=request)
    assert response.status_code==200,response.text
    definition=response.json()['definition']
    scope={'board_id':definition['board_id'],'board_revision_id':definition['revision_id']}
    return SimpleNamespace(app=app,client=client,root=root,board=root+'/boards/'+scope['board_id'],
        prep=prep,request=request,definition=definition,scope=scope,sources=sources,ranker=ranker,
        engine=engine,tmp=tmp_path)


def context(case, *, paper=None, field='diet:field'):
    params={'revision_id':case.scope['board_revision_id']}
    if paper is not None:params.update(paper_id=paper,field_id=field)
    return case.client.get(case.board+'/passage-search-context',params=params)


def retrieve(case, scope=None, key='run', question='women diet microbiome'):
    payload={'request_id':key,'question':question,'top_k':30,
        'expected_preparation_id':case.prep['id'],'expected_source_revision':case.prep['source_revision']}
    if scope is not None:payload['board_context']=scope
    # A separate process alarm bounds accidental lock recursion in actual HTTP.
    old=signal.signal(signal.SIGALRM,lambda *args:(_ for _ in ()).throw(AssertionError('retrieval deadlocked')))
    signal.alarm(8)
    try:return case.client.post(case.root+'/evidence-runs',json=payload)
    finally:signal.alarm(0);signal.signal(signal.SIGALRM,old)


def returned(case, run, scope, passage=None):
    return case.client.get(case.board+'/passage-source-context',params={
        'revision_id':scope['board_revision_id'],'paper_id':scope['paper_id'],'field_id':scope['field_id'],
        'run_id':run['id'],'passage_id':(passage or run['passages'][0])['id']})


def draft_path(case, scope):
    ids=[scope['board_id'],scope['board_revision_id']]
    if scope.get('paper_id') is not None:ids += [scope['paper_id'].encode().hex(),scope['field_id'].encode().hex()]
    value='board-evidence:'+':'.join(ids)
    return case.root+'/drafts/'+quote(value,safe='')


def test_navigation_reads_have_no_retrieval_preparation_or_cell_mutations(flow):
    c=flow
    before=c.client.get(c.root).json()
    export=c.client.get(c.board+'/exports?format=json').json()
    for _ in range(2):
        result=context(c);assert result.status_code==200,result.text
        assert result.json()['question']==c.definition['question']
        assert result.json()['paper_ids']==c.definition['paper_ids']
        assert c.client.get(draft_path(c,c.scope)).json()['version']==0
    assert c.client.get(c.root).json()==before
    assert c.client.get(c.board+'/exports?format=json').json()==export
    assert c.sources.search_calls==1 and c.sources.prepare_calls==4 and c.ranker.corpora==[]


def test_board_subset_is_restricted_before_unchanged_ranker_and_full_manifest_retained(flow):
    c=flow
    response=retrieve(c,c.scope);assert response.status_code==200,response.text
    run=response.json();assert c.ranker.corpora==[c.definition['paper_ids']]
    assert {p['paper_id'] for p in run['passages']}==set(c.definition['paper_ids'][:2])
    assert run['parameters']['board_passage_context']==context(c).json()
    with c.engine._storage._connection() as db:
        raw=json.loads(db.execute('SELECT snapshot FROM mvp_workspaces').fetchone()[0])
    assert run['source_snapshot_sha256']==digest(_manifest([PreparedSource.model_validate(source) for source in raw['sources']]))
    assert run['source_snapshot_sha256'] != c.definition['source_manifest_sha256']
    assert len(run['passages'])==4
    assert retrieve(c,c.scope).json()==run
    assert len(c.ranker.corpora)==1
    assert c.client.get(c.root).json()['runs'][-1]['board_context']=={
        **c.scope,'paper_id':None,'field_id':None}


def test_cell_return_opens_exact_long_unicode_abstract_slice_without_attachment(flow):
    c=flow;paper=c.definition['paper_ids'][0]
    scope={**c.scope,'paper_id':paper,'field_id':'diet:field'}
    selected=context(c,paper=paper);assert selected.json()['question']=='women diet microbiome'
    response=retrieve(c,scope);assert response.status_code==200,response.text
    run=response.json();assert c.ranker.corpora==[[paper]] and len(run['passages'])==1
    before=c.client.get(c.board).json()
    response=returned(c,run,scope);assert response.status_code==200,response.text
    opened=response.json();quote_text=opened['reference']['quote']
    assert opened['source']['source_type']=='abstract'
    assert quote_text==c.sources.papers[0].abstract[:4000] and len(quote_text)==4000
    assert opened['reference']['start']==opened['passage_start']==0
    assert opened['reference']['end']==4000
    assert opened['passage_end']==len(c.sources.papers[0].abstract)
    assert opened['passage_omitted_after']==opened['passage_end']-4000>0
    assert opened['block']['text']==quote_text
    assert c.client.get(c.board).json()==before
    assert c.sources.prepare_calls==4


def test_missing_source_and_empty_lexical_result_remain_explicit_empty_runs(flow):
    c=flow
    for index,(paper,question) in enumerate([(c.definition['paper_ids'][2],'women diet'),
        (c.definition['paper_ids'][0],'zzzznotretained')]):
        scope={**c.scope,'paper_id':paper,'field_id':'missing'}
        response=retrieve(c,scope,key='empty'+str(index),question=question)
        assert response.status_code==200,response.text
        assert response.json()['passages']==[] and response.json()['matched_passages']==0
        assert response.json()['parameters']['board_passage_context']['paper_ids']==[paper]


def test_scoped_search_draft_survives_refresh_preserves_unrelated_and_cas(flow):
    c=flow;paper=c.definition['paper_ids'][0]
    scope={**c.scope,'paper_id':paper,'field_id':'diet:field'}
    run=retrieve(c,scope).json();path=draft_path(c,scope)
    unrelated={'version':0,'data':{'question':'unrelated workspace query','top_k':5}}
    assert c.client.put(c.root+'/drafts/evidence',json=unrelated).status_code==200
    payload={'version':0,'data':{'question':'Edited query retained 😀','top_k':20,'selected_run_id':run['id']}}
    result=c.client.put(path,json=payload);assert result.status_code==200,result.text
    assert c.client.get(path).json()['data']==payload['data']
    other=TestClient(c.app,base_url='http://127.0.0.1:8765')
    other.cookies.set(COOKIE_NAME,c.client.cookies.get(COOKIE_NAME))
    assert other.get(path).json()['data']==payload['data']
    assert c.client.put(path,json={**payload,'data':{**payload['data'],'question':'stale overwrite'}}).status_code==409
    assert c.client.get(path).json()['data']==payload['data']
    assert c.client.get(c.root+'/drafts/evidence').json()['data']==unrelated['data']
    assert c.client.put(path,json={'version':1,'data':{**payload['data'],'question':''}}).status_code==200


def test_wrong_paper_field_and_unrelated_run_rejected_for_return_and_draft(flow):
    c=flow;first,second=c.definition['paper_ids'][:2]
    scope={**c.scope,'paper_id':first,'field_id':'diet:field'}
    run=retrieve(c,scope).json()
    wrong={**scope,'paper_id':second}
    assert returned(c,run,wrong).status_code==422
    assert returned(c,run,{**scope,'field_id':'missing'}).status_code==422
    ordinary=retrieve(c,key='ordinary').json()
    assert returned(c,ordinary,scope).status_code==422
    assert returned(c,run,scope,passage={'id':'unknown-passage'}).status_code==404
    for unrelated in (ordinary,run):
        target=scope if unrelated is ordinary else wrong
        response=c.client.put(draft_path(c,target),json={'version':0,'data':{
            'question':'kept','top_k':10,'selected_run_id':unrelated['id']}})
        assert response.status_code==422,response.text


def test_stale_board_or_preparation_rejects_search_and_return_without_new_run(flow):
    c=flow;scope={**c.scope,'paper_id':c.definition['paper_ids'][0],'field_id':'diet:field'}
    run=retrieve(c,scope).json()
    request={**c.request,'request_id':'revised','expected_revision_id':c.definition['revision_id'],
        'question':'Explicit revised comparison'}
    assert c.client.post(c.board+'/revisions',json=request).status_code==200
    before=len(c.client.get(c.root).json()['runs'])
    for response in (context(c),retrieve(c,scope,key='stale'),returned(c,run,scope),retrieve(c,scope)):
        assert response.status_code==409,response.text
        assert response.json()['error']['code']=='stale_board_revision'
    assert len(c.client.get(c.root).json()['runs'])==before


def test_new_workspace_preparation_never_silently_replaces_board_sources(flow):
    c=flow;scope={**c.scope,'paper_id':c.definition['paper_ids'][0],'field_id':'diet:field'}
    run=retrieve(c,scope).json()
    response=c.client.post(c.root+'/source-preparations',json={'request_id':'new-preparation',
        'search_id':c.prep['search_id'],'paper_ids':[c.definition['paper_ids'][1]]})
    assert response.status_code==200,response.text
    assert response.json()['id']!=c.prep['id']
    before=len(c.ranker.corpora)
    for response in (context(c),retrieve(c,scope,key='stale-prep'),returned(c,run,scope)):
        assert response.status_code==409,response.text
    assert len(c.ranker.corpora)==before
    # Exact retained drafts remain readable, even though running is forbidden.
    assert c.client.get(draft_path(c,scope)).status_code==200


def test_exact_return_can_be_explicitly_inspected_attached_then_submitted(flow):
    c=flow;paper=c.definition['paper_ids'][1]
    scope={**c.scope,'paper_id':paper,'field_id':'diet:field'}
    run=retrieve(c,scope).json();opened=returned(c,run,scope).json()
    ref={key:opened['reference'][key] for key in ('source_id','source_version','source_sha256',
        'blocks_sha256','block_id','start','end')}
    path=c.board+'/drafts/'+quote(paper,safe='')+'/diet%3Afield'
    saved=c.client.put(path,json={'expected_revision_id':scope['board_revision_id'],'version':0,
        'data':{'value':'Synthetic manual text after source inspection','references':[ref],
                'inspected_ranges':[ref],'semantic_assessment':'unassessed','scope_result':'value_found'}})
    assert saved.status_code==200,saved.text
    assert all(cell['head'] is None for cell in c.client.get(c.board).json()['cells'])
    submitted=c.client.post(c.board+'/cell-revisions',json={'request_id':'explicit-submit',
        'expected_revision_id':scope['board_revision_id'],'paper_id':paper,'field_id':'diet:field',
        'draft_version':saved.json()['version']})
    assert submitted.status_code==200,submitted.text
    assert submitted.json()['references'][0]['quote']==opened['reference']['quote']
    assert submitted.json()['semantic_assessment']=='unassessed'
    # Reopening a passage cannot rewrite an already submitted cell or its head.
    before=c.client.get(c.board).json()
    assert returned(c,run,scope).status_code==200
    assert c.client.get(c.board).json()==before


def test_same_cell_ids_from_another_board_are_not_interchangeable(flow):
    c=flow;scope={**c.scope,'paper_id':c.definition['paper_ids'][0],'field_id':'diet:field'}
    run=retrieve(c,scope).json()
    other=c.client.post(c.root+'/boards',json={**c.request,'request_id':'other-board'}).json()['definition']
    original=c.board;c.board=c.root+'/boards/'+other['board_id']
    other_scope={**scope,'board_id':other['board_id'],'board_revision_id':other['revision_id']}
    response=returned(c,run,other_scope)
    assert response.status_code==422,response.text
    c.board=original


def test_unsupported_retained_binding_is_explicit_and_does_not_retrieve(flow):
    c=flow
    with c.app.state.boards.store.connection() as db:
        raw=json.loads(db.execute('SELECT payload FROM board_definitions').fetchone()[0])
        raw['retrieval_profile']['profile_id']='unsupported-future-profile'
        raw['retrieval_profile_sha256']=digest(raw['retrieval_profile'])
        db.execute('UPDATE board_definitions SET payload=?,sha256=?',(json.dumps(raw),digest(raw)))
    for response in (context(c),retrieve(c,c.scope)):
        assert response.status_code==422,response.text
        assert response.json()['error']['code']=='unsupported_board_profile'
    assert c.ranker.corpora==[]


def test_deleted_workspace_invalidates_every_context_identifier(flow):
    c=flow;scope={**c.scope,'paper_id':c.definition['paper_ids'][0],'field_id':'diet:field'}
    run=retrieve(c,scope).json()
    assert c.client.delete(c.root).status_code==200
    assert context(c).status_code==404
    assert returned(c,run,scope).status_code==404
    assert c.client.get(draft_path(c,scope)).status_code==404


@pytest.mark.parametrize('count',[1,4,31,True])
def test_board_search_limit_is_five_to_thirty_without_changing_legacy_lower_limits(flow,count):
    c=flow
    response=c.client.post(c.root+'/evidence-runs',json={'request_id':'invalid-count',
        'question':'women diet','top_k':count,'expected_preparation_id':c.prep['id'],
        'expected_source_revision':c.prep['source_revision'],'board_context':c.scope})
    assert response.status_code==422,response.text
    assert c.ranker.corpora==[]


@pytest.mark.parametrize('target', ['source_version','source_sha256','blocks_sha256','anchor_quote','anchor_end','run_manifest','wrong_paper'])
def test_tampered_retained_passage_cannot_reopen_cell_inspector(flow,target):
    c=flow;scope={**c.scope,'paper_id':c.definition['paper_ids'][0],'field_id':'diet:field'}
    run=retrieve(c,scope).json()
    with c.engine._storage._connection() as db:
        raw=json.loads(db.execute('SELECT snapshot FROM mvp_workspaces').fetchone()[0])
        saved=raw['runs'][-1];passage=saved['passages'][0]
        if target in {'source_version','source_sha256','blocks_sha256'}:passage[target]='0'*64
        elif target=='anchor_quote':passage['anchor']['quote']='X'+passage['anchor']['quote'][1:]
        elif target=='anchor_end':
            passage['anchor']['end']+=1;passage['anchor']['quote']+='X'
        elif target=='wrong_paper':passage['paper_id']=c.definition['paper_ids'][1]
        else:saved['source_snapshot_sha256']='0'*64
        db.execute('UPDATE mvp_workspaces SET snapshot=?',(json.dumps(raw),))
    response=returned(c,run,scope)
    assert response.status_code==422,response.text
    assert response.json()['error']['code'] in {'source_integrity_error','board_integrity'}


def test_unscoped_old_receipt_fingerprint_replays_exactly(flow):
    c=flow;response=retrieve(c,key='legacy');assert response.status_code==200,response.text
    run=response.json()
    legacy={'request_id':'legacy','question':'women diet microbiome','top_k':30,
        'expected_preparation_id':c.prep['id'],'expected_source_revision':c.prep['source_revision']}
    with c.engine._storage._connection() as db:
        row=db.execute("SELECT fingerprint FROM mvp_requests WHERE operation='retrieve_bound_v1' AND request_id='legacy'").fetchone()
        assert row['fingerprint']==digest(legacy)
    assert c.client.post(c.root+'/evidence-runs',json=legacy).json()==run
    assert len(c.ranker.corpora)==1


def test_context_and_return_require_original_authorized_session(flow):
    c=flow;scope={**c.scope,'paper_id':c.definition['paper_ids'][0],'field_id':'diet:field'}
    run=retrieve(c,scope).json()
    other=TestClient(c.app,base_url='http://127.0.0.1:8765');other.get('/api/v1/session')
    for suffix in ['/passage-search-context?revision_id='+scope['board_revision_id'],
        '/passage-source-context?revision_id='+scope['board_revision_id']+'&paper_id='+scope['paper_id']+
        '&field_id=diet%3Afield&run_id='+run['id']+'&passage_id='+run['passages'][0]['id']]:
        assert other.get(c.board+suffix).status_code==404
    assert other.get(draft_path(c,scope)).status_code==404


@pytest.mark.parametrize('suffix',['a:b:c','a:b:%FF:d','a:b:paper:diet:field'])
def test_malformed_context_scopes_fail_safely(flow,suffix):
    response=flow.client.get(flow.root+'/drafts/'+quote('board-evidence:'+suffix,safe=''))
    assert response.status_code==422,response.text
