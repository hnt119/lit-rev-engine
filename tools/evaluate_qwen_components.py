#!/usr/bin/env python3
"""Prospectively frozen component batches: local preparation and immutable grading."""

import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.review.documents import parse_source_bytes
from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.qwen import canonical, digest, read_json
from src.review.store import ReviewStore
from src.review_components import PROFILE, export_job, import_results
from src.review_components.ledger import execution_paths

REQUIRED = {"review_components.py", "tools/evaluate_qwen_components.py", "tools/qwen_components_kaggle_runner.py",
            "tools/qwen_kaggle_environment.py", "notebooks/qwen_components_kaggle.ipynb", "docs/qwen-components-contract-v1.md",
            "docs/qwen-components-interface-selection-v1.json", "docs/qwen-components-evaluation.md",
            "tests/test_qwen_components.py", "tests/test_qwen_components_evaluation.py", "tests/test_qwen_components_environment.py", "tests/test_qwen_components_worker.py",
            "docs/qwen-kaggle-freeze-v2.json", "tools/evaluate_qwen_pilot.py", "tools/evaluate_qwen_kaggle.py"}
REQUIRED.update(str(p.relative_to(ROOT)) for folder in ("src/review", "src/review_components") for p in (ROOT / folder).glob("*.py"))
GATE = {"min_mean_support_coverage": .85, "min_complete_positives": 4, "positive_questions": 6, "null_questions": 2,
        "top_k": 5, "candidate_k": 20, "max_batch_seconds": 1800, "paid_inference_calls": 0,
        "nonregression_comparators": ["whole_lexical", "whole_qwen", "component_lexical"]}
METHODS = {"candidate": "qwen_components_hybrid", "whole_qwen": "qwen_kaggle_hybrid",
           "whole_lexical": "bm25_context_blocks", "component_lexical": "bm25_context_components"}
METHOD_SELECTION = "docs/qwen-components-method-selection-v1.json"
DEVELOPMENT_FREEZE = "docs/qwen-components-development-freeze-v1.json"
DEVELOPMENT_RESULT = "tests/fixtures/qwen_components_development_run_v1/result.json"
HISTORICAL_FREEZE_SHA256 = "04f0a961eb0f7d91626a72e93f68c5d4f8cc77f4ff0f78fbb72063219d878b62"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pin(path):
    raw = Path(path).read_bytes()
    return {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}


def contained(name):
    require(isinstance(name, str) and bool(name) and not Path(name).is_absolute() and ".." not in Path(name).parts,
            "Freeze paths must be contained repository paths")
    path = ROOT / name
    require(path.resolve().is_relative_to(ROOT.resolve()), "Freeze path escapes repository")
    return path


def verify_freeze(path):
    freeze = read_json(Path(path).read_bytes())
    require(isinstance(freeze, dict) and type(freeze.get("schema_version")) is int and freeze["schema_version"] == 1
            and freeze.get("status") == "frozen_before_first_components_ranking" and freeze.get("split") in {"development", "confirmation"}
            and type(freeze.get("ranking_runs_before_freeze")) is int and freeze["ranking_runs_before_freeze"] == 0,
            "A prospective component freeze with zero previous rankings is required")
    require(canonical(freeze.get("gate")) == canonical(GATE) and canonical(freeze.get("profile")) == canonical(PROFILE),
            "Frozen component profile or acceptance gate differs")
    selection_path = contained("docs/qwen-components-interface-selection-v1.json")
    require(canonical(freeze.get("contract_selection_pin")) == canonical(pin(selection_path)), "Prospective interface selection pin differs")
    selection = read_json(selection_path.read_bytes())
    require(type(selection.get("schema_version")) is int and selection["schema_version"] == 1
            and selection.get("status") == "selected_before_implementation"
            and type(selection.get("development_rankings_before_selection")) is int and selection["development_rankings_before_selection"] == 0
            and type(selection.get("confirmation_rankings_before_selection")) is int and selection["confirmation_rankings_before_selection"] == 0
            and selection.get("confirmation_questions_seen_by_coordinator") is False and selection.get("no_paid_inference") is True,
            "Interface was not selected prospectively with blind confirmation")
    contract = selection.get("contract", {})
    require(contract.get("path") == "docs/qwen-components-contract-v1.md"
            and canonical({k: contract.get(k) for k in ("sha256", "size_bytes")}) == canonical(pin(contained(contract["path"]))),
            "Selected contract bytes changed")
    split = freeze["split"]
    expected_source = f"tests/fixtures/qwen_components_{split}_sources"
    expected_gold = f"tests/fixtures/qwen_components_{split}_gold/questions.json"
    require(freeze.get("source_dir") == expected_source and freeze.get("source_manifest") == expected_source + "/manifest.json"
            and freeze.get("questions_file") == expected_gold, "Freeze split/source/truth binding differs")
    required = set(REQUIRED)
    if split == "confirmation":
        selection_file = contained(METHOD_SELECTION)
        require(canonical(freeze.get("method_selection_pin")) == canonical(pin(selection_file)), "Confirmation method-selection pin differs")
        method_selection = read_json(selection_file.read_bytes())
        receipt_fields = {"schema_version", "status", "profile_sha256", "development_freeze_pin", "development_result_pin", "development_result_file",
                          "development_status", "confirmation_questions_seen_by_coordinator", "confirmation_rankings_before_selection",
                          "method_changed_after_development", "selection_reason"}
        require(isinstance(method_selection, dict) and set(method_selection) == receipt_fields
                and type(method_selection["schema_version"]) is int and method_selection["schema_version"] == 1
                and method_selection["status"] == "selected_after_development_before_confirmation"
                and method_selection["profile_sha256"] == digest(PROFILE)
                and method_selection["confirmation_questions_seen_by_coordinator"] is False
                and type(method_selection["confirmation_rankings_before_selection"]) is int and method_selection["confirmation_rankings_before_selection"] == 0
                and method_selection["method_changed_after_development"] is False
                and isinstance(method_selection["selection_reason"], str) and method_selection["selection_reason"].strip()
                and method_selection["development_result_file"] == DEVELOPMENT_RESULT, "Confirmation selection was not recorded prospectively")
        development_path = contained(DEVELOPMENT_FREEZE)
        development = verify_freeze(development_path)
        require(development["split"] == "development"
                and canonical(method_selection["development_freeze_pin"]) == canonical(pin(development_path)), "Selection development-freeze binding differs")
        result_path = contained(DEVELOPMENT_RESULT)
        require(canonical(method_selection["development_result_pin"]) == canonical(pin(result_path)), "Selection original development-result bytes differ")
        development_result = read_json(result_path.read_bytes())
        require(type(development_result.get("schema_version")) is int and development_result["schema_version"] == 1
                and development_result.get("split") == "development" and development_result.get("status") in {"passed", "failed"}
                and development_result["status"] == method_selection["development_status"]
                and canonical(development_result.get("freeze")) == canonical(pin(development_path))
                and all(isinstance(development_result.get(key), str) and re.fullmatch(r"[a-f0-9]{64}", development_result[key])
                        for key in ("job_sha256", "results_sha256")), "Selection factual first development-grade binding differs")
        checks = development_result.get("checks")
        require(isinstance(checks, dict) and checks and all(type(v) is bool for v in checks.values())
                and development_result["status"] == ("passed" if all(checks.values()) else "failed"), "Development status contradicts preserved checks")
        required.update({METHOD_SELECTION, DEVELOPMENT_FREEZE, DEVELOPMENT_RESULT})
    for directory in (contained(expected_source), contained(expected_gold).parent):
        required.update(str(p.relative_to(ROOT)) for p in directory.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    historical_path = contained("docs/qwen-kaggle-freeze-v2.json")
    require(pin(historical_path)["sha256"] == HISTORICAL_FREEZE_SHA256, "Historical first-failure freeze bytes changed")
    historical = read_json(historical_path.read_bytes())
    historical_pins = historical.get("files")
    require(isinstance(historical_pins, dict), "Historical v2 freeze is missing")
    required.update(historical_pins)
    files = freeze.get("files")
    require(isinstance(files, dict) and required.issubset(files), "Freeze omits required source, truth, code, test or historical pins")
    for name, expected in files.items():
        require(isinstance(expected, dict) and set(expected) == {"sha256", "size_bytes"}
                and type(expected["size_bytes"]) is int and expected["size_bytes"] >= 0
                and canonical(pin(contained(name))) == canonical(expected), "Frozen component input changed: " + name)
    for name, expected in historical_pins.items():
        require(canonical(pin(contained(name))) == canonical(expected), "Historical v2 input changed: " + name)
    return freeze


def original_blocks(raw, source_id):
    """Reconstruct own canonical spans directly from XML, before saved gold/parser."""
    require(not re.search(rb"<!ENTITY\b", raw, re.I), "Source XML entities are unsupported")
    root = ET.fromstring(raw.decode("utf-8-sig"))
    require(root.tag.rsplit("}", 1)[-1] == "article", "Main article XML required")
    blocks, roles = [], {}
    def name(node): return node.tag.rsplit("}", 1)[-1]
    def inline(node): return " ".join("".join(node.itertext()).split()) if node is not None else ""
    def child(node, tag): return next((n for n in node if name(n) == tag), None)
    def walk(node, path, ancestors, sections):
        tag = name(node)
        if tag in {"ref-list", "ref", "sub-article"}: return
        if tag == "sec": sections = [*sections, inline(child(node, "title"))]
        selected = (tag == "article-title" and "front" in ancestors) or (tag == "p" and ("body" in ancestors or "abstract" in ancestors)) or (tag == "table-wrap" and "body" in ancestors)
        if selected:
            if tag == "table-wrap":
                lines = [inline(child(node, v)) for v in ("label", "caption")]
                lines = [v for v in lines if v]
                for row in node.iter():
                    if name(row) == "tr":
                        value = "\t".join(inline(cell) for cell in row if name(cell) in {"td", "th"})
                        if value.strip(): lines.append(value)
                lines.extend(inline(n) for n in node if name(n) == "table-wrap-foot" and inline(n))
                text = "\n".join(lines)
            else: text = inline(node)
            if text:
                locator = {"type": "xml_element", "path": path, "tag": tag}
                if node.get("id") is not None: locator["element_id"] = node.get("id")
                section = next((v for v in reversed(sections) if v), "")
                if section: locator["section_title"] = section
                if tag == "table-wrap" and inline(child(node, "label")): locator["table_label"] = inline(child(node, "label"))
                block = {"source_id": source_id, "block_id": "xml:" + path, "ordinal": len(blocks) + 1,
                         "source_path": path, "kind": tag, "section": section, "text": text,
                         "sha256": hashlib.sha256(text.encode()).hexdigest(), "locator": locator}
                blocks.append(block)
                roles[block["block_id"]] = {role for title in sections for role, pattern in (("methods", r"\b(methods?|methodology)\b"), ("results", r"\bresults?\b"))
                                            if "body" in ancestors and re.search(pattern, title, re.I)}
            if tag == "table-wrap": return
        seen = {}
        for item in node:
            item_name = name(item)
            seen[item_name] = seen.get(item_name, 0) + 1
            walk(item, f"{path}/{item_name}[{seen[item_name]}]", [*ancestors, tag], sections)
    walk(root, "/article[1]", [], [])
    return root, blocks, roles


def validate_data(freeze):
    source_manifest = read_json(contained(freeze["source_manifest"]).read_bytes())
    gold_dir = contained(freeze["questions_file"]).parent
    gold_manifest = read_json((gold_dir / "manifest.json").read_bytes())
    questions_data = read_json(contained(freeze["questions_file"]).read_bytes())
    prospective = gold_manifest.get("prospective", {})
    require(prospective.get("truth_status") == "accepted_independent_source_first_evaluation"
            and type(prospective.get("rankings_observed")) is int and prospective["rankings_observed"] == 0
            and type(prospective.get("paid_inference_calls")) is int and prospective["paid_inference_calls"] == 0
            and (freeze["split"] != "confirmation" or prospective.get("coordinator_confirmation_qa_blind") is True),
            "Original truth requires accepted pre-ranking independent review and blind confirmation")
    sources = source_manifest.get("sources")
    require(type(source_manifest.get("schema_version")) is int and source_manifest["schema_version"] == 1
            and source_manifest.get("split") == gold_manifest.get("split") == freeze["split"]
            and isinstance(sources, list) and len(sources) == 2 and len({s["id"] for s in sources}) == 2
            and len({s["doi"] for s in sources}) == 2, "Fresh source split and identities differ")
    require(canonical({k: gold_manifest.get("source_manifest", {}).get(k) for k in ("sha256", "size_bytes")}) == canonical(pin(contained(freeze["source_manifest"]))),
            "Truth-to-acquisition binding differs")
    for name in ("blocks.json", "questions.json"):
        require(canonical(gold_manifest.get("files", {}).get(name)) == canonical(pin(gold_dir / name)), "Truth file digest differs: " + name)
    require(type(questions_data.get("schema_version")) is int and questions_data["schema_version"] == 1, "Truth schema differs")
    rebuilt, roles = [], {}
    for source in sources:
        filename = source["file"]
        require(isinstance(filename, str) and Path(filename).name == filename and filename.endswith(".xml"), "Own source path differs")
        path = contained(freeze["source_dir"]) / filename
        require(path.resolve().is_relative_to(contained(freeze["source_dir"]).resolve()) and not path.is_symlink(), "Source path escapes archive")
        raw = path.read_bytes()
        require(canonical(pin(path)) == canonical({"sha256": source["source_sha256"], "size_bytes": source["size_bytes"]}), "Original source bytes differ")
        root, blocks, source_roles = original_blocks(raw, source["id"])
        metadata = root.find("./front/article-meta")
        require(metadata is not None and metadata.findtext('./article-id[@pub-id-type="doi"]') == source["doi"], "Own DOI differs")
        license_node = metadata.find("./permissions/license")
        require(license_node is not None and license_node.get("{http://www.w3.org/1999/xlink}href") in
                {"http://creativecommons.org/licenses/by/4.0/", "https://creativecommons.org/licenses/by/4.0/"}, "Original CC BY 4 license required")
        require(len(blocks) == source["block_count"] and digest(blocks) == source["canonical_blocks_sha256"], "Own source inventory differs")
        parsed = parse_source_bytes(raw, "jats_xml")
        require(parsed["parser_id"] == source["parser_id"] and canonical(parsed["blocks"]) == canonical(
                [{"id": b["block_id"], "ordinal": b["ordinal"], "text": b["text"], "locator": b["locator"]} for b in blocks]), "Parser disagrees with original XML")
        rebuilt.extend(blocks)
        roles.update({(source["id"], key): value for key, value in source_roles.items()})
    require(canonical(read_json((gold_dir / "blocks.json").read_bytes())["blocks"]) == canonical(rebuilt), "Saved blocks disagree with independent original inventory")
    by_id = {(b["source_id"], b["block_id"]): b for b in rebuilt}
    questions = questions_data.get("questions")
    require(isinstance(questions, list) and len(questions) == 8 and len({q["id"] for q in questions}) == 8, "Truth requires eight unique questions")
    from src.review_components.core import normalize_questions
    normalized = normalize_questions([{k: q[k] for k in ("id", "query", "components")} for q in questions])
    positive, necessary_methods_results = 0, 0
    def anchor_ok(a, source_id):
        require(isinstance(a, dict) and set(a) == {"source_id", "block_id", "source_path", "block_sha256", "start", "end", "quote"}
                and a["source_id"] == source_id, "Truth anchor/source schema differs")
        b = by_id.get((source_id, a["block_id"]))
        require(b is not None and a["source_path"] == b["source_path"] and a["block_sha256"] == b["sha256"], "Truth anchor original identity differs")
        require(type(a["start"]) is int and type(a["end"]) is int and 0 <= a["start"] < a["end"] <= len(b["text"])
                and a["quote"] == b["text"][a["start"]:a["end"]], "Truth Unicode quotation/bounds differ")
    for q, request in zip(questions, normalized, strict=True):
        require(set(q) == {"id", "source_id", "query", "components", "answerable", "quantitative", "category", "expected_answer", "necessary_and", "support_sets", "context_anchors", "null_reason"}
                and type(q.get("answerable")) is bool and type(q.get("quantitative")) is bool and type(q.get("necessary_and")) is bool
                and isinstance(q.get("support_sets"), list) and isinstance(q.get("context_anchors"), list)
                and q["answerable"] == bool(q["support_sets"]) and len(request["components"]) in {2, 3}, "Compound truth flags or components differ")
        positive += q["answerable"]
        require(not q["answerable"] or (q["quantitative"] and isinstance(q.get("expected_answer"), str) and q["expected_answer"].strip()), "Positive truth lacks quantitative answer")
        require(q["answerable"] or (q.get("expected_answer") is None and isinstance(q.get("null_reason"), str) and q["null_reason"].strip()), "Null requires scoped rationale and no answer")
        each_roles = []
        for support in q["support_sets"]:
            require(isinstance(support, list) and support, "Sufficient OR alternative needs nonempty AND spans")
            for a in support: anchor_ok(a, q["source_id"])
            block_ids = {a["block_id"] for a in support}
            require(len({canonical(a) for a in support}) == len(support), "Duplicate support spans inflate denominator")
            each_roles.append(len(block_ids) >= 2 and any("methods" in roles[(q["source_id"], b)] for b in block_ids)
                              and any("results" in roles[(q["source_id"], b)] for b in block_ids))
        necessary_methods_results += bool(each_roles) and all(each_roles)
        necessary_and = bool(q["support_sets"]) and all(len({a["block_id"] for a in support}) >= 2 for support in q["support_sets"])
        require(q["necessary_and"] == necessary_and, "Truth necessary-AND declaration differs from sufficient alternatives")
        for a in q["context_anchors"]: anchor_ok(a, q["source_id"])
    require(positive == 6 and necessary_methods_results >= 4, "Truth needs six quantitative positives and at least four necessary body Methods/Results ANDs")
    return sources, questions, {"questions": 8, "positives": positive, "nulls": 8 - positive,
                                "necessary_methods_results_and": necessary_methods_results, "blocks": len(rebuilt)}


def ledger_hash(store):
    return digest(list(store._connection.iterdump()))


def save_new(path, data):
    with Path(path).open("x", encoding="utf-8") as stream: stream.write(canonical(data))


def bindings_ok(store, project, sources, documents):
    require(isinstance(documents, dict) and set(documents) == {s["id"] for s in sources} and len(set(documents.values())) == 2, "Prepared document bindings differ")
    current = {d["id"]: d for d in store.list_documents(project) if d["active"]}
    require(set(current) == set(documents.values()), "Prepared active source set differs")
    for source in sources:
        doc = current[documents[source["id"]]]
        require(doc["source_sha256"] == source["source_sha256"] and doc["parser_id"] == source["parser_id"], "Prepared document source differs")


def prepare(freeze_path, output):
    freeze = verify_freeze(freeze_path)
    sources, questions, truth_counts = validate_data(freeze)
    output = Path(output)
    require(not os.path.lexists(output), "Use a fresh component evaluation directory")
    output.mkdir(parents=True)
    upload = output / "kaggle-upload"
    upload.mkdir()
    with ReviewStore(output / "review.sqlite3") as store:
        project = store.create_project("Prospective components " + freeze["split"], "systematic", "Fixed licensed software evaluation")["id"]
        store.import_records(project, SearchRunSpec("Prospectively frozen main article XML"), [BibliographicRecord(title=s["title"], doi=s["doi"]) for s in sources])
        records = {r["doi"]: r for r in store.list_records(project)}
        documents = {}
        for source in sources:
            record = records[source["doi"]]["id"]
            store.record_decision(project, record, "title_abstract", "include", "Software fixture curator")
            store.set_full_text_status(project, record, "retrieved", "Software fixture curator")
            store.record_decision(project, record, "full_text", "include", "Software fixture curator")
            documents[source["id"]] = store.attach_document(project, record, (contained(freeze["source_dir"]) / source["file"]).read_bytes(),
                "jats_xml", "Software fixture curator", "Exact licensed original", source_url=source["publisher_xml_url"], version_label=source["version_label"])["id"]
        bindings_ok(store, project, sources, documents)
        before = ledger_hash(store)
        job = export_job(store, project, [{k: q[k] for k in ("id", "query", "components")} for q in questions], output_path=upload / "job.json")
        require(ledger_hash(store) == before, "Component preparation changed ledger")
        preparation = {"schema_version": 1, "status": "prepared_not_ranked", "split": freeze["split"], "freeze": pin(freeze_path),
                       "project_id": project, "document_bindings": documents, "job_sha256": job["payload_sha256"], "ledger_sha256": before,
                       "execution_files": job["payload"]["execution_files"], "truth_counts": truth_counts}
    for name, path in execution_paths().items():
        shutil.copyfile(path, upload / name)
        require(pin(upload / name) == job["payload"]["execution_files"][name], "Upload helper differs from frozen job")
    notebook = read_json(contained("notebooks/qwen_components_kaggle.ipynb").read_bytes())
    # Only the local job hash is substituted. The pristine frozen notebook remains unchanged.
    for cell in notebook["cells"]:
        cell["source"] = [line.replace("JOB_SHA256 = 'PASTE_TRUSTED_LOCAL_EXPORT_SHA256_HERE'", f'JOB_SHA256 = "{job["payload_sha256"]}"') for line in cell.get("source", [])]
    configured_code = "\n".join("".join(c.get("source", [])) for c in notebook["cells"] if c["cell_type"] == "code")
    require(job["payload_sha256"] in configured_code and "PASTE_TRUSTED_LOCAL_EXPORT_SHA256_HERE" not in configured_code,
            "Frozen notebook job-hash placeholder was not configured")
    save_new(upload / "qwen_components_kaggle.ipynb", notebook)
    with zipfile.ZipFile(output / "kaggle-upload.zip", "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ("job.json", *job["payload"]["execution_files"]): archive.write(upload / name, name)
    preparation["upload_zip"] = pin(output / "kaggle-upload.zip")
    preparation["configured_notebook"] = pin(upload / "qwen_components_kaggle.ipynb")
    save_new(output / "preparation.json", preparation)
    return {"status": "prepared_not_ranked", "split": freeze["split"], "directory": str(output.resolve()), "job_sha256": job["payload_sha256"],
            "upload_zip": str((output / "kaggle-upload.zip").resolve()), "notebook": str((upload / "qwen_components_kaggle.ipynb").resolve()),
            "upload_files": ["job.json", *job["payload"]["execution_files"]],
            "instructions": "Upload the four-file zip as a private Kaggle dataset; import the configured notebook and set only BUNDLE to that dataset folder. Keep draft off; enable GPU and Internet; save one finite version. No gold answers, ledger or keys are uploaded."}


def validate_trace(store, project, trace, question, method, job):
    from tools.evaluate_qwen_pilot import validate_trace as old_anchor_check
    require(trace.get("query_id") == question["id"] and trace.get("query") == question["query"] and trace.get("components") == question["components"], "Trace request binding differs")
    require(trace.get("method") == method and trace.get("method_version") == "lit-rev-engine.project-retrieval.qwen-components.v1." + method,
            "Trace method binding differs")
    require(trace.get("answerability") == trace.get("support_completeness") == "not_assessed" and trace.get("verification") == "human_review_required"
            and canonical(trace.get("profile")) == canonical(PROFILE) and trace.get("parameters", {}).get("profile_sha256") == digest(PROFILE), "Candidate/human-review boundaries differ")
    require(canonical(trace.get("source_manifest")) == canonical(job["source_manifest"]) and trace.get("source_snapshot_sha256") == job["source_snapshot_sha256"], "Trace snapshot differs")
    copy = deepcopy(trace)
    copy["method"] = "bm25_context_blocks"
    copy["method_version"] = "lit-rev-engine.project-retrieval.v3.bm25_context_blocks"
    old_anchor_check(store, project, copy)
    whole = method in {"qwen_kaggle_hybrid", "bm25_context_blocks"}
    require(trace.get("display_order") == ("whole-query-score-descending" if whole else "component-reservations-then-whole-query-fill"), "Trace display-order metadata differs")
    for row in trace["passages"]:
        score = row["score"]
        require(type(score) in (int, float) and math.isfinite(score) and (0 <= score <= 1 if "qwen" in method else score >= 0), "Trace score invalid")
        values = row.get("query_scores", {})
        require(type(values.get("whole")) in (int, float) and values["whole"] == score
                and [r.get("id") for r in values.get("components", [])] == ([] if whole else [c["id"] for c in question["components"]])
                and all(type(r.get("score")) in (int, float) and math.isfinite(r["score"]) and
                        (0 <= r["score"] <= 1 if "qwen" in method else r["score"] >= 0) for r in values.get("components", [])), "Trace component score roles differ")
    groups = trace.get("source_groups", [])
    require(isinstance(groups, list), "Source grouping schema differs")
    for group in groups:
        require(set(group) == {"record_id", "document_id", "document_version", "passage_ranks"} and isinstance(group["passage_ranks"], list)
                and type(group["document_version"]) is int
                and group["passage_ranks"] and all(type(r) is int and 1 <= r <= len(trace["passages"]) for r in group["passage_ranks"]), "Source group budget differs")
        for rank in group["passage_ranks"]:
            row = trace["passages"][rank - 1]
            require(canonical({k: group[k] for k in ("record_id", "document_id", "document_version")}) ==
                    canonical({k: row[k] for k in ("record_id", "document_id", "document_version")}), "Source group launders report identity")
    ranks = [r for group in groups for r in group["passage_ranks"]]
    require(sorted(ranks) == list(range(1, len(trace["passages"]) + 1)), "Source groups enlarge or duplicate display")


def supported(passages, document_id, anchor):
    return any(row["document_id"] == document_id and row["anchor"]["block_id"] == anchor["block_id"]
               and row["anchor"]["start"] <= anchor["start"] < anchor["end"] <= row["anchor"]["end"]
               and row["anchor"]["quote"][anchor["start"] - row["anchor"]["start"]:anchor["end"] - row["anchor"]["start"]] == anchor["quote"] for row in passages)


def assess(trace, question, document_id, *, pool=False):
    passages = trace["passages"] if pool else trace["passages"][:5]
    context = sum(supported(passages, document_id, a) for a in question["context_anchors"])
    row = {"id": question["id"], "answerable": question["answerable"], "returned_candidates": len(passages),
           "context_covered": context, "context_total": len(question["context_anchors"]),
           "source_scoped_hard_negative_candidates": sum(r["document_id"] != document_id for r in passages)}
    if not question["answerable"]: return {**row, "coverage": None, "complete": None}
    coverages = [sum(supported(passages, document_id, a) for a in support) / len(support) for support in question["support_sets"]]
    return {**row, "coverage": max(coverages), "complete": max(coverages) == 1.0, "alternative_coverage": coverages}


def aggregate(rows):
    positives = [r for r in rows if r["answerable"]]
    require(len(positives) == 6 and len(rows) == 8, "Frozen metric denominator differs")
    return {"answerable": 6, "mean_support_coverage": sum(r["coverage"] for r in positives) / 6,
            "complete_positives": sum(r["complete"] for r in positives), "nulls": [r for r in rows if not r["answerable"]]}


def grade(freeze_path, prepared, results_path, results_sha256):
    freeze = verify_freeze(freeze_path)
    sources, questions, counts = validate_data(freeze)
    prepared = Path(prepared)
    preparation = read_json((prepared / "preparation.json").read_bytes())
    fields = {"schema_version", "status", "split", "freeze", "project_id", "document_bindings", "job_sha256", "ledger_sha256", "execution_files", "truth_counts", "upload_zip", "configured_notebook"}
    require(isinstance(preparation, dict) and set(preparation) == fields and type(preparation["schema_version"]) is int and preparation["schema_version"] == 1
            and preparation["status"] == "prepared_not_ranked" and preparation["split"] == freeze["split"]
            and canonical(preparation["freeze"]) == canonical(pin(freeze_path)) and canonical(preparation["truth_counts"]) == canonical(counts), "Preparation differs from prospective freeze")
    require((prepared / "review.sqlite3").is_file() and not (prepared / "review.sqlite3").is_symlink(), "Prepared ledger missing or aliased")
    require(not any(os.path.lexists(prepared / name) for name in ("result.json", "validation.receipt.json")), "Preserve first comparison; this batch has already been graded")
    require(pin(prepared / "kaggle-upload.zip") == preparation["upload_zip"] and pin(prepared / "kaggle-upload/qwen_components_kaggle.ipynb") == preparation["configured_notebook"], "Prepared upload bundle changed")
    from src.review_components.core import read_artifact
    job_envelope = read_artifact(prepared / "kaggle-upload/job.json")
    raw_result = read_artifact(results_path)
    require(job_envelope["payload_sha256"] == preparation["job_sha256"] and raw_result["payload_sha256"] == results_sha256, "Trusted job or saved-run result differs")
    job = job_envelope["payload"]
    expected_questions = [{k: q[k] for k in ("id", "query", "components")} for q in questions]
    require(canonical(job["questions"]) == canonical(expected_questions) and job["scope"] == "included" and job["project_id"] == preparation["project_id"]
            and canonical(job["execution_files"]) == canonical(preparation["execution_files"]), "Prepared job request or helper binding differs")
    with ReviewStore(prepared / "review.sqlite3") as store:
        before = ledger_hash(store)
        require(before == preparation["ledger_sha256"], "Prepared ledger changed")
        project = preparation["project_id"]
        bindings_ok(store, project, sources, preparation["document_bindings"])
        arguments = dict(job_path=prepared / "kaggle-upload/job.json", job_sha256=preparation["job_sha256"], results_path=results_path, results_sha256=results_sha256)
        imported = import_results(store, project, **arguments)
        replay = import_results(store, project, **arguments)
        require(canonical(imported) == canonical(replay) and ledger_hash(store) == before, "Unchanged-result replay or read-only check failed")
        per_method, metrics = {}, {}
        for label, method in METHODS.items():
            traces = imported["traces"] if label == "candidate" else imported["comparators"][label]
            require(isinstance(traces, list) and len(traces) == 8, "Returned frozen question set differs")
            rows = []
            for q, trace in zip(questions, traces, strict=True):
                validate_trace(store, project, trace, q, method, job)
                rows.append(assess(trace, q, preparation["document_bindings"][q["source_id"]]))
            per_method[label], metrics[label] = rows, aggregate(rows)
        pool_rows = []
        require(len(imported["diagnostics"]) == 8, "Pool diagnostics question set differs")
        for q, diagnostic, display in zip(questions, imported["diagnostics"], per_method["candidate"], strict=True):
            require(diagnostic["question_id"] == q["id"] and diagnostic["not_for_display"] is True and diagnostic["pool_budget"] == 20
                    and len(diagnostic["target_pool_passages"]) <= 20 and len(diagnostic["whole_pool_passages"]) <= 20, "Pool budgets or identity differ")
            source_rows = {(r["passage"]["document_id"], r["passage"]["anchor"]["block_id"]): r["passage"] for r in job["candidates"]}
            for key in ("target_pool_passages", "whole_pool_passages"):
                seen = set()
                for rank, row in enumerate(diagnostic[key], 1):
                    identity = row["document_id"], row["anchor"]["block_id"]
                    require(identity in source_rows and identity not in seen and type(row["rank"]) is int and row["rank"] == rank
                            and canonical({k: row.get(k) for k in source_rows[identity]}) == canonical(source_rows[identity])
                            and type(row["score"]) in (int, float) and math.isfinite(row["score"]) and 0 <= row["score"] <= 1,
                            "Pool diagnostic source/own-anchor/rank differs")
                    seen.add(identity)
            pool_row = assess({"passages": diagnostic["target_pool_passages"]}, q, preparation["document_bindings"][q["source_id"]], pool=True)
            pool_rows.append({"id": q["id"], "pool_support": pool_row, "display_support": display,
                              "selection_loss": q["answerable"] and pool_row["coverage"] > display["coverage"]})
        require(ledger_hash(store) == before, "Grading changed the ledger")
        # Receipt is only published after all frozen inputs, traces and truth pass.
        import_results(store, project, receipt_path=prepared / "validation.receipt.json", **arguments)
    target = metrics["candidate"]
    checks = {"support_coverage": target["mean_support_coverage"] >= GATE["min_mean_support_coverage"],
              "complete_positives": target["complete_positives"] >= GATE["min_complete_positives"],
              "exact_anchors_scope_replay_readonly": True, "batch_time": raw_result["payload"]["runtime"]["elapsed_seconds"]["total"] <= GATE["max_batch_seconds"],
              "paid_inference_calls": raw_result["payload"]["runtime"]["paid_inference_calls"] == 0}
    for label in GATE["nonregression_comparators"]:
        checks[label + "_coverage_nonregression"] = target["mean_support_coverage"] >= metrics[label]["mean_support_coverage"]
        checks[label + "_complete_nonregression"] = target["complete_positives"] >= metrics[label]["complete_positives"]
    result = {"schema_version": 1, "status": "passed" if all(checks.values()) else "failed", "split": freeze["split"], "freeze": pin(freeze_path),
              "job_sha256": preparation["job_sha256"], "results_sha256": results_sha256, "checks": checks,
              "methods": {label: {"method": method, "metrics": metrics[label], "per_question": per_method[label]} for label, method in METHODS.items()},
              "pool_diagnostics": pool_rows, "runtime": imported["runtime"], "environment_audit": imported["environment_audit"],
              "distinct_rerank_pairs": imported["distinct_rerank_pairs"], "traces": imported["traces"], "comparators": imported["comparators"],
              "limitations": ["Eight fixed questions from two original main articles per split; no clinical validation.",
                              "CPU fake checks establish plumbing only; actual GPU quality requires saved run evidence.",
                              "Runtime and installer provenance are recorded claims, not cryptographic execution attestation.",
                              "Source-scoped hard negatives are other-article candidates, not an automatic semantic false-evidence verdict.",
                              "Candidate attribution does not assess source answerability or verify complete evidence."]}
    save_new(prepared / "result.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare"); prep.add_argument("--output", required=True)
    graded = commands.add_parser("grade")
    graded.add_argument("--prepared", required=True); graded.add_argument("--results", required=True); graded.add_argument("--results-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        result = prepare(args.freeze, args.output) if args.command == "prepare" else grade(args.freeze, args.prepared, args.results, args.results_sha256)
        print(canonical(result))
        return 2 if result["status"] == "failed" else 0
    except (ValueError, OSError, AssertionError, sqlite3.Error, KeyError, TypeError) as error:
        print("Component evaluation stopped: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
