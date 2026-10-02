"""Independent source/evidence CLI acceptance with no live dependencies."""

from copy import deepcopy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys

import pytest

from src.review import cli
from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.store import ReviewStore


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "evidence"
SOURCES = {source["alias"]: source for source in json.loads((FIXTURES / "manifest.json").read_text())["fixtures"]}
TRUTH = json.loads((FIXTURES / "extractions.json").read_text())
PROPOSALS = {proposal["id"]: proposal for proposal in TRUTH["proposals"]}


@pytest.fixture(autouse=True)
def no_live_dependencies(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Evidence CLI attempted network or real sleep")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr("time.sleep", denied)


def run_cli(directory, database, *arguments, success=True):
    environment = os.environ.copy()
    for name in ("NCBI_EMAIL", "NCBI_API_KEY"):
        environment.pop(name, None)
    environment.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    result = subprocess.run([sys.executable, str(ROOT / "review.py"), "--db", str(database), *map(str, arguments)],
                            cwd=directory, env=environment, capture_output=True, text=True, timeout=15)
    if success:
        assert result.returncode == 0 and result.stderr == "", result.stderr
        return json.loads(result.stdout)
    assert result.returncode != 0 and result.stderr.strip() and not result.stdout.strip(), result.stdout
    assert "Traceback" not in result.stderr
    return result.stderr


def state(database, project_id):
    with ReviewStore(database) as store:
        return deepcopy({
            "projects": store.list_projects(), "records": store.list_records(project_id), "counts": store.counts(project_id),
            "runs": store.list_search_runs(project_id), "occurrences": store.get_occurrences(project_id),
            "decisions": store.list_decisions(project_id), "retrieval": store.list_retrieval_events(project_id),
            "studies": store.list_studies(project_id), "links": store.list_study_links(project_id),
            "link_events": store.list_study_link_events(project_id), "documents": store.list_documents(project_id),
            "evidence": store.list_evidence(project_id), "revisions": store.list_evidence_revisions(project_id),
            "reviews": store.list_evidence_reviews(project_id),
        })


def input_payload(study_id, document_id, proposal_id="unicode_text"):
    result = deepcopy(PROPOSALS[proposal_id]["input"])
    for field in ("reviewer", "reason"):
        result.pop(field)
    return {"study_id": study_id, "document_id": document_id, **result}


def write_payload(directory, payload, name="payload with spaces.json"):
    path = directory / name
    path.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return path


def verify_revision_hash(revision):
    payload = {name: value for name, value in revision.items() if name != "revision_sha256"}
    assert hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()).hexdigest() == revision["revision_sha256"]


@pytest.fixture
def prepared(tmp_path):
    database = tmp_path / "ledger with spaces" / "reviews.sqlite3"
    with ReviewStore(database) as store:
        environment = {"database": database}
        for alias in ("main", "foreign"):
            project = store.create_project(alias, "systematic", "Synthetic source statements?")["id"]
            store.import_records(project, SearchRunSpec("Synthetic input"), [
                BibliographicRecord(title="Invented primary", doi="10.99999/cli-evidence-primary"),
                BibliographicRecord(title="Invented companion", doi="10.99999/cli-evidence-companion"),
            ])
            record, companion = [row["id"] for row in store.list_records(project)]
            study = store.create_study(project, "Invented identity A", "Linker", "Manual fixture")["id"]
            alternative = store.create_study(project, "Invented identity B", "Linker", "Alternative")["id"]
            store.record_study_links(project, record, [study], "Linker", "Complete association")
            store.record_decision(project, record, "title_abstract", "include", "Screener")
            store.set_full_text_status(project, record, "retrieved", "Custodian")
            store.record_decision(project, record, "full_text", "include", "Screener")
            document = store.attach_document(project, record, (FIXTURES / "source-v1.txt").read_bytes(), "txt", "Custodian", "Exact fixture")
            environment[alias] = {"project_id": project, "record_id": record, "companion_id": companion,
                                  "study_id": study, "alternative_id": alternative, "document": document}
    return environment


def test_complete_subprocess_source_finding_appraisal_revisions_verification_and_export(tmp_path):
    database = tmp_path / "ledger with spaces" / "reviews.sqlite3"
    project_id = run_cli(tmp_path, database, "create", "--title", "=Invented review", "--type", "systematic", "--question", "Which literal fixture entries?")["id"]
    bibliography = tmp_path / "bibliography.json"
    bibliography.write_text(json.dumps([{"title": "Invented text report"}, {"title": "Invented JATS report"}]))
    run_cli(tmp_path, database, "import", project_id, bibliography, "--source", "Manual fixture", "--import-key", "fixture-citations")
    reports = run_cli(tmp_path, database, "records", project_id)
    study_id = run_cli(tmp_path, database, "study-create", project_id, "--label", "Invented study α", "--reviewer", "Linker", "--reason", "Manual association")["id"]
    document_ids = []
    input_paths = [bibliography]
    for report, alias in zip(reports, ("text_v1", "jats_v1"), strict=True):
        record_id = report["id"]
        run_cli(tmp_path, database, "link-studies", project_id, record_id, "--study-id", study_id, "--reviewer", "Linker", "--reason", "Complete association")
        run_cli(tmp_path, database, "screen", project_id, record_id, "--stage", "title_abstract", "--decision", "include", "--reviewer", "Screener")
        run_cli(tmp_path, database, "fulltext", project_id, record_id, "--status", "retrieved", "--reviewer", "Custodian")
        run_cli(tmp_path, database, "screen", project_id, record_id, "--stage", "full_text", "--decision", "include", "--reviewer", "Screener")
        source = SOURCES[alias]
        source_path = tmp_path / ("=literal source.txt" if alias == "text_v1" else "invented article.xml")
        source_path.write_bytes((FIXTURES / source["file"]).read_bytes())
        input_paths.append(source_path)
        before = run_cli(tmp_path, database, "counts", project_id)
        document = run_cli(tmp_path, database, "attach-source", project_id, record_id, source_path,
                           "--format", source["format"], "--reviewer", "Custodian", "--reason", "=Preserve exact bytes",
                           "--source-url", "https://example.invalid/manual-source", "--version-label", "Submitted α")
        assert document["filename"] == source_path.name and document["source_sha256"] == source["source_sha256"]
        assert document["blocks_sha256"] == source["expected_blocks_sha256"]
        assert document["source_url"] == "https://example.invalid/manual-source" and document["version_label"] == "Submitted α"
        assert run_cli(tmp_path, database, "counts", project_id) == before
        snapshot = run_cli(tmp_path, database, "source-blocks", project_id, document["id"])
        assert snapshot == {"document": document, "blocks": source["expected_blocks"]}
        document_ids.append(document["id"])
    text_record, xml_record = reports[0]["id"], reports[1]["id"]
    counts = run_cli(tmp_path, database, "counts", project_id)
    assert counts["records_identified"] == counts["unique_records"] == counts["reports_included"] == 2
    assert counts["included_studies"] == 1 and counts["all_checks_passed"] is True
    finding_payload = input_payload(study_id, document_ids[0])
    finding_payload["field"] = "=fixture.unicode_marker"
    finding_path = write_payload(tmp_path, finding_payload, "finding.json")
    first = run_cli(tmp_path, database, "propose-evidence", project_id, text_record, "--payload", finding_path, "--reviewer", "Ari", "--reason", "=Manual literal finding")
    appraisal_payload = input_payload(study_id, document_ids[1], "appraisal_jats")
    appraisal_path = write_payload(tmp_path, appraisal_payload, "appraisal.json")
    appraisal = run_cli(tmp_path, database, "propose-evidence", project_id, xml_record, "--payload", appraisal_path, "--reviewer", "Ari", "--reason", "Protocol instrument input")
    for revision in (first, appraisal):
        verify_revision_hash(revision)
        assert revision["reviewer"] == "Ari"
    assert run_cli(tmp_path, database, "evidence", project_id, "--verified-only") == []
    run_cli(tmp_path, database, "review-evidence", project_id, first["id"], "--decision", "confirm", "--reviewer", "Bo", "--reason", "Independent Unicode source check")
    before = state(database, project_id)
    run_cli(tmp_path, database, "review-evidence", project_id, appraisal["id"], "--decision", "reject", "--reviewer", "Ari", "--reason", "Own proposal", success=False)
    run_cli(tmp_path, database, "adjudicate-evidence", project_id, appraisal["id"], "--decision", "confirm", "--reviewer", "Dee", "--reason", "No prior review", success=False)
    assert state(database, project_id) == before
    run_cli(tmp_path, database, "review-evidence", project_id, appraisal["id"], "--decision", "confirm", "--reviewer", "Bo", "--reason", "Check quote and explicit software instrument")
    assert len(run_cli(tmp_path, database, "evidence", project_id, "--verified-only")) == 2
    first_appraisal = deepcopy(appraisal)
    amended_appraisal = deepcopy(appraisal_payload)
    amended_appraisal.pop("kind")
    amended_appraisal["context"]["notes"] = "Complete revised appraisal context; preserve explicit instrument and judgment"
    incomplete_appraisal = deepcopy(amended_appraisal)
    incomplete_appraisal.pop("appraisal")
    amended_path = write_payload(tmp_path, incomplete_appraisal, "appraisal revision.json")
    before = state(database, project_id)
    run_cli(tmp_path, database, "revise-evidence", project_id, appraisal["evidence_id"], "--payload", amended_path,
            "--reviewer", "Carol", "--reason", "Missing complete instrument input", success=False)
    assert state(database, project_id) == before
    amended_path = write_payload(tmp_path, amended_appraisal, "appraisal revision.json")
    appraisal = run_cli(tmp_path, database, "revise-evidence", project_id, appraisal["evidence_id"], "--payload", amended_path,
                        "--reviewer", "Carol", "--reason", "Complete appraisal replacement")
    verify_revision_hash(appraisal)
    assert appraisal["kind"] == "appraisal" and appraisal["appraisal"] == first_appraisal["appraisal"] and appraisal["revision"] == 2
    assert len(run_cli(tmp_path, database, "evidence", project_id, "--verified-only")) == 1
    run_cli(tmp_path, database, "review-evidence", project_id, appraisal["id"], "--decision", "confirm", "--reviewer", "Ari", "--reason", "Distinct current appraisal author")
    input_paths.append(amended_path)
    run_cli(tmp_path, database, "review-evidence", project_id, first["id"], "--decision", "reject", "--reviewer", "Cy", "--reason", "Invented disagreement")
    assert [row["evidence_id"] for row in run_cli(tmp_path, database, "evidence", project_id, "--verified-only")] == [appraisal["evidence_id"]]
    run_cli(tmp_path, database, "adjudicate-evidence", project_id, first["id"], "--decision", "confirm", "--reviewer", "Dee", "--reason", "Resolve invented disagreement")
    run_cli(tmp_path, database, "review-evidence", project_id, first["id"], "--decision", "confirm", "--reviewer", "Cy", "--reason", "Later vote invalidates adjudication")
    replacement = deepcopy(finding_payload)
    replacement.pop("kind")
    replacement["context"]["notes"] = "Complete amended context; no inherited confirmation"
    revision_path = write_payload(tmp_path, replacement, "revision.json")
    second = run_cli(tmp_path, database, "revise-evidence", project_id, first["evidence_id"], "--payload", revision_path, "--reviewer", "Carol", "--reason", "Complete replacement")
    assert second["revision"] == 2 and second["evidence_id"] == first["evidence_id"]
    assert len(run_cli(tmp_path, database, "evidence", project_id, "--verified-only")) == 1
    before = state(database, project_id)
    for target, reviewer in ((second["id"], "Carol"), (first["id"], "Bo")):
        run_cli(tmp_path, database, "review-evidence", project_id, target, "--decision", "confirm", "--reviewer", reviewer, "--reason", "Invalid verification", success=False)
    assert state(database, project_id) == before
    run_cli(tmp_path, database, "review-evidence", project_id, second["id"], "--decision", "confirm", "--reviewer", "Ari", "--reason", "Distinct current revision author")
    replacement_source = tmp_path / "new source.txt"
    replacement_source.write_bytes((FIXTURES / "source-v2.txt").read_bytes())
    input_paths.append(replacement_source)
    new_document = run_cli(tmp_path, database, "attach-source", project_id, text_record, replacement_source, "--format", "txt", "--filename", "retained-source.txt", "--reviewer", "Custodian", "--reason", "Explicit new version")
    text_rows = run_cli(tmp_path, database, "evidence", project_id, "--record-id", text_record)
    assert len(text_rows) == 1 and text_rows[0]["state"] == "stale_source"
    assert text_rows[0]["verification_state"] == "confirmed" and text_rows[0]["dependency_issues"] == ["stale_source"]
    run_cli(tmp_path, database, "review-evidence", project_id, second["id"], "--decision", "confirm", "--reviewer", "Bo", "--reason", "Stale source", success=False)
    replacement["document_id"] = new_document["id"]
    revision_path = write_payload(tmp_path, replacement, "revision.json")
    third = run_cli(tmp_path, database, "revise-evidence", project_id, first["evidence_id"], "--payload", revision_path, "--reviewer", "Carol", "--reason", "Anchor to newest source")
    assert third["revision"] == 3
    assert len(run_cli(tmp_path, database, "evidence", project_id, "--verified-only")) == 1
    run_cli(tmp_path, database, "review-evidence", project_id, third["id"], "--decision", "confirm", "--reviewer", "Ari", "--reason", "New source checked independently")
    for input_path in input_paths + [finding_path, appraisal_path, revision_path]: input_path.unlink()
    before_export = state(database, project_id)
    rows = run_cli(tmp_path, database, "evidence", project_id)
    assert run_cli(tmp_path, database, "evidence", project_id, "--verified-only") == rows
    assert run_cli(tmp_path, database, "evidence", project_id, "--record-id", xml_record)[0]["current_revision"] == appraisal
    history = run_cli(tmp_path, database, "evidence-history", project_id)
    assert history == {"revisions": before_export["revisions"], "reviews": before_export["reviews"]}
    assert len(history["revisions"]) == 5 and len(history["reviews"]) == 8 and first_appraisal in history["revisions"]
    selected = run_cli(tmp_path, database, "evidence-history", project_id, "--evidence-id", first["evidence_id"])
    assert selected["revisions"] == [first, second, third] and len(selected["reviews"]) == 6
    documents = run_cli(tmp_path, database, "documents", project_id)
    assert documents == before_export["documents"] and len(documents) == 3
    assert [doc["version"] for doc in run_cli(tmp_path, database, "documents", project_id, "--record-id", text_record)] == [1, 2]
    assert run_cli(tmp_path, database, "counts", project_id) == counts
    output = tmp_path / "evidence export"
    result = run_cli(tmp_path, database, "export", project_id, output)
    bundle = json.loads((output / "project.json").read_text())
    assert bundle["evidence"] == bundle["verified_evidence"] == rows
    assert bundle["evidence_revisions"] == history["revisions"] and bundle["evidence_reviews"] == history["reviews"]
    assert bundle["documents"] == documents and bundle["counts"] == counts
    assert json.loads((output / "verified_evidence.json").read_text()) == rows
    verified_csv = list(csv.DictReader(io.StringIO((output / "verified_evidence.csv").read_text())))
    assert len(verified_csv) == 2 and verified_csv[0]["field"] == "'=fixture.unicode_marker"
    assert json.loads(verified_csv[0]["anchor"]) == third["anchor"]
    assert json.loads(verified_csv[1]["appraisal"]) == appraisal_payload["appraisal"]
    for asset in bundle["document_artifacts"]:
        content = (output / asset["export_file"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == asset["sha256"] and len(content) == asset["size_bytes"]
    original = {name: (output / name).read_bytes() for name in result["files"]}
    assert run_cli(tmp_path, database, "export", project_id, output) == result
    assert {name: (output / name).read_bytes() for name in result["files"]} == original
    assert state(database, project_id) == before_export


def invalid_payload_text(base, defect):
    if defect.startswith("missing:"):
        base.pop(defect.split(":", 1)[1])
    elif defect.startswith("unknown:"):
        base[defect.split(":", 1)[1]] = "Caller override"
    elif defect == "top_array": return "[]"
    elif defect == "top_null": return "null"
    elif defect == "syntax": return '{"study_id":'
    elif defect == "duplicate_root": return json.dumps(base)[:-1] + ', "field":"duplicate"}'
    elif defect == "duplicate_context":
        base["context"] = {"notes": "PLACEHOLDER"}
        return json.dumps(base).replace('"PLACEHOLDER"', '{"nested":1,"nested":2}')
    elif defect == "duplicate_array":
        base["value"] = "PLACEHOLDER"
        return json.dumps(base).replace('"PLACEHOLDER"', '[{"nested":1,"nested":2}]')
    elif defect in {"NaN", "Infinity", "-Infinity", "1e309"}:
        base["value"] = {"nested": "PLACEHOLDER"}
        return json.dumps(base).replace('"PLACEHOLDER"', defect)
    else: raise AssertionError(defect)
    return json.dumps(base, ensure_ascii=False)


PAYLOAD_DEFECTS = ["missing:" + key for key in ("study_id", "document_id", "field", "value", "context", "anchor")] + [
    "unknown:" + key for key in ("reviewer", "reason", "record_id", "evidence_id", "project_id", "surprise")
] + ["top_array", "top_null", "syntax", "duplicate_root", "duplicate_context", "duplicate_array", "NaN", "Infinity", "-Infinity", "1e309"]


@pytest.mark.parametrize("command", ["propose-evidence", "revise-evidence"])
@pytest.mark.parametrize("defect", PAYLOAD_DEFECTS)
def test_strict_payload_file_errors_preserve_complete_audit_and_both_projects(tmp_path, prepared, command, defect):
    case, foreign, database = prepared["main"], prepared["foreign"], prepared["database"]
    base = input_payload(case["study_id"], case["document"]["id"])
    if command == "revise-evidence":
        with ReviewStore(database) as store:
            inputs = {**base, "reviewer": "Alice", "reason": "Initial checked payload"}
            revision = store.propose_evidence(case["project_id"], case["record_id"], **inputs)
            store.review_evidence(case["project_id"], revision["id"], "confirm", "Bob", "Independent source")
        target = revision["evidence_id"]
        base.pop("kind")
    else:
        target = case["record_id"]
    path = tmp_path / "invalid payload.json"
    path.write_text(invalid_payload_text(base, defect), encoding="utf-8")
    before = state(database, case["project_id"]), state(database, foreign["project_id"])
    run_cli(tmp_path, database, command, case["project_id"], target, "--payload", path, "--reviewer", "Carol", "--reason", "Invalid input", success=False)
    assert (state(database, case["project_id"]), state(database, foreign["project_id"])) == before


@pytest.mark.parametrize("forbidden", ["kind", "report_id", "evidence", "revision", "id"])
def test_revision_payload_cannot_override_fixed_identity_or_kind(tmp_path, prepared, forbidden):
    case, database = prepared["main"], prepared["database"]
    base = input_payload(case["study_id"], case["document"]["id"])
    with ReviewStore(database) as store:
        first = store.propose_evidence(case["project_id"], case["record_id"], **base, reviewer="Alice", reason="Initial")
    base.pop("kind")
    base[forbidden] = "appraisal" if forbidden == "kind" else "Caller identity"
    path = write_payload(tmp_path, base)
    before = state(database, case["project_id"])
    run_cli(tmp_path, database, "revise-evidence", case["project_id"], first["evidence_id"], "--payload", path, "--reviewer", "Carol", "--reason", "Override", success=False)
    assert state(database, case["project_id"]) == before


@pytest.mark.parametrize("bad_file", ["missing", "directory", "invalid_utf8"])
def test_payload_file_read_failures_are_contextual_and_leave_ledger_unchanged(tmp_path, prepared, bad_file):
    case, database = prepared["main"], prepared["database"]
    path = tmp_path / "bad payload"
    if bad_file == "directory": path.mkdir()
    elif bad_file == "invalid_utf8": path.write_bytes(b"\xff\xfe")
    before = state(database, case["project_id"])
    run_cli(tmp_path, database, "propose-evidence", case["project_id"], case["record_id"], "--payload", path, "--reviewer", "Alice", "--reason", "Invalid file", success=False)
    assert state(database, case["project_id"]) == before


OWNERSHIP_CASES = ["documents_unknown_project", "documents_foreign_record", "blocks_foreign_document", "blocks_unknown_document",
                   "evidence_unknown_project", "evidence_foreign_record", "history_foreign_evidence", "history_unknown_evidence",
                   "attach_foreign_record", "proposal_foreign_record", "proposal_foreign_study", "proposal_foreign_document",
                   "revision_foreign_evidence", "revision_unknown_evidence", "review_foreign_revision", "adjudicate_foreign_revision"]


@pytest.mark.parametrize("operation", OWNERSHIP_CASES)
def test_all_cli_boundaries_reject_unknown_or_foreign_ownership_without_modifying_either_project(tmp_path, prepared, operation):
    case, foreign, database = prepared["main"], prepared["foreign"], prepared["database"]
    with ReviewStore(database) as store:
        revisions = {}
        for alias in ("main", "foreign"):
            chosen = prepared[alias]
            revisions[alias] = store.propose_evidence(chosen["project_id"], chosen["record_id"],
                **input_payload(chosen["study_id"], chosen["document"]["id"]), reviewer="Alice", reason="Owned fixture")
            store.review_evidence(chosen["project_id"], revisions[alias]["id"], "confirm", "Bob", "Owned source")
    p, foreign_record = case["project_id"], foreign["record_id"]
    base = input_payload(case["study_id"], case["document"]["id"])
    if operation == "documents_unknown_project": args = ["documents", "unknown-project"]
    elif operation == "documents_foreign_record": args = ["documents", p, "--record-id", foreign_record]
    elif operation == "blocks_foreign_document": args = ["source-blocks", p, foreign["document"]["id"]]
    elif operation == "blocks_unknown_document": args = ["source-blocks", p, "unknown-document"]
    elif operation == "evidence_unknown_project": args = ["evidence", "unknown-project"]
    elif operation == "evidence_foreign_record": args = ["evidence", p, "--record-id", foreign_record]
    elif operation == "history_foreign_evidence": args = ["evidence-history", p, "--evidence-id", revisions["foreign"]["evidence_id"]]
    elif operation == "history_unknown_evidence": args = ["evidence-history", p, "--evidence-id", "unknown-evidence"]
    elif operation == "attach_foreign_record": args = ["attach-source", p, foreign_record, FIXTURES / "source-v1.txt", "--format", "txt", "--reviewer", "Carol", "--reason", "Foreign source"]
    elif operation.startswith("proposal_"):
        target = foreign_record if operation == "proposal_foreign_record" else case["record_id"]
        if operation == "proposal_foreign_study": base["study_id"] = foreign["study_id"]
        if operation == "proposal_foreign_document": base["document_id"] = foreign["document"]["id"]
        args = ["propose-evidence", p, target, "--payload", write_payload(tmp_path, base), "--reviewer", "Carol", "--reason", "Foreign input"]
    elif operation.startswith("revision_"):
        base.pop("kind")
        target = revisions["foreign"]["evidence_id"] if operation == "revision_foreign_evidence" else "unknown-evidence"
        args = ["revise-evidence", p, target, "--payload", write_payload(tmp_path, base), "--reviewer", "Carol", "--reason", "Foreign input"]
    else:
        command = "review-evidence" if operation == "review_foreign_revision" else "adjudicate-evidence"
        args = [command, p, revisions["foreign"]["id"], "--decision", "confirm", "--reviewer", "Carol", "--reason", "Foreign verification"]
    before = state(database, p), state(database, foreign["project_id"])
    run_cli(tmp_path, database, *args, success=False)
    assert (state(database, p), state(database, foreign["project_id"])) == before


@pytest.mark.parametrize("defect", ["missing", "directory", "empty", "invalid_utf8", "entity_xml", "unsupported_format", "blank_reviewer", "blank_reason", "traversal_filename", "control_filename"])
def test_source_file_parser_and_metadata_errors_are_atomic_through_cli(tmp_path, prepared, defect):
    case, database = prepared["main"], prepared["database"]
    source_path = tmp_path / "supplied source.txt"
    source_path.write_bytes((FIXTURES / "source-v1.txt").read_bytes())
    fmt, reviewer, reason, optional = "txt", "Custodian", "Fixture source", []
    if defect == "missing": source_path.unlink()
    elif defect == "directory": source_path.unlink(); source_path.mkdir()
    elif defect == "empty": source_path.write_bytes(b"")
    elif defect == "invalid_utf8": source_path.write_bytes(b"\xff\xfe")
    elif defect == "entity_xml": fmt = "jats_xml"; source_path.write_bytes(b'<!DOCTYPE article [<!ENTITY x "value">]><article><body><p>&x;</p></body></article>')
    elif defect == "unsupported_format": fmt = "html"
    elif defect == "blank_reviewer": reviewer = " "
    elif defect == "blank_reason": reason = " "
    elif defect == "traversal_filename": optional = ["--filename", "../source.txt"]
    elif defect == "control_filename": optional = ["--filename", "bad\u0085source.txt"]
    before = state(database, case["project_id"])
    run_cli(tmp_path, database, "attach-source", case["project_id"], case["record_id"], source_path, "--format", fmt,
            "--reviewer", reviewer, "--reason", reason, *optional, success=False)
    assert state(database, case["project_id"]) == before


def test_conditional_screening_and_complete_link_set_changes_suppress_restore_same_cli_confirmation(tmp_path, prepared):
    case, database = prepared["main"], prepared["database"]
    p, record_id = case["project_id"], case["record_id"]
    payload = input_payload(case["study_id"], case["document"]["id"])
    path = write_payload(tmp_path, payload)
    revision = run_cli(tmp_path, database, "propose-evidence", p, record_id, "--payload", path, "--reviewer", "Alice", "--reason", "Manual fixture")
    event = run_cli(tmp_path, database, "review-evidence", p, revision["id"], "--decision", "confirm", "--reviewer", "Bob", "--reason", "Source checked")
    history = {"revisions": [revision], "reviews": [event]}
    changes = [
        (["screen", p, record_id, "--stage", "full_text", "--decision", "exclude", "--reviewer", "Screener", "--reason", "Temporary exclusion"], ["ineligible_report"]),
        (["screen", p, record_id, "--stage", "full_text", "--decision", "include", "--reviewer", "Screener"], []),
        (["link-studies", p, record_id, "--clear", "--reviewer", "Linker", "--reason", "No current association"], ["unresolved_linkage"]),
        (["link-studies", p, record_id, "--study-id", case["alternative_id"], "--reviewer", "Linker", "--reason", "Different complete set"], ["study_not_linked"]),
        (["link-studies", p, record_id, "--study-id", case["study_id"], "--study-id", case["alternative_id"], "--reviewer", "Linker", "--reason", "Restore association in complete set"], []),
    ]
    for args, issues in changes:
        run_cli(tmp_path, database, *args)
        row = run_cli(tmp_path, database, "evidence", p, "--record-id", record_id)[0]
        assert row["verification_state"] == "confirmed" and row["dependency_issues"] == issues
        assert row["state"] == (issues[0] if issues else "confirmed") and row["active_verification_event_ids"] == [event["id"]]
        assert run_cli(tmp_path, database, "evidence-history", p) == history
        assert run_cli(tmp_path, database, "evidence", p, "--verified-only") == ([] if issues else [row])
        output = tmp_path / "conditional export"
        run_cli(tmp_path, database, "export", p, output)
        assert json.loads((output / "verified_evidence.json").read_text()) == ([] if issues else [row])
        if issues:
            before = state(database, p)
            run_cli(tmp_path, database, "review-evidence", p, revision["id"], "--decision", "confirm", "--reviewer", "Carol", "--reason", "Invalid dependencies", success=False)
            assert state(database, p) == before


def test_later_canonical_pmid_enrichment_invalidates_cli_verification_and_new_source_revision_restores_it(tmp_path, prepared):
    case, database = prepared["main"], prepared["database"]
    p, record = case["project_id"], case["record_id"]
    def xml(pmid):
        return ('<article><front><article-meta><article-id pub-id-type="doi">10.99999/cli-evidence-primary</article-id>'
                f'<article-id pub-id-type="pmid">{pmid}</article-id></article-meta></front><body><p>Source α.</p></body></article>').encode()
    path = tmp_path / "identity source.xml"
    path.write_bytes(xml("999999111"))
    old = run_cli(tmp_path, database, "attach-source", p, record, path, "--format", "jats_xml", "--reviewer", "Custodian", "--reason", "Unknown bibliography PMID")
    payload = {"study_id": case["study_id"], "document_id": old["id"], "field": "fixture.marker", "value": "α", "context": {"notes": "Identity regression"},
               "anchor": {"block_id": "xml:/article[1]/body[1]/p[1]", "start": 7, "end": 8, "quote": "α"}}
    payload_path = write_payload(tmp_path, payload)
    first = run_cli(tmp_path, database, "propose-evidence", p, record, "--payload", payload_path, "--reviewer", "Alice", "--reason", "Initially valid identity")
    event = run_cli(tmp_path, database, "review-evidence", p, first["id"], "--decision", "confirm", "--reviewer", "Bob", "--reason", "Current source checked")
    assert len(run_cli(tmp_path, database, "evidence", p, "--verified-only")) == 1
    bibliography = tmp_path / "late enrichment.json"
    bibliography.write_text(json.dumps([{"title": "Invented primary", "doi": "10.99999/cli-evidence-primary", "pmid": "999999112"}]))
    imported = run_cli(tmp_path, database, "import", p, bibliography, "--source", "Later bibliography enrichment")
    assert imported["duplicates"] == 1 and imported["new_records"] == 0
    row = run_cli(tmp_path, database, "evidence", p)[0]
    assert row["state"] == "source_identity_conflict" and row["dependency_issues"] == ["source_identity_conflict"]
    assert row["verification_state"] == "confirmed" and row["active_verification_event_ids"] == [event["id"]]
    assert run_cli(tmp_path, database, "evidence", p, "--verified-only") == []
    before = state(database, p)
    run_cli(tmp_path, database, "review-evidence", p, first["id"], "--decision", "confirm", "--reviewer", "Carol", "--reason", "Conflicting current identity", success=False)
    run_cli(tmp_path, database, "revise-evidence", p, first["evidence_id"], "--payload", payload_path, "--reviewer", "Carol", "--reason", "Same conflicting source", success=False)
    assert state(database, p) == before
    output = tmp_path / "identity export"
    run_cli(tmp_path, database, "export", p, output)
    bundle = json.loads((output / "project.json").read_text())
    assert bundle["evidence_revisions"] == [first] and bundle["evidence_reviews"] == [event] and bundle["verified_evidence"] == []
    old_asset = next(asset for asset in bundle["document_artifacts"] if asset["document_id"] == old["id"])
    assert (output / old_asset["export_file"]).read_bytes() == xml("999999111")
    path.write_bytes(xml("999999112"))
    new = run_cli(tmp_path, database, "attach-source", p, record, path, "--format", "jats_xml", "--reviewer", "Custodian", "--reason", "Correct own source identifier")
    payload["document_id"] = new["id"]
    payload_path = write_payload(tmp_path, payload)
    second = run_cli(tmp_path, database, "revise-evidence", p, first["evidence_id"], "--payload", payload_path, "--reviewer", "Carol", "--reason", "Correct source replacement")
    assert run_cli(tmp_path, database, "evidence", p, "--verified-only") == []
    run_cli(tmp_path, database, "review-evidence", p, second["id"], "--decision", "confirm", "--reviewer", "Alice", "--reason", "Current author is distinct")
    assert len(run_cli(tmp_path, database, "evidence", p, "--verified-only")) == 1
    path.unlink(); bibliography.unlink(); payload_path.unlink()
    run_cli(tmp_path, database, "export", p, output)
    assert len(json.loads((output / "verified_evidence.json").read_text())) == 1


def test_attach_cli_reads_supplied_path_once_and_persists_that_exact_byte_snapshot(tmp_path, prepared, monkeypatch, capsys):
    case, database = prepared["main"], prepared["database"]
    path = tmp_path / "same snapshot.txt"
    original = (FIXTURES / "source-v1.txt").read_bytes()
    replacement = (FIXTURES / "source-v2.txt").read_bytes()
    path.write_bytes(original)
    previous_read = Path.read_bytes
    reads = []
    def mutate_after_read(chosen):
        content = previous_read(chosen)
        if chosen == path:
            reads.append(content)
            chosen.write_bytes(replacement)
        return content
    before = state(database, case["project_id"])["counts"]
    monkeypatch.setattr(Path, "read_bytes", mutate_after_read)
    assert cli.main(["--db", str(database), "attach-source", case["project_id"], case["record_id"], str(path),
                     "--format", "txt", "--reviewer", "Custodian", "--reason", "One immutable read"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    document = json.loads(captured.out)
    assert reads == [original] and document["source_sha256"] == SOURCES["text_v1"]["source_sha256"]
    assert previous_read(path) == replacement
    path.unlink()
    with ReviewStore(database) as store:
        assert store.get_document_bytes(case["project_id"], document["id"]) == original
        assert store.get_source_blocks(case["project_id"], document["id"]) == SOURCES["text_v1"]["expected_blocks"]
        assert store.counts(case["project_id"]) == before


def test_source_blocks_cli_returns_metadata_and_blocks_from_one_actual_wal_snapshot(tmp_path, prepared, monkeypatch, capsys):
    case, database = prepared["main"], prepared["database"]
    with sqlite3.connect(database) as configurator:
        assert configurator.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    configurator.close()
    p, document_id = case["project_id"], case["document"]["id"]
    new_source = SOURCES["text_v2"]
    new_content = (FIXTURES / new_source["file"]).read_bytes()
    blocks_json = json.dumps(new_source["expected_blocks"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    original = ReviewStore.list_documents
    triggered = False
    def concurrent_complete_rewrite(store, project_id, record_id=None):
        nonlocal triggered
        result = original(store, project_id, record_id)
        if project_id == p and not triggered:
            assert store._connection.in_transaction, "Combined CLI read must retain the outer SQLite snapshot"
            triggered = True
            # A consistent external rewrite is only a snapshot witness, not a claim
            # that this unsigned ledger prevents an actor rewriting data and hashes.
            with sqlite3.connect(database) as writer:
                writer.execute("UPDATE source_documents SET content=?, source_sha256=?, size_bytes=?, blocks_json=?, blocks_sha256=?, version_label=? WHERE id=?",
                               (new_content, new_source["source_sha256"], len(new_content), blocks_json,
                                new_source["expected_blocks_sha256"], "Consistent second-writer representation", document_id))
        return result
    monkeypatch.setattr(ReviewStore, "list_documents", concurrent_complete_rewrite)
    assert cli.main(["--db", str(database), "source-blocks", p, document_id]) == 0
    captured = capsys.readouterr()
    assert captured.err == "" and triggered
    snapshot = json.loads(captured.out)
    assert snapshot == {"document": case["document"], "blocks": SOURCES["text_v1"]["expected_blocks"]}
    next_snapshot = run_cli(tmp_path, database, "source-blocks", p, document_id)
    assert next_snapshot["document"]["source_sha256"] == new_source["source_sha256"]
    assert next_snapshot["document"]["version_label"] == "Consistent second-writer representation"
    assert next_snapshot["blocks"] == new_source["expected_blocks"]


def test_evidence_history_cli_returns_revisions_and_reviews_from_one_actual_wal_snapshot(tmp_path, prepared, monkeypatch, capsys):
    case, database = prepared["main"], prepared["database"]
    with sqlite3.connect(database) as configurator:
        assert configurator.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    configurator.close()
    p = case["project_id"]
    payload = input_payload(case["study_id"], case["document"]["id"])
    with ReviewStore(database) as store:
        first = store.propose_evidence(p, case["record_id"], **payload, reviewer="Alice", reason="Initial")
        event = store.review_evidence(p, first["id"], "confirm", "Bob", "Initial source checked")
    payload.pop("kind")
    payload["context"]["notes"] = "Concurrent complete revision"
    original = ReviewStore.list_evidence_revisions
    triggered = False
    def concurrent_revision(store, project_id, evidence_id=None):
        nonlocal triggered
        result = original(store, project_id, evidence_id)
        if project_id == p and not triggered:
            assert store._connection.in_transaction, "Combined history must retain its outer SQLite snapshot"
            triggered = True
            with ReviewStore(database) as writer:
                second = writer.revise_evidence(p, first["evidence_id"], **payload, reviewer="Carol", reason="Concurrent revision")
                writer.review_evidence(p, second["id"], "confirm", "Bob", "Concurrent source checked")
        return result
    monkeypatch.setattr(ReviewStore, "list_evidence_revisions", concurrent_revision)
    assert cli.main(["--db", str(database), "evidence-history", p, "--evidence-id", first["evidence_id"]]) == 0
    captured = capsys.readouterr()
    assert captured.err == "" and triggered
    assert json.loads(captured.out) == {"revisions": [first], "reviews": [event]}
    next_snapshot = run_cli(tmp_path, database, "evidence-history", p)
    assert len(next_snapshot["revisions"]) == len(next_snapshot["reviews"]) == 2
    assert next_snapshot["revisions"][1]["context"]["notes"] == "Concurrent complete revision"
    assert next_snapshot["reviews"][1]["revision_id"] == next_snapshot["revisions"][1]["id"]


def test_pdf_attachment_cli_uses_actual_pages_and_readable_durable_blocks_after_deletion(tmp_path, prepared):
    case, database = prepared["main"], prepared["database"]
    source = SOURCES["pdf_three_pages"]
    path = tmp_path / "physical pages.pdf"
    path.write_bytes((FIXTURES / source["file"]).read_bytes())
    before = state(database, case["project_id"])["counts"]
    document = run_cli(tmp_path, database, "attach-source", case["project_id"], case["record_id"], path, "--format", "pdf",
                       "--reviewer", "Custodian", "--reason", "Physical page provenance")
    path.unlink()
    snapshot = run_cli(tmp_path, database, "source-blocks", case["project_id"], document["id"])
    assert snapshot == {"document": document, "blocks": source["expected_blocks"]}
    assert [block["locator"] for block in snapshot["blocks"]] == [{"type": "pdf_page", "page": n} for n in (1, 2, 3)]
    assert snapshot["blocks"][1]["text"] == ""
    assert document["source_sha256"] == source["source_sha256"] and document["blocks_sha256"] == source["expected_blocks_sha256"]
    assert state(database, case["project_id"])["counts"] == before


def test_fresh_process_cli_workflow_and_durable_pdf_read_never_initialize_models_settings_or_pdf_parser(tmp_path, prepared):
    case, database = prepared["main"], prepared["database"]
    with ReviewStore(database) as store:
        pdf = store.attach_document(case["project_id"], case["record_id"], (FIXTURES / "three-pages.pdf").read_bytes(), "pdf", "Custodian", "Durable PDF representation")
    path = tmp_path / "isolated source.txt"
    path.write_bytes((FIXTURES / "source-v1.txt").read_bytes())
    code = """
import contextlib, importlib.abc, io, json, pathlib, socket, sys
sys.path.insert(0,sys.argv[1])
blocked={'torch','chromadb','sentence_transformers','dotenv','src.settings','fitz','pymupdf'}
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if any(fullname==name or fullname.startswith(name+'.') for name in blocked):
            raise AssertionError('CLI initialized forbidden dependency '+fullname)
sys.meta_path.insert(0,Guard())
def denied(*a,**k): raise AssertionError('CLI attempted network')
socket.create_connection=denied
from src.review import cli
def invoke(*arguments):
    output=io.StringIO()
    with contextlib.redirect_stdout(output):
        assert cli.main(['--db',sys.argv[2],*map(str,arguments)])==0
    return json.loads(output.getvalue())
p,r,s,pdf,source=sys.argv[3:8]
retained=invoke('source-blocks',p,pdf)
assert retained['blocks'][1]['text']=='' and retained['blocks'][2]['locator']['page']==3
d=invoke('attach-source',p,r,source,'--format','txt','--reviewer','Custodian','--reason','Exact bytes')
payload={'study_id':s,'document_id':d['id'],'field':'unicode','value':'α','context':{},'anchor':{'block_id':'text:1','start':53,'end':54,'quote':'α'}}
payload_path=pathlib.Path(sys.argv[8]); payload_path.write_text(json.dumps(payload))
rev=invoke('propose-evidence',p,r,'--payload',payload_path,'--reviewer','Alice','--reason','Manual fixture')
invoke('review-evidence',p,rev['id'],'--decision','confirm','--reviewer','Bob','--reason','Distinct source check')
pathlib.Path(source).unlink(); payload_path.unlink()
assert len(invoke('evidence',p,'--verified-only'))==1
invoke('export',p,sys.argv[9])
assert not blocked.intersection(sys.modules)
print(json.dumps({'isolated':True,'verified_rows':1,'durable_pdf_pages':3}))
"""
    environment = os.environ.copy()
    environment.pop("NCBI_EMAIL", None); environment.pop("NCBI_API_KEY", None)
    environment.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    result = subprocess.run([sys.executable, "-c", code, str(ROOT), str(database), case["project_id"], case["record_id"], case["study_id"],
                             pdf["id"], str(path), str(tmp_path / "isolated-payload.json"), str(tmp_path / "isolated-export")],
                            cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0 and result.stderr == "", result.stderr
    assert json.loads(result.stdout) == {"isolated": True, "verified_rows": 1, "durable_pdf_pages": 3}
