"""Offline integration for explicit candidate collections and attributed notes."""
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from src.mvp.contracts import Paper,SearchPreview,PreparedSource
from src.mvp.ports import ProviderFailure
from tests.web_api.test_investigations_adversarial import case,board,create,save,approve,execute_request,browser,ok,raw_snapshot


def investigated(case, *, papers=None):
    request=board(case)
    # An explicit insufficient-evidence judgment with a retained original quote.
    binding=case.definition['sources'][0]
    block=ok(case.c.get(case.board+'/sources/'+binding['source_id']+'/blocks',params={'revision_id':case.definition['revision_id']}))['blocks'][0]
    ref={k:block['reference'][k] for k in ('source_id','source_version','source_sha256','blocks_sha256','block_id','start','end')}
    draft=ok(case.c.put(case.board+'/drafts/paper-one/field',json={'expected_revision_id':case.definition['revision_id'],'version':0,
        'data':{'value':'Synthetic original population','semantic_assessment':'partial','scope_result':'value_found','reason':'Inspected material is incomplete',
        'missing_information':'Population detail remains unresolved','references':[ref],'inspected_ranges':[ref]}}))
    cell=ok(case.c.post(case.board+'/cell-revisions',json={'request_id':'submit-original','expected_revision_id':case.definition['revision_id'],'paper_id':'paper-one','field_id':'field','draft_version':draft['version']}))
    request.update(expected_cell_head_id=cell['id'],expected_draft_version=0)
    case.request=request;view=approve(case,save(case,create(case)))
    sample=papers or [Paper(id='candidate-b',pmid='99002',doi='10.1234/b',title='Synthetic related paper B',abstract='Women diet microbiome Ω 🧬 sample with distinct population details.'),
        Paper(id='candidate-c',pmid='99003',doi='10.1234/c',title='Synthetic related paper C',abstract='Women diet sample for a comparator.')]
    def search(request):
        case.provider.calls+=1
        return SearchPreview(query=request.query,date_from=request.date_from,date_to=request.date_to,sort=request.sort,
            provider='synthetic-offline',mode='test',papers=sample,fetched_count=len(sample),total_reported=len(sample),truncated=False)
    case.provider.search=search
    result=ok(case.c.post(case.ipath+'/execute',json={**execute_request(view),'max_results':len(sample)}))
    for c in result['executions'][0]['candidates']:
        result=ok(case.c.post(case.ipath+'/decisions',json={'request_id':'short-'+c['id'],'candidate_id':c['id'],'expected_version':0,'decision':'shortlist'}))
    case.view=result;case.original_cell=cell
    return result


def handoff_request(case, *, include_original=True, all_candidates=False, **extra):
    chosen=case.view['executions'][0]['candidates'] if all_candidates else case.view['executions'][0]['candidates'][:1]
    return {'request_id':'handoff','name':'Explicit related-paper collection','candidates':[{'candidate_id':c['id'],'expected_decision_version':c['decision_version']} for c in chosen],
        'original_paper_ids':['paper-one'] if include_original else [],**extra}


def commit(case,request=None):
    request=request or handoff_request(case)
    preview=ok(case.c.post(case.ipath+'/handoff-preview',json=request))
    request={**request,'preview_sha256':preview['input_sha256']}
    h=ok(case.c.post(case.ipath+'/handoffs',json=request))
    case.handoff=h;case.commit_request=request
    return h


def prepare(case,handoff=None,key='prepare-candidate'):
    h=handoff or case.handoff;state=ok(case.c.get(case.root))
    papers=ok(case.c.get(case.root+'/collections/'+h['collection']['id']+'/papers'))['papers']
    request={'request_id':key,'collection_ref':h['collection']['origin'],'paper_ids':[p['id'] for p in papers],
        'expected_source_revision':state['source_revision'],'expected_preparation_id':state['current_preparation_id']}
    r=case.c.post(case.root+'/collection-preparation-jobs',json=request);assert r.status_code==202,r.text
    assert case.app.state.preparation_worker.run_once()
    job=ok(case.c.get(case.root+'/collection-preparation-jobs/'+r.json()['job']['id']))
    assert job['status']=='succeeded',job
    p=ok(case.c.get(case.root+'/source-preparations/'+job['result_preparation_id']))
    case.preparation=p
    return p


def retrieve(case):
    p=case.preparation
    r=ok(case.c.post(case.root+'/evidence-runs',json={'request_id':'retrieve-candidate','question':'Women diet population','top_k':5,
        'expected_preparation_id':p['id'],'expected_source_revision':p['source_revision']}))
    case.run=r;return r


def inspection_request(case, paper_id='candidate-b'):
    passage=next(p for p in case.run['passages'] if p['paper_id']==paper_id)
    return {'request_id':'inspect-'+paper_id,'handoff_id':case.handoff['id'],'preparation_id':case.preparation['id'],
        'run_id':case.run['id'],'passage_id':passage['id']}


def inspect(case):
    i=ok(case.c.post(case.ipath+'/inspections',json=inspection_request(case)));case.inspection=i;return i


def note_request(case, **extra):
    return {'request_id':'note','inspection_id':case.inspection['id'],'research_question':'How does diet relate to population-specific microbiome findings?',
        'interpretation':'Paper B offers related context; this does not fill missing facts about Paper A.',
        'confirm_inspected':True,'acknowledge_related_paper':True,**extra}


def test_complete_handoff_preparation_note_revision_and_expanded_board(case):
    investigated(case);before=raw_snapshot(case)
    original=ok(case.c.get(case.board+'/exports?format=json'));original_view=ok(case.c.get(case.board));h=commit(case)
    assert raw_snapshot(case)==before
    assert ok(case.c.post(case.ipath+'/handoffs',json=case.commit_request))==h
    assert len(ok(case.c.get(case.root+'/collections'))['collections'])==2 # one original search + one explicit collection
    papers=ok(case.c.get(case.root+'/collections/'+h['collection']['id']+'/papers'))['papers']
    detail=ok(case.c.get(case.root+'/collections/'+h['collection']['id']+'/paper',params={'paper_id':'candidate-b'}))
    origin=detail['member']['origins'][0]
    execution=case.view['executions'][0]['execution']
    assert origin['kind']=='investigation_candidate' and origin['execution_id']==execution['id']
    assert origin['approval_id']==execution['approval_id'] and origin['search_snapshot_sha256']==execution['search_snapshot_sha256']
    assert origin['decision_version']==1 and origin['original_cell_revision_id']==case.original_cell['id']
    p=prepare(case);retrieve(case);i=inspect(case)
    assert i['source_paper']['id']=='candidate-b' and i['reference']['paper_id']=='candidate-b'
    assert i['meaning']=='verified_displayed_passage_not_human_support'
    note=ok(case.c.post(case.ipath+'/notes',json=note_request(case)))
    assert note['original_paper_id']=='paper-one' and note['inspection']['source_paper']['id']=='candidate-b'
    assert note['meaning']=='related_paper_evidence_not_original_paper_finding'
    assert ok(case.c.post(case.ipath+'/notes',json=note_request(case)))==note
    revision=ok(case.c.post(case.ipath+'/notes',json=note_request(case,request_id='revise',note_id=note['id'],expected_revision_id=note['revision_id'],interpretation='Revised human interpretation; still about Paper B.')))
    assert revision['revision']==2 and revision['parent_revision_id']==note['revision_id']
    assert case.c.post(case.ipath+'/notes',json=note_request(case,request_id='stale',note_id=note['id'],expected_revision_id=note['revision_id'])).status_code==409
    derived=ok(case.c.post(case.root+'/boards',json={'request_id':'derived','preparation_id':p['id'],'paper_ids':p['selected_paper_ids'],
        'question':'Expanded research comparison','fields':[{'id':'population','label':'Population','subquestion':'What population was inspected?'}]}))
    assert derived['definition']['collection_ref']==h['collection']['origin']
    assert all(c['head'] is None for c in derived['cells'])
    retained=ok(case.c.get(case.board))
    assert retained['definition']==case.definition and retained['cells']==original_view['cells']
    assert retained['freshness']=='historical'
    after_export=ok(case.c.get(case.board+'/exports?format=json'))
    def scientific_content(value):
        if isinstance(value,dict):return {k:scientific_content(v) for k,v in value.items() if k not in ('freshness','freshness_reasons')}
        if isinstance(value,list):return [scientific_content(v) for v in value]
        return value
    assert scientific_content(after_export)==scientific_content(original)
    oldref=case.original_cell['references'][0]
    assert case.c.get(case.board+'/references/'+oldref['id']+'/context',params={'revision_id':case.definition['revision_id']}).status_code==200
    exported=ok(case.c.get(case.ipath+'/export'));audit=json.loads(exported['json_text'])
    assert audit['schema_version']=='mvp.investigation-audit.v2' and len(audit['research']['notes'])==2
    recorded=[r for r in audit['operations'] if r['operation'].startswith('investigation-note:')]
    assert len(recorded)==2 and recorded[0]['request']['confirm_inspected'] is True
    assert 'Paper B offers related context' in exported['markdown_text']
    assert 'Related-paper evidence; not a finding contained in the triggering original paper' in exported['markdown_text']
    # Collection workspace export also handles the new discriminated origins.
    assert case.c.get(case.root+'/exports?format=json').status_code==200


def test_shortlist_exact_review_and_request_replay(case):
    investigated(case);request=handoff_request(case)
    assert case.c.post(case.ipath+'/handoffs',json=request).json()['error']['code']=='stale_investigation_handoff'
    preview=ok(case.c.post(case.ipath+'/handoff-preview',json=request));request['preview_sha256']=preview['input_sha256']
    c=case.view['executions'][0]['candidates'][0]
    ok(case.c.post(case.ipath+'/decisions',json={'request_id':'dismiss','candidate_id':c['id'],'expected_version':1,'decision':'dismiss'}))
    assert case.c.post(case.ipath+'/handoffs',json=request).json()['error']['code']=='investigation_shortlist_required'
    ok(case.c.post(case.ipath+'/decisions',json={'request_id':'reshort','candidate_id':c['id'],'expected_version':2,'decision':'shortlist'}))
    assert case.c.post(case.ipath+'/handoffs',json=request).status_code==409
    request['candidates'][0]['expected_decision_version']=3
    h=commit(case,request)
    assert case.c.post(case.ipath+'/handoffs',json={**case.commit_request,'name':'Changed payload'}).status_code==409
    assert ok(case.c.post(case.ipath+'/handoffs',json=case.commit_request))==h


def test_duplicate_identifiers_require_explicit_policy_and_preserve_both_origins(case):
    investigated(case,papers=[Paper(id='paper-one',pmid='99001',title='Synthetic original',abstract='Women diet sample.')])
    request=handoff_request(case)
    preview=ok(case.c.post(case.ipath+'/handoff-preview',json=request))
    assert preview['duplicate_groups'][0]['kind']=='exact_identifier_duplicate'
    assert case.c.post(case.ipath+'/handoffs',json={**request,'preview_sha256':preview['input_sha256']}).json()['error']['code']=='duplicate_review_required'
    h=commit(case,{**request,'duplicate_policy':'merge_exact'})
    assert h['collection']['member_count']==1
    detail=ok(case.c.get(case.root+'/collections/'+h['collection']['id']+'/paper',params={'paper_id':'paper-one'}))
    assert {'investigation_original_report','investigation_candidate'} <= {o['kind'] for o in detail['member']['origins']}


def test_conflicting_identifiers_cannot_auto_merge(case):
    investigated(case,papers=[Paper(id='b',pmid='99002',doi='10.1234/conflict',title='B',abstract='Women'),Paper(id='c',pmid='99003',doi='10.1234/conflict',title='C',abstract='Women')])
    request=handoff_request(case,include_original=False,all_candidates=True,duplicate_policy='merge_exact')
    preview=ok(case.c.post(case.ipath+'/handoff-preview',json=request));group=preview['duplicate_groups'][0]
    assert group['kind']=='identifier_conflict'
    assert case.c.post(case.ipath+'/handoffs',json={**request,'preview_sha256':preview['input_sha256']}).status_code>=400
    h=commit(case,{**request,'conflict_decisions':{group['id']:'keep_separate'}})
    assert h['collection']['member_count']==2


def test_no_unprepared_citation_or_original_only_paper_becomes_followup_evidence(case):
    investigated(case);commit(case)
    bogus={'request_id':'fake','handoff_id':case.handoff['id'],'preparation_id':case.definition['preparation_id'],'run_id':'missing','passage_id':'missing'}
    assert case.c.post(case.ipath+'/inspections',json=bogus).json()['error']['code']=='unprepared_investigation_source'
    case.inspection={'id':'citation-only'}
    assert case.c.post(case.ipath+'/notes',json=note_request(case)).status_code==404
    prepare(case);retrieve(case)
    assert case.c.post(case.ipath+'/inspections',json=inspection_request(case,'paper-one')).json()['error']['code']=='investigation_candidate_source_required'
    inspect(case)
    for flag in ('confirm_inspected','acknowledge_related_paper'):
        assert case.c.post(case.ipath+'/notes',json=note_request(case,**{flag:False})).status_code==422
    for forged in ({'source_paper_id':'paper-one'},{'source_sha256':'a'*64},{'reference':{'quote':'invented'}}):
        assert case.c.post(case.ipath+'/notes',json={**note_request(case),**forged}).status_code==422


def test_failed_preparation_retains_source_unavailable_and_cannot_fabricate_note(case):
    investigated(case,papers=[Paper(id='candidate-b',pmid='99002',title='No source',abstract='')]);commit(case)
    case.provider.prepare=lambda paper:PreparedSource(paper_id=paper.id,status='no_usable_text',source_type='none',provider='synthetic',source_url='')
    p=prepare(case)
    assert all(s['source_type']=='none' for s in p['sources'])
    r=retrieve(case);assert r['passages']==[]
    assert case.c.post(case.ipath+'/inspections',json={'request_id':'missing','handoff_id':case.handoff['id'],'preparation_id':p['id'],'run_id':r['id'],'passage_id':'invented'}).status_code>=400
    assert ok(case.c.get(case.ipath+'/research'))['notes']==[]


def test_source_tamper_and_unicode_ranges_are_rejected(case):
    investigated(case);commit(case);prepare(case);retrieve(case)
    request=inspection_request(case)
    assert case.c.post(case.ipath+'/inspections',json={**request,'start':0,'end':99999}).status_code>=400
    i=inspect(case)
    source=next(s for s in case.preparation['sources'] if s['paper_id']=='candidate-b')
    text='Women diet microbiome Ω 🧬 sample with distinct population details.';start=text.index('Ω');end=start+3
    precise=ok(case.c.post(case.ipath+'/inspections',json={**request,'request_id':'unicode','start':start,'end':end}))
    assert precise['reference']['quote']==text[start:end]=='Ω 🧬'
    with case.engine._storage._connection() as db:
        row=db.execute('SELECT snapshot FROM mvp_workspaces WHERE id=?',(case.root.split('/')[-1],)).fetchone()
        snapshot=json.loads(row['snapshot']);next(s for p in snapshot['preparations'] if p['id']==case.preparation['id'] for s in p['sources'] if s['id']==source['id'])['blocks'][0]['text']='Changed'
        db.execute('UPDATE mvp_workspaces SET snapshot=? WHERE id=?',(json.dumps(snapshot),case.root.split('/')[-1]))
    assert case.c.post(case.ipath+'/notes',json=note_request(case)).status_code>=400


def test_cross_session_workspace_csrf_delete_and_read_only_reopen(case):
    investigated(case);commit(case);prepare(case);retrieve(case);inspect(case)
    ok(case.c.post(case.ipath+'/notes',json=note_request(case)))
    before=raw_snapshot(case);calls=case.provider.calls
    stranger=browser(case.app)
    for path in ('research','export'):
        assert stranger.get(case.ipath+'/'+path).status_code==404
        ok(case.c.get(case.ipath+'/'+path))
    assert raw_snapshot(case)==before and case.provider.calls==calls
    stranger.cookies.update(case.c.cookies);stranger.headers.pop('X-CSRF-Token')
    assert stranger.post(case.ipath+'/notes',json=note_request(case,request_id='csrf')).status_code==403
    other=ok(case.c.post('/api/v1/workspaces',json={'request_id':'other','mode':'live','question':'Other'}))
    assert case.c.get('/api/v1/workspaces/'+other['id']+'/investigations/'+case.view['origin']['id']+'/research').status_code==404
    assert case.c.delete(case.root).status_code==200
    assert case.c.get(case.ipath+'/research').status_code==404
    with case.engine._storage._connection() as db:
        for table in ('mvp_investigation_handoffs','mvp_investigation_inspections','mvp_research_evaluation_notes'):
            assert db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0


def test_two_tab_note_revisions_have_one_winner(case):
    investigated(case);commit(case);prepare(case);retrieve(case);inspect(case)
    note=ok(case.c.post(case.ipath+'/notes',json=note_request(case)))
    def revise(key):return case.c.post(case.ipath+'/notes',json=note_request(case,request_id=key,note_id=note['id'],expected_revision_id=note['revision_id'],interpretation=key))
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(revise,['tab-a','tab-b']))
    assert sorted(r.status_code for r in responses)==[200,409]
    assert len(ok(case.c.get(case.ipath+'/research'))['notes'])==2


def test_collection_quota_rolls_back_handoff_atomically(case,monkeypatch):
    from src.mvp.adapters import collection_storage
    investigated(case)
    monkeypatch.setattr(collection_storage,'MAX_COLLECTIONS',0)
    request=handoff_request(case);preview=ok(case.c.post(case.ipath+'/handoff-preview',json=request))
    response=case.c.post(case.ipath+'/handoffs',json={**request,'preview_sha256':preview['input_sha256']})
    assert response.status_code>=400 and response.json()['error']['code']=='import_storage_limit'
    assert ok(case.c.get(case.ipath+'/research'))['handoffs']==[]
    assert len(ok(case.c.get(case.root+'/collections'))['collections'])==1


def test_real_capacity_is_explicit_and_does_not_drop_selected_candidates(case):
    papers=[Paper(id=f'candidate-{i}',pmid=str(100000+i),title=f'Candidate {i}',abstract='Women diet sample.') for i in range(30)]
    investigated(case,papers=papers)
    request=handoff_request(case,all_candidates=True)
    preview=ok(case.c.post(case.ipath+'/handoff-preview',json=request))
    assert len(preview['members'])==31
    response=case.c.post(case.ipath+'/handoffs',json={**request,'preview_sha256':preview['input_sha256']})
    assert response.json()['error']['code']=='investigation_comparison_capacity'
    assert ok(case.c.get(case.ipath+'/research'))['handoffs']==[]
    request['candidates']=request['candidates'][:29]
    assert commit(case,request)['collection']['member_count']==30


def test_concurrent_request_replay_publishes_one_collection(case):
    investigated(case);request=handoff_request(case)
    preview=ok(case.c.post(case.ipath+'/handoff-preview',json=request));request['preview_sha256']=preview['input_sha256']
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:case.c.post(case.ipath+'/handoffs',json=request),range(2)))
    assert ok(responses[0])==ok(responses[1])
    assert len(ok(case.c.get(case.ipath+'/research'))['handoffs'])==1


def test_provider_failure_retains_honest_abstract_status_and_original_sources(case):
    investigated(case);commit(case);before=ok(case.c.get(case.root+'/source-preparations/'+case.definition['preparation_id']));state=ok(case.c.get(case.root))
    case.provider.prepare=lambda paper:(_ for _ in ()).throw(ProviderFailure('fixture_failure','Synthetic failure'))
    response=case.c.post(case.root+'/collection-preparation-jobs',json={'request_id':'failed-prepare','collection_ref':case.handoff['collection']['origin'],
        'paper_ids':['candidate-b'],'expected_source_revision':state['source_revision'],'expected_preparation_id':state['current_preparation_id']})
    assert response.status_code==202
    assert case.app.state.preparation_worker.run_once()
    job=ok(case.c.get(case.root+'/collection-preparation-jobs/'+response.json()['job']['id']))
    assert job['status']=='succeeded'
    prepared=ok(case.c.get(case.root+'/source-preparations/'+job['result_preparation_id']))
    assert prepared['sources'][0]['source_type']=='abstract' and prepared['sources'][0]['status']=='fetch_failed'
    assert prepared['sources'][0]['error']['code']=='fixture_failure'
    assert ok(case.c.get(case.root+'/source-preparations/'+case.definition['preparation_id']))==before
    assert ok(case.c.get(case.ipath+'/research'))['inspections']==[]


def test_saved_example_restrictions_and_persistent_restart(case):
    from fastapi.testclient import TestClient
    from src.web_api.app import create_app
    from src.mvp.service import MVPService
    from src.mvp.adapters.storage import SQLiteWorkspaceStorage
    investigated(case);commit(case);prepare(case);retrieve(case);inspect(case)
    ok(case.c.post(case.ipath+'/notes',json=note_request(case)))
    original=ok(case.c.get(case.ipath+'/research'));calls=case.provider.calls
    engine=MVPService(SQLiteWorkspaceStorage(case.path/'research.sqlite3'),case.provider,case.provider)
    app=create_app(case.path,services={'live':engine,'saved_example':engine},search_diagnostics=case.diagnostics)
    reopened=TestClient(app,base_url='http://127.0.0.1:8765');reopened.cookies.update(case.c.cookies)
    assert ok(reopened.get(case.ipath+'/research'))==original
    assert case.provider.calls==calls
    with case.app.state.registry.connection() as db:
        db.execute("UPDATE web_workspaces SET mode='saved_example' WHERE workspace_id=?",(case.root.rsplit('/',1)[-1],))
    assert ok(case.c.get(case.ipath+'/research'))==original
    request=execute_request(case.view,'forbidden-saved')
    assert case.c.post(case.ipath+'/execute',json=request).status_code>=400
    assert not ok(case.c.get(case.ipath))['capabilities']['execution_enabled']
    assert case.provider.calls==calls and case.transport.calls==0
