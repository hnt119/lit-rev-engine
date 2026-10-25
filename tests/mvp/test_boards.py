"""Software contract checks for additive boards; not human usefulness evidence."""
from contextlib import contextmanager
import csv
import io
import json
import os

import pytest
from pydantic import ValidationError

from src.mvp.adapters.board_storage import BoardStore
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.board_contracts import (BoardCreateRequest, BoardFieldInput, BoardCandidatesRequest,
    BoardCellData, BoardDraftPutRequest, BoardSubmitRequest, BoardReferenceInput, BoardReviseRequest, BoardView)
from src.mvp.contracts import Paper, Block, PreparedSource, SearchPreview, SearchRequest, PrepareSourcesRequest, digest
from src.mvp.evidence_board import EvidenceBoardService
from src.mvp.ports import MvpError
from src.mvp.service import MVPService


class Registry:
    deleted = False
    @contextmanager
    def lifecycle_guard(self, workspace_id):
        yield
    def is_deleted(self, workspace_id):
        return self.deleted

class Provider:
    def search(self, request):
        papers = [Paper(title='Software fixture ' + str(i), pmid=str(i), abstract='Women diet microbiome cohort 😀 methods. ' + 'sample ' * 1300) for i in range(1, 4)]
        return SearchPreview(query=request.query, total_reported=3, fetched_count=3, papers=papers, truncated=False, mode='test')
    def prepare(self, paper):
        blocks = [Block(id='a', ordinal=1, text=paper.abstract, locator={'type': 'abstract'})]
        return PreparedSource(paper_id=paper.id, status='abstract_only', source_type='abstract', provider='fixture', source_url='',
                              blocks=blocks, blocks_sha256=digest([b.model_dump() for b in blocks]))

@pytest.fixture
def case(tmp_path):
    engine = MVPService(SQLiteWorkspaceStorage(tmp_path / 'research.sqlite3'), Provider(), Provider())
    handle = engine.create_workspace()
    search = engine.search_literature(handle, SearchRequest(request_id='search', query='diet microbiome women'))
    preparation = engine.prepare_sources(handle, PrepareSourcesRequest(request_id='prepare', search_id=search.id, paper_ids=[p.id for p in search.papers]))
    store = BoardStore(tmp_path / 'board.sqlite3')
    registry = Registry()
    boards = EvidenceBoardService(registry, lambda mode: engine, store)
    request = BoardCreateRequest(request_id='board', preparation_id=preparation.id, question='How does diet affect the microbiome?',
        paper_ids=preparation.selected_paper_ids, fields=[BoardFieldInput(id=key, label=key.title(), subquestion=key) for key in ('diet', 'cohort', 'methods')])
    board = boards.create('test', handle, request)
    return boards, handle, engine, store, registry, request, board


def ref_from(output):
    return BoardReferenceInput.model_validate(output.model_dump(include=set(BoardReferenceInput.model_fields)))


def test_three_by_three_empty_reopening_is_additive_and_no_read_mutations(case):
    boards, handle, engine, store, _, request, board = case
    before = engine.get_workspace(handle).model_dump_json()
    assert len(board.cells) == 9 and all(c.head is None and c.draft_version == 0 for c in board.cells)
    with store.connection() as db:
        before_sidecar = db.total_changes
        count = db.execute('SELECT COUNT(*) FROM board_requests').fetchone()[0]
    reopened = EvidenceBoardService(boards.registry, boards.service_for, BoardStore(store.path)).view('test', handle, board.definition.board_id)
    assert reopened == board
    assert boards.listing('test', handle).boards[0].board_id == board.definition.board_id
    assert engine.get_workspace(handle).model_dump_json() == before
    with store.connection() as db:
        assert db.total_changes == before_sidecar == 0
        assert db.execute('SELECT COUNT(*) FROM board_requests').fetchone()[0] == count
    assert boards.create('test', handle, request).definition == board.definition
    assert os.stat(store.path).st_mode & 0o777 == 0o600


def test_summary_matches_preparation_and_order_without_loading_board_cells(case):
    boards, handle, _, store, _, _, board = case
    summary = boards.listing('test', handle).boards[0]
    assert summary.preparation_id == board.definition.preparation_id
    assert summary.paper_ids == board.definition.paper_ids
    assert board.definitions[0].preparation_id == summary.preparation_id
    original = store.draft
    store.draft = lambda *args: pytest.fail('Board listing must not load every cell draft')
    try:
        assert boards.listing('test', handle).boards == [summary]
    finally:
        store.draft = original


def test_legacy_cached_board_view_replays_with_additive_summary_defaults(case):
    boards, handle, _, store, _, request, board = case
    legacy = board.model_dump(mode='json')
    legacy['limits'].pop('max_papers')
    for summary in legacy['definitions']:
        summary.pop('preparation_id')
        summary.pop('paper_ids')
    parsed = BoardView.model_validate(legacy)
    assert parsed.definition == board.definition
    assert parsed.definitions[0].preparation_id is None and parsed.definitions[0].paper_ids == []
    with store.connection() as db:
        db.execute('UPDATE board_requests SET result=? WHERE workspace_id=? AND request_id=?',
            (json.dumps(legacy), handle.workspace_id, request.request_id))
    replay = boards.create('test', handle, request)
    assert replay.definition == board.definition
    assert replay.definitions[0].preparation_id == board.definition.preparation_id
    assert replay.definitions[0].paper_ids == board.definition.paper_ids
    assert replay.limits.max_papers == 30 and replay.limits.max_cells == 180


def test_candidates_bounded_exact_unicode_and_context_paginated(case):
    boards, handle, _, _, _, _, board = case
    definition = board.definition
    candidate = boards.candidates('test', handle, definition.board_id, BoardCandidatesRequest(request_id='candidate', expected_revision_id=definition.revision_id, paper_id=definition.paper_ids[0], field_id='diet'))
    assert candidate.returned_count == 1 and candidate.indexed_blocks == candidate.matched_blocks == 1
    assert candidate.meaning == 'potential_relevance_not_inspected_support'
    ref = candidate.candidates[0].reference
    assert len(ref.quote) == 1200 and candidate.candidates[0].omitted_characters > 0
    inspected = boards.blocks('test', handle, definition.board_id, ref.source_id)
    first = inspected.blocks[0]
    assert len(first.text) == 4000 and first.omitted_after > 0
    second = boards.blocks('test', handle, definition.board_id, ref.source_id, block_id=ref.block_id, start=first.end)
    assert second.blocks[0].start == 4000 and second.blocks[0].omitted_before == 4000
    context = boards.reference_context('test', handle, definition.board_id, ref.id)
    assert context.reference == ref
    assert len(context.block.text) <= 4000
    view = boards.view('test', handle, definition.board_id)
    assert all(c.head is None and c.draft_version == 0 for c in view.cells)


def test_manual_submit_revision_history_compact_view_and_separate_exports(case):
    boards, handle, _, _, _, _, board = case
    definition = board.definition
    paper_id = definition.paper_ids[0]
    inspection = boards.blocks('test', handle, definition.board_id, definition.sources[0].source_id)
    reference = ref_from(inspection.blocks[0].reference)
    data = BoardCellData(value='=formula must be escaped in CSV', references=[reference], inspected_ranges=[reference],
                         semantic_assessment='human_supported', scope_result='value_found', reason='Software fixture user-declared support')
    draft = boards.put_draft('test', handle, definition.board_id, paper_id, 'diet', BoardDraftPutRequest(expected_revision_id=definition.revision_id, version=0, data=data))
    request = BoardSubmitRequest(request_id='submit', expected_revision_id=definition.revision_id, paper_id=paper_id, field_id='diet', draft_version=draft.version)
    cell = boards.submit('test', handle, definition.board_id, request)
    assert boards.submit('test', handle, definition.board_id, request) == cell
    assert cell.references[0].quote == inspection.blocks[0].text
    assert boards.get_draft('test', handle, definition.board_id, paper_id, 'diet').version == 0
    compact = boards.view('test', handle, definition.board_id).cells[0].head
    assert compact.id == cell.id
    assert 'quote' not in compact.references[0].model_dump()
    assert 'quote' not in compact.inspected_ranges[0].model_dump()
    assert len(compact.model_dump_json()) < 4000
    revised_data = data.model_copy(update={'value': 'Revised value'})
    draft = boards.put_draft('test', handle, definition.board_id, paper_id, 'diet', BoardDraftPutRequest(expected_revision_id=definition.revision_id, version=0, expected_cell_head_id=cell.id, data=revised_data))
    revised = boards.submit('test', handle, definition.board_id, request.model_copy(update={'request_id': 'submit2', 'draft_version': draft.version, 'supersedes_id': cell.id}))
    assert revised.supersedes_id == cell.id
    assert boards.history('test', handle, definition.board_id, paper_id, 'diet', limit=1).total == 2
    export = boards.export('test', handle, definition.board_id, history=True)
    audit = json.loads(export.json_text)
    assert audit['schema_version'] == 'mvp.board-audit.v1'
    assert len(audit['table']) == 9 and len(audit['cell_revisions']) == 2
    assert audit['cell_revisions'][0]['value'].startswith('=')
    assert audit['cell_revisions'][0]['references'][0]['quote'] == inspection.blocks[0].text
    first_export = boards.export('test', handle, definition.board_id)
    assert list(csv.DictReader(io.StringIO(first_export.csv_text)))[0]['value'] == 'Revised value'


def test_definition_revision_new_empty_cells_historical_references_preserved(case):
    boards, handle, _, _, _, request, board = case
    revised = boards.revise('test', handle, board.definition.board_id, BoardReviseRequest(**request.model_dump(exclude={'request_id'}), request_id='revise', expected_revision_id=board.definition.revision_id))
    assert revised.definition.parent_revision_id == board.definition.revision_id
    assert revised.definition.fields[0].revision_id != board.definition.fields[0].revision_id
    assert all(cell.head is None for cell in revised.cells)
    old = boards.view('test', handle, board.definition.board_id, board.definition.revision_id)
    assert old.freshness == 'historical'
    with pytest.raises(MvpError, match='definition or prepared sources changed'):
        boards.put_draft('test', handle, board.definition.board_id, old.definition.paper_ids[0], 'diet', BoardDraftPutRequest(expected_revision_id=old.definition.revision_id, version=0, data=BoardCellData()))


@pytest.mark.parametrize('identifier', ['../field', '..', 'a/b', 'a\\b', 'a\nfield', ' space', 'é'])
def test_unaddressable_field_ids_rejected(identifier):
    with pytest.raises(ValidationError):
        BoardFieldInput(id=identifier, label='Field', subquestion='What was measured?')


@pytest.mark.parametrize('limit_name,limit_value,operation', [
    ('max_boards', 1, 'create'), ('max_definitions', 1, 'revise'), ('max_workspace_bytes', 1, 'draft')])
def test_storage_bounds_rollback_preserve_existing(case, limit_name, limit_value, operation):
    boards, handle, _, store, _, request, board = case
    setattr(store, limit_name, limit_value)
    before = boards.view('test', handle, board.definition.board_id)
    with pytest.raises(MvpError):
        if operation == 'create':
            boards.create('test', handle, request.model_copy(update={'request_id': 'extra'}))
        elif operation == 'revise':
            boards.revise('test', handle, board.definition.board_id, BoardReviseRequest(**request.model_dump(exclude={'request_id'}), request_id='rev', expected_revision_id=board.definition.revision_id))
        else:
            boards.put_draft('test', handle, board.definition.board_id, board.definition.paper_ids[0], 'diet', BoardDraftPutRequest(expected_revision_id=board.definition.revision_id, version=0, data=BoardCellData(value='unfinished')))
    assert boards.view('test', handle, board.definition.board_id) == before


def test_delete_is_idempotent_and_late_operations_cannot_recreate(case):
    boards, handle, _, store, registry, request, board = case
    boards.delete_workspace(handle.workspace_id)
    boards.delete_workspace(handle.workspace_id)
    with pytest.raises(MvpError):
        boards.create('test', handle, request.model_copy(update={'request_id': 'late'}))
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM evidence_boards').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM board_deleted').fetchone()[0] == 1


def test_draft_reference_rejects_wrong_paper_and_preserves_prior(case):
    boards, handle, _, _, _, _, board = case
    definition = board.definition
    paper_id = definition.paper_ids[0]
    saved = boards.put_draft('test', handle, definition.board_id, paper_id, 'diet', BoardDraftPutRequest(expected_revision_id=definition.revision_id, version=0, data=BoardCellData(value='private unfinished draft')))
    wrong = boards.blocks('test', handle, definition.board_id, definition.sources[1].source_id).blocks[0].reference
    with pytest.raises(MvpError, match='must belong'):
        boards.put_draft('test', handle, definition.board_id, paper_id, 'diet', BoardDraftPutRequest(expected_revision_id=definition.revision_id, version=saved.version, data=BoardCellData(references=[ref_from(wrong)])))
    assert boards.get_draft('test', handle, definition.board_id, paper_id, 'diet') == saved


def test_unavailable_source_null_requires_reason_and_preserves_failed_draft(case):
    boards, handle, engine, _, _, request, _ = case
    original = engine._sources.prepare
    def prepare(paper):
        if paper.id == 'pmid:3':
            return PreparedSource(paper_id=paper.id, status='no_usable_text', source_type='none', provider='fixture', source_url='')
        return original(paper)
    engine._sources.prepare = prepare
    state = engine.get_workspace(handle)
    preparation = engine.prepare_sources(handle, PrepareSourcesRequest(request_id='prepare-unavailable', search_id=state.searches[0].id, paper_ids=request.paper_ids))
    board = boards.create('test', handle, request.model_copy(update={'request_id': 'board-unavailable', 'preparation_id': preparation.id}))
    definition = board.definition
    assert definition.sources[-1].source_type == 'none'
    candidates = boards.candidates('test', handle, definition.board_id, BoardCandidatesRequest(request_id='none-candidates', expected_revision_id=definition.revision_id, paper_id='pmid:3', field_id='diet'))
    assert candidates.indexed_blocks == candidates.matched_blocks == candidates.returned_count == 0
    assert boards.blocks('test', handle, definition.board_id, definition.sources[-1].source_id).blocks == []
    draft = boards.put_draft('test', handle, definition.board_id, 'pmid:3', 'diet', BoardDraftPutRequest(expected_revision_id=definition.revision_id, version=0, data=BoardCellData()))
    submit = BoardSubmitRequest(request_id='empty-submit', expected_revision_id=definition.revision_id, paper_id='pmid:3', field_id='diet', draft_version=draft.version)
    with pytest.raises(MvpError, match='missing value requires'):
        boards.submit('test', handle, definition.board_id, submit)
    assert boards.get_draft('test', handle, definition.board_id, 'pmid:3', 'diet') == draft
    data = BoardCellData(value=None, missing_information='Diet information cannot be inspected because no source text was retained.',
                         reason='No full text or abstract is available in this preparation.', scope_result='not_assessed')
    saved = boards.put_draft('test', handle, definition.board_id, 'pmid:3', 'diet', BoardDraftPutRequest(expected_revision_id=definition.revision_id, version=draft.version, data=data))
    cell = boards.submit('test', handle, definition.board_id, submit.model_copy(update={'request_id': 'explicit-unavailable', 'draft_version': saved.version}))
    assert cell.value is None and cell.scope_result == 'not_assessed' and not cell.inspected_ranges
    assert cell.semantic_assessment == 'unassessed' and cell.reference_integrity == 'not_applicable'


def test_cell_revision_limit_rolls_back_and_retains_revision_draft(case):
    boards, handle, _, store, _, _, board = case
    definition = board.definition
    paper = definition.paper_ids[0]
    data = BoardCellData(value='Provisional manual note', reason='Not assessed for support.')
    draft = boards.put_draft('test', handle, definition.board_id, paper, 'diet', BoardDraftPutRequest(expected_revision_id=definition.revision_id, version=0, data=data))
    first = boards.submit('test', handle, definition.board_id, BoardSubmitRequest(request_id='first', expected_revision_id=definition.revision_id, paper_id=paper, field_id='diet', draft_version=draft.version))
    draft = boards.put_draft('test', handle, definition.board_id, paper, 'diet', BoardDraftPutRequest(expected_revision_id=definition.revision_id, version=0, expected_cell_head_id=first.id, data=data))
    store.max_cell_revisions = 1
    with pytest.raises(MvpError, match='revision limit'):
        boards.submit('test', handle, definition.board_id, BoardSubmitRequest(request_id='second', expected_revision_id=definition.revision_id, paper_id=paper, field_id='diet', draft_version=draft.version, supersedes_id=first.id))
    assert boards.get_draft('test', handle, definition.board_id, paper, 'diet') == draft
    assert boards.view('test', handle, definition.board_id).cells[0].head.id == first.id


def test_idempotent_candidate_replay_still_checks_retained_source_integrity(case):
    import sqlite3
    boards, handle, engine, store, _, _, board = case
    definition = board.definition
    request = BoardCandidatesRequest(request_id='cached', expected_revision_id=definition.revision_id,
                                     paper_id=definition.paper_ids[0], field_id='diet')
    boards.candidates('test', handle, definition.board_id, request)
    with sqlite3.connect(engine._storage._path) as db:
        raw = json.loads(db.execute('SELECT snapshot FROM mvp_workspaces WHERE id=?', (handle.workspace_id,)).fetchone()[0])
        raw['preparations'][0]['sources'][0]['blocks'][0]['text'] = 'Corrupt stored text'
        db.execute('UPDATE mvp_workspaces SET snapshot=? WHERE id=?', (json.dumps(raw), handle.workspace_id))
    with pytest.raises(MvpError) as failure:
        boards.candidates('test', handle, definition.board_id, request)
    assert failure.value.code == 'source_integrity_error'
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM board_candidates').fetchone()[0] == 1
