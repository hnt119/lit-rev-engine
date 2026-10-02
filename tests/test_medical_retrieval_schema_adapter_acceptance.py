"""Independent schema-boundary acceptance using synthetic files and evaluators only."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tools import evaluate_medical_retrieval_v3_schema as adapter


URL = "https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1234567"
IMAGE_URL = "https://journals.plos.org/plosone/article?id=10.1371/journal.pone.7654321"
INDEPENDENT_FILE = "tests/test_medical_retrieval_schema_adapter_acceptance.py"
BASES = (
    (adapter.FREEZE_FILE, "base_freeze_file", "base_freeze_sha256"),
    (adapter.DEVELOPMENT_FILE, "development_result_file", "development_result_sha256"),
    (adapter.SELECTION_FILE, "selection_receipt_file", "selection_receipt_sha256"),
)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def independent_pin(path):
    data = path.read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def selected_metadata():
    return {"sources": [
        {"doi": "10.1371/journal.pmed.1234567", "acquisition_record": {"publisher_url": URL},
         "arbitrary": {"span": [0, 8], "text": "\u03b1\n\te\u0301"}},
        {"doi": "10.1371/journal.pone.7654321", "acquisition_record": {"publisher_article_url": IMAGE_URL}},
        {"doi": "10.1371/journal.pmed.1234567", "publisher_article_url": URL.replace("10.1371/", "10.1371%2F")},
    ], "untouched": {"questions": "synthetic sentinel only", "numeric": [1, 2.0, None, False]}}


@pytest.fixture
def repair(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    for name in [row[0] for row in BASES] + list(adapter.REPAIR_FILES) + [INDEPENDENT_FILE]:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("Synthetic pinned input: " + name).encode())
    receipt = {"schema_version": 1, "status": adapter.REPAIR_STATUS,
               "phase": "before_held_out_retry", "held_out_ranked_during_failed_attempt": False,
               "repair_files": {name: independent_pin(root / name) for name in adapter.REPAIR_FILES},
               "independent_acceptance_files": {INDEPENDENT_FILE: independent_pin(root / INDEPENDENT_FILE)}}
    for name, file_key, hash_key in BASES:
        receipt[file_key] = name
        receipt[hash_key] = independent_pin(root / name)["sha256"]

    def write(value=receipt):
        path = root / adapter.REPAIR_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical(value))

    write()
    monkeypatch.setattr(adapter, "ROOT", root)
    load = Mock(side_effect=AssertionError("Receipt rejection must precede evaluator import/query"))
    monkeypatch.setattr(adapter.importlib, "import_module", load)
    return root, receipt, write, load


def test_literal_preservation_and_scope_with_actual_synthetic_file(tmp_path):
    metadata = selected_metadata()
    snapshot = canonical(metadata)
    target = tmp_path / adapter.MANIFEST_FILE
    target.parent.mkdir(parents=True)
    target.write_bytes(snapshot)
    other = tmp_path / "unselected/manifest.json"
    other.parent.mkdir()
    other.write_bytes(b'{"sources": "invalid but untouched"}')
    values = {target: metadata, other: {"sources": "invalid but untouched"}}
    reader = lambda path: values[Path(path)]
    evaluator = SimpleNamespace(read_json=reader)
    with adapter.publisher_reader_adapter(evaluator, tmp_path):
        result = evaluator.read_json(target)
        assert result is not metadata
        assert result["sources"][0]["publisher_article_url"] == URL
        assert result["sources"][1]["publisher_article_url"] == IMAGE_URL
        assert result["sources"][2]["publisher_article_url"] == metadata["sources"][2]["publisher_article_url"]
        restored = deepcopy(result)
        for index in (0, 1):
            del restored["sources"][index]["publisher_article_url"]
        assert canonical(restored) == snapshot
        assert evaluator.read_json(other) is values[other]
        result["untouched"]["numeric"].append("independent mutation")
        assert canonical(metadata) == snapshot
    assert evaluator.read_json is reader
    assert target.read_bytes() == snapshot
    assert other.read_bytes() == b'{"sources": "invalid but untouched"}'


@pytest.mark.parametrize("invalid", [None, 5, "", URL + "\x00", URL + "\t", URL + "#anchor",
    URL.replace("https:", "http:"), URL.replace("journals.plos.org", "journals.plos.org:443"),
    URL.replace("journals.plos.org", "user@journals.plos.org"), URL.replace("journals.plos.org", "journals.plos.org.evil.test"),
    URL.replace("/plosmedicine/", "/plosone/"), URL.replace("/article?", "/article/file?"),
    URL + "&id=10.1371/journal.pmed.1234567", URL + "&download=1", URL.replace("?id=", "?doi="),
    URL.replace("1234567", "%ZZ"), URL.replace("10.1371", "10.9999")])
def test_invalid_url_never_produces_manifest(invalid):
    value = selected_metadata()
    value["sources"][0]["acquisition_record"]["publisher_url"] = invalid
    before = deepcopy(value)
    with pytest.raises(ValueError):
        adapter.adapt_manifest(value)
    assert value == before


@pytest.mark.parametrize("change", ["no_urls", "wrong_doi", "bad_acquisition", "conflicting_nested", "conflicting_top"])
def test_missing_identity_or_conflict_rejects_complete_adaptation(change):
    value = selected_metadata()
    row = value["sources"][0]
    if change == "no_urls":
        del row["acquisition_record"]
    elif change == "wrong_doi":
        row["doi"] = "10.1371/journal.pmed.7654321"
    elif change == "bad_acquisition":
        row["acquisition_record"] = []
    else:
        owner = row["acquisition_record"] if change == "conflicting_nested" else row
        owner["publisher_article_url"] = IMAGE_URL
    snapshot = canonical(value)
    with pytest.raises(ValueError):
        adapter.adapt_manifest(value)
    assert canonical(value) == snapshot


@pytest.mark.parametrize("change", ["missing", "invalid_json", "schema_bool", "status", "phase", "ranked", "ranked_zero",
    "freeze_path", "development_hash", "selection_hash", "repair_extra", "repair_missing", "repair_size_bool",
    "repair_size", "repair_hash", "independent_extra", "independent_empty", "independent_hash"])
def test_receipt_mutations_block_before_evaluator_import(repair, change):
    root, receipt, write, load = repair
    value = deepcopy(receipt)
    receipt_path = root / adapter.REPAIR_FILE
    if change == "missing":
        receipt_path.unlink()
    elif change == "invalid_json":
        receipt_path.write_bytes(b'{"not complete"')
    else:
        if change == "schema_bool": value["schema_version"] = True
        elif change == "status": value["status"] = "not authorized"
        elif change == "phase": value["phase"] = "after_held_out"
        elif change == "ranked": value["held_out_ranked_during_failed_attempt"] = True
        elif change == "ranked_zero": value["held_out_ranked_during_failed_attempt"] = 0
        elif change == "freeze_path": value["base_freeze_file"] = "../freeze.json"
        elif change == "development_hash": value["development_result_sha256"] = "0" * 64
        elif change == "selection_hash": value["selection_receipt_sha256"] = "0" * 64
        elif change == "repair_extra": value["repair_files"]["other.py"] = {"sha256": "0" * 64, "size_bytes": 0}
        elif change == "repair_missing": del value["repair_files"][adapter.REPAIR_FILES[-1]]
        elif change.startswith("repair_"):
            entry = value["repair_files"][adapter.REPAIR_FILES[0]]
            entry["size_bytes" if "size" in change else "sha256"] = True if change == "repair_size_bool" else (0 if change == "repair_size" else "G" * 64)
        elif change == "independent_extra": value["independent_acceptance_files"]["other.py"] = {"sha256": "0" * 64, "size_bytes": 0}
        elif change == "independent_empty": value["independent_acceptance_files"] = {}
        elif change == "independent_hash": value["independent_acceptance_files"][INDEPENDENT_FILE]["sha256"] = "0" * 64
        write(value)
    with pytest.raises((ValueError, OSError)):
        adapter.evaluate_held_out(adapter.SELECTION_FILE)
    load.assert_not_called()


@pytest.mark.parametrize("name", [row[0] for row in BASES] + list(adapter.REPAIR_FILES) + [INDEPENDENT_FILE])
@pytest.mark.parametrize("missing", [False, True])
def test_every_changed_or_missing_pinned_file_stops_before_import(repair, name, missing):
    root, _, _, load = repair
    path = root / name
    if missing:
        path.unlink()
    else:
        path.write_bytes(path.read_bytes() + b"\nchanged bytes")
    with pytest.raises((ValueError, OSError)):
        adapter.evaluate_held_out(adapter.SELECTION_FILE)
    load.assert_not_called()


def test_valid_wrapper_preserves_result_and_restores_reader_after_bad_metadata(repair):
    root, _, _, load = repair
    payload = selected_metadata()
    reader = lambda path: payload
    evaluator = SimpleNamespace(read_json=reader)
    original_result = {"split": "held-out", "sentinel": {"metrics": [0, False, "unchanged"]}}
    calls = []
    def evaluate(split, selection):
        calls.append((split, selection))
        adapted = evaluator.read_json(root / adapter.MANIFEST_FILE)
        assert adapted["sources"][0]["publisher_article_url"] == URL
        return original_result
    evaluator.evaluate = evaluate
    load.side_effect = None
    load.return_value = evaluator
    before = canonical(original_result)
    result = adapter.evaluate_held_out(adapter.SELECTION_FILE)
    assert calls == [("held-out", root / adapter.SELECTION_FILE)]
    assert evaluator.read_json is reader
    assert result["schema_repair_receipt_file"] == adapter.REPAIR_FILE
    assert result["schema_repair_receipt_sha256"] == independent_pin(root / adapter.REPAIR_FILE)["sha256"]
    for field in ("schema_repair_receipt_file", "schema_repair_receipt_sha256"):
        del result[field]
    assert canonical(result) == before == canonical(original_result)
    payload["sources"][0]["acquisition_record"]["publisher_url"] = None
    with pytest.raises(ValueError):
        adapter.evaluate_held_out(adapter.SELECTION_FILE)
    assert evaluator.read_json is reader


def test_wrong_selection_path_is_rejected_before_import(repair):
    _, _, _, load = repair
    with pytest.raises(ValueError):
        adapter.evaluate_held_out("docs/other-selection.json")
    load.assert_not_called()
