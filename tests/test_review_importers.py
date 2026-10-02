"""Focused format/provenance tests for the offline bibliography adapters."""

import json
from pathlib import Path
import socket
import urllib.request

import pytest

from src.review.importers import load_records, load_records_bytes


def _write(tmp_path, filename, text):
    path = tmp_path / filename
    path.write_text(text, encoding="utf-8")
    return path


def test_canonical_json_retains_arbitrary_original_fields(tmp_path):
    original = {
        "title": "Intervention in asthma",
        "authors": ["García, María", "Trial Consortium"],
        "year": 2024,
        "doi": "https://doi.org/10.1234/ASTHMA",
        "pmid": "PMID: 34567890",
        "abstract": "Medical evidence.",
        "url": "https://example.org/paper",
        "source_id": "database-item-1",
        "mesh": ["Asthma"],
        "raw": {"database": "PubMed"},
    }
    record = load_records(_write(tmp_path, "export.json", json.dumps([original])))[0]
    assert record.title == original["title"]
    assert record.authors == original["authors"]
    assert record.doi == original["doi"]
    assert record.pmid == original["pmid"]
    assert record.raw == original


@pytest.mark.parametrize("row, field", [
    ({"title": ""}, "title"),
    ({"title": "Valid", "authors": "Smith"}, "authors"),
    ({"title": "Valid", "authors": [""]}, "authors"),
    ({"title": "Valid", "year": True}, "year"),
    ({"title": "Valid", "year": "2020"}, "year"),
    ({"title": "Valid", "year": 10000}, "year"),
    ({"title": "Valid", "abstract": None}, "abstract"),
    ({"title": "Valid", "url": []}, "url"),
    ({"title": "Valid", "source_id": 9}, "source_id"),
    ({"title": "Valid", "doi": "not-a-doi"}, "doi"),
    ({"title": "Valid", "pmid": "PMC1234"}, "pmid"),
    ({"title": "Valid", "pmid": 1234}, "pmid"),
])
def test_invalid_json_record_has_context(tmp_path, row, field):
    path = _write(tmp_path, "bad.json", json.dumps([{"title": "First"}, row]))
    with pytest.raises(ValueError, match=rf"bad.json: JSON record 2.*{field}"):
        load_records(path)


@pytest.mark.parametrize("text, pattern", [
    ('{"title": "No array"}', "expected an array"),
    ('["not an object"]', "record 1.*expected a bibliographic object"),
    ('[{"title": "A", "doi": "10.1234/a", "doi": "10.1234/b"}]', "record 1.*duplicate JSON field"),
    ('[{"title": "A", "metadata": {"x": 1, "x": 2}}]', "record 1.metadata.*duplicate JSON field"),
    ('[{"title": "A", "metadata": NaN}]', "record 1.metadata.*non-finite"),
    ('[{"title": "A", "metadata": 1e9999}]', "record 1.metadata.*non-finite"),
    ('[\n{"title": "A"},\n]', "JSON line 3"),
])
def test_invalid_json_document_fails_instead_of_losing_fields(tmp_path, text, pattern):
    with pytest.raises(ValueError, match=pattern):
        load_records(_write(tmp_path, "bad.json", text))


def test_ris_repeated_fields_aliases_continuations_and_raw(tmp_path):
    text = (
        "TY  - JOUR\nT1  - Asthma trial\nAU  - Smith, Jane\nA1  - Trial Consortium\n"
        "Y1  - 2024/03/21\nDO  - doi:10.1234/ASTHMA\n"
        "AB  - First paragraph.\n    Continued paragraph.\nN2  - Second paragraph.\n"
        "DB  - PubMed\nAN  - PMID:34567890\nUR  - https://example.org/paper\n"
        "KW  - asthma\nKW  - randomized trial\nER  - \n"
    )
    record = load_records(_write(tmp_path, "export.ris", text))[0]
    assert record.title == "Asthma trial"
    assert record.authors == ["Smith, Jane", "Trial Consortium"]
    assert record.year == 2024
    assert record.doi == "doi:10.1234/ASTHMA"
    assert record.pmid == "34567890"
    assert record.source_id == "PMID:34567890"
    assert record.abstract == "First paragraph.\nContinued paragraph.\nSecond paragraph."
    assert record.raw["fields"]["KW"] == ["asthma", "randomized trial"]
    assert record.raw["text"] == text.rstrip("\n")


@pytest.mark.parametrize("database", ["", "Scopus", "MEDLINE", "PubMed Central"])
def test_numeric_ris_accession_is_not_assumed_to_be_pmid(tmp_path, database):
    text = f"TY  - JOUR\nTI  - Trial\nDB  - {database}\nAN  - 12345\nER  - \n"
    record = load_records(_write(tmp_path, "export.ris", text))[0]
    assert record.pmid is None
    assert record.source_id == "12345"


@pytest.mark.parametrize("text, pattern", [
    ("TI  - Title\nER  - \n", "line 1.*outside"),
    ("TY  - JOUR\nTI  - Title\n", "record 1.*missing ER"),
    ("TY  - JOUR\nTI  - Title\nTY  - JOUR\n", "line 3.*missing ER"),
    ("TY  - JOUR\nDO  - 10.1234/a\nER  - \n", "record 1.*title"),
    ("TY  - JOUR\nTI  - Title\nDO  - 10.1234/a\nDO  - 10.1234/b\nER  - \n", "conflicting doi"),
    ("TY  - JOUR\nTI  - Title\nDB  - PubMed\nAN  - PMC123\nER  - \n", "pmid"),
    ("TY  - JOUR\nTI  - Title\nPY  - unknown\nER  - \n", "publication year"),
    ("TY  - JOUR\nTI: Title\nER  - \n", "line 2.*malformed tag"),
])
def test_malformed_ris_fails_contextually(tmp_path, text, pattern):
    with pytest.raises(ValueError, match=pattern):
        load_records(_write(tmp_path, "bad.ris", text))


def _article_xml(pmid="34567890", doi="10.1234/ASTHMA"):
    return f"""<PubmedArticle>
      <MedlineCitation Status="MEDLINE"><PMID Version="1">{pmid}</PMID><Article>
        <Journal><JournalIssue><PubDate><MedlineDate>2024 Jan-Feb</MedlineDate></PubDate></JournalIssue></Journal>
        <ArticleTitle>Asthma <i>treatment</i> and IL-<sup>6</sup>.</ArticleTitle>
        <Abstract><AbstractText Label="METHODS">Randomized <b>trial</b>.</AbstractText>
          <AbstractText Label="RESULTS">Benefit in 40 patients.</AbstractText></Abstract>
        <AuthorList><Author><LastName>Smith</LastName><ForeName>Jane</ForeName></Author>
          <Author><CollectiveName>Trial Consortium</CollectiveName></Author></AuthorList>
        <ELocationID EIdType="doi">{doi}</ELocationID>
      </Article><MeshHeadingList><MeshHeading><DescriptorName UI="D001249">Asthma</DescriptorName></MeshHeading></MeshHeadingList></MedlineCitation>
      <PubmedData><ArticleIdList><ArticleId IdType="pubmed">{pmid}</ArticleId>
        <ArticleId IdType="doi">{doi.lower()}</ArticleId></ArticleIdList>
        <ReferenceList><Reference><ArticleIdList><ArticleId IdType="doi">10.9876/reference</ArticleId></ArticleIdList></Reference></ReferenceList>
      </PubmedData></PubmedArticle>"""


def test_pubmed_xml_mixed_text_authors_medline_date_and_raw(tmp_path):
    record = load_records(_write(tmp_path, "export.xml", f"<PubmedArticleSet>{_article_xml()}</PubmedArticleSet>"))[0]
    assert record.title == "Asthma treatment and IL-6."
    assert record.authors == ["Smith, Jane", "Trial Consortium"]
    assert record.year == 2024
    assert record.pmid == "34567890"
    assert record.doi == "10.1234/asthma"
    assert record.url == "https://pubmed.ncbi.nlm.nih.gov/34567890/"
    assert record.abstract == "METHODS: Randomized trial.\nRESULTS: Benefit in 40 patients."
    assert 'DescriptorName UI="D001249"' in record.raw["xml"]
    assert "10.9876/reference" in record.raw["xml"]
    assert record.raw["tree"]["tag"] == "PubmedArticle"


def test_book_xml_not_silently_dropped(tmp_path):
    xml = """<PubmedArticleSet><PubmedBookArticle><BookDocument>
      <PMID>34567891</PMID><ArticleTitle>Clinical guidance</ArticleTitle>
      <Book><BookTitle>Guidelines</BookTitle><PubDate><Year>2020</Year></PubDate></Book>
      <AuthorList><Author><CollectiveName>Guideline Committee</CollectiveName></Author></AuthorList>
      <ArticleIdList><ArticleId IdType="bookaccession">NBK1234</ArticleId></ArticleIdList>
    </BookDocument></PubmedBookArticle></PubmedArticleSet>"""
    record = load_records(_write(tmp_path, "book.xml", xml))[0]
    assert record.title == "Clinical guidance"
    assert record.year == 2020
    assert record.authors == ["Guideline Committee"]
    assert "NBK1234" in record.raw["xml"]


@pytest.mark.parametrize("xml, pattern", [
    ("<PubmedArticleSet>", "XML line 1"),
    ("<unrelated />", "unsupported root"),
    ("<PubmedArticleSet><ERROR>Failed</ERROR></PubmedArticleSet>", "record 1.*unsupported element"),
    ("<PubmedArticleSet><PubmedArticle /></PubmedArticleSet>", "record 1.*missing MedlineCitation"),
    (_article_xml(pmid="PMC123"), "record 1.*pmid"),
    (_article_xml(doi="invalid"), "record 1.*doi"),
    (_article_xml().replace("10.1234/asthma", "10.5678/conflict"), "conflicting doi"),
    (_article_xml().replace("2024 Jan-Feb", "unknown date"), "publication year"),
])
def test_invalid_pubmed_xml_fails_with_context(tmp_path, xml, pattern):
    with pytest.raises(ValueError, match=pattern):
        load_records(_write(tmp_path, "bad.xml", xml))


def test_pubmed_xml_never_resolves_network_or_local_entities(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("An offline importer tried to access the network")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    xml = '<!DOCTYPE PubmedArticleSet SYSTEM "https://example.org/pubmed.dtd"><PubmedArticleSet />'
    assert load_records(_write(tmp_path, "external-dtd.xml", xml)) == []
    for declaration in (
        '<!ENTITY secret SYSTEM "file:///etc/passwd">',
        '<!ENTITY remote SYSTEM "https://example.org/secret">',
        '<!ENTITY repeated "repeated text">',
    ):
        xml = f"<!DOCTYPE PubmedArticleSet [{declaration}]><PubmedArticleSet />"
        with pytest.raises(ValueError, match="ENTITY declarations"):
            load_records(_write(tmp_path, "entities.xml", xml))


@pytest.mark.parametrize("filename, text", [("empty.json", "[]"), ("empty.xml", "<PubmedArticleSet />"), ("empty.ris", "")])
def test_zero_result_exports(tmp_path, filename, text):
    assert load_records(_write(tmp_path, filename, text)) == []


def test_format_override_bom_and_unknown_formats(tmp_path):
    path = _write(tmp_path, "export.txt", '\ufeff[{"title": "A"}]')
    assert load_records(path, format="JSON")[0].title == "A"
    with pytest.raises(ValueError, match="unsupported import format"):
        load_records(path)
    with pytest.raises(ValueError, match="unsupported import format"):
        load_records(path, format="bibtex")
    with pytest.raises(ValueError, match="cannot read UTF-8"):
        load_records(tmp_path / "missing.json")


@pytest.mark.parametrize("format, text", [
    ("json", '[{"title": "García, synthetic metadata", "authors": ["Example, Áda"], "year": 2024, "original": {"tag": "value"}}]'),
    ("ris", "TY  - JOUR\r\nTI  - García synthetic metadata\r\nAU  - Example, Áda\r\nAN  - original-accession\r\nER  -\r\n"),
    ("pubmed_xml", f"<PubmedArticleSet>{_article_xml()}</PubmedArticleSet>"),
])
@pytest.mark.parametrize("bom", [False, True])
def test_bytes_and_path_imports_have_identical_records_and_raw(tmp_path, format, text, bom):
    content = (b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8")
    path = tmp_path / "original-export.txt"
    path.write_bytes(content)
    assert load_records_bytes(content, format, source_name=str(path)) == load_records(path, format=format)


@pytest.mark.parametrize("format, content", [("json", b"[]"), ("ris", b""), ("pubmed_xml", b"<PubmedArticleSet />")])
def test_bytes_zero_result_imports(format, content):
    assert load_records_bytes(content, format) == []


@pytest.mark.parametrize("alias", ["xml", "pubmed", "pubmed_xml", "pubmed-xml", "PUBMED_XML"])
def test_bytes_parser_accepts_existing_xml_aliases(alias):
    assert load_records_bytes(b"<PubmedArticleSet />", alias) == []


@pytest.mark.parametrize("content", ["[]", bytearray(b"[]"), memoryview(b"[]"), None, [], 3])
def test_bytes_parser_rejects_non_bytes_with_source_context(content):
    with pytest.raises(ValueError, match="captured-response:.*must be bytes"):
        load_records_bytes(content, "json", source_name="captured-response")


@pytest.mark.parametrize("format", [None, "", "bibtex", 3])
def test_bytes_parser_requires_explicit_supported_format(format):
    with pytest.raises(ValueError, match="<memory>: unsupported import format"):
        load_records_bytes(b"[]", format)


@pytest.mark.parametrize("format, content, context", [
    ("json", b'[{"title":"First"},{"title":""}]', "JSON record 2"),
    ("ris", b"TY  - JOUR\nTI  - A\n", "RIS record 1.*missing ER"),
    ("pubmed_xml", b"<PubmedArticleSet>", "XML line 1"),
    ("json", b"\xff[]", "cannot read UTF-8"),
])
def test_bytes_errors_match_path_errors_and_include_source(tmp_path, format, content, context):
    path = tmp_path / "captured-response.txt"
    path.write_bytes(content)
    with pytest.raises(ValueError, match=context) as memory_error:
        load_records_bytes(content, format, source_name=str(path))
    with pytest.raises(ValueError) as path_error:
        load_records(path, format=format)
    assert str(memory_error.value) == str(path_error.value)


def test_bytes_parser_does_not_open_files(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Captured-byte parsing must not reopen files")
    monkeypatch.setattr(Path, "open", forbidden)
    records = load_records_bytes(b'[{"title":"Captured record", "doi":"10.1234/record", "original":"untouched"}]', "json", source_name=str(tmp_path / "absent.json"))
    assert records[0].doi == "10.1234/record"
    assert records[0].raw["original"] == "untouched"
