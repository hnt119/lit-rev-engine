"""Independent manual report/study identity and append-only audit evidence."""

from copy import deepcopy
import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys

import pytest

from src.review.importers import load_records
from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.store import ReviewStore
from src.search.pubmed_search import capture_pubmed_search, verify_pubmed_capture


FIXTURES = Path(__file__).parent / "fixtures" / "studies"
PUBMED = Path(__file__).parent / "fixtures" / "pubmed"
BASE_COUNTS = {
    "records_identified": 8, "duplicate_records_removed": 0, "unique_records": 8,
    "records_awaiting_screening": 1, "records_screened": 7, "records_excluded": 0,
    "records_included_for_full_text": 7, "records_screening_unresolved": 0,
    "reports_awaiting_request": 0, "reports_sought_for_retrieval": 7, "reports_retrieved": 7,
    "reports_not_retrieved": 0, "reports_awaiting_retrieval": 0, "reports_awaiting_assessment": 0,
    "reports_assessed": 7, "reports_included": 6, "reports_excluded": 1,
    "reports_assessment_unresolved": 0, "study_linkage_available": True,
    "reconciliation": {name: True for name in (
        "identification", "screening_progress", "title_abstract", "retrieval_requests",
        "retrieval_progress", "assessment_progress", "full_text", "study_linkage",
    )},
    "all_checks_passed": True,
}
INITIAL_LINK_COUNTS = {
    "reports_included_linked": 3, "reports_included_awaiting_linkage": 2,
    "reports_included_linkage_unresolved": 1, "linked_included_studies": 3,
    "study_linkage_complete": False, "included_studies": None,
}
FINAL_LINK_COUNTS = {
    "reports_included_linked": 6, "reports_included_awaiting_linkage": 0,
    "reports_included_linkage_unresolved": 0, "linked_included_studies": 3,
    "study_linkage_complete": True, "included_studies": 3,
}


@pytest.fixture(autouse=True)
def no_live_dependencies(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Study acceptance attempted network or real sleep")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr("time.sleep", denied)


@pytest.fixture
def oracle():
    value = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    assert value["initial"]["counts"] == INITIAL_LINK_COUNTS
    assert value["final"]["counts"] == FINAL_LINK_COUNTS
    assert value["record_order"] == [f"r{number}" for number in range(1, 9)]
    return value


def new_project(store, label="Manual study review"):
    return store.create_project(label, "systematic", "Which distinct synthetic studies are represented?")["id"]


def import_reports(store, project_id, oracle):
    reports = load_records(FIXTURES / oracle["records_file"])
    store.import_records(project_id, SearchRunSpec(source="Synthetic export"), reports)
    by_doi = {row["doi"]: row["id"] for row in store.list_records(project_id)}
    return {alias: by_doi[doi] for alias, doi in oracle["report_dois"].items()}


def make_studies(store, project_id, oracle):
    result = {}
    for supplied in oracle["studies"]:
        created = store.create_study(project_id, supplied["label"], supplied["reviewer"], supplied["reason"], supplied["identifiers"])
        assert all(created[field] == supplied[field] for field in ("label", "reviewer", "reason", "identifiers"))
        result[supplied["alias"]] = created["id"]
    return result


def screen_fixture(store, project_id, reports, oracle):
    screening = oracle["screening"]
    reviewer = screening["reviewer"]
    for alias in screening["title_abstract_included"]:
        store.record_decision(project_id, reports[alias], "title_abstract", "include", reviewer)
    for alias in screening["full_text_retrieved"]:
        store.set_full_text_status(project_id, reports[alias], "retrieved", reviewer)
    for alias in screening["full_text_included"]:
        store.record_decision(project_id, reports[alias], "full_text", "include", reviewer)
    for excluded in screening["full_text_excluded"]:
        store.record_decision(project_id, reports[excluded["report"]], "full_text", "exclude", reviewer, excluded["reason"])


def apply_event(store, project_id, reports, studies, supplied):
    method = store.adjudicate_study_links if supplied["kind"] == "adjudication" else store.record_study_links
    return method(project_id, reports[supplied["report"]], [studies[alias] for alias in supplied["studies"]],
                  supplied["reviewer"], supplied["reason"])


def fixture_scenario(store, oracle, final=False):
    project_id = new_project(store)
    reports = import_reports(store, project_id, oracle)
    studies = make_studies(store, project_id, oracle)
    screen_fixture(store, project_id, reports, oracle)
    for event in oracle["initial"]["events"]:
        apply_event(store, project_id, reports, studies, event)
    if final:
        for event in oracle["final"]["events"]:
            apply_event(store, project_id, reports, studies, event)
    return project_id, reports, studies


def snapshot(store, project_id):
    return deepcopy({
        "studies": store.list_studies(project_id), "links": store.list_study_links(project_id),
        "events": store.list_study_link_events(project_id), "counts": store.counts(project_id),
        "records": store.list_records(project_id), "runs": store.list_search_runs(project_id),
        "screening": store.list_decisions(project_id), "retrieval": store.list_retrieval_events(project_id),
        "occurrences": store.get_occurrences(project_id),
    })


def assert_partition(counts):
    assert counts["reports_included"] == (counts["reports_included_linked"] + counts["reports_included_awaiting_linkage"]
                                           + counts["reports_included_linkage_unresolved"])
    assert all(counts["reconciliation"].values()) and counts["all_checks_passed"] is True


def assert_states(store, project_id, reports, studies, expected):
    rows = store.list_study_links(project_id)
    assert [row["record_id"] for row in rows] == [reports[f"r{index}"] for index in range(1, 9)]
    events = store.list_study_link_events(project_id)
    for alias, truth in expected.items():
        row = next(row for row in rows if row["record_id"] == reports[alias])
        assert row["project_id"] == project_id and row["state"] == truth["state"]
        assert row["study_ids"] == sorted(studies[name] for name in truth["studies"])
        report_events = [event for event in events if event["record_id"] == reports[alias]]
        if not report_events:
            assert row["active_event_ids"] == []
        elif report_events[-1]["kind"] == "adjudication":
            assert row["active_event_ids"] == [report_events[-1]["id"]]
        else:
            latest = {}
            for event in report_events:
                if event["kind"] == "review":
                    latest[event["reviewer"]] = event["id"]
            assert set(row["active_event_ids"]) == set(latest.values())


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_independent_initial_and_final_totals_distinguish_reports_from_studies(tmp_path, oracle):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = new_project(store)
        reports = import_reports(store, project_id, oracle)
        studies = make_studies(store, project_id, oracle)
        screen_fixture(store, project_id, reports, oracle)
        before_links = snapshot(store, project_id)
        assert all(row["state"] == "pending" for row in before_links["links"])
        assert before_links["counts"]["reports_included_linked"] == 0
        assert before_links["counts"]["reports_included_awaiting_linkage"] == 6
        assert before_links["counts"]["included_studies"] is None
        # Source-asserted alias metadata must not cause automatic identity decisions.
        events = [apply_event(store, project_id, reports, studies, supplied) for supplied in oracle["initial"]["events"]]
        assert store.counts(project_id) == {**BASE_COUNTS, **INITIAL_LINK_COUNTS}
        assert_partition(store.counts(project_id))
        assert_states(store, project_id, reports, studies, oracle["initial"]["links"])
        initial_export = store.export_project(project_id, tmp_path / "initial-export")
        assert initial_export["counts"]["included_studies"] is None and len(initial_export["files"]) == 12
        events.extend(apply_event(store, project_id, reports, studies, supplied) for supplied in oracle["final"]["events"])
        assert store.counts(project_id) == {**BASE_COUNTS, **FINAL_LINK_COUNTS}
        assert_partition(store.counts(project_id))
        assert_states(store, project_id, reports, studies, oracle["final"]["links"])
        assert store.list_study_link_events(project_id) == events and len(events) == 10
        assert [row["id"] for row in store.list_studies(project_id)] == [studies[alias] for alias in ("A", "B", "C", "D", "E")]
        assert store.list_records(project_id) == before_links["records"]
        assert store.list_decisions(project_id) == before_links["screening"]
        assert store.list_retrieval_events(project_id) == before_links["retrieval"]


def test_revision_clearing_adjudication_and_eligibility_changes_preserve_all_history(tmp_path, oracle):
    database = tmp_path / "reviews.sqlite3"
    literal_steps = [(5, 0, 1, 3, False, None, 11), (6, 0, 0, 3, True, 3, 12),
                     (5, 1, 0, 3, False, None, 13), (6, 0, 0, 3, True, 3, 14),
                     (7, 0, 0, 4, True, 4, 14), (6, 0, 0, 3, True, 3, 14)]
    with ReviewStore(database) as store:
        project_id, reports, studies = fixture_scenario(store, oracle, final=True)
        original_events = store.list_study_link_events(project_id)
        for probe, expected in zip(oracle["revision_sequence_after_final"], literal_steps):
            if "event" in probe:
                event = probe["event"]
                apply_event(store, project_id, reports, studies, event)
                row = store.list_study_links(project_id, reports[event["report"]])[0]
                assert row["state"] == probe["changed_link"]["state"]
                assert row["study_ids"] == sorted(studies[name] for name in probe["changed_link"]["studies"])
            else:
                event = probe["screening_event"]
                store.record_decision(project_id, reports[event["report"]], event["stage"], event["decision"], event["reviewer"], event["reason"])
            counts = store.counts(project_id)
            observed = tuple(counts[field] for field in ("reports_included_linked", "reports_included_awaiting_linkage",
                                                        "reports_included_linkage_unresolved", "linked_included_studies",
                                                        "study_linkage_complete", "included_studies"))
            assert observed == expected[:6]
            assert len(store.list_study_link_events(project_id)) == expected[6]
            assert_partition(counts)
        assert store.list_study_link_events(project_id)[:10] == original_events
        assert store.list_study_links(project_id, reports["r3"])[0]["study_ids"] == [studies["C"]]
        assert store.list_study_link_events(project_id, reports["r3"])[0]["study_ids"] == sorted([studies["B"], studies["C"]])
        assert store.list_study_links(project_id, reports["r6"])[0]["study_ids"] == [studies["D"]]
        before = snapshot(store, project_id)
    with ReviewStore(database) as reopened:
        assert snapshot(reopened, project_id) == before


def test_equal_timestamp_events_no_majority_union_and_empty_adjudication(monkeypatch, tmp_path, oracle):
    monkeypatch.setattr("src.review.studies._now", lambda: "2026-10-03T00:00:00+00:00")
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = new_project(store)
        reports = import_reports(store, project_id, oracle)
        studies = make_studies(store, project_id, oracle)
        record_id = reports["r1"]
        events = [store.record_study_links(project_id, record_id, [studies["A"]], "Alice", "Source A"),
                  store.record_study_links(project_id, record_id, [studies["A"]], "Bob", "Source A"),
                  store.record_study_links(project_id, record_id, [studies["B"]], "Carol", "Conflicting source B")]
        row = store.list_study_links(project_id, record_id)[0]
        assert row["state"] == "conflict" and row["study_ids"] == []
        assert set(row["active_event_ids"]) == {event["id"] for event in events}
        events.append(store.adjudicate_study_links(project_id, record_id, [], "Coordinator", "No association established"))
        row = store.list_study_links(project_id, record_id)[0]
        assert row["state"] == "unlinked" and row["active_event_ids"] == [events[-1]["id"]]
        events.append(store.record_study_links(project_id, record_id, [studies["A"]], "Carol", "Revised source A"))
        row = store.list_study_links(project_id, record_id)[0]
        assert row["state"] == "linked" and row["study_ids"] == [studies["A"]]
        assert set(row["active_event_ids"]) == {events[0]["id"], events[1]["id"], events[4]["id"]}
        assert store.list_study_link_events(project_id, record_id) == events
        assert {event["created_at"] for event in events} == {"2026-10-03T00:00:00+00:00"}
        assert all("sequence" not in event for event in events)


def test_empty_and_nonempty_review_sets_disagree_until_both_reviewers_clear(tmp_path, oracle):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id, reports, studies = fixture_scenario(store, oracle, final=True)
        first = store.record_study_links(project_id, reports["r4"], [], "linker-two", "No association established")
        row = store.list_study_links(project_id, reports["r4"])[0]
        assert row["state"] == "conflict" and row["study_ids"] == []
        counts = store.counts(project_id)
        assert counts["reports_included_linked"] == 5 and counts["reports_included_linkage_unresolved"] == 1
        assert counts["included_studies"] is None
        second = store.record_study_links(project_id, reports["r4"], [], "linker-one", "Clear whole proposed set")
        row = store.list_study_links(project_id, reports["r4"])[0]
        assert row["state"] == "unlinked" and row["study_ids"] == []
        assert row["active_event_ids"] == [first["id"], second["id"]]
        counts = store.counts(project_id)
        assert counts["reports_included_awaiting_linkage"] == 1 and counts["reports_included_linkage_unresolved"] == 0
        assert counts["linked_included_studies"] == 3 and counts["included_studies"] is None
        assert_partition(counts)


def test_study_supported_only_by_unresolved_full_text_is_not_currently_included(tmp_path, oracle):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id, reports, studies = fixture_scenario(store, oracle, final=True)
        original_links = store.list_study_link_events(project_id)
        store.record_decision(project_id, reports["r6"], "full_text", "include", "fixture-screener")
        assert store.counts(project_id)["included_studies"] == 4
        store.record_decision(project_id, reports["r6"], "full_text", "exclude", "second-screener", "Unresolved eligibility source")
        counts = store.counts(project_id)
        assert counts["reports_assessment_unresolved"] == 1 and counts["reports_included"] == 6
        assert counts["study_linkage_complete"] is True
        assert counts["linked_included_studies"] == counts["included_studies"] == 3
        assert store.list_study_links(project_id, reports["r6"])[0]["study_ids"] == [studies["D"]]
        assert store.list_study_link_events(project_id) == original_links
        assert_partition(counts)


def test_old_generic_counts_export_and_key_retry_do_not_opt_into_linkage(tmp_path):
    database = tmp_path / "reviews.sqlite3"
    with ReviewStore(database) as store:
        project_id = new_project(store)
        spec = SearchRunSpec(source="Generic legacy import")
        records = [BibliographicRecord(title="Generic report", doi="10.5555/no-linkage")]
        imported = store.import_records(project_id, spec, records, idempotency_key="legacy")
        before = store.counts(project_id)
        assert before["included_studies"] is None and before["study_linkage_available"] is False
        assert "study_linkage" not in before["reconciliation"]
        assert "linked_included_studies" not in before
        assert store.list_studies(project_id) == []
        assert store.list_study_links(project_id)[0]["state"] == "pending"
        assert store.import_records(project_id, spec, records, idempotency_key="legacy") == imported
        assert store.counts(project_id) == before
        exported = store.export_project(project_id, tmp_path / "legacy-export")
        assert len(exported["files"]) == 9
        bundle = json.loads((tmp_path / "legacy-export" / "project.json").read_text())
        assert not {"studies", "study_links", "study_link_events"}.intersection(bundle)
        old_history = store.list_search_runs(project_id), store.get_occurrences(project_id)
    # Reconstruct the prior ledger schema; opening it must add empty linkage
    # tables without rewriting search history, fingerprints, or current counts.
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE study_link_targets")
        connection.execute("DROP TABLE study_link_events")
        connection.execute("DROP TABLE studies")
    with ReviewStore(database) as store:
        assert store.counts(project_id) == before
        assert (store.list_search_runs(project_id), store.get_occurrences(project_id)) == old_history
        assert store.import_records(project_id, spec, records, idempotency_key="legacy") == imported
        assert store.list_studies(project_id) == [] and store.list_study_link_events(project_id) == []
        assert len(store.export_project(project_id, tmp_path / "reopened-legacy-export")["files"]) == 9


@pytest.mark.parametrize("opt_in", ["unused_study", "empty_link_event"])
def test_explicit_linkage_with_zero_confirmed_inclusions_counts_zero_not_unused_inventory(tmp_path, oracle, opt_in):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = new_project(store)
        reports = import_reports(store, project_id, oracle)
        if opt_in == "unused_study":
            study = store.create_study(project_id, "Unused identity", "Alice", "Inventory only")
            store.record_study_links(project_id, reports["r7"], [study["id"]], "Alice", "Link prior to screening")
            assert store.list_records(project_id)[6]["title_abstract_state"] == "pending"
        else:
            store.record_study_links(project_id, reports["r7"], [], "Alice", "No established association")
        counts = store.counts(project_id)
        assert counts["study_linkage_available"] is True and counts["study_linkage_complete"] is True
        assert counts["reports_included"] == counts["linked_included_studies"] == counts["included_studies"] == 0
        assert_partition(counts)


def test_duplicate_labels_and_identifiers_are_metadata_not_automatic_identity_merge(tmp_path):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = new_project(store)
        metadata = {"registry": {"namespace": "SYNTHETIC", "id": "SAME-METADATA"}}
        first = store.create_study(project_id, "Same label", "Alice", "Manual identity 1", metadata)
        second = store.create_study(project_id, "Same label", "Alice", "Manual identity 2", metadata)
        assert first["id"] != second["id"] and len(store.list_studies(project_id)) == 2
        metadata["registry"]["id"] = "Mutated caller value"
        first["identifiers"]["registry"]["id"] = "Mutated returned value"
        assert all(row["identifiers"]["registry"]["id"] == "SAME-METADATA" for row in store.list_studies(project_id))
        store.import_records(project_id, SearchRunSpec(source="Synthetic"), [BibliographicRecord(title="Two-study report")])
        record_id = store.list_records(project_id)[0]["id"]
        store.record_study_links(project_id, record_id, [second["id"], first["id"]], "Alice", "Report supports both manual identities")
        store.record_decision(project_id, record_id, "title_abstract", "include", "Alice")
        store.set_full_text_status(project_id, record_id, "retrieved", "Alice")
        store.record_decision(project_id, record_id, "full_text", "include", "Alice")
        counts = store.counts(project_id)
        assert counts["reports_included"] == 1 and counts["included_studies"] == 2
        assert store.list_study_links(project_id, record_id)[0]["study_ids"] == sorted([first["id"], second["id"]])


@pytest.mark.parametrize("invalid", [None, "study-id", (), {"study-id"}, [""], ["  "], [None], [1], ["duplicate", "duplicate"], ["valid", "unknown"]])
def test_invalid_association_sets_cannot_append_partial_events_or_targets(tmp_path, oracle, invalid):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id, reports, studies = fixture_scenario(store, oracle)
        targets = [studies["A"] if item in ("duplicate", "valid") else item for item in invalid] if isinstance(invalid, list) else invalid
        before = snapshot(store, project_id)
        for method in (store.record_study_links, store.adjudicate_study_links):
            with pytest.raises(ValueError):
                method(project_id, reports["r1"], targets, "Alice", "Invalid-target probe")
            assert snapshot(store, project_id) == before


@pytest.mark.parametrize("label,reviewer,reason,identifiers", [
    ("", "Alice", "Reason", {}), ("Study", "  ", "Reason", {}), ("Study", "Alice", "", {}),
    ("Study", "Alice", "Reason", []), ("Study", "Alice", "Reason", {1: "not a JSON string key"}),
    ("Study", "Alice", "Reason", {"bad": float("nan")}), ("Study", "Alice", "Reason", {"bad": float("inf")}),
    ("Study", "Alice", "Reason", {"bad": {"nonfinite": float("nan")}}),
    ("Study", "Alice", "Reason", {"nested": {1: "ambiguous key"}}),
    ("Study", "Alice", "Reason", {"nested": [{"bad": float("-inf")}]}),
])
def test_invalid_study_metadata_has_no_inventory_or_count_side_effect(tmp_path, label, reviewer, reason, identifiers):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = new_project(store)
        before = snapshot(store, project_id)
        with pytest.raises(ValueError):
            store.create_study(project_id, label, reviewer, reason, identifiers)
        assert snapshot(store, project_id) == before


@pytest.mark.parametrize("reviewer,reason", [("", "Reason"), ("Alice", ""), ("  ", "Reason"), ("Alice", "  "), (None, "Reason")])
def test_link_reviews_and_adjudications_require_reviewer_and_reason(tmp_path, oracle, reviewer, reason):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id, reports, studies = fixture_scenario(store, oracle)
        for method in (store.record_study_links, store.adjudicate_study_links):
            before = snapshot(store, project_id)
            with pytest.raises(ValueError):
                method(project_id, reports["r1"], [studies["A"]], reviewer, reason)
            assert snapshot(store, project_id) == before


def test_unknown_and_cross_project_ids_cannot_create_or_read_associations(tmp_path, oracle):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        first_id, reports, studies = fixture_scenario(store, oracle)
        second_id = new_project(store, "Other review")
        other_reports = import_reports(store, second_id, oracle)
        other_study = store.create_study(second_id, "Other identity", "Bob", "Other project source")["id"]
        before = snapshot(store, first_id)
        calls = [
            lambda: store.create_study("unknown", "Study", "Alice", "Reason"),
            lambda: store.list_studies("unknown"),
            lambda: store.record_study_links(first_id, other_reports["r1"], [studies["A"]], "Alice", "Cross-project report"),
            lambda: store.record_study_links(first_id, reports["r1"], [studies["A"], other_study], "Alice", "Late cross-project target"),
            lambda: store.adjudicate_study_links(first_id, reports["r1"], [other_study], "Alice", "Cross-project target"),
            lambda: store.list_study_links(first_id, other_reports["r1"]),
            lambda: store.list_study_link_events(first_id, other_reports["r1"]),
            lambda: store.list_study_links(first_id, "unknown-record"),
            lambda: store.list_study_link_events("unknown"),
            lambda: store.adjudicate_study_links(first_id, reports["r7"], [], "Coordinator", "No prior review"),
        ]
        for operation in calls:
            with pytest.raises(ValueError):
                operation()
            assert snapshot(store, first_id) == before


def test_linkage_export_exact_provenance_csv_formula_safety_and_determinism(tmp_path, oracle):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id, reports, studies = fixture_scenario(store, oracle, final=True)
        # Preserve formula-like reviewer/reason strings in JSON while escaping CSV.
        store.record_study_links(project_id, reports["r7"], [], "@synthetic-reviewer", "=No association\nSynthetic only")
        directory = tmp_path / "exported"
        directory.mkdir()
        (directory / "notes.txt").write_text("Preserve this annotation", encoding="utf-8")
        exported = store.export_project(project_id, directory)
        assert len(exported["files"]) == 12
        assert {"studies.csv", "study_links.csv", "study_link_events.csv"}.issubset(exported["files"])
        bundle = json.loads((directory / "project.json").read_text(encoding="utf-8"))
        assert bundle["studies"] == store.list_studies(project_id)
        assert bundle["study_links"] == store.list_study_links(project_id)
        assert bundle["study_link_events"] == store.list_study_link_events(project_id)
        assert bundle["counts"] == {**BASE_COUNTS, **FINAL_LINK_COUNTS}
        source_records = load_records(FIXTURES / "records.json")
        assert [row["record"] for row in bundle["occurrences"]] == [asdict(record) for record in source_records]
        studies_csv = read_csv(directory / "studies.csv")
        e_row = next(row for row in studies_csv if row["id"] == studies["E"])
        assert e_row["label"] == "'=SYNTHETIC_UNUSED_STUDY_E"
        assert next(row for row in bundle["studies"] if row["id"] == studies["E"])["label"] == "=SYNTHETIC_UNUSED_STUDY_E"
        assert [json.loads(row["identifiers"]) for row in studies_csv] == [row["identifiers"] for row in bundle["studies"]]
        links_csv = read_csv(directory / "study_links.csv")
        assert [json.loads(row["study_ids"]) for row in links_csv] == [row["study_ids"] for row in bundle["study_links"]]
        assert [json.loads(row["active_event_ids"]) for row in links_csv] == [row["active_event_ids"] for row in bundle["study_links"]]
        assert [row["state"] for row in links_csv] == [row["state"] for row in bundle["study_links"]]
        events_csv = read_csv(directory / "study_link_events.csv")
        assert [json.loads(row["study_ids"]) for row in events_csv] == [row["study_ids"] for row in bundle["study_link_events"]]
        for field in ("id", "project_id", "record_id", "kind", "created_at"):
            assert [row[field] for row in events_csv] == [row[field] for row in bundle["study_link_events"]]
        count_rows = {row["metric"]: row["value"] for row in read_csv(directory / "counts.csv")}
        assert count_rows["included_studies"] == "3" and count_rows["linked_included_studies"] == "3"
        assert count_rows["reports_included_linked"] == "6" and count_rows["study_linkage_complete"] == "True"
        assert count_rows["reconciliation.study_linkage"] == "True"
        assert events_csv[-1]["reviewer"] == "'@synthetic-reviewer"
        assert events_csv[-1]["reason"] == "'=No association\nSynthetic only"
        assert bundle["study_link_events"][-1]["reason"] == "=No association\nSynthetic only"
        assert (directory / "notes.txt").read_text() == "Preserve this annotation"
        second_directory = tmp_path / "exported-again"
        store.export_project(project_id, second_directory)
        assert {name: (directory / name).read_bytes() for name in exported["files"]} == {
            name: (second_directory / name).read_bytes() for name in exported["files"]
        }


@pytest.mark.parametrize("operation", ["counts", "export"])
def test_linkage_snapshot_does_not_mix_second_writer_revision_with_old_counts_or_history(tmp_path, monkeypatch, oracle, operation):
    database = tmp_path / "reviews.sqlite3"
    with ReviewStore(database) as store:
        project_id, reports, studies = fixture_scenario(store, oracle, final=True)
        before = snapshot(store, project_id)
        with sqlite3.connect(database) as connection:
            assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        original_list_records = store.list_records
        triggered = False
        def read_then_commit(pid):
            nonlocal triggered
            rows = original_list_records(pid)
            if not triggered:
                triggered = True
                with ReviewStore(database) as writer:
                    writer.record_study_links(project_id, reports["r1"], [studies["D"]], "linker-one", "Synthetic concurrent replacement")
            return rows
        monkeypatch.setattr(store, "list_records", read_then_commit)
        if operation == "counts":
            assert store.counts(project_id) == before["counts"]
        else:
            result = store.export_project(project_id, tmp_path / "snapshot-export")
            bundle = json.loads((tmp_path / "snapshot-export" / "project.json").read_text())
            assert bundle["counts"] == before["counts"] == result["counts"]
            assert bundle["study_links"] == before["links"]
            assert bundle["study_link_events"] == before["events"]
        assert triggered
        assert store.counts(project_id)["included_studies"] == 4
        assert len(store.list_study_link_events(project_id)) == 11


def test_pubmed_capture_assets_and_receipt_remain_exact_in_linkage_export(tmp_path):
    oracle = json.loads((PUBMED / "manifest.json").read_text())
    responses = [(PUBMED / oracle["search_file"]).read_bytes()]
    responses.extend((PUBMED / batch["response_file"]).read_bytes() for batch in oracle["batches"])
    class Client:
        def request(self, endpoint, params):
            return responses.pop(0)
    capture = capture_pubmed_search(oracle["query"], tmp_path / "capture", client=Client(), batch_size=2)
    from src.search.pubmed_search import import_pubmed_capture
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = new_project(store)
        imported = import_pubmed_capture(store, project_id, capture["directory"])
        original_assets = store.get_search_artifacts(project_id, imported["search_run_id"])
        study = store.create_study(project_id, "Synthetic study", "Alice", "Source checked")
        record_id = store.list_records(project_id)[0]["id"]
        store.record_study_links(project_id, record_id, [study["id"]], "Alice", "Manual association before screening")
        directory = tmp_path / "exported"
        exported = store.export_project(project_id, directory)
        assert len(exported["files"]) == 18
        bundle = json.loads((directory / "project.json").read_text())
        assert len(bundle["studies"]) == 1 and len(bundle["search_artifacts"]) == 6
        assert bundle["search_runs"][0]["execution"] == capture["receipt"]
        for entry in bundle["search_artifacts"]:
            content = (directory / entry["export_file"]).read_bytes()
            assert content == original_assets[entry["name"]]
            assert entry["sha256"] == hashlib.sha256(content).hexdigest()
        replay = directory / "search_captures" / imported["search_run_id"]
        assert verify_pubmed_capture(replay)["receipt"] == capture["receipt"]


def test_study_apis_initialize_no_models_settings_dotenv_or_network_in_fresh_process(tmp_path):
    root = Path(__file__).resolve().parents[1]
    code = """
import json, socket, sys
sys.path.insert(0, sys.argv[1])
def denied(*args, **kwargs):
    raise AssertionError('Study APIs attempted network')
socket.create_connection = denied
from src.review.store import ReviewStore
from src.review.models import BibliographicRecord, SearchRunSpec
with ReviewStore(sys.argv[2]) as store:
    project = store.create_project('Isolated study workflow', 'systematic', 'Which reports?')['id']
    store.import_records(project, SearchRunSpec('Synthetic'), [BibliographicRecord(title='Synthetic report')])
    record = store.list_records(project)[0]['id']
    study = store.create_study(project, 'Synthetic identity', 'Alice', 'Manual source')['id']
    store.record_study_links(project, record, [study], 'Alice', 'Manual association')
    assert store.list_study_links(project)[0]['state'] == 'linked'
    store.export_project(project, sys.argv[3])
assert not {'torch','chromadb','sentence_transformers','dotenv','src.settings'}.intersection(sys.modules)
print(json.dumps({'isolated': True}))
"""
    result = subprocess.run([sys.executable, "-c", code, str(root), str(tmp_path / "isolated.sqlite3"), str(tmp_path / "isolated-export")],
                            cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"isolated": True}
