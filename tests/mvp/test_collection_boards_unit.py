"""Collection board lifecycle contracts; inference is a software mock only."""
import json

import pytest

from test_collection_preparation_unit import case_for
from src.mvp.adapters.board_storage import BoardStore
from src.mvp.board_contracts import (
    BoardCandidatesRequest, BoardCreateRequest, BoardFieldInput, BoardRevision,
    BoardReviseRequest, BoardView, CollectionBoardExport, CollectionBoardRevision,
)
from src.mvp.cell_proposals import CellProposalService
from src.mvp.contracts import PrepareSourcesRequest, SearchRequest
from src.mvp.evidence_board import EvidenceBoardService
from src.mvp.ports import MvpError
from src.mvp.preparation_jobs import PreparationWorker
from src.mvp.proposal_contracts import ProposalGenerateRequest, ProposalGenerationResult

MODE = 'saved_example'


def prepare_collection(case, request=None):
    job = case.jobs.submit(MODE, case.handle, request or case.request).job
    assert PreparationWorker(case.jobs, modes=(MODE,)).run_once()
    assert case.jobs.job(MODE, case.handle, job.id).status == 'succeeded'
    return case.engine.get_workspace(case.handle).preparations[-1]


def board_request(preparation, key='board'):
    return BoardCreateRequest(request_id=key, preparation_id=preparation.id,
        question='What information is reported?', paper_ids=preparation.selected_paper_ids,
        fields=[BoardFieldInput(id='information', label='Information', subquestion='Imported source text')])


def test_collection_board_definition_retains_schema_origin_and_exact_paper_binding(tmp_path):
    case = case_for(tmp_path)
    preparation = prepare_collection(case)
    boards = EvidenceBoardService(case.registry, lambda mode: case.engine, BoardStore(tmp_path / 'boards.sqlite3'))
    board = boards.create(MODE, case.handle, board_request(preparation))
    definition = board.definition
    assert isinstance(definition, CollectionBoardRevision)
    assert definition.search_id is None and definition.search_sha256 is None
    assert definition.collection_ref == preparation.collection_ref
    assert definition.member_snapshot_sha256 == preparation.member_snapshot_sha256
    assert definition.papers[0].title == preparation.member_snapshots[0].paper.title
    assert not case.engine.get_workspace(case.handle).searches
    reopened = EvidenceBoardService(case.registry, boards.service_for, BoardStore(boards.store.path)).view(MODE, case.handle, definition.board_id)
    assert reopened == board
    assert isinstance(BoardView.model_validate_json(board.model_dump_json()).definition, CollectionBoardRevision)
    with boards.store.connection() as db:
        row = db.execute('SELECT * FROM board_definitions WHERE id=?', (definition.revision_id,)).fetchone()
        assert isinstance(boards.store.decode(row, BoardRevision), CollectionBoardRevision)
    wrong = definition.model_copy(update={'member_snapshot_sha256': 'f' * 64})
    with pytest.raises(MvpError) as error:
        boards._dependencies(case.engine.get_workspace(case.handle), wrong)
    assert error.value.code == 'board_integrity'


def test_mixed_definition_history_keeps_v1_bytes_but_uses_v2_export_for_v1_selection(tmp_path):
    case = case_for(tmp_path)
    boards = EvidenceBoardService(case.registry, lambda mode: case.engine, BoardStore(tmp_path / 'boards.sqlite3'))
    search = case.engine.search_literature(case.handle, SearchRequest(request_id='search', query='software fixture'))
    legacy_preparation = case.engine.prepare_sources(case.handle, PrepareSourcesRequest(request_id='legacy-prepare',
        search_id=search.id, paper_ids=[search.papers[0].id]))
    old = boards.create(MODE, case.handle, board_request(legacy_preparation))
    before = old.definition.model_dump_json()
    old_export = boards.export(MODE, case.handle, old.definition.board_id)
    assert old_export.schema_version == 'mvp.board-export.v1'
    assert 'collection_ref' not in old_export.csv_text
    preparation = prepare_collection(case, case.request.model_copy(update={
        'expected_source_revision': legacy_preparation.source_revision, 'expected_preparation_id': legacy_preparation.id}))
    revised = boards.revise(MODE, case.handle, old.definition.board_id, BoardReviseRequest(
        **board_request(preparation, 'revise').model_dump(), expected_revision_id=old.definition.revision_id))
    assert isinstance(revised.definition, CollectionBoardRevision)
    historical = boards.view(MODE, case.handle, old.definition.board_id, old.definition.revision_id)
    assert isinstance(historical.definition, BoardRevision) and historical.definition.model_dump_json() == before
    for history in (False, True):
        exported = boards.export(MODE, case.handle, old.definition.board_id, old.definition.revision_id, history=history)
        assert isinstance(exported, CollectionBoardExport)
        audit = json.loads(exported.json_text)
        assert audit['schema_version'] == 'mvp.collection-board-audit.v2'
        assert audit['table_schema_version'] == 'mvp.collection-board-table.v2'
        assert audit['table'][0]['collection_ref'] is None
        assert audit['table'][0]['member_snapshot_sha256'] is None
        assert len(audit['definitions']) == (2 if history else 1)
        assert audit['definitions'][0]['schema_version'] == 'mvp.board-definition.v1'
        assert 'collection_ref' not in audit['definitions'][0]


def test_collection_board_candidates_and_proposals_share_existing_manual_contracts(tmp_path):
    case = case_for(tmp_path)
    preparation = prepare_collection(case)
    boards = EvidenceBoardService(case.registry, lambda mode: case.engine, BoardStore(tmp_path / 'boards.sqlite3'))
    board = boards.create(MODE, case.handle, board_request(preparation))
    definition = board.definition
    candidates = boards.candidates(MODE, case.handle, definition.board_id, BoardCandidatesRequest(
        request_id='candidates', expected_revision_id=definition.revision_id,
        paper_id=definition.paper_ids[0], field_id='information'))
    assert candidates.returned_count == 1
    reference = candidates.candidates[0].reference
    assert boards.reference_context(MODE, case.handle, definition.board_id, reference.id).reference == reference

    class MockAdapter:
        enabled = True
        profile = {'model': 'software mock', 'revision': '1'}

        def generate(self, packet, *, timeout_seconds):
            evidence = packet.evidence[0]
            return ProposalGenerationResult(output_text=json.dumps({'cells': [{
                'field_id': packet.fields[0].field_id, 'value': 'Mock suggestion',
                'references': [{'evidence_id': evidence.evidence_id, 'quote': evidence.reference.quote}],
                'reason': 'Software fixture; no support judgment', 'missing_information': ''}]}))

    proposals = CellProposalService(boards, MockAdapter())
    run = proposals.generate(MODE, case.handle, definition.board_id, ProposalGenerateRequest(
        request_id='proposals', expected_revision_id=definition.revision_id,
        paper_ids=definition.paper_ids, field_ids=['information']))
    assert run.state == 'succeeded' and len(run.proposals) == 1
    assert run.proposals[0].paper_id == definition.paper_ids[0]
    assert all(cell.head is None for cell in boards.view(MODE, case.handle, definition.board_id).cells)
