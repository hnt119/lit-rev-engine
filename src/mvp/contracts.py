"""Versioned JSON contracts for the reusable, UI-independent MVP.

Quotation offsets are half-open Python/Unicode code-point offsets into the
canonical block text, never PDF page coordinates or JavaScript UTF-16 offsets.
"""

from datetime import date, datetime, timezone
from hashlib import sha256
import json
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.review.identity import normalize_doi, normalize_pmid


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid4())


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return sha256(canonical(value).encode("utf-8")).hexdigest()


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class StructuredError(Model):
    code: str
    message: str
    retryable: bool = False
    paper_id: str | None = None


class WorkspaceHandle(Model):
    workspace_id: str
    token: str = Field(repr=False)


class CreateWorkspaceRequest(Model):
    question: str = Field(default="", max_length=10000)


class QuerySuggestionRequest(Model):
    question: str = Field(min_length=1, max_length=10000)


class QuerySuggestion(Model):
    query: str
    explanation: str
    method: Literal["transparent-template-v1"] = "transparent-template-v1"


class SearchRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=1, max_length=20000)
    research_question: str | None = Field(default=None, min_length=1, max_length=10000)
    max_results: int = Field(default=30, ge=1, le=50, strict=True)
    sort: Literal["relevance", "pub_date"] = "relevance"
    date_from: str | None = None
    date_to: str | None = None

    @field_validator("date_from", "date_to")
    @classmethod
    def valid_date(cls, value):
        if value is not None:
            date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def valid_range(self):
        if not self.query.strip():
            raise ValueError("Query must contain text")
        if self.research_question is not None and not self.research_question.strip():
            raise ValueError("Research question must contain text")
        if (self.date_from is None) != (self.date_to is None):
            raise ValueError("PubMed publication-date restrictions require both start and end dates")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("Start date must be on or before end date")
        return self


class Paper(Model):
    id: str = ""
    title: str = Field(min_length=1)
    authors: list[str] = Field(default_factory=list)
    year: int | None = Field(default=None, ge=1, le=9999)
    pmid: str | None = None
    doi: str | None = None
    pmcid: str | None = None
    abstract: str = ""
    url: str = ""

    @model_validator(mode="after")
    def identity(self):
        pmid, doi = normalize_pmid(self.pmid), normalize_doi(self.doi)
        object.__setattr__(self, "pmid", pmid)
        object.__setattr__(self, "doi", doi)
        if not self.id:
            identity = "pmid:" + pmid if pmid else "doi:" + doi if doi else "unidentified:" + new_id()
            object.__setattr__(self, "id", identity)
        return self


class SearchPreview(Model):
    schema_version: Literal["mvp.exploratory-preview.v1"] = "mvp.exploratory-preview.v1"
    id: str = Field(default_factory=new_id)
    query: str
    research_question: str | None = None
    query_translation: str | None = None
    searched_at: str = Field(default_factory=now)
    sort: str = "relevance"
    date_from: str | None = None
    date_to: str | None = None
    total_reported: int = Field(ge=0)
    fetched_count: int = Field(ge=0)
    ordered_identifiers: list[str] = Field(default_factory=list)
    papers: list[Paper] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    truncated: bool
    provider: str = "pubmed"
    mode: Literal["live", "saved_example", "test"] = "live"
    errors: list[StructuredError] = Field(default_factory=list)


class Block(Model):
    id: str
    ordinal: int = Field(ge=1)
    text: str
    locator: dict[str, Any]


class PreparedSource(Model):
    id: str = Field(default_factory=new_id)
    paper_id: str
    status: Literal["full_text_retrieved", "abstract_only", "no_usable_text", "fetch_failed", "identity_mismatch", "permission_unresolved"]
    source_type: Literal["full_text", "abstract", "none"]
    provider: str
    source_url: str
    retrieved_at: str = Field(default_factory=now)
    license: str | None = None
    attribution: str | None = None
    version: str = "1"
    source_sha256: str = ""
    blocks_sha256: str = ""
    parser_id: str = ""
    parser_metadata: dict[str, Any] = Field(default_factory=dict)
    source_identifiers: dict[str, str] = Field(default_factory=dict)
    blocks: list[Block] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: StructuredError | None = None
    retained_content_utf8: str | None = None


class PrepareSourcesRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    search_id: str
    paper_ids: list[str] = Field(min_length=1, max_length=10)

    @field_validator("paper_ids")
    @classmethod
    def unique(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Select each paper only once")
        return value


class PreparationResult(Model):
    id: str = Field(default_factory=new_id)
    search_id: str
    source_revision: int
    selected_paper_ids: list[str]
    selection_state: Literal["selected_for_exploration"] = "selected_for_exploration"
    sources: list[PreparedSource]
    prepared_at: str = Field(default_factory=now)
    errors: list[StructuredError] = Field(default_factory=list)


class RetrieveEvidenceRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=10000)
    top_k: int = Field(default=5, ge=1, le=5, strict=True)

    @field_validator("question")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Question must contain text")
        return value


class Anchor(Model):
    block_id: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    quote: str

    @model_validator(mode="after")
    def exact_length(self):
        if self.end <= self.start or len(self.quote) != self.end - self.start:
            raise ValueError("Anchor must span its exact nonempty Unicode code-point quotation")
        return self


class Passage(Model):
    id: str
    rank: int
    paper_id: str
    source_id: str
    source_version: str
    source_sha256: str
    blocks_sha256: str
    source_type: Literal["full_text", "abstract"]
    anchor: Anchor
    locator: dict[str, Any]
    surrounding_text: str
    score: float


class EvidenceRun(Model):
    schema_version: Literal["mvp.lexical-evidence.v1"] = "mvp.lexical-evidence.v1"
    id: str = Field(default_factory=new_id)
    search_id: str
    preparation_id: str
    source_revision: int
    source_snapshot_sha256: str
    question: str
    method: Literal["bm25_context_blocks"] = "bm25_context_blocks"
    method_version: str = "lit-rev-engine.project-retrieval.v3.bm25_context_blocks"
    parameters: dict[str, Any] = Field(default_factory=dict)
    passages: list[Passage]
    indexed_passages: int
    matched_passages: int
    created_at: str = Field(default_factory=now)


class SourceContextRequest(Model):
    run_id: str
    passage_id: str


class SourceContext(Model):
    run_id: str
    passage: Passage
    paper: Paper
    source: PreparedSource
    block: Block
    offset_convention: Literal["half-open-unicode-codepoints"] = "half-open-unicode-codepoints"


class PassageJudgment(Model):
    passage_id: str
    decision: Literal["unreviewed", "useful", "not_useful", "uncertain"] = "unreviewed"
    notes: str = Field(default="", max_length=20000)


class BundleJudgment(Model):
    status: Literal["not_assessed", "sufficient", "partial", "insufficient", "uncertain"] = "not_assessed"
    reason: str = Field(default="", max_length=20000)
    supporting_passage_ids: list[str] = Field(default_factory=list)
    missing_information: str = Field(default="", max_length=20000)
    contradiction: bool = False

    @model_validator(mode="after")
    def reason_and_support(self):
        if self.status != "not_assessed" and not self.reason.strip():
            raise ValueError("Assessed bundles require a reason")
        if self.status in {"partial", "insufficient"} and not self.missing_information.strip():
            raise ValueError("Partial or insufficient bundles require missing information")
        if self.status == "sufficient" and not self.supporting_passage_ids:
            raise ValueError("Sufficient bundles require supporting passages")
        if self.status == "sufficient" and self.missing_information.strip():
            raise ValueError("A sufficient bundle cannot also declare missing information")
        return self


class SaveAssessmentRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    run_id: str
    supersedes_id: str | None = None
    passages: list[PassageJudgment] = Field(default_factory=list)
    bundle: BundleJudgment = Field(default_factory=BundleJudgment)
    feedback: str = Field(default="", max_length=20000)


class Assessment(Model):
    schema_version: Literal["mvp.assessment.v1"] = "mvp.assessment.v1"
    id: str = Field(default_factory=new_id)
    run_id: str
    source_revision: int
    source_snapshot_sha256: str
    supersedes_id: str | None
    passages: list[PassageJudgment]
    bundle: BundleJudgment
    feedback: str = ""
    review_state: Literal["single_human_self_declared_not_independently_verified"] = "single_human_self_declared_not_independently_verified"
    created_at: str = Field(default_factory=now)


class WorkspaceSnapshot(Model):
    schema_version: Literal["mvp.workspace.v1"] = "mvp.workspace.v1"
    id: str
    question: str
    created_at: str = Field(default_factory=now)
    source_revision: int = 0
    selected_paper_ids: list[str] = Field(default_factory=list)
    sources: list[PreparedSource] = Field(default_factory=list)
    searches: list[SearchPreview] = Field(default_factory=list)
    preparations: list[PreparationResult] = Field(default_factory=list)
    runs: list[EvidenceRun] = Field(default_factory=list)
    assessments: list[Assessment] = Field(default_factory=list)
    current_run_id: str | None = None
    current_assessment_ids: dict[str, str] = Field(default_factory=dict)


class WorkspaceExport(Model):
    schema_version: Literal["mvp.export.v1"] = "mvp.export.v1"
    csv_text: str
    json_text: str


class ClearResult(Model):
    cleared: bool = True
