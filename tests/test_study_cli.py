"""Synthetic offline study commands exercised through their actual CLI."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.review import cli
from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.store import ReviewStore


SCRIPT = Path(__file__).resolve().parents[1] / "review.py"


def invoke(tmp_path, *args, success=True):
    result = subprocess.run([sys.executable, str(SCRIPT), "--db", str(tmp_path / "ledger.sqlite3"), *args], cwd=tmp_path, text=True, capture_output=True)
    assert (result.returncode == 0) is success, result.stderr
    if success:
        assert result.stderr == ""
        return json.loads(result.stdout)
    assert result.stdout == "" and "Traceback" not in result.stderr
    return result.stderr


def setup_project(tmp_path):
    with ReviewStore(tmp_path / "ledger.sqlite3") as store:
        project_id = store.create_project("Synthetic review", "scoping", "Software question")["id"]
        store.import_records(project_id, SearchRunSpec("synthetic"), [BibliographicRecord(title="Synthetic report one", pmid="1"), BibliographicRecord(title="Synthetic report two", pmid="2")])
        ids = [record["id"] for record in store.list_records(project_id)]
        for record_id in ids:
            store.record_decision(project_id, record_id, "title_abstract", "include", "screener")
            store.set_full_text_status(project_id, record_id, "retrieved", "librarian")
            store.record_decision(project_id, record_id, "full_text", "include", "screener")
    return project_id, ids


def test_many_to_many_cli_counts_adjudication_clear_and_exports(tmp_path):
    project_id, reports = setup_project(tmp_path)
    metadata = {"registry": {"id": "SYNTHETIC-A", "source": ["Invented, Source"]}}
    first = invoke(tmp_path, "study-create", project_id, "--label", "Synthetic A", "--reviewer", "curator", "--reason", "Invented source identity", "--identifiers-json", json.dumps(metadata))
    second = invoke(tmp_path, "study-create", project_id, "--label", "Synthetic B", "--reviewer", "curator", "--reason", "Separate invented source")
    assert invoke(tmp_path, "studies", project_id) == [first, second]
    assert first["identifiers"] == metadata
    a, b = first["id"], second["id"]

    def link(report, reviewer, studies, command="link-studies"):
        flags = [flag for study_id in studies for flag in ("--study-id", study_id)] if studies else ["--clear"]
        return invoke(tmp_path, command, project_id, report, *flags, "--reviewer", reviewer, "--reason", "Synthetic source check")

    first_event = link(reports[0], "Alice", [b, a])
    assert first_event["study_ids"] == sorted([a, b])
    initial = invoke(tmp_path, "counts", project_id)
    assert initial["reports_included"] == 2
    assert initial["linked_included_studies"] == 2
    assert initial["reports_included_awaiting_linkage"] == 1
    assert initial["included_studies"] is None
    link(reports[1], "Alice", [a])
    assert invoke(tmp_path, "counts", project_id)["included_studies"] == 2
    link(reports[0], "Bob", [])
    conflict = invoke(tmp_path, "counts", project_id)
    assert conflict["reports_included_linkage_unresolved"] == 1
    assert conflict["linked_included_studies"] == 1
    assert conflict["included_studies"] is None
    resolved = link(reports[0], "Lead", [a, b], "adjudicate-links")
    selected = invoke(tmp_path, "links", project_id, "--record-id", reports[0])
    assert selected["links"][0]["active_event_ids"] == [resolved["id"]]
    link(reports[0], "Alice", [a])
    assert invoke(tmp_path, "links", project_id, "--record-id", reports[0])["links"][0]["state"] == "conflict"
    link(reports[0], "Bob", [a])
    assert invoke(tmp_path, "counts", project_id)["included_studies"] == 1
    link(reports[0], "Alice", [])
    link(reports[0], "Bob", [])
    cleared = invoke(tmp_path, "counts", project_id)
    assert cleared["reports_included_awaiting_linkage"] == 1 and cleared["included_studies"] is None
    link(reports[0], "Lead", [a, b], "adjudicate-links")
    final = invoke(tmp_path, "counts", project_id)
    assert final["included_studies"] == 2 and final["study_linkage_complete"]
    assert final["all_checks_passed"]
    histories = invoke(tmp_path, "links", project_id)
    assert len(histories["links"]) == 2 and len(histories["events"]) == 9
    assert histories["events"][0] == first_event
    exported = invoke(tmp_path, "export", project_id, str(tmp_path / "export"))
    assert len(exported["files"]) == 12
    assert exported["counts"] == final
    bundle = json.loads((tmp_path / "export/project.json").read_text())
    assert bundle["studies"] == [first, second]
    assert bundle["study_links"] == histories["links"]
    assert bundle["study_link_events"] == histories["events"]


@pytest.mark.parametrize("mode", [[], ["--clear", "--study-id", "unknown"]])
def test_association_mode_is_explicit_and_mutually_exclusive(tmp_path, mode):
    project_id, reports = setup_project(tmp_path)
    error = invoke(tmp_path, "link-studies", project_id, reports[0], *mode, "--reviewer", "Alice", "--reason", "Source", success=False)
    assert "--clear" in error and "--study-id" in error
    with ReviewStore(tmp_path / "ledger.sqlite3") as store:
        assert store.list_study_link_events(project_id) == []


@pytest.mark.parametrize("payload", ["[]", "null", "not json", '{"x":NaN}', '{"x":1e309}', '{"x":1,"x":2}', '{"x":[{"nested":1,"nested":2}]}'])
def test_study_identifier_json_is_unambiguous_and_finite(tmp_path, payload):
    project_id, _ = setup_project(tmp_path)
    error = invoke(tmp_path, "study-create", project_id, "--label", "A", "--reviewer", "curator", "--reason", "Source", "--identifiers-json", payload, success=False)
    assert "study identifiers JSON" in error
    with ReviewStore(tmp_path / "ledger.sqlite3") as store:
        assert store.list_studies(project_id) == []


def test_invalid_targets_reviewers_and_adjudication_leave_no_history(tmp_path):
    project_id, reports = setup_project(tmp_path)
    with ReviewStore(tmp_path / "ledger.sqlite3") as store:
        study = store.create_study(project_id, "A", "curator", "Source")["id"]
        other = store.create_project("Other", "scoping", "Question")["id"]
        wrong_study = store.create_study(other, "B", "curator", "Source")["id"]
    for command, flags, reviewer, reason in [
        ("link-studies", ["--study-id", study, "--study-id", study], "Alice", "Source"),
        ("link-studies", ["--study-id", study, "--study-id", "unknown"], "Alice", "Source"),
        ("link-studies", ["--study-id", wrong_study], "Alice", "Source"),
        ("link-studies", ["--study-id", study], " ", "Source"),
        ("link-studies", ["--study-id", study], "Alice", " "),
        ("adjudicate-links", ["--study-id", study], "Lead", "No existing review"),
    ]:
        invoke(tmp_path, command, project_id, reports[0], *flags, "--reviewer", reviewer, "--reason", reason, success=False)
    invoke(tmp_path, "links", project_id, "--record-id", "unknown", success=False)
    invoke(tmp_path, "studies", "unknown", success=False)
    with ReviewStore(tmp_path / "ledger.sqlite3") as store:
        assert store.list_study_link_events(project_id) == []


@pytest.mark.parametrize("payload", ['{"x":1,"x":2}', '{"array":[{"nested":1,"nested":2}]}', '{"array":[1e309]}'])
def test_shared_json_validation_protects_existing_metadata_commands(tmp_path, capsys, payload):
    database = tmp_path / "ledger.sqlite3"
    code = cli.main(["--db", str(database), "create", "--title", "Synthetic", "--type", "systematic", "--question", "Question", "--eligibility-json", payload])
    output = capsys.readouterr()
    assert code == 1 and output.out == ""
    assert "eligibility JSON" in output.err
    with ReviewStore(database) as store:
        assert store.list_projects() == []
