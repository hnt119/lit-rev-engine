"""Whole-block candidate with unchanged metrics and receipt-gated fresh evaluation."""

from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.evaluate_medical_retrieval import aggregate_metrics, assess_question, digest_json
from tools.evaluate_medical_retrieval_v2 import validate_trace as validate_context_trace

FREEZE_FILE = "tests/fixtures/medical_retrieval_v3/freeze.json"
DEVELOPMENT_FILE = "docs/medical-retrieval-development-v3.json"


def read_json(path): return json.loads(Path(path).read_text())


def pin(path):
    content = Path(path).read_bytes()
    return {"sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content)}


def verify_pins(pins):
    if not isinstance(pins, dict) or not pins:
        raise ValueError("An explicit nonempty file-pin mapping is required")
    for name, expected in pins.items():
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or (ROOT / path).resolve().is_relative_to(ROOT.resolve()) is False:
            raise ValueError("Frozen input must be a repository-relative contained path")
        if pin(ROOT / path) != expected:
            raise ValueError("Frozen input changed: " + name)


def verify_frozen_inputs():
    freeze = read_json(ROOT / FREEZE_FILE)
    if freeze.get("schema_version") != 1 or freeze.get("status") != "frozen_before_v3_ranking" or type(freeze.get("ranking_runs_before_freeze")) is not int or freeze["ranking_runs_before_freeze"] != 0:
        raise ValueError("V3 medical ranking requires the coordinator's prospective freeze")
    if freeze.get("methods") != ["bm25_context", "bm25_context_blocks"]:
        raise ValueError("V3 evaluation methods differ from the frozen reference/candidate")
    for section in ("development", "held_out"):
        verify_pins(freeze[section]["frozen_files"])
    verify_pins(freeze["implementation_files"])
    checkers = {}
    for section in ("development", "held_out"):
        checker = ROOT / freeze[section]["fixture_dir"] / "verify.py"
        result = subprocess.run([sys.executable, str(checker)], capture_output=True, text=True, check=True, timeout=30)
        checkers[section] = result.stdout.strip()
    return freeze, checkers


def validate_trace(trace, store, project_id, freeze):
    """Retain accepted context checks and independently require complete own blocks."""
    method = trace["method"]
    if method not in freeze["methods"] or trace["parameters"] != freeze["method_parameters"][method]:
        raise ValueError("Trace method parameters differ from the prospective freeze")
    projection = deepcopy(trace)
    candidate = method == "bm25_context_blocks"
    if candidate:
        if trace["method_version"] != "lit-rev-engine.project-retrieval.v3.bm25_context_blocks":
            raise ValueError("Whole-block method version differs from the frozen candidate")
        projection["method"] = "bm25_context"
        projection["method_version"] = "lit-rev-engine.project-retrieval.v2.bm25_context"
        projection["parameters"] = freeze["method_parameters"]["bm25_context"]
    context_freeze = {"methods": ["bm25_context"], "method_parameters": {"bm25_context": freeze["method_parameters"]["bm25_context"]}}
    counts = validate_context_trace(projection, store, project_id, context_freeze)
    if candidate:
        sources = {row["document_id"]: {block["id"]: block for block in store.get_source_blocks(project_id, row["document_id"])} for row in trace["source_manifest"]}
        expected_index = sum(bool(block["text"].strip()) for blocks in sources.values() for block in blocks.values())
        if trace["indexed_passages"] != expected_index:
            raise ValueError("Whole-block index does not contain exactly the selected nonblank blocks")
        seen = set()
        for passage in trace["passages"]:
            anchor = passage["anchor"]
            identity = passage["document_id"], anchor["block_id"]
            block = sources[identity[0]][identity[1]]
            if identity in seen or not block["text"].strip() or anchor != {"block_id": block["id"], "start": 0, "end": len(block["text"]), "quote": block["text"]}:
                raise ValueError("Whole-block own anchor is duplicated, blank, clipped or changed")
            seen.add(identity)
    return counts


def development_eligibility(result, freeze):
    gate, metrics = freeze["development_selection"], result["metrics"]
    checks = {
        "candidate_method": result["method"] == gate["candidate"],
        "answerable_denominator": metrics["answerable_questions"] == freeze["development"]["answerable"],
        "complete_support": metrics["complete_questions_at_5"] >= gate["min_complete_questions"],
        "mean_support_coverage": metrics["mean_support_coverage_at_5"] >= gate["min_mean_support_coverage_at_5"],
        "no_answer_context_preserved": metrics["no_answer_context_quotes_covered_at_5"] >= gate["min_no_answer_context_quotes_at_5"],
        "own_anchor_validity": result["own_anchor_validity"] == gate["exact_anchor_validity"],
        "scoring_context_anchor_validity": result["scoring_context_anchor_validity"] == gate["exact_anchor_validity"],
        "scope_isolation": result["project_active_document_scope_isolation"] == 1.0,
    }
    return {"checks": checks, "eligible": all(checks.values()), "coordinator_authorization_required_before_held_out": True}


def validate_selection(path, freeze):
    if path is None: raise ValueError("Fresh held-out ranking requires a coordinator selection receipt")
    receipt = read_json(path)
    if receipt.get("schema_version") != 1 or receipt.get("status") != "coordinator_selected_before_held_out_ranking" or receipt.get("held_out_ranked_at_selection") is not False:
        raise ValueError("Selected receipt must be fixed before held-out ranking")
    if receipt.get("freeze_file") != FREEZE_FILE or receipt.get("development_result_file") != DEVELOPMENT_FILE:
        raise ValueError("Selection receipt declares unexpected pinned inputs")
    for file_key, hash_key in (("freeze_file", "freeze_sha256"), ("development_result_file", "development_result_sha256")):
        if pin(ROOT / receipt[file_key])["sha256"] != receipt.get(hash_key):
            raise ValueError("Selection receipt input hash mismatch: " + file_key)
    candidate = freeze["development_selection"]["candidate"]
    if receipt.get("selected_method") != candidate or receipt.get("method_parameters") != freeze["method_parameters"][candidate] or receipt.get("implementation_files") != freeze["implementation_files"]:
        raise ValueError("Selection receipt method/code/parameters differ from the prospective freeze")
    if receipt.get("selection_rule") != freeze["development_selection"]:
        raise ValueError("Selection receipt rule differs from the prospective freeze")
    verify_pins(receipt["implementation_files"])
    development = read_json(ROOT / DEVELOPMENT_FILE)
    if development.get("split") != "development" or development.get("held_out_ranked") is not False or development.get("freeze_sha256") != receipt["freeze_sha256"]:
        raise ValueError("Selection requires a development-only result bound to this freeze")
    results = [result for result in development["method_results"] if result["method"] == candidate]
    if len(results) != 1 or aggregate_metrics(results[0]["per_question"]) != results[0]["metrics"] or not development_eligibility(results[0], freeze)["eligible"]:
        raise ValueError("Candidate does not meet the frozen development gate")
    return receipt


def evaluate(split="development", selection_path=None):
    if split not in ("development", "held-out"): raise ValueError("Unknown evaluation split")
    freeze, checkers = verify_frozen_inputs()
    selection = validate_selection(selection_path, freeze) if split == "held-out" else None
    from src.review.models import BibliographicRecord, SearchRunSpec
    from src.review.store import ReviewStore
    section = "development" if split == "development" else "held_out"
    declaration = freeze[section]
    directory = ROOT / declaration["fixture_dir"]
    manifest = read_json(directory / "manifest.json")
    questions = read_json(directory / declaration["file"])["questions"]
    passages = {row["id"]: row for row in read_json(directory / "passages.json")["passages"]}
    if len(questions) != declaration["questions"] or sum(bool(row["sufficient_support_sets"]) for row in questions) != declaration["answerable"]:
        raise ValueError("Frozen question/answerable counts differ from declared denominators")
    methods = freeze["methods"] if split == "development" else [selection["selected_method"]]
    results = []
    def denied(*args, **kwargs): raise AssertionError("V3 evaluator attempted network")
    original_connection = socket.create_connection
    socket.create_connection = denied
    try:
        with tempfile.TemporaryDirectory(prefix="medical-retrieval-v3-" + split + "-") as temporary:
            database = Path(temporary) / "reviews.sqlite3"
            with ReviewStore(database) as store:
                project_id = store.create_project("Pinned document-disjoint source pilot", "systematic", "Which exact source passages support predeclared questions?")["id"]
                store.import_records(project_id, SearchRunSpec("Pinned attributed publisher bibliography"), [BibliographicRecord(title=source["title"], doi=source["doi"]) for source in manifest["sources"]])
                bindings = {}
                for source, record in zip(manifest["sources"], store.list_records(project_id), strict=True):
                    store.record_decision(project_id, record["id"], "title_abstract", "include", "Pilot curator")
                    store.set_full_text_status(project_id, record["id"], "retrieved", "Pilot curator")
                    store.record_decision(project_id, record["id"], "full_text", "include", "Pilot curator")
                    content = (directory / source["file"]).read_bytes()
                    document = store.attach_document(project_id, record["id"], content, "jats_xml", "Pilot curator", "Pinned licensed source",
                                                     filename=Path(source["file"]).name, source_url=source["publisher_article_url"])
                    bindings[source["alias"]] = {"document_id": document["id"], "record_id": record["id"], "source_sha256": document["source_sha256"]}
                before = hashlib.sha256("\n".join(store._connection.iterdump()).encode()).hexdigest()
                for method in methods:
                    rows, traces, own_count, context_count = [], [], 0, 0
                    for question in questions:
                        trace = store.search_sources(project_id, question["question"], method=method)
                        counts = validate_trace(trace, store, project_id, freeze)
                        own_count += counts["own_anchors"]; context_count += counts["scoring_context_anchors"]
                        if store.search_sources(project_id, question["question"], method=method) != trace:
                            raise ValueError("Same-ledger trace changed during repeated retrieval")
                        with ReviewStore(database) as reopened:
                            if reopened.search_sources(project_id, question["question"], method=method) != trace:
                                raise ValueError("Trace changed on same-ledger reopening")
                        row = assess_question(question, trace, passages, bindings)
                        row["scoring_contexts_at_5"] = [{"rank": candidate["rank"], "document_id": candidate["document_id"], "context": deepcopy(candidate.get("scoring_context", []))} for candidate in trace["passages"]]
                        rows.append(row); traces.append({"question_id": question["id"], "trace": trace})
                    if hashlib.sha256("\n".join(store._connection.iterdump()).encode()).hexdigest() != before:
                        raise ValueError("Retrieval wrote ledger rows")
                    results.append({"method": method, "metrics": aggregate_metrics(rows), "own_anchors_checked": own_count,
                                    "scoring_context_anchors_checked": context_count, "own_anchor_validity": 1.0, "scoring_context_anchor_validity": 1.0,
                                    "project_active_document_scope_isolation": 1.0, "read_only": True, "same_ledger_repeat_and_reopen_deterministic": True,
                                    "per_question": rows, "operational_traces": traces})
    finally:
        socket.create_connection = original_connection
    result = {"schema_version": 1, "evaluation_version": "medical-retrieval-v3", "split": split, "held_out_ranked": split == "held-out",
              "freeze_sha256": pin(ROOT / FREEZE_FILE)["sha256"], "source_gold_checkers": checkers,
              "implementation_files": deepcopy(freeze["implementation_files"]), "frozen_parameters": deepcopy(freeze["method_parameters"]),
              "bindings": bindings, "method_results": results,
              "operational_trace_identity_note": "Operational UUIDs retained; traces repeat within the same reopened ledger, not across independently created ledgers.",
              "support_semantics": "Only own anchors cover required gold quotations; scoring_context is ranking provenance and never finding support.",
              "limits": ["Small agent-authored software pilot, not clinical validation", "New held-out article DOIs are disjoint from original development and both previous pilots", "Context creates no automatic evidence or verification", "Frozen v1 and v2 results remain unchanged"]}
    if split == "development":
        candidate = next(item for item in results if item["method"] == freeze["development_selection"]["candidate"])
        result["development_candidate_eligibility"] = development_eligibility(candidate, freeze)
        result["held_out_authorized"] = False
    else:
        gate, selected = freeze["held_out_acceptance"], results[0]
        checks = {"answerable_denominator": selected["metrics"]["answerable_questions"] == gate["answerable_questions"],
                  "mean_support_coverage": selected["metrics"]["mean_support_coverage_at_5"] >= gate["min_mean_support_coverage_at_5"],
                  "complete_questions": selected["metrics"]["complete_questions_at_5"] >= gate["min_complete_questions"],
                  "own_anchor_validity": selected["own_anchor_validity"] == gate["exact_anchor_validity"],
                  "scoring_context_anchor_validity": selected["scoring_context_anchor_validity"] == gate["exact_anchor_validity"],
                  "scope_isolation": selected["project_active_document_scope_isolation"] == gate["project_active_document_scope_isolation"]}
        result["selection_receipt_sha256"] = pin(selection_path)["sha256"]
        result["held_out_acceptance"] = {"checks": checks, "passed": all(checks.values())}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("development", "held-out"), default="development")
    parser.add_argument("--selection")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists(): parser.error("Evaluation output already exists; preserve prior result bytes")
    result = evaluate(args.split, args.selection)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"split": result["split"], "methods": [{"method": row["method"], "metrics": row["metrics"]} for row in result["method_results"]],
                      "gate": result.get("development_candidate_eligibility", result.get("held_out_acceptance"))}, sort_keys=True))


if __name__ == "__main__": main()
