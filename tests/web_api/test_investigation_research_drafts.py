"""Offline authorization/lifecycle tests for incomplete investigation UI drafts."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import copy, deepcopy
from threading import Event, local
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from tests.web_api.test_investigations_adversarial import case, browser, ok, raw_snapshot
from tests.web_api.test_investigation_research import (
    investigated, commit, prepare, retrieve, inspect, note_request, handoff_request,
)


def target(case, investigation_id=None, root=None):
    identifier=investigation_id or case.view['origin']['id']
    return (root or case.root)+'/drafts/'+quote('investigation-research:'+identifier,safe='')


def data(case, **changes):
    return {'investigation_id':case.view['origin']['id'], 'collection_name':'',
        'retrieval_question':'  \r\nWomen Ω 🧬\r\n ', 'research_question':'', 'interpretation':'',
        'confirm_inspected':False, 'acknowledge_related_paper':False, **changes}


def save(case, value=None, version=0, **changes):
    return case.c.put(target(case),json={'version':version,'data':data(case) if value is None else value,**changes})


@pytest.fixture
def prepared(case):
    investigated(case);commit(case);prepare(case);retrieve(case);inspect(case)
    case.note=ok(case.c.post(case.ipath+'/notes',json=note_request(case)))
    return case


def linked(case, **changes):
    return data(case,candidate_ids=case.handoff['selected_candidate_ids'],original_paper_ids=['paper-one'],
        handoff_id=case.handoff['id'],preparation_id=case.preparation['id'],run_id=case.run['id'],
        inspection_id=case.inspection['id'],note_id=case.note['id'],expected_note_revision_id=case.note['revision_id'],
        board_paper_ids=case.preparation['selected_paper_ids'],**changes)


def test_incomplete_draft_roundtrip_reopen_has_no_research_or_provider_side_effects(case,monkeypatch):
    investigated(case)
    before=raw_snapshot(case);research=ok(case.c.get(case.ipath+'/research'));board=ok(case.c.get(case.board+'/exports?format=json'))
    calls=case.provider.calls
    def forbidden(*args,**kwargs):pytest.fail('Draft navigation attempted provider/model/retrieval/compiler work')
    monkeypatch.setattr(case.provider,'search',forbidden)
    monkeypatch.setattr(case.provider,'prepare',forbidden)
    monkeypatch.setattr(case.transport,'request',forbidden)
    monkeypatch.setattr('src.mvp.search_plans.compile_search_plan',forbidden)
    assert ok(case.c.get(target(case)))['version']==0
    saved=ok(save(case));assert saved['data']==data(case)
    assert ok(case.c.get(target(case)))==saved
    from src.web_api.app import create_app
    app=create_app(case.path,services={'live':case.engine,'saved_example':case.engine},search_diagnostics=case.diagnostics)
    reopened=TestClient(app,base_url='http://127.0.0.1:8765');reopened.cookies.update(case.c.cookies)
    assert ok(reopened.get(target(case)))==saved
    assert raw_snapshot(case)==before and ok(case.c.get(case.ipath+'/research'))==research
    assert ok(case.c.get(case.board+'/exports?format=json'))==board
    assert case.provider.calls==calls


def test_draft_reads_and_writes_never_nest_nonreentrant_lifecycle_locks(case,monkeypatch):
    investigated(case);registry=case.app.state.registry;real_guard=registry.lifecycle_guard;thread_state=local()
    @contextmanager
    def guarded(identifier):
        assert not getattr(thread_state,'held',False), 'Nested lifecycle flock would deadlock the draft endpoint'
        thread_state.held=True
        try:
            with real_guard(identifier):yield
        finally:thread_state.held=False
    monkeypatch.setattr(registry,'lifecycle_guard',guarded)
    assert ok(case.c.get(target(case)))['version']==0
    assert ok(save(case))['version']==1
    assert ok(case.c.get(target(case)))['version']==1


@pytest.mark.parametrize('field,value',[
    ('investigation_id','foreign'),('candidate_ids',['foreign']),('original_paper_ids',['foreign']),
    ('handoff_id','foreign'),('preparation_id','foreign'),('run_id','foreign'),('inspection_id','foreign'),
    ('note_id','foreign'),('expected_note_revision_id','foreign'),('board_paper_ids',['foreign']),
    ('semantic_assessment','human_supported'),('interpretation','x'*10001),('collection_name','x'*201),
    ('confirm_inspected','false'),('acknowledge_related_paper',1),
])
def test_unknown_references_and_overbound_data_reject_without_losing_draft(prepared,field,value):
    case=prepared;prior=ok(save(case,linked(case)))
    changed=linked(case);changed[field]=value
    rejected=save(case,changed,version=1)
    assert rejected.status_code==422 and rejected.json()['error']['code']=='invalid_editor_draft'
    assert ok(case.c.get(target(case)))==prior


def test_dependencies_duplicates_and_unpaired_note_edits_reject_atomically(prepared):
    case=prepared;prior=ok(save(case,linked(case)))
    for change in (
        {'handoff_id':None},{'preparation_id':None},{'preparation_id':case.definition['preparation_id']},
        {'note_id':None},{'expected_note_revision_id':None},
        {'candidate_ids':case.handoff['selected_candidate_ids']*2},
        {'original_paper_ids':['paper-one','paper-one']},
        {'board_paper_ids':case.preparation['selected_paper_ids']*2},
        {'candidate_ids':['x']*31},
    ):
        value=linked(case);value.update(change)
        assert save(case,value,1).status_code==422
        assert ok(case.c.get(target(case)))==prior
    assert save(case,linked(case),1,expected_assessment_head='unrelated-assessment').status_code==422
    assert ok(case.c.get(target(case)))==prior


def test_real_foreign_workspace_records_cannot_be_embedded(prepared):
    case=prepared;prior=ok(save(case,linked(case)))
    other=copy(case);other.c=browser(case.app)
    other.provider.search=type(other.provider).search.__get__(other.provider)
    investigated(other);commit(other);prepare(other);retrieve(other);inspect(other)
    other.note=ok(other.c.post(other.ipath+'/notes',json=note_request(other)))
    replacements={
        'investigation_id':other.view['origin']['id'],
        'candidate_ids':[other.view['executions'][0]['candidates'][0]['id']],
        'handoff_id':other.handoff['id'],'preparation_id':other.preparation['id'],'run_id':other.run['id'],
        'inspection_id':other.inspection['id'],'note_id':other.note['id'],'expected_note_revision_id':other.note['revision_id'],
    }
    for field,value in replacements.items():
        changed=linked(case);changed[field]=value
        assert save(case,changed,1).status_code==422,field
        assert ok(case.c.get(target(case)))==prior
    assert other.c.get(target(case)).status_code==404
    assert other.c.put(target(case),json={'version':1,'data':linked(case)}).status_code==404
    # Same authorized browser, different owned workspace, still cannot reuse the investigation.
    root='/api/v1/workspaces/'+ok(case.c.post('/api/v1/workspaces',json={'request_id':'other-owned','mode':'live'}))['id']
    assert case.c.get(target(case,root=root)).status_code==404
    assert case.c.put(target(case,root=root),json={'version':0,'data':data(case)}).status_code==404


def test_unknown_scope_csrf_and_deleted_workspace_are_rejected(case):
    investigated(case)
    for identifier in ('unknown','x'*201):
        assert case.c.get(target(case,identifier)).status_code in {404,422}
        assert case.c.put(target(case,identifier),json={'version':0,'data':data(case)}).status_code in {404,422}
    ok(save(case))
    other=browser(case.app);other.cookies.update(case.c.cookies);other.headers.pop('X-CSRF-Token')
    assert other.put(target(case),json={'version':1,'data':data(case)}).status_code==403
    ok(case.c.delete(case.root))
    assert case.c.get(target(case)).status_code==404
    assert save(case,version=1).status_code==404
    with case.app.state.registry.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM web_drafts WHERE workspace_id=?',(case.root.rsplit('/',1)[-1],)).fetchone()[0]==0


def test_two_tabs_have_one_cas_winner_and_rejected_edits_are_not_overwritten(case):
    investigated(case);prior=ok(save(case))
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda text:save(case,data(case,interpretation=text),1),['Tab A human input','Tab B human input']))
    assert sorted(r.status_code for r in responses)==[200,409]
    winner=next(r.json() for r in responses if r.status_code==200)
    assert ok(case.c.get(target(case)))==winner and winner['version']==prior['version']+1
    assert save(case,data(case,interpretation='Still locally editable'),1).status_code==409
    assert ok(case.c.get(target(case)))==winner


def test_draft_keeps_older_inspection_and_note_revision_when_handoff_changes(prepared):
    case=prepared;older_inspection=deepcopy(case.inspection);older_note=deepcopy(case.note)
    next_request=handoff_request(case,request_id='second-handoff',include_original=False)
    next_request['candidates']=[{'candidate_id':case.view['executions'][0]['candidates'][1]['id'],'expected_decision_version':1}]
    commit(case,next_request);prepare(case,key='second-prep')
    value=data(case,handoff_id=case.handoff['id'],preparation_id=case.preparation['id'],
        board_paper_ids=case.preparation['selected_paper_ids'],inspection_id=older_inspection['id'],
        note_id=older_note['id'],expected_note_revision_id=older_note['revision_id'],interpretation='Unfinished revision about the older Paper B excerpt')
    saved=ok(save(case,value));assert saved['data']==value
    assert ok(case.c.get(target(case)))==saved
    ok(case.c.post(case.ipath+'/notes',json=note_request(case,request_id='newer-note',note_id=older_note['id'],expected_revision_id=older_note['revision_id'],interpretation='Other saved revision')))
    # Drafts retain historical editable intent; only explicit note submission checks the current note head.
    assert ok(case.c.get(target(case)))==saved
    assert ok(save(case,value,1))['version']==2
    assert case.c.post(case.ipath+'/notes',json=note_request(case,request_id='stale-draft-submit',note_id=older_note['id'],expected_revision_id=older_note['revision_id'])).status_code==409


def test_delete_after_record_read_cannot_resurrect_draft(case,monkeypatch):
    from src.mvp.investigation_research import InvestigationResearchService
    investigated(case);ok(save(case));entered,release=Event(),Event();real_state=InvestigationResearchService.state
    def paused(self,handle,identifier):
        result=real_state(self,handle,identifier);entered.set();assert release.wait(5)
        return result
    monkeypatch.setattr(InvestigationResearchService,'state',paused)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(save,case,data(case,interpretation='Racing input'),1)
        assert entered.wait(5)
        try:ok(case.c.delete(case.root))
        finally:release.set()
        assert pending.result(timeout=5).status_code==404
    with case.app.state.registry.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM web_drafts WHERE workspace_id=?',(case.root.rsplit('/',1)[-1],)).fetchone()[0]==0


def test_draft_byte_quota_rejection_preserves_previous_input(case):
    investigated(case);prior=ok(save(case));case.app.state.registry.max_draft_bytes=300
    assert save(case,data(case,interpretation='x'*1000),1).json()['error']['code']=='draft_limit'
    assert ok(case.c.get(target(case)))==prior


def test_same_workspace_different_investigation_cannot_reuse_research_records(prepared):
    case=prepared
    board=ok(case.c.post(case.root+'/boards',json={'request_id':'another-board','preparation_id':case.preparation['id'],
        'paper_ids':['candidate-b'],'question':'Separate inquiry','fields':[{'id':'related','label':'Related','subquestion':'Separate field'}]}))['definition']
    investigation=ok(case.c.post(case.root+'/investigations',json={'request_id':'another-investigation','board_id':board['board_id'],
        'expected_board_revision_id':board['revision_id'],'paper_id':'candidate-b','field_id':'related','expected_draft_version':0,'reason':'Separate question'}))
    identifier=investigation['origin']['id'];path=target(case,identifier)
    initial={'investigation_id':identifier,'interpretation':'Independent unfinished input'}
    prior=ok(case.c.put(path,json={'version':0,'data':initial}))
    for change in ({'handoff_id':case.handoff['id']},{'inspection_id':case.inspection['id']},
        {'candidate_ids':case.handoff['selected_candidate_ids']},
        {'note_id':case.note['id'],'expected_note_revision_id':case.note['revision_id']}):
        assert case.c.put(path,json={'version':1,'data':{**initial,**change}}).status_code==422
        assert ok(case.c.get(path))==prior


def test_candidate_decision_change_preserves_editable_intent_but_not_handoff_authority(case):
    investigated(case)
    candidate=case.view['executions'][0]['candidates'][0]
    value=data(case,candidate_ids=[candidate['id']]);prior=ok(save(case,value))
    ok(case.c.post(case.ipath+'/decisions',json={'request_id':'later-dismissal','candidate_id':candidate['id'],'expected_version':1,'decision':'dismiss'}))
    assert ok(case.c.get(target(case)))==prior
    assert ok(save(case,value,1))['data']==value
    request=handoff_request(case)
    rejected=case.c.post(case.ipath+'/handoff-preview',json=request)
    assert rejected.json()['error']['code']=='investigation_shortlist_required'
    assert ok(case.c.get(case.ipath+'/research'))['handoffs']==[]
