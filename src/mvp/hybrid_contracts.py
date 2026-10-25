"""Versioned hybrid retrieval contracts. Lexical-only records stay frozen."""
from typing import Literal
from pydantic import Field, model_validator
from .contracts import Model, digest
from .board_contracts import BoardReference
from .span_retrieval_contracts import SpanRequirement

QWEN_PROFILE = 'hybrid_qwen3_06b_rrf_rerank_v1'
MEDCPT_PROFILE = 'hybrid_medcpt_passage_rrf_rerank_v1'
HybridProfileId = Literal['hybrid_qwen3_06b_rrf_rerank_v1', 'hybrid_medcpt_passage_rrf_rerank_v1']

class HybridSourceBinding(Model):
    source_id: str
    paper_id: str
    version: str
    source_sha256: str
    blocks_sha256: str
    parser_id: str
    source_type: Literal['full_text', 'abstract', 'none']

class HybridWindow(Model):
    id: str
    reference: BoardReference
    title: str
    source_type: Literal['full_text', 'abstract']
    total_block_characters: int = Field(ge=1)
    split_sentence: bool = False
    context: Literal['title_is_metadata_quote_is_exact_passage'] = 'title_is_metadata_quote_is_exact_passage'

class HybridCoverage(Model):
    total_source_blocks: int = Field(ge=0)
    indexed_blocks: int = Field(ge=0)
    total_source_characters: int = Field(ge=0)
    indexed_source_characters: int = Field(ge=0)
    indexed_windows: int = Field(ge=0)
    unindexed_characters: int = Field(ge=0)
    complete: bool
    omissions: list[str]
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def counts(self):
        if (self.indexed_blocks > self.total_source_blocks or
            self.indexed_source_characters + self.unindexed_characters != self.total_source_characters or
            self.complete != (self.unindexed_characters == 0)):
            raise ValueError('Hybrid coverage must reconcile exact source characters')
        return self

class HybridInventory(Model):
    schema_version: Literal['mvp.hybrid-inventory.v1'] = 'mvp.hybrid-inventory.v1'
    windowizer: str
    source_manifest: list[HybridSourceBinding]
    source_snapshot_sha256: str
    windows: list[HybridWindow]
    coverage: HybridCoverage
    manifest_sha256: str

    def binding_data(self):
        return self.model_dump(mode='json', exclude={'manifest_sha256'})

    @model_validator(mode='after')
    def manifest(self):
        if self.manifest_sha256 != digest(self.binding_data()):
            raise ValueError('Hybrid inventory hash must bind complete contents and scope')
        if self.coverage.indexed_windows != len(self.windows) or len({v.id for v in self.windows}) != len(self.windows):
            raise ValueError('Hybrid inventory needs exact unique window counts')
        return self

class HybridIndex(Model):
    schema_version: Literal['mvp.hybrid-index.v1'] = 'mvp.hybrid-index.v1'
    profile_id: HybridProfileId
    profile_manifest_sha256: str
    window_manifest_sha256: str
    dimension: int = Field(ge=1)
    dtype: Literal['float32'] = 'float32'
    vectors: list[list[float]]
    vectors_sha256: str
    elapsed_seconds: float = Field(ge=0)
    runtime: dict
    index_key: str

    @model_validator(mode='after')
    def dimensions(self):
        if self.vectors_sha256 != digest(self.vectors):
            raise ValueError('Cached vector bytes must match the verified content hash')
        if any(len(row) != self.dimension for row in self.vectors):
            raise ValueError('Every vector must have the declared model dimension')
        if self.index_key != digest([self.profile_id, self.profile_manifest_sha256,
                                    self.window_manifest_sha256, self.dimension, self.dtype]):
            raise ValueError('Index key must bind profile and complete window inventory')
        return self

class HybridStage(Model):
    rank: int | None = Field(default=None, ge=1)
    score: float | None = None

    @model_validator(mode='after')
    def missing_pair(self):
        if (self.rank is None) != (self.score is None):
            raise ValueError('Absent branch rank and score must both remain null')
        return self

class HybridComponentStages(Model):
    component_id: str
    bm25: HybridStage
    dense: HybridStage
    fusion: HybridStage
    rerank: HybridStage

class HybridCandidate(Model):
    candidate_id: str
    rank: int = Field(ge=1)
    reference: BoardReference
    source_type: Literal['full_text', 'abstract']
    total_block_characters: int = Field(ge=1)
    omitted_before: int = Field(ge=0)
    omitted_after: int = Field(ge=0)
    component_ids: list[str]
    branch_membership: list[Literal['bm25', 'dense']]
    stages: list[HybridComponentStages]
    score: float
    score_meaning: Literal['reranker_relevance_not_support_probability'] = 'reranker_relevance_not_support_probability'

    @model_validator(mode='after')
    def exact(self):
        ref = self.reference
        if (ref.end - ref.start != len(ref.quote) or self.omitted_before != ref.start or
            self.omitted_after != self.total_block_characters-ref.end or
            len(set(self.component_ids)) != len(self.component_ids) or
            set(self.component_ids) != {v.component_id for v in self.stages}):
            raise ValueError('Hybrid candidate must preserve exact anchors and component associations')
        for stage in self.stages:
            branches = {name for name in ('bm25', 'dense') if getattr(stage, name).rank is not None}
            if not branches <= set(self.branch_membership) or stage.fusion.rank is None or stage.rerank.rank is None:
                raise ValueError('Hybrid stages must retain branch membership and completed reranking')
        return self

class HybridComponentReceipt(Model):
    requirement: SpanRequirement
    lexical_matches: int = Field(ge=0)
    lexical_candidates: int = Field(ge=0)
    dense_candidates: int = Field(ge=0)
    fusion_candidates: int = Field(ge=0)
    reranked_candidates: int = Field(ge=0)
    selected_candidates: int = Field(ge=0)
    meaning: Literal['candidate_association_not_semantic_coverage'] = 'candidate_association_not_semantic_coverage'

class HybridResult(Model):
    schema_version: Literal['mvp.hybrid-retrieval.v1'] = 'mvp.hybrid-retrieval.v1'
    run_id: str
    profile_id: HybridProfileId
    profile_revision: Literal[1] = 1
    experimental: bool = True
    original_query: str
    requirements: list[SpanRequirement]
    candidates: list[HybridCandidate]
    requested_count: int = Field(ge=1, le=30)
    returned_count: int = Field(ge=0, le=30)
    operation: Literal['search', 'cell']
    source_manifest: list[HybridSourceBinding]
    source_snapshot_sha256: str
    window_manifest_sha256: str
    coverage: HybridCoverage
    model_manifest: dict
    profile_parameters: dict
    component_receipts: list[HybridComponentReceipt]
    index_key: str
    timings: dict[str, float]
    runtime: dict
    terminal_status: Literal['completed'] = 'completed'
    offset_convention: Literal['half-open-unicode-codepoints'] = 'half-open-unicode-codepoints'
    meaning: Literal['retrieval_candidates_not_inspected_support'] = 'retrieval_candidates_not_inspected_support'

    @model_validator(mode='after')
    def counts(self):
        if self.returned_count != len(self.candidates) or self.returned_count > self.requested_count:
            raise ValueError('Hybrid result counts must agree')
        if self.operation == 'cell' and self.requested_count > 3:
            raise ValueError('Cell retrieval remains bounded to three selections')
        if [v.rank for v in self.candidates] != list(range(1, len(self.candidates)+1)):
            raise ValueError('Hybrid final ranks must be contiguous')
        if len({v.candidate_id for v in self.candidates}) != len(self.candidates):
            raise ValueError('Hybrid candidates must be unique')
        return self
