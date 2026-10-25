"""Citation ingestion DTOs, separate from legacy paper/search artifact models."""
from typing import Annotated, Literal

import re
from urllib.parse import unquote, urlsplit
from pydantic import Field, field_validator, model_validator
from src.review.identity import normalize_doi, normalize_pmid

from .contracts import Model, StructuredError
from .limits import MAX_IMPORT_BYTES, MAX_IMPORT_ROWS, MAX_IMPORT_RESOLUTION_ROWS

MAX_IMPORT_FIELD_CHARACTERS = 64 * 1024
MAX_IMPORT_COLUMNS = 200
MAX_METADATA_RESOLUTIONS = MAX_IMPORT_RESOLUTION_ROWS
MAX_METADATA_RUNTIME_SECONDS = 45
MAX_METADATA_RESPONSE_BYTES = 2 * 1024 * 1024
IMPORT_PARSER_VERSION = 'mvp.citation-import-parser.v1'
IMPORT_MAPPING_VERSION = 'mvp.citation-import-mapping.v1'


def normalize_citation_doi(value):
    """Preserve literal URL-path punctuation, including DOI semicolon suffixes.

    The legacy identity helper uses urlparse, whose separate params component
    can discard valid DOI text. Feed the complete trusted URL path to its
    established plain-DOI validator instead; do not alter the frozen helper.
    """
    if isinstance(value, str) and re.match(r'^https?://', value.strip(), re.I):
        parsed = urlsplit(value.strip())
        if parsed.hostname not in {'doi.org', 'dx.doi.org', 'www.doi.org'} or parsed.username or parsed.password or parsed.port not in (None, 80, 443) or parsed.query or parsed.fragment:
            raise ValueError('Unsupported DOI URL')
        return normalize_doi(unquote(parsed.path.lstrip('/')))
    return normalize_doi(value)


def normalize_pmcid(value):
    if value is None or value == '':
        return None
    if not isinstance(value, str):
        raise ValueError('PMCID must be an explicit PMC identifier')
    value = re.sub(r'^PMCID\s*:\s*', '', value.strip(), flags=re.I)
    if re.match(r'^https?://', value, re.I):
        parsed = urlsplit(value)
        if parsed.username or parsed.password or parsed.port not in (None, 80, 443) or parsed.query or parsed.fragment:
            raise ValueError('Unsupported PMCID URL')
        if parsed.hostname == 'pmc.ncbi.nlm.nih.gov':
            path = re.fullmatch(r'/articles/(PMC[1-9][0-9]*)/?', parsed.path, re.I)
        elif parsed.hostname in {'www.ncbi.nlm.nih.gov', 'ncbi.nlm.nih.gov'}:
            path = re.fullmatch(r'/pmc/articles/(PMC[1-9][0-9]*)/?', parsed.path, re.I)
        else:
            path = None
        if not path:
            raise ValueError('Unsupported PMCID URL')
        value = path[1]
    if not re.fullmatch(r'PMC[1-9][0-9]*', value, re.I):
        raise ValueError('PMCID must be an explicit PMC identifier')
    return value.upper()


class CitationMetadata(Model):
    title: str = Field(default='', max_length=10000)
    authors: list[Annotated[str, Field(max_length=2000)]] = Field(default_factory=list, max_length=200)
    year: int | None = Field(default=None, ge=1, le=9999, strict=True)
    doi: str | None = Field(default=None, max_length=4096)
    pmid: str | None = Field(default=None, max_length=50)
    pmcid: str | None = Field(default=None, max_length=50)
    abstract: str = Field(default='', max_length=MAX_IMPORT_FIELD_CHARACTERS)
    url: str = Field(default='', max_length=8192)
    publication_title: str = Field(default='', max_length=10000)

    @field_validator('doi', 'pmid', 'pmcid')
    @classmethod
    def identifiers(cls, value, info):
        return {'doi': normalize_citation_doi, 'pmid': normalize_pmid, 'pmcid': normalize_pmcid}[info.field_name](value)


class ImportDiagnostic(Model):
    code: str
    message: str
    severity: Literal['error', 'warning'] = 'error'
    row_number: int | None = None
    field: str | None = None


class ImportRow(Model):
    id: str
    row_number: int
    line_number: int
    source_key: str | None = None
    supplied_identifiers: dict[str, list[str]] = Field(default_factory=dict)
    metadata: CitationMetadata = Field(default_factory=CitationMetadata)
    original_fields: dict[str, str] = Field(default_factory=dict)
    status: Literal['ready', 'pending', 'invalid', 'conflict']
    duplicate_of: str | None = None
    diagnostics: list[ImportDiagnostic] = Field(default_factory=list)


class ParsedImport(Model):
    schema_version: Literal['mvp.import-parse.v1'] = 'mvp.import-parse.v1'
    format: Literal['csv', 'ris', 'identifiers']
    filename: str | None = None
    file_sha256: str
    byte_count: int
    parser_version: str = IMPORT_PARSER_VERSION
    mapping_version: str = IMPORT_MAPPING_VERSION
    headers: list[str] = Field(default_factory=list)
    mapping: dict[str, str] = Field(default_factory=dict)
    ignored_columns: list[str] = Field(default_factory=list)
    rows: list[ImportRow] = Field(default_factory=list, max_length=MAX_IMPORT_ROWS)
    diagnostics: list[ImportDiagnostic] = Field(default_factory=list)
    blank_line_count: int = 0


class ResolutionInput(Model):
    row_id: str = Field(min_length=1, max_length=200)
    doi: str | None = Field(default=None, max_length=4096)
    pmid: str | None = Field(default=None, max_length=50)
    pmcid: str | None = Field(default=None, max_length=50)

    @field_validator('doi', 'pmid', 'pmcid')
    @classmethod
    def identifiers(cls, value, info):
        return {'doi': normalize_citation_doi, 'pmid': normalize_pmid, 'pmcid': normalize_pmcid}[info.field_name](value)

    @model_validator(mode='after')
    def has_identifier(self):
        if not any((self.doi, self.pmid, self.pmcid)):
            raise ValueError('Explicit metadata resolution requires an identifier')
        return self


class ResolutionReceipt(Model):
    schema_version: Literal['mvp.identifier-resolution.v1'] = 'mvp.identifier-resolution.v1'
    row_id: str
    status: Literal['resolved', 'unresolved', 'conflict']
    provider: Literal['crossref', 'europe_pmc', 'none']
    requested_identifiers: dict[str, str]
    returned_identifiers: dict[str, str] = Field(default_factory=dict)
    metadata: CitationMetadata | None = None
    response_sha256: str | None = None
    retrieved_at: str
    error: StructuredError | None = None
    abstract_origin: str | None = None
    normalization: str = 'none'
    rights_note: str = 'Metadata resolution does not grant full-text redistribution rights.'


class ResolutionBatch(Model):
    items: list[ResolutionReceipt]
    elapsed_seconds: float
    calls: int
    budget_exhausted: bool = False
