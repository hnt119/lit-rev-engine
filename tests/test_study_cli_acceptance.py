"""Independent offline command-line report/study linkage acceptance."""

from copy import deepcopy
import csv
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys

import pytest

from src.review import cli
from src.review.importers import load_records
from src.review.models import SearchRunSpec
from src.review.store import ReviewStore


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "studies"
COMMON = {
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
    )}, "all_checks_passed": True,
}
INITIAL = {
    "reports_included_linked": 3, "reports_included_awaiting_linkage": 2,
    "reports_included_linkage_unresolved": 1, "linked_included_studies": 3,
    "study_linkage_complete": False, "included_studies": None,
}
FINAL = {
    "reports_included_linked": 6, "reports_included_awaiting_linkage": 0,
    "reports_included_linkage_unresolved": 0, "linked_included_studies": 3,
    "study_linkage_complete": True, "included_studies": 3,
}


@pytest.fixture(autouse=True)
def no_live_dependencies(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Study CLI attempted network or real sleep")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr("time.sleep", denied)


def run_cli(directory, database, *arguments, success=True):
    environment = os.environ.copy()
    environment.pop("NCBI_EMAIL", None)
    environment.pop("NCBI_API_KEY", None)
    result = subprocess.run([sys.executable, str(ROOT / "review.py"), "--db", str(database), *map(str, arguments)],
                            cwd=directory, env=environment, capture_output=True, text=True, timeout=15)
    if success:
        assert result.returncode == 0 and result.stderr == "", result.stderr
        return json.loads(result.stdout)
    assert result.returncode != 0 and result.stderr.strip() and result.stdout.strip() == ""
    assert "Traceback" not in result.stderr
    return result.stderr


def state(database, project_id):
    with ReviewStore(database) as store:
        return deepcopy({
            "projects": store.list_projects(), "studies": store.list_studies(project_id),
            "links": store.list_study_links(project_id), "events": store.list_study_link_events(project_id),
            "counts": store.counts(project_id), "records": store.list_records(project_id),
            "runs": store.list_search_runs(project_id), "occurrences": store.get_occurrences(project_id),
            "decisions": store.list_decisions(project_id), "retrieval": store.list_retrieval_events(project_id),
        })


@pytest.fixture
def prepared(tmp_path):
    database = tmp_path / "ledger with spaces" / "reviews.sqlite3"
    with ReviewStore(database) as store:
        project_id = store.create_project("CLI validation", "systematic", "Which synthetic studies?")["id"]
        other_id = store.create_project("Independent other project", "scoping", "Other question")["id"]
        reports = load_records(FIXTURES / "records.json")
        store.import_records(project_id, SearchRunSpec("Synthetic input"), reports)
        store.import_records(other_id, SearchRunSpec("Synthetic input"), reports)
        record_id = store.list_records(project_id)[0]["id"]
        other_record = store.list_records(other_id)[0]["id"]
        study_id = store.create_study(project_id, "Identity A", "Alice", "Invented source")["id"]
        other_study = store.create_study(other_id, "Identity B", "Bob", "Other source")["id"]
        store.record_study_links(project_id, record_id, [study_id], "Alice", "Prior review permits adjudication")
    return database, project_id, record_id, study_id, other_id, other_record, other_study


def association_args(event, project_id, reports, studies):
    command = "adjudicate-links" if event["kind"] == "adjudication" else "link-studies"
    args = [command, project_id, reports[event["report"]]]
    if event["studies"]:
        for alias in event["studies"]:
            args += ["--study-id", studies[alias]]
    else:
        args += ["--clear"]
    return args + ["--reviewer", event["reviewer"], "--reason", event["reason"]]


def test_exact_subprocess_workflow_counts_revisions_and_auditable_exports(tmp_path):
    oracle = json.loads((FIXTURES / "manifest.json").read_text())
    assert oracle["initial"]["counts"] == INITIAL and oracle["final"]["counts"] == FINAL
    database = tmp_path / "ledger with spaces" / "reviews.sqlite3"
    project_id = run_cli(tmp_path, database, "create", "--title", "Manual report to study review", "--type", "systematic",
                         "--question", "Which distinct synthetic studies are represented?")["id"]
    source = tmp_path / "source export with spaces.json"
    source.write_bytes((FIXTURES / "records.json").read_bytes())
    imported = run_cli(tmp_path, database, "import", project_id, source, "--source", "Synthetic export", "--import-key", "study-input")
    assert imported["identified"] == imported["new_records"] == 8 and imported["duplicates"] == 0
    reports = {row["source_id"]: row["id"] for row in run_cli(tmp_path, database, "records", project_id)}
    studies, inventory = {}, []
    for item in oracle["studies"]:
        created = run_cli(tmp_path, database, "study-create", project_id, "--label", item["label"],
                          "--reviewer", item["reviewer"], "--reason", item["reason"], "--identifiers-json", json.dumps(item["identifiers"]))
        assert all(created[field] == item[field] for field in ("label", "reviewer", "reason", "identifiers"))
        studies[item["alias"]] = created["id"]
        inventory.append(created)
    assert run_cli(tmp_path, database, "studies", project_id) == inventory
    screening = oracle["screening"]
    for alias in screening["title_abstract_included"]:
        run_cli(tmp_path, database, "screen", project_id, reports[alias], "--stage", "title_abstract", "--decision", "include", "--reviewer", screening["reviewer"])
    for alias in screening["full_text_retrieved"]:
        run_cli(tmp_path, database, "fulltext", project_id, reports[alias], "--status", "retrieved", "--reviewer", screening["reviewer"])
    for alias in screening["full_text_included"]:
        run_cli(tmp_path, database, "screen", project_id, reports[alias], "--stage", "full_text", "--decision", "include", "--reviewer", screening["reviewer"])
    for excluded in screening["full_text_excluded"]:
        run_cli(tmp_path, database, "screen", project_id, reports[excluded["report"]], "--stage", "full_text", "--decision", "exclude",
                "--reviewer", screening["reviewer"], "--reason", excluded["reason"])
    eligibility_before = run_cli(tmp_path, database, "decisions", project_id)
    events = [run_cli(tmp_path, database, *association_args(event, project_id, reports, studies)) for event in oracle["initial"]["events"]]
    assert run_cli(tmp_path, database, "counts", project_id) == {**COMMON, **INITIAL}
    current = run_cli(tmp_path, database, "links", project_id)
    assert set(current) == {"links", "events"} and current["events"] == events
    assert [row["record_id"] for row in current["links"]] == [reports[f"r{index}"] for index in range(1, 9)]
    for alias, truth in oracle["initial"]["links"].items():
        row = next(row for row in current["links"] if row["record_id"] == reports[alias])
        assert row["state"] == truth["state"] and row["study_ids"] == sorted(studies[study] for study in truth["studies"])
    r3 = run_cli(tmp_path, database, "links", project_id, "--record-id", reports["r3"])
    assert len(r3["links"]) == len(r3["events"]) == 1
    assert r3["links"][0]["study_ids"] == sorted([studies["B"], studies["C"]])
    events += [run_cli(tmp_path, database, *association_args(event, project_id, reports, studies)) for event in oracle["final"]["events"]]
    assert len(events) == 10 and run_cli(tmp_path, database, "counts", project_id) == {**COMMON, **FINAL}
    literal_revisions = [(5, 0, 1, 3, False, None), (6, 0, 0, 3, True, 3), (5, 1, 0, 3, False, None),
                         (6, 0, 0, 3, True, 3), (7, 0, 0, 4, True, 4), (6, 0, 0, 3, True, 3)]
    for probe, expected in zip(oracle["revision_sequence_after_final"], literal_revisions):
        if "event" in probe:
            events.append(run_cli(tmp_path, database, *association_args(probe["event"], project_id, reports, studies)))
        else:
            event = probe["screening_event"]
            run_cli(tmp_path, database, "screen", project_id, reports[event["report"]], "--stage", event["stage"], "--decision", event["decision"],
                    "--reviewer", event["reviewer"], "--reason", event["reason"])
        counts = run_cli(tmp_path, database, "counts", project_id)
        assert tuple(counts[field] for field in INITIAL) == expected
        assert counts["all_checks_passed"] and all(counts["reconciliation"].values())
    assert len(events) == 14
    final_links = run_cli(tmp_path, database, "links", project_id)
    assert final_links["events"] == events
    assert next(row for row in final_links["links"] if row["record_id"] == reports["r3"])["study_ids"] == [studies["C"]]
    decisions = run_cli(tmp_path, database, "decisions", project_id)
    assert decisions["decisions"][:len(eligibility_before["decisions"])] == eligibility_before["decisions"]
    assert decisions["retrieval_events"] == eligibility_before["retrieval_events"]
    directory = tmp_path / "exported review with spaces"
    exported = run_cli(tmp_path, database, "export", project_id, directory)
    assert len(exported["files"]) == 12 and exported["counts"] == {**COMMON, **FINAL}
    bundle = json.loads((directory / "project.json").read_text())
    assert bundle["studies"] == inventory and bundle["study_links"] == final_links["links"]
    assert bundle["study_link_events"] == events and bundle["counts"] == {**COMMON, **FINAL}
    with (directory / "studies.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[-1]["label"] == "'=SYNTHETIC_UNUSED_STUDY_E" and bundle["studies"][-1]["label"] == "=SYNTHETIC_UNUSED_STUDY_E"
    assert [json.loads(row["identifiers"]) for row in rows] == [row["identifiers"] for row in inventory]
    before = state(database, project_id)
    assert run_cli(tmp_path, database, "import", project_id, source, "--source", "Synthetic export", "--import-key", "study-input") == imported
    assert state(database, project_id) == before


@pytest.mark.parametrize("command", ["link-studies", "adjudicate-links"])
@pytest.mark.parametrize("case", ["omitted", "both", "duplicate", "unknown", "blank_id", "late_cross_project", "unknown_record", "cross_project_record"])
def test_invalid_association_modes_and_ids_leave_both_projects_unchanged(tmp_path, prepared, command, case):
    database, project_id, record_id, study_id, other_id, other_record, other_study = prepared
    selected_record = "unknown-record" if case == "unknown_record" else other_record if case == "cross_project_record" else record_id
    modes = {
        "omitted": [], "both": ["--study-id", study_id, "--clear"],
        "duplicate": ["--study-id", study_id, "--study-id", study_id],
        "unknown": ["--study-id", study_id, "--study-id", "unknown-study"],
        "blank_id": ["--study-id", "  "],
        "late_cross_project": ["--study-id", study_id, "--study-id", other_study],
        "unknown_record": ["--study-id", study_id], "cross_project_record": ["--study-id", study_id],
    }
    before = state(database, project_id), state(database, other_id)
    run_cli(tmp_path, database, command, project_id, selected_record, *modes[case], "--reviewer", "Alice", "--reason", "Invalid input probe", success=False)
    assert (state(database, project_id), state(database, other_id)) == before


@pytest.mark.parametrize("command", ["link-studies", "adjudicate-links"])
@pytest.mark.parametrize("reviewer,reason", [("", "Reason"), ("  ", "Reason"), ("Alice", ""), ("Alice", "  ")])
def test_blank_event_provenance_cannot_append_events(tmp_path, prepared, command, reviewer, reason):
    database, project_id, record_id, study_id, *_ = prepared
    before = state(database, project_id)
    run_cli(tmp_path, database, command, project_id, record_id, "--study-id", study_id, "--reviewer", reviewer, "--reason", reason, success=False)
    assert state(database, project_id) == before


@pytest.mark.parametrize("command", ["link-studies", "adjudicate-links"])
def test_explicit_clear_appends_auditable_empty_association(tmp_path, prepared, command):
    database, project_id, record_id, *_ = prepared
    before = state(database, project_id)
    event = run_cli(tmp_path, database, command, project_id, record_id, "--clear", "--reviewer", "Alice", "--reason", "Explicit whole-set clearing")
    after = state(database, project_id)
    assert event["study_ids"] == [] and event["reason"] == "Explicit whole-set clearing"
    assert event["kind"] == ("review" if command == "link-studies" else "adjudication")
    assert after["events"] == before["events"] + [event]
    assert after["links"][0]["state"] == "unlinked" and after["links"][0]["active_event_ids"] == [event["id"]]
    assert after["records"] == before["records"] and after["decisions"] == before["decisions"]


@pytest.mark.parametrize("record", ["unknown", "cross_project"])
def test_optional_record_filter_validates_project_membership(tmp_path, prepared, record):
    database, project_id, _, _, _, other_record, _ = prepared
    before = state(database, project_id)
    run_cli(tmp_path, database, "links", project_id, "--record-id", other_record if record == "cross_project" else "unknown-record", success=False)
    assert state(database, project_id) == before


def test_adjudication_cannot_create_a_first_association_without_review(tmp_path, prepared):
    database, project_id, _, study_id, *_ = prepared
    before = state(database, project_id)
    record_id = before["records"][1]["id"]
    run_cli(tmp_path, database, "adjudicate-links", project_id, record_id, "--study-id", study_id, "--reviewer", "Lead", "--reason", "No prior review", success=False)
    assert state(database, project_id) == before


BAD_JSON = ["{broken", "[]", "null", '"text"', '{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}', '{"x":1e309}',
            '{"x":1,"x":2}', '{"nested":{"x":1,"x":2}}', '{"nested":[{"x":1,"x":2}]}']


@pytest.mark.parametrize("value", BAD_JSON)
def test_identifiers_reject_ambiguous_or_nonfinite_json_without_inventory_change(tmp_path, prepared, value):
    database, project_id, *_ = prepared
    before = state(database, project_id)
    run_cli(tmp_path, database, "study-create", project_id, "--label", "New identity", "--reviewer", "Alice", "--reason", "Source",
            "--identifiers-json", value, success=False)
    assert state(database, project_id) == before


@pytest.mark.parametrize("label,reviewer,reason", [(" ", "Alice", "Reason"), ("Identity", "", "Reason"), ("Identity", "Alice", " ")])
def test_blank_inventory_provenance_cannot_create_study(tmp_path, prepared, label, reviewer, reason):
    database, project_id, *_ = prepared
    before = state(database, project_id)
    run_cli(tmp_path, database, "study-create", project_id, "--label", label, "--reviewer", reviewer, "--reason", reason, success=False)
    assert state(database, project_id) == before


@pytest.mark.parametrize("command", ["study-create", "studies", "link-studies", "adjudicate-links", "links"])
def test_unknown_project_is_rejected_in_each_study_command(tmp_path, prepared, command):
    database, project_id, record_id, study_id, *_ = prepared
    extra = {"study-create": ["--label", "Identity", "--reviewer", "Alice", "--reason", "Source"], "studies": [],
             "link-studies": [record_id, "--study-id", study_id, "--reviewer", "Alice", "--reason", "Source"],
             "adjudicate-links": [record_id, "--clear", "--reviewer", "Alice", "--reason", "Source"], "links": []}
    before = state(database, project_id)
    run_cli(tmp_path, database, command, "unknown-project", *extra[command], success=False)
    assert state(database, project_id) == before


@pytest.mark.parametrize("value", ['{"x":1,"x":2}', '{"nested":{"x":1,"x":2}}', '{"nested":[{"x":1,"x":2}]}', '{"x":NaN}', '{"x":1e309}'])
@pytest.mark.parametrize("command", ["create", "import"])
def test_shared_json_validation_rejects_ambiguous_eligibility_and_filters(tmp_path, prepared, command, value):
    database, project_id, *_ = prepared
    before = state(database, project_id)
    if command == "create":
        arguments = ["create", "--title", "Invalid extra project", "--type", "systematic", "--question", "Question", "--eligibility-json", value]
    else:
        arguments = ["import", project_id, FIXTURES / "records.json", "--source", "Invalid extra import", "--filters-json", value]
    run_cli(tmp_path, database, *arguments, success=False)
    assert state(database, project_id) == before


def test_valid_json_strings_and_default_empty_identifiers_are_retained_exactly(tmp_path, prepared):
    database, project_id, *_ = prepared
    metadata = {"literal": '{"x":1,"x":2}', "nested": [{"finite": 1.25, "flag": True, "value": None}], "registry": "SYNTHETIC\nquoted \"identity\""}
    first = run_cli(tmp_path, database, "study-create", project_id, "--label", "Distinct manual identity", "--reviewer", "Alice", "--reason", "Literal source",
                    "--identifiers-json", json.dumps(metadata))
    assert first["identifiers"] == metadata
    second = run_cli(tmp_path, database, "study-create", project_id, "--label", "Distinct manual identity", "--reviewer", "Alice", "--reason", "Default metadata")
    assert second["identifiers"] == {} and first["id"] != second["id"]
    assert run_cli(tmp_path, database, "studies", project_id)[-2:] == [first, second]


@pytest.mark.parametrize("filtered", [False, True])
def test_cli_links_pairs_current_state_and_history_within_one_wal_snapshot(tmp_path, prepared, monkeypatch, capsys, filtered):
    database, project_id, record_id, study_id, *_ = prepared
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    before = state(database, project_id)
    original = ReviewStore.list_study_links
    triggered = False
    def read_then_commit(store, pid, rid=None):
        nonlocal triggered
        rows = original(store, pid, rid)
        if not triggered:
            triggered = True
            with ReviewStore(database) as writer:
                writer.record_study_links(project_id, record_id, [], "Alice", "Concurrent whole-set clearing")
        return rows
    monkeypatch.setattr(ReviewStore, "list_study_links", read_then_commit)
    arguments = ["--db", str(database), "links", project_id]
    if filtered:
        arguments += ["--record-id", record_id]
    assert cli.main(arguments) == 0
    output = capsys.readouterr()
    assert output.err == ""
    expected_links = [row for row in before["links"] if not filtered or row["record_id"] == record_id]
    expected_events = [row for row in before["events"] if not filtered or row["record_id"] == record_id]
    assert json.loads(output.out) == {"links": expected_links, "events": expected_events}
    assert triggered
    monkeypatch.setattr(ReviewStore, "list_study_links", original)
    after = state(database, project_id)
    assert after["links"][0]["state"] == "unlinked" and len(after["events"]) == len(before["events"]) + 1


def test_fresh_cli_study_commands_load_no_models_settings_dotenv_or_network(tmp_path):
    code = """
import contextlib, io, json, socket, sys
sys.path.insert(0, sys.argv[1])
def denied(*args, **kwargs):
    raise AssertionError('Study CLI opened network')
socket.create_connection = denied
from src.review.cli import main
def invoke(*args):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        assert main(['--db', sys.argv[2], *args]) == 0
    return json.loads(stream.getvalue())
project = invoke('create','--title','Isolated CLI','--type','systematic','--question','Synthetic question')['id']
invoke('import', project, sys.argv[3], '--source', 'Synthetic source')
record = invoke('records', project)[0]['id']
study = invoke('study-create', project, '--label','Synthetic identity','--reviewer','Alice','--reason','Source')['id']
event = invoke('link-studies',project,record,'--study-id',study,'--reviewer','Alice','--reason','Manual source')
assert invoke('links',project,'--record-id',record)['events'] == [event]
assert invoke('studies',project)[0]['id'] == study
invoke('export',project,sys.argv[4])
assert not {'torch','chromadb','sentence_transformers','dotenv','src.settings'}.intersection(sys.modules)
print(json.dumps({'isolated': True}))
"""
    result = subprocess.run([sys.executable, "-c", code, str(ROOT), str(tmp_path / "isolated.sqlite3"), str(FIXTURES / "records.json"), str(tmp_path / "isolated-export")],
                            cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0 and result.stderr == "", result.stderr
    assert json.loads(result.stdout) == {"isolated": True}
