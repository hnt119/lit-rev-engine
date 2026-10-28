"""Bounded append-only investigation records in the existing research database."""
from .search_plan_storage import SearchPlanStore, packed, decoded
from ..ports import MvpError
from ..investigation_contracts import InvestigationOrigin

TABLES = ('mvp_investigations', 'mvp_investigation_previews', 'mvp_investigation_decisions', 'mvp_investigation_attempts')

def investigation_bytes(db, workspace_id):
    existing = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    total = 0
    for table in TABLES:
        if table in existing:
            total += db.execute(f'SELECT COALESCE(SUM(length(CAST(payload AS BLOB))+1024),0) FROM {table} WHERE workspace_id=?', (workspace_id,)).fetchone()[0]
    return total

def is_investigation_plan(db, workspace_id, plan_id):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mvp_investigations'").fetchone():
        return False
    return bool(db.execute('SELECT 1 FROM mvp_investigations WHERE workspace_id=? AND plan_id=?', (workspace_id, plan_id)).fetchone())

class InvestigationStore(SearchPlanStore):
    def __init__(self, storage):
        super().__init__(storage)
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS mvp_investigations(
                    id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,plan_id TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL,sha256 TEXT NOT NULL,
                    FOREIGN KEY(workspace_id) REFERENCES mvp_workspaces(id) ON DELETE CASCADE,
                    FOREIGN KEY(plan_id) REFERENCES mvp_search_plans(id) ON DELETE CASCADE);
                CREATE TABLE IF NOT EXISTS mvp_investigation_previews(
                    id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,plan_id TEXT NOT NULL,
                    payload TEXT NOT NULL,sha256 TEXT NOT NULL,
                    FOREIGN KEY(workspace_id) REFERENCES mvp_workspaces(id) ON DELETE CASCADE,
                    FOREIGN KEY(plan_id) REFERENCES mvp_search_plans(id) ON DELETE CASCADE);
                CREATE TABLE IF NOT EXISTS mvp_investigation_attempts(
                    id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,plan_id TEXT NOT NULL,
                    operation TEXT NOT NULL,request_id TEXT NOT NULL,payload TEXT NOT NULL,sha256 TEXT NOT NULL,
                    UNIQUE(workspace_id,operation,request_id),
                    FOREIGN KEY(workspace_id) REFERENCES mvp_workspaces(id) ON DELETE CASCADE,
                    FOREIGN KEY(plan_id) REFERENCES mvp_search_plans(id) ON DELETE CASCADE);
                CREATE TABLE IF NOT EXISTS mvp_investigation_decisions(
                    id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,investigation_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,version INTEGER NOT NULL,payload TEXT NOT NULL,sha256 TEXT NOT NULL,
                    UNIQUE(investigation_id,candidate_id,version),
                    FOREIGN KEY(workspace_id) REFERENCES mvp_workspaces(id) ON DELETE CASCADE,
                    FOREIGN KEY(investigation_id) REFERENCES mvp_investigations(id) ON DELETE CASCADE);
            ''')

    def origin(self, db, workspace_id, identifier):
        row = db.execute('SELECT * FROM mvp_investigations WHERE workspace_id=? AND id=?', (workspace_id, identifier)).fetchone()
        if row is None:
            raise MvpError('unknown_investigation', 'This investigation does not belong to this workspace.')
        value = decoded(row, InvestigationOrigin)
        if value.workspace_id != workspace_id or value.id != identifier or value.plan_id != row['plan_id']:
            raise MvpError('investigation_integrity', 'The retained investigation identity changed.')
        return value
