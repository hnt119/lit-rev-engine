"""Versioned web-bound retrieval and archived inspection; synthetic sources only."""
from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor
import pytest
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.contracts import (Block, BoundRetrieveEvidenceRequest, Paper, PreparedSource,
    PrepareSourcesRequest, RetrieveEvidenceRequest, SaveAssessmentRequest, SearchPreview,
    SearchRequest, SourceContextRequest, digest)
from src.mvp.ports import MvpError
from src.mvp.service import MVPService

class Provider:
    title = "Original synthetic citation"
    text = "Prefix 😀 e\u0301 女人. microbiome <tag> & source."
    def search(self, request):
        paper = Paper(title=self.title, pmid="1", abstract=self.text)
        return SearchPreview(query=request.query,total_reported=1,fetched_count=1,
            papers=[paper],ordered_identifiers=["1"],truncated=False,mode="test")
    def prepare(self,paper):
        block=Block(id="abstract:1",ordinal=1,text=paper.abstract,locator={"type":"abstract"})
        return PreparedSource(paper_id=paper.id,status="abstract_only",source_type="abstract",
            provider="synthetic",source_url="",blocks=[block],source_sha256=sha256(paper.abstract.encode()).hexdigest(),
            blocks_sha256=digest([block.model_dump()]))

@pytest.fixture
def workflow(tmp_path):
    provider=Provider()
    storage=SQLiteWorkspaceStorage(tmp_path/"workspace.sqlite3")
    service=MVPService(storage,provider,provider)
    handle=service.create_workspace()
    search=service.search_literature(handle,SearchRequest(request_id="s1",query="microbiome"))
    prep=service.prepare_sources(handle,PrepareSourcesRequest(request_id="p1",search_id=search.id,paper_ids=["pmid:1"]))
    return service,handle,search,prep,provider,storage

def bound(prep,key="run"):
    return BoundRetrieveEvidenceRequest(request_id=key,question="microbiome",expected_preparation_id=prep.id,expected_source_revision=prep.source_revision)

def test_bound_retrieval_is_idempotent_and_legacy_still_works(workflow):
    service,handle,_,prep,*_=workflow
    first=service.retrieve_evidence_bound(handle,bound(prep))
    assert service.retrieve_evidence_bound(handle,bound(prep))==first
    legacy=service.retrieve_evidence(handle,RetrieveEvidenceRequest(request_id="legacy",question="microbiome"))
    assert first.method==legacy.method and first.preparation_id==legacy.preparation_id
    assert len(service.get_workspace(handle).runs)==2

def test_expected_binding_checked_inside_serialized_operation(workflow,monkeypatch):
    service,handle,search,prep,_,storage=workflow
    original=storage.transact
    def transact(h,operation,*args):
        if operation=="retrieve_bound_v1":
            service.prepare_sources(handle,PrepareSourcesRequest(request_id="race",search_id=search.id,paper_ids=prep.selected_paper_ids))
        return original(h,operation,*args)
    monkeypatch.setattr(storage,"transact",transact)
    with pytest.raises(MvpError,match="Prepared sources changed") as error:
        service.retrieve_evidence_bound(handle,bound(prep))
    assert error.value.code=="stale_preparation"
    assert service.get_workspace(handle).runs==[]

def test_archived_source_remains_original_and_cannot_be_assessed(workflow):
    service,handle,search,prep,provider,_=workflow
    run=service.retrieve_evidence_bound(handle,bound(prep))
    request=SourceContextRequest(run_id=run.id,passage_id=run.passages[0].id)
    before=service.get_source_context(handle,request)
    provider.title="New metadata for same PMID"
    provider.text="Different microbiome source revision"
    later=service.search_literature(handle,SearchRequest(request_id="s2",query="microbiome"))
    service.prepare_sources(handle,PrepareSourcesRequest(request_id="p2",search_id=later.id,paper_ids=["pmid:1"]))
    with pytest.raises(MvpError): service.get_source_context(handle,request)
    archived=service.get_historical_source_context(handle,request)
    assert archived==before and archived.paper.title=="Original synthetic citation"
    assert archived.block.text==Provider.text
    with pytest.raises(MvpError): service.save_assessment(handle,SaveAssessmentRequest(request_id="a",run_id=run.id))
    assert service.get_workspace(handle).assessments==[]

def test_archived_manifest_or_canonical_text_tampering_fails(workflow):
    service,handle,_,prep,_,storage=workflow
    run=service.retrieve_evidence_bound(handle,bound(prep))
    request=SourceContextRequest(run_id=run.id,passage_id=run.passages[0].id)
    def tamper(state):
        bad=state.preparations[0].model_copy(update={"search_id":"different"})
        return state.model_copy(update={"preparations":[bad]}),{}
    storage.transact(handle,"test-corruption","tamper","test",tamper)
    with pytest.raises(MvpError,match="original preparation"):
        service.get_historical_source_context(handle,request)
