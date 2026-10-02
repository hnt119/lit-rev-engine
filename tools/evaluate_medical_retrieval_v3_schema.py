"""Receipt-gated held-out wrapper for the frozen v3 publisher-URL schema.

Only the exact v3 gold manifest is adapted, in memory. The frozen evaluator,
selection guards, retrieval, metrics, inputs and persistent files are unchanged.
The coordinator must authorize and pin these two new repair files first.
"""

from contextlib import contextmanager
from copy import deepcopy
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import parse_qsl, urlsplit


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_FILE = "tests/fixtures/medical_retrieval_v3/manifest.json"
FREEZE_FILE = "tests/fixtures/medical_retrieval_v3/freeze.json"
DEVELOPMENT_FILE = "docs/medical-retrieval-development-v3.json"
SELECTION_FILE = "docs/medical-retrieval-selection-v3.json"
REPAIR_FILE = "docs/medical-retrieval-v3-schema-repair.json"
REPAIR_FILES = (
    "tools/evaluate_medical_retrieval_v3_schema.py",
    "tests/test_medical_retrieval_schema_adapter.py",
)
INDEPENDENT_ACCEPTANCE_FILE = "tests/test_medical_retrieval_schema_adapter_acceptance.py"
REPAIR_STATUS = "coordinator_authorized_schema_repair_before_held_out_retry"


def normalize_publisher_url(value):
    """Normalize one primary PLOS article URL; never fetch or infer a URL."""
    if not isinstance(value, str) or not value or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Invalid publisher article URL")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.netloc.lower() != "journals.plos.org" or parsed.fragment:
        raise ValueError("Publisher article URL must use the exact HTTPS PLOS origin")
    try:
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as error:
        raise ValueError("Invalid publisher article URL query") from error
    if len(pairs) != 1 or pairs[0][0] != "id":
        raise ValueError("Publisher article URL must contain exactly one DOI id")
    doi = pairs[0][1]
    match = re.fullmatch(r"10\.1371/journal\.(pmed|pone)\.[0-9]+", doi)
    if match is None:
        raise ValueError("Publisher article URL has an unsupported DOI")
    journal = "plosmedicine" if match.group(1) == "pmed" else "plosone"
    if parsed.path != f"/{journal}/article":
        raise ValueError("Publisher article URL path differs from its DOI journal")
    return f"https://journals.plos.org/{journal}/article?id={doi}", doi


def resolve_publisher_article_url(source):
    """Use explicit top-level or verified acquisition-record URL metadata only."""
    if not isinstance(source, dict) or not isinstance(source.get("doi"), str):
        raise ValueError("Source DOI metadata is missing")
    candidates = []
    if "publisher_article_url" in source:
        candidates.append(source["publisher_article_url"])
    if "acquisition_record" in source:
        acquisition = source["acquisition_record"]
        if not isinstance(acquisition, dict):
            raise ValueError("Invalid acquisition metadata")
        for key in ("publisher_url", "publisher_article_url"):
            if key in acquisition:
                candidates.append(acquisition[key])
    if not candidates:
        raise ValueError("Publisher article URL metadata is missing")
    normalized = [normalize_publisher_url(value) for value in candidates]
    if len({url for url, _ in normalized}) != 1:
        raise ValueError("Conflicting publisher article URL metadata")
    url, doi = normalized[0]
    if doi != source["doi"]:
        raise ValueError("Publisher article URL DOI differs from source DOI")
    return url


def adapt_manifest(manifest):
    """Return a copy adding only missing source.publisher_article_url fields."""
    if not isinstance(manifest, dict) or not isinstance(manifest.get("sources"), list) or not manifest["sources"]:
        raise ValueError("Selected manifest source metadata is missing")
    result = deepcopy(manifest)
    for source in result["sources"]:
        url = resolve_publisher_article_url(source)
        if "publisher_article_url" not in source:
            source["publisher_article_url"] = url
    return result


@contextmanager
def publisher_reader_adapter(evaluator, root=None):
    """Temporarily adapt only the exact selected manifest; always restore reader."""
    directory = ROOT if root is None else Path(root)
    target = (directory / MANIFEST_FILE).resolve()
    original = evaluator.read_json

    def read(path):
        value = original(path)
        return adapt_manifest(value) if Path(path).resolve() == target else value

    evaluator.read_json = read
    try:
        yield
    finally:
        evaluator.read_json = original


def pin(path):
    raw = Path(path).read_bytes()
    return {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}


def verify_receipt_file_pins(directory, pins, expected_files, label):
    if not isinstance(pins, dict) or set(pins) != set(expected_files):
        raise ValueError("Exact " + label + " file pins are required")
    for name in expected_files:
        expected = pins[name]
        if (not isinstance(expected, dict) or set(expected) != {"sha256", "size_bytes"}
                or type(expected["size_bytes"]) is not int or expected["size_bytes"] < 0
                or not isinstance(expected["sha256"], str)
                or re.fullmatch(r"[0-9a-f]{64}", expected["sha256"]) is None
                or pin(directory / name) != expected):
            raise ValueError(label + " file pin mismatch: " + name)


def validate_repair_receipt(selection_path, root=None):
    """Verify coordinator phase and all repair/base pins before evaluator calls."""
    directory = (ROOT if root is None else Path(root)).resolve()
    receipt_path = directory / REPAIR_FILE
    try:
        raw = receipt_path.read_bytes()
        receipt = json.loads(raw)
    except (OSError, ValueError) as error:
        raise ValueError("Coordinator schema-repair receipt is missing or invalid") from error
    if not isinstance(receipt, dict) or type(receipt.get("schema_version")) is not int or receipt["schema_version"] != 1 or receipt.get("status") != REPAIR_STATUS:
        raise ValueError("Invalid coordinator schema-repair status")
    if receipt.get("phase") != "before_held_out_retry" or receipt.get("held_out_ranked_during_failed_attempt") is not False:
        raise ValueError("Schema repair must precede held-out retry after an unranked failed attempt")
    for file_key, hash_key, expected_file in (
        ("base_freeze_file", "base_freeze_sha256", FREEZE_FILE),
        ("development_result_file", "development_result_sha256", DEVELOPMENT_FILE),
        ("selection_receipt_file", "selection_receipt_sha256", SELECTION_FILE),
    ):
        if receipt.get(file_key) != expected_file:
            raise ValueError("Unexpected schema-repair input path: " + file_key)
        if pin(directory / expected_file)["sha256"] != receipt.get(hash_key):
            raise ValueError("Schema-repair input hash mismatch: " + file_key)
    selection = Path(selection_path)
    if not selection.is_absolute():
        selection = directory / selection
    if selection.resolve() != (directory / SELECTION_FILE).resolve():
        raise ValueError("Schema wrapper requires the exact pinned coordinator selection receipt")
    verify_receipt_file_pins(directory, receipt.get("repair_files"), REPAIR_FILES, "Schema-repair")
    if "independent_acceptance_files" in receipt:
        verify_receipt_file_pins(directory, receipt["independent_acceptance_files"], (INDEPENDENT_ACCEPTANCE_FILE,), "Independent acceptance")
    return {"receipt_file": REPAIR_FILE, "receipt_sha256": hashlib.sha256(raw).hexdigest(),
            "selection_path": (directory / SELECTION_FILE).resolve()}


def evaluate_held_out(selection_path):
    repair = validate_repair_receipt(selection_path)
    # Import only after receipt validation. All original freeze, selection,
    # checker, evaluation, metric and no-network guards execute unchanged.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    evaluator = importlib.import_module("tools.evaluate_medical_retrieval_v3")
    with publisher_reader_adapter(evaluator):
        result = evaluator.evaluate("held-out", repair["selection_path"])
    return {**result, "schema_repair_receipt_file": repair["receipt_file"],
            "schema_repair_receipt_sha256": repair["receipt_sha256"]}


def write_result(path, result):
    output = Path(path)
    if output.exists():
        raise FileExistsError("Evaluation output already exists; preserve prior bytes")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("held-out",), default="held-out")
    parser.add_argument("--selection", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if Path(args.output).exists():
        parser.error("Evaluation output already exists; preserve prior bytes")
    result = evaluate_held_out(args.selection)
    write_result(args.output, result)
    print(json.dumps({"split": result["split"], "schema_repair_receipt_file": result["schema_repair_receipt_file"],
                      "schema_repair_receipt_sha256": result["schema_repair_receipt_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
