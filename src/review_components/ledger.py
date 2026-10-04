"""Read-only local ledger adapter for the new component retrieval profile."""

from copy import deepcopy
import hashlib
import math
import os
from pathlib import Path
import re

from ..review.cloud_retrieval import _capture, _check_current, _representations
from ..review.qwen_batch import _artifact_paths, _runtime, _write_new
from ..review.retrieval import _snapshot_hash
from . import core


PROFILE = core.PROFILE


class _Limits:
    max_document_bytes = PROFILE["max_document_bytes"]
    max_representations = PROFILE["max_representations"]


def execution_paths():
    root = Path(__file__).resolve().parents[2]
    return {"component_core.py": Path(__file__).with_name("core.py"),
            "qwen_kaggle_environment.py": root / "tools/qwen_kaggle_environment.py",
            "qwen_components_kaggle_runner.py": root / "tools/qwen_components_kaggle_runner.py"}


def _execution_files():
    result = {}
    for name, path in execution_paths().items():
        data = path.read_bytes()
        result[name] = {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}
    core.validate_execution_files(result)
    return result


def _build_job(store, project_id, questions, scope):
    core.require(not store._connection.in_transaction, "Component export/import cannot run inside an existing ledger transaction")
    core.require(scope in {"included", "all_attached"}, "Component scope must be included or all_attached")
    questions = core.normalize_questions(questions)
    manifest, captured = _capture(store, project_id, scope)
    candidates = [{"passage": row["passage"], "tie": list(row["tie"])} for row in captured]
    reps = _representations(captured, _Limits())
    core.require(bool(reps), "Component job has no eligible source passages")
    job = {"schema_version": 1, "kind": "qwen-components-job-v1", "project_id": project_id, "scope": scope,
           "top_k": 5, "candidate_k": 20, "profile": deepcopy(PROFILE), "profile_sha256": core.digest(PROFILE),
           "source_manifest": manifest, "source_snapshot_sha256": _snapshot_hash(manifest),
           "candidates": candidates, "representations": reps, "questions": questions,
           "query_rows": core.query_rows(candidates, questions), "execution_files": _execution_files()}
    job = core.read_json(core.canonical(job))
    core.validate_job({"payload": job, "payload_sha256": core.digest(job)}, core.digest(job))
    return job, manifest, captured


def export_job(store, project_id, queries, *, output_path, scope="included"):
    _artifact_paths(store, output_path)
    core.require(not os.path.lexists(output_path), "Component jobs are immutable; choose a new output path")
    job, manifest, candidates = _build_job(store, project_id, queries, scope)
    _check_current(store, project_id, scope, manifest, candidates)
    _write_new(output_path, job)
    return {"payload": job, "payload_sha256": core.digest(job)}


def _trace(job, question, method, selection, scoremaps, component_ids, *, pool_size=None):
    reasons = {row["block_index"]: row["reasons"] for row in selection["reasons"]}
    passages, groups = [], []
    group_positions = {}
    for rank, index in enumerate(selection["block_indices"], 1):
        own = deepcopy(job["candidates"][index]["passage"])
        locator = own["locator"]
        passages.append({"rank": rank, "score": scoremaps[0][index], **own,
                         "candidate_kind": "title_or_navigation" if locator.get("tag") in {"article-title", "title", "label"} else "source_block",
                         "query_scores": {"whole": scoremaps[0][index], "components": [{"id": identifier, "score": scores[index]} for identifier, scores in zip(component_ids, scoremaps[1:], strict=True)]},
                         "selection_reasons": reasons[index]})
        key = (own["record_id"], own["document_id"], own["document_version"])
        if key not in group_positions:
            group_positions[key] = len(groups)
            groups.append({"record_id": key[0], "document_id": key[1], "document_version": key[2], "passage_ranks": []})
        groups[group_positions[key]]["passage_ranks"].append(rank)
    component_policy = method in {"qwen_components_hybrid", "bm25_context_components"}
    return {"schema_version": 1, "status": "candidate_passages", "project_id": job["project_id"],
            "query_id": question["id"], "query": question["query"], "components": deepcopy(question["components"]),
            "method": method, "method_version": "lit-rev-engine.project-retrieval.qwen-components.v1." + method,
            "parameters": {"profile_sha256": job["profile_sha256"], "candidate_k": 20, "display_budget": 5,
                           "pool_allocation": PROFILE["pool_allocation"] if component_policy else "whole-query-top20",
                           "selection": PROFILE["selection"] if component_policy else "whole-query-score-top5"},
            "scope": job["scope"], "top_k": 5, "source_manifest": deepcopy(job["source_manifest"]),
            "source_snapshot_sha256": job["source_snapshot_sha256"], "indexed_passages": len(job["candidates"]),
            "matched_passages": len(scoremaps[0]), "candidate_pool_size": len(scoremaps[0]) if pool_size is None else pool_size,
            "profile": deepcopy(PROFILE), "answerability": "not_assessed", "support_completeness": "not_assessed",
            "verification": "human_review_required", "display_order": "component-reservations-then-whole-query-fill" if component_policy else "whole-query-score-descending",
            "missing_component_selections": list(selection["missing_components"]), "passages": passages,
            "source_groups": groups}


def _lexical(job):
    whole, components, diagnostics = [], [], []
    for question in job["questions"]:
        encoded = [question["query"], *[part["query"] for part in question["components"]]]
        scored = [core.lexical_scores(job["candidates"], text) for text in encoded]
        orders = [[row["block_index"] for row in scores[:20]] for scores in scored]
        maps = [{row["block_index"]: row["score"] for row in scores} for scores in scored]
        ids = [part["id"] for part in question["components"]]
        whole_selection = core.select(job["candidates"], orders[0], [maps[0]], [])
        whole.append(_trace(job, question, "bm25_context_blocks", whole_selection, [maps[0]], [], pool_size=len(orders[0])))
        allocation = core.allocate(job["candidates"], orders, ids)
        pool = allocation["block_indices"]
        filled_maps = [{index: scores.get(index, 0.0) for index in pool} for scores in maps]
        selection = core.select(job["candidates"], pool, filled_maps, ids)
        components.append(_trace(job, question, "bm25_context_components", selection, filled_maps, ids))
        diagnostics.append({"question_id": question["id"], "whole_pool_block_indices": orders[0],
                            "component_pool_block_indices": pool, "component_pool_reasons": allocation["reasons"]})
    return {"whole_lexical": whole, "component_lexical": components, "diagnostics": diagnostics}


def lexical_comparators(store, project_id, questions, *, scope="included"):
    job, manifest, candidates = _build_job(store, project_id, questions, scope)
    result = _lexical(job)
    _check_current(store, project_id, scope, manifest, candidates)
    return result


def validate_environment_audit(audit, runtime, files):
    fields = {"schema_version", "recipe", "overlay_path", "base_python", "installer_report_sha256", "execution_files",
              "packages", "torch", "python_version", "setup_seconds", "requirements_passed"}
    core.require(isinstance(audit, dict) and set(audit) == fields and type(audit["schema_version"]) is int and audit["schema_version"] == 1
                 and audit["recipe"] == PROFILE["environment_recipe"] and audit["requirements_passed"] is True
                 and core.canonical(audit["execution_files"]) == core.canonical(files), "Component environment audit binding mismatch")
    def absolute_path(value):
        core.require(isinstance(value, str) and value and Path(value).is_absolute() and ".." not in Path(value).parts,
                     "Component environment paths must be canonical and absolute")
        return Path(value).resolve()
    overlay = absolute_path(audit["overlay_path"])
    absolute_path(audit["base_python"])
    core.require(isinstance(audit["installer_report_sha256"], str) and len(audit["installer_report_sha256"]) == 64
                 and all(char in "0123456789abcdef" for char in audit["installer_report_sha256"]), "Missing isolated installer report digest")
    core.require(type(audit["setup_seconds"]) in (int, float) and math.isfinite(audit["setup_seconds"]) and audit["setup_seconds"] >= 0, "Invalid setup elapsed time")
    packages = audit["packages"]
    core.require(isinstance(packages, dict) and set(packages) == set(PROFILE["packages"]), "Incomplete component environment package audit")
    for name, expected in PROFILE["packages"].items():
        package = packages[name]
        core.require(isinstance(package, dict) and set(package) == {"version", "location", "requirements"}
                     and package["version"] == expected and isinstance(package["location"], str)
                     and absolute_path(package["location"]).is_relative_to(overlay), "Pinned retrieval package must originate in the overlay")
        core.require(isinstance(package["requirements"], list), "Missing resolved dependency audit")
        for dependency in package["requirements"]:
            core.require(isinstance(dependency, dict) and set(dependency) == {"name", "requirement", "version", "location"}
                         and all(isinstance(value, str) and value for value in dependency.values()), "Invalid resolved dependency row")
            absolute_path(dependency["location"])
            expected_name = re.match(r"[A-Za-z0-9_.-]+", dependency["requirement"])
            canonical_name = lambda value: re.sub(r"[-_.]+", "-", value).lower()
            core.require(expected_name is not None and canonical_name(dependency["name"]) == canonical_name(expected_name.group()),
                         "Resolved dependency name contradicts its recorded requirement")
            dependency_name = canonical_name(dependency["name"])
            if dependency_name in PROFILE["packages"]:
                core.require(dependency["version"] == PROFILE["packages"][dependency_name]
                             and absolute_path(dependency["location"]).is_relative_to(overlay),
                             "Resolved retrieval dependency contradicts its pinned overlay package")
        core.require(sorted(row["requirement"] for row in package["requirements"]) == sorted(core.ACTIVE_REQUIREMENTS[name]),
                     "Resolved active dependency requirements are incomplete or changed")
    torch = audit["torch"]
    torch_fields = {"version", "location", "cuda_version", "device", "gpu_name", "device_count", "total_memory_bytes", "smoke_passed"}
    core.require(isinstance(torch, dict) and set(torch) == torch_fields and torch["smoke_passed"] is True
                 and isinstance(torch["location"], str)
                 and not absolute_path(torch["location"]).is_relative_to(overlay), "CUDA Torch must remain outside the retrieval overlay")
    for name, value in {"version": runtime["packages"]["torch"], "cuda_version": runtime["cuda_version"], "device": runtime["device"],
                        "gpu_name": runtime["gpu_name"], "device_count": runtime["device_count"], "total_memory_bytes": runtime["total_memory_bytes"]}.items():
        core.require(core.canonical(torch[name]) == core.canonical(value), "Environment CUDA audit contradicts runtime")
    core.require(audit["python_version"] == runtime["packages"]["python"], "Environment Python audit contradicts runtime")


def import_results(store, project_id, *, job_path, job_sha256, results_path, results_sha256=None, receipt_path=None):
    core.require(not store._connection.in_transaction, "Component import cannot run inside an existing ledger transaction")
    _artifact_paths(store, job_path, results_path, receipt_path)
    core.require(receipt_path is None or not os.path.lexists(receipt_path), "Component receipts are immutable; choose a new path")
    job_envelope, results_envelope = core.read_artifact(job_path), core.read_artifact(results_path)
    job = core.validate_job(job_envelope, job_sha256)
    core.require(job["project_id"] == project_id, "Component job belongs to another project")
    core.require(results_sha256 is None or results_envelope["payload_sha256"] == results_sha256, "Component returned results differ from trusted checksum")
    current, manifest, candidates = _build_job(store, project_id, job["questions"], job["scope"])
    core.require(core.canonical(current) == core.canonical(job), "Component source/eligibility/helper snapshot is stale or inconsistent")
    payload = results_envelope["payload"]
    checked = core.validate_results(job, payload, job_sha256)
    _runtime(payload["runtime"], checked["token_counts"])
    validate_environment_audit(payload["environment_audit"], payload["runtime"], job["execution_files"])
    target, whole, diagnostics = [], [], []
    for question, plan in zip(job["questions"], checked["plans"], strict=True):
        ids = [row["id"] for row in question["components"]]
        maps = [core.aggregate(job, plan, checked["scoremaps"], identifier) for identifier in [None, *ids]]
        selection = core.select(job["candidates"], plan["target_block_indices"], maps, ids)
        target.append(_trace(job, question, "qwen_components_hybrid", selection, maps, ids))
        whole_map = core.aggregate(job, plan, checked["scoremaps"], None, whole_reference=True)
        whole_selection = core.select(job["candidates"], plan["whole_block_indices"], [whole_map], [])
        whole.append(_trace(job, question, "qwen_kaggle_hybrid", whole_selection, [whole_map], []))
        def pool_passages(indices, scores):
            return [{"rank": rank, "score": scores[index], **deepcopy(job["candidates"][index]["passage"])} for rank, index in enumerate(indices, 1)]
        diagnostics.append({"question_id": question["id"], "not_for_display": True, "pool_budget": 20,
                            "target_pool_passages": pool_passages(plan["target_block_indices"], maps[0]),
                            "whole_pool_passages": pool_passages(plan["whole_block_indices"], whole_map),
                            "allocation": deepcopy(plan), "target_selected_block_indices": selection["block_indices"]})
    lexical = _lexical(job)
    for trace in [*target, *whole, *lexical["whole_lexical"], *lexical["component_lexical"]]:
        trace.update({"execution": "offline_import", "job_sha256": job_sha256, "results_sha256": results_envelope["payload_sha256"]})
    result = {"schema_version": 1, "status": "candidate_passages", "job_sha256": job_sha256,
              "results_sha256": results_envelope["payload_sha256"], "profile": deepcopy(PROFILE),
              "runtime": deepcopy(payload["runtime"]), "environment_audit": deepcopy(payload["environment_audit"]),
              "distinct_rerank_pairs": len(checked["pair_inputs"]), "traces": target,
              "comparators": {"whole_qwen": whole, "whole_lexical": lexical["whole_lexical"], "component_lexical": lexical["component_lexical"]},
              "diagnostics": diagnostics, "lexical_diagnostics": lexical["diagnostics"]}
    _check_current(store, project_id, job["scope"], manifest, candidates)
    if receipt_path is not None:
        receipt = {"schema_version": 1, "kind": "qwen-components-receipt-v1", "job": job_envelope,
                   "results": results_envelope, "recomputed": result}
        _write_new(receipt_path, receipt)
        result["receipt_sha256"] = core.digest(receipt)
    return result
