"""Independent installer/worker preflight evidence, without installs or GPU use."""

from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest

from src.review_components import core
from tools import qwen_kaggle_environment as environment


ROOT = Path(__file__).resolve().parents[1]
PINS = {"transformers": "4.51.3", "tokenizers": "0.21.1", "safetensors": "0.5.3", "huggingface-hub": "0.30.2"}
REQUIREMENTS = {
    "transformers": ["filelock", "huggingface-hub<1.0,>=0.30.0", "numpy>=1.17", "packaging>=20.0", "pyyaml>=5.1", "regex!=2019.12.17", "requests", "tokenizers<0.22,>=0.21", "safetensors>=0.4.3", "tqdm>=4.27"],
    "tokenizers": ["huggingface-hub>=0.16.4,<1.0"], "safetensors": [],
    "huggingface-hub": ["filelock", "fsspec>=2023.5.0", "packaging>=20.9", "pyyaml>=5.1", "requests", "tqdm>=4.42.1", "typing-extensions>=3.7.4.3"],
}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("Environment test attempted network"))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bundle(tmp_path):
    root = tmp_path / "upload"; root.mkdir()
    paths = {"component_core.py": ROOT / "src/review_components/core.py", "qwen_kaggle_environment.py": ROOT / "tools/qwen_kaggle_environment.py", "qwen_components_kaggle_runner.py": ROOT / "tools/qwen_components_kaggle_runner.py"}
    for name, path in paths.items(): (root / name).write_bytes(path.read_bytes())
    payload = {"execution_files": {name: environment.file_binding(root / name) for name in paths}, "profile_sha256": core.digest(core.PROFILE)}
    job = root / "job.json"; job.write_text(core.canonical({"payload": payload, "payload_sha256": core.digest(payload)}))
    return root, job, core.digest(payload)


def test_fresh_default_venv_installer_no_deps_overlay_and_isolated_original_python_worker(tmp_path, monkeypatch):
    root, job, sha = bundle(tmp_path)
    helper = load(root / "qwen_kaggle_environment.py", "isolated_installer_evaluation")
    base = tmp_path / "unchanged-base"; base.mkdir()
    for name, version in {"gradio": "6.26.0", "diffusers": "0.40.0", "torch": "2.6.0+cu124", "huggingface-hub": "0.33.4", "safetensors": "0.6.1"}.items():
        (base / name).write_text(version)
    before = {path.name: path.read_bytes() for path in base.iterdir()}
    calls = []; actual_run = subprocess.run
    def run(command, **kwargs):
        calls.append((command, kwargs))
        assert kwargs == {"check": True}
        if command[2:4] == ["-m", "venv"]:
            # Real default venv creation is local and uses ensurepip's bundled wheels.
            return actual_run(command, check=True, capture_output=True)
        if "pip" in command:
            assert "--no-deps" in command and "--target" in command and "--report" in command
            Path(command[command.index("--report") + 1]).write_text('{"install": []}')
            return SimpleNamespace(returncode=0)
        assert command[1] == "-I" and command[2] == str((root / "qwen_components_kaggle_runner.py").resolve())
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(helper.subprocess, "run", run)
    outputs = {name: tmp_path / "saved" / (name + ".json") for name in ("output", "checkpoint", "audit", "report")}
    result = helper.prepare_environment(job, sha, core_path=root / "component_core.py", runner_path=root / "qwen_components_kaggle_runner.py", output_path=outputs["output"], checkpoint_path=outputs["checkpoint"], audit_path=outputs["audit"], report_path=outputs["report"], temporary_root=tmp_path / "temporary")
    assert len(calls) == 3
    venv, pip, worker = [row[0] for row in calls]
    assert venv[:4] == [str(Path(sys.executable).resolve()), "-I", "-m", "venv"]
    config = (Path(venv[4]) / "pyvenv.cfg").read_text()
    assert "include-system-site-packages = false" in config
    assert pip[:6] == [str(Path(venv[4]) / "bin/python"), "-I", "-m", "pip", "install", "--no-deps"]
    assert pip[-4:] == [name + "==" + version for name, version in PINS.items()]
    assert Path(pip[pip.index("--target") + 1]).resolve() == Path(result["overlay_path"])
    assert not Path(result["overlay_path"]).is_relative_to(outputs["output"].parent)
    assert worker[0] == venv[0] and worker[0] != pip[0] and worker[1] == "-I"
    flags = dict(zip(worker[3::2], worker[4::2]))
    assert flags["--job-sha256"] == sha and float(flags["--setup-seconds"]) >= 0
    for flag in ("--job", "--core", "--environment-helper", "--overlay", "--installer-report", "--output", "--checkpoint", "--environment-audit"):
        assert Path(flags[flag]).is_absolute() and str(Path(flags[flag]).resolve()) == flags[flag]
    assert {path.name: path.read_bytes() for path in base.iterdir()} == before


@pytest.mark.parametrize("name", ["output", "checkpoint", "audit", "report"])
def test_installer_preserves_existing_artifacts_before_any_subprocess(tmp_path, monkeypatch, name):
    root, job, sha = bundle(tmp_path)
    helper = load(root / "qwen_kaggle_environment.py", "preservation_evaluation")
    paths = {key: tmp_path / (key + ".json") for key in ("output", "checkpoint", "audit", "report")}
    paths[name].write_bytes(b"prior immutable evidence")
    monkeypatch.setattr(helper.subprocess, "run", lambda *a, **k: pytest.fail("Preflight failure launched installer"))
    with pytest.raises(ValueError, match="Preserve existing"):
        helper.prepare_environment(job, sha, core_path=root / "component_core.py", runner_path=root / "qwen_components_kaggle_runner.py", output_path=paths["output"], checkpoint_path=paths["checkpoint"], audit_path=paths["audit"], report_path=paths["report"], temporary_root=tmp_path / "temporary")
    assert paths[name].read_bytes() == b"prior immutable evidence"


@pytest.mark.parametrize("name", ["component_core.py", "qwen_kaggle_environment.py", "qwen_components_kaggle_runner.py"])
def test_notebook_checks_every_executable_hash_before_helper_code_loading(tmp_path, name):
    root, job, sha = bundle(tmp_path)
    notebook = json.loads((ROOT / "notebooks/qwen_components_kaggle.ipynb").read_text())
    code = next("".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code" and "spec.loader.exec_module(helper)" in "".join(cell["source"]))
    marker = tmp_path / "unexpected-execution"
    (root / name).write_text("from pathlib import Path\nPath(" + repr(str(marker)) + ").write_text('executed')\n")
    values = {"BUNDLE": root, "JOB_PATH": job, "JOB_SHA256": sha, "CORE_PATH": root / "component_core.py", "HELPER_PATH": root / "qwen_kaggle_environment.py", "RUNNER_PATH": root / "qwen_components_kaggle_runner.py"}
    with pytest.raises(AssertionError): exec(compile(code, "independent-notebook-cell", "exec"), values)
    assert not marker.exists() and "helper" not in values


class Scalar:
    def __init__(self, data): self.data = data
    def __mul__(self, other): return Scalar([a * b for a, b in zip(self.data, other.data)])
    def sum(self): return Scalar(sum(self.data))
    def item(self): return self.data


def fake_environment(tmp_path, monkeypatch):
    overlay = tmp_path / "overlay"; overlay.mkdir()
    base = tmp_path / "base"; base.mkdir()
    report = tmp_path / "installer.json"; report.write_bytes(b'{"install":[]}')
    events = []
    class Distribution:
        def __init__(self, version, location, requirements=None):
            self.version, self.location, self.requires = version, location, requirements or []
            self.metadata = {"Requires-Python": ">=3.9"}
        def locate_file(self, value): return self.location / value
    versions = {"filelock": "3.18.0", "numpy": "2.0.2", "packaging": "24.2", "pyyaml": "6.0.2", "regex": "2024.11.6", "requests": "2.32.3", "tqdm": "4.67.1", "fsspec": "2025.3.0", "typing-extensions": "4.13.2"}
    distributions = {name: Distribution(version, base / name) for name, version in versions.items()}
    distributions.update({name: Distribution(version, overlay, deepcopy(REQUIREMENTS[name])) for name, version in PINS.items()})
    # Inactive extra and platform requirements must not trigger resolution/install.
    distributions["transformers"].requires += ["absent-test-extra>=2; extra == 'dev'", "absent-other-os>=2; sys_platform == 'not-the-current-platform'"]
    def distribution(name):
        name = name.replace("_", "-").lower()
        events.append(("distribution", name))
        if name not in distributions: raise environment.importlib.metadata.PackageNotFoundError(name)
        return distributions[name]
    monkeypatch.setattr(environment.importlib.metadata, "distribution", distribution)
    modules = {}
    for name, module_name in environment.MODULES.items():
        monkeypatch.delitem(sys.modules, module_name, raising=False)
        module = ModuleType(module_name)
        module.__file__ = str(overlay / module_name / "__init__.py")
        module.__version__ = PINS[name]
        modules[module_name] = module
    for name in ("AutoModel", "AutoModelForCausalLM", "AutoTokenizer"): setattr(modules["transformers"], name, SimpleNamespace(from_pretrained=lambda *a, **k: pytest.fail("Audit loaded weights")))
    qwen = ModuleType("transformers.models.qwen3.modeling_qwen3")
    qwen.Qwen3Model, qwen.Qwen3ForCausalLM = object, object
    torch = ModuleType("torch")
    torch.__file__, torch.__version__ = str(base / "torch/__init__.py"), "2.6.0+cu124"
    torch.version = SimpleNamespace(cuda="12.4")
    cuda = SimpleNamespace(is_available=lambda: True, set_device=lambda value: events.append(("device", value)), synchronize=lambda: events.append(("synchronize",)), get_device_properties=lambda value: SimpleNamespace(name="CPU fake CUDA GPU", total_memory=16 * 1024**3), device_count=lambda: 2)
    torch.cuda, torch.float16 = cuda, "float16"
    class Inference:
        def __enter__(self): events.append(("inference_mode",)); return self
        def __exit__(self, *args): return False
    torch.inference_mode = Inference
    def ones(shape, **kwargs):
        events.append(("smoke_allocation", shape, kwargs)); return Scalar([1.0] * shape[0])
    torch.ones = ones
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, qwen.__name__, qwen)
    real_import = environment.importlib.import_module
    def imported(name, *args, **kwargs):
        if name not in modules: return real_import(name, *args, **kwargs)
        events.append(("import", name))
        monkeypatch.setitem(sys.modules, name, modules[name])
        return modules[name]
    monkeypatch.setattr(environment.importlib, "import_module", imported)
    monkeypatch.setattr(sys, "path", list(sys.path))
    return overlay, report, distributions, modules, torch, events


def test_active_requirements_resolved_origins_and_cuda_operation_before_weights(tmp_path, monkeypatch):
    overlay, report, distributions, modules, torch, events = fake_environment(tmp_path, monkeypatch)
    monkeypatch.setenv("UNRELATED_PROVIDER_SECRET", "invented-secret-never-record")
    audit = environment.audit_environment(overlay / ".." / "overlay", report, {"bound": "executables"}, active_requirements=REQUIREMENTS, setup_seconds=1.25)
    assert audit["recipe"] == "isolated-installer-no-deps-overlay;isolated-base-worker-v1" and audit["requirements_passed"] is True
    assert audit["overlay_path"] == str(overlay.resolve()) and audit["base_python"] == str(Path(sys.executable).resolve())
    assert audit["setup_seconds"] == 1.25 and audit["installer_report_sha256"] == hashlib.sha256(report.read_bytes()).hexdigest()
    assert audit["torch"] == {"version": "2.6.0+cu124", "location": str(Path(torch.__file__).resolve()), "cuda_version": "12.4", "device": "cuda:0", "gpu_name": "CPU fake CUDA GPU", "device_count": 2, "total_memory_bytes": 16 * 1024**3, "smoke_passed": True}
    assert sys.path[0] == str(overlay.resolve())
    assert not any("absent" in event[1] for event in events if event[0] == "distribution")
    assert "invented-secret-never-record" not in json.dumps(audit) and "gradio" not in audit["packages"] and "diffusers" not in audit["packages"]
    for name, package in audit["packages"].items():
        assert package["version"] == PINS[name] and Path(package["location"]).is_relative_to(overlay)
        assert sorted(row["requirement"] for row in package["requirements"]) == sorted(REQUIREMENTS[name])
    assert ("smoke_allocation", (8,), {"dtype": "float16", "device": "cuda:0"}) in events
    assert events.index(("import", "huggingface_hub")) < events.index(("smoke_allocation", (8,), {"dtype": "float16", "device": "cuda:0"}))


@pytest.mark.parametrize("defect", ["missing", "incompatible", "python", "pin_version", "metadata_origin", "import_origin", "import_symlink", "import_version", "direct_url", "changed_recipe", "preloaded", "torch_overlay", "no_cuda", "bad_smoke"])
def test_missing_incompatible_or_escaped_environment_fails_closed(tmp_path, monkeypatch, defect):
    overlay, report, distributions, modules, torch, events = fake_environment(tmp_path, monkeypatch)
    if defect == "missing": del distributions["fsspec"]
    elif defect == "incompatible": distributions["fsspec"].version = "2022.1.0"
    elif defect == "python": distributions["transformers"].metadata["Requires-Python"] = ">=99"
    elif defect == "pin_version": distributions["tokenizers"].version = "0.22.0"
    elif defect == "metadata_origin": distributions["tokenizers"].location = tmp_path / "base"
    elif defect == "import_origin": modules["tokenizers"].__file__ = str(tmp_path / "base/tokenizers.py")
    elif defect == "import_symlink":
        target = tmp_path / "base/tokenizers.py"; target.write_text("base module")
        link = overlay / "tokenizers.py"; link.symlink_to(target)
        modules["tokenizers"].__file__ = str(link)
    elif defect == "import_version": modules["safetensors"].__version__ = "0.6.1"
    elif defect == "direct_url": distributions["transformers"].requires.append("novel @ https://invalid.example/pkg.whl"); distributions["novel"] = distributions["numpy"]
    elif defect == "changed_recipe": distributions["transformers"].requires.append("numpy>=1")
    elif defect == "preloaded": monkeypatch.setitem(sys.modules, "tokenizers", modules["tokenizers"])
    elif defect == "torch_overlay": torch.__file__ = str(overlay / "torch/__init__.py")
    elif defect == "no_cuda": torch.cuda.is_available = lambda: False
    elif defect == "bad_smoke": torch.ones = lambda *a, **k: Scalar([0.0] * 8)
    with pytest.raises(ValueError): environment.audit_environment(overlay, report, {}, active_requirements=REQUIREMENTS)
    assert not any(event[0] == "smoke_allocation" for event in events) if defect not in {"bad_smoke"} else True


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True])
def test_setup_elapsed_time_must_be_finite_nonnegative_number(tmp_path, monkeypatch, value):
    overlay, report, _, _, _, _ = fake_environment(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="setup elapsed"):
        environment.audit_environment(overlay, report, {}, active_requirements=REQUIREMENTS, setup_seconds=value)
