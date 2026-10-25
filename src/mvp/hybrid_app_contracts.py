"""Application envelopes for hybrid evidence; old lexical DTOs are unchanged."""
from typing import Annotated, Literal
from pydantic import Field
from .contracts import Model, BoardPassageScope, now
from .hybrid_contracts import HybridProfileId, HybridResult
from .board_contracts import BoardReferenceContext

class HybridScopeRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    profile_id: HybridProfileId
    device: Literal['cpu', 'mps'] = 'cpu'
    expected_preparation_id: str = Field(min_length=1, max_length=200)
    expected_source_revision: int = Field(ge=1, strict=True)
    board_context: BoardPassageScope | None = None

class HybridSearchRequest(HybridScopeRequest):
    question: str = Field(min_length=1, max_length=10000)
    top_k: int = Field(default=5, ge=5, le=30, strict=True)

class HybridCellSearchRequest(HybridScopeRequest):
    question: str = Field(min_length=1,max_length=10000)
    top_k: int = Field(default=3,ge=1,le=3,strict=True)

class HybridSavedRun(Model):
    schema_version: Literal['mvp.hybrid-saved-run.v1'] = 'mvp.hybrid-saved-run.v1'
    id: str
    workspace_id: str
    preparation_id: str
    source_revision: int
    board_context: BoardPassageScope | None
    request_sha256: str
    result: HybridResult
    created_at: str = Field(default_factory=now)

class HybridRunListing(Model):
    runs: list[HybridSavedRun]

class HybridBoardCandidates(Model):
    schema_version: Literal['mvp.board-candidates.hybrid.v1'] = 'mvp.board-candidates.hybrid.v1'
    id: str
    board_id: str
    board_revision_id: str
    paper_id: str
    field_id: str
    field_revision_id: str
    preparation_id: str
    source_manifest_sha256: str
    retrieval_profile: dict
    retrieval_profile_sha256: str
    result: HybridResult
    created_at: str = Field(default_factory=now)

class HybridSourceContext(BoardReferenceContext):
    run_id: str
    candidate_id: str
