"""Scoped pinned-library overlay; imports perform no installation or GPU work."""

import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time


PINS = {"transformers": "4.51.3", "tokenizers": "0.21.1", "safetensors": "0.5.3", "huggingface-hub": "0.30.2"}
MODULES = {"transformers": "transformers", "tokenizers": "tokenizers", "safetensors": "safetensors", "huggingface-hub": "huggingface_hub"}
RECIPE = "isolated-installer-no-deps-overlay;isolated-base-worker-v1"


def _require(value, message):
    if not value:
        raise ValueError(message)


def file_binding(path):
    data = Path(path).read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def _json(path):
    def pairs(items):
        value = {}
        for name, item in items:
            _require(name not in value, "Duplicate JSON key")
            value[name] = item
        return value
    path = Path(path)
    _require(path.stat().st_size <= 100 * 1024 * 1024, "Environment job exceeds artifact bound")
    value = json.loads(path.read_bytes(), object_pairs_hook=pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
    json.dumps(value, allow_nan=False)
    return value


def verify_bundle(job_path, job_sha256, *, core_path, runner_path, helper_path=None):
    envelope = _json(job_path)
    _require(isinstance(envelope, dict) and set(envelope) == {"payload", "payload_sha256"}, "Invalid component job envelope")
    encoded = json.dumps(envelope["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    _require(envelope["payload_sha256"] == hashlib.sha256(encoded).hexdigest() == job_sha256, "Component job checksum differs from trusted local export")
    job = envelope["payload"]
    paths = {"component_core.py": Path(core_path), "qwen_components_kaggle_runner.py": Path(runner_path),
             "qwen_kaggle_environment.py": Path(helper_path or __file__)}
    _require(set(job.get("execution_files", {})) == set(paths), "Missing exact executable byte bindings")
    _require(len({path.resolve() for path in paths.values()}) == 3, "Executable helper paths must be distinct")
    bundle_root = Path(job_path).resolve().parent
    for name, path in paths.items():
        _require(path.name == name and path.resolve().is_relative_to(bundle_root), "Executable file must be contained in the explicit upload bundle: " + name)
        _require(path.is_file() and file_binding(path) == job["execution_files"][name], "Executable file differs from trusted job: " + name)
    return job


def prepare_environment(job_path, job_sha256, *, core_path, runner_path, output_path, checkpoint_path,
                        audit_path, report_path, temporary_root="/kaggle/temp", base_python=None):
    """Use a disposable installer; launch a fresh isolated base-Python worker."""
    started = time.monotonic()
    job = verify_bundle(job_path, job_sha256, core_path=core_path, runner_path=runner_path)
    paths = [Path(path) for path in (job_path, core_path, runner_path, output_path, checkpoint_path, audit_path, report_path)]
    _require(len({path.resolve() for path in paths}) == len(paths), "Input/output paths must be distinct")
    for path in paths[3:]:
        _require(not os.path.lexists(path), "Preserve existing output and select a new path: " + str(path))
        path.parent.mkdir(parents=True, exist_ok=True)
    base_python = str(Path(base_python or sys.executable).resolve())
    Path(temporary_root).mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="qwen-components-", dir=temporary_root))
    installer, overlay = temporary / "installer", temporary / "overlay"
    overlay.mkdir()
    print("Creating isolated installer; preserving Kaggle base packages and CUDA Torch", flush=True)
    subprocess.run([base_python, "-I", "-m", "venv", str(installer)], check=True)
    installer_python = installer / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    print("Installing four exact Qwen packages without dependencies into a private overlay", flush=True)
    subprocess.run([str(installer_python), "-I", "-m", "pip", "install", "--no-deps", "--target", str(overlay),
                    "--report", str(Path(report_path).resolve()), *[name + "==" + version for name, version in PINS.items()]], check=True)
    print("Starting fresh base-Python worker; checking dependencies and CUDA before any weights", flush=True)
    command = [base_python, "-I", str(Path(runner_path).resolve()), "--job", str(Path(job_path).resolve()),
               "--job-sha256", job_sha256, "--core", str(Path(core_path).resolve()), "--environment-helper", str(Path(__file__).resolve()),
               "--overlay", str(overlay.resolve()), "--installer-report", str(Path(report_path).resolve()),
               "--setup-seconds", str(time.monotonic() - started), "--output", str(Path(output_path).resolve()),
               "--checkpoint", str(Path(checkpoint_path).resolve()), "--environment-audit", str(Path(audit_path).resolve())]
    subprocess.run(command, check=True)
    return {"output_path": str(Path(output_path).resolve()), "audit_path": str(Path(audit_path).resolve()),
            "installer_report_path": str(Path(report_path).resolve()), "overlay_path": str(overlay.resolve()),
            "profile_sha256": job["profile_sha256"]}


def audit_environment(overlay_path, installer_report_path, execution_files, *, active_requirements, setup_seconds=0.0):
    """Called only in a fresh worker, before any model-weight download."""
    overlay = Path(overlay_path).resolve()
    _require(overlay.is_dir(), "Retrieval overlay is missing")
    _require(type(setup_seconds) in (int, float) and math.isfinite(setup_seconds) and setup_seconds >= 0, "Invalid recorded setup elapsed time")
    for module in MODULES.values():
        _require(module not in sys.modules, "Start a fresh worker before importing retrieval libraries: " + module)
    sys.path.insert(0, str(overlay))
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    from packaging.specifiers import SpecifierSet
    marker_environment = {**default_environment(), "extra": ""}
    packages = {}
    for name, expected in PINS.items():
        distribution = importlib.metadata.distribution(name)
        _require(distribution.version == expected, "Pinned package version mismatch: " + name)
        distribution_location = Path(distribution.locate_file("")).resolve()
        _require(distribution_location.is_relative_to(overlay), "Pinned package metadata escaped overlay: " + name)
        python_requirement = distribution.metadata.get("Requires-Python")
        _require(not python_requirement or SpecifierSet(python_requirement).contains(platform.python_version()), "Python does not satisfy pinned package: " + name)
        dependencies = []
        for original in distribution.requires or []:
            requirement = Requirement(original)
            if requirement.marker is not None and not requirement.marker.evaluate(marker_environment):
                continue
            try:
                resolved = importlib.metadata.distribution(requirement.name)
            except importlib.metadata.PackageNotFoundError:
                raise ValueError("Missing active dependency " + requirement.name + " required by " + name + ": " + original) from None
            _require(not requirement.url, "Direct-URL dependency requires a new explicit recipe: " + original)
            _require(requirement.specifier.contains(resolved.version), "Incompatible active dependency " + requirement.name + "=" + resolved.version + " required by " + name + ": " + original)
            dependencies.append({"name": requirement.name, "requirement": original, "version": resolved.version,
                                 "location": str(Path(resolved.locate_file("")).resolve())})
        packages[name] = {"version": distribution.version, "location": None, "requirements": dependencies}
        _require(sorted(row["requirement"] for row in dependencies) == sorted(active_requirements[name]),
                 "Active dependency metadata differs from the prospective pinned recipe: " + name)
    for name, module_name in MODULES.items():
        module = importlib.import_module(module_name)
        location = Path(module.__file__).resolve()
        _require(location.is_relative_to(overlay), "Pinned library import escaped overlay: " + name)
        _require(getattr(module, "__version__", None) == PINS[name], "Imported library version mismatch: " + name)
        packages[name]["location"] = str(location)
    # Transformers is lazy: resolve the exact architecture before downloading weights.
    from transformers import AutoModel, AutoModelForCausalLM, AutoTokenizer
    from transformers.models.qwen3.modeling_qwen3 import Qwen3Model, Qwen3ForCausalLM
    import torch
    torch_path = Path(torch.__file__).resolve()
    _require(not torch_path.is_relative_to(overlay), "CUDA Torch must come from the unchanged Kaggle base environment")
    _require(torch.cuda.is_available(), "Kaggle CUDA GPU is unavailable; no CPU or paid fallback")
    torch.cuda.set_device(0)
    with torch.inference_mode():
        smoke = torch.ones((8,), dtype=torch.float16, device="cuda:0")
        _require(float((smoke * smoke).sum().item()) == 8.0, "CUDA allocation/operation smoke check failed")
    del smoke
    torch.cuda.synchronize()
    properties = torch.cuda.get_device_properties(0)
    return {"schema_version": 1, "recipe": RECIPE, "overlay_path": str(overlay), "base_python": str(Path(sys.executable).resolve()),
            "installer_report_sha256": file_binding(installer_report_path)["sha256"], "execution_files": execution_files,
            "packages": packages, "torch": {"version": torch.__version__, "location": str(torch_path),
                                              "cuda_version": torch.version.cuda, "device": "cuda:0", "gpu_name": properties.name,
                                              "device_count": torch.cuda.device_count(), "total_memory_bytes": properties.total_memory, "smoke_passed": True},
            "python_version": platform.python_version(), "setup_seconds": setup_seconds, "requirements_passed": True}
