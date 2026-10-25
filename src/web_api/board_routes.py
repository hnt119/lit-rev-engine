"""Thin session-authorized routes for the manual comparison-board sidecar."""
from typing import Literal

from fastapi import Depends, Query, Response
from pydantic import ValidationError

from src.mvp.adapters.board_storage import BoardStore
from src.mvp.board_contracts import (
    BoardCandidates, BoardCandidatesRequest, BoardCellDraft, BoardCellHistory,
    BoardCellRevision, BoardCreateRequest, BoardDraftPutRequest, BoardListing,
    BoardReferenceContext, BoardReviseRequest, BoardSourceInspection,
    BoardSubmitRequest, BoardView, BoardPassageSearchContext, BoardPassageSourceContext,
)
from src.mvp.contracts import BoardPassageScope
from src.mvp.ports import MvpError
from src.mvp.evidence_board import EvidenceBoardService
from src.mvp.span_board_contracts import (
    ProfiledBoardCreateRequest, ProfiledBoardReviseRequest, BoardCandidatesResult,
)


def install_board_routes(app, *, directory, registry, service, owned, session_for, dependencies):
    boards = EvidenceBoardService(registry, service, BoardStore(directory / "evidence-boards.sqlite3"))
    app.state.boards = boards
    prefix = "/api/v1/workspaces/{workspace_id}/boards"

    def passage_scope(board_id, revision_id, paper_id, field_id):
        try:
            return BoardPassageScope(board_id=board_id, board_revision_id=revision_id,
                                     paper_id=paper_id, field_id=field_id)
        except ValidationError:
            raise MvpError('invalid_board_passage_scope', 'Choose an exact comparison revision and both cell identifiers, or neither.') from None

    @app.get(prefix + "/{board_id}/passage-search-context", response_model=BoardPassageSearchContext, dependencies=dependencies)
    def passage_search_context(workspace_id: str, board_id: str,
                               revision_id: str = Query(min_length=1, max_length=200),
                               paper_id: str | None = Query(default=None, min_length=1, max_length=200),
                               field_id: str | None = Query(default=None, min_length=1, max_length=100),
                               session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return boards.passage_search_context(mode, handle, passage_scope(board_id, revision_id, paper_id, field_id))

    @app.get(prefix + "/{board_id}/passage-source-context", response_model=BoardPassageSourceContext, dependencies=dependencies)
    def passage_source_context(workspace_id: str, board_id: str,
                               revision_id: str = Query(min_length=1, max_length=200),
                               paper_id: str = Query(min_length=1, max_length=200),
                               field_id: str = Query(min_length=1, max_length=100),
                               run_id: str = Query(min_length=1, max_length=200),
                               passage_id: str = Query(min_length=1, max_length=200),
                               session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return boards.passage_source_context(mode, handle,
            passage_scope(board_id, revision_id, paper_id, field_id), run_id, passage_id)

    @app.get(prefix, response_model=BoardListing, dependencies=dependencies)
    def listing(workspace_id: str, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return boards.listing(mode, handle)

    @app.post(prefix, response_model=BoardView, dependencies=dependencies)
    def create(workspace_id: str, request: BoardCreateRequest | ProfiledBoardCreateRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return boards.create(mode, handle, request)

    @app.get(prefix + "/{board_id}", response_model=BoardView, dependencies=dependencies)
    def view(workspace_id: str, board_id: str, revision_id: str | None = None, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return boards.view(mode, handle, board_id, revision_id=revision_id)

    @app.post(prefix + "/{board_id}/revisions", response_model=BoardView, dependencies=dependencies)
    def revise(workspace_id: str, board_id: str, request: BoardReviseRequest | ProfiledBoardReviseRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return boards.revise(mode, handle, board_id, request)

    @app.post(prefix + "/{board_id}/candidates", response_model=BoardCandidatesResult, dependencies=dependencies)
    def candidates(workspace_id: str, board_id: str, request: BoardCandidatesRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return boards.candidates(mode, handle, board_id, request)

    @app.get(prefix + "/{board_id}/drafts/{paper_id}/{field_id}", response_model=BoardCellDraft, dependencies=dependencies)
    def get_draft(workspace_id: str, board_id: str, paper_id: str, field_id: str,
                  revision_id: str | None = None, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return boards.get_draft(mode, handle, board_id, paper_id, field_id, revision_id=revision_id)

    @app.put(prefix + "/{board_id}/drafts/{paper_id}/{field_id}", response_model=BoardCellDraft, dependencies=dependencies)
    def put_draft(workspace_id: str, board_id: str, paper_id: str, field_id: str,
                  request: BoardDraftPutRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return boards.put_draft(mode, handle, board_id, paper_id, field_id, request)

    @app.post(prefix + "/{board_id}/cell-revisions", response_model=BoardCellRevision, dependencies=dependencies)
    def submit(workspace_id: str, board_id: str, request: BoardSubmitRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return boards.submit(mode, handle, board_id, request)

    @app.get(prefix + "/{board_id}/cells/{paper_id}/{field_id}/history", response_model=BoardCellHistory, dependencies=dependencies)
    def history(workspace_id: str, board_id: str, paper_id: str, field_id: str,
                revision_id: str | None = None, offset: int = Query(default=0, ge=0),
                limit: int = Query(default=20, ge=1, le=50), session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return boards.history(mode, handle, board_id, paper_id, field_id,
                              revision_id=revision_id, offset=offset, limit=limit)

    @app.get(prefix + "/{board_id}/sources/{source_id}/blocks", response_model=BoardSourceInspection, dependencies=dependencies)
    def blocks(workspace_id: str, board_id: str, source_id: str,
               revision_id: str | None = None, offset: int = Query(default=0, ge=0),
               limit: int = Query(default=1, ge=1, le=3), block_id: str | None = None,
               start: int = Query(default=0, ge=0), session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return boards.blocks(mode, handle, board_id, source_id, revision_id=revision_id,
                             offset=offset, limit=limit, block_id=block_id, start=start)

    @app.get(prefix + "/{board_id}/references/{reference_id}/context", response_model=BoardReferenceContext, dependencies=dependencies)
    def reference_context(workspace_id: str, board_id: str, reference_id: str,
                          revision_id: str | None = None, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return boards.reference_context(mode, handle, board_id, reference_id, revision_id=revision_id)

    @app.get(prefix + "/{board_id}/exports", dependencies=dependencies)
    def export(workspace_id: str, board_id: str, format: Literal["csv", "json"] = "csv",
               revision_id: str | None = None, history: bool = False, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        value = boards.export(mode, handle, board_id, revision_id=revision_id, history=history)
        return Response(value.csv_text if format == "csv" else value.json_text,
                        media_type="text/csv" if format == "csv" else "application/json",
                        headers={"Content-Disposition": f'attachment; filename="comparison-board.{format}"'})

    return boards
