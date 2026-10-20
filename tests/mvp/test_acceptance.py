"""Independent MVP acceptance gates using synthetic software fixtures only.

No fixture in this module is a publication, saved demonstration, human review,
clinical conclusion, or retrieval-effectiveness benchmark. All normal tests are
offline and use temporary private workspaces.
"""

import ast
import csv
from hashlib import sha256
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
from urllib.error import HTTPError
from xml.sax.saxutils import escape

import pytest
from pydantic import ValidationError

from src.mvp.contracts import (
    Block, BundleJudgment, CreateWorkspaceRequest, Paper, PassageJudgment,
    PreparedSource, PrepareSourcesRequest, QuerySuggestionRequest,
    RetrieveEvidenceRequest, SaveAssessmentRequest, SearchPreview,
    SearchRequest, SourceContextRequest, WorkspaceHandle, digest,
)
from src.mvp.ports import MvpError, ProviderFailure


ROOT = Path(__file__).resolve().parents[2]
UNICODE_TEXT = "前置 😀 café e\u0301. Microbiome diversity in synthetic software fixture. 女人。"


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Offline MVP acceptance attempted network access")
    monkeypatch.setattr(socket, "create_connection", denied)


def paper(number=1, **changes):
    return Paper(
        title=f"Synthetic software fixture {number}", authors=["Software fixture"],
        year=2020, pmid=str(number), doi=f"10.1234/software.{number}",
        abstract=UNICODE_TEXT, url=f"https://pubmed.ncbi.nlm.nih.gov/{number}/",
        **changes,
    )


def source_for(record, *, text=UNICODE_TEXT, version="1", status="abstract_only"):
    content = text.encode("utf-8")
    blocks = [] if not text else [Block(
        id="abstract:1", ordinal=1, text=text,
        locator={"type": "abstract", "ordinal": 1},
    )]
    return PreparedSource(
        paper_id=record.id, status=status, source_type="abstract" if text else "none",
        provider="synthetic-software-fixture", source_url=record.url, version=version,
        source_sha256=sha256(content).hexdigest(),
        blocks_sha256=digest([b.model_dump(mode="json") for b in blocks]),
        parser_id="software-fixture.unicode.v1", blocks=blocks,
        source_identifiers={"pmid": record.pmid, "doi": record.doi},
        warnings=["Software fixture; not publication evidence"],
    )


class FixtureDiscovery:
    def __init__(self):
        self.calls = []
        self.papers = [paper(1), paper(2)]

    def search(self, request):
        self.calls.append(request)
        rows = self.papers[:request.max_results]
        return SearchPreview(
            query=request.query, query_translation="Exact software translation",
            total_reported=420, fetched_count=len(rows),
            ordered_identifiers=[row.pmid for row in rows], papers=rows,
            truncated=True, sort=request.sort, mode="test",
        )


class FixtureSources:
    def __init__(self):
        self.calls = []
        self.version = "1"

    def prepare(self, record):
        self.calls.append(record.id)
        return source_for(record, version=self.version)


@pytest.fixture
def workflow(tmp_path):
    from src.mvp.adapters.storage import SQLiteWorkspaceStorage
    from src.mvp.service import MVPService
    discovery, sources = FixtureDiscovery(), FixtureSources()
    storage = SQLiteWorkspaceStorage(tmp_path / "private" / "workspaces.sqlite3")
    service = MVPService(storage, discovery, sources)
    handle = service.create_workspace(CreateWorkspaceRequest(question="Microbiome diversity?"))
    return service, handle, discovery, sources, storage


def search_and_prepare(service, handle, *, selected=None, suffix="1"):
    search = service.search_literature(handle, SearchRequest(
        request_id="search-" + suffix, query="  exact microbiome\nquery  ", max_results=2,
    ))
    preparation = service.prepare_sources(handle, PrepareSourcesRequest(
        request_id="prepare-" + suffix, search_id=search.id,
        paper_ids=selected or [p.id for p in search.papers],
    ))
    return search, preparation


def retrieve(service, handle, *, suffix="1", question="Microbiome diversity"):
    return service.retrieve_evidence(handle, RetrieveEvidenceRequest(
        request_id="retrieve-" + suffix, question=question,
    ))


def test_headless_workflow_binds_search_source_question_and_exports(workflow):
    service, handle, discovery, sources, _ = workflow
    suggestion = service.suggest_query(handle, QuerySuggestionRequest(question="Microbiome in women"))
    assert suggestion.query and suggestion.method == "transparent-template-v1"
    search, preparation = search_and_prepare(service, handle)
    run = retrieve(service, handle)
    assert search.query == discovery.calls[0].query == "  exact microbiome\nquery  "
    assert search.total_reported == 420 and search.fetched_count == 2 and search.truncated
    assert search.schema_version == "mvp.exploratory-preview.v1"
    assert preparation.selection_state == "selected_for_exploration"
    assert run.schema_version == "mvp.lexical-evidence.v1"
    assert run.search_id == search.id and run.preparation_id == preparation.id
    assert run.question == "Microbiome diversity" and 1 <= len(run.passages) <= 5
    judgment = service.save_assessment(handle, SaveAssessmentRequest(
        request_id="assess", run_id=run.id,
        passages=[PassageJudgment(passage_id=run.passages[0].id, decision="useful", notes="Software check")],
        bundle=BundleJudgment(status="partial", reason="Fixture bundle only", missing_information="Study population"),
    ))
    snapshot = service.get_workspace(handle)
    assert snapshot.current_run_id == run.id and snapshot.assessments == [judgment]
    assert judgment.review_state == "single_human_self_declared_not_independently_verified"
    exported = service.export_workspace(handle)
    bundle = json.loads(exported.json_text)
    assert exported.schema_version == "mvp.export.v1" and bundle["schema_version"]
    assert run.id in exported.json_text and judgment.id in exported.json_text
    assert handle.token not in exported.json_text and handle.token not in exported.csv_text
    for model in (suggestion, search, preparation, run, judgment, snapshot, exported):
        json.dumps(model.model_dump(mode="json"), ensure_ascii=False, allow_nan=False)


def test_exact_unicode_codepoint_anchors_and_context(workflow):
    service, handle, *_ = workflow
    search_and_prepare(service, handle)
    run = retrieve(service, handle)
    context = service.get_source_context(handle, SourceContextRequest(
        run_id=run.id, passage_id=run.passages[0].id,
    ))
    anchor = context.passage.anchor
    assert context.offset_convention == "half-open-unicode-codepoints"
    assert context.block.text[anchor.start:anchor.end] == anchor.quote
    assert "😀" in context.block.text and "e\u0301" in context.block.text
    assert anchor.end <= len(context.block.text)
    assert context.passage.source_sha256 == context.source.source_sha256
    assert context.passage.blocks_sha256 == context.source.blocks_sha256
    assert "page" not in context.passage.locator


def test_no_matches_do_not_fill_with_unrelated_text(workflow):
    service, handle, *_ = workflow
    search_and_prepare(service, handle)
    run = retrieve(service, handle, question="zzzzabsenttoken")
    assert run.passages == [] and run.matched_passages == 0
    assert run.indexed_passages > 0


def test_repeated_requests_are_idempotent_and_explicit_refresh_is_new(workflow):
    service, handle, discovery, sources, _ = workflow
    search_request = SearchRequest(request_id="once", query="microbiome")
    first = service.search_literature(handle, search_request)
    assert service.search_literature(handle, search_request) == first
    assert len(discovery.calls) == 1
    preparation_request = PrepareSourcesRequest(request_id="prepare-once", search_id=first.id, paper_ids=[p.id for p in first.papers])
    prepared = service.prepare_sources(handle, preparation_request)
    assert service.prepare_sources(handle, preparation_request) == prepared
    assert len(sources.calls) == 2
    run_request = RetrieveEvidenceRequest(request_id="retrieve-once", question="microbiome")
    run = service.retrieve_evidence(handle, run_request)
    assert service.retrieve_evidence(handle, run_request) == run
    draft = SaveAssessmentRequest(request_id="save-once", run_id=run.id)
    assessment = service.save_assessment(handle, draft)
    assert service.save_assessment(handle, draft) == assessment
    refresh = service.search_literature(handle, SearchRequest(request_id="refresh", query="microbiome"))
    assert refresh.id != first.id and len(discovery.calls) == 2
    snapshot = service.get_workspace(handle)
    assert len(snapshot.searches) == 2 and len(snapshot.runs) == len(snapshot.assessments) == 1


def test_request_key_cannot_be_reused_with_changed_payload(workflow):
    service, handle, discovery, *_ = workflow
    service.search_literature(handle, SearchRequest(request_id="same-key", query="first"))
    with pytest.raises(MvpError):
        service.search_literature(handle, SearchRequest(request_id="same-key", query="changed"))
    assert len(discovery.calls) == 1


def test_two_capability_workspaces_cannot_access_each_other(workflow):
    service, handle, *_ = workflow
    search_and_prepare(service, handle)
    run = retrieve(service, handle)
    other = service.create_workspace(CreateWorkspaceRequest(question="Private other question"))
    counterfeit = WorkspaceHandle(workspace_id=handle.workspace_id, token=other.token)
    assert not hasattr(service, "list_workspaces")
    assert service.get_workspace(other).searches == []
    for operation in (
        lambda: service.get_workspace(counterfeit),
        lambda: service.export_workspace(counterfeit),
        lambda: service.clear_workspace(counterfeit),
        lambda: service.get_source_context(other, SourceContextRequest(run_id=run.id, passage_id=run.passages[0].id)),
    ):
        with pytest.raises(MvpError):
            operation()
    assert service.get_workspace(handle).current_run_id == run.id


def test_saved_assessment_survives_new_service_and_storage_instance(workflow, tmp_path):
    from src.mvp.adapters.storage import SQLiteWorkspaceStorage
    from src.mvp.service import MVPService
    service, handle, discovery, sources, _ = workflow
    search_and_prepare(service, handle)
    run = retrieve(service, handle)
    saved = service.save_assessment(handle, SaveAssessmentRequest(request_id="persist", run_id=run.id))
    reopened = MVPService(SQLiteWorkspaceStorage(tmp_path / "private" / "workspaces.sqlite3"), discovery, sources)
    assert reopened.get_workspace(handle).assessments == [saved]
    assert len(discovery.calls) == 1 and len(sources.calls) == 2


def test_assessment_revision_preserves_history_and_rejects_stale_draft(workflow):
    service, handle, *_ = workflow
    search_and_prepare(service, handle)
    run = retrieve(service, handle)
    original = service.save_assessment(handle, SaveAssessmentRequest(request_id="a1", run_id=run.id))
    revision = service.save_assessment(handle, SaveAssessmentRequest(
        request_id="a2", run_id=run.id, supersedes_id=original.id,
        bundle=BundleJudgment(status="uncertain", reason="Software-only revision"),
    ))
    draft = SaveAssessmentRequest(request_id="stale", run_id=run.id, supersedes_id=original.id, feedback="Keep my draft")
    before = draft.model_dump(mode="json")
    with pytest.raises(MvpError):
        service.save_assessment(handle, draft)
    assert draft.model_dump(mode="json") == before
    history = service.get_workspace(handle).assessments
    assert history == [original, revision]
    assert revision.supersedes_id == original.id
    with pytest.raises((ValidationError, AttributeError)):
        original.feedback = "mutated"


def test_new_selection_invalidates_current_evidence_and_old_judgment(workflow):
    service, handle, *_ = workflow
    search, _ = search_and_prepare(service, handle)
    run = retrieve(service, handle)
    old = service.save_assessment(handle, SaveAssessmentRequest(request_id="old-assess", run_id=run.id))
    service.prepare_sources(handle, PrepareSourcesRequest(request_id="changed-selection", search_id=search.id, paper_ids=[search.papers[0].id]))
    state = service.get_workspace(handle)
    assert state.current_run_id is None and state.current_assessment_ids == {}
    assert state.assessments == [old] and state.runs == [run]
    with pytest.raises(MvpError):
        service.save_assessment(handle, SaveAssessmentRequest(request_id="stale-save", run_id=run.id, supersedes_id=old.id))
    fresh = retrieve(service, handle, suffix="changed")
    assert fresh.source_revision != run.source_revision
    assert fresh.source_snapshot_sha256 != run.source_snapshot_sha256
    assert all(p.paper_id == search.papers[0].id for p in fresh.passages)
    with pytest.raises(MvpError):
        service.save_assessment(handle, SaveAssessmentRequest(request_id="cross-run", run_id=fresh.id, supersedes_id=old.id))


@pytest.mark.parametrize("bundle", [
    {"status": "sufficient", "reason": ""},
    {"status": "partial", "reason": "reason"},
    {"status": "insufficient", "reason": "reason"},
    {"status": "uncertain", "reason": " "},
])
def test_assessed_bundle_requirements_are_enforced(bundle):
    with pytest.raises(ValidationError):
        BundleJudgment(**bundle)


def test_foreign_support_and_duplicate_passage_ratings_rejected(workflow):
    service, handle, *_ = workflow
    search_and_prepare(service, handle)
    run = retrieve(service, handle)
    for draft in (
        SaveAssessmentRequest(request_id="foreign-support", run_id=run.id, bundle=BundleJudgment(status="sufficient", reason="Fixture", supporting_passage_ids=["foreign"])),
        SaveAssessmentRequest(request_id="foreign-rating", run_id=run.id, passages=[PassageJudgment(passage_id="foreign")]),
        SaveAssessmentRequest(request_id="duplicate-rating", run_id=run.id, passages=[PassageJudgment(passage_id=run.passages[0].id)] * 2),
    ):
        with pytest.raises((MvpError, ValidationError)):
            service.save_assessment(handle, draft)
    assert service.get_workspace(handle).assessments == []


@pytest.mark.parametrize("payload", ["=1+1", "+SUM(1,2)", "-1+2", "@SUM(1)", "\t=HYPERLINK(\"bad\")", "\r=1"])
def test_csv_escapes_formula_like_notes_without_changing_json(workflow, payload):
    service, handle, *_ = workflow
    search_and_prepare(service, handle)
    run = retrieve(service, handle)
    service.save_assessment(handle, SaveAssessmentRequest(
        request_id="formula", run_id=run.id,
        passages=[PassageJudgment(passage_id=run.passages[0].id, notes=payload)],
    ))
    export = service.export_workspace(handle)
    rows = list(csv.DictReader(io.StringIO(export.csv_text)))
    assert rows and any("unreviewed" in row.values() for row in rows)
    cells = [cell for row in rows for cell in row.values()]
    assert payload not in cells
    assert any(cell == "'" + payload for cell in cells)
    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            for child in value:
                yield from strings(child)
        elif isinstance(value, dict):
            for child in value.values():
                yield from strings(child)
    assert payload in set(strings(json.loads(export.json_text)))


def test_unreviewed_export_preserves_source_question_and_provenance(workflow):
    service, handle, *_ = workflow
    search_and_prepare(service, handle)
    run = retrieve(service, handle)
    export = service.export_workspace(handle)
    rows = list(csv.DictReader(io.StringIO(export.csv_text)))
    assert len(rows) == len(run.passages)
    text = export.csv_text
    for value in (run.question, run.id, run.search_id, run.passages[0].source_sha256,
                  run.passages[0].anchor.quote, "abstract", "unreviewed", "bm25_context_blocks"):
        assert value in text
    assert "not_assessed" in text


def test_clear_session_invalidates_handle_and_preserves_other_workspace(workflow):
    service, handle, *_ = workflow
    other = service.create_workspace(CreateWorkspaceRequest(question="Retain other workspace"))
    assert service.clear_workspace(handle).cleared
    with pytest.raises(MvpError):
        service.get_workspace(handle)
    assert service.get_workspace(other).question == "Retain other workspace"


def test_provider_failure_is_structured_without_recording_false_search(workflow):
    service, handle, discovery, *_ = workflow
    def failed(request):
        raise ProviderFailure("provider_timeout", "Provider timeout", retryable=True)
    discovery.search = failed
    with pytest.raises(MvpError) as failure:
        service.search_literature(handle, SearchRequest(request_id="timeout", query="microbiome"))
    assert failure.value.code == "provider_timeout" and failure.value.retryable
    assert service.get_workspace(handle).searches == []


def test_services_do_not_import_streamlit_or_heavy_models():
    script = """
import sys
from src.mvp.service import MVPService
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
assert not ({'streamlit','torch','transformers','sentence_transformers','chromadb'} & set(sys.modules))
"""
    process = subprocess.run([sys.executable, "-c", script], cwd=ROOT, capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    for path in (ROOT / "src/mvp").rglob("*.py"):
        parsed = ast.parse(path.read_text())
        imports = [node.module for node in ast.walk(parsed) if isinstance(node, ast.ImportFrom)]
        imports += [alias.name for node in ast.walk(parsed) if isinstance(node, ast.Import) for alias in node.names]
        assert not any(name and (name == "streamlit" or name.startswith("streamlit.")) for name in imports), path


def test_historical_file_bindings_are_unchanged():
    for filename, count in (
        ("qwen-components-confirmation-freeze-v1.json", 75),
        ("qwen-components-development-freeze-v1.json", 72),
        ("qwen-kaggle-freeze-v2.json", 35),
    ):
        manifest = json.loads((ROOT / "docs" / filename).read_bytes())
        assert len(manifest["files"]) == count
        for relative, binding in manifest["files"].items():
            content = (ROOT / relative).read_bytes()
            assert {"sha256": sha256(content).hexdigest(), "size_bytes": len(content)} == binding, relative


def search_xml(ids=("1", "2"), total=420):
    return (f"<eSearchResult><Count>{total}</Count><RetMax>{len(ids)}</RetMax>"
            "<RetStart>0</RetStart><IdList>" + "".join(f"<Id>{value}</Id>" for value in ids)
            + "</IdList><QueryTranslation>exact translated query</QueryTranslation></eSearchResult>").encode()


def citation_xml(ids=("2", "1")):
    rows = []
    for value in ids:
        rows.append(f"""<PubmedArticle><MedlineCitation><PMID>{value}</PMID><Article>
<ArticleTitle>Synthetic software fixture {value}</ArticleTitle>
<Abstract><AbstractText>{escape(UNICODE_TEXT)}</AbstractText></Abstract>
</Article></MedlineCitation><PubmedData><ArticleIdList>
<ArticleId IdType="doi">10.1234/software.{value}</ArticleId>
</ArticleIdList></PubmedData></PubmedArticle>""")
    return ("<PubmedArticleSet>" + "".join(rows) + "</PubmedArticleSet>").encode()


class FixtureTransport:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, endpoint, params):
        self.calls.append((endpoint, params))
        result = next(self.responses)
        if isinstance(result, BaseException):
            raise result
        return result


def test_pubmed_preview_preserves_exact_query_cap_counts_order_and_dates():
    from src.mvp.adapters.pubmed import PubMedPreviewProvider
    transport = FixtureTransport(search_xml(), citation_xml())
    request = SearchRequest(request_id="software", query="  term\nexact  ", max_results=2,
                            sort="pub_date", date_from="2020-01-01", date_to="2021-12-31")
    preview = PubMedPreviewProvider("software@example.org", transport=transport).search(request)
    assert preview.query == request.query
    assert preview.query_translation == "exact translated query"
    assert preview.total_reported == 420 and preview.fetched_count == 2 and preview.truncated
    assert preview.ordered_identifiers == ["1", "2"]
    assert [p.pmid for p in preview.papers] == ["1", "2"]
    assert preview.date_from == request.date_from and preview.date_to == request.date_to
    endpoint, executed = transport.calls[0]
    assert endpoint == "pubmed_search" and executed["term"] == request.query
    assert executed["retmax"] == 2 and executed["mindate"] == "2020/01/01"
    assert transport.calls[1][1]["id"] == "1,2"
    assert "complete PubMed capture" in " ".join(preview.warnings)


def test_preview_zero_results_do_not_retry_or_relax_query():
    from src.mvp.adapters.pubmed import PubMedPreviewProvider
    transport = FixtureTransport(search_xml((), total=0))
    preview = PubMedPreviewProvider("software@example.org", transport=transport).search(SearchRequest(request_id="zero", query="exact no result"))
    assert len(transport.calls) == 1 and transport.calls[0][1]["term"] == "exact no result"
    assert preview.total_reported == preview.fetched_count == 0
    assert preview.papers == [] and preview.truncated is False


def test_dedup_uses_identifiers_preserving_conflicting_reports_and_similar_titles():
    from src.mvp.adapters.pubmed import deduplicate_papers
    same_title = paper(2).model_copy(update={"title": paper(1).title})
    shared_doi = same_title.model_copy(update={"doi": paper(1).doi})
    rows, warnings = deduplicate_papers([paper(1), paper(1), shared_doi])
    assert [row.pmid for row in rows] == ["1", "2"] and warnings
    with pytest.raises(ProviderFailure):
        deduplicate_papers([paper(1), paper(1).model_copy(update={"doi": "10.1234/conflict"})])
    rows, _ = deduplicate_papers([paper(1), same_title])
    assert len(rows) == 2


def test_pubmed_fetch_identity_failure_preserves_preview_without_false_citations():
    from src.mvp.adapters.pubmed import PubMedPreviewProvider
    transport = FixtureTransport(search_xml(), citation_xml(("1", "3")))
    result = PubMedPreviewProvider("software@example.org", transport=transport).search(SearchRequest(request_id="identity", query="exact"))
    assert result.total_reported == 420 and result.ordered_identifiers == ["1", "2"]
    assert result.fetched_count == 0 and result.papers == [] and result.errors
    assert result.errors[0].code == "identity_mismatch"


@pytest.mark.parametrize("payload", [b"<broken", b"\xff", b"<x><ERROR>private provider detail</ERROR></x>",
    b'<!DOCTYPE article [<!ENTITY x SYSTEM "file:///etc/passwd">]><article>&x;</article>'])
def test_malformed_entity_and_error_xml_rejected(payload):
    from src.mvp.adapters.transport import safe_xml
    with pytest.raises(ProviderFailure) as error:
        safe_xml(payload)
    assert "private provider detail" not in error.value.message and "/etc/passwd" not in error.value.message


class FixtureResponse:
    def __init__(self, request, payload=b"<ok/>", *, url=None, headers=None, status=200):
        self.url, self.payload = url or request.full_url, payload
        self.headers, self.status = headers or {}, status
    def geturl(self):
        return self.url
    def read(self, limit):
        return self.payload[:limit]
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


@pytest.mark.parametrize("case", ["bytes", "length", "redirect", "compressed"])
def test_transport_rejects_oversize_redirect_and_compression(case):
    from src.mvp.adapters.transport import BoundedTransport
    def opener(request, timeout):
        options = {
            "bytes": {"payload": b"123456789"},
            "length": {"headers": {"Content-Length": "100"}},
            "redirect": {"url": "https://untrusted.invalid/data"},
            "compressed": {"headers": {"Content-Encoding": "gzip"}},
        }[case]
        return FixtureResponse(request, **options)
    transport = BoundedTransport(opener=opener, max_response_bytes=8, sleep=lambda _: None)
    with pytest.raises(ProviderFailure):
        transport.request("pubmed_search", {"term": "software"})


def test_transport_timeout_bounded_attempts_and_error_redaction():
    from src.mvp.adapters.transport import BoundedTransport
    calls = []
    def opener(request, timeout):
        calls.append(timeout)
        raise TimeoutError("secret-key-should-never-leak")
    transport = BoundedTransport(opener=opener, timeout=0.2, max_attempts=2, sleep=lambda _: None)
    with pytest.raises(ProviderFailure) as error:
        transport.request("pubmed_search", {"api_key": "secret-key-should-never-leak"})
    assert calls == [0.2, 0.2] and error.value.retryable
    assert "secret-key-should-never-leak" not in str(error.value)


def test_http_rate_limit_retry_after_is_honored_or_returns_retryable_failure():
    from src.mvp.adapters.transport import BoundedTransport
    calls, sleeps = [], []
    def opener(request, timeout):
        calls.append(request)
        if len(calls) == 1:
            raise HTTPError(request.full_url, 429, "secret-provider-message", {"Retry-After": "2"}, None)
        return FixtureResponse(request)
    transport = BoundedTransport(opener=opener, sleep=sleeps.append)
    try:
        assert transport.request("pubmed_search", {"term": "software"}) == b"<ok/>"
    except ProviderFailure as error:
        assert error.retryable and len(calls) == 1
    else:
        assert len(calls) == 2 and any(duration >= 2 for duration in sleeps)


def test_provider_gate_is_shared_across_transport_instances(monkeypatch):
    from src.mvp.adapters import transport as module
    monkeypatch.setattr(module, "_HOST_LAST", {})
    current, sleeps = [0.0], []
    def sleep(duration):
        sleeps.append(duration)
        current[0] += duration
    def opener(request, timeout):
        return FixtureResponse(request)
    first = module.BoundedTransport(opener=opener, sleep=sleep, monotonic=lambda: current[0])
    second = module.BoundedTransport(opener=opener, sleep=sleep, monotonic=lambda: current[0])
    first.request("pubmed_search", {"term": "one"})
    second.request("pubmed_search", {"term": "two"})
    assert sleeps and sum(sleeps) >= 0.4


@pytest.mark.parametrize("endpoint,params", [
    ("https://untrusted.invalid/", {}),
    ("europe_fulltext", {"pmcid": "PMC1/../../private"}),
    ("europe_fulltext", {"pmcid": "PMC1", "url": "https://untrusted.invalid"}),
])
def test_transport_never_fetches_arbitrary_urls(endpoint, params):
    from src.mvp.adapters.transport import BoundedTransport
    def opener(*args, **kwargs):
        pytest.fail("Invalid endpoint reached transport")
    with pytest.raises(ProviderFailure):
        BoundedTransport(opener=opener).request(endpoint, params)


def test_search_and_selection_caps_are_validated_before_provider_calls():
    for value in (0, 51):
        with pytest.raises(ValidationError):
            SearchRequest(request_id="bound", query="software", max_results=value)
    with pytest.raises(ValidationError):
        PrepareSourcesRequest(request_id="bound", search_id="x", paper_ids=[str(i) for i in range(11)])


def europe_metadata(**changes):
    return {"id": "1", "source": "MED", "pmid": "1", "doi": "10.1234/software.1",
            "pmcid": "PMC1", "isOpenAccess": "Y", "license": "CC BY", **changes}


def europe_json(*rows):
    return json.dumps({"resultList": {"result": list(rows)}}).encode()


def fulltext_xml(*, pmid="1", doi="10.1234/software.1", pmcid="PMC1", body=True,
                 license_url="https://creativecommons.org/licenses/by/4.0/"):
    return (f"""<article xmlns:xlink="http://www.w3.org/1999/xlink"><front><article-meta>
<article-id pub-id-type="pmid">{pmid}</article-id><article-id pub-id-type="doi">{doi}</article-id>
<article-id pub-id-type="pmcid">{pmcid}</article-id><title-group><article-title>Synthetic software fixture</article-title></title-group>
<permissions><copyright-statement>Software fixture</copyright-statement><license>
<ext-link xlink:href="{license_url}"/></license></permissions></article-meta></front>"""
            + (f"<body><sec><title>Software result</title><p>{escape(UNICODE_TEXT)}</p></sec></body>" if body else "")
            + "<back><ref-list><ref><pub-id pub-id-type=\"pmid\">999</pub-id></ref></ref-list></back></article>").encode()


def test_permitted_fulltext_retains_exact_source_bytes_license_and_own_identity():
    from src.mvp.adapters.europe_pmc import EuropePmcSourceProvider
    original = b"\xef\xbb\xbf" + fulltext_xml()
    transport = FixtureTransport(europe_json(europe_metadata()), original)
    source = EuropePmcSourceProvider(transport=transport).prepare(paper(1))
    assert source.status == "full_text_retrieved" and source.source_type == "full_text"
    assert source.retained_content_utf8.encode("utf-8") == original
    assert source.source_sha256 == sha256(original).hexdigest() == source.version
    assert source.blocks_sha256 == digest([block.model_dump(mode="json") for block in source.blocks])
    assert source.source_identifiers == {"pmid": "1", "doi": "10.1234/software.1", "pmcid": "PMC1"}
    assert source.license == "https://creativecommons.org/licenses/by/4.0/"
    assert source.attribution and source.parser_id and source.retrieved_at
    assert transport.calls[1] == ("europe_fulltext", {"pmcid": "PMC1"})
    assert any("Software result" == block.locator.get("section_title") for block in source.blocks)


@pytest.mark.parametrize("identifiers", [
    {"pmid": "2"}, {"doi": "10.1234/other"}, {"pmcid": "PMC2"},
])
def test_wrong_fulltext_identity_is_discarded_despite_matching_reference(identifiers):
    from src.mvp.adapters.europe_pmc import EuropePmcSourceProvider
    source = EuropePmcSourceProvider(transport=FixtureTransport(
        europe_json(europe_metadata()), fulltext_xml(**identifiers).replace(b">999<", b">1<"),
    )).prepare(paper(1))
    assert source.status == "identity_mismatch" and source.source_type == "abstract"
    assert source.retained_content_utf8 is None
    assert source.blocks[0].text == paper(1).abstract
    assert source.error and source.error.code == "identity_mismatch"


@pytest.mark.parametrize("metadata,xml,expected_calls", [
    (europe_metadata(license=None), fulltext_xml(), 1),
    (europe_metadata(isOpenAccess="N"), fulltext_xml(), 1),
    (europe_metadata(license="CC BY-NC"), fulltext_xml(), 1),
    (europe_metadata(), fulltext_xml(license_url="https://creativecommons.org/licenses/by-nc/4.0/"), 2),
], ids=["missing-license", "not-open-access", "restricted-metadata", "restricted-xml"])
def test_unresolved_or_restricted_reuse_keeps_abstract_without_retaining_xml(metadata, xml, expected_calls):
    from src.mvp.adapters.europe_pmc import EuropePmcSourceProvider
    transport = FixtureTransport(europe_json(metadata), xml)
    source = EuropePmcSourceProvider(transport=transport).prepare(paper(1))
    assert source.status == "permission_unresolved" and source.source_type == "abstract"
    assert source.retained_content_utf8 is None and source.blocks[0].text == UNICODE_TEXT
    assert len(transport.calls) == expected_calls and source.warnings


def test_empty_fulltext_body_uses_explicit_abstract_status_and_no_text_is_distinct():
    from src.mvp.adapters.europe_pmc import EuropePmcSourceProvider
    provider = EuropePmcSourceProvider(transport=FixtureTransport(europe_json(europe_metadata()), fulltext_xml(body=False)))
    abstract = provider.prepare(paper(1))
    assert abstract.source_type == "abstract" and abstract.status == "abstract_only"
    assert abstract.retained_content_utf8 is None and abstract.error.code == "no_usable_text"
    no_abstract = paper(1).model_copy(update={"abstract": ""})
    missing = EuropePmcSourceProvider(transport=FixtureTransport(europe_json())).prepare(no_abstract)
    assert missing.status == "no_usable_text" and missing.source_type == "none" and missing.blocks == []


@pytest.mark.parametrize("response", [
    ProviderFailure("timeout", "Bounded provider timeout", True),
    ProviderFailure("http_error", "Provider HTTP failure", True),
    b"<article><broken>",
    b'<!DOCTYPE article [<!ENTITY x SYSTEM "file:///etc/passwd">]><article>&x;</article>',
])
def test_fulltext_failures_preserve_honest_abstract_fallback(response):
    from src.mvp.adapters.europe_pmc import EuropePmcSourceProvider
    source = EuropePmcSourceProvider(transport=FixtureTransport(europe_json(europe_metadata()), response)).prepare(paper(1))
    assert source.status == "fetch_failed" and source.source_type == "abstract"
    assert source.blocks[0].text == UNICODE_TEXT and source.retained_content_utf8 is None
    assert source.error and source.warnings


def test_one_paper_failure_does_not_lose_successful_preparation(workflow):
    service, handle, discovery, sources, _ = workflow
    real_prepare = sources.prepare
    def partial(record):
        if record.pmid == "2":
            raise ProviderFailure("timeout", "Source request timed out", True)
        return real_prepare(record)
    sources.prepare = partial
    _, prepared = search_and_prepare(service, handle)
    assert len(prepared.sources) == 2 and len(prepared.errors) == 1
    assert prepared.sources[0].status == "abstract_only"
    assert prepared.sources[1].status == "fetch_failed" and prepared.sources[1].source_type == "abstract"
    assert prepared.errors[0].paper_id == discovery.papers[1].id
    run = retrieve(service, handle)
    assert len(run.passages) == 2


def test_streamlit_saved_example_workflow_reruns_do_not_repeat_or_lose_assessment(tmp_path, monkeypatch):
    """Actual screens with a real saved source; no listening server is needed."""
    pytest.importorskip("streamlit.testing.v1", reason="UI smoke needs focused MVP dependencies")
    from streamlit.testing.v1 import AppTest
    import src.mvp.bootstrap as bootstrap
    from src.mvp.adapters.saved_examples import SavedExampleProvider
    from src.mvp.adapters.storage import SQLiteWorkspaceStorage
    from src.mvp.service import MVPService

    class CountedExample:
        def __init__(self):
            self.provider = SavedExampleProvider()
            self.searches = self.preparations = 0
        def search(self, request):
            self.searches += 1
            return self.provider.search(request)
        def prepare(self, record):
            self.preparations += 1
            return self.provider.prepare(record)

    example = CountedExample()
    service = MVPService(SQLiteWorkspaceStorage(tmp_path / "ui.sqlite3"), example, example)
    monkeypatch.setenv("MVP_MODE", "saved_example")
    monkeypatch.setenv("MVP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(bootstrap, "build_service", lambda **kwargs: service)
    app = AppTest.from_file(str(ROOT / "apps/streamlit/app.py"), default_timeout=20).run()

    def widget(group, label):
        matches = [item for item in getattr(app, group) if item.label == label]
        assert len(matches) == 1, (group, label, [item.label for item in getattr(app, group)])
        return matches[0]

    assert not app.exception
    widget("button", "Search literature").click().run()
    assert not app.exception and example.searches == 1
    handle = WorkspaceHandle.model_validate(app.session_state["workspace_handle"])
    search = service.get_workspace(handle).searches[-1]
    assert search.mode == "saved_example" and search.papers
    widget("radio", "Workflow").set_value("Prepare sources").run()
    widget("multiselect", "Papers for exploration (maximum 10)").set_value([search.papers[0].id])
    widget("button", "Prepare selected papers").click().run()
    assert not app.exception and example.preparations == 1
    widget("radio", "Workflow").set_value("Evidence & export").run()
    widget("text_area", "Question for selected sources").set_value("microbiome")
    widget("button", "Search passages").click().run()
    assert not app.exception
    run = service.get_workspace(handle).runs[-1]
    assert run.passages
    notes = [item for item in app.text_area if item.label == "Notes"]
    notes[0].set_value("Saved UI smoke note")
    widget("button", "Save assessment").click().run()
    assert not app.exception and not app.error
    saved = service.get_workspace(handle).assessments[-1]
    assert saved.passages[0].notes == "Saved UI smoke note"
    for _ in range(2):
        app.run()
        assert not app.exception
    widget("radio", "Workflow").set_value("Discover").run()
    widget("radio", "Workflow").set_value("Evidence & export").run()
    state = service.get_workspace(handle)
    assert example.searches == example.preparations == 1
    assert len(state.searches) == len(state.preparations) == len(state.runs) == len(state.assessments) == 1
    assert state.assessments == [saved]
    assert len(app.get("download_button")) == 2

    # An edit after submission needs the explicit revision action; drafts survive
    # a rejected submission, including a revision made stale by another tab.
    [item for item in app.text_area if item.label == "Notes"][0].set_value("Unsaved correction draft")
    widget("button", "Save assessment").click().run()
    assert app.error and not app.exception
    assert service.get_workspace(handle).assessments == [saved]
    assert [item for item in app.text_area if item.label == "Notes"][0].value == "Unsaved correction draft"
    widget("button", "Revise saved assessment").click().run()
    concurrent_revision = service.save_assessment(handle, SaveAssessmentRequest(
        request_id="other-tab-revision", run_id=run.id, supersedes_id=saved.id,
        feedback="Software simulation of another tab",
    ))
    [item for item in app.text_area if item.label == "Notes"][0].set_value("Keep this stale revision draft")
    widget("button", "Save assessment").click().run()
    assert app.error and not app.exception
    assert [item for item in app.text_area if item.label == "Notes"][0].value == "Keep this stale revision draft"
    assert service.get_workspace(handle).assessments == [saved, concurrent_revision]
    assert example.searches == example.preparations == 1


def test_ui_citations_remain_bound_to_preparation_and_run_search(tmp_path, monkeypatch):
    """A later search's metadata must not rewrite an earlier source citation."""
    pytest.importorskip("streamlit.testing.v1", reason="UI smoke needs focused MVP dependencies")
    from streamlit.testing.v1 import AppTest
    import src.mvp.bootstrap as bootstrap
    from src.mvp.adapters.saved_examples import SavedExampleProvider
    from src.mvp.adapters.storage import SQLiteWorkspaceStorage
    from src.mvp.service import MVPService

    class ChangedMetadataExample:
        changed = False
        def __init__(self):
            self.provider = SavedExampleProvider()
        def search(self, request):
            result = self.provider.search(request)
            if self.changed:
                # Deliberate, conflicting software-test metadata. It is never
                # written into the saved example or presented as a publication.
                result = result.model_copy(update={"papers": [record.model_copy(update={
                    "title": "Synthetic conflicting metadata from later search B",
                    "authors": ["Synthetic changed author B"],
                }) for record in result.papers]})
            return result
        def prepare(self, record):
            return self.provider.prepare(record)

    example = ChangedMetadataExample()
    service = MVPService(SQLiteWorkspaceStorage(tmp_path / "citations.sqlite3"), example, example)
    handle = service.create_workspace(CreateWorkspaceRequest(question="microbiome"))
    search_a = service.search_literature(handle, SearchRequest(request_id="search-a", query="saved example"))
    original = search_a.papers[0]
    service.prepare_sources(handle, PrepareSourcesRequest(request_id="prepare-a", search_id=search_a.id, paper_ids=[original.id]))
    run = retrieve(service, handle, question="microbiome")
    assert run.passages and run.search_id == search_a.id

    monkeypatch.setenv("MVP_MODE", "saved_example")
    monkeypatch.setattr(bootstrap, "build_service", lambda **kwargs: service)
    app = AppTest.from_file(str(ROOT / "apps/streamlit/app.py"), default_timeout=20)
    app.session_state["workspace_handle"] = handle.model_dump(mode="json")
    app.session_state["screen"] = "Evidence & export"
    app.run()
    assert not app.exception

    example.changed = True
    search_b = service.search_literature(handle, SearchRequest(request_id="search-b", query="later software metadata"))
    changed = search_b.papers[0]
    assert changed.pmid == original.pmid and changed.title != original.title
    assert service.get_workspace(handle).current_run_id == run.id
    app.run()
    assert not app.exception
    text_values = [item.value for item in app.text]
    assert changed.title not in text_values
    assert text_values.count(original.title) >= len(run.passages) + 1  # passage cards and inspected source
    authors = ", ".join(original.authors[:4])
    captions = [item.value for item in app.caption]
    assert sum(authors in value for value in captions) >= len(run.passages) + 1
    assert not any(changed.authors[0] in value for value in captions)

    rows = list(csv.DictReader(io.StringIO(service.export_workspace(handle).csv_text)))
    assert rows and all(row["title"] == original.title and row["search_id"] == search_a.id for row in rows)
    assert all(changed.authors[0] not in row["citation"] for row in rows)
    assert service.get_source_context(handle, SourceContextRequest(run_id=run.id, passage_id=run.passages[0].id)).paper == original

    [item for item in app.radio if item.label == "Workflow"][0].set_value("Prepare sources").run()
    assert not app.exception
    assert original.title in [item.value for item in app.text]
    assert changed.title not in [item.value for item in app.text]
    assert not any(changed.authors[0] in item.value for item in app.caption)
