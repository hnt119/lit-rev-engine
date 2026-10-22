"""Editable search intent, deterministic candidates and explicit I/O receipts."""
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .contracts import Model, StructuredError, new_id, now
from .limits import DEFAULT_DISCOVERY_RESULTS, MAX_DISCOVERY_RESULTS
from .import_contracts import normalize_citation_doi
from src.review.identity import normalize_pmid

COMPILER_VERSION = 'mvp.pubmed-intent-compiler.v2'
PLANNER_PROMPT_VERSION = 'mvp.search-intent-proposal.v1'
MAX_CONCEPTS = 12
MAX_TERMS = 8
MAX_VARIANTS = 3
MAX_AST_NODES = 64
MAX_AST_DEPTH = 8
MAX_PLANNER_BYTES = 24 * 1024
MAX_PLANNER_SECONDS = 10


class QuestionSpan(Model):
    start: int = Field(ge=0, strict=True)
    end: int = Field(ge=1, strict=True)
    text: str = Field(max_length=10000)

    @model_validator(mode='after')
    def nonempty(self):
        if self.end <= self.start:
            raise ValueError('Use a nonempty Unicode-codepoint source span')
        return self


class SearchTerm(Model):
    id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=1000)
    field: Literal['text', 'title_abstract', 'mesh'] = 'text'
    origin: Literal['verbatim', 'manual', 'model_proposed', 'terminology'] = 'manual'
    state: Literal['proposed', 'approved'] = 'proposed'
    source_span: QuestionSpan | None = None
    provenance_note: str = Field(default='', max_length=2000)


class SearchConcept(Model):
    id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=200)
    role: Literal['topic', 'population', 'geography', 'exposure', 'outcome', 'comparator', 'study_design', 'other', 'unresolved']
    source_span: QuestionSpan | None = None
    requirement: Literal['required', 'preferred', 'excluded', 'unresolved']
    retrieval_use: Literal['query', 'rank_only', 'screen_later', 'unresolved']
    terms: list[SearchTerm] = Field(default_factory=list, max_length=MAX_TERMS)
    promoted_to_query: bool = False
    promotion_reason: str = Field(default='', max_length=2000)


class PlanExpression(Model):
    op: Literal['all_of', 'any_of', 'not', 'concept_ref']
    concept_id: str | None = Field(default=None, max_length=100)
    children: list['PlanExpression'] = Field(default_factory=list, max_length=MAX_CONCEPTS)

    @model_validator(mode='after')
    def shape(self):
        if self.op == 'concept_ref':
            valid = bool(self.concept_id) and not self.children
        elif self.op == 'not':
            valid = self.concept_id is None and len(self.children) == 1 and self.children[0].op == 'concept_ref'
        else:
            valid = self.concept_id is None and 2 <= len(self.children) <= MAX_CONCEPTS
        if not valid:
            raise ValueError('Use explicit Boolean groups; NOT must wrap one concept reference')
        return self


class SearchVariant(Model):
    id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=200)
    kind: Literal['focused', 'broad', 'subquestion']
    expression: PlanExpression
    deferred_concept_ids: list[str] = Field(default_factory=list, max_length=MAX_CONCEPTS)
    deferral_reason: str = Field(default='', max_length=2000)
    split_explanation: str = Field(default='', max_length=2000)


class PlanAmbiguity(Model):
    id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)
    concept_ids: list[str] = Field(default_factory=list, max_length=MAX_CONCEPTS)
    resolved: bool = False
    resolution: str = Field(default='', max_length=2000)


class SearchDateFilter(Model):
    date_from: str
    date_to: str

    @model_validator(mode='after')
    def dates(self):
        from datetime import date
        date.fromisoformat(self.date_from)
        date.fromisoformat(self.date_to)
        if self.date_from > self.date_to:
            raise ValueError('Publication date start must precede its end')
        return self


class SearchPlanDraft(Model):
    original_question: str = Field(max_length=10000)
    input_mode: Literal['natural_question', 'manual_strategy'] = 'natural_question'
    manual_strategy: str | None = Field(default=None, max_length=20000)
    concepts: list[SearchConcept] = Field(default_factory=list, max_length=MAX_CONCEPTS)
    variants: list[SearchVariant] = Field(default_factory=list, max_length=MAX_VARIANTS)
    ambiguities: list[PlanAmbiguity] = Field(default_factory=list, max_length=20)
    date_filter: SearchDateFilter | None = None
    sort: Literal['relevance', 'pub_date'] = 'relevance'

    @field_validator('original_question', 'manual_strategy')
    @classmethod
    def valid_unicode(cls, value):
        if value is not None:
            value.encode('utf-8')
        return value


class PlanValidationIssue(Model):
    code: str
    message: str
    severity: Literal['error', 'warning'] = 'error'
    concept_id: str | None = None
    variant_id: str | None = None


class CompiledSearchCandidate(Model):
    id: str
    label: str
    kind: Literal['focused', 'broad', 'subquestion', 'manual_strategy']
    query: str
    date_from: str | None = None
    date_to: str | None = None
    sort: Literal['relevance', 'pub_date'] = 'relevance'
    plan_sha256: str
    candidate_sha256: str
    included_concept_ids: list[str]
    deferred_required_ids: list[str]
    deferred_excluded_ids: list[str]
    deferred_constraints: list[str]
    unparsed_constraints: list[str]
    requires_split_approval: bool
    differences: list[str]
    issues: list[PlanValidationIssue]
    status: Literal['blocked', 'ready_for_approval']


class CompiledSearchPlan(Model):
    schema_version: Literal['mvp.compiled-search-plan.v2'] = 'mvp.compiled-search-plan.v2'
    compiler_version: str = COMPILER_VERSION
    terminology_status: Literal['no_server_mesh_registry'] = 'no_server_mesh_registry'
    plan_sha256: str
    candidates: list[CompiledSearchCandidate]
    issues: list[PlanValidationIssue]


class SearchPlanRevision(Model):
    schema_version: Literal['mvp.search-plan-revision.v2'] = 'mvp.search-plan-revision.v2'
    plan_id: str = Field(default_factory=new_id)
    revision_id: str = Field(default_factory=new_id)
    workspace_id: str
    revision: int = Field(ge=1, strict=True)
    parent_revision_id: str | None = None
    draft: SearchPlanDraft
    compiled: CompiledSearchPlan
    created_at: str = Field(default_factory=now)


class SearchPlanSummary(Model):
    plan_id: str
    revision_id: str
    revision: int
    original_question: str
    input_mode: Literal['natural_question', 'manual_strategy']
    candidate_count: int
    ready_count: int
    created_at: str


class SearchPlanListing(Model):
    plans: list[SearchPlanSummary]


class CreateSearchPlanRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    draft: SearchPlanDraft


class UpdateSearchPlanRequest(CreateSearchPlanRequest):
    expected_revision_id: str = Field(min_length=1, max_length=200)


class SearchCandidateRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    expected_revision_id: str = Field(min_length=1, max_length=200)
    candidate_id: str = Field(min_length=1, max_length=100)
    candidate_sha256: str = Field(min_length=64, max_length=64)


class ApproveSearchPlanRequest(SearchCandidateRequest):
    acknowledged_deferred_concept_ids: list[str] = Field(default_factory=list, max_length=MAX_CONCEPTS)
    accept_subquestion_split: bool = False
    acknowledge_unparsed_strategy: bool = False


class SearchApprovalReceipt(Model):
    schema_version: Literal['mvp.search-plan-approval.v2'] = 'mvp.search-plan-approval.v2'
    id: str = Field(default_factory=new_id)
    plan_id: str
    revision_id: str
    candidate_id: str
    candidate_sha256: str
    acknowledged_deferred_concept_ids: list[str]
    accept_subquestion_split: bool
    acknowledge_unparsed_strategy: bool
    created_at: str = Field(default_factory=now)
    meaning: Literal['researcher_intent_approval_not_mesh_validation'] = 'researcher_intent_approval_not_mesh_validation'


class DiagnosticSeed(Model):
    id: str = Field(min_length=1, max_length=100)
    pmid: str | None = None
    doi: str | None = None
    purpose: Literal['construction', 'held_out']
    approved: Literal[True]

    @field_validator('doi')
    @classmethod
    def doi_value(cls, value):
        return normalize_citation_doi(value)

    @field_validator('pmid')
    @classmethod
    def pmid_value(cls, value):
        return normalize_pmid(value)

    @model_validator(mode='after')
    def identity(self):
        if not (self.pmid or self.doi):
            raise ValueError('Seeds require an explicit PMID or DOI')
        return self


class DiagnoseSearchPlanRequest(SearchCandidateRequest):
    seeds: list[DiagnosticSeed] = Field(default_factory=list, max_length=3)
    preview_search_id: str | None = Field(default=None, max_length=200)

    @model_validator(mode='after')
    def unique_seed_identities(self):
        seen_ids, seen_identities = set(), set()
        for seed in self.seeds:
            identities = {('pmid', seed.pmid)} if seed.pmid else set()
            if seed.doi:
                identities.add(('doi', seed.doi))
            if seed.id in seen_ids or seen_identities.intersection(identities):
                raise ValueError('The same known seed identity cannot be counted twice or labeled both construction and held-out')
            seen_ids.add(seed.id)
            seen_identities.update(identities)
        return self


class ExecuteSearchPlanRequest(SearchCandidateRequest):
    approval_id: str = Field(min_length=1, max_length=200)
    max_results: int = Field(default=DEFAULT_DISCOVERY_RESULTS, ge=1, le=MAX_DISCOVERY_RESULTS, strict=True)


class ProposeSearchPlanRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    original_question: str = Field(min_length=1, max_length=10000)
    expected_revision_id: str | None = Field(default=None, max_length=200)


class QueryDiagnosticMessage(Model):
    code: str
    message: str
    severity: Literal['error', 'warning']


class DiagnosticSeedResult(Model):
    seed: DiagnosticSeed
    query_membership: Literal['matched', 'not_matched', 'unresolved', 'not_checked']
    preview_recovery: Literal['present', 'absent', 'not_checked']
    reason: str


class QueryDiagnosticReceipt(Model):
    schema_version: Literal['mvp.query-diagnostic.v2'] = 'mvp.query-diagnostic.v2'
    id: str = Field(default_factory=new_id)
    query: str
    query_sha256: str
    date_from: str | None = None
    date_to: str | None = None
    sort: Literal['relevance', 'pub_date'] = 'relevance'
    status: Literal['succeeded', 'provider_error', 'failed', 'not_run']
    provider: Literal['pubmed_esearch'] = 'pubmed_esearch'
    reported_count: int | None = None
    sample_pmids: list[str] = Field(default_factory=list, max_length=5)
    sample_limit: int = Field(default=5, ge=1, le=5)
    truncated_sample: bool | None = None
    query_translation: str | None = None
    messages: list[QueryDiagnosticMessage] = Field(default_factory=list)
    response_sha256: str | None = None
    membership_response_sha256: str | None = None
    seed_results: list[DiagnosticSeedResult] = Field(default_factory=list, max_length=3)
    calls: int = 0
    retrieved_at: str = Field(default_factory=now)
    error: StructuredError | None = None
    meaning: Literal['diagnostic_not_capture_relevance_or_recall'] = 'diagnostic_not_capture_relevance_or_recall'


class SearchPlanDiagnostic(Model):
    plan_id: str
    revision_id: str
    candidate_id: str
    candidate_sha256: str
    receipt: QueryDiagnosticReceipt
    preview_search_id: str | None = None
    preview_search_snapshot_sha256: str | None = None

    @model_validator(mode='after')
    def preview_binding(self):
        if (self.preview_search_id is None) != (self.preview_search_snapshot_sha256 is None):
            raise ValueError('Retained preview recovery requires both an artifact ID and snapshot digest')
        return self


class SearchPlanExecution(Model):
    schema_version: Literal['mvp.planned-search-execution.v2'] = 'mvp.planned-search-execution.v2'
    id: str = Field(default_factory=new_id)
    plan_id: str
    revision_id: str
    candidate_id: str
    candidate_sha256: str
    approval_id: str
    search_id: str
    search_snapshot_sha256: str
    created_at: str = Field(default_factory=now)


class SearchPlanningUsage(Model):
    input_tokens: int | None = Field(default=None, ge=0, le=1000000)
    output_tokens: int | None = Field(default=None, ge=0, le=1000000)
    total_tokens: int | None = Field(default=None, ge=0, le=1000000)
    measured: bool = False
    cost_usd: None = None


class SearchPlanningResult(Model):
    schema_version: Literal['mvp.search-plan-proposal.v1'] = 'mvp.search-plan-proposal.v1'
    draft: SearchPlanDraft
    question_sha256: str
    model_profile: dict
    prompt_version: str = PLANNER_PROMPT_VERSION
    response_sha256: str
    elapsed_seconds: float
    usage: SearchPlanningUsage = Field(default_factory=SearchPlanningUsage)
    meaning: Literal['model_proposal_needs_researcher_review'] = 'model_proposal_needs_researcher_review'


class SearchPlanningCapability(Model):
    enabled: bool = False
    reason: str = 'Optional local search planning is disabled. Manual intent editing and deterministic compilation remain available.'
    model_profile: dict | None = None
    max_calls: Literal[1] = 1
    max_runtime_seconds: Literal[10] = 10
    max_input_bytes: Literal[24576] = 24576
    max_output_bytes: Literal[24576] = 24576
    retries: Literal[0] = 0
    paid_calls: Literal[False] = False
