"""Opt-in research-case audit over existing saved MVP records.

This module has no discovery, model-loading, source-fetching or mutation path.
It records what a named saved case actually contains and separates that from
execution in the current command and from human scientific judgments.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import os
from src.platform_support import open_private
from pathlib import Path
import re
from typing import Literal

from pydantic import Field, model_validator

from .contracts import Model, QuerySuggestionRequest, digest, now
from .ports import MvpError
from .service import _assert_source_integrity
from .workspace_ui import private_directory


def query_sha256(query: str) -> str:
    """Hash the exact UTF-8 query; whitespace is not silently normalized."""
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


class QueryApproval(Model):
    status: Literal["pending", "approved"] = "pending"
    exact_query_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    recorded_at: str | None = None
    evidence_note: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def explicit_approval(self):
        if self.status == "approved" and (not self.exact_query_sha256 or not self.recorded_at or not self.evidence_note.strip()):
            raise ValueError("Approved queries require a digest, time and approval evidence note")
        return self


class KnownPaper(Model):
    paper_id: str = Field(min_length=1, max_length=200)
    reference_url: str = Field(min_length=1, max_length=2000)
    role: Literal["candidate", "held_out"] = "candidate"
    relevance_status: Literal["not_assessed", "reviewer_approved"] = "not_assessed"
    reviewer_rationale: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def approved_relevance(self):
        if self.relevance_status == "reviewer_approved" and not self.reviewer_rationale.strip():
            raise ValueError("Reviewer-approved known papers require an applicability rationale")
        return self


class ConceptGroup(Model):
    label: str = Field(min_length=1, max_length=100)
    terms: list[str] = Field(min_length=1, max_length=30)


class ResearchCaseProtocol(Model):
    schema_version: Literal["mvp.research-case-protocol.v1"] = "mvp.research-case-protocol.v1"
    case_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    question: str = Field(min_length=1, max_length=10000)
    exact_query: str = Field(min_length=1, max_length=20000)
    max_results: int = Field(default=30, ge=1, le=50, strict=True)
    sort: Literal["relevance", "pub_date"] = "relevance"
    date_from: str | None = None
    date_to: str | None = None
    query_approval: QueryApproval = Field(default_factory=QueryApproval)
    selected_paper_ids: list[str] = Field(default_factory=list, max_length=10)
    known_papers: list[KnownPaper] = Field(default_factory=list, max_length=30)
    reviewer_concept_groups: list[ConceptGroup] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def exact_protocol(self):
        from .contracts import SearchRequest
        SearchRequest(request_id="protocol-validation", query=self.exact_query,
                      research_question=self.question, max_results=self.max_results,
                      sort=self.sort, date_from=self.date_from, date_to=self.date_to)
        if self.selected_paper_ids and not 5 <= len(self.selected_paper_ids) <= 10:
            raise ValueError("A research case explicitly selects five to ten papers; leave selection empty until reviewed")
        if len(set(self.selected_paper_ids)) != len(self.selected_paper_ids):
            raise ValueError("Select each report only once")
        if len({item.paper_id for item in self.known_papers}) != len(self.known_papers):
            raise ValueError("Known-paper recovery uses unique report IDs")
        if self.query_approval.status == "approved" and self.query_approval.exact_query_sha256 != query_sha256(self.exact_query):
            raise ValueError("Approval does not match this exact query")
        return self


def configuration_status(environment=None):
    """Only presence/format leaves this function; never return contact/key values."""
    environment = os.environ if environment is None else environment
    email = environment.get("NCBI_EMAIL", "").strip()
    return {"ncbi_email_present": bool(email),
            "ncbi_email_valid_format": bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)),
            "ncbi_api_key_present": bool(environment.get("NCBI_API_KEY", "").strip())}


def require_live_preconditions(protocol, *, allow_live=False, environment=None):
    """Reusable guard for an explicit future/API capture; makes no request."""
    if not allow_live:
        raise MvpError("live_opt_in_required", "Live case capture requires explicit opt-in.")
    if protocol.query_approval.status != "approved":
        raise MvpError("query_approval_required", "The exact case query has not been approved.")
    if not configuration_status(environment)["ncbi_email_valid_format"]:
        raise MvpError("live_not_configured", "Configure a valid server NCBI_EMAIL before live case capture.")


def known_paper_recovery(protocol, search):
    present = {paper.id for paper in search.papers}
    held_out = [item.paper_id for item in protocol.known_papers
                if item.role == "held_out" and item.relevance_status == "reviewer_approved"]
    recovered = [identifier for identifier in held_out if identifier in present]
    return {"reviewer_approved_held_out_denominator": len(held_out),
            "recovered_count": len(recovered), "recovered_ids": recovered,
            "not_in_capped_preview_ids": [identifier for identifier in held_out if identifier not in present],
            "candidate_ids_not_scored": [item.paper_id for item in protocol.known_papers if item.paper_id not in held_out],
            "fraction": len(recovered) / len(held_out) if held_out else None,
            "interpretation": "Recovery within this capped preview, not recall of all relevant literature. Relevance labels are self-declared reviewer judgments."}


def readiness_manifest(protocol, environment=None):
    config = configuration_status(environment)
    return {"schema_version": "mvp.research-case-audit.v1", "case_id": protocol.case_id,
            "created_at": now(), "protocol_sha256": digest(protocol.model_dump(mode="json")),
            "query_sha256": query_sha256(protocol.exact_query), "configuration": config,
            "configuration_scope": "audit_process_environment_not_saved_capture_server",
            "query_approval": protocol.query_approval.status,
            "software_checks": {"protocol_validation": "PASS"},
            "provider_execution": {"status": "LIVE_NOT_RUN", "executed_by_this_command": False},
            "model_execution": {"status": "MODEL_NOT_RUN", "executed_by_this_command": False},
            "human_usefulness": "NOT_RUN", "scientific_quality": "NOT_ASSESSED",
            "publication": {"status": "NOT_REVIEWED_DO_NOT_PUBLISH", "retention": "local_private_research",
                            "abstracts_in_manifest": False, "source_text_in_manifest": False,
                            "credentials_in_manifest": False,
                            "field_rights": {"query_and_question": "private_research_protocol",
                                             "identifiers_and_hashes": "provenance_only_no_source_rights_implied",
                                             "abstracts_and_source_text": "omitted_pending_field_by_field_rights_review"}}}


def audit_saved_case(service, handle, protocol: ResearchCaseProtocol, *, search_id,
                     preparation_id=None, map_store=None, map_id=None, environment=None):
    """Inspect one named case and its original binding. No provider/model calls.

    A source hash check establishes exact retained-text integrity only. It does
    not establish that the text supports a scientific value or population.
    """
    manifest = readiness_manifest(protocol, environment)
    state = service.get_workspace(handle)
    search = next((item for item in state.searches if item.id == search_id), None)
    if search is None:
        raise MvpError("unknown_search", "The named case search does not belong to this workspace.")
    if (search.query != protocol.exact_query or search.research_question != protocol.question
            or search.sort != protocol.sort or search.date_from != protocol.date_from or search.date_to != protocol.date_to):
        raise MvpError("case_protocol_mismatch", "Saved search differs from the exact case query, question, sort or dates.")
    if search.fetched_count > protocol.max_results or len(search.papers) > protocol.max_results:
        raise MvpError("case_cap_mismatch", "Saved search exceeds the case's approved preview cap.")
    if search.mode == "live" and protocol.query_approval.status != "approved":
        raise MvpError("query_approval_required", "A live case needs recorded exact-query approval before this audit.")
    paper_ids = [paper.id for paper in search.papers]
    if any(identifier not in paper_ids for identifier in protocol.selected_paper_ids):
        raise MvpError("case_selection_mismatch", "An explicitly selected report is absent from this saved search.")
    manifest["workspace_id"] = state.id
    manifest["search"] = {"id": search.id, "query": search.query, "query_translation": search.query_translation,
        "research_question": search.research_question, "searched_at": search.searched_at,
        "sort": search.sort, "date_from": search.date_from, "date_to": search.date_to,
        "provider": search.provider, "mode": search.mode, "requested_cap_from_protocol": protocol.max_results,
        "provider_reported_count": search.total_reported, "fetched_count": search.fetched_count,
        "distinct_record_count": len(search.papers), "ordered_identifiers": search.ordered_identifiers,
        "paper_ids": paper_ids, "truncated": search.truncated,
        "saved_snapshot_sha256": digest(search.model_dump(mode="json")),
        "error_codes": [error.code for error in search.errors], "warning_count": len(search.warnings),
        "actual_20_to_50_metadata_target_met": 20 <= len(search.papers) <= 50,
        "input_hashes": {paper.id: digest(paper.model_dump(mode="json")) for paper in search.papers}}
    manifest["provider_execution"] = {"status": {"live": "SAVED_LIVE_CAPTURE_AUDITED", "test": "SOFTWARE_FIXTURE_ONLY",
        "saved_example": "SAVED_EXAMPLE_ONLY"}[search.mode], "executed_by_this_command": False,
        "live_execution_this_command": "LIVE_NOT_RUN", "capture_success_does_not_establish_relevance": True}
    suggestion = service.suggest_query(handle, QuerySuggestionRequest(question=protocol.question))
    manifest["query_review"] = {"existing_suggestion": suggestion.model_dump(mode="json"),
        "approved_syntax_is_unchanged": True, "suggestion_matches_executed_query": suggestion.query == search.query,
        "reviewer_concept_groups": [group.model_dump(mode="json") for group in protocol.reviewer_concept_groups],
        "concept_group_comparison_status": "HUMAN_REVIEW_REQUIRED", "additional_queries_executed": 0}
    manifest["known_paper_recovery"] = known_paper_recovery(protocol, search)
    if preparation_id is None:
        manifest["sources"] = {"status": "NOT_PREPARED", "selected_paper_ids": protocol.selected_paper_ids,
                               "outcomes": [], "human_semantic_inspection": "NOT_RUN"}
    else:
        preparation = next((item for item in state.preparations if item.id == preparation_id), None)
        if preparation is None or preparation.search_id != search.id:
            raise MvpError("case_preparation_mismatch", "Case preparation does not belong to the original case search.")
        if not protocol.selected_paper_ids or preparation.selected_paper_ids != protocol.selected_paper_ids:
            raise MvpError("case_selection_mismatch", "Prepared reports differ from the case's explicit ordered selection.")
        if ([source.paper_id for source in preparation.sources] != preparation.selected_paper_ids
                or len({source.id for source in preparation.sources}) != len(preparation.sources)):
            raise MvpError("source_integrity_error", "Prepared sources do not reconcile to the explicit report selection.")
        _assert_source_integrity(preparation.sources)
        outcomes = [{"paper_id": source.paper_id, "source_id": source.id, "status": source.status,
            "source_type": source.source_type, "provider": source.provider, "source_url": source.source_url,
            "retrieved_at": source.retrieved_at, "source_version": source.version,
            "source_sha256": source.source_sha256, "blocks_sha256": source.blocks_sha256,
            "canonical_block_count": len(source.blocks), "canonical_blocks_hash_check": "PASS",
            "retained_original_bytes_hash_check": "PASS" if source.retained_content_utf8 is not None else "NOT_RETAINED" if source.source_type != "none" else "NOT_APPLICABLE",
            "source_hash_basis": "NOT_APPLICABLE" if source.source_type == "none" else source.parser_metadata.get("source_hash_basis", "original retained bytes" if source.retained_content_utf8 is not None else "provider-recorded digest; original bytes not retained"),
            "canonical_block_inspection": [{"block_id": block.id, "ordinal": block.ordinal,
                "unicode_code_point_range": [0, len(block.text)],
                "text_sha256": hashlib.sha256(block.text.encode("utf-8")).hexdigest()}
                for block in source.blocks],
            "error_code": source.error.code if source.error else None, "warning_count": len(source.warnings),
            "recorded_license": source.license, "redistribution_review": "NOT_REVIEWED",
            "semantic_inspection": "NOT_ASSESSED"} for source in preparation.sources]
        counts = dict(Counter(item["source_type"] for item in outcomes))
        manifest["sources"] = {"status": "RETAINED_SNAPSHOT_CHECKED", "preparation_id": preparation.id,
            "source_revision": preparation.source_revision, "prepared_at": preparation.prepared_at,
            "is_current_preparation": bool(state.preparations and state.preparations[-1].id == preparation.id),
            "selected_paper_ids": preparation.selected_paper_ids, "outcomes": outcomes,
            "outcome_counts_by_retained_type": counts,
            "unobserved_outcome_classes": [kind for kind in ("full_text", "abstract", "none") if not counts.get(kind)],
            "human_semantic_inspection": "NOT_RUN", "selection_state": preparation.selection_state}
        manifest["software_checks"]["retained_source_hash_integrity"] = "PASS"
    if map_id is not None:
        if map_store is None:
            raise MvpError("case_map_unavailable", "Supply the existing private map store for a named map audit.")
        first = map_store.map(state.id, map_id)
        second = map_store.map(state.id, map_id)
        artifact = first.artifact
        if artifact.search_id != search.id or artifact.search_snapshot_sha256 != digest(search.model_dump(mode="json")):
            raise MvpError("case_map_mismatch", "The named map is bound to a different saved search snapshot.")
        from .mapping import counts, representations, validate_artifact
        if artifact.workspace_id != state.id or first.counts != counts(search, artifact):
            raise MvpError("case_map_mismatch", "The named map identity or counts do not reconcile to this case.")
        embedded = []
        for representation in representations(search):
            if representation.paper_id in artifact.coordinates_by_paper_id:
                item = map_store.embedding(state.id, artifact.embedding_profile, representation)
                if item is None:
                    raise MvpError("map_integrity", "The map's retained embedding is missing.")
                embedded.append(item)
        validate_artifact(artifact, search, artifact.embedding_profile, embedded)
        map_store.vectors(state.id, map_id)
        if first.model_dump(mode="json") != second.model_dump(mode="json"):
            raise MvpError("case_map_changed", "Reopening changed the persisted map artifact.")
        manifest["map"] = {"map_id": artifact.map_id, "created_at": artifact.created_at,
            "status": artifact.status, "counts": first.counts.model_dump(mode="json"),
            "search_snapshot_sha256": artifact.search_snapshot_sha256,
            "paper_input_hashes": artifact.paper_input_hashes,
            "embedding_profile": artifact.embedding_profile.model_dump(mode="json"),
            "embedding_profile_sha256": artifact.embedding_profile_sha256,
            "embedding_set_sha256": artifact.embedding_set_sha256,
            "coordinate_sha256": artifact.coordinate_sha256,
            "coordinates_by_paper_id": artifact.coordinates_by_paper_id,
            "projection_method": artifact.projection_method, "projection_parameters": artifact.projection_parameters,
            "dependency_versions": artifact.dependency_versions,
            "excluded_papers": [item.model_dump(mode="json") for item in artifact.excluded_papers_with_reasons],
            "reopen_without_refit": "PASS", "semantic_layout_quality": "NOT_ASSESSED"}
        manifest["model_execution"] = {"status": "PERSISTED_EMBEDDING_ARTIFACT_AUDITED",
            "executed_by_this_command": False, "real_model_execution_this_command": "MODEL_NOT_RUN",
            "runtime_seconds_this_command": None,
            "caveat": "A saved model/profile manifest is provenance, not independent proof of model execution or semantic quality. Keep the explicit real-model run receipt separately."}
        manifest["software_checks"]["persisted_map_reopening"] = "PASS"
    # Read once more with the same capability; never create a replacement case.
    if service.get_workspace(handle).id != state.id:
        raise MvpError("case_reopening_failed", "Reopening did not retain the original workspace identity.")
    manifest["software_checks"]["same_workspace_reopening"] = "PASS"
    return manifest


def write_private_manifest(output: Path, manifest: dict):
    """A fresh dedicated directory only; no generic export/publication path."""
    output = output.expanduser().absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Choose a new case-audit output directory")
    directory = private_directory(output)
    path = directory / "manifest.json"
    descriptor = open_private(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    from .contracts import canonical
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(canonical(manifest) + "\n")
    return path
