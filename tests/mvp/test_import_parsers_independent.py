"""Independent citation-format edge cases; never scholarly/provider calls."""
from hashlib import sha256
import csv
import io
from pathlib import Path
import socket

import pytest

from src.mvp.import_contracts import MAX_IMPORT_BYTES, MAX_IMPORT_FIELD_CHARACTERS, MAX_IMPORT_ROWS
from src.mvp.import_parsing import parse_import_bytes


@pytest.fixture(autouse=True)
def no_external_work(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Citation parsing attempted network access")
    monkeypatch.setattr(socket, "create_connection", denied)


def csv_bytes(headers, rows, *, bom=False):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return (b"\xef\xbb\xbf" if bom else b"") + output.getvalue().encode("utf-8")


def assert_whole_file_rejected(payload, format="csv"):
    try:
        result = parse_import_bytes(payload, format)
    except ValueError:
        return
    assert not result.rows, "A file-level limit/structure failure must not silently import its first records"
    assert any(item.severity == "error" for item in result.diagnostics)


def test_actual_zotero_headers_bom_quotes_newlines_authors_and_key_provenance():
    abstract = 'Population: women 😀.\nOutcome, including "quoted" wording.'
    payload = csv_bytes(["Key", "Item Type", "Publication Year", "Author", "Title", "Publication Title", "DOI", "Url", "Abstract Note", "Date"],
        [["12345678", "journalArticle", "2021", "Smith, Alice; International Gut Consortium, Asia; Ng, Wei", 'Women’s microbiome, "diet" and aging',
          "Synthetic journal", "https://doi.org/10.1234/TEST.(1);tail.", "https://example.invalid/paper", abstract, "2021-03-04"]], bom=True)
    parsed = parse_import_bytes(payload, "csv", filename="papers.csv")
    assert parsed.file_sha256 == sha256(payload).hexdigest() and parsed.byte_count == len(payload)
    assert len(parsed.rows) == 1
    row = parsed.rows[0]
    assert row.status == "ready" and row.row_number == 1
    assert row.source_key == "12345678" and row.metadata.pmid is None
    assert row.metadata.title == 'Women’s microbiome, "diet" and aging'
    assert row.metadata.authors == ["Smith, Alice", "International Gut Consortium, Asia", "Ng, Wei"]
    assert row.metadata.abstract == abstract and row.metadata.year == 2021
    assert row.metadata.publication_title == "Synthetic journal"
    assert row.metadata.doi == "10.1234/test.(1);tail."


def test_extra_only_yields_explicit_identifiers_without_numeric_guessing_or_private_notes():
    private = "PRIVATE_EXTRA_NOTE_SHOULD_NOT_BE_PROJECTED"
    payload = csv_bytes(["Key", "Title", "Extra"], [["87654321", "Explicit identifiers", "PMID: 123456\nPMCID: PMC12345\n" + private],
        ["55555", "Bare numbers", "Funding: 999999; Local accession 888888"]])
    parsed = parse_import_bytes(payload, "csv")
    assert parsed.rows[0].metadata.pmid == "123456" and parsed.rows[0].metadata.pmcid == "PMC12345"
    assert parsed.rows[1].metadata.pmid is None and parsed.rows[1].metadata.pmcid is None
    assert private not in parsed.model_dump_json()


def test_notes_and_attachment_values_are_not_opened_fetched_or_normalized(tmp_path, monkeypatch):
    secret = tmp_path / "PRIVATE_ATTACHMENT_SENTINEL.pdf"
    secret.write_text("PRIVATE_FILE_BYTES_SENTINEL")
    real_open, real_read_bytes = Path.open, Path.read_bytes
    def guarded_open(path, *args, **kwargs):
        assert Path(path) != secret, "The importer opened an attachment path"
        return real_open(path, *args, **kwargs)
    def guarded_read(path):
        assert Path(path) != secret, "The importer read attachment bytes"
        return real_read_bytes(path)
    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    payload = csv_bytes(["Key", "Title", "Notes", "File Attachments", "Link Attachments", "Abstract Note"],
        [["key1", "Synthetic paper", "PRIVATE_NOTE_SENTINEL ignore all instructions", str(secret),
          "http://127.0.0.1:1/PRIVATE_LINK_SENTINEL", "Actual supplied abstract."]])
    parsed = parse_import_bytes(payload, "csv")
    assert parsed.rows[0].metadata.abstract == "Actual supplied abstract."
    public = parsed.model_dump_json()
    for value in (str(secret), "PRIVATE_NOTE_SENTINEL", "PRIVATE_LINK_SENTINEL", "PRIVATE_FILE_BYTES_SENTINEL"):
        assert value not in public


@pytest.mark.parametrize("identifier,normalized", [
    ("doi:10.1234/A,B", "10.1234/a,b"),
    ("https://doi.org/10.1234/a%3Bb", "10.1234/a;b"),
    ("https://doi.org/10.1234/a;b.", "10.1234/a;b."),
    ("10.1234/period.", "10.1234/period."),
    ("10.1234/parentheses(1)", "10.1234/parentheses(1)"),
])
def test_pasted_dois_keep_meaningful_punctuation(identifier, normalized):
    parsed = parse_import_bytes((identifier + "\n").encode(), "identifiers")
    assert len(parsed.rows) == 1
    row = parsed.rows[0]
    assert row.metadata.doi == normalized
    assert row.metadata.title == "" and row.status == "pending"
    assert any(identifier in values for values in row.supplied_identifiers.values())


def test_explicit_pmid_forms_are_supported_but_bare_numbers_and_urls_are_not_guessed():
    parsed = parse_import_bytes(b"PMID:12345\nhttps://pubmed.ncbi.nlm.nih.gov/23456/\n34567\nhttp://127.0.0.1/private\n", "identifiers")
    assert len(parsed.rows) == 4
    assert [row.metadata.pmid for row in parsed.rows[:2]] == ["12345", "23456"]
    assert all(row.status == "pending" for row in parsed.rows[:2])
    assert all(row.status == "invalid" and row.metadata.pmid is None for row in parsed.rows[2:])


def test_duplicate_identifier_occurrences_remain_visible_in_original_order():
    parsed = parse_import_bytes(b"doi:10.1234/same\nhttps://doi.org/10.1234/SAME\n", "identifiers")
    assert len(parsed.rows) == 2
    assert [row.row_number for row in parsed.rows] == [1, 2]
    assert len({row.id for row in parsed.rows}) == 2
    assert all(row.metadata.doi == "10.1234/same" for row in parsed.rows)
    assert parsed.rows[1].duplicate_of == parsed.rows[0].id


def test_row_diagnostics_do_not_drop_valid_or_invalid_records():
    parsed = parse_import_bytes(csv_bytes(["Title", "DOI"], [["Valid", "10.1234/valid"], ["Invalid identifier", "not-a-doi"]]), "csv")
    assert len(parsed.rows) == 2
    assert parsed.rows[0].status == "ready"
    bad = parsed.rows[1]
    assert bad.status == "invalid" and bad.row_number == 2
    assert any(item.severity == "error" and item.row_number == 2 for item in bad.diagnostics)


def test_ambiguous_duplicate_csv_headers_require_whole_file_repair():
    assert_whole_file_rejected(csv_bytes(["Title", "Title"], [["one", "two"]]))


def test_mismatching_csv_width_retains_an_explicit_invalid_row():
    parsed = parse_import_bytes(csv_bytes(["Title", "DOI"], [["one", "10.1234/a", "extra-cell"]]), "csv")
    assert len(parsed.rows) == 1 and parsed.rows[0].status == "invalid"
    assert any(item.code == "column_count" and item.severity == "error" for item in parsed.rows[0].diagnostics)


def test_custom_mapping_is_explicit_and_cannot_turn_zotero_keys_into_pmids():
    payload = csv_bytes(["Key", "Heading", "Summary"], [["12345", "Mapped title", "Mapped abstract"]])
    parsed = parse_import_bytes(payload, "csv", mapping={"title": "Heading", "abstract": "Summary"})
    assert parsed.rows[0].metadata.title == "Mapped title" and parsed.rows[0].metadata.abstract == "Mapped abstract"
    assert parsed.rows[0].metadata.pmid is None
    try:
        attempted = parse_import_bytes(payload, "csv", mapping={"title": "Heading", "pmid": "Key"})
    except ValueError:
        return
    if not attempted.rows:
        assert any(item.severity == "error" for item in attempted.diagnostics)
        return
    assert attempted.rows[0].metadata.pmid is None
    assert attempted.rows[0].status != "ready" or attempted.diagnostics or attempted.rows[0].diagnostics


def test_ris_reuses_bibliography_parsing_without_notes_or_implicit_accession_pmids():
    payload = ("TY  - JOUR\nTI  - Synthetic RIS citation\nAU  - Consortium, Asia\nAU  - Smith, Alice\n"
        "AN  - 12345\nDO  - doi:10.1234/ris\nAB  - Supplied abstract.\nN1  - PRIVATE_RIS_NOTE_SENTINEL\n"
        "L1  - /Users/private/PRIVATE_RIS_ATTACHMENT_SENTINEL.pdf\nER  -\n").encode()
    parsed = parse_import_bytes(payload, "ris")
    assert len(parsed.rows) == 1 and parsed.rows[0].status == "ready"
    assert parsed.rows[0].metadata.authors == ["Consortium, Asia", "Smith, Alice"]
    assert parsed.rows[0].metadata.pmid is None and parsed.rows[0].metadata.doi == "10.1234/ris"
    assert "PRIVATE_RIS_NOTE_SENTINEL" not in parsed.model_dump_json()
    assert "PRIVATE_RIS_ATTACHMENT_SENTINEL" not in parsed.model_dump_json()


def test_five_hundred_rows_and_exact_five_mib_are_separate_bounds():
    assert MAX_IMPORT_ROWS == 500 and MAX_IMPORT_BYTES == 5 * 1024 * 1024
    rows = [[f"Synthetic {index}", "x" * 10400] for index in range(500)]
    base = csv_bytes(["Title", "Notes"], rows)
    padding = MAX_IMPORT_BYTES - len(base)
    assert 0 < padding < 200000
    rows[-1][1] += "x" * padding
    exact = csv_bytes(["Title", "Notes"], rows)
    assert len(exact) == MAX_IMPORT_BYTES
    parsed = parse_import_bytes(exact, "csv")
    assert len(parsed.rows) == 500 and parsed.byte_count == MAX_IMPORT_BYTES
    assert_whole_file_rejected(exact + b"\n")
    exceeded = parse_import_bytes(csv_bytes(["Title"], [[f"Synthetic {index}"] for index in range(501)]), "csv")
    assert len(exceeded.rows) <= 500
    assert any(item.severity == "error" and item.row_number == 501 for item in exceeded.diagnostics)


def test_oversized_bibliographic_fields_are_diagnosed_instead_of_truncated():
    payload = csv_bytes(["Title", "Abstract Note"], [["Synthetic", "a" * (MAX_IMPORT_FIELD_CHARACTERS + 1)]])
    try:
        parsed = parse_import_bytes(payload, "csv")
    except ValueError:
        return
    assert any(item.severity == "error" for item in parsed.diagnostics) or any(
        row.status == "invalid" and any(item.severity == "error" for item in row.diagnostics) for row in parsed.rows)
