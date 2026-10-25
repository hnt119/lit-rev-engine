"""Independent persistence/authority/race checks; all providers and models are mocks."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import socket
import threading
from types import SimpleNamespace

import pytest

from src.mvp.adapters.search_plan_storage import SearchPlanStore
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.contracts import Paper, SearchPreview, WorkspaceHandle, digest
from src.mvp.ports import MvpError
from src.mvp.search_plan_contracts import (ApproveSearchPlanRequest, CreateSearchPlanRequest,
    DiagnoseSearchPlanRequest, DiagnosticSeed, DiagnosticSeedResult, ExecuteSearchPlanRequest,
    PlanExpression, ProposeSearchPlanRequest, QueryDiagnosticReceipt, SearchConcept, SearchDateFilter,
    SearchPlanDraft, SearchPlanningCapability, SearchPlanningResult, SearchTerm, SearchVariant, UpdateSearchPlanRequest)
from src.mvp.search_plans import SearchPlanService
from src.mvp.service import MVPService

RAW = '  ("gut microbiome"[tiab])\r\n AND women[tiab]  '


class Blockable:
    def __init__(self):
        self.calls, self.block, self.failure, self.transform = [], False, False, None
        self.entered, self.release = threading.Event(), threading.Event()

    def invoked(self, value):
        self.calls.append(value)
        if self.block:
            self.entered.set()
            assert self.release.wait(timeout=6), "Test provider barrier was not released"
        if self.failure:
            raise RuntimeError("PRIVATE_PROVIDER_ERROR_SENTINEL")


class Discovery(Blockable):
    def search(self, request):
        self.invoked(request)
        papers = [Paper(pmid="111", title="SYNTHETIC planned-capture fixture", abstract="Fixture abstract only.")]
        value = SearchPreview(query=request.query, date_from=request.date_from, date_to=request.date_to, sort=request.sort,
            total_reported=100, fetched_count=1, ordered_identifiers=["111", "222"], papers=papers,
            truncated=True, mode="live", provider="mock-discovery-no-live-call")
        return self.transform(value) if self.transform else value

    def prepare(self, paper):
        raise AssertionError("Search planning must not prepare sources")


class Diagnostics(Blockable):
    enabled, reason = True, "MOCK explicit diagnostic; no network"

    def check(self, query, **kwargs):
        self.invoked((query, kwargs))
        preview = kwargs["preview_pmids"]
        seeds = [DiagnosticSeedResult(seed=seed, query_membership="matched" if seed.pmid else "unresolved",
            preview_recovery="not_checked" if preview is None or seed.pmid is None else "present" if seed.pmid in preview else "absent",
            reason="MOCK membership receipt; not a recall measure") for seed in kwargs["seeds"]]
        value = QueryDiagnosticReceipt(query=query, query_sha256=sha256(query.encode()).hexdigest(),
            date_from=kwargs["date_from"], date_to=kwargs["date_to"], sort=kwargs["sort"], status="succeeded",
            reported_count=100, sample_pmids=["111"], truncated_sample=True, calls=1,
            query_translation="MOCK ESearch translation", response_sha256="b" * 64, seed_results=seeds)
        return self.transform(value) if self.transform else value


class Planner(Blockable):
    profile = {"model": "MOCK no model executed", "model_revision": "independent-fixture-v1"}

    def capability(self):
        return SearchPlanningCapability(enabled=True, model_profile=self.profile)

    def propose(self, question, **kwargs):
        self.invoked((question, kwargs))
        group = SearchConcept(id="topic", label="Proposed keyword", role="topic", requirement="required", retrieval_use="query",
            terms=[SearchTerm(id="term", text="keyword", state="proposed", origin="model_proposed")])
        value = SearchPlanningResult(draft=SearchPlanDraft(original_question=question, concepts=[group],
            variants=[SearchVariant(id="focused", label="Proposed", kind="focused", expression=PlanExpression(op="concept_ref", concept_id="topic"))]),
            question_sha256=sha256(question.encode()).hexdigest(), model_profile=self.profile,
            response_sha256="c" * 64, elapsed_seconds=.001)
        return self.transform(value) if self.transform else value


@pytest.fixture
def case(tmp_path, monkeypatch):
    monkeypatch.setenv("MVP_SEARCH_PLANNER_ENABLED", "0")
    def denied(*args, **kwargs):
        pytest.fail("Independent plan tests attempted external network access")
    monkeypatch.setattr(socket, "create_connection", denied)
    discovery, diagnostics, planner = Discovery(), Diagnostics(), Planner()
    engine = MVPService(SQLiteWorkspaceStorage(tmp_path / "research.sqlite3"), discovery, discovery)
    handle = engine.create_workspace()
    store = SearchPlanStore(engine._storage)
    service = SearchPlanService(engine, store, mode="live", diagnostics=diagnostics, planner=planner)
    return SimpleNamespace(path=tmp_path, engine=engine, handle=handle, store=store, service=service,
        discovery=discovery, diagnostics=diagnostics, planner=planner)


def manual(raw=RAW, question="Manual researcher question"):
    return SearchPlanDraft(original_question=question, input_mode="manual_strategy", manual_strategy=raw,
        date_filter=SearchDateFilter(date_from="2010-01-01", date_to="2025-12-31"), sort="pub_date")


def create(case, key="create", value=None):
    return case.service.create(case.handle, CreateSearchPlanRequest(request_id=key, draft=value or manual()))


def candidate_request(view, key):
    revision = view.revision
    candidate = revision.compiled.candidates[0]
    return dict(request_id=key, expected_revision_id=revision.revision_id, candidate_id=candidate.id,
        candidate_sha256=candidate.candidate_sha256)


def approve(case, view, key="approve", **kwargs):
    return case.service.approve(case.handle, view.revision.plan_id, ApproveSearchPlanRequest(
        **candidate_request(view, key), acknowledge_unparsed_strategy=True, **kwargs))


def update(case, view, key="update", value=None):
    return case.service.update(case.handle, view.revision.plan_id, UpdateSearchPlanRequest(request_id=key,
        expected_revision_id=view.revision.revision_id, draft=value or manual(RAW + " AND diet[tiab]")))


def operation(case, view, kind, key="operation"):
    plan = view.revision.plan_id
    if kind == "diagnose":
        return lambda: case.service.diagnose(case.handle, plan, DiagnoseSearchPlanRequest(**candidate_request(view, key)))
    if kind == "propose":
        request = ProposeSearchPlanRequest(request_id=key, expected_revision_id=view.revision.revision_id,
            original_question=view.revision.draft.original_question)
        return lambda: case.service.propose(case.handle, plan, request)
    approval = approve(case, view)
    request = ExecuteSearchPlanRequest(**candidate_request(view, key), approval_id=approval.id, max_results=30)
    return lambda: case.service.execute(case.handle, plan, request)


def external(case, kind):
    return getattr(case, {"diagnose": "diagnostics", "propose": "planner", "execute": "discovery"}[kind])


def test_manual_history_reopens_exactly_and_plain_reads_never_trigger_io(case):
    before = case.engine.get_workspace(case.handle).model_dump_json()
    first = create(case)
    assert create(case).revision == first.revision
    edited = update(case, first)
    reopened = SearchPlanService(case.engine, SearchPlanStore(case.engine._storage), mode="live",
        diagnostics=case.diagnostics, planner=case.planner)
    assert reopened.view(case.handle, first.revision.plan_id).revision == edited.revision
    historical = reopened.view(case.handle, first.revision.plan_id, first.revision.revision_id)
    assert historical.revision.draft.manual_strategy.encode() == RAW.encode()
    assert historical.current_revision_id == edited.revision.revision_id and len(historical.revisions) == 2
    assert reopened.listing(case.handle).plans[0].revision == 2
    reopened.capabilities(case.handle)
    assert case.engine.get_workspace(case.handle).model_dump_json() == before
    assert case.discovery.calls == case.diagnostics.calls == case.planner.calls == []
    with pytest.raises(MvpError, match="request"):
        create(case, value=manual(RAW + " "))
    with pytest.raises(MvpError) as stale:
        update(case, first, key="stale-save")
    assert stale.value.code == "stale_search_plan"


def test_approval_requires_exact_acknowledgments_and_is_not_terminology_validation(case):
    view = create(case)
    with pytest.raises(MvpError) as missing:
        case.service.approve(case.handle, view.revision.plan_id, ApproveSearchPlanRequest(**candidate_request(view, "missing")))
    assert missing.value.code == "search_approval_incomplete"
    approval = approve(case, view)
    assert approve(case, view).id == approval.id
    assert approval.meaning == "researcher_intent_approval_not_mesh_validation"
    assert case.discovery.calls == case.diagnostics.calls == case.planner.calls == []


def test_subquestion_approval_requires_both_required_and_excluded_deferrals_and_explicit_split(case):
    groups = [SearchConcept(id="topic", label="Microbiome", role="topic", requirement="required", retrieval_use="query",
        terms=[SearchTerm(id="topic", text="microbiome", state="approved")]),
        SearchConcept(id="population", label="Asian-origin women", role="population", requirement="required", retrieval_use="screen_later"),
        SearchConcept(id="excluded", label="Animal studies", role="study_design", requirement="excluded", retrieval_use="screen_later")]
    draft = SearchPlanDraft(original_question="Microbiome in Asian-origin women; exclude animal studies", concepts=groups,
        variants=[SearchVariant(id="subquestion", label="Explicitly split exploratory subquestion", kind="subquestion",
            expression=PlanExpression(op="concept_ref", concept_id="topic"), deferred_concept_ids=["population", "excluded"],
            deferral_reason="These constraints remain mandatory screening judgments.", split_explanation="A separate discovery question needs researcher approval.")])
    view = create(case, value=draft)
    for index, extra in enumerate([{}, {"acknowledged_deferred_concept_ids": ["population"]},
            {"acknowledged_deferred_concept_ids": ["population", "excluded"]}]):
        with pytest.raises(MvpError) as incomplete:
            case.service.approve(case.handle, view.revision.plan_id, ApproveSearchPlanRequest(**candidate_request(view, f"incomplete-{index}"), **extra))
        assert incomplete.value.code == "search_approval_incomplete"
    accepted = case.service.approve(case.handle, view.revision.plan_id, ApproveSearchPlanRequest(**candidate_request(view, "explicit"),
        acknowledged_deferred_concept_ids=["population", "excluded"], accept_subquestion_split=True))
    assert accepted.accept_subquestion_split and set(accepted.acknowledged_deferred_concept_ids) == {"population", "excluded"}


def test_wrong_workspace_capability_candidate_and_historical_approval_never_execute(case):
    view = create(case)
    approval = approve(case, view)
    other = case.engine.create_workspace()
    with pytest.raises(MvpError):
        case.service.view(other, view.revision.plan_id)
    with pytest.raises(MvpError):
        case.service.view(WorkspaceHandle(workspace_id=case.handle.workspace_id, token=other.token), view.revision.plan_id)
    bad = DiagnoseSearchPlanRequest(**{**candidate_request(view, "bad-hash"), "candidate_sha256": "0" * 64})
    with pytest.raises(MvpError) as mismatch:
        case.service.diagnose(case.handle, view.revision.plan_id, bad)
    assert mismatch.value.code == "stale_search_candidate"
    edited = update(case, view)
    with pytest.raises(MvpError) as stale:
        case.service.execute(case.handle, view.revision.plan_id, ExecuteSearchPlanRequest(
            **candidate_request(edited, "old-approval"), approval_id=approval.id))
    assert stale.value.code == "stale_search_approval" and case.discovery.calls == []


def test_capture_is_explicit_idempotent_and_diagnostic_recovery_uses_actual_retained_papers(case):
    view = create(case)
    run = operation(case, view, "execute")
    captured = run()
    assert run() == captured and len(case.discovery.calls) == 1
    request = case.discovery.calls[0]
    assert (request.query, request.sort, request.date_from, request.date_to) == (RAW, "pub_date", "2010-01-01", "2025-12-31")
    assert captured.execution.search_snapshot_sha256 == digest(captured.search.model_dump(mode="json"))
    assert len(case.engine.get_workspace(case.handle).searches) == 1
    seeds = [DiagnosticSeed(id="captured", pmid="111", purpose="construction", approved=True),
        DiagnosticSeed(id="ordered-only", pmid="222", purpose="held_out", approved=True)]
    checked = case.service.diagnose(case.handle, view.revision.plan_id, DiagnoseSearchPlanRequest(
        **candidate_request(view, "diagnostic"), seeds=seeds, preview_search_id=captured.search.id))
    assert case.diagnostics.calls[0][1]["preview_pmids"] == ["111"]
    assert [item.preview_recovery for item in checked.receipt.seed_results] == ["present", "absent"]
    assert checked.preview_search_id == captured.search.id and checked.preview_search_snapshot_sha256 == digest(captured.search.model_dump(mode="json"))
    assert len(case.engine.get_workspace(case.handle).searches) == 1 and len(case.discovery.calls) == 1


@pytest.mark.parametrize("change", ["wrong_query", "wrong_hash", "wrong_filter", "excess_calls"])
def test_diagnostic_receipts_must_match_exact_server_inputs(case, change):
    view = create(case)
    changes = {"wrong_query": {"query": "rewritten"}, "wrong_hash": {"query_sha256": "0" * 64},
        "wrong_filter": {"date_from": None}, "excess_calls": {"calls": 3}}
    case.diagnostics.transform = lambda result: result.model_copy(update=changes[change])
    call = operation(case, view, "diagnose")
    for _ in range(2):
        with pytest.raises(MvpError) as error:
            call()
        assert error.value.code == "invalid_query_diagnostic"
    assert len(case.diagnostics.calls) == 1 and case.service.view(case.handle, view.revision.plan_id).diagnostics == []


def test_proposal_is_separate_from_human_editor_revision_and_has_no_approval(case):
    view = create(case)
    call = operation(case, view, "propose")
    proposed = call()
    assert call() == proposed and len(case.planner.calls) == 1
    reopened = case.service.view(case.handle, view.revision.plan_id)
    assert reopened.revision == view.revision and reopened.approvals == [] and reopened.executions == []
    assert reopened.proposals == [proposed] and proposed.result.usage.measured is False
    assert proposed.result.draft.concepts[0].terms[0].state == "proposed" and case.discovery.calls == []


@pytest.mark.parametrize("change", ["question", "profile", "elapsed", "approved_term"])
def test_planner_receipt_cannot_claim_other_input_profile_budget_or_human_approval(case, change):
    view = create(case)
    def malformed(result):
        if change == "question":
            return result.model_copy(update={"question_sha256": "0" * 64})
        if change == "profile":
            return result.model_copy(update={"model_profile": {"model": "unconfigured"}})
        if change == "elapsed":
            return result.model_copy(update={"elapsed_seconds": 11})
        concept = result.draft.concepts[0]
        altered = concept.model_copy(update={"terms": [concept.terms[0].model_copy(update={"state": "approved"})]})
        return result.model_copy(update={"draft": result.draft.model_copy(update={"concepts": [altered]})})
    case.planner.transform = malformed
    call = operation(case, view, "propose")
    for _ in range(2):
        with pytest.raises(MvpError) as error:
            call()
        assert error.value.code == "invalid_search_planner_output"
    assert len(case.planner.calls) == 1 and case.service.view(case.handle, view.revision.plan_id).proposals == []


@pytest.mark.parametrize("kind", ["diagnose", "propose", "execute"])
def test_external_calls_release_mutation_locks_and_late_aba_results_cannot_publish(case, kind):
    view = create(case)
    call = operation(case, view, kind)
    provider = external(case, kind)
    provider.block = True
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(call)
        assert provider.entered.wait(timeout=2)
        try:
            edited = pool.submit(update, case, view).result(timeout=1)
            restored = pool.submit(update, case, edited, "restore-A", view.revision.draft).result(timeout=1)
            assert restored.revision.draft == view.revision.draft and restored.revision.revision_id != view.revision.revision_id
        finally:
            provider.release.set()
        with pytest.raises(MvpError) as stale:
            pending.result(timeout=3)
    assert stale.value.code == "stale_search_plan"
    assert len(provider.calls) == 1 and case.engine.get_workspace(case.handle).searches == []
    current = case.service.view(case.handle, view.revision.plan_id)
    assert current.revision == restored.revision and current.proposals == current.diagnostics == current.executions == []


@pytest.mark.parametrize("kind", ["diagnose", "propose", "execute"])
def test_pending_request_is_reserved_before_io_and_never_repeated(case, kind):
    view = create(case)
    call = operation(case, view, kind)
    provider = external(case, kind)
    provider.block = True
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(call)
        assert provider.entered.wait(timeout=2)
        try:
            duplicate = pool.submit(call)
            with pytest.raises(MvpError) as reserved:
                duplicate.result(timeout=1)
            assert reserved.value.code == "search_plan_call_pending" and len(provider.calls) == 1
        finally:
            provider.release.set()
        result = pending.result(timeout=3)
    assert call() == result and len(provider.calls) == 1


@pytest.mark.parametrize("kind", ["diagnose", "propose", "execute"])
def test_deleted_workspace_cannot_be_recreated_by_late_external_result(case, kind):
    view = create(case)
    call = operation(case, view, kind)
    provider = external(case, kind)
    provider.block = True
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(call)
        assert provider.entered.wait(timeout=2)
        try:
            pool.submit(case.engine.clear_workspace, case.handle).result(timeout=1)
        finally:
            provider.release.set()
        with pytest.raises(MvpError):
            pending.result(timeout=3)
    with case.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM mvp_workspaces").fetchone()[0] == 0
        assert all(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0 for table in
            ["mvp_search_plans", "mvp_search_plan_revisions", "mvp_search_plan_events", "mvp_search_plan_requests"])


def test_preflight_quota_rejects_before_external_call_and_existing_history_survives(case, monkeypatch):
    import src.mvp.adapters.search_plan_storage as policy
    view = create(case)
    monkeypatch.setattr(policy, "MAX_PLAN_REQUESTS", 1)
    with pytest.raises(MvpError) as full:
        operation(case, view, "diagnose")()
    assert full.value.code == "search_plan_storage_limit" and case.diagnostics.calls == []
    assert case.service.view(case.handle, view.revision.plan_id).revision == view.revision
    with case.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM mvp_search_plan_requests").fetchone()[0] == 1


@pytest.mark.parametrize("limit", ["plans", "revisions"])
def test_plan_and_revision_capacity_roll_back_without_replacing_existing_history(case, monkeypatch, limit):
    import src.mvp.adapters.search_plan_storage as policy
    view = create(case)
    monkeypatch.setattr(policy, "MAX_SEARCH_PLANS" if limit == "plans" else "MAX_PLAN_REVISIONS", 1)
    with pytest.raises(MvpError) as full:
        create(case, key="second") if limit == "plans" else update(case, view)
    assert full.value.code == ("search_plan_storage_limit" if limit == "plans" else "search_plan_revision_limit")
    assert case.service.view(case.handle, view.revision.plan_id).revision == view.revision
    assert len(case.service.listing(case.handle).plans) == 1
    with case.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM mvp_search_plan_revisions").fetchone()[0] == 1
    assert case.discovery.calls == case.diagnostics.calls == case.planner.calls == []


def test_tampered_planning_history_fails_integrity_without_altering_research_snapshot(case):
    view = create(case)
    before = case.engine.get_workspace(case.handle).model_dump_json()
    with case.store.connection() as db:
        db.execute("UPDATE mvp_search_plan_revisions SET payload=payload||' ' WHERE id=?", (view.revision.revision_id,))
    for read in [lambda: case.service.view(case.handle, view.revision.plan_id), lambda: case.engine.export_workspace(case.handle)]:
        with pytest.raises(MvpError) as corrupt:
            read()
        assert corrupt.value.code == "search_plan_integrity"
    assert case.engine.get_workspace(case.handle).model_dump_json() == before


def test_full_receipt_capacity_is_rejected_before_starting_provider_or_model(case, monkeypatch):
    import src.mvp.adapters.search_plan_storage as policy
    view = create(case)
    approve(case, view)
    monkeypatch.setattr(policy, "MAX_PLAN_RECEIPTS", 1)
    with pytest.raises(MvpError) as full:
        operation(case, view, "diagnose")()
    assert full.value.code == "search_plan_storage_limit"
    assert case.diagnostics.calls == [], "Known exhausted receipt capacity must be checked before provider I/O"
    assert len(case.service.view(case.handle, view.revision.plan_id).approvals) == 1


def test_inflight_operation_reserves_a_receipt_slot_before_concurrent_writes(case, monkeypatch):
    import src.mvp.adapters.search_plan_storage as policy
    view = create(case)
    monkeypatch.setattr(policy, "MAX_PLAN_RECEIPTS", 1)
    case.diagnostics.block = True
    call = operation(case, view, "diagnose")
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(call)
        assert case.diagnostics.entered.wait(timeout=2)
        try:
            competing = pool.submit(approve, case, view)
            with pytest.raises(MvpError) as full:
                competing.result(timeout=1)
            assert full.value.code == "search_plan_storage_limit"
        finally:
            case.diagnostics.release.set()
        receipt = pending.result(timeout=3)
    assert receipt.receipt.status == "succeeded"
    saved = case.service.view(case.handle, view.revision.plan_id)
    assert len(saved.diagnostics) == 1 and saved.approvals == []


def test_failed_atomic_capture_link_rolls_back_both_capture_and_execution_receipt(case):
    view = create(case)
    call = operation(case, view, "execute")
    before = case.engine.get_workspace(case.handle).model_dump_json()
    with case.store.connection() as db:
        db.execute("CREATE TRIGGER reject_planned_execution BEFORE INSERT ON mvp_search_plan_events WHEN NEW.kind='execution' BEGIN SELECT RAISE(ABORT,'independent simulated receipt failure'); END")
    with pytest.raises(MvpError):
        call()
    assert len(case.discovery.calls) == 1 and case.engine.get_workspace(case.handle).model_dump_json() == before
    assert case.service.view(case.handle, view.revision.plan_id).executions == []
    with case.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM mvp_requests WHERE operation LIKE 'planned_search_v2:%'").fetchone()[0] == 0


@pytest.mark.parametrize("change", ["query", "date", "sort", "saved_example"])
def test_discovery_cannot_publish_a_preview_for_another_query_or_filter(case, change):
    view = create(case)
    changes = {"query": {"query": "rewritten strategy"}, "date": {"date_from": None},
        "sort": {"sort": "relevance"}, "saved_example": {"mode": "saved_example"}}
    case.discovery.transform = lambda result: result.model_copy(update=changes[change])
    call = operation(case, view, "execute")
    with pytest.raises(MvpError) as mismatch:
        call()
    assert mismatch.value.code == "planned_search_mismatch"
    assert case.engine.get_workspace(case.handle).searches == [] and len(case.discovery.calls) == 1


@pytest.mark.parametrize("kind", ["diagnose", "propose", "execute"])
def test_provider_failures_are_terminal_for_the_same_key_sanitized_and_have_no_fallback(case, kind):
    view = create(case)
    external(case, kind).failure = True
    call = operation(case, view, kind)
    for _ in range(2):
        with pytest.raises(MvpError) as failure:
            call()
        assert "PRIVATE_PROVIDER_ERROR_SENTINEL" not in failure.value.message
    assert len(external(case, kind).calls) == 1
    assert sum(len(provider.calls) for provider in [case.discovery, case.diagnostics, case.planner]) == 1
    assert case.engine.get_workspace(case.handle).searches == []


def test_defaults_disable_generation_and_saved_examples_cannot_execute_new_queries(case):
    default = SearchPlanService(case.engine, case.store, mode="saved_example")
    capabilities = default.capabilities(case.handle)
    assert capabilities.manual_enabled and not capabilities.planner.enabled and not capabilities.execution_enabled
    view = create(case)
    with pytest.raises(MvpError) as disabled:
        default.propose(case.handle, view.revision.plan_id, ProposeSearchPlanRequest(request_id="disabled",
            expected_revision_id=view.revision.revision_id, original_question=view.revision.draft.original_question))
    assert disabled.value.code == "search_planner_disabled"
    with pytest.raises(MvpError) as saved:
        default.execute(case.handle, view.revision.plan_id, ExecuteSearchPlanRequest(**candidate_request(view, "saved"), approval_id="missing"))
    assert saved.value.code == "planned_search_requires_live" and case.discovery.calls == case.planner.calls == []


def test_invalid_optional_planner_configuration_leaves_manual_editing_available(case, monkeypatch):
    monkeypatch.setenv("MVP_SEARCH_PLANNER_ENABLED", "1")
    monkeypatch.setenv("MVP_SEARCH_PLANNER_URL", "https://remote-provider.invalid/v1/chat/completions")
    monkeypatch.setenv("MVP_SEARCH_PLANNER_MODEL", "unconfigured")
    monkeypatch.setenv("MVP_SEARCH_PLANNER_MODEL_REVISION", "fixture")
    manual_service = SearchPlanService(case.engine, case.store, mode="live")
    capabilities = manual_service.capabilities(case.handle)
    assert not capabilities.planner.enabled and capabilities.planner.reason and capabilities.manual_enabled
    created = manual_service.create(case.handle, CreateSearchPlanRequest(request_id="manual-with-bad-model-config", draft=manual()))
    assert created.revision.compiled.candidates[0].query == RAW
    assert case.discovery.calls == case.diagnostics.calls == case.planner.calls == []
