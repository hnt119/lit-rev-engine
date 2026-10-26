"""Revision-bound search-design notes; legacy intent/compiler records stay exact."""
from datetime import date
import re
from typing import Literal
from pydantic import Field, field_validator, model_validator
from .contracts import Model, digest, now
from .collection_contracts import CollectionInputRef
from .ports import MvpError
from .search_plan_contracts import QuestionSpan
from .adapters.search_plan_storage import packed, decoded, search_plan_auxiliary_bytes
from .search_plan_service_contracts import MAX_PLAN_AUXILIARY_BYTES


class ExtractionQuestion(Model):
    id: str = Field(min_length=1,max_length=100)
    question: str = Field(default='',max_length=2000)
    source_span: QuestionSpan | None = None


class TermReferenceNote(Model):
    concept_id: str = Field(min_length=1,max_length=100)
    term_id: str = Field(min_length=1,max_length=100)
    note: str = Field(default='',max_length=2000)
    authority_reference: str = Field(default='',max_length=2000)


class ExternalSearchRecord(Model):
    id: str = Field(min_length=1,max_length=100)
    database: str = Field(default='',max_length=200)
    platform: str = Field(default='',max_length=200)
    query: str = Field(default='',max_length=20000)
    executed_on: str | None = None
    reported_count: int | None = Field(default=None,ge=0,le=2**63-1,strict=True)
    limits_note: str = Field(default='',max_length=2000)
    collection_ref: CollectionInputRef | None = None

    @field_validator('query')
    @classmethod
    def exact_query(cls,value):
        value.encode('utf-8')
        return value

    @field_validator('executed_on')
    @classmethod
    def execution_date(cls,value):
        if value is not None:date.fromisoformat(value)
        return value


class SearchPlanMetadataDraftInput(Model):
    extraction_questions: list[ExtractionQuestion] = Field(default_factory=list,max_length=12)
    term_notes: list[TermReferenceNote] = Field(default_factory=list,max_length=96)
    external_searches: list[ExternalSearchRecord] = Field(default_factory=list,max_length=5)

    @model_validator(mode='after')
    def unique_ids(self):
        for values in ([q.id for q in self.extraction_questions],[(n.concept_id,n.term_id) for n in self.term_notes],[e.id for e in self.external_searches]):
            if len(values)!=len(set(values)):raise ValueError('Use distinct note, field and external-search identities')
        pending=[self.model_dump(mode='json')]
        while pending:
            item=pending.pop()
            if isinstance(item,str):item.encode('utf-8')
            elif isinstance(item,dict):pending.extend(item.values())
            elif isinstance(item,list):pending.extend(item)
        return self


class SavedExtractionQuestion(ExtractionQuestion):
    question: str = Field(min_length=1,max_length=2000)

    @field_validator('question')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('Complete or remove this extraction question')
        return value


class SavedExternalSearchRecord(ExternalSearchRecord):
    database: str = Field(min_length=1,max_length=200)
    platform: str = Field(min_length=1,max_length=200)
    query: str = Field(min_length=1,max_length=20000)
    collection_ref: CollectionInputRef

    @field_validator('database','platform','query')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('Complete or remove this external strategy')
        return value


class SearchPlanMetadataInput(SearchPlanMetadataDraftInput):
    extraction_questions: list[SavedExtractionQuestion] = Field(default_factory=list,max_length=12)
    external_searches: list[SavedExternalSearchRecord] = Field(default_factory=list,max_length=5)


class SearchPlanMetadataPut(Model):
    request_id: str = Field(min_length=1,max_length=200)
    expected_revision_id: str = Field(min_length=1,max_length=200)
    expected_version: int = Field(ge=0,strict=True)
    metadata: SearchPlanMetadataInput


class SearchPlanMetadataDraft(Model):
    plan_id: str = Field(min_length=1,max_length=200)
    revision_id: str = Field(min_length=1,max_length=200)
    base_metadata_version: int = Field(ge=0,strict=True)
    metadata: SearchPlanMetadataDraftInput = Field(default_factory=SearchPlanMetadataDraftInput)


class SearchPlanMetadataView(Model):
    schema_version: Literal['mvp.search-plan-metadata.v1'] = 'mvp.search-plan-metadata.v1'
    plan_id: str
    revision_id: str
    version: int
    latest_version: int
    metadata: SearchPlanMetadataInput
    term_bindings: list[dict]
    current: bool
    history: list[dict]
    saved_at: str | None = None
    terminology_verification: Literal['unavailable'] = 'unavailable'
    meaning: Literal['researcher_design_notes_not_eligibility_or_verified_terminology'] = 'researcher_design_notes_not_eligibility_or_verified_terminology'


class StoredSearchPlanMetadata(Model):
    version: int = Field(ge=1,strict=True)
    metadata: SearchPlanMetadataInput
    saved_at: str = Field(min_length=1,max_length=100)


class SearchPlanMetadataService:
    """The existing research SQLite and UI-draft CAS own all new state."""
    def __init__(self,planning,registry,collections_for):
        self.planning,self.registry,self.collections_for=planning,registry,collections_for
        self._ready=set()

    def _services(self,mode):
        plans=self.planning(mode);collections=self.collections_for(mode)
        key=str(plans.store.storage._path)
        if key not in self._ready:
            with plans.store.connection() as db:
                db.execute('''CREATE TABLE IF NOT EXISTS mvp_search_plan_metadata(
                    workspace_id TEXT NOT NULL,plan_id TEXT NOT NULL,revision_id TEXT NOT NULL,
                    version INTEGER NOT NULL,payload TEXT NOT NULL,sha256 TEXT NOT NULL,created_at TEXT NOT NULL,
                    PRIMARY KEY(workspace_id,plan_id,revision_id,version),
                    FOREIGN KEY(workspace_id) REFERENCES mvp_workspaces(id) ON DELETE CASCADE,
                    FOREIGN KEY(plan_id) REFERENCES mvp_search_plans(id) ON DELETE CASCADE)''')
            self._ready.add(key)
        return plans,collections

    @staticmethod
    def _latest(db,workspace,plan,revision):
        row=db.execute('SELECT payload,sha256,version FROM mvp_search_plan_metadata WHERE workspace_id=? AND plan_id=? AND revision_id=? ORDER BY version DESC LIMIT 1',(workspace,plan,revision)).fetchone()
        if row is None:return {'version':0,'metadata':SearchPlanMetadataInput().model_dump(mode='json'),'saved_at':None}
        return SearchPlanMetadataService._decode(row)

    @staticmethod
    def _decode(row):
        value=decoded(row,StoredSearchPlanMetadata)
        if value.version!=row['version']:raise MvpError('search_plan_integrity','The retained design-note version does not match its stored identity.')
        return value.model_dump(mode='json')

    @staticmethod
    def _validate(revision,metadata,collections,db,*,draft=False):
        for item in metadata.extraction_questions:
            if not draft and not item.question.strip():raise MvpError('metadata_incomplete','Complete or remove each extraction question before saving design notes.')
            span=item.source_span
            if span and revision.draft.original_question[span.start:span.end]!=span.text:
                raise MvpError('metadata_source_span','An extraction question span must match the exact original question.')
        terms={(c.id,t.id) for c in revision.draft.concepts for t in c.terms}
        if any((n.concept_id,n.term_id) not in terms for n in metadata.term_notes):
            raise MvpError('metadata_term_binding','Terminology notes must refer to a term in this exact plan revision.')
        for external in metadata.external_searches:
            if not draft and (not external.database.strip() or not external.platform.strip() or not external.query.strip() or external.collection_ref is None):
                raise MvpError('metadata_incomplete','Record the database, platform, exact external query and imported bibliography before saving.')
            if external.collection_ref is None:continue
            _,checksum=collections.store.collection(revision.workspace_id,external.collection_ref.collection_id,db)
            if checksum!=external.collection_ref.collection_snapshot_sha256:
                raise MvpError('stale_collection_inputs','The external-query bibliography snapshot changed; no link was saved.')

    def view(self,mode,handle,plan_id,revision_id=None,version=None):
        plans,_=self._services(mode)
        selected=plans.view(handle,plan_id,revision_id)
        revision=selected.revision
        with plans.store.connection() as db:
            latest=self._latest(db,handle.workspace_id,plan_id,revision.revision_id)
            value=latest
            if version is not None and version!=latest['version']:
                row=db.execute('SELECT payload,sha256,version FROM mvp_search_plan_metadata WHERE workspace_id=? AND plan_id=? AND revision_id=? AND version=?',(handle.workspace_id,plan_id,revision.revision_id,version)).fetchone()
                if row is None:raise MvpError('unknown_search_plan_metadata','This metadata version does not belong to the selected plan revision.')
                value=self._decode(row)
            history=[{'version':row['version'],'saved_at':row['created_at']} for row in db.execute('SELECT version,created_at FROM mvp_search_plan_metadata WHERE workspace_id=? AND plan_id=? AND revision_id=? ORDER BY version DESC',(handle.workspace_id,plan_id,revision.revision_id))]
        bindings=[dict(concept_id=c.id,term_id=t.id,term_sha256=digest(t.model_dump(mode='json')),origin=t.origin,state=t.state,field=t.field,verification='unavailable') for c in revision.draft.concepts for t in c.terms]
        return SearchPlanMetadataView(plan_id=plan_id,revision_id=revision.revision_id,version=value['version'],latest_version=latest['version'],metadata=value['metadata'],term_bindings=bindings,current=revision.revision_id==selected.current_revision_id,history=history,saved_at=value['saved_at'])

    def put(self,mode,handle,plan_id,request):
        plans,collections=self._services(mode)
        def write(workspace):
            def change(db):
                revision=plans._head(db,workspace,plan_id,request.expected_revision_id)
                previous=self._latest(db,workspace,plan_id,revision.revision_id)
                if previous['version']!=request.expected_version:
                    raise MvpError('stale_search_plan_metadata','Another tab saved these design notes. Keep your edits and inspect the latest version.')
                self._validate(revision,request.metadata,collections,db)
                count=db.execute('SELECT COUNT(*) FROM mvp_search_plan_metadata WHERE workspace_id=?',(workspace,)).fetchone()[0]
                if count>=100:raise MvpError('search_plan_storage_limit','Design-note history reached its bounded capacity; existing versions remain readable.')
                value=dict(version=previous['version']+1,metadata=request.metadata.model_dump(mode='json'),saved_at=now())
                payload,checksum=packed(value)
                db.execute('INSERT INTO mvp_search_plan_metadata VALUES(?,?,?,?,?,?,?)',(workspace,plan_id,revision.revision_id,value['version'],payload,checksum,value['saved_at']))
                if search_plan_auxiliary_bytes(db,workspace)>MAX_PLAN_AUXILIARY_BYTES:
                    raise MvpError('search_plan_storage_limit','Planning history reached its bounded capacity; no design notes were replaced.')
                return {'revision_id':revision.revision_id,'version':value['version']}
            return plans.store.mutate(workspace,'metadata:'+plan_id,request.request_id,digest(request.model_dump(mode='json')),change)
        outcome=plans._locked(handle,write)
        return self.view(mode,handle,plan_id,outcome['revision_id'],version=outcome['version'])

    def draft(self,mode,handle,scope,request=None):
        from pydantic import ValidationError
        match=re.fullmatch(r'search-plan-metadata:([^:]{1,200}):([^:]{1,200})',scope)
        if not match:raise MvpError('invalid_draft_scope','Choose an exact saved search plan and revision for design notes.')
        plan_id,revision_id=match.groups();plans,collections=self._services(mode)
        def read(workspace):
            with plans.store.connection() as db:
                revision=plans.store.revision(db,workspace,plan_id,revision_id)
                current=plans.store.revision(db,workspace,plan_id)
                prior=self.registry.draft(workspace,scope)
                raw=request.data if request is not None else prior['data']
                if raw:
                    try:value=SearchPlanMetadataDraft.model_validate(raw)
                    except ValidationError:raise MvpError('invalid_editor_draft','Keep bounded search-design notes and exact owned references.') from None
                    if (value.plan_id,value.revision_id)!=(plan_id,revision_id):raise MvpError('metadata_term_binding','This draft belongs to a different search plan revision.')
                    self._validate(revision,value.metadata,collections,db,draft=True)
                if request is None:return prior
                latest=self._latest(db,workspace,plan_id,revision_id)
                if current.revision_id!=revision_id:raise MvpError('stale_search_plan','This plan revision is historical; keep its notes read-only.')
                if not raw or value.base_metadata_version!=latest['version'] or request.expected_assessment_head!=str(latest['version']):
                    raise MvpError('stale_search_plan_metadata','Design notes changed in another tab. Keep your draft and inspect the latest saved notes.')
                return self.registry.put_draft(workspace,scope,**request.model_dump(mode='json'))
        return plans._locked(handle,read)
