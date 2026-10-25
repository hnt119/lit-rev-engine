"""Independent board capacity contracts, separate from inference budgets."""
import pytest
from pydantic import ValidationError

from src.mvp.board_contracts import BoardCreateRequest, BoardLimits, BoardReviseRequest, BoardSummary
from src.mvp.limits import MAX_BOARD_CELLS, MAX_BOARD_FIELDS, MAX_BOARD_PAPERS, public_limits
from src.mvp.proposal_contracts import ProposalCapability
from src.mvp.span_board_contracts import ProfiledBoardCreateRequest, ProfiledBoardReviseRequest


def payload(papers=30, fields=6):
    return {'request_id': 'board', 'preparation_id': 'preparation', 'question': 'Synthetic capacity question',
        'paper_ids': [f'paper-{index}' for index in range(papers)],
        'fields': [{'id': f'field-{index}', 'label': f'Field {index}', 'subquestion': f'Question {index}'} for index in range(fields)]}


@pytest.mark.parametrize('model', [BoardCreateRequest, BoardReviseRequest, ProfiledBoardCreateRequest, ProfiledBoardReviseRequest])
@pytest.mark.parametrize('papers', [1, 10, 11, 29, 30])
def test_create_and_revise_accept_thirty_by_six_without_changing_profiles(model, papers):
    body = payload(papers)
    if model in (BoardReviseRequest, ProfiledBoardReviseRequest):
        body['expected_revision_id'] = 'revision'
    if model in (ProfiledBoardCreateRequest, ProfiledBoardReviseRequest):
        body['retrieval_profile_id'] = 'lexical_spans_v1'
    value = model.model_validate(body)
    assert len(value.paper_ids) * len(value.fields) == papers * 6


@pytest.mark.parametrize('model', [BoardCreateRequest, BoardReviseRequest, ProfiledBoardCreateRequest, ProfiledBoardReviseRequest])
@pytest.mark.parametrize('papers,fields', [(31, 6), (30, 7), (0, 6), (30, 0)])
def test_all_board_request_forms_reject_capacity_overflow(model, papers, fields):
    body = payload(papers, fields)
    if model in (BoardReviseRequest, ProfiledBoardReviseRequest):
        body['expected_revision_id'] = 'revision'
    if model in (ProfiledBoardCreateRequest, ProfiledBoardReviseRequest):
        body['retrieval_profile_id'] = 'lexical_spans_v1'
    with pytest.raises(ValidationError):
        model.model_validate(body)


def test_board_limits_are_central_and_proposal_bounds_remain_independent():
    assert (MAX_BOARD_PAPERS, MAX_BOARD_FIELDS, MAX_BOARD_CELLS) == (30, 6, 180)
    board, limits, proposal = BoardLimits(), public_limits(), ProposalCapability()
    assert (board.max_papers, board.max_fields, board.max_cells) == (30, 6, 180)
    assert (limits['max_board_papers'], limits['max_board_fields'], limits['max_board_cells']) == (30, 6, 180)
    assert limits['max_synchronous_prepared_sources'] == 10
    assert limits['max_passages'] == 30 and limits['default_passages'] == 5
    assert (proposal.max_papers, proposal.max_cells, proposal.max_calls) == (3, 9, 3)
    assert (board.max_references, board.max_inspector_characters, board.max_workspace_bytes) == (5, 4000, 32 * 1024 * 1024)


def test_old_summary_contract_remains_readable_with_additive_defaults():
    legacy = {'board_id': 'board', 'revision_id': 'revision', 'question': 'Retained question',
        'paper_count': 10, 'field_count': 6, 'created_at': '2026-10-22T00:00:00+00:00'}
    value = BoardSummary.model_validate(legacy)
    assert value.preparation_id is None and value.paper_ids == []
    assert value.model_dump(exclude={'preparation_id', 'paper_ids'}) == legacy


def test_expansion_preserves_unique_paper_and_field_requirements():
    for key in ('paper_ids', 'fields'):
        body = payload()
        body[key][-1] = body[key][0]
        with pytest.raises(ValidationError):
            BoardCreateRequest.model_validate(body)
