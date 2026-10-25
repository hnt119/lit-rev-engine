"""Independent packet safety checks. Synthetic adapter output is not quality evidence."""
from copy import deepcopy
import pytest
from test_hybrid_retrieval_independent import flow, post, board
from src.mvp.adapters import hybrid_packets as packets
from src.mvp.board_contracts import BoardRevision
from src.mvp.contracts import canonical, digest
from src.mvp.hybrid_app_contracts import HybridBoardCandidates
from src.mvp.ports import MvpError


def fixture_packet(flow):
    c=flow;definition,path,scope=board(c)
    post(c,'/hybrid-index',{**c.payload,'board_context':scope})
    result=c.client.post(path+'/candidates',json={'request_id':'packet-evidence','expected_revision_id':definition['revision_id'],
        'paper_id':scope['paper_id'],'field_id':'age','top_k':3})
    assert result.status_code==200,result.text
    return BoardRevision.model_validate(definition),HybridBoardCandidates.model_validate(result.json()),scope['paper_id']


def duplicate_field(definition,run):
    second=definition.fields[0].model_copy(update={'id':'second','revision_id':'field-second'})
    profile=deepcopy(definition.retrieval_profile)
    profile['requirements_by_field']['second']=deepcopy(profile['requirements_by_field']['age'])
    profile_hash=digest(profile)
    definition=definition.model_copy(update={'fields':[*definition.fields,second],
        'retrieval_profile':profile,'retrieval_profile_sha256':profile_hash})
    first=run.model_copy(update={'retrieval_profile':profile,'retrieval_profile_sha256':profile_hash})
    other=first.model_copy(update={'id':'second-candidate-run','field_id':'second','field_revision_id':second.revision_id})
    return definition,first,other


def test_exact_unicode_negative_dense_candidates_share_one_packet_anchor(flow):
    definition,run,paper=fixture_packet(flow)
    assert run.result.candidates[0].score<0
    definition,first,second=duplicate_field(definition,run)
    packet=packets.build_hybrid_packet(definition,paper,[first,second])
    assert packet.schema_version=='mvp.hybrid-proposal-packet.v1'
    assert len(packet.evidence)==1
    assert packet.evidence[0].field_ids==['age','second']
    assert all(field.evidence_ids==[packet.evidence[0].evidence_id] for field in packet.fields)
    assert packet.evidence[0].reference.quote==run.result.candidates[0].reference.quote
    assert '🧬' in packet.evidence[0].reference.quote and 'e\u0301' in packet.evidence[0].reference.quote
    assert packet.evidence_characters==len(packet.evidence[0].reference.quote)
    assert len(canonical(packet.model_dump(mode='json')).encode())<=packets.MAX_PACKET_BYTES
    assert all(field.meaning=='candidate_association_not_semantic_coverage' for field in packet.fields)


@pytest.mark.parametrize('key,value',[('board_id','wrong-board'),('board_revision_id','wrong-revision'),
    ('field_revision_id','wrong-field-revision'),('preparation_id','wrong-preparation'),
    ('source_manifest_sha256','0'*64),('retrieval_profile_sha256','0'*64)])
def test_mismatched_packet_receipt_binding_fails(flow,key,value):
    definition,run,paper=fixture_packet(flow)
    with pytest.raises(MvpError) as error:packets.build_hybrid_packet(definition,paper,[run.model_copy(update={key:value})])
    assert error.value.code=='proposal_invalid_evidence'


@pytest.mark.parametrize('key,value',[('paper_id','wrong-paper'),('source_id','wrong-source'),
    ('source_version','wrong-version'),('source_sha256','0'*64),('blocks_sha256','0'*64)])
def test_wrong_source_reference_rejected_before_packet(flow,key,value):
    definition,run,paper=fixture_packet(flow)
    candidate=run.result.candidates[0]
    candidate=candidate.model_copy(update={'reference':candidate.reference.model_copy(update={key:value})})
    changed=run.model_copy(update={'result':run.result.model_copy(update={'candidates':[candidate]})})
    with pytest.raises(MvpError) as error:packets.build_hybrid_packet(definition,paper,[changed])
    assert error.value.code=='proposal_invalid_evidence'


def test_primary_field_coverage_over_budget_is_explicit_failure(flow,monkeypatch):
    definition,run,paper=fixture_packet(flow)
    monkeypatch.setattr(packets,'MAX_PACKET_CHARACTERS',len(run.result.candidates[0].reference.quote)-1)
    with pytest.raises(MvpError) as error:packets.build_hybrid_packet(definition,paper,[run])
    assert error.value.code=='proposal_context_limit'


def test_extra_packet_candidate_is_omitted_whole_at_budget(flow,monkeypatch):
    definition,run,paper=fixture_packet(flow)
    original=run.result.candidates[0];ref=original.reference
    # Two distinct exact substrings from the already checked canonical block.
    first_ref=ref.model_copy(update={'id':'short-first','end':ref.start+10,'quote':ref.quote[:10]})
    second_ref=ref.model_copy(update={'id':'short-second','start':ref.start+10,'end':ref.start+20,'quote':ref.quote[10:20]})
    first=original.model_copy(update={'candidate_id':'first','rank':1,'reference':first_ref,
        'omitted_before':first_ref.start,'omitted_after':original.total_block_characters-first_ref.end})
    second=original.model_copy(update={'candidate_id':'second','rank':2,'reference':second_ref,
        'omitted_before':second_ref.start,'omitted_after':original.total_block_characters-second_ref.end})
    changed=run.model_copy(update={'result':run.result.model_copy(update={'candidates':[first,second],'returned_count':2})})
    monkeypatch.setattr(packets,'MAX_PACKET_CHARACTERS',10)
    packet=packets.build_hybrid_packet(definition,paper,[changed])
    assert len(packet.evidence)==1 and packet.evidence[0].reference==first_ref
    assert packet.evidence_characters==10
    assert packet.omitted_evidence==packet.fields[0].omitted_evidence==1


def test_packet_refuses_unapproved_component_query_change(flow):
    definition,run,paper=fixture_packet(flow)
    changed=run.model_copy(update={'result':run.result.model_copy(update={'requirements':[
        run.result.requirements[0].model_copy(update={'query':'silently rewritten question'})]})})
    with pytest.raises(MvpError) as error:packets.build_hybrid_packet(definition,paper,[changed])
    assert error.value.code=='proposal_invalid_evidence'
