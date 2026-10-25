"""Versioned collection-bound preparation; legacy search contracts stay intact."""
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from .collection_contracts import CollectionInputRef, CollectionMember
from .contracts import Model, PreparedSource, StructuredError, digest, new_id, now
from .limits import MAX_PREPARED_SOURCES
from .preparation_contracts import PreparationPaperOutcome


class CollectionPreparationJobRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    collection_ref: CollectionInputRef
    paper_ids: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(min_length=1, max_length=MAX_PREPARED_SOURCES)
    expected_source_revision: int = Field(ge=0, strict=True)
    expected_preparation_id: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator('paper_ids')
    @classmethod
    def unique(cls, values):
        if len(values) != len(set(values)):
            raise ValueError('Select each paper once')
        return values


class CollectionPreparationInput(Model):
    schema_version: Literal['mvp.collection-preparation-input.v2'] = 'mvp.collection-preparation-input.v2'
    mode: Literal['saved_example', 'live']
    collection_ref: CollectionInputRef
    paper_ids: list[str] = Field(min_length=1, max_length=MAX_PREPARED_SOURCES)
    members: list[CollectionMember] = Field(min_length=1, max_length=MAX_PREPARED_SOURCES)
    expected_source_revision: int = Field(ge=0)
    expected_preparation_id: str | None = None
    preparation_profile: Literal['mvp.strict-collection-source-preparation.v2'] = 'mvp.strict-collection-source-preparation.v2'

    @property
    def papers(self):
        return [member.paper for member in self.members]

    @model_validator(mode='after')
    def exact_order(self):
        if self.paper_ids != [member.paper.id for member in self.members] or len(set(self.paper_ids)) != len(self.paper_ids):
            raise ValueError('Collection preparation retains exact unique ordered member snapshots')
        return self


class CollectionPreparationResult(Model):
    schema_version: Literal['mvp.collection-preparation.v2'] = 'mvp.collection-preparation.v2'
    id: str = Field(default_factory=new_id)
    collection_ref: CollectionInputRef
    search_id: None = None
    source_revision: int
    selected_paper_ids: list[str]
    member_snapshots: list[CollectionMember]
    member_snapshot_sha256: str
    selection_state: Literal['selected_for_exploration'] = 'selected_for_exploration'
    sources: list[PreparedSource]
    prepared_at: str = Field(default_factory=now)
    errors: list[StructuredError] = Field(default_factory=list)

    @model_validator(mode='after')
    def exact_members(self):
        if self.selected_paper_ids != [member.paper.id for member in self.member_snapshots] or len(set(self.selected_paper_ids)) != len(self.selected_paper_ids):
            raise ValueError('Collection preparation must retain exact ordered selected metadata snapshots')
        if digest([member.model_dump(mode='json') for member in self.member_snapshots]) != self.member_snapshot_sha256:
            raise ValueError('Collection member snapshot checksum changed')
        return self


class CollectionPreparationJobView(Model):
    schema_version: Literal['mvp.collection-preparation-job.v2'] = 'mvp.collection-preparation-job.v2'
    id: str
    workspace_id: str
    collection_ref: CollectionInputRef
    selected_paper_ids: list[str]
    expected_source_revision: int
    expected_preparation_id: str | None = None
    status: Literal['queued', 'running', 'cancel_requested', 'cancelled', 'succeeded', 'failed', 'stale']
    attempt: int
    max_attempts: int
    progress_completed: int
    progress_total: int
    active_paper_id: str | None = None
    elapsed_seconds: float
    max_runtime_seconds: float
    interrupted_count: int
    result_preparation_id: str | None = None
    result_source_revision: int | None = None
    error: StructuredError | None = None
    outcomes: list[PreparationPaperOutcome]
    created_at: str
    updated_at: str


class CollectionPreparationSubmission(Model):
    job: CollectionPreparationJobView
    reused: bool = False


class CollectionPreparationJobListing(Model):
    jobs: list[CollectionPreparationJobView]
