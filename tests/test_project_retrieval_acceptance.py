"""Independent project source retrieval and quote-coverage metric acceptance."""

from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import sys

import pytest

from src.review import cli
from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.store import ReviewStore
from tools.evaluate_medical_retrieval import assess_question, aggregate_metrics, development_recommendation, digest_json, validate_selection


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "evidence"
STOP_WORDS = sorted("a an and are as at be been by did do does for from had has have how in is it its of on or that the their there these this to was were what when where which who with would".split())


@pytest.fixture(autouse=True)
def no_live_dependencies(monkeypatch):
    def denied(*args, **kwargs): pytest.fail("Project retrieval attempted network or real sleep")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr("time.sleep", denied)


def add_report(store, project_id, title, text=None, *, doi=None, eligible=True):
    store.import_records(project_id, SearchRunSpec("Invented retrieval input"), [BibliographicRecord(title=title, doi=doi)])
    record_id = store.list_records(project_id)[-1]["id"]
    if eligible:
        store.record_decision(project_id, record_id, "title_abstract", "include", "Screener")
        store.set_full_text_status(project_id, record_id, "retrieved", "Custodian")
        store.record_decision(project_id, record_id, "full_text", "include", "Screener")
    document = store.attach_document(project_id, record_id, text.encode(), "txt", "Custodian", "Invented exact bytes") if text is not None else None
    return record_id, document


def ledger_fingerprint(store):
    return hashlib.sha256("\n".join(store._connection.iterdump()).encode()).hexdigest()


def assert_trace(store, project_id, trace, *, method="bm25", scope="included", top_k=5):
    assert trace["schema_version"] == 1 and trace["status"] == "candidate_passages" and trace["project_id"] == project_id
    assert trace["method"] == method and trace["method_version"] == "lit-rev-engine.project-retrieval.v1." + method
    assert trace["scope"] == scope and trace["top_k"] == top_k
    params = {"tokenizer_id": "unicode-casefold-word-v1", "stop_words": STOP_WORDS, "window_words": 200, "overlap_words": 40}
    if method == "bm25": params.update(k1=1.2, b=0.75)
    assert trace["parameters"] == params and trace["source_snapshot_sha256"] == digest_json(trace["source_manifest"])
    manifests = {row["document_id"]: row for row in trace["source_manifest"]}
    documents = {row["id"]: row for row in store.list_documents(project_id)}
    records = {row["id"]: row for row in store.list_records(project_id)}
    links = {row["record_id"]: row for row in store.list_study_links(project_id)}
    for row in trace["source_manifest"]:
        assert set(row) == {"document_id", "record_id", "version", "format", "source_sha256", "blocks_sha256", "parser_id", "parser_metadata", "source_identifiers",
                            "source_url", "version_label", "record_title", "doi", "pmid", "title_abstract_state", "full_text_status", "full_text_state", "study_link_state", "study_ids"}
        document = documents[row["document_id"]]
        assert document["active"] is True and document["record_id"] == row["record_id"]
        for key in ("version", "format", "source_sha256", "blocks_sha256", "parser_id", "parser_metadata", "source_identifiers", "source_url", "version_label"):
            assert row[key] == document[key]
        record = records[row["record_id"]]
        assert row["record_title"] == record["title"]
        for key in ("doi", "pmid", "title_abstract_state", "full_text_status", "full_text_state"):
            assert row[key] == record[key]
        assert row["study_link_state"] == links[row["record_id"]]["state"] and row["study_ids"] == links[row["record_id"]]["study_ids"]
    for rank, passage in enumerate(trace["passages"], 1):
        assert passage["rank"] == rank and passage["score"] > 0 and math.isfinite(passage["score"])
        assert passage["project_id"] == project_id and passage["document_id"] in manifests
        manifest = manifests[passage["document_id"]]
        for key in ("record_id", "source_sha256", "blocks_sha256", "parser_id", "full_text_state", "study_link_state", "study_ids"):
            assert passage[key] == manifest[key]
        assert passage["document_version"] == manifest["version"]
        anchor = passage["anchor"]
        assert set(anchor) == {"block_id", "start", "end", "quote"}
        blocks = store.get_source_blocks(project_id, passage["document_id"])
        block = next(block for block in blocks if block["id"] == anchor["block_id"])
        assert type(anchor["start"]) is type(anchor["end"]) is int
        assert 0 <= anchor["start"] < anchor["end"] <= len(block["text"])
        assert anchor["quote"] == block["text"][anchor["start"]:anchor["end"]] and passage["locator"] == block["locator"]
    assert len(trace["passages"]) == min(top_k, trace["matched_passages"])


def run_cli(tmp_path, database, *args, success=True):
    environment = os.environ.copy()
    environment.pop("NCBI_EMAIL", None); environment.pop("NCBI_API_KEY", None)
    environment.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    result = subprocess.run([sys.executable, str(ROOT / "review.py"), "--db", str(database), *map(str, args)],
                            cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=10)
    if success:
        assert result.returncode == 0 and result.stderr == "", result.stderr
        return json.loads(result.stdout)
    assert result.returncode != 0 and result.stderr.strip() and not result.stdout.strip() and "Traceback" not in result.stderr
    return result.stderr


@pytest.mark.parametrize("method", ["token_overlap", "bm25"])
def test_analytically_known_distinct_token_scores_stop_words_and_no_mutation(tmp_path, method):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        p = store.create_project("Analytic synthetic ranking", "systematic", "Which literal words?")["id"]
        first, first_doc = add_report(store, p, "First", "the rare common common")
        second, second_doc = add_report(store, p, "Second", "common other")
        before = ledger_fingerprint(store)
        trace = store.search_sources(p, "  rare common common  ", method=method)
        assert_trace(store, p, trace, method=method)
        assert trace["query"] == "  rare common common  " and trace["indexed_passages"] == trace["matched_passages"] == 2
        assert [row["record_id"] for row in trace["passages"]] == [first, second]
        if method == "token_overlap":
            assert [row["score"] for row in trace["passages"]] == [2, 1]
        else:
            expected_first = math.log(2) * 2.2 / 2.38 + math.log(1.2) * 4.4 / 3.38
            expected_second = math.log(1.2) * 2.2 / 2.02
            assert [row["score"] for row in trace["passages"]] == pytest.approx([expected_first, expected_second], rel=1e-12)
        repeated = store.search_sources(p, "  rare common common  ", method=method)
        assert repeated == trace and ledger_fingerprint(store) == before
        reordered = store.search_sources(p, "common rare", method=method)
        assert reordered["passages"] == trace["passages"] and reordered["source_snapshot_sha256"] == trace["source_snapshot_sha256"]
        assert store.list_evidence(p) == store.list_evidence_reviews(p) == []


def test_exact_character_windows_200_words_40_overlap_short_tail_and_creation_order_ties(tmp_path):
    words = [f"term{number:04d}" for number in range(401)]
    text = " \r\n" + " \t".join(words) + "  \r\n"
    positions = list(re.finditer(r"\S+", text))
    expected = [(positions[start].start(), positions[end - 1].end()) for start, end in ((0, 200), (160, 360), (320, 401))]
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        p = store.create_project("Window truth", "systematic", "Exact source windows?")["id"]
        first, document = add_report(store, p, "First", text)
        second, _ = add_report(store, p, "Second", text)
        trace = store.search_sources(p, " ".join(words), top_k=1000000, method="token_overlap")
        assert_trace(store, p, trace, method="token_overlap", top_k=1000000)
        assert trace["indexed_passages"] == trace["matched_passages"] == 6
        assert [(passage["record_id"], passage["anchor"]["start"]) for passage in trace["passages"]] == [
            (first, expected[0][0]), (first, expected[1][0]), (second, expected[0][0]), (second, expected[1][0]),
            (first, expected[2][0]), (second, expected[2][0])]
        for record in (first, second):
            anchors = sorted((passage["anchor"] for passage in trace["passages"] if passage["record_id"] == record), key=lambda anchor: anchor["start"])
            assert [(anchor["start"], anchor["end"]) for anchor in anchors] == expected
            assert [anchor["quote"] for anchor in anchors] == [text[start:end] for start, end in expected]
        assert len(store.search_sources(p, " ".join(words), method="token_overlap", top_k=1)["passages"]) == 1


@pytest.mark.parametrize("word_count,expected_count", [(1, 1), (199, 1), (200, 1), (201, 2), (360, 2), (361, 3)])
def test_final_window_is_retained_only_when_it_adds_new_words(tmp_path, word_count, expected_count):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        p = store.create_project("Boundary windows", "scoping", "Word boundaries?")["id"]
        add_report(store, p, "Synthetic repeated word", " ".join(["needle"] * word_count))
        trace = store.search_sources(p, "needle", top_k=20)
        assert_trace(store, p, trace, top_k=20)
        assert trace["indexed_passages"] == trace["matched_passages"] == len(trace["passages"]) == expected_count


def test_unicode_casefold_numeric_negation_and_exact_quotes_keep_original_text(tmp_path):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        p = store.create_project("Unicode literal text", "scoping", "Unicode matches?")["id"]
        _, _ = add_report(store, p, "Unicode", "Straße α café café 🧪. Not 12 months.\r\nExact source.")
        trace = store.search_sources(p, "STRASSE α NOT 12", method="token_overlap")
        assert_trace(store, p, trace, method="token_overlap")
        assert trace["passages"][0]["score"] == 4
        assert trace["passages"][0]["anchor"]["quote"] == "Straße α café café 🧪. Not 12 months.\r\nExact source."


def test_project_active_document_scope_and_unresolved_linkage_provenance_are_exact(tmp_path):
    database = tmp_path / "reviews.sqlite3"
    with ReviewStore(database) as store:
        p = store.create_project("Scope truth", "systematic", "Current included sources?")["id"]
        foreign = store.create_project("Foreign", "systematic", "Other?")["id"]
        a, old = add_report(store, p, "Included", "obsolete obsolete obsolete")
        current = store.attach_document(p, a, b"shared included", "txt", "Custodian", "Replacement")
        b, excluded = add_report(store, p, "Excluded", "shared excluded")
        store.record_decision(p, b, "full_text", "exclude", "Screener", "Excluded fixture")
        c, pending = add_report(store, p, "Pending", "shared pending", eligible=False)
        add_report(store, p, "Included without source")
        add_report(store, foreign, "Foreign dominates", "shared " * 30)
        study_a = store.create_study(p, "A", "Linker", "Manual")["id"]
        study_b = store.create_study(p, "B", "Linker", "Alternative")["id"]
        store.record_study_links(p, a, [study_a], "Alice", "A")
        store.record_study_links(p, a, [study_b], "Bob", "B")
        before = ledger_fingerprint(store)
        included = store.search_sources(p, "shared")
        assert_trace(store, p, included)
        assert [row["document_id"] for row in included["source_manifest"]] == [current["id"]]
        assert included["source_manifest"][0]["study_link_state"] == "conflict" and included["source_manifest"][0]["study_ids"] == []
        all_sources = store.search_sources(p, "shared", scope="all_attached")
        assert_trace(store, p, all_sources, scope="all_attached")
        assert [row["record_id"] for row in all_sources["source_manifest"]] == [a, b, c]
        assert [row["full_text_state"] for row in all_sources["source_manifest"]] == ["include", "exclude", "pending"]
        assert store.search_sources(p, "obsolete", scope="all_attached")["passages"] == []
        store.record_decision(p, a, "full_text", "exclude", "Screener", "Conditional new exclusion")
        assert store.search_sources(p, "shared")["source_manifest"] == []
        store.record_decision(p, a, "full_text", "include", "Screener")
        assert store.search_sources(p, "shared") == included
        assert ledger_fingerprint(store) != before  # Only the explicit screening changes append history.


@pytest.mark.parametrize("query", ["the and with", "!!! 🧪", "unmatchedterm"])
def test_zero_effective_tokens_or_matches_retain_manifest_and_do_not_create_events(tmp_path, query):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        p = store.create_project("No matching tokens", "scoping", "No answers inferred?")["id"]
        add_report(store, p, "Literal source", "shared literal source")
        before = ledger_fingerprint(store)
        trace = store.search_sources(p, query)
        assert_trace(store, p, trace)
        assert trace["indexed_passages"] == 1 and trace["matched_passages"] == 0 and trace["passages"] == []
        assert len(trace["source_manifest"]) == 1 and ledger_fingerprint(store) == before


INVALID_OPTIONS = [("query", ""), ("query", " \t"), ("query", None), ("query", 123),
                   ("top_k", 0), ("top_k", -1), ("top_k", True), ("top_k", 1.5), ("top_k", "5"),
                   ("method", "unknown"), ("method", None), ("scope", "unknown"), ("scope", None)]


@pytest.mark.parametrize("field,value", INVALID_OPTIONS)
def test_api_invalid_options_are_atomic(tmp_path, field, value):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        p = store.create_project("Invalid retrieval", "scoping", "Validation?")["id"]
        add_report(store, p, "Literal", "needle")
        before = ledger_fingerprint(store)
        args = {"query": "needle", field: value}
        with pytest.raises(ValueError): store.search_sources(p, **args)
        assert ledger_fingerprint(store) == before


def test_unknown_project_and_empty_project_are_distinct_and_do_not_write(tmp_path):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        p = store.create_project("Empty", "scoping", "No sources?")["id"]
        before = ledger_fingerprint(store)
        trace = store.search_sources(p, "needle")
        assert_trace(store, p, trace)
        assert trace["indexed_passages"] == trace["matched_passages"] == 0 and trace["source_manifest"] == trace["passages"] == []
        with pytest.raises(ValueError): store.search_sources("unknown-project", "needle")
        assert ledger_fingerprint(store) == before


@pytest.mark.parametrize("column,value", [("content", b"Corrupt bytes"), ("blocks_json", "[]"), ("source_sha256", "0" * 64), ("blocks_sha256", "0" * 64)])
@pytest.mark.parametrize("query", ["needle", "the and"])
def test_selected_source_corruption_rejects_before_even_empty_effective_query_returns(tmp_path, column, value, query):
    database = tmp_path / "reviews.sqlite3"
    with ReviewStore(database) as store:
        p = store.create_project("Selected source integrity", "systematic", "Integrity?")["id"]
        _, document = add_report(store, p, "Literal", "needle original")
    with sqlite3.connect(database) as connection:
        connection.execute(f"UPDATE source_documents SET {column}=? WHERE id=?", (value, document["id"]))
    with ReviewStore(database) as store:
        before = ledger_fingerprint(store)
        with pytest.raises(ValueError): store.search_sources(p, query)
        assert ledger_fingerprint(store) == before


def test_inactive_and_excluded_corrupt_sources_do_not_leak_into_included_selected_integrity(tmp_path):
    database = tmp_path / "reviews.sqlite3"
    with ReviewStore(database) as store:
        p = store.create_project("Selected scope integrity", "systematic", "Only selected?")["id"]
        record, inactive = add_report(store, p, "Included", "obsolete needle")
        active = store.attach_document(p, record, b"current needle", "txt", "Custodian", "Explicit replacement")
        other, excluded = add_report(store, p, "Excluded", "excluded needle")
        store.record_decision(p, other, "full_text", "exclude", "Screener", "Excluded")
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE source_documents SET content=? WHERE id IN (?,?)", (b"Corrupt unselected bytes", inactive["id"], excluded["id"]))
    with ReviewStore(database) as store:
        before = ledger_fingerprint(store)
        trace = store.search_sources(p, "needle")
        assert [row["document_id"] for row in trace["source_manifest"]] == [active["id"]]
        assert [row["document_id"] for row in trace["passages"]] == [active["id"]]
        with pytest.raises(ValueError): store.search_sources(p, "the", scope="all_attached")
        assert ledger_fingerprint(store) == before


def test_later_canonical_identity_contradiction_rejects_selected_source_atomically(tmp_path):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        p = store.create_project("Late own-identifier contradiction", "systematic", "Current canonical association?")["id"]
        record, _ = add_report(store, p, "Identity", doi="10.99999/retrieval-identity")
        source = b'<article><front><article-meta><article-id pub-id-type="doi">10.99999/retrieval-identity</article-id><article-id pub-id-type="pmid">999999111</article-id></article-meta></front><body><p>needle exact</p></body></article>'
        store.attach_document(p, record, source, "jats_xml", "Custodian", "Bibliography PMID unknown")
        assert len(store.search_sources(p, "needle")["passages"]) == 1
        store.import_records(p, SearchRunSpec("Later identity enrichment"), [BibliographicRecord(title="Identity", doi="10.99999/retrieval-identity", pmid="999999112")])
        before = ledger_fingerprint(store)
        for query in ("needle", "the and"):
            with pytest.raises(ValueError): store.search_sources(p, query)
        assert ledger_fingerprint(store) == before


def test_pdf_and_xml_windows_keep_typed_locators_and_can_be_explicitly_proposed_without_auto_verification(tmp_path):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        p = store.create_project("Typed source candidates", "systematic", "Exact locators?")["id"]
        xml_record, _ = add_report(store, p, "Invented XML")
        pdf_record, _ = add_report(store, p, "Invented PDF")
        xml = store.attach_document(p, xml_record, (FIXTURES / "article-v1.xml").read_bytes(), "jats_xml", "Custodian", "Synthetic source")
        pdf = store.attach_document(p, pdf_record, (FIXTURES / "three-pages.pdf").read_bytes(), "pdf", "Custodian", "Physical pages")
        study = store.create_study(p, "Invented study", "Linker", "Manual")["id"]
        store.record_study_links(p, xml_record, [study], "Linker", "Complete set")
        before = ledger_fingerprint(store)
        trace = store.search_sources(p, "fixture α Table synthetic", top_k=100, method="token_overlap")
        assert_trace(store, p, trace, method="token_overlap", top_k=100)
        assert trace["indexed_passages"] == 9  # Seven XML blocks plus two nonblank physical PDF pages.
        assert {passage["locator"]["type"] for passage in trace["passages"]} == {"xml_element", "pdf_page"}
        assert not any(passage["anchor"]["block_id"] == "pdf:page:2" for passage in trace["passages"])
        assert ledger_fingerprint(store) == before and store.list_evidence(p) == []
        table = next(passage for passage in trace["passages"] if passage["locator"].get("tag") == "table-wrap")
        assert "α\t12" in table["anchor"]["quote"] and table["locator"]["table_label"] == "Table S1"
        proposal = store.propose_evidence(p, table["record_id"], study, table["document_id"], "fixture_group_count", 12,
                                         {"population": "Group α invented entries", "notes": "Manually entered, software-only value"},
                                         table["anchor"], "Alice", "Explicit manual source proposal")
        assert proposal["anchor"] == {**table["anchor"], "locator": table["locator"]}
        assert store.list_evidence(p)[0]["state"] == "proposed" and store.list_evidence(p, verified_only=True) == []


def test_source_manifest_and_traces_survive_source_deletion_export_reopening_and_cli_repeat(tmp_path):
    database = tmp_path / "reviews.sqlite3"
    source_path = tmp_path / "source original.txt"
    source_path.write_text("  Exact α source\r\nneedle preserved.", encoding="utf-8", newline="")
    content = source_path.read_bytes()
    with ReviewStore(database) as store:
        p = store.create_project("Durable candidate trace", "systematic", "Provenance?")["id"]
        record, _ = add_report(store, p, "Formula = source")
        document = store.attach_document(p, record, content, "txt", "Custodian", "Exact supplied bytes", filename=source_path.name,
                                         source_url="https://example.invalid/source", version_label="Manually supplied v1")
        trace = store.search_sources(p, "needle α")
        assert_trace(store, p, trace)
        before = ledger_fingerprint(store)
        result = store.export_project(p, tmp_path / "export")
        bundle = json.loads((tmp_path / "export" / "project.json").read_text())
        assert bundle["documents"][0]["source_sha256"] == trace["source_manifest"][0]["source_sha256"]
        assert (tmp_path / "export" / bundle["document_artifacts"][0]["export_file"]).read_bytes() == content
        assert ledger_fingerprint(store) == before
    source_path.unlink()
    with ReviewStore(database) as store:
        assert store.search_sources(p, "needle α") == trace
        assert ledger_fingerprint(store) == before
    assert run_cli(tmp_path, database, "retrieve-sources", p, "--query", "needle α") == trace
    assert run_cli(tmp_path, database, "retrieve-sources", p, "--query", "needle α") == trace


@pytest.mark.parametrize("arguments", [("--top-k", "0"), ("--top-k", "bad"), ("--method", "model"), ("--scope", "unknown"), ("--output", "unrequested.json")])
def test_cli_invalid_options_fail_without_output_artifacts_or_ledger_events(tmp_path, arguments):
    database = tmp_path / "reviews.sqlite3"
    with ReviewStore(database) as store:
        p = store.create_project("CLI invalid", "scoping", "No mutation?")["id"]
        add_report(store, p, "Synthetic", "needle")
        before = ledger_fingerprint(store)
    run_cli(tmp_path, database, "retrieve-sources", p, "--query", "needle", *arguments, success=False)
    assert not (tmp_path / "unrequested.json").exists()
    with ReviewStore(database) as store: assert ledger_fingerprint(store) == before


def test_retrieval_retains_one_actual_wal_snapshot_during_source_and_eligibility_change(tmp_path, monkeypatch):
    database = tmp_path / "reviews.sqlite3"
    with ReviewStore(database) as store:
        assert store._connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        p = store.create_project("Concurrent selected sources", "systematic", "One snapshot?")["id"]
        record, old = add_report(store, p, "Literal", "shared old")
        expected = store.search_sources(p, "shared")
        original = store.list_records
        triggered = False
        def concurrent_change(project_id):
            nonlocal triggered
            rows = original(project_id)
            if project_id == p and not triggered:
                assert store._connection.in_transaction
                triggered = True
                with ReviewStore(database) as writer:
                    writer.attach_document(p, record, b"shared new", "txt", "Custodian", "Concurrent version")
                    writer.record_decision(p, record, "full_text", "exclude", "Screener", "Concurrent exclusion")
            return rows
        monkeypatch.setattr(store, "list_records", concurrent_change)
        actual = store.search_sources(p, "shared")
        assert triggered and actual == expected
        assert store.search_sources(p, "shared")["source_manifest"] == []
        newer = store.search_sources(p, "shared", scope="all_attached")
        assert newer["source_manifest"][0]["document_id"] != old["id"] and newer["source_manifest"][0]["version"] == 2
        assert newer["passages"][0]["anchor"]["quote"] == "shared new" and newer["source_manifest"][0]["full_text_state"] == "exclude"


def metric_fixture():
    passages = {name: {"id": name, "article_alias": "source", "source_sha256": "known-source", "provisional_block_id": "block:" + name}
                for name in ("A", "B", "C", "D")}
    bindings = {"source": {"document_id": "known-document"}}
    question = {"id": "metric-truth", "article_alias": "source", "question": "All requested groups?", "expected_answer_as_reported": {"literal": True},
                "sufficient_support_sets": [["A", "B"], ["C"]], "context_only_passage_ids": [], "hard_negative_passage_ids": ["D"],
                "provisional_spans": [
                    {"passage_id": "A", "start": 2, "end": 5, "quote": "aaa"}, {"passage_id": "A", "start": 12, "end": 15, "quote": "bbb"},
                    {"passage_id": "B", "start": 3, "end": 8, "quote": "ccccc"}, {"passage_id": "C", "start": 20, "end": 25, "quote": "ddddd"}]}
    return question, passages, bindings


def candidate(rank, passage_id, start, end, **overrides):
    return {"rank": rank, "score": 10 / rank, "document_id": "known-document", "source_sha256": "known-source",
            "anchor": {"block_id": "block:" + passage_id, "start": start, "end": end, "quote": "Synthetic metric candidate"}, **overrides}


def test_metric_or_alternatives_require_complete_quote_groups_and_allow_separate_windows():
    question, passages, bindings = metric_fixture()
    candidates = [candidate(1, "A", 0, 8), candidate(2, "B", 0, 9), candidate(3, "D", 0, 30), candidate(4, "C", 19, 26)]
    partial = assess_question(question, {"passages": candidates}, passages, bindings)
    assert partial["alternative_support_coverages_at_5"] == [0.5, 1] and partial["complete_support_at_5"] is True
    assert partial["best_alternative_support_coverage_at_5"] == 1 and partial["reciprocal_rank_at_5"] == 1
    assert partial["passage_quote_coverage_at_5"]["A"] == {"required_quotes": 2, "quote_first_ranks": [1, None], "covered_quotes": 1, "covered": False}
    assert partial["hard_negative_candidates_at_5"] == [{"passage_id": "D", "rank": 3}]
    candidates.append(candidate(5, "A", 10, 16))
    complete = assess_question(question, {"passages": candidates}, passages, bindings)
    assert complete["alternative_support_coverages_at_5"] == [1, 1]
    assert complete["passage_quote_coverage_at_5"]["A"]["quote_first_ranks"] == [1, 5]


def test_metric_and_single_passage_hit_does_not_imply_complete_support():
    question, passages, bindings = metric_fixture()
    question["sufficient_support_sets"] = [["A", "B"]]
    row = assess_question(question, {"passages": [candidate(1, "A", 0, 30)]}, passages, bindings)
    assert row["any_required_support_hit_at_5"] is True and row["reciprocal_rank_at_5"] == 1
    assert row["best_alternative_support_coverage_at_5"] == 0.5 and row["complete_support_at_5"] is False
    assert row["failure_modes"] == ["incomplete_sufficient_support_set"]


@pytest.mark.parametrize("wrong", ["wrong_document", "wrong_source", "wrong_block", "clipped_left", "clipped_right", "rank_six_only"])
def test_metric_rejects_wrong_identity_partial_quotes_and_quotes_beyond_five(wrong):
    question, passages, bindings = metric_fixture()
    question["sufficient_support_sets"] = [["C"]]
    match = candidate(1, "C", 19, 26)
    if wrong == "wrong_document": match["document_id"] = "foreign-document"
    elif wrong == "wrong_source": match["source_sha256"] = "different-source"
    elif wrong == "wrong_block": match["anchor"]["block_id"] = "block:D"
    elif wrong == "clipped_left": match["anchor"]["start"] = 21
    elif wrong == "clipped_right": match["anchor"]["end"] = 24
    candidates = [match]
    if wrong == "rank_six_only": candidates = [candidate(rank, "D", 0, 30) for rank in range(1, 6)] + [candidate(6, "C", 19, 26)]
    row = assess_question(question, {"passages": candidates}, passages, bindings)
    assert row["any_required_support_hit_at_5"] is False and row["reciprocal_rank_at_5"] == 0
    assert row["best_alternative_support_coverage_at_5"] == 0 and row["complete_support_at_5"] is False


def test_metric_no_answer_context_is_reported_separately_from_answerable_denominators():
    question, passages, bindings = metric_fixture()
    answerable = assess_question(question, {"passages": [candidate(2, "C", 19, 26)]}, passages, bindings)
    no_answer = deepcopy(question)
    no_answer.update(id="no-answer-truth", expected_answer_as_reported=None, sufficient_support_sets=[], context_only_passage_ids=["A"])
    context = assess_question(no_answer, {"passages": [candidate(1, "A", 0, 30)]}, passages, bindings)
    assert context["reciprocal_rank_at_5"] is None and context["complete_support_at_5"] is None
    assert context["context_quote_coverage_at_5"]["A"]["covered_quotes"] == 2
    aggregate = aggregate_metrics([answerable, context])
    assert aggregate["answerable_questions"] == aggregate["no_answer_questions"] == 1
    assert aggregate["hit_rate_at_5"] == aggregate["mean_support_coverage_at_5"] == 1
    assert aggregate["mean_reciprocal_rank_at_5"] == 0.5 and aggregate["complete_questions_at_5"] == 1
    assert aggregate["no_answer_nonempty_candidate_rate_at_5"] == 1
    assert aggregate["no_answer_context_quotes_covered_at_5"] == aggregate["no_answer_context_quotes_declared"] == 2


def test_metric_missing_required_quote_is_invalid_gold_not_vacuous_complete_support():
    question, passages, bindings = metric_fixture()
    question["sufficient_support_sets"] = [["D"]]
    with pytest.raises(ValueError): assess_question(question, {"passages": []}, passages, bindings)


def test_development_selection_uses_frozen_thresholds_order_and_bm25_exact_tie():
    freeze = json.loads((ROOT / "tests" / "fixtures" / "medical_retrieval" / "freeze.json").read_text())
    def result(method, coverage, complete, mrr):
        return {"method": method, "metrics": {"answerable_questions": 7, "mean_support_coverage_at_5": coverage, "complete_questions_at_5": complete, "mean_reciprocal_rank_at_5": mrr}}
    tie = development_recommendation([result("token_overlap", 0.75, 4, 0.5), result("bm25", 0.75, 4, 0.5)], freeze)
    assert tie["recommended_method"] == "bm25" and tie["coordinator_authorization_required_before_held_out"] is True
    assert development_recommendation([result("token_overlap", 1, 4, 0.1), result("bm25", 0.9, 7, 1)], freeze)["recommended_method"] == "token_overlap"
    assert development_recommendation([result("token_overlap", 0.9, 5, 0.1), result("bm25", 0.9, 4, 1)], freeze)["recommended_method"] == "token_overlap"
    assert development_recommendation([result("token_overlap", 0.9, 5, 0.6), result("bm25", 0.9, 5, 0.5)], freeze)["recommended_method"] == "token_overlap"
    assert development_recommendation([result("token_overlap", 0.74, 7, 1), result("bm25", 1, 3, 1)], freeze)["recommended_method"] is None


def test_fresh_retrieval_cli_process_has_no_models_settings_dotenv_pdf_or_network(tmp_path):
    database = tmp_path / "reviews.sqlite3"
    with ReviewStore(database) as store:
        p = store.create_project("Isolated retrieval", "scoping", "Exact words?")["id"]
        add_report(store, p, "Literal", "needle α preserved")
        expected = store.search_sources(p, "needle α")
        before = ledger_fingerprint(store)
    code = """
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
with contextlib.redirect_stdout(output): assert cli.main(['--db',sys.argv[2],'retrieve-sources',sys.argv[3],'--query','needle α'])==0
assert not blocked.intersection(sys.modules)
print(output.getvalue(),end='')
"""
    result = subprocess.run([sys.executable, "-c", code, str(ROOT), str(database), p], cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and result.stderr == "", result.stderr
    assert json.loads(result.stdout) == expected
    with ReviewStore(database) as store: assert ledger_fingerprint(store) == before


@pytest.mark.parametrize("defect", ["missing_receipt", "ranked_before_selection", "wrong_method", "wrong_development_hash", "wrong_freeze_hash", "changed_selection_rule"])
def test_held_out_receipt_rejects_unreviewed_method_changed_pins_or_postranking_selection_without_ranking(tmp_path, defect):
    freeze = json.loads((ROOT / "tests" / "fixtures" / "medical_retrieval" / "freeze.json").read_text())
    receipt = json.loads((ROOT / "docs" / "medical-retrieval-selection-v1.json").read_text())
    if defect == "ranked_before_selection": receipt["held_out_ranked_at_selection"] = True
    elif defect == "wrong_method": receipt["selected_method"] = "token_overlap"
    elif defect == "wrong_development_hash": receipt["development_result_sha256"] = "0" * 64
    elif defect == "wrong_freeze_hash": receipt["freeze_sha256"] = "0" * 64
    elif defect == "changed_selection_rule": receipt["selection_rule"]["eligible_min_complete_questions"] = 0
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError): validate_selection(None if defect == "missing_receipt" else path, freeze)
