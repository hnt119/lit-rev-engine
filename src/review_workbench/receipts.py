"""Recompute four saved retrieval traces, then build a source-bound human packet."""

from copy import deepcopy

from ..review_components import core
from ..review_components.ledger import _lexical, _trace, validate_environment_audit
from ..review.qwen_batch import _runtime
from .contracts import (MAX_RECEIPT_BYTES, canonical, digest, is_digest,
                        read_bounded, read_json, require, sha256)

METHODS = ("qwen_components_hybrid", "qwen_kaggle_hybrid", "bm25_context_blocks", "bm25_context_components")
PASSAGE_FIELDS = {"project_id", "record_id", "document_id", "document_version", "source_sha256", "blocks_sha256",
                  "parser_id", "anchor", "locator", "full_text_state", "study_link_state", "study_ids", "scoring_context"}


def _envelope(value):
    require(isinstance(value, dict) and set(value) == {"payload", "payload_sha256"}
            and is_digest(value["payload_sha256"]) and value["payload_sha256"] == digest(value["payload"]),
            "Receipt envelope checksum mismatch")
    return value["payload"]


def _sources(job):
    """Check exact full canonical blocks against each retained document digest."""
    manifests, grouped = {}, {}
    for row in job["source_manifest"]:
        require(isinstance(row, dict), "Invalid source manifest")
        key = (row.get("record_id"), row.get("document_id"), row.get("version"))
        require(all(isinstance(part, str) and part for part in key[:2]) and type(key[2]) is int and key[2] > 0
                and key not in manifests, "Duplicate or invalid source version")
        require(all(is_digest(row.get(name)) for name in ("source_sha256", "blocks_sha256")), "Invalid source digest")
        manifests[key], grouped[key] = row, []
    seen = set()
    for candidate in job["candidates"]:
        passage = candidate["passage"]
        require(set(passage) == PASSAGE_FIELDS, "Source passage schema mismatch")
        key = (passage["record_id"], passage["document_id"], passage["document_version"])
        require(key in manifests, "Passage belongs to an unknown source version")
        manifest = manifests[key]
        require(all(passage[name] == manifest[name] for name in ("source_sha256", "blocks_sha256", "parser_id",
                    "full_text_state", "study_link_state", "study_ids")), "Passage source binding differs from manifest")
        require(isinstance(passage["locator"], dict), "Invalid source locator")
        anchor = passage["anchor"]
        unique = (*key, anchor["block_id"])
        require(isinstance(anchor["block_id"], str) and anchor["block_id"] and unique not in seen,
                "Duplicate or invalid source block")
        seen.add(unique)
        require(type(candidate["tie"][1]) is int and candidate["tie"][1] > 0, "Invalid canonical source ordinal")
        grouped[key].append((candidate["tie"][1], passage))
    output = []
    for key, manifest in manifests.items():
        rows = sorted(grouped[key], key=lambda item: item[0])
        require(rows and len({ordinal for ordinal, _ in rows}) == len(rows), "Missing or duplicate retained canonical blocks")
        blocks = [{"id": own["anchor"]["block_id"], "ordinal": ordinal, "text": own["anchor"]["quote"],
                   "locator": own["locator"]} for ordinal, own in rows]
        require(digest(blocks) == manifest["blocks_sha256"], "Retained full canonical source blocks do not match their digest")
        by_block = {block["id"]: block for block in blocks}
        for _, passage in rows:
            require(isinstance(passage["scoring_context"], list), "Invalid scoring context")
            for context in passage["scoring_context"]:
                require(isinstance(context, dict) and isinstance(context.get("anchor"), dict), "Invalid context anchor")
                anchor = context["anchor"]
                own = by_block.get(anchor.get("block_id"))
                require(own is not None and type(anchor.get("start")) is int and type(anchor.get("end")) is int
                        and 0 <= anchor["start"] < anchor["end"] <= len(own["text"])
                        and own["text"][anchor["start"]:anchor["end"]] == anchor.get("quote"),
                        "Scoring context is not an exact retained source span")
        output.append({"id": digest({"record_id": key[0], "document_id": key[1], "version": key[2],
                                      "source_sha256": manifest["source_sha256"]}),
                       "record_id": key[0], "document_id": key[1], "document_version": key[2],
                       "title": manifest.get("record_title", ""), "source_sha256": manifest["source_sha256"],
                       "blocks_sha256": manifest["blocks_sha256"], "source_url": manifest.get("source_url"),
                       "blocks": blocks})
    return output


def _recompute(job, results, job_sha, results_sha):
    checked = core.validate_results(job, results, job_sha)
    _runtime(results["runtime"], checked["token_counts"])
    validate_environment_audit(results["environment_audit"], results["runtime"], job["execution_files"])
    target, whole, diagnostics = [], [], []
    for question, plan in zip(job["questions"], checked["plans"], strict=True):
        ids = [part["id"] for part in question["components"]]
        maps = [core.aggregate(job, plan, checked["scoremaps"], identifier) for identifier in [None, *ids]]
        selection = core.select(job["candidates"], plan["target_block_indices"], maps, ids)
        target.append(_trace(job, question, METHODS[0], selection, maps, ids))
        whole_map = core.aggregate(job, plan, checked["scoremaps"], None, whole_reference=True)
        whole_selection = core.select(job["candidates"], plan["whole_block_indices"], [whole_map], [])
        whole.append(_trace(job, question, METHODS[1], whole_selection, [whole_map], []))
        def pool(indices, scores):
            return [{"rank": rank, "score": scores[index], **deepcopy(job["candidates"][index]["passage"])}
                    for rank, index in enumerate(indices, 1)]
        diagnostics.append({"question_id": question["id"], "not_for_display": True, "pool_budget": 20,
                            "target_pool_passages": pool(plan["target_block_indices"], maps[0]),
                            "whole_pool_passages": pool(plan["whole_block_indices"], whole_map),
                            "allocation": deepcopy(plan), "target_selected_block_indices": selection["block_indices"]})
    lexical = _lexical(job)
    for trace in [*target, *whole, *lexical["whole_lexical"], *lexical["component_lexical"]]:
        trace.update({"execution": "offline_import", "job_sha256": job_sha, "results_sha256": results_sha})
    return {"schema_version": 1, "status": "candidate_passages", "job_sha256": job_sha,
            "results_sha256": results_sha, "profile": deepcopy(core.PROFILE),
            "runtime": deepcopy(results["runtime"]), "environment_audit": deepcopy(results["environment_audit"]),
            "distinct_rerank_pairs": len(checked["pair_inputs"]), "traces": target,
            "comparators": {"whole_qwen": whole, "whole_lexical": lexical["whole_lexical"],
                            "component_lexical": lexical["component_lexical"]},
            "diagnostics": diagnostics, "lexical_diagnostics": lexical["diagnostics"]}


def _load_packet(path, receipt_sha256):
    """Trust is an external whole-file digest, never a checksum supplied by that file."""
    require(is_digest(receipt_sha256), "Supply the trusted whole-file --receipt-sha256")
    data = read_bounded(path, MAX_RECEIPT_BYTES)
    require(sha256(data) == receipt_sha256, "Receipt differs from trusted whole-file checksum")
    envelope = read_json(data)
    receipt = _envelope(envelope)
    require(isinstance(receipt, dict) and set(receipt) == {"schema_version", "kind", "job", "results", "recomputed"}
            and type(receipt["schema_version"]) is int and receipt["schema_version"] == 1
            and receipt["kind"] == "qwen-components-receipt-v1", "Unsupported saved receipt schema")
    job_payload, results = _envelope(receipt["job"]), _envelope(receipt["results"])
    job_sha, results_sha = receipt["job"]["payload_sha256"], receipt["results"]["payload_sha256"]
    job = core.validate_job(receipt["job"], job_sha)
    sources = _sources(job)
    computed = _recompute(job, results, job_sha, results_sha)
    require(canonical(computed) == canonical(receipt["recomputed"]), "Saved recomputed receipt contradicts frozen trace reconstruction")
    binding = {"receipt_file_sha256": receipt_sha256, "receipt_payload_sha256": envelope["payload_sha256"],
               "job_sha256": job_sha, "results_sha256": results_sha, "profile_sha256": job["profile_sha256"],
               "source_snapshot_sha256": job["source_snapshot_sha256"], "project_id": job["project_id"]}
    packet_id = digest({"kind": "review-workbench-packet-v1", "binding": binding})
    questions = [{"id": row["id"], "text": row["query"],
                  "components": [{"id": part["id"], "text": part["query"]} for part in row["components"]],
                  "question_sha256": digest(row)} for row in job["questions"]]
    order = sorted(METHODS, key=lambda method: digest({"packet_id": packet_id, "method": method}))
    labels = dict(zip(order, "ABCD", strict=True))
    titles = {(source["document_id"], source["document_version"]): source["title"] for source in sources}
    bundles = []
    traces = [*computed["traces"], *[trace for rows in computed["comparators"].values() for trace in rows]]
    for question in questions:
        own_traces = [row for row in traces if row["query_id"] == question["id"]]
        require(len(own_traces) == 4 and {row["method"] for row in own_traces} == set(METHODS), "Missing method trace")
        for trace in sorted(own_traces, key=lambda row: digest({"packet_id": packet_id, "question_id": question["id"], "method": row["method"]})):
            trace_sha = digest(trace)
            passages = []
            for passage in trace["passages"]:
                own = {name: deepcopy(passage[name]) for name in ("rank", "anchor", "locator", "record_id", "document_id",
                           "document_version", "source_sha256", "blocks_sha256", "candidate_kind", "score", "query_scores", "selection_reasons")}
                own["title"] = titles[(passage["document_id"], passage["document_version"])]
                own["id"] = digest({"record_id": own["record_id"], "document_id": own["document_id"],
                                    "document_version": own["document_version"], "source_sha256": own["source_sha256"],
                                    "blocks_sha256": own["blocks_sha256"], "anchor": own["anchor"], "locator": own["locator"]})
                passages.append(own)
            bundles.append({"id": digest({"packet_id": packet_id, "question_sha256": question["question_sha256"], "trace_sha256": trace_sha}),
                            "question_id": question["id"], "method_key": trace["method"], "label": labels[trace["method"]],
                            "trace_sha256": trace_sha, "passages": passages})
    return {"schema_version": 1, "kind": "review-workbench-packet-v1", "packet_id": packet_id, "binding": binding,
            "questions": questions, "bundles": bundles, "sources": sources, "review_basis": "single_human",
            "source_answerability": "not_assessed", "current_ledger_state": "not_checked", "verification": "NOT_RUN",
            "shared_batch_runtime": deepcopy(computed["runtime"]), "distinct_rerank_pairs": computed["distinct_rerank_pairs"],
            "limitations": ["Saved exposed regression material is not fresh confirmation.",
                            "The retained source view contains canonical text blocks, not original source bytes.",
                            "Bundle judgments do not establish source answerability or independent verification."]}


def load_packet(path, receipt_sha256):
    try:
        return _load_packet(path, receipt_sha256)
    except (KeyError, TypeError, IndexError, OverflowError, RecursionError):
        raise ValueError("Malformed saved receipt fields or bindings") from None


def public_packet(packet, reveal=False):
    """Only an explicit reveal exposes method keys, model metadata, scores or reasons."""
    output = deepcopy(packet)
    output.pop("shared_batch_runtime", None)
    if not reveal:
        for bundle in output["bundles"]:
            bundle.pop("method_key", None)
            for passage in bundle["passages"]:
                for name in ("score", "query_scores", "selection_reasons"):
                    passage.pop(name, None)
    output["display_mode"] = "revealed" if reveal else "blinded"
    return output
