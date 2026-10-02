"""Independent whole-block software gates. No medical query execution."""

from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
from xml.sax.saxutils import escape

import pytest

from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.store import ReviewStore
from tools.evaluate_medical_retrieval import assess_question, digest_json
from tools import evaluate_medical_retrieval_v3 as evaluator


ROOT = Path(__file__).resolve().parents[1]
STOP_WORDS = sorted("a an and are as at be been by did do does for from had has have how in is it its of on or that the their there these this to was were what when where which who with would".split())
PARAMETERS = {"tokenizer_id": "unicode-casefold-word-v1", "stop_words": STOP_WORDS,
              "k1": 1.2, "b": .75, "context_rule": "preceding-paragraph-same-xml-parent-v1",
              "context_max_words": 80, "passage_unit": "block"}
REFERENCE_PARAMETERS = {key: value for key, value in PARAMETERS.items() if key != "passage_unit"}
REFERENCE_PARAMETERS.update(window_words=200, overlap_words=40)
METHOD = "bm25_context_blocks"


@pytest.fixture(autouse=True)
def no_live_dependencies(monkeypatch):
    def denied(*args, **kwargs): pytest.fail("Whole-block retrieval attempted network or real sleep")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr("time.sleep", denied)


def fingerprint(store): return hashlib.sha256("\n".join(store._connection.iterdump()).encode()).hexdigest()


def report(store, project, title="Invented whole-block report", *, eligible=True, doi=None, pmid=None):
    store.import_records(project, SearchRunSpec("Independent whole-block input"), [BibliographicRecord(title=title, doi=doi, pmid=pmid)])
    rid = store.list_records(project)[-1]["id"]
    if eligible:
        store.record_decision(project, rid, "title_abstract", "include", "Screener")
        store.set_full_text_status(project, rid, "retrieved", "Custodian")
        store.record_decision(project, rid, "full_text", "include", "Screener")
    return rid


def attach(store, project, rid, body, *, front=""):
    return store.attach_document(project, rid, ("<article>" + front + "<body>" + body + "</body></article>").encode(), "jats_xml", "Custodian", "Exact invented XML")


def paragraph(text): return "<p>" + escape(text) + "</p>"


def assert_trace(store, project, trace, scope="included", top_k=100):
    assert trace["project_id"] == project and trace["scope"] == scope and trace["top_k"] == top_k
    assert trace["schema_version"] == 1 and trace["status"] == "candidate_passages"
    assert trace["method"] == METHOD and trace["method_version"] == "lit-rev-engine.project-retrieval.v3." + METHOD
    assert trace["parameters"] == PARAMETERS and trace["source_snapshot_sha256"] == digest_json(trace["source_manifest"])
    active = {doc["id"]: doc for doc in store.list_documents(project) if doc["active"]}
    records = {row["id"]: row for row in store.list_records(project)}
    selected = {row["document_id"]: row for row in trace["source_manifest"]}
    blocks = {}
    for did, manifest in selected.items():
        metadata = active[did]
        assert manifest["record_id"] == metadata["record_id"]
        assert all(manifest[key] == metadata[key] for key in ("version", "format", "source_sha256", "blocks_sha256", "parser_id", "parser_metadata", "source_identifiers", "source_url", "version_label"))
        assert manifest["full_text_state"] == records[manifest["record_id"]]["full_text_state"]
        if scope == "included": assert manifest["full_text_state"] == "include"
        blocks[did] = store.get_source_blocks(project, did)
    assert trace["indexed_passages"] == sum(bool(block["text"].strip()) for values in blocks.values() for block in values)
    seen = set()
    for rank, candidate in enumerate(trace["passages"], 1):
        did = candidate["document_id"]
        assert candidate["project_id"] == project and did in selected
        assert candidate["rank"] == rank and candidate["score"] > 0 and math.isfinite(candidate["score"])
        manifest = selected[did]
        assert candidate["document_version"] == manifest["version"]
        assert all(candidate[key] == manifest[key] for key in ("record_id", "source_sha256", "blocks_sha256", "parser_id", "full_text_state", "study_link_state", "study_ids"))
        block = next(block for block in blocks[did] if block["id"] == candidate["anchor"]["block_id"])
        assert (did, block["id"]) not in seen and block["text"].strip()
        seen.add((did, block["id"]))
        assert candidate["anchor"] == {"block_id": block["id"], "start": 0, "end": len(block["text"]), "quote": block["text"]}
        assert candidate["locator"] == block["locator"]
        expected_context = []
        if manifest["format"] == "jats_xml" and block["locator"]["tag"] in ("p", "table-wrap"):
            previous = [value for value in blocks[did] if value["ordinal"] < block["ordinal"] and value["locator"].get("tag") == "p" and value["locator"]["path"].rsplit("/", 1)[0] == block["locator"]["path"].rsplit("/", 1)[0]]
            if previous:
                source = previous[-1]
                words = list(re.finditer(r"\S+", source["text"]))
                if words:
                    start, end = words[max(0, len(words) - 80)].start(), words[-1].end()
                    expected_context = [{"anchor": {"block_id": source["id"], "start": start, "end": end, "quote": source["text"][start:end]}, "locator": source["locator"]}]
        assert candidate["scoring_context"] == expected_context


def test_literal_full_block_bm25_tf_df_lengths_and_context_once(tmp_path):
    long_text = " ".join(["filler"] * 400 + ["needle"])
    with ReviewStore(tmp_path / "review.sqlite3") as store:
        project = store.create_project("Whole-block math", "scoping", "Literal scores?")["id"]
        attach(store, project, report(store, project), "<sec><p>needle needle</p>" + paragraph(long_text) + "</sec>")
        before = fingerprint(store)
        trace = store.search_sources(project, "needle needle", method=METHOD, top_k=100)
        assert_trace(store, project, trace)
        assert trace["indexed_passages"] == trace["matched_passages"] == 2
        # Two complete augmented representations: own lengths 2/401; context gives 2/403.
        # N=2, DF=2, average=202.5; needle TF is 2/3, with the suffix added once.
        expected = {"needle needle": math.log(1.2) * 4.4 / (2 + 1.2 * (.25 + .75 * 2 / 202.5)),
                    long_text: math.log(1.2) * 6.6 / (3 + 1.2 * (.25 + .75 * 403 / 202.5))}
        for row in trace["passages"]: assert row["score"] == pytest.approx(expected[row["anchor"]["quote"]], rel=1e-12)
        assert store.search_sources(project, "needle", method=METHOD, top_k=100)["passages"] == trace["passages"]
        assert fingerprint(store) == before and store.list_evidence(project) == []


@pytest.mark.parametrize("text", [" \r\n\tneedle\r\n α e\u0301 é 😀 \t", "\ufeff \r\n" + " ".join(["needle"] * 401) + "\r\n \t"])
def test_complete_txt_includes_padding_bom_unicode_and_long_text(tmp_path, text):
    with ReviewStore(tmp_path / "review.sqlite3") as store:
        project = store.create_project("Padded text", "scoping", "Exact text?")["id"]
        doc = store.attach_document(project, report(store, project), text.encode(), "txt", "Custodian", "Exact text")
        trace = store.search_sources(project, "needle", method=METHOD, top_k=100)
        assert_trace(store, project, trace)
        assert trace["indexed_passages"] == trace["matched_passages"] == 1
        canonical = text.removeprefix("\ufeff")  # Frozen utf-8-sig decoding strips only the leading BOM.
        assert store.get_document_bytes(project, doc["id"]) == text.encode()
        assert trace["passages"][0]["anchor"] == {"block_id": "text:1", "start": 0, "end": len(canonical), "quote": canonical}
        assert trace["passages"][0]["document_id"] == doc["id"] and trace["passages"][0]["scoring_context"] == []


def test_pdf_uses_complete_physical_pages_and_skips_blank_page_only(tmp_path):
    fixtures = json.loads((ROOT / "tests/fixtures/evidence/manifest.json").read_text())["fixtures"]
    truth = next(row for row in fixtures if row["alias"] == "pdf_three_pages")
    with ReviewStore(tmp_path / "review.sqlite3") as store:
        project = store.create_project("Physical pages", "scoping", "Blank page?")["id"]
        store.attach_document(project, report(store, project), (ROOT / "tests/fixtures/evidence" / truth["file"]).read_bytes(), "pdf", "Custodian", "Three exact physical pages")
        trace = store.search_sources(project, "physical", method=METHOD, top_k=100)
        assert_trace(store, project, trace)
        assert trace["indexed_passages"] == 2
        assert trace["matched_passages"] == 2
        one_match = store.search_sources(project, "fixture", method=METHOD, top_k=100)
        assert one_match["indexed_passages"] == 2 and one_match["matched_passages"] == 1
        assert {row["anchor"]["block_id"] for row in trace["passages"]} == {"pdf:page:1", "pdf:page:3"}
        for row in trace["passages"]:
            block = next(block for block in truth["expected_blocks"] if block["id"] == row["anchor"]["block_id"])
            assert row["anchor"] == {"block_id": block["id"], "start": 0, "end": len(block["text"]), "quote": block["text"]}
            assert row["locator"] == block["locator"] and row["scoring_context"] == []


def test_full_long_jats_paragraph_and_table_preserve_every_row_foot_and_suffix(tmp_path):
    words = [f"paragraph{number}" for number in range(350)]
    rows = [(f"row{number}", f"value{number}") for number in range(120)]
    table = "<table-wrap><label>Table 42</label><caption><p>Invented exact table</p></caption><table><tr><th>Group</th><th>Value</th></tr>" + "".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in rows) + "</table><table-wrap-foot><p>Exact table foot</p></table-wrap-foot></table-wrap>"
    expected_table = "Table 42\nInvented exact table\nGroup\tValue\n" + "\n".join(a + "\t" + b for a, b in rows) + "\nExact table foot"
    with ReviewStore(tmp_path / "review.sqlite3") as store:
        project = store.create_project("Complete long XML", "scoping", "Whole tables?")["id"]
        attach(store, project, report(store, project), "<sec>" + paragraph(" ".join(words)) + table + "</sec>")
        trace = store.search_sources(project, "paragraph0 row0 row119 foot", method=METHOD, top_k=100)
        assert_trace(store, project, trace)
        assert trace["indexed_passages"] == trace["matched_passages"] == 2
        full_table = next(row for row in trace["passages"] if row["locator"]["tag"] == "table-wrap")
        assert full_table["anchor"]["quote"] == expected_table
        assert full_table["scoring_context"][0]["anchor"]["quote"] == " ".join(words[-80:])
        assert "paragraph0" not in full_table["scoring_context"][0]["anchor"]["quote"]
        assert any(row["anchor"]["quote"] == " ".join(words) for row in trace["passages"])


@pytest.mark.parametrize("text", ["  the and \r\n", "!!!\r\n"])
def test_nonblank_blocks_are_indexed_even_when_all_tokens_are_filtered(tmp_path, text):
    with ReviewStore(tmp_path / "review.sqlite3") as store:
        project = store.create_project("Tokenless block", "scoping", "Nonblank index?")["id"]
        store.attach_document(project, report(store, project), text.encode(), "txt", "Custodian", "Exact")
        for query in ("needle", "the and"):
            trace = store.search_sources(project, query, method=METHOD, top_k=100)
            assert_trace(store, project, trace)
            assert trace["indexed_passages"] == 1 and trace["matched_passages"] == 0 and trace["passages"] == []


def test_context_only_full_table_cannot_satisfy_own_quote_support(tmp_path):
    with ReviewStore(tmp_path / "review.sqlite3") as store:
        project = store.create_project("No borrowed support", "scoping", "Own quotations?")["id"]
        doc = attach(store, project, report(store, project), "<sec><p>needle measured result</p><table-wrap><table><tr><td>7.5</td></tr></table></table-wrap></sec>")
        trace = store.search_sources(project, "needle", method=METHOD, top_k=100)
        assert_trace(store, project, trace)
        table = next(row for row in trace["passages"] if row["locator"]["tag"] == "table-wrap")
        anchor = table["scoring_context"][0]["anchor"]
        question = {"id": "synthetic", "article_alias": "invented", "question": "needle?", "expected_answer_as_reported": "measured result", "sufficient_support_sets": [["gold"]], "provisional_spans": [{"passage_id": "gold", **{key: anchor[key] for key in ("start", "end", "quote")}}]}
        passages = {"gold": {"id": "gold", "article_alias": "invented", "source_sha256": doc["source_sha256"], "provisional_block_id": anchor["block_id"]}}
        metric = assess_question(question, {"passages": [{**table, "rank": 1}]}, passages, {"invented": {"document_id": doc["id"]}})
        assert metric["best_alternative_support_coverage_at_5"] == 0 and metric["complete_support_at_5"] is False and metric["first_required_quote_rank_at_5"] is None


def test_active_version_project_report_scope_and_no_cross_document_context(tmp_path):
    with ReviewStore(tmp_path / "review.sqlite3") as store:
        project = store.create_project("Owned sources", "systematic", "Isolation?")["id"]
        foreign = store.create_project("Foreign sources", "scoping", "Other?")["id"]
        first, second, pending = report(store, project, "First"), report(store, project, "Second"), report(store, project, "Pending", eligible=False)
        old = attach(store, project, first, "<sec><p>needle old</p><p>obsolete target</p></sec>")
        current = attach(store, project, first, "<sec><p>current target</p></sec>")
        other = attach(store, project, second, "<sec><p>second target</p></sec>")
        pending_doc = attach(store, project, pending, "<sec><p>needle pending</p><p>pending target</p></sec>")
        attach(store, foreign, report(store, foreign), "<sec><p>needle foreign</p><p>foreign target</p></sec>")
        before = fingerprint(store)
        included = store.search_sources(project, "needle", method=METHOD, top_k=100)
        assert_trace(store, project, included)
        assert [row["document_id"] for row in included["source_manifest"]] == [current["id"], other["id"]] and included["passages"] == []
        all_sources = store.search_sources(project, "needle", method=METHOD, scope="all_attached", top_k=100)
        assert_trace(store, project, all_sources, "all_attached")
        assert {row["document_id"] for row in all_sources["passages"]} == {pending_doc["id"]}
        assert old["id"] not in {row["document_id"] for row in all_sources["source_manifest"]}
        assert fingerprint(store) == before


@pytest.mark.parametrize("column,value", [("content", b"broken"), ("blocks_json", "[]"), ("source_sha256", "0" * 64), ("blocks_sha256", "0" * 64)])
def test_selected_source_corruption_rejects_even_zero_query_tokens(tmp_path, column, value):
    with ReviewStore(tmp_path / "review.sqlite3") as store:
        project = store.create_project("Whole-block integrity", "scoping", "Corrupt source?")["id"]
        doc = attach(store, project, report(store, project), "<sec><p>needle</p></sec>")
        store._connection.execute(f"UPDATE source_documents SET {column}=? WHERE id=?", (value, doc["id"]))
        store._connection.commit()
        before = fingerprint(store)
        with pytest.raises(ValueError): store.search_sources(project, "the and", method=METHOD)
        assert fingerprint(store) == before


def test_late_identifier_enrichment_rejects_current_source_contradiction(tmp_path):
    with ReviewStore(tmp_path / "review.sqlite3") as store:
        project = store.create_project("Whole-block identity", "scoping", "Current identity?")["id"]
        rid = report(store, project, doi="10.9999/whole-block")
        front = '<front><article-meta><article-id pub-id-type="doi">10.9999/whole-block</article-id><article-id pub-id-type="pmid">123</article-id></article-meta></front>'
        attach(store, project, rid, "<sec><p>needle</p></sec>", front=front)
        assert store.search_sources(project, "needle", method=METHOD)["passages"]
        store.import_records(project, SearchRunSpec("Later metadata"), [BibliographicRecord(title="Later", doi="10.9999/whole-block", pmid="124")])
        before = fingerprint(store)
        with pytest.raises(ValueError, match="source_identity_conflict"): store.search_sources(project, "the and", method=METHOD)
        assert fingerprint(store) == before


def test_original_three_methods_keep_window_bounds_literal_scores_and_fields(tmp_path):
    with ReviewStore(tmp_path / "review.sqlite3") as store:
        project = store.create_project("Old method compatibility", "scoping", "No baseline change?")["id"]
        attach(store, project, report(store, project), "<sec><p>needle common common</p><p>other common</p></sec>")
        before = fingerprint(store)
        old = {method: store.search_sources(project, "needle common", method=method, top_k=100) for method in ("bm25", "token_overlap", "bm25_context")}
        assert [row["score"] for row in old["token_overlap"]["passages"]] == [2, 1]
        assert [row["score"] for row in old["bm25"]["passages"]] == pytest.approx([math.log(2) * 2.2 / 2.38 + math.log(1.2) * 4.4 / 3.38, math.log(1.2) * 2.2 / 2.02], rel=1e-12)
        # Context representations lengths3/5 average4, both terms DF2.
        assert [row["score"] for row in old["bm25_context"]["passages"]] == pytest.approx([math.log(1.2) * (4.4 / 2.975 + 2.2 / 1.975), math.log(1.2) * (6.6 / 4.425 + 2.2 / 2.425)], rel=1e-12)
        assert old["bm25_context"]["parameters"] == REFERENCE_PARAMETERS
        assert all("scoring_context" not in row for method in ("bm25", "token_overlap") for row in old[method]["passages"])
        store.search_sources(project, "needle common", method=METHOD)
        for method, expected in old.items(): assert store.search_sources(project, "needle common", method=method, top_k=100) == expected
        rid = report(store, project, "Long old-method text")
        padded = "  \r\n" + " ".join(["needle"] * 361) + "\r\n\t"
        doc = store.attach_document(project, rid, padded.encode(), "txt", "Custodian", "Exact")
        for method in old:
            trace = store.search_sources(project, "needle", method=method, top_k=100)
            own = [row["anchor"] for row in trace["passages"] if row["document_id"] == doc["id"]]
            assert [len(value["quote"].split()) for value in own] == [200, 200, 41]
            assert all(value["start"] > 0 and value["end"] < len(padded) for value in own)
        assert before != fingerprint(store)  # Only the explicit additional report/source wrote rows.


def test_actual_wal_snapshot_keeps_full_old_blocks_during_source_and_screening_mutation(tmp_path, monkeypatch):
    database = tmp_path / "review.sqlite3"
    with ReviewStore(database) as store:
        project = store.create_project("Whole-block snapshot", "systematic", "One version?")["id"]
        rid = report(store, project)
        old = attach(store, project, rid, "<sec><p>needle old context</p>" + paragraph(" ".join(["oldtarget"] * 350)) + "</sec>")
        assert store._connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        expected = store.search_sources(project, "needle", method=METHOD, top_k=100)
        original = store.list_records
        changed = False
        def concurrent(pid):
            nonlocal changed
            rows = original(pid)
            if not changed:
                assert store._connection.in_transaction
                changed = True
                with ReviewStore(database) as writer:
                    attach(writer, project, rid, "<sec><p>needle new context</p><p>new target</p></sec>")
                    writer.record_decision(project, rid, "full_text", "exclude", "Screener", "Concurrent exclusion")
            return rows
        monkeypatch.setattr(store, "list_records", concurrent)
        assert store.search_sources(project, "needle", method=METHOD, top_k=100) == expected
        assert changed and {row["document_id"] for row in expected["passages"]} == {old["id"]}
        assert store.search_sources(project, "needle", method=METHOD)["source_manifest"] == []
        current = store.search_sources(project, "needle", method=METHOD, scope="all_attached", top_k=100)
        assert_trace(store, project, current, "all_attached")
        assert {row["anchor"]["quote"] for row in current["passages"]} == {"needle new context", "new target"}


def test_fresh_cli_repeat_reopen_and_dependency_guards_match_api_without_writes(tmp_path):
    database = tmp_path / "review.sqlite3"
    with ReviewStore(database) as store:
        project = store.create_project("Whole-block CLI", "scoping", "Exact trace?")["id"]
        attach(store, project, report(store, project), "<sec><p>needle context</p>" + paragraph(" ".join(["target"] * 350)) + "</sec>")
        before = fingerprint(store)
        expected = store.search_sources(project, "needle", method=METHOD)
    environment = os.environ.copy()
    environment.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    command = [sys.executable, str(ROOT / "review.py"), "--db", str(database), "retrieve-sources", project, "--query", "needle", "--method", METHOD]
    for _ in range(2):
        result = subprocess.run(command, cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0 and result.stderr == "" and json.loads(result.stdout) == expected
    guarded = """
import contextlib,importlib.abc,io,json,socket,sys
sys.path.insert(0,sys.argv[1])
blocked={'torch','chromadb','sentence_transformers','dotenv','src.settings','fitz','pymupdf'}
class Guard(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if any(fullname==name or fullname.startswith(name+'.') for name in blocked): raise AssertionError('Forbidden dependency '+fullname)
sys.meta_path.insert(0,Guard())
def denied(*a,**k): raise AssertionError('Retrieval attempted network')
socket.create_connection=denied
from src.review import cli
output=io.StringIO()
with contextlib.redirect_stdout(output): assert cli.main(['--db',sys.argv[2],'retrieve-sources',sys.argv[3],'--query','needle','--method','bm25_context_blocks'])==0
assert not blocked.intersection(sys.modules)
print(output.getvalue(),end='')
"""
    result = subprocess.run([sys.executable, "-c", guarded, str(ROOT), str(database), project], cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and result.stderr == "" and json.loads(result.stdout) == expected
    with ReviewStore(database) as store:
        assert fingerprint(store) == before and store.search_sources(project, "needle", method=METHOD) == expected


@pytest.mark.parametrize("defect", [None, "clipped", "trimmed", "duplicate", "index", "window_parameters", "missing_context"])
def test_harness_requires_full_exact_block_index_and_separate_exact_context(tmp_path, defect):
    with ReviewStore(tmp_path / "review.sqlite3") as store:
        project = store.create_project("Whole-block harness", "scoping", "Exact own boundaries?")["id"]
        attach(store, project, report(store, project), "<sec><p>needle context</p><p>target</p></sec>")
        rid = report(store, project, "Padded harness text")
        store.attach_document(project, rid, b"  needle padded \r\n", "txt", "Custodian", "Exact")
        trace = store.search_sources(project, "needle", method=METHOD)
        freeze = {"methods": ["bm25_context", METHOD], "method_parameters": {METHOD: PARAMETERS, "bm25_context": REFERENCE_PARAMETERS}}
        padded = next(row for row in trace["passages"] if row["anchor"]["quote"].startswith("  "))
        target = next(row for row in trace["passages"] if row["anchor"]["quote"] == "target")
        if defect == "clipped":
            padded["anchor"]["start"] = 1
            padded["anchor"]["quote"] = padded["anchor"]["quote"][1:]
        elif defect == "trimmed":
            padded["anchor"]["quote"] = "needle padded"
            padded["anchor"]["start"], padded["anchor"]["end"] = 2, 15
        elif defect == "duplicate": trace["passages"].append({**deepcopy(padded), "rank": 4})
        elif defect == "index": trace["indexed_passages"] += 1
        elif defect == "window_parameters": trace["parameters"]["window_words"] = 200
        elif defect == "missing_context": target["scoring_context"] = []
        if defect:
            with pytest.raises(ValueError): evaluator.validate_trace(trace, store, project, freeze)
        else: assert evaluator.validate_trace(trace, store, project, freeze) == {"own_anchors": 3, "scoring_context_anchors": 1}


def frozen_gate():
    return {"development": {"answerable": 7}, "development_selection": {"candidate": METHOD, "reference": "bm25_context", "min_complete_questions": 7, "min_mean_support_coverage_at_5": 1.0, "min_no_answer_context_quotes_at_5": 1, "exact_anchor_validity": 1.0}}


@pytest.mark.parametrize("defect", [None, "complete", "coverage", "context", "own", "scoring", "scope", "denominator", "method"])
def test_v3_prospective_development_gate_cannot_relax_any_requirement(defect):
    result = {"method": METHOD, "metrics": {"answerable_questions": 7, "complete_questions_at_5": 7, "mean_support_coverage_at_5": 1.0, "no_answer_context_quotes_covered_at_5": 1}, "own_anchor_validity": 1.0, "scoring_context_anchor_validity": 1.0, "project_active_document_scope_isolation": 1.0}
    changes = {"complete": ("complete_questions_at_5", 6), "coverage": ("mean_support_coverage_at_5", .999), "context": ("no_answer_context_quotes_covered_at_5", 0), "denominator": ("answerable_questions", 6)}
    if defect in changes:
        key, value = changes[defect]; result["metrics"][key] = value
    elif defect == "own": result["own_anchor_validity"] = .999
    elif defect == "scoring": result["scoring_context_anchor_validity"] = .999
    elif defect == "scope": result["project_active_document_scope_isolation"] = .999
    elif defect == "method": result["method"] = "bm25_context"
    assert evaluator.development_eligibility(result, frozen_gate())["eligible"] is (defect is None)


def synthetic_selection(tmp_path):
    freeze = frozen_gate()
    freeze["implementation_files"] = {"src/review/retrieval.py": {"sha256": hashlib.sha256(b"fixed code").hexdigest(), "size_bytes": 10}}
    freeze["method_parameters"] = {METHOD: PARAMETERS, "bm25_context": REFERENCE_PARAMETERS}
    code = tmp_path / "src/review/retrieval.py"; code.parent.mkdir(parents=True); code.write_bytes(b"fixed code")
    frozen = tmp_path / evaluator.FREEZE_FILE; frozen.parent.mkdir(parents=True); frozen.write_text(json.dumps(freeze))
    rows = [{"answerable": True, "any_required_support_hit_at_5": True, "reciprocal_rank_at_5": 1, "best_alternative_support_coverage_at_5": 1, "complete_support_at_5": True} for _ in range(7)]
    rows += [{"answerable": False, "nonempty_candidates_at_5": True, "context_quote_coverage_at_5": {"context": {"covered_quotes": int(number == 0), "required_quotes": 1}}} for number in range(2)]
    candidate = {"method": METHOD, "metrics": evaluator.aggregate_metrics(rows), "per_question": rows, "own_anchor_validity": 1.0, "scoring_context_anchor_validity": 1.0, "project_active_document_scope_isolation": 1.0}
    development = {"split": "development", "held_out_ranked": False, "freeze_sha256": evaluator.pin(frozen)["sha256"], "method_results": [candidate]}
    result = tmp_path / evaluator.DEVELOPMENT_FILE; result.parent.mkdir(); result.write_text(json.dumps(development))
    receipt = {"schema_version": 1, "status": "coordinator_selected_before_held_out_ranking", "held_out_ranked_at_selection": False, "freeze_file": evaluator.FREEZE_FILE, "freeze_sha256": evaluator.pin(frozen)["sha256"], "development_result_file": evaluator.DEVELOPMENT_FILE, "development_result_sha256": evaluator.pin(result)["sha256"], "selected_method": METHOD, "method_parameters": PARAMETERS, "implementation_files": freeze["implementation_files"], "selection_rule": freeze["development_selection"]}
    return freeze, receipt, result, code


@pytest.mark.parametrize("defect", [None, "missing", "late", "reference", "windows", "unit", "code", "freeze", "development", "ineligible"])
def test_v3_fresh_ranking_requires_selected_pinned_whole_block_receipt(tmp_path, monkeypatch, defect):
    freeze, receipt, development_file, code = synthetic_selection(tmp_path)
    monkeypatch.setattr(evaluator, "ROOT", tmp_path)
    if defect == "late": receipt["held_out_ranked_at_selection"] = True
    elif defect == "reference": receipt["selected_method"] = "bm25_context"
    elif defect == "windows": receipt["method_parameters"] = {**PARAMETERS, "window_words": 200}
    elif defect == "unit": receipt["method_parameters"] = {**PARAMETERS, "passage_unit": "window"}
    elif defect == "code": code.write_bytes(b"other code")
    elif defect == "freeze": receipt["freeze_sha256"] = "0" * 64
    elif defect == "development": receipt["development_result_sha256"] = "0" * 64
    elif defect == "ineligible":
        development = json.loads(development_file.read_text()); candidate = development["method_results"][0]
        candidate["per_question"][0]["complete_support_at_5"] = False
        candidate["metrics"] = evaluator.aggregate_metrics(candidate["per_question"])
        development_file.write_text(json.dumps(development)); receipt["development_result_sha256"] = evaluator.pin(development_file)["sha256"]
    path = tmp_path / "selection.json"; path.write_text(json.dumps(receipt))
    if defect:
        with pytest.raises(ValueError): evaluator.validate_selection(None if defect == "missing" else path, freeze)
    else: assert evaluator.validate_selection(path, freeze) == receipt
