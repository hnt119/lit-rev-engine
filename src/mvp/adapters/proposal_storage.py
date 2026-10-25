"""Proposal-only records in the existing board sidecar and payload budget."""
from ..contracts import digest
from ..proposal_contracts import CellProposal, ProposalRun, ProposalEvent, MAX_PROPOSAL_RUNS
from ..ports import MvpError
from .board_storage import unavailable

class ProposalStore:
    def __init__(self, boards):
        self.boards = boards

    def run(self, db, workspace_id, board_id, run_id):
        row = db.execute('SELECT * FROM proposal_runs WHERE workspace_id=? AND board_id=? AND id=?', (workspace_id, board_id, run_id)).fetchone()
        if row is None:
            raise unavailable('proposal_run')
        return self.boards.decode(row, ProposalRun)

    def prior_run(self, db, workspace_id, board_id, request_id, fingerprint):
        row = db.execute('SELECT * FROM proposal_runs WHERE workspace_id=? AND request_id=?', (workspace_id, request_id)).fetchone()
        if row is None:
            return None
        if row['fingerprint'] != fingerprint or row['board_id'] != board_id:
            raise MvpError('idempotency_conflict', 'This proposal request key was used with different input.')
        return self.boards.decode(row, ProposalRun)

    def reserve(self, db, workspace_id, run, fingerprint):
        if db.execute('SELECT COUNT(*) FROM proposal_runs WHERE workspace_id=?', (workspace_id,)).fetchone()[0] >= MAX_PROPOSAL_RUNS:
            raise MvpError('proposal_run_limit', 'This workspace reached its proposal-run limit. Failed and interrupted runs remain in the audit.')
        db.execute('INSERT INTO proposal_runs(workspace_id,board_id,definition_id,id,request_id,fingerprint,payload,sha256,failure_reserve) VALUES(?,?,?,?,?,?,?,?,?)', (workspace_id, run.board_id, run.board_revision_id, run.id, run.request_id,
                    fingerprint, run.model_dump_json(), digest(run.model_dump(mode='json')), ' ' * 4096))
        self.boards.limits(db, workspace_id)

    def put_run(self, db, workspace_id, run):
        # UPDATE only: deletion can never be repaired by inserting a delayed run.
        changed = db.execute('UPDATE proposal_runs SET payload=?,sha256=?,failure_reserve=? WHERE workspace_id=? AND board_id=? AND id=?',
                             (run.model_dump_json(), digest(run.model_dump(mode='json')), ' ' * 4096 if run.state == 'running' else '', workspace_id, run.board_id, run.id)).rowcount
        if changed != 1:
            raise unavailable('proposal_run')
        self.boards.limits(db, workspace_id)

    def proposal(self, db, workspace_id, board_id, proposal_id):
        row = db.execute('SELECT * FROM cell_proposals WHERE workspace_id=? AND board_id=? AND id=?', (workspace_id, board_id, proposal_id)).fetchone()
        if row is None:
            raise unavailable('cell_proposal')
        return self.with_event(db, workspace_id, self.boards.decode(row, CellProposal))

    def with_event(self, db, workspace_id, proposal):
        row = db.execute('SELECT * FROM proposal_events WHERE workspace_id=? AND proposal_id=? ORDER BY rowid DESC LIMIT 1', (workspace_id, proposal.id)).fetchone()
        if row is None:
            return proposal
        event = self.boards.decode(row, ProposalEvent)
        return proposal.model_copy(update={'status': event.action, 'latest_event': event})

    def add_proposal(self, db, workspace_id, proposal):
        db.execute('INSERT INTO cell_proposals VALUES(?,?,?,?,?,?,?,?,?)', (workspace_id, proposal.board_id, proposal.board_revision_id, proposal.run_id,
            proposal.paper_id, proposal.field_id, proposal.id, proposal.model_dump_json(), digest(proposal.model_dump(mode='json'))))

    def prior_action(self, db, workspace_id, request_id, fingerprint, model):
        row = db.execute('SELECT * FROM proposal_actions WHERE workspace_id=? AND request_id=?', (workspace_id, request_id)).fetchone()
        if row is None:
            return None
        if row['fingerprint'] != fingerprint:
            raise MvpError('idempotency_conflict', 'This proposal action key was used with different input.')
        return model.model_validate_json(row['result'])

    def add_event(self, db, workspace_id, board_id, event, fingerprint, result):
        db.execute('INSERT INTO proposal_events VALUES(?,?,?,?,?,?)', (workspace_id, board_id, event.proposal_id, event.id,
                     event.model_dump_json(), digest(event.model_dump(mode='json'))))
        db.execute('INSERT INTO proposal_actions VALUES(?,?,?,?)', (workspace_id, event.request_id, fingerprint, result.model_dump_json()))
        self.boards.limits(db, workspace_id)
