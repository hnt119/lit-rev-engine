"""Reviewable intent plans; explicit, revision-safe provider/model operations."""
import hashlib
from contextlib import contextmanager

from .contracts import SearchPreview, SearchRequest, digest
from .ports import MvpError
from .search_plan_compiler import compile_search_plan
from .search_plan_contracts import (
    PLANNER_PROMPT_VERSION,
    SearchApprovalReceipt, SearchPlanDiagnostic, SearchPlanExecution,
    SearchPlanListing, SearchPlanRevision, SearchPlanSummary, SearchPlanningResult,
    QueryDiagnosticReceipt,
)
from .search_plan_service_contracts import (
    PlannedSearchResult, SearchPlanCapabilities, SearchPlanProposalReceipt, SearchPlanView,
)


def _summary(revision):
    return SearchPlanSummary(plan_id=revision.plan_id, revision_id=revision.revision_id,
        revision=revision.revision, original_question=revision.draft.original_question,
        input_mode=revision.draft.input_mode, candidate_count=len(revision.compiled.candidates),
        ready_count=sum(item.status == 'ready_for_approval' for item in revision.compiled.candidates),
        created_at=revision.created_at)


class SearchPlanService:
    def __init__(self, engine, store, *, mode='live', diagnostics=None, planner=None, registry=None):
        from .adapters.search_diagnostics import PubMedSearchDiagnostics
        from .adapters.search_planning import ConfiguredSearchPlanningAdapter
        self.engine, self.store, self.mode = engine, store, mode
        self.registry = registry
        self.diagnostics = diagnostics if diagnostics is not None else PubMedSearchDiagnostics.from_provider(engine._discovery)
        self.planner_configuration_error = None
        if planner is not None:
            self.planner = planner
        else:
            try:
                self.planner = ConfiguredSearchPlanningAdapter.from_environment()
            except MvpError as error:
                self.planner = ConfiguredSearchPlanningAdapter()
                self.planner_configuration_error = error.message

    def capabilities(self, handle):
        with self._lifecycle(handle):
            self.engine.get_workspace(handle)
            live = self.mode == 'live'
            planner = self.planner.capability()
            if self.planner_configuration_error:
                planner = planner.model_copy(update={'reason': self.planner_configuration_error})
            return SearchPlanCapabilities(execution_enabled=live,
                execution_reason='Explicit execution uses the existing configured discovery provider.' if live else 'Saved examples do not execute supplied queries. Use a configured live workspace for an approved search.',
                diagnostics_enabled=bool(self.diagnostics.enabled), diagnostics_reason=self.diagnostics.reason,
                planner=planner)

    @contextmanager
    def _lifecycle(self, handle):
        if self.registry is None:
            yield
            return
        with self.registry.lifecycle_guard(handle.workspace_id):
            if self.registry.is_deleted(handle.workspace_id):
                raise MvpError('workspace_access_denied', 'Workspace is unavailable or its handle is invalid.')
            yield

    def _locked(self, handle, callback):
        with self._lifecycle(handle):
            return self.engine.with_workspace_state(handle, lambda state: callback(state.id))

    @staticmethod
    def _fingerprint(plan_id, request):
        return digest({'plan_id': plan_id, 'request': request.model_dump(mode='json')})

    def _head(self, db, workspace_id, plan_id, expected):
        revision = self.store.revision(db, workspace_id, plan_id)
        if revision.revision_id != expected:
            raise MvpError('stale_search_plan', 'The plan changed. Keep local edits and reload; this response cannot replace a newer revision.')
        if compile_search_plan(revision.draft) != revision.compiled:
            raise MvpError('search_plan_integrity', 'The stored query candidates no longer match their exact intent and compiler version.')
        return revision

    def _candidate(self, revision, request):
        candidate = next((item for item in revision.compiled.candidates if item.id == request.candidate_id), None)
        if candidate is None or candidate.candidate_sha256 != request.candidate_sha256:
            raise MvpError('stale_search_candidate', 'Choose a compiled candidate from this exact saved revision.')
        if candidate.status != 'ready_for_approval':
            raise MvpError('search_plan_blocked', 'Resolve the displayed planning issues before approval, diagnostics or execution.')
        return candidate

    def listing(self, handle):
        with self._lifecycle(handle):
            self.engine.get_workspace(handle)
            with self.store.connection() as db:
                rows = db.execute('SELECT id FROM mvp_search_plans WHERE workspace_id=? ORDER BY updated_at DESC,id', (handle.workspace_id,)).fetchall()
                return SearchPlanListing(plans=[_summary(self.store.revision(db, handle.workspace_id, row['id'])) for row in rows])

    def view(self, handle, plan_id, revision_id=None):
        with self._lifecycle(handle):
            self.engine.get_workspace(handle)
            with self.store.connection() as db:
                db.execute('BEGIN')
                current = self.store.revision(db, handle.workspace_id, plan_id)
                selected = current if revision_id is None else self.store.revision(db, handle.workspace_id, plan_id, revision_id)
                identifiers = db.execute('SELECT id FROM mvp_search_plan_revisions WHERE workspace_id=? AND plan_id=? ORDER BY revision DESC', (handle.workspace_id, plan_id)).fetchall()
                events = db.execute('SELECT id,kind FROM mvp_search_plan_events WHERE workspace_id=? AND plan_id=? AND revision_id=? ORDER BY created_at DESC,id DESC', (handle.workspace_id, plan_id, selected.revision_id)).fetchall()
                groups = {'approval': [], 'diagnostic': [], 'execution': [], 'proposal': []}
                models = {'approval': SearchApprovalReceipt, 'diagnostic': SearchPlanDiagnostic, 'execution': SearchPlanExecution, 'proposal': SearchPlanProposalReceipt}
                for row in events:
                    if row['kind'] not in models:
                        raise MvpError('search_plan_integrity', 'Unsupported retained planning receipt.')
                    groups[row['kind']].append(self.store.event(db, handle.workspace_id, plan_id, row['id'], row['kind'], models[row['kind']]))
                return SearchPlanView(revision=selected, current_revision_id=current.revision_id,
                    revisions=[_summary(self.store.revision(db, handle.workspace_id, plan_id, row['id'])) for row in identifiers],
                    approvals=groups['approval'], diagnostics=groups['diagnostic'], executions=groups['execution'], proposals=groups['proposal'])

    def create(self, handle, request):
        compiled = compile_search_plan(request.draft)
        def write(workspace_id):
            def change(db):
                revision = SearchPlanRevision(workspace_id=workspace_id, revision=1, draft=request.draft, compiled=compiled)
                self.store.insert_revision(db, revision)
                return {'plan_id': revision.plan_id, 'revision_id': revision.revision_id}
            return self.store.mutate(workspace_id, 'create', request.request_id, self._fingerprint(None, request), change)
        value = self._locked(handle, write)
        return self.view(handle, value['plan_id'], value['revision_id'])

    def update(self, handle, plan_id, request):
        compiled = compile_search_plan(request.draft)
        def write(workspace_id):
            def change(db):
                old = self._head(db, workspace_id, plan_id, request.expected_revision_id)
                revision = SearchPlanRevision(plan_id=plan_id, workspace_id=workspace_id, revision=old.revision+1,
                    parent_revision_id=old.revision_id, draft=request.draft, compiled=compiled)
                self.store.insert_revision(db, revision)
                return {'plan_id': plan_id, 'revision_id': revision.revision_id}
            return self.store.mutate(workspace_id, 'update:'+plan_id, request.request_id, self._fingerprint(plan_id, request), change)
        value = self._locked(handle, write)
        return self.view(handle, value['plan_id'], value['revision_id'])

    def _read_event(self, handle, plan_id, identifier, kind, model):
        with self._lifecycle(handle):
            self.engine.get_workspace(handle)
            with self.store.connection() as db:
                return self.store.event(db, handle.workspace_id, plan_id, identifier, kind, model)

    def approve(self, handle, plan_id, request):
        def write(workspace_id):
            def change(db):
                revision = self._head(db, workspace_id, plan_id, request.expected_revision_id)
                candidate = self._candidate(revision, request)
                required = set(candidate.deferred_required_ids + candidate.deferred_excluded_ids)
                if (len(request.acknowledged_deferred_concept_ids) != len(set(request.acknowledged_deferred_concept_ids))
                        or set(request.acknowledged_deferred_concept_ids) != required
                        or candidate.requires_split_approval and not request.accept_subquestion_split
                        or bool(candidate.unparsed_constraints) and not request.acknowledge_unparsed_strategy):
                    raise MvpError('search_approval_incomplete', 'Explicitly acknowledge every displayed deferred constraint, unparsed strategy and proposed subquestion split.')
                receipt = SearchApprovalReceipt(plan_id=plan_id, revision_id=revision.revision_id,
                    candidate_id=candidate.id, candidate_sha256=candidate.candidate_sha256,
                    acknowledged_deferred_concept_ids=request.acknowledged_deferred_concept_ids,
                    accept_subquestion_split=request.accept_subquestion_split, acknowledge_unparsed_strategy=request.acknowledge_unparsed_strategy)
                self.store.insert_event(db, workspace_id, plan_id, revision.revision_id, 'approval', receipt.id, receipt.model_dump(mode='json'))
                return {'id': receipt.id}
            return self.store.mutate(workspace_id, 'approve:'+plan_id, request.request_id, self._fingerprint(plan_id, request), change)
        value = self._locked(handle, write)
        return self._read_event(handle, plan_id, value['id'], 'approval', SearchApprovalReceipt)

    def _begin(self, handle, plan_id, request, kind, checker):
        operation, fingerprint = kind+':'+plan_id, self._fingerprint(plan_id, request)
        def reserve(workspace_id):
            with self.store.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                try:
                    replay = self.store.request(db, workspace_id, operation, request.request_id, fingerprint)
                    if replay is not None:
                        db.execute('COMMIT')
                        return None, replay
                    revision = self._head(db, workspace_id, plan_id, request.expected_revision_id)
                    capture = checker(db, revision)
                    self.store.save_request(db, workspace_id, operation, request.request_id, fingerprint, 'pending', {})
                    self.store.limits(db, workspace_id)
                    db.execute('COMMIT')
                    return (revision, capture), None
                except BaseException:
                    if db.in_transaction: db.execute('ROLLBACK')
                    raise
        captured, replay = self._locked(handle, reserve)
        return operation, fingerprint, captured, replay

    def _finish(self, handle, plan_id, request, operation, fingerprint, callback):
        def publish(workspace_id):
            with self.store.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                try:
                    row = db.execute('SELECT fingerprint,status FROM mvp_search_plan_requests WHERE workspace_id=? AND operation=? AND request_id=?', (workspace_id, operation, request.request_id)).fetchone()
                    if row is None or row['fingerprint'] != fingerprint or row['status'] != 'pending':
                        raise MvpError('search_plan_integrity', 'The exact pending planning operation is unavailable.')
                    revision = self._head(db, workspace_id, plan_id, request.expected_revision_id)
                    outcome = callback(db, revision)
                    self.store.save_request(db, workspace_id, operation, request.request_id, fingerprint, 'succeeded', outcome)
                    self.store.limits(db, workspace_id)
                    db.execute('COMMIT')
                    return outcome
                except BaseException:
                    if db.in_transaction: db.execute('ROLLBACK')
                    raise
        return self._locked(handle, publish)

    def _failed(self, handle, operation, request, fingerprint, error):
        safe = error if isinstance(error, MvpError) else MvpError('search_plan_operation_failed', 'The explicit planning operation failed. No newer revision was replaced.', True)
        def fail(workspace_id):
            with self.store.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                try:
                    row = db.execute('SELECT fingerprint,status FROM mvp_search_plan_requests WHERE workspace_id=? AND operation=? AND request_id=?', (workspace_id, operation, request.request_id)).fetchone()
                    if row and row['fingerprint'] == fingerprint and row['status'] == 'pending':
                        self.store.save_request(db, workspace_id, operation, request.request_id, fingerprint, 'failed', {'code': safe.code, 'message': safe.message.encode('utf-8')[:1024].decode('utf-8', errors='ignore'), 'retryable': safe.retryable})
                    db.execute('COMMIT')
                except BaseException:
                    if db.in_transaction: db.execute('ROLLBACK')
                    raise
        try: self._locked(handle, fail)
        except MvpError: pass  # A deleted workspace is never recreated for a late result.
        return safe

    def diagnose(self, handle, plan_id, request):
        if not self.diagnostics.enabled:
            self._locked(handle, lambda _: None)
            raise MvpError('query_diagnostics_disabled', self.diagnostics.reason)
        def check(db, revision):
            candidate = self._candidate(revision, request)
            preview = None
            if request.preview_search_id:
                state = self.engine.get_workspace(handle)
                preview = next((item for item in state.searches if item.id == request.preview_search_id), None)
                if preview is None or (preview.query, preview.date_from, preview.date_to, preview.sort) != (candidate.query, candidate.date_from, candidate.date_to, candidate.sort) or preview.mode == 'saved_example':
                    raise MvpError('diagnostic_preview_mismatch', 'Capped recovery requires a retained executed preview with this exact query, filters and sort.')
            return candidate, preview
        operation, fingerprint, capture, replay = self._begin(handle, plan_id, request, 'diagnose', check)
        if replay is not None:
            return self._read_event(handle, plan_id, replay['id'], 'diagnostic', SearchPlanDiagnostic)
        revision, (candidate, preview) = capture
        try:
            pmids = [paper.pmid for paper in preview.papers if paper.pmid] if preview else None
            receipt = QueryDiagnosticReceipt.model_validate(self.diagnostics.check(candidate.query,
                date_from=candidate.date_from, date_to=candidate.date_to, sort=candidate.sort, seeds=request.seeds, preview_pmids=pmids))
            if ((receipt.query, receipt.date_from, receipt.date_to, receipt.sort) != (candidate.query, candidate.date_from, candidate.date_to, candidate.sort)
                    or receipt.query_sha256 != hashlib.sha256(candidate.query.encode('utf-8')).hexdigest()
                    or not 0 <= receipt.calls <= 2 or len(set(receipt.sample_pmids)) != len(receipt.sample_pmids)
                    or receipt.reported_count is not None and (receipt.reported_count < 0 or len(receipt.sample_pmids) > receipt.reported_count)
                    or [item.seed for item in receipt.seed_results] != request.seeds):
                raise MvpError('invalid_query_diagnostic', 'The diagnostic did not match the exact requested query, bounds and seed identities.')
            expected_recovery = ['not_checked' if pmids is None or seed.pmid is None else 'present' if seed.pmid in pmids else 'absent' for seed in request.seeds]
            if [item.preview_recovery for item in receipt.seed_results] != expected_recovery:
                raise MvpError('invalid_query_diagnostic', 'Diagnostic sample membership cannot substitute for retained-preview recovery.')
            value = SearchPlanDiagnostic(plan_id=plan_id, revision_id=revision.revision_id, candidate_id=candidate.id,
                candidate_sha256=candidate.candidate_sha256, receipt=receipt,
                preview_search_id=preview.id if preview else None, preview_search_snapshot_sha256=digest(preview.model_dump(mode='json')) if preview else None)
            def publish(db, _):
                self.store.insert_event(db, handle.workspace_id, plan_id, revision.revision_id, 'diagnostic', receipt.id, value.model_dump(mode='json'))
                return {'id': receipt.id}
            result = self._finish(handle, plan_id, request, operation, fingerprint, publish)
            return self._read_event(handle, plan_id, result['id'], 'diagnostic', SearchPlanDiagnostic)
        except Exception as error:
            raise self._failed(handle, operation, request, fingerprint, error) from None

    def propose(self, handle, plan_id, request):
        if not self.planner.capability().enabled:
            self._locked(handle, lambda _: None)
            raise MvpError('search_planner_disabled', self.planner.capability().reason)
        def check(db, revision):
            if request.original_question != revision.draft.original_question:
                raise MvpError('stale_planner_question', 'Save the exact question before requesting a model proposal.')
            return None
        operation, fingerprint, capture, replay = self._begin(handle, plan_id, request, 'propose', check)
        if replay is not None:
            return self._read_event(handle, plan_id, replay['id'], 'proposal', SearchPlanProposalReceipt)
        revision, _ = capture
        try:
            result = SearchPlanningResult.model_validate(self.planner.propose(request.original_question, timeout_seconds=10))
            if (result.draft.original_question != request.original_question
                    or result.draft.input_mode != 'natural_question' or result.draft.manual_strategy is not None
                    or result.prompt_version != PLANNER_PROMPT_VERSION
                    or result.question_sha256 != hashlib.sha256(request.original_question.encode('utf-8')).hexdigest()
                    or result.model_profile != self.planner.capability().model_profile
                    or not 0 <= result.elapsed_seconds <= 10
                    or any(term.state != 'proposed' or term.origin != 'model_proposed' for concept in result.draft.concepts for term in concept.terms)
                    or any(concept.promoted_to_query for concept in result.draft.concepts)
                    or any(item.resolved for item in result.draft.ambiguities)):
                raise MvpError('invalid_search_planner_output', 'The model proposal failed question, profile, budget or review-state binding.')
            value = SearchPlanProposalReceipt(plan_id=plan_id, revision_id=revision.revision_id, result=result)
            def publish(db, _):
                self.store.insert_event(db, handle.workspace_id, plan_id, revision.revision_id, 'proposal', value.id, value.model_dump(mode='json'))
                return {'id': value.id}
            outcome = self._finish(handle, plan_id, request, operation, fingerprint, publish)
            return self._read_event(handle, plan_id, outcome['id'], 'proposal', SearchPlanProposalReceipt)
        except Exception as error:
            raise self._failed(handle, operation, request, fingerprint, error) from None

    def execute(self, handle, plan_id, request):
        if self.mode != 'live':
            self._locked(handle, lambda _: None)
            raise MvpError('planned_search_requires_live', 'A saved example does not execute supplied queries. Use a configured live workspace.')
        def check(db, revision):
            candidate = self._candidate(revision, request)
            approval = self.store.event(db, handle.workspace_id, plan_id, request.approval_id, 'approval', SearchApprovalReceipt)
            if (approval.revision_id, approval.candidate_id, approval.candidate_sha256) != (revision.revision_id, candidate.id, candidate.candidate_sha256):
                raise MvpError('stale_search_approval', 'This approval belongs to different query intent. Approve the current candidate explicitly.')
            return candidate
        operation, fingerprint, capture, replay = self._begin(handle, plan_id, request, 'execute', check)
        if replay is not None:
            return self._execution_result(handle, plan_id, replay['id'])
        revision, candidate = capture
        try:
            search_request = SearchRequest(request_id=request.request_id, query=candidate.query,
                research_question=revision.draft.original_question or None, max_results=request.max_results,
                date_from=candidate.date_from, date_to=candidate.date_to, sort=candidate.sort)
            preview = self.engine._discovery.search(search_request)
            def guard(db, value, replaying):
                if replaying:
                    raise MvpError('search_plan_integrity', 'An approved capture exists without its matching planning receipt.')
                current = self._head(db, handle.workspace_id, plan_id, request.expected_revision_id)
                check(db, current)
                pending = db.execute('SELECT status,fingerprint FROM mvp_search_plan_requests WHERE workspace_id=? AND operation=? AND request_id=?', (handle.workspace_id, operation, request.request_id)).fetchone()
                if pending is None or pending['status'] != 'pending' or pending['fingerprint'] != fingerprint:
                    raise MvpError('search_plan_integrity', 'The exact capture reservation changed.')
                execution = SearchPlanExecution(plan_id=plan_id, revision_id=revision.revision_id,
                    candidate_id=candidate.id, candidate_sha256=candidate.candidate_sha256,
                    approval_id=request.approval_id, search_id=value['id'], search_snapshot_sha256=digest(value))
                self.store.insert_event(db, handle.workspace_id, plan_id, revision.revision_id, 'execution', execution.id, execution.model_dump(mode='json'))
                self.store.save_request(db, handle.workspace_id, operation, request.request_id, fingerprint, 'succeeded', {'id': execution.id})
                self.store.limits(db, handle.workspace_id)
            with self._lifecycle(handle):
                self.engine.publish_planned_search(handle, search_request, preview, plan_id=plan_id, fingerprint=fingerprint, commit_guard=guard)
            with self.store.connection() as db:
                outcome = self.store.request(db, handle.workspace_id, operation, request.request_id, fingerprint)
            return self._execution_result(handle, plan_id, outcome['id'])
        except Exception as error:
            raise self._failed(handle, operation, request, fingerprint, error) from None

    def _execution_result(self, handle, plan_id, identifier):
        execution = self._read_event(handle, plan_id, identifier, 'execution', SearchPlanExecution)
        with self._lifecycle(handle):
            state = self.engine.get_workspace(handle)
            preview = next((item for item in state.searches if item.id == execution.search_id), None)
            if preview is None or digest(preview.model_dump(mode='json')) != execution.search_snapshot_sha256:
                raise MvpError('search_plan_integrity', 'The original approved capture no longer matches its immutable planning receipt.')
            return PlannedSearchResult(execution=execution, search=preview)
