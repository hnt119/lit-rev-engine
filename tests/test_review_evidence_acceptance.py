"""Independent source-anchored manual evidence/reviewer state acceptance."""

from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import unicodedata

import pytest

from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.store import ReviewStore


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "evidence"


def hash_revision(revision):
    payload = {key: value for key, value in revision.items() if key != "revision_sha256"}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


@pytest.fixture(autouse=True)
def no_live_dependencies(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Evidence acceptance attempted network or real sleep")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr("time.sleep", denied)


def sources():
    return {item["alias"]: item for item in json.loads((FIXTURES / "manifest.json").read_text())["fixtures"]}


def scenario(store, *, source_alias="text_v1", eligible=True, linkage="linked", title="Manual evidence audit"):
    project_id = store.create_project(title, "systematic", "Which invented source statements are anchored?")["id"]
    store.import_records(project_id, SearchRunSpec("Synthetic bibliography"), [
        BibliographicRecord(title="Invented primary report", doi="10.99999/evidence-primary"),
        BibliographicRecord(title="Invented companion report", doi="10.99999/evidence-companion"),
    ])
    reports = store.list_records(project_id)
    record_id, other_record_id = reports[0]["id"], reports[1]["id"]
    study = store.create_study(project_id, "Synthetic study A", "Link curator", "Invented source identity")
    other_study = store.create_study(project_id, "Synthetic study B", "Link curator", "Alternative identity")
    if eligible:
        store.record_decision(project_id, record_id, "title_abstract", "include", "Eligibility reviewer")
        store.set_full_text_status(project_id, record_id, "retrieved", "Source custodian")
        store.record_decision(project_id, record_id, "full_text", "include", "Eligibility reviewer")
    if linkage != "pending":
        store.record_study_links(project_id, record_id, [] if linkage == "unlinked" else [study["id"]], "Linker", "Complete association set")
    if linkage == "conflict":
        store.record_study_links(project_id, record_id, [other_study["id"]], "Other linker", "Disagreeing association")
    item = sources()[source_alias]
    doc = store.attach_document(project_id, record_id, (FIXTURES / item["file"]).read_bytes(), item["format"], "Source custodian", "Exact synthetic bytes")
    return {"project_id": project_id, "record_id": record_id, "other_record_id": other_record_id,
            "study_id": study["id"], "other_study_id": other_study["id"], "document": doc, "source_alias": source_alias}


def payload(case):
    item = sources()[case["source_alias"]]
    quote = next(quote for quote in item["quotes"] if quote["name"] == "unicode_marker")
    return {"study_id": case["study_id"], "document_id": case["document"]["id"], "field": "synthetic_unicode_marker",
            "value": {"literal": "α café café 🧪", "entered": True, "unknown": None},
            "context": {"population": "Invented entries, not patients", "notes": "Nonclinical fixture\r\nUnicode context"},
            "anchor": {key: quote[key] for key in ("block_id", "start", "end", "quote")}, "reviewer": "Alice", "reason": "Manual fixture proposal"}


def propose(store, case, supplied=None, **options):
    return store.propose_evidence(case["project_id"], case["record_id"], **(deepcopy(supplied) if supplied is not None else payload(case)), **options)


def revise(store, case, previous, supplied=None):
    return store.revise_evidence(case["project_id"], previous["evidence_id"], **(deepcopy(supplied) if supplied is not None else payload(case)))


def current(store, case, evidence_id):
    return next(row for row in store.list_evidence(case["project_id"]) if row["evidence_id"] == evidence_id)


def audit(store, project_id):
    return deepcopy({"current": store.list_evidence(project_id), "revisions": store.list_evidence_revisions(project_id),
                     "reviews": store.list_evidence_reviews(project_id), "counts": store.counts(project_id),
                     "records": store.list_records(project_id), "documents": store.list_documents(project_id),
                     "studies": store.list_studies(project_id), "links": store.list_study_links(project_id),
                     "link_events": store.list_study_link_events(project_id), "decisions": store.list_decisions(project_id),
                     "retrieval": store.list_retrieval_events(project_id), "runs": store.list_search_runs(project_id),
                     "occurrences": store.get_occurrences(project_id)})


def assert_revision(store, case, revision, supplied):
    assert revision["revision_sha256"] == hash_revision(revision)
    assert revision["project_id"] == case["project_id"] and revision["record_id"] == case["record_id"]
    for field in ("study_id", "document_id", "field", "value", "context", "reviewer", "reason"):
        assert revision[field] == supplied[field]
    doc = next(doc for doc in store.list_documents(case["project_id"]) if doc["id"] == supplied["document_id"])
    assert revision["source_sha256"] == doc["source_sha256"] and revision["blocks_sha256"] == doc["blocks_sha256"]
    block = next(block for block in store.get_source_blocks(case["project_id"], doc["id"]) if block["id"] == supplied["anchor"]["block_id"])
    assert revision["anchor"] == {**supplied["anchor"], "locator": block["locator"]}
    assert block["text"][revision["anchor"]["start"]:revision["anchor"]["end"]] == revision["anchor"]["quote"]


def assert_state(store, case, evidence_id, verification, issues=(), active=None):
    row = current(store, case, evidence_id)
    assert row["verification_state"] == verification and row["dependency_issues"] == list(issues)
    assert row["state"] == (issues[0] if issues else verification)
    assert row["verified"] is (verification == "confirmed" and not issues)
    if active is not None:
        assert row["active_verification_event_ids"] == active
    assert (row in store.list_evidence(case["project_id"], verified_only=True)) is row["verified"]
    return row


EXTRACTIONS = json.loads((FIXTURES / "extractions.json").read_text())


def fixture_setup(store):
    project_id = store.create_project("Independent invented extraction truth", "systematic", "Which literal fixture statements are supported?")["id"]
    setup = EXTRACTIONS["setup"]
    store.import_records(project_id, SearchRunSpec("Independent source fixture bibliography"),
                         [BibliographicRecord(title=report["title"]) for report in setup["reports"]])
    reports = {report["alias"]: stored["id"] for report, stored in zip(setup["reports"], store.list_records(project_id), strict=True)}
    studies = {study["alias"]: store.create_study(project_id, study["label"], "Fixture Linker", "Invented identity")["id"]
               for study in setup["studies"]}
    environment = {"project_id": project_id, "reports": reports, "studies": studies, "documents": {}}
    for report in setup["reports"]:
        record_id = reports[report["alias"]]
        store.record_decision(project_id, record_id, "title_abstract", "include", "Fixture Screener")
        store.set_full_text_status(project_id, record_id, "retrieved", "Fixture Custodian")
        store.record_decision(project_id, record_id, "full_text", "include", "Fixture Screener")
        store.record_study_links(project_id, record_id, [studies["study_alpha"]], "Fixture Linker", "Complete initial association")
        fixture_attach(store, environment, report["alias"], report["initial_source_alias"])
    return environment


def fixture_attach(store, environment, record_alias, source_alias, *, reviewer="Fixture Author Ari", reason="Exact independent fixture bytes"):
    source = sources()[source_alias]
    document = store.attach_document(environment["project_id"], environment["reports"][record_alias],
                                     (FIXTURES / source["file"]).read_bytes(), source["format"], reviewer, reason)
    assert document["source_sha256"] == source["source_sha256"]
    assert document["blocks_sha256"] == source["expected_blocks_sha256"]
    environment["documents"][(record_alias, source_alias)] = document
    return document


def fixture_bind(environment, fixture, *, document_override=None):
    target = fixture["target"]
    supplied = deepcopy(fixture["input"])
    supplied["study_id"] = environment["studies"][target["study_alias"]]
    supplied["document_id"] = (document_override or environment["documents"][(target["record_alias"], target["source_alias"])] )["id"]
    case = {"project_id": environment["project_id"], "record_id": environment["reports"][target["record_alias"]]}
    return case, supplied


@pytest.mark.parametrize("fixture", EXTRACTIONS["proposals"], ids=lambda fixture: fixture["id"])
def test_independently_authored_values_context_quotes_appraisal_and_typed_locators_round_trip(tmp_path, fixture):
    with ReviewStore(tmp_path / "fixture.sqlite3") as store:
        environment = fixture_setup(store)
        case, supplied = fixture_bind(environment, fixture)
        revision = propose(store, case, supplied)
        assert_revision(store, case, revision, supplied)
        assert revision["kind"] == supplied["kind"] and revision["appraisal"] == supplied["appraisal"]
        assert revision["anchor"]["locator"] == fixture["expected"]["anchor_locator"]
        assert_state(store, case, revision["evidence_id"], "proposed", active=[])
        event = store.review_evidence(case["project_id"], revision["id"], "confirm", "Fixture Reviewer Bo", "Check independently authored literal fixture value and context")
        row = assert_state(store, case, revision["evidence_id"], "confirmed", active=[event["id"]])
        directory = tmp_path / "export"
        store.export_project(case["project_id"], directory)
        assert json.loads((directory / "verified_evidence.json").read_text()) == [row]
        assert store.list_evidence_revisions(case["project_id"]) == [revision]
        assert store.list_evidence_reviews(case["project_id"]) == [event]


@pytest.mark.parametrize("fixture", EXTRACTIONS["invalid_anchor_cases"], ids=lambda fixture: fixture["id"])
def test_independent_invalid_unicode_version_reference_and_table_anchors_roll_back(tmp_path, fixture):
    with ReviewStore(tmp_path / "fixture.sqlite3") as store:
        environment = fixture_setup(store)
        target = fixture["target"]
        if (target["record_alias"], target["source_alias"]) not in environment["documents"]:
            fixture_attach(store, environment, target["record_alias"], target["source_alias"])
        case, supplied = fixture_bind(environment, fixture)
        before = audit(store, case["project_id"])
        with pytest.raises(ValueError): propose(store, case, supplied)
        assert audit(store, case["project_id"]) == before


@pytest.mark.parametrize("fixture", EXTRACTIONS["semantic_contrasts"], ids=lambda fixture: fixture["id"])
def test_exact_anchor_accepts_unsupported_interpretation_until_independent_reviewer_rejects_it(tmp_path, fixture):
    with ReviewStore(tmp_path / "fixture.sqlite3") as store:
        environment = fixture_setup(store)
        case, supplied = fixture_bind(environment, fixture)
        revision = propose(store, case, supplied)
        assert_revision(store, case, revision, supplied)
        assert_state(store, case, revision["evidence_id"], "proposed", active=[])
        expected = fixture["expected"]
        event = store.review_evidence(case["project_id"], revision["id"], expected["support_decision"], expected["reviewer"], expected["review_reason"])
        row = assert_state(store, case, revision["evidence_id"], "rejected", active=[event["id"]])
        assert row["current_revision"]["value"] == supplied["value"] and row["current_revision"]["context"] == supplied["context"]
        directory = tmp_path / "export"
        store.export_project(case["project_id"], directory)
        bundle = json.loads((directory / "project.json").read_text())
        assert bundle["evidence"] == [row] and bundle["evidence_reviews"] == [event]
        assert bundle["verified_evidence"] == json.loads((directory / "verified_evidence.json").read_text()) == []


@pytest.mark.parametrize("fixture", EXTRACTIONS["scenarios"], ids=lambda fixture: fixture["id"])
def test_independent_literal_scenarios_check_every_state_and_verified_export_then_reopen(tmp_path, fixture):
    database = tmp_path / "fixture.sqlite3"
    proposals = {proposal["id"]: proposal for proposal in EXTRACTIONS["proposals"]}
    templates = {revision["id"]: revision for revision in EXTRACTIONS["revisions"]}
    references = {}
    with ReviewStore(database) as store:
        environment = fixture_setup(store)
        project_id = environment["project_id"]
        for step in fixture["steps"]:
            operation, arguments = step["operation"], step["arguments"]
            if operation == "propose":
                case, supplied = fixture_bind(environment, proposals[arguments["proposal_id"]])
                revision = propose(store, case, supplied)
                assert_revision(store, case, revision, supplied)
                references[arguments["evidence_ref"]] = revision["evidence_id"]
                references[arguments["revision_ref"]] = revision
                evidence_id = revision["evidence_id"]
            elif operation == "revise":
                override = references.get(arguments.get("document_ref_override"))
                case, supplied = fixture_bind(environment, templates[arguments["revision_template"]], document_override=override)
                revision = store.revise_evidence(project_id, references[arguments["evidence_ref"]], **supplied)
                assert_revision(store, case, revision, supplied)
                references[arguments["revision_ref"]] = revision
            elif operation in {"review", "adjudicate", "review_rejected", "adjudicate_rejected"}:
                method = store.review_evidence if operation.startswith("review") else store.adjudicate_evidence
                args = (project_id, references[arguments["revision_ref"]]["id"], arguments["decision"], arguments["reviewer"], arguments["reason"])
                if operation.endswith("_rejected"):
                    before = audit(store, project_id)
                    with pytest.raises(ValueError): method(*args)
                    assert audit(store, project_id) == before
                    assert arguments["event_ref"] not in references
                else:
                    references[arguments["event_ref"]] = method(*args)
            elif operation == "attach":
                references[arguments["document_ref"]] = fixture_attach(store, environment, arguments["record_alias"], arguments["source_alias"],
                                                                      reviewer=arguments["reviewer"], reason=arguments["reason"])
            elif operation in {"eligibility", "linkage", "eligibility_and_linkage"}:
                record_id = environment["reports"][arguments["record_alias"]]
                if operation != "linkage":
                    store.record_decision(project_id, record_id, "full_text", arguments["full_text"], arguments.get("reviewer", "Fixture Screener"), arguments["reason"])
                if operation != "eligibility":
                    store.record_study_links(project_id, record_id, [environment["studies"][alias] for alias in arguments["study_aliases"]],
                                             "Fixture Linker", arguments["reason"])
            else:
                pytest.fail(f"Unhandled independent fixture operation: {operation}")
            expected = step["expected_current"]
            row = assert_state(store, {"project_id": project_id}, evidence_id, expected["verification_state"], expected["dependency_issues"],
                               [references[reference]["id"] for reference in expected["active_verification_event_refs"]])
            assert row["current_revision"]["revision"] == expected["revision"], step["id"]
            assert row["state"] == expected["state"] and row["verified"] is expected["verified"], step["id"]
            assert len(store.list_evidence_revisions(project_id)) == expected["history_counts"]["revisions"], step["id"]
            assert len(store.list_evidence_reviews(project_id)) == expected["history_counts"]["reviews"], step["id"]
            export_directory = tmp_path / "per-step-export"
            store.export_project(project_id, export_directory)
            exported = json.loads((export_directory / "project.json").read_text())
            assert exported["evidence"] == [row]
            assert exported["verified_evidence"] == json.loads((export_directory / "verified_evidence.json").read_text()) == ([row] if expected["verified"] else [])
            assert exported["evidence_revisions"] == store.list_evidence_revisions(project_id)
            assert exported["evidence_reviews"] == store.list_evidence_reviews(project_id)
        final = fixture["final_expected"]
        row = current(store, {"project_id": project_id}, evidence_id)
        assert row["current_revision"] == references[final["current_revision_ref"]]
        assert len(store.list_evidence(project_id, verified_only=True)) == final["verified_rows"]
        if "retained_values_in_order" in final:
            assert [revision["value"]["duration"] for revision in store.list_evidence_revisions(project_id)] == final["retained_values_in_order"]
            assert store.list_evidence_revisions(project_id) == [references[reference] for reference in final["retained_revision_refs"]]
            assert store.list_evidence_reviews(project_id) == [references[reference] for reference in final["retained_event_refs"]]
            assert row["current_revision"]["document_id"] == references[final["active_document_ref"]]["id"]
        if "appraisal" in final:
            assert row["current_revision"]["appraisal"] == final["appraisal"] and row["current_revision"]["value"] == final["value"]
            assert row["current_revision"]["kind"] == final["kind"] and "overall_score" not in row["current_revision"]
        before_reopen = audit(store, project_id)
    with ReviewStore(database) as store:
        assert audit(store, project_id) == before_reopen


def test_revision_hash_exact_unicode_values_context_locators_and_returned_input_isolation(tmp_path):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        case = scenario(store)
        supplied = payload(case)
        frozen = deepcopy(supplied)
        revision = store.propose_evidence(case["project_id"], case["record_id"], **supplied)
        assert type(revision["revision"]) is int and revision["revision"] == 1
        assert revision["kind"] == "finding" and revision["appraisal"] is None
        assert_revision(store, case, revision, frozen)
        assert_state(store, case, revision["evidence_id"], "proposed", active=[])
        supplied["value"]["literal"] = "Caller mutation"
        supplied["context"]["notes"] = "Caller mutation"
        revision["anchor"]["locator"]["ordinal"] = 999
        stored = store.list_evidence_revisions(case["project_id"])[0]
        assert_revision(store, case, stored, frozen)


def test_equal_timestamp_reviews_disagreement_no_majority_adjudication_and_later_vote_invalidation(tmp_path, monkeypatch):
    monkeypatch.setattr("src.review.evidence._now", lambda: "2026-10-03T00:00:00+00:00")
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        case = scenario(store)
        revision = propose(store, case)
        events = []
        def vote(decision, reviewer):
            event = store.review_evidence(case["project_id"], revision["id"], decision, reviewer, "Exact fixture checked")
            events.append(event)
            return event
        def adjudicate(decision):
            event = store.adjudicate_evidence(case["project_id"], revision["id"], decision, "Coordinator", "Resolve declared review disagreement")
            events.append(event)
            return event
        vote("confirm", "Bob")
        vote("confirm", "Carol")
        vote("reject", "Dave")
        assert_state(store, case, revision["evidence_id"], "conflict", active=[event["id"] for event in events])
        resolved = adjudicate("confirm")
        assert_state(store, case, revision["evidence_id"], "confirmed", active=[resolved["id"]])
        latest = vote("confirm", "Dave")
        assert_state(store, case, revision["evidence_id"], "confirmed", active=[events[0]["id"], events[1]["id"], latest["id"]])
        vote("reject", "Bob")
        assert_state(store, case, revision["evidence_id"], "conflict")
        resolved = adjudicate("reject")
        assert_state(store, case, revision["evidence_id"], "rejected", active=[resolved["id"]])
        vote("reject", "Carol")
        assert_state(store, case, revision["evidence_id"], "conflict")
        vote("reject", "Dave")
        assert_state(store, case, revision["evidence_id"], "rejected", active=[events[5]["id"], events[7]["id"], events[8]["id"]])
        assert store.list_evidence_reviews(case["project_id"], revision["evidence_id"]) == events
        assert len(events) == 9 and {event["created_at"] for event in events} == {"2026-10-03T00:00:00+00:00"}
        assert all("sequence" not in event for event in events)


def test_revision_changes_current_author_invalidates_reviews_and_old_revision_cannot_be_reviewed(tmp_path):
    database = tmp_path / "reviews.sqlite3"
    with ReviewStore(database) as store:
        case = scenario(store)
        first = propose(store, case)
        original_review = store.review_evidence(case["project_id"], first["id"], "confirm", "Bob", "Original revision checked")
        for method in (store.review_evidence, store.adjudicate_evidence):
            for decision in ("confirm", "reject"):
                before = audit(store, case["project_id"])
                with pytest.raises(ValueError):
                    method(case["project_id"], first["id"], decision, "Alice", "Author cannot verify own revision")
                assert audit(store, case["project_id"]) == before
        supplied = payload(case)
        supplied.update(reviewer="Bob", reason="Complete replacement payload", value={"literal": "Revised entered fixture value"})
        second = revise(store, case, first, supplied)
        assert second["evidence_id"] == first["evidence_id"] and second["id"] != first["id"] and second["revision"] == 2
        assert_revision(store, case, second, supplied)
        assert_state(store, case, first["evidence_id"], "proposed", active=[])
        for method in (store.review_evidence, store.adjudicate_evidence):
            with pytest.raises(ValueError):
                method(case["project_id"], first["id"], "confirm", "Carol", "Historical revision")
            with pytest.raises(ValueError):
                method(case["project_id"], second["id"], "confirm", "Bob", "Now the current author")
        # Prior authorship does not prevent independent review of Bob's revision.
        accepted = store.review_evidence(case["project_id"], second["id"], "confirm", "Alice", "Different current author checked")
        assert_state(store, case, first["evidence_id"], "confirmed", active=[accepted["id"]])
        assert store.list_evidence_revisions(case["project_id"], first["evidence_id"]) == [first, second]
        assert store.list_evidence_reviews(case["project_id"]) == [original_review, accepted]
        saved = audit(store, case["project_id"])
    with ReviewStore(database) as reopened:
        assert audit(reopened, case["project_id"]) == saved


def test_dependency_issue_order_restoration_and_identical_source_replacement_still_stale(tmp_path):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        case = scenario(store)
        revision = propose(store, case)
        review = store.review_evidence(case["project_id"], revision["id"], "confirm", "Bob", "Independent quotation check")
        def eligibility(decision):
            store.record_decision(case["project_id"], case["record_id"], "full_text", decision, "Eligibility reviewer", "Synthetic eligibility revision")
        def links(ids):
            store.record_study_links(case["project_id"], case["record_id"], ids, "Linker", "Whole-set association revision")
        eligibility("uncertain")
        assert_state(store, case, revision["evidence_id"], "confirmed", ["ineligible_report"])
        eligibility("include")
        assert_state(store, case, revision["evidence_id"], "confirmed")
        links([])
        assert_state(store, case, revision["evidence_id"], "confirmed", ["unresolved_linkage"])
        links([case["other_study_id"]])
        assert_state(store, case, revision["evidence_id"], "confirmed", ["study_not_linked"])
        links([case["study_id"]])
        assert_state(store, case, revision["evidence_id"], "confirmed")
        store.record_study_links(case["project_id"], case["record_id"], [case["other_study_id"]], "Other linker", "Disagreement")
        assert_state(store, case, revision["evidence_id"], "confirmed", ["unresolved_linkage"])
        store.adjudicate_study_links(case["project_id"], case["record_id"], [case["study_id"]], "Link coordinator", "Restore association")
        assert_state(store, case, revision["evidence_id"], "confirmed")
        item = sources()["text_v1"]
        replacement = store.attach_document(case["project_id"], case["record_id"], (FIXTURES / item["file"]).read_bytes(), "txt", "Source custodian", "Identical-byte new source version")
        assert replacement["source_sha256"] == case["document"]["source_sha256"] and replacement["id"] != case["document"]["id"]
        assert_state(store, case, revision["evidence_id"], "confirmed", ["stale_source"])
        eligibility("exclude")
        links([])
        assert_state(store, case, revision["evidence_id"], "confirmed", ["stale_source", "ineligible_report", "unresolved_linkage"])
        store.adjudicate_study_links(case["project_id"], case["record_id"], [case["other_study_id"]], "Link coordinator", "Resolved different association")
        assert_state(store, case, revision["evidence_id"], "confirmed", ["stale_source", "ineligible_report", "study_not_linked"])
        before = audit(store, case["project_id"])
        for method in (store.review_evidence, store.adjudicate_evidence):
            with pytest.raises(ValueError):
                method(case["project_id"], revision["id"], "confirm", "Carol", "Invalid current dependencies")
        assert audit(store, case["project_id"]) == before
        eligibility("include")
        store.adjudicate_study_links(case["project_id"], case["record_id"], [case["study_id"]], "Link coordinator", "Restore original association")
        assert_state(store, case, revision["evidence_id"], "confirmed", ["stale_source"])
        assert store.list_evidence_reviews(case["project_id"]) == [review]
        supplied = payload(case)
        supplied.update(document_id=replacement["id"], reviewer="Carol", reason="Reanchor to active version")
        new_revision = revise(store, case, revision, supplied)
        assert_state(store, case, revision["evidence_id"], "proposed", active=[])
        store.review_evidence(case["project_id"], new_revision["id"], "confirm", "Alice", "New active source independently checked")
        assert_state(store, case, revision["evidence_id"], "confirmed")


def test_late_canonical_identifier_enrichment_invalidates_source_until_correct_replacement_and_new_review(tmp_path):
    def xml(pmid):
        return f'<article><front><article-meta><article-id pub-id-type="doi">10.99999/evidence-primary</article-id><article-id pub-id-type="pmid">{pmid}</article-id></article-meta></front><body><p>Source α.</p></body></article>'.encode("utf-8")
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        case = scenario(store)
        original_bytes = xml("999999111")
        doc = store.attach_document(case["project_id"], case["record_id"], original_bytes, "jats_xml", "Custodian", "Explicit own source identifiers")
        supplied = payload(case)
        supplied.update(document_id=doc["id"], field="synthetic_marker", value="α", anchor={"block_id": "xml:/article[1]/body[1]/p[1]", "start": 7, "end": 8, "quote": "α"})
        revision = propose(store, case, supplied)
        review = store.review_evidence(case["project_id"], revision["id"], "confirm", "Bob", "Own source IDs match known bibliography")
        assert_state(store, case, revision["evidence_id"], "confirmed")
        enriched = store.import_records(case["project_id"], SearchRunSpec("Later identifier enrichment"),
                                        [BibliographicRecord(title="Invented primary report", doi="10.99999/evidence-primary", pmid="999999112")])
        assert enriched["new_records"] == 0 and enriched["duplicates"] == 1
        assert_state(store, case, revision["evidence_id"], "confirmed", ["source_identity_conflict"])
        before = audit(store, case["project_id"])
        for operation in (lambda: propose(store, case, supplied), lambda: revise(store, case, revision, supplied),
                          lambda: store.review_evidence(case["project_id"], revision["id"], "confirm", "Carol", "Identity conflict"),
                          lambda: store.adjudicate_evidence(case["project_id"], revision["id"], "confirm", "Coordinator", "Identity conflict")):
            with pytest.raises(ValueError): operation()
            assert audit(store, case["project_id"]) == before
        corrected = store.attach_document(case["project_id"], case["record_id"], xml("999999112"), "jats_xml", "Custodian", "Correct explicit source identity")
        store.record_decision(case["project_id"], case["record_id"], "full_text", "exclude", "Eligibility reviewer", "Temporary eligibility revision")
        store.record_study_links(case["project_id"], case["record_id"], [], "Linker", "Temporary association clearing")
        assert_state(store, case, revision["evidence_id"], "confirmed", ["stale_source", "source_identity_conflict", "ineligible_report", "unresolved_linkage"])
        directory = tmp_path / "identity-conflict-export"
        store.export_project(case["project_id"], directory)
        bundle = json.loads((directory / "project.json").read_text())
        assert bundle["verified_evidence"] == [] and bundle["evidence_reviews"] == [review]
        assert store.get_document_bytes(case["project_id"], doc["id"]) == original_bytes
        store.record_decision(case["project_id"], case["record_id"], "full_text", "include", "Eligibility reviewer")
        store.record_study_links(case["project_id"], case["record_id"], [case["study_id"]], "Linker", "Restore original association")
        supplied.update(document_id=corrected["id"], reviewer="Carol", reason="Reanchor to corrected source identity")
        replacement = revise(store, case, revision, supplied)
        assert_state(store, case, revision["evidence_id"], "proposed", active=[])
        store.review_evidence(case["project_id"], replacement["id"], "confirm", "Alice", "Distinct reviewer checks corrected source")
        assert_state(store, case, revision["evidence_id"], "confirmed")
        assert store.list_evidence_revisions(case["project_id"]) == [revision, replacement]


@pytest.mark.parametrize("failure", ["ineligible", "pending_link", "empty_link", "conflicted_link", "study_not_linked", "stale_source"])
def test_new_proposals_require_current_inclusion_resolved_study_and_active_source(tmp_path, failure):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        case = scenario(store, eligible=failure != "ineligible", linkage={"pending_link": "pending", "empty_link": "unlinked", "conflicted_link": "conflict"}.get(failure, "linked"))
        supplied = payload(case)
        if failure == "study_not_linked":
            supplied["study_id"] = case["other_study_id"]
        if failure == "stale_source":
            item = sources()["text_v2"]
            store.attach_document(case["project_id"], case["record_id"], (FIXTURES / item["file"]).read_bytes(), "txt", "Custodian", "Replaced source")
        before = audit(store, case["project_id"])
        with pytest.raises(ValueError):
            propose(store, case, supplied)
        assert audit(store, case["project_id"]) == before


@pytest.mark.parametrize("bad_anchor", ["missing_block", "extra_locator", "start_bool", "end_bool", "negative_start", "reversed", "past_end", "float_offset", "empty_quote", "blank_quote", "wrong_quote", "unicode_normalized", "byte_offsets"])
def test_invalid_anchor_offsets_text_and_shape_reject_proposals_and_revisions_atomically(tmp_path, bad_anchor):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        case = scenario(store)
        first = propose(store, case)
        supplied = payload(case)
        anchor = supplied["anchor"]
        text = store.get_source_blocks(case["project_id"], case["document"]["id"])[0]["text"]
        if bad_anchor == "missing_block": anchor["block_id"] = "unknown-block"
        elif bad_anchor == "extra_locator": anchor["locator"] = {"type": "text_block", "ordinal": 1}
        elif bad_anchor == "start_bool": anchor["start"] = True
        elif bad_anchor == "end_bool": anchor["end"] = True
        elif bad_anchor == "negative_start": anchor["start"] = -1
        elif bad_anchor == "reversed": anchor["start"] = anchor["end"]
        elif bad_anchor == "past_end": anchor["end"] = len(text) + 1
        elif bad_anchor == "float_offset": anchor["start"] = float(anchor["start"])
        elif bad_anchor == "empty_quote": anchor["quote"] = ""
        elif bad_anchor == "blank_quote": anchor.update(start=0, end=1, quote=" ")
        elif bad_anchor == "wrong_quote": anchor["quote"] = "Wrong quotation"
        elif bad_anchor == "unicode_normalized": anchor["quote"] = unicodedata.normalize("NFC", anchor["quote"])
        elif bad_anchor == "byte_offsets":
            anchor["start"], anchor["end"] = len(text[:anchor["start"]].encode("utf-8")), len(text[:anchor["end"]].encode("utf-8"))
        before = audit(store, case["project_id"])
        for operation in (lambda: propose(store, case, supplied), lambda: revise(store, case, first, supplied)):
            with pytest.raises(ValueError): operation()
            assert audit(store, case["project_id"]) == before


@pytest.mark.parametrize("field,value", [("value", float("nan")), ("value", {"nested": [float("inf")]}), ("value", {1: "nonstring JSON key"}),
                                         ("context", []), ("context", {"unsupported": "extra key"}), ("context", {"notes": float("nan")}),
                                         ("field", " "), ("field", None), ("reviewer", ""), ("reason", " \t"), ("reason", None)])
def test_invalid_value_context_and_provenance_cannot_append_partial_revisions(tmp_path, field, value):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        case = scenario(store)
        first = propose(store, case)
        supplied = payload(case)
        supplied[field] = value
        before = audit(store, case["project_id"])
        for operation in (lambda: propose(store, case, supplied), lambda: revise(store, case, first, supplied)):
            with pytest.raises(ValueError): operation()
            assert audit(store, case["project_id"]) == before


@pytest.mark.parametrize("decision,reviewer,reason", [("include", "Bob", "Reason"), ("", "Bob", "Reason"), ("confirm", "", "Reason"), ("reject", "Bob", ""), ("reject", "Bob", "  ")])
def test_verification_validation_and_adjudication_prerequisite_preserve_history(tmp_path, decision, reviewer, reason):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        case = scenario(store)
        revision = propose(store, case)
        with pytest.raises(ValueError):
            store.adjudicate_evidence(case["project_id"], revision["id"], "confirm", "Coordinator", "No review yet")
        store.review_evidence(case["project_id"], revision["id"], "confirm", "Carol", "Allows adjudication probe")
        before = audit(store, case["project_id"])
        for method in (store.review_evidence, store.adjudicate_evidence):
            with pytest.raises(ValueError): method(case["project_id"], revision["id"], decision, reviewer, reason)
            assert audit(store, case["project_id"]) == before


@pytest.mark.parametrize("judgment,appraisal", [
    ("", {"instrument": "Software Fixture Appraisal", "instrument_version": "0.1-synthetic", "domain": "Source scope"}),
    ({"score": 1}, {"instrument": "Software Fixture Appraisal", "instrument_version": "0.1-synthetic", "domain": "Source scope"}),
    ("Manual judgment", None), ("Manual judgment", {}),
    ("Manual judgment", {"instrument": "Fixture", "instrument_version": "v1", "domain": " "}),
    ("Manual judgment", {"instrument": "Fixture", "instrument_version": "v1", "domain": "Domain", "score": 1}),
])
def test_appraisal_requires_explicit_instrument_version_domain_and_string_judgment(tmp_path, judgment, appraisal):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        case = scenario(store)
        supplied = payload(case)
        supplied["value"] = judgment
        before = audit(store, case["project_id"])
        with pytest.raises(ValueError):
            propose(store, case, supplied, kind="appraisal", appraisal=appraisal)
        assert audit(store, case["project_id"]) == before


def test_appraisal_revision_preserves_kind_and_replaces_all_entered_instrument_metadata(tmp_path):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        case = scenario(store)
        supplied = payload(case)
        supplied.update(field="synthetic_source_scope", value="Entered scope judgment")
        instrument = {"instrument": "Software Fixture Appraisal", "instrument_version": "0.1-synthetic", "domain": "Source scope"}
        first = propose(store, case, supplied, kind="appraisal", appraisal=instrument)
        assert first["appraisal"] == instrument and first["kind"] == "appraisal"
        before = audit(store, case["project_id"])
        # Appraisal metadata cannot be omitted on a complete replacement revision.
        with pytest.raises(ValueError): revise(store, case, first, supplied)
        with pytest.raises(ValueError): propose(store, case, supplied, kind="finding", appraisal=instrument)
        with pytest.raises(ValueError): propose(store, case, supplied, kind="risk_score")
        assert audit(store, case["project_id"]) == before
        supplied.update(reviewer="Carol", reason="Revised manual instrument choice", value="Revised scope judgment")
        replacement = {"instrument": "Another Software Fixture", "instrument_version": "2.0-invented", "domain": "Revised source domain"}
        second = store.revise_evidence(case["project_id"], first["evidence_id"], **supplied, appraisal=replacement)
        assert second["kind"] == "appraisal" and second["appraisal"] == replacement and second["revision"] == 2
        assert_revision(store, case, second, supplied)
        assert first["appraisal"] == instrument and store.list_evidence_revisions(case["project_id"])[0] == first


def test_duplicate_slots_and_same_study_reports_are_retained_without_pooling_or_merge(tmp_path):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        case = scenario(store)
        first = propose(store, case)
        second = propose(store, case)
        assert first["evidence_id"] != second["evidence_id"]
        store.record_decision(case["project_id"], case["other_record_id"], "title_abstract", "include", "Eligibility reviewer")
        store.set_full_text_status(case["project_id"], case["other_record_id"], "retrieved", "Source custodian")
        store.record_decision(case["project_id"], case["other_record_id"], "full_text", "include", "Eligibility reviewer")
        store.record_study_links(case["project_id"], case["other_record_id"], [case["study_id"]], "Linker", "Companion report of same invented study")
        item = sources()["text_v1"]
        companion_doc = store.attach_document(case["project_id"], case["other_record_id"], (FIXTURES / item["file"]).read_bytes(), "txt", "Custodian", "Companion source")
        companion = {**case, "record_id": case["other_record_id"], "document": companion_doc}
        supplied = payload(companion)
        supplied.update(value={"literal": "Deliberately different entered marker"}, reason="Keep cross-report entry visible")
        third = propose(store, companion, supplied)
        for revision in (first, second, third):
            store.review_evidence(case["project_id"], revision["id"], "confirm", "Bob", "Manual structural-source check")
        rows = store.list_evidence(case["project_id"], verified_only=True)
        assert len(rows) == 3 and [row["evidence_id"] for row in rows] == [first["evidence_id"], second["evidence_id"], third["evidence_id"]]
        assert rows[0]["current_revision"]["value"] != rows[2]["current_revision"]["value"]
        assert store.counts(case["project_id"])["reports_included"] == 2 and store.counts(case["project_id"])["included_studies"] == 1


def test_all_evidence_api_ownership_filters_and_unknown_ids_fail_without_cross_project_changes(tmp_path):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        case = scenario(store)
        other = scenario(store, title="Other evidence review")
        first, foreign = propose(store, case), propose(store, other)
        other_doc = store.attach_document(case["project_id"], case["other_record_id"], b"Different report source", "txt", "Custodian", "Ownership probe")
        before = audit(store, case["project_id"]), audit(store, other["project_id"])
        operations = [
            lambda: store.list_evidence("unknown"),
            lambda: store.list_evidence(case["project_id"], other["record_id"]),
            lambda: store.list_evidence(case["project_id"], "unknown-record"),
            lambda: store.list_evidence_revisions(case["project_id"], foreign["evidence_id"]),
            lambda: store.list_evidence_reviews(case["project_id"], foreign["evidence_id"]),
            lambda: store.list_evidence_revisions(case["project_id"], "unknown-evidence"),
            lambda: store.list_evidence_reviews("unknown"),
            lambda: store.revise_evidence(case["project_id"], foreign["evidence_id"], **payload(case)),
        ]
        for field, invalid in (("document_id", other["document"]["id"]), ("document_id", other_doc["id"]),
                               ("study_id", other["study_id"]), ("study_id", "unknown-study"), ("document_id", "unknown-document")):
            supplied = payload(case)
            supplied[field] = invalid
            operations += [lambda supplied=supplied: propose(store, case, supplied), lambda supplied=supplied: revise(store, case, first, supplied)]
        for method in (store.review_evidence, store.adjudicate_evidence):
            operations += [lambda method=method: method(case["project_id"], foreign["id"], "confirm", "Bob", "Foreign revision"),
                           lambda method=method: method(case["project_id"], "unknown-revision", "confirm", "Bob", "Unknown revision")]
        for operation in operations:
            with pytest.raises(ValueError): operation()
            assert (audit(store, case["project_id"]), audit(store, other["project_id"])) == before


def test_audit_and_verified_exports_exact_json_formula_safe_csv_and_determinism(tmp_path):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        case = scenario(store)
        baseline = audit(store, case["project_id"])
        supplied = payload(case)
        supplied.update(field="=synthetic_field", value="=Manually entered fixture value", reviewer="@manual-author", reason='=Source checked, "quoted"\nExact provenance')
        confirmed = propose(store, case, supplied)
        event = store.review_evidence(case["project_id"], confirmed["id"], "confirm", "@independent-reviewer", "-Manual quote check")
        proposed = propose(store, case)
        rejected = propose(store, case)
        store.review_evidence(case["project_id"], rejected["id"], "reject", "Bob", "Manual rejection remains visible")
        directory = tmp_path / "evidence-export"
        directory.mkdir()
        (directory / "notes.txt").write_text("Preserve independent annotation")
        result = store.export_project(case["project_id"], directory)
        bundle = json.loads((directory / "project.json").read_text())
        assert len(result["files"]) == 20 and result["counts"] == baseline["counts"]
        assert bundle["evidence"] == store.list_evidence(case["project_id"])
        assert bundle["evidence_revisions"] == store.list_evidence_revisions(case["project_id"])
        assert bundle["evidence_reviews"] == store.list_evidence_reviews(case["project_id"])
        assert bundle["verified_evidence"] == store.list_evidence(case["project_id"], verified_only=True)
        assert len(bundle["verified_evidence"]) == 1 and bundle["verified_evidence"][0]["evidence_id"] == confirmed["evidence_id"]
        assert json.loads((directory / "verified_evidence.json").read_text()) == bundle["verified_evidence"]
        with (directory / "verified_evidence.csv").open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        assert rows[0]["field"] == "'=synthetic_field" and rows[0]["value"] == "'=Manually entered fixture value"
        assert rows[0]["reviewer"] == "'@manual-author" and rows[0]["reason"] == '\'=Source checked, "quoted"\nExact provenance'
        assert rows[0]["state"] == "confirmed" and json.loads(rows[0]["dependency_issues"]) == []
        assert json.loads(rows[0]["anchor"]) == confirmed["anchor"] and json.loads(rows[0]["context"]) == supplied["context"]
        with (directory / "evidence_reviews.csv").open(newline="", encoding="utf-8") as handle:
            reviews = list(csv.DictReader(handle))
        assert reviews[0]["reviewer"] == "'@independent-reviewer" and reviews[0]["reason"] == "'-Manual quote check"
        assert bundle["evidence_reviews"][0] == event
        assert {row["state"] for row in bundle["evidence"]} == {"confirmed", "proposed", "rejected"}
        assert {row["evidence_id"] for row in bundle["evidence"]} == {confirmed["evidence_id"], proposed["evidence_id"], rejected["evidence_id"]}
        assert (directory / "notes.txt").read_text() == "Preserve independent annotation"
        second_directory = tmp_path / "evidence-export-again"
        store.export_project(case["project_id"], second_directory)
        assert {name: (directory / name).read_bytes() for name in result["files"]} == {name: (second_directory / name).read_bytes() for name in result["files"]}
        after = audit(store, case["project_id"])
        for field in ("counts", "records", "documents", "studies", "links", "link_events", "decisions", "retrieval", "runs", "occurrences"):
            assert after[field] == baseline[field]


@pytest.mark.parametrize("mutation", ["revision", "source"])
def test_export_snapshot_never_mixes_concurrent_source_or_evidence_revision_with_old_confirmation(tmp_path, monkeypatch, mutation):
    database = tmp_path / "reviews.sqlite3"
    with ReviewStore(database) as store:
        case = scenario(store)
        revision = propose(store, case)
        store.review_evidence(case["project_id"], revision["id"], "confirm", "Bob", "Checked original revision")
        before = audit(store, case["project_id"])
        with sqlite3.connect(database) as connection:
            assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        original = store.list_records
        triggered = False
        def read_then_commit(project_id):
            nonlocal triggered
            records = original(project_id)
            if not triggered:
                triggered = True
                with ReviewStore(database) as writer:
                    if mutation == "revision":
                        supplied = payload(case)
                        supplied.update(value={"entered": "Concurrent complete replacement"}, reviewer="Carol", reason="Concurrent revision")
                        revise(writer, case, revision, supplied)
                    else:
                        item = sources()["text_v2"]
                        writer.attach_document(case["project_id"], case["record_id"], (FIXTURES / item["file"]).read_bytes(), "txt", "Custodian", "Concurrent source version")
            return records
        monkeypatch.setattr(store, "list_records", read_then_commit)
        directory = tmp_path / "snapshot-export"
        store.export_project(case["project_id"], directory)
        bundle = json.loads((directory / "project.json").read_text())
        assert triggered and bundle["evidence"] == bundle["verified_evidence"] == before["current"]
        assert bundle["evidence_revisions"] == before["revisions"] and bundle["evidence_reviews"] == before["reviews"]
        assert bundle["documents"] == before["documents"] and bundle["counts"] == before["counts"]
        assert store.list_evidence(case["project_id"], verified_only=True) == []
        assert current(store, case, revision["evidence_id"])["state"] == ("proposed" if mutation == "revision" else "stale_source")


@pytest.mark.parametrize("corruption", ["current_payload", "old_payload", "revision_hash", "source_bytes", "source_blocks"])
def test_revision_or_retained_source_tampering_blocks_audit_and_export_before_replacing_files(tmp_path, corruption):
    database = tmp_path / "reviews.sqlite3"
    with ReviewStore(database) as store:
        case = scenario(store)
        first = propose(store, case)
        store.review_evidence(case["project_id"], first["id"], "confirm", "Bob", "Original checked")
        supplied = payload(case)
        supplied.update(reviewer="Carol", reason="New revision")
        second = revise(store, case, first, supplied)
        store.review_evidence(case["project_id"], second["id"], "confirm", "Bob", "New revision checked")
        directory = tmp_path / "preexisting-export"
        result = store.export_project(case["project_id"], directory)
        previous = {name: (directory / name).read_bytes() for name in result["files"]}
    with sqlite3.connect(database) as connection:
        if corruption in {"current_payload", "old_payload"}:
            target = second if corruption == "current_payload" else first
            altered = {key: value for key, value in target.items() if key != "revision_sha256"}
            altered["value"] = {"tampered": "Unsigned accidental change without matching digest"}
            connection.execute("UPDATE evidence_revisions SET payload = ? WHERE id = ?", (json.dumps(altered, ensure_ascii=False), target["id"]))
        elif corruption == "revision_hash":
            connection.execute("UPDATE evidence_revisions SET revision_sha256 = ? WHERE id = ?", ("0" * 64, second["id"]))
        else:
            column, value = ("content", b"Tampered original source") if corruption == "source_bytes" else ("blocks_json", "[]")
            connection.execute(f"UPDATE source_documents SET {column} = ? WHERE id = ?", (value, case["document"]["id"]))
    with ReviewStore(database) as store:
        with pytest.raises(ValueError): store.list_evidence_revisions(case["project_id"])
        with pytest.raises(ValueError): store.list_evidence_reviews(case["project_id"])
        with pytest.raises(ValueError): store.export_project(case["project_id"], directory)
        with pytest.raises(ValueError): store.list_evidence(case["project_id"], verified_only=True)
    assert {name: (directory / name).read_bytes() for name in result["files"]} == previous


def test_reconstructed_legacy_schema_has_no_evidence_side_effect_or_optional_export_files(tmp_path):
    database = tmp_path / "reviews.sqlite3"
    with ReviewStore(database) as store:
        project_id = store.create_project("Legacy bibliography", "scoping", "What was imported?")["id"]
        records = [BibliographicRecord(title="Unscreened generic record", doi="10.99999/legacy-evidence")]
        spec = SearchRunSpec("Legacy import")
        imported = store.import_records(project_id, spec, records, "legacy-evidence-input")
        before = audit(store, project_id)
    with sqlite3.connect(database) as connection:
        for table in ("evidence_review_events", "evidence_revisions", "evidence_entries"):
            connection.execute(f"DROP TABLE {table}")
    with ReviewStore(database) as store:
        assert audit(store, project_id) == before
        assert store.import_records(project_id, spec, records, "legacy-evidence-input") == imported
        directory = tmp_path / "legacy-export"
        result = store.export_project(project_id, directory)
        assert len(result["files"]) == 9 and result["counts"] == before["counts"]
        bundle = json.loads((directory / "project.json").read_text())
        assert not {"evidence", "evidence_revisions", "evidence_reviews", "verified_evidence"}.intersection(bundle)


def test_fresh_evidence_flow_initializes_no_models_settings_dotenv_or_network(tmp_path):
    code = """
import socket, sys, json
sys.path.insert(0,sys.argv[1])
def denied(*args, **kwargs): raise AssertionError('Evidence API opened network')
socket.create_connection=denied
from src.review.store import ReviewStore
from src.review.models import BibliographicRecord,SearchRunSpec
with ReviewStore(sys.argv[2]) as store:
    p=store.create_project('Isolated evidence','systematic','Synthetic source?')['id']
    store.import_records(p,SearchRunSpec('Synthetic'),[BibliographicRecord(title='Fixture report')])
    r=store.list_records(p)[0]['id']
    s=store.create_study(p,'Fixture identity','Linker','Manual source')['id']
    store.record_study_links(p,r,[s],'Linker','Manual association')
    store.record_decision(p,r,'title_abstract','include','Screener')
    store.set_full_text_status(p,r,'retrieved','Custodian')
    store.record_decision(p,r,'full_text','include','Screener')
    d=store.attach_document(p,r,'Source α.'.encode(),'txt','Custodian','Exact source')['id']
    rev=store.propose_evidence(p,r,s,d,'fixture_marker','α',{'notes':'Nonclinical'}, {'block_id':'text:1','start':7,'end':8,'quote':'α'}, 'Alice','Manual value')
    store.review_evidence(p,rev['id'],'confirm','Bob','Independent source check')
    assert len(store.list_evidence(p,verified_only=True))==1
    store.export_project(p,sys.argv[3])
assert not {'torch','chromadb','sentence_transformers','dotenv','src.settings','fitz','pymupdf'}.intersection(sys.modules)
print(json.dumps({'isolated':True}))
"""
    result = subprocess.run([sys.executable, "-c", code, str(ROOT), str(tmp_path / "isolated.sqlite3"), str(tmp_path / "isolated-export")],
                            cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and result.stderr == "", result.stderr
    assert json.loads(result.stdout) == {"isolated": True}
