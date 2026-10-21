"""C0 software fixtures only: no real reports, provider calls or model weights."""
import json
from pathlib import Path
import stat

import pytest
from pydantic import ValidationError

from src.mvp.adapters.map_storage import MapStore
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.contracts import (Block, CreateWorkspaceRequest, Paper, PreparationResult,
    PrepareSourcesRequest, PreparedSource, SearchPreview, SearchRequest, digest)
from src.mvp.mapping import (CreateMapRequest, EmbeddedPaper, EmbeddingProfile,
    ExcludedPaper, build_artifact, counts, representations)
from src.mvp.ports import MvpError
from src.mvp.research_case import (KnownPaper, QueryApproval, ResearchCaseProtocol,
    audit_saved_case, configuration_status, known_paper_recovery, query_sha256,
    readiness_manifest, require_live_preconditions, write_private_manifest)
from src.mvp.service import MVPService


class FixtureDiscovery:
    calls = 0
    def search(self, request):
        self.calls += 1
        papers = [Paper(id=f"fixture:report-{index}", title=f"SOFTWARE FIXTURE {index}",
            abstract=f"Private synthetic abstract microbiome {index}.") for index in range(24)]
        return SearchPreview(query=request.query, sort=request.sort, date_from=request.date_from,
            date_to=request.date_to, query_translation="SOFTWARE FIXTURE translation",
            total_reported=87, fetched_count=24, ordered_identifiers=[paper.id for paper in papers],
            papers=papers, truncated=True, provider="software-fixture", mode="test")


class FixtureSources:
    calls = 0
    def prepare(self, paper):
        self.calls += 1
        index = int(paper.id.rsplit("-", 1)[1])
        kind = ("full_text", "abstract", "none")[index % 3]
        blocks = [] if kind == "none" else [Block(id="block-1", ordinal=1,
            text=f"Private synthetic source 😀 microbiome {index}.", locator={"type": "software_fixture"})]
        return PreparedSource(paper_id=paper.id, source_type=kind,
            status={"full_text": "full_text_retrieved", "abstract": "abstract_only", "none": "no_usable_text"}[kind],
            provider="software-fixture", source_url="https://example.invalid/fixture",
            license="CC0 synthetic software fixture" if kind == "full_text" else None,
            blocks=blocks, warnings=["Synthetic unavailable fixture"] if kind == "none" else [])


def setup_case(tmp_path):
    discovery, sources = FixtureDiscovery(), FixtureSources()
    service = MVPService(SQLiteWorkspaceStorage(tmp_path / "workspaces.sqlite3"), discovery, sources)
    protocol = ResearchCaseProtocol(case_id="software-fixture", question="SYNTHETIC microbiome question",
        exact_query="EXACT SOFTWARE FIXTURE QUERY", selected_paper_ids=[f"fixture:report-{index}" for index in range(6)])
    handle = service.create_workspace(CreateWorkspaceRequest(question=protocol.question))
    search = service.search_literature(handle, SearchRequest(request_id="fixture-search",
        query=protocol.exact_query, research_question=protocol.question))
    preparation = service.prepare_sources(handle, PrepareSourcesRequest(request_id="fixture-prepare",
        search_id=search.id, paper_ids=protocol.selected_paper_ids))
    return service, handle, protocol, search, preparation, discovery, sources


def test_saved_case_integrity_is_separate_from_live_model_and_human_evidence(tmp_path):
    service, handle, protocol, search, preparation, discovery, sources = setup_case(tmp_path)
    result = audit_saved_case(service, handle, protocol, search_id=search.id,
        preparation_id=preparation.id, environment={})
    assert discovery.calls == 1 and sources.calls == 6
    assert result["search"]["distinct_record_count"] == 24
    assert result["search"]["provider_reported_count"] == 87
    assert result["search"]["query_translation"] == "SOFTWARE FIXTURE translation"
    assert result["search"]["actual_20_to_50_metadata_target_met"] is True
    assert result["sources"]["selected_paper_ids"] == protocol.selected_paper_ids
    assert result["sources"]["outcome_counts_by_retained_type"] == {"full_text": 2, "abstract": 2, "none": 2}
    assert result["sources"]["unobserved_outcome_classes"] == []
    assert result["provider_execution"]["status"] == "SOFTWARE_FIXTURE_ONLY"
    assert result["provider_execution"]["executed_by_this_command"] is False
    assert result["model_execution"]["status"] == "MODEL_NOT_RUN"
    assert result["human_usefulness"] == "NOT_RUN" and result["scientific_quality"] == "NOT_ASSESSED"
    assert result["software_checks"]["retained_source_hash_integrity"] == "PASS"
    encoded = json.dumps(result)
    assert "Private synthetic abstract" not in encoded and "Private synthetic source" not in encoded
    assert handle.token not in encoded and "retained_content_utf8" not in encoded


def fixture_map(tmp_path, handle, search):
    # One deliberately retained synthetic vector; other exclusions remain visible.
    # This is not a model run or a multi-point semantic-quality demonstration.
    profile = EmbeddingProfile(model="SOFTWARE FIXTURE VECTOR", model_revision="fixture-only",
        tokenizer_revision="fixture-only", dimension=3, runtime_versions={"fixture": "synthetic software only"})
    inputs = representations(search)
    vector = EmbeddedPaper(paper_id=inputs[0].paper_id, input_sha256=inputs[0].input_sha256,
        representation=inputs[0].representation, vector=[1.0, 0.0, 0.0], token_count=1, window_token_weights=[1])
    excluded = [ExcludedPaper(paper_id=item.paper_id, code="software_fixture_exclusion",
        reason="Deliberate synthetic software fixture exclusion, not a real model failure") for item in inputs[1:]]
    store = MapStore(tmp_path / "paper-maps.sqlite3")
    submission = store.submit(handle.workspace_id, search, profile,
        CreateMapRequest(request_id="synthetic-map", search_id=search.id))
    job = store.claim("software-fixture-worker", 120)
    artifact, vectors = build_artifact(handle.workspace_id, search, profile, [vector], excluded, submission.job.map_id)
    store.put_embedding(handle.workspace_id, profile, vector)
    store.publish(job, artifact, vectors, counts(search, artifact))
    return store, artifact


def test_existing_map_reopens_without_projection_or_model_call(tmp_path, monkeypatch):
    service, handle, protocol, search, preparation, discovery, sources = setup_case(tmp_path)
    store, artifact = fixture_map(tmp_path, handle, search)
    def forbidden(*args, **kwargs):
        raise AssertionError("Audit must not refit or execute a model/provider")
    monkeypatch.setattr("src.mvp.mapping.projection", forbidden)
    monkeypatch.setattr(discovery, "search", forbidden)
    monkeypatch.setattr(sources, "prepare", forbidden)
    result = audit_saved_case(service, handle, protocol, search_id=search.id,
        preparation_id=preparation.id, map_store=store, map_id=artifact.map_id)
    assert result["map"]["coordinate_sha256"] == artifact.coordinate_sha256
    assert result["map"]["reopen_without_refit"] == "PASS"
    assert result["map"]["counts"]["excluded_papers"] == 23
    assert result["model_execution"]["status"] == "PERSISTED_EMBEDDING_ARTIFACT_AUDITED"
    assert result["model_execution"]["real_model_execution_this_command"] == "MODEL_NOT_RUN"


@pytest.mark.parametrize("changes", [
    {"max_results": 51}, {"max_results": True},
    {"selected_paper_ids": ["one", "two", "three", "four"]},
    {"selected_paper_ids": ["duplicate"] * 5},
    {"date_from": "2025-01-01"},
    {"known_papers": [{"paper_id": "x", "reference_url": "https://example.invalid",
                         "relevance_status": "reviewer_approved"}]},
])
def test_protocol_rejects_ambiguous_caps_selection_and_relevance(changes):
    with pytest.raises(ValidationError):
        ResearchCaseProtocol(case_id="fixture", question="Question?", exact_query="exact", **changes)


def test_approval_requires_matching_exact_query_and_live_prerequisites():
    protocol = ResearchCaseProtocol(case_id="fixture", question="Question?", exact_query="a AND b")
    with pytest.raises(MvpError, match="explicit"):
        require_live_preconditions(protocol)
    with pytest.raises(MvpError) as error:
        require_live_preconditions(protocol, allow_live=True, environment={"NCBI_EMAIL": "valid@example.org"})
    assert error.value.code == "query_approval_required"
    approval = QueryApproval(status="approved", exact_query_sha256=query_sha256(protocol.exact_query),
        recorded_at="2026-10-21T00:00:00+00:00", evidence_note="Software fixture approval only")
    approved = ResearchCaseProtocol.model_validate({**protocol.model_dump(), "query_approval": approval.model_dump()})
    assert require_live_preconditions(approved, allow_live=True, environment={"NCBI_EMAIL": "valid@example.org"}) is None
    with pytest.raises(MvpError) as error:
        require_live_preconditions(approved, allow_live=True, environment={})
    assert error.value.code == "live_not_configured"
    with pytest.raises(ValidationError):
        ResearchCaseProtocol.model_validate({**approved.model_dump(), "exact_query": "a  AND b"})


def test_configuration_only_reports_presence_not_contact_or_key():
    info = configuration_status({"NCBI_EMAIL": "private@example.org", "NCBI_API_KEY": "private-secret"})
    assert info == {"ncbi_email_present": True, "ncbi_email_valid_format": True, "ncbi_api_key_present": True}
    assert "private" not in json.dumps(info)


def test_known_paper_recovery_does_not_score_unreviewed_candidates(tmp_path):
    service, handle, protocol, search, *_ = setup_case(tmp_path)
    result = known_paper_recovery(protocol, search)
    assert result["reviewer_approved_held_out_denominator"] == 0 and result["fraction"] is None
    papers = [KnownPaper(paper_id="fixture:report-0", reference_url="https://example.invalid/0", role="held_out",
        relevance_status="reviewer_approved", reviewer_rationale="Synthetic applicability rubric"),
        KnownPaper(paper_id="fixture:missing", reference_url="https://example.invalid/missing", role="held_out",
        relevance_status="reviewer_approved", reviewer_rationale="Synthetic applicability rubric"),
        KnownPaper(paper_id="fixture:report-1", reference_url="https://example.invalid/1")]
    result = known_paper_recovery(protocol.model_copy(update={"known_papers": papers}), search)
    assert result["reviewer_approved_held_out_denominator"] == 2 and result["fraction"] == 0.5
    assert result["candidate_ids_not_scored"] == ["fixture:report-1"]
    assert result["not_in_capped_preview_ids"] == ["fixture:missing"]


def test_wrong_search_selection_and_source_corruption_are_rejected(tmp_path):
    service, handle, protocol, search, preparation, *_ = setup_case(tmp_path)
    with pytest.raises(MvpError) as mismatch:
        audit_saved_case(service, handle, protocol.model_copy(update={"exact_query": "silently broadened"}), search_id=search.id)
    assert mismatch.value.code == "case_protocol_mismatch"
    with pytest.raises(MvpError) as mismatch:
        audit_saved_case(service, handle, protocol.model_copy(update={"selected_paper_ids": list(reversed(protocol.selected_paper_ids))}),
            search_id=search.id, preparation_id=preparation.id)
    assert mismatch.value.code == "case_selection_mismatch"
    state = service.get_workspace(handle)
    corrupted = preparation.model_copy(update={"sources": [preparation.sources[0].model_copy(update={"blocks_sha256": "0" * 64}), *preparation.sources[1:]]})
    class Reader:
        def get_workspace(self, capability):
            return state.model_copy(update={"preparations": [corrupted]})
        def suggest_query(self, capability, request):
            return service.suggest_query(capability, request)
    with pytest.raises(MvpError) as mismatch:
        audit_saved_case(Reader(), handle, protocol, search_id=search.id, preparation_id=preparation.id)
    assert mismatch.value.code == "source_integrity_error"


def test_missing_steps_stay_not_run_and_private_manifests_never_overwrite(tmp_path):
    protocol = ResearchCaseProtocol(case_id="fixture", question="Question?", exact_query="exact")
    manifest = readiness_manifest(protocol, {})
    assert manifest["configuration_scope"] == "audit_process_environment_not_saved_capture_server"
    assert manifest["provider_execution"]["status"] == "LIVE_NOT_RUN"
    assert manifest["model_execution"]["status"] == "MODEL_NOT_RUN"
    target = tmp_path / "new-audit"
    path = write_private_manifest(target, manifest)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(target.stat().st_mode) == 0o700
    with pytest.raises(ValueError):
        write_private_manifest(target, manifest)
    (tmp_path / "linked-parent").symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError):
        write_private_manifest(tmp_path / "linked-parent" / "another-audit", manifest)
