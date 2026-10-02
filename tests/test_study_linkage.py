"""Manual study-linkage unit evidence against explicitly synthetic source truth."""

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from src.review.importers import load_records
from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.store import ReviewStore


FIXTURES = Path(__file__).parent / "fixtures/studies"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text())


def project(store):
    return store.create_project("Synthetic study linkage", "systematic", "Software question")["id"]


def scenario(store):
    project_id = project(store)
    store.import_records(project_id, SearchRunSpec("synthetic fixture"), load_records(FIXTURES / "records.json"))
    reports = {record["source_id"]: record["id"] for record in store.list_records(project_id)}
    studies = {}
    for item in MANIFEST["studies"]:
        created = store.create_study(project_id, item["label"], item["reviewer"], item["reason"], item["identifiers"])
        studies[item["alias"]] = created["id"]
    screening = MANIFEST["screening"]
    for alias in screening["title_abstract_included"]:
        store.record_decision(project_id, reports[alias], "title_abstract", "include", screening["reviewer"])
        store.set_full_text_status(project_id, reports[alias], "retrieved", "fixture librarian")
    for alias in screening["full_text_included"]:
        store.record_decision(project_id, reports[alias], "full_text", "include", screening["reviewer"])
    for excluded in screening["full_text_excluded"]:
        store.record_decision(project_id, reports[excluded["report"]], "full_text", "exclude", screening["reviewer"], excluded["reason"])
    return project_id, reports, studies


def apply(store, project_id, reports, studies, item):
    if "screening_event" in item:
        event = item["screening_event"]
        return store.record_decision(project_id, reports[event["report"]], event["stage"], event["decision"], event["reviewer"], event["reason"])
    event = item.get("event", item)
    method = store.adjudicate_study_links if event["kind"] == "adjudication" else store.record_study_links
    return method(project_id, reports[event["report"]], [studies[alias] for alias in event["studies"]], event["reviewer"], event["reason"])


def assert_truth(store, project_id, reports, studies, truth):
    counts = store.counts(project_id)
    assert {key: counts[key] for key in truth["counts"]} == truth["counts"]
    assert counts["reconciliation"]["study_linkage"] is True
    assert counts["all_checks_passed"] is True
    if "links" in truth:
        links = {link["record_id"]: link for link in store.list_study_links(project_id)}
        for alias, expected in truth["links"].items():
            assert links[reports[alias]]["state"] == expected["state"]
            assert links[reports[alias]]["study_ids"] == sorted(studies[study] for study in expected["studies"])


def test_fixture_initial_final_and_revision_counts_reconcile(tmp_path):
    database = tmp_path / "ledger.sqlite3"
    with ReviewStore(database) as store:
        project_id, reports, studies = scenario(store)
        for event in MANIFEST["initial"]["events"]:
            apply(store, project_id, reports, studies, event)
        assert_truth(store, project_id, reports, studies, MANIFEST["initial"])
        initial = store.list_study_link_events(project_id)
        for event in MANIFEST["final"]["events"]:
            apply(store, project_id, reports, studies, event)
        assert_truth(store, project_id, reports, studies, MANIFEST["final"])
        for revision in MANIFEST["revision_sequence_after_final"]:
            apply(store, project_id, reports, studies, revision)
            assert_truth(store, project_id, reports, studies, revision)
            assert len(store.list_study_link_events(project_id)) == revision["link_event_count"]
        assert store.list_study_link_events(project_id)[:len(initial)] == initial
        saved = store.list_study_link_events(project_id), store.list_study_links(project_id), store.counts(project_id)
    with ReviewStore(database) as store:
        assert (store.list_study_link_events(project_id), store.list_study_links(project_id), store.counts(project_id)) == saved


def test_no_opt_in_preserves_count_dictionary_and_nine_export_files(tmp_path):
    database = tmp_path / "ledger.sqlite3"
    with ReviewStore(database) as store:
        project_id = project(store)
        store.import_records(project_id, SearchRunSpec("generic"), [BibliographicRecord(title="Synthetic record")], "old key")
        before = store.counts(project_id)
        assert store.list_studies(project_id) == []
        assert store.list_study_links(project_id)[0]["state"] == "pending"
        assert store.counts(project_id) == before
        assert len(before["reconciliation"]) == 7
        assert before["study_linkage_available"] is False and before["included_studies"] is None
        assert len(store.export_project(project_id, tmp_path / "export")["files"]) == 9
        assert "studies" not in json.loads((tmp_path / "export/project.json").read_text())
    with ReviewStore(database) as store:
        assert store.counts(project_id) == before
        assert store.import_records(project_id, SearchRunSpec("generic"), [BibliographicRecord(title="Synthetic record")], "old key")["new_records"] == 1


def test_study_inventory_or_empty_event_opts_in_but_does_not_add_inclusions():
    with ReviewStore(":memory:") as store:
        first = project(store)
        created = store.create_study(first, "Duplicate allowed", "curator", "Synthetic source", {"registry": "invented"})
        duplicate = store.create_study(first, "Duplicate allowed", "curator", "Synthetic source", {"registry": "invented"})
        assert duplicate["id"] != created["id"]
        assert store.list_studies(first) == [created, duplicate]
        counts = store.counts(first)
        assert counts["study_linkage_available"] and counts["study_linkage_complete"]
        assert counts["included_studies"] == counts["linked_included_studies"] == 0
        second = project(store)
        store.import_records(second, SearchRunSpec("generic"), [BibliographicRecord(title="Synthetic record")])
        record_id = store.list_records(second)[0]["id"]
        store.record_study_links(second, record_id, [], "linker", "No association yet")
        assert store.list_studies(second) == []
        assert store.list_study_links(second)[0]["state"] == "unlinked"
        assert store.counts(second)["included_studies"] == 0


def test_equal_timestamp_events_remain_ordered_and_adjudication_is_invalidated(monkeypatch):
    monkeypatch.setattr("src.review.studies._now", lambda: "2026-10-03T00:00:00+00:00")
    with ReviewStore(":memory:") as store:
        project_id = project(store)
        store.import_records(project_id, SearchRunSpec("generic"), [BibliographicRecord(title="Synthetic record")])
        record_id = store.list_records(project_id)[0]["id"]
        study = store.create_study(project_id, "A", "curator", "Source")["id"]
        first = store.record_study_links(project_id, record_id, [study], "Alice", "Source A")
        second = store.record_study_links(project_id, record_id, [], "Bob", "Not established")
        assert store.list_study_links(project_id)[0]["state"] == "conflict"
        resolved = store.adjudicate_study_links(project_id, record_id, [study], "Lead", "Resolved A")
        assert store.list_study_links(project_id)[0]["active_event_ids"] == [resolved["id"]]
        revision = store.record_study_links(project_id, record_id, [study], "Alice", "Later source check")
        current = store.list_study_links(project_id)[0]
        assert current["state"] == "conflict" and current["study_ids"] == []
        assert current["active_event_ids"] == [second["id"], revision["id"]]
        assert store.list_study_link_events(project_id) == [first, second, resolved, revision]


@pytest.mark.parametrize("identifiers", [[], {1: "bad"}, {"nested": {1: "bad"}}, {"x": float("nan")}, {"x": float("inf")}, {"x": {"not": "a set"}.keys()}])
def test_invalid_study_metadata_does_not_create_an_inventory(identifiers):
    with ReviewStore(":memory:") as store:
        project_id = project(store)
        with pytest.raises(ValueError):
            store.create_study(project_id, "A", "reviewer", "reason", identifiers)
        assert store.list_studies(project_id) == []
        assert not store.counts(project_id)["study_linkage_available"]


def test_cyclic_study_metadata_fails_without_writes():
    identifiers = {}
    identifiers["cycle"] = identifiers
    with ReviewStore(":memory:") as store:
        project_id = project(store)
        with pytest.raises(ValueError, match="cyclic"):
            store.create_study(project_id, "A", "reviewer", "reason", identifiers)
        assert store.list_studies(project_id) == []


def test_invalid_targets_cross_project_inputs_and_adjudication_are_atomic():
    with ReviewStore(":memory:") as store:
        project_id, other = project(store), project(store)
        store.import_records(project_id, SearchRunSpec("generic"), [BibliographicRecord(title="Synthetic record")])
        record_id = store.list_records(project_id)[0]["id"]
        study = store.create_study(project_id, "A", "curator", "Source")["id"]
        wrong_study = store.create_study(other, "B", "curator", "Source")["id"]
        for targets, reviewer, reason in [(None, "Alice", "reason"), ((study,), "Alice", "reason"), ([study, study], "Alice", "reason"), ([study, "unknown"], "Alice", "reason"), ([study, wrong_study], "Alice", "reason"), ([study, " "], "Alice", "reason"), ([study], " ", "reason"), ([study], "Alice", " ")]:
            with pytest.raises(ValueError):
                store.record_study_links(project_id, record_id, targets, reviewer, reason)
            assert store.list_study_link_events(project_id) == []
            assert store._connection.execute("SELECT COUNT(*) FROM study_link_targets").fetchone()[0] == 0
        with pytest.raises(ValueError, match="existing review"):
            store.adjudicate_study_links(project_id, record_id, [study], "Lead", "No review")
        for method, args in [(store.record_study_links, ([study], "Alice", "Source")), (store.adjudicate_study_links, ([study], "Lead", "Source")), (store.list_study_links, ()), (store.list_study_link_events, ())]:
            with pytest.raises(ValueError, match="Unknown record"):
                method(other, record_id, *args)
        for method in (store.list_studies, store.list_study_links, store.list_study_link_events):
            with pytest.raises(ValueError, match="Unknown project"):
                method("unknown")
        event = store.record_study_links(project_id, record_id, [study], "Alice", "Source")
        with pytest.raises(sqlite3.IntegrityError):
            with store._connection:
                store._connection.execute("INSERT INTO study_link_targets VALUES (?, ?, ?)", (project_id, event["id"], wrong_study))
        assert store.list_study_link_events(project_id) == [event]


def test_linkage_exports_are_deterministic_and_formula_safe(tmp_path):
    with ReviewStore(":memory:") as store:
        project_id, reports, studies = scenario(store)
        for event in MANIFEST["initial"]["events"]:
            apply(store, project_id, reports, studies, event)
        destination = tmp_path / "export"
        destination.mkdir()
        (destination / "notes.txt").write_text("Preserve me")
        result = store.export_project(project_id, destination)
        original = {name: (destination / name).read_bytes() for name in result["files"]}
        assert len(original) == 12
        assert store.export_project(project_id, destination) == result
        assert {name: (destination / name).read_bytes() for name in result["files"]} == original
        assert (destination / "notes.txt").read_text() == "Preserve me"
        bundle = json.loads((destination / "project.json").read_text())
        assert bundle["study_links"] == store.list_study_links(project_id)
        assert bundle["study_link_events"] == store.list_study_link_events(project_id)
        with (destination / "studies.csv").open(newline="") as file:
            study_rows = list(csv.DictReader(file))
        unused = next(row for row in study_rows if row["id"] == studies["E"])
        assert unused["label"] == "'=SYNTHETIC_UNUSED_STUDY_E"
        assert bundle["studies"][-1]["label"] == "=SYNTHETIC_UNUSED_STUDY_E"
        with (destination / "study_links.csv").open(newline="") as file:
            links = list(csv.DictReader(file))
        linked = next(row for row in links if row["record_id"] == reports["r3"])
        assert json.loads(linked["study_ids"]) == sorted([studies["B"], studies["C"]])
        with (destination / "study_link_events.csv").open(newline="") as file:
            events = list(csv.DictReader(file))
        assert len(events) == len(MANIFEST["initial"]["events"])
        assert all(json.loads(event["study_ids"]) == sorted(json.loads(event["study_ids"])) for event in events)
