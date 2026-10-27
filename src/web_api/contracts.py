"""Small, versioned browser projections. Credentials never belong here."""
from typing import Any, Literal
from pydantic import Field
from src.mvp.board_contracts import BoardLimits, BoardPaper
from src.mvp.span_board_contracts import BoardSpanCapability
from src.mvp.collection_contracts import CollectionInputRef, PaperInputRef
from src.mvp.workspace_versions import CollectionEvidenceRun
from src.mvp.limits import public_limits
from src.mvp.contracts import (
    Model, Assessment, Block, BoardPassageScope, EvidenceRun, Paper, Passage, StructuredError,
)

class SessionInfo(Model):
    csrf_token: str
    expires_at: str

class CreateWebWorkspace(Model):
    request_id: str = Field(min_length=1, max_length=200)
    question: str = Field(default="", max_length=10000)
    mode: Literal["saved_example", "live"] = "saved_example"

class SearchSummary(Model):
    id: str
    query: str
    research_question: str | None = None
    searched_at: str
    mode: str
    provider: str
    total_reported: int
    fetched_count: int
    distinct_count: int
    truncated: bool
    warnings: list[str]

class PreparationSummary(Model):
    id: str
    search_id: str
    source_revision: int
    selected_paper_ids: list[str]
    prepared_at: str

class CollectionPreparationSummary(PreparationSummary):
    search_id: None = None
    collection_ref: CollectionInputRef

class RunSummary(Model):
    id: str
    search_id: str
    preparation_id: str
    source_revision: int
    question: str
    created_at: str
    passage_count: int
    current: bool
    board_context: BoardPassageScope | None = None

class CollectionRunSummary(RunSummary):
    search_id: None = None
    collection_ref: CollectionInputRef

class AssessmentSummary(Model):
    id: str
    run_id: str
    supersedes_id: str | None
    status: str
    created_at: str

class WorkspaceSummary(Model):
    id: str
    question: str
    mode: Literal["saved_example", "live"]
    created_at: str
    source_revision: int
    current_preparation_id: str | None
    selected_paper_ids: list[str]
    current_run_id: str | None
    current_assessment_ids: dict[str, str]
    searches: list[SearchSummary]
    preparations: list[PreparationSummary | CollectionPreparationSummary]
    runs: list[RunSummary | CollectionRunSummary]
    assessments: list[AssessmentSummary]

class WorkspaceList(Model):
    workspaces: list[WorkspaceSummary]

class SourceMetadata(Model):
    id: str
    paper_id: str
    status: str
    source_type: str
    provider: str
    source_url: str
    retrieved_at: str
    license: str | None
    attribution: str | None
    version: str
    source_sha256: str
    blocks_sha256: str
    parser_id: str
    parser_metadata: dict[str, Any]
    source_identifiers: dict[str, str]
    block_count: int
    warnings: list[str]
    error: StructuredError | None

class PreparationView(PreparationSummary):
    selection_state: Literal["selected_for_exploration"]
    sources: list[SourceMetadata]
    errors: list[StructuredError]

class CollectionPreparationView(CollectionPreparationSummary):
    selection_state: Literal["selected_for_exploration"]
    sources: list[SourceMetadata]
    errors: list[StructuredError]

class PreparationPapers(Model):
    preparation_id: str
    origin: PaperInputRef
    papers: list[BoardPaper]

class RunPapers(Model):
    run_id: str
    origin: PaperInputRef
    papers: list[BoardPaper]

class RunView(Model):
    run: EvidenceRun | CollectionEvidenceRun
    current: bool
    assessment_head: Assessment | None
    assessment_history: list[Assessment]
    assessment_total: int
    next_assessment_offset: int | None

class ContextView(Model):
    run_id: str
    passage: Passage
    paper: Paper
    source: SourceMetadata
    block: Block
    blocks: list[Block]
    offset: int
    total_blocks: int
    next_offset: int | None
    archived: bool
    current: bool
    offset_convention: Literal["half-open-unicode-codepoints"] = "half-open-unicode-codepoints"

class DraftUpdate(Model):
    version: int = Field(ge=0, strict=True)
    data: dict[str, Any]
    expected_assessment_head: str | None = None

class DraftRecord(Model):
    scope: str
    version: int
    data: dict[str, Any]
    expected_assessment_head: str | None = None
    updated_at: str | None = None

class MapCapability(Model):
    ready: bool = False
    reason: str = "Setup required: optional pinned local embedding profile is not configured."

class Capabilities(Model):
    desktop_onboarding_ready: bool = False
    default_mode: Literal["saved_example"] = "saved_example"
    live_available: bool
    saved_example: dict[str, Any]
    limits: dict[str, int] = Field(default_factory=public_limits)
    preparation_jobs_ready: bool = False
    search_plans_ready: bool = False
    board_span_profiles: BoardSpanCapability | None = None
    map: MapCapability = Field(default_factory=MapCapability)
    boards: BoardLimits = Field(default_factory=BoardLimits)
