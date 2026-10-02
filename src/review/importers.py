"""Offline bibliography importers with original-field provenance.

These adapters read citation exports, not live database searches. No model,
network client, or third-party parser is initialized by importing this module.
"""

import json
import math
import re
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from .identity import normalize_doi, normalize_pmid
from .models import BibliographicRecord


_FORMATS = {
    "json": "json",
    "ris": "ris",
    "xml": "xml",
    "pubmed": "xml",
    "pubmed_xml": "xml",
    "pubmed-xml": "xml",
}
_RIS_TAG = re.compile(r"^([A-Z0-9]{2})[ \t]+-[ \t]?(.*)$")


def load_records(path, format=None) -> list[BibliographicRecord]:
    """Read a UTF-8 JSON array, RIS export, or PubMed XML citation export.

    Infer the format from ``.json``, ``.ris``, or ``.xml`` unless explicitly
    supplied. Return all records in file order; fail the whole load on an
    invalid record. Every error contains the source filename and document,
    record, or line context.
    """
    source = Path(path)
    requested = source.suffix.lstrip(".") if format is None else format
    selected = _select_format(requested, source)
    try:
        content = source.read_bytes()
    except OSError as error:
        raise ValueError(f"{source}: cannot read UTF-8 citation export: {error}") from error
    return load_records_bytes(content, selected, source_name=str(source))


def load_records_bytes(content: bytes, format, source_name="<memory>") -> list[BibliographicRecord]:
    """Parse captured bytes without reopening a file or making external calls.

    An explicit supported format is required. ``source_name`` labels contextual
    errors; parsing, validation, and original-field provenance match path imports.
    """
    if not isinstance(content, bytes):
        raise ValueError(f"{source_name}: citation export content must be bytes")
    selected = _select_format(format, source_name)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeError as error:
        raise ValueError(f"{source_name}: cannot read UTF-8 citation export: {error}") from error
    try:
        if selected == "json":
            return _load_json(text)
        if selected == "ris":
            return _load_ris(text)
        return _load_xml(text)
    except ValueError as error:
        raise ValueError(f"{source_name}: {error}") from error


def _select_format(requested, source_name):
    if not isinstance(requested, str) or requested.lower() not in _FORMATS:
        raise ValueError(f"{source_name}: unsupported import format {requested!r}; use json, ris, or xml")
    return _FORMATS[requested.lower()]


class _JSONPairs(list):
    """Distinguish JSON objects from arrays without losing duplicate keys."""


class _NonFiniteJSON:
    def __init__(self, value):
        self.value = value


def _json_value(value, context):
    if isinstance(value, _JSONPairs):
        result = {}
        for key, child in value:
            if key in result:
                raise ValueError(f"{context}: duplicate JSON field {key!r}")
            result[key] = _json_value(child, f"{context}.{key}")
        return result
    if isinstance(value, list):
        return [_json_value(child, f"{context}[{index}]") for index, child in enumerate(value)]
    if isinstance(value, _NonFiniteJSON):
        raise ValueError(f"{context}: non-finite JSON value {value.value!r} is invalid")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{context}: non-finite JSON number is invalid")
    return value


def _load_json(text):
    try:
        rows = json.loads(text, object_pairs_hook=_JSONPairs, parse_constant=_NonFiniteJSON)
    except json.JSONDecodeError as error:
        raise ValueError(f"JSON line {error.lineno}, column {error.colno}: {error.msg}") from error
    if not isinstance(rows, list) or isinstance(rows, _JSONPairs):
        raise ValueError("JSON document: expected an array of bibliographic objects")
    records = []
    for index, original in enumerate(rows, 1):
        context = f"JSON record {index}"
        row = _json_value(original, context)
        if not isinstance(row, dict):
            raise ValueError(f"{context}: expected a bibliographic object")
        records.append(_record(row, row, context))
    return records


def _record(fields, raw, context):
    title = fields.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError(f"{context}: title must be a nonempty string")
    authors = fields.get("authors", [])
    if not isinstance(authors, list) or any(not isinstance(author, str) or not author.strip() for author in authors):
        raise ValueError(f"{context}: authors must be an array of nonempty strings")
    year = fields.get("year")
    if year is not None and (isinstance(year, bool) or not isinstance(year, int) or not 1 <= year <= 9999):
        raise ValueError(f"{context}: year must be an integer from 1 to 9999 or null")
    for name in ("abstract", "url", "source_id"):
        if not isinstance(fields.get(name, ""), str):
            raise ValueError(f"{context}: {name} must be a string")
    for name, normalize in (("doi", normalize_doi), ("pmid", normalize_pmid)):
        value = fields.get(name)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{context}: {name} must be a string or null")
        try:
            normalize(value)
        except ValueError as error:
            raise ValueError(f"{context}: {name}: {error}") from error
    return BibliographicRecord(
        title=title.strip(),
        authors=[author.strip() for author in authors],
        year=year,
        doi=fields.get("doi"),
        pmid=fields.get("pmid"),
        abstract=fields.get("abstract", ""),
        url=fields.get("url", ""),
        source_id=fields.get("source_id", ""),
        raw=raw,
    )


def _unique_identifier(values, name, context):
    normalize = normalize_doi if name == "doi" else normalize_pmid
    identifiers = {}
    for value in values:
        try:
            normalized = normalize(value)
        except ValueError as error:
            raise ValueError(f"{context}: {name}: {error}") from error
        if normalized is not None:
            identifiers.setdefault(normalized, value)
    if len(identifiers) > 1:
        raise ValueError(f"{context}: conflicting {name} identifiers: {list(identifiers)}")
    return next(iter(identifiers.values()), None)


def _first(fields, *names):
    for name in names:
        for value in fields.get(name, []):
            if value.strip():
                return value.strip()
    return ""


def _year(value, context, field):
    if not value:
        return None
    match = re.search(r"(?<!\d)(\d{4})(?!\d)", value)
    if match is None or int(match.group(1)) == 0:
        raise ValueError(f"{context}: {field} has no valid four-digit publication year: {value!r}")
    return int(match.group(1))


def _load_ris(text):
    records = []
    entries = None
    raw_lines = []
    start_line = 0
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            if entries is not None:
                raw_lines.append(line)
            continue
        match = _RIS_TAG.fullmatch(line)
        if match is None:
            if entries is None:
                raise ValueError(f"RIS line {line_number}: expected TY record-start tag")
            # Untagged continuation lines are commonly used for long abstracts.
            if re.match(r"^[A-Z0-9]{2}\s*[-:]", line):
                raise ValueError(f"RIS record {len(records) + 1}, line {line_number}: malformed tag")
            entries[-1]["value"] += "\n" + line.strip()
            raw_lines.append(line)
            continue
        tag, value = match.groups()
        if tag == "TY":
            if entries is not None:
                raise ValueError(f"RIS record {len(records) + 1}, line {line_number}: missing ER before next TY")
            if not value.strip():
                raise ValueError(f"RIS line {line_number}: TY type must be nonempty")
            entries = [{"tag": tag, "value": value}]
            raw_lines = [line]
            start_line = line_number
            continue
        if entries is None:
            raise ValueError(f"RIS line {line_number}: {tag} outside a TY/ER record")
        entries.append({"tag": tag, "value": value})
        raw_lines.append(line)
        if tag == "ER":
            context = f"RIS record {len(records) + 1}, lines {start_line}-{line_number}"
            if value.strip():
                raise ValueError(f"{context}: ER must not contain a value")
            records.append(_ris_record(entries, raw_lines, context))
            entries = None
    if entries is not None:
        raise ValueError(f"RIS record {len(records) + 1}, line {start_line}: missing ER at end of file")
    return records


def _ris_record(entries, raw_lines, context):
    fields = {}
    for entry in entries:
        fields.setdefault(entry["tag"], []).append(entry["value"])
    # An accession number is database-specific. A bare numeric AN is not PMID.
    pubmed = any(
        re.fullmatch(r"(?:NCBI\s+)?PubMed(?:\s*\(NCBI\))?", value.strip(), re.IGNORECASE)
        for tag in ("DB", "DP") for value in fields.get(tag, [])
    )
    accession = fields.get("AN", [])
    pmid_values = fields.get("PM", []) + (accession if pubmed else [])
    # Some PubMed RIS exporters prefix AN with an explicit PMID label.
    pmid_values = [re.sub(r"^\s*PMID\s*:\s*", "", value, flags=re.IGNORECASE) for value in pmid_values]
    record = {
        "title": _first(fields, "TI", "T1"),
        "authors": [entry["value"].strip() for entry in entries if entry["tag"] in ("AU", "A1")],
        "year": _year(_first(fields, "PY", "Y1"), context, "PY/Y1"),
        "doi": _unique_identifier(fields.get("DO", []) + fields.get("DI", []), "doi", context),
        "pmid": _unique_identifier(pmid_values, "pmid", context),
        "abstract": "\n".join(entry["value"].strip() for entry in entries if entry["tag"] in ("AB", "N2")),
        "url": _first(fields, "UR"),
        "source_id": _first(fields, "AN", "ID"),
    }
    raw = {"fields": fields, "entries": entries, "text": "\n".join(raw_lines)}
    return _record(record, raw, context)


def _tag(element):
    return element.tag.rsplit("}", 1)[-1]


def _children(element, tag):
    return [] if element is None else [child for child in element if _tag(child) == tag]


def _path(element, path):
    current = element
    for tag in path.split("/"):
        children = _children(current, tag)
        if not children:
            return None
        current = children[0]
    return current


def _text(element):
    return "" if element is None else " ".join("".join(element.itertext()).split())


def _tree(element):
    return {
        "tag": element.tag,
        "attributes": dict(element.attrib),
        "text": element.text or "",
        "tail": element.tail or "",
        "children": [_tree(child) for child in element],
    }


def _load_xml(text):
    # ElementTree ignores external DTDs, but expands declared internal entities.
    # Reject declarations before parsing so no local/network entity is processed.
    if re.search(r"<!ENTITY\b", text, re.IGNORECASE):
        raise ValueError("PubMed XML document: ENTITY declarations are unsupported")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise ValueError(f"PubMed XML line {error.position[0]}, column {error.position[1]}: {error}") from error
    record_tags = {"PubmedArticle", "PubmedBookArticle", "MedlineCitation"}
    containers = {"PubmedArticleSet", "PubmedBookArticleSet", "MedlineCitationSet"}
    if _tag(root) in record_tags:
        elements = [root]
    elif _tag(root) in containers:
        elements = list(root)
        for index, element in enumerate(elements, 1):
            if _tag(element) not in record_tags:
                raise ValueError(f"PubMed XML record {index}: unsupported element {_tag(element)!r}")
        if (root.text or "").strip():
            raise ValueError("PubMed XML document: unexpected text outside citation records")
    else:
        raise ValueError(f"PubMed XML document: unsupported root {_tag(root)!r}; expected PubmedArticleSet")
    return [_xml_record(element, f"PubMed XML record {index}") for index, element in enumerate(elements, 1)]


def _xml_record(element, context):
    is_book = _tag(element) == "PubmedBookArticle"
    citation = _path(element, "BookDocument" if is_book else "MedlineCitation")
    if _tag(element) == "MedlineCitation":
        citation = element
    if citation is None:
        raise ValueError(f"{context}: missing {'BookDocument' if is_book else 'MedlineCitation'}")
    article = citation if is_book else _path(citation, "Article")
    if article is None:
        raise ValueError(f"{context}: missing Article")
    title = _text(_path(article, "ArticleTitle"))
    if not title:
        title = _text(_path(article, "VernacularTitle"))
    if is_book and not title:
        title = _text(_path(article, "Book/BookTitle"))

    authors = []
    for author_list in _children(article, "AuthorList"):
        for author in _children(author_list, "Author"):
            collective = _text(_path(author, "CollectiveName"))
            if collective:
                authors.append(collective)
                continue
            last = _text(_path(author, "LastName"))
            given = _text(_path(author, "ForeName")) or _text(_path(author, "Initials"))
            suffix = _text(_path(author, "Suffix"))
            name = f"{last}, {given}" if last and given else last or given
            if suffix:
                name = f"{name} {suffix}".strip()
            if not name:
                raise ValueError(f"{context}: Author has neither personal nor collective name")
            authors.append(name)

    sections = []
    for abstract in _children(article, "Abstract"):
        parts = _children(abstract, "AbstractText")
        if not parts:
            sections.append(_text(abstract))
        for part in parts:
            body = _text(part)
            label = part.get("Label", "").strip()
            sections.append(f"{label}: {body}" if label else body)

    doi_values = []
    pmid_values = [_text(pmid) for pmid in _children(citation, "PMID")]
    id_lists = _children(citation, "ArticleIdList")
    for data_tag in ("PubmedData", "PubmedBookData"):
        id_lists.extend(_children(_path(element, data_tag), "ArticleIdList"))
    for id_list in id_lists:
        for identifier in _children(id_list, "ArticleId"):
            kind = identifier.get("IdType", "").lower()
            if kind == "doi":
                doi_values.append(_text(identifier))
            elif kind in ("pubmed", "pmid"):
                pmid_values.append(_text(identifier))
    doi_values.extend(_text(identifier) for identifier in _children(article, "ELocationID") if identifier.get("EIdType", "").lower() == "doi")
    doi = _unique_identifier(doi_values, "doi", context)
    pmid = _unique_identifier(pmid_values, "pmid", context)

    publication = _path(article, "Book/PubDate" if is_book else "Journal/JournalIssue/PubDate")
    date_value = _text(_path(publication, "Year")) or _text(_path(publication, "MedlineDate"))
    if not date_value:
        date_value = _text(_path(article, "ArticleDate/Year"))
    year = _year(date_value, context, "publication date")
    url = f"https://pubmed.ncbi.nlm.nih.gov/{normalize_pmid(pmid)}/" if pmid else ""
    raw = {"xml": ET.tostring(element, encoding="unicode"), "tree": _tree(element)}
    return _record({
        "title": title,
        "authors": authors,
        "year": year,
        "doi": doi,
        "pmid": pmid,
        "abstract": "\n".join(sections),
        "url": url,
        "source_id": pmid or "",
    }, raw, context)
