"""Authorized optional proposals; generation never runs during a read."""
from fastapi import Depends, Query, Response
from copy import copy
from src.mvp.ports import MvpError
from src.mvp.contracts import new_id, digest
from .settings_routes import RuntimeProposalRequest, configured_adapter, core_request, disclosure, packet_data

from src.mvp.board_contracts import BoardCellDraft, BoardReferenceContext
from src.mvp.proposal_contracts import (
    CellProposal, ProposalAdoptRequest, ProposalAudit, ProposalCapability,
    ProposalDismissRequest, ProposalGenerateRequest, ProposalListing, ProposalRun,
)


def install_proposal_routes(app, *, proposals, owned, session_for, dependencies):
    app.state.proposals = proposals
    prefix = "/api/v1/workspaces/{workspace_id}/boards/{board_id}"

    def for_session(session, revision=None):
        settings = getattr(app.state, 'runtime_settings', None)
        if settings is None: return proposals, None
        adapter, snapshot = configured_adapter(settings, session['token_hash'], 'proposals', revision)
        if not snapshot['configured']: return proposals, snapshot
        selected = copy(proposals)
        selected.adapter = adapter
        return selected, snapshot

    def capability_for(selected, snapshot):
        result = selected.capabilities()
        if snapshot and snapshot['configured']:
            ai = snapshot['preferences']['ai']
            result = result.model_copy(update={'settings_revision': snapshot['revision'], 'provider': ai['provider'],
                'paid_calls': ai['provider'] in {'openai', 'deepseek'},
                'reason': ('Session provider configured, not live-tested. Each run requires explicit data/cost consent.' if result.enabled
                           else 'Generation disabled or the session key is missing. Configure Research & AI Settings; manual comparison remains available.')})
        return hosted_capability(result)

    def binding(workspace_id, board_id, request):
        return dict(task='proposals', workspace_id=workspace_id, board_id=board_id,
                    request=core_request(request, ProposalGenerateRequest).model_dump(mode='json'))

    @app.post(prefix + '/prepare-generation', dependencies=dependencies)
    def prepare_generation(workspace_id: str, board_id: str, request: RuntimeProposalRequest, session=Depends(session_for)):
        from src.mvp.board_contracts import BoardCandidatesRequest
        from src.mvp.adapters.cell_generation import build_packet
        from src.mvp.adapters.span_packets import build_span_packet
        from src.mvp.span_board_contracts import SPAN_BOARD_PROFILE
        mode, handle, _ = owned(workspace_id, session)
        selected, snapshot = for_session(session, request.settings_revision)
        settings = getattr(app.state, 'runtime_settings', None)
        if settings is None or not snapshot or not snapshot['configured'] or request.settings_revision != snapshot['revision'] or not selected.capabilities().enabled:
            raise MvpError('generation_configuration', 'Enable proposals and provide the current session configuration/key in Settings.')
        view = proposals.boards.view(mode, handle, board_id)
        definition = view.definition
        if definition.revision_id != request.expected_revision_id or view.freshness != 'current':
            raise MvpError('stale_board_revision', 'Prepare proposals from the exact current comparison and retained sources.')
        packets = []
        seed = new_id()
        for pi, paper in enumerate(request.paper_ids):
            candidates = [proposals.boards.candidates(mode, handle, board_id, BoardCandidatesRequest(
                request_id=f'consent:{seed}:{pi}:{fi}', expected_revision_id=definition.revision_id,
                paper_id=paper, field_id=field)) for fi, field in enumerate(request.field_ids)]
            builder = build_span_packet if definition.retrieval_profile.get('profile_id') == SPAN_BOARD_PROFILE else build_packet
            packets.append(builder(definition, paper, candidates).model_dump(mode='json'))
        return settings.prepare(session['token_hash'], snapshot['revision'], binding(workspace_id, board_id, request),
            disclosure(selected.adapter, 'proposals', packets, len(packets)),
            packet_hashes={packet['paper_id']: digest(packet_data(packet)) for packet in packets})

    def hosted_capability(capability):
        if getattr(getattr(app.state, "deployment", None), "hosted", False):
            return capability.model_copy(update={"reason": "AI cell proposals are unavailable in this hosted release. A local laptop model is not part of this deployment; manual comparison remains available."})
        return capability

    @app.get(prefix + "/proposal-capabilities", response_model=ProposalCapability, dependencies=dependencies)
    def capabilities(workspace_id: str, board_id: str, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        proposals.boards.view(mode, handle, board_id)
        selected, snapshot = for_session(session)
        result = capability_for(selected, snapshot)
        if app.state.proposal_configuration_error and not (snapshot and snapshot['configured']):
            result = result.model_copy(update={"reason": "Invalid generation configuration: " + app.state.proposal_configuration_error})
        return hosted_capability(result)

    @app.post(prefix + "/proposal-runs", response_model=ProposalRun, dependencies=dependencies)
    def generate(workspace_id: str, board_id: str, request: RuntimeProposalRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        selected, snapshot = for_session(session, request.settings_revision)
        if not snapshot or not snapshot['configured']:
            return selected.generate(mode, handle, board_id, core_request(request, ProposalGenerateRequest))
        if request.settings_revision != snapshot['revision']:
            raise MvpError('stale_settings', 'Review the current generation configuration.')
        settings = app.state.runtime_settings
        with settings.generation_slot():
            selected.adapter.expected_packet_hashes = settings.consume(session['token_hash'], snapshot['revision'], request.consent_id,
                             binding(workspace_id, board_id, request))
            return selected.generate(mode, handle, board_id, core_request(request, ProposalGenerateRequest))

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
        selected, snapshot = for_session(session)
        result = selected.listing(mode, handle, board_id, revision_id, paper_id=paper_id,
                                   field_id=field_id, offset=offset, limit=limit)
        return result.model_copy(update={"capability": capability_for(selected, snapshot)})

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
