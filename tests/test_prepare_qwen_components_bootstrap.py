"""Offline transport checks against an actual validated exported development job."""

from copy import deepcopy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import zipfile

import pytest

from src.review_components import core
from tools import prepare_qwen_components_bootstrap as prepare


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ARCHIVE = ROOT / "tests/fixtures/qwen_components_development_job_v1/kaggle-upload.zip"
TRUSTED_JOB = "4de843130af3727968e1a0f7bfd150c5743fcfb521d820a5c0fe0fd9c3bc3ce2"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("Transport preparation attempted network"))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("Transport preparation launched a process"))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("Transport preparation launched a process"))


@pytest.fixture
def job(tmp_path):
    path = tmp_path / "original-project-job.json"
    with zipfile.ZipFile(SOURCE_ARCHIVE) as archive:
        path.write_bytes(archive.read("job.json"))
    return path


@pytest.fixture
def prepared(job, tmp_path):
    output = tmp_path / "prepared"
    summary = prepare.prepare_bundle(job, TRUSTED_JOB, output_path=output)
    return output, summary


def receipt(output):
    return json.loads((output / "preparation.json").read_bytes())


def code_cells(output):
    book = json.loads((output / "qwen_components_bootstrap_kaggle.ipynb").read_bytes())
    return ["".join(cell["source"]) for cell in book["cells"] if cell["cell_type"] == "code"]


def run_configuration(output, monkeypatch):
    cells = code_cells(output)
    configured = cells[0].replace("'/kaggle/input/REPLACE_WITH_PRIVATE_DATASET_DIRECTORY'", repr(str(output / "kaggle-upload")))
    assert configured != cells[0]
    monkeypatch.setenv("HF_HOME", "temporary-test-prior-value")
    monkeypatch.setenv("TOKENIZERS_PARALLELISM", "temporary-test-prior-value")
    values = {}
    exec(compile(configured, "configured-offline-notebook", "exec"), values)
    return values, cells


def test_real_export_exact_five_members_and_prospective_bindings(job, prepared):
    output, summary = prepared
    assert summary["status"] == "prepared_not_run" and summary["job_sha256"] == TRUSTED_JOB
    assert set(path.name for path in output.iterdir()) == {"kaggle-upload", "kaggle-upload.zip", "qwen_components_bootstrap_kaggle.ipynb", "preparation.json"}
    assert set(path.name for path in (output / "kaggle-upload").iterdir()) == set(prepare.MEMBERS)
    envelope = core.read_artifact(job)
    original = core.validate_job(envelope, TRUSTED_JOB)
    assert (output / "kaggle-upload/job.json").read_bytes() == job.read_bytes()
    facts = receipt(output)
    assert facts["schema_version"] == 1 and facts["status"] == "prepared_not_run"
    assert facts["job"] == {"source_path": str(job.resolve()), "filename": "job.json", **prepare.binding(job.read_bytes())}
    assert facts["job_sha256"] == TRUSTED_JOB and facts["profile_sha256"] == original["profile_sha256"]
    assert facts["original_execution_files"] == original["execution_files"]
    assert facts["original_job_and_three_execution_files_unchanged"] is True
    assert facts["bootstrap_checked_before_import"] is True
    assert facts["ranking_runs_performed_by_preparation"] == facts["paid_inference_calls_performed_by_preparation"] == 0
    assert "ranking_runs" not in facts and "paid_inference_calls" not in facts
    assert facts["bootstrap"] == {"filename": "qwen_kaggle_bootstrap.py", **prepare.BOOTSTRAP_PIN}
    assert facts["installer_wheel"] == prepare.WHEEL_PIN
    for name, source in prepare.execution_paths().items():
        assert (output / "kaggle-upload" / name).read_bytes() == source.read_bytes()
        assert facts["upload_members"][name] == original["execution_files"][name]
    assert facts["upload_members"]["qwen_kaggle_bootstrap.py"] == prepare.BOOTSTRAP_PIN
    with zipfile.ZipFile(summary["zip_path"]) as archive:
        assert archive.namelist() == list(prepare.MEMBERS)
        for info in archive.infolist():
            assert info.filename == Path(info.filename).name and not info.is_dir()
            assert stat.S_ISREG(info.external_attr >> 16)
            body = archive.read(info.filename)
            assert body == (output / "kaggle-upload" / info.filename).read_bytes()
            assert facts["upload_members"][info.filename] == prepare.binding(body)
    for field in ("archive", "notebook"):
        assert facts[field] == {"filename": facts[field]["filename"], **prepare.binding((output / facts[field]["filename"]).read_bytes())}
    for field in ("zip_path", "notebook_path", "receipt_path", "output_directory"):
        assert Path(summary[field]).is_absolute()
    assert {row["filename"] for row in summary["files_to_upload"]} == set(prepare.MEMBERS)
    assert all(Path(row["path"]).is_absolute() and prepare.binding(Path(row["path"]).read_bytes()) == {key: row[key] for key in ("sha256", "size_bytes")} for row in summary["files_to_upload"])


def test_deterministic_transport_bytes_except_receipt_time(job, tmp_path):
    outputs = [tmp_path / "one", tmp_path / "two"]
    for output in outputs: prepare.prepare_bundle(job, TRUSTED_JOB, output_path=output)
    for name in ("kaggle-upload.zip", "qwen_components_bootstrap_kaggle.ipynb"):
        assert (outputs[0] / name).read_bytes() == (outputs[1] / name).read_bytes()
    facts = [receipt(output) for output in outputs]
    for fact in facts: fact.pop("created_at_utc")
    assert facts[0] == facts[1]


@pytest.mark.parametrize("defect", ["wrong_trusted_sha", "invalid_json", "tampered_payload", "rehashed_extra_field", "rehashed_bad_scope", "duplicate_json", "nonfinite_json"])
def test_bad_original_job_rejected_before_output(job, tmp_path, defect):
    output = tmp_path / "missing-parent" / "output"
    trusted = TRUSTED_JOB
    if defect == "wrong_trusted_sha": trusted = "0" * 64
    elif defect == "invalid_json": job.write_bytes(b"broken")
    elif defect == "duplicate_json": job.write_text('{"payload":{},"payload":{},"payload_sha256":"x"}')
    elif defect == "nonfinite_json": job.write_text('{"payload":NaN,"payload_sha256":"x"}')
    else:
        envelope = json.loads(job.read_bytes())
        if defect == "tampered_payload": envelope["payload"]["questions"][0]["query"] += " changed"
        elif defect == "rehashed_extra_field": envelope["payload"]["gold_answers"] = ["never permitted"]
        elif defect == "rehashed_bad_scope": envelope["payload"]["scope"] = "unrecognized"
        if defect.startswith("rehashed"):
            trusted = core.digest(envelope["payload"]); envelope["payload_sha256"] = trusted
        job.write_text(json.dumps(envelope))
    with pytest.raises(ValueError): prepare.prepare_bundle(job, trusted, output_path=output)
    assert not output.exists() and not output.parent.exists()


@pytest.mark.parametrize("name", ["component_core.py", "qwen_kaggle_environment.py", "qwen_components_kaggle_runner.py"])
def test_repository_executable_binding_mismatch_rejects_before_output(job, tmp_path, monkeypatch, name):
    paths = prepare.execution_paths()
    altered = tmp_path / name; altered.write_bytes(paths[name].read_bytes() + b"\n# changed\n")
    paths[name] = altered
    monkeypatch.setattr(prepare, "execution_paths", lambda: paths)
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="Repository executable differs"):
        prepare.prepare_bundle(job, TRUSTED_JOB, output_path=output)
    assert not output.exists()


def test_separate_bootstrap_binding_mismatch_rejects_before_output(job, tmp_path, monkeypatch):
    other = tmp_path / "other-root"; (other / "tools").mkdir(parents=True)
    (other / "tools/qwen_kaggle_bootstrap.py").write_bytes((ROOT / "tools/qwen_kaggle_bootstrap.py").read_bytes() + b"\n# changed\n")
    monkeypatch.setattr(prepare, "ROOT", other)
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="separately accepted byte pin"):
        prepare.prepare_bundle(job, TRUSTED_JOB, output_path=output)
    assert not output.exists()


def test_job_growing_after_validation_has_bounded_capture_and_no_output(job, tmp_path, monkeypatch):
    original_validator = core.validate_job
    bound = job.stat().st_size + 8
    monkeypatch.setattr(prepare, "ARTIFACT_BYTES", bound)
    def growing_validator(envelope, expected):
        validated = original_validator(envelope, expected)
        with job.open("ab") as stream:
            stream.write(b" " * 128)
        return validated
    monkeypatch.setattr(core, "validate_job", growing_validator)
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="exceeds artifact bound during preparation"):
        prepare.prepare_bundle(job, TRUSTED_JOB, output_path=output)
    assert not output.exists()


def test_fixture_comes_from_portable_committed_archive(job):
    assert SOURCE_ARCHIVE.is_file()
    body = job.read_bytes()
    assert hashlib.sha256(body).hexdigest() == "4b32d55c6cad6e2534dab3804885b2238e6ada54c305d0adc68352ea3e6dea65"
    assert core.validate_job(core.read_json(body), TRUSTED_JOB)["kind"] == "qwen-components-job-v1"
    assert SOURCE_ARCHIVE.is_relative_to(ROOT / "tests/fixtures")


def test_initial_capture_and_snapshot_are_bounded_without_unbounded_job_reader(job, tmp_path, monkeypatch):
    original_open, original_read_bytes = Path.open, Path.read_bytes
    body = job.read_bytes(); reads = []
    class BoundedStream(io.BytesIO):
        def read(self, size=-1):
            reads.append(size)
            assert size == prepare.ARTIFACT_BYTES + 1
            return super().read(size)
    def opened(path, *args, **kwargs):
        if path == job and args == ("rb",): return BoundedStream(body)
        return original_open(path, *args, **kwargs)
    def read_bytes(path):
        if path == job: pytest.fail("Preparation used an unbounded job read")
        return original_read_bytes(path)
    monkeypatch.setattr(Path, "open", opened)
    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    monkeypatch.setattr(core, "read_artifact", lambda *a, **k: pytest.fail("Preparation called frozen unbounded artifact reader"))
    output = tmp_path / "output"
    prepare.prepare_bundle(job, TRUSTED_JOB, output_path=output)
    assert reads == [prepare.ARTIFACT_BYTES + 1] * 2
    assert (output / "kaggle-upload/job.json").read_bytes() == body


def test_initial_race_growth_rejected_before_json_parse_or_output(job, tmp_path, monkeypatch):
    body = job.read_bytes(); bound = len(body) + 8
    monkeypatch.setattr(prepare, "ARTIFACT_BYTES", bound)
    original_open = Path.open; reads = []
    class GrowingStream(io.BytesIO):
        def read(self, size=-1):
            reads.append(size)
            assert size == bound + 1
            return super().read(size)
    def opened(path, *args, **kwargs):
        if path == job and args == ("rb",): return GrowingStream(body + b" " * 128)
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", opened)
    monkeypatch.setattr(core, "read_json", lambda *a, **k: pytest.fail("Oversized initial capture was parsed"))
    monkeypatch.setattr(core, "read_artifact", lambda *a, **k: pytest.fail("Unbounded artifact reader was called"))
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="exceeds artifact bound during preparation"):
        prepare.prepare_bundle(job, TRUSTED_JOB, output_path=output)
    assert reads == [bound + 1] and not output.exists()


def test_formatting_change_after_validation_rejects_before_output(job, tmp_path, monkeypatch):
    original_validator = core.validate_job
    def changing_validator(envelope, expected):
        validated = original_validator(envelope, expected)
        with job.open("ab") as stream: stream.write(b"\n")
        return validated
    monkeypatch.setattr(core, "validate_job", changing_validator)
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="changed during preparation"):
        prepare.prepare_bundle(job, TRUSTED_JOB, output_path=output)
    assert not output.exists()


@pytest.mark.parametrize("kind", ["directory", "file", "symlink", "broken_symlink", "original_job"])
def test_preexisting_output_never_overwritten(job, tmp_path, kind):
    output = tmp_path / "output"
    if kind == "directory": output.mkdir(); (output / "evidence").write_bytes(b"old evidence")
    elif kind == "file": output.write_bytes(b"old evidence")
    elif kind == "symlink": output.symlink_to(job)
    elif kind == "broken_symlink": output.symlink_to(tmp_path / "nonexistent")
    else: output = job
    original = job.read_bytes()
    with pytest.raises(ValueError, match="fresh directory"):
        prepare.prepare_bundle(job, TRUSTED_JOB, output_path=output)
    assert job.read_bytes() == original
    if kind == "directory": assert (output / "evidence").read_bytes() == b"old evidence"
    elif kind == "file": assert output.read_bytes() == b"old evidence"
    elif "symlink" in kind: assert output.is_symlink()


@pytest.mark.parametrize("path", ["job", "output"])
def test_relative_paths_rejected(job, tmp_path, path):
    given = Path("relative.json") if path == "job" else job
    output = Path("relative-output") if path == "output" else tmp_path / "output"
    with pytest.raises(ValueError, match="paths must be absolute"):
        prepare.prepare_bundle(given, TRUSTED_JOB, output_path=output)
    assert not (tmp_path / "output").exists()


def test_original_job_symlink_rejected_without_output(job, tmp_path):
    alias = tmp_path / "alias.json"; alias.symlink_to(job)
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="regular file"):
        prepare.prepare_bundle(alias, TRUSTED_JOB, output_path=output)
    assert not output.exists() and alias.is_symlink()


def test_notebook_compiles_and_calls_only_the_accepted_adapter_with_original_paths(prepared, monkeypatch):
    output, summary = prepared
    cells = code_cells(output)
    assert len(cells) == 3
    for cell in cells: compile(cell, "generated-bootstrap-notebook", "exec")
    values, cells = run_configuration(output, monkeypatch)
    loaded = []; actual = importlib.util.spec_from_file_location
    def tracking(name, path, *args, **kwargs):
        loaded.append(Path(path).name)
        return actual(name, path, *args, **kwargs)
    monkeypatch.setattr(importlib.util, "spec_from_file_location", tracking)
    exec(compile(cells[1], "notebook-integrity-preflight", "exec"), values)
    assert loaded == ["qwen_kaggle_environment.py", "qwen_kaggle_bootstrap.py"]
    assert values["BOOTSTRAP_SHA256"] == prepare.BOOTSTRAP_PIN["sha256"]
    assert values["JOB_SHA256"] == TRUSTED_JOB
    calls = []
    def fake_call(*args, **kwargs):
        calls.append((args, kwargs)); return {"status": "offline simulated adapter call"}
    monkeypatch.setattr(values["bootstrap"], "prepare_environment", fake_call)
    exec(compile(cells[2], "notebook-adapter-invocation", "exec"), values)
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == (values["helper"], output / "kaggle-upload/job.json", TRUSTED_JOB)
    assert kwargs == {"core_path": output / "kaggle-upload/component_core.py", "runner_path": output / "kaggle-upload/qwen_components_kaggle_runner.py",
        "output_path": Path("/kaggle/working/components-results.json"), "checkpoint_path": Path("/kaggle/working/components-checkpoint.json"),
        "audit_path": Path("/kaggle/working/components-environment-audit.json"), "report_path": Path("/kaggle/working/components-installer-report.json"),
        "bootstrap_audit_path": Path("/kaggle/working/components-bootstrap-audit.json")}


@pytest.mark.parametrize("name", prepare.MEMBERS)
def test_notebook_tamper_blocks_both_executable_imports(prepared, monkeypatch, name):
    output, summary = prepared
    target = output / "kaggle-upload" / name
    if name == "job.json":
        value = json.loads(target.read_bytes()); value["payload"]["questions"][0]["query"] += " changed"
        target.write_text(json.dumps(value))
    else: target.write_bytes(target.read_bytes() + b"\n# changed\n")
    values, cells = run_configuration(output, monkeypatch)
    monkeypatch.setattr(importlib.util, "spec_from_file_location", lambda *a, **k: pytest.fail("Tampered bundle imported executable code"))
    with pytest.raises((AssertionError, ValueError)):
        exec(compile(cells[1], "tampered-notebook-preflight", "exec"), values)
    assert "helper" not in values and "bootstrap" not in values


def test_notebook_missing_mount_stops_before_import(prepared, monkeypatch):
    output, summary = prepared
    values, cells = run_configuration(output, monkeypatch)
    values["BUNDLE"] = output / "missing-mount"
    monkeypatch.setattr(importlib.util, "spec_from_file_location", lambda *a, **k: pytest.fail("Missing mount imported executable code"))
    with pytest.raises(AssertionError): exec(compile(cells[1], "missing-mount-preflight", "exec"), values)


def test_cli_outputs_only_absolute_artifact_facts(job, tmp_path, capsys):
    output = tmp_path / "cli-output"
    assert prepare.main(["--job", str(job), "--job-sha256", TRUSTED_JOB, "--output", str(output)]) == 0
    captured = capsys.readouterr(); assert not captured.err
    summary = json.loads(captured.out)
    assert Path(summary["zip_path"]).is_absolute() and summary["job_sha256"] == TRUSTED_JOB
    value = json.loads(job.read_bytes())["payload"]
    assert value["project_id"] not in captured.out
    assert value["questions"][0]["query"] not in captured.out
    assert value["candidates"][0]["passage"]["anchor"]["quote"] not in captured.out
    assert "payload" not in summary and "questions" not in summary and "candidates" not in summary


def test_cli_validation_failure_emits_no_artifacts(job, tmp_path, capsys):
    output = tmp_path / "cli-output"
    assert prepare.main(["--job", str(job), "--job-sha256", "0" * 64, "--output", str(output)]) == 1
    captured = capsys.readouterr()
    assert not captured.out and "trusted original component job checksum" in captured.err
    assert not output.exists()


def test_packaging_failure_removes_only_its_new_directory(job, tmp_path, monkeypatch):
    output = tmp_path / "output"
    original = job.read_bytes()
    def failed(*args, **kwargs): raise OSError("simulated packaging failure")
    monkeypatch.setattr(prepare.zipfile, "ZipFile", failed)
    with pytest.raises(OSError, match="packaging failure"):
        prepare.prepare_bundle(job, TRUSTED_JOB, output_path=output)
    assert not output.exists() and job.read_bytes() == original
