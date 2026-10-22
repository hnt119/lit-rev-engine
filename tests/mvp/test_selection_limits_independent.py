"""Independent source-selection gates; synthetic records, no provider network.

Thirty is the selection contract. The legacy synchronous operation remains
bounded at ten until callers use the persisted preparation-job interface.
"""
import pytest
from pydantic import ValidationError

from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.board_contracts import BoardCreateRequest, BoardFieldInput, BoardLimits
from src.mvp.contracts import Block, Paper, PreparedSource, PrepareSourcesRequest, SearchPreview, SearchRequest
from src.mvp.limits import MAX_PREPARED_SOURCES, MAX_SYNCHRONOUS_PREPARED_SOURCES
from src.mvp.ports import MvpError
from src.mvp.proposal_contracts import ProposalCapability, ProposalGenerateRequest
from src.mvp.service import MVPService


@pytest.mark.parametrize("count", [1, 10, 11, 29, 30])
def test_selection_contract_accepts_up_to_thirty_unique_ids(count):
    ids = [f"synthetic:{index}" for index in range(count)]
    request = PrepareSourcesRequest(request_id="independent-contract", search_id="saved", paper_ids=ids)
    assert request.paper_ids == ids
    assert MAX_PREPARED_SOURCES == 30
    assert MAX_SYNCHRONOUS_PREPARED_SOURCES == 10


@pytest.mark.parametrize("ids", [[], [f"synthetic:{index}" for index in range(31)], ["same", "same"]])
def test_invalid_selection_contract_is_rejected(ids):
    with pytest.raises(ValidationError):
        PrepareSourcesRequest(request_id="independent-invalid", search_id="saved", paper_ids=ids)


class SyntheticProvider:
    def __init__(self):
        self.papers = [Paper(pmid=str(510000 + index), title=f"SOFTWARE LIMITS RECORD {index}",
                             abstract="Synthetic text for storage and selection tests.") for index in range(31)]
        self.source_calls = []

    def search(self, request):
        return SearchPreview(query=request.query, papers=self.papers, fetched_count=len(self.papers),
            total_reported=len(self.papers), ordered_identifiers=[paper.id for paper in self.papers],
            provider="synthetic-selection-test", mode="test", truncated=False)

    def prepare(self, paper):
        self.source_calls.append(paper.id)
        return PreparedSource(paper_id=paper.id, status="abstract_only", source_type="abstract",
            provider="synthetic-selection-test", source_url="", source_identifiers={"pmid": paper.pmid},
            blocks=[Block(id="abstract:1", ordinal=1, text=paper.abstract, locator={"type": "abstract"})])


@pytest.mark.parametrize("count", [1, 10, 11, 29, 30])
def test_legacy_prepare_never_expands_the_locked_provider_loop(tmp_path, count):
    provider = SyntheticProvider()
    engine = MVPService(SQLiteWorkspaceStorage(tmp_path / "workspace.sqlite3"), provider, provider)
    handle = engine.create_workspace()
    search = engine.search_literature(handle, SearchRequest(request_id="search", query="synthetic", max_results=50))
    before = engine.get_workspace(handle)
    ids = [paper.id for paper in search.papers[:count]]
    request = PrepareSourcesRequest(request_id="prepare", search_id=search.id, paper_ids=ids)
    if count <= 10:
        result = engine.prepare_sources(handle, request)
        assert result.selected_paper_ids == ids
        assert provider.source_calls == ids
    else:
        with pytest.raises(MvpError) as failure:
            engine.prepare_sources(handle, request)
        assert failure.value.code == "preparation_job_required"
        assert provider.source_calls == []
        assert engine.get_workspace(handle).model_dump_json() == before.model_dump_json()


def test_discovery_board_and_generation_limits_are_independent():
    assert SearchRequest(request_id="search", query="synthetic", max_results=50).max_results == 50
    with pytest.raises(ValidationError):
        SearchRequest(request_id="search", query="synthetic", max_results=51)
    field = BoardFieldInput(id="field", label="Field", subquestion="What is reported?")
    assert len(BoardCreateRequest(request_id="board", preparation_id="prepared", question="Synthetic?",
        paper_ids=[str(index) for index in range(10)], fields=[field]).paper_ids) == 10
    with pytest.raises(ValidationError):
        BoardCreateRequest(request_id="board", preparation_id="prepared", question="Synthetic?",
            paper_ids=[str(index) for index in range(11)], fields=[field])
    assert BoardLimits().max_cells == 60
    assert ProposalCapability().max_papers == ProposalCapability().max_calls == 3
    with pytest.raises(ValidationError):
        ProposalGenerateRequest(request_id="proposal", expected_revision_id="revision",
            paper_ids=[str(index) for index in range(4)], field_ids=["field"])
