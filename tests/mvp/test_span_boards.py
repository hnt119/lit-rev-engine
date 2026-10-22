"""Software integration of explicit span profiles; no human/model evaluation."""
from contextlib import contextmanager
import json

import pytest

from test_boards import case
from src.mvp.board_contracts import BoardCandidatesRequest, BoardFieldInput, BoardReviseRequest
from src.mvp.contracts import Block, PrepareSourcesRequest, PreparedSource, digest
from src.mvp.ports import MvpError
from src.mvp.span_board_contracts import ProfiledBoardCreateRequest, ProfiledBoardReviseRequest, SpanBoardCandidates


def profiled(case, **changes):
    boards, handle, _, _, _, request, _ = case
    values = {**request.model_dump(), 'request_id': 'explicit-span-board', 'retrieval_profile_id': 'lexical_spans_v1', **changes}
    return boards.create('test', handle, ProfiledBoardCreateRequest(**values))


def retrieve(boards, handle, definition, key='span-candidates'):
    return boards.candidates('test', handle, definition.board_id, BoardCandidatesRequest(
        request_id=key, expected_revision_id=definition.revision_id,
        paper_id=definition.paper_ids[0], field_id=definition.fields[0].id))


def test_span_profile_keeps_old_requests_and_definitions_identical_and_requires_explicit_revisions(case):
    boards, handle, _, _, _, request, old = case
    original = old.definition.model_dump_json()
    assert 'retrieval_profile_id' not in request.model_dump()
    board = profiled(case)
    profile = board.definition.retrieval_profile
    assert profile['profile_id'] == 'lexical_spans_v1'
    assert profile['packet_policy'] == 'primary-spans-round-robin.v1'
    assert profile['explicit_requirement_field_ids'] == []
    for field in board.definition.fields:
        assert profile['requirements_by_field'][field.id] == [{'id': 'field', 'label': field.label, 'query': field.subquestion}]
    with pytest.raises(MvpError) as error:
        boards.revise('test', handle, board.definition.board_id, BoardReviseRequest(
            **request.model_dump(exclude={'request_id'}), request_id='implicit-downgrade', expected_revision_id=board.definition.revision_id))
    assert error.value.code == 'explicit_board_profile_required'
    revised = boards.revise('test', handle, board.definition.board_id, ProfiledBoardReviseRequest(
        **request.model_dump(exclude={'request_id'}), request_id='explicit-baseline',
        retrieval_profile_id='legacy_block_prefix_v1', expected_revision_id=board.definition.revision_id))
    assert revised.definition.retrieval_profile == old.definition.retrieval_profile
    assert boards.view('test', handle, old.definition.board_id).definition.model_dump_json() == original


def test_late_span_is_delivered_inspectable_replayed_and_exported_without_changing_canonical_locators(case):
    boards, handle, engine, _, _, request, _ = case
    text = 'SOFTWARE FIXTURE. ' + 'Irrelevant boilerplate. ' * 700 + 'Lateanchor population comprised 120 women in Japan; this was not a validation cohort. '
    locator = {'type': 'paragraph', 'section': 'Results', 'heading': 'Study participants'}
    def prepare(paper):
        block = Block(id='late-block', ordinal=1, text=text, locator=locator)
        return PreparedSource(paper_id=paper.id, status='abstract_only', source_type='abstract', provider='software-fixture',
            source_url='', blocks=[block], blocks_sha256=digest([block.model_dump()]))
    engine._sources.prepare = prepare
    preparation = engine.prepare_sources(handle, PrepareSourcesRequest(request_id='late-preparation',
        search_id=engine.get_workspace(handle).searches[0].id, paper_ids=request.paper_ids))
    fields = [BoardFieldInput(id='population', label='Population', subquestion='Lateanchor population women validation')]
    plain = boards.create('test', handle, request.model_copy(update={'request_id': 'late-baseline', 'preparation_id': preparation.id, 'fields': fields}))
    baseline = retrieve(boards, handle, plain.definition, 'late-prefix')
    assert all('Lateanchor' not in candidate.reference.quote for candidate in baseline.candidates)
    board = profiled(case, request_id='late-spans', preparation_id=preparation.id, fields=fields)
    before = engine.get_workspace(handle).model_dump_json()
    result = retrieve(boards, handle, board.definition)
    assert isinstance(result, SpanBoardCandidates) and result.returned_count
    selected = next(candidate for candidate in result.candidates if 'Lateanchor' in candidate.reference.quote)
    assert selected.reference.start > 1200
    assert selected.reference.quote == text[selected.reference.start:selected.reference.end]
    assert selected.omitted_before == selected.reference.start and selected.omitted_after == len(text)-selected.reference.end
    assert selected.reference.locator == locator
    assert retrieve(boards, handle, board.definition).model_dump_json() == result.model_dump_json()
    context = boards.reference_context('test', handle, board.definition.board_id, selected.reference.id)
    assert context.reference == selected.reference and context.block.locator == locator
    audit = json.loads(boards.export('test', handle, board.definition.board_id).json_text)
    assert audit['schema_version'] == 'mvp.board-audit.v1'
    assert audit['candidate_runs'][0]['schema_version'] == 'mvp.board-candidates.spans.v2'
    assert audit['candidate_runs'][0]['candidates'][0]['reference']['locator'] == locator
    assert engine.get_workspace(handle).model_dump_json() == before


def test_span_cpu_ranking_releases_all_guards_and_rejects_a_concurrent_definition_revision(case, monkeypatch):
    boards, handle, engine, store, registry, request, _ = case
    board = profiled(case)
    counters = dict(lifecycle=0, research=0, sqlite=0)
    def instrument(original, name):
        @contextmanager
        def tracked(*args, **kwargs):
            with original(*args, **kwargs) as resource:
                counters[name] += 1
                try:
                    yield resource
                finally:
                    counters[name] -= 1
        return tracked
    monkeypatch.setattr(registry, 'lifecycle_guard', instrument(registry.lifecycle_guard, 'lifecycle'))
    monkeypatch.setattr(engine._storage, '_workspace_lock', instrument(engine._storage._workspace_lock, 'research'))
    monkeypatch.setattr(store, 'transaction', instrument(store.transaction, 'sqlite'))
    ranker = boards.span_ranker
    class ConcurrentRevision:
        profile = staticmethod(ranker.profile)
        def search(self, *args, **kwargs):
            assert counters == dict(lifecycle=0, research=0, sqlite=0)
            result = ranker.search(*args, **kwargs)
            boards.revise('test', handle, board.definition.board_id, ProfiledBoardReviseRequest(
                **request.model_dump(exclude={'request_id'}), request_id='concurrent-definition',
                retrieval_profile_id='lexical_spans_v1', expected_revision_id=board.definition.revision_id))
            return result
    boards.span_ranker = ConcurrentRevision()
    with pytest.raises(MvpError) as error:
        retrieve(boards, handle, board.definition)
    assert error.value.code == 'stale_board_revision'
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM board_candidates').fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM board_requests WHERE request_id='span-candidates'").fetchone()[0] == 0
