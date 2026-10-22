"""Bounded offline citation parsing; no paths, providers or formal ledger writes.

CSV support is independently implemented from the published Zotero field format,
not copied from its AGPL translator. Original projections contain bibliographic
columns only. The caller may retain original bytes in its protected import store.
"""
import csv
from hashlib import sha256
import io
import ipaddress
import re
from urllib.parse import urlsplit

from pydantic import ValidationError
from src.review.identity import normalize_pmid
from src.review.importers import load_records_bytes
from .contracts import digest
from .import_contracts import (
    CitationMetadata, ImportDiagnostic, ImportRow, ParsedImport, normalize_pmcid, normalize_citation_doi as normalize_doi,
    MAX_IMPORT_BYTES, MAX_IMPORT_COLUMNS, MAX_IMPORT_FIELD_CHARACTERS, MAX_IMPORT_ROWS,
)

_ALIASES = {
    'title': ('Title', 'Article Title', 'TI'),
    'authors': ('Author', 'Authors', 'AU'),
    'year': ('Publication Year', 'Year'),
    'date': ('Date', 'Publication Date'),
    'doi': ('DOI',), 'pmid': ('PMID', 'PubMed ID'), 'pmcid': ('PMCID', 'PMC ID'),
    'abstract': ('Abstract Note', 'Abstract', 'AB'),
    'url': ('Url', 'URL', 'Web URL'),
    'publication_title': ('Publication Title', 'Journal', 'Journal Title'),
    'source_key': ('Key', 'Source Key', 'Citation Key'),
    'item_type': ('Item Type', 'Type'), 'extra': ('Extra',),
}
_PRIVATE = re.compile(r'^(?:notes?|(?:file|link) attachments?|attachments?|file path|attachment path)$', re.I)
_TAG = re.compile(r'^([A-Z0-9]{2})[ \t]+-[ \t]?(.*)$')
_IDENTIFIERS = {'doi': normalize_doi, 'pmid': normalize_pmid, 'pmcid': normalize_pmcid}


def _diag(code, message, row=None, field=None, severity='error'):
    return ImportDiagnostic(code=code, message=message, row_number=row, field=field, severity=severity)


def _header(value):
    return ' '.join(value.strip().split()).casefold()


def _public_url(value):
    """Retain bibliographic HTTP(S) links, never a local path or private host."""
    if not value:
        return ''
    try:
        parsed = urlsplit(value.strip())
        host = (parsed.hostname or '').lower()
        if parsed.scheme not in {'http', 'https'} or not host or parsed.username or parsed.password:
            return ''
        if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')) or '.' not in host:
            return ''
        try:
            if not ipaddress.ip_address(host).is_global:
                return ''
        except ValueError:
            pass
        if parsed.port not in (None, 80, 443) or any(ord(c) < 32 for c in value):
            return ''
        return value.strip()
    except ValueError:
        return ''


def _safe_supplied(value):
    # A malformed identifier is still reviewable, but local paths are not part
    # of the normal bibliographic projection. Raw bytes stay with the caller.
    stripped = value.strip()
    return not (stripped.startswith(('/', '~', '\\', 'file:')) or re.match(r'^[A-Za-z]:[\\/]', stripped))


def _row(parsed, number, line, values, original, identifiers=None, diagnostics=None):
    diagnostics = list(diagnostics or [])
    supplied = {key: list(value) for key, value in (identifiers or {}).items()}
    for name in _IDENTIFIERS:
        if values.get(name):
            supplied.setdefault(name, []).append(values[name])
    # Only explicit labels in Extra are considered. Other free text is omitted.
    for label, value in re.findall(r'^\s*(DOI|PMID|PMCID)\s*:\s*(\S.*?)\s*$', values.get('extra', ''), re.I | re.M):
        supplied.setdefault(label.casefold(), []).append(value)
    link = values.get('url', '')
    safe_link = _public_url(link)
    if link and not safe_link:
        diagnostics.append(_diag('url_omitted', 'A local, private or unsupported URL was omitted.', number, 'url', 'warning'))
    if safe_link:
        host = (urlsplit(safe_link).hostname or '').casefold()
        if host in {'doi.org', 'dx.doi.org', 'www.doi.org'}:
            supplied.setdefault('doi', []).append(safe_link)
        if host in {'pubmed.ncbi.nlm.nih.gov', 'www.pubmed.ncbi.nlm.nih.gov', 'www.ncbi.nlm.nih.gov', 'ncbi.nlm.nih.gov'}:
            # normalize_pmid rejects non-PubMed paths and query/fragment links.
            try:
                if normalize_pmid(safe_link):
                    supplied.setdefault('pmid', []).append(safe_link)
            except ValueError:
                pass
        if host in {'pmc.ncbi.nlm.nih.gov', 'www.ncbi.nlm.nih.gov', 'ncbi.nlm.nih.gov'}:
            try:
                if normalize_pmcid(safe_link):
                    supplied.setdefault('pmcid', []).append(safe_link)
            except ValueError:
                pass
    normalized = {}
    for name, normalize in _IDENTIFIERS.items():
        distinct = set()
        for value in supplied.get(name, []):
            if len(value) > (4096 if name == 'doi' else 50):
                diagnostics.append(_diag('identifier_limit', 'An identifier exceeds the permitted length.', number, name))
                continue
            try:
                found = normalize(value)
                if found:
                    distinct.add(found)
            except ValueError:
                diagnostics.append(_diag('invalid_identifier', 'An explicitly supplied identifier is malformed.', number, name))
        if len(distinct) > 1:
            diagnostics.append(_diag('identifier_conflict', 'Different identifiers of the same type were supplied for this row.', number, name))
        elif distinct:
            normalized[name] = next(iter(distinct))
    year = None
    raw_year = values.get('year') or values.get('date') or ''
    if raw_year:
        match = re.search(r'(?<!\d)([1-9][0-9]{3})(?!\d)', str(raw_year))
        if match:
            year = int(match.group(1))
        else:
            diagnostics.append(_diag('invalid_year', 'Publication year was not recognized; it remains missing.', number, 'year', 'warning'))
    authors = values.get('authors', [])
    if isinstance(authors, str):
        authors = [author.strip() for author in authors.split(';') if author.strip()]
    metadata_input = dict(title=values.get('title', ''), authors=authors, year=year,
                          abstract=values.get('abstract', ''), url=safe_link,
                          publication_title=values.get('publication_title', ''), **normalized)
    try:
        metadata = CitationMetadata.model_validate(metadata_input)
    except ValidationError:
        metadata = CitationMetadata(**normalized)
        diagnostics.append(_diag('field_limit', 'A bibliographic field exceeds the permitted size or shape.', number))
    if not metadata.title.strip():
        diagnostics.append(_diag('title_missing', 'Title is missing; resolve an identifier or provide the title before acceptance.', number, 'title', 'warning'))
    if not metadata.abstract.strip():
        diagnostics.append(_diag('abstract_missing', 'No abstract was supplied; evidence access is not established.', number, 'abstract', 'warning'))
    conflict = any(item.code == 'identifier_conflict' for item in diagnostics)
    invalid = any(item.severity == 'error' for item in diagnostics)
    original = {key: value for key, value in original.items()
                if key != 'extra' and len(value) <= MAX_IMPORT_FIELD_CHARACTERS and (key != 'url' or bool(safe_link))
                and (key not in {'doi', 'pmid', 'pmcid', 'identifier'} or _safe_supplied(value))}
    supplied = {key: list(dict.fromkeys(value for value in entries if _safe_supplied(value)))
                for key, entries in supplied.items()}
    key = values.get('source_key') or None
    if key and (not _safe_supplied(key) or len(key) > 2000):
        key = None
        original.pop('source_key', None)
    return ImportRow(id='import-row:' + digest([parsed.file_sha256, parsed.format, number, line]),
                     row_number=number, line_number=line, source_key=key,
                     supplied_identifiers=supplied, original_fields=original, metadata=metadata,
                     status='conflict' if conflict else 'invalid' if invalid else 'pending' if not metadata.title.strip() else 'ready',
                     diagnostics=diagnostics)


def _duplicates(rows):
    # No occurrence is dropped. Compatible exact IDs get a visible linkage;
    # contradictory shared IDs remain separate and require review.
    indexed = {name: {} for name in _IDENTIFIERS}
    result = []
    for row in rows:
        prior = {}
        for name in indexed:
            identifier = getattr(row.metadata, name)
            if identifier:
                prior.update(indexed[name].get(identifier, {}))
        diagnostics = list(row.diagnostics)
        duplicate = None
        for old in prior.values():
            if any(getattr(old.metadata, name) and getattr(row.metadata, name)
                   and getattr(old.metadata, name) != getattr(row.metadata, name) for name in indexed):
                diagnostics.append(_diag('cross_row_identity_conflict', 'A shared identifier occurs with contradictory identifiers in another row.', row.row_number))
            elif duplicate is None:
                duplicate = old.id
        row = row.model_copy(update={'duplicate_of': duplicate, 'diagnostics': diagnostics,
                                    'status': 'conflict' if any(d.code == 'cross_row_identity_conflict' for d in diagnostics) else row.status})
        result.append(row)
        for name in indexed:
            identifier = getattr(row.metadata, name)
            if identifier:
                indexed[name].setdefault(identifier, {})[row.id] = row
    return result


def _csv_rows(parsed, text, mapping):
    reader = csv.reader(io.StringIO(text, newline=''), strict=True)
    rows, headers, used, ignored, diagnostics, blanks = [], [], {}, [], [], 0
    try:
        while not headers:
            headers = next(reader)
            if not headers:
                blanks += 1
        normalized_headers = [_header(value) for value in headers]
        if len(headers) > MAX_IMPORT_COLUMNS or any(len(value) > 256 for value in headers):
            raise ValueError('headers')
        if len(set(normalized_headers)) != len(headers):
            return [], headers, {}, [], [_diag('duplicate_headers', 'CSV headers are duplicated after whitespace/case normalization.')], blanks
        if mapping is None:
            for field, aliases in _ALIASES.items():
                matches = [header for header in headers if _header(header) in {_header(a) for a in aliases}]
                if len(matches) > 1:
                    diagnostics.append(_diag('ambiguous_mapping', 'Multiple CSV columns match one bibliographic field; provide an explicit mapping.', field=field))
                elif matches:
                    used[field] = matches[0]
        elif not isinstance(mapping, dict) or any(key not in _ALIASES or not isinstance(value, str) for key, value in mapping.items()):
            return [], headers, {}, [], [_diag('invalid_mapping', 'CSV mapping must use supported bibliographic field names and exact headers.')], blanks
        else:
            used = {key: value for key, value in mapping.items() if value}
        if any(value not in headers or _PRIVATE.fullmatch(_header(value))
               or (_header(value) == 'extra' and key != 'extra')
               or (_header(value) in {'key', 'source key', 'citation key'} and key != 'source_key')
               for key, value in used.items()) or len(set(used.values())) != len(used):
            return [], headers, {}, [], [_diag('invalid_mapping', 'Mapping references a missing, private, reused or incompatible provenance column.')], blanks
        if diagnostics:
            return [], headers, used, [], diagnostics, blanks
        ignored = [header for header in headers if header not in used.values()]
        while True:
            line = reader.line_num + 1
            try:
                cells = next(reader)
            except StopIteration:
                break
            if not cells or all(not cell.strip() for cell in cells):
                blanks += 1
                continue
            number = len(rows) + 1
            if number > MAX_IMPORT_ROWS:
                diagnostics.append(_diag('too_many_rows', 'Import exceeds 500 citation rows; split the file before importing.', number))
                break
            errors = []
            if len(cells) != len(headers):
                errors.append(_diag('column_count', 'CSV row width does not match the header; repair this row.', number))
            if any(len(cell) > MAX_IMPORT_FIELD_CHARACTERS for cell in cells):
                errors.append(_diag('field_limit', 'A CSV field exceeds 64 KiB characters; repair or remove that field.', number))
            values = {field: cells[headers.index(header)] for field, header in used.items() if headers.index(header) < len(cells)}
            if any(len(str(value)) > MAX_IMPORT_FIELD_CHARACTERS for value in values.values()):
                values = {field: value for field, value in values.items() if len(value) <= MAX_IMPORT_FIELD_CHARACTERS}
            rows.append(_row(parsed, number, line, values, dict(values), diagnostics=errors))
    except StopIteration:
        diagnostics.append(_diag('empty_import', 'CSV contains no header or citation rows.'))
    except (csv.Error, ValueError):
        diagnostics.append(_diag('csv_repair_required', 'CSV structure or field size is invalid; repair the file before importing.', len(rows) + 1))
    return rows, headers, used, ignored, diagnostics, blanks


def _ris_rows(parsed, text):
    # Segment only by strict TY/ER boundaries; the established pure parser owns
    # the record interpretation. Missing-title records use its parsed safe tags
    # after the same structural check, without inserting a made-up title.
    chunks, current, start, blanks = [], None, 0, 0
    try:
        for line_number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                blanks += 1
                if current is not None:
                    current.append(line)
                continue
            match = _TAG.fullmatch(line)
            if match and match[1] == 'TY':
                if current is not None or not match[2].strip():
                    raise ValueError()
                current, start = [line], line_number
                continue
            if current is None:
                raise ValueError()
            current.append(line)
            if match and match[1] == 'ER':
                if match[2].strip():
                    raise ValueError()
                chunks.append((start, '\n'.join(current)))
                current = None
                if len(chunks) > MAX_IMPORT_ROWS:
                    return [], [_diag('too_many_rows', 'Import exceeds 500 citation records; split the file before importing.', MAX_IMPORT_ROWS + 1)], blanks
        if current is not None:
            raise ValueError()
        rows = []
        for number, (line, chunk) in enumerate(chunks, 1):
            fields, active = {}, None
            for entry in chunk.splitlines():
                if not entry.strip():
                    continue
                match = _TAG.fullmatch(entry)
                if match:
                    active = match[1]
                    fields.setdefault(active, []).append(match[2])
                elif active and not re.match(r'^[A-Z0-9]{2}\s*[-:]', entry):
                    fields[active][-1] += '\n' + entry.strip()
                else:
                    raise ValueError()
            try:
                records = load_records_bytes(chunk.encode('utf-8'), 'ris', source_name='<citation-import>')
                record = records[0]
                values = dict(title=record.title, authors=record.authors, year=str(record.year or ''),
                              abstract=record.abstract, url=record.url, source_key=record.source_id)
            except ValueError as error:
                if not str(error).endswith('title must be a nonempty string'):
                    raise
                values = dict(title='', authors=fields.get('AU', []) + fields.get('A1', []),
                              year=(fields.get('PY') or fields.get('Y1') or [''])[0],
                              abstract='\n'.join(fields.get('AB', []) + fields.get('N2', [])),
                              url=(fields.get('UR') or [''])[0], source_key=(fields.get('AN') or fields.get('ID') or [''])[0])
            ids = {'doi': fields.get('DO', []) + fields.get('DI', []), 'pmid': fields.get('PM', [])}
            # AN only becomes PMID when explicitly labeled or DB/DP says PubMed.
            pubmed = any(re.fullmatch(r'(?:NCBI\s+)?PubMed(?:\s*\(NCBI\))?', value.strip(), re.I)
                         for tag in ('DB', 'DP') for value in fields.get(tag, []))
            for value in fields.get('AN', []):
                if pubmed or re.match(r'^\s*PMID\s*:', value, re.I):
                    ids['pmid'].append(value)
            values['publication_title'] = (fields.get('JF') or fields.get('JO') or fields.get('T2') or [''])[0]
            original = {key: '; '.join(value) if isinstance(value, list) else value for key, value in values.items()}
            rows.append(_row(parsed, number, line, values, original, identifiers=ids))
        return rows, [], blanks
    except (ValueError, IndexError):
        return [], [_diag('ris_repair_required', 'RIS structure or a citation field is invalid; repair the file before importing.')], blanks


def _identifier_rows(parsed, text):
    rows, blanks, diagnostics = [], 0, []
    for line, raw in enumerate(text.splitlines(), 1):
        value = raw.strip()
        if not value:
            blanks += 1
            continue
        number = len(rows) + 1
        if number > MAX_IMPORT_ROWS:
            diagnostics.append(_diag('too_many_rows', 'Import exceeds 500 identifier rows; split the list before importing.', number))
            break
        values, errors = {}, []
        if len(value) > 4096:
            errors.append(_diag('identifier_limit', 'An identifier exceeds the permitted length.', number))
        elif re.match(r'^PMID\s*:', value, re.I) or re.match(r'^https?://(?:www\.)?(?:pubmed\.ncbi\.nlm\.nih\.gov|ncbi\.nlm\.nih\.gov/pubmed)/', value, re.I):
            values['pmid'] = value
        elif re.match(r'^PMCID\s*:|^PMC[1-9][0-9]*$|^https?://(?:pmc\.ncbi\.nlm\.nih\.gov/articles/|(?:www\.)?ncbi\.nlm\.nih\.gov/pmc/articles/)', value, re.I):
            values['pmcid'] = value
        else:
            try:
                normalize_doi(value)
                values['doi'] = value
            except ValueError:
                errors.append(_diag('explicit_identifier_required', 'Use a DOI, DOI URL, explicit PMID label/PubMed URL, or PMC identifier. Bare numbers are not inferred as PMID.', number))
        rows.append(_row(parsed, number, line, values, {'identifier': value} if len(value) <= 4096 else {}, diagnostics=errors))
    return rows, diagnostics, blanks


def parse_import_bytes(payload: bytes, format: str, filename: str | None = None, mapping: dict | None = None) -> ParsedImport:
    """Parse at most 5 MiB/500 occurrences, retaining every safe row or a repair diagnostic.

    A supplied CSV mapping is complete (omitted keys disable autodetection).
    Errors never include source text, filenames with directories, or raw paths.
    CSV fields are capped at 64 KiB, within stdlib's normal field-size policy;
    parsing never changes its process-global limit.
    """
    if not isinstance(payload, bytes) or format not in {'csv', 'ris', 'identifiers'}:
        raise ValueError('Citation imports require bytes and an explicit csv, ris or identifiers format')
    safe_name = re.split(r'[/\\]', filename)[-1][:200] if isinstance(filename, str) else None
    if safe_name:
        safe_name = ''.join(c for c in safe_name if ord(c) >= 32)
    parsed = ParsedImport(format=format, filename=safe_name, file_sha256=sha256(payload).hexdigest(), byte_count=len(payload))
    if len(payload) > MAX_IMPORT_BYTES:
        return parsed.model_copy(update={'diagnostics': [_diag('file_too_large', 'Citation imports are limited to 5 MiB.')]})
    try:
        text = payload.decode('utf-8-sig')
    except UnicodeError:
        return parsed.model_copy(update={'diagnostics': [_diag('invalid_utf8', 'Citation imports must be UTF-8 text.')]})
    if '\x00' in text:
        return parsed.model_copy(update={'diagnostics': [_diag('invalid_text', 'Citation text contains unsupported null characters.')]})
    if mapping is not None and format != 'csv':
        return parsed.model_copy(update={'diagnostics': [_diag('invalid_mapping', 'Column mapping applies only to CSV imports.')]})
    if format == 'csv':
        rows, headers, used, ignored, diagnostics, blanks = _csv_rows(parsed, text, mapping)
        parsed = parsed.model_copy(update={'headers': headers, 'mapping': used, 'ignored_columns': ignored})
    elif format == 'ris':
        rows, diagnostics, blanks = _ris_rows(parsed, text)
    else:
        rows, diagnostics, blanks = _identifier_rows(parsed, text)
    if not rows and not diagnostics:
        diagnostics = [_diag('empty_import', 'No citation occurrences were found.')]
    return parsed.model_copy(update={'rows': _duplicates(rows), 'diagnostics': diagnostics, 'blank_line_count': blanks})
