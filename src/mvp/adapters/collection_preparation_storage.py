"""Genuine collection-bound queue tables sharing existing preparation safety."""
import json

from ..collection_contracts import CollectionInputRef
from ..collection_preparation_contracts import (
    CollectionPreparationInput, CollectionPreparationJobListing,
    CollectionPreparationJobView, CollectionPreparationSubmission,
)
from ..contracts import StructuredError, canonical, digest, new_id, now
from ..ports import MvpError
from ..preparation_contracts import MAX_PREPARATION_INPUT_BYTES, PreparationPaperOutcome
from .preparation_storage import PreparationStore


class CollectionPreparationStore(PreparationStore):
    job_table = 'collection_preparation_jobs'
    request_table = 'collection_preparation_requests'
    stage_table = 'collection_preparation_stages'
    filter_column = 'collection_id'
    submission_model = CollectionPreparationSubmission
    listing_model = CollectionPreparationJobListing

    def _initialize(self):
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS collection_preparation_jobs(
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL,
                    mode TEXT NOT NULL, collection_id TEXT NOT NULL,
                    collection_snapshot_sha256 TEXT NOT NULL, selected_json TEXT NOT NULL,
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
                CREATE TABLE IF NOT EXISTS collection_preparation_requests(
                    workspace_id TEXT NOT NULL, request_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    job_id TEXT NOT NULL, PRIMARY KEY(workspace_id,request_id),
                    FOREIGN KEY(workspace_id) REFERENCES mvp_workspaces(id) ON DELETE CASCADE,
                    FOREIGN KEY(job_id) REFERENCES collection_preparation_jobs(id) ON DELETE CASCADE);
                CREATE TABLE IF NOT EXISTS collection_preparation_stages(
                    workspace_id TEXT NOT NULL, job_id TEXT NOT NULL, paper_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL, payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
                    outcome_json TEXT NOT NULL, PRIMARY KEY(job_id,paper_id),
                    FOREIGN KEY(workspace_id) REFERENCES mvp_workspaces(id) ON DELETE CASCADE,
                    FOREIGN KEY(job_id) REFERENCES collection_preparation_jobs(id) ON DELETE CASCADE);
                CREATE INDEX IF NOT EXISTS collection_preparation_jobs_queue
                    ON collection_preparation_jobs(status,created_at,id);
            ''')

    @staticmethod
    def input(job):
        captured = CollectionPreparationInput.model_validate_json(job['input_json'])
        if digest(captured.model_dump(mode='json')) != job['input_sha256']:
            raise MvpError('preparation_integrity', 'The retained collection preparation input failed its integrity check.')
        if (captured.paper_ids != json.loads(job['selected_json'])
                or captured.collection_ref.collection_id != job['collection_id']
                or captured.collection_ref.collection_snapshot_sha256 != job['collection_snapshot_sha256']
                or captured.mode != job['mode']
                or captured.expected_source_revision != job['expected_source_revision']
                or captured.expected_preparation_id != job['expected_preparation_id']
                or len(captured.paper_ids) != job['progress_total']):
            raise MvpError('preparation_integrity', 'The retained collection preparation identities changed.')
        return captured

    def view(self, db, row):
        ids = json.loads(row['selected_json'])
        completed = {r['paper_id']: PreparationPaperOutcome.model_validate_json(r['outcome_json']) for r in db.execute(
            f'SELECT paper_id,outcome_json FROM {self.stage_table} WHERE job_id=? ORDER BY ordinal', (row['id'],))}
        outcomes = []
        for position, identifier in enumerate(ids, 1):
            fallback = 'cancelled' if row['status'] == 'cancelled' else ('preparing' if row['active_paper_id'] == identifier and row['status'] in {'running', 'cancel_requested'} else 'pending')
            outcomes.append(completed.get(identifier) or PreparationPaperOutcome(paper_id=identifier, position=position, outcome=fallback))
        values = {name: row[name] for name in CollectionPreparationJobView.model_fields
                  if name not in {'schema_version', 'collection_ref', 'selected_paper_ids', 'error', 'outcomes'}}
        return CollectionPreparationJobView(**values, selected_paper_ids=ids, outcomes=outcomes,
            collection_ref=CollectionInputRef(collection_id=row['collection_id'], collection_snapshot_sha256=row['collection_snapshot_sha256']),
            error=StructuredError.model_validate_json(row['error_json']) if row['error_json'] else None)

    def submit(self, workspace_id, request_id, fingerprint, captured: CollectionPreparationInput):
        encoded = captured.model_dump_json()
        if len(encoded.encode('utf-8')) > MAX_PREPARATION_INPUT_BYTES:
            raise MvpError('preparation_input_limit', 'The selected collection metadata exceeds the bounded preparation input limit.')
        identifier, timestamp = new_id(), now()
        with self.transaction() as db:
            prior = db.execute(f'SELECT * FROM {self.request_table} WHERE workspace_id=? AND request_id=?', (workspace_id, request_id)).fetchone()
            if prior:
                if prior['fingerprint'] != fingerprint:
                    raise MvpError('idempotency_conflict', 'This preparation request key was already used with different input.')
                return CollectionPreparationSubmission(job=self.view(db, self._row(db, workspace_id, prior['job_id'])), reused=True)
            db.execute('''INSERT INTO collection_preparation_jobs(id,workspace_id,mode,collection_id,collection_snapshot_sha256,
                selected_json,input_json,input_sha256,expected_source_revision,expected_preparation_id,status,max_attempts,
                progress_total,max_runtime_seconds,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,'queued',?,?,?,?,?)''',
                (identifier, workspace_id, captured.mode, captured.collection_ref.collection_id,
                 captured.collection_ref.collection_snapshot_sha256, canonical(captured.paper_ids), encoded,
                 digest(captured.model_dump(mode='json')), captured.expected_source_revision, captured.expected_preparation_id,
                 self.max_attempts, len(captured.paper_ids), self.max_runtime_seconds, timestamp, timestamp))
            db.execute('INSERT INTO collection_preparation_requests VALUES(?,?,?,?)', (workspace_id, request_id, fingerprint, identifier))
            self._limits(db, workspace_id)
            return CollectionPreparationSubmission(job=self.view(db, self._row(db, workspace_id, identifier)))

    def listing(self, workspace_id, collection_id=None):
        return super().listing(workspace_id, collection_id)

    @staticmethod
    def _publication_binding(result, captured):
        return (result.get('schema_version') == 'mvp.collection-preparation.v2'
                and result.get('search_id') is None
                and result.get('collection_ref') == captured.collection_ref.model_dump(mode='json'))
