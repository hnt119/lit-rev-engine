#!/usr/bin/env python3
"""Prepare an immutable real-project component bundle; never execute inference."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.review_components import core
from src.review_components.ledger import execution_paths


BOOTSTRAP_PIN = {"sha256": "b81fcf821708b40ee5cce907858851595cc58df01a9f8a9e24c8d68b457ff41c", "size_bytes": 16118}
WHEEL_PIN = {
    "version": "25.2", "filename": "pip-25.2-py3-none-any.whl",
    "url": "https://files.pythonhosted.org/packages/b7/3f/945ef7ab14dc4f9d7f40288d2df998d1837ee0888ec3659c813487572faa/pip-25.2-py3-none-any.whl",
    "size_bytes": 1752557, "sha256": "6d67a2b4e7f14d8b31b8b52648866fa717f45a1eb70e83002f4331d07e953717",
}
MEMBERS = ("job.json", "component_core.py", "qwen_kaggle_environment.py",
           "qwen_components_kaggle_runner.py", "qwen_kaggle_bootstrap.py")
ARTIFACT_BYTES = 100 * 1024 * 1024


def binding(body):
    return {"sha256": hashlib.sha256(body).hexdigest(), "size_bytes": len(body)}


def _capture_job_bytes(path):
    with path.open("rb") as stream:
        body = stream.read(ARTIFACT_BYTES + 1)
    core.require(len(body) <= ARTIFACT_BYTES, "Original job exceeds artifact bound during preparation")
    return body


def _cell(kind, source):
    cell = {"id": hashlib.sha256(source.encode("utf-8")).hexdigest()[:12],
            "cell_type": kind, "metadata": {}, "source": source.splitlines(keepends=True)}
    if kind == "code":
        cell.update(execution_count=None, outputs=[])
    return cell


def _notebook(job_sha256, profile_sha256):
    configuration = f'''import os
from pathlib import Path

# Set the exact directory containing the five attached private dataset files.
BUNDLE = Path('/kaggle/input/REPLACE_WITH_PRIVATE_DATASET_DIRECTORY')
JOB_PATH = BUNDLE / 'job.json'
CORE_PATH = BUNDLE / 'component_core.py'
HELPER_PATH = BUNDLE / 'qwen_kaggle_environment.py'
RUNNER_PATH = BUNDLE / 'qwen_components_kaggle_runner.py'
BOOTSTRAP_PATH = BUNDLE / 'qwen_kaggle_bootstrap.py'
JOB_SHA256 = {job_sha256!r}
PROFILE_SHA256 = {profile_sha256!r}
BOOTSTRAP_SHA256 = {BOOTSTRAP_PIN['sha256']!r}
BOOTSTRAP_SIZE_BYTES = {BOOTSTRAP_PIN['size_bytes']}
OUTPUT_PATH = Path('/kaggle/working/components-results.json')
CHECKPOINT_PATH = Path('/kaggle/working/components-checkpoint.json')
AUDIT_PATH = Path('/kaggle/working/components-environment-audit.json')
INSTALLER_REPORT_PATH = Path('/kaggle/working/components-installer-report.json')
BOOTSTRAP_AUDIT_PATH = Path('/kaggle/working/components-bootstrap-audit.json')
os.environ['HF_HOME'] = '/kaggle/temp/components-huggingface'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
'''
    preflight = '''import hashlib
import importlib.util
import json

def load_json(path):
    def pairs(items):
        value = {}
        for name, item in items:
            if name in value:
                raise ValueError('Duplicate JSON key')
            value[name] = item
        return value
    if path.stat().st_size > 100 * 1024 * 1024:
        raise ValueError('Component job exceeds artifact bound')
    return json.loads(path.read_bytes(), object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))

assert BUNDLE.is_absolute() and BUNDLE.is_dir()
assert JOB_PATH.is_file() and not JOB_PATH.is_symlink()
envelope = load_json(JOB_PATH)
assert isinstance(envelope, dict) and set(envelope) == {'payload', 'payload_sha256'}
encoded = json.dumps(envelope['payload'], ensure_ascii=False, sort_keys=True,
                     separators=(',', ':'), allow_nan=False).encode('utf-8')
assert hashlib.sha256(encoded).hexdigest() == envelope['payload_sha256'] == JOB_SHA256
assert envelope['payload']['profile_sha256'] == PROFILE_SHA256
bound_files = {'component_core.py': CORE_PATH, 'qwen_kaggle_environment.py': HELPER_PATH,
               'qwen_components_kaggle_runner.py': RUNNER_PATH}
assert set(envelope['payload']['execution_files']) == set(bound_files)
for name, path in bound_files.items():
    assert path.name == name and path.is_file() and not path.is_symlink()
    assert path.resolve().is_relative_to(BUNDLE.resolve())
    body = path.read_bytes()
    assert {'sha256': hashlib.sha256(body).hexdigest(), 'size_bytes': len(body)} == envelope['payload']['execution_files'][name]

# The additional bootstrap has a separate prospective binding, outside the original job's three-file binding.
assert BOOTSTRAP_PATH.name == 'qwen_kaggle_bootstrap.py'
assert BOOTSTRAP_PATH.is_file() and not BOOTSTRAP_PATH.is_symlink()
assert BOOTSTRAP_PATH.resolve().is_relative_to(BUNDLE.resolve())
bootstrap_bytes = BOOTSTRAP_PATH.read_bytes()
assert len(bootstrap_bytes) == BOOTSTRAP_SIZE_BYTES
assert hashlib.sha256(bootstrap_bytes).hexdigest() == BOOTSTRAP_SHA256

# Verify every executable above before loading either helper.
def load_verified_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

helper = load_verified_module('verified_qwen_environment', HELPER_PATH)
bootstrap = load_verified_module('verified_qwen_bootstrap', BOOTSTRAP_PATH)
print({'job_sha256': JOB_SHA256, 'questions': len(envelope['payload']['questions']),
       'encoded_queries': len(envelope['payload']['query_rows'])})
'''
    invocation = '''summary = bootstrap.prepare_environment(helper, JOB_PATH, JOB_SHA256,
    core_path=CORE_PATH, runner_path=RUNNER_PATH, output_path=OUTPUT_PATH,
    checkpoint_path=CHECKPOINT_PATH, audit_path=AUDIT_PATH,
    report_path=INSTALLER_REPORT_PATH, bootstrap_audit_path=BOOTSTRAP_AUDIT_PATH)
print(json.dumps(summary, sort_keys=True))
'''
    for source in (configuration, preflight, invocation):
        compile(source, "prepared-component-bootstrap-notebook", "exec")
    return {
        "nbformat": 4, "nbformat_minor": 5,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                     "language_info": {"name": "python"}},
        "cells": [_cell("markdown", """# Run the verified component batch on Kaggle

Upload `kaggle-upload.zip` as a **private** Kaggle dataset and attach it. Enable Internet and a CUDA GPU; set `BUNDLE` below to the exact mounted directory containing all five files. The trusted job digest is already filled in. Use one finite Save & Run All with the interactive draft off.

This notebook uses a separately verified pip-wheel bootstrap, the original source job/core/helper/worker, and the original package/model pins. It saves the bootstrap audit and stage logs, installer report, worker audit, checkpoint and result under `/kaggle/working`; temporary packages and model cache stay under `/kaggle/temp`. Keep the printed result digest and saved notebook version for local import. Existing output files cause setup to stop; choose fresh output paths for another run.

Preparation performs no inference and provides no quality or human-pilot acceptance result. Review candidate passages and screening decisions in the local workflow after validated results are returned.
"""), _cell("code", configuration), _cell("code", preflight), _cell("code", invocation)],
    }


def prepare_bundle(job_path, job_sha256, *, output_path):
    """Validate all input bindings before creating a fresh five-file transport."""
    job_path, output = Path(job_path), Path(output_path)
    core.require(job_path.is_absolute() and output.is_absolute(), "Job and output paths must be absolute")
    core.require(job_path.is_file() and not job_path.is_symlink(), "Original job must be a regular file")
    core.require(not os.path.lexists(output), "Preparation output must be a fresh directory")
    # Bound the first read itself, including growth after the initial file check.
    job_bytes = _capture_job_bytes(job_path)
    envelope = core.read_json(job_bytes)
    job = core.validate_job(envelope, job_sha256)
    # Copy the validated bytes exactly; reject even a formatting-only change.
    core.require(_capture_job_bytes(job_path) == job_bytes, "Original job changed during preparation")
    captured = {"job.json": job_bytes}
    paths = execution_paths()
    core.require(set(paths) == set(job["execution_files"]), "Original executable file set differs")
    for name, path in paths.items():
        body = Path(path).read_bytes()
        core.require(binding(body) == job["execution_files"][name], "Repository executable differs from the trusted job: " + name)
        captured[name] = body
    adapter_path = ROOT / "tools/qwen_kaggle_bootstrap.py"
    adapter_bytes = adapter_path.read_bytes()
    core.require(binding(adapter_bytes) == BOOTSTRAP_PIN, "Bootstrap adapter differs from its separately accepted byte pin")
    captured["qwen_kaggle_bootstrap.py"] = adapter_bytes
    notebook_bytes = (json.dumps(_notebook(job_sha256, job["profile_sha256"]), ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    member_pins = {name: binding(captured[name]) for name in MEMBERS}
    core.require(set(captured) == set(MEMBERS), "Upload bundle must contain exactly five files")
    # No input validation below this point needs to read source truth or a ledger.
    try:
        output.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise ValueError("Preparation output must be a fresh directory") from None
    try:
        upload = output / "kaggle-upload"; upload.mkdir()
        for name in MEMBERS:
            with (upload / name).open("xb") as stream:
                stream.write(captured[name])
        archive = output / "kaggle-upload.zip"
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as stream:
            for name in MEMBERS:
                item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                item.create_system = 3
                item.compress_type = zipfile.ZIP_DEFLATED
                item.external_attr = 0o100644 << 16
                stream.writestr(item, captured[name])
        notebook = output / "qwen_components_bootstrap_kaggle.ipynb"
        with notebook.open("xb") as stream:
            stream.write(notebook_bytes)
        receipt = output / "preparation.json"
        provenance = {
            "schema_version": 1, "kind": "qwen-components-bootstrap-preparation-v1", "status": "prepared_not_run",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "job": {"source_path": str(job_path.resolve()), "filename": "job.json", **binding(job_bytes)},
            "job_sha256": job_sha256, "profile_sha256": job["profile_sha256"],
            "original_execution_files": job["execution_files"],
            "bootstrap": {"filename": "qwen_kaggle_bootstrap.py", **BOOTSTRAP_PIN},
            "installer_wheel": WHEEL_PIN, "upload_members": member_pins,
            "archive": {"filename": archive.name, **binding(archive.read_bytes())},
            "notebook": {"filename": notebook.name, **binding(notebook_bytes)},
            "preparer": {"filename": Path(__file__).name, **binding(Path(__file__).read_bytes())},
            "original_job_and_three_execution_files_unchanged": True,
            "bootstrap_checked_before_import": True,
            "ranking_runs_performed_by_preparation": 0, "paid_inference_calls_performed_by_preparation": 0,
        }
        with receipt.open("x", encoding="utf-8") as stream:
            json.dump(provenance, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
    except BaseException:
        # The directory was created by this call; preserve every preexisting input.
        shutil.rmtree(output)
        raise
    return {"status": "prepared_not_run", "job_sha256": job_sha256, "output_directory": str(output.resolve()),
            "files_to_upload": [{"path": str((upload / name).resolve()), "filename": name, **member_pins[name]} for name in MEMBERS],
            "zip_path": str(archive.resolve()), "notebook_path": str(notebook.resolve()), "receipt_path": str(receipt.resolve())}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Package an exported component job with the separately verified Kaggle bootstrap")
    parser.add_argument("--job", required=True)
    parser.add_argument("--job-sha256", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        result = prepare_bundle(args.job, args.job_sha256, output_path=args.output)
    except (ValueError, OSError) as error:
        print("component-bootstrap-prepare: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
