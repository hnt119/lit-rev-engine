"""Focused concurrency/integrity checks with software fixtures, never real studies."""

from concurrent.futures import ThreadPoolExecutor
import csv
import io
import json
import threading

import pytest
from pydantic import ValidationError

from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.contracts import (
    Block, BundleJudgment, CreateWorkspaceRequest, Paper, PrepareSourcesRequest,
    PassageJudgment, PreparedSource, RetrieveEvidenceRequest, SaveAssessmentRequest, SearchPreview,
    SearchRequest, digest,
)
from src.mvp.ports import MvpError
from src.mvp.service import MVPService


class Discovery:
    def __init__(self, barrier=None):
        self.calls = 0
        self.barrier = barrier
        self.papers = [Paper(title="Synthetic software fixture", pmid="1", abstract="😀 微生物 microbiome diversity.")]

    def search(self, request):
        self.calls += 1
        if self.barrier is not None:
            self.barrier.wait(timeout=5)
        return SearchPreview(query=request.query, total_reported=100, fetched_count=len(self.papers),
                             ordered_identifiers=[paper.pmid or paper.id for paper in self.papers],
                             papers=self.papers, truncated=True, mode="test")


class Sources:
    def __init__(self):
        self.calls = 0
        self.corrupt = False

    def prepare(self, paper):
        self.calls += 1
        block = Block(id="abstract:1", ordinal=1, text=paper.abstract, locator={"type": "abstract"})
        return PreparedSource(paper_id=paper.id, status="abstract_only", source_type="abstract",
                              provider="software-fixture", source_url=paper.url, blocks=[block],
                              blocks_sha256="incorrect" if self.corrupt else digest([block.model_dump()]))


def setup(tmp_path, discovery=None):
    discovery, sources = discovery or Discovery(), Sources()
    storage = SQLiteWorkspaceStorage(tmp_path / "private.sqlite3")
    service = MVPService(storage, discovery, sources)
    handle = service.create_workspace(CreateWorkspaceRequest(question="microbiome"))
    return service, handle, discovery, sources


def prepared(service, handle):
    search = service.search_literature(handle, SearchRequest(request_id="search", query="microbiome"))
    preparation = service.prepare_sources(handle, PrepareSourcesRequest(
        request_id="prepare", search_id=search.id, paper_ids=[paper.id for paper in search.papers]))
    return search, preparation


def test_concurrent_duplicate_request_commits_once(tmp_path):
    service, handle, discovery, sources = setup(tmp_path)
    request = SearchRequest(request_id="one-submit", query="microbiome")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: service.search_literature(handle, request), range(8)))
    assert discovery.calls == 1 and len({result.id for result in results}) == 1
    assert len(service.get_workspace(handle).searches) == 1


def test_separate_workspaces_do_not_hold_database_lock_while_fetching(tmp_path):
    discovery = Discovery(barrier=threading.Barrier(2))
    service, handle, *_ = setup(tmp_path, discovery)
    other = service.create_workspace()
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(service.search_literature, capability,
                             SearchRequest(request_id="same-key-separate-scope", query="microbiome"))
                 for capability in (handle, other)]
        results = [task.result(timeout=10) for task in tasks]
    assert discovery.calls == 2 and results[0].id != results[1].id


def test_preparation_replay_never_reactivates_an_old_selection(tmp_path):
    service, handle, _, sources = setup(tmp_path)
    search, first = prepared(service, handle)
    run = service.retrieve_evidence(handle, RetrieveEvidenceRequest(request_id="run", question="microbiome"))
    assessment = service.save_assessment(handle, SaveAssessmentRequest(request_id="assess", run_id=run.id))
    fresh = service.prepare_sources(handle, PrepareSourcesRequest(request_id="explicit-refresh", search_id=search.id, paper_ids=first.selected_paper_ids))
    with pytest.raises(MvpError) as stale:
        service.prepare_sources(handle, PrepareSourcesRequest(request_id="prepare", search_id=search.id, paper_ids=first.selected_paper_ids))
    snapshot = service.get_workspace(handle)
    assert stale.value.code == "stale_source_revision" and sources.calls == 2
    assert snapshot.source_revision == fresh.source_revision == 2
    assert snapshot.current_run_id is None and not snapshot.current_assessment_ids
    assert snapshot.assessments == [assessment]
    exported = json.loads(service.export_workspace(handle).json_text)
    assert exported["workspace"]["assessments"][0]["id"] == assessment.id
    for operation, old_request in (
        (service.retrieve_evidence, RetrieveEvidenceRequest(request_id="run", question="microbiome")),
        (service.save_assessment, SaveAssessmentRequest(request_id="assess", run_id=run.id)),
    ):
        with pytest.raises(MvpError) as stale:
            operation(handle, old_request)
        assert stale.value.code == "stale_source_revision"


def test_bad_block_hash_is_rejected_and_abstract_is_explicit_fallback(tmp_path):
    service, handle, _, sources = setup(tmp_path)
    sources.corrupt = True
    _, result = prepared(service, handle)
    assert result.sources[0].source_type == "abstract"
    assert result.sources[0].status == "fetch_failed"
    assert result.errors[0].code == "source_integrity_error"
    assert result.sources[0].blocks[0].text.startswith("😀 微生物")


def test_conservative_duplicate_reports_and_original_fetched_counts(tmp_path):
    service, handle, discovery, _ = setup(tmp_path)
    one = Paper(title="First software fixture", pmid="1", doi="10.1234/shared")
    two = Paper(title="Separate software report", pmid="2", doi="10.1234/shared")
    discovery.papers = [one, one, two]
    search = service.search_literature(handle, SearchRequest(request_id="duplicates", query="microbiome"))
    assert search.papers == [one, two]
    assert search.fetched_count == 3 and search.ordered_identifiers == ["1", "1", "2"]
    assert any("duplicate" in warning for warning in search.warnings)


def test_assessment_retry_fingerprint_rejects_new_payload(tmp_path):
    service, handle, *_ = setup(tmp_path)
    prepared(service, handle)
    run = service.retrieve_evidence(handle, RetrieveEvidenceRequest(request_id="run", question="microbiome"))
    request = SaveAssessmentRequest(request_id="assess", run_id=run.id)
    first = service.save_assessment(handle, request)
    assert service.save_assessment(handle, request).id == first.id
    with pytest.raises(MvpError) as conflict:
        service.save_assessment(handle, request.model_copy(update={"feedback": "changed input"}))
    assert conflict.value.code == "idempotency_conflict"
    assert service.get_workspace(handle).assessments == [first]


def test_research_question_is_bound_to_each_search_and_new_workspace_state(tmp_path):
    service, handle, *_ = setup(tmp_path)
    first = service.search_literature(handle, SearchRequest(request_id="first", query="exact query one", research_question="First edited question?"))
    second = service.search_literature(handle, SearchRequest(request_id="second", query="exact query two", research_question="Different question?"))
    snapshot = service.get_workspace(handle)
    assert first.research_question == snapshot.searches[0].research_question == "First edited question?"
    assert second.research_question == snapshot.question == "Different question?"
    with pytest.raises(MvpError) as conflict:
        service.search_literature(handle, SearchRequest(request_id="first", query="exact query one", research_question="Changed question on same key?"))
    assert conflict.value.code == "idempotency_conflict"


def test_workspace_size_limit_rejects_before_commit(tmp_path):
    discovery, sources = Discovery(), Sources()
    storage = SQLiteWorkspaceStorage(tmp_path / "bounded.sqlite3", max_workspace_bytes=800)
    service = MVPService(storage, discovery, sources)
    handle = service.create_workspace()
    with pytest.raises(MvpError) as limited:
        service.search_literature(handle, SearchRequest(request_id="oversized-state", query="microbiome"))
    assert limited.value.code == "workspace_limit"
    assert service.get_workspace(handle).searches == []
    assert json.loads(service.export_workspace(handle).json_text)["workspace"]["searches"] == []


@pytest.mark.parametrize("note", ["\n=SUM(A1:A2)", "  @function()", "\r\n+1+1"])
def test_csv_whitespace_formula_guard_preserves_original_json_note(tmp_path, note):
    service, handle, *_ = setup(tmp_path)
    prepared(service, handle)
    run = service.retrieve_evidence(handle, RetrieveEvidenceRequest(request_id="run", question="microbiome"))
    service.save_assessment(handle, SaveAssessmentRequest(request_id="assess", run_id=run.id,
        passages=[PassageJudgment(passage_id=run.passages[0].id, notes=note)]))
    exported = service.export_workspace(handle)
    assert list(csv.DictReader(io.StringIO(exported.csv_text)))[0]["notes"] == "'" + note
    assert json.loads(exported.json_text)["workspace"]["assessments"][0]["passages"][0]["notes"] == note


@pytest.mark.parametrize("model,fields", [
    (SearchRequest, {"request_id": "x", "query": "microbiome", "max_results": True}),
    (RetrieveEvidenceRequest, {"request_id": "x", "question": "microbiome", "top_k": True}),
    (BundleJudgment, {"status": "sufficient", "reason": "provided", "supporting_passage_ids": ["p"], "missing_information": "also missing"}),
])
def test_contracts_reject_ambiguous_cap_or_bundle_values(model, fields):
    with pytest.raises(ValidationError):
        model(**fields)
