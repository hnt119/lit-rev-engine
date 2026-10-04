"""Separately pinned pip-wheel bootstrap; importing this module performs no work."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request


PIP_WHEEL = {
    "version": "25.2",
    "filename": "pip-25.2-py3-none-any.whl",
    "url": "https://files.pythonhosted.org/packages/b7/3f/945ef7ab14dc4f9d7f40288d2df998d1837ee0888ec3659c813487572faa/pip-25.2-py3-none-any.whl",
    "size_bytes": 1752557,
    "sha256": "6d67a2b4e7f14d8b31b8b52648866fa717f45a1eb70e83002f4331d07e953717",
}
PINS = {"transformers": "4.51.3", "tokenizers": "0.21.1", "safetensors": "0.5.3", "huggingface-hub": "0.30.2"}
RECIPE = "verified-pip25.2-wheel-no-site-installer-v1"
FETCH_SECONDS = 60
LOG_BYTES = 1024 * 1024
STAGES = ("venv", "installer_isolation", "wheel_download", "pip_version", "pip_install", "worker")
PROBE = (
    "import importlib.util,json,sys; "
    "print(json.dumps({'executable':sys.executable,'python_version':sys.version.split()[0],"
    "'prefix':sys.prefix,'base_prefix':sys.base_prefix,'sys_path':sys.path,"
    "'isolated':sys.flags.isolated,'no_site':sys.flags.no_site,"
    "'pip_present':importlib.util.find_spec('pip') is not None},sort_keys=True))"
)


def _require(value, message):
    if not value:
        raise ValueError(message)


def _binding(path):
    data = Path(path).read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def _write_new(path, value):
    path = Path(path)
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    _require(len(encoded) <= LOG_BYTES, "Bootstrap audit exceeds its size bound")
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".qwen-bootstrap-", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        try:
            os.link(temporary, path)
        except FileExistsError:
            raise ValueError("Bootstrap audits are immutable; select a new path") from None
    finally:
        temporary.unlink(missing_ok=True)


def _child_environment():
    # Do not mutate the notebook environment or record its values in provenance.
    environment = {name: value for name, value in os.environ.items()
                   if not name.startswith(("PYTHON", "PIP_"))
                   and name not in {"VIRTUAL_ENV", "ENSUREPIP_OPTIONS", "_PIP_RUNNING_IN_SUBPROCESS"}}
    environment["PIP_CONFIG_FILE"] = os.devnull
    return environment


def _wheel_binding(path):
    path = Path(path)
    _require(path.is_file() and not path.is_symlink(), "Verified pip wheel must be a regular file")
    _require(path.stat().st_size == PIP_WHEEL["size_bytes"], "Pip wheel size differs from the fixed release")
    binding = _binding(path)
    _require(binding["sha256"] == PIP_WHEEL["sha256"], "Pip wheel checksum differs from the fixed release")
    return binding


def _download_wheel(path):
    """Runs only in a child with a parent-enforced total sixty-second deadline."""
    path = Path(path)
    _require(path.is_absolute() and path.name == PIP_WHEEL["filename"], "Unexpected pip wheel destination")
    _require(not os.path.lexists(path), "Preserve existing pip wheel artifacts")
    request = urllib.request.Request(PIP_WHEEL["url"], headers={"User-Agent": "lit-rev-engine-pinned-bootstrap-v1"})
    # HTTPS uses Python's default certificate verification. No TLS fallback.
    with urllib.request.urlopen(request, timeout=FETCH_SECONDS) as response:
        _require(response.geturl() == PIP_WHEEL["url"], "Pip wheel redirects require a new explicit binding")
        _require(response.status == 200, "Pip wheel HTTP request failed")
        declared = response.headers.get("Content-Length")
        if declared is not None:
            _require(declared.isdecimal() and int(declared) == PIP_WHEEL["size_bytes"], "Pip wheel declared size differs")
        with path.open("xb") as stream:
            count = 0
            while True:
                chunk = response.read(min(65536, PIP_WHEEL["size_bytes"] + 1 - count))
                if not chunk:
                    break
                count += len(chunk)
                _require(count <= PIP_WHEEL["size_bytes"], "Pip wheel exceeds the fixed release size")
                stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
    _wheel_binding(path)
    print("Downloaded and verified fixed pip25.2 wheel", flush=True)


def _stage(name, command, log_path, environment, evidence, *, timeout=None):
    """Bound fetch time; stream other stage output into a new diagnostic log."""
    started = time.monotonic()
    row = {"stage": name, "status": "started", "returncode": None, "elapsed_seconds": 0.0}
    evidence.append(row)
    process = None
    captured = bytearray()
    print("Bootstrap stage: " + name, flush=True)
    try:
        with Path(log_path).open("xb") as log:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=environment)
            if timeout is not None:
                try:
                    output, _ = process.communicate(timeout=timeout)
                except subprocess.TimeoutExpired:
                    process.kill()
                    output, _ = process.communicate()
                    _require(len(output) <= LOG_BYTES, "Bootstrap stage output exceeds its size bound")
                    log.write(output)
                    captured.extend(output)
                    row["status"] = "timed_out"
                    raise TimeoutError("Bootstrap wheel download exceeded sixty seconds") from None
                _require(len(output) <= LOG_BYTES, "Bootstrap stage output exceeds its size bound")
                log.write(output)
                captured.extend(output)
                print(output.decode("utf-8", errors="replace"), end="", flush=True)
            else:
                while True:
                    output = process.stdout.readline(LOG_BYTES + 1)
                    if not output:
                        break
                    _require(len(captured) + len(output) <= LOG_BYTES, "Bootstrap stage output exceeds its size bound")
                    log.write(output)
                    captured.extend(output)
                    print(output.decode("utf-8", errors="replace"), end="", flush=True)
                process.wait()
            row["returncode"] = process.returncode
            _require(process.returncode == 0, "Bootstrap stage failed: " + name + "; inspect its saved diagnostic log")
            row["status"] = "passed"
            log.flush()
            os.fsync(log.fileno())
        return bytes(captured)
    except BaseException:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        if row["status"] != "timed_out":
            row["status"] = "failed"
        if process is not None:
            row["returncode"] = process.returncode
        raise
    finally:
        row["elapsed_seconds"] = time.monotonic() - started
        if Path(log_path).is_file():
            row["log"] = {"path": str(Path(log_path).resolve()), **_binding(log_path)}


def _check_isolation(output, installer, installer_python):
    config = (installer / "pyvenv.cfg").read_text(encoding="utf-8")
    _require("include-system-site-packages = false" in config.splitlines(), "Installer must exclude system site-packages")
    _require("--without-pip" in config, "Installer must skip ensurepip")
    probe = json.loads(output)
    fields = {"executable", "python_version", "prefix", "base_prefix", "sys_path", "isolated", "no_site", "pip_present"}
    _require(isinstance(probe, dict) and set(probe) == fields, "Installer isolation probe is incomplete")
    _require(probe["executable"] == str(installer_python) and type(probe["isolated"]) is int and probe["isolated"] == 1
             and type(probe["no_site"]) is int and probe["no_site"] == 1 and probe["pip_present"] is False,
             "Installer did not start with isolated no-site Python")
    _require(all(isinstance(probe[name], str) and probe[name] for name in ("python_version", "prefix", "base_prefix")),
             "Installer interpreter identity is missing")
    _require(isinstance(probe["sys_path"], list) and all(isinstance(path, str) and path
             and Path(path).is_absolute() and not {"site-packages", "dist-packages"}.intersection(Path(path).parts)
             for path in probe["sys_path"]), "Installer exposes a site-packages path")
    return probe


def prepare_environment(helper, job_path, job_sha256, *, core_path, runner_path, output_path, checkpoint_path,
                        audit_path, report_path, bootstrap_audit_path, temp_root="/kaggle/temp", base_python=None):
    """Replace only setup orchestration; retain the verified original GPU worker."""
    started = time.monotonic()
    helper_path, adapter_path = Path(helper.__file__), Path(__file__)
    job = helper.verify_bundle(job_path, job_sha256, core_path=core_path, runner_path=runner_path, helper_path=helper_path)
    _require(helper.PINS == PINS, "Original helper package pins differ from bootstrap selection")
    inputs = [Path(path) for path in (job_path, core_path, runner_path, helper_path, adapter_path)]
    outputs = [Path(path) for path in (output_path, checkpoint_path, audit_path, report_path, bootstrap_audit_path)]
    logs = {stage: Path(str(bootstrap_audit_path) + "." + stage + ".log") for stage in STAGES}
    paths = [*inputs, *outputs, *logs.values()]
    _require(len({path.resolve() for path in paths}) == len(paths), "Bootstrap input/output/log paths must be distinct")
    for path in [*outputs, *logs.values()]:
        _require(not os.path.lexists(path), "Preserve existing bootstrap artifacts and choose new paths: " + str(path))
    base_python = str(Path(base_python or sys.executable).resolve())
    _require(Path(base_python).is_file(), "Original base Python interpreter is missing")
    for path in [*outputs, *logs.values()]:
        path.parent.mkdir(parents=True, exist_ok=True)
    Path(temp_root).mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="qwen-components-bootstrap-", dir=temp_root)).resolve()
    installer, overlay = temporary / "installer", temporary / "overlay"
    overlay.mkdir()
    installer_python = installer / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    wheel_path = temporary / PIP_WHEEL["filename"]
    evidence = {"schema_version": 1, "kind": "qwen-components-bootstrap-audit-v1", "recipe": RECIPE,
                "created_at_utc": datetime.now(timezone.utc).isoformat(), "status": "setup_started",
                "job_sha256": job_sha256, "profile_sha256": job["profile_sha256"], "execution_files": job["execution_files"],
                "adapter": {"filename": adapter_path.name, **_binding(adapter_path)},
                "pip_wheel": {**PIP_WHEEL, "path": str(wheel_path), "verified": False},
                "base_python": base_python, "installer_python": str(installer_python), "overlay_path": str(overlay),
                "installer_probe": None, "package_pins": dict(PINS), "stages": [], "setup_seconds": None,
                "elapsed_seconds": None, "paid_inference_calls": 0}
    environment = _child_environment()
    stage = "venv"
    try:
        _stage(stage, [base_python, "-I", "-m", "venv", "--without-pip", str(installer)], logs[stage], environment, evidence["stages"])
        stage = "installer_isolation"
        probe = _stage(stage, [str(installer_python), "-I", "-S", "-c", PROBE], logs[stage], environment, evidence["stages"])
        evidence["installer_probe"] = _check_isolation(probe, installer, installer_python)
        stage = "wheel_download"
        _stage(stage, [base_python, "-I", "-S", str(adapter_path.resolve()), "--download-wheel", str(wheel_path)],
               logs[stage], environment, evidence["stages"], timeout=FETCH_SECONDS)
        _wheel_binding(wheel_path)
        evidence["pip_wheel"]["verified"] = True
        pip_command = [str(installer_python), "-I", "-S", str(wheel_path / "pip"), "--isolated", "--disable-pip-version-check",
                       "--no-cache-dir", "--no-input", "--keyring-provider", "disabled"]
        stage = "pip_version"
        version_output = _stage(stage, [*pip_command, "--version"], logs[stage], environment, evidence["stages"]).decode("utf-8").strip()
        python_version = ".".join(evidence["installer_probe"]["python_version"].split(".")[:2])
        _require(version_output == "pip " + PIP_WHEEL["version"] + " from " + str(wheel_path / "pip") + " (python " + python_version + ")",
                 "Installer pip version or wheel origin differs from the verified release")
        evidence["pip_runtime"] = {"version": PIP_WHEEL["version"], "origin": str(wheel_path / "pip"),
                                   "python_version": python_version, "version_output": version_output}
        stage = "pip_install"
        command = [*pip_command, "install", "--no-deps", "--only-binary", ":all:",
                   "--index-url", "https://pypi.org/simple", "--target", str(overlay), "--report", str(Path(report_path).resolve()),
                   *[name + "==" + version for name, version in helper.PINS.items()]]
        _stage(stage, command, logs[stage], environment, evidence["stages"])
        _require(Path(report_path).is_file() and not Path(report_path).is_symlink(), "Installer did not save its package report")
        evidence["installer_report"] = {"path": str(Path(report_path).resolve()), **_binding(report_path)}
        evidence["setup_seconds"] = time.monotonic() - started
        stage = "worker"
        command = [base_python, "-I", str(Path(runner_path).resolve()), "--job", str(Path(job_path).resolve()),
                   "--job-sha256", job_sha256, "--core", str(Path(core_path).resolve()), "--environment-helper", str(helper_path.resolve()),
                   "--overlay", str(overlay), "--installer-report", str(Path(report_path).resolve()),
                   "--setup-seconds", str(evidence["setup_seconds"]), "--output", str(Path(output_path).resolve()),
                   "--checkpoint", str(Path(checkpoint_path).resolve()), "--environment-audit", str(Path(audit_path).resolve())]
        _stage(stage, command, logs[stage], environment, evidence["stages"])
        _require(_binding(adapter_path) == {key: evidence["adapter"][key] for key in ("sha256", "size_bytes")}, "Bootstrap adapter changed during execution")
        evidence["status"] = "completed"
    except BaseException as error:
        evidence["status"] = "worker_failed" if stage == "worker" else "setup_failed"
        evidence["error"] = {"stage": stage, "type": type(error).__name__}
        raise
    finally:
        evidence["elapsed_seconds"] = time.monotonic() - started
        _write_new(bootstrap_audit_path, evidence)
        print("Saved immutable bootstrap audit: " + str(Path(bootstrap_audit_path).resolve()), flush=True)
    return {"output_path": str(Path(output_path).resolve()), "audit_path": str(Path(audit_path).resolve()),
            "installer_report_path": str(Path(report_path).resolve()), "bootstrap_audit_path": str(Path(bootstrap_audit_path).resolve()),
            "overlay_path": str(overlay), "profile_sha256": job["profile_sha256"]}


def main():
    parser = argparse.ArgumentParser(description="Bounded fixed-release wheel download for a verified bootstrap parent")
    parser.add_argument("--download-wheel", required=True)
    args = parser.parse_args()
    try:
        _download_wheel(args.download_wheel)
    except Exception as error:
        # No environment values or credential-bearing proxy errors in logs.
        print("Fixed pip wheel download failed: " + type(error).__name__, file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
