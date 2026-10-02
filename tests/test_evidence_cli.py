"""Offline source/evidence commands, strict payloads, and retained provenance."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.review import cli
from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.store import ReviewStore


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures/evidence"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text())
TEXT = MANIFEST["fixtures"][0]
QUOTE = TEXT["quotes"][0]


def setup(tmp_path):
    database = tmp_path / "ledger.sqlite3"
    with ReviewStore(database) as store:
        project = store.create_project("Synthetic evidence CLI", "systematic", "Software question")["id"]
        store.import_records(project, SearchRunSpec("invented"), [BibliographicRecord(title="Software report")])
        record = store.list_records(project)[0]["id"]
        study = store.create_study(project, "Software study", "curator", "Invented identity")["id"]
        store.record_decision(project, record, "title_abstract", "include", "screener")
        store.set_full_text_status(project, record, "retrieved", "librarian")
        store.record_decision(project, record, "full_text", "include", "screener")
        store.record_study_links(project, record, [study], "linker", "Manual association")
    return database, project, record, study


def process(database, *args, success=True):
    result = subprocess.run([sys.executable, str(ROOT / "review.py"), "--db", str(database), *args], cwd=database.parent, text=True, capture_output=True)
    assert (result.returncode == 0) is success, result.stderr
    if success:
        assert result.stderr == ""
        return json.loads(result.stdout)
    assert result.stdout == "" and "Traceback" not in result.stderr
    return result.stderr


def invoked(capsys, database, *args, success=True):
    status = cli.main(["--db", str(database), *args])
    output = capsys.readouterr()
    assert (status == 0) is success, output.err
    if success:
        assert output.err == ""
        return json.loads(output.out)
    assert output.out == "" and "Traceback" not in output.err
    return output.err


def attach(database, project, record, path=FIXTURES / TEXT["file"], format="txt", **options):
    flags = [item for name, value in options.items() for item in ("--" + name.replace("_", "-"), value)]
    return process(database, "attach-source", project, record, str(path), "--format", format, "--reviewer", "librarian", "--reason", "Exact software source", *flags)


def payload(tmp_path, study, document, **options):
    value = {"study_id": study, "document_id": document, "field": "follow_up", "value": {"duration": 6, "unit": "weeks"}, "context": {"notes": "Synthetic, not clinical"}, "anchor": {key: QUOTE[key] for key in ("block_id", "start", "end", "quote")}, **options}
    path = tmp_path / "payload.json"
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path, value


def proposal(database, project, record, file, **options):
    return process(database, "propose-evidence", project, record, "--payload", str(file), "--reviewer", options.get("reviewer", "Alice"), "--reason", "Manual source-supported software finding")


def test_portable_cli_finding_appraisal_votes_revision_and_conditional_exports(tmp_path):
    database, project, record, study = setup(tmp_path)
    source = tmp_path / "review source.txt"
    source.write_bytes((FIXTURES / TEXT["file"]).read_bytes())
    document = attach(database, project, record, source, source_url="https://invalid.example/unfetched", version_label="Author copy")
    assert document["filename"] == source.name and document["version_label"] == "Author copy"
    assert process(database, "documents", project, "--record-id", record) == [document]
    snapshot = process(database, "source-blocks", project, document["id"])
    assert snapshot == {"document": document, "blocks": TEXT["expected_blocks"]}
    source.unlink()
    assert process(database, "source-blocks", project, document["id"]) == snapshot
    file, supplied = payload(tmp_path, study, document["id"])
    first = proposal(database, project, record, file)
    assert first["value"] == supplied["value"] and first["anchor"]["locator"] == {"type": "text_block", "ordinal": 1}
    assert process(database, "evidence", project, "--verified-only") == []
    review = process(database, "review-evidence", project, first["id"], "--decision", "confirm", "--reviewer", "Bob", "--reason", "Independent literal check")
    assert process(database, "evidence", project, "--verified-only")[0]["current_revision"] == first
    process(database, "review-evidence", project, first["id"], "--decision", "reject", "--reviewer", "Carol", "--reason", "Disagreed about context")
    assert process(database, "evidence", project)[0]["state"] == "conflict"
    resolution = process(database, "adjudicate-evidence", project, first["id"], "--decision", "confirm", "--reviewer", "Lead", "--reason", "Resolved source reading")
    assert process(database, "evidence", project)[0]["active_verification_event_ids"] == [resolution["id"]]
    file, _ = payload(tmp_path, study, document["id"], context={})
    second = process(database, "revise-evidence", project, first["evidence_id"], "--payload", str(file), "--reviewer", "Carol", "--reason", "Complete corrected context")
    assert second["revision"] == 2 and second["context"] == {}
    assert process(database, "evidence", project, "--verified-only") == []
    process(database, "review-evidence", project, second["id"], "--decision", "confirm", "--reviewer", "Alice", "--reason", "Current author is Carol")
    file, _ = payload(tmp_path, study, document["id"], kind="appraisal", field="manual_domain", value="Invented judgment", appraisal={"instrument": "Software fixture checklist", "instrument_version": "1", "domain": "Source provenance"})
    judgment = proposal(database, project, record, file)
    assert judgment["kind"] == "appraisal" and judgment["appraisal"]["domain"] == "Source provenance"
    history = process(database, "evidence-history", project, "--evidence-id", first["evidence_id"])
    assert history["revisions"] == [first, second] and history["reviews"][0] == review
    assert len(history["reviews"]) == 4
    assert len(process(database, "evidence", project, "--record-id", record)) == 2
    exported = process(database, "export", project, str(tmp_path / "export"))
    assert "verified_evidence.json" in exported["files"]
    assert len(json.loads((tmp_path / "export/verified_evidence.json").read_text())) == 1
    # A new source version makes both existing proposals stale while retaining audit data.
    replacement = attach(database, project, record, FIXTURES / "source-v2.txt")
    assert replacement["version"] == 2
    assert [row["active"] for row in process(database, "documents", project)] == [False, True]
    assert all(row["state"] == "stale_source" for row in process(database, "evidence", project))
    assert process(database, "evidence", project, "--verified-only") == []
    assert process(database, "evidence-history", project, "--evidence-id", first["evidence_id"]) == history


@pytest.mark.parametrize("fixture", [MANIFEST["fixtures"][2], MANIFEST["fixtures"][4]], ids=lambda item: item["format"])
def test_cli_jats_pdf_source_formats_and_filename_override(tmp_path, fixture):
    database, project, record, _ = setup(tmp_path)
    document = attach(database, project, record, FIXTURES / fixture["file"], fixture["format"], filename="retained-source.bin")
    assert document["source_sha256"] == fixture["source_sha256"] and document["filename"] == "retained-source.bin"
    result = process(database, "source-blocks", project, document["id"])
    assert result["blocks"] == fixture["expected_blocks"]


def test_attachment_reads_one_byte_snapshot_for_parser_hash_and_storage(tmp_path, capsys, monkeypatch):
    database, project, record, _ = setup(tmp_path)
    source = tmp_path / "source.txt"
    original = b"Original source\r\n"
    source.write_bytes(original)
    actual, reads = Path.read_bytes, []
    def read(path):
        content = actual(path)
        if path == source:
            reads.append(content)
            source.write_bytes(b"Changed after read")
        return content
    monkeypatch.setattr(Path, "read_bytes", read)
    document = invoked(capsys, database, "attach-source", project, record, str(source), "--format", "txt", "--reviewer", "Alice", "--reason", "Single snapshot")
    assert reads == [original]
    assert document["source_sha256"] == hashlib.sha256(original).hexdigest()
    with ReviewStore(database) as store:
        assert store.get_document_bytes(project, document["id"]) == original
        assert store.get_source_blocks(project, document["id"])[0]["text"] == original.decode()


@pytest.mark.parametrize("text", ['[]', 'null', 'not JSON', '{"value":NaN}', '{"value":1e309}', '{"value":1,"value":2}', '{"value":[{"nested":1,"nested":2}]}'])
def test_strict_payload_json_fails_contextually_without_proposals(tmp_path, capsys, text):
    database, project, record, _ = setup(tmp_path)
    file = tmp_path / "bad.json"
    file.write_text(text)
    error = invoked(capsys, database, "propose-evidence", project, record, "--payload", str(file), "--reviewer", "Alice", "--reason", "Software source", success=False)
    assert "evidence payload JSON" in error
    with ReviewStore(database) as store:
        assert store.list_evidence(project) == []


@pytest.mark.parametrize("key", ["study_id", "document_id", "field", "value", "context", "anchor"])
def test_every_required_payload_key_is_explicit(tmp_path, capsys, key):
    database, project, record, study = setup(tmp_path)
    file, data = payload(tmp_path, study, "unused")
    del data[key]
    file.write_text(json.dumps(data))
    error = invoked(capsys, database, "propose-evidence", project, record, "--payload", str(file), "--reviewer", "Alice", "--reason", "Software source", success=False)
    assert "missing required keys" in error and key in error
    with ReviewStore(database) as store:
        assert store.list_evidence_revisions(project) == []


@pytest.mark.parametrize("key", ["reviewer", "reason", "record_id", "evidence_id", "project_id", "unsupported"])
def test_payload_cannot_override_named_flags_or_targets(tmp_path, capsys, key):
    database, project, record, study = setup(tmp_path)
    document = attach(database, project, record)
    file, _ = payload(tmp_path, study, document["id"], **{key: "silent override"})
    error = invoked(capsys, database, "propose-evidence", project, record, "--payload", str(file), "--reviewer", "Alice", "--reason", "Software source", success=False)
    assert "unknown keys" in error and key in error
    with ReviewStore(database) as store:
        assert store.list_evidence(project) == []


def test_revision_rejects_kind_override_and_invalid_anchor_without_new_history(tmp_path, capsys):
    database, project, record, study = setup(tmp_path)
    document = attach(database, project, record)
    file, data = payload(tmp_path, study, document["id"])
    first = proposal(database, project, record, file)
    original_history = process(database, "evidence-history", project)
    for updated, expected in [({**data, "kind": "finding"}, "unknown keys"), ({**data, "anchor": {**data["anchor"], "quote": "Wrong"}}, "quote")]:
        file.write_text(json.dumps(updated))
        error = invoked(capsys, database, "revise-evidence", project, first["evidence_id"], "--payload", str(file), "--reviewer", "Alice", "--reason", "Correction", success=False)
        assert expected in error
        assert process(database, "evidence-history", project) == original_history


def test_unknown_cross_project_source_and_self_review_errors_preserve_history(tmp_path, capsys):
    database, project, record, study = setup(tmp_path)
    document = attach(database, project, record)
    file, _ = payload(tmp_path, study, document["id"])
    first = proposal(database, project, record, file)
    with ReviewStore(database) as store:
        other = store.create_project("Other project", "scoping", "Software question")["id"]
    for command, arguments in [("source-blocks", [other, document["id"]]), ("documents", [project, "--record-id", "unknown"]), ("evidence-history", [other, "--evidence-id", first["evidence_id"]]), ("evidence", [other, "--record-id", record]), ("review-evidence", [project, first["id"], "--decision", "confirm", "--reviewer", "Alice", "--reason", "Self review"]), ("adjudicate-evidence", [project, first["id"], "--decision", "confirm", "--reviewer", "Lead", "--reason", "No prior review"]), ("attach-source", [other, record, str(FIXTURES / TEXT["file"]), "--format", "txt", "--reviewer", "Alice", "--reason", "Wrong report"])]:
        invoked(capsys, database, command, *arguments, success=False)
    assert process(database, "evidence-history", project) == {"revisions": [first], "reviews": []}
