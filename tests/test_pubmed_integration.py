"""Durable capture and ledger integration unit cases; all fixtures are synthetic."""

import hashlib
import json
import shutil
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.store import ReviewStore
from src.search.pubmed_search import capture_pubmed_search, import_pubmed_capture, validate_pubmed_artifacts, verify_pubmed_capture


FIXTURES = Path(__file__).parent / "fixtures/pubmed"


def capture(tmp_path, zero=False):
    responses = ["search-zero.xml"] if zero else ["search-five.xml", "fetch-0001.xml", "fetch-0002.xml", "fetch-0003.xml"]

    class Client:
        def request(self, endpoint, params):
            return (FIXTURES / responses.pop(0)).read_bytes()

    return Path(capture_pubmed_search(" synthetic software fixture ", tmp_path / "capture", client=Client(), batch_size=2)["directory"])


def artifacts(directory):
    return {str(path.relative_to(directory)): path.read_bytes() for path in directory.rglob("*") if path.is_file()}


def mutate_receipt(payload, change):
    updated = dict(payload)
    receipt = json.loads(updated["receipt.json"])
    change(receipt)
    updated["receipt.json"] = json.dumps(receipt).encode()
    return updated


def project(store):
    return store.create_project("Synthetic review", "systematic", "Software question")["id"]


def test_complete_capture_import_relocation_reopen_and_export_without_original(tmp_path):
    directory = capture(tmp_path)
    original = artifacts(directory)
    verified = verify_pubmed_capture(directory)
    assert validate_pubmed_artifacts(original)["receipt"] == verified["receipt"]
    database = tmp_path / "ledger.sqlite3"
    with ReviewStore(database) as store:
        project_id = project(store)
        result = import_pubmed_capture(store, project_id, directory, "capture-key")
        assert result["identified"] == result["new_records"] == 5
        assert store.get_search_artifacts(project_id, result["search_run_id"]) == original
        assert store.list_search_runs(project_id)[0]["execution"] == verified["receipt"]
        relocated = tmp_path / "moved"
        shutil.copytree(directory, relocated)
        assert import_pubmed_capture(store, project_id, relocated, "capture-key") == result
        assert store.list_search_runs(project_id)[0]["source_file"] == str(directory / "records.xml")
    shutil.rmtree(directory)
    shutil.rmtree(relocated)
    with ReviewStore(database) as store:
        exported = store.export_project(project_id, tmp_path / "export")
        export_directory = Path(exported["directory"])
        bundle = json.loads((export_directory / "project.json").read_text())
        assert len(bundle["search_artifacts"]) == len(original)
        restored = export_directory / "search_captures" / result["search_run_id"]
        assert artifacts(restored) == original
        assert verify_pubmed_capture(restored)["receipt"] == verified["receipt"]
        fresh_project = project(store)
        assert import_pubmed_capture(store, fresh_project, restored)["identified"] == 5
        assert store.counts(project_id)["unique_records"] == 5
        assert len(exported["files"]) == 9 + len(original)
        assert all(item["export_file"] in exported["files"] for item in bundle["search_artifacts"])


def test_zero_capture_is_durable_without_batches(tmp_path):
    directory = capture(tmp_path, zero=True)
    with ReviewStore(":memory:") as store:
        project_id = project(store)
        result = import_pubmed_capture(store, project_id, directory)
        assert result["identified"] == 0
        assert set(store.get_search_artifacts(project_id, result["search_run_id"])) == {"receipt.json", "search.xml", "records.xml"}
        assert store.counts(project_id)["records_identified"] == 0
        assert store.export_project(project_id, tmp_path / "export")["counts"]["all_checks_passed"]


def test_legacy_fingerprint_and_generic_export_shape_are_compatible(tmp_path):
    spec = SearchRunSpec("PubMed", query="old query", source_file="old.json")
    record = BibliographicRecord(title="Legacy synthetic record", pmid="1")
    legacy_spec = asdict(spec)
    legacy_spec.pop("execution")
    payload = {"spec": legacy_spec, "records": [asdict(record)]}
    legacy_fingerprint = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    database = tmp_path / "legacy.sqlite3"
    with ReviewStore(database) as store:
        project_id = project(store)
        original = store.import_records(project_id, spec, [record], "old-key")
        with store._connection:
            store._connection.execute("UPDATE search_runs SET spec = ?, fingerprint = ? WHERE id = ?", (json.dumps(legacy_spec), legacy_fingerprint, original["search_run_id"]))
    with ReviewStore(database) as store:
        assert store.import_records(project_id, replace(spec, execution={}), [record], "old-key", artifacts={}) == original
        assert store.list_search_runs(project_id)[0]["execution"] is None
        assert store.get_search_artifacts(project_id, original["search_run_id"]) == {}
        exported = store.export_project(project_id, tmp_path / "export")
        assert len(exported["files"]) == 9
        assert "search_artifacts" not in json.loads((tmp_path / "export/project.json").read_text())


@pytest.mark.parametrize("change", [
    lambda receipt: receipt.update(complete=False),
    lambda receipt: receipt.update(reported_count=True),
    lambda receipt: receipt.update(started_at="2026-10-03T00:00:00"),
    lambda receipt: receipt.update(completed_at="2000-01-01T00:00:00+00:00"),
    lambda receipt: receipt.update(query_translation="contradiction"),
    lambda receipt: receipt["requests"][0]["params"].update(api_key="synthetic-secret"),
    lambda receipt: receipt["requests"][1].update(response_file="../outside.xml"),
])
def test_invalid_receipt_rejected_before_import(tmp_path, change):
    payload = mutate_receipt(artifacts(capture(tmp_path)), change)
    with pytest.raises(ValueError):
        validate_pubmed_artifacts(payload)


def test_combined_content_tamper_rejected_even_after_hash_update(tmp_path):
    payload = artifacts(capture(tmp_path))
    payload["records.xml"] = payload["records.xml"].replace(b"Synthetic", b"Altered", 1)
    payload = mutate_receipt(payload, lambda receipt: receipt.update(records_sha256=hashlib.sha256(payload["records.xml"]).hexdigest()))
    with pytest.raises(ValueError, match="content differs"):
        validate_pubmed_artifacts(payload)


def test_mapping_extras_reject_but_directory_annotations_are_ignored(tmp_path):
    directory = capture(tmp_path)
    payload = artifacts(directory)
    payload["notes.txt"] = b"unrelated"
    with pytest.raises(ValueError, match="unsupported files"):
        validate_pubmed_artifacts(payload)
    (directory / "notes.txt").write_text("unrelated")
    (directory / ".DS_Store").write_bytes(b"unrelated")
    assert verify_pubmed_capture(directory)["receipt"]["complete"]
    with ReviewStore(":memory:") as store:
        project_id = project(store)
        result = import_pubmed_capture(store, project_id, directory)
        assert "notes.txt" not in store.get_search_artifacts(project_id, result["search_run_id"])


def test_symlinked_declared_artifact_rejected(tmp_path):
    directory = capture(tmp_path)
    original = directory / "records.xml"
    outside = tmp_path / "outside.xml"
    original.rename(outside)
    original.symlink_to(outside)
    with pytest.raises(ValueError, match="symlinks"):
        verify_pubmed_capture(directory)
    assert outside.exists()


def test_import_uses_single_byte_snapshot_when_file_changes(monkeypatch, tmp_path):
    directory = capture(tmp_path)
    original = artifacts(directory)
    reader = Path.read_bytes
    reads = []

    def read(path):
        content = reader(path)
        if path == directory / "records.xml":
            reads.append(path)
            path.write_bytes(b"changed after read")
        return content

    monkeypatch.setattr(Path, "read_bytes", read)
    with ReviewStore(":memory:") as store:
        project_id = project(store)
        result = import_pubmed_capture(store, project_id, directory)
        assert len(reads) == 1
        assert store.get_search_artifacts(project_id, result["search_run_id"]) == original
        assert len(store.list_records(project_id)) == 5


def test_record_identity_conflict_rolls_back_records_run_and_assets(tmp_path):
    directory = capture(tmp_path)
    payload = artifacts(directory)
    parsed = validate_pubmed_artifacts(payload)["records"]
    conflicting = next(record for record in parsed if record.doi)
    with ReviewStore(":memory:") as store:
        project_id = project(store)
        store.import_records(project_id, SearchRunSpec("seed"), [BibliographicRecord(title="Existing synthetic record", doi="10.1234/conflict", pmid=conflicting.pmid)])
        prior = store.counts(project_id), store.list_search_runs(project_id), store.get_occurrences(project_id)
        with pytest.raises(ValueError, match="Conflicting"):
            import_pubmed_capture(store, project_id, directory)
        assert (store.counts(project_id), store.list_search_runs(project_id), store.get_occurrences(project_id)) == prior
        assert store._connection.execute("SELECT COUNT(*) FROM search_artifacts").fetchone()[0] == 0


def test_direct_receipt_only_import_and_cross_project_artifact_access_rejected(tmp_path):
    directory = capture(tmp_path)
    validated = validate_pubmed_artifacts(artifacts(directory))
    with ReviewStore(":memory:") as store:
        project_id = project(store)
        with pytest.raises(ValueError, match="supplied together"):
            store.import_records(project_id, SearchRunSpec("PubMed", execution=validated["receipt"]), validated["records"])
        result = import_pubmed_capture(store, project_id, directory)
        other = project(store)
        for supplied_project, run_id in [(project_id, "unknown"), (other, result["search_run_id"]), ("unknown", result["search_run_id"])]:
            with pytest.raises(ValueError):
                store.get_search_artifacts(supplied_project, run_id)
