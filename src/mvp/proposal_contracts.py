"""Optional cell proposals: model suggestions never confer inspection or support."""
from typing import Any, Literal
from pydantic import Field, model_validator
from .contracts import Model, new_id, now
from .board_contracts import BoardReference, BoardReferenceInput, BoardCellDraft

MAX_PROPOSAL_PAPERS = 3
MAX_PROPOSAL_CELLS = 9
MAX_PROPOSAL_FIELDS = 6
MAX_PROPOSAL_RUNS = 20
MAX_PACKET_CHARACTERS = 12000
MAX_PACKET_BYTES = 20000
MAX_OUTPUT_BYTES = 32768
MAX_RUN_SECONDS = 35
PROMPT_VERSION = 'mvp.cell-proposals.context-only.v1'

class ProposalCapability(Model):
    enabled: bool = False
    reason: str = 'Generation is disabled. Configure one explicit local generation adapter to enable it.'
    model_profile: dict[str, Any] | None = None
    prompt_version: str = PROMPT_VERSION
    max_papers: int = MAX_PROPOSAL_PAPERS
    max_fields: int = MAX_PROPOSAL_FIELDS
    max_cells: int = MAX_PROPOSAL_CELLS
    max_calls: int = MAX_PROPOSAL_PAPERS
    max_runs_per_workspace: int = MAX_PROPOSAL_RUNS
    max_packet_characters: int = MAX_PACKET_CHARACTERS
    max_packet_bytes: int = MAX_PACKET_BYTES
    max_output_bytes: int = MAX_OUTPUT_BYTES
    max_runtime_seconds: float = MAX_RUN_SECONDS
    retries: int = 0
    paid_calls: bool = False
    settings_revision: int | None = None
    provider: str | None = None

class ProposalGenerateRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    expected_revision_id: str = Field(min_length=1, max_length=200)
    paper_ids: list[str] = Field(min_length=1, max_length=MAX_PROPOSAL_PAPERS)
    field_ids: list[str] = Field(min_length=1, max_length=MAX_PROPOSAL_FIELDS)

    @model_validator(mode='after')
    def bounds(self):
        if len(set(self.paper_ids)) != len(self.paper_ids) or len(set(self.field_ids)) != len(self.field_ids):
            raise ValueError('Select unique papers and fields')
        if len(self.paper_ids) * len(self.field_ids) > MAX_PROPOSAL_CELLS:
            raise ValueError('Select at most nine cells per proposal run')
        return self

class ProposalCellBaseline(Model):
    paper_id: str
    field_id: str
    head_id: str | None
    draft_version: int
    draft_sha256: str

class ProposalEvidence(Model):
    evidence_id: str
    reference: BoardReference
    total_block_characters: int = Field(ge=1)
    omitted_characters: int = Field(ge=0)
    field_ids: list[str]

class ProposalPacketField(Model):
    field_id: str
    field_revision_id: str
    label: str
    subquestion: str
    evidence_ids: list[str]
    candidate_run_id: str
    indexed_blocks: int
    matched_blocks: int
    omitted_matched_blocks: int
    omitted_evidence: int = 0

class ProposalPacket(Model):
    schema_version: Literal['mvp.proposal-packet.v1'] = 'mvp.proposal-packet.v1'
    paper_id: str
    title: str
    question: str
    source_type: Literal['full_text', 'abstract', 'none']
    source_status: str
    context_scope: Literal['retrieved_context_only'] = 'retrieved_context_only'
    fields: list[ProposalPacketField]
    evidence: list[ProposalEvidence]
    evidence_characters: int
    omitted_evidence: int

class ProposalQuoteOutput(Model):
    evidence_id: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=1, max_length=1200)

class ProposalCellOutput(Model):
    field_id: str = Field(min_length=1, max_length=100)
    value: str | None = Field(max_length=4000)
    references: list[ProposalQuoteOutput] = Field(default_factory=list, max_length=5)
    reason: str = Field(min_length=1, max_length=2000)
    missing_information: str = Field(default='', max_length=2000)
    context_scope: Literal['retrieved_context_only'] = 'retrieved_context_only'

    @model_validator(mode='after')
    def evidence(self):
        if not self.reason.strip():
            raise ValueError('Explain the suggestion within retrieved context')
        if self.value is not None and (not self.value.strip() or not self.references):
            raise ValueError('A nonnull suggestion needs nonblank value and exact evidence')
        if self.value is None and not self.missing_information.strip():
            raise ValueError('A null suggestion needs missing information')
        return self

class ProposalModelOutput(Model):
    cells: list[ProposalCellOutput] = Field(min_length=1, max_length=MAX_PROPOSAL_FIELDS)

class ProposalUsage(Model):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    measured: bool = False

class ProposalGenerationResult(Model):
    """Adapter output remains untrusted text until strict domain validation."""
    output_text: str
    usage: ProposalUsage = Field(default_factory=ProposalUsage)

class ProposalEvent(Model):
    id: str = Field(default_factory=new_id)
    proposal_id: str
    action: Literal['adopted', 'dismissed']
    request_id: str
    reason: str = ''
    draft_version: int | None = None
    edited_value_sha256: str | None = None
    created_at: str = Field(default_factory=now)

class CellProposal(Model):
    schema_version: Literal['mvp.cell-proposal.v1'] = 'mvp.cell-proposal.v1'
    id: str = Field(default_factory=new_id)
    run_id: str
    board_id: str
    board_revision_id: str
    field_id: str
    field_revision_id: str
    paper_id: str
    source_manifest_sha256: str
    source_bindings: list[dict[str, Any]]
    retrieval_input_sha256: str
    candidate_run_ids: list[str]
    packet_sha256: str
    prompt_version: str
    model_profile: dict[str, Any]
    model_profile_sha256: str
    value: str | None
    references: list[BoardReference]
    reason: str
    missing_information: str
    context_scope: Literal['retrieved_context_only'] = 'retrieved_context_only'
    semantic_assessment: Literal['unassessed'] = 'unassessed'
    review_state: Literal['ai_suggestion_needs_review_not_independently_verified'] = 'ai_suggestion_needs_review_not_independently_verified'
    producer: Literal['ai_proposal'] = 'ai_proposal'
    status: Literal['pending', 'adopted', 'dismissed'] = 'pending'
    latest_event: ProposalEvent | None = None
    created_at: str = Field(default_factory=now)

class ProposalCallReceipt(Model):
    paper_id: str
    packet_sha256: str
    request_sha256: str
    output_sha256: str | None = None
    output_bytes: int | None = None
    usage: ProposalUsage = Field(default_factory=ProposalUsage)
    elapsed_seconds: float = Field(default=0, ge=0)
    outcome: Literal['not_started', 'running', 'succeeded', 'invalid_output', 'provider_failure', 'timeout'] = 'not_started'

class ProposalRun(Model):
    schema_version: Literal['mvp.proposal-run.v1'] = 'mvp.proposal-run.v1'
    id: str = Field(default_factory=new_id)
    board_id: str
    board_revision_id: str
    request_id: str
    request_sha256: str
    paper_ids: list[str]
    field_ids: list[str]
    source_manifest_sha256: str
    retrieval_profile_sha256: str
    prompt_version: str
    model_profile: dict[str, Any]
    model_profile_sha256: str
    baselines: list[ProposalCellBaseline]
    state: Literal['running', 'succeeded', 'failed'] = 'running'
    failure_code: str | None = None
    failure_message: str | None = None
    packets: list[ProposalPacket] = Field(default_factory=list)
    calls: list[ProposalCallReceipt] = Field(default_factory=list)
    proposals: list[CellProposal] = Field(default_factory=list)
    created_at: str = Field(default_factory=now)
    completed_at: str | None = None

class ProposalRunSummary(Model):
    id: str
    board_id: str
    board_revision_id: str
    paper_ids: list[str]
    field_ids: list[str]
    state: Literal['running', 'succeeded', 'failed']
    failure_code: str | None = None
    failure_message: str | None = None
    calls: list[ProposalCallReceipt]
    proposal_count: int
    created_at: str
    completed_at: str | None = None
    recovery_note: str | None = None

class ProposalListing(Model):
    items: list[CellProposal]
    offset: int
    limit: int
    total: int
    runs: list[ProposalRunSummary] = Field(default_factory=list)
    capability: ProposalCapability

class ProposalDismissRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    expected_revision_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(default='', max_length=2000)

class ProposalAdoptRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    expected_revision_id: str = Field(min_length=1, max_length=200)
    draft_version: int = Field(ge=0, strict=True)
    expected_cell_head_id: str | None = Field(default=None, max_length=200)
    value: str | None = Field(max_length=10000)
    reason: str = Field(min_length=1, max_length=10000)
    missing_information: str = Field(default='', max_length=10000)

    @model_validator(mode='after')
    def content(self):
        if not self.reason.strip() or self.value is not None and not self.value.strip():
            raise ValueError('Use a nonblank value or explicit null and give a reason')
        if self.value is None and not self.missing_information.strip():
            raise ValueError('Explain missing information for a null draft')
        return self

class ProposalAudit(Model):
    schema_version: Literal['mvp.proposal-audit.v1'] = 'mvp.proposal-audit.v1'
    board_id: str
    board_revision_id: str
    runs: list[ProposalRun]
    events: list[ProposalEvent]
    review_state: Literal['ai_suggestions_not_human_validation'] = 'ai_suggestions_not_human_validation'
