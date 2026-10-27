"""Byte-bound build-only omission of three unused pywin32 optional APIs.

This does not execute Windows code or change pywin32's loader, .pth, metadata,
licenses, or any retained Python byte. Unknown wheel/file variants fail closed.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "apps/desktop/windows-core-pruning.json"
POLICY_SOURCE_PATH = "apps/desktop/windows-core-pruning.json"
POLICY_COPY_PATH = "resources/WINDOWS_PYWIN32_POLICY.json"
RECEIPT_PATH = "resources/WINDOWS_PYWIN32_SUBSET.json"
SITE = "resources/python/Lib/site-packages/"
ALLOWED_DIRECTORIES = (
    SITE + "pythonwin",
    SITE + "win32comext/mapi",
    SITE + "win32comext/axdebug",
)
WHEEL = {
    "name": "pywin32", "version": "312",
    "filename": "pywin32-312-cp312-cp312-win_amd64.whl",
    "sha256": "b457f6d628a47e8a7346ce22acb7e1a46a4a78b52e1d17e1af56871bd19a93bc",
}


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _path(root, relative):
    parsed = PurePosixPath(relative)
    if not isinstance(relative, str) or "\\" in relative or parsed.is_absolute() or ".." in parsed.parts or parsed.as_posix() != relative:
        raise ValueError("Unsafe Windows Core policy path.")
    result = root.joinpath(*parsed.parts)
    current = root
    if current.is_symlink() or not current.is_dir():
        raise ValueError("Windows Core payload root must be an ordinary directory.")
    for part in parsed.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Windows Core inputs must not contain links.")
    return result


def _file(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Missing or linked Windows Core input: " + path.name)
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": _digest(data)}


def _check(root, files):
    if not isinstance(files, dict) or not files:
        raise ValueError("Windows Core policy requires a nonempty file inventory.")
    for relative, expected in files.items():
        if not isinstance(expected, dict) or set(expected) != {"bytes", "sha256"} or _file(_path(root, relative)) != expected:
            raise ValueError("Windows Core wheel byte mismatch: " + relative)


def _inventory(root, directory, omitted):
    result = {}
    base = _path(root, directory)
    if not base.is_dir():
        raise ValueError("Missing Windows Python tree.")
    for item in sorted(base.rglob("*")):
        if item.is_symlink():
            raise ValueError("Linked Windows Python payload input.")
        if item.is_dir():
            continue
        relative = item.relative_to(root).as_posix()
        if relative not in omitted:
            result[relative] = _file(item)
    return result


def _wheel_report(path, wheel):
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    found = [item for item in report.get("install", []) if item.get("metadata", {}).get("name", "").lower() == "pywin32"]
    if len(found) != 1:
        raise ValueError("One exact pywin32 wheel installation report is required.")
    item = found[0]
    info = item.get("download_info", {})
    hashes = info.get("archive_info", {}).get("hashes", {})
    if (item["metadata"].get("version") != wheel["version"]
            or unquote(PurePosixPath(urlsplit(info.get("url", "")).path).name) != wheel["filename"]
            or hashes.get("sha256") != wheel["sha256"]):
        raise ValueError("Windows Core pywin32 wheel identity mismatch.")


def _record(root, policy):
    record_path = policy["record_path"]
    expected_path = SITE + "pywin32-312.dist-info/RECORD"
    if record_path != expected_path:
        raise ValueError("Unexpected pywin32 RECORD identity.")
    rows = list(csv.reader(io.StringIO(_path(root, record_path).read_text(encoding="utf-8"))))
    if any(len(row) != 3 for row in rows) or len({row[0] for row in rows}) != len(rows):
        raise ValueError("Malformed or duplicate pywin32 RECORD rows.")
    actual = {name: (hash_value, size) for name, hash_value, size in rows}
    full = policy["wheel_record_files"]
    removed = policy["record_removed_entrypoints"]
    allowed_removed = {"../../bin/pywin32_postinstall", "../../bin/pywin32_postinstall.py", "../../bin/pywin32_testall", "../../bin/pywin32_testall.py"}
    if not isinstance(removed, list) or set(removed) != allowed_removed or len(removed) != len(allowed_removed):
        raise ValueError("Unexpected removed pywin32 build entry point.")
    expected = {relative.removeprefix(SITE) for relative in full} | set(removed) | {record_path.removeprefix(SITE)}
    if set(actual) != expected or actual[record_path.removeprefix(SITE)] != ("", ""):
        raise ValueError("pywin32 RECORD file set differs from the reviewed wheel policy.")
    for relative, entry in full.items():
        if not relative.startswith(SITE):
            raise ValueError("pywin32 RECORD policy escaped site-packages.")
        encoded = base64.urlsafe_b64encode(bytes.fromhex(entry["sha256"])).decode("ascii").rstrip("=")
        if actual[relative.removeprefix(SITE)] != ("sha256=" + encoded, str(entry["bytes"])):
            raise ValueError("pywin32 RECORD hash mismatch: " + relative)
    _check(root, full)


def prune_optional_pywin32(resources, wheel_report, *, policy_path=POLICY_PATH):
    """Preflight the pinned wheel, omit only reviewed optional dirs, bind proof.

    `resources` is the candidate app's resources directory. The original wheel's
    RECORD intentionally remains unchanged; the receipt explains this subset.
    """
    resources = Path(resources)
    root = resources.parent
    if resources.name != "resources" or resources.is_symlink() or not resources.is_dir():
        raise ValueError("Supply an ordinary candidate resources directory.")
    raw_policy = Path(policy_path).read_bytes()
    policy = json.loads(raw_policy)
    if policy.get("schema") != "litrev.windows.optional-pywin32-policy.v1" or policy.get("wheel") != WHEEL:
        raise ValueError("Unknown Windows Core wheel/pruning policy.")
    if tuple(policy.get("omitted_directories", [])) != ALLOWED_DIRECTORIES:
        raise ValueError("Only the three reviewed optional pywin32 directories may be omitted.")
    omitted = policy["omitted_files"]
    protected = policy["protected_files"]
    if not omitted or set(omitted) & set(protected) or not policy.get("unsupported_optional_apis"):
        raise ValueError("Missing omission/protection/limitation policy.")
    if any(not any(relative.startswith(prefix + "/") for prefix in ALLOWED_DIRECTORIES) for relative in omitted):
        raise ValueError("Omission escaped the three optional pywin32 components.")
    if any(relative not in policy["wheel_record_files"] or policy["wheel_record_files"][relative] != entry for relative, entry in omitted.items()):
        raise ValueError("Omitted bytes are not pinned original wheel bytes.")
    for output in (POLICY_COPY_PATH, RECEIPT_PATH):
        if _path(root, output).exists():
            raise ValueError("Never overwrite an existing Windows Core subset receipt.")
    _wheel_report(wheel_report, policy["wheel"])
    _record(root, policy)
    _check(root, protected)
    # Exact component file AND directory keysets prevent unknown/empty extras.
    actual = {}
    for prefix in ALLOWED_DIRECTORIES:
        directory = _path(root, prefix)
        if not directory.is_dir():
            raise ValueError("Missing reviewed optional pywin32 directory.")
        expected_dirs = {prefix}
        for relative in omitted:
            if relative.startswith(prefix + "/"):
                parent = PurePosixPath(relative).parent
                while parent.as_posix().startswith(prefix):
                    expected_dirs.add(parent.as_posix())
                    parent = parent.parent
        actual_dirs = {prefix}
        for item in directory.rglob("*"):
            relative = item.relative_to(root).as_posix()
            if item.is_symlink():
                raise ValueError("Linked optional pywin32 component.")
            if item.is_dir():
                actual_dirs.add(relative)
            else:
                actual[relative] = _file(item)
        if actual_dirs != expected_dirs:
            raise ValueError("Unexpected optional pywin32 component directory.")
    if actual != omitted:
        raise ValueError("Optional pywin32 component files differ from reviewed policy.")
    retained = _inventory(root, "resources/python", set(omitted))
    # No deletion occurs until every preflight above has passed. Recheck each
    # byte immediately before unlink; no recursive broad-directory deletion.
    for relative, expected in omitted.items():
        path = _path(root, relative)
        if _file(path) != expected:
            raise ValueError("Optional pywin32 input changed during pruning.")
        path.unlink()
    for prefix in ALLOWED_DIRECTORIES:
        directory = _path(root, prefix)
        for item in sorted(directory.rglob("*"), key=lambda path: len(path.parts), reverse=True):
            if item.is_symlink() or not item.is_dir():
                raise ValueError("Unexpected content while removing empty optional directories.")
            item.rmdir()
        directory.rmdir()
    after = _inventory(root, "resources/python", set())
    if after != retained:
        raise ValueError("Retained Windows Python bytes changed during pruning.")
    _check(root, protected)
    (root / POLICY_COPY_PATH).write_bytes(raw_policy)
    receipt = {
        "schema": "litrev.windows.optional-pywin32-subset.v1",
        "policy_path": POLICY_SOURCE_PATH,
        "packaged_policy_path": POLICY_COPY_PATH,
        "policy_sha256": _digest(raw_policy),
        "wheel": policy["wheel"],
        "omitted_directories": policy["omitted_directories"],
        "omitted_files": omitted,
        "protected_files": protected,
        "preserved_python_inventory": {"files": len(after), "bytes": sum(entry["bytes"] for entry in after.values()), "sha256": _digest(json_bytes(after))},
        "unsupported_optional_apis": policy["unsupported_optional_apis"],
        "runtime_execution": "NOT_RUN",
    }
    raw_receipt = json_bytes(receipt)
    (root / RECEIPT_PATH).write_bytes(raw_receipt)
    return {
        "schema": "litrev.windows.optional-pywin32-subset-binding.v1",
        "receipt_path": RECEIPT_PATH,
        "receipt_sha256": _digest(raw_receipt),
        "omitted_file_count": len(omitted),
        "runtime_execution": "NOT_RUN",
    }
