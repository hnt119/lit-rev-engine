"""Bootstrap acceptance without a real download, package installation, or model."""

from copy import deepcopy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest

from tools import qwen_kaggle_bootstrap as bootstrap


ROOT = Path(__file__).resolve().parents[1]
ORIGINALS = {"component_core.py": ROOT / "src/review_components/core.py",
             "qwen_components_kaggle_runner.py": ROOT / "tools/qwen_components_kaggle_runner.py",
             "qwen_kaggle_environment.py": ROOT / "tools/qwen_kaggle_environment.py"}
WHEEL_BODY = b"offline fake wheel; never imported or installed"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("Bootstrap acceptance attempted network"))
    monkeypatch.setattr(bootstrap.urllib.request, "urlopen", lambda *a, **k: pytest.fail("Bootstrap acceptance attempted download"))


def load(path):
    spec = importlib.util.spec_from_file_location("unchanged_original_environment_for_bootstrap", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_bundle(tmp_path):
    bundle = tmp_path / "bundle"; bundle.mkdir()
    for name, path in ORIGINALS.items():
        (bundle / name).write_bytes(path.read_bytes())
    payload = {"execution_files": {name: bootstrap._binding(bundle / name) for name in ORIGINALS}, "profile_sha256": "a" * 64}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    sha = hashlib.sha256(encoded).hexdigest()
    job = bundle / "job.json"
    job.write_text(json.dumps({"payload": payload, "payload_sha256": sha}))
    helper = load(bundle / "qwen_kaggle_environment.py")
    saved = tmp_path / "saved"
    arguments = {"core_path": bundle / "component_core.py", "runner_path": bundle / "qwen_components_kaggle_runner.py",
                 "output_path": saved / "results.json", "checkpoint_path": saved / "checkpoint.json",
                 "audit_path": saved / "environment.json", "report_path": saved / "installer-report.json",
                 "bootstrap_audit_path": saved / "bootstrap.json", "temp_root": tmp_path / "temporary"}
    return helper, job, sha, arguments


@pytest.fixture
def fake_pipeline(tmp_path, monkeypatch):
    helper, job, sha, arguments = make_bundle(tmp_path)
    wheel = {**bootstrap.PIP_WHEEL, "size_bytes": len(WHEEL_BODY), "sha256": hashlib.sha256(WHEEL_BODY).hexdigest()}
    monkeypatch.setattr(bootstrap, "PIP_WHEEL", wheel)
    settings = {"fail": None, "wheel": WHEEL_BODY, "probe": {}, "timeout": False, "missing_report": False,
                "version": None, "large_log": None}
    calls = []

    class FakeProcess:
        def __init__(self, command, **kwargs):
            assert set(kwargs) == {"stdout", "stderr", "env"}
            assert kwargs["stdout"] is subprocess.PIPE and kwargs["stderr"] is subprocess.STDOUT
            environment = kwargs["env"]
            assert environment["PIP_CONFIG_FILE"] == os.devnull
            assert not any(name.startswith("PYTHON") for name in environment)
            assert "_PIP_RUNNING_IN_SUBPROCESS" not in environment
            self.returncode = None
            self.killed = False
            self.command = command
            if "venv" in command:
                self.stage = "venv"
                assert command[1:5] == ["-I", "-m", "venv", "--without-pip"]
                installer = Path(command[-1]); (installer / "bin").mkdir(parents=True)
                (installer / "pyvenv.cfg").write_text("include-system-site-packages = false\ncommand = base -m venv --without-pip installer\n")
                (installer / "bin/python").write_text("fake interpreter, not executable")
                self.output = b"pip-free installer created\n"
            elif "-c" in command:
                self.stage = "installer_isolation"
                probe = {"executable": command[0], "python_version": "3.13.0", "prefix": "/usr", "base_prefix": "/usr",
                         "sys_path": ["/usr/lib/python313.zip", "/usr/lib/python3.13", "/usr/lib/python3.13/lib-dynload"],
                         "isolated": 1, "no_site": 1, "pip_present": False}
                probe.update(settings["probe"])
                self.output = json.dumps(probe).encode() + b"\n"
            elif "--download-wheel" in command:
                self.stage = "wheel_download"
                assert command[1:3] == ["-I", "-S"]
                Path(command[-1]).write_bytes(settings["wheel"])
                self.output = b"fixed wheel downloaded\n"
            elif "--version" in command:
                self.stage = "pip_version"
                assert command[1:3] == ["-I", "-S"] and command[4] == "--isolated"
                self.output = (settings["version"] or "pip 25.2 from " + command[3] + " (python 3.13)").encode() + b"\n"
            elif "install" in command:
                self.stage = "pip_install"
                assert command[1:3] == ["-I", "-S"] and command[4] == "--isolated"
                if settings["fail"] != self.stage and not settings["missing_report"]:
                    Path(command[command.index("--report") + 1]).write_text('{"install":[]}')
                self.output = b"offline simulated installation\n"
            else:
                self.stage = "worker"
                assert command[1] == "-I" and command[2] == str(arguments["runner_path"].resolve())
                self.output = b"offline simulated worker\n"
            if settings["large_log"] == self.stage:
                self.output = b"x" * (bootstrap.LOG_BYTES + 1)
            self.stdout = io.BytesIO(self.output)
            calls.append({"stage": self.stage, "command": command, "environment": environment, "process": self})

        def communicate(self, timeout=None):
            if not self.killed and settings["timeout"]:
                assert timeout == 60
                raise subprocess.TimeoutExpired(self.command, timeout)
            if self.stage == "wheel_download" and not self.killed:
                assert timeout == 60
            self.returncode = -9 if self.killed else (17 if settings["fail"] == self.stage else 0)
            return self.output, None

        def wait(self):
            self.returncode = -9 if self.killed else (17 if settings["fail"] == self.stage else 0)
            return self.returncode

        def poll(self): return self.returncode
        def kill(self): self.killed = True

    monkeypatch.setattr(bootstrap.subprocess, "Popen", FakeProcess)
    return SimpleNamespace(helper=helper, job=job, sha=sha, arguments=arguments, settings=settings, calls=calls)


def run(fake):
    return bootstrap.prepare_environment(fake.helper, fake.job, fake.sha, **fake.arguments)


def audit(fake):
    return json.loads(fake.arguments["bootstrap_audit_path"].read_bytes())


def test_production_wheel_and_package_pins_are_exact():
    assert bootstrap.PIP_WHEEL == {"version": "25.2", "filename": "pip-25.2-py3-none-any.whl",
        "url": "https://files.pythonhosted.org/packages/b7/3f/945ef7ab14dc4f9d7f40288d2df998d1837ee0888ec3659c813487572faa/pip-25.2-py3-none-any.whl",
        "size_bytes": 1752557, "sha256": "6d67a2b4e7f14d8b31b8b52648866fa717f45a1eb70e83002f4331d07e953717"}
    assert bootstrap.PINS == {"transformers": "4.51.3", "tokenizers": "0.21.1", "safetensors": "0.5.3", "huggingface-hub": "0.30.2"}
    assert bootstrap.FETCH_SECONDS == 60


def test_exact_pipeline_preserves_originals_and_records_provenance(fake_pipeline, monkeypatch):
    fake = fake_pipeline
    before = {name: path.read_bytes() for name, path in ORIGINALS.items()}
    monkeypatch.setenv("UNRELATED_PROVIDER_SECRET", "invented-secret-not-recorded")
    for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE", "PIP_EXTRA_INDEX_URL", "_PIP_RUNNING_IN_SUBPROCESS"):
        monkeypatch.setenv(name, "hostile-input-not-recorded")
    original_environment = dict(os.environ)
    result = run(fake)
    assert [row["stage"] for row in fake.calls] == list(bootstrap.STAGES)
    assert not any("ensurepip" in argument or argument == "--python" for row in fake.calls for argument in row["command"])
    install = next(row["command"] for row in fake.calls if row["stage"] == "pip_install")
    assert install[-4:] == [name + "==" + version for name, version in bootstrap.PINS.items()]
    for flag in ("--no-deps", "--only-binary", "--target", "--report", "--no-cache-dir", "--disable-pip-version-check", "--no-input"):
        assert flag in install
    assert install[install.index("--only-binary") + 1] == ":all:"
    assert install[install.index("--index-url") + 1] == "https://pypi.org/simple"
    assert install[install.index("--target") + 1] == result["overlay_path"]
    assert not any(flag in install for flag in ("--upgrade", "--user", "--prefix", "--system-site-packages", "--no-warn-conflicts"))
    worker = fake.calls[-1]["command"]
    assert worker[0] == str(Path(sys.executable).resolve()) and worker[1] == "-I"
    assert worker[worker.index("--environment-helper") + 1] == str(Path(fake.helper.__file__).resolve())
    assert worker[worker.index("--job-sha256") + 1] == fake.sha
    evidence = audit(fake)
    assert evidence["status"] == "completed" and evidence["paid_inference_calls"] == 0
    assert evidence["adapter"] == {"filename": "qwen_kaggle_bootstrap.py", **bootstrap._binding(bootstrap.__file__)}
    assert evidence["execution_files"] == json.loads(fake.job.read_bytes())["payload"]["execution_files"]
    assert evidence["pip_wheel"]["verified"] is True and evidence["pip_runtime"]["version"] == "25.2"
    assert all(row["status"] == "passed" and row["returncode"] == 0 for row in evidence["stages"])
    for row in evidence["stages"]:
        assert row["log"] == {"path": row["log"]["path"], **bootstrap._binding(row["log"]["path"])}
    assert float(worker[worker.index("--setup-seconds") + 1]) == evidence["setup_seconds"]
    assert evidence["setup_seconds"] >= sum(row["elapsed_seconds"] for row in evidence["stages"][:-1])
    assert {name: path.read_bytes() for name, path in ORIGINALS.items()} == before
    assert dict(os.environ) == original_environment
    assert "invented-secret-not-recorded" not in fake.arguments["bootstrap_audit_path"].read_text()


@pytest.mark.parametrize("stage", bootstrap.STAGES)
def test_failed_stage_stops_before_next_stage_and_saves_diagnostics(fake_pipeline, stage):
    fake = fake_pipeline; fake.settings["fail"] = stage
    with pytest.raises(ValueError, match="Bootstrap stage failed"):
        run(fake)
    assert [row["stage"] for row in fake.calls] == list(bootstrap.STAGES[:bootstrap.STAGES.index(stage) + 1])
    evidence = audit(fake)
    assert evidence["status"] == ("worker_failed" if stage == "worker" else "setup_failed")
    assert evidence["error"] == {"stage": stage, "type": "ValueError"}
    assert evidence["stages"][-1]["returncode"] == 17
    assert evidence["stages"][-1]["log"]["size_bytes"] > 0


def test_hard_fetch_timeout_kills_child_and_never_accepts_its_complete_wheel(fake_pipeline):
    fake = fake_pipeline; fake.settings["timeout"] = True
    with pytest.raises(TimeoutError, match="sixty seconds"):
        run(fake)
    assert fake.calls[-1]["stage"] == "wheel_download" and fake.calls[-1]["process"].killed is True
    evidence = audit(fake)
    assert evidence["pip_wheel"]["verified"] is False and evidence["stages"][-1]["status"] == "timed_out"
    assert all(row["stage"] != "pip_install" for row in fake.calls)


@pytest.mark.parametrize("body", [b"short", WHEEL_BODY + b"extra", b"X" * len(WHEEL_BODY)])
def test_parent_rechecks_wheel_even_if_child_claims_success(fake_pipeline, body):
    fake = fake_pipeline; fake.settings["wheel"] = body
    with pytest.raises(ValueError, match="Pip wheel"):
        run(fake)
    assert fake.calls[-1]["stage"] == "wheel_download"
    assert audit(fake)["pip_wheel"]["verified"] is False


@pytest.mark.parametrize("defect", [{"pip_present": True}, {"isolated": 0}, {"isolated": True}, {"no_site": 0},
    {"no_site": True}, {"sys_path": ["/usr/local/lib/python3.13/dist-packages"]}, {"sys_path": [""]},
    {"sys_path": ["relative"]}, {"executable": "/usr/bin/python3.13"}])
def test_installer_isolation_failures_stop_before_fetch(fake_pipeline, defect):
    fake = fake_pipeline; fake.settings["probe"] = defect
    with pytest.raises(ValueError, match="Installer"):
        run(fake)
    assert fake.calls[-1]["stage"] == "installer_isolation"
    assert audit(fake)["status"] == "setup_failed"


@pytest.mark.parametrize("version", ["pip 26.0 from /unexpected (python 3.13)", "pip 25.2 from /usr/site-packages/pip (python 3.13)"])
def test_wrong_runtime_pip_version_or_origin_stops_install(fake_pipeline, version):
    fake = fake_pipeline; fake.settings["version"] = version
    with pytest.raises(ValueError, match="version or wheel origin"):
        run(fake)
    assert fake.calls[-1]["stage"] == "pip_version"


def test_missing_installer_report_stops_before_worker(fake_pipeline):
    fake = fake_pipeline; fake.settings["missing_report"] = True
    with pytest.raises(ValueError, match="package report"):
        run(fake)
    assert fake.calls[-1]["stage"] == "pip_install"


@pytest.mark.parametrize("stage", bootstrap.STAGES)
def test_stage_logs_are_bounded_and_fail_closed(fake_pipeline, stage):
    fake = fake_pipeline; fake.settings["large_log"] = stage
    with pytest.raises(ValueError, match="output exceeds"):
        run(fake)
    evidence = audit(fake)
    assert evidence["stages"][-1]["log"]["size_bytes"] <= bootstrap.LOG_BYTES
    assert fake.calls[-1]["stage"] == stage


@pytest.mark.parametrize("name", ["output_path", "checkpoint_path", "audit_path", "report_path", "bootstrap_audit_path", *bootstrap.STAGES])
def test_existing_outputs_and_logs_preserved_before_any_subprocess(fake_pipeline, name):
    fake = fake_pipeline
    path = fake.arguments[name] if name.endswith("_path") else Path(str(fake.arguments["bootstrap_audit_path"]) + "." + name + ".log")
    path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b"original evidence")
    with pytest.raises(ValueError, match="Preserve existing"):
        run(fake)
    assert path.read_bytes() == b"original evidence" and fake.calls == []


@pytest.mark.parametrize("target", ["job", "core_path", "runner_path", "report_path"])
def test_path_collisions_reject_before_any_subprocess(fake_pipeline, target):
    fake = fake_pipeline
    fake.arguments["bootstrap_audit_path"] = fake.job if target == "job" else fake.arguments[target]
    with pytest.raises(ValueError, match="paths must be distinct"):
        run(fake)
    assert fake.calls == []


@pytest.mark.parametrize("name", ["component_core.py", "qwen_components_kaggle_runner.py", "qwen_kaggle_environment.py", "job.json"])
def test_input_binding_failure_precedes_any_subprocess(fake_pipeline, name):
    fake = fake_pipeline
    path = fake.job.parent / name
    path.write_bytes(path.read_bytes() + b"\n# changed")
    with pytest.raises((ValueError, json.JSONDecodeError)):
        run(fake)
    assert fake.calls == [] and not fake.arguments["bootstrap_audit_path"].exists()


def test_existing_symlink_is_preserved_before_any_subprocess(fake_pipeline, tmp_path):
    fake = fake_pipeline
    target = tmp_path / "untouched"; target.write_bytes(b"original")
    path = fake.arguments["bootstrap_audit_path"]; path.parent.mkdir(parents=True, exist_ok=True); path.symlink_to(target)
    with pytest.raises(ValueError, match="Preserve existing"):
        run(fake)
    assert target.read_bytes() == b"original" and path.is_symlink() and fake.calls == []


class Response:
    def __init__(self, body, *, url=None, length=None, status=200):
        self.stream = io.BytesIO(body); self.url = url or bootstrap.PIP_WHEEL["url"]
        self.headers = {} if length is None else {"Content-Length": str(length)}
        self.status = status
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def geturl(self): return self.url
    def read(self, count): return self.stream.read(count)


@pytest.mark.parametrize("defect", [None, "extra", "short", "checksum", "redirect", "declared_size", "status", "tls"])
def test_child_download_fixed_verified_https_request_and_byte_bound(tmp_path, monkeypatch, defect):
    pin = {**bootstrap.PIP_WHEEL, "size_bytes": len(WHEEL_BODY), "sha256": hashlib.sha256(WHEEL_BODY).hexdigest()}
    monkeypatch.setattr(bootstrap, "PIP_WHEEL", pin)
    calls = []
    def fetch(request, **kwargs):
        calls.append((request, kwargs))
        assert request.full_url == pin["url"] and request.full_url.startswith("https://files.pythonhosted.org/")
        assert kwargs == {"timeout": 60}  # No custom/unverified SSL context.
        if defect == "tls": raise OSError("simulated TLS verification error")
        body = WHEEL_BODY + b"x" if defect == "extra" else (b"short" if defect == "short" else (b"X" * len(WHEEL_BODY) if defect == "checksum" else WHEEL_BODY))
        return Response(body, url="https://unbound.example/pip.whl" if defect == "redirect" else None,
                        length=len(WHEEL_BODY) + 1 if defect == "declared_size" else None, status=403 if defect == "status" else 200)
    monkeypatch.setattr(bootstrap.urllib.request, "urlopen", fetch)
    output = tmp_path / pin["filename"]
    if defect is None:
        bootstrap._download_wheel(output)
        assert output.read_bytes() == WHEEL_BODY
    else:
        with pytest.raises((ValueError, OSError)):
            bootstrap._download_wheel(output)
    assert len(calls) == 1
    if output.exists(): assert output.stat().st_size <= pin["size_bytes"]


def test_download_preserves_preexisting_wheel_without_network(tmp_path):
    path = tmp_path / bootstrap.PIP_WHEEL["filename"]; path.write_bytes(b"evidence")
    with pytest.raises(ValueError, match="Preserve existing"):
        bootstrap._download_wheel(path)
    assert path.read_bytes() == b"evidence"


def test_real_pip_free_venv_and_isolated_verified_wheel_version_only(tmp_path):
    # Optional retained official wheel enables a real offline entry-point check.
    # No download or install occurs if it is absent; the provenance owner supplies it.
    wheel = Path(os.environ.get("QWEN_BOOTSTRAP_SMOKE_WHEEL", "/private/tmp/lre-pip-bootstrap-25-2/pip-25.2-py3-none-any.whl"))
    if not wheel.is_file(): pytest.skip("Retained verified pip wheel is unavailable; no download fallback")
    bootstrap._wheel_binding(wheel)
    base = str(Path(sys.executable).resolve())
    installer = tmp_path / "installer"
    subprocess.run([base, "-I", "-m", "venv", "--without-pip", str(installer)], check=True, capture_output=True)
    python = installer / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    hostile = {**os.environ, "PYTHONHOME": str(tmp_path / "missing-home"), "PYTHONPATH": str(tmp_path / "poison"),
               "PYTHONUSERBASE": str(tmp_path / "poison-user"), "PIP_EXTRA_INDEX_URL": "https://invalid.example/no-network"}
    poison = tmp_path / "poison"; poison.mkdir()
    marker = tmp_path / "poison-ran"
    (poison / "sitecustomize.py").write_text("from pathlib import Path\nPath(" + repr(str(marker)) + ").write_text('ran')\n")
    probe = subprocess.run([str(python), "-I", "-S", "-c", bootstrap.PROBE], check=True, capture_output=True, env=hostile)
    checked = bootstrap._check_isolation(probe.stdout, installer, python)
    version = subprocess.run([str(python), "-I", "-S", str(wheel / "pip"), "--isolated", "--disable-pip-version-check",
                              "--no-cache-dir", "--no-input", "--keyring-provider", "disabled", "--version"],
                             check=True, capture_output=True, env=hostile)
    assert version.stdout.decode().strip() == "pip 25.2 from " + str(wheel / "pip") + " (python " + ".".join(checked["python_version"].split(".")[:2]) + ")"
    assert not marker.exists()
    assert not any(path.name.startswith("pip") for path in installer.rglob("site-packages/*"))
