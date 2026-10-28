"""Explicit investigation handoff and properly attributed research-note contracts."""
from typing import Literal
from pydantic import Field, model_validator
from .contracts import Model, Paper, new_id, now
from .board_contracts import BoardReference
from .collection_contracts import CollectionSummary, DuplicateGroup
from .limits import MAX_BOARD_PAPERS

class InvestigationCandidateSelection(Model):
    candidate_id: str = Field(min_length=1, max_length=200)
    expected_decision_version: int = Field(ge=1, strict=True)

class InvestigationHandoffRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    candidates: list[InvestigationCandidateSelection] = Field(min_length=1, max_length=MAX_BOARD_PAPERS)
    original_paper_ids: list[str] = Field(default_factory=list, max_length=MAX_BOARD_PAPERS)
    duplicate_policy: Literal['review_required','keep_separate','merge_exact'] = 'review_required'
    conflict_decisions: dict[str, Literal['keep_separate']] = Field(default_factory=dict)
    preview_sha256: str | None = Field(default=None, min_length=64, max_length=64)

    @model_validator(mode='after')
    def unique(self):
        if not self.name.strip() or len({c.candidate_id for c in self.candidates}) != len(self.candidates) or len(set(self.original_paper_ids)) != len(self.original_paper_ids):
            raise ValueError('Name the collection and select each candidate/original report once')
        return self

class InvestigationHandoffMember(Model):
    selection_id: str
    paper: Paper
    kind: Literal['candidate','original_report']

class InvestigationHandoffPreview(Model):
    schema_version: Literal['mvp.investigation-handoff-preview.v1'] = 'mvp.investigation-handoff-preview.v1'
    input_sha256: str
    members: list[InvestigationHandoffMember]
    duplicate_groups: list[DuplicateGroup]
    max_comparison_papers: int = MAX_BOARD_PAPERS
    original_board_id: str
    original_board_revision_id: str

class InvestigationHandoff(Model):
    schema_version: Literal['mvp.investigation-handoff.v1'] = 'mvp.investigation-handoff.v1'
    id: str = Field(default_factory=new_id)
    investigation_id: str
    request_id: str
    selection_sha256: str
    collection: CollectionSummary
    original_board_id: str
    original_board_revision_id: str
    original_cell_revision_id: str | None
    selected_candidate_ids: list[str]
    selected_original_paper_ids: list[str]
    created_at: str = Field(default_factory=now)
    meaning: Literal['explicit_collection_commit_not_source_preparation_or_scientific_judgment'] = 'explicit_collection_commit_not_source_preparation_or_scientific_judgment'

class InvestigationInspectionRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    handoff_id: str = Field(min_length=1, max_length=200)
    preparation_id: str = Field(min_length=1, max_length=200)
    run_id: str = Field(min_length=1, max_length=200)
    passage_id: str = Field(min_length=1, max_length=200)
    start: int | None = Field(default=None, ge=0, strict=True)
    end: int | None = Field(default=None, ge=1, strict=True)

    @model_validator(mode='after')
    def range(self):
        if (self.start is None) != (self.end is None) or self.start is not None and not self.start < self.end:
            raise ValueError('Use both exact Unicode offsets or the whole returned passage')
        return self

class InvestigationInspection(Model):
    schema_version: Literal['mvp.investigation-inspection.v1'] = 'mvp.investigation-inspection.v1'
    id: str = Field(default_factory=new_id)
    investigation_id: str
    handoff_id: str
    preparation_id: str
    run_id: str
    passage_id: str
    source_paper: Paper
    reference: BoardReference
    source_type: Literal['full_text','abstract']
    source_status: str
    source_manifest_sha256: str
    source_revision: int
    created_at: str = Field(default_factory=now)
    meaning: Literal['verified_displayed_passage_not_human_support'] = 'verified_displayed_passage_not_human_support'

class ResearchEvaluationNoteRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    note_id: str | None = Field(default=None, min_length=1, max_length=200)
    expected_revision_id: str | None = Field(default=None, min_length=1, max_length=200)
    inspection_id: str = Field(min_length=1, max_length=200)
    research_question: str = Field(min_length=1, max_length=10000)
    interpretation: str = Field(min_length=1, max_length=10000)
    confirm_inspected: Literal[True]
    acknowledge_related_paper: Literal[True]

    @model_validator(mode='after')
    def text(self):
        if not self.research_question.strip() or not self.interpretation.strip():
            raise ValueError('Write a research question and your own interpretation')
        if (self.note_id is None) != (self.expected_revision_id is None):
            raise ValueError('Revisions require both the note and expected revision identity')
        return self

class ResearchEvaluationNote(Model):
    schema_version: Literal['mvp.research-evaluation-note.v1'] = 'mvp.research-evaluation-note.v1'
    id: str = Field(default_factory=new_id)
    revision_id: str = Field(default_factory=new_id)
    revision: int
    parent_revision_id: str | None = None
    investigation_id: str
    original_board_id: str
    original_board_revision_id: str
    original_paper_id: str
    original_field_id: str
    original_cell_revision_id: str | None
    research_question: str
    interpretation: str
    inspection: InvestigationInspection
    confirm_inspected: Literal[True] = True
    acknowledge_related_paper: Literal[True] = True
    created_at: str = Field(default_factory=now)
    meaning: Literal['related_paper_evidence_not_original_paper_finding'] = 'related_paper_evidence_not_original_paper_finding'

class InvestigationResearchState(Model):
    schema_version: Literal['mvp.investigation-research.v1'] = 'mvp.investigation-research.v1'
    investigation_id: str
    handoffs: list[InvestigationHandoff]
    inspections: list[InvestigationInspection]
    notes: list[ResearchEvaluationNote]
