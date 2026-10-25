"""Explicit span packet projection; all generation is a software-only mock."""
import pytest

from test_boards import case
from test_span_boards import profiled
from test_proposals import Adapter
from src.mvp.adapters.span_packets import build_span_packet
from src.mvp.board_contracts import BoardCandidatesRequest
from src.mvp.cell_proposals import CellProposalService
from src.mvp.contracts import Block, PrepareSourcesRequest, PreparedSource, digest
from src.mvp.ports import MvpError
from src.mvp.proposal_contracts import ProposalGenerateRequest
from src.mvp.span_board_contracts import SpanBoardCandidates
from pydantic import ValidationError


def candidates(case, board):
    boards, handle, *_ = case
    return [boards.candidates('test', handle, board.definition.board_id, BoardCandidatesRequest(
        request_id='packet:'+field.id, expected_revision_id=board.definition.revision_id,
        paper_id=board.definition.paper_ids[0], field_id=field.id)) for field in board.definition.fields]


def test_primary_anchor_projection_deduplicates_fields_without_changing_packet_schema_or_questions(case):
    board = profiled(case)
    runs = candidates(case, board)
    packet = build_span_packet(board.definition, board.definition.paper_ids[0], runs)
    assert packet.schema_version == 'mvp.proposal-packet.v1'
    assert len(packet.evidence) == 1
    assert set(packet.evidence[0].field_ids) == {field.id for field in board.definition.fields}
    assert [field.subquestion for field in packet.fields] == [field.subquestion for field in board.definition.fields]
    assert all(field.evidence_ids == [packet.evidence[0].evidence_id] for field in packet.fields)
    assert {field.candidate_run_id for field in packet.fields} == {run.id for run in runs}
    assert packet.context_scope == 'retrieved_context_only'
    assert packet.evidence[0].reference == runs[0].candidates[0].reference


@pytest.mark.parametrize('change', ['wrong_paper', 'wrong_component', 'wrong_quotation'])
def test_span_packet_rejects_mismatched_paper_component_or_quotation_metadata(case, change):
    board = profiled(case)
    runs = candidates(case, board)
    value = runs[0]
    if change == 'wrong_paper':
        changed_ref=value.candidates[0].reference.model_copy(update={'paper_id':'another-paper'})
        value=value.model_copy(update={'candidates':[value.candidates[0].model_copy(update={'reference':changed_ref}),*value.candidates[1:]]})
    elif change == 'wrong_component':
        value=value.model_copy(update={'requirements':[value.requirements[0].model_copy(update={'query':'unapproved new retrieval input'}),*value.requirements[1:]]})
    else:
        changed_ref=value.candidates[0].reference.model_copy(update={'quote':value.candidates[0].reference.quote+'unbound text'})
        value=value.model_copy(update={'candidates':[value.candidates[0].model_copy(update={'reference':changed_ref}),*value.candidates[1:]]})
    with pytest.raises(MvpError) as error:
        build_span_packet(board.definition, board.definition.paper_ids[0], [value, *runs[1:]])
    assert error.value.code == 'proposal_invalid_evidence'


def test_round_robin_reserves_later_fields_before_filling_earlier_fields(case, monkeypatch):
    boards, handle, engine, _, _, request, _ = case
    def prepare(paper):
        blocks = [Block(id=term+str(index), ordinal=order,
            text=term+' '+('Neutral data. '*75), locator={'type':'paragraph'})
            for order,(term,index) in enumerate(( (term,index) for term in ('diet','cohort','methods') for index in range(3)),1)]
        return PreparedSource(paper_id=paper.id,status='abstract_only',source_type='abstract',
            provider='software-fixture',source_url='',blocks=blocks,blocks_sha256=digest([block.model_dump() for block in blocks]))
    engine._sources.prepare = prepare
    preparation = engine.prepare_sources(handle,PrepareSourcesRequest(request_id='packet-preparation',
        search_id=engine.get_workspace(handle).searches[0].id,paper_ids=request.paper_ids))
    board = profiled(case, preparation_id=preparation.id)
    runs = candidates(case,board)
    assert all(len(run.candidates)==3 for run in runs)
    monkeypatch.setattr('src.mvp.adapters.span_packets.MAX_PACKET_CHARACTERS',4000)
    packet = build_span_packet(board.definition,board.definition.paper_ids[0],runs)
    assert len(packet.evidence)==3 and packet.evidence_characters<=4000
    assert all(len(field.evidence_ids)==1 and field.omitted_evidence==2 for field in packet.fields)
    assert packet.omitted_evidence==6


def test_span_proposals_reuse_unchanged_mock_adapter_and_require_separate_human_review(case):
    board = profiled(case)
    boards,handle,*_ = case
    adapter = Adapter()
    service = CellProposalService(boards,adapter)
    run = service.generate('test',handle,board.definition.board_id,ProposalGenerateRequest(
        request_id='span-mock-run',expected_revision_id=board.definition.revision_id,
        paper_ids=board.definition.paper_ids,field_ids=[field.id for field in board.definition.fields]))
    assert run.state=='succeeded' and len(run.proposals)==9 and len(adapter.calls)==3
    assert all(packet.schema_version=='mvp.proposal-packet.v1' for packet,_ in adapter.calls)
    assert run.retrieval_profile_sha256==board.definition.retrieval_profile_sha256
    for proposal in run.proposals:
        packet=next(packet for packet in run.packets if packet.paper_id==proposal.paper_id)
        field=next(field for field in board.definition.fields if field.id==proposal.field_id)
        assert proposal.retrieval_input_sha256==digest({'field':field.model_dump(mode='json'),
            'packet':packet.model_dump(mode='json'),'retrieval_profile_sha256':board.definition.retrieval_profile_sha256})
    assert all(cell.head is None and cell.draft_version==0 for cell in boards.view('test',handle,board.definition.board_id).cells)
    assert run.model_profile_sha256==digest(adapter.profile)


def test_initial_field_coverage_budget_failure_calls_no_model_and_changes_no_cells(case,monkeypatch):
    board=profiled(case)
    boards,handle,*_=case
    adapter=Adapter()
    service=CellProposalService(boards,adapter)
    monkeypatch.setattr('src.mvp.adapters.span_packets.MAX_PACKET_BYTES',1)
    run=service.generate('test',handle,board.definition.board_id,ProposalGenerateRequest(
        request_id='span-over-budget',expected_revision_id=board.definition.revision_id,
        paper_ids=board.definition.paper_ids[:1],field_ids=[field.id for field in board.definition.fields]))
    assert run.state=='failed' and run.failure_code=='proposal_context_limit'
    assert adapter.calls==[] and run.proposals==[]
    assert all(cell.head is None and cell.draft_version==0 for cell in boards.view('test',handle,board.definition.board_id).cells)


@pytest.mark.parametrize('change',['matched_blocks','partial_blocks','blank_blocks','token_budget','duplicate_anchor','elapsed','requirement_count'])
def test_receipt_and_packet_reject_impossible_metadata_and_understated_exact_quote_budgets(case,change):
    board=profiled(case)
    runs=candidates(case,board)
    data=runs[0].model_dump(mode='json')
    if change=='matched_blocks':
        data['matched_blocks']=0
    elif change=='partial_blocks':
        data['partially_indexed_blocks']=data['indexed_blocks']+1
    elif change=='blank_blocks':
        data['skipped_blank_blocks']=data['unindexed_source_blocks']+1
    elif change=='token_budget':
        assert data['candidates'][0]['budget_tokens']>1
        data['delivered_budget_tokens']-=data['candidates'][0]['budget_tokens']-1
        data['candidates'][0]['budget_tokens']=1
    elif change=='duplicate_anchor':
        data['candidates'].append({**data['candidates'][0],'rank':2})
        data['returned_count']+=1
        data['delivered_budget_tokens']+=data['candidates'][0]['budget_tokens']
        data['delivered_characters']+=len(data['candidates'][0]['reference']['quote'])
        data['matched_windows']+=1
        data['indexed_windows']+=1
        data['requirement_matches'][0]['matched_windows']+=1
        data['requirement_matches'][0]['selected_windows']+=1
    elif change=='elapsed':
        data['elapsed_seconds']=float('inf')
    else:
        data['requirement_matches'][0]['matched_windows']=data['matched_windows']+1
    with pytest.raises(ValidationError):
        SpanBoardCandidates.model_validate(data)
    # model_copy/construct deliberately bypass validation: the packet boundary
    # must revalidate even a forged in-process adapter value.
    updates={key:value for key,value in data.items() if key not in {'candidates','requirements','requirement_matches'}}
    updates['candidates']=[runs[0].candidates[0].model_copy(update={'rank':value['rank'],
        'budget_tokens':value['budget_tokens']}) for value in data['candidates']]
    updates['requirement_matches']=[old.model_copy(update=new) for old,new in zip(runs[0].requirement_matches,data['requirement_matches'])]
    forged=runs[0].model_copy(update=updates)
    with pytest.raises(MvpError) as error:
        build_span_packet(board.definition,board.definition.paper_ids[0],[forged,*runs[1:]])
    assert error.value.code=='proposal_invalid_evidence'
