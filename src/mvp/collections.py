"""Explicit citation review and immutable exploratory collections.

No import is represented as an executed search. Metadata resolution occurs
outside mutation locks; only a current, authorized preview can publish results.
"""
from dataclasses import dataclass
from contextlib import nullcontext
import hashlib
import ipaddress
import unicodedata
from urllib.parse import urlsplit

from .adapters.collection_storage import CollectionStore, RetainedImportRevision
from .collection_contracts import (
    CollectionDecision, CollectionInputRef, CollectionListing, CollectionMember,
    CollectionPaperDetail, CollectionPaperPage, CollectionSummary,
    CombineCollectionsPreview, CombineMemberPreview, DuplicateGroup,
    ImportAccounting, ImportListing, ImportRowAccounting, ImportRowPage,
    ImportSummary, MAX_IMPORT_ROWS, MemberOrigin, MetadataSnapshot,
    PaperCollectionSnapshot, ReviewedImportRow, SavedSearchCitationMetadata, SearchInputRef, SearchMetadata,
)
from .contracts import Paper, StructuredError, digest, new_id, now
from .import_contracts import CitationMetadata, ImportDiagnostic, ResolutionBatch, ResolutionInput
from .import_parsing import parse_import_bytes
from .ports import MvpError


def _text(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def _safe_public_link(value):
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or '').lower().rstrip('.')
        if parsed.scheme not in {'http', 'https'} or not host or parsed.username or parsed.password:
            return False
        if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return '.' in host
    except ValueError:
        return False


def _kind(members):
    metadata = [member.metadata_version.metadata if isinstance(member, CollectionMember) else member for _, member in members]
    if any(len({getattr(item, key) for item in metadata if getattr(item, key)}) > 1
           for key in ('doi', 'pmid', 'pmcid')):
        return 'identifier_conflict'
    if any(len([item for item in metadata if getattr(item, key)]) > 1
           for key in ('doi', 'pmid', 'pmcid')):
        return 'exact_identifier_duplicate'
    return 'possible_duplicate'


def duplicate_groups(members):
    """Exact identities/title equality identify review groups, never studies."""
    parents = list(range(len(members)))
    def find(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i
    keys = {}
    for i, (_, member) in enumerate(members):
        metadata = member.metadata_version.metadata if isinstance(member, CollectionMember) else member
        values = [(name, getattr(metadata, name)) for name in ('doi', 'pmid', 'pmcid')]
        if metadata.title.strip():
            values.append(('title', _text(metadata.title)))
        for name, value in values:
            if not value:
                continue
            previous = keys.setdefault((name, value), i)
            parents[find(i)] = find(previous)
    buckets = {}
    for i, item in enumerate(members):
        buckets.setdefault(find(i), []).append(item)
    result = []
    for items in buckets.values():
        if len(items) < 2:
            continue
        ids = [identifier for identifier, _ in items]
        kind = _kind(items)
        result.append(DuplicateGroup(id='duplicate:' + digest(sorted(ids)), kind=kind, row_ids=ids,
            message={'exact_identifier_duplicate': 'Exact identifiers recur. Choose whether to merge occurrences or retain separate reports.',
                     'identifier_conflict': 'Identifiers disagree within this review group. Keep separate explicitly or exclude conflicting rows.',
                     'possible_duplicate': 'The normalized titles match; this does not establish the same report. Keep separate or review your accepted set.'}[kind]))
    return result


def _metadata_version(row):
    content = {'metadata': row.metadata.model_dump(mode='json'), 'supplied_metadata': row.supplied_metadata.model_dump(mode='json'),
               'field_origins': row.field_origins,
               'resolution_receipts': [item.model_dump(mode='json') for item in row.resolution_receipts]}
    return digest(content)


def _abstract_provider(row):
    origin = row.field_origins.get('abstract', 'supplied')
    if origin.startswith('resolution:'):
        receipt = next((item for item in row.resolution_receipts if digest(item.model_dump(mode='json')) == origin.removeprefix('resolution:')), None)
        if receipt:
            return receipt.abstract_origin or receipt.provider + '_abstract'
    return 'imported_abstract'


def _row_member(row, import_id, revision, parsed):
    metadata = row.metadata
    paper_id = 'import-report:' + digest([import_id, row.id, row.metadata_version_sha256])
    paper = Paper(id=paper_id, **metadata.model_dump(exclude={'publication_title'}))
    version = MetadataSnapshot(id=row.metadata_version_sha256, metadata=metadata,
        abstract_provider=_abstract_provider(row), field_origins=row.field_origins,
        resolution_receipts=row.resolution_receipts)
    origin = MemberOrigin(kind='import_row', import_id=import_id, import_revision=revision,
        file_sha256=parsed.file_sha256, filename=parsed.filename, row_id=row.id,
        row_number=row.row_number, source_key=row.source_key,
        supplied_metadata_sha256=digest(row.supplied_metadata.model_dump(mode='json')),
        paper_id=paper_id, metadata_version_id=version.id)
    origins = [origin]
    for receipt in row.resolution_receipts:
        origins.append(MemberOrigin(kind='resolved_identifier', import_id=import_id, import_revision=revision,
            row_id=row.id, row_number=row.row_number, paper_id=paper_id, metadata_version_id=version.id,
            resolution_receipt_sha256=digest(receipt.model_dump(mode='json'))))
    return CollectionMember(paper=paper, metadata_version=version, origins=origins)


def _apply_policy(members, policy, decisions, known_groups=None):
    indexed = dict(members)
    groups = duplicate_groups(members) if known_groups is None else known_groups
    if set(decisions) - {group.id for group in groups}:
        raise MvpError('invalid_duplicate_decision', 'Duplicate review decisions must refer to the current preview groups.')
    remaining = set(indexed)
    merged, recorded = {}, []
    for original in groups:
        items = [(identifier, indexed[identifier]) for identifier in original.row_ids if identifier in indexed]
        if len(items) < 2:
            continue
        kind = _kind(items)
        explicit_separate = decisions.get(original.id) == 'keep_separate'
        if kind != 'exact_identifier_duplicate' and not explicit_separate:
            raise MvpError('duplicate_review_required', 'Review conflicting identifiers or matching titles explicitly before committing this collection.')
        if kind == 'exact_identifier_duplicate' and policy == 'review_required' and not explicit_separate:
            raise MvpError('duplicate_review_required', 'Choose an explicit duplicate policy before committing repeated identifiers.')
        merge = kind == 'exact_identifier_duplicate' and policy == 'merge_exact' and not explicit_separate
        ids = [identifier for identifier, _ in items]
        recorded.append(CollectionDecision(group_id=original.id, action='merge_exact' if merge else 'keep_separate', member_ids=ids))
        if merge:
            first = items[0][1]
            origins = [origin for _, member in items for origin in member.origins]
            merged[ids[0]] = first.model_copy(update={'origins': origins})
            remaining.difference_update(ids[1:])
    output, used = [], set()
    for identifier, member in members:
        if identifier not in remaining:
            continue
        value = merged.get(identifier, member)
        if value.paper.id in used:
            value = value.model_copy(update={'paper': value.paper.model_copy(update={
                'id': 'report-occurrence:' + digest([identifier, value.paper.id])})})
        used.add(value.paper.id)
        output.append(value)
    return output, recorded


@dataclass(frozen=True)
class ResolvedCollection:
    summary: CollectionSummary
    members: tuple[CollectionMember, ...]


class CollectionService:
    def __init__(self, engine, store: CollectionStore, resolver=None, *, registry=None):
        self.engine, self.store, self.registry = engine, store, registry
        if resolver is None:
            from .adapters.metadata_resolution import ExactMetadataResolver
            resolver = ExactMetadataResolver()
        self.resolver = resolver

    def _read(self, handle):
        # Resolution is also used inside existing lifecycle/workspace guards.
        # Do not acquire a second non-reentrant flock or reverse their order.
        if self.registry is not None and self.registry.is_deleted(handle.workspace_id):
            raise MvpError('unknown_workspace', 'This workspace is unavailable.')
        return self.engine.get_workspace(handle)

    def _mutate(self, handle, operation, request_id, fingerprint, model, callback):
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 200:
            raise MvpError('invalid_request_id', 'Provide a bounded import request identifier.')
        guard = self.registry.lifecycle_guard(handle.workspace_id) if self.registry is not None else nullcontext()
        with guard:
            self._read(handle)
            result = self.engine.with_workspace_state(handle, lambda state:
                self.store.mutate(handle.workspace_id, operation, request_id, fingerprint, lambda db: callback(state, db)))
        return model.model_validate(result)

    @staticmethod
    def _parsed(parsed):
        if any(item.severity == 'error' for item in parsed.diagnostics):
            raise MvpError('import_parse_error', 'Repair the citation file before importing: ' + '; '.join(item.code for item in parsed.diagnostics if item.severity == 'error'))
        if not parsed.rows:
            raise MvpError('empty_import', 'No citation records were supplied.')

    @staticmethod
    def _reviewed(parsed, revision=1):
        rows = []
        for row in parsed.rows:
            value = ReviewedImportRow(**row.model_dump(mode='json'), supplied_metadata=row.metadata,
                metadata_version_sha256='', field_origins={field: 'supplied' for field in CitationMetadata.model_fields})
            rows.append(value.model_copy(update={'metadata_version_sha256': _metadata_version(value)}))
        return RetainedImportRevision(**parsed.model_dump(exclude={'rows'}), rows=rows, revision=revision)

    @staticmethod
    def _summary(identifier, workspace_id, document, previous=None):
        members = [(row.id, row.metadata) for row in document.rows]
        timestamp = now()
        return ImportSummary(id=identifier, workspace_id=workspace_id, revision=document.revision,
            filename=document.filename, format=document.format, file_sha256=document.file_sha256,
            byte_count=document.byte_count, parser_version=document.parser_version, mapping_version=document.mapping_version,
            headers=document.headers, mapping=document.mapping, ignored_columns=document.ignored_columns,
            row_count=len(document.rows), ready_count=sum(row.status == 'ready' for row in document.rows),
            pending_count=sum(row.status == 'pending' for row in document.rows),
            error_count=sum(row.status in {'invalid', 'conflict'} for row in document.rows),
            duplicate_groups=duplicate_groups(members), diagnostics=document.diagnostics,
            committed_collection_ids=previous.committed_collection_ids if previous else [],
            created_at=previous.created_at if previous else timestamp, updated_at=timestamp)

    def upload(self, handle, payload, format, request_id, filename=None):
        self._read(handle)
        fingerprint = digest({'format': format, 'file_sha256': hashlib.sha256(payload).hexdigest(), 'filename': filename})
        prior = self.store.replay(handle.workspace_id, 'upload', request_id, fingerprint)
        if prior is not None:
            return ImportSummary.model_validate(prior)
        parsed = parse_import_bytes(payload, format, filename=filename)
        self._parsed(parsed)
        document, identifier = self._reviewed(parsed), new_id()
        summary = self._summary(identifier, handle.workspace_id, document)
        def publish(state, db):
            self.store.insert_import(db, handle.workspace_id, summary, document, payload)
            return summary
        return self._mutate(handle, 'upload', request_id, fingerprint, ImportSummary, publish)

    def imports(self, handle):
        self._read(handle)
        return ImportListing(imports=self.store.imports(handle.workspace_id))

    def import_summary(self, handle, identifier):
        self._read(handle)
        return self.store.summary(handle.workspace_id, identifier)

    def import_rows(self, handle, identifier, offset=0, limit=25):
        self._read(handle)
        if offset < 0 or not 1 <= limit <= 50:
            raise MvpError('invalid_page', 'Choose a bounded citation page.')
        document = self.store.document(handle.workspace_id, identifier)
        total = len(document.rows)
        return ImportRowPage(import_id=identifier, revision=document.revision, rows=document.rows[offset:offset + limit],
            offset=offset, total=total, next_offset=offset + limit if offset + limit < total else None)

    def _revision(self, handle, identifier, expected, db=None):
        document = self.store.document(handle.workspace_id, identifier, db)
        if document.revision != expected:
            raise MvpError('stale_import_revision', 'This import changed. Reload its preview before applying another review action.')
        return document

    def _publish_revision(self, handle, identifier, request, document, operation):
        fingerprint = digest({'import_id': identifier, **request.model_dump(mode='json')})
        def publish(state, db):
            self._revision(handle, identifier, request.expected_revision, db)
            previous = self.store.summary(handle.workspace_id, identifier, db)
            summary = self._summary(identifier, handle.workspace_id, document, previous)
            self.store.update_import(db, handle.workspace_id, identifier, request.expected_revision, summary, document)
            return summary
        return self._mutate(handle, operation, request.request_id, fingerprint, ImportSummary, publish)

    def _replay(self, handle, identifier, request, operation):
        self._read(handle)
        fingerprint = digest({'import_id': identifier, **request.model_dump(mode='json')})
        prior = self.store.replay(handle.workspace_id, operation, request.request_id, fingerprint)
        return ImportSummary.model_validate(prior) if prior is not None else None

    def remap(self, handle, identifier, request):
        prior = self._replay(handle, identifier, request, 'mapping')
        if prior is not None:
            return prior
        document = self._revision(handle, identifier, request.expected_revision)
        parsed = parse_import_bytes(self.store.raw(handle.workspace_id, identifier), document.format,
            filename=document.filename, mapping=request.mapping)
        self._parsed(parsed)
        return self._publish_revision(handle, identifier, request, self._reviewed(parsed, document.revision + 1), 'mapping')

    def edit_row(self, handle, identifier, request):
        prior = self._replay(handle, identifier, request, 'edit_row')
        if prior is not None:
            return prior
        document = self._revision(handle, identifier, request.expected_revision)
        found, rows = False, []
        for row in document.rows:
            if row.id != request.row_id:
                rows.append(row)
                continue
            found = True
            metadata = CitationMetadata.model_validate(request.metadata.model_dump(mode='json'))
            if metadata.url and not _safe_public_link(metadata.url):
                metadata = metadata.model_copy(update={'url': ''})
            updated = row.model_copy(update={'metadata': metadata, 'status': 'ready' if metadata.title.strip() else 'pending',
                'diagnostics': [ImportDiagnostic(code='manual_metadata_edit', message='The researcher explicitly corrected normalized metadata.', severity='warning', row_number=row.row_number)],
                'field_origins': {field: row.field_origins.get(field, 'supplied') if getattr(metadata, field) == getattr(row.metadata, field) else 'manual' for field in CitationMetadata.model_fields}})
            rows.append(updated.model_copy(update={'metadata_version_sha256': _metadata_version(updated)}))
        if not found:
            raise MvpError('unknown_import_row', 'The requested row does not belong to this import.')
        return self._publish_revision(handle, identifier, request,
            document.model_copy(update={'rows': rows, 'revision': document.revision + 1}), 'edit_row')

    def resolve_metadata(self, handle, identifier, request):
        prior = self._replay(handle, identifier, request, 'resolve')
        if prior is not None:
            return prior
        document = self._revision(handle, identifier, request.expected_revision)
        if len(set(request.row_ids)) != len(request.row_ids):
            raise MvpError('invalid_resolution', 'Select each metadata row once.')
        indexed = {row.id: row for row in document.rows}
        if set(request.row_ids) - indexed.keys():
            raise MvpError('unknown_import_row', 'Metadata resolution must use rows from this import.')
        try:
            inputs = [ResolutionInput(row_id=key, **indexed[key].metadata.model_dump(include={'doi', 'pmid', 'pmcid'})) for key in request.row_ids]
        except ValueError:
            raise MvpError('invalid_resolution', 'Selected rows need an explicit DOI, PMID or PMCID.') from None
        # Deliberately outside every workspace/database mutation lock.
        try:
            batch = ResolutionBatch.model_validate(self.resolver.resolve(inputs))
        except Exception:
            raise MvpError('metadata_resolution_failed', 'Metadata resolution did not return a valid bounded receipt. No changes were published.', True) from None
        receipts = {item.row_id: item for item in batch.items}
        if len(receipts) != len(batch.items) or set(receipts) != set(request.row_ids):
            raise MvpError('resolution_integrity', 'Metadata resolution returned unexpected row identities. No changes were published.')
        rows = []
        for row in document.rows:
            receipt = receipts.get(row.id)
            if receipt is None:
                rows.append(row)
                continue
            expected = {key: value for key in ('doi', 'pmid', 'pmcid') if (value := getattr(row.metadata, key))}
            matching = bool(expected) and all(receipt.returned_identifiers.get(key) == value for key, value in expected.items())
            metadata_identifiers = {key: value for key in ('doi', 'pmid', 'pmcid')
                if receipt.metadata is not None and (value := getattr(receipt.metadata, key))}
            mismatch = metadata_identifiers != receipt.returned_identifiers
            if receipt.requested_identifiers != expected or (receipt.status == 'resolved' and (not matching or mismatch or receipt.metadata is None)):
                receipt = receipt.model_copy(update={'status': 'conflict', 'metadata': None, 'error': StructuredError(
                    code='metadata_identity_mismatch', message='Resolved identifiers did not match the requested row.')})
            metadata, origins = row.metadata, dict(row.field_origins)
            diagnostics = list(row.diagnostics)
            if receipt.status == 'resolved' and receipt.metadata is not None:
                updates = {}
                for key in CitationMetadata.model_fields:
                    value = getattr(receipt.metadata, key)
                    if not getattr(metadata, key) and value:
                        updates[key] = value
                        origins[key] = 'resolution:' + digest(receipt.model_dump(mode='json'))
                metadata = CitationMetadata.model_validate({**metadata.model_dump(mode='json'), **updates})
                diagnostics = [item for item in diagnostics if not (item.code == 'title_missing' and metadata.title.strip())]
            else:
                diagnostics.append(ImportDiagnostic(code='metadata_' + receipt.status,
                    message='Exact metadata resolution did not establish compatible metadata; review or supply metadata manually.',
                    severity='error' if receipt.status == 'conflict' else 'warning', row_number=row.row_number))
            status = 'conflict' if receipt.status == 'conflict' else ('invalid' if any(item.severity == 'error' and item.code != 'cross_row_identity_conflict' for item in diagnostics) else 'ready' if metadata.title.strip() else 'pending')
            updated = row.model_copy(update={'metadata': metadata, 'field_origins': origins, 'diagnostics': diagnostics,
                'status': status, 'resolution_receipts': [*row.resolution_receipts, receipt]})
            rows.append(updated.model_copy(update={'metadata_version_sha256': _metadata_version(updated)}))
        return self._publish_revision(handle, identifier, request,
            document.model_copy(update={'rows': rows, 'revision': document.revision + 1}), 'resolve')

    @staticmethod
    def _collection_summary(snapshot, checksum):
        return CollectionSummary(id=snapshot.id, collection_id=snapshot.collection_id, revision_id=snapshot.revision_id,
            revision=snapshot.revision, name=snapshot.name, kind=snapshot.kind,
            origin=CollectionInputRef(collection_id=snapshot.id, collection_snapshot_sha256=checksum),
            member_count=len(snapshot.members), created_at=snapshot.created_at,
            search_metadata=snapshot.search_metadata, parents=snapshot.parents, coverage=snapshot.coverage)

    def commit_import(self, handle, identifier, request):
        self._read(handle)
        fingerprint = digest({'import_id': identifier, **request.model_dump(mode='json')})
        def commit(state, db):
            document = self._revision(handle, identifier, request.expected_revision, db)
            self._parsed(document)
            indexed = {row.id: row for row in document.rows}
            if set(request.accepted_row_ids) - indexed.keys():
                raise MvpError('unknown_import_row', 'The accepted rows must belong to this import.')
            accepted = [indexed[key] for key in request.accepted_row_ids]
            if any(not row.metadata.title.strip() or any(item.severity == 'error' and item.code != 'cross_row_identity_conflict' for item in row.diagnostics) for row in accepted):
                raise MvpError('import_review_required', 'Accepted records need usable titles and repaired row errors. Unresolved records remain pending.')
            original = [(row.id, row.metadata) for row in document.rows]
            members, decisions = _apply_policy([(row.id, _row_member(row, identifier, document.revision, document)) for row in accepted],
                request.duplicate_policy, request.conflict_decisions, duplicate_groups(original))
            if not request.name.strip():
                raise MvpError('invalid_collection_name', 'Provide a collection name.')
            accepted_ids = set(request.accepted_row_ids)
            accounting = ImportAccounting(import_id=identifier, import_revision=document.revision,
                file_sha256=document.file_sha256, accepted_row_ids=request.accepted_row_ids,
                not_committed=[ImportRowAccounting(row_id=row.id, status=row.status, diagnostic_codes=[item.code for item in row.diagnostics]) for row in document.rows if row.id not in accepted_ids])
            snapshot = PaperCollectionSnapshot(workspace_id=handle.workspace_id, name=request.name, kind='import',
                members=members, input_digests=[document.file_sha256, digest(document.model_dump(mode='json'))],
                duplicate_decisions=decisions, import_accounting=accounting, coverage='imported_records')
            checksum = self.store.insert_collection(db, snapshot)
            previous = self.store.summary(handle.workspace_id, identifier, db)
            updated = previous.model_copy(update={'committed_collection_ids': [*previous.committed_collection_ids, snapshot.id], 'updated_at': now()})
            self.store.update_import(db, handle.workspace_id, identifier, document.revision, updated)
            return self._collection_summary(snapshot, checksum)
        return self._mutate(handle, 'commit', request.request_id, fingerprint, CollectionSummary, commit)

    def _search_collection(self, state, search):
        checksum = digest(search.model_dump(mode='json'))
        origin = SearchInputRef(search_id=search.id, search_snapshot_sha256=checksum)
        metadata = SearchMetadata(original_query=search.query, searched_at=search.searched_at, provider=search.provider,
            total_reported=search.total_reported, fetched_count=search.fetched_count)
        summary = CollectionSummary(id=search.id, collection_id=search.id, revision_id=search.id, revision=1,
            name=search.query, kind='saved_search', origin=origin, member_count=len(search.papers),
            created_at=search.searched_at, search_metadata=metadata, parents=[], coverage='saved_exploratory_search_preview')
        members = []
        for paper in search.papers:
            citation = SavedSearchCitationMetadata(**paper.model_dump(exclude={'id'}))
            version_id = digest(paper.model_dump(mode='json'))
            provider = 'pubmed_abstract' if search.provider == 'pubmed' else search.provider + '_abstract'
            version = MetadataSnapshot(id=version_id, metadata=citation, abstract_provider=provider,
                field_origins={key: search.provider for key in CitationMetadata.model_fields})
            members.append(CollectionMember(paper=paper, metadata_version=version, origins=[MemberOrigin(
                kind='search_occurrence', search_id=search.id, search_snapshot_sha256=checksum,
                paper_id=paper.id, metadata_version_id=version_id)]))
        return ResolvedCollection(summary, tuple(members))

    def resolve_collection(self, handle, origin):
        state = self._read(handle)
        if origin.kind == 'search':
            search = next((item for item in state.searches if item.id == origin.search_id), None)
            if search is None:
                raise MvpError('unknown_search', 'The requested search does not belong to this workspace.')
            resolved = self._search_collection(state, search)
            if resolved.summary.origin.search_snapshot_sha256 != origin.search_snapshot_sha256:
                raise MvpError('stale_collection_inputs', 'The saved search snapshot no longer matches the reviewed input.')
            return resolved
        snapshot, checksum = self.store.collection(handle.workspace_id, origin.collection_id)
        if checksum != origin.collection_snapshot_sha256:
            raise MvpError('stale_collection_inputs', 'The collection snapshot does not match the reviewed input.')
        return ResolvedCollection(self._collection_summary(snapshot, checksum), tuple(snapshot.members))

    def listing(self, handle):
        state = self._read(handle)
        return CollectionListing(collections=[
            *[self._collection_summary(snapshot, checksum) for snapshot, checksum in self.store.collections(handle.workspace_id)],
            *[self._search_collection(state, search).summary for search in reversed(state.searches)]])

    def _resolve_id(self, handle, identifier):
        state = self._read(handle)
        search = next((item for item in state.searches if item.id == identifier), None)
        if search is not None:
            return self._search_collection(state, search)
        snapshot, checksum = self.store.collection(handle.workspace_id, identifier)
        return ResolvedCollection(self._collection_summary(snapshot, checksum), tuple(snapshot.members))

    def collection(self, handle, identifier):
        return self._resolve_id(handle, identifier).summary

    def papers(self, handle, identifier, offset=0, limit=25, filter=''):
        if offset < 0 or not 1 <= limit <= 50 or len(filter) > 200:
            raise MvpError('invalid_page', 'Choose a bounded paper page/filter.')
        resolved = self._resolve_id(handle, identifier)
        needle = _text(filter)
        papers = [member.paper for member in resolved.members if not needle or needle in _text(member.paper.title + ' ' + ' '.join(member.paper.authors))]
        total = len(papers)
        return CollectionPaperPage(collection_id=identifier, origin=resolved.summary.origin, papers=papers[offset:offset + limit],
            offset=offset, total=total, next_offset=offset + limit if offset + limit < total else None)

    def paper(self, handle, identifier, paper_id):
        resolved = self._resolve_id(handle, identifier)
        member = next((item for item in resolved.members if item.paper.id == paper_id), None)
        if member is None:
            raise MvpError('unknown_paper', 'The requested paper does not belong to this collection.')
        return CollectionPaperDetail(collection_id=identifier, origin=resolved.summary.origin, member=member)

    def _combine_input(self, handle, request):
        if not request.name.strip():
            raise MvpError('invalid_collection_name', 'Provide a collection name.')
        members = []
        for position, source in enumerate(request.sources):
            resolved = self.resolve_collection(handle, source.origin)
            ids = source.paper_ids
            if ids is not None and (not ids or len(ids) != len(set(ids)) or set(ids) - {member.paper.id for member in resolved.members}):
                raise MvpError('invalid_collection_selection', 'Choose distinct owned papers for each collection input.')
            chosen = [member for member in resolved.members if ids is None or member.paper.id in set(ids)]
            for member in chosen:
                members.append((str(position) + ':' + member.paper.id, member))
        if not 1 <= len(members) <= MAX_IMPORT_ROWS:
            raise MvpError('collection_size_limit', 'An explicit combined collection can contain at most five hundred input report occurrences.')
        payload = {'sources': [source.model_dump(mode='json') for source in request.sources]}
        return members, digest(payload)

    def combine_preview(self, handle, request):
        members, checksum = self._combine_input(handle, request)
        return CombineCollectionsPreview(input_sha256=checksum, member_count=len(members), duplicate_groups=duplicate_groups(members),
            members=[CombineMemberPreview(id=identifier, paper_id=member.paper.id, title=member.paper.title,
                pmid=member.paper.pmid, doi=member.paper.doi, pmcid=member.paper.pmcid,
                collection_id=request.sources[int(identifier.split(':', 1)[0])].origin.search_id if request.sources[int(identifier.split(':', 1)[0])].origin.kind == 'search' else request.sources[int(identifier.split(':', 1)[0])].origin.collection_id) for identifier, member in members],
            sources=[source.origin for source in request.sources])

    def combine(self, handle, request):
        self._read(handle)
        fingerprint = digest(request.model_dump(mode='json'))
        def commit(state, db):
            members, checksum = self._combine_input(handle, request)
            if request.preview_sha256 is not None and request.preview_sha256 != checksum:
                raise MvpError('stale_combination_preview', 'The reviewed combination changed. Preview the selected inputs again.')
            output, decisions = _apply_policy(members, request.duplicate_policy, request.conflict_decisions)
            subset = len(request.sources) == 1 and request.sources[0].paper_ids is not None
            snapshot = PaperCollectionSnapshot(workspace_id=handle.workspace_id, name=request.name,
                kind='subset' if subset else 'combined', members=output, parents=[source.origin for source in request.sources],
                input_digests=[checksum], duplicate_decisions=decisions,
                coverage='explicit_subset' if subset else 'explicit_combination')
            checksum = self.store.insert_collection(db, snapshot)
            return self._collection_summary(snapshot, checksum)
        return self._mutate(handle, 'combine', request.request_id, fingerprint, CollectionSummary, commit)
