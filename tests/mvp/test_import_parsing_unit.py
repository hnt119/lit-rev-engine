from src.mvp.import_parsing import parse_import_bytes


def test_ris_reuses_pure_parser_and_retains_identifier_only_pending_record():
    content = b'TY  - JOUR\nTI  - Report title\nAU  - Lee, H.\nDO  - 10.1234/a\nN1  - private note\nL1  - /private/source.pdf\nER  -\n\nTY  - JOUR\nDO  - 10.1234/b\nER  -\n'
    parsed = parse_import_bytes(content, 'ris', '/private/export.ris')
    assert parsed.filename == 'export.ris' and not parsed.diagnostics
    assert [row.status for row in parsed.rows] == ['ready', 'pending']
    assert parsed.rows[0].metadata.authors == ['Lee, H.']
    assert parsed.rows[1].metadata.title == '' and parsed.rows[1].metadata.doi == '10.1234/b'
    assert 'private note' not in parsed.model_dump_json() and '/private/' not in parsed.model_dump_json()


def test_mapping_is_complete_and_extra_only_extracts_explicit_ids():
    content = b'Title,Extra,Notes,URL\nTitle,"PMID: 123\nprivate extra",private note,file:///private/a.pdf\n'
    parsed = parse_import_bytes(content, 'csv')
    row = parsed.rows[0]
    assert row.metadata.pmid == '123'
    assert row.metadata.url == '' and 'url' not in row.original_fields
    assert all(value not in parsed.model_dump_json() for value in ('private extra', 'private note', '/private/a.pdf'))
    disabled = parse_import_bytes(content, 'csv', mapping={'title': 'Title'})
    assert disabled.rows[0].metadata.pmid is None


def test_long_identifier_is_diagnosed_without_unhandled_model_error():
    parsed = parse_import_bytes(('Title,DOI\nTitle,10.1234/' + 'x' * 5000).encode(), 'csv')
    assert parsed.rows[0].status == 'invalid'
    assert any(d.code == 'identifier_limit' for d in parsed.rows[0].diagnostics)


def test_explicit_pmc_identifier_urls_are_normalized_without_fetching():
    parsed = parse_import_bytes(b'https://pmc.ncbi.nlm.nih.gov/articles/PMC123/\nPMCID: PMC456\n', 'identifiers')
    assert [row.metadata.pmcid for row in parsed.rows] == ['PMC123', 'PMC456']
    assert all(row.status == 'pending' for row in parsed.rows)
