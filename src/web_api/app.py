"""Internal FastAPI adapter; all research operations use MVPService.

Run one provider-owning API process. Normal ``def`` endpoints run in Starlette's
thread pool; an explicit eight-operation gate bounds concurrent blocking work.
The Next.js bridge forwards only this API and preserves the original Origin.
"""
from datetime import datetime, timezone
import os
from pathlib import Path
import re
from threading import BoundedSemaphore
from typing import Literal

from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from pydantic import BaseModel, ConfigDict, Field

from src.mvp.bootstrap import ROOT, build_service, public_runtime_info
from src.mvp.contracts import (
    Assessment, BoundRetrieveEvidenceRequest, ClearResult, CreateWorkspaceRequest,
    EvidenceRun, PrepareSourcesRequest, QuerySuggestion, QuerySuggestionRequest,
    SaveAssessmentRequest, SearchPreview, SearchRequest, SelectionDraft, SourceContextRequest,
)
from src.mvp.ports import MvpError
from src.mvp.workspace_versions import CollectionEvidenceRun
from src.mvp.workspace_ui import WorkspaceUIStore, private_directory
from src.mvp.usability_draft_contracts import (
    ComparisonHandoffDraft, ImportIntakeDraft, SearchPlanEditorDraft, usability_scope,
    validate_handoff_state, validate_handoff_update,
)
from .contracts import (
    Capabilities, ContextView, CreateWebWorkspace, DraftRecord, DraftUpdate,
    CollectionPreparationView, PreparationPapers, PreparationView, RunPapers, RunView, SessionInfo, WorkspaceList, WorkspaceSummary,
)
from .projections import preparation_view, source_metadata, workspace_summary
from .deployment import DeploymentConfig, validate_local
from .hosted_admission import (
    ADMISSION_COOKIE, ADMISSION_SECONDS, HOSTED_SESSION_COOKIE, AdmissionDenied,
    HostedAdmissionStore, expensive_request,
)

COOKIE_NAME = "litrev_local_session"
PREFIX = "/api/v1"
MAX_REQUEST_BYTES = 1024 * 1024


def _loopback_configuration(allowed_host, allowed_origin):
    validate_local(allowed_host, allowed_origin)


class AdmissionLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=32, max_length=256)


def create_app(data_dir=None, *, allowed_host="127.0.0.1:8765",
               allowed_origin="http://127.0.0.1:3000", services=None, ui_store=None, map_embedder=None,
               proposal_adapter=None, metadata_resolver=None, search_diagnostics=None, search_planner=None,
               deployment=None):
    # Existing explicit factory arguments remain local unless hosted mode was
    # deliberately configured. An environment cannot silently weaken local rules.
    if deployment is None and os.environ.get("MVP_DEPLOYMENT_MODE", "local") != "local":
        deployment = DeploymentConfig.from_environment()
    if deployment is None:
        _loopback_configuration(allowed_host, allowed_origin)
        deployment = DeploymentConfig("local", allowed_host, "http://" + allowed_host, allowed_origin,
            Path(data_dir or os.environ.get("MVP_WEB_DATA_DIR") or ROOT / ".mvp-web-state"))
    if deployment.hosted:
        if data_dir is not None and Path(data_dir) != deployment.data_dir:
            raise ValueError("Hosted factory data directory must match its persistent configuration.")
        if any(item is not None for item in (proposal_adapter, search_planner, map_embedder, ui_store)) or services:
            raise ValueError("Hosted mode uses only configured adapters and its persistent private registry.")
        deployment.validate_storage()
    else:
        _loopback_configuration(deployment.api_host, deployment.public_origin)
    allowed_host, allowed_origin = deployment.api_host, deployment.public_origin
    directory = private_directory(deployment.data_dir)
    cookie_name = HOSTED_SESSION_COOKIE if deployment.hosted else COOKIE_NAME
    admission = HostedAdmissionStore(directory / "hosted-admission.sqlite3", deployment.invite_sha256) if deployment.hosted else None
    registry = ui_store or WorkspaceUIStore(directory / "web-credentials.sqlite3")
    services = services if services is not None else {}
    gate = BoundedSemaphore(8)
    app = FastAPI(title="Literature Review Engine local adapter", version="0.2.0", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.registry, app.state.services = registry, services
    app.state.data_dir = directory
    app.state.deployment, app.state.admission = deployment, admission

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
            return JSONResponse({"error": {"code": "invalid_host", "message": "Use the configured application origin.", "retryable": False}}, 403)
        origin = request.headers.get("origin")
        if (origin is not None and origin != allowed_origin) or (request.method not in {"GET", "HEAD"} and origin != allowed_origin):
            return JSONResponse({"error": {"code": "invalid_origin", "message": "Mutation requires the configured application origin.", "retryable": False}}, 403)
        if admission is not None:
            path = request.url.path
            public = {"/healthz", "/readyz", PREFIX + "/admission/status", PREFIX + "/admission/login", PREFIX + "/admission/logout"}
            try:
                if path == PREFIX + "/admission/login" and request.method == "POST":
                    admission.login_attempt()
                elif path not in public:
                    admission.consume(request.cookies.get(ADMISSION_COOKIE), expensive=expensive_request(request.method, path))
            except AdmissionDenied as error:
                return JSONResponse({"error": {"code": error.code, "message": "Hosted admission is required or its usage limit was reached.", "retryable": error.status == 429}}, error.status)
        content_length = request.headers.get("content-length")
        from src.mvp.limits import MAX_IMPORT_BYTES
        upload = request.method == 'POST' and re.fullmatch(r'/api/v1/workspaces/[^/]+/imports/(csv|ris|identifiers)', request.url.path)
        limit = MAX_IMPORT_BYTES if upload else MAX_REQUEST_BYTES
        if upload:
            media = request.headers.get('content-type', '').split(';', 1)[0].strip().lower()
            if media not in {'application/octet-stream', 'text/csv', 'text/plain', 'application/x-research-info-systems'}:
                return JSONResponse({'error': {'code': 'invalid_upload_type', 'message': 'Use a raw citation file or identifier text upload.', 'retryable': False}}, 415)
        try:
            oversized = content_length is not None and (int(content_length) < 0 or int(content_length) > limit)
        except ValueError:
            oversized = True
        if oversized:
            return JSONResponse({"error": {"code": "request_limit", "message": "Request exceeds this local route's size limit.", "retryable": False}}, 413)
        if request.method not in {"GET", "HEAD"}:
            body = bytearray()
            async for chunk in request.stream():
                if len(body) + len(chunk) > limit:
                    return JSONResponse({"error": {"code": "request_limit", "message": "Request exceeds this local route's size limit.", "retryable": False}}, 413)
                body.extend(chunk)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.middleware("http")
    async def private_responses(request, call_next):
        try:
            response = await call_next(request)
        except Exception:
            if not deployment.hosted:
                raise
            # Provider/SQLite exceptions must not render or log source text,
            # private paths, credentials, or a detailed traceback publicly.
            response = JSONResponse({"error": {"code": "internal_error", "message": "The operation could not be completed.", "retryable": True}}, 500)
        response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"})
        return response

    @app.exception_handler(MvpError)
    async def safe_domain_error(request, error):
        missing = error.code.startswith("unknown_") or error.code in {"workspace_access_denied", "session_unavailable"}
        conflict = error.code.startswith("stale_") or error.code in {"idempotency_conflict", "workspace_conflict"}
        status = 404 if missing else 409 if conflict else 503 if error.retryable or error.code == "server_busy" else 422
        message = "The operation could not be completed. Check the supplied input and retry if permitted." if deployment.hosted else error.message
        return JSONResponse({"error": {"code": error.code, "message": message, "retryable": error.retryable}}, status)

    @app.exception_handler(RequestValidationError)
    async def safe_validation_error(request, error):
        if deployment.hosted:
            return JSONResponse({"error": {"code": "invalid_fields", "message": "Check the supplied fields.", "retryable": False}}, 422)
        return JSONResponse({"error": {"code": "invalid_fields", "message": "Check the supplied fields.", "retryable": False,
                                      "fields": [{"loc": list(item["loc"]), "message": item["msg"]} for item in error.errors()]}}, 422)

    def session_for(request: Request):
        session = registry.resolve_session(request.cookies.get(cookie_name))
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

    @app.get("/healthz")
    def health():
        return {"healthy": True}

    @app.get("/readyz")
    def ready():
        thread = getattr(getattr(app.state, "preparation_worker", None), "_thread", None)
        ready = bool(app.state.preparation_jobs_ready and thread and thread.is_alive())
        if deployment.hosted:
            try:
                deployment.validate_storage()
                with registry.connection() as db:
                    db.execute("SELECT 1 FROM web_sessions LIMIT 1").fetchone()
                with admission.connection() as db:
                    db.execute("SELECT 1 FROM admission_grants LIMIT 1").fetchone()
            except Exception:
                ready = False
        return JSONResponse({"ready": ready}, 200 if ready else 503)

    @app.get(PREFIX + "/admission/status")
    def admission_status(request: Request):
        if admission is None:
            return {"mode": "local", "admitted": True}
        grant = admission.resolve(request.cookies.get(ADMISSION_COOKIE))
        return {"mode": "hosted", "admitted": grant is not None, **({"expires_at": admission.expires_at(grant)} if grant else {})}

    @app.post(PREFIX + "/admission/login")
    def admission_login(payload: AdmissionLogin, response: Response):
        if admission is None:
            return {"mode": "local", "admitted": True}
        try:
            token, grant = admission.issue(payload.code)
        except AdmissionDenied as error:
            return JSONResponse({"error": {"code": error.code, "message": "Hosted admission was not granted.", "retryable": error.status == 429}}, error.status)
        response.set_cookie(ADMISSION_COOKIE, token, max_age=ADMISSION_SECONDS,
                            httponly=True, secure=True, samesite="strict", path="/")
        return {"mode": "hosted", "admitted": True, "expires_at": admission.expires_at(grant)}

    @app.post(PREFIX + "/admission/logout")
    def admission_logout(request: Request, response: Response):
        if admission is not None:
            admission.revoke(request.cookies.get(ADMISSION_COOKIE))
            response.delete_cookie(ADMISSION_COOKIE, secure=True, httponly=True, samesite="strict", path="/")
            # Admission is separate from browser workspace ownership. Retain
            # the private research cookie so a later invitation login can
            # reopen this same browser's work rather than strand its records.
        return {"mode": deployment.mode, "admitted": not deployment.hosted}

    @app.get(PREFIX + "/session", response_model=SessionInfo, dependencies=dependencies)
    def bootstrap_session(request: Request, response: Response):
        token, session = registry.session(request.cookies.get(cookie_name))
        remaining = max(0, int((datetime.fromisoformat(session["expires_at"]) - datetime.now(timezone.utc)).total_seconds()))
        response.set_cookie(cookie_name, token, max_age=remaining, httponly=True, samesite="strict", secure=allowed_origin.startswith("https:"), path="/")
        return SessionInfo(csrf_token=session["csrf"], expires_at=session["expires_at"])

    @app.get(PREFIX + "/capabilities", response_model=Capabilities, dependencies=dependencies)
    def capabilities():
        from .contracts import MapCapability
        from src.mvp.span_board_contracts import BoardSpanCapability
        ready, reason = app.state.maps.readiness()
        return Capabilities(**public_runtime_info(), map=MapCapability(ready=ready, reason=reason),
                            preparation_jobs_ready=app.state.preparation_jobs_ready,
                            search_plans_ready=app.state.search_plans_ready,
                            board_span_profiles=BoardSpanCapability())

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

    @app.get(PREFIX + "/workspaces/{workspace_id}/source-preparations/{preparation_id}", response_model=PreparationView | CollectionPreparationView, dependencies=dependencies)
    def preparation(workspace_id: str, preparation_id: str, session=Depends(session_for)):
        _, handle, engine = owned(workspace_id, session)
        return preparation_view(find(engine.get_workspace(handle).preparations, preparation_id, "preparation"))

    @app.get(PREFIX + '/workspaces/{workspace_id}/source-preparations/{preparation_id}/papers', response_model=PreparationPapers, dependencies=dependencies)
    def preparation_papers(workspace_id: str, preparation_id: str, session=Depends(session_for)):
        from src.mvp.board_contracts import BoardPaper
        from src.mvp.origin_resolver import resolve_preparation
        _, handle, engine = owned(workspace_id, session)
        state = engine.get_workspace(handle)
        resolved = resolve_preparation(state, find(state.preparations, preparation_id, 'preparation'))
        return PreparationPapers(preparation_id=preparation_id, origin=resolved.origin,
            papers=[BoardPaper(**paper.model_dump(include=set(BoardPaper.model_fields))) for paper in resolved.papers])

    @app.get(PREFIX + '/workspaces/{workspace_id}/runs/{run_id}/papers', response_model=RunPapers, dependencies=dependencies)
    def run_papers(workspace_id: str, run_id: str, session=Depends(session_for)):
        from src.mvp.board_contracts import BoardPaper
        from src.mvp.origin_resolver import resolve_run
        _, handle, engine = owned(workspace_id, session)
        state = engine.get_workspace(handle)
        _, resolved = resolve_run(state, find(state.runs, run_id, 'run'))
        return RunPapers(run_id=run_id, origin=resolved.origin,
            papers=[BoardPaper(**paper.model_dump(include=set(BoardPaper.model_fields))) for paper in resolved.papers])

    @app.post(PREFIX + "/workspaces/{workspace_id}/evidence-runs", response_model=EvidenceRun | CollectionEvidenceRun, dependencies=dependencies)
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

    def validate_scope(state, scope, expected_head=None, writing=False, data=None):
        if scope in {"discover", "evidence"}:
            return
        if scope.startswith("selection:"):
            search = find(state.searches, scope.removeprefix("selection:"), "search")
            if writing:
                try:
                    selection = SelectionDraft.model_validate(data)
                except ValidationError:
                    raise MvpError("invalid_selection_draft", "Choose at most thirty distinct paper IDs from this saved preview. Existing drafts are unchanged.") from None
                if set(selection.selected_paper_ids) - {paper.id for paper in search.papers}:
                    raise MvpError("invalid_selection_draft", "Selected papers must belong to this saved preview. Existing drafts are unchanged.")
            return
        if scope.startswith('collection-selection:'):
            identifier = scope.removeprefix('collection-selection:')
            # The route resolves the owning engine/handle before entering this
            # common validator; see the explicit collection guard below.
            if not identifier:
                raise MvpError('invalid_draft_scope', 'Choose a saved collection.')
            return
        if scope.startswith("assessment:"):
            run_id = scope.removeprefix("assessment:")
            find(state.runs, run_id, "run")
            head = next((item.id for item in reversed(state.assessments) if item.run_id == run_id), None)
            if writing and expected_head != head:
                raise MvpError("stale_assessment_draft", "A newer assessment exists. Keep your draft for comparison before revising.")
            return
        raise MvpError("invalid_draft_scope", "Choose a supported workspace screen or saved search/run draft scope.")

    def usability_draft(mode, handle, engine, workspace_id, scope, scope_parts, request=None):
        kind, identifier = scope_parts
        model = {'search-plan-editor': SearchPlanEditorDraft, 'comparison-handoff': ComparisonHandoffDraft,
                 'import-intake': ImportIntakeDraft}[kind]

        def parse(data):
            try:
                return model.model_validate(data)
            except ValidationError:
                raise MvpError('invalid_comparison_handoff' if kind == 'comparison-handoff' else 'invalid_editor_draft',
                    'Keep bounded editable inputs and exact owned references. Existing drafts are unchanged.') from None

        value = parse(request.data) if request is not None else None
        # Initialize sidecars before acquiring lifecycle/research locks. These
        # stores read retained local records only; no compiler/provider/model runs.
        planning = app.state.search_plans_for(mode) if kind == 'search-plan-editor' and identifier != 'new' else None
        collections = app.state.collections_for(mode) if kind == 'comparison-handoff' else None
        job_stores = ({'search': app.state.preparation_jobs.store_for(mode),
                       'collection': app.state.collection_preparation_jobs.store_for(mode)}
                      if kind == 'comparison-handoff' else {})
        with registry.lifecycle_guard(workspace_id):
            if registry.is_deleted(workspace_id):
                raise MvpError('unknown_workspace', 'This workspace is unavailable.')
            engine.get_workspace(handle)
            prior = registry.draft(workspace_id, scope)
            if value is None and prior['version']:
                value = parse(prior['data'])
            if kind == 'import-intake':
                if request is None:
                    return DraftRecord(**prior)
                return DraftRecord(**registry.put_draft(workspace_id, scope, **request.model_dump(mode='json')))
            if kind == 'search-plan-editor':
                if value is not None and (value.plan_id != (None if identifier == 'new' else identifier) or
                        identifier == 'new' and value.base_revision_id is not None):
                    raise MvpError('invalid_editor_draft', 'The editable draft must retain its owning plan scope and revision.')
                if planning is not None:
                    with planning.store.connection() as db:
                        planning.store.revision(db, workspace_id, identifier, value.base_revision_id if value else None)
                if request is None:
                    return DraftRecord(**prior)
                return DraftRecord(**registry.put_draft(workspace_id, scope, **request.model_dump(mode='json')))

            if value is None:
                return DraftRecord(**prior)
            # Collection snapshots and job input projections are bounded,
            # immutable references. Resolve them before the short mutation lock.
            collection_ids = None
            if value.origin.kind == 'collection':
                resolved = collections.resolve_collection(handle, value.origin)
                collection_ids = [member.paper.id for member in resolved.members]
            job = job_stores[value.origin.kind].job(workspace_id, value.job_id) if value.job_id is not None else None

            def finish(state):
                # Check CAS before immutable-click checks, so competing tabs get
                # the same actionable stale-draft response as existing scopes.
                current = registry.draft(workspace_id, scope) if request is not None else prior
                if request is not None and current['version'] != request.version:
                    raise MvpError('stale_draft', 'A newer saved draft exists. Your local edits were not overwritten; reload for comparison.')
                retained = parse(current['data']) if current['version'] else None
                if request is not None and retained is not None:
                    validate_handoff_update(retained, value)
                # A synchronous publication must be current when first attached.
                # Once acknowledged it remains recoverable historical input.
                retained_sync = retained is not None and value.preparation_id is not None and retained.preparation_id == value.preparation_id
                validate_handoff_state(state, value, collection_paper_ids=collection_ids, job=job,
                    retained_sync_acknowledgement=retained_sync)
                if request is None:
                    return DraftRecord(**prior)
                return DraftRecord(**registry.put_draft(workspace_id, scope, **request.model_dump(mode='json')))

            return engine.with_workspace_state(handle, finish) if request is not None else finish(engine.get_workspace(handle))

    @app.get(PREFIX + "/workspaces/{workspace_id}/drafts/{scope}", response_model=DraftRecord, dependencies=dependencies)
    def get_draft(workspace_id: str, scope: str, session=Depends(session_for)):
        mode, handle, engine = owned(workspace_id, session)
        scope_parts = usability_scope(scope)
        if scope_parts is not None:
            return usability_draft(mode, handle, engine, workspace_id, scope, scope_parts)
        if scope.startswith('collection-selection:'):
            app.state.collections_for(mode).collection(handle, scope.removeprefix('collection-selection:'))
        validate_scope(engine.get_workspace(handle), scope)
        return DraftRecord(**registry.draft(workspace_id, scope))

    @app.put(PREFIX + "/workspaces/{workspace_id}/drafts/{scope}", response_model=DraftRecord, dependencies=dependencies)
    def put_draft(workspace_id: str, scope: str, request: DraftUpdate, session=Depends(session_for)):
        mode, handle, engine = owned(workspace_id, session)
        scope_parts = usability_scope(scope)
        if scope_parts is not None:
            return usability_draft(mode, handle, engine, workspace_id, scope, scope_parts, request)
        def save_under_guard(state):
            if scope.startswith('collection-selection:'):
                collections = app.state.collections_for(mode)
                identifier = scope.removeprefix('collection-selection:')
                summary = collections.collection(handle, identifier)
                try:
                    selection = SelectionDraft.model_validate(request.data)
                except ValidationError:
                    raise MvpError('invalid_selection_draft', 'Choose at most thirty distinct owned collection papers.') from None
                resolved = collections.resolve_collection(handle, summary.origin)
                if set(selection.selected_paper_ids) - {item.paper.id for item in resolved.members}:
                    raise MvpError('invalid_selection_draft', 'Selected papers must belong to this saved collection.')
            validate_scope(state, scope, request.expected_assessment_head, writing=True, data=request.data)
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
        def clear_sidecars(identifier):
            app.state.maps.delete_workspace(identifier)
            app.state.boards.delete_workspace(identifier)
            app.state.preparation_jobs.delete_workspace(identifier)
            app.state.collection_preparation_jobs.delete_workspace(identifier)
        registry.delete_workspace(session["token_hash"], workspace_id, lambda mode, handle: service(mode).clear_workspace_if_present(handle), clear_sidecars)
        return ClearResult()

    from .collection_routes import install_collection_routes
    install_collection_routes(app, service=service, owned=owned, session_for=session_for,
                              dependencies=dependencies, metadata_resolver=metadata_resolver)
    from .search_plan_routes import install_search_plan_routes
    install_search_plan_routes(app, service=service, owned=owned, session_for=session_for,
        dependencies=dependencies, diagnostics=search_diagnostics, planner=search_planner, registry=registry)
    from .map_routes import install_map_routes
    install_map_routes(app, directory=directory, registry=registry, service=service, owned=owned,
                       session_for=session_for, dependencies=dependencies, embedder=map_embedder)
    from .collection_map_routes import install_collection_map_routes
    install_collection_map_routes(app, registry=registry, service=service, owned=owned,
        session_for=session_for, dependencies=dependencies)
    from .board_routes import install_board_routes
    install_board_routes(app, directory=directory, registry=registry, service=service, owned=owned,
                         session_for=session_for, dependencies=dependencies)
    from src.mvp.adapters.cell_generation import ConfiguredCellGenerationAdapter
    from src.mvp.cell_proposals import CellProposalService
    from .proposal_routes import install_proposal_routes
    app.state.proposal_configuration_error = None
    if proposal_adapter is None:
        try:
            proposal_adapter = ConfiguredCellGenerationAdapter.from_environment()
        except MvpError as error:
            # Invalid optional configuration disables AI only. It must not take
            # the existing manual research workflow offline or select a fallback.
            app.state.proposal_configuration_error = error.message
            proposal_adapter = ConfiguredCellGenerationAdapter()
    proposals = CellProposalService(app.state.boards, proposal_adapter)
    install_proposal_routes(app, proposals=proposals, owned=owned, session_for=session_for,
                            dependencies=dependencies)
    from .collection_preparation_routes import install_collection_preparation_routes
    collection_jobs = install_collection_preparation_routes(app, registry=registry, service=service, owned=owned,
        session_for=session_for, dependencies=dependencies)
    from .preparation_routes import install_preparation_routes
    install_preparation_routes(app, registry=registry, service=service, owned=owned,
                               session_for=session_for, dependencies=dependencies, additional_domains=(collection_jobs,))
    return app


def app_factory():
    return create_app(deployment=DeploymentConfig.from_environment())
