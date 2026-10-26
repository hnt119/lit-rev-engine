"""Typed manual normalization and presentation only; no retrieval/inference engine."""
import json
from pydantic import ValidationError
from src.review.exporters import _csv
from .contracts import digest, new_id
from .board_contracts import BoardCellRevision, BoardReferenceInput, BoardReferenceSummary
from .proposal_contracts import CellProposal
from .adapters.proposal_storage import ProposalStore
from .ports import MvpError
from .evidence_view_contracts import (
    DIMENSIONS, DimensionPut, DimensionDefinition, AttributePut, AttributeRevision,
    EvidenceViewConfig, SavedViewPut, SavedEvidenceView, EvidenceViewDraft,
    AttributeProjection, PaperProfileView, EvidenceProfileSet, EvidenceViewResult, ProfileDraft, AttributeHistory, SavedViewHistory,
)
TABLES = ('evidence_dimensions_v1', 'evidence_attributes_v1', 'evidence_views_v1')

def fail(code, message):
    raise MvpError(code, message)

class EvidenceViewService:
    def __init__(self, boards):
        self.boards = boards

    def _with(self, mode, handle, callback, *, write=False):
        def apply(state,db):
            if write:return callback(state,db)
            db.execute('BEGIN')
            try:return callback(state,db)
            finally:db.execute('ROLLBACK')
        return self.boards._with(mode,handle,apply,write=write)

    def _definition(self, state, db, board, revision, *, writable=False):
        definition = (self.boards._writable(state, db, board, revision) if writable else
                      self.boards.store.definition(db, state.id, board, revision))
        self.boards._dependencies(state, definition)
        return definition

    def _rows(self, db, table, definition, model):
        return [self.boards.store.decode(row, model) for row in db.execute(
            'SELECT * FROM '+table+' WHERE workspace_id=? AND board_id=? AND definition_id=? ORDER BY rowid',
            (definition.workspace_id, definition.board_id, definition.revision_id))]

    def _append(self, db, table, definition, item):
        if db.execute('SELECT COUNT(*) FROM '+table+' WHERE workspace_id=?', (definition.workspace_id,)).fetchone()[0] >= 1000:
            fail('evidence_view_limit', 'This workspace reached its bounded classification/view revision limit.')
        db.execute('INSERT INTO '+table+' VALUES(?,?,?,?,?,?)', (definition.workspace_id, definition.board_id,
            definition.revision_id, getattr(item, 'revision_id', item.id), item.model_dump_json(), digest(item.model_dump(mode='json'))))
        self.boards.store.limits(db, definition.workspace_id)

    def _config(self, definition, config):
        allowed = {*DIMENSIONS, 'availability', 'review_status', *('field:'+f.id for f in definition.fields)}
        if set(config.columns) - allowed:
            fail('invalid_evidence_view', 'Visible columns must belong to this exact comparison.')
        return config

    def bind_dimension(self, mode, handle, board, revision, request: DimensionPut):
        def apply(state, db):
            d = self._definition(state, db, board, revision, writable=True)
            fingerprint = digest({'operation':'dimension', 'board':board, 'revision':revision, 'request':request.model_dump(mode='json')})
            prior = self.boards.store.prior(db, state.id, request.request_id, fingerprint, DimensionDefinition)
            if prior: return prior
            field = self.boards._cell(d, d.paper_ids[0], request.field_id)
            records = self._rows(db, TABLES[0], d, DimensionDefinition)
            head = next((r for r in reversed(records) if r.dimension_id == request.dimension_id), None)
            if request.expected_head_id != (head.id if head else None):
                fail('stale_dimension', 'Another tab changed this dimension. Your inputs were not overwritten.')
            result = DimensionDefinition(workspace_id=state.id, board_id=board, board_revision_id=revision,
                dimension_id=request.dimension_id, field_id=field.id, field_revision_id=field.revision_id,
                label=request.label, definition=request.definition, supersedes_id=head.id if head else None)
            self._append(db, TABLES[0], d, result)
            self.boards.store.record_request(db, state.id, request.request_id, fingerprint, result)
            return result
        return self._with(mode, handle, apply, write=True)

    def classify(self, mode, handle, board, revision, request: AttributePut):
        def apply(state, db):
            d = self._definition(state, db, board, revision, writable=True)
            fingerprint = digest({'operation':'classify', 'board':board, 'revision':revision, 'request':request.model_dump(mode='json')})
            prior = self.boards.store.prior(db, state.id, request.request_id, fingerprint, AttributeRevision)
            if prior: return prior
            dimensions = self._rows(db, TABLES[0], d, DimensionDefinition)
            dimension = next((r for r in dimensions if r.id == request.dimension_revision_id), None)
            if not dimension or next(r for r in reversed(dimensions) if r.dimension_id == dimension.dimension_id).id != dimension.id:
                fail('stale_dimension', 'Use the exact current explicit dimension-to-field binding.')
            self.boards._cell(d, request.paper_id, dimension.field_id)
            records = self._rows(db, TABLES[1], d, AttributeRevision)
            head = next((r for r in reversed(records) if r.paper_id == request.paper_id and r.dimension_id == dimension.dimension_id), None)
            if request.expected_head_id != (head.id if head else None):
                fail('stale_attribute', 'Another tab changed this classification. Compare it before revising.')
            if request.origin_kind == 'cell':
                row = db.execute('SELECT * FROM board_cells WHERE workspace_id=? AND id=?', (state.id, request.origin_id)).fetchone()
                if row is None: fail('invalid_attribute_origin', 'Choose an owned submitted cell.')
                origin = self.boards.store.decode(row, BoardCellRevision)
                if (origin.board_id != board or origin.board_revision_id != revision or origin.paper_id != request.paper_id or
                    origin.field_revision_id != dimension.field_revision_id or origin.field_id != dimension.field_id or
                    self.boards.store.cell_head(db, d, request.paper_id, dimension.field_id) != origin.id):
                    fail('stale_attribute_origin', 'Use the exact current paper/field submission; no automatic rebase ran.')
                if request.review_state == 'confirmed' and (origin.semantic_assessment != 'human_supported' or not origin.references or request.value_state != 'value'):
                    fail('attribute_not_confirmable', 'Confirmed values require an explicitly human-supported source-bound submitted cell.')
                if request.value_state == 'not_found_in_inspected_material' and origin.scope_result != request.value_state:
                    fail('invalid_attribute_scope', 'Not-found must retain the existing inspected-material scope.')
                references = origin.references
            else:
                origin = ProposalStore(self.boards.store).proposal(db, state.id, board, request.origin_id)
                if (origin.board_revision_id != revision or origin.paper_id != request.paper_id or origin.field_id != dimension.field_id or
                    origin.field_revision_id != dimension.field_revision_id or origin.source_manifest_sha256 != d.source_manifest_sha256 or origin.status == 'dismissed'):
                    fail('invalid_attribute_origin', 'Use an owned non-dismissed proposal for this exact paper, field and source binding.')
                references = origin.references
            for ref in references:
                reconstructed = self.boards._reference(state, d, request.paper_id,
                    BoardReferenceInput.model_validate(ref.model_dump(include=set(BoardReferenceInput.model_fields))))
                if reconstructed != ref: fail('board_integrity', 'The normalized value source anchor changed.')
            result = AttributeRevision(**request.model_dump(), workspace_id=state.id, board_id=board,
                board_revision_id=revision, dimension_id=dimension.dimension_id, field_id=dimension.field_id,
                field_revision_id=dimension.field_revision_id, source_manifest_sha256=d.source_manifest_sha256,
                references=[BoardReferenceSummary.model_validate(ref.model_dump(exclude={'quote'}))for ref in references], supersedes_id=head.id if head else None)
            self._append(db, TABLES[1], d, result)
            self.boards.store.record_request(db, state.id, request.request_id, fingerprint, result)
            return result
        return self._with(mode, handle, apply, write=True)

    def _profiles(self, state, db, d):
        view = self.boards._view(state, db, d)
        dimensions = list({r.dimension_id:r for r in self._rows(db, TABLES[0], d, DimensionDefinition)}.values())
        all_attributes = self._rows(db, TABLES[1], d, AttributeRevision)
        attributes = {(r.paper_id,r.dimension_id):r for r in all_attributes}
        proposals = [ProposalStore(self.boards.store).with_event(db, state.id, self.boards.store.decode(row, CellProposal))
            for row in db.execute('SELECT * FROM cell_proposals WHERE workspace_id=? AND board_id=? AND definition_id=?', (state.id,d.board_id,d.revision_id))]
        papers = []
        for paper in d.papers:
            source = next(s for s in d.sources if s.paper_id == paper.id)
            pending = [p.id for p in proposals if p.paper_id == paper.id and p.status == 'pending']
            statuses = []
            projected = []
            for key in DIMENSIONS:
                binding = next((r for r in dimensions if r.dimension_id == key), None)
                item = attributes.get((paper.id,key))
                projection = AttributeProjection(dimension_id=key)
                if item:
                    head = self.boards.store.cell_head(db, d, paper.id, item.field_id)
                    outdated = (view.freshness != 'current' or not binding or binding.id != item.dimension_revision_id or
                        item.source_manifest_sha256 != d.source_manifest_sha256 or
                        item.origin_kind == 'cell' and head != item.origin_id or
                        item.origin_kind == 'proposal' and any(p.id == item.origin_id and p.status == 'dismissed' for p in proposals))
                    state_value = 'outdated' if outdated else 'unknown' if item.value_state != 'value' else item.review_state
                    projection = AttributeProjection(dimension_id=key, values=item.values, value_state=item.value_state,
                        state=state_value, reason=item.reason, revision=item)
                projected.append(projection)
                if projection.state != 'confirmed': statuses.append(projection.state)
            if pending: statuses.append('suggestions')
            if source.source_type == 'none': statuses.append('source_unavailable')
            if view.freshness != 'current': statuses.append('outdated')
            papers.append(PaperProfileView(paper_id=paper.id,title=paper.title,year=paper.year,
                availability=source.source_type,attributes=projected,review_status=sorted(set(statuses)) or ['reviewed'],pending_proposal_ids=pending))
        basis = digest({'definition':d.revision_id,'dimensions':[r.model_dump(mode='json')for r in dimensions],'attributes':[r.model_dump(mode='json')for r in all_attributes],
            'heads':[(c.paper_id,c.field_id,c.head.id if c.head else None) for c in view.cells],
            'proposals':[(p.id,p.status)for p in proposals],'freshness':view.freshness})
        return EvidenceProfileSet(board_id=d.board_id, board_revision_id=d.revision_id, freshness=view.freshness,
            basis_sha256=basis,dimensions=dimensions,papers=papers)

    def profiles(self, mode, handle, board, revision):
        return self._with(mode, handle, lambda state,db:self._profiles(state,db,self._definition(state,db,board,revision)))

    def _query(self, profiles, config):
        def values(paper, dimension):
            if dimension == 'availability': return [paper.availability]
            if dimension == 'review_status': return paper.review_status
            item = next(a for a in paper.attributes if a.dimension_id == dimension)
            if item.state == 'confirmed' or config.include_unreviewed and item.state == 'unreviewed': return item.values or ['unknown']
            return ['unknown']
        selected = [p for p in profiles.papers if all(set(values(p,f.dimension)) & set(f.values) for f in config.filters)]
        if config.sort_by != 'report_order':
            key = {'title':lambda p:(p.title.casefold(),p.paper_id),'year':lambda p:(p.year is None,p.year or 0,p.paper_id),
                'review_status':lambda p:(','.join(p.review_status),p.paper_id)}[config.sort_by]
            selected.sort(key=key,reverse=config.descending)
        elif config.descending: selected.reverse()
        groups = {}
        for paper in selected:
            for key in values(paper, config.group_by) if config.group_by else ['All reports']:
                groups.setdefault(key,[]).append(paper.paper_id)
        facets = {key:sorted({value for paper in profiles.papers for value in values(paper,key)}) for key in (*DIMENSIONS,'availability','review_status')}
        summary = ' AND '.join(f.dimension+' = ('+' OR '.join(f.values)+')' for f in config.filters) or 'All reports; no scientific filters'
        return EvidenceViewResult(config=config,profiles=profiles,paper_ids=[p.paper_id for p in selected],groups=groups,
            unique_report_count=len(selected),group_occurrences=sum(len(g)for g in groups.values()),facets=facets,filter_summary=summary)

    def query(self, mode, handle, board, revision, config):
        def read(state,db):
            d=self._definition(state,db,board,revision)
            return self._query(self._profiles(state,db,d),self._config(d,config))
        return self._with(mode,handle,read)

    def views(self, mode, handle, board, revision):
        def read(state,db):
            d=self._definition(state,db,board,revision)
            return list({r.id:r for r in self._rows(db,TABLES[2],d,SavedEvidenceView)}.values())
        return self._with(mode,handle,read)

    def save_view(self,mode,handle,board,revision,request:SavedViewPut,view_id=None):
        def apply(state,db):
            d=self._definition(state,db,board,revision)
            config=self._config(d,request.config)
            fingerprint=digest({'operation':'saved-view','board':board,'revision':revision,'view':view_id,'request':request.model_dump(mode='json')})
            prior=self.boards.store.prior(db,state.id,request.request_id,fingerprint,SavedEvidenceView)
            if prior:return prior
            rows=self._rows(db,TABLES[2],d,SavedEvidenceView)
            head=next((r for r in reversed(rows)if r.id==view_id),None)if view_id else None
            if view_id and not head:fail('unknown_evidence_view','The saved view is unavailable in this exact comparison.')
            if request.version!=(head.version if head else 0):fail('stale_evidence_view','Another tab changed this view. Keep your local filters and compare before saving.')
            if not view_id and len({r.id for r in rows})>=20:fail('evidence_view_limit','Keep at most twenty named views for this board definition.')
            snapshot=self._query(self._profiles(state,db,d),config)
            result=SavedEvidenceView(id=view_id or new_id(),workspace_id=state.id,board_id=board,board_revision_id=revision,
                version=request.version+1,name=request.name,config=config,basis_sha256=snapshot.profiles.basis_sha256,paper_ids=snapshot.paper_ids)
            self._append(db,TABLES[2],d,result)
            self.boards.store.record_request(db,state.id,request.request_id,fingerprint,result)
            return result
        return self._with(mode,handle,apply,write=True)

    def view_draft(self,mode,handle,scope,request=None):
        identity=scope.removeprefix('board-view:').split(':')
        if not scope.startswith('board-view:')or len(identity)!=2 or any(not x or len(x)>200 for x in identity):fail('invalid_evidence_view','Use an exact owned board/revision view draft.')
        board,revision=identity
        def apply(state,db):
            d=self._definition(state,db,board,revision)
            prior=self.boards.registry.draft(state.id,scope)
            if request is not None:
                if request.version!=prior['version']:fail('stale_draft','Another tab changed the view draft. Research cell edits were not overwritten.')
                if request.expected_assessment_head is not None:fail('invalid_evidence_view','View settings cannot set a scientific assessment head.')
            data=request.data if request is not None else prior['data']
            if request is not None or prior['version']:
                try:value=EvidenceViewDraft.model_validate(data)
                except ValidationError:fail('invalid_evidence_view','Keep only bounded typed view controls and owned identifiers.')
                if value.board_id!=board or value.board_revision_id!=revision:fail('invalid_evidence_view','View draft belongs to another board definition.')
                self._config(d,value.config)
                rows=self._rows(db,TABLES[2],d,SavedEvidenceView)
                if value.view_id and not any(r.id==value.view_id for r in rows):fail('unknown_evidence_view','The chosen view belongs to another definition.')
                if value.base_view_version and not any(r.id==value.view_id and r.version==value.base_view_version for r in rows):fail('invalid_evidence_view','Keep the exact selected saved view baseline version.')
            return prior if request is None else self.boards.registry.put_draft(state.id,scope,version=request.version,data=value.model_dump(mode='json'),expected_assessment_head=None)
        return self._with(mode,handle,apply)

    def export(self,mode,handle,board,revision,config,format):
        def read(state,db):
            d=self._definition(state,db,board,revision)
            self._config(d,config)
            profiles=self._profiles(state,db,d)
            result=self._query(profiles,config)
            cells=self.boards._view(state,db,d).cells
            rows=[]
            visible_dimensions={c for c in config.columns if c in DIMENSIONS}
            paper_profiles=[]
            for order,paper_id in enumerate(result.paper_ids,1):
                paper=next(p for p in result.profiles.papers if p.paper_id==paper_id)
                visible={}
                for column in config.columns:
                    if column.startswith('field:'):
                        field=next(f for f in d.fields if f.id==column.removeprefix('field:'))
                        cell=next(c for c in cells if c.paper_id==paper_id and c.field_id==field.id)
                        visible[column]={'state':'submitted'if cell.head else 'unsubmitted','field_revision_id':field.revision_id,
                            'head':cell.head.model_dump(mode='json')if cell.head else None}
                    elif column in DIMENSIONS:
                        visible[column]=next(a for a in paper.attributes if a.dimension_id==column).model_dump(mode='json')
                    elif column=='availability':visible[column]=paper.availability
                    elif column=='review_status':visible[column]=paper.review_status
                rows.append({'order':order,'paper_id':paper_id,'paper_title':paper.title,'visible_values':visible})
                projection={'paper_id':paper_id,'title':paper.title,'attributes':[a.model_dump(mode='json')for a in paper.attributes if a.dimension_id in visible_dimensions]}
                if 'availability'in config.columns:projection['availability']=paper.availability
                if 'review_status'in config.columns:projection['review_status']=paper.review_status
                paper_profiles.append(projection)
            scope={'board_id':board,'board_revision_id':revision,'preparation_id':d.preparation_id,
                'source_manifest_sha256':d.source_manifest_sha256,'retrieval_profile_sha256':d.retrieval_profile_sha256}
            view={'config':config.model_dump(mode='json'),'paper_ids':result.paper_ids,'groups':result.groups,
                'unique_report_count':result.unique_report_count,'group_occurrences':result.group_occurrences,
                'filter_summary':result.filter_summary,'profiles':{'board_id':board,'board_revision_id':revision,
                    'basis_sha256':profiles.basis_sha256,'scope':profiles.scope,'papers':paper_profiles,
                    'dimensions':[v.model_dump(mode='json')for v in profiles.dimensions if v.dimension_id in visible_dimensions]},
                'facets':{},'filter_basis_context':'Filters/grouping use the selected report-level facts; hidden attributes and drafts are omitted.'}
            value={'schema_version':'mvp.evidence-view-export.v1','scope':scope,'view':view,'rows':rows,
                'meaning':'Actual visible table: filtered ordered reports, submitted heads or unsubmitted nulls; report cooccurrence only, not eligibility or independent studies'}
            if format=='json':return json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
            fields=['schema_version','board_id','board_revision_id','basis_sha256','view_config','order','paper_id','paper_title','visible_values']
            return _csv([{'schema_version':value['schema_version'],'board_id':board,'board_revision_id':revision,
                'basis_sha256':profiles.basis_sha256,'view_config':config.model_dump(mode='json'),**row}for row in rows],fields)
        return self._with(mode,handle,read)

    def profile_draft(self,mode,handle,scope,request=None):
        parts=scope.removeprefix('board-profile:').split(':')
        if not scope.startswith('board-profile:')or len(parts)!=3 or any(not p or len(p)>1600 for p in parts):
            fail('invalid_profile_draft','Use an exact owned paper profile draft.')
        board,revision,encoded=parts
        try:paper=bytes.fromhex(encoded).decode('utf-8')
        except (ValueError,UnicodeError):fail('invalid_profile_draft','Use a valid bounded paper identifier.')
        def apply(state,db):
            d=self._definition(state,db,board,revision)
            self.boards._cell(d,paper,d.fields[0].id)
            prior=self.boards.registry.draft(state.id,scope)
            if request is not None:
                self.boards._writable(state,db,board,revision)
                if request.version!=prior['version']:fail('stale_draft','Another tab changed this profile draft. Your local values remain here.')
                if request.expected_assessment_head is not None:fail('invalid_profile_draft','Profile form drafts cannot set scientific assessment heads.')
            data=request.data if request is not None else prior['data']
            if request is not None or prior['version']:
                try:value=ProfileDraft.model_validate(data)
                except ValidationError:fail('invalid_profile_draft','Keep bounded unfinished profile inputs and owned identifiers.')
                if (value.board_id,value.board_revision_id,value.paper_id)!=(board,revision,paper):fail('invalid_profile_draft','The profile form belongs to another exact paper scope.')
                self.boards._cell(d,paper,value.field_id)
                dimensions=self._rows(db,TABLES[0],d,DimensionDefinition)
                attributes=self._rows(db,TABLES[1],d,AttributeRevision)
                if value.base_dimension_head_id and not any(r.id==value.base_dimension_head_id and r.dimension_id==value.dimension_id for r in dimensions):
                    fail('invalid_profile_draft','The retained dimension baseline belongs to another scope.')
                if value.base_attribute_head_id and not any(r.id==value.base_attribute_head_id and r.dimension_id==value.dimension_id and r.paper_id==paper for r in attributes):
                    fail('invalid_profile_draft','The retained classification baseline belongs to another scope.')
                if value.origin_cell_head_id:
                    row=db.execute('SELECT * FROM board_cells WHERE workspace_id=? AND id=?',(state.id,value.origin_cell_head_id)).fetchone()
                    origin=self.boards.store.decode(row,BoardCellRevision)if row else None
                    if not origin or origin.board_id!=board or origin.board_revision_id!=revision or origin.paper_id!=paper:
                        fail('invalid_profile_draft','The retained cell baseline belongs to another paper scope.')
                if value.origin!='cell':
                    proposal=ProposalStore(self.boards.store).proposal(db,state.id,board,value.origin)
                    if proposal.board_revision_id!=revision or proposal.paper_id!=paper:fail('invalid_profile_draft','The proposed origin belongs to another paper scope.')
            return prior if request is None else self.boards.registry.put_draft(state.id,scope,version=request.version,data=value.model_dump(mode='json'),expected_assessment_head=None)
        return self._with(mode,handle,apply)

    def attribute_history(self,mode,handle,board,revision,paper,dimension,offset=0,limit=20):
        if type(offset)is not int or type(limit)is not int or offset<0 or not 1<=limit<=50:fail('invalid_page','Choose a bounded history page.')
        def read(state,db):
            d=self._definition(state,db,board,revision)
            self.boards._cell(d,paper,d.fields[0].id)
            rows=[r for r in self._rows(db,TABLES[1],d,AttributeRevision)if r.paper_id==paper and r.dimension_id==dimension]
            items=list(reversed(rows))[offset:offset+limit]
            ids={r.dimension_revision_id for r in items}
            definitions=[r for r in self._rows(db,TABLES[0],d,DimensionDefinition)if r.id in ids]
            return AttributeHistory(items=items,dimension_definitions=definitions,offset=offset,total=len(rows),limit=limit)
        return self._with(mode,handle,read)

    def view_history(self,mode,handle,board,revision,view_id,offset=0,limit=20):
        if type(offset)is not int or type(limit)is not int or offset<0 or not 1<=limit<=50:fail('invalid_page','Choose a bounded history page.')
        def read(state,db):
            d=self._definition(state,db,board,revision)
            rows=[r for r in self._rows(db,TABLES[2],d,SavedEvidenceView)if r.id==view_id]
            if not rows:fail('unknown_evidence_view','This view belongs to another exact definition or is unavailable.')
            return SavedViewHistory(items=list(reversed(rows))[offset:offset+limit],offset=offset,total=len(rows),limit=limit)
        return self._with(mode,handle,read)
