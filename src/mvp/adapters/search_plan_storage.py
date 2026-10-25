"""Bounded additive planning history in the existing research SQLite file."""
import hashlib
import json

from ..contracts import canonical, now
from ..ports import MvpError
from ..search_plan_contracts import SearchPlanRevision
from ..search_plan_service_contracts import (
    MAX_PLAN_AUXILIARY_BYTES, MAX_PLAN_RECEIPTS, MAX_PLAN_RECORD_BYTES,
    MAX_PLAN_REQUESTS, MAX_PLAN_REVISIONS, MAX_SEARCH_PLANS,
)

TABLES = ('mvp_search_plans', 'mvp_search_plan_revisions', 'mvp_search_plan_events', 'mvp_search_plan_requests')
# One bounded event plus its bounded terminal request outcome. The small
# allowance also covers row identity and timestamps; completion releases this.
CALL_RESERVATION_BYTES = 2 * MAX_PLAN_RECORD_BYTES + 4096


def search_plan_auxiliary_bytes(db, workspace_id):
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    total = 0
    for table in TABLES:
        if table not in tables:
            continue
        columns = [row[1] for row in db.execute(f'PRAGMA table_info({table})')]
        expression = '+'.join('COALESCE(length(CAST("' + name.replace('"', '""') + '" AS BLOB)),0)' for name in columns)
        total += db.execute(f'SELECT COALESCE(SUM({expression}),0) FROM {table} WHERE workspace_id=?', (workspace_id,)).fetchone()[0]
    if 'mvp_search_plan_requests' in tables:
        total += CALL_RESERVATION_BYTES * db.execute("SELECT COUNT(*) FROM mvp_search_plan_requests WHERE workspace_id=? AND status='pending'", (workspace_id,)).fetchone()[0]
    return total


def packed(value):
    payload = canonical(value)
    if len(payload.encode('utf-8')) > MAX_PLAN_RECORD_BYTES:
        raise MvpError('search_plan_size_limit', 'This planning record exceeds its bounded capacity. Existing history remains readable.')
    return payload, hashlib.sha256(payload.encode('utf-8')).hexdigest()


def decoded(row, model=None):
    try:
        payload = row['payload']
        if payload is None or len(payload.encode('utf-8')) > MAX_PLAN_RECORD_BYTES or hashlib.sha256(payload.encode('utf-8')).hexdigest() != row['sha256']:
            raise ValueError('checksum')
        value = json.loads(payload)
        return model.model_validate(value) if model else value
    except Exception:
        raise MvpError('search_plan_integrity', 'The retained planning record failed its version or checksum check.') from None


class SearchPlanStore:
    def __init__(self, storage):
        self.storage = storage
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS mvp_search_plans(
                    id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,head_revision_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
                    FOREIGN KEY(workspace_id) REFERENCES mvp_workspaces(id) ON DELETE CASCADE);
                CREATE TABLE IF NOT EXISTS mvp_search_plan_revisions(
                    id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,plan_id TEXT NOT NULL,revision INTEGER NOT NULL,
                    payload TEXT NOT NULL,sha256 TEXT NOT NULL,created_at TEXT NOT NULL,
                    UNIQUE(plan_id,revision),FOREIGN KEY(plan_id) REFERENCES mvp_search_plans(id) ON DELETE CASCADE,
                    FOREIGN KEY(workspace_id) REFERENCES mvp_workspaces(id) ON DELETE CASCADE);
                CREATE TABLE IF NOT EXISTS mvp_search_plan_events(
                    id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,plan_id TEXT NOT NULL,revision_id TEXT NOT NULL,
                    kind TEXT NOT NULL,payload TEXT NOT NULL,sha256 TEXT NOT NULL,created_at TEXT NOT NULL,
                    FOREIGN KEY(plan_id) REFERENCES mvp_search_plans(id) ON DELETE CASCADE,
                    FOREIGN KEY(workspace_id) REFERENCES mvp_workspaces(id) ON DELETE CASCADE);
                CREATE TABLE IF NOT EXISTS mvp_search_plan_requests(
                    workspace_id TEXT NOT NULL,operation TEXT NOT NULL,request_id TEXT NOT NULL,fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending','succeeded','failed')),
                    outcome TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
                    PRIMARY KEY(workspace_id,operation,request_id),
                    FOREIGN KEY(workspace_id) REFERENCES mvp_workspaces(id) ON DELETE CASCADE);
            ''')

    def connection(self):
        return self.storage._connection()

    def limits(self, db, workspace_id):
        counts = {table: db.execute(f'SELECT COUNT(*) FROM {table} WHERE workspace_id=?', (workspace_id,)).fetchone()[0] for table in TABLES}
        original = db.execute('SELECT length(CAST(snapshot AS BLOB)) FROM mvp_workspaces WHERE id=?', (workspace_id,)).fetchone()
        if original is None:
            raise MvpError('unknown_workspace', 'This workspace is unavailable.')
        research = original[0] + db.execute('SELECT COALESCE(SUM(length(CAST(result AS BLOB))),0) FROM mvp_requests WHERE workspace_id=?', (workspace_id,)).fetchone()[0]
        pending = db.execute("SELECT COUNT(*) FROM mvp_search_plan_requests WHERE workspace_id=? AND status='pending'", (workspace_id,)).fetchone()[0]
        if (counts[TABLES[0]] > MAX_SEARCH_PLANS or counts[TABLES[2]] + pending > MAX_PLAN_RECEIPTS
                or counts[TABLES[3]] > MAX_PLAN_REQUESTS
                or search_plan_auxiliary_bytes(db, workspace_id) > MAX_PLAN_AUXILIARY_BYTES
                or research + self.storage._auxiliary_bytes(db, workspace_id) > self.storage._max_workspace_bytes):
            raise MvpError('search_plan_storage_limit', 'Planning history reached its bounded capacity. Existing research and plans remain readable.')

    @staticmethod
    def request(db, workspace_id, operation, request_id, fingerprint):
        row = db.execute('SELECT * FROM mvp_search_plan_requests WHERE workspace_id=? AND operation=? AND request_id=?', (workspace_id, operation, request_id)).fetchone()
        if row is None:
            return None
        if row['fingerprint'] != fingerprint:
            raise MvpError('idempotency_conflict', 'This request key already belongs to different planning input.')
        if row['status'] == 'pending':
            raise MvpError('search_plan_call_pending', 'This exact call is in progress or its outcome is unknown after interruption. It was not repeated.', True)
        value = json.loads(row['outcome'])
        if row['status'] == 'failed':
            raise MvpError(value['code'], value['message'], value.get('retryable', False))
        return value

    def mutate(self, workspace_id, operation, request_id, fingerprint, callback):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                replay = self.request(db, workspace_id, operation, request_id, fingerprint)
                if replay is not None:
                    db.execute('COMMIT')
                    return replay
                outcome = callback(db)
                self.save_request(db, workspace_id, operation, request_id, fingerprint, 'succeeded', outcome)
                self.limits(db, workspace_id)
                db.execute('COMMIT')
                return outcome
            except BaseException:
                if db.in_transaction:
                    db.execute('ROLLBACK')
                raise

    @staticmethod
    def save_request(db, workspace_id, operation, request_id, fingerprint, status, outcome):
        text, _ = packed(outcome)
        stamp = now()
        db.execute('INSERT INTO mvp_search_plan_requests VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(workspace_id,operation,request_id) DO UPDATE SET status=excluded.status,outcome=excluded.outcome,updated_at=excluded.updated_at',
            (workspace_id, operation, request_id, fingerprint, status, text, stamp, stamp))

    def revision(self, db, workspace_id, plan_id, revision_id=None):
        plan = db.execute('SELECT * FROM mvp_search_plans WHERE workspace_id=? AND id=?', (workspace_id, plan_id)).fetchone()
        if plan is None:
            raise MvpError('unknown_search_plan', 'This search plan does not belong to the workspace.')
        identifier = revision_id or plan['head_revision_id']
        row = db.execute('SELECT id,CASE WHEN length(CAST(payload AS BLOB))<=? THEN payload ELSE NULL END AS payload,sha256 FROM mvp_search_plan_revisions WHERE workspace_id=? AND plan_id=? AND id=?',
            (MAX_PLAN_RECORD_BYTES, workspace_id, plan_id, identifier)).fetchone()
        if row is None:
            raise MvpError('unknown_search_plan_revision', 'This revision does not belong to the search plan.')
        result = decoded(row, SearchPlanRevision)
        if result.plan_id != plan_id or result.workspace_id != workspace_id or result.revision_id != identifier:
            raise MvpError('search_plan_integrity', 'Retained planning identity changed.')
        return result

    def insert_revision(self, db, revision):
        payload, checksum = packed(revision.model_dump(mode='json'))
        if revision.revision > MAX_PLAN_REVISIONS:
            raise MvpError('search_plan_revision_limit', 'This plan reached its retained revision bound. Existing revisions remain readable.')
        if revision.parent_revision_id is None:
            db.execute('INSERT INTO mvp_search_plans VALUES(?,?,?,?,?)', (revision.plan_id, revision.workspace_id, revision.revision_id, revision.created_at, revision.created_at))
        else:
            changed = db.execute('UPDATE mvp_search_plans SET head_revision_id=?,updated_at=? WHERE workspace_id=? AND id=? AND head_revision_id=?',
                (revision.revision_id, revision.created_at, revision.workspace_id, revision.plan_id, revision.parent_revision_id)).rowcount
            if changed != 1:
                raise MvpError('stale_search_plan', 'A newer plan revision exists. Keep local edits and reload before saving.')
        db.execute('INSERT INTO mvp_search_plan_revisions VALUES(?,?,?,?,?,?,?)', (revision.revision_id, revision.workspace_id, revision.plan_id, revision.revision, payload, checksum, revision.created_at))

    def event(self, db, workspace_id, plan_id, event_id, kind, model=None):
        row = db.execute('SELECT CASE WHEN length(CAST(payload AS BLOB))<=? THEN payload ELSE NULL END AS payload,sha256 FROM mvp_search_plan_events WHERE workspace_id=? AND plan_id=? AND id=? AND kind=?',
            (MAX_PLAN_RECORD_BYTES, workspace_id, plan_id, event_id, kind)).fetchone()
        if row is None:
            raise MvpError('unknown_search_plan_receipt', 'This receipt does not belong to the exact plan and workspace.')
        return decoded(row, model)

    def insert_event(self, db, workspace_id, plan_id, revision_id, kind, identifier, value):
        payload, checksum = packed(value)
        db.execute('INSERT INTO mvp_search_plan_events VALUES(?,?,?,?,?,?,?,?)', (identifier, workspace_id, plan_id, revision_id, kind, payload, checksum, now()))
