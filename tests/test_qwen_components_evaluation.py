"""Prospective harness attack checks using authored CPU fixtures, never medical ranking."""

from copy import deepcopy
import builtins
import hashlib
import json
from pathlib import Path
import shutil
import socket
import zipfile

import pytest

from src.review.qwen import canonical
from src.review.store import ReviewStore
from src.review_components import PROFILE
from tools import evaluate_qwen_components as evaluation
from test_qwen_components import envelope, fingerprint, save, synthetic_results

PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def forbid_network_credentials(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Component harness attempted model, paid network or credential loading")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr("src.review.qwen.api_key_from_env", denied)
    monkeypatch.setattr("src.review.qwen.QwenClient.__init__", denied)


def fixture_data(root, split="development"):
    source_dir = root / f"tests/fixtures/qwen_components_{split}_sources"
    gold_dir = root / f"tests/fixtures/qwen_components_{split}_gold"
    source_dir.mkdir(parents=True); gold_dir.mkdir(parents=True)
    sources, blocks = [], []
    for alias in ("authored_a", "authored_b"):
        doi = "10.1111/" + alias
        xml = ('<article xmlns:xlink="http://www.w3.org/1999/xlink"><front><article-meta><article-id pub-id-type="doi">' + doi +
               '</article-id><title-group><article-title>Synthetic ' + alias + '</article-title></title-group>' +
               '<permissions><license xlink:href="https://creativecommons.org/licenses/by/4.0/"><license-p>Authored CPU fixture.</license-p></license></permissions></article-meta></front>' +
               '<body><sec><title>Materials and methods</title><p>Adults n=120 randomized with reference method; no pediatric outcomes. Unicode α 🧪.</p></sec>' +
               '<sec><title>Results</title><p>Adult symptom difference −3.1 with confidence interval −4.8 to −1.4 at 12 months.</p></sec></body></article>').encode()
        path = source_dir / (alias + ".xml"); path.write_bytes(xml)
        _, own, _ = evaluation.original_blocks(xml, alias)
        blocks.extend(own)
        sources.append({"id": alias, "file": path.name, "doi": doi, "title": "Synthetic " + alias,
                        "source_sha256": hashlib.sha256(xml).hexdigest(), "size_bytes": len(xml), "block_count": len(own),
                        "canonical_blocks_sha256": evaluation.digest(own), "parser_id": "lit-rev-engine.source.v1.jats_xml",
                        "publisher_xml_url": "https://example.test/" + alias + ".xml", "version_label": "Authored test v1"})
    source_manifest = {"schema_version": 1, "split": split, "sources": sources}
    (source_dir / "manifest.json").write_text(canonical(source_manifest))
    def anchor(block):
        return {"source_id": block["source_id"], "block_id": block["block_id"], "source_path": block["source_path"],
                "block_sha256": block["sha256"], "start": 0, "end": len(block["text"]), "quote": block["text"]}
    questions = []
    for i in range(8):
        alias = sources[(i % 2)]["id"]
        own = [b for b in blocks if b["source_id"] == alias]
        positive = i < 6
        questions.append({"id": f"authored-q{i}", "source_id": alias, "query": "adult reference symptom difference interval" if positive else "pediatric adverse productivity",
                          "components": [{"id": "population", "query": "adult reference randomized"}, {"id": "outcome", "query": "symptom difference interval"}],
                          "answerable": positive, "quantitative": positive, "necessary_and": positive,
                          "category": "authored_fixture", "expected_answer": "Authored known result." if positive else None,
                          "support_sets": [[anchor(own[1]), anchor(own[2])]] if positive else [],
                          "context_anchors": [] if positive else [anchor(own[1])], "null_reason": None if positive else "Source-scoped authored absence."})
    (gold_dir / "blocks.json").write_text(canonical({"schema_version": 1, "blocks": blocks}))
    (gold_dir / "questions.json").write_text(canonical({"schema_version": 1, "questions": questions}))
    (gold_dir / "manifest.json").write_text(canonical({"schema_version": 1, "split": split, "source_manifest": evaluation.pin(source_dir / "manifest.json"),
        "prospective": {"truth_status": "accepted_independent_source_first_evaluation", "rankings_observed": 0, "paid_inference_calls": 0, "coordinator_confirmation_qa_blind": split == "confirmation"},
        "files": {name: evaluation.pin(gold_dir / name) for name in ("blocks.json", "questions.json")}}))


@pytest.fixture
def prospective(tmp_path, monkeypatch):
    root = tmp_path / "authored-repository"
    root.mkdir()
    historical = json.loads((PROJECT / "docs/qwen-kaggle-freeze-v2.json").read_text())
    for name in set(evaluation.REQUIRED) | set(historical["files"]):
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True)
        original = PROJECT / name
        path.write_bytes(original.read_bytes() if original.is_file() else ("Prospectively pinned CPU placeholder " + name).encode())
    fixture_data(root)
    files = {str(p.relative_to(root)): evaluation.pin(p) for p in root.rglob("*") if p.is_file()}
    freeze = {"schema_version": 1, "status": "frozen_before_first_components_ranking", "split": "development", "ranking_runs_before_freeze": 0,
              "profile": deepcopy(PROFILE), "gate": deepcopy(evaluation.GATE), "contract_selection_pin": evaluation.pin(root / "docs/qwen-components-interface-selection-v1.json"),
              "source_dir": "tests/fixtures/qwen_components_development_sources", "source_manifest": "tests/fixtures/qwen_components_development_sources/manifest.json",
              "questions_file": "tests/fixtures/qwen_components_development_gold/questions.json", "files": files}
    path = root / "prospective.json"; path.write_text(canonical(freeze))
    monkeypatch.setattr(evaluation, "ROOT", root)
    return root, path, freeze


def prepared(prospective, tmp_path):
    _, freeze_path, _ = prospective
    output = tmp_path / "prepared"
    response = evaluation.prepare(freeze_path, output)
    job = json.loads((output / "kaggle-upload/job.json").read_text())
    results_path = tmp_path / "synthetic-saved-result.json"
    wrapped = save(results_path, synthetic_results(job))
    return output, response, results_path, wrapped


@pytest.mark.parametrize("defect", ["schema_bool", "rank_bool", "rank_posthoc", "status", "split", "profile_bool", "profile_revision", "gate_bool", "gate_relax", "missing_old", "missing_new", "missing_truth", "missing_xml", "missing_worker", "changed_old", "changed_new", "selection_pin", "selection_seen", "contract_changed", "absolute", "parent", "symlink", "extra_pin_escape", "pin_bool"])
def test_freeze_refuses_posthoc_or_incomplete_code_source_selection_and_acceptance(prospective, tmp_path, defect):
    root, path, freeze = prospective
    if defect == "schema_bool": freeze["schema_version"] = True
    elif defect == "rank_bool": freeze["ranking_runs_before_freeze"] = False
    elif defect == "rank_posthoc": freeze["ranking_runs_before_freeze"] = 1
    elif defect == "status": freeze["status"] = "ranked"
    elif defect == "split": freeze["split"] = "confirmation"
    elif defect == "profile_bool": freeze["profile"]["schema_version"] = True
    elif defect == "profile_revision": freeze["profile"]["embedding_revision"] = "main"
    elif defect == "gate_bool": freeze["gate"]["paid_inference_calls"] = False
    elif defect == "gate_relax": freeze["gate"]["min_mean_support_coverage"] = .8
    elif defect == "missing_old": freeze["files"].pop("src/review/store.py")
    elif defect == "missing_new": freeze["files"].pop("src/review_components/core.py")
    elif defect == "missing_truth": freeze["files"].pop(freeze["questions_file"])
    elif defect == "missing_xml": freeze["files"].pop(freeze["source_dir"] + "/authored_a.xml")
    elif defect == "missing_worker": freeze["files"].pop("tests/test_qwen_components_worker.py")
    elif defect == "changed_old": (root / "src/review/store.py").write_text("changed")
    elif defect == "changed_new": (root / "src/review_components/core.py").write_text("changed")
    elif defect == "selection_pin": freeze["contract_selection_pin"]["sha256"] = "0" * 64
    elif defect == "selection_seen":
        target = root / "docs/qwen-components-interface-selection-v1.json"
        value = json.loads(target.read_text()); value["confirmation_questions_seen_by_coordinator"] = True
        target.write_text(canonical(value)); freeze["contract_selection_pin"] = evaluation.pin(target); freeze["files"][str(target.relative_to(root))] = evaluation.pin(target)
    elif defect == "contract_changed": (root / "docs/qwen-components-contract-v1.md").write_text("new method")
    elif defect == "absolute": freeze["questions_file"] = str(root / freeze["questions_file"])
    elif defect == "parent": freeze["questions_file"] = "../questions.json"
    elif defect == "symlink":
        target = root / freeze["questions_file"]; outside = tmp_path / "outside.json"
        outside.write_bytes(target.read_bytes()); target.unlink(); target.symlink_to(outside)
    elif defect == "extra_pin_escape": freeze["files"]["../outside"] = {"sha256": "0" * 64, "size_bytes": 1}
    elif defect == "pin_bool": freeze["files"]["src/review_components/core.py"]["size_bytes"] = True
    path.write_text(canonical(freeze))
    with pytest.raises((ValueError, OSError)): evaluation.verify_freeze(path)


def test_prepare_uploads_only_exact_four_files_and_compiled_notebook_actual_job_hash(prospective, tmp_path, monkeypatch):
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in {"torch", "transformers", "sentence_transformers"}: pytest.fail("Preparation loaded heavy libraries")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    output, response, _, _ = prepared(prospective, tmp_path)
    job = json.loads((output / "kaggle-upload/job.json").read_text())
    assert response["job_sha256"] == job["payload_sha256"]
    assert "BUNDLE" in response["instructions"]
    assert set(response["upload_files"]) == {"job.json", "component_core.py", "qwen_kaggle_environment.py", "qwen_components_kaggle_runner.py"}
    with zipfile.ZipFile(output / "kaggle-upload.zip") as archive:
        assert set(archive.namelist()) == set(response["upload_files"])
        for name in archive.namelist(): assert archive.read(name) == (output / "kaggle-upload" / name).read_bytes()
    notebook = json.loads((output / "kaggle-upload/qwen_components_kaggle.ipynb").read_text())
    code = "\n".join("".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == "code")
    assert response["job_sha256"] in code and "PASTE_TRUSTED_LOCAL_EXPORT_SHA256_HERE" not in code
    for c in notebook["cells"]:
        if c["cell_type"] == "code": compile("".join(c["source"]), "configured-cell", "exec")
    uploaded = canonical(job)
    assert all(key not in uploaded for key in ("expected_answer", "support_sets", "context_anchors", "null_reason", "DEEPINFRA_API_KEY"))
    prep = json.loads((output / "preparation.json").read_text())
    assert prep["status"] == "prepared_not_ranked" and "reference" not in prep
    with pytest.raises(ValueError): evaluation.prepare(prospective[1], output)


def test_grade_independently_recomputes_three_nonregression_gates_and_preserves_first_fake_result(prospective, tmp_path):
    output, _, results, wrapped = prepared(prospective, tmp_path)
    with ReviewStore(output / "review.sqlite3") as store: before = fingerprint(store)
    graded = evaluation.grade(prospective[1], output, results, wrapped["payload_sha256"])
    assert set(graded["methods"]) == {"candidate", "whole_qwen", "whole_lexical", "component_lexical"}
    for name in ("whole_qwen", "whole_lexical", "component_lexical"):
        assert name + "_coverage_nonregression" in graded["checks"] and name + "_complete_nonregression" in graded["checks"]
    assert graded["status"] == ("passed" if all(graded["checks"].values()) else "failed")
    assert all(row["coverage"] is None and row["complete"] is None for row in graded["methods"]["candidate"]["metrics"]["nulls"])
    assert len(graded["pool_diagnostics"]) == 8
    with ReviewStore(output / "review.sqlite3") as store: assert fingerprint(store) == before
    first = (output / "result.json").read_bytes()
    with pytest.raises(ValueError, match="first comparison"):
        evaluation.grade(prospective[1], output, results, wrapped["payload_sha256"])
    assert (output / "result.json").read_bytes() == first


@pytest.mark.parametrize("defect", ["missing_db", "ledger_changed", "project", "binding", "extra_binding", "job_query", "job_hash", "results_hash", "upload_zip", "notebook", "prep_extra", "prep_schema_bool", "counts", "reference_forgery", "prior_receipt", "prior_grade"])
def test_preparation_or_saved_result_corruption_rejected_before_receipt(prospective, tmp_path, defect):
    output, _, results, wrapped = prepared(prospective, tmp_path)
    prep_path = output / "preparation.json"; prep = json.loads(prep_path.read_text())
    result_sha = wrapped["payload_sha256"]
    if defect == "missing_db": (output / "review.sqlite3").unlink()
    elif defect == "ledger_changed":
        with ReviewStore(output / "review.sqlite3") as store: store.create_project("foreign", "systematic", "changed")
    elif defect == "project": prep["project_id"] = "wrong"
    elif defect == "binding": prep["document_bindings"]["authored_a"] = prep["document_bindings"]["authored_b"]
    elif defect == "extra_binding": prep["document_bindings"]["extra"] = "bad"
    elif defect == "job_query":
        path = output / "kaggle-upload/job.json"; job = json.loads(path.read_text())["payload"]
        job["questions"][0]["query"] += " changed"; prep["job_sha256"] = save(path, job)["payload_sha256"]
    elif defect == "job_hash": prep["job_sha256"] = "0" * 64
    elif defect == "results_hash": result_sha = "0" * 64
    elif defect == "upload_zip": (output / "kaggle-upload.zip").write_bytes(b"changed")
    elif defect == "notebook": (output / "kaggle-upload/qwen_components_kaggle.ipynb").write_text("changed")
    elif defect == "prep_extra": prep["unexpected"] = 1
    elif defect == "prep_schema_bool": prep["schema_version"] = True
    elif defect == "counts": prep["truth_counts"]["necessary_methods_results_and"] = 0
    elif defect == "reference_forgery": prep["reference"] = {"metrics": {"mean_support_coverage": 0}}
    elif defect == "prior_receipt": (output / "validation.receipt.json").write_text("first saved import")
    elif defect == "prior_grade": (output / "result.json").write_text("first saved grade")
    prep_path.write_text(canonical(prep))
    with pytest.raises((ValueError, OSError, KeyError)): evaluation.grade(prospective[1], output, results, result_sha)
    if defect != "prior_receipt": assert not (output / "validation.receipt.json").exists()
    if defect != "prior_grade": assert not (output / "result.json").exists()


def test_failed_quality_or_operational_gate_is_saved_and_cannot_be_relabelled(prospective, tmp_path):
    output, _, path, wrapped = prepared(prospective, tmp_path)
    payload = wrapped["payload"]; payload["runtime"]["elapsed_seconds"]["total"] = 1801.
    changed = save(path, payload)
    grade = evaluation.grade(prospective[1], output, path, changed["payload_sha256"])
    assert grade["status"] == "failed" and grade["checks"]["batch_time"] is False
    payload["runtime"]["elapsed_seconds"]["total"] = 1.
    changed = save(path, payload)
    with pytest.raises(ValueError): evaluation.grade(prospective[1], output, path, changed["payload_sha256"])
    assert json.loads((output / "result.json").read_text())["status"] == "failed"


@pytest.mark.parametrize("defect", ["unicode_quote", "bool_offset", "wrong_hash", "wrong_path", "wrong_source", "duplicate_span", "empty_or", "zero_positive", "null_answer", "null_reason", "source_xml", "licence", "canonical_blocks", "body_methods_results"])
def test_original_truth_bounds_roles_and_positive_null_denominators_fail_closed(prospective, defect):
    root, _, freeze = prospective
    questions_path = root / freeze["questions_file"]
    data = json.loads(questions_path.read_text())
    q = data["questions"][0]; anchor = q["support_sets"][0][0]
    if defect == "unicode_quote": anchor["quote"] += " altered"
    elif defect == "bool_offset": anchor["start"] = False
    elif defect == "wrong_hash": anchor["block_sha256"] = "0" * 64
    elif defect == "wrong_path": anchor["source_path"] = "/wrong"
    elif defect == "wrong_source": anchor["source_id"] = "authored_b"
    elif defect == "duplicate_span": q["support_sets"][0].append(deepcopy(anchor))
    elif defect == "empty_or": q["support_sets"].append([])
    elif defect == "zero_positive": q["answerable"] = False; q["support_sets"] = []; q["expected_answer"] = None; q["null_reason"] = "changed"
    elif defect == "null_answer": data["questions"][-1]["expected_answer"] = "forged answer"
    elif defect == "null_reason": data["questions"][-1]["null_reason"] = None
    elif defect == "source_xml": (root / freeze["source_dir"] / "authored_a.xml").write_text("changed")
    elif defect == "licence":
        path = root / freeze["source_dir"] / "authored_a.xml"; path.write_text(path.read_text().replace("licenses/by/4.0/", "licenses/all-rights-reserved/"))
    elif defect == "canonical_blocks": (questions_path.parent / "blocks.json").write_text('{"blocks":[]}')
    elif defect == "body_methods_results":
        for question in data["questions"][:6]: question["support_sets"] = [[deepcopy(question["support_sets"][0][0])]]
    questions_path.write_text(canonical(data))
    manifest_path = questions_path.parent / "manifest.json"; manifest = json.loads(manifest_path.read_text())
    for name in manifest["files"]: manifest["files"][name] = evaluation.pin(questions_path.parent / name)
    manifest_path.write_text(canonical(manifest))
    with pytest.raises((ValueError, KeyError)): evaluation.validate_data(freeze)


def test_assessment_never_credits_context_other_source_or_component_labels():
    a = {"block_id": "own", "start": 0, "end": 5, "quote": "truth"}
    q = {"id": "q", "answerable": True, "support_sets": [[a]], "context_anchors": []}
    passage = {"rank": 1, "document_id": "d", "anchor": {"block_id": "other", "start": 0, "end": 5, "quote": "truth"},
               "scoring_context": [{"anchor": a}], "selection_reasons": [{"kind": "component_selection", "component_id": "answer"}]}
    assert evaluation.assess({"passages": [passage]}, q, "d")["coverage"] == 0.
    passage["anchor"] = a; passage["document_id"] = "wrong"
    assert evaluation.assess({"passages": [passage]}, q, "d")["coverage"] == 0.
    null = {**q, "answerable": False, "support_sets": [], "context_anchors": [a]}
    passage["document_id"] = "d"
    row = evaluation.assess({"passages": [passage]}, null, "d")
    assert row["coverage"] is row["complete"] is None and row["context_covered"] == 1


@pytest.mark.parametrize("defect", ["none", "missing", "bool_schema", "seen", "rank_bool", "rank_after", "changed", "profile", "reason", "dev_freeze", "dev_result", "status_lie", "status_checks", "result_split", "result_hash", "file_escape", "missing_pin"])
def test_confirmation_requires_factual_method_selection_before_question_parsing(prospective, monkeypatch, defect):
    root, _, development = prospective
    dev_path = root / evaluation.DEVELOPMENT_FREEZE; dev_path.write_text(canonical(development))
    result_path = root / evaluation.DEVELOPMENT_RESULT; result_path.parent.mkdir(parents=True)
    original_result = {"schema_version": 1, "split": "development", "status": "failed", "checks": {"support_coverage": False},
                       "freeze": evaluation.pin(dev_path), "job_sha256": "a" * 64, "results_sha256": "b" * 64}
    result_path.write_text(canonical(original_result))
    fixture_data(root, "confirmation")
    receipt = {"schema_version": 1, "status": "selected_after_development_before_confirmation", "profile_sha256": evaluation.digest(PROFILE),
               "development_freeze_pin": evaluation.pin(dev_path), "development_result_pin": evaluation.pin(result_path),
               "development_result_file": evaluation.DEVELOPMENT_RESULT, "development_status": "failed",
               "confirmation_questions_seen_by_coordinator": False, "confirmation_rankings_before_selection": 0,
               "method_changed_after_development": False, "selection_reason": "Synthetic CPU method-selection boundary test."}
    selection = root / evaluation.METHOD_SELECTION
    if defect == "bool_schema": receipt["schema_version"] = True
    elif defect == "seen": receipt["confirmation_questions_seen_by_coordinator"] = True
    elif defect == "rank_bool": receipt["confirmation_rankings_before_selection"] = False
    elif defect == "rank_after": receipt["confirmation_rankings_before_selection"] = 1
    elif defect == "changed": receipt["method_changed_after_development"] = True
    elif defect == "profile": receipt["profile_sha256"] = "0" * 64
    elif defect == "reason": receipt["selection_reason"] = " "
    elif defect == "dev_freeze": receipt["development_freeze_pin"]["sha256"] = "0" * 64
    elif defect == "dev_result": receipt["development_result_pin"]["sha256"] = "0" * 64
    elif defect == "status_lie": receipt["development_status"] = "passed"
    elif defect in {"status_checks", "result_split", "result_hash"}:
        if defect == "status_checks": original_result["checks"] = {"support_coverage": True}
        elif defect == "result_split": original_result["split"] = "confirmation"
        else: original_result["results_sha256"] = "invalid"
        result_path.write_text(canonical(original_result)); receipt["development_result_pin"] = evaluation.pin(result_path)
    elif defect == "file_escape": receipt["development_result_file"] = "../private/result.json"
    selection.write_text(canonical(receipt))
    freeze = {**deepcopy(development), "split": "confirmation", "source_dir": "tests/fixtures/qwen_components_confirmation_sources",
              "source_manifest": "tests/fixtures/qwen_components_confirmation_sources/manifest.json", "questions_file": "tests/fixtures/qwen_components_confirmation_gold/questions.json",
              "method_selection_pin": evaluation.pin(selection),
              "files": {str(p.relative_to(root)): evaluation.pin(p) for p in root.rglob("*") if p.is_file() and p.name != "prospective.json"}}
    if defect == "missing_pin": freeze["files"].pop(evaluation.METHOD_SELECTION)
    path = root / "confirmation.json"; path.write_text(canonical(freeze))
    if defect == "missing": selection.unlink()
    def no_truth(*args, **kwargs): pytest.fail("Confirmation QA parsed before method-selection validation")
    monkeypatch.setattr(evaluation, "validate_data", no_truth)
    if defect == "none": assert evaluation.verify_freeze(path)["split"] == "confirmation"
    else:
        with pytest.raises((ValueError, OSError)): evaluation.prepare(path, root / "unused-preparation")


@pytest.mark.parametrize("defect", ["pending", "rank_bool", "rank_after", "paid_bool", "paid_after"])
def test_prepare_requires_accepted_independent_truth_before_creating_ledger(prospective, tmp_path, defect):
    root, path, freeze = prospective
    manifest_path = root / freeze["questions_file"]; manifest_path = manifest_path.with_name("manifest.json")
    manifest = json.loads(manifest_path.read_text())
    if defect == "pending": manifest["prospective"]["truth_status"] = "pending_independent_source_first_evaluation"
    elif defect == "rank_bool": manifest["prospective"]["rankings_observed"] = False
    elif defect == "rank_after": manifest["prospective"]["rankings_observed"] = 1
    elif defect == "paid_bool": manifest["prospective"]["paid_inference_calls"] = False
    else: manifest["prospective"]["paid_inference_calls"] = 1
    manifest_path.write_text(canonical(manifest))
    freeze["files"][str(manifest_path.relative_to(root))] = evaluation.pin(manifest_path)
    path.write_text(canonical(freeze))
    output = tmp_path / "unprepared"
    with pytest.raises(ValueError): evaluation.prepare(path, output)
    assert not output.exists()


@pytest.mark.parametrize("defect", ["own_quote", "context_quote", "source_group", "source_group_version", "score_bool", "component_score", "query_order", "semantic_verified", "pool_own_quote", "pool_duplicates", "comparator_method", "comparator_extra"])
def test_corrupt_candidate_comparator_or_pool_trace_fails_before_receipt(prospective, tmp_path, monkeypatch, defect):
    output, _, path, wrapped = prepared(prospective, tmp_path)
    original = evaluation.import_results
    def corrupted(*args, **kwargs):
        value = original(*args, **kwargs)
        trace = value["traces"][0]; passage = trace["passages"][0]
        if defect == "own_quote": passage["anchor"]["quote"] += "changed"
        elif defect == "context_quote":
            passage["scoring_context"] = [{"anchor": {"block_id": passage["anchor"]["block_id"], "start": 0, "end": 1, "quote": "X"}, "locator": passage["locator"]}]
        elif defect == "source_group": trace["source_groups"][0]["document_id"] = "another-report"
        elif defect == "source_group_version": trace["source_groups"][0]["document_version"] = True
        elif defect == "score_bool": passage["score"] = True
        elif defect == "component_score": passage["query_scores"]["components"][0]["score"] = True
        elif defect == "query_order": value["traces"].reverse()
        elif defect == "semantic_verified": trace["support_completeness"] = "verified"
        elif defect == "pool_own_quote": value["diagnostics"][0]["target_pool_passages"][0]["anchor"]["quote"] += "changed"
        elif defect == "pool_duplicates": value["diagnostics"][0]["target_pool_passages"].append(deepcopy(value["diagnostics"][0]["target_pool_passages"][0]))
        elif defect == "comparator_method": value["comparators"]["whole_qwen"][0]["method"] = "qwen_components_hybrid"
        else: value["comparators"]["component_lexical"][0]["passages"].append(deepcopy(value["comparators"]["component_lexical"][0]["passages"][0]))
        return value
    monkeypatch.setattr(evaluation, "import_results", corrupted)
    with pytest.raises((ValueError, AssertionError, KeyError)): evaluation.grade(prospective[1], output, path, wrapped["payload_sha256"])
    assert not (output / "validation.receipt.json").exists() and not (output / "result.json").exists()
