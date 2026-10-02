"""Independent captured-byte-chain and durable-ledger integration acceptance."""

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timedelta
import csv
import hashlib
import json
from pathlib import Path
import shutil
import socket
import sqlite3
import xml.etree.ElementTree as ET

import pytest

from src.review.importers import load_records_bytes
from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.store import ReviewStore
from src.search.pubmed_search import (
    PubMedClient,
    capture_pubmed_search,
    import_pubmed_capture,
    validate_pubmed_artifacts,
    verify_pubmed_capture,
)


FIXTURES = Path(__file__).parent / "fixtures" / "pubmed"
ORDER = ["999999803", "999999801", "999999805", "999999802", "999999804"]


@pytest.fixture(autouse=True)
def no_live_network_or_sleep(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Integration acceptance attempted live network or sleep")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr("time.sleep", denied)


class FixtureClient:
    def __init__(self, responses):
        self.responses = list(responses)

    def request(self, endpoint, params):
        assert self.responses
        return self.responses.pop(0)


@pytest.fixture
def valid_capture(tmp_path):
    oracle = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    responses = [(FIXTURES / oracle["search_file"]).read_bytes()]
    responses.extend((FIXTURES / batch["response_file"]).read_bytes() for batch in oracle["batches"])
    result = capture_pubmed_search(oracle["query"], tmp_path / "original-capture", client=FixtureClient(responses),
                                   filters=oracle["filters"], sort=oracle["sort"], batch_size=2)
    artifacts = {path.relative_to(result["directory"]).as_posix(): path.read_bytes()
                 for path in Path(result["directory"]).rglob("*") if path.is_file()}
    assert len(artifacts) == 6
    return result, artifacts


def new_project(store, title="Synthetic capture review"):
    return store.create_project(title, "scoping", "What synthetic records were captured?")["id"]


def receipt_from(artifacts):
    return json.loads(artifacts["receipt.json"].decode("utf-8"))


def receipt_bytes(receipt):
    return (json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def change_receipt(artifacts, change):
    altered = dict(artifacts)
    receipt = receipt_from(altered)
    change(receipt)
    altered["receipt.json"] = receipt_bytes(receipt)
    return altered


def capture_spec(receipt, source_file="/synthetic-capture/records.xml"):
    return SearchRunSpec(
        source="PubMed", query=receipt["query"], searched_at=receipt["searched_at"],
        filters=receipt["filters"], import_format="pubmed_xml", source_file=source_file,
        source_sha256=receipt["records_sha256"], reported_count=receipt["reported_count"], execution=receipt,
    )


def ledger_snapshot(store, project_id):
    runs = store.list_search_runs(project_id)
    return deepcopy({
        "runs": runs, "records": store.list_records(project_id), "occurrences": store.get_occurrences(project_id),
        "counts": store.counts(project_id),
        "artifacts": {run["id"]: store.get_search_artifacts(project_id, run["id"]) for run in runs},
    })


def replace_artifact(artifacts, name, content, *, update_hash=True):
    changed = dict(artifacts)
    changed[name] = content
    if update_hash:
        receipt = receipt_from(changed)
        digest = hashlib.sha256(content).hexdigest()
        if name == "records.xml":
            receipt["records_sha256"] = digest
        else:
            next(request for request in receipt["requests"] if request["response_file"] == name)["response_sha256"] = digest
        changed["receipt.json"] = receipt_bytes(receipt)
    return changed


def test_verified_capture_bytes_survive_reopen_export_source_deletion_and_offline_replay(tmp_path, valid_capture):
    original, artifacts = valid_capture
    validated = validate_pubmed_artifacts(artifacts)
    assert validated["receipt"] == original["receipt"]
    assert [record.pmid for record in validated["records"]] == ORDER
    verified = verify_pubmed_capture(original["directory"])
    assert verified == original
    database = tmp_path / "reviews.sqlite3"
    with ReviewStore(database) as store:
        project_id = new_project(store)
        imported = import_pubmed_capture(store, project_id, original["directory"], idempotency_key="capture-001")
        assert imported["identified"] == imported["new_records"] == 5 and imported["duplicates"] == 0
        run_id = imported["search_run_id"]
        assert store.get_search_artifacts(project_id, run_id) == artifacts
        assert import_pubmed_capture(store, project_id, original["directory"], idempotency_key="capture-001") == imported
        assert len(store.list_search_runs(project_id)) == 1
        run = store.list_search_runs(project_id)[0]
        assert run["execution"] == original["receipt"]
        for field in ("source", "query", "searched_at", "filters", "reported_count"):
            assert run[field] == original["receipt"][field]
        assert run["import_format"] == "pubmed_xml"
        assert run["source_file"] == str((Path(original["directory"]) / "records.xml").resolve())
        assert run["source_sha256"] == hashlib.sha256(artifacts["records.xml"]).hexdigest()
        assert [row["record"] for row in store.get_occurrences(project_id)] == [asdict(row) for row in validated["records"]]
        before = ledger_snapshot(store, project_id)
    shutil.rmtree(original["directory"])
    with ReviewStore(database) as reopened:
        assert ledger_snapshot(reopened, project_id) == before
        directory = tmp_path / "exported"
        directory.mkdir()
        (directory / "unrelated.txt").write_text("Keep unrelated destination content", encoding="utf-8")
        exported = reopened.export_project(project_id, directory)
        assert len(exported["files"]) == 15
        bundle = json.loads((directory / "project.json").read_text(encoding="utf-8"))
        assert bundle["search_runs"][0]["execution"] == original["receipt"]
        manifest = bundle["search_artifacts"]
        assert len(manifest) == len(artifacts) == 6
        for entry in manifest:
            name = entry["name"]
            expected_path = f"search_captures/{run_id}/{name}"
            assert entry == {"search_run_id": run_id, "name": name, "sha256": hashlib.sha256(artifacts[name]).hexdigest(),
                             "size_bytes": len(artifacts[name]), "export_file": expected_path}
            assert (directory / expected_path).read_bytes() == artifacts[name]
            assert expected_path in exported["files"]
        with (directory / "search_runs.csv").open(encoding="utf-8", newline="") as handle:
            assert json.loads(list(csv.DictReader(handle))[0]["execution"]) == original["receipt"]
        assert (directory / "unrelated.txt").read_text(encoding="utf-8") == "Keep unrelated destination content"
        copied_capture = directory / "search_captures" / run_id
        assert verify_pubmed_capture(copied_capture)["receipt"] == original["receipt"]
        assert import_pubmed_capture(reopened, project_id, copied_capture, idempotency_key="capture-001") == imported
        assert ledger_snapshot(reopened, project_id) == before
        assert reopened.list_search_runs(project_id)[0]["source_file"] == str(Path(original["xml_file"]))
        second_project = new_project(reopened, "Offline replay review")
        replay = import_pubmed_capture(reopened, second_project, copied_capture, idempotency_key="capture-001")
        assert replay["identified"] == replay["new_records"] == 5 and replay["duplicates"] == 0
        assert reopened.get_search_artifacts(second_project, replay["search_run_id"]) == artifacts
        assert reopened.list_search_runs(second_project)[0]["execution"] == original["receipt"]
        assert [row["record"] for row in reopened.get_occurrences(second_project)] == [asdict(row) for row in validated["records"]]
        second_directory = tmp_path / "exported-again"
        reopened.export_project(project_id, second_directory)
        assert {name: (directory / name).read_bytes() for name in exported["files"]} == {
            name: (second_directory / name).read_bytes() for name in exported["files"]
        }


def test_validator_uses_only_supplied_bytes_and_makes_no_file_reads(monkeypatch, valid_capture):
    _, artifacts = valid_capture
    def denied(*args, **kwargs):
        pytest.fail("Pure artifact validation read a file")
    monkeypatch.setattr(Path, "read_bytes", denied)
    monkeypatch.setattr(Path, "read_text", denied)
    monkeypatch.setattr(Path, "open", denied)
    result = validate_pubmed_artifacts(artifacts)
    assert [record.pmid for record in result["records"]] == ORDER


def test_zero_result_capture_is_durable_history_with_three_assets_and_no_invented_records(tmp_path):
    oracle = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))["zero"]
    source = (FIXTURES / oracle["search_file"]).read_bytes()
    capture = capture_pubmed_search(oracle["query"], tmp_path / "zero-capture", client=FixtureClient([source]))
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = new_project(store)
        imported = import_pubmed_capture(store, project_id, capture["directory"])
        assert imported["identified"] == imported["new_records"] == imported["duplicates"] == 0
        assert store.list_records(project_id) == store.get_occurrences(project_id) == []
        run = store.list_search_runs(project_id)[0]
        assert run["reported_count"] == 0 and run["execution"] == capture["receipt"]
        assets = store.get_search_artifacts(project_id, imported["search_run_id"])
        assert set(assets) == {"receipt.json", "records.xml", "search.xml"}
        assert assets["search.xml"] == source
        exported = store.export_project(project_id, tmp_path / "zero-export")
        assert len(exported["files"]) == 12 and exported["counts"]["unique_records"] == 0
        assert exported["counts"]["all_checks_passed"] is True
        exported_capture = tmp_path / "zero-export" / "search_captures" / imported["search_run_id"]
        assert verify_pubmed_capture(exported_capture)["receipt"] == capture["receipt"]


def test_import_parses_and_stores_same_single_byte_snapshot_during_file_mutation(tmp_path, monkeypatch, valid_capture):
    original, artifacts = valid_capture
    source_records = Path(original["xml_file"])
    read_bytes = Path.read_bytes
    reads = []
    def read_then_mutate(path):
        content = read_bytes(path)
        if path.resolve() == source_records.resolve():
            reads.append(content)
            path.write_bytes(b"Mutated after snapshot read")
        return content
    monkeypatch.setattr(Path, "read_bytes", read_then_mutate)
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = new_project(store)
        imported = import_pubmed_capture(store, project_id, original["directory"])
        assert len(reads) == 1 and reads[0] == artifacts["records.xml"]
        assert store.get_search_artifacts(project_id, imported["search_run_id"])["records.xml"] == artifacts["records.xml"]
        assert [row["pmid"] for row in store.list_records(project_id)] == ORDER
        assert store.counts(project_id)["unique_records"] == 5
    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    with pytest.raises(ValueError):
        verify_pubmed_capture(original["directory"])


@pytest.mark.parametrize("source_file", ["records.xml", "batches/0001.xml", "search.xml"])
def test_changed_source_bytes_without_updated_hash_are_rejected_without_ledger_mutation(tmp_path, valid_capture, source_file):
    _, artifacts = valid_capture
    changed = dict(artifacts)
    changed[source_file] += b"\n"
    with pytest.raises(ValueError):
        validate_pubmed_artifacts(changed)
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = new_project(store)
        before = ledger_snapshot(store, project_id)
        with pytest.raises(ValueError):
            store.import_records(project_id, capture_spec(receipt_from(changed)), load_records_bytes(artifacts["records.xml"], "xml"), artifacts=changed)
        assert ledger_snapshot(store, project_id) == before


@pytest.mark.parametrize("changed_file", ["records.xml", "batches/0001.xml"])
def test_recomputed_hash_cannot_hide_combined_record_text_disagreeing_with_saved_sources(valid_capture, changed_file):
    _, artifacts = valid_capture
    root = ET.fromstring(artifacts[changed_file])
    title = root.find(".//ArticleTitle")
    assert title is not None
    title.text = "Altered synthetic title while retaining identical own PMIDs"
    changed = replace_artifact(artifacts, changed_file, ET.tostring(root, encoding="utf-8", xml_declaration=True))
    assert receipt_from(changed)["reported_count"] == 5
    with pytest.raises(ValueError):
        validate_pubmed_artifacts(changed)


@pytest.mark.parametrize("field,value", [
    ("schema_version", True), ("schema_version", 2), ("source", "Other source"), ("adapter", "other.v1"),
    ("complete", False), ("complete", "true"), ("reported_count", True), ("fetched_count", "5"),
    ("query", "Changed query only"), ("query_translation", "Changed translation"), ("sort", "relevance"),
    ("filters", {"datetype": "pdat", "mindate": "2021", "maxdate": "2025"}),
    ("warnings", []), ("history", {"webenv": "different", "query_key": "1"}),
    ("records_file", "../records.xml"), ("records_sha256", "bad digest"),
    ("started_at", "2026-10-03T04:00:00"), ("searched_at", "2026-10-03T12:00:00+08:00"),
    ("completed_at", "1900-01-01T00:00:00+00:00"), ("searched_at", "not a date"),
    ("unknown_field", "Unknown receipt metadata"),
])
def test_receipt_type_metadata_time_and_source_contradictions_are_rejected(valid_capture, field, value):
    _, artifacts = valid_capture
    changed = change_receipt(artifacts, lambda receipt: receipt.__setitem__(field, value))
    with pytest.raises(ValueError):
        validate_pubmed_artifacts(changed)


@pytest.mark.parametrize("variant", ["duplicate_receipt_key", "nonfinite", "wrong_json_type", "missing_required_field"])
def test_receipt_json_is_strict_and_complete(valid_capture, variant):
    _, artifacts = valid_capture
    changed = dict(artifacts)
    if variant == "duplicate_receipt_key":
        changed["receipt.json"] = artifacts["receipt.json"].rstrip()[:-1] + b', "complete": true}'
    elif variant == "nonfinite":
        changed["receipt.json"] = artifacts["receipt.json"].replace(b'"reported_count": 5', b'"reported_count": NaN')
        assert changed["receipt.json"] != artifacts["receipt.json"]
    elif variant == "wrong_json_type":
        changed["receipt.json"] = b"[]"
    else:
        changed = change_receipt(artifacts, lambda receipt: receipt.pop("requests"))
    with pytest.raises(ValueError):
        validate_pubmed_artifacts(changed)


@pytest.mark.parametrize("variant", ["missing_batch", "extra_name", "traversal_name", "absolute_name", "backslash_name", "declared_traversal", "unexpected_request_param"])
def test_exact_artifact_mapping_and_declared_relative_paths_are_enforced(valid_capture, variant):
    _, artifacts = valid_capture
    changed = dict(artifacts)
    if variant == "missing_batch":
        changed.pop("batches/0001.xml")
    elif variant == "extra_name":
        changed["notes.txt"] = b"Unrelated mapping asset"
    elif variant == "traversal_name":
        changed["../search.xml"] = changed.pop("search.xml")
    elif variant == "absolute_name":
        changed["/tmp/search.xml"] = changed.pop("search.xml")
    elif variant == "backslash_name":
        changed["batches\\0001.xml"] = changed.pop("batches/0001.xml")
    elif variant == "declared_traversal":
        changed = change_receipt(changed, lambda receipt: receipt["requests"][1].__setitem__("response_file", "batches/../search.xml"))
    else:
        changed = change_receipt(changed, lambda receipt: receipt["requests"][0]["params"].__setitem__("unexpected", "value"))
    with pytest.raises(ValueError):
        validate_pubmed_artifacts(changed)


@pytest.mark.parametrize("variant", ["batch_id_order", "batch_duplicate", "boolean_retstart", "receipt_member_order"])
def test_receipt_requests_must_describe_exact_ordered_membership_with_typed_search_params(valid_capture, variant):
    _, artifacts = valid_capture
    def mutate(receipt):
        if variant == "batch_id_order":
            receipt["requests"][1]["params"]["id"] = "999999801,999999803"
        elif variant == "batch_duplicate":
            receipt["requests"][2]["params"]["id"] = receipt["requests"][1]["params"]["id"]
        elif variant == "boolean_retstart":
            receipt["requests"][0]["params"]["retstart"] = False
        else:
            receipt["pmids"][0], receipt["pmids"][1] = receipt["pmids"][1], receipt["pmids"][0]
    with pytest.raises(ValueError):
        validate_pubmed_artifacts(change_receipt(artifacts, mutate))


@pytest.mark.parametrize("secret_field", ["api_key", "email", "tool"])
def test_operational_credentials_are_rejected_from_execution_metadata_and_errors(valid_capture, secret_field):
    _, artifacts = valid_capture
    secret = "SYNTHETIC_DURABILITY_SECRET"
    changed = change_receipt(artifacts, lambda receipt: receipt["requests"][0]["params"].__setitem__(secret_field, secret))
    with pytest.raises(ValueError) as failure:
        validate_pubmed_artifacts(changed)
    assert secret not in str(failure.value)


def test_operational_api_key_never_enters_sqlite_blobs_history_or_exports(tmp_path):
    oracle = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    responses = [(FIXTURES / oracle["search_file"]).read_bytes()]
    responses.extend((FIXTURES / batch["response_file"]).read_bytes() for batch in oracle["batches"])
    key = "SYNTHETIC_SQLITE_CREDENTIAL_NEVER_PERSIST"
    operational_bodies = []
    clock = [0.0]
    def transport(url, data, timeout):
        operational_bodies.append(data)
        return responses.pop(0)
    def sleep(seconds):
        clock[0] += seconds
    client = PubMedClient("synthetic@example.invalid", api_key=key, transport=transport,
                          sleep=sleep, monotonic=lambda: clock[0])
    captured = capture_pubmed_search(oracle["query"], tmp_path / "credential-capture", client=client,
                                     filters=oracle["filters"], batch_size=2)
    assert len(operational_bodies) == 4 and all(key.encode() in body for body in operational_bodies)
    database = tmp_path / "reviews.sqlite3"
    with ReviewStore(database) as store:
        project_id = new_project(store)
        imported = import_pubmed_capture(store, project_id, captured["directory"])
        assert key not in json.dumps(store.list_search_runs(project_id))
        assert all(key.encode() not in content for content in store.get_search_artifacts(project_id, imported["search_run_id"]).values())
        directory = tmp_path / "credential-export"
        exported = store.export_project(project_id, directory)
        assert all(key.encode() not in (directory / name).read_bytes() for name in exported["files"])
    assert key.encode() not in database.read_bytes()


@pytest.mark.parametrize("symlink_target", ["search.xml", "batches"])
def test_verification_rejects_declared_file_or_directory_symlinks_and_preserves_files(tmp_path, valid_capture, symlink_target):
    original, artifacts = valid_capture
    capture_dir = Path(original["directory"])
    path = capture_dir / symlink_target
    outside = tmp_path / ("outside-" + symlink_target.replace("/", "-"))
    path.rename(outside)
    path.symlink_to(outside, target_is_directory=outside.is_dir())
    with pytest.raises(ValueError):
        verify_pubmed_capture(capture_dir)
    assert path.is_symlink() and outside.exists()
    if outside.is_file():
        assert outside.read_bytes() == artifacts[symlink_target]


def test_unrelated_directory_notes_are_ignored_but_never_stored(tmp_path, valid_capture):
    original, artifacts = valid_capture
    directory = Path(original["directory"])
    (directory / "notes.txt").write_text("Unrelated notes", encoding="utf-8")
    assert verify_pubmed_capture(directory)["receipt"] == original["receipt"]
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = new_project(store)
        imported = import_pubmed_capture(store, project_id, directory)
        assert store.get_search_artifacts(project_id, imported["search_run_id"]) == artifacts
    assert (directory / "notes.txt").read_text(encoding="utf-8") == "Unrelated notes"


def test_identity_conflict_rolls_back_new_reports_run_and_all_artifact_bytes(tmp_path, valid_capture):
    _, artifacts = valid_capture
    # R4's801 has no DOI. Add one consistently to temporary source/combined bytes
    # so a conflict at the second report occurs after803 has been newly inserted.
    changed = dict(artifacts)
    for name in ("batches/0001.xml", "records.xml"):
        root = ET.fromstring(changed[name])
        record = next(child for child in root if child.find("MedlineCitation/PMID") is not None
                      and child.find("MedlineCitation/PMID").text == "999999801")
        ET.SubElement(record.find("MedlineCitation/Article"), "ELocationID", {"EIdType": "doi"}).text = "10.5555/evaluation-late-doi"
        changed = replace_artifact(changed, name, ET.tostring(root, encoding="utf-8", xml_declaration=True))
    reports = validate_pubmed_artifacts(changed)["records"]
    second = reports[1]
    assert second.pmid == "999999801" and second.doi
    directory = tmp_path / "late-conflict-capture"
    for name, content in changed.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = new_project(store)
        store.import_records(project_id, SearchRunSpec(source="Legacy conflicting record"), [
            BibliographicRecord(title="Prior record with conflicting DOI", pmid=second.pmid, doi="10.5555/conflicting-existing"),
        ])
        before = ledger_snapshot(store, project_id)
        with pytest.raises(ValueError):
            import_pubmed_capture(store, project_id, directory)
        assert ledger_snapshot(store, project_id) == before


def test_unknown_or_cross_project_runs_cannot_expose_artifacts(tmp_path, valid_capture):
    original, artifacts = valid_capture
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        first_id = new_project(store)
        second_id = new_project(store, "Other project")
        imported = import_pubmed_capture(store, first_id, original["directory"])
        run_id = imported["search_run_id"]
        for project_id, target_run in (("unknown-project", run_id), (second_id, run_id), (first_id, "unknown-run")):
            with pytest.raises(ValueError):
                store.get_search_artifacts(project_id, target_run)
        assert store.get_search_artifacts(first_id, run_id) == artifacts
        prior = ledger_snapshot(store, first_id)
        with pytest.raises(ValueError):
            import_pubmed_capture(store, "unknown-project", original["directory"])
        assert ledger_snapshot(store, first_id) == prior


@pytest.mark.parametrize("missing", ["execution", "artifacts"])
def test_complete_execution_claim_requires_its_source_bytes_and_matching_spec(tmp_path, valid_capture, missing):
    original, artifacts = valid_capture
    spec = capture_spec(original["receipt"])
    if missing == "execution":
        spec = SearchRunSpec(source="PubMed")
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = new_project(store)
        before = ledger_snapshot(store, project_id)
        with pytest.raises(ValueError):
            store.import_records(project_id, spec, load_records_bytes(artifacts["records.xml"], "xml"),
                                 artifacts=None if missing == "artifacts" else artifacts)
        assert ledger_snapshot(store, project_id) == before


@pytest.mark.parametrize("field,value", [("source", "Other"), ("query", "different"), ("source_sha256", "0" * 64), ("reported_count", 4)])
def test_direct_artifact_import_rejects_mismatching_search_spec_transactionally(tmp_path, valid_capture, field, value):
    original, artifacts = valid_capture
    fields = asdict(capture_spec(original["receipt"]))
    fields[field] = value
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = new_project(store)
        before = ledger_snapshot(store, project_id)
        with pytest.raises(ValueError):
            store.import_records(project_id, SearchRunSpec(**fields), load_records_bytes(artifacts["records.xml"], "xml"), artifacts=artifacts)
        assert ledger_snapshot(store, project_id) == before


def test_direct_import_cannot_attach_valid_source_bytes_to_changed_record_payload(tmp_path, valid_capture):
    original, artifacts = valid_capture
    records = load_records_bytes(artifacts["records.xml"], "xml")
    changed_records = [replace(records[0], title="Unsupported title supplied outside verified bytes"), *records[1:]]
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = new_project(store)
        before = ledger_snapshot(store, project_id)
        with pytest.raises(ValueError):
            store.import_records(project_id, capture_spec(original["receipt"]), changed_records, artifacts=artifacts)
        assert ledger_snapshot(store, project_id) == before


def test_changed_valid_receipt_under_key_fails_and_original_artifacts_remain_immutable(tmp_path, valid_capture):
    original, artifacts = valid_capture
    changed_receipt = deepcopy(original["receipt"])
    for field in ("started_at", "searched_at", "completed_at"):
        changed_receipt[field] = (datetime.fromisoformat(changed_receipt[field]) + timedelta(seconds=1)).isoformat()
    changed_artifacts = dict(artifacts)
    changed_artifacts["receipt.json"] = receipt_bytes(changed_receipt)
    validated = validate_pubmed_artifacts(changed_artifacts)
    assert validated["receipt"] == changed_receipt
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = new_project(store)
        imported = import_pubmed_capture(store, project_id, original["directory"], idempotency_key="immutable-key")
        before = ledger_snapshot(store, project_id)
        spec = capture_spec(changed_receipt, source_file=original["xml_file"])
        with pytest.raises(ValueError):
            store.import_records(project_id, spec, validated["records"], idempotency_key="immutable-key", artifacts=changed_artifacts)
        assert ledger_snapshot(store, project_id) == before
        fresh = store.import_records(project_id, spec, validated["records"], artifacts=changed_artifacts)
        assert fresh["identified"] == fresh["duplicates"] == 5 and fresh["new_records"] == 0
        assert store.get_search_artifacts(project_id, imported["search_run_id"]) == artifacts
        assert store.get_search_artifacts(project_id, fresh["search_run_id"]) == changed_artifacts


@pytest.mark.parametrize("execution,artifacts", [(None, None), ({}, None), (None, {}), ({}, {})])
def test_pre_extension_key_fingerprint_retries_unchanged_with_empty_new_fields(tmp_path, execution, artifacts):
    database = tmp_path / "reviews.sqlite3"
    record = BibliographicRecord(title="Historical generic import", doi="10.5555/legacy-key")
    legacy_spec = {
        "source": "Legacy RIS", "query": None, "searched_at": None, "filters": {}, "notes": "",
        "import_format": "ris", "source_file": "historical.ris", "source_sha256": "", "reported_count": None,
    }
    with ReviewStore(database) as store:
        project_id = new_project(store)
        result = store.import_records(project_id, SearchRunSpec(**legacy_spec), [record], idempotency_key="historical-key")
    # Reconstitute the historical on-disk spec/fingerprint from the pre-extension format.
    encode = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    historical_fingerprint = hashlib.sha256(encode({"spec": legacy_spec, "records": [asdict(record)]}).encode()).hexdigest()
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE search_runs SET spec=?, fingerprint=? WHERE id=?", (encode(legacy_spec), historical_fingerprint, result["search_run_id"]))
    with ReviewStore(database) as reopened:
        assert reopened.list_search_runs(project_id)[0]["execution"] is None
        assert reopened.import_records(project_id, SearchRunSpec(**legacy_spec, execution=execution), [record],
                                       idempotency_key="historical-key", artifacts=artifacts) == result
        assert len(reopened.list_search_runs(project_id)) == len(reopened.get_occurrences(project_id)) == 1
        assert reopened.get_search_artifacts(project_id, result["search_run_id"]) == {}
        exported = reopened.export_project(project_id, tmp_path / "generic-export")
        assert len(exported["files"]) == 9
        bundle = json.loads((tmp_path / "generic-export" / "project.json").read_text(encoding="utf-8"))
        assert not bundle.get("search_artifacts")
        with (tmp_path / "generic-export" / "search_runs.csv").open(encoding="utf-8", newline="") as handle:
            assert list(csv.DictReader(handle))[0]["execution"] == ""


def test_artifact_export_uses_same_read_snapshot_during_second_writer_import(tmp_path, monkeypatch, valid_capture):
    original, artifacts = valid_capture
    database = tmp_path / "reviews.sqlite3"
    with ReviewStore(database) as store:
        project_id = new_project(store)
        first = import_pubmed_capture(store, project_id, original["directory"])
        before = ledger_snapshot(store, project_id)
        with sqlite3.connect(database) as connection:
            assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        list_records = store.list_records
        second_import = []
        def read_then_commit(pid):
            rows = list_records(pid)
            if not second_import:
                with ReviewStore(database) as writer:
                    second_import.append(import_pubmed_capture(writer, project_id, original["directory"]))
            return rows
        monkeypatch.setattr(store, "list_records", read_then_commit)
        exported = store.export_project(project_id, tmp_path / "snapshot-export")
        bundle = json.loads((tmp_path / "snapshot-export" / "project.json").read_text(encoding="utf-8"))
        assert second_import and second_import[0]["duplicates"] == 5
        assert bundle["counts"] == before["counts"]
        assert len(bundle["search_runs"]) == 1 and len(bundle["search_artifacts"]) == 6
        assert {row["search_run_id"] for row in bundle["search_artifacts"]} == {first["search_run_id"]}
        assert len(exported["files"]) == 15
        assert store.counts(project_id)["records_identified"] == 10
        assert store.counts(project_id)["duplicate_records_removed"] == 5
        assert store.get_search_artifacts(project_id, second_import[0]["search_run_id"]) == artifacts


@pytest.mark.parametrize("damage", ["content", "stored_digest"])
def test_corrupted_sqlite_artifact_hash_blocks_export_before_replacing_destination(tmp_path, valid_capture, damage):
    original, _ = valid_capture
    database = tmp_path / "reviews.sqlite3"
    with ReviewStore(database) as store:
        project_id = new_project(store)
        imported = import_pubmed_capture(store, project_id, original["directory"])
    # Simulate external corruption of an otherwise immutable SQLite asset.
    with sqlite3.connect(database) as connection:
        if damage == "content":
            connection.execute("UPDATE search_artifacts SET content=? WHERE search_run_id=? AND name='records.xml'",
                               (b"Corrupt persisted artifact", imported["search_run_id"]))
        else:
            connection.execute("UPDATE search_artifacts SET sha256=? WHERE search_run_id=? AND name='records.xml'",
                               ("0" * 64, imported["search_run_id"]))
    destination = tmp_path / "exported"
    destination.mkdir()
    (destination / "project.json").write_text("Existing output", encoding="utf-8")
    (destination / "notes.txt").write_text("Unrelated file", encoding="utf-8")
    with ReviewStore(database) as reopened:
        with pytest.raises(ValueError, match="hash"):
            reopened.export_project(project_id, destination)
        assert reopened.counts(project_id)["unique_records"] == 5
    assert (destination / "project.json").read_text(encoding="utf-8") == "Existing output"
    assert (destination / "notes.txt").read_text(encoding="utf-8") == "Unrelated file"
    assert len(list(destination.iterdir())) == 2
