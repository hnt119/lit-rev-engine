"""Independent optional-proposal checks over retained synthetic sources.

Every generation result is an explicit mock; sockets are denied. These checks
test state/integrity boundaries, not model quality, entailment or usefulness.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import csv
import io
import json
import socket
import sqlite3

import pytest

from test_boards_independent import board_case, _draft, _submit
from src.mvp.board_contracts import BoardCellData, BoardFieldInput, BoardReviseRequest
from src.mvp.contracts import PrepareSourcesRequest, SearchRequest, digest
from src.mvp.ports import MvpError
from src.mvp.proposal_contracts import (
    ProposalAdoptRequest, ProposalDismissRequest, ProposalGenerateRequest,
    ProposalGenerationResult, ProposalPacket, ProposalUsage,
)


MODE = "saved_example"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Independent proposal check attempted network access")
    monkeypatch.setattr(socket, "create_connection", denied)


def valid_output(packet):
    """Deliberately non-entailing value: exactness must not certify support."""
    by_id = {item.evidence_id: item for item in packet.evidence}
    cells = []
    for field in packet.fields:
        allowed = field.evidence_ids
        if allowed:
            quote = by_id[allowed[0]].reference.quote
            cells.append({"field_id": field.field_id,
                "value": "SYNTHETIC claim not established by this quotation",
                "references": [{"evidence_id": allowed[0], "quote": quote}],
                "reason": "Software-only mock; requires actual researcher review",
                "missing_information": "", "context_scope": "retrieved_context_only"})
        else:
            cells.append({"field_id": field.field_id, "value": None, "references": [],
                "reason": "The bounded retrieved context provides no usable evidence",
                "missing_information": "Information unavailable in the provided retrieved context",
                "context_scope": "retrieved_context_only"})
    return {"cells": cells}


class MockGenerator:
    enabled = True
    profile = {"provider": "synthetic-software-mock", "model": "mock", "revision": "v1"}

    def __init__(self, change=None):
        self.change = change
        self.calls = []

    def generate(self, packet, *, timeout_seconds):
        self.calls.append((packet, timeout_seconds))
        output = valid_output(packet)
        if self.change:
            changed = self.change(packet, output)
            if changed is not None:
                output = changed
        text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
        return ProposalGenerationResult(output_text=text,
            usage=ProposalUsage(input_tokens=13, output_tokens=11, total_tokens=24, measured=True))


class DelayedGenerator(MockGenerator):
    def __init__(self):
        super().__init__()
        self.started, self.finish = Event(), Event()

    def generate(self, packet, *, timeout_seconds):
        self.started.set()
        assert self.finish.wait(5), "Independent test did not release delayed mock"
        return super().generate(packet, timeout_seconds=timeout_seconds)


@pytest.fixture
def proposal_case(board_case):
    from src.mvp.cell_proposals import CellProposalService
    case = board_case
    case.generator = MockGenerator()
    case.proposals = CellProposalService(case.boards, case.generator)
    case.generation_request = ProposalGenerateRequest(request_id="proposal-run",
        expected_revision_id=case.definition.revision_id,
        paper_ids=case.definition.paper_ids[:1], field_ids=["diversity"])
    return case


def generate(case, request=None):
    return case.proposals.generate(MODE, case.handle, case.definition.board_id,
                                  request or case.generation_request)


def listing(case, **kwargs):
    return case.proposals.listing(MODE, case.handle, case.definition.board_id,
        revision_id=case.definition.revision_id, **kwargs)


def adoption(case, proposal, *, version=0, head=None, value="Edited software-only value"):
    return case.proposals.adopt(MODE, case.handle, case.definition.board_id, proposal.id,
        ProposalAdoptRequest(request_id="adopt-" + proposal.id,
            expected_revision_id=case.definition.revision_id, draft_version=version,
            expected_cell_head_id=head, value=value,
            reason="Edited by the software walkthrough; unassessed",
            missing_information="Not supplied in bounded context" if value is None else ""))


def assert_no_proposals_or_submission(case):
    assert listing(case).items == []
    view = case.boards.view(MODE, case.handle, case.definition.board_id)
    assert all(cell.head is None for cell in view.cells)


def test_disabled_by_default_never_retrieves_or_calls_and_keeps_manual_board(proposal_case):
    from src.mvp.cell_proposals import CellProposalService
    case = proposal_case
    disabled = CellProposalService(case.boards)
    assert disabled.capabilities().enabled is False
    before = case.boards.view(MODE, case.handle, case.definition.board_id)
    with case.store.connection() as db:
        candidates_before = db.execute("SELECT COUNT(*) FROM board_candidates").fetchone()[0]
    with pytest.raises(MvpError):
        disabled.generate(MODE, case.handle, case.definition.board_id, case.generation_request)
    assert case.generator.calls == []
    assert case.boards.view(MODE, case.handle, case.definition.board_id) == before
    with case.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM board_candidates").fetchone()[0] == candidates_before


def test_generation_is_additive_and_nonentailing_exact_quotes_remain_unassessed(proposal_case):
    case = proposal_case
    before = case.engine.get_workspace(case.handle).model_dump(mode="json")
    old_board_export = case.boards.export(MODE, case.handle, case.definition.board_id)
    old_engine_export = case.engine.export_workspace(case.handle)
    run = generate(case)
    assert run.state == "succeeded" and len(run.proposals) == 1
    proposal = run.proposals[0]
    assert proposal.semantic_assessment == "unassessed"
    assert proposal.review_state == "ai_suggestion_needs_review_not_independently_verified"
    assert proposal.context_scope == "retrieved_context_only"
    assert proposal.status == "pending" and proposal.producer == "ai_proposal"
    assert proposal.board_revision_id == case.definition.revision_id
    assert proposal.field_revision_id == next(f.revision_id for f in case.definition.fields if f.id == "diversity")
    assert proposal.source_manifest_sha256 == case.definition.source_manifest_sha256
    assert proposal.retrieval_input_sha256 and proposal.packet_sha256 and proposal.prompt_version
    assert proposal.model_profile_sha256 == digest(proposal.model_profile)
    assert proposal.references and all(ref.paper_id == proposal.paper_id for ref in proposal.references)
    context = case.proposals.context(MODE, case.handle, case.definition.board_id,
                                     proposal.id, proposal.references[0].id)
    assert context.reference == proposal.references[0]
    assert context.reference.integrity == "checked"
    assert context.block.text[context.reference.start-context.block.start:
                              context.reference.end-context.block.start] == context.reference.quote
    assert case.engine.get_workspace(case.handle).model_dump(mode="json") == before
    view = case.boards.view(MODE, case.handle, case.definition.board_id)
    assert all(cell.head is None and cell.draft_version == 0 for cell in view.cells)
    after_board = case.boards.export(MODE, case.handle, case.definition.board_id)
    before_audit, after_audit = json.loads(old_board_export.json_text), json.loads(after_board.json_text)
    # Existing board audit includes retrieval audit, but its schema and submitted
    # table/history do not turn proposals into accepted evidence.
    assert before_audit["schema_version"] == after_audit["schema_version"] == "mvp.board-audit.v1"
    assert before_audit["table"] == after_audit["table"]
    assert before_audit["cell_revisions"] == after_audit["cell_revisions"] == []
    assert after_board.csv_text == old_board_export.csv_text
    legacy_after = case.engine.export_workspace(case.handle)
    assert legacy_after.csv_text == old_engine_export.csv_text
    assert {k: v for k, v in json.loads(legacy_after.json_text).items() if k != "exported_at"} == {
        k: v for k, v in json.loads(old_engine_export.json_text).items() if k != "exported_at"}


def test_packet_reuses_individual_cell_candidates_and_deduplicates_shared_anchors(proposal_case):
    case = proposal_case
    run = generate(case, case.generation_request.model_copy(update={"field_ids": ["diversity", "fertility"]}))
    assert run.state == "succeeded" and len(case.generator.calls) == 1
    packet = run.packets[0]
    assert len(packet.fields) == 2 and packet.evidence
    assert len(packet.evidence) < sum(len(field.evidence_ids) for field in packet.fields)
    assert packet.fields[0].evidence_ids == packet.fields[1].evidence_ids
    assert packet.evidence_characters == sum(len(item.reference.quote) for item in packet.evidence)
    assert all(set(item.field_ids) == {"diversity", "fertility"} for item in packet.evidence)
    assert len({(item.reference.block_id, item.reference.start, item.reference.end)
                for item in packet.evidence}) == len(packet.evidence)
    with case.store.connection() as db:
        rows = list(db.execute("SELECT payload FROM board_candidates"))
    assert len(rows) == 2
    candidates = [json.loads(row[0]) for row in rows]
    assert {item["field_id"] for item in candidates} == {"diversity", "fertility"}
    assert all(item["paper_id"] == packet.paper_id and item["retrieval_profile"] == case.definition.retrieval_profile
               for item in candidates)


def test_idempotent_replay_still_checks_canonical_source_integrity(proposal_case):
    case = proposal_case
    run = generate(case)
    assert run.state == "succeeded" and len(case.generator.calls) == 1
    with sqlite3.connect(case.root / "research.sqlite3") as db:
        snapshot = json.loads(db.execute("SELECT snapshot FROM mvp_workspaces WHERE id=?",
                                        (case.handle.workspace_id,)).fetchone()[0])
        snapshot["preparations"][0]["sources"][0]["blocks"][0]["text"] = "Changed after generation"
        db.execute("UPDATE mvp_workspaces SET snapshot=? WHERE id=?", (json.dumps(snapshot), case.handle.workspace_id))
    for operation in [lambda: generate(case), lambda: listing(case),
        lambda: case.proposals.context(MODE, case.handle, case.definition.board_id,
                                        run.proposals[0].id, run.proposals[0].references[0].id)]:
        with pytest.raises(MvpError): operation()
    assert len(case.generator.calls) == 1


def test_three_source_types_allow_null_without_inventing_whole_paper_absence(proposal_case):
    case = proposal_case
    request = case.generation_request.model_copy(update={"paper_ids": case.definition.paper_ids,
                                                       "field_ids": ["diversity", "fertility", "diet"]})
    run = generate(case, request)
    assert run.state == "succeeded" and len(run.proposals) == 9
    assert [packet.source_type for packet in run.packets] == ["full_text", "abstract", "none"]
    unavailable = [p for p in run.proposals if p.paper_id == case.definition.paper_ids[2]]
    assert len(unavailable) == 3
    assert all(p.value is None and p.missing_information and not p.references for p in unavailable)
    assert all(p.context_scope == "retrieved_context_only" for p in run.proposals)
    assert all(p.semantic_assessment == "unassessed" for p in run.proposals)
    assert len(case.generator.calls) <= 3
    assert all(0 < timeout <= 35 for _, timeout in case.generator.calls)


@pytest.mark.parametrize("kind", ["unknown_evidence", "mismatching_quote", "ambiguous_quote", "unknown_field",
    "duplicate_field", "missing_field", "extra_key", "null_without_missing", "blank_value",
    "malformed_json", "duplicate_json_key", "nonfinite", "oversized"])
def test_invalid_model_output_is_atomic_and_audited_without_accepting_values(proposal_case, kind):
    case = proposal_case
    def change(packet, output):
        cell = output["cells"][0]
        if kind == "unknown_evidence": cell["references"][0]["evidence_id"] = "unknown"
        elif kind == "mismatching_quote": cell["references"][0]["quote"] = "fabricated quotation"
        elif kind == "ambiguous_quote":
            quote = cell["references"][0]["quote"]
            repeated = next(char for char in quote if not char.isspace() and quote.count(char) > 1)
            cell["references"][0]["quote"] = repeated
        elif kind == "unknown_field": cell["field_id"] = "not-selected"
        elif kind == "duplicate_field": output["cells"].append(dict(cell))
        elif kind == "missing_field": output["cells"] = []
        elif kind == "extra_key": cell["independently_verified"] = True
        elif kind == "null_without_missing": cell.update(value=None, references=[], missing_information="")
        elif kind == "blank_value": cell["value"] = "  "
        elif kind == "malformed_json": return "```json\n{\"cells\":[]}\n```"
        elif kind == "duplicate_json_key": return '{"cells":[],"cells":' + json.dumps(output["cells"]) + '}'
        elif kind == "nonfinite": return json.dumps(output)[:-1] + ',"x":NaN}'
        elif kind == "oversized": return " " * 32769
        return output
    case.generator.change = change
    run = generate(case)
    assert run.state == "failed" and run.failure_code and run.proposals == []
    assert len(case.generator.calls) == 1
    assert run.calls and run.calls[0].usage.measured is True
    assert_no_proposals_or_submission(case)
    assert generate(case) == run
    assert len(case.generator.calls) == 1  # Explicit new key required; no paid retry.


def test_wrong_paper_evidence_cannot_be_used_by_a_later_paper(proposal_case):
    case = proposal_case
    first = {}
    def change(packet, output):
        if not first:
            first.update(output["cells"][0]["references"][0])
        elif output["cells"][0]["references"]:
            output["cells"][0]["references"] = [dict(first)]
        return output
    case.generator.change = change
    request = case.generation_request.model_copy(update={"paper_ids": case.definition.paper_ids[:2], "field_ids": ["diet"]})
    run = generate(case, request)
    assert run.state == "failed" and run.proposals == []
    assert len(case.generator.calls) == 2
    assert_no_proposals_or_submission(case)


def test_evidence_returned_for_another_field_is_not_a_valid_field_reference(proposal_case):
    case = proposal_case
    def change(packet, output):
        field_diet = next(field for field in packet.fields if field.field_id == "diet")
        field_diversity = next(field for field in packet.fields if field.field_id == "diversity")
        wrong_ids = set(field_diet.evidence_ids) - set(field_diversity.evidence_ids)
        assert wrong_ids, "Synthetic fixture must have distinct diet-only candidate evidence"
        wrong = next(item for item in packet.evidence if item.evidence_id in wrong_ids)
        next(cell for cell in output["cells"] if cell["field_id"] == "diversity")["references"] = [
            {"evidence_id": wrong.evidence_id, "quote": wrong.reference.quote}]
        return output
    case.generator.change = change
    run = generate(case, case.generation_request.model_copy(update={"field_ids": ["diet", "diversity"]}))
    assert run.state == "failed" and run.proposals == []
    assert_no_proposals_or_submission(case)


def test_unicode_subquote_is_reconstructed_at_exact_canonical_offsets(proposal_case):
    case = proposal_case
    def change(packet, output):
        cell = output["cells"][0]
        cell["references"][0]["quote"] = "😀 中文"
        return output
    case.generator.change = change
    proposal = generate(case).proposals[0]
    reference = proposal.references[0]
    source = next(source for source in case.prep.sources if source.paper_id == proposal.paper_id)
    block = next(block for block in source.blocks if block.id == reference.block_id)
    assert reference.quote == "😀 中文"
    assert reference.start == block.text.index("😀 中文")
    assert block.text[reference.start:reference.end] == reference.quote


def test_overlapping_exact_occurrences_are_ambiguous_not_unique(proposal_case):
    case = proposal_case
    # Python str.count('aaa') in 'aaaa' is one, but canonical offsets 0 and 1
    # are both valid exact anchors. The server must refuse that ambiguity.
    case.provider.papers[0] = case.provider.papers[0].model_copy(
        update={"abstract": "aaaa microbial diversity in women."})
    search = case.engine.search_literature(case.handle,
        SearchRequest(request_id="overlap-search", query="synthetic fixture"))
    case.prep = case.engine.prepare_sources(case.handle, PrepareSourcesRequest(request_id="overlap-prepare",
        search_id=search.id, paper_ids=[paper.id for paper in search.papers]))
    case.view = case.boards.create(MODE, case.handle,
        case.request.model_copy(update={"request_id": "overlap-board", "preparation_id": case.prep.id}))
    case.definition = case.view.definition
    case.generation_request = case.generation_request.model_copy(
        update={"expected_revision_id": case.definition.revision_id})
    def change(packet, output):
        output["cells"][0]["references"][0]["quote"] = "aaa"
        return output
    case.generator.change = change
    run = generate(case)
    assert run.state == "failed" and run.proposals == []


def test_provider_failure_persists_unknown_usage_and_no_implicit_retry(proposal_case):
    case = proposal_case
    def failed(packet, output):
        raise MvpError("proposal_provider_failure", "Synthetic provider failure")
    case.generator.change = failed
    run = generate(case)
    assert run.state == "failed" and run.proposals == [] and run.failure_code
    assert len(case.generator.calls) == 1
    assert run.calls[0].usage.input_tokens is None
    assert run.calls[0].usage.output_tokens is None
    assert run.calls[0].usage.cost_usd is None
    assert run.calls[0].usage.measured is False
    assert generate(case) == run
    assert len(case.generator.calls) == 1


@pytest.mark.parametrize("outcome,expected", [
    ("success", None), ("malformed", "proposal_invalid_output"),
    ("timeout", "proposal_timeout"), ("provider", "proposal_provider_failure"),
])
def test_configured_http_adapter_integrates_with_service_deadlines_and_error_types(proposal_case, outcome, expected):
    """The real adapter is exercised, with the HTTP transport mocked locally."""
    from src.mvp.adapters.cell_generation import ConfiguredCellGenerationAdapter
    from src.mvp.cell_proposals import CellProposalService
    case = proposal_case
    connections = []
    class FakeSocket:
        def settimeout(self, timeout): assert 0 < timeout <= 10
        def shutdown(self, how): pass
        def close(self): pass
    class FakeResponse:
        status = 500 if outcome == "provider" else 200
        def __init__(self, payload): self.payload = payload
        def getheader(self, name, default=None): return default
        def read1(self, limit):
            result, self.payload = self.payload[:limit], self.payload[limit:]
            return result
    class FakeConnection:
        def __init__(self, host, port, *, timeout):
            assert host == "127.0.0.1" and port == 19998 and 0 < timeout <= 10
            self.sock, self.closed, self.requests = FakeSocket(), False, []
            connections.append(self)
        def request(self, method, path, *, body, headers):
            if outcome == "timeout": raise TimeoutError("Synthetic transport timeout")
            data = json.loads(body)
            self.requests.append(data)
            packet = ProposalPacket.model_validate(json.loads(data["messages"][1]["content"]))
            output = "{" if outcome == "malformed" else json.dumps(valid_output(packet))
            self.payload = json.dumps({"model": "configured-mock", "choices": [{"finish_reason": "stop",
                "message": {"role": "assistant", "content": output}}],
                "usage": {"prompt_tokens": 17, "completion_tokens": 5, "total_tokens": 22}}).encode()
        def getresponse(self): return FakeResponse(self.payload)
        def close(self): self.closed = True
    adapter = ConfiguredCellGenerationAdapter(enabled=True,
        url="http://127.0.0.1:19998/v1/chat/completions", model="configured-mock",
        model_revision="configured-synthetic-revision", _connection_factory=FakeConnection)
    case.proposals = CellProposalService(case.boards, adapter)
    run = generate(case)
    assert len(connections) == 1 and connections[0].closed
    assert run.failure_code == expected
    assert run.state == ("succeeded" if expected is None else "failed")
    if expected is None:
        assert run.calls[0].usage.total_tokens == 22
        request = connections[0].requests[0]
        assert "tools" not in request and "tool_choice" not in request
    else:
        assert run.proposals == []
        assert run.calls[0].outcome == ("timeout" if outcome == "timeout" else
            "invalid_output" if outcome == "malformed" else "provider_failure")


def test_timeout_never_publishes_late_and_blocks_orphaned_call_overlap(proposal_case):
    from src.mvp.cell_proposals import CellProposalService
    case = proposal_case
    finished = Event()
    class TimeoutGenerator(DelayedGenerator):
        def generate(self, packet, *, timeout_seconds):
            try: return super().generate(packet, timeout_seconds=timeout_seconds)
            finally: finished.set()
    delayed = TimeoutGenerator()
    case.proposals = CellProposalService(case.boards, delayed, max_runtime_seconds=0.05)
    try:
        run = generate(case)
        assert run.state == "failed" and run.failure_code == "proposal_timeout"
        assert run.calls[0].outcome == "timeout" and run.proposals == []
        assert delayed.started.is_set() and not finished.is_set()
        with pytest.raises(MvpError) as failure:
            generate(case, case.generation_request.model_copy(update={"request_id": "would-overlap"}))
        assert failure.value.code == "proposal_busy"
    finally:
        delayed.finish.set()
        assert finished.wait(2)
    assert listing(case).items == []
    stored = case.proposals.get_run(MODE, case.handle, case.definition.board_id, run.id)
    assert stored.state == "failed" and stored.proposals == []


def test_concurrent_duplicate_request_never_calls_twice_and_new_request_is_busy(proposal_case):
    from src.mvp.cell_proposals import CellProposalService
    case = proposal_case
    delayed = DelayedGenerator()
    case.proposals = CellProposalService(case.boards, delayed)
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(generate, case)
        assert delayed.started.wait(2)
        try:
            assert generate(case).state == "running"
            with pytest.raises(MvpError) as failure:
                generate(case, case.generation_request.model_copy(update={"request_id": "competing-request"}))
            assert failure.value.code == "proposal_busy"
        finally:
            delayed.finish.set()
        completed = future.result(timeout=3)
    assert completed.state == "succeeded" and len(delayed.calls) == 1
    assert len(listing(case).items) == 1


def test_failed_and_successful_runs_count_toward_hard_workspace_quota(proposal_case):
    case = proposal_case
    for index in range(20):
        run = generate(case, case.generation_request.model_copy(update={"request_id": f"run-{index}"}))
        assert run.state == "succeeded"
    with pytest.raises(MvpError) as failure:
        generate(case, case.generation_request.model_copy(update={"request_id": "run-over-quota"}))
    assert failure.value.code == "proposal_run_limit" and len(case.generator.calls) == 20


def test_adoption_copies_only_reviewable_draft_then_submission_still_requires_inspection(proposal_case):
    case = proposal_case
    proposal = generate(case).proposals[0]
    draft = adoption(case, proposal)
    assert draft.data.value == "Edited software-only value"
    assert draft.data.references and draft.data.inspected_ranges == []
    assert draft.data.semantic_assessment == "unassessed" and draft.data.scope_result == "not_assessed"
    assert draft.data.producer == "manual"
    with pytest.raises(MvpError):
        _submit(case, draft)  # References have not been declared inspected.
    current = case.boards.get_draft(MODE, case.handle, case.definition.board_id, draft.paper_id, draft.field_id)
    assert current == draft
    assert adoption(case, proposal) == draft  # A retry does not overwrite newer human edits.
    with pytest.raises(MvpError):
        case.proposals.dismiss(MODE, case.handle, case.definition.board_id, proposal.id,
            ProposalDismissRequest(request_id="dismiss-adopted", expected_revision_id=case.definition.revision_id))
    assert listing(case).items[0].status == "adopted"
    assert all(cell.head is None for cell in case.boards.view(MODE, case.handle, case.definition.board_id).cells)


def test_existing_manual_edits_and_submitted_heads_cannot_be_overwritten(proposal_case):
    case = proposal_case
    proposal = generate(case).proposals[0]
    draft = _draft(case, BoardCellData(value="Keep existing researcher edits"))
    with pytest.raises(MvpError):
        adoption(case, proposal, version=draft.version)
    assert case.boards.get_draft(MODE, case.handle, case.definition.board_id, draft.paper_id, draft.field_id) == draft
    head = _submit(case, draft)
    with pytest.raises(MvpError):
        adoption(case, proposal)
    # Explicitly matching the saved head permits a new empty revision draft,
    # while immutable submitted history remains untouched.
    revised = adoption(case, proposal, head=head.id)
    assert revised.expected_cell_head_id == head.id
    assert case.boards.history(MODE, case.handle, case.definition.board_id,
        draft.paper_id, draft.field_id).items == [head]


def test_historical_suggestions_retain_original_context_but_cannot_be_adopted_or_dismissed(proposal_case):
    case = proposal_case
    run = generate(case)
    proposal = run.proposals[0]
    before = case.boards.export(MODE, case.handle, case.definition.board_id)
    revised = case.boards.revise(MODE, case.handle, case.definition.board_id,
        BoardReviseRequest(**case.request.model_dump(exclude={"request_id"}), request_id="new-definition",
                           expected_revision_id=case.definition.revision_id))
    assert revised.definition.parent_revision_id == case.definition.revision_id
    assert listing(case).items[0].id == proposal.id
    context = case.proposals.context(MODE, case.handle, case.definition.board_id, proposal.id, proposal.references[0].id)
    assert context.freshness == "historical" and context.reference == proposal.references[0]
    with pytest.raises(MvpError): adoption(case, proposal)
    with pytest.raises(MvpError):
        case.proposals.dismiss(MODE, case.handle, case.definition.board_id, proposal.id,
            ProposalDismissRequest(request_id="historical-dismiss", expected_revision_id=case.definition.revision_id))
    old = case.boards.export(MODE, case.handle, case.definition.board_id, revision_id=case.definition.revision_id)
    assert [{k: v for k, v in row.items() if k != "freshness"}
            for row in csv.DictReader(io.StringIO(old.csv_text))] == [
        {k: v for k, v in row.items() if k != "freshness"}
        for row in csv.DictReader(io.StringIO(before.csv_text))]
    assert [{k: v for k, v in row.items() if k != "freshness"}
            for row in json.loads(old.json_text)["table"]] == [
        {k: v for k, v in row.items() if k != "freshness"}
        for row in json.loads(before.json_text)["table"]]


def test_dismiss_does_not_write_draft_or_submission_and_persists_across_restart(proposal_case):
    from src.mvp.cell_proposals import CellProposalService
    case = proposal_case
    proposal = generate(case).proposals[0]
    request = ProposalDismissRequest(request_id="dismiss", expected_revision_id=case.definition.revision_id,
                                     reason="Researcher will assess manually")
    dismissed = case.proposals.dismiss(MODE, case.handle, case.definition.board_id, proposal.id, request)
    assert dismissed.status == "dismissed"
    assert case.proposals.dismiss(MODE, case.handle, case.definition.board_id, proposal.id, request) == dismissed
    case.proposals = CellProposalService(case.boards, case.generator)
    assert listing(case).items[0].status == "dismissed"
    with pytest.raises(MvpError):
        adoption(case, proposal)
    audit = case.proposals.export(MODE, case.handle, case.definition.board_id,
                                  revision_id=case.definition.revision_id)
    assert audit.schema_version == "mvp.proposal-audit.v1" and len(audit.events) == 1
    assert audit.events[0].action == "dismissed"
    assert all(cell.head is None and cell.draft_version == 0
               for cell in case.boards.view(MODE, case.handle, case.definition.board_id).cells)


@pytest.mark.parametrize("mutation", ["draft", "head", "definition", "source", "delete"])
def test_slow_generation_releases_locks_and_stale_results_never_publish(proposal_case, mutation):
    from src.mvp.cell_proposals import CellProposalService
    case = proposal_case
    delayed = DelayedGenerator()
    case.proposals = CellProposalService(case.boards, delayed)
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(generate, case)
        assert delayed.started.wait(2), "Mock generation did not begin"
        def mutate():
            if mutation in {"draft", "head"}:
                draft = _draft(case, BoardCellData(value="Keep this concurrent researcher edit"))
                if mutation == "head": _submit(case, draft)
            elif mutation == "definition":
                case.boards.revise(MODE, case.handle, case.definition.board_id,
                    BoardReviseRequest(**case.request.model_dump(exclude={"request_id"}), request_id="new-definition",
                                       expected_revision_id=case.definition.revision_id))
            elif mutation == "source":
                case.engine.prepare_sources(case.handle, PrepareSourcesRequest(request_id="new-preparation",
                    search_id=case.search.id, paper_ids=case.prep.selected_paper_ids))
            elif mutation == "delete":
                case.registry.delete_workspace(case.session["token_hash"], case.handle.workspace_id,
                    lambda mode, handle: case.engine.clear_workspace_if_present(handle), case.boards.delete_workspace)
        mutation_future = pool.submit(mutate)
        try:
            mutation_future.result(timeout=2)  # Must finish while generation is blocked.
        finally:
            delayed.finish.set()
        try:
            result = future.result(timeout=3)
        except MvpError:
            assert mutation == "delete"
        else:
            assert result.state == "failed" and result.proposals == [] and result.failure_code
    if mutation == "delete":
        assert case.registry.is_deleted(case.handle.workspace_id)
        with case.store.connection() as db:
            for table in ("proposal_runs", "cell_proposals", "proposal_events"):
                assert db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0
    else:
        assert listing(case).items == []
