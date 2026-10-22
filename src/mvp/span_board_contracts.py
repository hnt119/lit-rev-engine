"""Explicit profile requests and additive span receipts; legacy DTOs stay intact."""
from typing import Annotated, Literal
import math

from pydantic import Field, model_validator

from .board_contracts import BoardCandidate, BoardCandidates, BoardCreateRequest
from .contracts import Model
from .span_budget import budget_token_count
from .span_retrieval_contracts import (
    SpanRequirement, MAX_SPAN_REQUIREMENTS, MAX_SPAN_CHARACTERS, MAX_SPAN_BUDGET_TOKENS,
    MAX_SPAN_SELECTIONS, MAX_DELIVERED_CHARACTERS, MAX_DELIVERED_BUDGET_TOKENS,
    MAX_INDEXED_BLOCKS, MAX_INDEXED_WINDOWS, MAX_INDEXED_CHARACTERS, MAX_SEARCH_SECONDS,
    BUDGET_TOKENIZER_ID,
)


LEGACY_BOARD_PROFILE = 'legacy_block_prefix_v1'
SPAN_BOARD_PROFILE = 'lexical_spans_v1'
BoardProfileId = Literal['legacy_block_prefix_v1', 'lexical_spans_v1']


class FieldSpanRequirements(Model):
    field_id: str = Field(min_length=1, max_length=100)
    requirements: list[SpanRequirement] = Field(min_length=1, max_length=MAX_SPAN_REQUIREMENTS)

    @model_validator(mode='after')
    def unique(self):
        if len({value.id for value in self.requirements}) != len(self.requirements):
            raise ValueError('Use unique explicit component identifiers within each field.')
        return self


class ProfiledBoardCreateRequest(BoardCreateRequest):
    schema_version: Literal['mvp.board-profile-request.v2'] = 'mvp.board-profile-request.v2'
    retrieval_profile_id: BoardProfileId
    field_requirements: list[FieldSpanRequirements] = Field(default_factory=list, max_length=6)

    @model_validator(mode='after')
    def component_ownership(self):
        fields = {value.id for value in self.fields}
        selected = [value.field_id for value in self.field_requirements]
        if len(set(selected)) != len(selected) or not set(selected) <= fields:
            raise ValueError('Explicit components must belong to unique fields in this exact board request.')
        if self.retrieval_profile_id == LEGACY_BOARD_PROFILE and self.field_requirements:
            raise ValueError('Legacy retrieval cannot silently ignore explicit span components.')
        return self


class ProfiledBoardReviseRequest(ProfiledBoardCreateRequest):
    expected_revision_id: str = Field(min_length=1, max_length=200)


class SpanBoardCandidate(BoardCandidate):
    omitted_before: int = Field(ge=0, strict=True)
    omitted_after: int = Field(ge=0, strict=True)
    matched_requirement_ids: list[str] = Field(min_length=1, max_length=MAX_SPAN_REQUIREMENTS)
    budget_tokens: int = Field(ge=1, le=MAX_SPAN_BUDGET_TOKENS, strict=True)
    hard_boundary_clipped: bool

    @model_validator(mode='after')
    def exact_delivered_span(self):
        ref = self.reference
        if (not math.isfinite(self.score) or self.score <= 0 or self.rank < 1
                or len(ref.quote) != ref.end - ref.start or len(ref.quote) > MAX_SPAN_CHARACTERS
                or self.budget_tokens != budget_token_count(ref.quote)
                or ref.end > self.total_block_characters
                or self.omitted_before != ref.start
                or self.omitted_after != self.total_block_characters - ref.end
                or self.omitted_characters != self.omitted_before + self.omitted_after
                or len(set(self.matched_requirement_ids)) != len(self.matched_requirement_ids)):
            raise ValueError('Span metadata must describe the exact delivered canonical quotation.')
        return self


class SpanRequirementMatch(Model):
    requirement_id: str
    matched_windows: int = Field(ge=0, strict=True)
    selected_windows: int = Field(ge=0, strict=True)
    state: Literal['no_lexical_match', 'candidates_selected', 'candidates_not_selected', 'no_query_tokens']
    index_incomplete: bool
    meaning: Literal['lexical_potential_not_inspected_or_supported'] = 'lexical_potential_not_inspected_or_supported'


class SpanBoardCandidates(BoardCandidates):
    schema_version: Literal['mvp.board-candidates.spans.v2'] = 'mvp.board-candidates.spans.v2'
    candidates: list[SpanBoardCandidate] = Field(max_length=MAX_SPAN_SELECTIONS)
    requirements: list[SpanRequirement] = Field(min_length=1, max_length=MAX_SPAN_REQUIREMENTS)
    requirement_matches: list[SpanRequirementMatch] = Field(min_length=1, max_length=MAX_SPAN_REQUIREMENTS)
    indexed_windows: int = Field(ge=0, strict=True)
    matched_windows: int = Field(ge=0, strict=True)
    omitted_matched_windows: int = Field(ge=0, strict=True)
    total_source_blocks: int = Field(ge=0, strict=True)
    unindexed_source_blocks: int = Field(ge=0, strict=True)
    partially_indexed_blocks: int = Field(ge=0, strict=True)
    skipped_blank_blocks: int = Field(ge=0, strict=True)
    total_source_characters: int = Field(ge=0, strict=True)
    indexed_source_characters: int = Field(ge=0, strict=True)
    unindexed_source_characters: int = Field(ge=0, strict=True)
    delivered_characters: int = Field(ge=0, le=MAX_DELIVERED_CHARACTERS, strict=True)
    delivered_budget_tokens: int = Field(ge=0, le=MAX_DELIVERED_BUDGET_TOKENS, strict=True)
    budget_tokenizer_id: str
    index_limits: list[str] = Field(max_length=20)
    warnings: list[str] = Field(max_length=20)
    elapsed_seconds: float = Field(ge=0)
    context_scope: Literal['exact_retained_spans_only_not_whole_paper'] = 'exact_retained_spans_only_not_whole_paper'

    @model_validator(mode='after')
    def counts(self):
        ids = [value.id for value in self.requirements]
        matches = {value.requirement_id: value for value in self.requirement_matches}
        blocks = {(value.reference.source_id,value.reference.block_id) for value in self.candidates}
        anchors = {(value.reference.source_id,value.reference.block_id,value.reference.start,value.reference.end)
                   for value in self.candidates}
        if (len(set(ids)) != len(ids) or len(matches) != len(self.requirement_matches) or set(matches) != set(ids)
                or not math.isfinite(self.elapsed_seconds)
                or self.budget_tokenizer_id != BUDGET_TOKENIZER_ID
                or self.returned_count != len(self.candidates)
                or len(anchors) != self.returned_count
                or len({value.reference.id for value in self.candidates}) != self.returned_count
                or [value.rank for value in self.candidates] != list(range(1,self.returned_count+1))
                or any(value.reference.paper_id != self.paper_id for value in self.candidates)
                or self.delivered_characters != sum(len(value.reference.quote) for value in self.candidates)
                or self.delivered_budget_tokens != sum(value.budget_tokens for value in self.candidates)
                or self.matched_windows > self.indexed_windows or self.matched_blocks > self.indexed_blocks
                or len(blocks) > self.matched_blocks
                or self.omitted_matched_blocks != self.matched_blocks-len(blocks)
                or self.partially_indexed_blocks > self.indexed_blocks
                or self.skipped_blank_blocks > self.unindexed_source_blocks
                or self.omitted_matched_windows != self.matched_windows - self.returned_count
                or self.unindexed_source_blocks != self.total_source_blocks - self.indexed_blocks
                or self.unindexed_source_characters != self.total_source_characters - self.indexed_source_characters):
            raise ValueError('Span receipt counts must retain block/window and delivered/indexed distinctions.')
        for value in self.candidates:
            if not set(value.matched_requirement_ids) <= set(ids):
                raise ValueError('Candidate components must belong to this exact field retrieval input.')
        for key, value in matches.items():
            selected = sum(key in candidate.matched_requirement_ids for candidate in self.candidates)
            expected = 'candidates_selected' if selected else 'candidates_not_selected' if value.matched_windows else 'no_lexical_match'
            if value.state == 'no_query_tokens' and not value.matched_windows and not selected:
                expected = 'no_query_tokens'
            if (value.selected_windows != selected or selected > value.matched_windows
                    or value.matched_windows > self.matched_windows or value.state != expected):
                raise ValueError('Component match state must describe candidates, never semantic support.')
        return self


BoardCandidatesResult = Annotated[BoardCandidates | SpanBoardCandidates, Field(discriminator='schema_version')]


class BoardSpanCapability(Model):
    enabled: bool = True
    profile_ids: list[BoardProfileId] = [LEGACY_BOARD_PROFILE, SPAN_BOARD_PROFILE]
    default_profile_id: BoardProfileId = LEGACY_BOARD_PROFILE
    max_requirements_per_field: int = MAX_SPAN_REQUIREMENTS
    max_candidates_per_field: int = MAX_SPAN_SELECTIONS
    max_candidate_characters: int = MAX_SPAN_CHARACTERS
    max_candidate_budget_tokens: int = MAX_SPAN_BUDGET_TOKENS
    max_delivered_characters: int = MAX_DELIVERED_CHARACTERS
    max_delivered_budget_tokens: int = MAX_DELIVERED_BUDGET_TOKENS
    max_indexed_blocks: int = MAX_INDEXED_BLOCKS
    max_indexed_windows: int = MAX_INDEXED_WINDOWS
    max_indexed_characters: int = MAX_INDEXED_CHARACTERS
    max_search_seconds: float = MAX_SEARCH_SECONDS
    budget_tokenizer_id: str = BUDGET_TOKENIZER_ID
    meaning: str = 'Explicit definition profiles; lexical matches are not inspected evidence or human support.'
