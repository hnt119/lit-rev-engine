import csv
import json

import pytest

from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.store import ReviewStore


def test_exports_are_deterministic_full_fidelity_and_formula_safe(tmp_path):
    with ReviewStore(tmp_path / "ledger.sqlite3") as store:
        project = store.create_project("Export", "scoping", "Question")
        original = BibliographicRecord(title='=HYPERLINK("bad")', authors=["Smith, Anne", "Study; Group"], pmid="123", abstract="Line one\nLine two", raw={"original": "=formula"})
        spec = SearchRunSpec("PubMed", query="+formula", notes="\tformula", reported_count=10, filters={"a": "b"})
        store.import_records(project["id"], spec, [original])
        record_id = store.list_records(project["id"])[0]["id"]
        store.record_decision(project["id"], record_id, "title_abstract", "exclude", "@Reviewer", '-reason, with "quotes"\nand newline')
        destination = tmp_path / "exports"
        destination.mkdir()
        unrelated = destination / "keep.txt"
        unrelated.write_text("Preserve me")
        result = store.export_project(project["id"], destination)
        first_contents = {name: (destination / name).read_bytes() for name in result["files"]}
        repeated = store.export_project(project["id"], destination)
        assert {name: (destination / name).read_bytes() for name in repeated["files"]} == first_contents
        assert unrelated.read_text() == "Preserve me"
        assert len(result["files"]) == 9
        bundle = json.loads((destination / "project.json").read_text())
        assert bundle["schema_version"] == 1
        assert bundle["occurrences"][0]["record"]["title"] == original.title
        assert bundle["decisions"][0]["reason"] == '-reason, with "quotes"\nand newline'
        assert bundle["counts"] == result["counts"]
        with (destination / "records.csv").open(newline="") as file:
            rows = list(csv.DictReader(file))
        assert rows[0]["title"] == "'" + original.title
        assert rows[0]["abstract"] == original.abstract
        assert json.loads(rows[0]["authors"]) == original.authors
        assert json.loads(rows[0]["raw"]) == original.raw
        with (destination / "search_runs.csv").open(newline="") as file:
            search = list(csv.DictReader(file))[0]
        assert search["query"] == "'+formula"
        assert search["notes"] == "'\tformula"
        assert search["searched_at"] == ""
        assert search["reported_count"] == "10"
        with (destination / "decisions.csv").open(newline="") as file:
            event = list(csv.DictReader(file))[0]
        assert event["reviewer"] == "'@Reviewer"
        assert event["reason"] == "'" + bundle["decisions"][0]["reason"]
        with (destination / "counts.csv").open(newline="") as file:
            counts = {row["metric"]: row["value"] for row in csv.DictReader(file)}
        assert counts["included_studies"] == ""
        assert counts["reconciliation.identification"].lower() == "true"
        with (destination / "exclusions.csv").open(newline="") as file:
            exclusions = list(csv.DictReader(file))
        assert len(exclusions) == 1
        assert exclusions[0]["kind"] == "review"
        assert exclusions[0]["reason"] == event["reason"]


def test_active_exclusion_reasons_revisions_and_adjudication(tmp_path):
    with ReviewStore(":memory:") as store:
        project = store.create_project("Reasons", "systematic", "Question")
        store.import_records(project["id"], SearchRunSpec("PubMed"), [BibliographicRecord(title="Trial")])
        record_id = store.list_records(project["id"])[0]["id"]
        store.record_decision(project["id"], record_id, "title_abstract", "exclude", "Alice", "Old reason")
        store.record_decision(project["id"], record_id, "title_abstract", "exclude", "Alice", "Current reason")
        store.record_decision(project["id"], record_id, "title_abstract", "exclude", "Bob", "Second reason")
        store.export_project(project["id"], tmp_path)
        with (tmp_path / "exclusions.csv").open(newline="") as file:
            exclusion = list(csv.DictReader(file))[0]
        assert exclusion["reason"] == "Alice: Current reason\nBob: Second reason"
        assert json.loads(exclusion["reviewers"]) == ["Alice", "Bob"]
        store.adjudicate(project["id"], record_id, "title_abstract", "exclude", "Lead", "Resolved reason")
        store.export_project(project["id"], tmp_path)
        with (tmp_path / "exclusions.csv").open(newline="") as file:
            exclusion = list(csv.DictReader(file))[0]
        assert exclusion["reason"] == "Resolved reason"
        assert exclusion["kind"] == "adjudication"
        bundle = json.loads((tmp_path / "project.json").read_text())
        assert [event["reason"] for event in bundle["decisions"]] == ["Old reason", "Current reason", "Second reason", "Resolved reason"]


def test_empty_project_exports_and_failed_reconciliation(tmp_path):
    with ReviewStore(":memory:") as store:
        project = store.create_project("Empty", "scoping", "Question")
        result = store.export_project(project["id"], tmp_path / "empty")
        assert result["counts"]["unique_records"] == 0
        assert result["counts"]["all_checks_passed"]
        store.import_records(project["id"], SearchRunSpec("PubMed"), [BibliographicRecord(title="Trial")])
        with store._connection:
            store._connection.execute("UPDATE search_runs SET identified = 50")
        with pytest.raises(ValueError, match="do not reconcile"):
            store.export_project(project["id"], tmp_path / "bad")
        assert not (tmp_path / "bad").exists()
