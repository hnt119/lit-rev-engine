"""Independent pinned-profile/lifecycle checks; synthetic model methods only."""
from copy import deepcopy
import json
from test_hybrid_retrieval_independent import flow, post, board, search
from src.mvp.hybrid_contracts import QWEN_PROFILE


def test_bound_board_cannot_use_new_model_manifest_under_same_profile_id(flow):
    c=flow;definition,path,scope=board(c)
    c.packs.adapters[QWEN_PROFILE].manifest['revision']='changed-immutable-revision'
    response=c.client.post(c.base+'/hybrid-index',json={**c.payload,'board_context':scope})
    assert response.status_code in {409,422},response.text
    assert not any(kind=='documents' for kind,_ in c.packs.adapters[QWEN_PROFILE].calls)


def test_bound_board_device_cannot_change_without_definition_revision(flow):
    c=flow;definition,path,scope=board(c)
    assert definition['retrieval_profile']['device']=='cpu'
    response=c.client.post(c.base+'/hybrid-index',json={**c.payload,'board_context':scope,'device':'mps'})
    assert response.status_code in {409,422},response.text
    assert not any(kind=='documents' for kind,_ in c.packs.adapters[QWEN_PROFILE].calls)


def test_saved_exact_inspector_remains_readable_after_new_manifest_installed(flow):
    c=flow;definition,path,scope=board(c)
    post(c,'/hybrid-index',{**c.payload,'board_context':scope})
    run=search(c,board_context=scope)
    candidate=run['result']['candidates'][0]
    c.packs.adapters[QWEN_PROFILE].manifest['revision']='newly-installed-revision'
    c.packs.installed=False
    calls=deepcopy(c.packs.adapters[QWEN_PROFILE].calls)
    assert c.client.get(c.base+'/hybrid-runs/'+run['id']).json()==run
    result=c.client.get(c.base+'/hybrid-runs/'+run['id']+'/candidates/'+candidate['candidate_id']+'/context')
    assert result.status_code==200,result.text
    assert result.json()['reference']==candidate['reference']
    assert c.packs.adapters[QWEN_PROFILE].calls==calls


def test_cancel_after_reranker_forward_has_no_saved_success(flow):
    c=flow;post(c,'/hybrid-index',c.payload)
    def cancel(stage):
        if stage=='rerank':
            result=c.client.post(c.base+'/hybrid-jobs/cancelled-run/cancel')
            assert result.status_code==200,result.text
    c.packs.adapters[QWEN_PROFILE].hook=cancel
    result=c.client.post(c.base+'/hybrid-runs',json={**c.payload,'request_id':'cancelled-run','question':'paraphrase','top_k':5})
    assert result.status_code!=200,result.text
    assert c.client.get(c.base+'/hybrid-runs').json()['runs']==[]
    assert c.client.get(c.base+'/hybrid-jobs/cancelled-run').json()['state']=='cancelled'


def test_delete_during_reranker_forward_prevents_run_and_history_publication(flow):
    c=flow;post(c,'/hybrid-index',c.payload)
    c.packs.adapters[QWEN_PROFILE].hook=lambda stage:c.client.delete(c.base) if stage=='rerank' else None
    result=c.client.post(c.base+'/hybrid-runs',json={**c.payload,'request_id':'deleted-during-query','question':'paraphrase','top_k':5})
    assert result.status_code==503 and result.json()['error']['code']=='hybrid_cancelled',result.text
    with c.app.state.hybrid_retrieval.db() as db:
        assert db.execute('SELECT COUNT(*) FROM hybrid_runs WHERE workspace_id=?',(c.workspace['id'],)).fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM hybrid_jobs_v1 WHERE workspace_id=?',(c.workspace['id'],)).fetchone()[0]==0


def test_board_revision_during_rerank_rejects_late_candidates(flow):
    c=flow;definition,path,scope=board(c)
    post(c,'/hybrid-index',{**c.payload,'board_context':scope})
    def revise(stage):
        if stage=='rerank':
            result=c.client.post(path+'/revisions',json={'request_id':'revise','schema_version':'mvp.board-profile-request.v2',
                'retrieval_profile_id':QWEN_PROFILE,'expected_revision_id':definition['revision_id'],
                'preparation_id':c.prep['id'],'question':'Revised comparison question','paper_ids':definition['paper_ids'],
                'fields':[{'id':'age','label':'Age','subquestion':'participant age'}]})
            assert result.status_code==200,result.text
    c.packs.adapters[QWEN_PROFILE].hook=revise
    result=c.client.post(path+'/candidates',json={'request_id':'stale-cell','expected_revision_id':definition['revision_id'],
        'paper_id':scope['paper_id'],'field_id':'age','top_k':3})
    assert result.status_code==409,result.text
    assert c.client.get(c.base+'/hybrid-runs').json()['runs']==[]
    with c.app.state.boards.store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM board_candidates').fetchone()[0]==0


def test_hybrid_proposal_packet_keeps_exact_negative_score_candidate_evidence(flow):
    from src.mvp.adapters.hybrid_packets import build_hybrid_packet
    from src.mvp.board_contracts import BoardRevision
    from src.mvp.hybrid_app_contracts import HybridBoardCandidates
    c=flow;definition,path,scope=board(c)
    post(c,'/hybrid-index',{**c.payload,'board_context':scope})
    result=c.client.post(path+'/candidates',json={'request_id':'packet-cell','expected_revision_id':definition['revision_id'],
        'paper_id':scope['paper_id'],'field_id':'age','top_k':3})
    assert result.status_code==200,result.text
    candidates=HybridBoardCandidates.model_validate(result.json())
    assert all(candidate.score<0 for candidate in candidates.result.candidates)
    packet=build_hybrid_packet(BoardRevision.model_validate(definition),scope['paper_id'],[candidates])
    assert packet.schema_version=='mvp.hybrid-proposal-packet.v1'
    assert packet.evidence
    assert packet.evidence[0].reference.quote==candidates.result.candidates[0].reference.quote
    assert packet.evidence_characters==sum(len(e.reference.quote) for e in packet.evidence)
    assert packet.evidence_characters<=12000
    assert all(field.component_ids==['field'] for field in packet.fields)


def _mock_proposal_output(packet):
    from src.mvp.proposal_contracts import ProposalGenerationResult,ProposalUsage
    evidence={item.evidence_id:item for item in packet.evidence}
    cells=[]
    for field in packet.fields:
        identifier=field.evidence_ids[0] if field.evidence_ids else None
        cells.append({'field_id':field.field_id,'value':'SYNTHETIC suggestion; human review required' if identifier else None,
            'references':[{'evidence_id':identifier,'quote':evidence[identifier].reference.quote}] if identifier else [],
            'reason':'Software test output is not a support judgment','missing_information':'' if identifier else 'No retained evidence',
            'context_scope':'retrieved_context_only'})
    return ProposalGenerationResult(output_text=json.dumps({'cells':cells}),usage=ProposalUsage(input_tokens=10,output_tokens=10,total_tokens=20,measured=True))


def _configured_mock_proposals(c,monkeypatch):
    from src.mvp.adapters.cell_generation import ConfiguredCellGenerationAdapter
    calls=[]
    def generate(adapter,packet,*,timeout_seconds):
        calls.append((packet,timeout_seconds))
        return _mock_proposal_output(packet)
    monkeypatch.setattr(ConfiguredCellGenerationAdapter,'generate',generate)
    settings=c.client.get('/api/v1/settings').json()
    preferences=deepcopy(settings['preferences'])
    preferences['ai'].update(provider='local',model='synthetic-local-fixture',model_revision='not-a-real-model.v1',proposals_enabled=True)
    saved=c.client.put('/api/v1/settings',json={'expected_revision':settings['revision'],'preferences':preferences})
    assert saved.status_code==200,saved.text
    return calls,saved.json()['revision']


def test_hybrid_mocked_proposal_consent_generation_and_adoption_preserve_manual_review(flow,monkeypatch):
    c=flow;definition,path,scope=board(c)
    post(c,'/hybrid-index',{**c.payload,'board_context':scope})
    response=c.client.post(path+'/candidates',json={'request_id':'explicit-proposal-evidence','expected_revision_id':definition['revision_id'],'paper_id':scope['paper_id'],'field_id':'age','top_k':3})
    assert response.status_code==200,response.text
    # Saved evidence remains sufficient for proposals even after model removal.
    c.packs.installed=False
    retrieval_calls=deepcopy(c.packs.adapters[QWEN_PROFILE].calls)
    index_calls=sum(kind=='documents' for kind,_ in c.packs.adapters[QWEN_PROFILE].calls)
    generation,revision=_configured_mock_proposals(c,monkeypatch)
    request={'request_id':'hybrid-proposal','expected_revision_id':definition['revision_id'],
        'paper_ids':[scope['paper_id']],'field_ids':['age'],'settings_revision':revision}
    prepared=c.client.post(path+'/prepare-generation',json=request)
    assert prepared.status_code==200,prepared.text
    assert prepared.json()['max_calls']==1 and generation==[]
    generated=c.client.post(path+'/proposal-runs',json={**request,'consent_id':prepared.json()['consent_id']})
    assert generated.status_code==200,generated.text
    run=generated.json();assert run['state']=='succeeded',run
    assert len(generation)==1
    assert c.packs.adapters[QWEN_PROFILE].calls==retrieval_calls
    packet=generation[0][0]
    assert packet.schema_version=='mvp.hybrid-proposal-packet.v1'
    assert all(field.meaning=='candidate_association_not_semantic_coverage' for field in packet.fields)
    assert sum(kind=='documents' for kind,_ in c.packs.adapters[QWEN_PROFILE].calls)==index_calls
    proposal=run['proposals'][0];assert proposal['semantic_assessment']=='unassessed'
    assert proposal['review_state']=='ai_suggestion_needs_review_not_independently_verified'
    reference=proposal['references'][0]
    exact=c.client.get(path+'/proposals/'+proposal['id']+'/references/'+reference['id']+'/context')
    assert exact.status_code==200 and exact.json()['reference']==reference
    replay=c.client.post(path+'/proposal-runs',json={**request,'consent_id':prepared.json()['consent_id']})
    assert replay.status_code==422 and len(generation)==1
    adopted=c.client.post(path+'/proposals/'+proposal['id']+'/adopt',json={'request_id':'adopt-hybrid',
        'expected_revision_id':definition['revision_id'],'draft_version':0,'value':'SYNTHETIC edited value','reason':'Software adoption test'})
    assert adopted.status_code==200,adopted.text
    draft=adopted.json()
    assert draft['data']['semantic_assessment']=='unassessed' and draft['data']['inspected_ranges']==[]
    assert c.client.get(path).json()['cells'][0]['head'] is None
    attempted=c.client.post(path+'/cell-revisions',json={'request_id':'not-human-reviewed',
        'expected_revision_id':definition['revision_id'],'paper_id':scope['paper_id'],'field_id':'age','draft_version':draft['version']})
    assert attempted.status_code==422


def test_prepared_hybrid_consent_rejects_changed_exact_packet_before_generator(flow,monkeypatch):
    c=flow;definition,path,scope=board(c)
    post(c,'/hybrid-index',{**c.payload,'board_context':scope})
    response=c.client.post(path+'/candidates',json={'request_id':'explicit-proposal-evidence','expected_revision_id':definition['revision_id'],'paper_id':scope['paper_id'],'field_id':'age','top_k':3})
    assert response.status_code==200,response.text
    generation,revision=_configured_mock_proposals(c,monkeypatch)
    request={'request_id':'changing-packet','expected_revision_id':definition['revision_id'],
        'paper_ids':[scope['paper_id']],'field_ids':['age'],'settings_revision':revision}
    prepared=c.client.post(path+'/prepare-generation',json=request)
    assert prepared.status_code==200,prepared.text
    original=c.app.state.boards.saved_hybrid_candidates
    def changed_selection(*args,**kwargs):
        run=original(*args,**kwargs)
        # A valid but different bounded selection simulates changed retrieval
        # behavior between consent and execution, preserving the source snapshot.
        result=run.result.model_copy(update={'candidates':[],'returned_count':0,
            'component_receipts':[v.model_copy(update={'selected_candidates':0}) for v in run.result.component_receipts]})
        return run.model_copy(update={'result':result})
    monkeypatch.setattr(c.app.state.boards,'saved_hybrid_candidates',changed_selection)
    attempted=c.client.post(path+'/proposal-runs',json={**request,'consent_id':prepared.json()['consent_id']})
    assert attempted.status_code==200,attempted.text
    assert attempted.json()['state']=='failed' and attempted.json()['failure_code']=='proposal_stale_inputs'
    assert generation==[]


def test_hybrid_retrieval_deadline_expires_before_generation_without_extra_calls(flow,monkeypatch):
    import src.mvp.cell_proposals as module
    c=flow;definition,path,scope=board(c)
    post(c,'/hybrid-index',{**c.payload,'board_context':scope})
    response=c.client.post(path+'/candidates',json={'request_id':'explicit-proposal-evidence','expected_revision_id':definition['revision_id'],'paper_id':scope['paper_id'],'field_id':'age','top_k':3})
    assert response.status_code==200,response.text
    class Generator:
        enabled=True;profile={'provider':'synthetic','model':'mock','revision':'fixture.v1'}
        def __init__(self):self.calls=[]
        def generate(self,packet,*,timeout_seconds):self.calls.append(packet);return _mock_proposal_output(packet)
    adapter=Generator()
    # The complete preparation/retrieval interval is part of the existing
    # generation operation deadline. Make that interval deterministically expire.
    clock=[0.]
    real=c.app.state.boards.saved_hybrid_candidates
    def slow_retrieval(*args,**kwargs):
        result=real(*args,**kwargs);clock[0]=1.;return result
    monkeypatch.setattr(c.app.state.boards,'saved_hybrid_candidates',slow_retrieval)
    monkeypatch.setattr(module.time,'monotonic',lambda:clock[0])
    # Call through the already-wired HTTP service after swapping only its
    # test-owned budget/adapter; preserves route ownership/CSRF checks.
    proposals=c.app.state.proposals
    proposals.adapter=adapter;proposals.max_runtime_seconds=.01
    response=c.client.post(path+'/proposal-runs',json={'request_id':'bounded-no-generation',
        'expected_revision_id':definition['revision_id'],'paper_ids':[scope['paper_id']],'field_ids':['age']})
    assert response.status_code==200,response.text
    assert response.json()['state']=='failed' and response.json()['failure_code']=='proposal_timeout'
    assert adapter.calls==[]


def test_hybrid_prepare_requires_explicit_saved_cell_candidates_without_neural_calls(flow,monkeypatch):
    c=flow;definition,path,scope=board(c)
    generation,revision=_configured_mock_proposals(c,monkeypatch)
    response=c.client.post(path+'/prepare-generation',json={'request_id':'no-hidden-retrieval',
        'expected_revision_id':definition['revision_id'],'paper_ids':[scope['paper_id']],
        'field_ids':['age'],'settings_revision':revision})
    assert response.status_code==422,response.text
    assert response.json()['error']['code']=='hybrid_candidates_required'
    assert generation==[] and c.packs.adapters[QWEN_PROFILE].calls==[]
    with c.app.state.boards.store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM board_candidates').fetchone()[0]==0
