"""Thin local adapter over ReviewStore and the existing comparison services.

The pilot library never becomes a SearchPreview or an alternate screening
engine. A comparison is an explicit immutable working subset, with a separate
ledger receipt; neither the copy nor its board establishes review inclusion.
"""
from __future__ import annotations

from contextlib import contextmanager
import base64
import binascii
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
from urllib.parse import urlsplit
import zipfile

from src.review.store import ReviewStore
from src.review.pilot import PilotConflict, PilotLedger

from .adapters.collection_storage import CollectionStore
from .adapters.europe_pmc import prepare_permitted_xml
from .adapters.saved_examples import SavedExampleProvider, saved_example_info
from .adapters.transport import safe_xml
from .board_contracts import BoardCreateRequest
from .collection_contracts import ImportCommitRequest
from .collections import CollectionService
from .contracts import Block, Paper, PreparedSource, SearchRequest, digest
from .ports import MvpError
from .service import _abstract, _assert_source_integrity, _validated_source
from .workspace_ui import private_directory


def _safe_link(value):
    if not value:
        return ''
    parsed = urlsplit(value)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
        raise MvpError('invalid_pilot_source_url', 'Use an HTTP(S) source URL without credentials, or leave it empty.')
    return value


def _paper(record):
    raw = record.get('raw', {})
    return Paper(id='review-record:' + record['id'], **{key: record.get(key) for key in
        ('title', 'authors', 'year', 'pmid', 'doi', 'abstract', 'url')}, pmcid=raw.get('pmcid'))


class ReviewPilotService:
    def __init__(self, directory, registry, service_for, boards):
        self.directory = Path(directory) / 'review-pilots'
        self.registry, self.service_for, self.boards = registry, service_for, boards

    def _path(self, workspace_id):
        return self.directory / (hashlib.sha256(workspace_id.encode()).hexdigest() + '.sqlite3')

    @contextmanager
    def _ledger(self, handle, *, create=False):
        path = self._path(handle.workspace_id)
        if not path.is_file() and not create:
            raise MvpError('unknown_review_pilot', 'Initialize a new isolated pilot before recording library or review actions.')
        if any(part.is_symlink() for part in (path,*path.parents)) or any(Path(str(path)+suffix).is_symlink() for suffix in ('-wal', '-shm', '-journal')):
            raise MvpError('pilot_integrity', 'Pilot storage must not use linked files.')
        if create:
            private_directory(self.directory)
        try:
            with ReviewStore(path) as store:
                path.chmod(0o600)
                yield PilotLedger(store)
        except PilotConflict as error:
            raise MvpError('stale_pilot_state', str(error)) from None
        except ValueError as error:
            if isinstance(error, MvpError):
                raise
            if str(error).startswith('Unknown source'):
                raise MvpError('unknown_pilot_source', 'This source does not belong to the authorized isolated project.') from None
            raise MvpError('invalid_review_pilot', str(error)) from None

    def _present(self, mode, handle, view):
        state = self.service_for(mode).get_workspace(handle)
        result = dict(view)
        result.pop('occurrences', None)
        result.update(available=True, workspace_source_revision=state.source_revision,
            current_preparation_id=state.preparations[-1].id if state.preparations else None)
        for key in ('protocols',):
            result[key] = [self._protocol(item) for item in view.get(key, [])]
        if view.get('current_protocol'):
            result['current_protocol'] = self._protocol(view['current_protocol'])
        result['sources'] = [{**item, 'document_id': item['id'], 'kind': item.get('source_kind'),
                              'permissions': item.get('permission_note', ''), 'current': item['active']}
                             for item in view.get('sources', [])]
        return result

    @staticmethod
    def _protocol(item):
        return {**item, 'revision': item['number'],
            'status': 'declared_ready' if item['content']['ready_for_screening'] else 'unresolved_draft'}

    def view(self, mode, handle, *, offset=0, limit=50):
        self.service_for(mode).get_workspace(handle)
        if not self._path(handle.workspace_id).is_file():
            return {'available': False, 'limitations': ['Initialize only a new isolated project; exploratory previews do not establish review inclusion.']}
        with self.registry.lifecycle_guard(handle.workspace_id), self._ledger(handle) as ledger:
            return self._present(mode, handle, ledger.view(handle.workspace_id, offset=offset, limit=limit))

    def initialize(self, mode, handle, payload):
        with self.registry.lifecycle_guard(handle.workspace_id):
            engine = self.service_for(mode)
            state = engine.get_workspace(handle)
            if self._path(handle.workspace_id).is_file():
                with self._ledger(handle) as existing:
                    if existing.store._connection.execute('SELECT 1 FROM pilot_bindings WHERE workspace_id=?',(handle.workspace_id,)).fetchone():
                        return self._present(mode, handle, existing.initialize(handle.workspace_id, {**payload, 'reviewer':payload.get('reviewer') or 'Declared local operator', 'reason':payload.get('reason') or 'Initial supplied protocol; unresolved choices preserved'}))
            with engine._storage._connection() as db:
                tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                retained=any(table in tables and db.execute('SELECT 1 FROM '+table+' WHERE workspace_id=? LIMIT 1',(handle.workspace_id,)).fetchone() for table in ('mvp_ingestion_imports','mvp_collections','mvp_search_plans'))
            if retained or state.searches or state.preparations or state.runs or state.assessments:
                raise MvpError('pilot_requires_new_workspace', 'Create a new empty workspace for this isolated review pilot. Existing exploration data will not be imported or changed.')
            with self._ledger(handle, create=True) as ledger:
                return self._present(mode, handle, ledger.initialize(handle.workspace_id, {**payload, 'reviewer':payload.get('reviewer') or 'Declared local operator', 'reason':payload.get('reason') or 'Initial supplied protocol; unresolved choices preserved'}))

    def mutate(self, mode, handle, method, payload):
        with self.registry.lifecycle_guard(handle.workspace_id), self._ledger(handle) as ledger:
            self.service_for(mode).get_workspace(handle)
            return self._present(mode, handle, getattr(ledger, method)(handle.workspace_id, payload))

    def import_file(self, mode, handle, payload):
        body = dict(payload); content = body.pop('content_utf8').encode('utf-8'); filename = body.pop('filename')
        with self.registry.lifecycle_guard(handle.workspace_id), self._ledger(handle) as ledger:
            self.service_for(mode).get_workspace(handle)
            return self._present(mode, handle, ledger.import_file(handle.workspace_id, content, filename, body))

    def import_capture(self, mode, handle, payload):
        body = dict(payload)
        try:
            artifacts = {name: base64.b64decode(value, validate=True) for name, value in body.pop('artifacts').items()}
        except (ValueError, binascii.Error):
            raise MvpError('invalid_pilot_capture', 'Capture artifacts must contain exact base64-encoded saved bytes.') from None
        with self.registry.lifecycle_guard(handle.workspace_id), self._ledger(handle) as ledger:
            self.service_for(mode).get_workspace(handle)
            return self._present(mode, handle, ledger.import_capture(handle.workspace_id, artifacts, body))

    def import_public_example(self, mode, handle, payload):
        provider = SavedExampleProvider()
        info = saved_example_info()
        preview = provider.search(SearchRequest(request_id='pilot-approved-public-sample', query='Approved saved public example — no query executed', max_results=50))
        # Preserve the exact supplied bibliography and explicit capture limits in
        # each original occurrence. This is not the PubMed capture importer.
        rows = [{**paper.model_dump(exclude={'id'}), 'source_id': paper.id,
                 'public_bundle_provenance': info} for paper in preview.papers]
        content = (json.dumps(rows, ensure_ascii=False, sort_keys=True, indent=2)+'\n').encode()
        body = {**payload, 'format': 'json', 'source': 'Approved saved Europe PMC public example',
            'query': info['query'], 'searched_at': info['searched_at'], 'filters': {},
            'reported_count': info['total_reported'], 'scope': 'exploratory_subset',
            'notes': 'All 30 supplied records retained in manifest order. Provider reported 194, metadata capture 100, rights/identity-filtered retained 30. Complete intake of supplied set only; incomplete query capture. No live query executed.'}
        manifest_bytes = (provider._root/'manifest.json').read_bytes()
        manifest = json.loads(manifest_bytes)
        if manifest != provider._manifest:
            raise MvpError('pilot_integrity', 'Approved public sample manifest changed during intake.')
        extra_assets = {'upstream/manifest.json':manifest_bytes,
            'upstream/README.md':(provider._root/'README.md').read_bytes()}
        candidate_name=manifest['capture_candidates_file']
        candidates=(provider._root/candidate_name).read_bytes()
        if hashlib.sha256(candidates).hexdigest()!=manifest['capture_candidates_sha256']:
            raise MvpError('pilot_integrity', 'Approved public capture membership receipt changed during intake.')
        extra_assets['upstream/'+candidate_name]=candidates
        for entry in manifest['sources']:
            name=entry['metadata_file']; value=(provider._root/name).read_bytes()
            if hashlib.sha256(value).hexdigest()!=entry['metadata_sha256']:
                raise MvpError('pilot_integrity','Approved public bibliography metadata changed during intake.')
            extra_assets['upstream/'+name]=value
        with self.registry.lifecycle_guard(handle.workspace_id), self._ledger(handle) as ledger:
            self.service_for(mode).get_workspace(handle)
            return self._present(mode, handle, ledger.import_file(handle.workspace_id, content,
                'approved-public-30-bibliography.json', body, extra_assets=extra_assets))

    @staticmethod
    def _record(ledger, workspace_id, record_id):
        project_id = ledger.project(workspace_id)['id']
        item = next((record for record in ledger.store.list_records(project_id) if record['id'] == record_id), None)
        if item is None:
            raise MvpError('unknown_pilot_record', 'This report does not belong to the authorized pilot project.')
        return item

    @staticmethod
    def _jats(paper, content, license, source_url=''):
        # Reuse the original permission/own-identity parser. Its current policy
        # supports CC BY/CC0 JATS with an own PMCID, not arbitrary local PDFs/TXT.
        root = safe_xml(content, 'Supplied retained JATS')
        own_pmcids = {''.join(node.itertext()).strip().upper() for front in root
            if str(front.tag).rsplit('}',1)[-1] == 'front' for meta in front
            if str(meta.tag).rsplit('}',1)[-1] == 'article-meta' for node in meta
            if str(node.tag).rsplit('}',1)[-1] == 'article-id' and node.get('pub-id-type','').lower() in {'pmc','pmcid'}}
        if len(own_pmcids) != 1:
            raise MvpError('unsupported_pilot_source', 'This JATS handoff requires one own PMCID and supported explicit CC BY/CC0 permission. TXT/PDF handoff is not implemented.')
        metadata = {key: value for key,value in (('pmid', paper.pmid),('doi', paper.doi),('pmcid',next(iter(own_pmcids)))) if value}
        metadata.update(isOpenAccess='Y', license=license)
        value = prepare_permitted_xml(paper, content, metadata, provider='retained_review_pilot_jats')
        return value.model_copy(update={'source_url': _safe_link(source_url) or value.source_url})

    def attach_source(self, mode, handle, payload):
        with self.registry.lifecycle_guard(handle.workspace_id), self._ledger(handle) as ledger:
            self.service_for(mode).get_workspace(handle)
            body = dict(payload); kind = body.pop('kind'); supplied = body.pop('content_utf8', None)
            record = self._record(ledger, handle.workspace_id, body['record_id']); paper = _paper(record)
            if kind == 'public_jats':
                source = SavedExampleProvider().prepare_collection_paper(paper)
                if source.status != 'full_text_retrieved' or source.retained_content_utf8 is None:
                    raise MvpError('unknown_public_source', 'This report does not match a rights-checked source in the approved public bundle.')
                content = source.retained_content_utf8.encode('utf-8')
                body.update(format='jats_xml', source_kind='full_text', license=source.license,
                    attribution=source.attribution, source_url=source.source_url,
                    permission_note='Explicit attachment of approved public CC BY/CC0 source; no eligibility decision or retrieval status implied.')
                filename = (paper.pmid or record['id'])+'.xml'
            elif kind == 'abstract':
                if supplied is not None:
                    raise MvpError('invalid_abstract_source', 'Abstract coverage uses the exact retained bibliography abstract; do not supply replacement text.')
                content = paper.abstract.encode('utf-8')
                if not content.strip():
                    raise MvpError('missing_pilot_abstract', 'No abstract is retained for this report. Missing information remains explicit.')
                checked = SavedExampleProvider().prepare_collection_paper(paper)
                body.update(format='txt', source_kind='abstract',
                    license=body['license'] or checked.license or 'Bibliographic abstract: rights not independently established; private local review only',
                    attribution=body['attribution'] or checked.attribution or paper.title,
                    source_url=_safe_link(body['source_url']) or paper.url,
                    permission_note=body['permission_note'] or 'Intentionally abstract-only coverage. Does not establish that full text is absent or retrieved.')
                filename = (paper.pmid or record['id'])+'-abstract.txt'
            else:
                if supplied is None or not body['license'].strip() or not body['attribution'].strip() or not body['permission_note'].strip():
                    raise MvpError('permission_unresolved', 'Supply exact JATS text, license, attribution and an explicit permission note.')
                content = supplied.encode('utf-8')
                prepared = self._jats(paper, content, body['license'], body['source_url'])
                body.update(format='jats_xml', source_kind='full_text', license=prepared.license,
                    source_url=prepared.source_url)
                filename = (paper.pmid or record['id'])+'.xml'
            return self._present(mode, handle, ledger.attach_source(handle.workspace_id, content, filename, body))

    def source(self, mode, handle, document_id, *, offset=0, limit=10):
        with self.registry.lifecycle_guard(handle.workspace_id), self._ledger(handle) as ledger:
            self.service_for(mode).get_workspace(handle)
            source = ledger.source(handle.workspace_id, document_id)
            document = source['document']
            blocks = source['blocks']
            return {'document': {**document, 'document_id': document['id']}, 'blocks': blocks[offset:offset+limit],
                'total': len(blocks), 'offset': offset, 'next_offset': offset+limit if offset+limit<len(blocks) else None}

    def _prepared(self, ledger, workspace_id, record, document_id, expected_hash):
        source = ledger.source(workspace_id, document_id)
        document = source['document']
        if document['record_id'] != record['id']:
            raise MvpError('invalid_pilot_source_binding', 'A source from another report cannot be handed off to this selected report.')
        if not document['active']:
            raise MvpError('stale_pilot_source', 'The selected source has been superseded; choose the exact current source explicitly.')
        if document['source_sha256'] != expected_hash:
            raise MvpError('stale_pilot_source', 'The selected source digest no longer matches the retained exact source.')
        paper = _paper(record)
        if document['source_kind'] == 'abstract':
            prepared = _abstract(paper)
        elif document['source_kind'] == 'full_text' and document['format'] == 'jats_xml':
            prepared = self._jats(paper, source['content'], document['license'], document['source_url'])
        else:
            raise MvpError('unsupported_pilot_source', 'Only permitted retained JATS and explicitly typed abstract-only sources can be handed off. TXT/PDF full-text handoff is not implemented.')
        if prepared.source_sha256 != document['source_sha256'] or prepared.blocks_sha256 != document['blocks_sha256']:
            raise MvpError('pilot_integrity', 'Existing preparation parser did not reproduce the exact ledger source and canonical block hashes.')
        prepared = prepared.model_copy(update={'id': 'review-source:'+document['id'],
            'version': 'review-document:'+document['id']+':v'+str(document['version']),
            'license': document['license'], 'attribution': document['attribution'],
            'warnings': [*prepared.warnings, 'Pilot working subset; comparison selection does not establish eligibility.'],
            'parser_metadata': {**prepared.parser_metadata, 'review_document_id': document['id'], 'review_document_version': document['version']}})
        _assert_source_integrity([prepared])
        if _validated_source(prepared, paper) != prepared:
            raise MvpError('pilot_integrity', 'The selected retained source did not pass existing preparation integrity checks.')
        return prepared, document

    def handoff(self, mode, handle, payload):
        engine = self.service_for(mode)
        collection_store = CollectionStore(engine._storage)
        # Caller holds the real lifecycle guard below; do not acquire it twice.
        collections = CollectionService(engine, collection_store, registry=None)
        with self.registry.lifecycle_guard(handle.workspace_id), self._ledger(handle) as ledger:
            engine.get_workspace(handle)
            request_sha256=digest(payload)
            prior_operation=next((item for item in ledger.view(handle.workspace_id)['handoff_operations'] if item['request_id']==payload['request_id']),None)
            if prior_operation is not None:
                if prior_operation['input'].get('receipt',{}).get('request_sha256')!=request_sha256:
                    raise MvpError('idempotency_conflict','This handoff request ID was used with different inputs. Use a new explicit request.')
                if prior_operation['status']=='completed':
                    return self._present(mode,handle,ledger.publish_handoff(handle.workspace_id,prior_operation['input'],
                        lambda _progress: (_ for _ in ()).throw(RuntimeError('Completed handoff must not republish'))))
            records, sources, bindings = [], [], []
            for selected in payload['sources']:
                record = self._record(ledger, handle.workspace_id, selected['record_id'])
                if record['title_abstract_state'] != 'include' or record['full_text_state'] == 'exclude':
                    raise MvpError('pilot_handoff_not_allowed', 'Select explicitly title/abstract-included reports without full-text exclusion. Exploration selections never set eligibility.')
                prepared, document = self._prepared(ledger, handle.workspace_id, record, selected['document_id'], selected['source_sha256'])
                provisional = record['full_text_state'] != 'include' or document['source_kind'] != 'full_text'
                if provisional and not payload['acknowledge_provisional']:
                    raise MvpError('pilot_provisional_acknowledgement', 'Explicitly acknowledge that pending, uncertain or abstract-only reports are a provisional working subset, not formally included reports.')
                records.append(record); sources.append(prepared)
                bindings.append({key: document[key] for key in ('record_id','source_sha256','blocks_sha256','source_kind')} | {
                    'document_id': document['id'], 'document_version': document['version'],
                    'title_abstract_state': record['title_abstract_state'], 'full_text_state': record['full_text_state'],
                    'provisional': provisional, 'record_sha256': digest(record)})
            body = {key:value for key,value in payload.items() if key not in {'sources','question','fields','acknowledge_provisional','expected_source_revision','expected_preparation_id'}}
            body['receipt'] = {'schema_version':'review-pilot.handoff.v1','request_sha256':request_sha256,'bindings':bindings,
                'question':payload['question'],'fields':payload['fields'],'acknowledge_provisional':payload['acknowledge_provisional'],
                'expected_source_revision':payload['expected_source_revision'],'expected_preparation_id':payload['expected_preparation_id']}
            operation_id = 'pilot:'+digest([handle.workspace_id,payload['request_id']])
            def publish(progress):
                current = engine.get_workspace(handle)
                # A retry after partial preparation publication may reuse the
                # request's known immutable result; unrelated new sources fail CAS.
                previous = next((item for item in ledger.view(handle.workspace_id)['handoff_operations'] if item['request_id']==payload['request_id']), None)
                partial = previous['partial_ids'] if previous else {}
                # Deterministic existing-service request receipts also permit
                # reconciliation when a controller dies before progress is saved.
                with engine._storage._connection() as db:
                    published=db.execute('SELECT result FROM mvp_requests WHERE workspace_id=? AND operation=? AND request_id=?',(handle.workspace_id,'prepare_collection_job_v2',operation_id+':prepare')).fetchone()
                retained_preparation_id=json.loads(published['result'])['id'] if published else partial.get('preparation_id')
                reused_preparation = next((p for p in current.preparations if p.id==retained_preparation_id and p.id==current.preparations[-1].id), None)
                if reused_preparation is None and (current.source_revision != payload['expected_source_revision'] or
                        (current.preparations[-1].id if current.preparations else None) != payload['expected_preparation_id']):
                    raise MvpError('stale_pilot_preparation', 'Workspace sources changed before handoff. Reload and explicitly select the intended comparison input.')
                output = io.StringIO(newline=''); writer = csv.writer(output)
                columns = ['title','authors','year','pmid','doi','pmcid','abstract','url']; writer.writerow(columns)
                for record in records:
                    paper = _paper(record)
                    writer.writerow([getattr(paper,key) if key!='authors' else '; '.join(paper.authors) for key in columns])
                uploaded = collections.upload(handle, output.getvalue().encode(), 'csv', operation_id+':upload', filename='pilot-selected-reports.csv')
                progress('citation_copy', {'import_id':uploaded.id})
                rows = collections.import_rows(handle, uploaded.id, 0, 50)
                copied = collections.commit_import(handle, uploaded.id, ImportCommitRequest(request_id=operation_id+':collection',
                    expected_revision=uploaded.revision, name='Explicit review pilot working subset',
                    accepted_row_ids=[item.id for item in rows.rows], duplicate_policy='keep_separate',
                    conflict_decisions={group.id:'keep_separate' for group in uploaded.duplicate_groups}))
                progress('collection', {'collection_id':copied.id})
                resolved = collections.resolve_collection(handle, copied.origin)
                if len(resolved.members)!=len(records):
                    raise MvpError('pilot_integrity','The derived comparison subset did not preserve each selected report.')
                bound_sources = [source.model_copy(update={'paper_id':member.paper.id}) for source,member in zip(sources,resolved.members)]
                preparation = engine.publish_collection_preparation_job(handle, operation_id+':prepare',
                    payload['expected_source_revision'], copied.origin, [member.paper.id for member in resolved.members],
                    bound_sources, lambda _db, _result, _replay: None, expected_preparation_id=payload['expected_preparation_id'])
                progress('preparation', {'preparation_id':preparation.id})
                board = self.boards._create_under_lifecycle_guard(mode, handle, BoardCreateRequest(
                    request_id=operation_id+':board', preparation_id=preparation.id, question=payload['question'],
                    paper_ids=preparation.selected_paper_ids, fields=payload['fields']))
                progress('board', {'board_id':board.definition.board_id,'revision_id':board.definition.revision_id})
                receipt = {**body['receipt'], 'collection_ref':copied.origin.model_dump(mode='json'),
                    'preparation_id':preparation.id,'source_revision':preparation.source_revision,
                    'board_id':board.definition.board_id,'revision_id':board.definition.revision_id,
                    'source_manifest_sha256':board.definition.source_manifest_sha256,
                    'bindings':[{**binding,'paper_id':source.paper_id,'comparison_source_id':source.id,
                        'comparison_source_version':source.version} for binding,source in zip(bindings,bound_sources)]}
                return receipt
            return self._present(mode, handle, ledger.publish_handoff(handle.workspace_id, body, publish))

    def export(self, mode, handle):
        with self.registry.lifecycle_guard(handle.workspace_id), self._ledger(handle) as ledger:
            self.service_for(mode).get_workspace(handle)
            with tempfile.TemporaryDirectory(prefix='litrev-pilot-export-') as folder:
                ledger.export(handle.workspace_id, folder)
                view = ledger.view(handle.workspace_id)
                for handoff in view['handoffs']:
                    receipt=handoff['receipt']
                    value=self.boards._export_under_lifecycle_guard(mode, handle, receipt['board_id'], receipt['revision_id'], history=True)
                    target=Path(folder)/'pilot'/'comparisons'/handoff['id'];target.mkdir(parents=True)
                    (target/'comparison.csv').write_text(value.csv_text)
                    (target/'comparison.json').write_text(value.json_text)
                output=io.BytesIO()
                with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
                    for path in sorted(Path(folder).rglob('*')):
                        if path.is_file():
                            archive.writestr(zipfile.ZipInfo(path.relative_to(folder).as_posix(),date_time=(1980,1,1,0,0,0)),path.read_bytes())
                return output.getvalue()

    def delete_workspace(self, workspace_id):
        # Existing owned deletion/lifecycle callback invokes this only after
        # tombstoning the same workspace; never enumerate or touch other projects.
        path=self._path(workspace_id)
        for suffix in ('','-wal','-shm','-journal'):
            item=Path(str(path)+suffix)
            if item.is_symlink():
                raise MvpError('pilot_integrity','Refusing linked pilot storage cleanup.')
            if item.is_file():
                item.unlink()
