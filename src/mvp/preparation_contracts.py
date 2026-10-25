"""Durable preparation requests and small progress projections.

The job input is private immutable research metadata. HTTP projections never
include retained source text, the workspace capability, or provider credentials.
"""
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .contracts import Model, Paper, PrepareSourcesRequest, StructuredError
from .limits import MAX_PREPARED_SOURCES

MAX_PREPARATION_JOBS = 20
MAX_PREPARATION_ATTEMPTS = 3
MAX_PREPARATION_AUXILIARY_BYTES = 32 * 1024 * 1024
MAX_PREPARATION_INPUT_BYTES = 8 * 1024 * 1024
MAX_PREPARATION_SOURCE_BYTES = 16 * 1024 * 1024
MAX_PREPARATION_RUNTIME_SECONDS = 2400


class PreparationJobRequest(PrepareSourcesRequest):
    paper_ids: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(min_length=1, max_length=MAX_PREPARED_SOURCES)
    expected_source_revision: int = Field(ge=0, strict=True)
    expected_preparation_id: str | None = Field(default=None, min_length=1, max_length=200)


class PreparationInput(Model):
    schema_version: Literal['mvp.preparation-input.v1'] = 'mvp.preparation-input.v1'
    mode: Literal['saved_example', 'live']
    search_id: str
    search_snapshot_sha256: str
    search_provider: str
    paper_ids: list[str] = Field(min_length=1, max_length=MAX_PREPARED_SOURCES)
    papers: list[Paper] = Field(min_length=1, max_length=MAX_PREPARED_SOURCES)
    expected_source_revision: int = Field(ge=0)
    expected_preparation_id: str | None = None
    preparation_profile: Literal['mvp.strict-source-preparation.v1'] = 'mvp.strict-source-preparation.v1'

    @model_validator(mode='after')
    def exact_order(self):
        if self.paper_ids != [paper.id for paper in self.papers] or len(set(self.paper_ids)) != len(self.paper_ids):
            raise ValueError('Preparation input must retain the exact unique ordered papers')
        return self


class PreparationPaperOutcome(Model):
    paper_id: str
    position: int = Field(ge=1)
    outcome: Literal['pending', 'preparing', 'full_text', 'abstract_only', 'unavailable', 'failed', 'cancelled']
    source_id: str | None = None
    source_type: Literal['full_text', 'abstract', 'none'] | None = None
    source_status: str | None = None
    error: StructuredError | None = None


class PreparationJobView(Model):
    schema_version: Literal['mvp.preparation-job.v1'] = 'mvp.preparation-job.v1'
    id: str
    workspace_id: str
    search_id: str
    search_snapshot_sha256: str
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


class PreparationSubmission(Model):
    job: PreparationJobView
    reused: bool = False


class PreparationJobListing(Model):
    jobs: list[PreparationJobView]
