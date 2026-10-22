"""Planning provenance for new audit wrappers; legacy schemas remain unchanged."""
from .adapters.search_plan_storage import MAX_PLAN_RECORD_BYTES, decoded


def has_search_plans(storage, workspace_id):
    with storage._connection() as db:
        present = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mvp_search_plans'").fetchone()
        return bool(present and db.execute('SELECT 1 FROM mvp_search_plans WHERE workspace_id=? LIMIT 1', (workspace_id,)).fetchone())


def planning_audit(db, workspace_id, charge):
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mvp_search_plans'").fetchone() is None:
        return None
    plans = db.execute('SELECT id,head_revision_id FROM mvp_search_plans WHERE workspace_id=? ORDER BY created_at,id', (workspace_id,)).fetchall()
    if not plans:
        return None
    output = []
    for plan in plans:
        revisions = [charge(decoded(row)) for row in db.execute('SELECT CASE WHEN length(CAST(payload AS BLOB))<=? THEN payload ELSE NULL END AS payload,sha256 FROM mvp_search_plan_revisions WHERE workspace_id=? AND plan_id=? ORDER BY revision', (MAX_PLAN_RECORD_BYTES, workspace_id, plan['id']))]
        events = [charge({'kind': row['kind'], 'receipt': decoded(row)}) for row in db.execute('SELECT kind,CASE WHEN length(CAST(payload AS BLOB))<=? THEN payload ELSE NULL END AS payload,sha256 FROM mvp_search_plan_events WHERE workspace_id=? AND plan_id=? ORDER BY created_at,id', (MAX_PLAN_RECORD_BYTES, workspace_id, plan['id']))]
        output.append({'plan_id': plan['id'], 'current_revision_id': plan['head_revision_id'], 'revisions': revisions, 'receipts': events})
    operations = []
    for row in db.execute('SELECT operation,request_id,fingerprint,status,outcome,created_at,updated_at FROM mvp_search_plan_requests WHERE workspace_id=? ORDER BY created_at,operation,request_id', (workspace_id,)):
        operations.append(charge(dict(row)))
    return {'schema_version': 'mvp.search-planning-audit.v2', 'plans': output, 'operations': operations,
        'limitations': ['Pending call outcomes are unknown after interruption and are not automatically repeated.',
            'Failed model calls may have unmeasured usage; absence of a successful proposal is not evidence of zero computation.']}
