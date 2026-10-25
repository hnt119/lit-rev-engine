"""Versioned, bounded local exports for imported/combined research inputs."""
import json
from typing import Literal

from .adapters.collection_storage import CollectionStore
from .contracts import WorkspaceExport, now
from .ports import MvpError
from src.review.exporters import _csv

MAX_EXPORT_BYTES = 64 * 1024 * 1024


class CollectionWorkspaceExport(WorkspaceExport):
    schema_version: Literal['mvp.collection-export.v2'] = 'mvp.collection-export.v2'


class ResearchInputWorkspaceExport(WorkspaceExport):
    schema_version: Literal['mvp.research-input-export.v3'] = 'mvp.research-input-export.v3'


def has_ingestion(storage, workspace_id):
    with storage._connection() as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return any(db.execute(f'SELECT 1 FROM {table} WHERE workspace_id=? LIMIT 1', (workspace_id,)).fetchone()
            for table in ('mvp_ingestion_imports', 'mvp_collections') if table in tables)


def export_collection_workspace(engine, handle, _state=None):
    storage = engine._storage
    store = CollectionStore(storage)
    budget = 0

    def charge(value):
        nonlocal budget
        budget += len(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode('utf-8'))
        if budget > MAX_EXPORT_BYTES:
            raise MvpError('export_size_limit', 'The complete audit exceeds the 64 MiB export bound; no partial audit was exported.')
        return value

    # Read the workspace and immutable provenance from one SQLite snapshot.
    # This holds no workspace mutation lock and performs no provider work.
    with storage._connection() as db:
        db.execute('BEGIN')
        state = storage._authorized(db, handle)
        workspace = charge(state.model_dump(mode='json'))
        collections, needed_versions = [], {}
        for row in db.execute('SELECT id FROM mvp_collections WHERE workspace_id=? ORDER BY created_at,id', (state.id,)).fetchall():
            snapshot, checksum = store.collection(state.id, row['id'], db)
            collections.append(charge({'snapshot_sha256': checksum, 'snapshot': snapshot.model_dump(mode='json')}))
            for member in snapshot.members:
                for origin in member.origins:
                    if origin.import_id and origin.import_revision:
                        needed_versions.setdefault((origin.import_id, origin.import_revision), set()).add(origin.row_id)
        imports = []
        for row in db.execute('SELECT id FROM mvp_ingestion_imports WHERE workspace_id=? ORDER BY created_at,id', (state.id,)).fetchall():
            summary = store.summary(state.id, row['id'], db)
            current = store.document(state.id, summary.id, db)
            # Current pending/error accounting is retained; historical accepted
            # rows are included only when an immutable collection cites them.
            versions = []
            selected = {revision: identifiers for (identifier, revision), identifiers in needed_versions.items() if identifier == summary.id}
            selected[current.revision] = None
            for revision, identifiers in sorted(selected.items()):
                document = current if revision == current.revision else store.document(state.id, summary.id, db, revision)
                rows = [charge(item.model_dump(mode='json', exclude={'original_fields'})) for item in document.rows if identifiers is None or item.id in identifiers]
                versions.append({'revision': revision, 'rows': rows})
            imports.append({'summary': charge(summary.model_dump(mode='json')), 'versions': versions})
        from .planning_exports import planning_audit
        plans = planning_audit(db, state.id, charge)

    rows = engine._evidence_export_rows(state, with_collections=True)
    if plans is not None:
        executions = {item['receipt']['search_id']: item['receipt'] for plan in plans['plans'] for item in plan['receipts'] if item['kind'] == 'execution'}
        for row in rows:
            row['search_plan_execution'] = json.dumps(executions[row['search_id']], ensure_ascii=False, sort_keys=True) if row['search_id'] in executions else ''
    fields = list(rows[0]) if rows else ['workspace_id', 'question', 'search_id', 'run_id', 'passage_id', 'citation', 'pmid', 'doi', 'source_type', 'quotation', 'locator', 'source_version', 'source_sha256', 'method', 'decision', 'notes', 'assessed_at', 'input_kind', 'collection_ref', 'member_snapshot_sha256', 'member_origins']
    if plans is not None and not rows:
        fields.append('search_plan_execution')
    safe_rows = [{key: "'" + value if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')) else value for key, value in row.items()} for row in rows]
    audit = {'schema_version': 'mvp.collection-audit-bundle.v2', 'exported_at': now(),
        'offset_convention': 'half-open-unicode-codepoints', 'workspace': workspace,
        'paper_collections': collections, 'citation_imports': imports,
        'raw_import_files_included': False,
        'limitations': ['Imported collections are retained citations, not fabricated PubMed searches, complete captures or formal inclusion decisions.',
            'Original bibliographic provenance is retained; private notes, attachment fields and raw import bytes are excluded from this export.',
            'Judgments are self-declared by one human and not independently verified.',
            'Insufficient retrieved evidence is not evidence of whole-paper or literature-wide absence.']}
    if plans is not None:
        audit['schema_version'] = 'mvp.research-input-audit-bundle.v3'
        audit['search_planning'] = plans
        audit['limitations'].append('Search intent approval is a researcher declaration, not proof of MeSH validity, recall, relevance or complete question coverage. Diagnostic receipts are not search captures.')
    text = json.dumps(audit, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n'
    csv_text = _csv(safe_rows, fields)
    if len(text.encode('utf-8')) > MAX_EXPORT_BYTES or len(csv_text.encode('utf-8')) > MAX_EXPORT_BYTES:
        raise MvpError('export_size_limit', 'The complete export exceeds its 64 MiB bound; no partial audit was exported.')
    model = ResearchInputWorkspaceExport if plans is not None else CollectionWorkspaceExport
    return model(csv_text=csv_text, json_text=text)
