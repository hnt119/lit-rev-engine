"""Independent manual-board checks over synthetic retained sources.

No provider/model execution or human usefulness validation occurs here. An exact
reference proves source integrity only; semantic support stays a human claim.
"""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from types import SimpleNamespace
from xml.sax.saxutils import escape
import csv
import io
import json
import socket
import sqlite3

import pytest
from pydantic import ValidationError

from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.contracts import (
    Block, CreateWorkspaceRequest, Paper, PreparedSource, PrepareSourcesRequest,
    SearchPreview, SearchRequest, digest,
)
from src.mvp.ports import MvpError
from src.mvp.service import MVPService
from src.mvp.workspace_ui import WorkspaceUIStore
from src.review.documents import parse_source_bytes
from src.mvp.board_contracts import (
    BoardCandidatesRequest, BoardCellData, BoardCreateRequest, BoardDraftPutRequest,
    BoardFieldInput, BoardReferenceInput, BoardReviseRequest, BoardSubmitRequest,
    MAX_CANDIDATE_CHARACTERS, MAX_INSPECTOR_CHARACTERS,
)


QUESTION = "SYNTHETIC board software case: diet, microbiome and fertility"
UNICODE = "Café e\u0301 😀 中文 women had microbial diversity; fertility was not measured."


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Independent board software check attempted network access")
    monkeypatch.setattr(socket, "create_connection", denied)


class BoardFixtureProviders:
    def __init__(self):
        self.searches = self.preparations = 0
        self.papers = [
            Paper(title="=SYNTHETIC original report one", pmid="99999701", abstract=UNICODE),
            Paper(title="SYNTHETIC abstract-only report two", pmid="99999702",
                  abstract="Diet was measured by questionnaire in women. No fertility measure is described."),
            Paper(title="SYNTHETIC unavailable report three", pmid="99999703", abstract=""),
        ]

    def search(self, request):
        self.searches += 1
        return SearchPreview(query=request.query, research_question=QUESTION,
            total_reported=3, fetched_count=3, papers=self.papers,
            ordered_identifiers=[paper.pmid for paper in self.papers], truncated=False,
            provider="synthetic-board-fixture", mode="test")

    def prepare(self, paper):
        self.preparations += 1
        full, unavailable = paper.pmid == "99999701", paper.pmid == "99999703"
        blocks = [] if unavailable else [Block(id="canonical:1", ordinal=1,
            text=paper.abstract, locator={"type": "synthetic-fixture", "ordinal": 1})]
        raw = "\n\n".join(block.text for block in blocks)
        if full:
            raw = ('<article><front><article-meta><article-id pub-id-type="pmid">' + paper.pmid +
                '</article-id></article-meta></front><body><sec><p>' + escape(paper.abstract) +
                '</p><p>Synthetic diet and microbiome methods. This block makes no reproductive claim.'
                '</p></sec></body></article>')
            parsed = parse_source_bytes(raw.encode("utf-8"), "jats_xml")
            blocks = [Block.model_validate(block) for block in parsed["blocks"]]
        return PreparedSource(paper_id=paper.id,
            status="no_usable_text" if unavailable else "full_text_retrieved" if full else "abstract_only",
            source_type="none" if unavailable else "full_text" if full else "abstract",
            provider="synthetic-board-fixture", source_url="https://example.invalid/" + paper.pmid,
            source_identifiers={"pmid": paper.pmid}, blocks=blocks,
            source_sha256=sha256(raw.encode()).hexdigest() if blocks else "",
            blocks_sha256=digest([block.model_dump(mode="json") for block in blocks]),
            license="SYNTHETIC permission label for software fixture" if full else None,
            retained_content_utf8=raw if full else None,
            parser_id="synthetic-board-fixture.v1")


def _base_case(tmp_path):
    registry = WorkspaceUIStore(tmp_path / "registry.sqlite3")
    token, session = registry.session()
    provider = BoardFixtureProviders()
    engine = MVPService(SQLiteWorkspaceStorage(tmp_path / "research.sqlite3"), provider, provider)
    handle = registry.create_workspace(session["token_hash"], "create",
        {"mode": "saved_example", "question": QUESTION},
        lambda reserved: engine.create_reserved_workspace(reserved, CreateWorkspaceRequest(question=QUESTION)))
    search = engine.search_literature(handle, SearchRequest(request_id="search", query="synthetic fixture",
                                                           research_question=QUESTION))
    prep = engine.prepare_sources(handle, PrepareSourcesRequest(request_id="prepare", search_id=search.id,
                                   paper_ids=[paper.id for paper in search.papers]))
    return SimpleNamespace(registry=registry, token=token, session=session, provider=provider,
                           engine=engine, handle=handle, search=search, prep=prep, root=tmp_path)


@pytest.fixture
def board_case(tmp_path):
    from src.mvp.adapters.board_storage import BoardStore
    from src.mvp.evidence_board import EvidenceBoardService
    case = _base_case(tmp_path)
    case.store = BoardStore(tmp_path / "boards.sqlite3")
    case.boards = EvidenceBoardService(case.registry, lambda mode: case.engine, case.store)
    case.request = BoardCreateRequest(request_id="board", preparation_id=case.prep.id,
        question=QUESTION, paper_ids=case.prep.selected_paper_ids,
        fields=[BoardFieldInput(id="diet", label="Diet", subquestion="What diet was measured?"),
                BoardFieldInput(id="diversity", label="Diversity", subquestion="microbial diversity"),
                BoardFieldInput(id="fertility", label="Fertility", subquestion="fertility")])
    case.view = case.boards.create("saved_example", case.handle, case.request)
    case.definition = case.view.definition
    return case


def _reference(case, paper_index=0, block_index=0, *, start=0, end=None):
    source = case.prep.sources[paper_index]
    block = source.blocks[block_index]
    return BoardReferenceInput(source_id=source.id, source_version=source.version,
        source_sha256=source.source_sha256, blocks_sha256=source.blocks_sha256,
        block_id=block.id, start=start, end=len(block.text) if end is None else end)


def _draft(case, data=None, *, paper_index=0, field="diversity", version=0, head=None,
           revision=None):
    return case.boards.put_draft("saved_example", case.handle, case.definition.board_id,
        case.prep.selected_paper_ids[paper_index], field,
        BoardDraftPutRequest(expected_revision_id=revision or case.definition.revision_id,
            version=version, expected_cell_head_id=head, data=data or BoardCellData()))


def _submit(case, draft, *, request_id="submit", head=None):
    return case.boards.submit("saved_example", case.handle, case.definition.board_id,
        BoardSubmitRequest(request_id=request_id, expected_revision_id=draft.board_revision_id,
            paper_id=draft.paper_id, field_id=draft.field_id, draft_version=draft.version,
            supersedes_id=head))


def test_three_by_three_reopens_without_mutating_engine_or_inferencing(board_case):
    case = board_case
    before = case.engine.get_workspace(case.handle).model_dump(mode="json")
    before_calls = case.provider.searches, case.provider.preparations
    assert [source.source_type for source in case.prep.sources] == ["full_text", "abstract", "none"]
    assert case.prep.errors == []
    assert len(case.view.cells) == 9
    assert all(cell.head is None and cell.draft_version == 0 for cell in case.view.cells)
    assert case.boards.create("saved_example", case.handle, case.request) == case.view
    for _ in range(2):
        assert case.boards.view("saved_example", case.handle, case.definition.board_id) == case.view
        assert len(case.boards.listing("saved_example", case.handle).boards) == 1
    from src.mvp.adapters.board_storage import BoardStore
    from src.mvp.evidence_board import EvidenceBoardService
    reopened = EvidenceBoardService(case.registry, lambda mode: case.engine,
                                    BoardStore(case.root / "boards.sqlite3"))
    assert reopened.view("saved_example", case.handle, case.definition.board_id) == case.view
    assert case.engine.get_workspace(case.handle).model_dump(mode="json") == before
    assert (case.provider.searches, case.provider.preparations) == before_calls


def test_per_cell_candidates_and_inspection_never_create_judgment_or_inspection_record(board_case):
    case = board_case
    request = BoardCandidatesRequest(request_id="candidates", expected_revision_id=case.definition.revision_id,
        paper_id=case.prep.selected_paper_ids[1], field_id="diet", top_k=3)
    found = case.boards.candidates("saved_example", case.handle, case.definition.board_id, request)
    assert found.returned_count == len(found.candidates) >= 1
    assert found.indexed_blocks == 1
    assert found.meaning == "potential_relevance_not_inspected_support"
    assert all(candidate.reference.paper_id == request.paper_id for candidate in found.candidates)
    assert case.boards.candidates("saved_example", case.handle, case.definition.board_id, request) == found
    chunk = case.boards.blocks("saved_example", case.handle, case.definition.board_id,
        case.prep.sources[1].id, offset=0, limit=1)
    assert chunk.source.source_type == "abstract"
    draft = case.boards.get_draft("saved_example", case.handle, case.definition.board_id,
                                  request.paper_id, request.field_id)
    assert draft.data.inspected_ranges == draft.data.references == []
    assert draft.data.semantic_assessment == "unassessed" and draft.data.scope_result == "not_assessed"
    view = case.boards.view("saved_example", case.handle, case.definition.board_id)
    assert all(cell.head is None for cell in view.cells)
    empty = case.boards.candidates("saved_example", case.handle, case.definition.board_id,
        request.model_copy(update={"request_id": "unavailable", "paper_id": case.prep.selected_paper_ids[2]}))
    assert empty.returned_count == empty.indexed_blocks == empty.matched_blocks == 0
    assert all(cell.head is None for cell in case.boards.view(
        "saved_example", case.handle, case.definition.board_id).cells)


def test_unicode_reference_is_server_reconstructed_and_exactness_does_not_infer_support(board_case):
    case = board_case
    start = UNICODE.index("😀")
    reference = _reference(case, start=start, end=start + len("😀 中文"))
    draft = _draft(case, BoardCellData(value="Unrelated provisional human text", references=[reference],
        inspected_ranges=[reference], scope_result="value_found", semantic_assessment="unassessed"))
    submitted = _submit(case, draft)
    assert submitted.references[0].quote == "😀 中文"
    assert submitted.references[0].integrity == submitted.reference_integrity == "checked"
    assert submitted.semantic_assessment == "unassessed"
    assert submitted.review_state == "single_human_self_declared_not_independently_verified"
    context = case.boards.reference_context("saved_example", case.handle, case.definition.board_id,
                                            submitted.references[0].id)
    assert context.reference.quote == "😀 中文"
    assert context.block.text[reference.start-context.block.start:reference.end-context.block.start] == "😀 中文"


@pytest.mark.parametrize("bad", [
    {"source_id": "wrong-source"}, {"source_version": "wrong-version"},
    {"source_sha256": "0" * 64}, {"blocks_sha256": "f" * 64},
    {"block_id": "wrong-block"}, {"end": 1000},
])
def test_invalid_source_bindings_and_ranges_preserve_draft_and_head(board_case, bad):
    case = board_case
    original = _draft(case, BoardCellData(value="Preserve these unsent edits"))
    invalid = BoardReferenceInput.model_validate({**_reference(case).model_dump(), **bad})
    with pytest.raises(MvpError):
        _draft(case, BoardCellData(value="Bad update", references=[invalid]), version=original.version)
    restored = case.boards.get_draft("saved_example", case.handle, case.definition.board_id,
        original.paper_id, original.field_id)
    assert restored == original
    assert case.boards.history("saved_example", case.handle, case.definition.board_id,
        original.paper_id, original.field_id).total == 0


def test_wrong_paper_reference_cannot_be_saved_to_another_report_cell(board_case):
    case = board_case
    with pytest.raises(MvpError):
        _draft(case, BoardCellData(value="Wrong paper", references=[_reference(case, 1)]))
    assert all(cell.draft_version == 0 and cell.head is None for cell in case.boards.view(
        "saved_example", case.handle, case.definition.board_id).cells)


@pytest.mark.parametrize("missing", ["reason", "inspection"])
def test_supported_value_requires_explicit_inspected_ranges_and_reason(board_case, missing):
    case = board_case
    reference = _reference(case)
    data = BoardCellData(value="Diversity", references=[reference],
        reason="" if missing == "reason" else "Software assertion",
        inspected_ranges=[] if missing == "inspection" else [reference],
        semantic_assessment="human_supported", scope_result="value_found")
    draft = _draft(case, data)
    with pytest.raises(MvpError):
        _submit(case, draft)
    assert case.boards.get_draft("saved_example", case.handle, case.definition.board_id,
        draft.paper_id, draft.field_id) == draft


def test_null_missing_scope_is_a_human_inspection_claim_not_source_absence(board_case):
    case = board_case
    reference = _reference(case, 1)
    draft = _draft(case, BoardCellData(value=None, inspected_ranges=[reference],
        semantic_assessment="unassessed", scope_result="not_found_in_inspected_material",
        missing_information="No fertility outcome in this abstract", reason="Only this abstract inspected"),
        paper_index=1, field="fertility")
    head = _submit(case, draft)
    assert head.value is None and head.references == []
    assert head.scope_result == "not_found_in_inspected_material"
    assert head.semantic_assessment == "unassessed"
    unavailable = _submit(case, _draft(case, BoardCellData(value=None,
        missing_information="No retained source text", reason="Source unavailable"),
        paper_index=2, field="fertility"), request_id="submit-unavailable")
    assert unavailable.scope_result == "not_assessed" and unavailable.inspected_ranges == []


@pytest.mark.parametrize("data", [BoardCellData(), BoardCellData(reason="Missing source"),
    BoardCellData(missing_information="No retained text")])
def test_submitted_null_requires_missing_information_and_reason_without_inventing_absence(board_case, data):
    case = board_case
    draft = _draft(case, data, paper_index=2, field="fertility")
    with pytest.raises(MvpError):
        _submit(case, draft)
    assert case.boards.get_draft("saved_example", case.handle, case.definition.board_id,
        draft.paper_id, draft.field_id) == draft


def test_simultaneous_draft_saves_have_one_winner_and_revision_is_explicit(board_case):
    case = board_case
    def save(value):
        try:
            return _draft(case, BoardCellData(value=value))
        except MvpError as error:
            return error
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, ["Tab one", "Tab two"]))
    winners = [result for result in results if not isinstance(result, MvpError)]
    assert len(winners) == 1
    assert len([result for result in results if isinstance(result, MvpError)]) == 1
    head = _submit(case, winners[0])
    assert _submit(case, winners[0]) == head  # Idempotent despite consumed draft.
    empty = case.boards.get_draft("saved_example", case.handle, case.definition.board_id,
                                  winners[0].paper_id, winners[0].field_id)
    assert empty.version == 0 and empty.data.value is None
    with pytest.raises(MvpError):
        _draft(case, BoardCellData(value="Implicit overwrite"))
    revision = _draft(case, BoardCellData(value="Explicit human revision"), head=head.id)
    with pytest.raises(MvpError):
        _submit(case, revision, request_id="wrong-parent")
    assert case.boards.get_draft("saved_example", case.handle, case.definition.board_id,
                                revision.paper_id, revision.field_id) == revision
    revised = _submit(case, revision, request_id="correct-parent", head=head.id)
    assert revised.supersedes_id == head.id
    assert case.boards.history("saved_example", case.handle, case.definition.board_id,
        revision.paper_id, revision.field_id).total == 2


def test_changed_field_or_sources_reject_stale_writes_but_keep_historical_judgment(board_case):
    case = board_case
    draft = _draft(case, BoardCellData(value="Old definition value"))
    head = _submit(case, draft)
    revised_request = BoardReviseRequest(**case.request.model_dump(exclude={"request_id", "fields"}),
        request_id="field-revision", expected_revision_id=case.definition.revision_id,
        fields=[BoardFieldInput(id="diet", label="Diet revised", subquestion="diet exposure"),
                *case.request.fields[1:]])
    revised = case.boards.revise("saved_example", case.handle, case.definition.board_id, revised_request)
    assert revised.definition.parent_revision_id == case.definition.revision_id
    assert all(cell.head is None for cell in revised.cells)
    with pytest.raises(MvpError):
        _draft(case, BoardCellData(value="Stale definition"), head=head.id)
    old = case.boards.view("saved_example", case.handle, case.definition.board_id,
                           revision_id=case.definition.revision_id)
    assert old.freshness == "historical" and any(cell.head and cell.head.id == head.id for cell in old.cells)
    assert case.boards.history("saved_example", case.handle, case.definition.board_id,
        draft.paper_id, draft.field_id, revision_id=case.definition.revision_id).items == [head]
    case.engine.prepare_sources(case.handle, PrepareSourcesRequest(request_id="new-source-state",
        search_id=case.search.id, paper_ids=case.prep.selected_paper_ids))
    with pytest.raises(MvpError):
        _draft(case, BoardCellData(value="Stale source"), revision=revised.definition.revision_id)
    assert case.boards.view("saved_example", case.handle, case.definition.board_id).freshness == "historical"


def test_exports_retain_original_bibliography_and_do_not_change_legacy_schema(board_case):
    case = board_case
    legacy_before = case.engine.export_workspace(case.handle)
    reference = _reference(case)
    head = _submit(case, _draft(case, BoardCellData(value="=1+1", references=[reference],
        inspected_ranges=[reference], scope_result="value_found", reason="Synthetic manual draft")))
    exported = case.boards.export("saved_example", case.handle, case.definition.board_id, history=True)
    audit = json.loads(exported.json_text)
    assert audit["schema_version"] == "mvp.board-audit.v1"
    assert "=1+1" in exported.json_text
    assert head.references[0].quote in exported.json_text
    rows = list(csv.reader(io.StringIO(exported.csv_text)))
    flattened = [value for row in rows for value in row]
    assert "'=1+1" in flattened
    assert "'=SYNTHETIC original report one" in flattened
    assert case.handle.token not in exported.json_text + exported.csv_text
    legacy_after = case.engine.export_workspace(case.handle)
    assert legacy_after.csv_text == legacy_before.csv_text
    assert {key: value for key, value in json.loads(legacy_after.json_text).items() if key != "exported_at"} == {
        key: value for key, value in json.loads(legacy_before.json_text).items() if key != "exported_at"}
    case.provider.papers = [paper.model_copy(update={"title": "CHANGED LATER BIBLIOGRAPHY"})
                            for paper in case.provider.papers]
    case.engine.search_literature(case.handle, SearchRequest(request_id="later-search", query="synthetic fixture"))
    reread = case.boards.export("saved_example", case.handle, case.definition.board_id, history=True)
    assert "=SYNTHETIC original report one" in reread.json_text
    assert "CHANGED LATER BIBLIOGRAPHY" not in reread.json_text
    # Board writes do not alter the old research export at all.
    # The later intentional search is the only engine mutation in this check.
    assert case.engine.get_workspace(case.handle).runs == []
    assert json.loads(legacy_before.json_text)["schema_version"] == "mvp.audit-bundle.v1"
    assert json.loads(case.engine.export_workspace(case.handle).json_text)["schema_version"] == "mvp.audit-bundle.v1"


def test_deleted_workspace_cannot_be_recreated_by_late_board_save(board_case):
    case = board_case
    draft = _draft(case, BoardCellData(value="Late edit"))
    case.registry.delete_workspace(case.session["token_hash"], case.handle.workspace_id,
        lambda mode, handle: case.engine.clear_workspace_if_present(handle),
        case.boards.delete_workspace)
    for operation in [lambda: _submit(case, draft), lambda: _draft(case),
                      lambda: case.boards.create("saved_example", case.handle, case.request)]:
        with pytest.raises(MvpError):
            operation()
    assert case.registry.is_deleted(case.handle.workspace_id)


def test_long_candidates_label_omission_and_canonical_inspector_paginates_unicode(board_case):
    case = board_case
    long_text = "microbial diversity " + ("😀 e\u0301 中文 " * 1000) + "FINAL_MARKER"
    case.provider.papers[0] = case.provider.papers[0].model_copy(update={"abstract": long_text})
    later = case.engine.search_literature(case.handle, SearchRequest(request_id="long-search", query="synthetic fixture"))
    case.prep = case.engine.prepare_sources(case.handle, PrepareSourcesRequest(request_id="long-prepare",
        search_id=later.id, paper_ids=[paper.id for paper in later.papers]))
    case.view = case.boards.create("saved_example", case.handle,
        case.request.model_copy(update={"request_id": "long-board", "preparation_id": case.prep.id}))
    case.definition = case.view.definition
    candidates = case.boards.candidates("saved_example", case.handle, case.definition.board_id,
        BoardCandidatesRequest(request_id="long-candidates", expected_revision_id=case.definition.revision_id,
            paper_id=case.prep.selected_paper_ids[0], field_id="diversity"))
    canonical_id = case.prep.sources[0].blocks[0].id
    candidate = next(item for item in candidates.candidates if item.reference.block_id == canonical_id)
    assert len(candidate.reference.quote) == MAX_CANDIDATE_CHARACTERS
    assert candidate.total_block_characters == len(long_text)
    assert candidate.omitted_characters == len(long_text) - MAX_CANDIDATE_CHARACTERS > 0
    reconstructed, start = [], 0
    while start < len(long_text):
        page = case.boards.blocks("saved_example", case.handle, case.definition.board_id,
            case.prep.sources[0].id, block_id=canonical_id, start=start)
        assert len(page.blocks) == 1
        chunk = page.blocks[0]
        assert chunk.start == start and chunk.end - chunk.start <= MAX_INSPECTOR_CHARACTERS
        assert chunk.omitted_before == start and chunk.omitted_after == len(long_text) - chunk.end
        assert chunk.text == long_text[chunk.start:chunk.end]
        reconstructed.append(chunk.text)
        start = chunk.end
    assert "".join(reconstructed) == long_text


def test_canonical_hash_tampering_is_detected_before_candidates_or_source_inspection(board_case):
    case = board_case
    with sqlite3.connect(case.root / "research.sqlite3") as db:
        snapshot = json.loads(db.execute("SELECT snapshot FROM mvp_workspaces WHERE id=?",
                                        (case.handle.workspace_id,)).fetchone()[0])
        snapshot["preparations"][0]["sources"][0]["blocks"][0]["text"] = "TAMPERED CANONICAL TEXT"
        db.execute("UPDATE mvp_workspaces SET snapshot=? WHERE id=?", (json.dumps(snapshot), case.handle.workspace_id))
    for operation in [
        lambda: case.boards.blocks("saved_example", case.handle, case.definition.board_id, case.prep.sources[0].id),
        lambda: case.boards.candidates("saved_example", case.handle, case.definition.board_id,
            BoardCandidatesRequest(request_id="tampered", expected_revision_id=case.definition.revision_id,
                paper_id=case.prep.selected_paper_ids[0], field_id="diversity"))]:
        with pytest.raises(MvpError) as failure:
            operation()
        assert failure.value.code == "source_integrity_error"
    with case.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM board_candidates").fetchone()[0] == 0


def test_reference_client_cannot_supply_authoritative_quote_or_non_codepoint_range(board_case):
    reference = _reference(board_case).model_dump()
    for changed in [{"quote": "Fabricated quote"}, {"start": True}, {"end": 1.5},
                    {"start": -1}, {"start": 3, "end": 3}]:
        with pytest.raises(ValidationError):
            BoardReferenceInput.model_validate({**reference, **changed})


def test_inspecting_later_candidate_reports_real_canonical_position_for_pagination(board_case):
    case = board_case
    source = case.prep.sources[0]
    assert len(source.blocks) >= 2
    inspection = case.boards.blocks("saved_example", case.handle, case.definition.board_id,
        source.id, block_id=source.blocks[1].id)
    assert inspection.blocks[0].block_id == source.blocks[1].id
    assert inspection.offset == 1
    assert inspection.offset + len(inspection.blocks) == inspection.total_blocks


@pytest.mark.parametrize("operation", ["candidate", "submission"])
def test_idempotent_replay_does_not_bypass_retained_source_integrity(board_case, operation):
    case = board_case
    if operation == "candidate":
        request = BoardCandidatesRequest(request_id="cached-candidate", expected_revision_id=case.definition.revision_id,
            paper_id=case.prep.selected_paper_ids[0], field_id="diversity")
        replay = lambda: case.boards.candidates("saved_example", case.handle, case.definition.board_id, request)
    else:
        draft = _draft(case, BoardCellData(value="Synthetic saved manual value"))
        replay = lambda: _submit(case, draft, request_id="cached-submission")
    first = replay()
    assert replay() == first
    with sqlite3.connect(case.root / "research.sqlite3") as db:
        snapshot = json.loads(db.execute("SELECT snapshot FROM mvp_workspaces WHERE id=?",
                                        (case.handle.workspace_id,)).fetchone()[0])
        snapshot["preparations"][0]["sources"][0]["blocks"][0]["text"] = "TAMPERED AFTER CACHED RESULT"
        db.execute("UPDATE mvp_workspaces SET snapshot=? WHERE id=?", (json.dumps(snapshot), case.handle.workspace_id))
    with pytest.raises(MvpError) as failure:
        replay()
    assert failure.value.code == "source_integrity_error"
