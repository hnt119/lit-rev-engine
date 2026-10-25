"""Additive preparation jobs in the existing research SQLite database.

Staging uses short transactions and no workspace lock. Publication is guarded
inside the research transaction, so cancellation and source publication have a
single atomic ordering. Existing source history is never removed to make room.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json

from ..contracts import PreparedSource, StructuredError, canonical, digest, new_id, now
from ..ports import MvpError
from ..preparation_contracts import (
    MAX_PREPARATION_ATTEMPTS, MAX_PREPARATION_AUXILIARY_BYTES,
    MAX_PREPARATION_INPUT_BYTES, MAX_PREPARATION_JOBS,
    MAX_PREPARATION_RUNTIME_SECONDS, MAX_PREPARATION_SOURCE_BYTES,
    PreparationInput, PreparationJobListing, PreparationJobView,
    PreparationPaperOutcome, PreparationSubmission,
)

_JOB_TABLES = ('preparation_jobs', 'collection_preparation_jobs')
_TABLES = ('preparation_jobs', 'preparation_requests', 'preparation_stages',
           'collection_preparation_jobs', 'collection_preparation_requests', 'collection_preparation_stages')
_TERMINAL = {'succeeded', 'failed', 'stale', 'cancelled'}
_VARIABLE_COLUMNS = {
    'error_json', 'lease_owner', 'lease_expires', 'active_paper_id',
    'result_preparation_id', 'result_source_revision', 'status', 'attempt',
    'progress_completed', 'elapsed_seconds', 'interrupted_count', 'updated_at',
}


def unavailable():
    return MvpError('unknown_preparation_job', 'The requested preparation job does not belong to this workspace.')


def later(seconds):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def preparation_auxiliary_bytes(db, workspace_id):
    """UTF-8 payload budget, including reserved terminal/lease metadata.

Readers of old databases return zero until the additive tables exist. This is
also used by the existing research store before any research snapshot commit.
"""
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    total = 0
    for table in _TABLES:
        if table not in tables:
            continue
        names = [row[1] for row in db.execute('PRAGMA table_info(' + table + ')')]
        counted = [name for name in names if table not in _JOB_TABLES or name not in _VARIABLE_COLUMNS]
        expression = '+'.join('COALESCE(length(CAST(' + name + ' AS BLOB)),0)' for name in counted)
        total += db.execute('SELECT COALESCE(SUM(' + expression + '),0) FROM ' + table + ' WHERE workspace_id=?', (workspace_id,)).fetchone()[0]
        if table in _JOB_TABLES:
            variable = '+'.join('COALESCE(length(CAST(' + name + ' AS BLOB)),0)' for name in sorted(_VARIABLE_COLUMNS))
            total += db.execute('SELECT COALESCE(SUM(MAX(8192,' + variable + ')),0) FROM ' + table + ' WHERE workspace_id=?', (workspace_id,)).fetchone()[0]
    return total


class PreparationStore:
    # Trusted class-level identifiers let additive job domains share all
    # attempt/staging/atomic-guard logic without changing legacy rows or hashes.
    job_table = 'preparation_jobs'
    request_table = 'preparation_requests'
    stage_table = 'preparation_stages'
    filter_column = 'search_id'
    submission_model = PreparationSubmission
    listing_model = PreparationJobListing

    def __init__(self, storage, *, max_workspace_bytes=MAX_PREPARATION_AUXILIARY_BYTES,
                 max_jobs=MAX_PREPARATION_JOBS, max_attempts=MAX_PREPARATION_ATTEMPTS,
                 max_runtime_seconds=MAX_PREPARATION_RUNTIME_SECONDS):
        self.storage = storage
        self.path = storage._path
        self.max_workspace_bytes, self.max_jobs = max_workspace_bytes, max_jobs
        self.max_attempts = min(MAX_PREPARATION_ATTEMPTS, max(1, int(max_attempts)))
        self.max_runtime_seconds = min(MAX_PREPARATION_RUNTIME_SECONDS, max(.01, float(max_runtime_seconds)))
        self._initialize()

    def _initialize(self):
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS preparation_jobs(
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL,
                    mode TEXT NOT NULL, search_id TEXT NOT NULL,
                    search_snapshot_sha256 TEXT NOT NULL, selected_json TEXT NOT NULL,
                    input_json TEXT NOT NULL, input_sha256 TEXT NOT NULL,
                    expected_source_revision INTEGER NOT NULL, expected_preparation_id TEXT,
                    status TEXT NOT NULL, attempt INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL, lease_owner TEXT, lease_expires TEXT,
                    active_paper_id TEXT, progress_completed INTEGER NOT NULL DEFAULT 0,
                    progress_total INTEGER NOT NULL, elapsed_seconds REAL NOT NULL DEFAULT 0,
                    max_runtime_seconds REAL NOT NULL, interrupted_count INTEGER NOT NULL DEFAULT 0,
                    error_json TEXT, result_preparation_id TEXT, result_source_revision INTEGER,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    FOREIGN KEY(workspace_id) REFERENCES mvp_workspaces(id) ON DELETE CASCADE);
                CREATE TABLE IF NOT EXISTS preparation_requests(
                    workspace_id TEXT NOT NULL, request_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    job_id TEXT NOT NULL, PRIMARY KEY(workspace_id,request_id),
                    FOREIGN KEY(workspace_id) REFERENCES mvp_workspaces(id) ON DELETE CASCADE,
                    FOREIGN KEY(job_id) REFERENCES preparation_jobs(id) ON DELETE CASCADE);
                CREATE TABLE IF NOT EXISTS preparation_stages(
                    workspace_id TEXT NOT NULL, job_id TEXT NOT NULL, paper_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL, payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
                    outcome_json TEXT NOT NULL, PRIMARY KEY(job_id,paper_id),
                    FOREIGN KEY(workspace_id) REFERENCES mvp_workspaces(id) ON DELETE CASCADE,
                    FOREIGN KEY(job_id) REFERENCES preparation_jobs(id) ON DELETE CASCADE);
                CREATE INDEX IF NOT EXISTS preparation_jobs_queue ON preparation_jobs(status,created_at,id);
            ''')

    @contextmanager
    def connection(self):
        with self.storage._connection() as db:
            yield db

    @contextmanager
    def transaction(self):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                yield db
                db.execute('COMMIT')
            except BaseException:
                if db.in_transaction:
                    db.execute('ROLLBACK')
                raise

    def _limits(self, db, workspace_id):
        row = db.execute('SELECT length(CAST(snapshot AS BLOB)) FROM mvp_workspaces WHERE id=?', (workspace_id,)).fetchone()
        if row is None:
            raise unavailable()
        research = row[0] + db.execute('SELECT COALESCE(SUM(length(CAST(result AS BLOB))),0) FROM mvp_requests WHERE workspace_id=?', (workspace_id,)).fetchone()[0]
        auxiliary = preparation_auxiliary_bytes(db, workspace_id)
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        count = sum(db.execute('SELECT COUNT(*) FROM ' + table + ' WHERE workspace_id=?', (workspace_id,)).fetchone()[0]
                    for table in _JOB_TABLES if table in tables)
        if auxiliary > self.max_workspace_bytes or research + self.storage._auxiliary_bytes(db, workspace_id) > self.storage._max_workspace_bytes or count > self.max_jobs:
            raise MvpError('preparation_storage_limit', 'This workspace reached its bounded preparation storage limit. Existing sources and history remain readable.')

    @classmethod
    def _row(cls, db, workspace_id, job_id):
        row = db.execute(f'SELECT * FROM {cls.job_table} WHERE workspace_id=? AND id=?', (workspace_id, job_id)).fetchone()
        if row is None:
            raise unavailable()
        return row

    @staticmethod
    def input(job):
        value = PreparationInput.model_validate_json(job['input_json'])
        if digest(value.model_dump(mode='json')) != job['input_sha256']:
            raise MvpError('preparation_integrity', 'The retained preparation input failed its integrity check.')
        if (value.paper_ids != json.loads(job['selected_json']) or value.search_snapshot_sha256 != job['search_snapshot_sha256']
                or value.search_id != job['search_id'] or value.mode != job['mode']
                or value.expected_source_revision != job['expected_source_revision']
                or value.expected_preparation_id != job['expected_preparation_id']
                or len(value.paper_ids) != job['progress_total']):
            raise MvpError('preparation_integrity', 'The retained preparation identities changed.')
        return value

    @staticmethod
    def _outcome(source, position):
        if source.status == 'full_text_retrieved':
            label = 'full_text'
        elif source.status in {'fetch_failed', 'identity_mismatch'}:
            label = 'failed'
        elif source.source_type == 'abstract':
            label = 'abstract_only'
        else:
            label = 'unavailable'
        return PreparationPaperOutcome(paper_id=source.paper_id, position=position, outcome=label,
            source_id=source.id, source_type=source.source_type, source_status=source.status, error=source.error)

    def view(self, db, row):
        ids = json.loads(row['selected_json'])
        completed = {r['paper_id']: PreparationPaperOutcome.model_validate_json(r['outcome_json']) for r in db.execute(
            f'SELECT paper_id,outcome_json FROM {self.stage_table} WHERE job_id=? ORDER BY ordinal', (row['id'],))}
        outcomes = []
        for position, identifier in enumerate(ids, 1):
            fallback = 'cancelled' if row['status'] == 'cancelled' else ('preparing' if row['active_paper_id'] == identifier and row['status'] in {'running', 'cancel_requested'} else 'pending')
            outcomes.append(completed.get(identifier) or PreparationPaperOutcome(paper_id=identifier, position=position, outcome=fallback))
        values = {name: row[name] for name in PreparationJobView.model_fields if name not in {'schema_version', 'selected_paper_ids', 'error', 'outcomes'}}
        return PreparationJobView(**values, selected_paper_ids=ids, outcomes=outcomes,
            error=StructuredError.model_validate_json(row['error_json']) if row['error_json'] else None)

    def replay(self, workspace_id, request_id, fingerprint):
        with self.connection() as db:
            prior = db.execute(f'SELECT * FROM {self.request_table} WHERE workspace_id=? AND request_id=?', (workspace_id, request_id)).fetchone()
            if prior is None:
                return None
            if prior['fingerprint'] != fingerprint:
                raise MvpError('idempotency_conflict', 'This preparation request key was already used with different input.')
            return self.submission_model(job=self.view(db, self._row(db, workspace_id, prior['job_id'])), reused=True)

    def submit(self, workspace_id, request_id, fingerprint, captured: PreparationInput):
        encoded = captured.model_dump_json()
        if len(encoded.encode('utf-8')) > MAX_PREPARATION_INPUT_BYTES:
            raise MvpError('preparation_input_limit', 'The selected preparation metadata exceeds the bounded job input limit.')
        identifier, timestamp = new_id(), now()
        with self.transaction() as db:
            prior = db.execute('SELECT * FROM preparation_requests WHERE workspace_id=? AND request_id=?', (workspace_id, request_id)).fetchone()
            if prior:
                if prior['fingerprint'] != fingerprint:
                    raise MvpError('idempotency_conflict', 'This preparation request key was already used with different input.')
                return PreparationSubmission(job=self.view(db, self._row(db, workspace_id, prior['job_id'])), reused=True)
            db.execute('''INSERT INTO preparation_jobs(id,workspace_id,mode,search_id,search_snapshot_sha256,selected_json,input_json,input_sha256,
                expected_source_revision,expected_preparation_id,status,max_attempts,progress_total,max_runtime_seconds,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,'queued',?,?,?,?,?)''',
                (identifier, workspace_id, captured.mode, captured.search_id, captured.search_snapshot_sha256,
                 canonical(captured.paper_ids), encoded, digest(captured.model_dump(mode='json')),
                 captured.expected_source_revision, captured.expected_preparation_id, self.max_attempts,
                 len(captured.paper_ids), self.max_runtime_seconds, timestamp, timestamp))
            db.execute('INSERT INTO preparation_requests VALUES(?,?,?,?)', (workspace_id, request_id, fingerprint, identifier))
            self._limits(db, workspace_id)
            return PreparationSubmission(job=self.view(db, self._row(db, workspace_id, identifier)))

    def job(self, workspace_id, job_id):
        with self.connection() as db:
            return self.view(db, self._row(db, workspace_id, job_id))

    def listing(self, workspace_id, search_id=None):
        with self.connection() as db:
            query = f'SELECT * FROM {self.job_table} WHERE workspace_id=?'
            args = [workspace_id]
            if search_id is not None:
                query += f' AND {self.filter_column}=?'
                args.append(search_id)
            return self.listing_model(jobs=[self.view(db, row) for row in db.execute(query + ' ORDER BY created_at DESC,id DESC', args)])

    def cancel(self, workspace_id, job_id):
        with self.transaction() as db:
            row = self._row(db, workspace_id, job_id)
            if row['status'] not in _TERMINAL:
                status = 'cancelled' if row['status'] == 'queued' else 'cancel_requested'
                db.execute(f'UPDATE {self.job_table} SET status=?,updated_at=? WHERE id=?', (status, now(), job_id))
            return self.view(db, self._row(db, workspace_id, job_id))

    def recover(self):
        """Call only after acquiring the OS owner lock: the former owner is gone."""
        with self.transaction() as db:
            for row in db.execute(f"SELECT * FROM {self.job_table} WHERE status IN ('running','cancel_requested')").fetchall():
                if row['status'] == 'cancel_requested':
                    status, error = 'cancelled', None
                elif row['attempt'] >= row['max_attempts']:
                    status, error = 'failed', StructuredError(code='preparation_attempt_limit', message='The preparation restart limit was reached. Staged outcomes remain available; explicitly submit a new job to retry.', retryable=False)
                else:
                    status, error = 'queued', None
                db.execute(f'UPDATE {self.job_table} SET status=?,lease_owner=NULL,lease_expires=NULL,active_paper_id=NULL,interrupted_count=interrupted_count+1,error_json=?,updated_at=? WHERE id=?',
                           (status, error.model_dump_json() if error else None, now(), row['id']))

    def claim(self, owner, lease_seconds=90):
        with self.transaction() as db:
            row = db.execute(f"SELECT * FROM {self.job_table} WHERE status='queued' ORDER BY created_at,id LIMIT 1").fetchone()
            if row is None:
                return None
            db.execute(f"UPDATE {self.job_table} SET status='running',attempt=attempt+1,lease_owner=?,lease_expires=?,active_paper_id=NULL,updated_at=? WHERE id=?",
                       (owner, later(lease_seconds), now(), row['id']))
            return dict(self._row(db, row['workspace_id'], row['id']))

    def _attempt(self, db, job):
        row = self._row(db, job['workspace_id'], job['id'])
        if row['status'] == 'cancel_requested':
            raise MvpError('preparation_cancelled', 'Preparation was cancelled. Previously current sources are unchanged.')
        if (row['status'] != 'running' or row['attempt'] != job['attempt'] or row['lease_owner'] != job['lease_owner']
                or not row['lease_expires'] or row['lease_expires'] <= now()):
            raise MvpError('preparation_attempt_lost', 'This preparation attempt is no longer active and cannot publish.')
        if row['input_sha256'] != job['input_sha256']:
            raise MvpError('preparation_integrity', 'The preparation input changed during this attempt and cannot publish.')
        return row

    def checkpoint(self, job, *, elapsed_seconds=None, active_paper_id=None, lease_seconds=90):
        with self.transaction() as db:
            row = self._attempt(db, job)
            elapsed = max(row['elapsed_seconds'], elapsed_seconds or 0)
            if elapsed >= row['max_runtime_seconds']:
                raise MvpError('preparation_runtime_limit', 'The bounded preparation runtime expired. Existing sources and staged outcomes remain available.')
            if active_paper_id is not None and active_paper_id not in json.loads(row['selected_json']):
                raise MvpError('preparation_integrity', 'Preparation progress does not match the selected paper identities.')
            db.execute(f'UPDATE {self.job_table} SET elapsed_seconds=?,active_paper_id=?,lease_expires=?,updated_at=? WHERE id=?',
                       (elapsed, active_paper_id if active_paper_id is not None else row['active_paper_id'], later(lease_seconds), now(), job['id']))

    def stage(self, job, source: PreparedSource, *, elapsed_seconds=0):
        payload = source.model_dump_json()
        if len(payload.encode('utf-8')) > MAX_PREPARATION_SOURCE_BYTES:
            raise MvpError('preparation_source_limit', 'This prepared source exceeds the bounded per-paper staging size.')
        with self.transaction() as db:
            row = self._attempt(db, job)
            ids = json.loads(row['selected_json'])
            if source.paper_id not in ids:
                raise MvpError('preparation_integrity', 'A staged source does not belong to the captured preparation selection.')
            if elapsed_seconds >= row['max_runtime_seconds']:
                raise MvpError('preparation_runtime_limit', 'The bounded preparation runtime expired before staging.')
            position = ids.index(source.paper_id) + 1
            prior = db.execute(f'SELECT payload_sha256 FROM {self.stage_table} WHERE job_id=? AND paper_id=?', (job['id'], source.paper_id)).fetchone()
            sha = digest(source.model_dump(mode='json'))
            if prior:
                if prior[0] != sha:
                    raise MvpError('preparation_integrity', 'An already staged source cannot be silently replaced.')
                return
            db.execute(f'INSERT INTO {self.stage_table} VALUES(?,?,?,?,?,?,?)',
                (job['workspace_id'], job['id'], source.paper_id, position, payload, sha, self._outcome(source, position).model_dump_json()))
            db.execute(f'UPDATE {self.job_table} SET progress_completed=progress_completed+1,active_paper_id=NULL,elapsed_seconds=MAX(elapsed_seconds,?),updated_at=? WHERE id=?',
                (elapsed_seconds, now(), job['id']))
            self._limits(db, job['workspace_id'])

    def staged(self, job):
        with self.connection() as db:
            self._row(db, job['workspace_id'], job['id'])
            sources = []
            for row in db.execute(f'SELECT * FROM {self.stage_table} WHERE job_id=? ORDER BY ordinal', (job['id'],)):
                source = PreparedSource.model_validate_json(row['payload_json'])
                if digest(source.model_dump(mode='json')) != row['payload_sha256'] or source.paper_id != row['paper_id']:
                    raise MvpError('preparation_integrity', 'A staged source failed its hash or identity check; it was not reused.')
                sources.append(source)
            return sources

    @staticmethod
    def _publication_binding(result, captured):
        return result['search_id'] == captured.search_id

    def publication_guard(self, job):
        def guard(db, result, replayed):
            row = self._row(db, job['workspace_id'], job['id'])
            if replayed and row['status'] == 'succeeded' and row['result_preparation_id'] == result['id']:
                return
            row = self._attempt(db, job)
            captured = self.input(row)
            if (result['selected_paper_ids'] != captured.paper_ids or not self._publication_binding(result, captured)
                    or result['source_revision'] != captured.expected_source_revision + 1
                    or row['progress_completed'] != row['progress_total']):
                raise MvpError('preparation_integrity', 'Preparation publication did not match its captured input and completed stages.')
            staged = db.execute(f'SELECT paper_id,payload_sha256 FROM {self.stage_table} WHERE job_id=? ORDER BY ordinal', (job['id'],)).fetchall()
            actual = [(source['paper_id'], digest(source)) for source in result['sources']]
            if actual != [(item['paper_id'], item['payload_sha256']) for item in staged]:
                raise MvpError('preparation_integrity', 'Preparation publication differs from its validated staged sources.')
            # The final checkpoint can precede a lifecycle/workspace-lock wait
            # and result encoding. Charge that active interval at the actual
            # publication boundary, inside the same research transaction.
            timestamp = now()
            try:
                updated = datetime.fromisoformat(row['updated_at'])
                current = datetime.fromisoformat(timestamp)
                if updated.tzinfo is None or current.tzinfo is None:
                    raise ValueError()
                final_elapsed = row['elapsed_seconds'] + max(0., (current - updated).total_seconds())
            except (TypeError, ValueError):
                raise MvpError('preparation_integrity', 'The preparation runtime receipt is invalid.') from None
            if final_elapsed >= row['max_runtime_seconds']:
                raise MvpError('preparation_runtime_limit', 'The bounded preparation runtime expired before publication. Previously current sources are unchanged.')
            if row['lease_expires'] <= timestamp:
                raise MvpError('preparation_attempt_lost', 'This preparation lease expired before publication and cannot publish.')
            db.execute(f"UPDATE {self.job_table} SET status='succeeded',result_preparation_id=?,result_source_revision=?,elapsed_seconds=?,active_paper_id=NULL,lease_owner=NULL,lease_expires=NULL,error_json=NULL,updated_at=? WHERE id=?",
                (result['id'], result['source_revision'], final_elapsed, timestamp, job['id']))
            self._limits(db, row['workspace_id'])
        return guard

    def finish_failure(self, job, error):
        with self.transaction() as db:
            row = db.execute(f'SELECT * FROM {self.job_table} WHERE workspace_id=? AND id=?', (job['workspace_id'], job['id'])).fetchone()
            if row is None or row['status'] in _TERMINAL or row['attempt'] != job['attempt'] or row['lease_owner'] != job['lease_owner']:
                return
            status = 'cancelled' if row['status'] == 'cancel_requested' or error.code == 'preparation_cancelled' else (
                'stale' if error.code in {'stale_source_revision', 'stale_preparation', 'stale_preparation_job', 'preparation_stale_inputs', 'stale_collection_inputs'} else 'failed')
            safe = StructuredError(code=str(error.code)[:120], message=str(error.message)[:1000], retryable=False)
            db.execute(f'UPDATE {self.job_table} SET status=?,error_json=?,lease_owner=NULL,lease_expires=NULL,active_paper_id=NULL,updated_at=? WHERE id=?',
                       (status, safe.model_dump_json(), now(), job['id']))

    def delete_workspace(self, workspace_id):
        with self.transaction() as db:
            db.execute(f'DELETE FROM {self.job_table} WHERE workspace_id=?', (workspace_id,))
