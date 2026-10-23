"""Additive, strict contracts for manual report-by-field comparison boards.

Offsets use half-open Unicode code points. Mechanical quote integrity and
single-human support judgments are deliberately separate dimensions.
"""
from typing import Annotated, Any, Literal
import re
from pydantic import Field, model_validator
from .contracts import Model, new_id, now
from .collection_contracts import CollectionInputRef
from .limits import MAX_BOARD_PAPERS, MAX_BOARD_FIELDS, MAX_BOARD_CELLS

# Keep existing imports compatible while the selection policy has one source.
MAX_FIELDS = MAX_BOARD_FIELDS
MAX_CELLS = MAX_BOARD_CELLS
MAX_BOARDS = 10
MAX_DEFINITIONS = 20
MAX_CELL_REVISIONS = 50
MAX_REFERENCES = 5
MAX_WORKSPACE_BYTES = 32 * 1024 * 1024
MAX_CANDIDATE_CHARACTERS = 1200
MAX_INSPECTOR_CHARACTERS = 4000

class BoardLimits(Model):
    max_papers: int = MAX_BOARD_PAPERS
    max_fields: int = MAX_FIELDS
    max_cells: int = MAX_CELLS
    max_boards: int = MAX_BOARDS
    max_definition_revisions: int = MAX_DEFINITIONS
    max_cell_revisions: int = MAX_CELL_REVISIONS
    max_references: int = MAX_REFERENCES
    max_workspace_bytes: int = MAX_WORKSPACE_BYTES
    max_candidate_characters: int = MAX_CANDIDATE_CHARACTERS
    max_inspector_characters: int = MAX_INSPECTOR_CHARACTERS

class BoardFieldInput(Model):
    id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=200)
    subquestion: str = Field(min_length=1, max_length=2000)

    @model_validator(mode='after')
    def text(self):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_:.\-]{0,99}', self.id):
            raise ValueError('Use a path-safe ASCII field identifier')
        if not self.id.strip() or not self.label.strip() or not self.subquestion.strip():
            raise ValueError('Fields need an identifier, label and subquestion')
        return self

class BoardField(BoardFieldInput):
    revision_id: str = Field(default_factory=new_id)

class BoardCreateRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    preparation_id: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=10000)
    paper_ids: list[str] = Field(min_length=1, max_length=MAX_BOARD_PAPERS)
    fields: list[BoardFieldInput] = Field(min_length=1, max_length=MAX_FIELDS)

    @model_validator(mode='after')
    def unique(self):
        if not self.question.strip() or len(set(self.paper_ids)) != len(self.paper_ids):
            raise ValueError('Use a question and unique papers')
        if len({f.id for f in self.fields}) != len(self.fields) or len(self.fields) * len(self.paper_ids) > MAX_CELLS:
            raise ValueError('Use unique fields within the board cell limit')
        return self

class BoardReviseRequest(BoardCreateRequest):
    expected_revision_id: str = Field(min_length=1, max_length=200)

class BoardSourceBinding(Model):
    source_id: str
    paper_id: str
    version: str
    source_sha256: str
    blocks_sha256: str
    parser_id: str
    source_type: Literal['full_text', 'abstract', 'none']
    status: str
    block_count: int

class BoardPaper(Model):
    id: str
    title: str
    authors: list[str]
    year: int | None = None
    pmid: str | None = None
    doi: str | None = None
    pmcid: str | None = None
    url: str

class BoardRevision(Model):
    schema_version: Literal['mvp.board-definition.v1'] = 'mvp.board-definition.v1'
    board_id: str
    revision_id: str = Field(default_factory=new_id)
    workspace_id: str
    parent_revision_id: str | None = None
    search_id: str
    search_sha256: str
    question: str
    question_sha256: str
    preparation_id: str
    source_revision: int
    source_manifest_sha256: str
    sources: list[BoardSourceBinding]
    papers: list[BoardPaper]
    paper_ids: list[str]
    fields: list[BoardField]
    retrieval_profile: dict[str, Any]
    retrieval_profile_sha256: str
    created_at: str = Field(default_factory=now)

class CollectionBoardRevision(Model):
    """New origin contract; legacy BoardRevision serialization is unchanged."""
    schema_version: Literal['mvp.collection-board-definition.v2'] = 'mvp.collection-board-definition.v2'
    board_id: str
    revision_id: str = Field(default_factory=new_id)
    workspace_id: str
    parent_revision_id: str | None = None
    search_id: None = None
    search_sha256: None = None
    collection_ref: CollectionInputRef
    member_snapshot_sha256: str
    question: str
    question_sha256: str
    preparation_id: str
    source_revision: int
    source_manifest_sha256: str
    sources: list[BoardSourceBinding]
    papers: list[BoardPaper]
    paper_ids: list[str]
    fields: list[BoardField]
    retrieval_profile: dict[str, Any]
    retrieval_profile_sha256: str
    created_at: str = Field(default_factory=now)

BoardDefinition = Annotated[BoardRevision | CollectionBoardRevision, Field(discriminator='schema_version')]

class BoardReferenceInput(Model):
    source_id: str = Field(min_length=1, max_length=200)
    source_version: str = Field(min_length=1, max_length=200)
    source_sha256: str = Field(max_length=64)
    blocks_sha256: str = Field(max_length=64)
    block_id: str = Field(min_length=1, max_length=200)
    start: int = Field(ge=0, strict=True)
    end: int = Field(ge=1, strict=True)

    @model_validator(mode='after')
    def range(self):
        if self.end <= self.start or self.end - self.start > MAX_INSPECTOR_CHARACTERS:
            raise ValueError('Use a nonempty bounded Unicode code-point range')
        return self

class BoardReference(BoardReferenceInput):
    id: str
    paper_id: str
    quote: str
    locator: dict[str, Any]
    integrity: Literal['checked'] = 'checked'

class BoardCellData(Model):
    value: str | None = Field(default=None, max_length=10000)
    references: list[BoardReferenceInput] = Field(default_factory=list, max_length=MAX_REFERENCES)
    inspected_ranges: list[BoardReferenceInput] = Field(default_factory=list, max_length=30)
    semantic_assessment: Literal['unassessed', 'human_supported', 'partial', 'unsupported'] = 'unassessed'
    scope_result: Literal['not_assessed', 'value_found', 'not_found_in_inspected_material'] = 'not_assessed'
    missing_information: str = Field(default='', max_length=10000)
    reason: str = Field(default='', max_length=10000)
    producer: Literal['manual'] = 'manual'

class BoardDraftPutRequest(Model):
    expected_revision_id: str = Field(min_length=1, max_length=200)
    version: int = Field(ge=0, strict=True)
    expected_cell_head_id: str | None = Field(default=None, max_length=200)
    data: BoardCellData

class BoardCellDraft(Model):
    board_id: str
    board_revision_id: str
    paper_id: str
    field_id: str
    version: int = 0
    expected_cell_head_id: str | None = None
    data: BoardCellData = Field(default_factory=BoardCellData)
    updated_at: str | None = None

class BoardSubmitRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    expected_revision_id: str = Field(min_length=1, max_length=200)
    paper_id: str = Field(min_length=1, max_length=200)
    field_id: str = Field(min_length=1, max_length=100)
    draft_version: int = Field(ge=1, strict=True)
    supersedes_id: str | None = Field(default=None, max_length=200)

class BoardCellRevision(Model):
    schema_version: Literal['mvp.board-cell.v1'] = 'mvp.board-cell.v1'
    id: str = Field(default_factory=new_id)
    board_id: str
    board_revision_id: str
    field_revision_id: str
    paper_id: str
    field_id: str
    supersedes_id: str | None = None
    value: str | None
    references: list[BoardReference]
    inspected_ranges: list[BoardReference]
    semantic_assessment: Literal['unassessed', 'human_supported', 'partial', 'unsupported']
    scope_result: Literal['not_assessed', 'value_found', 'not_found_in_inspected_material']
    missing_information: str
    reason: str
    producer: Literal['manual'] = 'manual'
    reference_integrity: Literal['checked', 'not_applicable']
    review_state: Literal['single_human_self_declared_not_independently_verified'] = 'single_human_self_declared_not_independently_verified'
    created_at: str = Field(default_factory=now)

class BoardReferenceSummary(BoardReferenceInput):
    id: str
    paper_id: str
    locator: dict[str, Any]
    integrity: Literal['checked'] = 'checked'

class BoardCellHead(BoardCellRevision):
    references: list[BoardReferenceSummary]
    inspected_ranges: list[BoardReferenceSummary]

class BoardCellSummary(Model):
    paper_id: str
    field_id: str
    head: BoardCellHead | None = None
    draft_version: int = 0

class BoardSummary(Model):
    board_id: str
    revision_id: str
    question: str
    paper_count: int
    field_count: int
    created_at: str
    preparation_id: str | None = None
    paper_ids: list[str] = Field(default_factory=list)

class BoardListing(Model):
    boards: list[BoardSummary]
    limits: BoardLimits = Field(default_factory=BoardLimits)

class BoardView(Model):
    definition: BoardDefinition
    current_revision_id: str
    freshness: Literal['current', 'historical']
    freshness_reasons: list[str] = Field(default_factory=list)
    cells: list[BoardCellSummary]
    definitions: list[BoardSummary]
    limits: BoardLimits = Field(default_factory=BoardLimits)

class BoardCandidatesRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    expected_revision_id: str = Field(min_length=1, max_length=200)
    paper_id: str = Field(min_length=1, max_length=200)
    field_id: str = Field(min_length=1, max_length=100)
    top_k: int = Field(default=3, ge=1, le=3, strict=True)

class BoardCandidate(Model):
    rank: int
    score: float
    reference: BoardReference
    total_block_characters: int
    omitted_characters: int

class BoardCandidates(Model):
    schema_version: Literal['mvp.board-candidates.v1'] = 'mvp.board-candidates.v1'
    id: str = Field(default_factory=new_id)
    board_id: str
    board_revision_id: str
    paper_id: str
    field_id: str
    field_revision_id: str
    preparation_id: str
    source_manifest_sha256: str
    retrieval_profile: dict[str, Any]
    retrieval_profile_sha256: str
    indexed_blocks: int
    matched_blocks: int
    returned_count: int
    omitted_matched_blocks: int
    candidates: list[BoardCandidate]
    meaning: Literal['potential_relevance_not_inspected_support'] = 'potential_relevance_not_inspected_support'
    created_at: str = Field(default_factory=now)

class BoardCellHistory(Model):
    items: list[BoardCellRevision]
    offset: int
    limit: int
    total: int

class BoardBlockChunk(Model):
    source_id: str
    paper_id: str
    block_id: str
    ordinal: int
    locator: dict[str, Any]
    start: int
    end: int
    total_characters: int
    text: str
    omitted_before: int
    omitted_after: int
    reference: BoardReference

class BoardSourceInspection(Model):
    board_revision_id: str
    source: BoardSourceBinding
    freshness: Literal['current', 'historical']
    blocks: list[BoardBlockChunk]
    offset: int
    limit: int
    total_blocks: int
    offset_convention: Literal['half-open-unicode-codepoints'] = 'half-open-unicode-codepoints'

class BoardReferenceContext(Model):
    reference: BoardReference
    paper: BoardPaper
    source: BoardSourceBinding
    freshness: Literal['current', 'historical']
    block: BoardBlockChunk

class BoardExport(Model):
    schema_version: Literal['mvp.board-export.v1'] = 'mvp.board-export.v1'
    csv_text: str
    json_text: str

class CollectionBoardExport(Model):
    schema_version: Literal['mvp.collection-board-export.v2'] = 'mvp.collection-board-export.v2'
    csv_text: str
    json_text: str
