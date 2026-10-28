"""Explicit bridges from isolated candidates to existing collections and notes.

No providers, source replacement, board edits or scientific judgments occur here.
Every mutation shares the investigation lifecycle/workspace guard and research DB.
"""
from .contracts import digest, new_id, SearchPreview
from .ports import MvpError
from .collections import _apply_policy, duplicate_groups
from .collection_contracts import InvestigationMemberOrigin, PaperCollectionSnapshot
from .collection_preparation_contracts import CollectionPreparationResult
from .board_contracts import BoardReference, MAX_INSPECTOR_CHARACTERS
from .search_plan_contracts import SearchPlanExecution, SearchApprovalReceipt
from .investigation_contracts import InvestigationDecision
from .investigation_research_contracts import (
    InvestigationHandoff, InvestigationHandoffPreview, InvestigationHandoffMember,
    InvestigationInspection, ResearchEvaluationNote, InvestigationResearchState,
)
from .adapters.search_plan_storage import packed, decoded
from .service import _find, _assert_source_integrity, _manifest
from .origin_resolver import resolve_run
from .limits import MAX_BOARD_PAPERS

RESEARCH_TABLES = ('mvp_investigation_handoffs', 'mvp_investigation_inspections', 'mvp_research_evaluation_notes')
MAX_NOTE_REVISIONS = 50
MAX_NOTE_RECORDS = 500
MAX_INSPECTIONS = 500


def research_state(db, workspace_id, identifier):
    models = (InvestigationHandoff, InvestigationInspection, ResearchEvaluationNote)
    values = [[decoded(row, model) for row in db.execute(
        f'SELECT payload,sha256 FROM {table} WHERE workspace_id=? AND investigation_id=? ORDER BY rowid',
        (workspace_id, identifier))] for table, model in zip(RESEARCH_TABLES, models)]
    if any(item.investigation_id != identifier for group in values for item in group):
        raise MvpError('investigation_integrity','A retained research record no longer matches this investigation.')
    return InvestigationResearchState(investigation_id=identifier, handoffs=values[0], inspections=values[1], notes=values[2])


class InvestigationResearchService:
    def __init__(self, investigation, collections):
        self.investigation, self.collections = investigation, collections
        self.boards, self.planning, self.store = investigation.boards, investigation.planning, investigation.store

    def _guard(self, mode, handle, operation, request, identifier, callback):
        fingerprint = digest({'investigation_id':identifier, 'request':request.model_dump(mode='json')})
        def guarded(state, board_db):
            def change(db):
                origin = self.store.origin(db, state.id, identifier)
                result = callback(state, board_db, db, origin)
                payload, checksum = packed(request.model_dump(mode='json'))
                db.execute('INSERT INTO mvp_investigation_attempts VALUES(?,?,?,?,?,?,?)',
                    (new_id(),state.id,origin.plan_id,operation+':'+identifier,request.request_id,payload,checksum))
                return result
            return self.store.mutate(state.id, operation+':'+identifier, request.request_id, fingerprint, change)
        return self.boards._with(mode, handle, guarded)

    def state(self, handle, identifier):
        def read(workspace_id):
            with self.store.connection() as db:
                db.execute('BEGIN')
                self.store.origin(db, workspace_id, identifier)
                return research_state(db, workspace_id, identifier)
        return self.planning._locked(handle, read)

    def _handoff_input(self, state, board_db, db, origin, request, handoff_id='pending'):
        # Revalidate the captured original, including historical source bindings.
        definition = self.boards.store.definition(board_db, state.id, origin.board.board_id, origin.board.revision_id)
        if definition != origin.board:
            raise MvpError('investigation_integrity', 'The captured original comparison no longer matches its retained definition.')
        bibliography, preparation, _ = self.boards._dependencies(state, definition)
        if set(request.original_paper_ids) - set(definition.paper_ids):
            raise MvpError('unknown_investigation_original_paper', 'Choose previous reports from this investigation original comparison.')
        common = dict(investigation_id=origin.id, handoff_id=handoff_id, original_board_id=definition.board_id,
            original_board_revision_id=definition.revision_id, original_cell_revision_id=origin.cell.id if origin.cell else None,
            original_source_manifest_sha256=definition.source_manifest_sha256)
        members, labels = [], []
        if isinstance(preparation, CollectionPreparationResult):
            originals = {member.paper.id:member for member in preparation.member_snapshots}
        else:
            search = _find(state.searches, preparation.search_id, 'search')
            originals = {member.paper.id:member for member in self.collections._search_collection(state, search).members}
        for paper_id in request.original_paper_ids:
            member = originals[paper_id]
            linked = InvestigationMemberOrigin(kind='investigation_original_report', **common,
                paper_id=paper_id, metadata_version_id=member.metadata_version.id)
            member = member.model_copy(update={'origins':[*member.origins, linked]})
            key = 'original:'+paper_id
            members.append((key, member)); labels.append(InvestigationHandoffMember(selection_id=key, paper=member.paper, kind='original_report'))
        decisions = {}
        for row in db.execute('SELECT payload,sha256 FROM mvp_investigation_decisions WHERE workspace_id=? AND investigation_id=? ORDER BY rowid',(state.id,origin.id)):
            value = decoded(row, InvestigationDecision); decisions[value.candidate_id] = value
        indexed = {}
        rows = db.execute('SELECT id,payload,sha256 FROM mvp_investigation_previews WHERE workspace_id=? AND plan_id=?',(state.id,origin.plan_id)).fetchall()
        for row in rows:
            search = decoded(row, SearchPreview)
            execution = self.store.event(db,state.id,origin.plan_id,row['id'],'execution',SearchPlanExecution)
            if execution.search_id != search.id or execution.search_snapshot_sha256 != digest(search.model_dump(mode='json')):
                raise MvpError('investigation_integrity', 'The isolated provider capture no longer matches its retained execution.')
            approval = self.store.event(db,state.id,origin.plan_id,execution.approval_id,'approval',SearchApprovalReceipt)
            if (approval.revision_id != execution.revision_id or approval.candidate_id != execution.candidate_id
                    or approval.candidate_sha256 != execution.candidate_sha256):
                raise MvpError('investigation_integrity', 'The retained execution no longer matches its exact approved query.')
            for member in self.collections._search_collection(state,search).members:
                key = digest({'execution_id':execution.id,'paper_id':member.paper.id})
                indexed[key] = (member,search,execution)
        for selected in request.candidates:
            item, decision = indexed.get(selected.candidate_id), decisions.get(selected.candidate_id)
            if item is None or decision is None or decision.decision != 'shortlist':
                raise MvpError('investigation_shortlist_required', 'Only manually shortlisted candidates can be committed to this collection.')
            if decision.version != selected.expected_decision_version:
                raise MvpError('stale_investigation_decision','The candidate decision changed. Review the shortlist again before committing.')
            member, search, execution = item
            linked = InvestigationMemberOrigin(kind='investigation_candidate', **common,
                candidate_id=selected.candidate_id, decision_id=decision.id, decision_version=decision.version,
                execution_id=execution.id, plan_id=execution.plan_id, plan_revision_id=execution.revision_id,
                approval_id=execution.approval_id, candidate_sha256=execution.candidate_sha256, approved_query=search.query,
                search_id=search.id, search_snapshot_sha256=execution.search_snapshot_sha256,
                paper_id=member.paper.id, metadata_version_id=member.metadata_version.id)
            member = member.model_copy(update={'origins':[linked]})
            key = 'candidate:'+selected.candidate_id
            members.append((key,member));labels.append(InvestigationHandoffMember(selection_id=key,paper=member.paper,kind='candidate'))
        # Handoff ID is assigned only at commit; it is not part of reviewed input.
        payload = {'request':request.model_dump(mode='json',exclude={'request_id','preview_sha256'}),
            'members':[{'selection_id':key,'member':member.model_dump(mode='json')} for key,member in members]}
        checksum = digest(payload)
        return members, labels, checksum, bibliography.origin

    def preview(self, mode, handle, identifier, request):
        def read(state, board_db):
            with self.store.connection() as db:
                db.execute('BEGIN')
                origin = self.store.origin(db,state.id,identifier)
                members, labels, checksum, _ = self._handoff_input(state,board_db,db,origin,request)
                return InvestigationHandoffPreview(input_sha256=checksum,members=labels,duplicate_groups=duplicate_groups(members),
                    original_board_id=origin.board.board_id,original_board_revision_id=origin.board.revision_id)
        return self.boards._with(mode,handle,read)

    def commit(self, mode, handle, identifier, request):
        def write(state, board_db, db, origin):
            members, _, checksum, parent = self._handoff_input(state,board_db,db,origin,request)
            if request.preview_sha256 != checksum:
                raise MvpError('stale_investigation_handoff','Review this exact selected candidate collection before committing it.')
            output, decisions = _apply_policy(members,request.duplicate_policy,request.conflict_decisions)
            if len(output) > MAX_BOARD_PAPERS:
                raise MvpError('investigation_comparison_capacity',f'This selection exceeds the {MAX_BOARD_PAPERS}-paper comparison limit. Choose a smaller explicit set; no papers were discarded.')
            identifier = new_id()
            output = [member.model_copy(update={'origins':[o.model_copy(update={'handoff_id':identifier}) if isinstance(o,InvestigationMemberOrigin) and o.handoff_id=='pending' else o for o in member.origins]}) for member in output]
            snapshot = PaperCollectionSnapshot(workspace_id=state.id,name=request.name,kind='combined' if request.original_paper_ids else 'subset',
                members=output,parents=[parent] if request.original_paper_ids else [],input_digests=[checksum],duplicate_decisions=decisions,
                coverage='explicit_combination' if request.original_paper_ids else 'explicit_subset')
            collection_sha = self.collections.store.insert_collection(db,snapshot)
            self.collections.store._limits(db,state.id)
            event = InvestigationHandoff(id=identifier,investigation_id=origin.id,request_id=request.request_id,selection_sha256=checksum,
                collection=self.collections._collection_summary(snapshot,collection_sha),original_board_id=origin.board.board_id,
                original_board_revision_id=origin.board.revision_id,original_cell_revision_id=origin.cell.id if origin.cell else None,
                selected_candidate_ids=[c.candidate_id for c in request.candidates],selected_original_paper_ids=request.original_paper_ids)
            self._insert(db,'mvp_investigation_handoffs',state.id,origin.id,event.id,event)
            return event.model_dump(mode='json')
        return InvestigationHandoff.model_validate(self._guard(mode,handle,'investigation-handoff',request,identifier,write))

    @staticmethod
    def _insert(db,table,workspace_id,investigation_id,key,value):
        payload,checksum = packed(value.model_dump(mode='json'))
        db.execute(f'INSERT INTO {table} VALUES(?,?,?,?,?)',(key,workspace_id,investigation_id,payload,checksum))

    @staticmethod
    def _record(db,table,workspace_id,investigation_id,identifier,model):
        row = db.execute(f'SELECT payload,sha256 FROM {table} WHERE workspace_id=? AND investigation_id=? AND id=?',(workspace_id,investigation_id,identifier)).fetchone()
        if row is None:
            raise MvpError('unknown_investigation_research_record','This research record does not belong to the investigation.')
        value = decoded(row,model)
        if value.id != identifier or value.investigation_id != investigation_id:
            raise MvpError('investigation_integrity','The retained research record identity changed.')
        return value

    def _inspection_context(self,state,db,origin,request):
        handoff = self._record(db,'mvp_investigation_handoffs',state.id,origin.id,request.handoff_id,InvestigationHandoff)
        preparation = _find(state.preparations,request.preparation_id,'preparation')
        if not isinstance(preparation,CollectionPreparationResult) or preparation.collection_ref != handoff.collection.origin:
            raise MvpError('unprepared_investigation_source','Prepare this exact committed candidate collection before attaching source evidence.')
        run = _find(state.runs,request.run_id,'run')
        bound, _ = resolve_run(state,run)
        if bound.id != preparation.id or run.source_snapshot_sha256 != digest(_manifest(preparation.sources)):
            raise MvpError('unrelated_investigation_passage','Retrieve passages from this exact prepared candidate collection.')
        _assert_source_integrity(preparation.sources)
        context = self.planning.engine._source_context(state,run,preparation.sources,request.passage_id)
        member = next((m for m in preparation.member_snapshots if m.paper.id == context.paper.id),None)
        if member is None or not any(isinstance(o,InvestigationMemberOrigin) and o.kind=='investigation_candidate'
                and o.investigation_id==origin.id and o.handoff_id==handoff.id for o in member.origins):
            raise MvpError('investigation_candidate_source_required','Research evaluation evidence must come from a shortlisted candidate committed through this investigation.')
        return context,run,preparation

    def inspect(self,mode,handle,identifier,request):
        def write(state,board_db,db,origin):
            context,run,preparation = self._inspection_context(state,db,origin,request)
            source,block,passage = context.source,context.block,context.passage
            start = passage.anchor.start if request.start is None else request.start
            end = passage.anchor.end if request.end is None else request.end
            if not 0 <= start < end <= len(block.text) or end-start > MAX_INSPECTOR_CHARACTERS:
                raise MvpError('invalid_investigation_excerpt','Choose a nonempty bounded Unicode range in this retained passage block.')
            # A receipt retains exactly what the explicit inspector displays. It
            # is not a declaration that the researcher read/supports the passage.
            reference = BoardReference(id='research-ref:'+digest([run.id,passage.id,start,end]),paper_id=source.paper_id,
                source_id=source.id,source_version=source.version,source_sha256=source.source_sha256,blocks_sha256=source.blocks_sha256,
                block_id=block.id,start=start,end=end,quote=block.text[start:end],locator=block.locator)
            count=db.execute('SELECT COUNT(*) FROM mvp_investigation_inspections WHERE workspace_id=?',(state.id,)).fetchone()[0]
            if count >= MAX_INSPECTIONS:raise MvpError('investigation_inspection_limit','This workspace reached its retained inspection limit.')
            event=InvestigationInspection(investigation_id=origin.id,handoff_id=request.handoff_id,preparation_id=preparation.id,
                run_id=run.id,passage_id=passage.id,source_paper=context.paper,reference=reference,source_type=source.source_type,
                source_status=source.status,source_manifest_sha256=run.source_snapshot_sha256,source_revision=preparation.source_revision)
            self._insert(db,'mvp_investigation_inspections',state.id,origin.id,event.id,event)
            return event.model_dump(mode='json')
        return InvestigationInspection.model_validate(self._guard(mode,handle,'investigation-inspect',request,identifier,write))

    def note(self,mode,handle,identifier,request):
        def write(state,board_db,db,origin):
            inspection=self._record(db,'mvp_investigation_inspections',state.id,origin.id,request.inspection_id,InvestigationInspection)
            # The exact source remains required, even after this preparation is
            # historical. A newer global preparation never rewrites this binding.
            context,_,_=self._inspection_context(state,db,origin,inspection)
            ref=inspection.reference
            if (context.source.id != ref.source_id or context.source.version != ref.source_version
                or context.source.source_sha256 != ref.source_sha256 or context.source.blocks_sha256 != ref.blocks_sha256
                or context.block.id != ref.block_id or context.block.text[ref.start:ref.end] != ref.quote
                or context.paper != inspection.source_paper):
                raise MvpError('investigation_source_integrity','The inspected source no longer matches its exact retained passage.')
            if request.note_id:
                versions=[decoded(row,ResearchEvaluationNote) for row in db.execute('SELECT payload,sha256 FROM mvp_research_evaluation_notes WHERE workspace_id=? AND investigation_id=? ORDER BY rowid',(state.id,origin.id))]
                prior=next((v for v in reversed(versions) if v.id==request.note_id),None)
                if prior is None:raise MvpError('unknown_research_evaluation_note','Choose a note in this investigation.')
                if prior.revision_id != request.expected_revision_id:raise MvpError('stale_research_evaluation_note','This note changed in another tab. Keep your interpretation and inspect the current saved revision.')
                if prior.revision>=MAX_NOTE_REVISIONS:raise MvpError('research_note_revision_limit','This note reached its retained revision limit.')
                note_id,revision,parent=prior.id,prior.revision+1,prior.revision_id
            else:note_id,revision,parent=new_id(),1,None
            if db.execute('SELECT COUNT(*) FROM mvp_research_evaluation_notes WHERE workspace_id=?',(state.id,)).fetchone()[0]>=MAX_NOTE_RECORDS:
                raise MvpError('research_note_limit','This workspace reached its retained research-note limit.')
            event=ResearchEvaluationNote(id=note_id,revision=revision,parent_revision_id=parent,investigation_id=origin.id,
                original_board_id=origin.board.board_id,original_board_revision_id=origin.board.revision_id,
                original_paper_id=origin.paper_id,original_field_id=origin.field_id,original_cell_revision_id=origin.cell.id if origin.cell else None,
                research_question=request.research_question,interpretation=request.interpretation,inspection=inspection)
            self._insert(db,'mvp_research_evaluation_notes',state.id,origin.id,event.revision_id,event)
            return event.model_dump(mode='json')
        return ResearchEvaluationNote.model_validate(self._guard(mode,handle,'investigation-note',request,identifier,write))
