"""Optional evidence-bound suggestions beside the manual comparison board.

Slow generation never holds workspace, lifecycle or SQLite mutation locks.
Publication is all-or-nothing after exact snapshot and cell CAS revalidation.
Quotes are mechanically checked; scientific support remains unassessed.
"""
from __future__ import annotations
import json
import queue
import threading
import time
from datetime import datetime, timezone
from pydantic import ValidationError
from .proposal_contracts import *
from .board_contracts import (BoardCellData, BoardCellDraft, BoardReferenceInput, BoardReferenceContext,
                              BoardCandidatesRequest)
from .contracts import canonical, digest, now
from .adapters.proposal_storage import ProposalStore
from .adapters.board_storage import unavailable
from .ports import MvpError
from .service import _find

_SAFE_FAILURES = {
    'proposal_invalid_output': 'The model output did not satisfy the typed cell and exact-evidence contract. No proposals were published.',
    'proposal_provider_failure': 'The configured generation adapter failed. No proposals were published; this request is not automatically retried.',
    'proposal_timeout': 'The bounded generation runtime expired. No proposals were published; an unfinished adapter call cannot publish later.',
    'proposal_stale_inputs': 'The board, sources, cell submission or saved draft changed during generation. No proposals were published.',
    'proposal_context_limit': 'The retained evidence packet exceeded its bounded input limit. No proposals were published.',
    'proposal_storage_limit': 'The bounded comparison storage limit prevented publication. No proposals were published.',
}

class CellProposalService:
    def __init__(self, boards, adapter=None, *, max_runtime_seconds=MAX_RUN_SECONDS):
        self.boards, self.adapter = boards, adapter
        self.store = ProposalStore(boards.store)
        self.max_runtime_seconds = min(MAX_RUN_SECONDS, max(0.01, float(max_runtime_seconds)))
        self._run_gate = threading.Lock()
        self._call_gate = threading.Lock()

    def _profile(self):
        profile = getattr(self.adapter, 'profile', None)
        if hasattr(profile, 'model_dump'):
            profile = profile.model_dump(mode='json')
        if not isinstance(profile, dict) or not profile or len(canonical(profile).encode('utf-8')) > 4000:
            raise MvpError('proposal_configuration', 'Configure one bounded, versioned generation profile before enabling proposals.')
        return json.loads(canonical(profile))

    def capabilities(self):
        enabled = self.adapter is not None and getattr(self.adapter, 'enabled', False) is True
        profile = self._profile() if enabled else None
        return ProposalCapability(enabled=enabled, model_profile=profile,
            reason='One configured local generation adapter is enabled. Suggestions require explicit researcher review.' if enabled else ProposalCapability().reason,
            max_runtime_seconds=self.max_runtime_seconds)

    def _run(self, mode, handle, callback, *, write=False):
        return self.boards._with(mode, handle, callback, write=write)

    def _checked_run(self, state, db, board_id, run_id):
        run = self.store.run(db, state.id, board_id, run_id)
        definition = self.boards.store.definition(db, state.id, board_id, run.board_revision_id)
        self.boards._dependencies(state, definition)
        return run, definition

    def _baseline(self, db, definition, paper_id, field_id):
        draft = self.boards.store.draft(db, definition, paper_id, field_id)
        return ProposalCellBaseline(paper_id=paper_id, field_id=field_id,
            head_id=self.boards.store.cell_head(db, definition, paper_id, field_id), draft_version=draft.version,
            draft_sha256=digest(draft.model_dump(mode='json')))

    def _unchanged(self, state, db, run):
        if (getattr(self.adapter, 'enabled', False) is not True or self._profile() != run.model_profile
                or getattr(self.adapter, 'prompt_version', PROMPT_VERSION) != run.prompt_version):
            raise MvpError('proposal_stale_inputs', _SAFE_FAILURES['proposal_stale_inputs'])
        definition = self.boards._writable(state, db, run.board_id, run.board_revision_id)
        if (definition.source_manifest_sha256 != run.source_manifest_sha256 or
                definition.retrieval_profile_sha256 != run.retrieval_profile_sha256):
            raise MvpError('proposal_stale_inputs', _SAFE_FAILURES['proposal_stale_inputs'])
        for baseline in run.baselines:
            if self._baseline(db, definition, baseline.paper_id, baseline.field_id) != baseline:
                raise MvpError('proposal_stale_inputs', _SAFE_FAILURES['proposal_stale_inputs'])
        return definition

    def generate(self, mode, handle, board_id, request: ProposalGenerateRequest):
        # Replays are checked even while disabled or another run is in flight.
        fingerprint = digest({'operation': 'proposal-generate', 'board_id': board_id, 'request': request.model_dump(mode='json')})
        def replay(state, db):
            prior = self.store.prior_run(db, state.id, board_id, request.request_id, fingerprint)
            if prior is not None:
                self.boards._dependencies(state, self.boards.store.definition(db, state.id, board_id, prior.board_revision_id))
                return self._decorate_run(db, state.id, prior)
        prior = self._run(mode, handle, replay)
        if prior is not None:
            return prior
        if not self.capabilities().enabled:
            raise MvpError('proposal_generation_disabled', 'AI cell proposals are disabled. The manual comparison workflow remains available.')
        if not self._run_gate.acquire(blocking=False):
            raise MvpError('proposal_busy', 'Another bounded proposal run is in progress. No additional call was started.')
        try:
            if self._call_gate.locked():
                raise MvpError('proposal_busy', 'An earlier timed-out adapter call is still finishing. No additional call was started.')
            started = time.monotonic()
            profile = self._profile()
            prompt_version = getattr(self.adapter, 'prompt_version', PROMPT_VERSION)
            if prompt_version != PROMPT_VERSION:
                raise MvpError('proposal_configuration', 'The adapter prompt version does not match this proposal contract.')
            def reserve(state, db):
                prior = self.store.prior_run(db, state.id, board_id, request.request_id, fingerprint)
                if prior is not None:
                    self.boards._dependencies(state, self.boards.store.definition(db, state.id, board_id, prior.board_revision_id))
                    return prior, None
                definition = self.boards._writable(state, db, board_id, request.expected_revision_id)
                for paper_id in request.paper_ids:
                    for field_id in request.field_ids:
                        self.boards._cell(definition, paper_id, field_id)
                run = ProposalRun(board_id=board_id, board_revision_id=definition.revision_id,
                    request_id=request.request_id, request_sha256=digest(request.model_dump(mode='json')),
                    paper_ids=request.paper_ids, field_ids=request.field_ids, source_manifest_sha256=definition.source_manifest_sha256,
                    retrieval_profile_sha256=definition.retrieval_profile_sha256, prompt_version=prompt_version,
                    model_profile=profile, model_profile_sha256=digest(profile),
                    baselines=[self._baseline(db, definition, p, f) for p in request.paper_ids for f in request.field_ids])
                self.store.reserve(db, state.id, run, fingerprint)
                return run, definition
            run, definition = self._run(mode, handle, reserve, write=True)
            if definition is None:
                return run
            try:
                from .adapters.cell_generation import build_packet
                packets = []
                for paper_id in request.paper_ids:
                    self._deadline(started)
                    candidates = [self.boards.candidates(mode, handle, board_id, BoardCandidatesRequest(
                        request_id=f'proposal:{run.id}:{index}:{len(packets)}', expected_revision_id=definition.revision_id,
                        paper_id=paper_id, field_id=field_id)) for index, field_id in enumerate(request.field_ids)]
                    packets.append(build_packet(definition, paper_id, candidates))
                run = run.model_copy(update={'packets': packets, 'calls': [ProposalCallReceipt(paper_id=p.paper_id,
                    packet_sha256=digest(p.model_dump(mode='json')), request_sha256=digest({'packet': p.model_dump(mode='json'),
                        'prompt_version': run.prompt_version, 'model_profile_sha256': run.model_profile_sha256})) for p in packets]})
                def save_inputs(state, db):
                    current_definition = self._unchanged(state, db, run)
                    for packet in run.packets:
                        for evidence in packet.evidence:
                            exact = self.boards._reference(state, current_definition, packet.paper_id,
                                BoardReferenceInput.model_validate(evidence.reference.model_dump(include=set(BoardReferenceInput.model_fields))))
                            if exact != evidence.reference:
                                raise MvpError('proposal_invalid_output', _SAFE_FAILURES['proposal_invalid_output'])
                    self.store.put_run(db, state.id, run)
                self._run(mode, handle, save_inputs, write=True)
                outputs = []
                for index, packet in enumerate(packets):
                    remaining = self._deadline(started)
                    before = time.monotonic()
                    receipt = run.calls[index].model_copy(update={'outcome': 'running'})
                    run = self._receipt(run, index, receipt)
                    self._persist_running(mode, handle, run)
                    try:
                        result = self._call(packet, min(10.0, remaining))
                    except MvpError as exc:
                        outcome = 'timeout' if exc.code == 'proposal_timeout' else ('invalid_output' if exc.code == 'proposal_invalid_output' else 'provider_failure')
                        run = self._receipt(run, index, receipt.model_copy(update={'outcome': outcome, 'elapsed_seconds': time.monotonic() - before}))
                        raise
                    output_bytes = len(result.output_text.encode('utf-8'))
                    receipt = receipt.model_copy(update={'output_sha256': digest(result.output_text), 'output_bytes': output_bytes,
                        'usage': result.usage, 'elapsed_seconds': time.monotonic() - before})
                    try:
                        if output_bytes > MAX_OUTPUT_BYTES:
                            raise ValueError('oversized output')
                        output = self._parse(result.output_text)
                        # Structural and ownership checks happen before another call.
                        self._validate_packet_output(packet, output)
                    except (ValueError, ValidationError, TypeError, MvpError):
                        run = self._receipt(run, index, receipt.model_copy(update={'outcome': 'invalid_output'}))
                        raise MvpError('proposal_invalid_output', _SAFE_FAILURES['proposal_invalid_output'])
                    outputs.append(output)
                    run = self._receipt(run, index, receipt.model_copy(update={'outcome': 'succeeded'}))
                    self._persist_running(mode, handle, run)
                self._deadline(started)
                def publish(state, db):
                    self._deadline(started)
                    definition = self._unchanged(state, db, run)
                    proposals = []
                    for packet, output in zip(packets, outputs):
                        for cell in output.cells:
                            refs = self._references(state, definition, packet, cell)
                            field = self.boards._cell(definition, packet.paper_id, cell.field_id)
                            field_packet = next(f for f in packet.fields if f.field_id == cell.field_id)
                            proposal = CellProposal(run_id=run.id, board_id=board_id, board_revision_id=definition.revision_id,
                                field_id=cell.field_id, field_revision_id=field.revision_id, paper_id=packet.paper_id,
                                source_manifest_sha256=definition.source_manifest_sha256,
                                source_bindings=[s.model_dump(mode='json') for s in definition.sources if s.paper_id == packet.paper_id],
                                retrieval_input_sha256=digest({'field': field.model_dump(mode='json'), 'packet': packet.model_dump(mode='json'),
                                    'retrieval_profile_sha256': definition.retrieval_profile_sha256}),
                                candidate_run_ids=[field_packet.candidate_run_id], packet_sha256=digest(packet.model_dump(mode='json')),
                                prompt_version=run.prompt_version, model_profile=run.model_profile, model_profile_sha256=run.model_profile_sha256,
                                value=cell.value, references=refs, reason=cell.reason, missing_information=cell.missing_information)
                            self.store.add_proposal(db, state.id, proposal)
                            proposals.append(proposal)
                    result = run.model_copy(update={'state': 'succeeded', 'proposals': proposals, 'completed_at': now()})
                    self.store.put_run(db, state.id, result)
                    return result
                return self._run(mode, handle, publish, write=True)
            except Exception as exc:
                return self._fail(mode, handle, run, self._failure_code(exc))
        finally:
            self._run_gate.release()

    def _deadline(self, started):
        remaining = self.max_runtime_seconds - (time.monotonic() - started)
        if remaining <= 0:
            raise MvpError('proposal_timeout', _SAFE_FAILURES['proposal_timeout'])
        return remaining

    def _call(self, packet, remaining):
        # The daemon cannot publish or mutate data. On timeout it retains the call
        # lease until it exits, preventing unbounded orphaned provider calls.
        replies = queue.Queue(maxsize=1)
        if not self._call_gate.acquire(blocking=False):
            raise MvpError('proposal_busy', 'A generation call is already in progress.')
        def invoke():
            try:
                value = self.adapter.generate(packet, timeout_seconds=remaining)
                if not isinstance(value, ProposalGenerationResult):
                    value = ProposalGenerationResult.model_validate(value)
                replies.put((True, value))
            except BaseException as exc:
                replies.put((False, self._failure_code(exc)))
            finally:
                self._call_gate.release()
        threading.Thread(target=invoke, daemon=True, name='bounded-cell-proposal').start()
        try:
            ok, value = replies.get(timeout=remaining)
        except queue.Empty:
            raise MvpError('proposal_timeout', _SAFE_FAILURES['proposal_timeout'])
        if not ok:
            raise MvpError(value, _SAFE_FAILURES[value])
        return value

    @staticmethod
    def _parse(text):
        from .adapters.cell_generation import strict_json_loads
        return ProposalModelOutput.model_validate(strict_json_loads(text))

    @staticmethod
    def _validate_packet_output(packet, output):
        expected = {field.field_id for field in packet.fields}
        actual = [cell.field_id for cell in output.cells]
        if len(set(actual)) != len(actual) or set(actual) != expected:
            raise ValueError('Every requested field must occur exactly once')
        evidence = {item.evidence_id: item for item in packet.evidence}
        fields = {field.field_id: field for field in packet.fields}
        for cell in output.cells:
            seen = set()
            for quote in cell.references:
                item = evidence.get(quote.evidence_id)
                if item is None or quote.evidence_id not in fields[cell.field_id].evidence_ids or cell.field_id not in item.field_ids:
                    raise ValueError('Reference is outside this paper and field packet')
                text = item.reference.quote
                first = text.find(quote.quote)
                if first < 0 or text.find(quote.quote, first + 1) != -1:
                    raise ValueError('Quotation must have one exact unambiguous occurrence')
                identity = (quote.evidence_id, quote.quote)
                if identity in seen:
                    raise ValueError('Duplicate references are not permitted')
                seen.add(identity)

    def _references(self, state, definition, packet, cell):
        self._validate_packet_output(packet, ProposalModelOutput(cells=[cell])) if len(packet.fields) == 1 else None
        evidence = {item.evidence_id: item for item in packet.evidence}
        refs = []
        for quoted in cell.references:
            original = evidence[quoted.evidence_id].reference
            offset = original.quote.index(quoted.quote)
            request = BoardReferenceInput.model_validate(original.model_dump(include=set(BoardReferenceInput.model_fields))).model_copy(
                update={'start': original.start + offset, 'end': original.start + offset + len(quoted.quote)})
            reference = self.boards._reference(state, definition, packet.paper_id, request)
            if reference.quote != quoted.quote:
                raise MvpError('proposal_invalid_output', _SAFE_FAILURES['proposal_invalid_output'])
            refs.append(reference)
        return refs

    @staticmethod
    def _receipt(run, index, receipt):
        calls = list(run.calls)
        calls[index] = receipt
        return run.model_copy(update={'calls': calls})

    def _persist_running(self, mode, handle, run):
        def save(state, db):
            self._unchanged(state, db, run)
            self.store.put_run(db, state.id, run)
        self._run(mode, handle, save, write=True)

    @staticmethod
    def _failure_code(exc):
        code = getattr(exc, 'code', '')
        if code in _SAFE_FAILURES:
            return code
        if code in {'proposal_generation_timeout', 'proposal_timeout'}:
            return 'proposal_timeout'
        if code in {'proposal_invalid_evidence', 'proposal_output'}:
            return 'proposal_invalid_output'
        if code in {'stale_board_revision', 'stale_source_revision', 'board_integrity', 'invalid_board_reference',
                    'unknown_source', 'unknown_preparation', 'unknown_board_source', 'unknown_board_revision'}:
            return 'proposal_stale_inputs'
        if code in {'board_storage_limit', 'board_limit'}:
            return 'proposal_storage_limit'
        if 'context' in code:
            return 'proposal_context_limit'
        return 'proposal_provider_failure'

    def _fail(self, mode, handle, run, code):
        result = run.model_copy(update={'state': 'failed', 'failure_code': code, 'failure_message': _SAFE_FAILURES[code],
                                      'proposals': [], 'completed_at': now()})
        try:
            # Intentionally do not require current revision here: preserve the
            # failed receipt for stale runs, while lifecycle/deletion still gate.
            def save_failure(state, db):
                persisted = self.store.run(db, state.id, run.board_id, run.id)
                # Inputs must have been acknowledged before a call. If saving a
                # larger input packet itself hit quota, retain the last saved
                # input receipt rather than trying to write those inputs again.
                terminal = result.model_copy(update={'packets': persisted.packets})
                self.store.put_run(db, state.id, terminal)
                return terminal
            result = self._run(mode, handle, save_failure, write=True)
        except MvpError:
            # Deleted workspaces remain deleted; no late insert or retry occurs.
            # A reserve counted in shared quota normally guarantees room for a
            # terminal receipt; externally lowered limits can still prevent it.
            pass
        return result

    def _decorate_run(self, db, workspace_id, run):
        return run.model_copy(update={'proposals': [self.store.with_event(db, workspace_id, p) for p in run.proposals]})

    def get_run(self, mode, handle, board_id, run_id):
        def read(state, db):
            run, _ = self._checked_run(state, db, board_id, run_id)
            return self._decorate_run(db, state.id, run)
        return self._run(mode, handle, read)

    def listing(self, mode, handle, board_id, revision_id, paper_id=None, field_id=None, offset=0, limit=10):
        if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 20:
            raise MvpError('invalid_proposal_pagination', 'Use a nonnegative proposal offset and limit from 1 to 20.')
        def read(state, db):
            definition = self.boards.store.definition(db, state.id, board_id, revision_id)
            self.boards._dependencies(state, definition)
            if paper_id is not None and paper_id not in definition.paper_ids:
                raise unavailable('board_paper')
            if field_id is not None and field_id not in {f.id for f in definition.fields}:
                raise unavailable('board_field')
            clauses, args = ['workspace_id=?', 'board_id=?', 'definition_id=?'], [state.id, board_id, definition.revision_id]
            for key, value in [('paper_id', paper_id), ('field_id', field_id)]:
                if value is not None:
                    clauses.append(key + '=?')
                    args.append(value)
            where = ' AND '.join(clauses)
            total = db.execute('SELECT COUNT(*) FROM cell_proposals WHERE ' + where, args).fetchone()[0]
            rows = db.execute('SELECT * FROM cell_proposals WHERE ' + where + ' ORDER BY rowid DESC LIMIT ? OFFSET ?', [*args, limit, offset])
            items = [self.store.with_event(db, state.id, self.boards.store.decode(row, CellProposal)) for row in rows]
            runs = []
            for row in db.execute('SELECT * FROM proposal_runs WHERE workspace_id=? AND board_id=? AND definition_id=? ORDER BY rowid DESC', (state.id, board_id, definition.revision_id)):
                run = self.boards.store.decode(row, ProposalRun)
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(run.created_at)).total_seconds()
                runs.append(ProposalRunSummary(**run.model_dump(include=set(ProposalRunSummary.model_fields) - {'proposal_count', 'recovery_note'}),
                    proposal_count=len(run.proposals), recovery_note='Interrupted or expired run; no automatic retry. Use a new request only after reviewing its receipt.'
                    if run.state == 'running' and age > self.max_runtime_seconds else None))
            return ProposalListing(items=items, offset=offset, limit=limit, total=total, runs=runs, capability=self.capabilities())
        return self._run(mode, handle, read)

    def _proposal(self, state, db, board_id, proposal_id, revision_id=None, writable=False):
        proposal = self.store.proposal(db, state.id, board_id, proposal_id)
        if revision_id is not None and proposal.board_revision_id != revision_id:
            raise MvpError('stale_board_revision', 'The proposal belongs to another board definition.')
        definition = (self.boards._writable(state, db, board_id, proposal.board_revision_id) if writable else
            self.boards.store.definition(db, state.id, board_id, proposal.board_revision_id))
        self.boards._dependencies(state, definition)
        if proposal.source_manifest_sha256 != definition.source_manifest_sha256:
            raise MvpError('board_integrity', 'The proposal source binding changed.')
        for ref in proposal.references:
            reconstructed = self.boards._reference(state, definition, proposal.paper_id,
                BoardReferenceInput.model_validate(ref.model_dump(include=set(BoardReferenceInput.model_fields))))
            if reconstructed != ref:
                raise MvpError('board_integrity', 'The proposal exact quotation changed.')
        return proposal, definition

    def dismiss(self, mode, handle, board_id, proposal_id, request: ProposalDismissRequest):
        def apply(state, db):
            proposal, definition = self._proposal(state, db, board_id, proposal_id, request.expected_revision_id)
            fingerprint = digest({'operation': 'proposal-dismiss', 'proposal_id': proposal_id, 'request': request.model_dump(mode='json')})
            prior = self.store.prior_action(db, state.id, request.request_id, fingerprint, CellProposal)
            if prior is not None:
                return prior
            self.boards._writable(state, db, board_id, request.expected_revision_id)
            if proposal.status != 'pending':
                raise MvpError('proposal_already_reviewed', 'This proposal already has an explicit review action.')
            event = ProposalEvent(proposal_id=proposal.id, action='dismissed', request_id=request.request_id, reason=request.reason)
            result = proposal.model_copy(update={'status': 'dismissed', 'latest_event': event})
            self.store.add_event(db, state.id, board_id, event, fingerprint, result)
            return result
        return self._run(mode, handle, apply, write=True)

    def adopt(self, mode, handle, board_id, proposal_id, request: ProposalAdoptRequest):
        def apply(state, db):
            proposal, definition = self._proposal(state, db, board_id, proposal_id, request.expected_revision_id)
            fingerprint = digest({'operation': 'proposal-adopt', 'proposal_id': proposal_id, 'request': request.model_dump(mode='json')})
            prior = self.store.prior_action(db, state.id, request.request_id, fingerprint, BoardCellDraft)
            if prior is not None:
                return prior
            self.boards._writable(state, db, board_id, request.expected_revision_id)
            if proposal.status != 'pending':
                raise MvpError('proposal_already_reviewed', 'This proposal already has an explicit review action.')
            current = self.boards.store.draft(db, definition, proposal.paper_id, proposal.field_id)
            head = self.boards.store.cell_head(db, definition, proposal.paper_id, proposal.field_id)
            if request.draft_version != current.version:
                raise MvpError('stale_board_draft', 'The cell draft changed. Existing edits were not overwritten.')
            if request.expected_cell_head_id != head:
                raise MvpError('stale_board_cell', 'The submitted cell changed. Begin an explicit revision from its current head.')
            if current.data != BoardCellData():
                raise MvpError('proposal_draft_not_empty', 'Use in draft requires an empty current draft. Existing values, references and judgments were not overwritten.')
            refs = [BoardReferenceInput.model_validate(ref.model_dump(include=set(BoardReferenceInput.model_fields))) for ref in proposal.references]
            data = BoardCellData(value=request.value, references=refs, inspected_ranges=[], reason=request.reason,
                missing_information=request.missing_information, semantic_assessment='unassessed', scope_result='not_assessed')
            result = BoardCellDraft(board_id=board_id, board_revision_id=definition.revision_id, paper_id=proposal.paper_id,
                field_id=proposal.field_id, version=current.version + 1, expected_cell_head_id=head, data=data, updated_at=now())
            self.boards.store.put_draft(db, definition, result)
            event = ProposalEvent(proposal_id=proposal.id, action='adopted', request_id=request.request_id,
                draft_version=result.version, edited_value_sha256=digest(data.model_dump(mode='json')))
            self.store.add_event(db, state.id, board_id, event, fingerprint, result)
            return result
        return self._run(mode, handle, apply, write=True)

    def context(self, mode, handle, board_id, proposal_id, reference_id):
        def read(state, db):
            proposal, definition = self._proposal(state, db, board_id, proposal_id)
            reference = next((ref for ref in proposal.references if ref.id == reference_id), None)
            if reference is None:
                raise unavailable('proposal_reference')
            source = self.boards._source(state, definition, reference.source_id, proposal.paper_id)
            block = _find(source.blocks, reference.block_id, 'source_block')
            freshness, _ = self.boards._freshness(state, db, definition)
            return BoardReferenceContext(reference=reference, paper=next(p for p in definition.papers if p.id == proposal.paper_id),
                source=next(s for s in definition.sources if s.source_id == source.id), freshness=freshness,
                block=self.boards._chunk(state, definition, source, block, reference.start))
        return self._run(mode, handle, read)

    def export(self, mode, handle, board_id, revision_id):
        def read(state, db):
            definition = self.boards.store.definition(db, state.id, board_id, revision_id)
            self.boards._dependencies(state, definition)
            runs = [self._decorate_run(db, state.id, self.boards.store.decode(row, ProposalRun)) for row in db.execute(
                'SELECT * FROM proposal_runs WHERE workspace_id=? AND board_id=? AND definition_id=? ORDER BY rowid', (state.id, board_id, definition.revision_id))]
            events = [self.boards.store.decode(row, ProposalEvent) for row in db.execute(
                'SELECT * FROM proposal_events WHERE workspace_id=? AND board_id=? ORDER BY rowid', (state.id, board_id))
                if any(p.id == row['proposal_id'] for run in runs for p in run.proposals)]
            return ProposalAudit(board_id=board_id, board_revision_id=definition.revision_id, runs=runs, events=events)
        return self._run(mode, handle, read)
