"""Additive exact-span retrieval contracts; legacy board/profile models stay frozen."""
from typing import Literal

from pydantic import Field, model_validator

from .contracts import Model

SPAN_PROFILE_ID = 'lexical_spans_v1'
SPAN_METHOD = 'bm25_exact_lexical_spans'
SPAN_METHOD_VERSION = 'lit-rev-engine.board-retrieval.v1.lexical_spans'
MAX_SPAN_CHARACTERS = 1200
MAX_SPAN_BUDGET_TOKENS = 400
MAX_SPAN_SELECTIONS = 3
MAX_DELIVERED_CHARACTERS = 3600
MAX_DELIVERED_BUDGET_TOKENS = 1200
MAX_SPAN_REQUIREMENTS = 3
MAX_INDEXED_BLOCKS = 2048
MAX_INDEXED_WINDOWS = 8192
MAX_INDEXED_CHARACTERS = 4_000_000
MAX_SEARCH_SECONDS = 8
MAX_QUERY_CHARACTERS = 2000
MAX_RETRIEVAL_MESSAGES = 20
TOKEN_BOUNDARY_LOOKBACK_CHARACTERS = 64
OVERLAP_CHARACTERS = 200
MIN_SENTENCE_WINDOW_CHARACTERS = 600
OVERLAP_DEDUP_THRESHOLD = .5
BUDGET_TOKENIZER_ID = 'unicode-word-or-nonspace-punctuation-v1'


class SpanRequirement(Model):
    id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=1, max_length=MAX_QUERY_CHARACTERS)

    @model_validator(mode='after')
    def nonblank(self):
        if not self.id.strip() or not self.label.strip() or not self.query.strip():
            raise ValueError('Explicit retrieval requirements need nonblank IDs, labels and queries')
        for value in (self.id, self.label, self.query):
            value.encode('utf-8')
        return self


class SpanSelection(Model):
    source_id: str
    paper_id: str
    block_id: str
    start: int = Field(ge=0, strict=True)
    end: int = Field(ge=1, strict=True)
    quote: str = Field(min_length=1, max_length=MAX_SPAN_CHARACTERS)
    score: float = Field(gt=0)
    matched_requirement_ids: list[str]
    budget_tokens: int = Field(ge=0, le=MAX_SPAN_BUDGET_TOKENS, strict=True)
    hard_boundary_clipped: bool

    @model_validator(mode='after')
    def exact_length(self):
        if self.end <= self.start or self.end - self.start != len(self.quote):
            raise ValueError('A span must retain its exact nonempty Unicode-codepoint range')
        return self


class SpanRequirementStatus(Model):
    requirement: SpanRequirement
    status: Literal['selected_lexical_match', 'matched_but_not_selected',
                    'no_lexical_match_in_indexed_text', 'no_query_tokens']
    matched_windows: int = Field(ge=0)
    selected_spans: int = Field(ge=0)
    index_incomplete: bool
    meaning: Literal['lexical_potential_not_semantic_coverage'] = 'lexical_potential_not_semantic_coverage'


class SpanRetrievalMessage(Model):
    code: str
    message: str
    severity: Literal['info', 'warning'] = 'warning'


class SpanRetrievalResult(Model):
    schema_version: Literal['mvp.lexical-span-retrieval.v1'] = 'mvp.lexical-span-retrieval.v1'
    run_id: str
    profile_id: Literal['lexical_spans_v1'] = SPAN_PROFILE_ID
    selections: list[SpanSelection] = Field(max_length=MAX_SPAN_SELECTIONS)
    indexed_blocks: int = Field(ge=0)
    matched_blocks: int = Field(ge=0)
    indexed_windows: int = Field(ge=0)
    matched_windows: int = Field(ge=0)
    matched_block_ids: list[str]
    total_source_blocks: int = Field(ge=0)
    total_source_characters: int = Field(ge=0)
    unindexed_blocks: int = Field(ge=0)
    partially_indexed_blocks: int = Field(ge=0)
    skipped_blank_blocks: int = Field(ge=0)
    unindexed_characters: int = Field(ge=0)
    delivered_characters: int = Field(ge=0, le=MAX_DELIVERED_CHARACTERS)
    delivered_tokens: int = Field(ge=0, le=MAX_DELIVERED_BUDGET_TOKENS)
    requirement_statuses: list[SpanRequirementStatus] = Field(max_length=MAX_SPAN_REQUIREMENTS)
    messages: list[SpanRetrievalMessage] = Field(max_length=MAX_RETRIEVAL_MESSAGES)
    elapsed_seconds: float = Field(ge=0)
    offset_convention: Literal['half-open-unicode-codepoints'] = 'half-open-unicode-codepoints'
    meaning: Literal['potential_relevance_not_inspected_support'] = 'potential_relevance_not_inspected_support'
