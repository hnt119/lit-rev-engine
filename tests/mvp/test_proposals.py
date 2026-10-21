"""Bounded proposal execution and storage checks; all adapters are software mocks."""
import json
from threading import Event
import time

import pytest
from pydantic import ValidationError

from test_boards import case
from src.mvp.cell_proposals import CellProposalService
from src.mvp.contracts import digest
from src.mvp.ports import MvpError
from src.mvp.proposal_contracts import ProposalGenerateRequest, ProposalGenerationResult, ProposalUsage

class Adapter:
    enabled = True
    profile = {'model': 'software-only-mock', 'revision': '1', 'paid_calls': False}
    def __init__(self, behavior=None):
        self.calls = []
        self.behavior = behavior
    def generate(self, packet, *, timeout_seconds):
        self.calls.append((packet, timeout_seconds))
        if self.behavior:
            return self.behavior(packet)
        evidence = {e.evidence_id: e for e in packet.evidence}
        cells = []
        for field in packet.fields:
            refs = [{'evidence_id': field.evidence_ids[0], 'quote': evidence[field.evidence_ids[0]].reference.quote}] if field.evidence_ids else []
            cells.append({'field_id': field.field_id, 'value': 'Software mock value' if refs else None,
                'references': refs, 'reason': 'Software mock, not scientific support',
                'missing_information': '' if refs else 'Not supplied in the retrieved context'})
        return ProposalGenerationResult(output_text=json.dumps({'cells': cells}),
            usage=ProposalUsage(input_tokens=10, output_tokens=20, total_tokens=30, measured=True))

def request(board, key='run', papers=None, fields=None):
    return ProposalGenerateRequest(request_id=key, expected_revision_id=board.definition.revision_id,
        paper_ids=papers or board.definition.paper_ids[:1], field_ids=fields or ['diet'])

def make(case, adapter=None, **kwargs):
    boards, handle, _, _, _, _, board = case
    adapter = adapter or Adapter()
    return CellProposalService(boards, adapter, **kwargs), handle, board, adapter

@pytest.mark.parametrize('papers,fields', [(['a','a'],['a']), (['a'],['a','a']), (['a','b','c'],['a','b','c','d']), (['a','b','c','d'],['a'])])
def test_selection_bounds_are_typed_before_any_generation(papers, fields):
    with pytest.raises(ValidationError):
        ProposalGenerateRequest(request_id='bounded', expected_revision_id='revision', paper_ids=papers, field_ids=fields)

def test_configured_call_receives_per_call_timeout_and_typed_usage(case):
    service, handle, board, adapter = make(case)
    run = service.generate('test', handle, board.definition.board_id, request(board, papers=board.definition.paper_ids, fields=['diet','cohort','methods']))
    assert run.state == 'succeeded' and len(run.proposals) == 9
    assert len(adapter.calls) == 3 and all(0 < seconds <= 10 for _, seconds in adapter.calls)
    assert all(call.usage.measured and call.usage.total_tokens == 30 for call in run.calls)
    assert len({p.packet_sha256 for p in run.proposals}) == 3
    assert len({p.references[0].paper_id for p in run.proposals}) == 3
    assert all(p.model_profile_sha256 == digest(adapter.profile) for p in run.proposals)

def test_packet_deduplicates_same_canonical_evidence_across_fields(case):
    service, handle, board, _ = make(case)
    run = service.generate('test', handle, board.definition.board_id, request(board, fields=['diet','cohort','methods']))
    packet = run.packets[0]
    assert len(packet.evidence) == 1 and len(packet.fields) == 3
    assert len(packet.evidence[0].field_ids) == 3
    assert len({f.evidence_ids[0] for f in packet.fields}) == 1
    assert len({f.candidate_run_id for f in packet.fields}) == 3

def test_second_paper_failure_has_no_partial_publication_or_raw_error(case):
    adapter = Adapter()
    original = adapter.generate
    def generate(packet, *, timeout_seconds):
        if adapter.calls:
            raise RuntimeError('SECRET provider body and private source text')
        return original(packet, timeout_seconds=timeout_seconds)
    adapter.generate = generate
    service, handle, board, _ = make(case, adapter)
    run = service.generate('test', handle, board.definition.board_id, request(board, papers=board.definition.paper_ids[:2]))
    assert run.state == 'failed' and run.proposals == []
    assert run.failure_code == 'proposal_provider_failure' and 'SECRET' not in run.model_dump_json()
    assert [c.outcome for c in run.calls] == ['succeeded','provider_failure']
    assert service.listing('test', handle, board.definition.board_id, board.definition.revision_id).total == 0
    assert service.get_run('test', handle, board.definition.board_id, run.id) == run

def test_timeout_retains_call_lease_and_never_publishes_late_result(case):
    started, finish, completed = Event(), Event(), Event()
    normal = Adapter()
    def delayed(packet):
        started.set()
        finish.wait(2)
        result = normal.generate(packet, timeout_seconds=1)
        completed.set()
        return result
    service, handle, board, adapter = make(case, Adapter(delayed), max_runtime_seconds=0.05)
    before = time.monotonic()
    run = service.generate('test', handle, board.definition.board_id, request(board))
    assert time.monotonic() - before < 1 and started.is_set()
    assert run.state == 'failed' and run.failure_code == 'proposal_timeout'
    with pytest.raises(MvpError) as error:
        service.generate('test', handle, board.definition.board_id, request(board, key='second'))
    assert error.value.code == 'proposal_busy'
    finish.set()
    assert completed.wait(1)
    assert service.get_run('test', handle, board.definition.board_id, run.id).state == 'failed'
    assert service.listing('test', handle, board.definition.board_id, board.definition.revision_id).items == []
    assert len(adapter.calls) == 1

def test_run_limit_counts_failed_attempts_and_idempotency_does_not_retry(case):
    adapter = Adapter(lambda p: ProposalGenerationResult(output_text='malformed'))
    service, handle, board, _ = make(case, adapter)
    for index in range(20):
        attempt = request(board, key='attempt-' + str(index))
        run = service.generate('test', handle, board.definition.board_id, attempt)
        assert run.state == 'failed'
        assert service.generate('test', handle, board.definition.board_id, attempt) == run
    assert len(adapter.calls) == 20
    with pytest.raises(MvpError) as error:
        service.generate('test', handle, board.definition.board_id, request(board, key='over-limit'))
    assert error.value.code == 'proposal_run_limit' and len(adapter.calls) == 20

def test_shared_storage_quota_rejects_reservation_without_provider_call(case):
    service, handle, board, adapter = make(case)
    store = case[3]
    before = case[0].view('test', handle, board.definition.board_id)
    store.max_workspace_bytes = 1
    with pytest.raises(MvpError) as error:
        service.generate('test', handle, board.definition.board_id, request(board))
    assert error.value.code == 'board_storage_limit' and adapter.calls == []
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM proposal_runs').fetchone()[0] == 0
    assert case[0].view('test', handle, board.definition.board_id) == before

def test_normal_list_is_compact_and_failed_runs_reopen_without_auto_retry(case):
    service, handle, board, adapter = make(case)
    run = service.generate('test', handle, board.definition.board_id, request(board))
    listing = service.listing('test', handle, board.definition.board_id, board.definition.revision_id)
    summary = listing.runs[0].model_dump()
    assert 'packets' not in summary and 'proposals' not in summary and 'baselines' not in summary
    assert summary['proposal_count'] == 1
    reopened = CellProposalService(case[0])
    assert reopened.capabilities().enabled is False
    assert reopened.get_run('test', handle, board.definition.board_id, run.id) == run
    assert len(adapter.calls) == 1

def test_provider_output_budget_is_checked_before_publication(case):
    service, handle, board, _ = make(case, Adapter(lambda p: ProposalGenerationResult(output_text='x'*32769)))
    run = service.generate('test', handle, board.definition.board_id, request(board))
    assert run.failure_code == 'proposal_invalid_output' and run.proposals == []
    assert run.calls[0].output_bytes == 32769 and run.calls[0].outcome == 'invalid_output'

def test_packet_quota_failure_keeps_terminal_receipt_and_starts_no_call(case, monkeypatch):
    from src.mvp.adapters import cell_generation
    service, handle, board, adapter = make(case)
    store = case[3]
    build = cell_generation.build_packet
    def set_budget_at_acknowledged_inputs(*args):
        packet = build(*args)
        with store.connection() as db:
            total = 0
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'"):
                table = row[0]
                if 'workspace_id' not in {c['name'] for c in db.execute('PRAGMA table_info(' + table + ')')}:
                    continue
                for record in db.execute('SELECT * FROM ' + table + ' WHERE workspace_id=?', (handle.workspace_id,)):
                    total += sum(len(str(v).encode('utf-8')) for v in record if v is not None) + 256
        store.max_workspace_bytes = total + 100
        return packet
    monkeypatch.setattr(cell_generation, 'build_packet', set_budget_at_acknowledged_inputs)
    run = service.generate('test', handle, board.definition.board_id, request(board))
    assert run.state == 'failed' and run.failure_code == 'proposal_storage_limit'
    assert adapter.calls == [] and run.proposals == []
    reopened = service.get_run('test', handle, board.definition.board_id, run.id)
    assert reopened.state == 'failed' and reopened.failure_code == 'proposal_storage_limit'
    assert reopened.packets == []  # no unacknowledged packet represented as saved input

def test_changed_model_profile_cannot_publish_under_original_profile(case):
    adapter = Adapter()
    normal = adapter.generate
    def changed(packet, *, timeout_seconds):
        result = normal(packet, timeout_seconds=timeout_seconds)
        adapter.profile = {**adapter.profile, 'revision': 'changed-after-reservation'}
        return result
    adapter.generate = changed
    service, handle, board, _ = make(case, adapter)
    run = service.generate('test', handle, board.definition.board_id, request(board))
    assert run.state == 'failed' and run.failure_code == 'proposal_stale_inputs'
    assert run.proposals == [] and run.model_profile['revision'] == '1'

def test_historical_action_replay_returns_original_receipt_without_new_mutation(case):
    from src.mvp.board_contracts import BoardReviseRequest
    from src.mvp.proposal_contracts import ProposalDismissRequest
    service, handle, board, adapter = make(case)
    proposal = service.generate('test', handle, board.definition.board_id, request(board)).proposals[0]
    action = ProposalDismissRequest(request_id='dismiss', expected_revision_id=board.definition.revision_id)
    original = service.dismiss('test', handle, board.definition.board_id, proposal.id, action)
    case[0].revise('test', handle, board.definition.board_id, BoardReviseRequest(**case[5].model_dump(exclude={'request_id'}),
        request_id='new-definition', expected_revision_id=board.definition.revision_id))
    assert service.dismiss('test', handle, board.definition.board_id, proposal.id, action) == original
    with pytest.raises(MvpError) as error:
        service.dismiss('test', handle, board.definition.board_id, proposal.id, action.model_copy(update={'request_id':'new-action'}))
    assert error.value.code == 'stale_board_revision'
    assert len(adapter.calls) == 1
