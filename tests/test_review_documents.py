"""Source-version persistence and exact synthetic quotation-block truth."""

import csv
import hashlib
import json
import platform
from pathlib import Path

import pytest

from src.review.documents import parse_source_bytes
from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.store import ReviewStore


FIXTURES = Path(__file__).parent / "fixtures/evidence"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text())


def digest(content):
    return hashlib.sha256(content).hexdigest()


def block_digest(blocks):
    return digest(json.dumps(blocks, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"))


def scenario(store, *, doi=None, pmid=None):
    project = store.create_project("Synthetic source review", "systematic", "Software question")["id"]
    store.import_records(project, SearchRunSpec("invented"), [BibliographicRecord(title="Software report", doi=doi, pmid=pmid)])
    return project, store.list_records(project)[0]["id"]


@pytest.mark.parametrize("fixture", MANIFEST["fixtures"], ids=lambda value: value["alias"])
def test_independent_fixture_blocks_hashes_and_quote_offsets(fixture):
    content = (FIXTURES / fixture["file"]).read_bytes()
    parsed = parse_source_bytes(content, fixture["format"])
    assert digest(content) == fixture["source_sha256"]
    assert parsed["parser_id"] == fixture["expected_parser_id"]
    assert parsed["blocks"] == fixture["expected_blocks"]
    assert block_digest(parsed["blocks"]) == fixture["expected_blocks_sha256"]
    assert parsed["source_identifiers"] == {}
    expected = {"python_version": platform.python_version()}
    if fixture["format"] == "txt":
        expected.update(encoding="utf-8-sig", normalization="none")
    elif fixture["format"] == "jats_xml":
        expected.update(normalization="xml-whitespace-v1", tables="rows-tab-separated-v1", external_dtd="ignored", entities="rejected")
    else:
        import fitz
        expected.update(pymupdf_version=fitz.VersionBind, sort=True, normalization="none")
    assert parsed["parser_metadata"] == expected
    blocks = {block["id"]: block for block in parsed["blocks"]}
    for quote in fixture["quotes"]:
        assert blocks[quote["block_id"]]["text"][quote["start"]:quote["end"]] == quote["quote"]


def test_pure_parser_does_not_read_files_and_main_article_scope(monkeypatch):
    xml = b'''<!DOCTYPE article SYSTEM "https://invalid.example/never-fetch.dtd">
    <article xmlns="urn:test"><front><article-meta><title-group><article-title>Main <italic>title</italic>.</article-title></title-group></article-meta></front>
    <body><sec><title>Outer</title><sec><p id="p">Text <bold>joined</bold> correctly.</p></sec></sec></body>
    <sub-article><front><article-meta><title-group><article-title>Peer title</article-title></title-group></article-meta></front><body><p>Peer review letter.</p></body></sub-article>
    <back><ref-list><ref><p>Reference only.</p></ref></ref-list></back></article>'''
    monkeypatch.setattr(Path, "read_bytes", lambda *args: pytest.fail("Parser must use supplied bytes"))
    assert parse_source_bytes(b"\xef\xbb\xbfText\r\n", "txt")["blocks"][0]["text"] == "Text\r\n"
    blocks = parse_source_bytes(xml, "jats_xml")["blocks"]
    assert [block["text"] for block in blocks] == ["Main title.", "Text joined correctly."]
    assert blocks[1]["locator"] == {"type": "xml_element", "path": "/article[1]/body[1]/sec[1]/sec[1]/p[1]", "tag": "p", "element_id": "p", "section_title": "Outer"}


def own_ids(*ids):
    elements = "".join(f'<article-id pub-id-type="{kind}">{value}</article-id>' for kind, value in ids)
    return f'<article><front><article-meta>{elements}</article-meta></front><body><p>Software source.</p></body><back><ref-list><ref><article-id pub-id-type="doi">bad reference</article-id><article-id pub-id-type="pmid">bad reference</article-id></ref></ref-list></back></article>'.encode()


def test_own_identifiers_are_normalized_and_same_type_contradictions_are_atomic():
    content = own_ids(("doi", "DOI:10.1234/SYNTHETIC"), ("doi", "https://doi.org/10.1234/synthetic"), ("pmid", "PMID:000123"))
    assert parse_source_bytes(content, "jats_xml")["source_identifiers"] == {"doi": "10.1234/synthetic", "pmid": "123"}
    with ReviewStore(":memory:") as store:
        project, record = scenario(store, doi="10.1234/synthetic", pmid="123")
        saved = store.attach_document(project, record, content, "jats_xml", "Alice", "Same report")
        assert saved["source_identifiers"] == {"doi": "10.1234/synthetic", "pmid": "123"}
        for mismatch in [own_ids(("doi", "10.1234/other")), own_ids(("pmid", "124"))]:
            with pytest.raises(ValueError, match="contradicts"):
                store.attach_document(project, record, mismatch, "jats_xml", "Alice", "Wrong report")
            assert store.list_documents(project) == [saved]
        # A supplied missing-type identifier remains source provenance, not inferred report metadata.
        other, other_record = scenario(store)
        store.attach_document(other, other_record, content, "jats_xml", "Alice", "Manual association")
        canonical = store.list_records(other)[0]
        assert canonical["doi"] is canonical["pmid"] is None


@pytest.mark.parametrize("ids", [[("doi", "bad")], [("pmid", "0")], [("doi", " ")], [("pmid", "")], [("doi", "10.1234/a"), ("doi", "10.1234/b")], [("pmid", "123"), ("pmid", "124")]])
def test_invalid_or_conflicting_own_identifiers_fail(ids):
    with pytest.raises(ValueError, match="own"):
        parse_source_bytes(own_ids(*ids), "jats_xml")


def test_new_versions_same_bytes_reopen_and_counts_unchanged(tmp_path, monkeypatch):
    database = tmp_path / "ledger.sqlite3"
    content = (FIXTURES / "source-v1.txt").read_bytes()
    source = tmp_path / "removed.txt"
    source.write_bytes(content)
    monkeypatch.setattr("src.review.documents._now", lambda: "2026-10-03T00:00:00+00:00")
    with ReviewStore(database) as store:
        project, record = scenario(store)
        before = store.counts(project)
        first = store.attach_document(project, record, content, "txt", "Alice", "First association", source_url="https://invalid.example/unfetched", version_label="Publisher A")
        repeat = store.attach_document(project, record, content, "txt", "Bob", "Checked same bytes")
        replacement = store.attach_document(project, record, (FIXTURES / "source-v2.txt").read_bytes(), "txt", "Alice", "Replacement")
        assert [document["version"] for document in store.list_documents(project, record)] == [1, 2, 3]
        assert first["source_sha256"] == repeat["source_sha256"] != replacement["source_sha256"]
        assert first["blocks_sha256"] == repeat["blocks_sha256"] != replacement["blocks_sha256"]
        assert [document["active"] for document in store.list_documents(project)] == [False, False, True]
        assert first["size_bytes"] == len(content) and first["block_count"] == 1
        assert first["filename"] == "source.txt"
        assert store.counts(project) == before
        documents = store.list_documents(project)
    source.unlink()
    with ReviewStore(database) as store:
        monkeypatch.setattr("src.review.documents.parse_source_bytes", lambda *args: pytest.fail("Retained reads must not reparse"))
        assert store.list_documents(project) == documents
        assert store.get_document_bytes(project, first["id"]) == content
        assert store.get_source_blocks(project, first["id"]) == MANIFEST["fixtures"][0]["expected_blocks"]
        assert store.counts(project) == before


@pytest.mark.parametrize("content,format", [(b"", "txt"), (b" \r\n", "txt"), ("text", "txt"), (bytearray(b"text"), "txt"), (b"\xff", "txt"), (b"text", "TXT"), (b"text", None), (b"<article>", "jats_xml"), (b"<body><p>Wrong root</p></body>", "jats_xml"), (b"<article><body><p> </p></body></article>", "jats_xml"), (b'<!DOCTYPE article [<!ENTITY x "text">]><article><body><p>&x;</p></body></article>', "jats_xml"), (b"<article><ERROR>Server failure</ERROR><body><p>Text</p></body></article>", "jats_xml"), (b"not a pdf", "pdf")])
def test_invalid_source_parse_is_contextual_and_atomic(content, format):
    with ReviewStore(":memory:") as store:
        project, record = scenario(store)
        with pytest.raises(ValueError):
            store.attach_document(project, record, content, format, "Alice", "Source")
        assert store.list_documents(project) == []


def test_encrypted_and_all_blank_pdf_rejected():
    import fitz
    with fitz.open() as pdf:
        pdf.new_page()
        blank = pdf.tobytes()
        pdf[0].insert_text((40, 40), "Software source")
        encrypted = pdf.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="reader")
    for content in (blank, encrypted):
        with pytest.raises(ValueError):
            parse_source_bytes(content, "pdf")


@pytest.mark.parametrize("kwargs", [{"filename": "../source.txt"}, {"filename": "a/b.txt"}, {"filename": "a\\b.txt"}, {"filename": ".."}, {"filename": " "}, {"filename": "bad\n.txt"}, {"filename": "bad\x7f.txt"}, {"filename": "bad\x85.txt"}, {"filename": 42}, {"reviewer": " "}, {"reason": ""}, {"source_url": None}, {"version_label": 1}])
def test_invalid_attachment_metadata_is_atomic(kwargs):
    args = {"reviewer": "Alice", "reason": "Source", **kwargs}
    with ReviewStore(":memory:") as store:
        project, record = scenario(store)
        with pytest.raises(ValueError):
            store.attach_document(project, record, b"Software source", "txt", **args)
        assert store.list_documents(project) == []


def test_document_project_record_ownership_and_per_record_versions():
    with ReviewStore(":memory:") as store:
        first, record = scenario(store)
        second, other_record = scenario(store)
        document = store.attach_document(first, record, b"First source", "txt", "Alice", "Source")
        other = store.attach_document(second, other_record, b"Second source", "txt", "Alice", "Source")
        assert document["version"] == other["version"] == 1
        for project, target in [(second, document["id"]), (first, "unknown")]:
            for getter in (store.get_document_bytes, store.get_source_blocks):
                with pytest.raises(ValueError, match="Unknown source document"):
                    getter(project, target)
        with pytest.raises(ValueError, match="Unknown record"):
            store.list_documents(second, record)
        with pytest.raises(ValueError, match="Unknown record"):
            store.attach_document(second, record, b"Source", "txt", "Alice", "Source")
        with pytest.raises(ValueError, match="Unknown project"):
            store.list_documents("unknown")
        assert store.list_documents(first) == [document]


@pytest.mark.parametrize("column,value", [("content", b"tampered"), ("blocks_json", '[{"text":"tampered"}]'), ("blocks_json", "not json"), ("blocks_json", "[NaN]")])
def test_corrupt_bytes_or_blocks_reject_both_reads_and_export_before_replacement(tmp_path, column, value):
    with ReviewStore(":memory:") as store:
        project, record = scenario(store)
        document = store.attach_document(project, record, b"Software source", "txt", "Alice", "Source")
        destination = tmp_path / "export"
        original_result = store.export_project(project, destination)
        originals = {name: (destination / name).read_bytes() for name in original_result["files"]}
        with store._connection:
            store._connection.execute(f"UPDATE source_documents SET {column} = ? WHERE id = ?", (value, document["id"]))
        for getter in (store.get_document_bytes, store.get_source_blocks):
            with pytest.raises(ValueError, match="corrupt"):
                getter(project, document["id"])
        with pytest.raises(ValueError, match="corrupt"):
            store.export_project(project, destination)
        assert {name: (destination / name).read_bytes() for name in original_result["files"]} == originals


def test_conditional_document_exports_preserve_every_version_and_exact_json(tmp_path):
    with ReviewStore(":memory:") as store:
        project, record = scenario(store)
        baseline = store.export_project(project, tmp_path / "generic")
        assert len(baseline["files"]) == 9
        assert "documents" not in json.loads((tmp_path / "generic/project.json").read_text())
        first = store.attach_document(project, record, b"First\r\nsource", "txt", "@reviewer", "=reason", filename="=source.txt", version_label="+version")
        second = store.attach_document(project, record, b"Replacement source", "txt", "Alice", "New association")
        destination = tmp_path / "export"
        destination.mkdir()
        (destination / "notes.txt").write_text("Unrelated")
        result = store.export_project(project, destination)
        assert result["counts"] == baseline["counts"]
        assert len(result["files"]) == 13
        bundle = json.loads((destination / "project.json").read_text())
        assert bundle["documents"] == store.list_documents(project)
        assert [item["active"] for item in bundle["documents"]] == [False, True]
        assert json.loads((destination / "source_blocks.json").read_text()) == bundle["source_blocks"]
        for document, asset in zip([first, second], bundle["document_artifacts"]):
            assert asset == {"document_id": document["id"], "sha256": document["source_sha256"], "size_bytes": document["size_bytes"], "export_file": f"documents/{document['id']}/{document['filename']}"}
            assert (destination / asset["export_file"]).read_bytes() == store.get_document_bytes(project, document["id"])
            assert asset["export_file"] in result["files"]
        with (destination / "documents.csv").open(newline="") as file:
            row = next(csv.DictReader(file))
        assert row["reviewer"] == "'@reviewer" and row["reason"] == "'=reason"
        assert row["filename"] == "'=source.txt" and row["version_label"] == "'+version"
        assert json.loads(row["parser_metadata"]) == first["parser_metadata"]
        assert json.loads(row["source_identifiers"]) == {}
        assert bundle["documents"][0]["reason"] == "=reason"
        original = {name: (destination / name).read_bytes() for name in result["files"]}
        assert store.export_project(project, destination) == result
        assert {name: (destination / name).read_bytes() for name in result["files"]} == original
        assert (destination / "notes.txt").read_text() == "Unrelated"
