"""Independent context-ranking software gates; no medical query execution."""

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
from tools import evaluate_medical_retrieval_v2 as evaluator


ROOT = Path(__file__).resolve().parents[1]
STOP_WORDS = sorted("a an and are as at be been by did do does for from had has have how in is it its of on or that the their there these this to was were what when where which who with would".split())
PARAMETERS = {"tokenizer_id": "unicode-casefold-word-v1", "stop_words": STOP_WORDS,
              "window_words": 200, "overlap_words": 40, "k1": 1.2, "b": 0.75,
              "context_rule": "preceding-paragraph-same-xml-parent-v1", "context_max_words": 80}


@pytest.fixture(autouse=True)
def no_live_dependencies(monkeypatch):
    def denied(*args, **kwargs): pytest.fail("Context retrieval attempted network or real sleep")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr("time.sleep", denied)


def fingerprint(store): return hashlib.sha256("\n".join(store._connection.iterdump()).encode()).hexdigest()


def report(store, project, title="Invented report", *, eligible=True, doi=None, pmid=None):
    store.import_records(project, SearchRunSpec("Independent invented context input"), [BibliographicRecord(title=title, doi=doi, pmid=pmid)])
    record_id = store.list_records(project)[-1]["id"]
    if eligible:
        store.record_decision(project, record_id, "title_abstract", "include", "Screener")
        store.set_full_text_status(project, record_id, "retrieved", "Custodian")
        store.record_decision(project, record_id, "full_text", "include", "Screener")
    return record_id


def attach(store, project, record_id, body, *, front=""):
    content = ("<article>" + front + "<body>" + body + "</body></article>").encode()
    return store.attach_document(project, record_id, content, "jats_xml", "Custodian", "Exact invented XML")


def paragraph(text): return "<p>" + escape(text) + "</p>"


def anchors_by_text(trace): return {row["anchor"]["quote"]: row for row in trace["passages"]}


def assert_provenance(store, project, trace, *, scope="included", top_k=100):
    assert trace["project_id"] == project and trace["scope"] == scope and trace["top_k"] == top_k
    assert trace["schema_version"] == 1 and trace["status"] == "candidate_passages"
    assert trace["method"] == "bm25_context" and trace["method_version"] == "lit-rev-engine.project-retrieval.v2.bm25_context"
    assert trace["parameters"] == PARAMETERS and trace["source_snapshot_sha256"] == digest_json(trace["source_manifest"])
    selected = {row["document_id"]: row for row in trace["source_manifest"]}
    active = {doc["id"]: doc for doc in store.list_documents(project) if doc["active"]}
    records = {row["id"]: row for row in store.list_records(project)}
    for document_id, manifest in selected.items():
        assert document_id in active and manifest["record_id"] == active[document_id]["record_id"]
        assert all(manifest[key] == active[document_id][key] for key in ("version", "format", "source_sha256", "blocks_sha256", "parser_id", "parser_metadata", "source_identifiers", "source_url", "version_label"))
        assert manifest["full_text_state"] == records[manifest["record_id"]]["full_text_state"]
        if scope == "included": assert manifest["full_text_state"] == "include"
    for rank, candidate in enumerate(trace["passages"], 1):
        assert candidate["project_id"] == project and candidate["document_id"] in selected
        manifest = selected[candidate["document_id"]]
        assert candidate["rank"] == rank and candidate["score"] > 0 and math.isfinite(candidate["score"])
        assert candidate["document_version"] == manifest["version"]
        assert all(candidate[key] == manifest[key] for key in ("record_id", "source_sha256", "blocks_sha256", "parser_id", "full_text_state", "study_link_state", "study_ids"))
        blocks = {block["id"]: block for block in store.get_source_blocks(project, candidate["document_id"])}
        for value in [{"anchor": candidate["anchor"], "locator": candidate["locator"]}] + candidate["scoring_context"]:
            anchor = value["anchor"]
            assert set(anchor) == {"block_id", "start", "end", "quote"} and type(anchor["start"]) is type(anchor["end"]) is int
            block = blocks[anchor["block_id"]]
            assert 0 <= anchor["start"] < anchor["end"] <= len(block["text"])
            assert block["text"][anchor["start"]:anchor["end"]] == anchor["quote"] and block["locator"] == value["locator"]
        assert len(candidate["scoring_context"]) <= 1
        if candidate["scoring_context"]:
            own = blocks[candidate["anchor"]["block_id"]]
            context = blocks[candidate["scoring_context"][0]["anchor"]["block_id"]]
            assert manifest["format"] == "jats_xml" and own["locator"]["tag"] in ("p", "table-wrap") and context["locator"]["tag"] == "p"
            assert context["ordinal"] < own["ordinal"]
            assert context["locator"]["path"].rsplit("/", 1)[0] == own["locator"]["path"].rsplit("/", 1)[0]
            assert len(re.findall(r"\S+", candidate["scoring_context"][0]["anchor"]["quote"])) <= 80


def test_augmented_bm25_literal_tf_df_average_lengths_query_deduplication_and_no_writes(tmp_path):
    with ReviewStore(tmp_path / "review.sqlite3") as store:
        project = store.create_project("Analytic context fixture", "systematic", "Literal lexical scores?")["id"]
        rid = report(store, project)
        attach(store, project, rid, "<sec>" + paragraph("the rare common common") + paragraph("common other") + paragraph("third rare") + "</sec>")
        before = fingerprint(store)
        trace = store.search_sources(project, "rare common common", method="bm25_context", top_k=100)
        assert_provenance(store, project, trace)
        assert trace["indexed_passages"] == trace["matched_passages"] == 3
        # Augmented lengths are 3,5,4; common and rare each occur in all three representations.
        idf = math.log(8 / 7)
        expected = [idf * (4.4 / 2.975 + 2.2 / 1.975), idf * (6.6 / 4.425 + 2.2 / 2.425), idf * 2]
        assert [row["score"] for row in trace["passages"]] == pytest.approx(expected, rel=1e-12)
        assert [row["anchor"]["quote"] for row in trace["passages"]] == ["the rare common common", "common other", "third rare"]
        assert [row["scoring_context"] for row in trace["passages"]][0] == []
        assert trace["passages"][1]["scoring_context"][0]["anchor"]["quote"] == "the rare common common"
        assert trace["passages"][2]["scoring_context"][0]["anchor"]["quote"] == "common other"
        assert store.search_sources(project, "common rare", method="bm25_context", top_k=100)["passages"] == trace["passages"]
        assert store.search_sources(project, "rare common common", method="bm25_context", top_k=100) == trace
        assert fingerprint(store) == before and store.list_evidence(project) == store.list_evidence_reviews(project) == []


@pytest.mark.parametrize("count", [1, 79, 80, 81, 100])
def test_exact_last_eighty_original_words_not_prefix_and_unicode_offsets(tmp_path, count):
    words = [f"prefix{index}" for index in range(count - 1)] + ["Straßeα"]
    text = "\r\n\t" + " \t\n".join(words) + " \r\n"
    with ReviewStore(tmp_path / "review.sqlite3") as store:
        project = store.create_project("Suffix fixture", "scoping", "Exact suffix?")["id"]
        rid = report(store, project)
        document = attach(store, project, rid, "<sec>" + paragraph(text) + paragraph("target beta") + "</sec>")
        block = next(block for block in store.get_source_blocks(project, document["id"]) if "Straßeα" in block["text"])
        canonical_text = " ".join(words)
        assert block["text"] == canonical_text
        trace = store.search_sources(project, "STRASSEΑ", method="bm25_context", top_k=100)
        assert_provenance(store, project, trace)
        target = anchors_by_text(trace)["target beta"]
        positions = list(re.finditer(r"\S+", canonical_text))
        start, end = positions[max(0, count - 80)].start(), positions[-1].end()
        assert target["scoring_context"] == [{"anchor": {"block_id": block["id"], "start": start, "end": end, "quote": canonical_text[start:end]}, "locator": block["locator"]}]
        if count > 80:
            lost = store.search_sources(project, "prefix0", method="bm25_context", top_k=100)
            assert all(row["anchor"]["quote"] != "target beta" for row in lost["passages"])


@pytest.mark.parametrize("body,expected_targets", [
    ("<sec><p>needle first</p><p>nearest unrelated</p><p>target</p></sec>", {}),
    ("<sec><p>needle first</p><table-wrap><table><tr><td>table intervenes</td></tr></table></table-wrap><p>target</p></sec>", {"target": "needle first"}),
    ("<sec><p>needle first</p><sec><p>nested target</p></sec><p>target</p></sec>", {"target": "needle first"}),
    ("<sec><p>needle first</p></sec><sec><p>target</p></sec>", {}),
    ("<p>needle direct</p><sec><p>target</p></sec><p>direct target</p>", {"direct target": "needle direct"}),
    ("<sec><p>needle first</p><title>target title</title><p>target</p></sec>", {"target": "needle first"}),
])
def test_closest_preceding_paragraph_immediate_parent_and_nonparagraph_intervening_blocks(tmp_path, body, expected_targets):
    with ReviewStore(tmp_path / "review.sqlite3") as store:
        project = store.create_project("Structural context fixture", "scoping", "Immediate parent only?")["id"]
        attach(store, project, report(store, project), body)
        trace = store.search_sources(project, "needle", method="bm25_context", top_k=100)
        assert_provenance(store, project, trace)
        returned = anchors_by_text(trace)
        for own, context in expected_targets.items(): assert returned[own]["scoring_context"][0]["anchor"]["quote"] == context
        for own in ("target", "nested target", "direct target", "target title"):
            if own not in expected_targets: assert own not in returned
        assert returned[next(key for key in returned if key.startswith("needle"))]["scoring_context"] == []
        if "nearest unrelated" in body:
            target = anchors_by_text(store.search_sources(project, "target", method="bm25_context", top_k=100))["target"]
            assert target["scoring_context"][0]["anchor"]["quote"] == "nearest unrelated"


def test_context_only_matches_return_own_table_anchor_but_never_count_as_support(tmp_path):
    with ReviewStore(tmp_path / "review.sqlite3") as store:
        project = store.create_project("Context is ranking input", "systematic", "No invented support?")["id"]
        rid = report(store, project)
        document = attach(store, project, rid, "<sec><p>needle measured result</p><table-wrap><label>Fixture table</label><table><tr><td>7.5</td></tr></table></table-wrap></sec>")
        trace = store.search_sources(project, "needle", method="bm25_context", top_k=100)
        assert_provenance(store, project, trace)
        table = next(row for row in trace["passages"] if row["locator"]["tag"] == "table-wrap")
        assert "needle" not in table["anchor"]["quote"] and table["scoring_context"][0]["anchor"]["quote"] == "needle measured result"
        gold_anchor = table["scoring_context"][0]["anchor"]
        passage = {"id": "gold", "article_alias": "synthetic", "source_sha256": document["source_sha256"], "provisional_block_id": gold_anchor["block_id"]}
        question = {"id": "synthetic-question", "article_alias": "synthetic", "question": "needle?", "expected_answer_as_reported": "measured result",
                    "sufficient_support_sets": [["gold"]], "provisional_spans": [{"passage_id": "gold", "start": gold_anchor["start"], "end": gold_anchor["end"], "quote": gold_anchor["quote"]}]}
        metric = assess_question(question, {"passages": [{**table, "rank": 1}]}, {"gold": passage}, {"synthetic": {"document_id": document["id"]}})
        assert metric["best_alternative_support_coverage_at_5"] == 0 and metric["complete_support_at_5"] is False and metric["first_required_quote_rank_at_5"] is None


def test_context_once_for_each_own_window_changes_length_and_frequency_only_once(tmp_path):
    own_text = " ".join(["target"] * 361)
    with ReviewStore(tmp_path / "review.sqlite3") as store:
        project = store.create_project("Window context fixture", "scoping", "One suffix per window?")["id"]
        attach(store, project, report(store, project), "<sec><p>needle needle</p>" + paragraph(own_text) + "</sec>")
        trace = store.search_sources(project, "needle", method="bm25_context", top_k=100)
        assert_provenance(store, project, trace)
        assert trace["indexed_passages"] == trace["matched_passages"] == 4
        # Four representations: lengths2,202,202,43; average112.25; each contains needle twice.
        idf = math.log(10 / 9)
        for candidate in trace["passages"]:
            own_length = len(candidate["anchor"]["quote"].split())
            length = own_length if not candidate["scoring_context"] else own_length + 2
            expected = idf * 4.4 / (2 + 1.2 * (.25 + .75 * length / 112.25))
            assert candidate["score"] == pytest.approx(expected, rel=1e-12)
            if candidate["scoring_context"]: assert candidate["scoring_context"][0]["anchor"]["quote"] == "needle needle"


@pytest.mark.parametrize("kind", ["txt", "pdf", "title", "abstract"])
def test_non_jats_formats_and_titles_do_not_borrow_and_abstract_parent_is_local(tmp_path, kind):
    with ReviewStore(tmp_path / "review.sqlite3") as store:
        project = store.create_project("No inferred context", "scoping", "Format isolation?")["id"]
        rid = report(store, project)
        if kind == "txt": store.attach_document(project, rid, b"needle first\nneedle second", "txt", "Custodian", "Literal")
        elif kind == "pdf": store.attach_document(project, rid, (ROOT / "tests/fixtures/evidence/three-pages.pdf").read_bytes(), "pdf", "Custodian", "Literal")
        else:
            front = "<front><article-meta><title-group><article-title>needle title</article-title></title-group><abstract><p>needle abstract one</p><p>needle abstract two</p></abstract></article-meta></front>"
            attach(store, project, rid, "<sec><p>needle body</p><title>needle section</title></sec>", front=front)
        trace = store.search_sources(project, "needle fixture", method="bm25_context", top_k=100)
        assert_provenance(store, project, trace)
        assert trace["passages"]
        # Abstract p blocks are ordinary accepted XML paragraphs: their own immediate parent still applies.
        for candidate in trace["passages"]:
            if kind in ("txt", "pdf") or candidate["locator"].get("tag") not in ("p", "table-wrap"):
                assert candidate["scoring_context"] == []
        if kind == "abstract":
            second = anchors_by_text(trace)["needle abstract two"]
            assert second["scoring_context"][0]["anchor"]["quote"] == "needle abstract one"
            assert anchors_by_text(trace)["needle body"]["scoring_context"] == []


def test_no_context_crosses_projects_reports_documents_versions_or_included_scope(tmp_path):
    with ReviewStore(tmp_path / "review.sqlite3") as store:
        project = store.create_project("Selected context", "systematic", "Ownership?")["id"]
        foreign = store.create_project("Foreign context", "systematic", "Other?")["id"]
        r1, r2, pending = report(store, project, "First"), report(store, project, "Second"), report(store, project, "Pending", eligible=False)
        old = attach(store, project, r1, "<sec><p>needle obsolete</p><p>old target</p></sec>")
        current = attach(store, project, r1, "<sec><p>current target</p></sec>")
        other = attach(store, project, r2, "<sec><p>second target</p></sec>")
        pending_doc = attach(store, project, pending, "<sec><p>needle pending</p><p>pending target</p></sec>")
        attach(store, foreign, report(store, foreign), "<sec><p>needle foreign</p><p>foreign target</p></sec>")
        before = fingerprint(store)
        included = store.search_sources(project, "needle", method="bm25_context", top_k=100)
        assert_provenance(store, project, included)
        assert [row["document_id"] for row in included["source_manifest"]] == [current["id"], other["id"]] and included["passages"] == []
        all_sources = store.search_sources(project, "needle", method="bm25_context", scope="all_attached", top_k=100)
        assert_provenance(store, project, all_sources, scope="all_attached")
        assert {row["document_id"] for row in all_sources["passages"]} == {pending_doc["id"]}
        assert all(row["document_id"] != old["id"] for row in all_sources["source_manifest"])
        assert fingerprint(store) == before


@pytest.mark.parametrize("column,value", [("content", b"broken"), ("blocks_json", "[]"), ("source_sha256", "0" * 64), ("blocks_sha256", "0" * 64)])
def test_selected_context_source_integrity_fails_even_stopword_only_query(tmp_path, column, value):
    with ReviewStore(tmp_path / "review.sqlite3") as store:
        project = store.create_project("Context integrity", "scoping", "Fail corrupt source?")["id"]
        document = attach(store, project, report(store, project), "<sec><p>needle</p><p>target</p></sec>")
        store._connection.execute(f"UPDATE source_documents SET {column}=? WHERE id=?", (value, document["id"]))
        store._connection.commit()
        before = fingerprint(store)
        with pytest.raises(ValueError): store.search_sources(project, "the and", method="bm25_context")
        assert fingerprint(store) == before


def test_current_identifier_conflict_rejects_context_source_after_late_enrichment(tmp_path):
    with ReviewStore(tmp_path / "review.sqlite3") as store:
        project = store.create_project("Context identity", "scoping", "Current identity?")["id"]
        rid = report(store, project, doi="10.9999/context")
        front = '<front><article-meta><article-id pub-id-type="doi">10.9999/context</article-id><article-id pub-id-type="pmid">123</article-id></article-meta></front>'
        attach(store, project, rid, "<sec><p>needle</p><p>target</p></sec>", front=front)
        assert store.search_sources(project, "needle", method="bm25_context")["passages"]
        store.import_records(project, SearchRunSpec("Late explicit PMID"), [BibliographicRecord(title="Later metadata", doi="10.9999/context", pmid="124")])
        before = fingerprint(store)
        with pytest.raises(ValueError, match="source_identity_conflict"): store.search_sources(project, "the and", method="bm25_context")
        assert fingerprint(store) == before


def test_original_method_traces_remain_literal_bm25_and_overlap_without_context_fields(tmp_path):
    with ReviewStore(tmp_path / "review.sqlite3") as store:
        project = store.create_project("Original methods", "scoping", "No v1 change?")["id"]
        attach(store, project, report(store, project), "<sec><p>needle common common</p><p>other common</p></sec>")
        before = fingerprint(store)
        overlap = store.search_sources(project, "needle common", method="token_overlap", top_k=100)
        baseline = store.search_sources(project, "needle common", top_k=100)
        assert [row["score"] for row in overlap["passages"]] == [2, 1]
        assert [row["score"] for row in baseline["passages"]] == pytest.approx([math.log(2) * 2.2 / 2.38 + math.log(1.2) * 4.4 / 3.38, math.log(1.2) * 2.2 / 2.02], rel=1e-12)
        for trace in (overlap, baseline):
            assert trace["method_version"] == "lit-rev-engine.project-retrieval.v1." + trace["method"]
            assert "context_rule" not in trace["parameters"] and all("scoring_context" not in row for row in trace["passages"])
        assert store.search_sources(project, "needle common", method="bm25_context", top_k=100)["passages"][1]["scoring_context"]
        assert store.search_sources(project, "needle common", top_k=100) == baseline
        assert store.search_sources(project, "needle common", method="token_overlap", top_k=100) == overlap
        assert fingerprint(store) == before


def test_context_retrieval_uses_actual_wal_snapshot_during_source_and_screening_change(tmp_path, monkeypatch):
    database = tmp_path / "review.sqlite3"
    with ReviewStore(database) as store:
        project = store.create_project("Context snapshot", "systematic", "One version?")["id"]
        rid = report(store, project)
        old = attach(store, project, rid, "<sec><p>needle old context</p><p>old target</p></sec>")
        assert store._connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        expected = store.search_sources(project, "needle", method="bm25_context", top_k=100)
        original = store.list_records
        changed = False
        def concurrent(project_id):
            nonlocal changed
            rows = original(project_id)
            if not changed:
                assert store._connection.in_transaction
                changed = True
                with ReviewStore(database) as writer:
                    attach(writer, project, rid, "<sec><p>needle new context</p><p>new target</p></sec>")
                    writer.record_decision(project, rid, "full_text", "exclude", "Screener", "Concurrent explicit exclusion")
            return rows
        monkeypatch.setattr(store, "list_records", concurrent)
        assert store.search_sources(project, "needle", method="bm25_context", top_k=100) == expected
        assert changed and all(row["document_id"] == old["id"] for row in expected["passages"])
        assert store.search_sources(project, "needle", method="bm25_context")["source_manifest"] == []
        current = store.search_sources(project, "needle", method="bm25_context", scope="all_attached", top_k=100)
        assert_provenance(store, project, current, scope="all_attached")
        assert anchors_by_text(current)["new target"]["scoring_context"][0]["anchor"]["quote"] == "needle new context"


def test_fresh_context_cli_repeat_and_reopen_match_exact_api_without_events(tmp_path):
    database = tmp_path / "review.sqlite3"
    with ReviewStore(database) as store:
        project = store.create_project("CLI context", "scoping", "Exact trace?")["id"]
        attach(store, project, report(store, project), "<sec><p>needle context</p><p>target</p></sec>")
        before = fingerprint(store)
        expected = store.search_sources(project, "needle", method="bm25_context")
    environment = os.environ.copy()
    environment.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    command = [sys.executable, str(ROOT / "review.py"), "--db", str(database), "retrieve-sources", project, "--query", "needle", "--method", "bm25_context"]
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
def denied(*a,**k): raise AssertionError('Context retrieval attempted network')
socket.create_connection=denied
from src.review import cli
output=io.StringIO()
with contextlib.redirect_stdout(output): assert cli.main(['--db',sys.argv[2],'retrieve-sources',sys.argv[3],'--query','needle','--method','bm25_context'])==0
assert not blocked.intersection(sys.modules)
print(output.getvalue(),end='')
"""
    result = subprocess.run([sys.executable, "-c", guarded, str(ROOT), str(database), project], cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and result.stderr == "" and json.loads(result.stdout) == expected
    with ReviewStore(database) as store:
        assert fingerprint(store) == before and store.search_sources(project, "needle", method="bm25_context") == expected


@pytest.mark.parametrize("defect", [None, "missing", "self", "wrong_locator", "clipped", "duplicate", "wrong_parameters"])
def test_harness_context_validation_recomputes_nearest_suffix_without_borrowing_support(tmp_path, defect):
    with ReviewStore(tmp_path / "review.sqlite3") as store:
        project = store.create_project("Harness context fixture", "scoping", "Exact context validation?")["id"]
        attach(store, project, report(store, project), "<sec><p>needle context</p><p>target</p></sec>")
        trace = store.search_sources(project, "needle", method="bm25_context")
        freeze = {"methods": ["bm25", "bm25_context"], "method_parameters": {"bm25_context": PARAMETERS}}
        target = next(row for row in trace["passages"] if row["anchor"]["quote"] == "target")
        if defect == "missing": target["scoring_context"] = []
        elif defect == "self": target["scoring_context"] = [{"anchor": deepcopy(target["anchor"]), "locator": deepcopy(target["locator"])}]
        elif defect == "wrong_locator": target["scoring_context"][0]["locator"]["path"] += "/p[99]"
        elif defect == "clipped": target["scoring_context"][0]["anchor"]["start"] = 1
        elif defect == "duplicate": target["scoring_context"] *= 2
        elif defect == "wrong_parameters": trace["parameters"]["context_max_words"] = 79
        if defect:
            with pytest.raises(ValueError): evaluator.validate_trace(trace, store, project, freeze)
        else:
            assert evaluator.validate_trace(trace, store, project, freeze) == {"own_anchors": 2, "scoring_context_anchors": 1}


def frozen_gate():
    return {"development": {"answerable": 7},
            "development_selection": {"candidate": "bm25_context", "reference": "bm25", "min_complete_questions": 7,
                                      "min_mean_support_coverage_at_5": 1.0, "min_no_answer_context_quotes_at_5": 1, "exact_anchor_validity": 1.0}}


@pytest.mark.parametrize("defect", [None, "complete", "coverage", "no_answer_context", "own_anchor", "context_anchor", "isolation", "denominator", "method"])
def test_development_gate_requires_all_seven_complete_and_preserves_one_no_answer_context(defect):
    result = {"method": "bm25_context", "metrics": {"answerable_questions": 7, "complete_questions_at_5": 7,
               "mean_support_coverage_at_5": 1.0, "no_answer_context_quotes_covered_at_5": 1},
              "own_anchor_validity": 1.0, "scoring_context_anchor_validity": 1.0, "project_active_document_scope_isolation": 1.0}
    if defect == "complete": result["metrics"]["complete_questions_at_5"] = 6
    elif defect == "coverage": result["metrics"]["mean_support_coverage_at_5"] = .999
    elif defect == "no_answer_context": result["metrics"]["no_answer_context_quotes_covered_at_5"] = 0
    elif defect == "own_anchor": result["own_anchor_validity"] = .999
    elif defect == "context_anchor": result["scoring_context_anchor_validity"] = .999
    elif defect == "isolation": result["project_active_document_scope_isolation"] = .999
    elif defect == "denominator": result["metrics"]["answerable_questions"] = 6
    elif defect == "method": result["method"] = "bm25"
    assert evaluator.development_eligibility(result, frozen_gate())["eligible"] is (defect is None)


def synthetic_selection(tmp_path):
    freeze = frozen_gate()
    freeze["implementation_files"] = {"src/review/retrieval.py": {"sha256": hashlib.sha256(b"fixed code").hexdigest(), "size_bytes": 10}}
    freeze["method_parameters"] = {"bm25_context": PARAMETERS}
    code = tmp_path / "src/review/retrieval.py"; code.parent.mkdir(parents=True); code.write_bytes(b"fixed code")
    frozen = tmp_path / evaluator.FREEZE_FILE; frozen.parent.mkdir(parents=True); frozen.write_text(json.dumps(freeze))
    rows = [{"answerable": True, "any_required_support_hit_at_5": True, "reciprocal_rank_at_5": 1,
             "best_alternative_support_coverage_at_5": 1, "complete_support_at_5": True} for _ in range(7)]
    rows += [{"answerable": False, "nonempty_candidates_at_5": True,
              "context_quote_coverage_at_5": {"context": {"covered_quotes": 1 if number == 0 else 0, "required_quotes": 1}}} for number in range(2)]
    candidate = {"method": "bm25_context", "metrics": evaluator.aggregate_metrics(rows), "per_question": rows,
                 "own_anchor_validity": 1.0, "scoring_context_anchor_validity": 1.0, "project_active_document_scope_isolation": 1.0}
    development = {"split": "development", "held_out_ranked": False, "freeze_sha256": evaluator.pin(frozen)["sha256"], "method_results": [candidate]}
    result = tmp_path / evaluator.DEVELOPMENT_FILE; result.parent.mkdir(); result.write_text(json.dumps(development))
    receipt = {"schema_version": 1, "status": "coordinator_selected_before_held_out_ranking", "held_out_ranked_at_selection": False,
               "freeze_file": evaluator.FREEZE_FILE, "freeze_sha256": evaluator.pin(frozen)["sha256"],
               "development_result_file": evaluator.DEVELOPMENT_FILE, "development_result_sha256": evaluator.pin(result)["sha256"],
               "selected_method": "bm25_context", "method_parameters": PARAMETERS, "implementation_files": freeze["implementation_files"],
               "selection_rule": freeze["development_selection"]}
    return freeze, receipt, result, code


@pytest.mark.parametrize("defect", [None, "missing", "late", "baseline", "parameters", "code_hash", "code_bytes", "freeze_hash", "development_hash", "rule", "metrics_inconsistent", "ineligible"])
def test_fresh_held_out_guard_requires_pinned_code_gold_parameters_and_eligible_dev_receipt(tmp_path, monkeypatch, defect):
    freeze, receipt, development_file, code = synthetic_selection(tmp_path)
    monkeypatch.setattr(evaluator, "ROOT", tmp_path)
    if defect == "late": receipt["held_out_ranked_at_selection"] = True
    elif defect == "baseline": receipt["selected_method"] = "bm25"
    elif defect == "parameters": receipt["method_parameters"] = {**PARAMETERS, "context_max_words": 81}
    elif defect == "code_hash": receipt["implementation_files"] = {"src/review/retrieval.py": {"sha256": "0" * 64, "size_bytes": 10}}
    elif defect == "code_bytes": code.write_bytes(b"other code")
    elif defect == "freeze_hash": receipt["freeze_sha256"] = "0" * 64
    elif defect == "development_hash": receipt["development_result_sha256"] = "0" * 64
    elif defect == "rule": receipt["selection_rule"] = {**freeze["development_selection"], "min_complete_questions": 6}
    elif defect in ("metrics_inconsistent", "ineligible"):
        development = json.loads(development_file.read_text())
        candidate = development["method_results"][0]
        candidate["per_question"][0]["complete_support_at_5"] = False
        if defect == "ineligible": candidate["metrics"] = evaluator.aggregate_metrics(candidate["per_question"])
        development_file.write_text(json.dumps(development)); receipt["development_result_sha256"] = evaluator.pin(development_file)["sha256"]
    path = tmp_path / "selection.json"; path.write_text(json.dumps(receipt))
    if defect:
        with pytest.raises(ValueError): evaluator.validate_selection(None if defect == "missing" else path, freeze)
    else:
        assert evaluator.validate_selection(path, freeze) == receipt
