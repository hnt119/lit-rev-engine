"""Private additive SQLite sidecar; no changes to research snapshots or maps."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3

from ..contracts import canonical, digest
from ..board_contracts import MAX_WORKSPACE_BYTES, MAX_BOARDS, MAX_DEFINITIONS, MAX_CELL_REVISIONS
from ..ports import MvpError
from ..workspace_ui import private_directory


def unavailable(kind='board'):
    return MvpError('unknown_' + kind, 'The requested comparison resource does not belong to this workspace.')


class BoardStore:
    def __init__(self, path, *, max_workspace_bytes=MAX_WORKSPACE_BYTES, max_boards=MAX_BOARDS,
                 max_definitions=MAX_DEFINITIONS, max_cell_revisions=MAX_CELL_REVISIONS, max_requests=1000):
        self.path = Path(path)
        private_directory(self.path.parent)
        if any(Path(str(self.path) + suffix).is_symlink() for suffix in ('', '-wal', '-shm', '-journal')):
            raise ValueError('Board storage must not be a symlink')
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.fchmod(fd, 0o600)
        os.close(fd)
        self.max_workspace_bytes, self.max_boards = max_workspace_bytes, max_boards
        self.max_definitions, self.max_cell_revisions, self.max_requests = max_definitions, max_cell_revisions, max_requests
        with self.connection() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS board_schema(version INTEGER PRIMARY KEY);
              INSERT OR IGNORE INTO board_schema VALUES(1);
              CREATE TABLE IF NOT EXISTS evidence_boards(workspace_id TEXT NOT NULL, board_id TEXT PRIMARY KEY, head_id TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS board_definitions(workspace_id TEXT NOT NULL, board_id TEXT NOT NULL, id TEXT PRIMARY KEY, payload TEXT NOT NULL, sha256 TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS board_cells(workspace_id TEXT NOT NULL, board_id TEXT NOT NULL, definition_id TEXT NOT NULL, paper_id TEXT NOT NULL, field_id TEXT NOT NULL, id TEXT PRIMARY KEY, payload TEXT NOT NULL, sha256 TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS board_heads(workspace_id TEXT NOT NULL, board_id TEXT NOT NULL, definition_id TEXT NOT NULL, paper_id TEXT NOT NULL, field_id TEXT NOT NULL, head_id TEXT NOT NULL, PRIMARY KEY(workspace_id,board_id,definition_id,paper_id,field_id));
              CREATE TABLE IF NOT EXISTS board_drafts(workspace_id TEXT NOT NULL, board_id TEXT NOT NULL, definition_id TEXT NOT NULL, paper_id TEXT NOT NULL, field_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(workspace_id,board_id,definition_id,paper_id,field_id));
              CREATE TABLE IF NOT EXISTS board_candidates(workspace_id TEXT NOT NULL, board_id TEXT NOT NULL, definition_id TEXT NOT NULL, id TEXT PRIMARY KEY, payload TEXT NOT NULL, sha256 TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS board_requests(workspace_id TEXT NOT NULL, request_id TEXT NOT NULL, fingerprint TEXT NOT NULL, result TEXT NOT NULL, PRIMARY KEY(workspace_id,request_id));
              CREATE TABLE IF NOT EXISTS board_deleted(workspace_id TEXT PRIMARY KEY);
              CREATE TABLE IF NOT EXISTS proposal_runs(workspace_id TEXT NOT NULL, board_id TEXT NOT NULL, definition_id TEXT NOT NULL, id TEXT PRIMARY KEY, request_id TEXT NOT NULL, fingerprint TEXT NOT NULL, payload TEXT NOT NULL, sha256 TEXT NOT NULL, failure_reserve TEXT NOT NULL DEFAULT '', UNIQUE(workspace_id,request_id));
              CREATE TABLE IF NOT EXISTS cell_proposals(workspace_id TEXT NOT NULL, board_id TEXT NOT NULL, definition_id TEXT NOT NULL, run_id TEXT NOT NULL, paper_id TEXT NOT NULL, field_id TEXT NOT NULL, id TEXT PRIMARY KEY, payload TEXT NOT NULL, sha256 TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS proposal_events(workspace_id TEXT NOT NULL, board_id TEXT NOT NULL, proposal_id TEXT NOT NULL, id TEXT PRIMARY KEY, payload TEXT NOT NULL, sha256 TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS proposal_actions(workspace_id TEXT NOT NULL, request_id TEXT NOT NULL, fingerprint TEXT NOT NULL, result TEXT NOT NULL, PRIMARY KEY(workspace_id,request_id));
            ''')
            # Only this new checkpoint's table may predate its reserved failure
            # budget. Existing research, board and cell schemas are unchanged.
            if 'failure_reserve' not in {row['name'] for row in db.execute('PRAGMA table_info(proposal_runs)')}:
                db.execute("ALTER TABLE proposal_runs ADD COLUMN failure_reserve TEXT NOT NULL DEFAULT ''")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

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

    def alive(self, db, workspace_id):
        if db.execute('SELECT 1 FROM board_deleted WHERE workspace_id=?', (workspace_id,)).fetchone():
            raise unavailable('workspace')

    @staticmethod
    def decode(row, model):
        result = model.model_validate_json(row['payload'])
        if 'sha256' in row.keys() and digest(result.model_dump(mode='json')) != row['sha256']:
            raise MvpError('board_integrity', 'Saved comparison data failed its integrity check.')
        return result

    def limits(self, db, workspace_id):
        total = 0
        for table in ('evidence_boards', 'board_definitions', 'board_cells', 'board_heads', 'board_drafts', 'board_candidates', 'board_requests', 'proposal_runs', 'cell_proposals', 'proposal_events', 'proposal_actions'):
            for row in db.execute('SELECT * FROM ' + table + ' WHERE workspace_id=?', (workspace_id,)):
                total += sum(len(str(value).encode('utf-8')) for value in row if value is not None) + 256
        if total > self.max_workspace_bytes or db.execute('SELECT COUNT(*) FROM board_requests WHERE workspace_id=?', (workspace_id,)).fetchone()[0] > self.max_requests:
            raise MvpError('board_storage_limit', 'This workspace reached its bounded comparison storage limit. Existing records remain readable.')

    def prior(self, db, workspace_id, request_id, fingerprint, model):
        row = db.execute('SELECT * FROM board_requests WHERE workspace_id=? AND request_id=?', (workspace_id, request_id)).fetchone()
        if row is None:
            return None
        if row['fingerprint'] != fingerprint:
            raise MvpError('idempotency_conflict', 'This comparison request key was used with different input.')
        return model.model_validate_json(row['result'])

    def record_request(self, db, workspace_id, request_id, fingerprint, result):
        db.execute('INSERT INTO board_requests VALUES(?,?,?,?)', (workspace_id, request_id, fingerprint, result.model_dump_json()))
        self.limits(db, workspace_id)

    def board_head(self, db, workspace_id, board_id):
        self.alive(db, workspace_id)
        row = db.execute('SELECT head_id FROM evidence_boards WHERE workspace_id=? AND board_id=?', (workspace_id, board_id)).fetchone()
        if row is None:
            raise unavailable()
        return row[0]

    def definition(self, db, workspace_id, board_id, revision_id=None):
        from ..board_contracts import BoardRevision
        head = self.board_head(db, workspace_id, board_id)
        row = db.execute('SELECT * FROM board_definitions WHERE workspace_id=? AND board_id=? AND id=?', (workspace_id, board_id, revision_id or head)).fetchone()
        if row is None:
            raise unavailable('board_revision')
        return self.decode(row, BoardRevision)

    def add_definition(self, db, definition, *, create=False):
        workspace_id, board_id = definition.workspace_id, definition.board_id
        if create:
            if db.execute('SELECT COUNT(*) FROM evidence_boards WHERE workspace_id=?', (workspace_id,)).fetchone()[0] >= self.max_boards:
                raise MvpError('board_limit', 'This workspace reached its comparison-board limit.')
            db.execute('INSERT INTO evidence_boards VALUES(?,?,?)', (workspace_id, board_id, definition.revision_id))
        if db.execute('SELECT COUNT(*) FROM board_definitions WHERE workspace_id=? AND board_id=?', (workspace_id, board_id)).fetchone()[0] >= self.max_definitions:
            raise MvpError('board_definition_limit', 'This board reached its definition revision limit.')
        db.execute('INSERT INTO board_definitions VALUES(?,?,?,?,?)', (workspace_id, board_id, definition.revision_id, definition.model_dump_json(), digest(definition.model_dump(mode='json'))))
        db.execute('UPDATE evidence_boards SET head_id=? WHERE workspace_id=? AND board_id=?', (definition.revision_id, workspace_id, board_id))

    @staticmethod
    def cell_key(definition, paper_id, field_id):
        return definition.workspace_id, definition.board_id, definition.revision_id, paper_id, field_id

    def cell_head(self, db, definition, paper_id, field_id):
        row = db.execute('SELECT head_id FROM board_heads WHERE workspace_id=? AND board_id=? AND definition_id=? AND paper_id=? AND field_id=?', self.cell_key(definition, paper_id, field_id)).fetchone()
        return row[0] if row else None

    def draft(self, db, definition, paper_id, field_id):
        from ..board_contracts import BoardCellDraft
        row = db.execute('SELECT payload FROM board_drafts WHERE workspace_id=? AND board_id=? AND definition_id=? AND paper_id=? AND field_id=?', self.cell_key(definition, paper_id, field_id)).fetchone()
        return BoardCellDraft.model_validate_json(row[0]) if row else BoardCellDraft(board_id=definition.board_id, board_revision_id=definition.revision_id, paper_id=paper_id, field_id=field_id)

    def put_draft(self, db, definition, draft):
        db.execute('INSERT INTO board_drafts VALUES(?,?,?,?,?,?) ON CONFLICT(workspace_id,board_id,definition_id,paper_id,field_id) DO UPDATE SET payload=excluded.payload', (*self.cell_key(definition, draft.paper_id, draft.field_id), draft.model_dump_json()))
        self.limits(db, definition.workspace_id)

    def add_cell(self, db, definition, cell):
        key = self.cell_key(definition, cell.paper_id, cell.field_id)
        if db.execute('SELECT COUNT(*) FROM board_cells WHERE workspace_id=? AND board_id=? AND definition_id=? AND paper_id=? AND field_id=?', key).fetchone()[0] >= self.max_cell_revisions:
            raise MvpError('board_cell_revision_limit', 'This cell reached its submitted revision limit.')
        db.execute('INSERT INTO board_cells VALUES(?,?,?,?,?,?,?,?)', (*key, cell.id, cell.model_dump_json(), digest(cell.model_dump(mode='json'))))
        db.execute('INSERT INTO board_heads VALUES(?,?,?,?,?,?) ON CONFLICT(workspace_id,board_id,definition_id,paper_id,field_id) DO UPDATE SET head_id=excluded.head_id', (*key, cell.id))
        # Submission consumes the exact acknowledged draft; later revision needs
        # an explicit fresh PUT carrying the new head, never an implicit rebase.
        db.execute('DELETE FROM board_drafts WHERE workspace_id=? AND board_id=? AND definition_id=? AND paper_id=? AND field_id=?', key)

    def delete_workspace(self, workspace_id):
        with self.transaction() as db:
            db.execute('INSERT OR IGNORE INTO board_deleted VALUES(?)', (workspace_id,))
            for table in ('evidence_boards', 'board_definitions', 'board_cells', 'board_heads', 'board_drafts', 'board_candidates', 'board_requests', 'proposal_runs', 'cell_proposals', 'proposal_events', 'proposal_actions'):
                db.execute('DELETE FROM ' + table + ' WHERE workspace_id=?', (workspace_id,))
