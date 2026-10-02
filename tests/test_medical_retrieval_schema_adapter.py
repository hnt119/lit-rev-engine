"""Synthetic metadata-only tests; never open medical QA, source or result files."""

from copy import deepcopy
import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import evaluate_medical_retrieval_v3_schema as adapter


MEDICINE = "https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1004510"
MRI = "https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0188679"


def source(url=MEDICINE, key="publisher_url", doi="10.1371/journal.pmed.1004510"):
    return {"alias": "synthetic", "doi": doi, "file": "never-open.xml", "source_sha256": "f" * 64,
            "acquisition_record": {key: url, "unchanged": {"license": "CC-BY-4.0"}}}


class PublisherMetadataTests(unittest.TestCase):
    def test_both_acquisition_schemas_and_encoded_doi_normalize_exactly(self):
        row = source(MEDICINE.replace("10.1371/", "10.1371%2F"))
        before = deepcopy(row)
        self.assertEqual(adapter.resolve_publisher_article_url(row), MEDICINE)
        self.assertEqual(row, before)
        self.assertEqual(adapter.resolve_publisher_article_url(source(MRI, "publisher_article_url", "10.1371/journal.pone.0188679")), MRI)

    def test_only_missing_top_level_field_added_without_input_mutation(self):
        manifest = {"schema_version": 1, "sources": [source()], "splits": {"held-out": {"file": "never-read.json"}}, "sentinel": [1, 2]}
        before = deepcopy(manifest)
        result = adapter.adapt_manifest(manifest)
        expected = deepcopy(before)
        expected["sources"][0]["publisher_article_url"] = MEDICINE
        self.assertEqual(result, expected)
        self.assertEqual(manifest, before)

    def test_equivalent_existing_url_preserved_and_conflicts_rejected(self):
        row = source()
        row["publisher_article_url"] = MEDICINE.replace("10.1371/", "10.1371%2F")
        self.assertEqual(adapter.adapt_manifest({"sources": [row]})["sources"][0], row)
        row["publisher_article_url"] = MRI
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            adapter.resolve_publisher_article_url(row)

    def test_missing_invalid_and_doi_mismatches_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            adapter.resolve_publisher_article_url({"doi": "10.1371/journal.pmed.1004510"})
        invalid = [None, "", "http://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1004510",
                   MEDICINE + "&token=signed", MEDICINE + "#fragment", MEDICINE + "&id=duplicate",
                   MEDICINE.replace("journals.plos.org", "example.com"), MEDICINE.replace("/article", "/article/file"),
                   MEDICINE.replace("/plosmedicine/", "/plosone/"), MEDICINE + "\n"]
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(ValueError):
                adapter.resolve_publisher_article_url(source(url))
        with self.assertRaisesRegex(ValueError, "differs from source DOI"):
            adapter.resolve_publisher_article_url(source(doi="10.1371/journal.pmed.1004629"))

    def test_exact_manifest_only_other_reader_values_untouched_and_finally_restored(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            expected = root / adapter.MANIFEST_FILE
            wrong = root / "other/manifest.json"
            payload = {"sources": [source()]}
            calls = []
            def reader(path):
                calls.append(Path(path))
                return payload
            evaluator = SimpleNamespace(read_json=reader)
            with adapter.publisher_reader_adapter(evaluator, root):
                self.assertIs(evaluator.read_json(wrong), payload)
                self.assertEqual(evaluator.read_json(expected)["sources"][0]["publisher_article_url"], MEDICINE)
                self.assertEqual(calls, [wrong, expected])
                self.assertNotIn("publisher_article_url", payload["sources"][0])
            self.assertIs(evaluator.read_json, reader)
            with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
                with adapter.publisher_reader_adapter(evaluator, root):
                    raise RuntimeError("synthetic failure")
            self.assertIs(evaluator.read_json, reader)


class RepairReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        for name in (adapter.FREEZE_FILE, adapter.DEVELOPMENT_FILE, adapter.SELECTION_FILE, *adapter.REPAIR_FILES):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("synthetic pinned file: " + name).encode())
        self.receipt = {"schema_version": 1, "status": adapter.REPAIR_STATUS, "phase": "before_held_out_retry",
                        "held_out_ranked_during_failed_attempt": False,
                        "base_freeze_file": adapter.FREEZE_FILE, "base_freeze_sha256": adapter.pin(self.root / adapter.FREEZE_FILE)["sha256"],
                        "development_result_file": adapter.DEVELOPMENT_FILE, "development_result_sha256": adapter.pin(self.root / adapter.DEVELOPMENT_FILE)["sha256"],
                        "selection_receipt_file": adapter.SELECTION_FILE, "selection_receipt_sha256": adapter.pin(self.root / adapter.SELECTION_FILE)["sha256"],
                        "repair_files": {name: adapter.pin(self.root / name) for name in adapter.REPAIR_FILES}}
        self.write_receipt()

    def write_receipt(self):
        path = self.root / adapter.REPAIR_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.receipt), encoding="utf-8")

    def test_valid_receipt_exact_selection_and_no_base_file_changes(self):
        originals = {name: (self.root / name).read_bytes() for name in (adapter.FREEZE_FILE, adapter.DEVELOPMENT_FILE, adapter.SELECTION_FILE, *adapter.REPAIR_FILES)}
        record = adapter.validate_repair_receipt(adapter.SELECTION_FILE, self.root)
        self.assertEqual(record["receipt_file"], adapter.REPAIR_FILE)
        self.assertEqual(record["receipt_sha256"], adapter.pin(self.root / adapter.REPAIR_FILE)["sha256"])
        self.assertEqual(record["selection_path"], self.root / adapter.SELECTION_FILE)
        self.assertEqual(originals, {name: (self.root / name).read_bytes() for name in originals})

    def test_missing_or_wrong_phase_status_receipts_block_before_evaluator_import(self):
        for mutation in ("missing", "status", "phase", "already_ranked"):
            with self.subTest(mutation=mutation):
                self.write_receipt()
                if mutation == "missing":
                    (self.root / adapter.REPAIR_FILE).unlink()
                else:
                    changed = deepcopy(self.receipt)
                    changed[{"status": "status", "phase": "phase", "already_ranked": "held_out_ranked_during_failed_attempt"}[mutation]] = True if mutation == "already_ranked" else "invalid"
                    (self.root / adapter.REPAIR_FILE).write_text(json.dumps(changed))
                with patch.object(adapter, "ROOT", self.root), patch.object(adapter.importlib, "import_module") as load, self.assertRaises(ValueError):
                    adapter.evaluate_held_out(adapter.SELECTION_FILE)
                load.assert_not_called()

    def test_mutated_missing_and_unexpected_repair_pins_rejected(self):
        for mutation in ("adapter", "test", "missing_pin", "extra_pin"):
            with self.subTest(mutation=mutation):
                changed = deepcopy(self.receipt)
                if mutation in ("adapter", "test"):
                    name = adapter.REPAIR_FILES[0 if mutation == "adapter" else 1]
                    changed["repair_files"][name]["sha256"] = "0" * 64
                elif mutation == "missing_pin":
                    changed["repair_files"].pop(adapter.REPAIR_FILES[1])
                else:
                    changed["repair_files"]["other.py"] = {"sha256": "0" * 64, "size_bytes": 0}
                (self.root / adapter.REPAIR_FILE).write_text(json.dumps(changed))
                with self.assertRaises(ValueError):
                    adapter.validate_repair_receipt(adapter.SELECTION_FILE, self.root)

    def test_actual_changed_or_missing_repair_bytes_block_before_evaluator_import(self):
        for name in adapter.REPAIR_FILES:
            path = self.root / name
            original = path.read_bytes()
            for missing in (False, True):
                with self.subTest(name=name, missing=missing):
                    if missing:
                        path.unlink()
                    else:
                        path.write_bytes(original + b"changed")
                    with patch.object(adapter, "ROOT", self.root), patch.object(adapter.importlib, "import_module") as load, self.assertRaises((ValueError, OSError)):
                        adapter.evaluate_held_out(adapter.SELECTION_FILE)
                    load.assert_not_called()
                    path.write_bytes(original)

    def test_optional_independent_acceptance_pin_has_exact_set_and_strict_bytes(self):
        path = self.root / adapter.INDEPENDENT_ACCEPTANCE_FILE
        path.write_bytes(b"synthetic independent acceptance test bytes")
        self.receipt["independent_acceptance_files"] = {adapter.INDEPENDENT_ACCEPTANCE_FILE: adapter.pin(path)}
        self.write_receipt()
        adapter.validate_repair_receipt(adapter.SELECTION_FILE, self.root)
        original = deepcopy(self.receipt["independent_acceptance_files"])
        for bad in ({}, None, {"tests/wrong-acceptance.py": adapter.pin(path)},
                    {adapter.INDEPENDENT_ACCEPTANCE_FILE: {"sha256": "0" * 64, "size_bytes": path.stat().st_size}},
                    {adapter.INDEPENDENT_ACCEPTANCE_FILE: {"sha256": adapter.pin(path)["sha256"], "size_bytes": True}}):
            with self.subTest(pin=bad):
                self.receipt["independent_acceptance_files"] = bad
                self.write_receipt()
                with patch.object(adapter, "ROOT", self.root), patch.object(adapter.importlib, "import_module") as load, self.assertRaises(ValueError):
                    adapter.evaluate_held_out(adapter.SELECTION_FILE)
                load.assert_not_called()
        self.receipt["independent_acceptance_files"] = original
        self.write_receipt()
        path.write_bytes(b"changed independent acceptance bytes")
        with self.assertRaises(ValueError):
            adapter.validate_repair_receipt(adapter.SELECTION_FILE, self.root)

    def test_base_hash_path_and_selection_mismatches_rejected(self):
        for key in ("base_freeze_sha256", "development_result_sha256", "selection_receipt_sha256", "base_freeze_file"):
            with self.subTest(key=key):
                changed = deepcopy(self.receipt)
                changed[key] = "wrong"
                (self.root / adapter.REPAIR_FILE).write_text(json.dumps(changed))
                with self.assertRaises(ValueError):
                    adapter.validate_repair_receipt(adapter.SELECTION_FILE, self.root)
        self.write_receipt()
        with self.assertRaisesRegex(ValueError, "exact pinned"):
            adapter.validate_repair_receipt("docs/other-selection.json", self.root)

    def test_wrapper_calls_frozen_held_only_with_metadata_adapter_and_restores_reader(self):
        payload = {"sources": [source()], "unchanged": ["synthetic"]}
        before = deepcopy(payload)
        calls = []
        def reader(path):
            self.assertEqual(Path(path), self.root / adapter.MANIFEST_FILE)
            calls.append("manifest metadata only")
            return payload
        original_result = {"split": "held-out", "held_out_ranked": True, "sentinel": {"metrics": "unchanged synthetic sentinel"}}
        evaluator = SimpleNamespace(read_json=reader)
        def evaluate(split, selection):
            self.assertEqual(split, "held-out")
            self.assertEqual(selection, self.root / adapter.SELECTION_FILE)
            value = evaluator.read_json(self.root / adapter.MANIFEST_FILE)
            expected = deepcopy(before)
            expected["sources"][0]["publisher_article_url"] = MEDICINE
            self.assertEqual(value, expected)
            return original_result
        evaluator.evaluate = evaluate
        with patch.object(adapter, "ROOT", self.root), patch.object(adapter.importlib, "import_module", return_value=evaluator), patch.object(sys, "path", list(sys.path)):
            result = adapter.evaluate_held_out(adapter.SELECTION_FILE)
        self.assertEqual(calls, ["manifest metadata only"])
        self.assertEqual(payload, before)
        self.assertIs(evaluator.read_json, reader)
        self.assertEqual(set(result) - set(original_result), {"schema_repair_receipt_file", "schema_repair_receipt_sha256"})
        self.assertEqual({key: result[key] for key in original_result}, original_result)
        self.assertNotIn("schema_repair_receipt_file", original_result)
        evaluator.evaluate = lambda *args: (_ for _ in ()).throw(RuntimeError("synthetic evaluator failure"))
        with patch.object(adapter, "ROOT", self.root), patch.object(adapter.importlib, "import_module", return_value=evaluator), patch.object(sys, "path", list(sys.path)), self.assertRaises(RuntimeError):
            adapter.evaluate_held_out(adapter.SELECTION_FILE)
        self.assertIs(evaluator.read_json, reader)

    def test_fresh_process_direct_entry_uses_only_synthetic_metadata_evaluator(self):
        script = self.root / adapter.REPAIR_FILES[0]
        script.write_bytes(Path(adapter.__file__).read_bytes())
        stub = self.root / "tools/evaluate_medical_retrieval_v3.py"
        stub.write_text(
            "import json\nfrom pathlib import Path\n"
            "ROOT = Path(__file__).resolve().parents[1]\n"
            "def read_json(path): return json.loads(Path(path).read_text())\n"
            "def evaluate(split, selection):\n"
            "    assert split == 'held-out'\n"
            "    assert selection == ROOT / 'docs/medical-retrieval-selection-v3.json'\n"
            "    metadata = read_json(ROOT / 'tests/fixtures/medical_retrieval_v3/manifest.json')\n"
            "    assert metadata['sources'][0]['publisher_article_url'] == '" + MEDICINE + "'\n"
            "    return {'split': split, 'synthetic_metadata_only': True}\n",
            encoding="utf-8")
        manifest = self.root / adapter.MANIFEST_FILE
        manifest.parent.mkdir(parents=True, exist_ok=True)
        payload = {"sources": [source()]}
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        original_manifest = manifest.read_bytes()
        self.receipt["repair_files"] = {name: adapter.pin(self.root / name) for name in adapter.REPAIR_FILES}
        self.write_receipt()
        outside = self.root / "outside-repository"
        outside.mkdir()
        output = outside / "synthetic-result.json"
        result = subprocess.run([sys.executable, str(script), "--selection", adapter.SELECTION_FILE, "--output", str(output)],
                                cwd=outside, env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": ""},
                                capture_output=True, text=True, check=True, timeout=10)
        report = json.loads(output.read_text())
        self.assertTrue(report["synthetic_metadata_only"])
        self.assertEqual(report["split"], "held-out")
        self.assertEqual(report["schema_repair_receipt_sha256"], adapter.pin(self.root / adapter.REPAIR_FILE)["sha256"])
        self.assertEqual(manifest.read_bytes(), original_manifest)
        self.assertEqual(json.loads(result.stdout)["split"], "held-out")

    def test_result_refuses_overwrite_and_cli_refuses_development(self):
        path = self.root / "synthetic-result.json"
        path.write_bytes(b"preserve these prior bytes")
        with self.assertRaises(FileExistsError):
            adapter.write_result(path, {"synthetic": True})
        self.assertEqual(path.read_bytes(), b"preserve these prior bytes")
        with patch("sys.argv", ["adapter", "--split", "development", "--selection", "unused", "--output", "unused"]), patch.object(adapter, "evaluate_held_out") as evaluate, contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            adapter.main()
        evaluate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
