"""Independent source-byte, version, locator, and durable export acceptance."""

from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import platform
import re
import socket
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.store import ReviewStore


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "evidence"
MEDICAL = Path(__file__).parent / "fixtures" / "medical_sources"
PUBMED = Path(__file__).parent / "fixtures" / "pubmed"
ALIASES = ["text_v1", "text_v2", "jats_v1", "jats_v2", "pdf_three_pages"]


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def block_hash(blocks):
    return sha256(json.dumps(blocks, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"))


@pytest.fixture(autouse=True)
def no_live_dependencies(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Document acceptance attempted network or real sleep")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr("time.sleep", denied)


@pytest.fixture
def oracle():
    value = json.loads((FIXTURES / "manifest.json").read_text())
    assert value["synthetic"] is True
    assert [item["alias"] for item in value["fixtures"]] == ALIASES
    for item in value["fixtures"]:
        content = (FIXTURES / item["file"]).read_bytes()
        assert sha256(content) == item["source_sha256"] and len(content) == item["size_bytes"]
        assert block_hash(item["expected_blocks"]) == item["expected_blocks_sha256"]
        assert len(item["expected_blocks"]) == item["expected_block_count"]
        texts = {block["id"]: block["text"] for block in item["expected_blocks"]}
        for quote in item["quotes"]:
            assert texts[quote["block_id"]][quote["start"]:quote["end"]] == quote["quote"]
    return {item["alias"]: item for item in value["fixtures"]}


@pytest.fixture
def parser():
    from src.review.documents import parse_source_bytes
    return parse_source_bytes


def metadata_for(format):
    common = {"python_version": platform.python_version()}
    if format == "txt":
        return {**common, "encoding": "utf-8-sig", "normalization": "none"}
    if format == "jats_xml":
        return {**common, "normalization": "xml-whitespace-v1", "tables": "rows-tab-separated-v1", "external_dtd": "ignored", "entities": "rejected"}
    import fitz
    return {**common, "pymupdf_version": fitz.VersionBind, "sort": True, "normalization": "none"}


def project_reports(store, title="Source audit"):
    project_id = store.create_project(title, "systematic", "Which sources support the review?")["id"]
    records = [BibliographicRecord(title=f"Synthetic source report {index}", doi=f"10.99999/source-audit-{index}") for index in (1, 2)]
    store.import_records(project_id, SearchRunSpec("Synthetic bibliography"), records, "bibliography-v1")
    return project_id, [row["id"] for row in store.list_records(project_id)]


def state(store, project_id):
    docs = store.list_documents(project_id)
    return deepcopy({
        "documents": docs,
        "bytes": {doc["id"]: store.get_document_bytes(project_id, doc["id"]) for doc in docs},
        "blocks": {doc["id"]: store.get_source_blocks(project_id, doc["id"]) for doc in docs},
        "records": store.list_records(project_id), "runs": store.list_search_runs(project_id),
        "occurrences": store.get_occurrences(project_id), "decisions": store.list_decisions(project_id),
        "retrieval": store.list_retrieval_events(project_id), "counts": store.counts(project_id),
        "studies": store.list_studies(project_id), "links": store.list_study_links(project_id),
        "link_events": store.list_study_link_events(project_id),
    })


def attach(store, project_id, record_id, item, **kwargs):
    return store.attach_document(project_id, record_id, (FIXTURES / item["file"]).read_bytes(), item["format"],
                                 "Source reviewer", "Exact invented source", **kwargs)


@pytest.mark.parametrize("alias", ALIASES)
def test_independent_exact_blocks_hashes_locators_quotes_and_parser_options(parser, oracle, alias, monkeypatch):
    item = oracle[alias]
    content = (FIXTURES / item["file"]).read_bytes()
    def no_file(*args, **kwargs):
        pytest.fail("Byte parser attempted a filesystem source read")
    monkeypatch.setattr(Path, "read_bytes", no_file)
    monkeypatch.setattr(Path, "read_text", no_file)
    result = parser(content, item["format"])
    assert result["parser_id"] == item["expected_parser_id"]
    assert result["source_identifiers"] == {}
    assert result["parser_metadata"] == metadata_for(item["format"])
    assert result["blocks"] == item["expected_blocks"]
    assert block_hash(result["blocks"]) == item["expected_blocks_sha256"]
    assert [block["ordinal"] for block in result["blocks"]] == list(range(1, len(result["blocks"]) + 1))
    assert len({block["id"] for block in result["blocks"]}) == len(result["blocks"])
    if item["format"] == "pdf":
        assert result["blocks"][1]["text"] == "" and result["blocks"][2]["locator"]["page"] == 3
        assert "printed label 12" in result["blocks"][2]["text"]
    elif item["format"] == "jats_xml":
        assert all("page" not in block["locator"] for block in result["blocks"])
        assert sum(block["locator"]["tag"] == "table-wrap" for block in result["blocks"]) == 1
        assert all("/back[" not in block["locator"]["path"] for block in result["blocks"])
        assert "REFERENCE-ONLY" not in "\n".join(block["text"] for block in result["blocks"])
    assert parser(content, item["format"]) == result


@pytest.mark.parametrize("content,format", [
    (None, "txt"), ("text", "txt"), (bytearray(b"text"), "txt"), (b"", "txt"), (b" \t\r\n", "txt"),
    (b"\xef\xbb\xbf \r\n", "txt"), (b"\xff", "txt"), (b"text", "TXT"), (b"text", "xml"), (b"text", None),
    (b"<article><body><p>Partial</p>", "jats_xml"), (b"<ERROR>Publisher error</ERROR>", "jats_xml"),
    (b"<html><body>Article unavailable</body></html>", "jats_xml"), (b"<article><body/></article>", "jats_xml"),
    (b'<!DOCTYPE article [<!ENTITY x "expanded">]><article><body><p>&x;</p></body></article>', "jats_xml"),
    (b"%PDF-1.7\nnot a readable PDF", "pdf"),
])
def test_invalid_sources_reject_pure_parse_and_attachment_atomically(tmp_path, parser, content, format):
    with pytest.raises(ValueError):
        parser(content, format)
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id, reports = project_reports(store)
        before = state(store, project_id)
        with pytest.raises(ValueError):
            store.attach_document(project_id, reports[0], content, format, "Alice", "Invalid-source probe")
        assert state(store, project_id) == before


@pytest.mark.parametrize("kind", ["blank_pdf", "encrypted_pdf"])
def test_blank_or_encrypted_pdf_cannot_create_source_versions(tmp_path, parser, kind):
    import fitz
    document = fitz.open()
    try:
        page = document.new_page()
        if kind == "encrypted_pdf":
            page.insert_text((72, 72), "Readable only after a password; no guessing permitted")
            content = document.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="synthetic-user", owner_pw="synthetic-owner")
        else:
            document.new_page()
            content = document.tobytes()
    finally:
        document.close()
    with pytest.raises(ValueError):
        parser(content, "pdf")
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id, reports = project_reports(store)
        before = state(store, project_id)
        with pytest.raises(ValueError):
            store.attach_document(project_id, reports[0], content, "pdf", "Alice", "Rejected PDF")
        assert state(store, project_id) == before


@pytest.mark.parametrize("filename", ["", ".", "..", "../source.txt", "sub/source.txt", "sub\\source.txt", "/source.txt", "null\x00.txt", "line\n.txt", "del\x7f.txt", "control\u0085.txt"])
def test_unsafe_filenames_leave_no_document_version(tmp_path, oracle, filename):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id, reports = project_reports(store)
        before = state(store, project_id)
        with pytest.raises(ValueError):
            attach(store, project_id, reports[0], oracle["text_v1"], filename=filename)
        assert state(store, project_id) == before


@pytest.mark.parametrize("field,value", [("reviewer", ""), ("reason", " \t"), ("reviewer", None), ("reason", 1),
                                         ("filename", 1), ("source_url", None), ("source_url", []), ("version_label", None), ("version_label", 1)])
def test_invalid_attachment_metadata_is_atomic(tmp_path, oracle, field, value):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id, reports = project_reports(store)
        before = state(store, project_id)
        options = {"reviewer": "Alice", "reason": "Source audit", "filename": None, "source_url": "", "version_label": ""}
        options[field] = value
        with pytest.raises(ValueError):
            store.attach_document(project_id, reports[0], (FIXTURES / oracle["text_v1"]["file"]).read_bytes(), "txt", **options)
        assert state(store, project_id) == before


def test_per_report_versions_exact_bytes_and_blocks_survive_reopen_and_source_deletion(tmp_path, oracle, monkeypatch):
    database = tmp_path / "reviews.sqlite3"
    source = tmp_path / "original-source.txt"
    source.write_bytes((FIXTURES / oracle["text_v1"]["file"]).read_bytes())
    with ReviewStore(database) as store:
        project_id, reports = project_reports(store)
        before = state(store, project_id)
        first = store.attach_document(project_id, reports[0], source.read_bytes(), "txt", "Alice", "Original source", source_url="https://example.invalid/not-fetched", version_label="Publisher label retained")
        other = attach(store, project_id, reports[1], oracle["pdf_three_pages"])
        second = attach(store, project_id, reports[0], oracle["text_v2"])
        third = attach(store, project_id, reports[0], oracle["text_v2"])
        assert [doc["version"] for doc in (first, other, second, third)] == [1, 1, 2, 3]
        assert len({doc["id"] for doc in (first, other, second, third)}) == 4
        assert second["source_sha256"] == third["source_sha256"] != first["source_sha256"]
        assert first["blocks_sha256"] != second["blocks_sha256"]
        docs = store.list_documents(project_id)
        assert [doc["id"] for doc in docs] == [first["id"], other["id"], second["id"], third["id"]]
        assert [doc["active"] for doc in docs] == [False, True, False, True]
        assert [doc["version"] for doc in store.list_documents(project_id, reports[0])] == [1, 2, 3]
        for returned, alias in ((first, "text_v1"), (other, "pdf_three_pages"), (second, "text_v2"), (third, "text_v2")):
            item = oracle[alias]
            assert type(returned["version"]) is int and returned["active"] is True
            assert returned["source_sha256"] == item["source_sha256"] and returned["blocks_sha256"] == item["expected_blocks_sha256"]
            assert returned["size_bytes"] == item["size_bytes"] and returned["block_count"] == item["expected_block_count"]
            assert returned["filename"] == {"txt": "source.txt", "jats_xml": "source.xml", "pdf": "source.pdf"}[item["format"]]
            assert returned["parser_id"] == item["expected_parser_id"] and returned["parser_metadata"] == metadata_for(item["format"])
            assert returned["source_identifiers"] == {}
            assert store.get_source_blocks(project_id, returned["id"]) == item["expected_blocks"]
            assert store.get_document_bytes(project_id, returned["id"]) == (FIXTURES / item["file"]).read_bytes()
        assert first["source_url"] == "https://example.invalid/not-fetched" and first["version_label"] == "Publisher label retained"
        assert second["source_url"] == "" and second["version_label"] == ""
        for field in ("records", "runs", "occurrences", "decisions", "retrieval", "counts", "links", "link_events"):
            assert state(store, project_id)[field] == before[field]
        saved = state(store, project_id)
    source.unlink()
    def no_reparse(*args, **kwargs):
        pytest.fail("Durable source read attempted to reparse")
    monkeypatch.setattr("src.review.documents.parse_source_bytes", no_reparse)
    with ReviewStore(database) as store:
        assert state(store, project_id) == saved
        exported = store.export_project(project_id, tmp_path / "durable-export")
        assert len(exported["files"]) == 15


def test_attachment_parses_hashes_and_stores_the_same_immutable_byte_snapshot(tmp_path, oracle, monkeypatch):
    from src.review import documents
    source = tmp_path / "source.txt"
    original = (FIXTURES / oracle["text_v1"]["file"]).read_bytes()
    replacement = (FIXTURES / oracle["text_v2"]["file"]).read_bytes()
    source.write_bytes(original)
    captured = source.read_bytes()
    parse = documents.parse_source_bytes
    calls = []
    def change_file_after_snapshot(content, format):
        calls.append((content, format))
        source.write_bytes(replacement)
        return parse(content, format)
    monkeypatch.setattr(documents, "parse_source_bytes", change_file_after_snapshot)
    def no_file_read(*args, **kwargs):
        pytest.fail("Attachment reread a file instead of supplied bytes")
    monkeypatch.setattr(Path, "read_bytes", no_file_read)
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id, reports = project_reports(store)
        doc = store.attach_document(project_id, reports[0], captured, "txt", "Alice", "Immutable snapshot", filename=source.name, source_url=str(source))
        assert calls == [(original, "txt")]
        assert store.get_document_bytes(project_id, doc["id"]) == original
        assert store.get_source_blocks(project_id, doc["id"]) == oracle["text_v1"]["expected_blocks"]
        assert doc["source_sha256"] == sha256(original)


def test_unknown_foreign_project_record_and_document_ids_are_rejected_without_changes(tmp_path, oracle):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        first_id, reports = project_reports(store)
        second_id, other_reports = project_reports(store, "Other source review")
        first = attach(store, first_id, reports[0], oracle["jats_v1"])
        other = attach(store, second_id, other_reports[0], oracle["jats_v2"])
        before = state(store, first_id), state(store, second_id)
        operations = [lambda: store.attach_document(first_id, other_reports[0], b"Valid", "txt", "Alice", "Wrong report"),
                      lambda: store.attach_document(first_id, "unknown-record", b"Valid", "txt", "Alice", "Unknown report"),
                      lambda: store.attach_document("unknown", reports[0], b"Valid", "txt", "Alice", "Wrong project"),
                      lambda: store.list_documents("unknown"), lambda: store.list_documents(first_id, other_reports[0]),
                      lambda: store.list_documents(first_id, "unknown-record")]
        for getter in (store.get_document_bytes, store.get_source_blocks):
            operations.extend([lambda getter=getter: getter(first_id, other["id"]), lambda getter=getter: getter(second_id, first["id"]),
                               lambda getter=getter: getter(first_id, "unknown-document"), lambda getter=getter: getter("unknown", first["id"])])
        for operation in operations:
            with pytest.raises(ValueError):
                operation()
            assert (state(store, first_id), state(store, second_id)) == before


def test_exact_document_export_old_versions_formula_csv_and_determinism(tmp_path, oracle):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id, reports = project_reports(store)
        old_counts = store.counts(project_id)
        first = store.attach_document(project_id, reports[0], (FIXTURES / oracle["text_v1"]["file"]).read_bytes(), "txt",
                                      "@source-reviewer", '=Source checked, "quoted"\nExact reason', filename="=source α.txt", version_label="=Label retained")
        second = attach(store, project_id, reports[0], oracle["jats_v2"])
        third = attach(store, project_id, reports[1], oracle["pdf_three_pages"])
        directory = tmp_path / "exported sources"
        directory.mkdir()
        (directory / "notes.txt").write_text("Unrelated annotation")
        result = store.export_project(project_id, directory)
        assert result["counts"] == old_counts and len(result["files"]) == 14
        bundle = json.loads((directory / "project.json").read_text())
        assert bundle["documents"] == store.list_documents(project_id) and bundle["counts"] == old_counts
        rows = [{"document_id": doc["id"], **block} for doc in bundle["documents"] for block in store.get_source_blocks(project_id, doc["id"])]
        assert bundle["source_blocks"] == rows
        assert json.loads((directory / "source_blocks.json").read_text()) == rows
        assert len(bundle["document_artifacts"]) == 3
        for doc, alias in ((first, "text_v1"), (second, "jats_v2"), (third, "pdf_three_pages")):
            manifest = next(row for row in bundle["document_artifacts"] if row["document_id"] == doc["id"])
            expected_path = f"documents/{doc['id']}/{doc['filename']}"
            assert manifest == {"document_id": doc["id"], "sha256": doc["source_sha256"], "size_bytes": doc["size_bytes"], "export_file": expected_path}
            assert expected_path in result["files"]
            assert (directory / expected_path).read_bytes() == (FIXTURES / oracle[alias]["file"]).read_bytes()
        with (directory / "documents.csv").open(newline="", encoding="utf-8") as handle:
            csv_rows = list(csv.DictReader(handle))
        assert csv_rows[0]["filename"] == "'=source α.txt" and csv_rows[0]["reviewer"] == "'@source-reviewer"
        assert csv_rows[0]["reason"] == '\'=Source checked, "quoted"\nExact reason'
        assert [json.loads(row["parser_metadata"]) for row in csv_rows] == [doc["parser_metadata"] for doc in bundle["documents"]]
        assert [json.loads(row["source_identifiers"]) for row in csv_rows] == [doc["source_identifiers"] for doc in bundle["documents"]]
        assert bundle["documents"][0]["filename"] == "=source α.txt" and bundle["documents"][0]["version_label"] == "=Label retained"
        assert (directory / "notes.txt").read_text() == "Unrelated annotation"
        again = tmp_path / "exported again"
        store.export_project(project_id, again)
        assert {name: (directory / name).read_bytes() for name in result["files"]} == {name: (again / name).read_bytes() for name in result["files"]}


def test_export_snapshot_keeps_active_versions_blocks_and_bytes_consistent_during_second_writer(tmp_path, oracle, monkeypatch):
    database = tmp_path / "reviews.sqlite3"
    with ReviewStore(database) as store:
        project_id, reports = project_reports(store)
        attach(store, project_id, reports[0], oracle["text_v1"])
        before = state(store, project_id)
        with sqlite3.connect(database) as connection:
            assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        original = store.list_records
        triggered = False
        def read_then_commit(pid):
            nonlocal triggered
            rows = original(pid)
            if not triggered:
                triggered = True
                with ReviewStore(database) as writer:
                    attach(writer, project_id, reports[0], oracle["text_v2"])
            return rows
        monkeypatch.setattr(store, "list_records", read_then_commit)
        directory = tmp_path / "snapshot-export"
        result = store.export_project(project_id, directory)
        bundle = json.loads((directory / "project.json").read_text())
        assert triggered and bundle["documents"] == before["documents"]
        assert bundle["counts"] == result["counts"] == before["counts"]
        doc_id = before["documents"][0]["id"]
        assert bundle["source_blocks"] == [{"document_id": doc_id, **block} for block in before["blocks"][doc_id]]
        assert (directory / bundle["document_artifacts"][0]["export_file"]).read_bytes() == before["bytes"][doc_id]
        assert [doc["active"] for doc in store.list_documents(project_id)] == [False, True]


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def resolve_path(article, path):
    parts = path.strip("/").split("/")
    root_name, root_index = re.fullmatch(r"([^\[]+)\[(\d+)\]", parts[0]).groups()
    assert root_name == local_name(article.tag) == "article" and root_index == "1"
    node = article
    ancestors = [article]
    for part in parts[1:]:
        name, index = re.fullmatch(r"([^\[]+)\[(\d+)\]", part).groups()
        matching = [child for child in node if local_name(child.tag) == name]
        node = matching[int(index) - 1]
        ancestors.append(node)
    return node, ancestors


@pytest.mark.parametrize("alias", ["coach", "whitehall", "raptor"])
def test_actual_pinned_medical_jats_blocks_resolve_to_their_exact_source_elements(tmp_path, parser, alias):
    source = next(row for row in json.loads((MEDICAL / "manifest.json").read_text())["sources"] if row["alias"] == alias)
    content = (MEDICAL / source["file"]).read_bytes()
    assert sha256(content) == source["sha256"] and len(content) == source["size_bytes"]
    article = ET.fromstring(content)
    own_dois = [element.text for element in article.findall("./front/article-meta/article-id") if element.get("pub-id-type") == "doi"]
    assert own_dois == [source["doi"]]
    parsed = parser(content, "jats_xml")
    assert parsed["parser_metadata"] == metadata_for("jats_xml")
    assert parsed["source_identifiers"] == {"doi": source["doi"]}
    assert parsed["blocks"][0]["text"] == source["title"]
    assert len(parsed["blocks"]) > 20 and len({block["id"] for block in parsed["blocks"]}) == len(parsed["blocks"])
    for ordinal, block in enumerate(parsed["blocks"], start=1):
        locator = block["locator"]
        assert locator["type"] == "xml_element" and "page" not in locator
        assert block["id"] == "xml:" + locator["path"] and block["ordinal"] == ordinal
        element, ancestors = resolve_path(article, locator["path"])
        assert locator["tag"] == local_name(element.tag) and all(local_name(parent.tag) not in {"back", "ref-list", "sub-article"} for parent in ancestors)
        if locator["tag"] == "p":
            assert any(local_name(parent.tag) in {"body", "abstract"} for parent in ancestors)
        if locator["tag"] == "article-title":
            assert element is article.find("./front/article-meta/title-group/article-title")
        if element.get("id"):
            assert locator["element_id"] == element.get("id")
        if locator["tag"] != "table-wrap":
            assert block["text"] == " ".join("".join(element.itertext()).split())
            assert all(local_name(parent.tag) != "table-wrap" for parent in ancestors)
        else:
            label = element.find("label")
            if label is not None:
                assert locator["table_label"] == " ".join("".join(label.itertext()).split())
        sections = [parent for parent in ancestors[:-1] if local_name(parent.tag) == "sec"]
        if sections:
            title = sections[-1].find("title")
            if title is not None:
                assert locator["section_title"] == " ".join("".join(title.itertext()).split())
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = store.create_project("Pinned publisher source", "scoping", "Do locators retain their source?")["id"]
        store.import_records(project_id, SearchRunSpec("Pinned publisher bibliography"), [BibliographicRecord(title=source["title"], doi=source["doi"])])
        record_id = store.list_records(project_id)[0]["id"]
        doc = store.attach_document(project_id, record_id, content, "jats_xml", "Source reviewer", "Publisher snapshot checked", filename=source["file"], source_url=source["download_url"], version_label=source["version_statement"])
        assert store.get_source_blocks(project_id, doc["id"]) == parsed["blocks"]
        assert store.get_document_bytes(project_id, doc["id"]) == content and doc["source_sha256"] == source["sha256"]
        assert doc["source_identifiers"] == {"doi": source["doi"]}
        store.import_records(project_id, SearchRunSpec("Wrong report probe"), [BibliographicRecord(title=source["title"], doi="10.99999/wrong-medical-source")])
        wrong_record = store.list_records(project_id)[1]["id"]
        before = state(store, project_id)
        with pytest.raises(ValueError):
            store.attach_document(project_id, wrong_record, content, "jats_xml", "Alice", "Wrong report despite matching title")
        assert state(store, project_id) == before


def identifier_xml(own="", cited=""):
    return ("<article><front><article-meta>" + own + "<title-group><article-title>Invented identity probe</article-title></title-group></article-meta></front>"
            "<body><p>Source identity is explicit metadata, not a clinical assertion.</p></body><back><ref-list><ref>" + cited + "</ref></ref-list></back></article>").encode("utf-8")


def test_namespaced_jats_uses_local_tag_paths_and_sibling_indices(parser):
    content = b'<j:article xmlns:j="urn:synthetic:jats"><j:front><j:article-meta><j:article-id pub-id-type="doi">10.99999/NAMESPACED</j:article-id></j:article-meta></j:front><j:body><j:p>X<j:sub>2</j:sub></j:p><j:label>interleaved sibling</j:label><j:p>Second paragraph.</j:p></j:body></j:article>'
    result = parser(content, "jats_xml")
    assert result["source_identifiers"] == {"doi": "10.99999/namespaced"}
    assert result["blocks"] == [
        {"id": "xml:/article[1]/body[1]/p[1]", "ordinal": 1, "text": "X2", "locator": {"type": "xml_element", "path": "/article[1]/body[1]/p[1]", "tag": "p"}},
        {"id": "xml:/article[1]/body[1]/p[2]", "ordinal": 2, "text": "Second paragraph.", "locator": {"type": "xml_element", "path": "/article[1]/body[1]/p[2]", "tag": "p"}},
    ]


def test_nested_peer_review_and_editorial_subarticles_do_not_become_primary_finding_blocks(parser):
    content = b'<article><body><p>Main source paragraph.</p></body><sub-article article-type="reviewer-report"><front><article-meta><article-id pub-id-type="doi">malformed excluded identity</article-id><title-group><article-title>PEER_REVIEW_TITLE</article-title></title-group><abstract><p>PEER_REVIEW_ABSTRACT</p></abstract></article-meta></front><body><p>PEER_REVIEW_BODY</p><table-wrap><table><tr><td>PEER_REVIEW_TABLE</td></tr></table></table-wrap></body></sub-article><sub-article article-type="reply"><body><p>EDITORIAL_RESPONSE_BODY</p></body></sub-article></article>'
    result = parser(content, "jats_xml")
    assert result["source_identifiers"] == {}
    assert result["blocks"] == [{"id": "xml:/article[1]/body[1]/p[1]", "ordinal": 1, "text": "Main source paragraph.",
                                "locator": {"type": "xml_element", "path": "/article[1]/body[1]/p[1]", "tag": "p"}}]


def test_only_own_explicit_identifiers_are_normalized_and_cited_ids_cannot_supply_identity(tmp_path, parser):
    own = ('<article-id pub-id-type="doi"> https://doi.org/10.99999/SOURCE-AUDIT-1 </article-id>'
           '<article-id pub-id-type="doi">doi:10.99999/source-audit-1</article-id>'
           '<article-id pub-id-type="pmid">PMID: 000999999111</article-id>'
           '<article-id pub-id-type="pmid">999999111</article-id>')
    cited = '<article-id pub-id-type="doi">not a valid DOI</article-id><article-id pub-id-type="pmid">not a PMID</article-id>'
    content = identifier_xml(own, cited)
    parsed = parser(content, "jats_xml")
    assert parsed["source_identifiers"] == {"doi": "10.99999/source-audit-1", "pmid": "999999111"}
    assert parser(identifier_xml(cited=cited), "jats_xml")["source_identifiers"] == {}
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id, reports = project_reports(store)
        original_records = store.list_records(project_id)
        doc = store.attach_document(project_id, reports[0], content, "jats_xml", "Alice", "Known DOI matches; unknown PMID stays source metadata")
        assert doc["source_identifiers"] == parsed["source_identifiers"]
        assert store.list_records(project_id) == original_records
        # A missing source ID remains unknown even when cited reference IDs differ.
        cited_other = '<article-id pub-id-type="doi">10.99999/foreign-citation</article-id>'
        doc = store.attach_document(project_id, reports[1], identifier_xml(cited=cited_other), "jats_xml", "Alice", "Own identifier missing")
        assert doc["source_identifiers"] == {}


@pytest.mark.parametrize("own", [
    '<article-id pub-id-type="doi">broken</article-id>', '<article-id pub-id-type="pmid">zero</article-id>',
    '<article-id pub-id-type="doi">10.99999/a</article-id><article-id pub-id-type="doi">10.99999/b</article-id>',
    '<article-id pub-id-type="pmid">999999111</article-id><article-id pub-id-type="pmid">999999112</article-id>',
])
def test_invalid_or_conflicting_repeated_own_identifiers_reject_without_versions(tmp_path, parser, own):
    content = identifier_xml(own)
    with pytest.raises(ValueError):
        parser(content, "jats_xml")
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id, reports = project_reports(store)
        before = state(store, project_id)
        with pytest.raises(ValueError):
            store.attach_document(project_id, reports[0], content, "jats_xml", "Alice", "Invalid own ID")
        assert state(store, project_id) == before


@pytest.mark.parametrize("field", ["doi", "pmid"])
def test_source_identifier_of_same_type_cannot_contradict_known_report(tmp_path, field):
    own_doi = "10.99999/other-report" if field == "doi" else "10.99999/known-report"
    own_pmid = "999999112" if field == "pmid" else "999999111"
    content = identifier_xml(f'<article-id pub-id-type="doi">{own_doi}</article-id><article-id pub-id-type="pmid">{own_pmid}</article-id>')
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = store.create_project("Identity guard", "systematic", "Is this the same report?")["id"]
        store.import_records(project_id, SearchRunSpec("Known bibliography"), [BibliographicRecord(title="Invented identity probe", doi="10.99999/known-report", pmid="999999111")])
        record_id = store.list_records(project_id)[0]["id"]
        before = state(store, project_id)
        with pytest.raises(ValueError):
            store.attach_document(project_id, record_id, content, "jats_xml", "Alice", "Contradictory identity")
        assert state(store, project_id) == before


@pytest.mark.parametrize("corruption", ["content", "blocks_json", "source_sha256", "blocks_sha256", "malformed_blocks"])
def test_corrupt_inactive_version_rejects_both_getters_and_export_before_output_changes(tmp_path, oracle, corruption):
    database = tmp_path / "reviews.sqlite3"
    with ReviewStore(database) as store:
        project_id, reports = project_reports(store)
        first = attach(store, project_id, reports[0], oracle["text_v1"])
        attach(store, project_id, reports[0], oracle["text_v2"])
        destination = tmp_path / "preexisting-export"
        exported = store.export_project(project_id, destination)
        previous = {name: (destination / name).read_bytes() for name in exported["files"]}
    if corruption == "content":
        column, value = "content", b"Altered source without updating its hash"
    elif corruption == "blocks_json":
        altered = deepcopy(oracle["text_v1"]["expected_blocks"])
        altered[0]["text"] = "Altered canonical block without updating its hash"
        column, value = "blocks_json", json.dumps(altered, ensure_ascii=False)
    elif corruption == "malformed_blocks":
        column, value = "blocks_json", "{not-json"
    else:
        column, value = corruption, "0" * 64
    with sqlite3.connect(database) as connection:
        connection.execute(f"UPDATE source_documents SET {column} = ? WHERE id = ?", (value, first["id"]))
    with ReviewStore(database) as store:
        for getter in (store.get_document_bytes, store.get_source_blocks):
            with pytest.raises(ValueError):
                getter(project_id, first["id"])
        with pytest.raises(ValueError):
            store.export_project(project_id, destination)
    assert {name: (destination / name).read_bytes() for name in exported["files"]} == previous
    assert not list(destination.glob(".review-export-*"))


def test_old_schema_reopens_without_document_data_or_new_count_meanings(tmp_path):
    database = tmp_path / "reviews.sqlite3"
    with ReviewStore(database) as store:
        project_id, reports = project_reports(store)
        before = state(store, project_id)
        assert before["documents"] == []
        assert len(store.export_project(project_id, tmp_path / "before-export")["files"]) == 9
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE source_documents")
    with ReviewStore(database) as store:
        assert state(store, project_id) == before
        result = store.export_project(project_id, tmp_path / "after-export")
        assert len(result["files"]) == 9 and result["counts"] == before["counts"]
        bundle = json.loads((tmp_path / "after-export" / "project.json").read_text())
        assert not {"documents", "source_blocks", "document_artifacts"}.intersection(bundle)


def test_document_export_preserves_existing_pubmed_assets_and_manual_study_arrays(tmp_path, oracle):
    from src.search.pubmed_search import capture_pubmed_search, import_pubmed_capture, verify_pubmed_capture
    pubmed = json.loads((PUBMED / "manifest.json").read_text())
    responses = [(PUBMED / pubmed["search_file"]).read_bytes()] + [(PUBMED / batch["response_file"]).read_bytes() for batch in pubmed["batches"]]
    class Client:
        def request(self, endpoint, params):
            return responses.pop(0)
    capture = capture_pubmed_search(pubmed["query"], tmp_path / "capture", client=Client(), batch_size=2)
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = store.create_project("Combined provenance", "scoping", "Are all sources retained?")["id"]
        imported = import_pubmed_capture(store, project_id, capture["directory"])
        assets = store.get_search_artifacts(project_id, imported["search_run_id"])
        record_id = store.list_records(project_id)[0]["id"]
        study = store.create_study(project_id, "Manual source identity", "Alice", "Invented association")
        event = store.record_study_links(project_id, record_id, [study["id"]], "Alice", "Source association before screening")
        before_counts = store.counts(project_id)
        doc = attach(store, project_id, record_id, oracle["jats_v1"])
        directory = tmp_path / "combined-export"
        result = store.export_project(project_id, directory)
        bundle = json.loads((directory / "project.json").read_text())
        assert len(result["files"]) == 21 and bundle["counts"] == before_counts
        assert bundle["studies"] == [study] and bundle["study_link_events"] == [event]
        assert bundle["documents"] == [doc] and bundle["search_runs"][0]["execution"] == capture["receipt"]
        for asset in bundle["search_artifacts"]:
            assert (directory / asset["export_file"]).read_bytes() == assets[asset["name"]]
        assert verify_pubmed_capture(directory / "search_captures" / imported["search_run_id"])["receipt"] == capture["receipt"]


def test_fresh_source_parse_and_durable_pdf_reads_load_no_models_settings_or_pdf_parser(tmp_path, oracle):
    database = tmp_path / "reviews.sqlite3"
    with ReviewStore(database) as store:
        project_id, reports = project_reports(store)
        doc = attach(store, project_id, reports[0], oracle["pdf_three_pages"])
    code = """
import json, socket, sys
sys.path.insert(0, sys.argv[1])
def denied(*args, **kwargs):
    raise AssertionError('Document API attempted network')
socket.create_connection = denied
from src.review.documents import parse_source_bytes
from src.review.store import ReviewStore
assert parse_source_bytes(b'Exact text', 'txt')['blocks'][0]['text'] == 'Exact text'
assert parse_source_bytes(b'<article><body><p>Exact XML</p></body></article>', 'jats_xml')['blocks'][0]['text'] == 'Exact XML'
with ReviewStore(sys.argv[2]) as store:
    assert len(store.get_source_blocks(sys.argv[3], sys.argv[4])) == 3
    assert store.get_document_bytes(sys.argv[3], sys.argv[4]).startswith(b'%PDF-')
    store.export_project(sys.argv[3], sys.argv[5])
assert not {'torch','chromadb','sentence_transformers','dotenv','src.settings','fitz','pymupdf'}.intersection(sys.modules)
print(json.dumps({'isolated': True}))
"""
    result = subprocess.run([sys.executable, "-c", code, str(ROOT), str(database), project_id, doc["id"], str(tmp_path / "isolated-export")],
                            cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and result.stderr == "", result.stderr
    assert json.loads(result.stdout) == {"isolated": True}
