"""Synthetic HTTP source-binding/profile/publication checks; no model/live calls."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import socket
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.contracts import Paper, SearchPreview
from src.mvp.service import MVPService
from src.mvp.span_evaluation import load_frozen_cases
from src.web_api.app import create_app

FIELDS = [{"id": "population", "label": "Population", "subquestion": "What were the intervention cohort sample size, population origin and age range?"},
    {"id": "covariates", "label": "Adjustment covariates", "subquestion": "Which adjustment covariates were used for the dietary microbiome association?"}]


class Providers:
    def __init__(self, sources):
        self.sources = {source.paper_id: source for source in sources}
        self.search_calls, self.source_calls = 0, 0

    def search(self, request):
        self.search_calls += 1
        return SearchPreview(query=request.query, mode="test", provider="synthetic-span-http-fixtures", total_reported=len(self.sources),
            fetched_count=len(self.sources), truncated=False, papers=[Paper(id=key, title="SYNTHETIC " + source.id,
                abstract="Synthetic bibliographic abstract.") for key, source in self.sources.items()])

    def prepare(self, paper):
        self.source_calls += 1
        return self.sources[paper.id]


def browser(app):
    client = TestClient(app, base_url="http://127.0.0.1:8765", raise_server_exceptions=False)
    csrf = client.get("/api/v1/session").json()["csrf_token"]
    client.headers.update({"Origin": "http://127.0.0.1:3000", "X-CSRF-Token": csrf})
    return client


@pytest.fixture
def case(tmp_path, monkeypatch):
    for name in ("MVP_MAP_ENABLED", "MVP_PROPOSALS_ENABLED", "MVP_SEARCH_PLANNER_ENABLED"):
        monkeypatch.setenv(name, "0")
    monkeypatch.delenv("NCBI_EMAIL", raising=False)
    def denied(*args, **kwargs):
        pytest.fail("Span HTTP test attempted external provider/model networking")
    monkeypatch.setattr(socket, "create_connection", denied)
    _, sources = load_frozen_cases()
    # The engine's raw retained-byte contract is JATS XML. These are explicit
    # synthetic canonical-block providers, so they do not claim raw XML bytes.
    # The frozen source text/anchors remain untouched.
    selected = [sources[key].model_copy(update={"retained_content_utf8": None})
        for key in ("synthetic-late", "synthetic-abstract-only", "synthetic-no-answer")]
    provider = Providers(selected)
    engine = MVPService(SQLiteWorkspaceStorage(tmp_path / "research.sqlite3"), provider, provider)
    app = create_app(tmp_path, services={"saved_example": engine})
    client = browser(app)
    made = client.post("/api/v1/workspaces", json={"request_id": "workspace", "mode": "saved_example"})
    made.raise_for_status()
    root = "/api/v1/workspaces/" + made.json()["id"]
    search = client.post(root + "/searches", json={"request_id": "search", "query": "synthetic span fixtures"})
    search.raise_for_status()
    papers = [paper["id"] for paper in search.json()["papers"]]
    prepared = client.post(root + "/source-preparations", json={"request_id": "prepare", "search_id": search.json()["id"], "paper_ids": papers})
    prepared.raise_for_status()
    body = {"request_id": "board", "question": "Synthetic source-first board software checks", "preparation_id": prepared.json()["id"], "paper_ids": papers, "fields": FIELDS}
    return SimpleNamespace(app=app, client=client, root=root, provider=provider, engine=engine, sources=selected,
        papers=papers, search=search.json(), preparation=prepared.json(), body=body, path=tmp_path)


def make(case, profile="lexical_spans_v1", key="board"):
    body = {**case.body, "request_id": key}
    if profile is not None:
        body.update(schema_version="mvp.board-profile-request.v2", retrieval_profile_id=profile)
    response = case.client.post(case.root + "/boards", json=body)
    response.raise_for_status()
    return response.json()


def path(case, board):
    return case.root + "/boards/" + board["definition"]["board_id"]


def request(board, paper, field="population", key="candidates"):
    return {"request_id": key, "expected_revision_id": board["definition"]["revision_id"], "paper_id": paper, "field_id": field, "top_k": 3}


class WrappedRanker:
    def __init__(self, real, transform=None, block=False):
        self.real, self.transform, self.block = real, transform, block
        self.calls = 0
        self.entered, self.release = threading.Event(), threading.Event()

    def profile(self): return self.real.profile()

    def search(self, *args, **kwargs):
        self.calls += 1
        result = self.real.search(*args, **kwargs)
        if self.block:
            self.entered.set()
            assert self.release.wait(timeout=6)
        return self.transform(result) if self.transform else result


def test_explicit_spans_are_exact_inspectable_replayable_and_preserve_legacy_history(case):
    legacy = make(case, profile=None, key="legacy")
    original = deepcopy(legacy["definition"])
    baseline = case.client.post(path(case, legacy) + "/candidates", json=request(legacy, case.papers[0], key="legacy-candidates"))
    baseline.raise_for_status()
    assert baseline.json()["schema_version"] == "mvp.board-candidates.v1"
    assert all("64 Japanese women" not in value["reference"]["quote"] for value in baseline.json()["candidates"])
    board = make(case)
    before_sources = [(source.source_sha256, source.blocks_sha256) for source in case.sources]
    api = path(case, board)
    ranker = WrappedRanker(case.app.state.boards._span())
    case.app.state.boards.span_ranker = ranker
    body = request(board, case.papers[0])
    retrieved = case.client.post(api + "/candidates", json=body)
    retrieved.raise_for_status()
    result = retrieved.json()
    assert result["schema_version"] == "mvp.board-candidates.spans.v2"
    chosen = next(value for value in result["candidates"] if "64 Japanese women" in value["reference"]["quote"])
    reference = chosen["reference"]
    block = case.sources[0].blocks[0]
    assert reference["start"] > 0 and reference["end"] > 1200 and reference["quote"] == block.text[reference["start"]:reference["end"]]
    assert chosen["omitted_before"] == reference["start"] and chosen["omitted_after"] == len(block.text) - reference["end"]
    assert result["context_scope"] == "exact_retained_spans_only_not_whole_paper"
    assert all(value["meaning"] == "lexical_potential_not_inspected_or_supported" for value in result["requirement_matches"])
    inspected = case.client.get(api + "/references/" + reference["id"] + "/context")
    inspected.raise_for_status()
    assert inspected.json()["reference"] == reference
    assert case.client.post(api + "/candidates", json=body).json() == result and ranker.calls == 1
    csv_export = case.client.get(api + "/exports", params={"format": "csv"})
    audit = case.client.get(api + "/exports", params={"format": "json", "history": True})
    csv_export.raise_for_status(); audit.raise_for_status()
    assert audit.json()["candidate_runs"][0]["schema_version"] == "mvp.board-candidates.spans.v2"
    assert case.client.get(path(case, legacy)).json()["definition"] == original
    assert [(source.source_sha256, source.blocks_sha256) for source in case.sources] == before_sources
    assert case.provider.search_calls == 1 and case.provider.source_calls == 3
    assert case.client.get(api + "/cells/" + case.papers[0] + "/population/history").json()["items"] == []


def test_profile_revisions_are_explicit_and_source_field_requirements_are_owned(case):
    board = make(case)
    api = path(case, board)
    legacy_body = {**case.body, "request_id": "implicit", "expected_revision_id": board["definition"]["revision_id"]}
    rejected = case.client.post(api + "/revisions", json=legacy_body)
    assert rejected.status_code == 422 and rejected.json()["error"]["code"] == "explicit_board_profile_required"
    wrong = {**case.body, "request_id": "wrong-requirement", "schema_version": "mvp.board-profile-request.v2", "retrieval_profile_id": "lexical_spans_v1",
        "field_requirements": [{"field_id": "not-a-field", "requirements": [{"id": "wrong", "label": "Wrong", "query": "participants"}]}]}
    assert case.client.post(case.root + "/boards", json=wrong).status_code == 422
    explicit = case.client.post(api + "/revisions", json={**legacy_body, "request_id": "explicit", "schema_version": "mvp.board-profile-request.v2", "retrieval_profile_id": "legacy_block_prefix_v1"})
    explicit.raise_for_status()
    assert explicit.json()["definition"]["retrieval_profile"].get("profile_id", "legacy_block_prefix_v1") == "legacy_block_prefix_v1"
    assert case.client.get(api, params={"revision_id": board["definition"]["revision_id"]}).json()["definition"] == board["definition"]


@pytest.mark.parametrize("change", ["paper", "source", "quote", "range", "run", "profile", "tokens", "source_characters", "source_blocks",
    "matched_blocks", "partial", "blank", "elapsed", "component"])
def test_ranker_output_must_match_captured_source_profile_and_real_span_metadata(case, change):
    board = make(case)
    def altered(result):
        first = result.selections[0]
        updates = {"paper": {"paper_id": "wrong-paper"}, "source": {"source_id": "wrong-source"},
            "quote": {"quote": first.quote + "invented"}, "range": {"start": first.start + 1}, "tokens": {"budget_tokens": 1},
            "component": {"matched_requirement_ids": ["not-the-field-component"]}}
        if change in updates:
            selections = [first.model_copy(update=updates[change]), *result.selections[1:]]
            extra = {"delivered_tokens": sum(value.budget_tokens for value in selections)} if change == "tokens" else {}
            return result.model_copy(update={"selections": selections, **extra})
        return result.model_copy(update={"run": {"run_id": "wrong-run"}, "profile": {"profile_id": "wrong-profile"},
            "source_characters": {"total_source_characters": result.total_source_characters + 1},
            "source_blocks": {"total_source_blocks": result.total_source_blocks + 1},
            "matched_blocks": {"matched_blocks": 0}, "partial": {"partially_indexed_blocks": 999},
            "blank": {"skipped_blank_blocks": 999}, "elapsed": {"elapsed_seconds": float("nan")}}[change])
    case.app.state.boards.span_ranker = WrappedRanker(case.app.state.boards._span(), transform=altered)
    response = case.client.post(path(case, board) + "/candidates", json=request(board, case.papers[0]))
    assert response.status_code == 422, response.text
    with case.app.state.boards.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM board_candidates").fetchone()[0] == 0


@pytest.mark.parametrize("mutation", ["revision", "refresh", "delete", "tombstone", "source_tamper"])
def test_cpu_ranking_is_outside_guards_and_late_work_cannot_publish(case, mutation):
    board = make(case)
    ranker = WrappedRanker(case.app.state.boards._span(), block=True)
    case.app.state.boards.span_ranker = ranker
    api = path(case, board)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(case.client.post, api + "/candidates", json=request(board, case.papers[0]))
        assert ranker.entered.wait(timeout=2)
        try:
            if mutation == "revision":
                body = {**case.body, "request_id": "revise", "expected_revision_id": board["definition"]["revision_id"],
                    "schema_version": "mvp.board-profile-request.v2", "retrieval_profile_id": "lexical_spans_v1"}
                changed = pool.submit(case.client.post, api + "/revisions", json=body).result(timeout=1)
                changed.raise_for_status()
            elif mutation == "refresh":
                refreshed = pool.submit(case.client.post, case.root + "/source-preparations", json={"request_id": "refresh", "search_id": case.search["id"], "paper_ids": case.papers}).result(timeout=1)
                refreshed.raise_for_status()
            elif mutation == "delete":
                assert pool.submit(case.client.delete, case.root).result(timeout=1).status_code == 200
            elif mutation == "source_tamper":
                def corrupt_source():
                    with case.engine._storage._connection() as db:
                        row = db.execute("SELECT id,snapshot FROM mvp_workspaces").fetchone()
                        document = json.loads(row["snapshot"])
                        document["preparations"][0]["sources"][0]["blocks"][0]["text"] += " CORRUPTED"
                        db.execute("UPDATE mvp_workspaces SET snapshot=? WHERE id=?", (json.dumps(document), row["id"]))
                pool.submit(corrupt_source).result(timeout=1)
            else:
                def tombstone():
                    registry = case.app.state.registry
                    workspace_id = case.root.rsplit("/", 1)[-1]
                    with registry.lifecycle_guard(workspace_id), registry.connection() as db:
                        db.execute("INSERT INTO web_tombstones VALUES(?,?)", (workspace_id, "2026-10-22T00:00:00+00:00"))
                pool.submit(tombstone).result(timeout=1)
        finally:
            ranker.release.set()
        response = pending.result(timeout=3)
    assert response.status_code in ({422} if mutation == "source_tamper" else {404, 409}), response.text
    with case.app.state.boards.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM board_candidates").fetchone()[0] == 0


def test_abstract_only_and_missing_information_keep_candidate_and_human_states_distinct(case):
    board = make(case)
    api = path(case, board)
    for index in (1, 2):
        response = case.client.post(api + "/candidates", json=request(board, case.papers[index], "covariates", "missing-" + str(index)))
        response.raise_for_status()
        result = response.json()
        assert result["context_scope"] == "exact_retained_spans_only_not_whole_paper"
        assert all("support" not in match["state"] for match in result["requirement_matches"])
        if index == 1:
            bindings = {value["source_id"]: value for value in board["definition"]["sources"]}
            assert result["candidates"] and all(bindings[value["reference"]["source_id"]]["source_type"] == "abstract" for value in result["candidates"])
        assert case.client.get(api + "/cells/" + case.papers[index] + "/covariates/history").json()["items"] == []


def test_span_endpoints_preserve_session_csrf_and_owned_paper_boundaries(case):
    board = make(case)
    api = path(case, board)
    other = browser(case.app)
    assert other.post(api + "/candidates", json=request(board, case.papers[0])).status_code == 404
    assert case.client.post(api + "/candidates", json=request(board, case.papers[0]), headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert case.client.post(api + "/candidates", json=request(board, "not-owned")).status_code in (404, 422)
