"""Cell-bound investigations that leave every original research record unchanged."""
import json
import re
from .contracts import digest, SearchPreview
from .board_contracts import BoardCellRevision
from .ports import MvpError
from .search_plan_contracts import SearchPlanDraft, SearchPlanRevision, SearchApprovalReceipt, SearchPlanExecution
from .search_plan_compiler import compile_search_plan
from .adapters.search_plan_storage import packed, decoded
from .investigation_contracts import (
    InvestigationOrigin, InvestigationListing, InvestigationView, InvestigationExecution,
    InvestigationCandidate, InvestigationDecision, InvestigationOperation, InvestigationExport,
)

SAFEGUARDS = [
    'An unresolved comparison cell is not proof of a research gap.',
    'Not found in inspected material does not establish whole-paper absence.',
    'A new paper cannot supply missing facts about a different paper.',
    'Search matches and retrieval scores do not establish relevance, eligibility or support.',
    'Shortlisted candidates remain separate from the comparison board and source preparations.',
]

def unresolved(data):
    return data is None or (data.semantic_assessment != 'human_supported'
        or data.scope_result != 'value_found' or data.value is None or bool(data.missing_information.strip()))


def meaningful_draft(data):
    return data is not None and bool((data.value or '').strip() or data.reason.strip()
        or data.missing_information.strip() or data.references or data.inspected_ranges)


class InvestigationService:
    def __init__(self, boards, planning, store):
        self.boards, self.planning, self.store = boards, planning, store

    def create(self, mode, handle, request):
        fingerprint = digest(request.model_dump(mode='json'))
        def capture(state, board_db):
            def change(db):
                definition = self.boards._writable(state, board_db, request.board_id, request.expected_board_revision_id)
                field = self.boards._cell(definition, request.paper_id, request.field_id)
                head = self.boards.store.cell_head(board_db, definition, request.paper_id, request.field_id)
                draft = self.boards.store.draft(board_db, definition, request.paper_id, request.field_id)
                if head != request.expected_cell_head_id or draft.version != request.expected_draft_version:
                    raise MvpError('stale_investigation_origin', 'The original cell or saved draft changed. Keep local edits and reload before starting an investigation.')
                if request.local_draft is not None:
                    for reference in [*request.local_draft.references, *request.local_draft.inspected_ranges]:
                        self.boards._reference(state, definition, request.paper_id, reference)
                row = board_db.execute('SELECT * FROM board_cells WHERE workspace_id=? AND id=?', (state.id, head)).fetchone() if head else None
                cell = self.boards.store.decode(row, BoardCellRevision) if row else None
                source_unavailable = any(s.paper_id == request.paper_id and s.source_type == 'none' for s in definition.sources)
                unfinished_draft = ((draft.version > 0 and meaningful_draft(draft.data) and unresolved(draft.data))
                    or (meaningful_draft(request.local_draft) and unresolved(request.local_draft)))
                if not unresolved(cell) and not source_unavailable and not unfinished_draft:
                    raise MvpError('investigation_origin_resolved', 'Start an investigation from an unresolved comparison cell.')
                seed, approvals = None, []
                # Follow a board's exact executed plan, when available. Never infer
                # constraints from a field label, paper metadata or an LLM.
                seed_plan, seed_revision = request.seed_plan_id, request.seed_revision_id
                if seed_plan is None and definition.search_id:
                    rows = db.execute("SELECT payload,sha256 FROM mvp_search_plan_events WHERE workspace_id=? AND kind='execution' ORDER BY created_at,id", (state.id,)).fetchall()
                    for item in rows:
                        execution = decoded(item)
                        if execution['search_id'] == definition.search_id:
                            seed_plan, seed_revision = execution['plan_id'], execution['revision_id']
                            break
                if seed_plan:
                    seed = self.store.revision(db, state.id, seed_plan, seed_revision)
                    rows = db.execute("SELECT payload,sha256 FROM mvp_search_plan_events WHERE workspace_id=? AND plan_id=? AND revision_id=? AND kind='approval' ORDER BY created_at,id", (state.id, seed_plan, seed_revision)).fetchall()
                    approvals = [decoded(row, SearchApprovalReceipt).id for row in rows]
                    if not approvals:
                        raise MvpError('investigation_seed_unapproved', 'Prefill requires an exact researcher-approved plan revision.')
                # Retain the seed question so its Unicode concept spans stay exact;
                # field question is separately retained in the original definition.
                plan_draft = seed.draft if seed else SearchPlanDraft(original_question=field.subquestion, input_mode='manual_strategy', manual_strategy='')
                revision = SearchPlanRevision(workspace_id=state.id, revision=1, draft=plan_draft, compiled=compile_search_plan(plan_draft))
                self.store.insert_revision(db, revision)
                origin = InvestigationOrigin(workspace_id=state.id, request_id=request.request_id, board=definition, paper_id=request.paper_id,
                    field_id=request.field_id, cell=cell, draft=draft, local_draft=request.local_draft,
                    reason=request.reason, plan_id=revision.plan_id, seed_plan_id=seed_plan,
                    seed_revision_id=seed_revision, seed_approval_ids=approvals)
                payload, checksum = packed(origin.model_dump(mode='json'))
                db.execute('INSERT INTO mvp_investigations VALUES(?,?,?,?,?)', (origin.id, state.id, revision.plan_id, payload, checksum))
                return {'id': origin.id}
            return self.store.mutate(state.id, 'investigation-create', request.request_id, fingerprint, change)
        # Capture and persist under one existing lifecycle/workspace guard; no
        # nested service lock, no provider I/O and no writes to the board sidecar.
        result = self.boards._with(mode, handle, capture)
        return self.view(handle, result['id'])

    def origin(self, handle, identifier):
        def read(workspace_id):
            with self.store.connection() as db:
                return self.store.origin(db, workspace_id, identifier)
        return self.planning._locked(handle, read)

    def listing(self, handle, board_id=None, paper_id=None, field_id=None):
        def read(workspace_id):
            with self.store.connection() as db:
                ids = db.execute('SELECT id FROM mvp_investigations WHERE workspace_id=? ORDER BY rowid DESC', (workspace_id,)).fetchall()
                origins = [self.store.origin(db, workspace_id, row['id']) for row in ids]
                return InvestigationListing(investigations=[item for item in origins if
                    (board_id is None or item.board.board_id == board_id) and
                    (paper_id is None or item.paper_id == paper_id) and (field_id is None or item.field_id == field_id)])
        return self.planning._locked(handle, read)

    def view(self, handle, identifier):
        return self._snapshot(handle, identifier)[0]

    def _snapshot(self, handle, identifier, *, audit=False):
        capabilities = self.planning.capabilities(handle)
        if self.planning.mode != 'live':
            capabilities = capabilities.model_copy(update={'diagnostics_enabled': False, 'diagnostics_reason': 'Saved examples do not send follow-up queries to PubMed.'})
        def read(workspace_id):
            with self.store.connection() as db:
                # Origin, plans, receipts, previews and decisions are read from
                # one SQLite snapshot. Concurrent edits cannot yield an export
                # with an execution whose approved revision is missing.
                db.execute('BEGIN')
                origin = self.store.origin(db, workspace_id, identifier)
                plan = self.planning.view_in_transaction(db, workspace_id, origin.plan_id)
                decisions = [decoded(row, InvestigationDecision) for row in db.execute(
                    'SELECT payload,sha256 FROM mvp_investigation_decisions WHERE workspace_id=? AND investigation_id=? ORDER BY rowid', (workspace_id, identifier))]
                executions = [decoded(row, SearchPlanExecution) for row in db.execute("SELECT payload,sha256 FROM mvp_search_plan_events WHERE workspace_id=? AND plan_id=? AND kind='execution' ORDER BY created_at,id", (workspace_id, origin.plan_id))]
                failures = []
                rows = db.execute('SELECT request_id,operation,fingerprint,status,outcome,created_at,updated_at FROM mvp_search_plan_requests WHERE workspace_id=? AND operation IN (?,?,?,?,?) ORDER BY created_at,request_id',
                    (workspace_id, *[kind+':'+origin.plan_id for kind in ('update','approve','diagnose','execute')], 'investigation-decide:'+identifier)).fetchall()
                operations = [{**dict(row), 'outcome': json.loads(row['outcome'])} for row in rows]
                for operation in operations:
                    attempt = db.execute('SELECT payload,sha256 FROM mvp_investigation_attempts WHERE workspace_id=? AND plan_id=? AND operation=? AND request_id=?',
                        (workspace_id, origin.plan_id, operation['operation'], operation['request_id'])).fetchone()
                    operation['request'] = decoded(attempt) if attempt else None
                for row in operations:
                    if row['status'] in ('failed','pending'):
                        failures.append(InvestigationOperation(request_id=row['request_id'], operation=row['operation'].split(':')[0],
                            status=row['status'], code=row['outcome'].get('code'), message=row['outcome'].get('message'), created_at=row['created_at']))
                current = {item.candidate_id: item for item in decisions}
                results = []
                for execution in executions:
                    row = db.execute('SELECT payload,sha256 FROM mvp_investigation_previews WHERE workspace_id=? AND plan_id=? AND id=?',
                        (workspace_id, origin.plan_id, execution.id)).fetchone()
                    search = decoded(row, SearchPreview) if row else None
                    if search is None or search.id != execution.search_id or digest(search.model_dump(mode='json')) != execution.search_snapshot_sha256:
                        raise MvpError('investigation_integrity', 'The isolated candidate capture no longer matches its exact execution receipt.')
                    candidates = []
                    for paper in search.papers:
                        key = digest({'execution_id': execution.id, 'paper_id': paper.id})
                        decision = current.get(key)
                        candidates.append(InvestigationCandidate(id=key, paper=paper,
                            decision=decision.decision if decision else 'unassessed', decision_version=decision.version if decision else 0))
                    results.append(InvestigationExecution(execution=execution, search=search, candidates=candidates))
                view = InvestigationView(origin=origin, plan=plan, capabilities=capabilities, executions=results, decisions=decisions, failures=failures)
                history = [self.planning.view_in_transaction(db, workspace_id, origin.plan_id, item.revision_id)
                    for item in reversed(plan.revisions)] if audit else []
                return view, history, operations
        return self.planning._locked(handle, read)

    def operation(self, handle, identifier, kind, request):
        origin = self.origin(handle, identifier)
        if kind == 'diagnose' and request.preview_search_id is not None:
            raise MvpError('investigation_diagnostic_preview', 'Follow-up diagnostics do not use the original comparison search as a recovery sample.')
        getattr(self.planning, kind)(handle, origin.plan_id, request, **({'isolated': True} if kind == 'execute' else {}))
        return self.view(handle, identifier)

    def decide(self, handle, identifier, request):
        origin = self.origin(handle, identifier)
        fingerprint = digest({'investigation_id': identifier, 'request': request.model_dump(mode='json')})
        def write(workspace_id):
            def change(db):
                executions = db.execute('SELECT id,payload,sha256 FROM mvp_investigation_previews WHERE workspace_id=? AND plan_id=?', (workspace_id, origin.plan_id)).fetchall()
                match = None
                for row in executions:
                    result = decoded(row)
                    for paper in result['papers']:
                        if digest({'execution_id': row['id'], 'paper_id': paper['id']}) == request.candidate_id:
                            match = row['id'], paper['id']
                if match is None:
                    raise MvpError('unknown_investigation_candidate', 'Choose a candidate retained by this exact investigation.')
                version = db.execute('SELECT COALESCE(MAX(version),0) FROM mvp_investigation_decisions WHERE workspace_id=? AND investigation_id=? AND candidate_id=?', (workspace_id, identifier, request.candidate_id)).fetchone()[0]
                if version != request.expected_version:
                    raise MvpError('stale_investigation_decision', 'This candidate decision changed. Keep your note and reload before deciding again.')
                event = InvestigationDecision(investigation_id=identifier, request_id=request.request_id, candidate_id=request.candidate_id,
                    execution_id=match[0], paper_id=match[1], version=version+1, decision=request.decision, note=request.note)
                payload, checksum = packed(event.model_dump(mode='json'))
                db.execute('INSERT INTO mvp_investigation_decisions VALUES(?,?,?,?,?,?,?)',
                    (event.id, workspace_id, identifier, request.candidate_id, event.version, payload, checksum))
                return {'id': event.id}
            return self.store.mutate(workspace_id, 'investigation-decide:'+identifier, request.request_id, fingerprint, change)
        self.planning._locked(handle, write)
        return self.view(handle, identifier)

    def export(self, handle, identifier):
        view, history, operations = self._snapshot(handle, identifier, audit=True)
        payload = {'schema_version': 'mvp.investigation-audit.v1', 'investigation': view.model_dump(mode='json'),
            'plan_history': [item.model_dump(mode='json') for item in history], 'operations': operations, 'safeguards': SAFEGUARDS}
        origin = view.origin
        paper = next(p for p in origin.board.papers if p.id == origin.paper_id)
        field = next(f for f in origin.board.fields if f.id == origin.field_id)
        lines = ['# Literature investigation audit', '', '## Original comparison',
            f'Investigation: {identifier}', f'Board: {origin.board.board_id} / {origin.board.revision_id}',
            f'Paper: {paper.title} ({paper.id})', f'Field: {field.label}', f'Question: {field.subquestion}',
            f'Cell revision: {origin.cell.id if origin.cell else "No submitted revision"}',
            f'Saved draft version: {origin.draft.version}', f'Source manifest: {origin.board.source_manifest_sha256}',
            '', 'Researcher reason:', origin.reason, '', '## Scientific boundaries', *['- '+item for item in SAFEGUARDS]]
        for item in history:
            lines += ['', f'## Search plan revision {item.revision.revision}', f'Revision: {item.revision.revision_id}']
            for candidate in item.revision.compiled.candidates:
                # Indentation keeps arbitrary researcher text readable as literal
                # query content, including Markdown fence-like input.
                lines += ['', 'Exact executable query:', *['    '+line for line in candidate.query.splitlines()],
                    f'Query candidate hash: {candidate.candidate_sha256}',
                    f'Dates: {candidate.date_from} to {candidate.date_to}; sort: {candidate.sort}']
            for approval in item.approvals:
                lines += [f'Approval: {approval.id}; candidate hash: {approval.candidate_sha256}; {approval.created_at}']
            for diagnostic in item.diagnostics:
                lines += [f'Diagnostic: {diagnostic.receipt.id}; status: {diagnostic.receipt.status}; reported count: {diagnostic.receipt.reported_count}']
        for result in view.executions:
            lines += ['', '## Candidate execution', f'Execution: {result.execution.id}; approval: {result.execution.approval_id}',
                f'Saved search: {result.search.id}; hash: {result.execution.search_snapshot_sha256}',
                f'Provider: {result.search.provider}; reported: {result.search.total_reported}; fetched: {result.search.fetched_count}; capped: {result.search.truncated}']
            for candidate in result.candidates:
                lines += [f'- {candidate.paper.title} ({candidate.paper.id}): {candidate.decision}']
        lines += ['', '## Decision history']
        lines += [f'- {item.created_at}: {item.paper_id} -> {item.decision} (version {item.version}); {item.note}' for item in view.decisions]
        lines += ['', '## Request history']
        lines += [f"- {item['created_at']}: {item['operation']} / {item['request_id']}: {item['status']}" for item in operations]
        lines += ['', '## Failed or interrupted operations']
        lines += [f'- {item.operation} / {item.request_id}: {item.status}; {item.code or "outcome unknown"}; {item.message or "No automatic retry."}' for item in view.failures]
        # All researcher/provider prose is literal, including HTML, links and
        # Markdown fences. A dynamically longer fence preserves exact queries.
        body = '\n'.join(lines[2:])
        fence = '~' * max(3, 1 + max((len(m.group()) for m in re.finditer(r'~+', body)), default=0))
        return InvestigationExport(json_text=json.dumps(payload, ensure_ascii=False, indent=2),
            markdown_text='# Literature investigation audit\n\n'+fence+'text\n'+body+'\n'+fence+'\n')
