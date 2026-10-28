"""Researcher-controlled follow-up searches; candidates never become evidence."""
from typing import Literal
from pydantic import Field, model_validator
from .contracts import Model, Paper, SearchPreview, new_id, now
from .board_contracts import BoardDefinition, BoardCellRevision, BoardCellDraft, BoardCellData
from .search_plan_contracts import SearchPlanExecution
from .search_plan_service_contracts import SearchPlanView, SearchPlanCapabilities

Decision = Literal['unassessed', 'shortlist', 'dismiss']

class CreateInvestigationRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    board_id: str = Field(min_length=1, max_length=200)
    expected_board_revision_id: str = Field(min_length=1, max_length=200)
    paper_id: str = Field(min_length=1, max_length=200)
    field_id: str = Field(min_length=1, max_length=100)
    expected_cell_head_id: str | None = Field(default=None, max_length=200)
    expected_draft_version: int = Field(ge=0, strict=True)
    local_draft: BoardCellData | None = None
    reason: str = Field(min_length=1, max_length=10000)
    seed_plan_id: str | None = Field(default=None, min_length=1, max_length=200)
    seed_revision_id: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode='after')
    def valid(self):
        if not self.reason.strip():
            raise ValueError('Describe why you are investigating')
        if (self.seed_plan_id is None) != (self.seed_revision_id is None):
            raise ValueError('Use both seed plan and exact revision identities')
        return self

class InvestigationOrigin(Model):
    schema_version: Literal['mvp.investigation-origin.v1'] = 'mvp.investigation-origin.v1'
    id: str = Field(default_factory=new_id)
    workspace_id: str
    request_id: str
    board: BoardDefinition
    paper_id: str
    field_id: str
    cell: BoardCellRevision | None
    draft: BoardCellDraft
    local_draft: BoardCellData | None
    reason: str
    plan_id: str
    seed_plan_id: str | None = None
    seed_revision_id: str | None = None
    seed_approval_ids: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=now)
    meaning: Literal['unresolved_cell_not_proof_of_research_gap'] = 'unresolved_cell_not_proof_of_research_gap'

class InvestigationDecisionRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    candidate_id: str = Field(min_length=1, max_length=200)
    expected_version: int = Field(ge=0, strict=True)
    decision: Decision
    note: str = Field(default='', max_length=10000)

class InvestigationDecision(Model):
    id: str = Field(default_factory=new_id)
    investigation_id: str
    request_id: str
    candidate_id: str
    execution_id: str
    paper_id: str
    version: int
    decision: Decision
    note: str
    created_at: str = Field(default_factory=now)
    meaning: Literal['manual_candidate_organization_not_relevance_eligibility_or_support'] = 'manual_candidate_organization_not_relevance_eligibility_or_support'

class InvestigationCandidate(Model):
    id: str
    paper: Paper
    decision: Decision = 'unassessed'
    decision_version: int = 0

class InvestigationExecution(Model):
    execution: SearchPlanExecution
    search: SearchPreview
    candidates: list[InvestigationCandidate]

class InvestigationOperation(Model):
    request_id: str
    operation: str
    status: Literal['pending', 'failed']
    code: str | None = None
    message: str | None = None
    created_at: str

class InvestigationView(Model):
    schema_version: Literal['mvp.investigation.v1'] = 'mvp.investigation.v1'
    origin: InvestigationOrigin
    plan: SearchPlanView
    capabilities: SearchPlanCapabilities
    executions: list[InvestigationExecution]
    decisions: list[InvestigationDecision]
    failures: list[InvestigationOperation]

class InvestigationListing(Model):
    investigations: list[InvestigationOrigin]

class InvestigationExport(Model):
    schema_version: Literal['mvp.investigation-export.v1'] = 'mvp.investigation-export.v1'
    json_text: str
    markdown_text: str
