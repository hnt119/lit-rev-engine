"""Owned local review-pilot endpoints delegating to ReviewStore and MVP services."""
from fastapi import Depends, Query, Response

from src.mvp.ports import MvpError
from src.mvp.review_pilot import ReviewPilotService
from .pilot_contracts import (
    PilotCaptureRequest, PilotCreateRequest, PilotDecisionRequest, PilotFileRequest,
    PilotHandoffRequest, PilotMutation, PilotProtocolRequest, PilotRetrievalRequest,
    PilotSourceRequest,
)


def install_pilot_routes(app, *, directory, registry, service, owned, session_for, dependencies):
    pilots = ReviewPilotService(directory, registry, service, app.state.boards)
    app.state.review_pilots = pilots
    prefix = '/api/v1/workspaces/{workspace_id}/review-pilot'

    def context(workspace_id, session):
        mode, handle, _ = owned(workspace_id, session)
        if app.state.deployment.hosted:
            raise MvpError('pilot_local_only', 'This research checkpoint is available in local mode only; hosted deployment remains deferred.')
        return mode, handle

    @app.get(prefix, dependencies=dependencies)
    def view(workspace_id: str, offset: int = Query(default=0, ge=0),
             limit: int = Query(default=50, ge=1, le=50), session=Depends(session_for)):
        mode, handle = context(workspace_id, session)
        return pilots.view(mode, handle, offset=offset, limit=limit)

    @app.post(prefix, dependencies=dependencies)
    def initialize(workspace_id: str, request: PilotCreateRequest, session=Depends(session_for)):
        mode, handle = context(workspace_id, session)
        return pilots.initialize(mode, handle, request.model_dump(mode='json'))

    @app.post(prefix+'/protocols', dependencies=dependencies)
    def protocols(workspace_id: str, request: PilotProtocolRequest, session=Depends(session_for)):
        mode, handle = context(workspace_id, session)
        return pilots.mutate(mode, handle, 'revise_protocol', request.model_dump(mode='json'))

    @app.post(prefix+'/intakes/public-example', dependencies=dependencies)
    def public_example(workspace_id: str, request: PilotMutation, session=Depends(session_for)):
        mode, handle = context(workspace_id, session)
        return pilots.import_public_example(mode, handle, request.model_dump(mode='json'))

    @app.post(prefix+'/intakes/file', dependencies=dependencies)
    def file(workspace_id: str, request: PilotFileRequest, session=Depends(session_for)):
        mode, handle = context(workspace_id, session)
        return pilots.import_file(mode, handle, request.model_dump(mode='json'))

    @app.post(prefix+'/intakes/pubmed-capture', dependencies=dependencies)
    def capture(workspace_id: str, request: PilotCaptureRequest, session=Depends(session_for)):
        mode, handle = context(workspace_id, session)
        return pilots.import_capture(mode, handle, request.model_dump(mode='json'))

    @app.post(prefix+'/decisions', dependencies=dependencies)
    def decision(workspace_id: str, request: PilotDecisionRequest, session=Depends(session_for)):
        mode, handle = context(workspace_id, session)
        return pilots.mutate(mode, handle, 'record_decision', request.model_dump(mode='json'))

    @app.post(prefix+'/retrieval-status', dependencies=dependencies)
    def retrieval_status(workspace_id: str, request: PilotRetrievalRequest, session=Depends(session_for)):
        mode, handle = context(workspace_id, session)
        return pilots.mutate(mode, handle, 'set_status', request.model_dump(mode='json'))

    @app.post(prefix+'/sources', dependencies=dependencies)
    def attach(workspace_id: str, request: PilotSourceRequest, session=Depends(session_for)):
        mode, handle = context(workspace_id, session)
        return pilots.attach_source(mode, handle, request.model_dump(mode='json'))

    @app.get(prefix+'/sources/{document_id}', dependencies=dependencies)
    def source(workspace_id: str, document_id: str, offset: int = Query(default=0, ge=0),
               limit: int = Query(default=10, ge=1, le=50), session=Depends(session_for)):
        mode, handle = context(workspace_id, session)
        return pilots.source(mode, handle, document_id, offset=offset, limit=limit)

    @app.post(prefix+'/handoffs', dependencies=dependencies)
    def handoff(workspace_id: str, request: PilotHandoffRequest, session=Depends(session_for)):
        mode, handle = context(workspace_id, session)
        return pilots.handoff(mode, handle, request.model_dump(mode='json'))

    @app.get(prefix+'/exports', dependencies=dependencies)
    def export(workspace_id: str, session=Depends(session_for)):
        mode, handle = context(workspace_id, session)
        return Response(pilots.export(mode, handle), media_type='application/zip',
            headers={'Content-Disposition':'attachment; filename="review-pilot-audit.zip"'})
