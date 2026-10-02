"""Independent event-ledger, reconciliation, and export acceptance evidence."""

from copy import deepcopy
import csv
import json
from pathlib import Path
import sqlite3

import pytest

from src.review.importers import load_records
from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.store import ReviewStore


FIXTURES = Path(__file__).parent / "fixtures" / "review"
RECONCILIATION_KEYS = {
    "identification", "screening_progress", "title_abstract", "retrieval_requests",
    "retrieval_progress", "assessment_progress", "full_text",
}
EXPECTED_COUNTS = {
    "records_identified": 15,
    "duplicate_records_removed": 2,
    "unique_records": 13,
    "records_awaiting_screening": 1,
    "records_screened": 12,
    "records_excluded": 2,
    "records_included_for_full_text": 8,
    "records_screening_unresolved": 2,
    "reports_awaiting_request": 1,
    "reports_sought_for_retrieval": 7,
    "reports_retrieved": 5,
    "reports_not_retrieved": 1,
    "reports_awaiting_retrieval": 1,
    "reports_awaiting_assessment": 1,
    "reports_assessed": 4,
    "reports_included": 1,
    "reports_excluded": 1,
    "reports_assessment_unresolved": 2,
    "included_studies": None,
    "study_linkage_available": False,
    "reconciliation": {name: True for name in RECONCILIATION_KEYS},
    "all_checks_passed": True,
}
EXPECTED_FILES = {
    "project.json", "records.csv", "search_runs.csv", "occurrences.csv",
    "decisions.csv", "retrieval_events.csv", "counts.json", "counts.csv", "exclusions.csv",
}


def new_project(store):
    return store.create_project("Postoperative monitoring", "systematic", "Which approaches improve monitoring?")["id"]


def one_record(store, project_id):
    store.import_records(project_id, SearchRunSpec(source="Local export"), [
        BibliographicRecord(title="Synthetic report", doi="10.5555/single"),
    ])
    return store.list_records(project_id)[0]["id"]


def state(store, project_id, record_id):
    return next(row for row in store.list_records(project_id) if row["id"] == record_id)


def event_snapshot(store, project_id):
    return deepcopy({
        "records": store.list_records(project_id),
        "decisions": store.list_decisions(project_id),
        "retrieval_events": store.list_retrieval_events(project_id),
        "counts": store.counts(project_id),
    })


def assert_seven_identities(counts):
    assert counts["records_identified"] == counts["duplicate_records_removed"] + counts["unique_records"]
    assert counts["unique_records"] == counts["records_awaiting_screening"] + counts["records_screened"]
    assert counts["records_screened"] == (
        counts["records_excluded"] + counts["records_included_for_full_text"] + counts["records_screening_unresolved"]
    )
    assert counts["records_included_for_full_text"] == counts["reports_awaiting_request"] + counts["reports_sought_for_retrieval"]
    assert counts["reports_sought_for_retrieval"] == (
        counts["reports_retrieved"] + counts["reports_not_retrieved"] + counts["reports_awaiting_retrieval"]
    )
    assert counts["reports_retrieved"] == counts["reports_awaiting_assessment"] + counts["reports_assessed"]
    assert counts["reports_assessed"] == (
        counts["reports_included"] + counts["reports_excluded"] + counts["reports_assessment_unresolved"]
    )
    assert counts["reconciliation"] == {name: True for name in RECONCILIATION_KEYS}
    assert counts["all_checks_passed"] is True
    assert counts["included_studies"] is None
    assert counts["study_linkage_available"] is False


def build_screening_scenario(store):
    project_id = new_project(store)
    reports = load_records(FIXTURES / "screening_records.json")
    store.import_records(project_id, SearchRunSpec(source="PubMed", reported_count=20), reports[:7] + [reports[0]])
    store.import_records(project_id, SearchRunSpec(source="Embase", reported_count=7), reports[7:] + [reports[8]])
    store.import_records(project_id, SearchRunSpec(source="ClinicalTrials.gov", reported_count=0), [])
    identifiers = {row["source_id"]: row["id"] for row in store.list_records(project_id)}
    store.record_decision(project_id, identifiers["r02"], "title_abstract", "exclude", "Alice", "Children only")
    store.record_decision(project_id, identifiers["r03"], "title_abstract", "uncertain", "Alice", "Design unclear")
    store.record_decision(project_id, identifiers["r04"], "title_abstract", "include", "Alice")
    store.record_decision(project_id, identifiers["r04"], "title_abstract", "exclude", "Bob", "Wrong intervention")
    for number in range(5, 13):
        store.record_decision(project_id, identifiers[f"r{number:02}"], "title_abstract", "include", "Alice")
    store.record_decision(project_id, identifiers["r13"], "title_abstract", "exclude", "Alice", "Superseded population reason")
    store.record_decision(project_id, identifiers["r13"], "title_abstract", "exclude", "Bob", "No monitoring outcome")
    store.record_decision(project_id, identifiers["r13"], "title_abstract", "exclude", "Alice", "Revised: healthy volunteers")
    store.set_full_text_status(project_id, identifiers["r06"], "requested", "Librarian")
    store.set_full_text_status(project_id, identifiers["r07"], "requested", "Librarian")
    store.set_full_text_status(project_id, identifiers["r07"], "not_retrieved", "Librarian", "Publisher copy unavailable")
    for number in range(8, 13):
        store.set_full_text_status(project_id, identifiers[f"r{number:02}"], "retrieved", "Librarian")
    store.record_decision(project_id, identifiers["r09"], "full_text", "include", "Alice")
    store.record_decision(project_id, identifiers["r10"], "full_text", "exclude", "Alice", 'Outcome, "quality of life", unavailable\nNo eligible follow-up')
    store.record_decision(project_id, identifiers["r11"], "full_text", "uncertain", "Alice", "Methods require author clarification")
    store.record_decision(project_id, identifiers["r12"], "full_text", "include", "Alice")
    store.record_decision(project_id, identifiers["r12"], "full_text", "exclude", "Bob", "Protocol outcome absent")
    return project_id, identifiers


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_mixed_pending_unresolved_and_complete_states_match_hand_computed_counts(tmp_path):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id, identifiers = build_screening_scenario(store)
        assert store.counts(project_id) == EXPECTED_COUNTS
        assert_seven_identities(store.counts(project_id))
        rows = {row["source_id"]: row for row in store.list_records(project_id)}
        expected_states = {
            "r01": ("pending", "not_requested", "pending"),
            "r02": ("exclude", "not_requested", "pending"),
            "r03": ("uncertain", "not_requested", "pending"),
            "r04": ("conflict", "not_requested", "pending"),
            "r05": ("include", "not_requested", "pending"),
            "r06": ("include", "requested", "pending"),
            "r07": ("include", "not_retrieved", "pending"),
            "r08": ("include", "retrieved", "pending"),
            "r09": ("include", "retrieved", "include"),
            "r10": ("include", "retrieved", "exclude"),
            "r11": ("include", "retrieved", "uncertain"),
            "r12": ("include", "retrieved", "conflict"),
            "r13": ("exclude", "not_requested", "pending"),
        }
        for key, expected in expected_states.items():
            assert tuple(rows[key][field] for field in ("title_abstract_state", "full_text_status", "full_text_state")) == expected
        runs = store.list_search_runs(project_id)
        assert [(run["source"], run["identified"], run["new_records"], run["duplicates"]) for run in runs] == [
            ("PubMed", 8, 7, 1), ("Embase", 7, 6, 1), ("ClinicalTrials.gov", 0, 0, 0),
        ]
        assert sum(run["identified"] for run in runs) == EXPECTED_COUNTS["records_identified"]
        assert sum(run["new_records"] for run in runs) == EXPECTED_COUNTS["unique_records"]
        assert sum(run["duplicates"] for run in runs) == EXPECTED_COUNTS["duplicate_records_removed"]
        assert len(store.get_occurrences(project_id, identifiers["r09"])) == 2


def test_revisions_disagreement_and_adjudication_invalidation_are_append_only(tmp_path, monkeypatch):
    monkeypatch.setattr("src.review.store._now", lambda: "2026-10-03T00:00:00+00:00")
    database = tmp_path / "reviews.sqlite3"
    with ReviewStore(database) as store:
        project_id = new_project(store)
        record_id = one_record(store, project_id)
        events = []
        events.append(store.record_decision(project_id, record_id, "title_abstract", "include", "Alice"))
        events.append(store.record_decision(project_id, record_id, "title_abstract", "exclude", "Bob", "Wrong outcome"))
        assert state(store, project_id, record_id)["title_abstract_state"] == "conflict"
        events.append(store.record_decision(project_id, record_id, "title_abstract", "include", "Bob"))
        assert state(store, project_id, record_id)["title_abstract_state"] == "include"
        events.append(store.record_decision(project_id, record_id, "title_abstract", "uncertain", "Bob", "Need methods"))
        assert state(store, project_id, record_id)["title_abstract_state"] == "conflict"
        events.append(store.adjudicate(project_id, record_id, "title_abstract", "include", "Coordinator", "Protocol resolves question"))
        assert state(store, project_id, record_id)["title_abstract_state"] == "include"
        events.append(store.record_decision(project_id, record_id, "title_abstract", "include", "Alice"))
        assert state(store, project_id, record_id)["title_abstract_state"] == "conflict"
        events.append(store.record_decision(project_id, record_id, "title_abstract", "exclude", "Bob", "Revised: excluded design"))
        assert state(store, project_id, record_id)["title_abstract_state"] == "conflict"
        events.append(store.adjudicate(project_id, record_id, "title_abstract", "exclude", "Coordinator", "Final protocol exclusion"))
        assert state(store, project_id, record_id)["title_abstract_state"] == "exclude"
        assert store.list_decisions(project_id, record_id) == events
        assert len({event["id"] for event in events}) == 8
        assert {event["created_at"] for event in events} == {"2026-10-03T00:00:00+00:00"}
        assert [event["kind"] for event in events] == ["review"] * 4 + ["adjudication", "review", "review", "adjudication"]
        before = event_snapshot(store, project_id)
        assert_seven_identities(before["counts"])
    with ReviewStore(database) as reopened:
        assert event_snapshot(reopened, project_id) == before


def test_invalid_events_and_missing_reasons_are_rejected_without_history_changes(tmp_path):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = new_project(store)
        record_id = one_record(store, project_id)
        with pytest.raises(ValueError):
            store.adjudicate(project_id, record_id, "title_abstract", "include", "Coordinator", "No prior decisions")
        store.record_decision(project_id, record_id, "title_abstract", "include", "Alice")
        store.set_full_text_status(project_id, record_id, "retrieved", "Librarian")
        invalid_operations = [
            lambda: store.record_decision(project_id, record_id, "full_text", "exclude", "Alice"),
            lambda: store.record_decision(project_id, record_id, "full_text", "include", "  "),
            lambda: store.record_decision(project_id, record_id, "full_text", "maybe", "Alice"),
            lambda: store.record_decision(project_id, record_id, "unknown", "include", "Alice"),
            lambda: store.adjudicate(project_id, record_id, "title_abstract", "include", "Coordinator"),
            lambda: store.adjudicate(project_id, record_id, "title_abstract", "exclude", "Coordinator", "  "),
            lambda: store.adjudicate(project_id, record_id, "title_abstract", "include", "", "Reason"),
            lambda: store.set_full_text_status(project_id, record_id, "retrieved", "  "),
            lambda: store.set_full_text_status(project_id, record_id, "unknown", "Librarian"),
        ]
        for operation in invalid_operations:
            before = event_snapshot(store, project_id)
            with pytest.raises(ValueError):
                operation()
            assert event_snapshot(store, project_id) == before
        second_id = new_project(store)
        second_record = one_record(store, second_id)
        store.record_decision(second_id, second_record, "title_abstract", "include", "Alice")
        before = event_snapshot(store, second_id)
        with pytest.raises(ValueError):
            store.set_full_text_status(second_id, second_record, "not_retrieved", "Librarian")
        assert event_snapshot(store, second_id) == before


def test_stage_prerequisites_and_terminal_retrieved_status(tmp_path):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = new_project(store)
        record_id = one_record(store, project_id)
        for operation in (
            lambda: store.set_full_text_status(project_id, record_id, "requested", "Librarian"),
            lambda: store.record_decision(project_id, record_id, "full_text", "include", "Alice"),
        ):
            with pytest.raises(ValueError):
                operation()
        store.record_decision(project_id, record_id, "title_abstract", "include", "Alice")
        with pytest.raises(ValueError):
            store.record_decision(project_id, record_id, "full_text", "include", "Alice")
        store.set_full_text_status(project_id, record_id, "requested", "Librarian")
        with pytest.raises(ValueError):
            store.record_decision(project_id, record_id, "full_text", "include", "Alice")
        store.set_full_text_status(project_id, record_id, "not_retrieved", "Librarian", "Copy unavailable")
        with pytest.raises(ValueError):
            store.record_decision(project_id, record_id, "full_text", "include", "Alice")
        store.set_full_text_status(project_id, record_id, "retrieved", "Librarian", "Copy later obtained")
        for status_value in ("requested", "not_retrieved"):
            before = event_snapshot(store, project_id)
            with pytest.raises(ValueError):
                store.set_full_text_status(project_id, record_id, status_value, "Librarian", "Attempt downgrade before assessment")
            assert event_snapshot(store, project_id) == before
        store.record_decision(project_id, record_id, "full_text", "uncertain", "Alice", "Need protocol")
        before = event_snapshot(store, project_id)
        with pytest.raises(ValueError):
            store.set_full_text_status(project_id, record_id, "not_retrieved", "Librarian", "Attempt downgrade after assessment")
        assert event_snapshot(store, project_id) == before
        store.adjudicate(project_id, record_id, "full_text", "include", "Coordinator", "Protocol confirmed")
        assert state(store, project_id, record_id)["full_text_state"] == "include"
        store.record_decision(project_id, record_id, "full_text", "exclude", "Alice", "Revised design assessment")
        assert state(store, project_id, record_id)["full_text_state"] == "exclude"
        assert_seven_identities(store.counts(project_id))


def test_title_abstract_inclusion_guard_allows_concordant_reviews_only(tmp_path):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = new_project(store)
        record_id = one_record(store, project_id)
        store.record_decision(project_id, record_id, "title_abstract", "include", "Alice")
        store.set_full_text_status(project_id, record_id, "requested", "Librarian")
        store.record_decision(project_id, record_id, "title_abstract", "include", "Bob")
        for operation in (
            lambda: store.record_decision(project_id, record_id, "title_abstract", "exclude", "Bob", "Revision after request"),
            lambda: store.record_decision(project_id, record_id, "title_abstract", "uncertain", "Alice", "Revision after request"),
            lambda: store.adjudicate(project_id, record_id, "title_abstract", "exclude", "Coordinator", "Would invalidate retrieval"),
        ):
            before = event_snapshot(store, project_id)
            with pytest.raises(ValueError):
                operation()
            assert event_snapshot(store, project_id) == before
        store.adjudicate(project_id, record_id, "title_abstract", "include", "Coordinator", "Concordant inclusion confirmed")
        store.record_decision(project_id, record_id, "title_abstract", "include", "Bob")
        assert state(store, project_id, record_id)["title_abstract_state"] == "include"
        assert len(store.list_decisions(project_id, record_id)) == 4


def test_later_concordant_vote_that_invalidates_adjudicated_inclusion_is_rejected(tmp_path):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = new_project(store)
        record_id = one_record(store, project_id)
        store.record_decision(project_id, record_id, "title_abstract", "include", "Alice")
        store.record_decision(project_id, record_id, "title_abstract", "exclude", "Bob", "Wrong outcome")
        store.adjudicate(project_id, record_id, "title_abstract", "include", "Coordinator", "Protocol permits outcome")
        store.set_full_text_status(project_id, record_id, "retrieved", "Librarian")
        before = event_snapshot(store, project_id)
        with pytest.raises(ValueError):
            store.record_decision(project_id, record_id, "title_abstract", "include", "Alice")
        assert event_snapshot(store, project_id) == before
        store.record_decision(project_id, record_id, "title_abstract", "include", "Bob")
        assert state(store, project_id, record_id)["title_abstract_state"] == "include"


@pytest.mark.parametrize("bad_project,bad_record", [(True, False), (False, True), (False, False)])
def test_unknown_or_cross_project_ids_cannot_create_or_read_events(tmp_path, bad_project, bad_record):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        first_id = new_project(store)
        first_record = one_record(store, first_id)
        other_id = new_project(store)
        other_record = one_record(store, other_id)
        target_project = "unknown-project" if bad_project else first_id
        target_record = "unknown-record" if bad_record else other_record
        before = event_snapshot(store, first_id)
        operations = [
            lambda: store.record_decision(target_project, target_record, "title_abstract", "include", "Alice"),
            lambda: store.adjudicate(target_project, target_record, "title_abstract", "include", "Coordinator", "Reason"),
            lambda: store.set_full_text_status(target_project, target_record, "requested", "Librarian"),
            lambda: store.list_decisions(target_project, target_record),
            lambda: store.list_retrieval_events(target_project, target_record),
        ]
        for operation in operations:
            with pytest.raises(ValueError):
                operation()
        assert event_snapshot(store, first_id) == before
        assert state(store, first_id, first_record)["title_abstract_state"] == "pending"


def test_export_reconciles_roundtrips_and_preserves_current_exclusion_reasons(tmp_path):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id, identifiers = build_screening_scenario(store)
        first_directory = tmp_path / "exports-one"
        first_directory.mkdir()
        (first_directory / "unrelated.txt").write_text("Keep this file", encoding="utf-8")
        exported = store.export_project(project_id, first_directory)
        assert set(exported["files"]) == EXPECTED_FILES
        assert Path(exported["directory"]).resolve() == first_directory.resolve()
        assert exported["counts"] == EXPECTED_COUNTS
        assert (first_directory / "unrelated.txt").read_text(encoding="utf-8") == "Keep this file"
        bundle = json.loads((first_directory / "project.json").read_text(encoding="utf-8"))
        assert bundle["schema_version"] == 1
        assert bundle["counts"] == EXPECTED_COUNTS
        assert bundle["project"] == store.get_project(project_id)
        assert bundle["search_runs"] == store.list_search_runs(project_id)
        assert bundle["records"] == store.list_records(project_id)
        assert bundle["occurrences"] == store.get_occurrences(project_id)
        assert bundle["decisions"] == store.list_decisions(project_id)
        assert bundle["retrieval_events"] == store.list_retrieval_events(project_id)
        assert json.loads((first_directory / "counts.json").read_text(encoding="utf-8")) == EXPECTED_COUNTS
        csv_count_rows = read_csv(first_directory / "counts.csv")
        csv_counts = {row["metric"]: row["value"] for row in csv_count_rows}
        assert len(csv_count_rows) == len(csv_counts)
        for metric, expected in EXPECTED_COUNTS.items():
            if metric == "reconciliation":
                for key in RECONCILIATION_KEYS:
                    assert csv_counts[f"reconciliation.{key}"].casefold() == "true"
            elif expected is None:
                assert csv_counts[metric] == ""
            elif isinstance(expected, bool):
                assert csv_counts[metric].casefold() == str(expected).casefold()
            else:
                assert int(csv_counts[metric]) == expected
        csv_records = read_csv(first_directory / "records.csv")
        assert len(csv_records) == 13
        assert {row["id"] for row in csv_records} == set(identifiers.values())
        assert all(json.loads(row["authors"]) == [] for row in csv_records)
        csv_occurrences = read_csv(first_directory / "occurrences.csv")
        assert len(csv_occurrences) == 15
        assert [json.loads(row["record"]) for row in csv_occurrences] == [row["record"] for row in bundle["occurrences"]]
        csv_runs = read_csv(first_directory / "search_runs.csv")
        assert len(csv_runs) == 3
        assert all(json.loads(row["filters"]) == {} for row in csv_runs)
        exclusions = read_csv(first_directory / "exclusions.csv")
        assert len(exclusions) == 3
        assert {(row["record_id"], row["stage"]) for row in exclusions} == {
            (identifiers["r02"], "title_abstract"), (identifiers["r10"], "full_text"), (identifiers["r13"], "title_abstract"),
        }
        current_reasons = json.dumps(exclusions)
        assert "Children only" in current_reasons
        assert "Revised: healthy volunteers" in current_reasons
        assert "No monitoring outcome" in current_reasons
        assert "Superseded population reason" not in current_reasons
        decisions = read_csv(first_directory / "decisions.csv")
        assert "Superseded population reason" in json.dumps(decisions)
        expected_multiline = 'Outcome, "quality of life", unavailable\nNo eligible follow-up'
        assert next(row for row in decisions if row["record_id"] == identifiers["r10"] and row["stage"] == "full_text")["reason"] == expected_multiline
        assert len(read_csv(first_directory / "retrieval_events.csv")) == 8
        second_directory = tmp_path / "exports-two"
        store.export_project(project_id, second_directory)
        assert {name: (first_directory / name).read_bytes() for name in EXPECTED_FILES} == {
            name: (second_directory / name).read_bytes() for name in EXPECTED_FILES
        }
        store.export_project(project_id, first_directory)
        assert (first_directory / "project.json").read_bytes() == (second_directory / "project.json").read_bytes()


def test_unreconciled_export_is_rejected_before_any_destination_replacement(tmp_path, monkeypatch):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = new_project(store)
        one_record(store, project_id)
        good_counts = store.counts(project_id)
        bad_counts = deepcopy(good_counts)
        bad_counts["reconciliation"]["identification"] = False
        bad_counts["all_checks_passed"] = False
        monkeypatch.setattr(store, "counts", lambda pid: deepcopy(bad_counts))
        directory = tmp_path / "exports"
        directory.mkdir()
        (directory / "project.json").write_text("Previously saved output", encoding="utf-8")
        (directory / "unrelated.txt").write_text("Keep this too", encoding="utf-8")
        with pytest.raises(ValueError, match="reconcil"):
            store.export_project(project_id, directory)
        assert (directory / "project.json").read_text(encoding="utf-8") == "Previously saved output"
        assert (directory / "unrelated.txt").read_text(encoding="utf-8") == "Keep this too"
        assert len(list(directory.iterdir())) == 2


def test_export_exclusions_use_adjudication_then_latest_reviewer_reasons(tmp_path):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = new_project(store)
        record_id = one_record(store, project_id)
        store.record_decision(project_id, record_id, "title_abstract", "include", "Alice")
        store.record_decision(project_id, record_id, "title_abstract", "exclude", "Bob", "Superseded Bob reason")
        store.adjudicate(project_id, record_id, "title_abstract", "exclude", "Coordinator", "Active adjudication reason")
        directory = tmp_path / "exports"
        store.export_project(project_id, directory)
        exclusion_text = json.dumps(read_csv(directory / "exclusions.csv"))
        assert "Active adjudication reason" in exclusion_text
        assert "Superseded Bob reason" not in exclusion_text
        store.record_decision(project_id, record_id, "title_abstract", "exclude", "Alice", "Latest Alice reason")
        store.export_project(project_id, directory)
        exclusion_text = json.dumps(read_csv(directory / "exclusions.csv"))
        assert "Active adjudication reason" not in exclusion_text
        assert "Latest Alice reason" in exclusion_text
        assert "Superseded Bob reason" in exclusion_text  # Bob's still-current exclusion vote.


@pytest.mark.parametrize("separator", ["\r", "\n", "\r\n"])
def test_plain_multiline_csv_cells_roundtrip_without_extra_rows(tmp_path, separator):
    # No comma or double quote is present to accidentally force minimal quoting.
    text = "First line" + separator + "Second line"
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = new_project(store)
        store.import_records(project_id, SearchRunSpec(source="Local export", query=text), [
            BibliographicRecord(title="Plain report", abstract=text),
        ])
        record_id = store.list_records(project_id)[0]["id"]
        store.record_decision(project_id, record_id, "title_abstract", "exclude", "Alice", text)
        directory = tmp_path / "exports"
        store.export_project(project_id, directory)
        records = read_csv(directory / "records.csv")
        searches = read_csv(directory / "search_runs.csv")
        decisions = read_csv(directory / "decisions.csv")
        exclusions = read_csv(directory / "exclusions.csv")
        assert len(records) == len(searches) == len(decisions) == len(exclusions) == 1
        assert records[0]["abstract"] == searches[0]["query"] == decisions[0]["reason"] == exclusions[0]["reason"] == text


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
def test_formula_like_csv_cells_are_escaped_and_originals_survive_json(tmp_path, prefix):
    text = prefix + 'HYPERLINK("https://example.invalid", "medical")'
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = store.create_project(text, "scoping", text, protocol=text)["id"]
        record = BibliographicRecord(title=text, authors=["Ng, Ada", "Collective; Team"],
                                     abstract=text, url=text, source_id=text, raw={"original": text})
        store.import_records(project_id, SearchRunSpec(source=text, query=text, notes=text), [record])
        record_id = store.list_records(project_id)[0]["id"]
        store.record_decision(project_id, record_id, "title_abstract", "exclude", text, text)
        directory = tmp_path / "exports"
        store.export_project(project_id, directory)
        csv_record = read_csv(directory / "records.csv")[0]
        assert csv_record["title"] == "'" + text
        assert csv_record["abstract"] == "'" + text
        assert csv_record["url"] == "'" + text
        assert csv_record["source_id"] == "'" + text
        assert json.loads(csv_record["authors"]) == ["Ng, Ada", "Collective; Team"]
        csv_run = read_csv(directory / "search_runs.csv")[0]
        assert csv_run["source"] == csv_run["query"] == csv_run["notes"] == "'" + text
        csv_decision = read_csv(directory / "decisions.csv")[0]
        assert csv_decision["reviewer"] == csv_decision["reason"] == "'" + text
        bundle = json.loads((directory / "project.json").read_text(encoding="utf-8"))
        assert bundle["project"]["title"] == text
        assert bundle["records"][0]["title"] == text
        assert bundle["occurrences"][0]["record"]["raw"]["original"] == text
        assert bundle["search_runs"][0]["query"] == text
        assert bundle["decisions"][0]["reason"] == text


@pytest.mark.parametrize("operation", ["counts", "export"])
def test_counts_and_export_use_one_consistent_read_snapshot_during_concurrent_import(tmp_path, monkeypatch, operation):
    database = tmp_path / "reviews.sqlite3"
    with ReviewStore(database) as store:
        project_id = new_project(store)
        one_record(store, project_id)
        before = store.counts(project_id)
        with sqlite3.connect(database) as mode_connection:
            assert mode_connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        original_list_records = store.list_records
        triggered = False

        def read_then_concurrent_commit(pid):
            nonlocal triggered
            rows = original_list_records(pid)
            if not triggered:
                triggered = True
                with ReviewStore(database) as writer:
                    writer.import_records(project_id, SearchRunSpec(source="Concurrent local export"), [
                        BibliographicRecord(title="Concurrent new report", doi="10.5555/concurrent"),
                    ])
            return rows

        monkeypatch.setattr(store, "list_records", read_then_concurrent_commit)
        if operation == "counts":
            observed = store.counts(project_id)
        else:
            directory = tmp_path / "exports"
            observed = store.export_project(project_id, directory)["counts"]
            bundle = json.loads((directory / "project.json").read_text(encoding="utf-8"))
            assert len(bundle["records"]) == len(bundle["occurrences"]) == len(bundle["search_runs"]) == 1
            assert bundle["counts"] == before
        assert triggered, "The public read seam was not reached; revise evaluation instrumentation"
        assert observed == before
        assert_seven_identities(observed)
        assert store.counts(project_id)["unique_records"] == 2
