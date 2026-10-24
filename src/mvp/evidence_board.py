"""Manual comparison boards over immutable retained preparation dependencies.

No model/provider calls, global selection mutations or existing export changes.
Mutation lock order is lifecycle -> research snapshot -> short sidecar transaction.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from pydantic import ValidationError
from .board_contracts import *
from .contracts import BoardPassageScope, digest, new_id, now
from .adapters.board_storage import BoardStore, unavailable
from .adapters.retrieval import LexicalRetrieval
from .ports import MvpError
from .service import _assert_source_integrity, _manifest, _find
from .origin_resolver import resolve_preparation
from src.review.exporters import _csv
from .span_board_contracts import (ProfiledBoardCreateRequest, LEGACY_BOARD_PROFILE, SPAN_BOARD_PROFILE,
    SpanBoardCandidate, SpanBoardCandidates, SpanRequirementMatch)
from .span_retrieval_contracts import SpanRequirement, SpanRetrievalResult


@dataclass(frozen=True)
class _SpanWork:
    definition: object
    source: object
    field: BoardField
    request: BoardCandidatesRequest
    fingerprint: str
    run_id: str


class EvidenceBoardService:
    def __init__(self, registry, service_for, store: BoardStore):
        self.registry, self.service_for, self.store = registry, service_for, store
        self.ranker = LexicalRetrieval()
        self.span_ranker = None

    def _with(self, mode, handle, callback, *, write=False):
        def guarded(state):
            if self.registry.is_deleted(state.id):
                raise unavailable('workspace')
            manager = self.store.transaction if write else self.store.connection
            with manager() as db:
                self.store.alive(db, state.id)
                return callback(state, db)
        with self.registry.lifecycle_guard(handle.workspace_id):
            return self.service_for(mode).with_workspace_state(handle, guarded)

    def _span(self):
        if self.span_ranker is None:
            from .adapters.span_retrieval import LexicalSpanRetrieval
            self.span_ranker = LexicalSpanRetrieval()
        return self.span_ranker

    def _profile(self, request=None):
        if isinstance(request, ProfiledBoardCreateRequest) and request.retrieval_profile_id == SPAN_BOARD_PROFILE:
            explicit = {value.field_id: value.requirements for value in request.field_requirements}
            profile = self._span().profile()
            profile.update({'profile_id': SPAN_BOARD_PROFILE, 'scope': 'one-paper-one-field',
                'candidate_text_limit': MAX_CANDIDATE_CHARACTERS,
                'requirements_by_field': {field.id: [value.model_dump(mode='json') for value in explicit.get(field.id,
                    [SpanRequirement(id='field', label=field.label, query=field.subquestion)])] for field in request.fields},
                'explicit_requirement_field_ids': [value.field_id for value in request.field_requirements],
                'packet_policy': 'primary-spans-round-robin.v1'})
            return profile
        return {'method': self.ranker.method, 'method_version': 'lit-rev-engine.project-retrieval.v3.bm25_context_blocks',
                'parameters': self.ranker.parameters, 'scope': 'one-paper-one-field', 'candidate_text_limit': MAX_CANDIDATE_CHARACTERS}

    @staticmethod
    def _summary(definition):
        return BoardSummary(board_id=definition.board_id, revision_id=definition.revision_id, question=definition.question,
                            paper_count=len(definition.paper_ids), field_count=len(definition.fields), created_at=definition.created_at,
                            preparation_id=definition.preparation_id, paper_ids=definition.paper_ids)

    @staticmethod
    def _cell(definition, paper_id, field_id):
        if paper_id not in definition.paper_ids:
            raise unavailable('board_paper')
        field = next((field for field in definition.fields if field.id == field_id), None)
        if field is None:
            raise unavailable('board_field')
        return field

    def _dependencies(self, state, definition):
        preparation = _find(state.preparations, definition.preparation_id, 'preparation')
        bibliography = resolve_preparation(state, preparation)
        if isinstance(definition, CollectionBoardRevision):
            valid_origin = (bibliography.origin.kind == 'collection' and bibliography.origin == definition.collection_ref
                and getattr(preparation, 'member_snapshot_sha256', None) == definition.member_snapshot_sha256)
        else:
            valid_origin = (bibliography.origin.kind == 'search' and bibliography.origin.search_id == definition.search_id
                and bibliography.origin.search_snapshot_sha256 == definition.search_sha256)
        if not valid_origin or preparation.source_revision != definition.source_revision:
            raise MvpError('board_integrity', 'The board original bibliography or preparation binding changed.')
        sources = [_find(preparation.sources, source.source_id, 'source') for source in definition.sources]
        _assert_source_integrity(sources)
        if digest(_manifest(sources)) != definition.source_manifest_sha256:
            raise MvpError('board_integrity', 'The board retained source manifest changed.')
        if [source.paper_id for source in sources] != definition.paper_ids:
            raise MvpError('board_integrity', 'The board source ownership changed.')
        indexed = {paper.id: paper for paper in bibliography.papers}
        if (len(set(definition.paper_ids)) != len(definition.paper_ids)
                or any(identifier not in indexed for identifier in definition.paper_ids)
                or definition.papers != [BoardPaper.model_validate(indexed[identifier].model_dump(exclude={'abstract'})) for identifier in definition.paper_ids]
                or digest(definition.question) != definition.question_sha256
                or digest(definition.retrieval_profile) != definition.retrieval_profile_sha256):
            raise MvpError('board_integrity', 'The board retained papers, question or retrieval-profile binding changed.')
        return bibliography, preparation, sources

    def _freshness(self, state, db, definition):
        self._dependencies(state, definition)
        reasons = []
        if self.store.board_head(db, state.id, definition.board_id) != definition.revision_id:
            reasons.append('A newer board definition exists.')
        if not state.preparations or state.preparations[-1].id != definition.preparation_id or state.source_revision != definition.source_revision:
            reasons.append('The workspace has a newer source preparation; this board retains its original sources.')
        return ('historical' if reasons else 'current'), reasons

    def _writable(self, state, db, board_id, expected_revision_id):
        definition = self.store.definition(db, state.id, board_id, expected_revision_id)
        freshness, _ = self._freshness(state, db, definition)
        if freshness != 'current':
            raise MvpError('stale_board_revision', 'Board definition or prepared sources changed. Create an explicit definition revision before editing; historical judgments remain readable.')
        return definition

    def _passage_search_context(self, state, db, scope, *, require_current=True):
        definition = (self._writable(state, db, scope.board_id, scope.board_revision_id)
                      if require_current else self.store.definition(db, state.id, scope.board_id, scope.board_revision_id))
        _, _, sources = self._dependencies(state, definition)
        if definition.retrieval_profile.get('profile_id', LEGACY_BOARD_PROFILE) not in {LEGACY_BOARD_PROFILE, SPAN_BOARD_PROFILE}:
            raise MvpError('unsupported_board_profile', 'This comparison retains an unsupported profile. Its sources were not silently replaced.')
        field = self._cell(definition, scope.paper_id, scope.field_id) if scope.paper_id is not None else None
        paper_ids = [scope.paper_id] if field is not None else definition.paper_ids
        selected = [source for source in sources if source.paper_id in paper_ids]
        context = BoardPassageSearchContext(**scope.model_dump(), preparation_id=definition.preparation_id,
            source_revision=definition.source_revision, source_manifest_sha256=definition.source_manifest_sha256,
            board_paper_ids=definition.paper_ids, paper_ids=paper_ids,
            sources=[source for source in definition.sources if source.paper_id in paper_ids],
            papers=[paper for paper in definition.papers if paper.id in paper_ids], board_question=definition.question,
            question=field.subquestion if field else definition.question,
            field_revision_id=field.revision_id if field else None, field_label=field.label if field else None)
        return context, selected

    def passage_search_context(self, mode, handle, scope):
        return self._with(mode, handle, lambda state, db: self._passage_search_context(state, db, scope)[0])

    @staticmethod
    def _matching_passage_run(state, context, run_id):
        from .origin_resolver import resolve_run
        run = _find(state.runs, run_id, 'run')
        if run.parameters.get('board_passage_context') != context.model_dump(mode='json'):
            raise MvpError('unrelated_comparison_run', 'This saved passage run does not belong to the exact comparison, paper scope and field.')
        if run.preparation_id != context.preparation_id or run.source_revision != context.source_revision:
            raise MvpError('board_integrity', 'The saved passage run preparation does not match this comparison.')
        preparation, _ = resolve_run(state, run)
        _assert_source_integrity(preparation.sources)
        if run.source_snapshot_sha256 != digest(_manifest(preparation.sources)):
            raise MvpError('source_integrity_error', 'The saved passage run manifest does not match its original preparation.')
        if any(passage.paper_id not in context.paper_ids for passage in run.passages):
            raise MvpError('board_integrity', 'The saved passage run contains a paper outside this comparison scope.')
        return run

    def retrieve_passages(self, mode, handle, request):
        """Delegate to the existing ranker under its original publication lock."""
        def resolve(state, scope):
            with self.store.connection() as db:
                self.store.alive(db, state.id)
                return self._passage_search_context(state, db, scope)
        with self.registry.lifecycle_guard(handle.workspace_id):
            if self.registry.is_deleted(handle.workspace_id):
                raise unavailable('workspace')
            result = self.service_for(mode).retrieve_evidence_bound(handle, request, board_resolver=resolve)
            # Idempotent receipt replay must also revalidate the board head.
            def check(state):
                context, _ = resolve(state, request.board_context)
                self._matching_passage_run(state, context, result.id)
            self.service_for(mode).with_workspace_state(handle, check)
            return result

    @staticmethod
    def passage_draft_scope(scope):
        """Decode bounded IDs, never query text, without nested URL escaping."""
        if not scope.startswith('board-evidence:'):
            return None
        parts = scope.removeprefix('board-evidence:').split(':')
        if len(parts) not in {2, 4} or any(not value or len(value) > 1600 for value in parts):
            raise MvpError('invalid_draft_scope', 'Use an exact comparison revision and optional paper/field draft scope.')
        try:
            decoded = parts[:2] + [bytes.fromhex(value).decode('utf-8') for value in parts[2:]]
            if any(value.encode('utf-8').hex() != encoded for value, encoded in zip(decoded[2:], parts[2:])):
                raise ValueError('Use canonical lowercase UTF-8 hex cell identifiers')
            return BoardPassageScope(board_id=decoded[0], board_revision_id=decoded[1],
                paper_id=decoded[2] if len(parts) == 4 else None, field_id=decoded[3] if len(parts) == 4 else None)
        except (ValueError, UnicodeError):
            raise MvpError('invalid_draft_scope', 'Use bounded comparison identifiers for this search draft.') from None

    def passage_draft(self, mode, handle, scope, request=None):
        identity = self.passage_draft_scope(scope)
        def validate(state, db):
            # Retain historical query edits, but retrieval remains current-only.
            context, _ = self._passage_search_context(state, db, identity, require_current=False)
            prior = self.registry.draft(state.id, scope)
            if request is not None and prior['version'] != request.version:
                raise MvpError('stale_draft', 'A newer saved draft exists. Your local edits were not overwritten; reload for comparison.')
            data = request.data if request is not None else prior['data']
            if request is not None or prior['version']:
                try:
                    parsed = BoardPassageSearchDraft.model_validate(data)
                except ValidationError:
                    raise MvpError('invalid_comparison_search_draft', 'Keep a bounded query, passage count from 5 to 30, and an optional matching saved run.') from None
                if parsed.selected_run_id is not None:
                    self._matching_passage_run(state, context, parsed.selected_run_id)
            if request is None:
                return prior
            if request.expected_assessment_head is not None:
                raise MvpError('invalid_comparison_search_draft', 'Comparison search drafts do not set an assessment head.')
            return self.registry.put_draft(state.id, scope, **request.model_dump(mode='json'))
        return self._with(mode, handle, validate)

    def passage_source_context(self, mode, handle, scope, run_id, passage_id):
        if scope.paper_id is None:
            raise MvpError('invalid_board_reference', 'Choose an exact comparison cell before opening a passage in its inspector.')
        def inspect(state, db):
            context, _ = self._passage_search_context(state, db, scope)
            run = self._matching_passage_run(state, context, run_id)
            # Existing exact source checks validate retained hashes, version,
            # quotation and Unicode range; no client quotation is accepted.
            source_context = self.service_for(mode)._source_context(state, run,
                _find(state.preparations, run.preparation_id, 'preparation').sources, passage_id)
            passage = source_context.passage
            if passage.paper_id != scope.paper_id:
                raise MvpError('invalid_board_reference', 'A passage from another paper cannot be opened in this cell.')
            definition = self._writable(state, db, scope.board_id, scope.board_revision_id)
            reference = self._reference(state, definition, scope.paper_id, BoardReferenceInput(
                source_id=passage.source_id, source_version=passage.source_version,
                source_sha256=passage.source_sha256, blocks_sha256=passage.blocks_sha256,
                block_id=passage.anchor.block_id, start=passage.anchor.start,
                end=min(passage.anchor.end, passage.anchor.start + MAX_INSPECTOR_CHARACTERS)))
            return BoardPassageSourceContext(reference=reference,
                paper=next(paper for paper in definition.papers if paper.id == scope.paper_id),
                source=next(source for source in definition.sources if source.source_id == passage.source_id),
                freshness='current', block=self._chunk(state, definition, source_context.source,
                    source_context.block, passage.anchor.start), run_id=run.id, passage_id=passage.id,
                passage_start=passage.anchor.start, passage_end=passage.anchor.end,
                passage_omitted_after=passage.anchor.end-reference.end)
        return self._with(mode, handle, inspect)

    def _definition(self, state, request, *, board_id=None, parent=None):
        preparation = _find(state.preparations, request.preparation_id, 'preparation')
        if not state.preparations or state.preparations[-1].id != preparation.id or state.source_revision != preparation.source_revision:
            raise MvpError('stale_source_revision', 'Select the current retained preparation for a new board definition.')
        bibliography = resolve_preparation(state, preparation)
        sources, papers = [], []
        for paper_id in request.paper_ids:
            if paper_id not in preparation.selected_paper_ids:
                raise unavailable('prepared_paper')
            paper = _find(bibliography.papers, paper_id, 'paper')
            source = next((source for source in preparation.sources if source.paper_id == paper_id), None)
            if source is None:
                raise unavailable('prepared_source')
            sources.append(source)
            papers.append(BoardPaper.model_validate(paper.model_dump(exclude={'abstract'})))
        _assert_source_integrity(sources)
        bindings = [BoardSourceBinding(source_id=s.id, paper_id=s.paper_id, version=s.version,
                    source_sha256=s.source_sha256, blocks_sha256=s.blocks_sha256, parser_id=s.parser_id,
                    source_type=s.source_type, status=s.status, block_count=len(s.blocks)) for s in sources]
        profile = self._profile(request)
        common = dict(board_id=board_id or new_id(), workspace_id=state.id, parent_revision_id=parent,
                question=request.question, question_sha256=digest(request.question), preparation_id=preparation.id,
                source_revision=preparation.source_revision, source_manifest_sha256=digest(_manifest(sources)),
                sources=bindings, papers=papers, paper_ids=request.paper_ids,
                fields=[BoardField(**f.model_dump()) for f in request.fields], retrieval_profile=profile,
                retrieval_profile_sha256=digest(profile))
        if bibliography.origin.kind == 'collection':
            return CollectionBoardRevision(**common, collection_ref=bibliography.origin,
                member_snapshot_sha256=preparation.member_snapshot_sha256)
        return BoardRevision(**common, search_id=bibliography.origin.search_id,
            search_sha256=bibliography.origin.search_snapshot_sha256)

    def _view(self, state, db, definition):
        freshness, reasons = self._freshness(state, db, definition)
        cells = []
        for paper_id in definition.paper_ids:
            for field in definition.fields:
                head_id = self.store.cell_head(db, definition, paper_id, field.id)
                row = db.execute('SELECT * FROM board_cells WHERE workspace_id=? AND id=?', (state.id, head_id)).fetchone() if head_id else None
                head = self.store.decode(row, BoardCellRevision) if row else None
                if head is not None:
                    payload = head.model_dump(mode='json')
                    for key in ('references', 'inspected_ranges'):
                        payload[key] = [{k: v for k, v in ref.items() if k != 'quote'} for ref in payload[key]]
                    head = BoardCellHead.model_validate(payload)
                cells.append(BoardCellSummary(paper_id=paper_id, field_id=field.id, head=head,
                             draft_version=self.store.draft(db, definition, paper_id, field.id).version))
        definitions = [self._summary(self.store.decode(row, BoardRevision)) for row in db.execute(
            'SELECT * FROM board_definitions WHERE workspace_id=? AND board_id=? ORDER BY rowid', (state.id, definition.board_id))]
        return BoardView(definition=definition, current_revision_id=self.store.board_head(db, state.id, definition.board_id),
                         freshness=freshness, freshness_reasons=reasons, cells=cells, definitions=definitions)

    def create(self, mode, handle, request: BoardCreateRequest):
        def run(state, db):
            fingerprint = digest({'operation': 'create', 'request': request.model_dump(mode='json')})
            prior = self.store.prior(db, state.id, request.request_id, fingerprint, BoardView)
            if prior is not None:
                # Replays return their original immutable definition and latest
                # compact cell state, never create/re-activate an old definition.
                definition = self.store.definition(db, state.id, prior.definition.board_id, prior.definition.revision_id)
                return self._view(state, db, definition)
            definition = self._definition(state, request)
            self.store.add_definition(db, definition, create=True)
            result = self._view(state, db, definition)
            self.store.record_request(db, state.id, request.request_id, fingerprint, result)
            return result
        return self._with(mode, handle, run, write=True)

    def listing(self, mode, handle):
        def run(state, db):
            definitions = [self.store.definition(db, state.id, row['board_id']) for row in db.execute(
                'SELECT board_id FROM evidence_boards WHERE workspace_id=? ORDER BY rowid', (state.id,))]
            return BoardListing(boards=[self._summary(item) for item in definitions])
        return self._with(mode, handle, run)

    def view(self, mode, handle, board_id, revision_id=None):
        return self._with(mode, handle, lambda state, db: self._view(state, db, self.store.definition(db, state.id, board_id, revision_id)))

    def revise(self, mode, handle, board_id, request: BoardReviseRequest):
        def run(state, db):
            fingerprint = digest({'operation': 'revise', 'board_id': board_id, 'request': request.model_dump(mode='json')})
            prior = self.store.prior(db, state.id, request.request_id, fingerprint, BoardView)
            if prior is not None:
                return self._view(state, db, self.store.definition(db, state.id, board_id, prior.definition.revision_id))
            if self.store.board_head(db, state.id, board_id) != request.expected_revision_id:
                raise MvpError('stale_board_revision', 'A newer board definition exists. Your inputs were not overwritten.')
            original = self.store.definition(db, state.id, board_id, request.expected_revision_id)
            if original.retrieval_profile.get('profile_id') == SPAN_BOARD_PROFILE and not isinstance(request, ProfiledBoardCreateRequest):
                raise MvpError('explicit_board_profile_required', 'Choose an explicit retrieval profile for this definition revision; a legacy request cannot downgrade a span-profile board.')
            definition = self._definition(state, request, board_id=board_id, parent=request.expected_revision_id)
            self.store.add_definition(db, definition)
            result = self._view(state, db, definition)
            self.store.record_request(db, state.id, request.request_id, fingerprint, result)
            return result
        return self._with(mode, handle, run, write=True)

    def _source(self, state, definition, source_id, paper_id=None):
        _, _, sources = self._dependencies(state, definition)
        source = _find(sources, source_id, 'board_source')
        if paper_id is not None and source.paper_id != paper_id:
            raise MvpError('invalid_board_reference', 'A cell reference must belong to that cell paper and retained source.')
        return source

    def _reference(self, state, definition, paper_id, request):
        source = self._source(state, definition, request.source_id, paper_id)
        if (source.version != request.source_version or source.source_sha256 != request.source_sha256
                or source.blocks_sha256 != request.blocks_sha256):
            raise MvpError('invalid_board_reference', 'The reference source version or hashes do not match this board.')
        block = _find(source.blocks, request.block_id, 'source_block')
        if request.start < 0 or request.end <= request.start or request.end > len(block.text) or request.end - request.start > MAX_INSPECTOR_CHARACTERS:
            raise MvpError('invalid_board_reference', 'The reference range is outside the canonical Unicode text.')
        identity = digest([definition.board_id, definition.revision_id, paper_id, request.model_dump(mode='json')])
        return BoardReference(**request.model_dump(), id='board-ref:' + identity, paper_id=paper_id,
                              quote=block.text[request.start:request.end], locator=block.locator)

    @staticmethod
    def _input(source, block, start, end):
        return BoardReferenceInput(source_id=source.id, source_version=source.version, source_sha256=source.source_sha256,
                                   blocks_sha256=source.blocks_sha256, block_id=block.id, start=start, end=end)

    def candidates(self, mode, handle, board_id, request: BoardCandidatesRequest):
        def run(state, db):
            fingerprint = digest({'operation': 'candidates', 'board_id': board_id, 'request': request.model_dump(mode='json')})
            prior = self.store.prior(db, state.id, request.request_id, fingerprint, BoardCandidates)
            if prior is not None:
                definition = self.store.definition(db, state.id, board_id, request.expected_revision_id)
                self._dependencies(state, definition)
                if isinstance(prior, SpanBoardCandidates):
                    self._check_span_replay(state, db, definition, request, prior)
                return prior
            definition = self._writable(state, db, board_id, request.expected_revision_id)
            field = self._cell(definition, request.paper_id, request.field_id)
            source = self._source(state, definition, next(s.source_id for s in definition.sources if s.paper_id == request.paper_id))
            profile_id = definition.retrieval_profile.get('profile_id', LEGACY_BOARD_PROFILE)
            if profile_id == SPAN_BOARD_PROFILE:
                return _SpanWork(definition.model_copy(deep=True), source.model_copy(deep=True), field.model_copy(deep=True),
                    request.model_copy(deep=True), fingerprint, new_id())
            if profile_id != LEGACY_BOARD_PROFILE:
                raise MvpError('unsupported_board_profile', 'This retained retrieval profile is not executable by this engine version.')
            identifier = new_id()
            passages, indexed, matched = self.ranker.search(field.subquestion, [source], identifier, request.top_k)
            candidates = []
            for passage in passages:
                block = _find(source.blocks, passage.anchor.block_id, 'source_block')
                end = min(len(block.text), MAX_CANDIDATE_CHARACTERS)
                reference = self._reference(state, definition, request.paper_id, self._input(source, block, 0, end))
                candidates.append(BoardCandidate(rank=passage.rank, score=passage.score, reference=reference,
                                  total_block_characters=len(block.text), omitted_characters=len(block.text) - end))
            result = BoardCandidates(id=identifier, board_id=board_id, board_revision_id=definition.revision_id,
                        paper_id=request.paper_id, field_id=field.id, field_revision_id=field.revision_id,
                        preparation_id=definition.preparation_id, source_manifest_sha256=definition.source_manifest_sha256,
                        retrieval_profile=definition.retrieval_profile, retrieval_profile_sha256=definition.retrieval_profile_sha256,
                        indexed_blocks=indexed, matched_blocks=matched, returned_count=len(candidates),
                        omitted_matched_blocks=max(0, matched - len(candidates)), candidates=candidates)
            db.execute('INSERT INTO board_candidates VALUES(?,?,?,?,?,?)', (state.id, board_id, definition.revision_id,
                        result.id, result.model_dump_json(), digest(result.model_dump(mode='json'))))
            self.store.record_request(db, state.id, request.request_id, fingerprint, result)
            return result
        result = self._with(mode, handle, run, write=True)
        if isinstance(result, _SpanWork):
            return self._span_candidates(mode, handle, board_id, result)
        return result

    def _check_span_replay(self, state, db, definition, request, result):
        row = db.execute('SELECT * FROM board_candidates WHERE workspace_id=? AND board_id=? AND definition_id=? AND id=?',
            (state.id, definition.board_id, definition.revision_id, result.id)).fetchone()
        if row is None or self.store.decode(row, BoardCandidates) != result:
            raise MvpError('board_integrity', 'The span replay does not match its immutable retrieval receipt.')
        field = self._cell(definition, request.paper_id, request.field_id)
        if (result.board_id != definition.board_id or result.board_revision_id != definition.revision_id
                or result.paper_id != request.paper_id or result.field_id != field.id or result.field_revision_id != field.revision_id
                or result.preparation_id != definition.preparation_id
                or result.retrieval_profile_sha256 != definition.retrieval_profile_sha256
                or result.source_manifest_sha256 != definition.source_manifest_sha256):
            raise MvpError('board_integrity', 'The saved span receipt belongs to different board dependencies.')
        for candidate in result.candidates:
            canonical = self._reference(state, definition, request.paper_id,
                BoardReferenceInput.model_validate(candidate.reference.model_dump(include=set(BoardReferenceInput.model_fields))))
            if candidate.reference != canonical:
                raise MvpError('board_integrity', 'The saved span quotation or locator no longer matches the retained canonical source.')

    def _span_candidates(self, mode, handle, board_id, work):
        """Rank immutable copies outside lifecycle, research and SQLite guards."""
        profile = work.definition.retrieval_profile
        from .adapters.span_retrieval import INDEX_LIMIT_CODES
        ranker = self._span()
        actual = ranker.profile()
        if any(profile.get(key) != value for key, value in actual.items()):
            raise MvpError('unsupported_board_profile', 'The retained span method or parameters do not match this installed version.')
        try:
            saved = profile['requirements_by_field']
            if set(saved) != {field.id for field in work.definition.fields}:
                raise ValueError('Missing field requirements')
            requirements = [SpanRequirement.model_validate(value) for value in saved[work.field.id]]
            if not 1 <= len(requirements) <= 3 or len({value.id for value in requirements}) != len(requirements):
                raise ValueError('Invalid requirement count')
        except (KeyError, TypeError, ValueError):
            raise MvpError('board_integrity', 'The saved span requirements do not match this board field.') from None
        try:
            raw = ranker.search(work.field.subquestion, [work.source.model_copy(deep=True)], work.run_id, work.request.top_k,
                requirements=[value.model_copy(deep=True) for value in requirements])
            # A constructed/model_copy object can bypass Pydantic validation.
            # Re-parse the complete returned tree before accepting its metadata.
            ranked = SpanRetrievalResult.model_validate(raw.model_dump(mode='python') if isinstance(raw, SpanRetrievalResult) else raw)
        except MvpError:
            raise
        except (ValidationError, ValueError, TypeError):
            raise MvpError('board_integrity', 'Span retrieval returned invalid bounded quotation or metadata output.') from None
        blocks = work.source.blocks
        block_ids = {block.id for block in blocks}
        total_characters = sum(len(block.text) for block in blocks)
        parameters = profile['parameters']
        codes = {value.code for value in ranked.messages}
        incomplete = bool(ranked.unindexed_characters or INDEX_LIMIT_CODES.intersection(codes))
        if (len(block_ids) != len(blocks)
                or ranked.total_source_blocks != len(blocks) or ranked.total_source_characters != total_characters
                or ranked.indexed_blocks > min(len(blocks), parameters['max_source_blocks'])
                or ranked.unindexed_blocks != len(blocks)-ranked.indexed_blocks
                or ranked.indexed_windows > parameters['max_windows']
                or ranked.indexed_blocks > ranked.indexed_windows
                or ranked.matched_windows > ranked.indexed_windows
                or ranked.matched_blocks > min(ranked.indexed_blocks, ranked.matched_windows)
                or not 0 <= ranked.unindexed_characters <= total_characters
                or total_characters-ranked.unindexed_characters > parameters['max_source_characters']
                or ranked.partially_indexed_blocks > ranked.indexed_blocks
                or ranked.skipped_blank_blocks > sum(not block.text.strip() for block in blocks)
                or len(ranked.matched_block_ids) != ranked.matched_blocks
                or len(set(ranked.matched_block_ids)) != ranked.matched_blocks
                or not set(ranked.matched_block_ids) <= block_ids
                or any(value.block_id not in ranked.matched_block_ids for value in ranked.selections)
                or any(value.index_incomplete != incomplete for value in ranked.requirement_statuses)
                or len(ranked.messages) > parameters['max_messages']):
            raise MvpError('board_integrity', 'Span retrieval scope statistics do not match the captured canonical source and index bounds.')

        def publish(state, db):
            prior = self.store.prior(db, state.id, work.request.request_id, work.fingerprint, BoardCandidates)
            if prior is not None:
                original = self.store.definition(db, state.id, board_id, work.request.expected_revision_id)
                self._dependencies(state, original)
                self._check_span_replay(state, db, original, work.request, prior)
                return prior
            definition = self._writable(state, db, board_id, work.request.expected_revision_id)
            if definition != work.definition:
                raise MvpError('stale_board_revision', 'The captured definition changed before span publication.')
            field = self._cell(definition, work.request.paper_id, work.request.field_id)
            source = self._source(state, definition, work.source.id, work.request.paper_id)
            if source != work.source or ranked.run_id != work.run_id or ranked.profile_id != SPAN_BOARD_PROFILE:
                raise MvpError('board_integrity', 'Span retrieval does not match the exact captured source or profile.')
            if [value.requirement for value in ranked.requirement_statuses] != requirements or len(ranked.selections) > work.request.top_k:
                raise MvpError('board_integrity', 'Span retrieval changed the explicit field requirements or candidate budget.')
            candidates, identities = [], set()
            for rank, selection in enumerate(ranked.selections, 1):
                if selection.source_id != source.id or selection.paper_id != work.request.paper_id:
                    raise MvpError('invalid_board_reference', 'A retrieved span must belong to this exact report and source.')
                block = _find(source.blocks, selection.block_id, 'source_block')
                reference = self._reference(state, definition, work.request.paper_id,
                    self._input(source, block, selection.start, selection.end))
                if reference.quote != selection.quote or reference.id in identities:
                    raise MvpError('invalid_board_reference', 'The retrieved quotation must match one unique canonical source range.')
                identities.add(reference.id)
                candidates.append(SpanBoardCandidate(rank=rank, score=selection.score, reference=reference,
                    total_block_characters=len(block.text), omitted_characters=len(block.text)-len(reference.quote),
                    omitted_before=reference.start, omitted_after=len(block.text)-reference.end,
                    matched_requirement_ids=selection.matched_requirement_ids, budget_tokens=selection.budget_tokens,
                    hard_boundary_clipped=selection.hard_boundary_clipped))
            statuses = {'selected_lexical_match': 'candidates_selected', 'matched_but_not_selected': 'candidates_not_selected',
                        'no_lexical_match_in_indexed_text': 'no_lexical_match', 'no_query_tokens': 'no_query_tokens'}
            result = SpanBoardCandidates(id=work.run_id, board_id=board_id, board_revision_id=definition.revision_id,
                paper_id=work.request.paper_id, field_id=field.id, field_revision_id=field.revision_id,
                preparation_id=definition.preparation_id, source_manifest_sha256=definition.source_manifest_sha256,
                retrieval_profile=profile, retrieval_profile_sha256=definition.retrieval_profile_sha256,
                indexed_blocks=ranked.indexed_blocks, matched_blocks=ranked.matched_blocks,
                returned_count=len(candidates), omitted_matched_blocks=max(0, ranked.matched_blocks-len({value.reference.block_id for value in candidates})),
                candidates=candidates, requirements=requirements,
                requirement_matches=[SpanRequirementMatch(requirement_id=value.requirement.id,
                    matched_windows=value.matched_windows, selected_windows=value.selected_spans,
                    state=statuses[value.status], index_incomplete=value.index_incomplete) for value in ranked.requirement_statuses],
                indexed_windows=ranked.indexed_windows, matched_windows=ranked.matched_windows,
                omitted_matched_windows=ranked.matched_windows-len(candidates), total_source_blocks=ranked.total_source_blocks,
                unindexed_source_blocks=ranked.total_source_blocks-ranked.indexed_blocks,
                partially_indexed_blocks=ranked.partially_indexed_blocks, skipped_blank_blocks=ranked.skipped_blank_blocks,
                total_source_characters=ranked.total_source_characters,
                indexed_source_characters=ranked.total_source_characters-ranked.unindexed_characters,
                unindexed_source_characters=ranked.unindexed_characters, delivered_characters=ranked.delivered_characters,
                delivered_budget_tokens=ranked.delivered_tokens, budget_tokenizer_id=profile['parameters']['budget_tokenizer_id'],
                index_limits=[value.code for value in ranked.messages if value.code in INDEX_LIMIT_CODES],
                warnings=[value.message for value in ranked.messages], elapsed_seconds=ranked.elapsed_seconds)
            db.execute('INSERT INTO board_candidates VALUES(?,?,?,?,?,?)', (state.id, board_id, definition.revision_id,
                result.id, result.model_dump_json(), digest(result.model_dump(mode='json'))))
            self.store.record_request(db, state.id, work.request.request_id, work.fingerprint, result)
            return result
        try:
            return self._with(mode, handle, publish, write=True)
        except MvpError:
            raise
        except (ValidationError, ValueError, TypeError):
            # The sidecar transaction has rolled back before translating this
            # invalid internal result into the safe domain/API failure contract.
            raise MvpError('board_integrity', 'Span retrieval metadata does not describe valid exact canonical candidates.') from None

    def get_draft(self, mode, handle, board_id, paper_id, field_id, revision_id=None):
        def run(state, db):
            definition = self.store.definition(db, state.id, board_id, revision_id)
            self._dependencies(state, definition)
            self._cell(definition, paper_id, field_id)
            return self.store.draft(db, definition, paper_id, field_id)
        return self._with(mode, handle, run)

    def put_draft(self, mode, handle, board_id, paper_id, field_id, request: BoardDraftPutRequest):
        def run(state, db):
            definition = self._writable(state, db, board_id, request.expected_revision_id)
            self._cell(definition, paper_id, field_id)
            current = self.store.draft(db, definition, paper_id, field_id)
            if request.version != current.version:
                raise MvpError('stale_board_draft', 'A newer saved cell draft exists. Your edits were not overwritten; compare with the saved draft.')
            if request.expected_cell_head_id != self.store.cell_head(db, definition, paper_id, field_id):
                raise MvpError('stale_board_cell', 'This cell has a newer submission. Start an explicit revision from its current head.')
            # Drafts may be incomplete human judgments, but source anchors are
            # always typed and mechanically valid. No client quote is accepted.
            for reference in [*request.data.references, *request.data.inspected_ranges]:
                self._reference(state, definition, paper_id, reference)
            result = BoardCellDraft(board_id=board_id, board_revision_id=definition.revision_id, paper_id=paper_id,
                     field_id=field_id, version=current.version + 1, expected_cell_head_id=request.expected_cell_head_id,
                     data=request.data, updated_at=now())
            self.store.put_draft(db, definition, result)
            return result
        return self._with(mode, handle, run, write=True)

    def submit(self, mode, handle, board_id, request: BoardSubmitRequest):
        def run(state, db):
            fingerprint = digest({'operation': 'submit', 'board_id': board_id, 'request': request.model_dump(mode='json')})
            prior = self.store.prior(db, state.id, request.request_id, fingerprint, BoardCellRevision)
            if prior is not None:
                self._dependencies(state, self.store.definition(db, state.id, board_id, request.expected_revision_id))
                return prior
            definition = self._writable(state, db, board_id, request.expected_revision_id)
            field = self._cell(definition, request.paper_id, request.field_id)
            head = self.store.cell_head(db, definition, request.paper_id, request.field_id)
            if request.supersedes_id != head:
                raise MvpError('stale_board_cell', 'Submission must explicitly supersede the current cell head.')
            draft = self.store.draft(db, definition, request.paper_id, request.field_id)
            if draft.version != request.draft_version or draft.expected_cell_head_id != head:
                raise MvpError('stale_board_draft', 'The cell draft changed or was submitted already. Your saved edits were preserved.')
            data = draft.data
            refs = [self._reference(state, definition, request.paper_id, ref) for ref in data.references]
            inspected = [self._reference(state, definition, request.paper_id, ref) for ref in data.inspected_ranges]
            if len({ref.id for ref in refs}) != len(refs) or len({ref.id for ref in inspected}) != len(inspected):
                raise MvpError('invalid_board_cell', 'Reference and inspected ranges must be unique.')
            if any(not any(scope.source_id == ref.source_id and scope.block_id == ref.block_id and scope.start <= ref.start and scope.end >= ref.end for scope in inspected) for ref in refs):
                raise MvpError('invalid_board_cell', 'Each cited range must be contained in the declared inspected material.')
            if data.value is not None and not data.value.strip():
                raise MvpError('invalid_board_cell', 'Use an explicit null for a missing value, rather than blank text.')
            if data.value is None and (not data.reason.strip() or not data.missing_information.strip()):
                raise MvpError('invalid_board_cell', 'A missing value requires an explicit scope, reason and missing-information statement.')
            if data.scope_result == 'value_found' and not inspected:
                raise MvpError('invalid_board_cell', 'Value-found requires explicit inspected material.')
            if data.semantic_assessment != 'unassessed' and not data.reason.strip():
                raise MvpError('invalid_board_cell', 'A human support judgment requires a reason.')
            if data.semantic_assessment == 'human_supported' and (not data.value or not data.value.strip() or not refs or data.scope_result != 'value_found'):
                raise MvpError('invalid_board_cell', 'Human-supported requires a value, reason, valid reference and declared value-found inspection scope.')
            if data.scope_result == 'not_found_in_inspected_material' and (not inspected or data.value is not None or not data.reason.strip() or not data.missing_information.strip()):
                raise MvpError('invalid_board_cell', 'Not found requires a null value, explicit inspected material, missing information and reason; it does not establish absence from a whole paper.')
            if data.value is None and data.scope_result == 'value_found':
                raise MvpError('invalid_board_cell', 'Value-found requires an explicit value.')
            if data.value is None and data.semantic_assessment != 'unassessed' and not data.missing_information.strip():
                raise MvpError('invalid_board_cell', 'Missing values require explicit missing information.')
            cell = BoardCellRevision(board_id=board_id, board_revision_id=definition.revision_id,
                    field_revision_id=field.revision_id, paper_id=request.paper_id, field_id=field.id,
                    supersedes_id=head, value=data.value, references=refs, inspected_ranges=inspected,
                    semantic_assessment=data.semantic_assessment, scope_result=data.scope_result,
                    missing_information=data.missing_information, reason=data.reason,
                    reference_integrity='checked' if refs else 'not_applicable')
            self.store.add_cell(db, definition, cell)
            self.store.record_request(db, state.id, request.request_id, fingerprint, cell)
            return cell
        return self._with(mode, handle, run, write=True)

    def history(self, mode, handle, board_id, paper_id, field_id, revision_id=None, offset=0, limit=20):
        if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 50:
            raise MvpError('invalid_board_pagination', 'Use a nonnegative offset and history limit from 1 to 50.')
        def run(state, db):
            definition = self.store.definition(db, state.id, board_id, revision_id)
            self._dependencies(state, definition)
            self._cell(definition, paper_id, field_id)
            key = self.store.cell_key(definition, paper_id, field_id)
            where = 'workspace_id=? AND board_id=? AND definition_id=? AND paper_id=? AND field_id=?'
            total = db.execute('SELECT COUNT(*) FROM board_cells WHERE ' + where, key).fetchone()[0]
            rows = db.execute('SELECT * FROM board_cells WHERE ' + where + ' ORDER BY rowid DESC LIMIT ? OFFSET ?', (*key, limit, offset))
            return BoardCellHistory(items=[self.store.decode(row, BoardCellRevision) for row in rows], offset=offset, limit=limit, total=total)
        return self._with(mode, handle, run)

    def _chunk(self, state, definition, source, block, start):
        if not block.text or type(start) is not int or start < 0 or start >= len(block.text):
            raise MvpError('invalid_board_pagination', 'Choose a start offset within the canonical source block.')
        end = min(len(block.text), start + MAX_INSPECTOR_CHARACTERS)
        ref = self._reference(state, definition, source.paper_id, self._input(source, block, start, end))
        return BoardBlockChunk(source_id=source.id, paper_id=source.paper_id, block_id=block.id, ordinal=block.ordinal,
                  locator=block.locator, start=start, end=end, total_characters=len(block.text), text=block.text[start:end],
                  omitted_before=start, omitted_after=len(block.text) - end, reference=ref)

    def blocks(self, mode, handle, board_id, source_id, revision_id=None, offset=0, limit=1, block_id=None, start=0):
        if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 3:
            raise MvpError('invalid_board_pagination', 'Use a nonnegative block offset and limit from 1 to 3.')
        def run(state, db):
            definition = self.store.definition(db, state.id, board_id, revision_id)
            source = self._source(state, definition, source_id)
            nonempty = [block for block in source.blocks if block.text]
            chosen = [_find(nonempty, block_id, 'source_block')] if block_id else nonempty[offset:offset + limit]
            effective_offset = nonempty.index(chosen[0]) if block_id else offset
            chunks = [self._chunk(state, definition, source, block, start if index == 0 else 0) for index, block in enumerate(chosen)]
            freshness, _ = self._freshness(state, db, definition)
            binding = next(item for item in definition.sources if item.source_id == source_id)
            return BoardSourceInspection(board_revision_id=definition.revision_id, source=binding, freshness=freshness,
                       blocks=chunks, offset=effective_offset, limit=limit, total_blocks=len(nonempty))
        return self._with(mode, handle, run)

    def reference_context(self, mode, handle, board_id, reference_id, revision_id=None):
        def run(state, db):
            definition = self.store.definition(db, state.id, board_id, revision_id)
            found = None
            for table, model in (('board_candidates', BoardCandidates), ('board_cells', BoardCellRevision)):
                for row in db.execute('SELECT * FROM ' + table + ' WHERE workspace_id=? AND board_id=? AND definition_id=?', (state.id, board_id, definition.revision_id)):
                    item = self.store.decode(row, model)
                    refs = [candidate.reference for candidate in item.candidates] if table == 'board_candidates' else [*item.references, *item.inspected_ranges]
                    found = next((ref for ref in refs if ref.id == reference_id), None)
                    if found:
                        break
                if found:
                    break
            if found is None:
                raise unavailable('board_reference')
            reference = self._reference(state, definition, found.paper_id, BoardReferenceInput.model_validate(found.model_dump(include=set(BoardReferenceInput.model_fields))))
            source = self._source(state, definition, reference.source_id, reference.paper_id)
            block = _find(source.blocks, reference.block_id, 'source_block')
            freshness, _ = self._freshness(state, db, definition)
            return BoardReferenceContext(reference=reference, paper=next(p for p in definition.papers if p.id == reference.paper_id),
                     source=next(s for s in definition.sources if s.source_id == source.id), freshness=freshness,
                     block=self._chunk(state, definition, source, block, reference.start))
        return self._with(mode, handle, run)

    def export(self, mode, handle, board_id, revision_id=None, history=False):
        def run(state, db):
            definition = self.store.definition(db, state.id, board_id, revision_id)
            view = self._view(state, db, definition)
            all_definitions = [self.store.decode(row, BoardRevision) for row in db.execute(
                'SELECT * FROM board_definitions WHERE workspace_id=? AND board_id=? ORDER BY rowid', (state.id, board_id))]
            collection_board = any(isinstance(item, CollectionBoardRevision) for item in all_definitions)
            table_schema = 'mvp.collection-board-table.v2' if collection_board else 'mvp.board-table.v1'
            rows = []
            for item in view.cells:
                paper = next(p for p in definition.papers if p.id == item.paper_id)
                field = next(f for f in definition.fields if f.id == item.field_id)
                source = next(s for s in definition.sources if s.paper_id == item.paper_id)
                cell = self.store.decode(db.execute('SELECT * FROM board_cells WHERE workspace_id=? AND id=?', (state.id, item.head.id)).fetchone(), BoardCellRevision) if item.head else None
                rows.append({'schema_version': table_schema, 'board_id': board_id, 'board_revision_id': definition.revision_id,
                    'search_id': definition.search_id, 'search_sha256': definition.search_sha256, 'question': definition.question,
                    'preparation_id': definition.preparation_id, 'source_manifest_sha256': definition.source_manifest_sha256,
                    'paper_id': paper.id, 'paper_title': paper.title, 'pmid': paper.pmid, 'doi': paper.doi,
                    'authors': paper.authors, 'year': paper.year, 'source_id': source.source_id, 'source_type': source.source_type,
                    'source_status': source.status, 'source_sha256': source.source_sha256, 'blocks_sha256': source.blocks_sha256,
                    'field_id': field.id, 'field_revision_id': field.revision_id, 'field_label': field.label, 'field_subquestion': field.subquestion,
                    'cell_revision_id': cell.id if cell else None, 'supersedes_id': cell.supersedes_id if cell else None,
                    'value': cell.value if cell else None, 'semantic_assessment': cell.semantic_assessment if cell else 'unassessed',
                    'scope_result': cell.scope_result if cell else 'not_assessed', 'reference_integrity': cell.reference_integrity if cell else 'not_applicable',
                    'missing_information': cell.missing_information if cell else '', 'reason': cell.reason if cell else '',
                    'references': [ref.model_dump(mode='json') for ref in cell.references] if cell else [],
                    'inspected_ranges': [ref.model_dump(mode='json') for ref in cell.inspected_ranges] if cell else [],
                    'freshness': view.freshness, 'review_state': cell.review_state if cell else 'not_assessed',
                    'producer': cell.producer if cell else None, 'created_at': cell.created_at if cell else None})
                if collection_board:
                    rows[-1].update({
                        'collection_ref': definition.collection_ref.model_dump(mode='json') if isinstance(definition, CollectionBoardRevision) else None,
                        'member_snapshot_sha256': definition.member_snapshot_sha256 if isinstance(definition, CollectionBoardRevision) else None})
            definitions = [definition]
            if history:
                definitions = all_definitions
                for old in definitions:
                    self._dependencies(state, old)
            included = {item.revision_id for item in definitions}
            cells = [self.store.decode(row, BoardCellRevision) for row in db.execute('SELECT * FROM board_cells WHERE workspace_id=? AND board_id=? ORDER BY rowid', (state.id, board_id)) if row['definition_id'] in included]
            candidate_runs = [self.store.decode(row, BoardCandidates) for row in db.execute('SELECT * FROM board_candidates WHERE workspace_id=? AND board_id=? ORDER BY rowid', (state.id, board_id)) if row['definition_id'] in included]
            audit = {'schema_version': 'mvp.collection-board-audit.v2' if collection_board else 'mvp.board-audit.v1', 'table_schema_version': table_schema,
                     'board_id': board_id, 'selected_revision_id': definition.revision_id, 'freshness': view.freshness,
                     'definitions': [item.model_dump(mode='json') for item in definitions], 'table': rows,
                     'cell_revisions': [item.model_dump(mode='json') for item in cells],
                     'candidate_runs': [item.model_dump(mode='json') for item in candidate_runs],
                     'history_included': history, 'offset_convention': 'half-open-unicode-codepoints',
                     'review_state': 'single_human_self_declared_not_independently_verified'}
            export_model = CollectionBoardExport if collection_board else BoardExport
            return export_model(csv_text=_csv(rows, list(rows[0]) if rows else []), json_text=json.dumps(audit, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n')
        return self._with(mode, handle, run)

    def delete_workspace(self, workspace_id):
        self.store.delete_workspace(workspace_id)
