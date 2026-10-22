"""Additive import/collection contracts; legacy search artifacts are unchanged."""
from typing import Annotated, Literal
from pydantic import Field, field_validator

from .contracts import Model, Paper, new_id, now
from .import_contracts import CitationMetadata, ImportDiagnostic, ImportRow, ResolutionReceipt
from .limits import MAX_IMPORT_ROWS, MAX_IMPORT_BYTES

MAX_COLLECTIONS = 40
MAX_IMPORTS = 20
MAX_IMPORT_REVISIONS = 20
MAX_INGESTION_BYTES = 32 * 1024 * 1024
PAGE_SIZE = 25


class SearchInputRef(Model):
    kind: Literal['search'] = 'search'
    search_id: str
    search_snapshot_sha256: str


class CollectionInputRef(Model):
    kind: Literal['collection'] = 'collection'
    collection_id: str
    collection_snapshot_sha256: str


PaperInputRef = Annotated[SearchInputRef | CollectionInputRef, Field(discriminator='kind')]


class MemberOrigin(Model):
    kind: Literal['search_occurrence', 'import_row', 'resolved_identifier']
    search_id: str | None = None
    search_snapshot_sha256: str | None = None
    import_id: str | None = None
    import_revision: int | None = None
    file_sha256: str | None = None
    filename: str | None = None
    row_id: str | None = None
    row_number: int | None = None
    source_key: str | None = None
    supplied_metadata_sha256: str | None = None
    resolution_receipt_sha256: str | None = None
    paper_id: str | None = None
    metadata_version_id: str | None = None


class ImportRowAccounting(Model):
    row_id: str
    status: str
    diagnostic_codes: list[str]


class ImportAccounting(Model):
    import_id: str
    import_revision: int
    file_sha256: str
    accepted_row_ids: list[str]
    not_committed: list[ImportRowAccounting]


class SavedSearchCitationMetadata(Model):
    """Lossless read adapter for papers predating import-specific field bounds."""
    metadata_schema_version: Literal['mvp.saved-search-metadata.v1'] = 'mvp.saved-search-metadata.v1'
    title: str
    authors: list[str]
    year: int | None
    doi: str | None
    pmid: str | None
    pmcid: str | None
    abstract: str
    url: str
    publication_title: str = ''


class MetadataSnapshot(Model):
    id: str
    metadata: CitationMetadata | SavedSearchCitationMetadata
    abstract_provider: str
    field_origins: dict[str, str]
    resolution_receipts: list[ResolutionReceipt] = Field(default_factory=list)


class CollectionMember(Model):
    paper: Paper
    metadata_version: MetadataSnapshot
    origins: list[MemberOrigin] = Field(min_length=1)


class SearchMetadata(Model):
    original_query: str | None = None
    searched_at: str | None = None
    provider: str | None = None
    total_reported: int | None = None
    fetched_count: int | None = None


class DuplicateGroup(Model):
    id: str
    kind: Literal['exact_identifier_duplicate', 'identifier_conflict', 'possible_duplicate']
    row_ids: list[str]
    message: str


class CollectionDecision(Model):
    group_id: str
    action: Literal['merge_exact', 'keep_separate']
    member_ids: list[str]


class PaperCollectionSnapshot(Model):
    schema_version: Literal['mvp.paper-collection.v1'] = 'mvp.paper-collection.v1'
    id: str = Field(default_factory=new_id)
    collection_id: str = Field(default_factory=new_id)
    revision_id: str = Field(default_factory=new_id)
    revision: int = 1
    workspace_id: str
    name: str = Field(min_length=1, max_length=200)
    kind: Literal['import', 'combined', 'subset']
    parent_snapshot_id: str | None = None
    parents: list[PaperInputRef] = Field(default_factory=list)
    input_digests: list[str] = Field(default_factory=list)
    members: list[CollectionMember] = Field(min_length=1, max_length=MAX_IMPORT_ROWS)
    duplicate_decisions: list[CollectionDecision] = Field(default_factory=list)
    import_accounting: ImportAccounting | None = None
    search_metadata: SearchMetadata = Field(default_factory=SearchMetadata)
    coverage: Literal['imported_records', 'explicit_combination', 'explicit_subset']
    created_at: str = Field(default_factory=now)


class CollectionSummary(Model):
    id: str
    collection_id: str
    revision_id: str
    revision: int
    name: str
    kind: Literal['saved_search', 'import', 'combined', 'subset']
    origin: PaperInputRef
    member_count: int
    created_at: str
    search_metadata: SearchMetadata
    parents: list[PaperInputRef]
    coverage: str


class CollectionListing(Model):
    collections: list[CollectionSummary]
    max_map_papers: int = 50
    max_prepared_sources: int = 30


class CollectionPaperPage(Model):
    collection_id: str
    origin: PaperInputRef
    papers: list[Paper]
    offset: int
    total: int
    next_offset: int | None


class CollectionPaperDetail(Model):
    collection_id: str
    origin: PaperInputRef
    member: CollectionMember


class ReviewedImportRow(ImportRow):
    supplied_metadata: CitationMetadata
    metadata_version_sha256: str
    field_origins: dict[str, str]
    resolution_receipts: list[ResolutionReceipt] = Field(default_factory=list)


class ImportSummary(Model):
    id: str
    workspace_id: str
    revision: int
    filename: str | None
    format: Literal['csv', 'ris', 'identifiers']
    file_sha256: str
    byte_count: int
    parser_version: str
    mapping_version: str
    headers: list[str]
    mapping: dict[str, str]
    ignored_columns: list[str]
    row_count: int
    ready_count: int
    pending_count: int
    error_count: int
    duplicate_groups: list[DuplicateGroup]
    diagnostics: list[ImportDiagnostic]
    committed_collection_ids: list[str]
    created_at: str
    updated_at: str


class ImportListing(Model):
    imports: list[ImportSummary]


class ImportRowPage(Model):
    import_id: str
    revision: int
    rows: list[ReviewedImportRow]
    offset: int
    total: int
    next_offset: int | None


class ImportMappingRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    expected_revision: int = Field(ge=1, strict=True)
    mapping: dict[str, str]


class ImportResolveRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    expected_revision: int = Field(ge=1, strict=True)
    row_ids: list[str] = Field(min_length=1, max_length=3)


class ImportEditRowRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    expected_revision: int = Field(ge=1, strict=True)
    row_id: str
    metadata: CitationMetadata


class ImportCommitRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    expected_revision: int = Field(ge=1, strict=True)
    name: str = Field(min_length=1, max_length=200)
    accepted_row_ids: list[str] = Field(min_length=1, max_length=MAX_IMPORT_ROWS)
    duplicate_policy: Literal['review_required', 'keep_separate', 'merge_exact'] = 'review_required'
    conflict_decisions: dict[str, Literal['keep_separate']] = Field(default_factory=dict)

    @field_validator('accepted_row_ids')
    @classmethod
    def distinct(cls, values):
        if len(values) != len(set(values)):
            raise ValueError('Select each row once')
        return values


class CollectionSourceSelection(Model):
    origin: PaperInputRef
    paper_ids: list[str] | None = Field(default=None, max_length=MAX_IMPORT_ROWS)


class CombineCollectionsRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    sources: list[CollectionSourceSelection] = Field(min_length=1, max_length=10)
    duplicate_policy: Literal['review_required', 'keep_separate', 'merge_exact'] = 'review_required'
    conflict_decisions: dict[str, Literal['keep_separate']] = Field(default_factory=dict)
    preview_sha256: str | None = Field(default=None, max_length=64)


class CombineMemberPreview(Model):
    id: str
    paper_id: str
    title: str
    pmid: str | None
    doi: str | None
    pmcid: str | None
    collection_id: str


class CombineCollectionsPreview(Model):
    input_sha256: str
    member_count: int
    duplicate_groups: list[DuplicateGroup]
    members: list[CombineMemberPreview]
    sources: list[PaperInputRef]
