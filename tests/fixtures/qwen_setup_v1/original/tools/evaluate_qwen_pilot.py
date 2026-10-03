"""One prospective cloud comparison; never tune old medical held-out artifacts."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.review.cloud_retrieval import search_sources_cloud, _read, _write
from src.review.documents import parse_source_bytes
from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.qwen import QwenClient, QwenProfile, api_key_from_env, canonical, digest, read_json, parse_embeddings, parse_scores
from src.review.store import ReviewStore


def pin(path):
    content = Path(path).read_bytes()
    return {"sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content)}


def verify_freeze(path):
    freeze = read_json(Path(path).read_bytes())
    if freeze.get("status") != "frozen_before_first_live_qwen_ranking" or type(freeze.get("live_ranking_runs_before_freeze")) is not int or freeze["live_ranking_runs_before_freeze"] != 0:
        raise ValueError("Prospective Qwen freeze is required")
    if not isinstance(freeze.get("files"), dict) or not freeze["files"]:
        raise ValueError("A nonempty complete Qwen file-pin mapping is required")
    required = {"tools/evaluate_qwen_pilot.py", "src/review/qwen.py", "src/review/cloud_retrieval.py", "src/review/qwen_cli.py",
                "src/review/cli.py", "src/review/store.py", "src/review/retrieval.py", "src/review/documents.py", "review.py",
                "tests/test_qwen_cloud_acceptance.py", "tests/test_qwen_pilot_evaluation.py", "docs/qwen-milestone.md"}
    for key in ("source_dir", "source_manifest", "questions_file"):
        value = freeze.get(key)
        if not isinstance(value, str) or Path(value).is_absolute() or ".." in Path(value).parts or not (ROOT / value).resolve().is_relative_to(ROOT.resolve()):
            raise ValueError("Qwen source/gold paths must be contained repository paths")
    required.update((freeze["source_manifest"], freeze["questions_file"]))
    for directory in (ROOT / freeze["source_dir"], (ROOT / freeze["questions_file"]).parent):
        required.update(str(file.relative_to(ROOT)) for file in directory.rglob("*") if file.is_file() and "__pycache__" not in file.parts)
    if not required.issubset(freeze["files"]):
        raise ValueError("Qwen freeze omits required implementation, source, gold or evaluation pins")
    for name, expected in freeze["files"].items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or not (ROOT / relative).resolve().is_relative_to(ROOT.resolve()) or pin(ROOT / relative) != expected:
            raise ValueError("Frozen Qwen input changed: " + name)
    if freeze["profile"] != QwenProfile.from_env().metadata():
        raise ValueError("Configured Qwen profile differs from the prospective freeze")
    return freeze


def supported(trace, document_id, anchor):
    return any(type(row.get("rank")) is int and 1 <= row["rank"] <= 5
               and row["document_id"] == document_id and row["anchor"]["block_id"] == anchor["block_id"]
               and row["anchor"]["start"] <= anchor["start"] < anchor["end"] <= row["anchor"]["end"]
               and row["anchor"]["quote"][anchor["start"] - row["anchor"]["start"]:anchor["end"] - row["anchor"]["start"]] == anchor["quote"]
               for row in trace["passages"][:5])


def assess(trace, question, document_id):
    sets = question["support_sets"]
    if not sets:
        contexts = question.get("context_anchors", [])
        return {"id": question["id"], "answerable": False, "coverage": None, "complete": None,
                "returned_candidates": len(trace["passages"]),
                "context_covered": sum(supported(trace, document_id, anchor) for anchor in contexts),
                "context_total": len(contexts)}
    if any(not isinstance(support, list) or not support for support in sets):
        raise ValueError("Positive support alternatives need a nonempty denominator")
    coverage = [sum(supported(trace, document_id, anchor) for anchor in support) / len(support) for support in sets]
    return {"id": question["id"], "answerable": True, "coverage": max(coverage), "complete": max(coverage) == 1.0}


def aggregate(rows):
    positives = [row for row in rows if row["answerable"]]
    if not positives:
        raise ValueError("Support metrics require a nonempty positive denominator")
    return {"answerable": len(positives), "mean_support_coverage": sum(row["coverage"] for row in positives) / len(positives),
            "complete_positives": sum(row["complete"] for row in positives),
            "nulls": [row for row in rows if not row["answerable"]]}


def validate_trace(store, project, trace):
    records = {record["id"]: record for record in store.list_records(project)}
    expected = {document["id"]: document for document in store.list_documents(project) if document["active"]
                and records[document["record_id"]]["title_abstract_state"] == "include"
                and records[document["record_id"]]["full_text_status"] == "retrieved"
                and records[document["record_id"]]["full_text_state"] == "include"}
    links = {link["record_id"]: link for link in store.list_study_links(project)}
    assert trace["project_id"] == project and trace["status"] == "candidate_passages" and trace["schema_version"] == 1
    assert trace["scope"] == "included" and trace["top_k"] == 5
    assert trace["method"] in {"qwen_hybrid", "bm25_context_blocks"}
    version = ("lit-rev-engine.project-retrieval.cloud-qwen.v1.qwen_hybrid" if trace["method"] == "qwen_hybrid"
               else "lit-rev-engine.project-retrieval.v3.bm25_context_blocks")
    assert trace["method_version"] == version and len(trace["passages"]) <= trace["top_k"]
    if trace["method"] == "qwen_hybrid":
        assert trace["profile"] == QwenProfile.from_env().metadata()
        assert trace["parameters"]["profile_sha256"] == digest(trace["profile"])
        assert trace["parameters"]["candidate_k"] == 20
        assert trace["answerability"] == "not_assessed" and trace["verification"] == "human_review_required"
    manifest = trace["source_manifest"]
    assert len(manifest) == len(expected) and {row["document_id"] for row in manifest} == set(expected)
    for row in manifest:
        document = expected[row["document_id"]]
        record = records[document["record_id"]]
        assert row["record_id"] == document["record_id"] and row["record_title"] == record["title"]
        for key in ("version", "format", "source_sha256", "blocks_sha256", "parser_id", "parser_metadata", "source_identifiers", "source_url", "version_label"):
            assert row[key] == document[key]
        for key in ("doi", "pmid", "title_abstract_state", "full_text_status", "full_text_state"):
            assert row[key] == record[key]
        assert row["study_link_state"] == links[record["id"]]["state"] and row["study_ids"] == links[record["id"]]["study_ids"]
    assert trace["indexed_passages"] == sum(bool(block["text"].strip()) for document in expected.values()
                                           for block in store.get_source_blocks(project, document["id"]))
    seen = set()
    for rank, row in enumerate(trace["passages"], 1):
        document = expected[row["document_id"]]
        assert type(row["rank"]) is int and row["rank"] == rank
        assert type(row["score"]) in (int, float) and math.isfinite(row["score"])
        if trace["method"] == "qwen_hybrid": assert 0 <= row["score"] <= 1
        assert row["project_id"] == project and row["record_id"] == document["record_id"]
        assert row["document_version"] == document["version"]
        for key in ("source_sha256", "blocks_sha256", "parser_id"):
            assert row[key] == document[key]
        assert row["full_text_state"] == records[document["record_id"]]["full_text_state"]
        assert row["study_link_state"] == links[document["record_id"]]["state"] and row["study_ids"] == links[document["record_id"]]["study_ids"]
        blocks = {block["id"]: block for block in store.get_source_blocks(project, document["id"])}
        anchor = row["anchor"]
        assert type(anchor["start"]) is int and type(anchor["end"]) is int
        block = blocks[anchor["block_id"]]
        assert anchor == {"block_id": block["id"], "start": 0, "end": len(block["text"]), "quote": block["text"]}
        assert row["locator"] == block["locator"]
        identity = document["id"], block["id"]
        assert identity not in seen
        seen.add(identity)
        for context in row.get("scoring_context", []):
            own = context["anchor"]
            block = blocks[own["block_id"]]
            assert type(own["start"]) is int and type(own["end"]) is int and 0 <= own["start"] < own["end"] <= len(block["text"])
            assert own["quote"] == block["text"][own["start"]:own["end"]] and context["locator"] == block["locator"]
    assert trace["source_snapshot_sha256"] == digest(trace["source_manifest"])


def validate_gold(store, project, questions, documents):
    if len(questions) != 8 or len({question["id"] for question in questions}) != 8:
        raise ValueError("Qwen truth requires eight unique questions")
    positives, ands = 0, 0
    for question in questions:
        if not isinstance(question["id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]+", question["id"]):
            raise ValueError("Qwen question IDs must be safe artifact names")
        if question["source_id"] not in documents or not isinstance(question["query"], str) or not question["query"].strip():
            raise ValueError("Qwen question has invalid source/query")
        if not isinstance(question["support_sets"], list) or type(question["answerable"]) is not bool or question["answerable"] != bool(question["support_sets"]):
            raise ValueError("Qwen answerability and support sets disagree")
        positives += question["answerable"]
        if question["answerable"] and question.get("quantitative") is not True:
            raise ValueError("The fixed Qwen positives must be quantitative")
        if question["answerable"] and all(len({a["block_id"] for a in support}) >= 2 for support in question["support_sets"]):
            ands += 1
        if not question["answerable"] and not question.get("null_reason"):
            raise ValueError("Qwen null requires a source-scoped rationale")
        blocks = {block["id"]: block for block in store.get_source_blocks(project, documents[question["source_id"]])}
        for support in question["support_sets"]:
            if not isinstance(support, list) or not support:
                raise ValueError("Qwen positive support alternatives cannot be empty")
        for anchors in question["support_sets"] + [question.get("context_anchors", [])]:
            for anchor in anchors:
                if anchor["block_id"] not in blocks or type(anchor["start"]) is not int or type(anchor["end"]) is not int:
                    raise ValueError("Qwen gold anchor has invalid identity/bounds")
                text = blocks[anchor["block_id"]]["text"]
                if not 0 <= anchor["start"] < anchor["end"] <= len(text) or anchor["quote"] != text[anchor["start"]:anchor["end"]]:
                    raise ValueError("Qwen gold quotation does not match original canonical bytes")
    if positives != 6 or ands < 3:
        raise ValueError("Qwen truth requires six positives, at least three necessary distinct-block ANDs and two nulls")


class MeasuredClient(QwenClient):
    def __init__(self, profile, api_key, directory, budget):
        super().__init__(profile, api_key)
        self.calls, self.directory, self.budget = [], directory, budget
        self.cost = 0.0
        self.phase_start, self.phase_limit = time.monotonic(), 900
        self.stopped = False

    def begin_query(self, max_seconds):
        if type(max_seconds) not in (int, float) or not math.isfinite(max_seconds) or not 0 < max_seconds <= 900:
            raise ValueError("Qwen phase budget must be finite and within 900 seconds")
        self.phase_start, self.phase_limit = time.monotonic(), max_seconds

    def _post(self, url, request):
        if self.stopped:
            raise ValueError("Qwen evaluation has stopped; no more calls")
        if time.monotonic() - self.phase_start > self.phase_limit:
            self.stopped = True
            raise ValueError("Qwen phase time exceeded its prospective bound; no more calls")
        try:
            response, elapsed = super()._post(url, request)
        except ValueError:
            self.stopped = True
            _write(self.directory / "provider-calls.json", {"status": "provider_call_failed_charge_unknown", "calls": self.calls,
                                                            "failed_request": {"url": url, "request": request}})
            raise
        cost = response.get("inference_status", {}).get("cost")
        self.calls.append({"url": url, "request": request, "response": response, "elapsed_seconds": elapsed})
        _write(self.directory / "provider-calls.json", {"status": "observed_provider_calls", "calls": self.calls})
        try:
            if "inputs" in request:
                parse_embeddings(self.profile, response, len(request["inputs"]))
            else:
                parse_scores(self.profile, response, len(request["documents"]))
        except ValueError:
            self.stopped = True
            raise
        if type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0:
            self.stopped = True
            raise ValueError("Provider cost is unavailable or invalid; stop further budgeted calls")
        if cost is not None:
            self.cost += cost
        if len(self.calls) % 10 == 0:
            print(f"Observed {len(self.calls)} provider calls; reported cost USD {self.cost:.6f}", flush=True)
        if cost is not None and self.cost > self.budget:
            self.stopped = True
            raise ValueError("Observed Qwen cost exceeded the prospective bound; no more calls")
        if time.monotonic() - self.phase_start > self.phase_limit:
            self.stopped = True
            raise ValueError("Qwen phase time exceeded its prospective bound; no more calls")
        return response, elapsed


def evaluate(freeze_path, output):
    freeze = verify_freeze(freeze_path)
    if Path(output).exists():
        raise ValueError("Use a fresh Qwen evaluation directory")
    output = Path(output)
    sources = read_json((ROOT / freeze["source_manifest"]).read_bytes())["sources"]
    questions = read_json((ROOT / freeze["questions_file"]).read_bytes())["questions"]
    if len(questions) != 8 or sum(bool(q["support_sets"]) for q in questions) != 6:
        raise ValueError("The prospective Qwen denominator must be six positives and two nulls")
    profile = QwenProfile.from_env()
    # Bound an upper workload estimate before network; byte counts are a resource estimate,
    # not a measured tokenizer or an assurance about provider billing.
    source_bytes = sum(len(block["text"].encode("utf-8")) for source in sources
                       for block in parse_source_bytes((ROOT / freeze["source_dir"] / source["file"]).read_bytes(), "jats_xml")["blocks"])
    representation_bound = sum((len(block["text"].encode("utf-8")) + profile.max_document_bytes - 1) // profile.max_document_bytes
                              for source in sources for block in parse_source_bytes((ROOT / freeze["source_dir"] / source["file"]).read_bytes(), "jats_xml")["blocks"])
    query_bound = max(len(q["query"].encode("utf-8")) for q in questions)
    estimate = source_bytes * 0.020 / 1_000_000 + 8 * (source_bytes + representation_bound * (query_bound + 512 + 1024)) * 0.025 / 1_000_000
    if estimate > freeze["gate"]["max_reported_cost_usd"] or representation_bound > profile.max_representations:
        raise ValueError("Prospective Qwen workload estimate exceeds its bound")
    output.mkdir(parents=True)
    reference_rows, candidate_rows, timings = [], [], []
    with ReviewStore(output / "review.sqlite3") as store:
        project = store.create_project("Prospective Qwen software pilot", "systematic", "Fixed source-grounded retrieval questions")['id']
        store.import_records(project, SearchRunSpec("Licensed publisher XML, fixed Qwen evaluation"),
                             [BibliographicRecord(title=source["title"], doi=source["doi"]) for source in sources])
        record_by_doi = {row["doi"]: row for row in store.list_records(project)}
        documents = {}
        for source in sources:
            record = record_by_doi[source["doi"]]
            store.record_decision(project, record["id"], "title_abstract", "include", "Pilot curator")
            store.set_full_text_status(project, record["id"], "retrieved", "Pilot curator")
            store.record_decision(project, record["id"], "full_text", "include", "Pilot curator")
            documents[source["id"]] = store.attach_document(project, record["id"], (ROOT / freeze["source_dir"] / source["file"]).read_bytes(),
                                                            "jats_xml", "Pilot curator", "Fixed licensed XML", source_url=source["publisher_xml_url"])["id"]
        before = tuple(store._connection.iterdump())
        validate_gold(store, project, questions, documents)
        client = MeasuredClient(profile, api_key_from_env(), output, freeze["gate"]["max_reported_cost_usd"])
        for number, question in enumerate(questions, 1):
            document = documents[question["source_id"]]
            blocks = {block["id"]: block for block in store.get_source_blocks(project, document)}
            for anchors in question["support_sets"] + [question.get("context_anchors", [])]:
                for anchor in anchors:
                    assert anchor["quote"] == blocks[anchor["block_id"]]["text"][anchor["start"]:anchor["end"]]
            reference = store.search_sources(project, question["query"], top_k=5, method="bm25_context_blocks")
            validate_trace(store, project, reference)
            start = time.monotonic()
            client.begin_query(freeze["gate"]["max_cold_seconds"] if number == 1 else freeze["gate"]["max_warm_p95_seconds"])
            trace = search_sources_cloud(store, project, question["query"], profile=profile, client=client,
                                         mode="qwen_hybrid", top_k=5, candidate_k=20,
                                         index_path=output / "index.json", receipt_path=output / (question["id"] + ".receipt.json"))
            timings.append(time.monotonic() - start)
            validate_trace(store, project, trace)
            replay = search_sources_cloud(store, project, question["query"], profile=profile, mode="qwen_hybrid", top_k=5, candidate_k=20,
                                          replay_path=output / (question["id"] + ".receipt.json"), replay_sha256=trace["receipt_sha256"])
            assert replay["provider_calls"] == 0 and replay["passages"] == trace["passages"]
            assert tuple(store._connection.iterdump()) == before
            reference_rows.append(assess(reference, question, document))
            candidate_rows.append(assess(trace, question, document))
            (output / (question["id"] + ".trace.json")).write_text(canonical(trace))
            print(f"{number}/8 {question['id']}: own-support {candidate_rows[-1]['coverage']}; complete {candidate_rows[-1]['complete']}", flush=True)
        reference_metrics, candidate_metrics = aggregate(reference_rows), aggregate(candidate_rows)
        observed_costs = [call["response"].get("inference_status", {}).get("cost") for call in client.calls]
        measured_cost = sum(observed_costs) if all(cost is not None for cost in observed_costs) else None
        warm = sorted(timings[1:])
        p95 = warm[max(0, (95 * len(warm) + 99) // 100 - 1)]
        checks = {"support_coverage": candidate_metrics["mean_support_coverage"] >= freeze["gate"]["min_mean_support_coverage"],
                  "complete_positives": candidate_metrics["complete_positives"] >= freeze["gate"]["min_complete_positives"],
                  "coverage_nonregression": candidate_metrics["mean_support_coverage"] >= reference_metrics["mean_support_coverage"],
                  "complete_nonregression": candidate_metrics["complete_positives"] >= reference_metrics["complete_positives"],
                  "exact_anchors_scope_replay_readonly": True,
                  "cost": measured_cost is not None and measured_cost <= freeze["gate"]["max_reported_cost_usd"],
                  "cold_time": timings[0] <= freeze["gate"]["max_cold_seconds"],
                  "warm_p95": p95 <= freeze["gate"]["max_warm_p95_seconds"]}
        result = {"schema_version": 1, "status": "passed" if all(checks.values()) else "failed", "checks": checks,
                  "freeze": pin(freeze_path), "profile": profile.metadata(), "workload_estimate_usd": estimate,
                  "reference": {"method": "bm25_context_blocks", "metrics": reference_metrics, "per_question": reference_rows},
                  "candidate": {"method": "qwen_hybrid", "metrics": candidate_metrics, "per_question": candidate_rows},
                  "usage": {"provider_calls": len(client.calls), "input_tokens": sum(call["response"]["input_tokens"] for call in client.calls),
                            "reported_cost_usd": measured_cost, "cold_query_seconds": timings[0], "warm_p95_seconds": p95},
                  "project_id": project, "document_bindings": documents,
                  "limitations": ["Eight fixed main-article questions; not clinical validation", "Managed aliases; immutable revisions and server truncation not exposed",
                                  "Relevance candidates do not assess answerability or verify evidence", "Warm latency sample has seven queries"]}
        (output / "result.json").write_text(canonical(result))
        print(canonical({"status": result["status"], "checks": checks, "metrics": candidate_metrics, "usage": result["usage"]}), flush=True)
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    try:
        outcome = evaluate(arguments.freeze, arguments.output)
        raise SystemExit(0 if outcome["status"] == "passed" else 2)
    except (ValueError, OSError) as error:
        print("Qwen evaluation stopped: " + str(error), file=sys.stderr)
        raise SystemExit(1)
