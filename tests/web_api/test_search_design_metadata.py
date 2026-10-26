"""Offline additive notes/export acceptance; never real provider/model validation."""
from copy import deepcopy
import json
import pytest
from tests.web_api.test_search_plans_independent import case,create,route,candidate,browser,RAW,update


def notes():return {'extraction_questions':[{'id':'specimen','question':'Which microbiome specimens were sampled?','source_span':None}], 'term_notes':[], 'external_searches':[]}


def save(case,view,metadata=None,version=0,key='metadata'):
    return case.client.put(route(case,view)+'/metadata',json={'request_id':key,'expected_revision_id':view['revision']['revision_id'],'expected_version':version,'metadata':metadata or notes()})


def test_sidecar_is_revision_bound_append_only_and_does_not_rehash_legacy_plan(case):
    view=create(case);original=deepcopy(view)
    response=save(case,view);assert response.status_code==200,response.text
    assert response.json()['version']==1
    assert case.client.get(route(case,view)).json()==original
    assert not case.provider.calls and not case.planner.calls and not case.transport.calls
    conflict=save(case,view,key='other');assert conflict.status_code==409,conflict.text
    again=save(case,view);assert again.json()['version']==1
    changed=notes();changed['extraction_questions'][0]['question']='Which outcome domain is reported?'
    second=save(case,view,changed,1,'second');assert second.status_code==200,second.text
    assert [h['version'] for h in second.json()['history']]==[2,1]
    revised=update(case,view)
    old=case.client.get(route(case,view)+'/metadata',params={'revision_id':view['revision']['revision_id']}).json()
    assert old['version']==2 and old['current'] is False
    assert case.client.get(route(case,revised)+'/metadata').json()['version']==0
    assert save(case,view,version=2,key='stale').status_code==409


def test_readable_export_preserves_raw_query_and_labels_missing_diagnostics(case):
    view=create(case)
    saved=save(case,view);assert saved.status_code==200,saved.text
    params={'revision_id':view['revision']['revision_id'],'candidate_id':'manual_strategy','format':'json'}
    exported=case.client.get(route(case,view)+'/strategy-export',params=params)
    assert exported.status_code==200,exported.text
    value=exported.json();assert value['query']==RAW and value['approval_status']=='not_approved'
    assert value['diagnostic'] is None and value['capture'] is None
    assert value['design_notes']['metadata']==notes()
    markdown=case.client.get(route(case,view)+'/strategy-export',params={**params,'format':'markdown'})
    assert RAW in markdown.text and 'No provider diagnostic is recorded' in markdown.text
    assert 'No authoritative terminology registry' in markdown.text
    approved=case.client.post(route(case,view)+'/approve',json={**candidate(view,'approval'),'acknowledge_unparsed_strategy':True})
    assert approved.status_code==200,approved.text
    assert case.client.get(route(case,view)+'/strategy-export',params=params).json()['approval_status']=='researcher_approved_intent'
    other=browser(case.app)
    assert other.get(route(case,view)+'/metadata').status_code==404
    assert other.get(route(case,view)+'/strategy-export',params=params).status_code==404
    assert not case.provider.calls and not case.planner.calls and not case.transport.calls


def test_external_strategy_links_only_owned_import_snapshot_and_keeps_exact_query(case):
    view=create(case)
    imported=case.client.post(case.root+'/imports/csv',content=b'Title,Abstract\nSYNTHETIC import,fixture only\n',headers={'Content-Type':'application/octet-stream','X-Request-ID':'import'})
    assert imported.status_code==200,imported.text
    doc=imported.json();rows=case.client.get(case.root+'/imports/'+doc['id']+'/rows').json()['rows']
    collection=case.client.post(case.root+'/imports/'+doc['id']+'/commit',json={'request_id':'commit','expected_revision':doc['revision'],'name':'SYNTHETIC imported bibliography','accepted_row_ids':[rows[0]['id']]}).json()
    raw='  (outside ADJ3 query)\r\nNOT exclusion\r  '
    metadata=notes();metadata['external_searches']=[{'id':'external','database':'MEDLINE','platform':'Researcher external platform','query':raw,'executed_on':'2026-10-26','reported_count':0,'collection_ref':collection['origin']}]
    response=save(case,view,metadata);assert response.status_code==200,response.text
    assert response.json()['metadata']['external_searches'][0]['query']==raw
    bad=deepcopy(metadata);bad['external_searches'][0]['collection_ref']['collection_snapshot_sha256']='0'*64
    assert save(case,view,bad,1,'bad-hash').status_code==409
    bad['external_searches'][0]['collection_ref']['collection_id']='another-workspace-id'
    assert save(case,view,bad,1,'bad-owner').status_code==404
    exported=case.client.get(route(case,view)+'/strategy-export',params={'revision_id':view['revision']['revision_id'],'candidate_id':'manual_strategy','format':'json'}).json()
    assert exported['design_notes']['metadata']['external_searches'][0]['query']==raw
    assert exported['execution'] is None and exported['diagnostic'] is None
    assert any('researcher-recorded' in text for text in exported['limitations'])
    assert not case.provider.calls and not case.transport.calls


def test_metadata_draft_uses_existing_cas_and_rejects_stale_or_wrong_revision(case):
    view=create(case);plan=view['revision']['plan_id'];revision=view['revision']['revision_id']
    scope='search-plan-metadata:'+plan+':'+revision
    path=case.root+'/drafts/'+scope
    payload={'version':0,'expected_assessment_head':'0','data':{'plan_id':plan,'revision_id':revision,'base_metadata_version':0,'metadata':notes()}}
    result=case.client.put(path,json=payload);assert result.status_code==200,result.text
    assert case.client.get(path).json()['data']['metadata']==notes()
    assert case.client.put(path,json=payload).status_code==409
    assert save(case,view).status_code==200
    payload['version']=1
    assert case.client.put(path,json=payload).status_code==409
    assert not case.provider.calls and not case.planner.calls


def test_markdown_source_prose_is_literal_and_diagnostic_fields_stay_truthful(case):
    from src.web_api.search_strategy_routes import strategy_markdown
    view=create(case)
    params={'revision_id':view['revision']['revision_id'],'candidate_id':'manual_strategy','format':'json'}
    value=case.client.get(route(case,view)+'/strategy-export',params=params).json()
    value['question']='![track](https://invalid.example/image) <script>unsafe</script>'
    value['concepts']=[{'label':'[link](https://invalid.example)','role':'other','requirement':'required','retrieval_use':'query','terms':[]}]
    value['differences']=['Explicitly deferred condition; not automatically relaxed']
    value['diagnostic']={'receipt':{'status':'provider_error','reported_count':0,'calls':1,'retrieved_at':'2026-10-26T00:00:00Z','sample_pmids':[],'sample_limit':5,'query_translation':None,
        'messages':[{'code':'Unrecognized','message':'term warning'}],'error':{'code':'provider_error','message':'Provider failed'},
        'seed_results':[{'seed':{'id':'known','pmid':'123','purpose':'construction'},'query_membership':'not_checked','preview_recovery':'absent','reason':'Membership unavailable; preview absence is distinct'}]}}
    text=strategy_markdown(value)
    assert '![track](' not in text and '[link](' not in text and '<script>' not in text
    assert '\\!\\[track\\]' in text and '&lt;script&gt;' in text
    assert RAW in text
    assert 'Retrieved at:' in text and '0/5' in text and 'Seed 123' in text
    assert 'Membership unavailable' in text and 'Provider/operation error:' in text
    assert 'Successful diagnostic reported zero' not in text
    assert 'Explicitly deferred condition' in text


def test_incomplete_notes_are_durable_drafts_but_not_submittable_metadata(case):
    view=create(case);plan=view['revision']['plan_id'];revision=view['revision']['revision_id']
    path=case.root+'/drafts/search-plan-metadata:'+plan+':'+revision
    partial={'extraction_questions':[{'id':'later','question':'','source_span':None}], 'term_notes':[],
             'external_searches':[{'id':'external','database':'','platform':'','query':'','executed_on':None,'reported_count':None,'limits_note':'','collection_ref':None}]}
    body={'version':0,'expected_assessment_head':'0','data':{'plan_id':plan,'revision_id':revision,'base_metadata_version':0,'metadata':partial}}
    result=case.client.put(path,json=body);assert result.status_code==200,result.text
    assert case.client.get(path).json()['data']['metadata']==partial
    assert save(case,view,partial).status_code==422
    body['version']=1;body['data']['metadata']['extraction_questions'][0]['question']='Which specimens are reported?'
    body['data']['metadata']['external_searches']=[]
    result=case.client.put(path,json=body);assert result.status_code==200,result.text
    assert save(case,view,body['data']['metadata']).status_code==200
    assert not case.provider.calls and not case.planner.calls and not case.transport.calls


def test_notes_reject_wrong_term_and_span_but_replay_returns_exact_saved_version(case):
    view=create(case);metadata=notes()
    metadata['term_notes']=[{'concept_id':'wrong','term_id':'wrong','note':'not verified','authority_reference':''}]
    assert save(case,view,metadata).status_code==422
    metadata=notes();metadata['extraction_questions'][0]['source_span']={'start':0,'end':1,'text':'incorrect'}
    assert save(case,view,metadata,key='span').status_code==422
    assert save(case,view,key='first').status_code==200
    changed=notes();changed['extraction_questions'][0]['question']='Changed reading question'
    assert save(case,view,changed,1,'second').json()['version']==2
    replay=save(case,view,key='first').json()
    assert replay['version']==1 and replay['latest_version']==2 and replay['metadata']==notes()
