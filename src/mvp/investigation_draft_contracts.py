"""Incomplete, bounded research inputs; these records never authorize source attachment."""
from typing import Literal
from pydantic import Field, field_validator
from .contracts import Model
from .usability_draft_contracts import Identifier
from .limits import MAX_BOARD_PAPERS

class InvestigationResearchDraft(Model):
    schema_version: Literal['mvp.investigation-research-draft.v1'] = 'mvp.investigation-research-draft.v1'
    investigation_id: Identifier
    candidate_ids: list[Identifier] = Field(default_factory=list, max_length=MAX_BOARD_PAPERS)
    original_paper_ids: list[Identifier] = Field(default_factory=list, max_length=MAX_BOARD_PAPERS)
    collection_name: str = Field(default='Follow-up research selection', max_length=200, strict=True)
    duplicate_policy: Literal['review_required','keep_separate','merge_exact'] = 'review_required'
    handoff_id: Identifier | None = None
    preparation_id: Identifier | None = None
    retrieval_question: str = Field(default='', max_length=10000, strict=True)
    run_id: Identifier | None = None
    inspection_id: Identifier | None = None
    research_question: str = Field(default='', max_length=10000, strict=True)
    interpretation: str = Field(default='', max_length=10000, strict=True)
    note_id: Identifier | None = None
    expected_note_revision_id: Identifier | None = None
    confirm_inspected: bool = Field(default=False, strict=True)
    acknowledge_related_paper: bool = Field(default=False, strict=True)
    board_question: str = Field(default='', max_length=10000, strict=True)
    board_paper_ids: list[Identifier] = Field(default_factory=list, max_length=MAX_BOARD_PAPERS)

    @field_validator('candidate_ids','original_paper_ids','board_paper_ids')
    @classmethod
    def unique(cls,value):
        if len(value)!=len(set(value)):raise ValueError('Select each retained identity once')
        return value

    @field_validator('collection_name','retrieval_question','research_question','interpretation','board_question')
    @classmethod
    def unicode(cls,value):
        value.encode('utf-8')
        return value
