"""Loopback-only FastAPI adapter; all research operations use MVPService.

Run one provider-owning API process. Normal ``def`` endpoints run in Starlette's
thread pool; an explicit eight-operation gate bounds concurrent blocking work.
The Next.js bridge forwards only this API and preserves the original Origin.
"""
from datetime import datetime, timezone
import os
from pathlib import Path
from threading import BoundedSemaphore
from typing import Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.mvp.bootstrap import ROOT, build_service, public_runtime_info
from src.mvp.contracts import (
    Assessment, BoundRetrieveEvidenceRequest, ClearResult, CreateWorkspaceRequest,
    EvidenceRun, PrepareSourcesRequest, QuerySuggestion, QuerySuggestionRequest,
    SaveAssessmentRequest, SearchPreview, SearchRequest, SourceContextRequest,
)
from src.mvp.ports import MvpError
from src.mvp.workspace_ui import WorkspaceUIStore, private_directory
from .contracts import (
    Capabilities, ContextView, CreateWebWorkspace, DraftRecord, DraftUpdate,
    PreparationView, RunView, SessionInfo, WorkspaceList, WorkspaceSummary,
)
from .projections import preparation_view, source_metadata, workspace_summary

COOKIE_NAME = "litrev_local_session"
PREFIX = "/api/v1"
MAX_REQUEST_BYTES = 1024 * 1024


def _loopback_configuration(allowed_host, allowed_origin):
    backend = urlsplit("http://" + allowed_host)
    origin = urlsplit(allowed_origin)
    loopback = {"127.0.0.1", "localhost", "::1"}
    if (backend.hostname not in loopback or backend.netloc != allowed_host or backend.path
            or origin.hostname not in loopback or origin.scheme not in {"http", "https"}
            or origin.path or origin.query or origin.fragment or origin.username or origin.password):
        raise ValueError("The local API Host and application Origin must be exact loopback origins")


def create_app(data_dir=None, *, allowed_host="127.0.0.1:8765",
               allowed_origin="http://127.0.0.1:3000", services=None, ui_store=None, map_embedder=None):
    _loopback_configuration(allowed_host, allowed_origin)
    directory = private_directory(Path(data_dir or os.environ.get("MVP_WEB_DATA_DIR") or ROOT / ".mvp-web-state"))
    registry = ui_store or WorkspaceUIStore(directory / "web-credentials.sqlite3")
    services = services if services is not None else {}
    gate = BoundedSemaphore(8)
    app = FastAPI(title="Literature Review Engine local adapter", version="0.2.0", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.registry, app.state.services = registry, services
    app.state.data_dir = directory

    def service(mode):
        # build_service itself shares provider objects and rate gates per process.
        if mode not in services:
            services[mode] = build_service(mode, directory)
        return services[mode]

    def bounded():
        if not gate.acquire(blocking=False):
            raise MvpError("server_busy", "The local server is busy. Retry this operation explicitly.", True)
        try:
            yield
        finally:
            gate.release()

    @app.middleware("http")
    async def local_boundary(request, call_next):
        if request.headers.get("host") != allowed_host:
            return JSONResponse({"error": {"code": "invalid_host", "message": "Use the configured local application origin.", "retryable": False}}, 403)
        origin = request.headers.get("origin")
        if (origin is not None and origin != allowed_origin) or (request.method not in {"GET", "HEAD"} and origin != allowed_origin):
            return JSONResponse({"error": {"code": "invalid_origin", "message": "Mutation requires the configured local application origin.", "retryable": False}}, 403)
        content_length = request.headers.get("content-length")
        try:
            oversized = content_length is not None and (int(content_length) < 0 or int(content_length) > MAX_REQUEST_BYTES)
        except ValueError:
            oversized = True
        if oversized:
            return JSONResponse({"error": {"code": "request_limit", "message": "Request exceeds the local JSON size limit.", "retryable": False}}, 413)
        if request.method not in {"GET", "HEAD"}:
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > MAX_REQUEST_BYTES:
                    return JSONResponse({"error": {"code": "request_limit", "message": "Request exceeds the local JSON size limit.", "retryable": False}}, 413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(MvpError)
    async def safe_domain_error(request, error):
        missing = error.code.startswith("unknown_") or error.code in {"workspace_access_denied", "session_unavailable"}
        conflict = error.code.startswith("stale_") or error.code in {"idempotency_conflict", "workspace_conflict"}
        status = 404 if missing else 409 if conflict else 503 if error.retryable or error.code == "server_busy" else 422
        return JSONResponse({"error": {"code": error.code, "message": error.message, "retryable": error.retryable}}, status)

    @app.exception_handler(RequestValidationError)
    async def safe_validation_error(request, error):
        return JSONResponse({"error": {"code": "invalid_fields", "message": "Check the supplied fields.", "retryable": False,
                                      "fields": [{"loc": list(item["loc"]), "message": item["msg"]} for item in error.errors()]}}, 422)

    def session_for(request: Request):
        session = registry.resolve_session(request.cookies.get(COOKIE_NAME))
        if session is None:
            raise MvpError("session_unavailable", "Local browser session expired or was cleared. Create a new workspace; UUID-only recovery is not available.")
        if request.method not in {"GET", "HEAD"} and not registry.check_csrf(session, request.headers.get("X-CSRF-Token")):
            # A safe domain failure is normally422; CSRF explicitly403 below.
            from fastapi import HTTPException
            raise HTTPException(403, detail={"code": "invalid_csrf", "message": "Refresh the local session before saving."})
        return session

    def owned(workspace_id, session):
        mode, handle = registry.workspace(session["token_hash"], workspace_id)
        return mode, handle, service(mode)

    def find(items, identifier, kind):
        item = next((item for item in items if item.id == identifier), None)
        if item is None:
            raise MvpError("unknown_" + kind, "The requested resource does not belong to this workspace.")
        return item

    dependencies = [Depends(bounded)]

    @app.get(PREFIX + "/session", response_model=SessionInfo, dependencies=dependencies)
    def bootstrap_session(request: Request, response: Response):
        token, session = registry.session(request.cookies.get(COOKIE_NAME))
        remaining = max(0, int((datetime.fromisoformat(session["expires_at"]) - datetime.now(timezone.utc)).total_seconds()))
        response.set_cookie(COOKIE_NAME, token, max_age=remaining, httponly=True, samesite="strict", secure=allowed_origin.startswith("https:"), path="/")
        return SessionInfo(csrf_token=session["csrf"], expires_at=session["expires_at"])

    @app.get(PREFIX + "/capabilities", response_model=Capabilities, dependencies=dependencies)
    def capabilities():
        from .contracts import MapCapability
        ready, reason = app.state.maps.readiness()
        return Capabilities(**public_runtime_info(), map=MapCapability(ready=ready, reason=reason))

    @app.get(PREFIX + "/workspaces", response_model=WorkspaceList, dependencies=dependencies)
    def list_workspaces(session=Depends(session_for)):
        output = []
        for identifier in registry.workspace_ids(session["token_hash"]):
            mode, handle, engine = owned(identifier, session)
            output.append(workspace_summary(engine.get_workspace(handle), mode))
        return WorkspaceList(workspaces=output)

    @app.post(PREFIX + "/workspaces", response_model=WorkspaceSummary, dependencies=dependencies)
    def create_workspace(request: CreateWebWorkspace, session=Depends(session_for)):
        handle = registry.create_workspace(session["token_hash"], request.request_id, request.model_dump(mode="json"), lambda handle: service(request.mode).create_reserved_workspace(handle, CreateWorkspaceRequest(question=request.question)))
        return workspace_summary(service(request.mode).get_workspace(handle), request.mode)

    @app.get(PREFIX + "/workspaces/{workspace_id}", response_model=WorkspaceSummary, dependencies=dependencies)
    def get_workspace(workspace_id: str, session=Depends(session_for)):
        mode, handle, engine = owned(workspace_id, session)
        return workspace_summary(engine.get_workspace(handle), mode)

    @app.post(PREFIX + "/workspaces/{workspace_id}/query-suggestions", response_model=QuerySuggestion, dependencies=dependencies)
    def suggest_query(workspace_id: str, request: QuerySuggestionRequest, session=Depends(session_for)):
        _, handle, engine = owned(workspace_id, session)
        return engine.suggest_query(handle, request)

    @app.post(PREFIX + "/workspaces/{workspace_id}/searches", response_model=SearchPreview, dependencies=dependencies)
    def search(workspace_id: str, request: SearchRequest, session=Depends(session_for)):
        mode, handle, engine = owned(workspace_id, session)
        preview = engine.search_literature(handle, request)
        app.state.maps.install_saved_example(mode, handle, preview.id)
        return preview

    @app.get(PREFIX + "/workspaces/{workspace_id}/searches/{search_id}/papers", response_model=SearchPreview, dependencies=dependencies)
    def papers(workspace_id: str, search_id: str, session=Depends(session_for)):
        _, handle, engine = owned(workspace_id, session)
        return find(engine.get_workspace(handle).searches, search_id, "search")

    @app.post(PREFIX + "/workspaces/{workspace_id}/source-preparations", response_model=PreparationView, dependencies=dependencies)
    def prepare(workspace_id: str, request: PrepareSourcesRequest, session=Depends(session_for)):
        _, handle, engine = owned(workspace_id, session)
        return preparation_view(engine.prepare_sources(handle, request))

    @app.get(PREFIX + "/workspaces/{workspace_id}/source-preparations/{preparation_id}", response_model=PreparationView, dependencies=dependencies)
    def preparation(workspace_id: str, preparation_id: str, session=Depends(session_for)):
        _, handle, engine = owned(workspace_id, session)
        return preparation_view(find(engine.get_workspace(handle).preparations, preparation_id, "preparation"))

    @app.post(PREFIX + "/workspaces/{workspace_id}/evidence-runs", response_model=EvidenceRun, dependencies=dependencies)
    def retrieve(workspace_id: str, request: BoundRetrieveEvidenceRequest, session=Depends(session_for)):
        _, handle, engine = owned(workspace_id, session)
        return engine.retrieve_evidence_bound(handle, request)

    @app.get(PREFIX + "/workspaces/{workspace_id}/runs/{run_id}", response_model=RunView, dependencies=dependencies)
    def run(workspace_id: str, run_id: str, assessment_offset: int = Query(default=0, ge=0),
            assessment_limit: int = Query(default=20, ge=1, le=50), session=Depends(session_for)):
        _, handle, engine = owned(workspace_id, session)
        state = engine.get_workspace(handle)
        result = find(state.runs, run_id, "run")
        history = [item for item in reversed(state.assessments) if item.run_id == run_id]
        head = history[0] if history else None
        current = result.source_revision == state.source_revision and bool(state.preparations) and result.preparation_id == state.preparations[-1].id
        return RunView(run=result, current=current, assessment_head=head, assessment_history=history[assessment_offset:assessment_offset + assessment_limit],
                       assessment_total=len(history), next_assessment_offset=assessment_offset + assessment_limit if assessment_offset + assessment_limit < len(history) else None)

    @app.get(PREFIX + "/workspaces/{workspace_id}/runs/{run_id}/passages/{passage_id}/context", response_model=ContextView, dependencies=dependencies)
    def context(workspace_id: str, run_id: str, passage_id: str, archived: bool = False,
                offset: int = Query(default=0, ge=0), limit: int = Query(default=5, ge=1, le=10), session=Depends(session_for)):
        _, handle, engine = owned(workspace_id, session)
        request = SourceContextRequest(run_id=run_id, passage_id=passage_id)
        value = engine.get_historical_source_context(handle, request) if archived else engine.get_source_context(handle, request)
        state = engine.get_workspace(handle)
        result = find(state.runs, run_id, "run")
        current = result.source_revision == state.source_revision and bool(state.preparations) and result.preparation_id == state.preparations[-1].id
        total = len(value.source.blocks)
        blocks = value.source.blocks[offset:offset + limit]
        return ContextView(run_id=run_id, passage=value.passage, paper=value.paper, source=source_metadata(value.source), block=value.block,
                           blocks=blocks, offset=offset, total_blocks=total, next_offset=offset + limit if offset + limit < total else None,
                           archived=archived, current=current)

    def validate_scope(state, scope, expected_head=None, writing=False):
        if scope in {"discover", "evidence"}:
            return
        if scope.startswith("selection:"):
            find(state.searches, scope.removeprefix("selection:"), "search")
            return
        if scope.startswith("assessment:"):
            run_id = scope.removeprefix("assessment:")
            find(state.runs, run_id, "run")
            head = next((item.id for item in reversed(state.assessments) if item.run_id == run_id), None)
            if writing and expected_head != head:
                raise MvpError("stale_assessment_draft", "A newer assessment exists. Keep your draft for comparison before revising.")
            return
        raise MvpError("invalid_draft_scope", "Choose a supported workspace screen or saved search/run draft scope.")

    @app.get(PREFIX + "/workspaces/{workspace_id}/drafts/{scope}", response_model=DraftRecord, dependencies=dependencies)
    def get_draft(workspace_id: str, scope: str, session=Depends(session_for)):
        _, handle, engine = owned(workspace_id, session)
        validate_scope(engine.get_workspace(handle), scope)
        return DraftRecord(**registry.draft(workspace_id, scope))

    @app.put(PREFIX + "/workspaces/{workspace_id}/drafts/{scope}", response_model=DraftRecord, dependencies=dependencies)
    def put_draft(workspace_id: str, scope: str, request: DraftUpdate, session=Depends(session_for)):
        _, handle, engine = owned(workspace_id, session)
        def save_under_guard(state):
            validate_scope(state, scope, request.expected_assessment_head, writing=True)
            return DraftRecord(**registry.put_draft(workspace_id, scope, **request.model_dump(mode="json")))
        return engine.with_workspace_state(handle, save_under_guard)

    @app.post(PREFIX + "/workspaces/{workspace_id}/assessments", response_model=Assessment, dependencies=dependencies)
    def assess(workspace_id: str, request: SaveAssessmentRequest, session=Depends(session_for)):
        _, handle, engine = owned(workspace_id, session)
        return engine.save_assessment(handle, request)

    @app.get(PREFIX + "/workspaces/{workspace_id}/exports", dependencies=dependencies)
    def export(workspace_id: str, format: Literal["csv", "json"] = "csv", session=Depends(session_for)):
        _, handle, engine = owned(workspace_id, session)
        value = engine.export_workspace(handle)
        body = value.csv_text if format == "csv" else value.json_text
        return Response(body, media_type="text/csv" if format == "csv" else "application/json", headers={"Content-Disposition": f'attachment; filename="evidence.{format}"'})

    @app.delete(PREFIX + "/workspaces/{workspace_id}", response_model=ClearResult, dependencies=dependencies)
    def delete(workspace_id: str, session=Depends(session_for)):
        registry.delete_workspace(session["token_hash"], workspace_id, lambda mode, handle: service(mode).clear_workspace_if_present(handle), app.state.maps.delete_workspace)
        return ClearResult()

    from .map_routes import install_map_routes
    install_map_routes(app, directory=directory, registry=registry, service=service, owned=owned,
                       session_for=session_for, dependencies=dependencies, embedder=map_embedder)
    return app


def app_factory():
    return create_app(allowed_host=os.environ.get("MVP_API_HOST", "127.0.0.1:8765"), allowed_origin=os.environ.get("MVP_WEB_ORIGIN", "http://127.0.0.1:3000"))
