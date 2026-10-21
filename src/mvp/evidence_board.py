"""Manual comparison boards over immutable retained preparation dependencies.

No model/provider calls, global selection mutations or existing export changes.
Mutation lock order is lifecycle -> research snapshot -> short sidecar transaction.
"""
from __future__ import annotations
import json
from .board_contracts import *
from .contracts import digest, new_id, now
from .adapters.board_storage import BoardStore, unavailable
from .adapters.retrieval import LexicalRetrieval
from .ports import MvpError
from .service import _assert_source_integrity, _manifest, _find
from src.review.exporters import _csv


class EvidenceBoardService:
    def __init__(self, registry, service_for, store: BoardStore):
        self.registry, self.service_for, self.store = registry, service_for, store
        self.ranker = LexicalRetrieval()

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

    def _profile(self):
        return {'method': self.ranker.method, 'method_version': 'lit-rev-engine.project-retrieval.v3.bm25_context_blocks',
                'parameters': self.ranker.parameters, 'scope': 'one-paper-one-field', 'candidate_text_limit': MAX_CANDIDATE_CHARACTERS}

    @staticmethod
    def _summary(definition):
        return BoardSummary(board_id=definition.board_id, revision_id=definition.revision_id, question=definition.question,
                            paper_count=len(definition.paper_ids), field_count=len(definition.fields), created_at=definition.created_at)

    @staticmethod
    def _cell(definition, paper_id, field_id):
        if paper_id not in definition.paper_ids:
            raise unavailable('board_paper')
        field = next((field for field in definition.fields if field.id == field_id), None)
        if field is None:
            raise unavailable('board_field')
        return field

    def _dependencies(self, state, definition):
        search = _find(state.searches, definition.search_id, 'search')
        preparation = _find(state.preparations, definition.preparation_id, 'preparation')
        if (digest(search.model_dump(mode='json')) != definition.search_sha256 or preparation.search_id != definition.search_id
                or preparation.source_revision != definition.source_revision):
            raise MvpError('board_integrity', 'The board original search or preparation binding changed.')
        sources = [_find(preparation.sources, source.source_id, 'source') for source in definition.sources]
        _assert_source_integrity(sources)
        if digest(_manifest(sources)) != definition.source_manifest_sha256:
            raise MvpError('board_integrity', 'The board retained source manifest changed.')
        if [source.paper_id for source in sources] != definition.paper_ids:
            raise MvpError('board_integrity', 'The board source ownership changed.')
        return search, preparation, sources

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

    def _definition(self, state, request, *, board_id=None, parent=None):
        preparation = _find(state.preparations, request.preparation_id, 'preparation')
        if not state.preparations or state.preparations[-1].id != preparation.id or state.source_revision != preparation.source_revision:
            raise MvpError('stale_source_revision', 'Select the current retained preparation for a new board definition.')
        search = _find(state.searches, preparation.search_id, 'search')
        sources, papers = [], []
        for paper_id in request.paper_ids:
            if paper_id not in preparation.selected_paper_ids:
                raise unavailable('prepared_paper')
            paper = _find(search.papers, paper_id, 'paper')
            source = next((source for source in preparation.sources if source.paper_id == paper_id), None)
            if source is None:
                raise unavailable('prepared_source')
            sources.append(source)
            papers.append(BoardPaper.model_validate(paper.model_dump(exclude={'abstract'})))
        _assert_source_integrity(sources)
        bindings = [BoardSourceBinding(source_id=s.id, paper_id=s.paper_id, version=s.version,
                    source_sha256=s.source_sha256, blocks_sha256=s.blocks_sha256, parser_id=s.parser_id,
                    source_type=s.source_type, status=s.status, block_count=len(s.blocks)) for s in sources]
        profile = self._profile()
        return BoardRevision(board_id=board_id or new_id(), workspace_id=state.id,
                parent_revision_id=parent, search_id=search.id, search_sha256=digest(search.model_dump(mode='json')),
                question=request.question, question_sha256=digest(request.question), preparation_id=preparation.id,
                source_revision=preparation.source_revision, source_manifest_sha256=digest(_manifest(sources)),
                sources=bindings, papers=papers, paper_ids=request.paper_ids,
                fields=[BoardField(**f.model_dump()) for f in request.fields], retrieval_profile=profile,
                retrieval_profile_sha256=digest(profile))

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
                self._dependencies(state, self.store.definition(db, state.id, board_id, request.expected_revision_id))
                return prior
            definition = self._writable(state, db, board_id, request.expected_revision_id)
            field = self._cell(definition, request.paper_id, request.field_id)
            source = self._source(state, definition, next(s.source_id for s in definition.sources if s.paper_id == request.paper_id))
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
        return self._with(mode, handle, run, write=True)

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
            rows = []
            for item in view.cells:
                paper = next(p for p in definition.papers if p.id == item.paper_id)
                field = next(f for f in definition.fields if f.id == item.field_id)
                source = next(s for s in definition.sources if s.paper_id == item.paper_id)
                cell = self.store.decode(db.execute('SELECT * FROM board_cells WHERE workspace_id=? AND id=?', (state.id, item.head.id)).fetchone(), BoardCellRevision) if item.head else None
                rows.append({'schema_version': 'mvp.board-table.v1', 'board_id': board_id, 'board_revision_id': definition.revision_id,
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
            definitions = [definition]
            if history:
                definitions = [self.store.decode(row, BoardRevision) for row in db.execute('SELECT * FROM board_definitions WHERE workspace_id=? AND board_id=? ORDER BY rowid', (state.id, board_id))]
                for old in definitions:
                    self._dependencies(state, old)
            included = {item.revision_id for item in definitions}
            cells = [self.store.decode(row, BoardCellRevision) for row in db.execute('SELECT * FROM board_cells WHERE workspace_id=? AND board_id=? ORDER BY rowid', (state.id, board_id)) if row['definition_id'] in included]
            candidate_runs = [self.store.decode(row, BoardCandidates) for row in db.execute('SELECT * FROM board_candidates WHERE workspace_id=? AND board_id=? ORDER BY rowid', (state.id, board_id)) if row['definition_id'] in included]
            audit = {'schema_version': 'mvp.board-audit.v1', 'table_schema_version': 'mvp.board-table.v1',
                     'board_id': board_id, 'selected_revision_id': definition.revision_id, 'freshness': view.freshness,
                     'definitions': [item.model_dump(mode='json') for item in definitions], 'table': rows,
                     'cell_revisions': [item.model_dump(mode='json') for item in cells],
                     'candidate_runs': [item.model_dump(mode='json') for item in candidate_runs],
                     'history_included': history, 'offset_convention': 'half-open-unicode-codepoints',
                     'review_state': 'single_human_self_declared_not_independently_verified'}
            return BoardExport(csv_text=_csv(rows, list(rows[0]) if rows else []), json_text=json.dumps(audit, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n')
        return self._with(mode, handle, run)

    def delete_workspace(self, workspace_id):
        self.store.delete_workspace(workspace_id)
