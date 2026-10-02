"""Independent frozen medical retrieval metrics with receipt-gated held-out runs."""

from collections import defaultdict
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "medical_retrieval"


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def assess_question(question, trace, passages, bindings, *, top_k=5):
    """Score exact source/block quote containment, OR alternatives and AND groups."""
    returned = trace["passages"][:top_k]
    required_sets = question["sufficient_support_sets"]
    spans = defaultdict(list)
    for span in question["provisional_spans"]:
        spans[span["passage_id"]].append(span)
    required = set(passage for alternative in required_sets for passage in alternative)
    if any(not spans[passage] for passage in required):
        raise ValueError("Every required passage must declare question-specific gold quotes")
    coverage = {}
    for passage_id, gold_quotes in spans.items():
        passage = passages[passage_id]
        document = bindings[passage["article_alias"]]
        matching_ranks = []
        for quote in gold_quotes:
            ranks = [candidate["rank"] for candidate in returned
                     if candidate["document_id"] == document["document_id"]
                     and candidate["source_sha256"] == passage["source_sha256"]
                     and candidate["anchor"]["block_id"] == passage["provisional_block_id"]
                     and candidate["anchor"]["start"] <= quote["start"]
                     and candidate["anchor"]["end"] >= quote["end"]]
            matching_ranks.append(min(ranks) if ranks else None)
        coverage[passage_id] = {"required_quotes": len(gold_quotes), "quote_first_ranks": matching_ranks,
                                "covered_quotes": sum(rank is not None for rank in matching_ranks),
                                "covered": all(rank is not None for rank in matching_ranks)}
    answerable = bool(required_sets)
    first = min((rank for passage in required for rank in coverage[passage]["quote_first_ranks"] if rank is not None), default=None)
    fractions = [sum(coverage[passage]["covered"] for passage in alternative) / len(alternative) for alternative in required_sets]
    best = max(fractions, default=None)
    complete = any(fraction == 1 for fraction in fractions) if answerable else None
    failure_modes = []
    if answerable and first is None:
        failure_modes.append("no_required_gold_quote_at_5")
    if answerable and any(0 < coverage[passage]["covered_quotes"] < coverage[passage]["required_quotes"] for passage in required):
        failure_modes.append("partial_quotes_for_required_passage")
    if answerable and not complete:
        failure_modes.append("incomplete_sufficient_support_set")
    contexts = {passage: coverage[passage] for passage in question.get("context_only_passage_ids", []) if passage in coverage}
    hard_negatives = []
    for candidate in returned:
        for passage_id in question.get("hard_negative_passage_ids", []):
            passage = passages[passage_id]
            if candidate["document_id"] == bindings[passage["article_alias"]]["document_id"] and candidate["anchor"]["block_id"] == passage["provisional_block_id"]:
                hard_negatives.append({"passage_id": passage_id, "rank": candidate["rank"]})
    return {"question_id": question["id"], "article_alias": question["article_alias"], "question": question["question"],
            "answerable": answerable, "expected_answer_as_reported": question["expected_answer_as_reported"],
            "sufficient_support_sets": deepcopy(required_sets), "gold_quotes": deepcopy(question["provisional_spans"]),
            "first_required_quote_rank_at_5": first if answerable else None,
            "any_required_support_hit_at_5": first is not None if answerable else None,
            "reciprocal_rank_at_5": (1 / first if first is not None else 0) if answerable else None,
            "alternative_support_coverages_at_5": fractions, "best_alternative_support_coverage_at_5": best,
            "complete_support_at_5": complete, "passage_quote_coverage_at_5": coverage,
            "nonempty_candidates_at_5": bool(returned), "context_quote_coverage_at_5": contexts,
            "hard_negative_candidates_at_5": hard_negatives, "failure_modes": failure_modes,
            "returned_ranks_scores": [{"rank": candidate["rank"], "score": candidate["score"], "document_id": candidate["document_id"],
                                      "block_id": candidate["anchor"]["block_id"], "start": candidate["anchor"]["start"], "end": candidate["anchor"]["end"]}
                                     for candidate in returned]}


def aggregate_metrics(rows):
    answerable = [row for row in rows if row["answerable"]]
    unanswerable = [row for row in rows if not row["answerable"]]
    if not answerable:
        raise ValueError("An answerable denominator is required")
    return {"questions": len(rows), "answerable_questions": len(answerable), "no_answer_questions": len(unanswerable),
            "hit_rate_at_5": sum(row["any_required_support_hit_at_5"] for row in answerable) / len(answerable),
            "mean_reciprocal_rank_at_5": sum(row["reciprocal_rank_at_5"] for row in answerable) / len(answerable),
            "mean_support_coverage_at_5": sum(row["best_alternative_support_coverage_at_5"] for row in answerable) / len(answerable),
            "complete_questions_at_5": sum(row["complete_support_at_5"] for row in answerable),
            "complete_question_rate_at_5": sum(row["complete_support_at_5"] for row in answerable) / len(answerable),
            "no_answer_nonempty_candidate_rate_at_5": sum(row["nonempty_candidates_at_5"] for row in unanswerable) / len(unanswerable) if unanswerable else None,
            "no_answer_context_quotes_covered_at_5": sum(item["covered_quotes"] for row in unanswerable for item in row["context_quote_coverage_at_5"].values()),
            "no_answer_context_quotes_declared": sum(item["required_quotes"] for row in unanswerable for item in row["context_quote_coverage_at_5"].values())}


def development_recommendation(method_results, freeze):
    gate = freeze["development_selection"]
    eligible = [result for result in method_results
                if result["metrics"]["answerable_questions"] == gate["answerable_questions"]
                and result["metrics"]["mean_support_coverage_at_5"] >= gate["eligible_min_mean_support_coverage_at_5"]
                and result["metrics"]["complete_questions_at_5"] >= gate["eligible_min_complete_questions"]]
    eligible.sort(key=lambda result: tuple(result["metrics"][key] for key in gate["order"]) + (result["method"] == gate["final_tie_preference"],), reverse=True)
    return {"eligible_methods": [result["method"] for result in eligible],
            "recommended_method": eligible[0]["method"] if eligible else None,
            "coordinator_authorization_required_before_held_out": True}


def validate_trace(trace, store, project_id):
    if trace["project_id"] != project_id or trace["status"] != "candidate_passages" or trace["schema_version"] != 1:
        raise ValueError("Invalid operational retrieval trace identity")
    if digest_json(trace["source_manifest"]) != trace["source_snapshot_sha256"]:
        raise ValueError("Trace manifest hash mismatch")
    if trace["scope"] != "included" or trace["top_k"] != 5 or trace["method_version"] != "lit-rev-engine.project-retrieval.v1." + trace["method"]:
        raise ValueError("Benchmark trace method/scope differs from frozen settings")
    documents = {document["id"]: document for document in store.list_documents(project_id) if document["active"]}
    selected = {row["document_id"]: row for row in trace["source_manifest"]}
    if set(selected) != set(documents):
        raise ValueError("Benchmark selected sources differ from its three included active documents")
    records = {record["id"]: record for record in store.list_records(project_id)}
    links = {link["record_id"]: link for link in store.list_study_links(project_id)}
    for document_id, row in selected.items():
        document = documents[document_id]
        record = records[document["record_id"]]
        if row["record_id"] != record["id"] or row["record_title"] != record["title"]:
            raise ValueError("Selected manifest report ownership mismatch")
        if any(row[name] != document[name] for name in ("version", "format", "source_sha256", "blocks_sha256", "parser_id", "parser_metadata", "source_identifiers", "source_url", "version_label")):
            raise ValueError("Selected manifest source provenance mismatch")
        if any(row[name] != record[name] for name in ("doi", "pmid", "title_abstract_state", "full_text_status", "full_text_state")) or record["full_text_state"] != "include":
            raise ValueError("Selected manifest screening/scope mismatch")
        if row["study_link_state"] != links[record["id"]]["state"] or row["study_ids"] != links[record["id"]]["study_ids"]:
            raise ValueError("Selected manifest linkage provenance mismatch")
    blocks = {document_id: {block["id"]: block for block in store.get_source_blocks(project_id, document_id)} for document_id in selected}
    for rank, candidate in enumerate(trace["passages"], 1):
        document = documents[candidate["document_id"]]
        anchor = candidate["anchor"]
        block = blocks[document["id"]][anchor["block_id"]]
        if candidate["rank"] != rank or candidate["record_id"] != document["record_id"] or candidate["project_id"] != project_id:
            raise ValueError("Trace passage ownership or rank mismatch")
        if any(candidate[name] != document[name] for name in ("source_sha256", "blocks_sha256", "parser_id")):
            raise ValueError("Trace passage source provenance mismatch")
        if candidate["document_version"] != document["version"] or any(candidate[name] != selected[document["id"]][name] for name in ("full_text_state", "study_link_state", "study_ids")):
            raise ValueError("Trace passage current source/scope provenance mismatch")
        if set(anchor) != {"block_id", "start", "end", "quote"} or candidate["locator"] != block["locator"]:
            raise ValueError("Trace anchor/locator mismatch")
        if type(anchor["start"]) is not int or type(anchor["end"]) is not int or not 0 <= anchor["start"] < anchor["end"] <= len(block["text"]) or block["text"][anchor["start"]:anchor["end"]] != anchor["quote"]:
            raise ValueError("Trace passage is not an exact canonical source substring")
    return len(trace["passages"])


def verify_frozen_inputs():
    freeze = json.loads((FIXTURES / "freeze.json").read_text())
    for name, pin in freeze["frozen_files"].items():
        content = (FIXTURES / name).read_bytes()
        if len(content) != pin["size_bytes"] or hashlib.sha256(content).hexdigest() != pin["sha256"]:
            raise ValueError("Coordinator-frozen fixture changed: " + name)
    result = subprocess.run([sys.executable, str(FIXTURES / "verify.py")], capture_output=True, text=True, check=True)
    return freeze, result.stdout.strip()


def validate_selection(path, freeze):
    """Bind held-out execution to the coordinator's already-reviewed development."""
    if path is None:
        raise ValueError("Held-out evaluation requires a coordinator selection receipt")
    receipt = json.loads(Path(path).read_text())
    if receipt.get("schema_version") != 1 or receipt.get("status") != "coordinator_selected_before_held_out_ranking" or receipt.get("held_out_ranked_at_selection") is not False:
        raise ValueError("Selection receipt must precede held-out ranking")
    if receipt.get("freeze_file") != "tests/fixtures/medical_retrieval/freeze.json" or receipt.get("development_result_file") != "docs/medical-retrieval-development-v1.json":
        raise ValueError("Selection receipt declares unexpected pinned inputs")
    for file_key, hash_key in (("freeze_file", "freeze_sha256"), ("development_result_file", "development_result_sha256")):
        if hashlib.sha256((ROOT / receipt[file_key]).read_bytes()).hexdigest() != receipt.get(hash_key):
            raise ValueError("Selection receipt input hash mismatch: " + file_key)
    development = json.loads((ROOT / receipt["development_result_file"]).read_text())
    if development.get("split") != "development" or development.get("held_out_ranked") is not False:
        raise ValueError("Selection requires a development-only result")
    recommended = development_recommendation(development["method_results"], freeze)["recommended_method"]
    if receipt.get("selected_method") not in freeze["methods"] or receipt["selected_method"] != recommended:
        raise ValueError("Selected method differs from frozen development selection")
    if receipt.get("selection_rule") != freeze["development_selection"]:
        raise ValueError("Selection rule differs from prospective freeze")
    return receipt


def evaluate(split="development", selection_path=None):
    if split not in {"development", "held-out"}:
        raise ValueError("Unknown evaluation split")
    freeze, checker = verify_frozen_inputs()
    selection = validate_selection(selection_path, freeze) if split == "held-out" else None
    sys.path.insert(0, str(ROOT))
    from src.review.models import BibliographicRecord, SearchRunSpec
    from src.review.store import ReviewStore
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    passages = {passage["id"]: passage for passage in json.loads((FIXTURES / "passages.json").read_text())["passages"]}
    split_key = "development" if split == "development" else "held_out"
    questions = json.loads((FIXTURES / manifest["splits"][split_key]["file"]).read_text())["questions"]
    if [question["id"] for question in questions] != manifest["splits"][split_key]["ids"]:
        raise ValueError("Evaluation split IDs do not match the frozen declaration")
    results = []
    def deny_network(*args, **kwargs):
        raise AssertionError("Medical retrieval evaluator attempted network")
    socket.create_connection = deny_network
    with tempfile.TemporaryDirectory(prefix="medical-retrieval-" + split + "-") as directory:
        database = Path(directory) / "reviews.sqlite3"
        with ReviewStore(database) as store:
            project_id = store.create_project("Frozen three-source software pilot", "systematic", "Which exact published passages support the predeclared questions?")["id"]
            store.import_records(project_id, SearchRunSpec("Pinned licensed publisher XML bibliography"),
                                 [BibliographicRecord(title=source["title"], doi=source["doi"]) for source in manifest["sources"]])
            records = store.list_records(project_id)
            bindings = {}
            for source, record in zip(manifest["sources"], records, strict=True):
                store.record_decision(project_id, record["id"], "title_abstract", "include", "Pilot curator")
                store.set_full_text_status(project_id, record["id"], "retrieved", "Pilot curator")
                store.record_decision(project_id, record["id"], "full_text", "include", "Pilot curator")
                content = (FIXTURES / source["file"]).read_bytes()
                document = store.attach_document(project_id, record["id"], content, "jats_xml", "Pilot curator", "Pinned licensed source",
                                                 filename=Path(source["file"]).name, source_url=source["publisher_article_url"])
                bindings[source["alias"]] = {"document_id": document["id"], "record_id": record["id"], "source_sha256": document["source_sha256"]}
            baseline = hashlib.sha256("\n".join(store._connection.iterdump()).encode()).hexdigest()
            for method in ([selection["selected_method"]] if selection else freeze["methods"]):
                rows, traces, anchors = [], [], 0
                for question in questions:
                    trace = store.search_sources(project_id, question["question"], top_k=5, method=method)
                    if trace != store.search_sources(project_id, question["question"], top_k=5, method=method):
                        raise ValueError("Repeated same-ledger retrieval trace differs")
                    anchors += validate_trace(trace, store, project_id)
                    rows.append(assess_question(question, trace, passages, bindings))
                    traces.append(trace)
                if hashlib.sha256("\n".join(store._connection.iterdump()).encode()).hexdigest() != baseline:
                    raise ValueError("Retrieval changed ledger rows")
                results.append({"method": method, "metrics": aggregate_metrics(rows), "valid_exact_anchors": anchors,
                                "total_returned_anchors": anchors, "same_ledger_deterministic": True,
                                "ledger_rows_unchanged": True, "per_question": rows, "operational_traces": traces})
        with ReviewStore(database) as reopened:
            for result in results:
                for question, original in zip(questions, result["operational_traces"], strict=True):
                    if reopened.search_sources(project_id, question["question"], top_k=5, method=result["method"]) != original:
                        raise ValueError("Same-ledger reopened trace differs")
    if {"torch", "chromadb", "sentence_transformers", "dotenv", "src.settings", "fitz", "pymupdf"}.intersection(sys.modules):
        raise ValueError("Retrieval evaluator initialized a forbidden dependency")
    result = {"schema_version": 1, "evaluation_version": "independent-medical-retrieval.v1", "split": split,
            "held_out_ranked": split == "held-out", "source_gold_checker": checker, "freeze_sha256": hashlib.sha256((FIXTURES / "freeze.json").read_bytes()).hexdigest(),
            "frozen_parameters": freeze["fixed_parameters"], "method_results": results,
            "bindings": bindings, "operational_trace_identity_note": "Real IDs are retained and repeat exactly in the same reopened ledger. Fresh ledgers generate different UUIDs; those IDs are not cross-ledger reproducibility claims.",
            "limits": freeze["limits"]}
    if selection:
        metrics = results[0]["metrics"]
        gate = freeze["held_out_acceptance"]
        result["coordinator_selection"] = selection
        result["selection_receipt_sha256"] = hashlib.sha256(Path(selection_path).read_bytes()).hexdigest()
        result["held_out_acceptance"] = {
            "mean_support_coverage_at_5": metrics["mean_support_coverage_at_5"] >= gate["min_mean_support_coverage_at_5"],
            "complete_questions_at_5": metrics["complete_questions_at_5"] >= gate["min_complete_questions"],
            "answerable_denominator": metrics["answerable_questions"] == gate["answerable_questions"],
            "exact_anchor_validity": results[0]["valid_exact_anchors"] == results[0]["total_returned_anchors"],
            "project_active_document_scope_isolation": True,
        }
        result["all_held_out_checks_passed"] = all(result["held_out_acceptance"].values())
    else:
        result["development_selection_recommendation"] = development_recommendation(results, freeze)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--split", choices=("development", "held-out"), default="development")
    parser.add_argument("--selection", type=Path, help="Required coordinator selection receipt for held-out only")
    args = parser.parse_args()
    if args.split == "held-out" and args.selection is None:
        parser.error("--split held-out requires --selection")
    if args.split == "development" and args.selection is not None:
        parser.error("--selection applies only to held-out evaluation")
    result = evaluate(args.split, args.selection)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    selection_summary = result.get("development_selection_recommendation")
    if selection_summary is None:
        selection_summary = {"selected_method": result["coordinator_selection"]["selected_method"]}
    print(json.dumps({"split": result["split"], "held_out_ranked": result["held_out_ranked"],
                      "methods": [{"method": row["method"], **row["metrics"]} for row in result["method_results"]],
                      "selection": selection_summary,
                      "held_out_acceptance": result.get("held_out_acceptance")}, indent=2))


if __name__ == "__main__":
    main()
