"""Independent case audits use synthetic records; no research execution occurs.

These tests establish reporting and provenance behavior, not relevance, live
provider execution, real embedding execution, or usefulness of a research case.
"""
import json
import hashlib
import socket

import pytest
from pydantic import ValidationError

from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.contracts import (
    Block, CreateWorkspaceRequest, Paper, PrepareSourcesRequest,
    PreparedSource, QuerySuggestion, SearchPreview, SearchRequest, StructuredError,
    digest,
)
from src.mvp.mapping import (
    EmbeddedPaper, EmbeddingProfile, ExcludedPaper, MapView, build_artifact, counts, representations,
)
from src.mvp.ports import MvpError
from src.mvp.research_case import (
    KnownPaper, QueryApproval, ResearchCaseProtocol, audit_saved_case,
    known_paper_recovery, query_sha256, readiness_manifest,
    require_live_preconditions, write_private_manifest,
)
from src.mvp.service import MVPService


QUERY = '"SYNTHETIC AUDIT QUERY"[Title/Abstract]'
QUESTION = "Synthetic reporting question; not a scientific research result"
SECRET_ABSTRACT = "PRIVATE_ABSTRACT_SENTINEL_4a47"
SECRET_SOURCE = "PRIVATE_CANONICAL_SOURCE_SENTINEL_e7bd"
SECRET_ERROR = "PRIVATE_PROVIDER_ERROR_SENTINEL_7ecc"


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Case audit attempted network access")
    monkeypatch.setattr(socket, "create_connection", denied)


class Discovery:
    def __init__(self):
        self.calls = 0
        self.papers = [Paper(title=f"SYNTHETIC audit report {index}", pmid=str(index),
                            abstract=SECRET_ABSTRACT + str(index)) for index in range(1, 6)]

    def search(self, request):
        self.calls += 1
        return SearchPreview(query=request.query, research_question=QUESTION,
            query_translation="SYNTHETIC PROVIDER TRANSLATION", papers=self.papers,
            total_reported=123, fetched_count=5, ordered_identifiers=[str(i) for i in range(1, 6)],
            truncated=True, mode="test", provider="synthetic-software-fixture")


class Sources:
    def __init__(self):
        self.calls = 0

    def prepare(self, paper):
        self.calls += 1
        status, kind = {
            "1": ("full_text_retrieved", "full_text"),
            "2": ("abstract_only", "abstract"),
            "3": ("no_usable_text", "none"),
            "4": ("permission_unresolved", "abstract"),
            "5": ("fetch_failed", "none"),
        }[paper.pmid]
        blocks = [] if kind == "none" else [Block(id="synthetic:1", ordinal=1,
                    text=SECRET_SOURCE + paper.pmid + " 😀 e\u0301", locator={"type": "software-fixture"})]
        return PreparedSource(paper_id=paper.id, status=status, source_type=kind,
            provider="synthetic-software-fixture", source_url="https://example.invalid/synthetic/" + paper.pmid,
            blocks=blocks, source_identifiers={"pmid": paper.pmid},
            blocks_sha256=digest([block.model_dump(mode="json") for block in blocks]),
            source_sha256=digest([block.model_dump(mode="json") for block in blocks]) if blocks else "",
            license="SYNTHETIC SOFTWARE LICENSE LABEL" if kind == "full_text" else None,
            error=StructuredError(code="synthetic_fetch_failure", message=SECRET_ERROR) if paper.pmid == "5" else None)


def case(tmp_path):
    discovery, sources = Discovery(), Sources()
    engine = MVPService(SQLiteWorkspaceStorage(tmp_path / "private.sqlite3"), discovery, sources)
    handle = engine.create_workspace(CreateWorkspaceRequest(question=QUESTION))
    search = engine.search_literature(handle, SearchRequest(request_id="synthetic-search", query=QUERY,
                                                          research_question=QUESTION, max_results=30))
    selected = [paper.id for paper in search.papers]
    preparation = engine.prepare_sources(handle, PrepareSourcesRequest(request_id="synthetic-prepare",
                                      search_id=search.id, paper_ids=selected))
    protocol = ResearchCaseProtocol(case_id="synthetic-case", question=QUESTION,
                                    exact_query=QUERY, selected_paper_ids=selected)
    discovery.calls, sources.calls = 0, 0
    return engine, handle, search, preparation, protocol, discovery, sources


def test_saved_case_audit_preserves_missing_outcomes_and_cannot_become_live(tmp_path):
    engine, handle, search, prep, protocol, discovery, sources = case(tmp_path)
    before = engine.get_workspace(handle).model_dump(mode="json")
    result = audit_saved_case(engine, handle, protocol, search_id=search.id,
                              preparation_id=prep.id, environment={})
    assert result["provider_execution"]["status"] == "SOFTWARE_FIXTURE_ONLY"
    assert result["provider_execution"]["executed_by_this_command"] is False
    assert result["provider_execution"]["live_execution_this_command"] == "LIVE_NOT_RUN"
    assert result["model_execution"]["status"] == "MODEL_NOT_RUN"
    assert result["human_usefulness"] == "NOT_RUN"
    assert result["scientific_quality"] == "NOT_ASSESSED"
    assert result["search"]["provider_reported_count"] == 123
    assert result["search"]["fetched_count"] == result["search"]["distinct_record_count"] == 5
    assert result["search"]["actual_20_to_50_metadata_target_met"] is False
    assert [row["paper_id"] for row in result["sources"]["outcomes"]] == protocol.selected_paper_ids
    assert [row["status"] for row in result["sources"]["outcomes"]] == [source.status for source in prep.sources]
    assert result["sources"]["outcome_counts_by_retained_type"] == {"full_text": 1, "abstract": 2, "none": 2}
    assert result["sources"]["unobserved_outcome_classes"] == []
    for original, outcome in zip(prep.sources, result["sources"]["outcomes"]):
        assert outcome["canonical_blocks_hash_check"] == "PASS"
        assert outcome["retained_original_bytes_hash_check"] == ("NOT_APPLICABLE" if original.source_type == "none" else "NOT_RETAINED")
        assert len(outcome["canonical_block_inspection"]) == len(original.blocks)
        for block, inspection in zip(original.blocks, outcome["canonical_block_inspection"]):
            assert inspection["block_id"] == block.id
            assert inspection["unicode_code_point_range"] == [0, len(block.text)]
            assert inspection["text_sha256"] == hashlib.sha256(block.text.encode("utf-8")).hexdigest()
    assert discovery.calls == sources.calls == 0
    assert engine.get_workspace(handle).model_dump(mode="json") == before


def test_manifest_omits_private_content_capability_error_and_configuration_values(tmp_path):
    engine, handle, search, prep, protocol, *_ = case(tmp_path)
    environment = {"NCBI_EMAIL": "PRIVATE_CONTACT_SENTINEL@example.invalid", "NCBI_API_KEY": "PRIVATE_KEY_SENTINEL"}
    report = audit_saved_case(engine, handle, protocol, search_id=search.id,
                              preparation_id=prep.id, environment=environment)
    serialized = json.dumps(report)
    for secret in (SECRET_ABSTRACT, SECRET_SOURCE, SECRET_ERROR, handle.token, *environment.values()):
        assert secret not in serialized
    assert report["configuration"] == {"ncbi_email_present": True, "ncbi_email_valid_format": True,
                                         "ncbi_api_key_present": True}
    assert report["publication"]["status"] == "NOT_REVIEWED_DO_NOT_PUBLISH"
    assert report["publication"]["abstracts_in_manifest"] is False
    assert report["publication"]["source_text_in_manifest"] is False


def test_historical_case_keeps_original_bibliography_after_same_report_metadata_changes(tmp_path):
    engine, handle, search, prep, protocol, discovery, sources = case(tmp_path)
    original_hashes = {paper.id: digest(paper.model_dump(mode="json")) for paper in search.papers}
    discovery.papers = [paper.model_copy(update={"title": "CHANGED LATER METADATA",
                                                 "abstract": "CHANGED LATER ABSTRACT"}) for paper in discovery.papers]
    later_search = engine.search_literature(handle, SearchRequest(request_id="later-search", query=QUERY,
                                                                 research_question=QUESTION, max_results=30))
    later_prep = engine.prepare_sources(handle, PrepareSourcesRequest(request_id="later-preparation",
                                        search_id=later_search.id, paper_ids=protocol.selected_paper_ids))
    discovery.calls, sources.calls = 0, 0
    report = audit_saved_case(engine, handle, protocol, search_id=search.id,
                              preparation_id=prep.id, environment={})
    assert report["search"]["id"] == search.id
    assert report["search"]["input_hashes"] == original_hashes
    assert report["sources"]["is_current_preparation"] is False
    assert report["sources"]["source_revision"] == prep.source_revision < later_prep.source_revision
    assert [row["source_id"] for row in report["sources"]["outcomes"]] == [source.id for source in prep.sources]
    assert discovery.calls == sources.calls == 0


@pytest.mark.parametrize("changed", [
    {"exact_query": QUERY + " "}, {"question": QUESTION + " changed"},
    {"sort": "pub_date"}, {"date_from": "2020-01-01", "date_to": "2024-12-31"},
])
def test_saved_search_must_match_exact_original_protocol(tmp_path, changed):
    engine, handle, search, _, protocol, *_ = case(tmp_path)
    protocol = ResearchCaseProtocol.model_validate({**protocol.model_dump(), **changed})
    with pytest.raises(MvpError) as failure:
        audit_saved_case(engine, handle, protocol, search_id=search.id, environment={})
    assert failure.value.code == "case_protocol_mismatch"


def test_cap_selection_preparation_and_source_hash_tampering_are_rejected(tmp_path):
    engine, handle, search, prep, protocol, *_ = case(tmp_path)
    with pytest.raises(MvpError) as failure:
        audit_saved_case(engine, handle, protocol.model_copy(update={"max_results": 4}), search_id=search.id)
    assert failure.value.code == "case_cap_mismatch"
    reverse = protocol.model_copy(update={"selected_paper_ids": list(reversed(protocol.selected_paper_ids))})
    with pytest.raises(MvpError) as failure:
        audit_saved_case(engine, handle, reverse, search_id=search.id, preparation_id=prep.id)
    assert failure.value.code == "case_selection_mismatch"
    state = engine.get_workspace(handle)
    class SnapshotService:
        def get_workspace(self, ignored): return state
        def suggest_query(self, *args): return QuerySuggestion(query=QUERY, explanation="Software fixture")
    bad_block = prep.sources[0].blocks[0].model_copy(update={"text": "tampered"})
    bad_source = prep.sources[0].model_copy(update={"blocks": [bad_block]})
    state.preparations[0] = prep.model_copy(update={"sources": [bad_source, *prep.sources[1:]]})
    with pytest.raises(MvpError) as failure:
        audit_saved_case(SnapshotService(), handle, protocol, search_id=search.id, preparation_id=prep.id)
    assert failure.value.code == "source_integrity_error"


def test_only_approved_held_out_papers_contribute_to_recovery_denominator(tmp_path):
    _, _, search, _, protocol, *_ = case(tmp_path)
    protocol = protocol.model_copy(update={"known_papers": [
        KnownPaper(paper_id="pmid:1", reference_url="https://example.invalid/1", role="held_out",
                   relevance_status="reviewer_approved", reviewer_rationale="Synthetic approval fixture"),
        KnownPaper(paper_id="pmid:9", reference_url="https://example.invalid/9", role="held_out",
                   relevance_status="reviewer_approved", reviewer_rationale="Synthetic missing fixture"),
        KnownPaper(paper_id="pmid:2", reference_url="https://example.invalid/2", role="candidate",
                   relevance_status="reviewer_approved", reviewer_rationale="Candidate remains unscored"),
        KnownPaper(paper_id="pmid:3", reference_url="https://example.invalid/3", role="held_out"),
    ]})
    report = known_paper_recovery(protocol, search)
    assert report["reviewer_approved_held_out_denominator"] == 2
    assert report["recovered_count"] == 1 and report["fraction"] == .5
    assert report["recovered_ids"] == ["pmid:1"]
    assert report["not_in_capped_preview_ids"] == ["pmid:9"]
    assert report["candidate_ids_not_scored"] == ["pmid:2", "pmid:3"]
    assert "not recall" in report["interpretation"]
    empty = known_paper_recovery(protocol.model_copy(update={"known_papers": []}), search)
    assert empty["reviewer_approved_held_out_denominator"] == 0 and empty["fraction"] is None


def test_live_guard_requires_each_explicit_prerequisite_without_execution():
    protocol = ResearchCaseProtocol(case_id="test-guard", question=QUESTION, exact_query=QUERY)
    for allow, env, code in [(False, {}, "live_opt_in_required"),
                             (True, {}, "query_approval_required")]:
        with pytest.raises(MvpError) as failure:
            require_live_preconditions(protocol, allow_live=allow, environment=env)
        assert failure.value.code == code
    approved = protocol.model_copy(update={"query_approval": QueryApproval(status="approved",
                exact_query_sha256=query_sha256(QUERY), recorded_at="2026-10-21T00:00:00Z",
                evidence_note="Synthetic test approval; no real live authorization")})
    for environment in ({}, {"NCBI_EMAIL": "invalid"}):
        with pytest.raises(MvpError) as failure:
            require_live_preconditions(approved, allow_live=True, environment=environment)
        assert failure.value.code == "live_not_configured"
    assert require_live_preconditions(approved, allow_live=True,
                                      environment={"NCBI_EMAIL": "test@example.invalid"}) is None
    assert readiness_manifest(approved, {"NCBI_EMAIL": "test@example.invalid"})["provider_execution"]["status"] == "LIVE_NOT_RUN"


def test_changed_query_cannot_reuse_original_approval():
    raw = dict(case_id="approval-binding", question=QUESTION, exact_query=QUERY + " ",
               query_approval=dict(status="approved", exact_query_sha256=query_sha256(QUERY),
                                   recorded_at="2026-10-21T00:00:00Z", evidence_note="Synthetic approval"))
    with pytest.raises(ValidationError, match="Approval does not match"):
        ResearchCaseProtocol.model_validate(raw)


def test_audit_reopens_persisted_map_twice_without_computing_and_rejects_wrong_binding(tmp_path):
    engine, handle, search, _, protocol, *_ = case(tmp_path)
    profile = EmbeddingProfile(model="SYNTHETIC/software-vector", model_revision="test-v1",
                               tokenizer_revision="test-v1", dimension=3)
    representations_ = representations(search)
    row = representations_[0]
    vectors = [EmbeddedPaper(paper_id=row.paper_id, input_sha256=row.input_sha256,
                representation=row.representation, vector=[1., 0., 0.],
                window_token_weights=[3], token_count=3)]
    excluded = [ExcludedPaper(paper_id=other.paper_id, code="synthetic_exclusion",
                              reason="Software fixture omission; no model executed") for other in representations_[1:]]
    artifact, _ = build_artifact(handle.workspace_id, search, profile, vectors, excluded, "synthetic-map")
    view = MapView(artifact=artifact, counts=counts(search, artifact))
    class SavedMap:
        calls = 0
        def vectors(self, workspace_id, map_id):
            assert workspace_id == handle.workspace_id and map_id == artifact.map_id
            return {item.paper_id: item.vector for item in vectors}
        def embedding(self, workspace_id, actual_profile, representation):
            assert workspace_id == handle.workspace_id and actual_profile == profile
            return next((item for item in vectors if item.paper_id == representation.paper_id), None)
        def map(self, workspace_id, map_id):
            self.calls += 1
            assert workspace_id == handle.workspace_id and map_id == artifact.map_id
            return view.model_copy(deep=True)
    store = SavedMap()
    report = audit_saved_case(engine, handle, protocol, search_id=search.id,
                              map_store=store, map_id=artifact.map_id, environment={})
    assert store.calls == 2
    assert report["map"]["reopen_without_refit"] == "PASS"
    assert report["model_execution"]["executed_by_this_command"] is False
    assert report["model_execution"]["real_model_execution_this_command"] == "MODEL_NOT_RUN"
    assert report["map"]["semantic_layout_quality"] == "NOT_ASSESSED"
    artifact = artifact.model_copy(update={"search_snapshot_sha256": "0" * 64})
    view = view.model_copy(update={"artifact": artifact})
    with pytest.raises(MvpError) as failure:
        audit_saved_case(engine, handle, protocol, search_id=search.id,
                         map_store=store, map_id=artifact.map_id, environment={})
    assert failure.value.code == "case_map_mismatch"


def test_private_manifest_is_exclusive_and_rejects_symlink_paths(tmp_path):
    protocol = ResearchCaseProtocol(case_id="private-write", question=QUESTION, exact_query=QUERY)
    report = readiness_manifest(protocol, {})
    output = tmp_path / "new-audit"
    path = write_private_manifest(output, report)
    assert output.stat().st_mode & 0o777 == 0o700
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text()) == report
    with pytest.raises(ValueError, match="new case-audit"):
        write_private_manifest(output, report)
    linked = tmp_path / "symlink-parent"
    linked.symlink_to(output, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        write_private_manifest(linked / "escaped", report)
    assert not (output / "escaped").exists()
