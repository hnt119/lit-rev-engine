"""Exact lexical mathematics and project-source isolation on synthetic text."""

import hashlib
import json
import math
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.store import ReviewStore


ROOT = Path(__file__).resolve().parents[1]


def project(store, contents, *, included=True, doi=None):
    project_id = store.create_project("Synthetic retrieval", "systematic", "Software query")["id"]
    store.import_records(project_id, SearchRunSpec("synthetic"), [BibliographicRecord(title=f"Invented report {index}", doi=doi if index == 0 else None) for index in range(len(contents))])
    records = store.list_records(project_id)
    documents = []
    for record, text in zip(records, contents, strict=True):
        if included:
            include(store, project_id, record["id"])
        documents.append(store.attach_document(project_id, record["id"], text.encode("utf-8"), "txt", "custodian", "Synthetic source"))
    return project_id, [record["id"] for record in records], documents


def include(store, project_id, record_id):
    store.record_decision(project_id, record_id, "title_abstract", "include", "screener")
    store.set_full_text_status(project_id, record_id, "retrieved", "custodian")
    store.record_decision(project_id, record_id, "full_text", "include", "screener")


def assert_anchors(store, project_id, result):
    for passage in result["passages"]:
        anchor = passage["anchor"]
        block = next(block for block in store.get_source_blocks(project_id, passage["document_id"]) if block["id"] == anchor["block_id"])
        assert anchor["quote"] == block["text"][anchor["start"]:anchor["end"]]
        assert passage["locator"] == block["locator"]
        assert passage["project_id"] == project_id
    serialized = json.dumps(result["source_manifest"], ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    assert result["source_snapshot_sha256"] == hashlib.sha256(serialized).hexdigest()


def test_independent_bm25_math_and_distinct_token_overlap_tie_order():
    with ReviewStore(":memory:") as store:
        project_id, reports, _ = project(store, ["alpha alpha and beta delta", "alpha gamma gamma", "beta"])
        query = " ALPHA alpha AND beta\n"
        result = store.search_sources(project_id, query, top_k=100)
        # Three windows have lengths 4, 3, 1 after stop-word removal; both query
        # terms have df=2, and repeated query alpha contributes only once.
        idf, average = math.log(1 + 1.5 / 2.5), 8 / 3
        def term(tf, length):
            return idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / average))
        expected = {reports[0]: term(2, 4) + term(1, 4), reports[1]: term(1, 3), reports[2]: term(1, 1)}
        assert result["query"] == query and result["method"] == "bm25"
        assert result["indexed_passages"] == result["matched_passages"] == 3
        assert [row["record_id"] for row in result["passages"]] == [reports[0], reports[2], reports[1]]
        assert [row["rank"] for row in result["passages"]] == [1, 2, 3]
        for row in result["passages"]:
            assert row["score"] == pytest.approx(expected[row["record_id"]], abs=1e-15)
        overlap = store.search_sources(project_id, query, method="token_overlap", top_k=2)
        assert overlap["matched_passages"] == 3 and len(overlap["passages"]) == 2
        assert [(row["record_id"], row["score"]) for row in overlap["passages"]] == [(reports[0], 2), (reports[1], 1)]
        assert overlap["parameters"]["tokenizer_id"] == "unicode-casefold-word-v1"
        assert overlap["parameters"]["stop_words"] == sorted("a an and are as at be been by did do does for from had has have how in is it its of on or that the their there these this to was were what when where which who with would".split())
        assert "k1" not in overlap["parameters"]
        assert result["parameters"]["k1"] == 1.2 and result["parameters"]["b"] == 0.75
        assert_anchors(store, project_id, result)


@pytest.mark.parametrize("words,windows", [(1, 1), (160, 1), (200, 1), (201, 2), (320, 2), (360, 2), (361, 3)])
def test_windows_preserve_bounds_overlap_and_only_additional_final_words(words, windows):
    text = " \t" + "\r\n".join(f"w{index}" for index in range(words)) + "  \n"
    with ReviewStore(":memory:") as store:
        project_id, _, _ = project(store, [text])
        result = store.search_sources(project_id, "the", top_k=1000)
        assert result["indexed_passages"] == windows
        assert result["matched_passages"] == 0 and result["passages"] == []
        assert len(result["source_manifest"]) == 1
        first = store.search_sources(project_id, "w0", method="token_overlap")["passages"][0]["anchor"]
        assert first == {"block_id": "text:1", "start": 2, "end": text.index(f"w{min(words, 200) - 1}") + len(f"w{min(words, 200) - 1}"), "quote": "\r\n".join(f"w{index}" for index in range(min(words, 200)))}
        if words > 200:
            shared = store.search_sources(project_id, "w160", method="token_overlap", top_k=1000)
            assert [row["anchor"]["start"] for row in shared["passages"]] == [2, text.index("w160")]
            assert shared["passages"][1]["anchor"]["quote"].split() == [f"w{index}" for index in range(160, min(360, words))]
            assert_anchors(store, project_id, shared)


def test_unicode_casefold_numeric_negation_and_no_stemming():
    with ReviewStore(":memory:") as store:
        project_id, _, _ = project(store, [" \tStraße α 12 not sensitive.\r\n"])
        result = store.search_sources(project_id, "STRASSE α 12 not", method="token_overlap")
        assert result["passages"][0]["score"] == 4
        assert result["passages"][0]["anchor"]["quote"] == "Straße α 12 not sensitive."
        assert store.search_sources(project_id, "sensitivity")["passages"] == []
        assert_anchors(store, project_id, result)


def test_scope_project_active_version_and_linkage_provenance_are_independent():
    with ReviewStore(":memory:") as store:
        project_id, reports, documents = project(store, ["alpha included", "alpha pending", "alpha excluded"], included=False)
        include(store, project_id, reports[0])
        include(store, project_id, reports[2])
        store.record_decision(project_id, reports[2], "full_text", "exclude", "screener", "Synthetic exclusion")
        foreign, _, _ = project(store, ["alpha foreign"])
        study = store.create_study(project_id, "Invented study", "linker", "Association")["id"]
        store.record_study_links(project_id, reports[0], [study], "Alice", "Association")
        store.record_study_links(project_id, reports[0], [], "Bob", "Unresolved identity")
        result = store.search_sources(project_id, "alpha", method="token_overlap")
        assert result["indexed_passages"] == 1
        assert result["source_manifest"][0]["study_link_state"] == "conflict"
        assert result["passages"][0]["study_ids"] == []
        assert [row["record_id"] for row in result["source_manifest"]] == [reports[0]]
        all_sources = store.search_sources(project_id, "alpha", method="token_overlap", scope="all_attached")
        assert [row["record_id"] for row in all_sources["source_manifest"]] == reports
        assert [row["record_id"] for row in all_sources["passages"]] == reports
        assert all(row["project_id"] != foreign for row in all_sources["passages"])
        replacement = store.attach_document(project_id, reports[0], b"beta replacement", "txt", "custodian", "New active source")
        assert store.search_sources(project_id, "alpha")["passages"] == []
        current = store.search_sources(project_id, "beta")
        assert current["source_manifest"][0]["document_id"] == replacement["id"]
        assert current["passages"][0]["document_version"] == 2
        assert current["source_manifest"][0]["source_sha256"] != documents[0]["source_sha256"]


@pytest.mark.parametrize("options", [{"query": ""}, {"query": " \n"}, {"query": None}, {"query": []}, {"top_k": True}, {"top_k": 0}, {"top_k": -1}, {"top_k": 2.0}, {"top_k": None}, {"method": "embedding"}, {"method": []}, {"scope": "linked"}, {"scope": []}])
def test_invalid_options_fail_without_writes(options):
    with ReviewStore(":memory:") as store:
        project_id, _, _ = project(store, ["alpha source"])
        changes = store._connection.total_changes
        values = {"query": "alpha", **options}
        with pytest.raises(ValueError):
            store.search_sources(project_id, **values)
        assert store._connection.total_changes == changes


def test_empty_project_all_stop_words_and_punctuation_index_without_false_matches():
    with ReviewStore(":memory:") as store:
        empty = store.create_project("Empty", "scoping", "Software question")["id"]
        result = store.search_sources(empty, "alpha")
        assert result["source_manifest"] == result["passages"] == []
        assert result["indexed_passages"] == result["matched_passages"] == 0
        with pytest.raises(ValueError, match="Unknown project"):
            store.search_sources("unknown", "alpha")
        project_id, _, _ = project(store, ["the and or", "--- !!!"])
        for query in ("alpha", "the and", "!!!"):
            result = store.search_sources(project_id, query)
            assert result["indexed_passages"] == 2 and result["passages"] == []
            assert len(result["source_manifest"]) == 2


@pytest.mark.parametrize("column,value", [("content", b"corrupt bytes"), ("blocks_json", "[]")])
def test_integrity_checks_only_selected_sources_even_for_stopword_query(column, value):
    with ReviewStore(":memory:") as store:
        project_id, reports, documents = project(store, ["alpha original", "alpha excluded"], included=False)
        include(store, project_id, reports[0])
        replacement = store.attach_document(project_id, reports[0], b"alpha current", "txt", "custodian", "New version")
        foreign, _, foreign_documents = project(store, ["alpha foreign"])
        with store._connection:
            store._connection.executemany(f"UPDATE source_documents SET {column} = ? WHERE id = ?", [(value, document["id"]) for document in [*documents, *foreign_documents]])
        # Superseded, unselected, and foreign bytes/blocks cannot contaminate this scope.
        valid = store.search_sources(project_id, "alpha")
        assert valid["passages"][0]["document_id"] == replacement["id"]
        with pytest.raises(ValueError, match="corrupt"):
            store.search_sources(project_id, "the and", scope="all_attached")
        with pytest.raises(ValueError, match="corrupt"):
            store.search_sources(foreign, "alpha")
        with store._connection:
            store._connection.execute(f"UPDATE source_documents SET {column} = ? WHERE id = ?", (value, replacement["id"]))
        with pytest.raises(ValueError, match="corrupt"):
            store.search_sources(project_id, "the and")


@pytest.mark.parametrize("method", ["bm25", "bm25_context"])
def test_later_canonical_identifier_enrichment_rejects_current_source_identity(method):
    with ReviewStore(":memory:") as store:
        project_id, reports, _ = project(store, ["alpha first"], doi="10.1234/synthetic")
        xml = b'<article><front><article-meta><article-id pub-id-type="doi">10.1234/synthetic</article-id><article-id pub-id-type="pmid">123</article-id></article-meta></front><body><p>alpha source</p></body></article>'
        document = store.attach_document(project_id, reports[0], xml, "jats_xml", "custodian", "Known source IDs")
        assert store.search_sources(project_id, "alpha", method=method)["passages"][0]["document_id"] == document["id"]
        store.import_records(project_id, SearchRunSpec("Later identifier"), [BibliographicRecord(title="Invented report 0", doi="10.1234/synthetic", pmid="124")])
        changes = store._connection.total_changes
        for scope in ("included", "all_attached"):
            with pytest.raises(ValueError, match="source_identity_conflict"):
                store.search_sources(project_id, "the and", scope=scope, method=method)
        assert store._connection.total_changes == changes


def test_reopening_export_and_snapshot_concurrent_writer_preserve_trace(tmp_path, monkeypatch):
    database = tmp_path / "ledger.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
    with ReviewStore(database) as store:
        project_id, reports, _ = project(store, ["alpha source"])
        baseline = store.search_sources(project_id, "alpha")
        changes = store._connection.total_changes
        store.export_project(project_id, tmp_path / "export")
        assert store._connection.total_changes == changes
    with ReviewStore(database) as store:
        assert store.search_sources(project_id, "alpha") == baseline
        original, fired = store.list_records, []
        def concurrent(project):
            records = original(project)
            if not fired:
                fired.append(True)
                with ReviewStore(database) as writer:
                    writer.attach_document(project, reports[0], b"beta source", "txt", "custodian", "Concurrent replacement")
                    writer.record_decision(project, reports[0], "full_text", "exclude", "screener", "Concurrent exclusion")
            return records
        monkeypatch.setattr(store, "list_records", concurrent)
        assert store.search_sources(project_id, "alpha") == baseline
        after = store.search_sources(project_id, "beta")
        assert after["source_manifest"] == []
        attached = store.search_sources(project_id, "beta", scope="all_attached")
        assert attached["source_manifest"][0]["version"] == 2
        assert attached["source_manifest"][0]["full_text_state"] == "exclude"
        assert attached["source_snapshot_sha256"] != baseline["source_snapshot_sha256"]


def test_cli_default_explicit_options_repeated_trace_and_contextual_errors(tmp_path):
    database = tmp_path / "ledger.sqlite3"
    with ReviewStore(database) as store:
        project_id, _, _ = project(store, ["alpha source", "alpha secondary"])
        expected = store.search_sources(project_id, "alpha", top_k=1, method="token_overlap", scope="all_attached")
        baseline_history = store.list_search_runs(project_id), store.list_evidence_revisions(project_id)
    command = [sys.executable, str(ROOT / "review.py"), "--db", str(database), "retrieve-sources", project_id, "--query", "alpha"]
    default = subprocess.run(command, cwd=tmp_path, text=True, capture_output=True)
    assert default.returncode == 0 and default.stderr == ""
    assert json.loads(default.stdout)["method"] == "bm25"
    explicit = command + ["--top-k", "1", "--method", "token_overlap", "--scope", "all_attached"]
    result = subprocess.run(explicit, cwd=tmp_path, text=True, capture_output=True)
    assert result.returncode == 0 and result.stderr == ""
    assert json.loads(result.stdout) == expected
    repeated = subprocess.run(explicit, cwd=tmp_path, text=True, capture_output=True)
    assert repeated.stdout == result.stdout
    for options in (["--top-k", "0"], ["--query", " "], ["--output", str(tmp_path / "unsupported")]):
        failed = subprocess.run(command + options, cwd=tmp_path, text=True, capture_output=True)
        assert failed.returncode != 0 and failed.stdout == "" and "Traceback" not in failed.stderr
    with ReviewStore(database) as store:
        assert (store.list_search_runs(project_id), store.list_evidence_revisions(project_id)) == baseline_history


def attach_xml(store, project_id, record_id, body, *, front=""):
    xml = f"<article><front>{front}</front><body>{body}</body></article>".encode("utf-8")
    return store.attach_document(project_id, record_id, xml, "jats_xml", "custodian", "Synthetic XML source")


def assert_contexts(store, project_id, result):
    assert_anchors(store, project_id, result)
    for passage in result["passages"]:
        assert len(passage["scoring_context"]) <= 1
        blocks = {block["id"]: block for block in store.get_source_blocks(project_id, passage["document_id"])}
        for context in passage["scoring_context"]:
            anchor = context["anchor"]
            assert set(context) == {"anchor", "locator"}
            assert set(anchor) == {"block_id", "start", "end", "quote"}
            assert anchor["quote"] == blocks[anchor["block_id"]]["text"][anchor["start"]:anchor["end"]]
            assert context["locator"] == blocks[anchor["block_id"]]["locator"]
            assert context["locator"]["path"].rsplit("/", 1)[0] == passage["locator"]["path"].rsplit("/", 1)[0]
            assert context["locator"]["tag"] == "p" and anchor["block_id"] != passage["anchor"]["block_id"]


def test_context_augmented_bm25_math_own_anchor_and_v1_trace_regression():
    with ReviewStore(":memory:") as store:
        project_id, reports, _ = project(store, ["temporary"])
        attach_xml(store, project_id, reports[0], '<sec><p id="first">alpha alpha beta delta</p><p id="second">alpha gamma gamma</p><p id="third">beta</p></sec>')
        query = "alpha ALPHA beta"
        v1 = {method: store.search_sources(project_id, query, method=method, top_k=100) for method in ("bm25", "token_overlap")}
        changes = store._connection.total_changes
        result = store.search_sources(project_id, query, method="bm25_context", top_k=100)
        # Augmented lengths are 4, 3+4=7, and 1+3=4; both terms now have df=3.
        idf, average = math.log(1 + 0.5 / 3.5), 5
        def term(tf, length):
            return idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / average))
        expected = {"first": term(2, 4) + term(1, 4), "second": term(3, 7) + term(1, 7), "third": term(1, 4) + term(1, 4)}
        actual = {row["locator"]["element_id"]: row for row in result["passages"]}
        assert result["method_version"] == "lit-rev-engine.project-retrieval.v2.bm25_context"
        assert result["parameters"] == {**v1["bm25"]["parameters"], "context_rule": "preceding-paragraph-same-xml-parent-v1", "context_max_words": 80}
        assert result["indexed_passages"] == result["matched_passages"] == 3
        for key, score in expected.items():
            assert actual[key]["score"] == pytest.approx(score, abs=1e-15)
        assert actual["first"]["scoring_context"] == []
        assert actual["second"]["scoring_context"][0]["locator"]["element_id"] == "first"
        assert actual["third"]["scoring_context"][0]["locator"]["element_id"] == "second"
        assert actual["third"]["anchor"]["quote"] == "beta"
        assert result["source_manifest"] == v1["bm25"]["source_manifest"]
        assert store._connection.total_changes == changes
        assert_contexts(store, project_id, result)
        for method, before in v1.items():
            assert store.search_sources(project_id, query, method=method, top_k=100) == before
            assert all("scoring_context" not in row for row in before["passages"])


def test_context_uses_exact_last_80_words_once_per_own_window():
    context = " ".join(f"c{index}" for index in range(95))
    own = " ".join(f"t{index}" for index in range(201))
    with ReviewStore(":memory:") as store:
        project_id, reports, _ = project(store, ["temporary"])
        attach_xml(store, project_id, reports[0], f'<sec><p id="context">{context}</p><p id="target">{own}</p></sec>')
        result = store.search_sources(project_id, "c15", method="bm25_context", top_k=100)
        targets = [row for row in result["passages"] if row["locator"]["element_id"] == "target"]
        assert len(targets) == 2
        suffix = {"block_id": "xml:/article[1]/body[1]/sec[1]/p[1]", "start": context.index("c15"), "end": len(context), "quote": " ".join(f"c{index}" for index in range(15, 95))}
        # Context tokens are appended once to lengths 200 and 41; own context
        # paragraph has length 95. All three windows contain the queried token.
        average, idf = (95 + 280 + 121) / 3, math.log(1 + 0.5 / 3.5)
        for row in targets:
            assert row["scoring_context"][0]["anchor"] == suffix
            length = len(row["anchor"]["quote"].split()) + 80
            assert row["score"] == pytest.approx(idf * 2.2 / (1 + 1.2 * (0.25 + 0.75 * length / average)), abs=1e-15)
            assert "c15" not in row["anchor"]["quote"]
        outside = store.search_sources(project_id, "c14", method="bm25_context", top_k=100)
        assert [row["locator"]["element_id"] for row in outside["passages"]] == ["context"]
        assert_contexts(store, project_id, result)


def test_nearest_same_parent_paragraph_tables_titles_nested_branches_and_documents():
    body = '<sec><p id="outer">needle outer</p><sec><p id="inner">needle nested</p><p id="inner-next">inner next</p></sec><table-wrap id="table-one"><table><tr><td>own table</td></tr></table></table-wrap><p id="later">beta later</p><p id="last">gamma last</p><table-wrap id="table-two"><table><tr><td>own final</td></tr></table></table-wrap></sec><sec><p id="other-parent">other branch</p></sec>'
    front = '<article-meta><title-group><article-title id="title">needle title</article-title></title-group><abstract><p id="abstract">needle abstract</p><p id="abstract-next">abstract next</p></abstract></article-meta>'
    with ReviewStore(":memory:") as store:
        project_id, reports, _ = project(store, ["temporary", "second temporary"])
        document = attach_xml(store, project_id, reports[0], body, front=front)
        second = attach_xml(store, project_id, reports[1], '<sec><p id="isolated">isolated own</p></sec>')
        result = store.search_sources(project_id, "needle own next beta gamma other isolated", method="bm25_context", top_k=100)
        rows = {row["locator"]["element_id"]: row for row in result["passages"]}
        expected = {"title": None, "abstract": None, "abstract-next": "abstract", "outer": None, "inner": None, "inner-next": "inner", "table-one": "outer", "later": "outer", "last": "later", "table-two": "last", "other-parent": None, "isolated": None}
        assert set(rows) == set(expected)
        for target, preceding in expected.items():
            contexts = rows[target]["scoring_context"]
            assert ([item["locator"]["element_id"] for item in contexts] if preceding else contexts) == ([preceding] if preceding else [])
        assert rows["isolated"]["document_id"] == second["id"]
        assert all(row["document_id"] == document["id"] for key, row in rows.items() if key != "isolated")
        assert_contexts(store, project_id, result)


def test_txt_pdf_context_exclusion_and_optional_cli_method(tmp_path):
    database = tmp_path / "ledger.sqlite3"
    with ReviewStore(database) as store:
        project_id, reports, _ = project(store, ["Software fixture text", "temporary PDF"])
        store.attach_document(project_id, reports[1], (ROOT / "tests/fixtures/evidence/three-pages.pdf").read_bytes(), "pdf", "custodian", "Synthetic PDF")
        result = store.search_sources(project_id, "software fixture", method="bm25_context", top_k=100)
        assert result["passages"] and all(row["scoring_context"] == [] for row in result["passages"])
        assert {row["format"] for row in result["source_manifest"]} == {"txt", "pdf"}
    command = [sys.executable, str(ROOT / "review.py"), "--db", str(database), "retrieve-sources", project_id, "--query", "software fixture", "--method", "bm25_context", "--top-k", "100"]
    completed = subprocess.run(command, cwd=tmp_path, text=True, capture_output=True)
    assert completed.returncode == 0 and completed.stderr == ""
    assert json.loads(completed.stdout) == result


def test_context_integrity_and_current_version_snapshot(tmp_path, monkeypatch):
    database = tmp_path / "ledger.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
    with ReviewStore(database) as store:
        project_id, reports, _ = project(store, ["temporary"])
        document = attach_xml(store, project_id, reports[0], '<sec><p id="context">alpha context</p><p id="target">own result</p></sec>')
        baseline = store.search_sources(project_id, "alpha", method="bm25_context")
        original, fired = store.list_records, []
        def concurrent(project):
            records = original(project)
            if not fired:
                fired.append(True)
                with ReviewStore(database) as writer:
                    attach_xml(writer, project, reports[0], '<sec><p id="context">beta replacement</p><p id="target">own result</p></sec>')
            return records
        monkeypatch.setattr(store, "list_records", concurrent)
        assert store.search_sources(project_id, "alpha", method="bm25_context") == baseline
        assert store.search_sources(project_id, "alpha", method="bm25_context")["passages"] == []
        current = store.search_sources(project_id, "beta", method="bm25_context")
        assert current["source_manifest"][0]["document_id"] != document["id"]
        assert_contexts(store, project_id, current)
        active = current["source_manifest"][0]["document_id"]
        blocks = store.get_source_blocks(project_id, active)
        blocks[0]["text"] = "Corrupt scoring context"
        with store._connection:
            store._connection.execute("UPDATE source_documents SET blocks_json = ? WHERE id = ?", (json.dumps(blocks), active))
        with pytest.raises(ValueError, match="corrupt"):
            store.search_sources(project_id, "the and", method="bm25_context")
