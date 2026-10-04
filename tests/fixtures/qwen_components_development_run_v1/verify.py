#!/usr/bin/env python3
"""Read-only numeric/source replay of the preserved first development grade."""

from copy import deepcopy
import hashlib
import io
import json
import lzma
import math
from pathlib import Path
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from src.review_components import core, ledger
from src.review.qwen_batch import _runtime
from tools import evaluate_qwen_components as evaluation

HERE = Path(__file__).resolve().parent
JOB_SHA = "4de843130af3727968e1a0f7bfd150c5743fcfb521d820a5c0fe0fd9c3bc3ce2"
RESULT_SHA = "c823163facad5db6614d37e57b4845e92af252ff88bfb463895a489a6f7cc923"
GRADE_PIN = {"sha256": "fb1697b165c9a3d9323193a0bb233208b65363f24a1ba635afd063567c6a5043", "size_bytes": 532051}
ARCHIVE_PIN = {"sha256": "ff3e3ca5b8f54e5256066ae8db32e3c9986793dc89a2121cdbc9d07a3ed6d40d", "size_bytes": 2618364}
FREEZE_SHA = "a70cfd4a4a1526e2e8da72f1b34ef1586ce6be430e9474892cf76a9b45d5ade0"
STAGES = ("venv", "installer_isolation", "wheel_download", "pip_version", "pip_install", "worker")
OUTPUTS = {"components-bootstrap-audit.json", "components-checkpoint.json", "components-environment-audit.json",
           "components-installer-report.json", "components-results.json",
           *{"components-bootstrap-audit.json." + stage + ".log" for stage in STAGES}}
MEMBERS = OUTPUTS | {"job.json", "preparation.json", "validation.receipt.json"}


def require(value, message):
    if not value: raise ValueError(message)


def pin(body):
    return {"sha256": hashlib.sha256(body).hexdigest(), "size_bytes": len(body)}


def read(path, limit):
    require(path.is_file() and not path.is_symlink(), "Evidence must be a regular file: " + path.name)
    with path.open("rb") as stream: body = stream.read(limit + 1)
    require(len(body) <= limit, "Evidence exceeds its size bound: " + path.name)
    return body


def envelope(body):
    value = core.read_json(body)
    require(isinstance(value, dict) and set(value) == {"payload", "payload_sha256"}
            and value["payload_sha256"] == core.digest(value["payload"]), "Artifact envelope digest differs")
    return value


def same(left, right, message):
    require(core.canonical(left) == core.canonical(right), message)


def unpack(body, manifest):
    require(pin(body) == ARCHIVE_PIN, "Original compressed archive differs")
    require(manifest["archive"].get("filename") == "artifacts.tar.xz", "Manifest archive filename differs")
    same({k: manifest["archive"].get(k) for k in ARCHIVE_PIN}, ARCHIVE_PIN, "Manifest archive binding differs")
    decoder = lzma.LZMADecompressor(memlimit=256 * 1024 * 1024)
    raw = decoder.decompress(body, max_length=64 * 1024 * 1024 + 1)
    require(decoder.eof and not decoder.unused_data and len(raw) <= 64 * 1024 * 1024, "Unbounded or concatenated XZ archive")
    require(type(manifest["archive"].get("member_count")) is int and manifest["archive"]["member_count"] == 14
            and type(manifest["archive"].get("uncompressed_tar_bytes")) is int
            and manifest["archive"]["uncompressed_tar_bytes"] == len(raw), "Manifest archive dimensions differ")
    require(set(manifest["archive_members"]) == MEMBERS, "Archive member manifest differs")
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for item in archive:
            require(item.name in MEMBERS and item.name not in files and item.isreg() and item.name == Path(item.name).name
                    and 0 <= item.size <= 16 * 1024 * 1024 and not item.pax_headers
                    and item.uid == item.gid == item.mtime == 0 and item.mode == 0o644, "Unsafe or duplicate archive member")
            content = archive.extractfile(item).read(item.size + 1)
            require(len(content) == item.size, "Truncated archive member")
            same(pin(content), {k: manifest["archive_members"][item.name].get(k) for k in ("sha256", "size_bytes")}, "Original member digest differs")
            files[item.name] = content
    require(set(files) == MEMBERS, "Archive requires all fourteen exact members")
    return files


def replay(job, payload, checked):
    target, whole, diagnostics = [], [], []
    for question, plan in zip(job["questions"], checked["plans"], strict=True):
        ids = [part["id"] for part in question["components"]]
        maps = [core.aggregate(job, plan, checked["scoremaps"], identifier) for identifier in [None, *ids]]
        selected = core.select(job["candidates"], plan["target_block_indices"], maps, ids)
        target.append(ledger._trace(job, question, "qwen_components_hybrid", selected, maps, ids))
        whole_map = core.aggregate(job, plan, checked["scoremaps"], None, whole_reference=True)
        whole_selected = core.select(job["candidates"], plan["whole_block_indices"], [whole_map], [])
        whole.append(ledger._trace(job, question, "qwen_kaggle_hybrid", whole_selected, [whole_map], []))
        def passages(indices, scores):
            return [{"rank": rank, "score": scores[index], **deepcopy(job["candidates"][index]["passage"])} for rank, index in enumerate(indices, 1)]
        diagnostics.append({"question_id": question["id"], "not_for_display": True, "pool_budget": 20,
            "target_pool_passages": passages(plan["target_block_indices"], maps[0]),
            "whole_pool_passages": passages(plan["whole_block_indices"], whole_map), "allocation": deepcopy(plan),
            "target_selected_block_indices": selected["block_indices"]})
    lexical = ledger._lexical(job)
    for trace in [*target, *whole, *lexical["whole_lexical"], *lexical["component_lexical"]]:
        trace.update(execution="offline_import", job_sha256=JOB_SHA, results_sha256=RESULT_SHA)
    return {"schema_version": 1, "status": "candidate_passages", "job_sha256": JOB_SHA, "results_sha256": RESULT_SHA,
            "profile": deepcopy(core.PROFILE), "runtime": deepcopy(payload["runtime"]), "environment_audit": deepcopy(payload["environment_audit"]),
            "distinct_rerank_pairs": len(checked["pair_inputs"]), "traces": target,
            "comparators": {"whole_qwen": whole, "whole_lexical": lexical["whole_lexical"], "component_lexical": lexical["component_lexical"]},
            "diagnostics": diagnostics, "lexical_diagnostics": lexical["diagnostics"]}


def verify(directory=HERE):
    directory = Path(directory)
    manifest = core.read_json(read(directory / "manifest.json", 1024 * 1024))
    require(isinstance(manifest, dict) and set(manifest) == {"schema_version", "status", "created_at_utc", "job_payload_sha256",
        "results_payload_sha256", "files", "archive", "archive_members", "development_freeze", "bootstrap_deployment",
        "software_commit", "saved_version", "grade", "runtime", "excluded"}, "Preservation manifest fields differ")
    require(type(manifest.get("schema_version")) is int and manifest["schema_version"] == 1
            and manifest.get("status") == "preserved_first_components_development_grade", "Preservation manifest status differs")
    require(manifest.get("job_payload_sha256") == JOB_SHA and manifest.get("results_payload_sha256") == RESULT_SHA
            and manifest.get("software_commit") == "85b5df4", "Trusted saved-run identity differs")
    saved = manifest["saved_version"]
    require(type(saved.get("id")) is int and saved["id"] == 355187018 and type(saved.get("number")) is int and saved["number"] == 3
            and saved.get("saved_at_utc") == "2026-10-04T14:16:50Z" and type(saved.get("ui_wall_seconds")) is float
            and saved["ui_wall_seconds"] == 1108.3 and saved.get("internet_enabled") is True
            and saved.get("interactive_draft_started") is False and saved.get("visibility") == "private"
            and saved.get("accelerator") == "T4x2" and saved.get("editor_environment_setting") == "Pin to original environment (2026-10-03)"
            and saved.get("saved_page_image_link") == "gcr.io/kaggle-gpu-images/python@sha256:2757e0c7d1e0a9cb43da657b97e223c321a98f5014bdf64f44f2f6b083ad2b2f"
            and saved.get("image_link_claim") == "Observed saved Logs page link; not cryptographic execution attestation.", "Saved UI provenance differs")
    require(set(manifest["files"]) == {"result.json", "run.log", "imported-draft.ipynb"}, "Plain evidence set differs")
    plain = {}
    original_paths = {"result.json": "data/qwen-components-development-v1/result.json",
        "run.log": "data/qwen-components-development-v1/run-evidence/bootstrap-v2-run.log",
        "imported-draft.ipynb": "data/qwen-components-development-v1/run-evidence/bootstrap-v2-imported-draft.ipynb"}
    for name in manifest["files"]:
        plain[name] = read(directory / name, 2 * 1024 * 1024)
        same({"original_path": original_paths[name], **pin(plain[name])}, manifest["files"][name], "Plain evidence digest/origin differs")
    require(pin(plain["result.json"]) == GRADE_PIN, "First local grade bytes differ")
    grade = core.read_json(plain["result.json"])
    files = unpack(read(directory / "artifacts.tar.xz", 16 * 1024 * 1024), manifest)
    for name in files:
        original_path = ("data/qwen-components-development-v1/kaggle-upload/job.json" if name == "job.json"
            else "data/qwen-components-development-v1/" + name if name in {"preparation.json", "validation.receipt.json"}
            else "data/qwen-components-development-v1/run-evidence/bootstrap-v2-output/" + name)
        same({"original_path": original_path, **pin(files[name])}, manifest["archive_members"][name], "Archived original path differs")
    freeze_path = ROOT / "docs/qwen-components-development-freeze-v1.json"
    require(pin(read(freeze_path, 1024 * 1024))["sha256"] == FREEZE_SHA, "Prospective development freeze differs")
    same(manifest["development_freeze"], {"path": str(freeze_path.relative_to(ROOT)), **evaluation.pin(freeze_path)}, "Manifest freeze differs")
    freeze = evaluation.verify_freeze(freeze_path)
    _, questions, counts = evaluation.validate_data(freeze)
    deployment_path = ROOT / "tests/fixtures/qwen_components_development_bootstrap_v2/deployment.json"
    same(manifest["bootstrap_deployment"], {"path": str(deployment_path.relative_to(ROOT)), **evaluation.pin(deployment_path)}, "Bootstrap deployment differs")
    deployment = core.read_json(read(deployment_path, 1024 * 1024))
    imported = core.read_json(plain["imported-draft.ipynb"])
    code = [cell["source"] if isinstance(cell["source"], str) else "".join(cell["source"]) for cell in imported["cells"] if cell["cell_type"] == "code"]
    require(len(code) == 1, "Imported script cell count differs")
    same(code[0].rstrip("\n"), read(ROOT / deployment["submission"]["path"], 1024 * 1024).decode().rstrip("\n"), "Actual imported script differs from prospective launch")
    compile(code[0], "preserved-imported-script", "exec")  # Compilation only; never execute it.
    job_envelope, result_envelope = envelope(files["job.json"]), envelope(files["components-results.json"])
    job = core.validate_job(job_envelope, JOB_SHA)
    require(result_envelope["payload_sha256"] == RESULT_SHA, "Trusted numeric result digest differs")
    payload = result_envelope["payload"]
    checked = core.validate_results(job, payload, JOB_SHA)
    _runtime(payload["runtime"], checked["token_counts"])
    ledger.validate_environment_audit(payload["environment_audit"], payload["runtime"], job["execution_files"])
    preparation = core.read_json(files["preparation.json"])
    require(preparation["job_sha256"] == JOB_SHA and preparation["project_id"] == job["project_id"] and job["scope"] == "included", "Preparation job binding differs")
    same(preparation["freeze"], evaluation.pin(freeze_path), "Preparation freeze differs")
    same(preparation["truth_counts"], counts, "Preparation question denominators differ")
    same(preparation["execution_files"], job["execution_files"], "Original helper binding differs")
    same(job["questions"], [{k: q[k] for k in ("id", "query", "components")} for q in questions], "Original reviewer requests differ")
    worker_audit = envelope(files["components-environment-audit.json"])["payload"]
    same(worker_audit, payload["environment_audit"], "Saved worker audit differs from numeric result")
    checkpoint = envelope(files["components-checkpoint.json"])["payload"]
    require(checkpoint["phase"] == "complete" and checkpoint["job_sha256"] == JOB_SHA and checkpoint["profile_sha256"] == job["profile_sha256"], "Final checkpoint binding differs")
    for key in ("document_embeddings", "query_embeddings", "score_rows"):
        same(checkpoint[key], payload[key], "Final checkpoint numeric values differ")
    bootstrap = core.read_json(files["components-bootstrap-audit.json"])
    require(type(bootstrap["schema_version"]) is int and bootstrap["schema_version"] == 1 and bootstrap["status"] == "completed"
            and bootstrap["kind"] == "qwen-components-bootstrap-audit-v1" and bootstrap["job_sha256"] == JOB_SHA
            and bootstrap["profile_sha256"] == job["profile_sha256"], "Bootstrap runtime binding differs")
    same(bootstrap["execution_files"], job["execution_files"], "Bootstrap original helpers differ")
    same(bootstrap["adapter"], {"filename": "qwen_kaggle_bootstrap.py", **{k: deployment["adapter"][k] for k in ("sha256", "size_bytes")}}, "Separate bootstrap code binding differs")
    same({k: bootstrap["pip_wheel"][k] for k in deployment["installer_wheel"]}, deployment["installer_wheel"], "Fixed installer wheel differs")
    require(bootstrap["pip_wheel"]["verified"] is True and type(bootstrap["paid_inference_calls"]) is int and bootstrap["paid_inference_calls"] == 0, "Bootstrap verification or paid-call claim differs")
    require([row["stage"] for row in bootstrap["stages"]] == list(STAGES), "Six bootstrap stages differ")
    for row in bootstrap["stages"]:
        require(row["status"] == "passed" and type(row["returncode"]) is int and row["returncode"] == 0
                and type(row["elapsed_seconds"]) in (int, float) and math.isfinite(row["elapsed_seconds"]) and row["elapsed_seconds"] >= 0, "Bootstrap stage failed or elapsed time invalid")
        name = "components-bootstrap-audit.json." + row["stage"] + ".log"
        same({k: row["log"][k] for k in ("sha256", "size_bytes")}, pin(files[name]), "Stage diagnostic log binding differs")
    report_pin = pin(files["components-installer-report.json"])
    same({k: bootstrap["installer_report"][k] for k in report_pin}, report_pin, "Bootstrap installer report differs")
    require(worker_audit["installer_report_sha256"] == report_pin["sha256"] and worker_audit["setup_seconds"] == bootstrap["setup_seconds"], "Worker setup audit differs")
    report = core.read_json(files["components-installer-report.json"])
    package_versions = {row["metadata"]["name"].lower().replace("_", "-"): row["metadata"]["version"] for row in report["install"]}
    same(package_versions, core.PROFILE["packages"], "Installed package versions differ")
    require(len(report["install"]) == 4 and all(row["requested"] is True and row["download_info"]["url"].startswith("https://files.pythonhosted.org/") for row in report["install"]), "Installer report does not contain exactly four public direct packages")
    receipt = envelope(files["validation.receipt.json"])["payload"]
    require(receipt["kind"] == "qwen-components-receipt-v1", "Validation receipt kind differs")
    same(receipt["job"], job_envelope, "Receipt original job differs")
    same(receipt["results"], result_envelope, "Receipt original results differ")
    recomputed = replay(job, payload, checked)
    same(recomputed, receipt["recomputed"], "Frozen numeric/lexical replay differs from original receipt")
    per_method, metrics = {}, {}
    for label in evaluation.METHODS:
        traces = recomputed["traces"] if label == "candidate" else recomputed["comparators"][label]
        rows = [evaluation.assess(trace, q, preparation["document_bindings"][q["source_id"]]) for q, trace in zip(questions, traces, strict=True)]
        per_method[label], metrics[label] = rows, evaluation.aggregate(rows)
        same(grade["methods"][label], {"method": evaluation.METHODS[label], "metrics": metrics[label], "per_question": rows}, "Original per-question grade differs")
    pools = []
    for q, diagnostic, display in zip(questions, recomputed["diagnostics"], per_method["candidate"], strict=True):
        supported = evaluation.assess({"passages": diagnostic["target_pool_passages"]}, q, preparation["document_bindings"][q["source_id"]], pool=True)
        pools.append({"id": q["id"], "pool_support": supported, "display_support": display,
                      "selection_loss": q["answerable"] and supported["coverage"] > display["coverage"]})
    same(grade["pool_diagnostics"], pools, "Original pool/display grade differs")
    target = metrics["candidate"]; gate = evaluation.GATE
    checks = {"support_coverage": target["mean_support_coverage"] >= gate["min_mean_support_coverage"],
              "complete_positives": target["complete_positives"] >= gate["min_complete_positives"],
              "exact_anchors_scope_replay_readonly": True, "batch_time": payload["runtime"]["elapsed_seconds"]["total"] <= gate["max_batch_seconds"],
              "paid_inference_calls": payload["runtime"]["paid_inference_calls"] == 0}
    for label in gate["nonregression_comparators"]:
        checks[label + "_coverage_nonregression"] = target["mean_support_coverage"] >= metrics[label]["mean_support_coverage"]
        checks[label + "_complete_nonregression"] = target["complete_positives"] >= metrics[label]["complete_positives"]
    same(grade["checks"], checks, "First frozen acceptance checks differ")
    require(grade["status"] == ("passed" if all(checks.values()) else "failed") and grade["split"] == "development"
            and grade["job_sha256"] == JOB_SHA and grade["results_sha256"] == RESULT_SHA, "First grade status or binding differs")
    same(grade["freeze"], evaluation.pin(freeze_path), "First grade freeze differs")
    for key in ("traces", "comparators", "runtime", "environment_audit", "distinct_rerank_pairs"):
        same(grade[key], recomputed[key], "First grade replay field differs: " + key)
    summary = {"status": grade["status"], "checks": checks,
        "methods": {label: {k: metric[k] for k in ("mean_support_coverage", "complete_positives")} for label, metric in metrics.items()},
        "distinct_rerank_pairs": len(checked["pair_inputs"]), "positive_pool_selection_losses": sum(row["selection_loss"] for row in pools),
        "candidate_nulls": metrics["candidate"]["nulls"]}
    same(manifest["grade"], summary, "Manifest quality summary contradicts the preserved first grade")
    runtime = {"worker_seconds": payload["runtime"]["elapsed_seconds"]["total"], "bootstrap_setup_seconds": bootstrap["setup_seconds"],
        "bootstrap_seconds": bootstrap["elapsed_seconds"], "paid_inference_calls": payload["runtime"]["paid_inference_calls"],
        "max_input_tokens": payload["runtime"]["max_input_tokens"], "peak_vram_bytes": payload["runtime"]["peak_vram_bytes"]}
    same(manifest["runtime"], runtime, "Manifest runtime summary differs")
    require(JOB_SHA.encode() in plain["run.log"] and RESULT_SHA.encode() in plain["run.log"]
            and RESULT_SHA.encode() in files["components-bootstrap-audit.json.worker.log"], "Printed trusted digest evidence missing")
    return {"status": "verified", "quality_status": grade["status"], "candidate_mean_support_coverage": target["mean_support_coverage"],
            "complete_positives": target["complete_positives"], "distinct_rerank_pairs": len(checked["pair_inputs"]),
            "worker_seconds": runtime["worker_seconds"], "bootstrap_seconds": runtime["bootstrap_seconds"], "paid_inference_calls": runtime["paid_inference_calls"],
            "saved_version": saved["id"], "archive_members": len(files), "database_opened": False,
            "limitations": "Remote execution and original ledger-readonly provenance are preserved claims; no database, GPU or inference is used for replay."}


if __name__ == "__main__":
    try:
        print(json.dumps(verify(), sort_keys=True, allow_nan=False))
    except (ValueError, OSError, KeyError, TypeError, lzma.LZMAError, tarfile.TarError) as error:
        print("component-first-run-verify: " + str(error), file=sys.stderr)
        raise SystemExit(1)
