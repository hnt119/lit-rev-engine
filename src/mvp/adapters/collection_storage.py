"""Private, additive citation and immutable collection records in research SQLite.

Raw citation bytes remain private until workspace deletion. They are never part
of a paper projection or default export. New metadata snapshots are compressed,
bounded and checksum checked; existing research/source storage is not migrated.
"""
from contextlib import contextmanager
import hashlib
import hmac
import json
import zlib

from pydantic import Field

from ..collection_contracts import (
    ImportSummary, MAX_COLLECTIONS, MAX_IMPORTS, MAX_IMPORT_REVISIONS,
    MAX_INGESTION_BYTES, PaperCollectionSnapshot, ReviewedImportRow,
)
from ..contracts import canonical, digest
from ..import_contracts import ParsedImport
from ..ports import MvpError

_TABLES = ('mvp_ingestion_imports', 'mvp_ingestion_versions', 'mvp_collections', 'mvp_ingestion_requests')
MAX_VERSION_BYTES = 32 * 1024 * 1024


class RetainedImportRevision(ParsedImport):
    revision: int = Field(ge=1)
    rows: list[ReviewedImportRow]


def ingestion_auxiliary_bytes(db, workspace_id):
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    total = 0
    for table in _TABLES:
        if table not in tables:
            continue
        names = [row[1] for row in db.execute('PRAGMA table_info(' + table + ')')]
        expression = '+'.join('COALESCE(length(CAST(' + name + ' AS BLOB)),0)' for name in names)
        total += db.execute('SELECT COALESCE(SUM(' + expression + '),0) FROM ' + table + ' WHERE workspace_id=?', (workspace_id,)).fetchone()[0]
    return total


def _pack(value):
    raw = canonical(value.model_dump(mode='json')).encode('utf-8')
    if len(raw) > MAX_VERSION_BYTES:
        raise MvpError('import_storage_limit', 'The bounded normalized citation snapshot is too large. Existing imports remain unchanged.')
    return zlib.compress(raw, 6), hashlib.sha256(raw).hexdigest()


def _unpack(payload, checksum, model):
    try:
        decoder = zlib.decompressobj()
        raw = decoder.decompress(payload, MAX_VERSION_BYTES + 1)
        if len(raw) > MAX_VERSION_BYTES or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError('unbounded or incomplete payload')
        if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), checksum):
            raise ValueError('checksum')
        result = model.model_validate_json(raw)
        if not hmac.compare_digest(digest(result.model_dump(mode='json')), checksum):
            raise ValueError('canonical metadata changed')
        return result
    except Exception:
        raise MvpError('collection_integrity', 'Retained citation metadata failed its integrity check.') from None


class CollectionStore:
    def __init__(self, storage):
        self.storage, self.path = storage, storage._path
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS mvp_ingestion_imports(
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL,
                    format TEXT NOT NULL, filename TEXT, file_sha256 TEXT NOT NULL,
                    raw_payload BLOB NOT NULL, current_revision INTEGER NOT NULL,
                    summary_json TEXT NOT NULL, summary_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(workspace_id) REFERENCES mvp_workspaces(id) ON DELETE CASCADE);
                CREATE TABLE IF NOT EXISTS mvp_ingestion_versions(
                    workspace_id TEXT NOT NULL, import_id TEXT NOT NULL,
                    revision INTEGER NOT NULL, payload BLOB NOT NULL,
                    payload_sha256 TEXT NOT NULL, PRIMARY KEY(import_id,revision),
                    FOREIGN KEY(workspace_id) REFERENCES mvp_workspaces(id) ON DELETE CASCADE,
                    FOREIGN KEY(import_id) REFERENCES mvp_ingestion_imports(id) ON DELETE CASCADE);
                CREATE TABLE IF NOT EXISTS mvp_collections(
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL,
                    payload BLOB NOT NULL, payload_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(workspace_id) REFERENCES mvp_workspaces(id) ON DELETE CASCADE);
                CREATE TABLE IF NOT EXISTS mvp_ingestion_requests(
                    workspace_id TEXT NOT NULL, operation TEXT NOT NULL,
                    request_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    result_json TEXT NOT NULL, PRIMARY KEY(workspace_id,operation,request_id),
                    FOREIGN KEY(workspace_id) REFERENCES mvp_workspaces(id) ON DELETE CASCADE);
            ''')

    @contextmanager
    def connection(self):
        with self.storage._connection() as db:
            yield db

    def _limits(self, db, workspace_id):
        row = db.execute('SELECT length(CAST(snapshot AS BLOB)) FROM mvp_workspaces WHERE id=?', (workspace_id,)).fetchone()
        if row is None:
            raise MvpError('unknown_workspace', 'This workspace is unavailable.')
        research = row[0] + db.execute('SELECT COALESCE(SUM(length(CAST(result AS BLOB))),0) FROM mvp_requests WHERE workspace_id=?', (workspace_id,)).fetchone()[0]
        if (ingestion_auxiliary_bytes(db, workspace_id) > MAX_INGESTION_BYTES
                or research + self.storage._auxiliary_bytes(db, workspace_id) > self.storage._max_workspace_bytes
                or db.execute('SELECT COUNT(*) FROM mvp_ingestion_imports WHERE workspace_id=?', (workspace_id,)).fetchone()[0] > MAX_IMPORTS
                or db.execute('SELECT COUNT(*) FROM mvp_collections WHERE workspace_id=?', (workspace_id,)).fetchone()[0] > MAX_COLLECTIONS):
            raise MvpError('import_storage_limit', 'This workspace reached its bounded import/collection capacity. Existing records remain readable.')

    @staticmethod
    def _request(db, workspace_id, operation, request_id, fingerprint):
        prior = db.execute('SELECT * FROM mvp_ingestion_requests WHERE workspace_id=? AND operation=? AND request_id=?', (workspace_id, operation, request_id)).fetchone()
        if prior is None:
            return None
        if not hmac.compare_digest(prior['fingerprint'], fingerprint):
            raise MvpError('idempotency_conflict', 'This import request key was already used with different input.')
        return json.loads(prior['result_json'])

    def replay(self, workspace_id, operation, request_id, fingerprint):
        with self.connection() as db:
            return self._request(db, workspace_id, operation, request_id, fingerprint)

    def mutate(self, workspace_id, operation, request_id, fingerprint, callback):
        """Caller holds authorized lifecycle/workspace guards; no provider I/O here."""
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                if db.execute('SELECT 1 FROM mvp_workspaces WHERE id=?', (workspace_id,)).fetchone() is None:
                    raise MvpError('unknown_workspace', 'This workspace is unavailable.')
                prior = self._request(db, workspace_id, operation, request_id, fingerprint)
                if prior is not None:
                    db.execute('COMMIT')
                    return prior
                result = callback(db)
                output = result.model_dump(mode='json')
                db.execute('INSERT INTO mvp_ingestion_requests VALUES(?,?,?,?,?)', (workspace_id, operation, request_id, fingerprint, canonical(output)))
                self._limits(db, workspace_id)
                db.execute('COMMIT')
                return output
            except BaseException:
                if db.in_transaction:
                    db.execute('ROLLBACK')
                raise

    @staticmethod
    def _import(db, workspace_id, import_id):
        row = db.execute('SELECT * FROM mvp_ingestion_imports WHERE workspace_id=? AND id=?', (workspace_id, import_id)).fetchone()
        if row is None:
            raise MvpError('unknown_import', 'The requested import does not belong to this workspace.')
        return row

    @staticmethod
    def _summary(row):
        try:
            value = ImportSummary.model_validate_json(row['summary_json'])
            if digest(value.model_dump(mode='json')) != row['summary_sha256'] or value.revision != row['current_revision']:
                raise ValueError('summary changed')
            return value
        except Exception:
            raise MvpError('collection_integrity', 'Retained import metadata failed its integrity check.') from None

    def summary(self, workspace_id, import_id, db=None):
        if db is None:
            with self.connection() as connection:
                return self.summary(workspace_id, import_id, connection)
        return self._summary(self._import(db, workspace_id, import_id))

    def imports(self, workspace_id):
        with self.connection() as db:
            return [self._summary(row) for row in db.execute('SELECT * FROM mvp_ingestion_imports WHERE workspace_id=? ORDER BY created_at DESC,id DESC', (workspace_id,))]

    def document(self, workspace_id, import_id, db=None, revision=None):
        if db is None:
            with self.connection() as connection:
                return self.document(workspace_id, import_id, connection, revision)
        record = self._import(db, workspace_id, import_id)
        version = record['current_revision'] if revision is None else revision
        row = db.execute('SELECT * FROM mvp_ingestion_versions WHERE workspace_id=? AND import_id=? AND revision=?', (workspace_id, import_id, version)).fetchone()
        if row is None:
            raise MvpError('unknown_import_revision', 'The requested import revision is unavailable.')
        value = _unpack(row['payload'], row['payload_sha256'], RetainedImportRevision)
        if value.file_sha256 != record['file_sha256'] or value.revision != version:
            raise MvpError('collection_integrity', 'Retained import identity changed.')
        return value

    def raw(self, workspace_id, import_id):
        with self.connection() as db:
            row = self._import(db, workspace_id, import_id)
            payload = bytes(row['raw_payload'])
            if hashlib.sha256(payload).hexdigest() != row['file_sha256']:
                raise MvpError('collection_integrity', 'The retained original citation bytes failed their integrity check.')
            return payload

    def insert_import(self, db, workspace_id, summary, document, payload):
        packed, checksum = _pack(document)
        db.execute('INSERT INTO mvp_ingestion_imports VALUES(?,?,?,?,?,?,?,?,?,?)',
                   (summary.id, workspace_id, document.format, document.filename, document.file_sha256,
                    payload, document.revision, canonical(summary.model_dump(mode='json')),
                    digest(summary.model_dump(mode='json')), summary.created_at))
        db.execute('INSERT INTO mvp_ingestion_versions VALUES(?,?,?,?,?)', (workspace_id, summary.id, document.revision, packed, checksum))

    def update_import(self, db, workspace_id, import_id, expected_revision, summary, document=None):
        prior = self._import(db, workspace_id, import_id)
        if prior['current_revision'] != expected_revision:
            raise MvpError('stale_import_revision', 'This import changed. Reload its preview before applying another review action.')
        if document is not None:
            if document.revision != expected_revision + 1 or document.revision > MAX_IMPORT_REVISIONS:
                raise MvpError('import_revision_limit', 'This import reached its bounded revision count. Retained versions remain readable.')
            packed, checksum = _pack(document)
            db.execute('INSERT INTO mvp_ingestion_versions VALUES(?,?,?,?,?)', (workspace_id, import_id, document.revision, packed, checksum))
        db.execute('UPDATE mvp_ingestion_imports SET current_revision=?,summary_json=?,summary_sha256=? WHERE workspace_id=? AND id=?',
                   (summary.revision, canonical(summary.model_dump(mode='json')), digest(summary.model_dump(mode='json')), workspace_id, import_id))

    def insert_collection(self, db, snapshot):
        packed, checksum = _pack(snapshot)
        db.execute('INSERT INTO mvp_collections VALUES(?,?,?,?,?)', (snapshot.id, snapshot.workspace_id, packed, checksum, snapshot.created_at))
        return checksum

    def collection(self, workspace_id, identifier, db=None):
        if db is None:
            with self.connection() as connection:
                return self.collection(workspace_id, identifier, connection)
        row = db.execute('SELECT * FROM mvp_collections WHERE workspace_id=? AND id=?', (workspace_id, identifier)).fetchone()
        if row is None:
            raise MvpError('unknown_collection', 'The requested collection does not belong to this workspace.')
        value = _unpack(row['payload'], row['payload_sha256'], PaperCollectionSnapshot)
        if value.id != identifier or value.workspace_id != workspace_id:
            raise MvpError('collection_integrity', 'Retained collection identity changed.')
        return value, row['payload_sha256']

    def collections(self, workspace_id):
        with self.connection() as db:
            return [self.collection(workspace_id, row['id'], db) for row in db.execute('SELECT id FROM mvp_collections WHERE workspace_id=? ORDER BY created_at DESC,id DESC', (workspace_id,)).fetchall()]
