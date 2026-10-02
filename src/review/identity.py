"""Conservative bibliographic identities, without network or model access."""

import json
import re
import unicodedata
from dataclasses import asdict
from urllib.parse import unquote, urlparse

from .models import BibliographicRecord


def normalize_doi(value):
    """Return a lower-case DOI, accepting common DOI prefixes and URLs."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("DOI must be a string")
    value = value.strip()
    if not value:
        return None
    if re.match(r"^https?://", value, re.I):
        parsed = urlparse(value)
        if parsed.hostname not in {"doi.org", "dx.doi.org", "www.doi.org"}:
            raise ValueError(f"Malformed DOI: {value!r}")
        value = unquote(parsed.path.lstrip("/"))
        if parsed.query or parsed.fragment:
            raise ValueError("DOI URLs must not contain a query or fragment")
    value = re.sub(r"^doi\s*:\s*", "", value, flags=re.I).strip().lower()
    if not re.fullmatch(r"10\.\d{4,9}/[^\s]+", value):
        raise ValueError(f"Malformed DOI: {value!r}")
    return value


def normalize_pmid(value):
    """Return a digit-only PMID, accepting PubMed URL and PMID prefix forms."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("PMID must be a string")
    value = value.strip()
    if not value:
        return None
    if re.match(r"^https?://", value, re.I):
        parsed = urlparse(value)
        if parsed.query or parsed.fragment:
            raise ValueError("PMID URLs must not contain a query or fragment")
        if parsed.hostname in {"pubmed.ncbi.nlm.nih.gov", "www.pubmed.ncbi.nlm.nih.gov"}:
            value = parsed.path.strip("/")
        elif parsed.hostname in {"ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov"}:
            match = re.fullmatch(r"/pubmed/(\d+)/?", parsed.path)
            if not match:
                raise ValueError("Malformed PubMed URL")
            value = match.group(1)
        else:
            raise ValueError("Malformed PubMed URL")
    value = re.sub(r"^pmid\s*:\s*", "", value, flags=re.I).strip()
    if not re.fullmatch(r"[0-9]+", value) or not int(value):
        raise ValueError(f"Malformed PMID: {value!r}")
    return str(int(value))


def validate_record(record):
    """Validate a typed record and return its normalized canonical payload."""
    if not isinstance(record, BibliographicRecord):
        raise ValueError("Records must be BibliographicRecord instances")
    if not isinstance(record.title, str) or not record.title.strip():
        raise ValueError("Record title must be nonempty")
    if not isinstance(record.authors, list) or any(
        not isinstance(author, str) or not author.strip() for author in record.authors
    ):
        raise ValueError("Record authors must be a list of nonempty strings")
    if record.year is not None and (
        isinstance(record.year, bool)
        or not isinstance(record.year, int)
        or not 1 <= record.year <= 9999
    ):
        raise ValueError("Record year must be an integer from 1 to 9999")
    for field in ("abstract", "url", "source_id"):
        if not isinstance(getattr(record, field), str):
            raise ValueError(f"Record {field} must be a string")
    if not isinstance(record.raw, dict):
        raise ValueError("Record raw fields must be a dictionary")
    payload = asdict(record)
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("Record fields must be JSON-compatible") from error
    payload["doi"] = normalize_doi(record.doi)
    payload["pmid"] = normalize_pmid(record.pmid)
    return payload


def _normalized_text(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def fallback_identity(record):
    """Exact normalized title/year/first-author identity for unidentified records."""
    if record.get("doi") or record.get("pmid"):
        return None
    if not record.get("title") or not record.get("year") or not record.get("authors"):
        return None
    return json.dumps(
        [_normalized_text(record["title"]), record["year"], _normalized_text(record["authors"][0])],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _arxiv_identity(record):
    for value in (record.get("source_id", ""), record.get("url", "")):
        value = value.strip()
        if re.match(r"^https?://", value, re.I):
            parsed = urlparse(value)
            if parsed.hostname not in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
                continue
            value = re.sub(r"^/(?:abs|pdf)/", "", parsed.path).removesuffix(".pdf")
        value = re.sub(r"^arxiv\s*:\s*", "", value, flags=re.I)
        if re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-zA-Z.-]+/\d{7})(?:v\d+)?", value):
            return value.lower()
    return None


def fallback_compatible(existing, incoming):
    """Do not collapse distinct arXiv report/version identities by title."""
    existing_arxiv = _arxiv_identity(existing)
    incoming_arxiv = _arxiv_identity(incoming)
    if existing_arxiv or incoming_arxiv:
        return existing_arxiv == incoming_arxiv
    return True
