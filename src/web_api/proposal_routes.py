"""Authorized optional proposals; generation never runs during a read."""
from fastapi import Depends, Query, Response

from src.mvp.board_contracts import BoardCellDraft, BoardReferenceContext
from src.mvp.proposal_contracts import (
    CellProposal, ProposalAdoptRequest, ProposalAudit, ProposalCapability,
    ProposalDismissRequest, ProposalGenerateRequest, ProposalListing, ProposalRun,
)


def install_proposal_routes(app, *, proposals, owned, session_for, dependencies):
    app.state.proposals = proposals
    prefix = "/api/v1/workspaces/{workspace_id}/boards/{board_id}"

    @app.get(prefix + "/proposal-capabilities", response_model=ProposalCapability, dependencies=dependencies)
    def capabilities(workspace_id: str, board_id: str, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        proposals.boards.view(mode, handle, board_id)
        result = proposals.capabilities()
        if app.state.proposal_configuration_error:
            result = result.model_copy(update={"reason": "Invalid generation configuration: " + app.state.proposal_configuration_error})
        return result

    @app.post(prefix + "/proposal-runs", response_model=ProposalRun, dependencies=dependencies)
    def generate(workspace_id: str, board_id: str, request: ProposalGenerateRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return proposals.generate(mode, handle, board_id, request)

    @app.get(prefix + "/proposal-runs/{run_id}", response_model=ProposalRun, dependencies=dependencies)
    def run(workspace_id: str, board_id: str, run_id: str, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return proposals.get_run(mode, handle, board_id, run_id)

    @app.get(prefix + "/proposals", response_model=ProposalListing, dependencies=dependencies)
    def listing(workspace_id: str, board_id: str, revision_id: str,
                paper_id: str | None = None, field_id: str | None = None,
                offset: int = Query(default=0, ge=0), limit: int = Query(default=10, ge=1, le=20),
                session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return proposals.listing(mode, handle, board_id, revision_id, paper_id=paper_id,
                                 field_id=field_id, offset=offset, limit=limit)

    @app.post(prefix + "/proposals/{proposal_id}/dismiss", response_model=CellProposal, dependencies=dependencies)
    def dismiss(workspace_id: str, board_id: str, proposal_id: str, request: ProposalDismissRequest,
                session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return proposals.dismiss(mode, handle, board_id, proposal_id, request)

    @app.post(prefix + "/proposals/{proposal_id}/adopt", response_model=BoardCellDraft, dependencies=dependencies)
    def adopt(workspace_id: str, board_id: str, proposal_id: str, request: ProposalAdoptRequest,
              session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return proposals.adopt(mode, handle, board_id, proposal_id, request)

    @app.get(prefix + "/proposals/{proposal_id}/references/{reference_id}/context",
             response_model=BoardReferenceContext, dependencies=dependencies)
    def context(workspace_id: str, board_id: str, proposal_id: str, reference_id: str,
                session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return proposals.context(mode, handle, board_id, proposal_id, reference_id)

    @app.get(prefix + "/proposal-audit", dependencies=dependencies)
    def export(workspace_id: str, board_id: str, revision_id: str, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        audit: ProposalAudit = proposals.export(mode, handle, board_id, revision_id)
        return Response(audit.model_dump_json(indent=2), media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="cell-proposals.json"'})
