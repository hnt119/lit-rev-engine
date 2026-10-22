"""Application views and storage policy for persisted search planning."""
from pydantic import Field

from src.mvp.contracts import Model, SearchPreview, new_id, now
from src.mvp.search_plan_contracts import (
    MAX_AST_DEPTH, MAX_AST_NODES, MAX_CONCEPTS, MAX_TERMS, MAX_VARIANTS, SearchApprovalReceipt,
    SearchPlanDiagnostic, SearchPlanExecution, SearchPlanRevision,
    SearchPlanSummary, SearchPlanningCapability, SearchPlanningResult,
)
from src.mvp.limits import MAX_DISCOVERY_RESULTS

MAX_SEARCH_PLANS = 20
MAX_PLAN_REVISIONS = 40
MAX_PLAN_RECEIPTS = 100
MAX_PLAN_REQUESTS = 500
MAX_PLAN_AUXILIARY_BYTES = 8 * 1024 * 1024
MAX_PLAN_RECORD_BYTES = 512 * 1024


class SearchPlanProposalReceipt(Model):
    id: str = Field(default_factory=new_id)
    plan_id: str
    revision_id: str
    result: SearchPlanningResult
    created_at: str = Field(default_factory=now)


class SearchPlanView(Model):
    revision: SearchPlanRevision
    current_revision_id: str
    revisions: list[SearchPlanSummary]
    approvals: list[SearchApprovalReceipt]
    diagnostics: list[SearchPlanDiagnostic]
    executions: list[SearchPlanExecution]
    proposals: list[SearchPlanProposalReceipt]


class PlannedSearchResult(Model):
    execution: SearchPlanExecution
    search: SearchPreview


class SearchPlanLimits(Model):
    max_concepts: int = MAX_CONCEPTS
    max_terms_per_concept: int = MAX_TERMS
    max_variants: int = MAX_VARIANTS
    max_expression_depth: int = MAX_AST_DEPTH
    max_expression_nodes: int = MAX_AST_NODES
    max_ambiguities: int = 20
    max_query_characters: int = 20000
    max_question_characters: int = 10000
    max_discovery_records: int = MAX_DISCOVERY_RESULTS
    max_plans: int = MAX_SEARCH_PLANS
    max_revisions_per_plan: int = MAX_PLAN_REVISIONS
    max_receipts: int = MAX_PLAN_RECEIPTS
    max_requests: int = MAX_PLAN_REQUESTS
    max_auxiliary_bytes: int = MAX_PLAN_AUXILIARY_BYTES
    max_record_bytes: int = MAX_PLAN_RECORD_BYTES


class SearchPlanCapabilities(Model):
    manual_enabled: bool = True
    execution_enabled: bool
    execution_reason: str
    diagnostics_enabled: bool
    diagnostics_reason: str
    planner: SearchPlanningCapability
    limits: SearchPlanLimits = Field(default_factory=SearchPlanLimits)
