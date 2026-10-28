"""Authorized planning operations over the existing application services."""
from threading import Lock
from copy import copy

from fastapi import Depends

from src.mvp.adapters.search_plan_storage import SearchPlanStore
from src.mvp.search_plans import SearchPlanService
from src.mvp.search_plan_contracts import (
    ApproveSearchPlanRequest, CreateSearchPlanRequest, DiagnoseSearchPlanRequest,
    ExecuteSearchPlanRequest, ProposeSearchPlanRequest, SearchApprovalReceipt,
    SearchPlanDiagnostic, SearchPlanListing, UpdateSearchPlanRequest,
)
from src.mvp.search_plan_service_contracts import (
    PlannedSearchResult, SearchPlanCapabilities, SearchPlanProposalReceipt, SearchPlanView,
)
from src.mvp.ports import MvpError
from src.mvp.core_concept_suggestions import (CoreConceptSuggestion, CoreConceptSuggestionRequest, suggest_core_concepts)
from .settings_routes import (RuntimePlanRequest, configured_adapter, core_request,
                              disclosure, engine_for)


def install_search_plan_routes(app, *, service, owned, session_for, dependencies, diagnostics=None, planner=None, registry=None):
    services, lock = {}, Lock()
    def planning(mode):
        with lock:
            if mode not in services:
                engine = service(mode)
                services[mode] = SearchPlanService(engine, SearchPlanStore(engine._storage),
                    mode=mode, diagnostics=diagnostics, planner=planner, registry=registry)
            return services[mode]
    app.state.search_plans_for = planning
    app.state.search_plans_ready = True
    prefix = '/api/v1/workspaces/{workspace_id}'

    def for_session(mode, session):
        base = planning(mode)
        settings = getattr(app.state, 'runtime_settings', None)
        if settings is None: return base
        owner = session['token_hash']
        adapter, snapshot = configured_adapter(settings, owner, 'planning')
        if not snapshot['configured']: return base
        from src.mvp.adapters.search_diagnostics import PubMedSearchDiagnostics
        result = copy(base)
        result.engine = engine_for(settings, owner, mode, base.engine)
        result.planner = adapter
        result.planner_configuration_error = None
        result.diagnostics = PubMedSearchDiagnostics.from_provider(result.engine._discovery)
        return result

    def generation_binding(workspace_id, plan_id, request):
        return dict(task='planning', workspace_id=workspace_id, plan_id=plan_id,
                    request=core_request(request, ProposeSearchPlanRequest).model_dump(mode='json'))

    @app.post(prefix+'/search-plans/{plan_id}/prepare-generation', dependencies=dependencies)
    def prepare_generation(workspace_id: str, plan_id: str, request: RuntimePlanRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        settings = getattr(app.state, 'runtime_settings', None)
        if settings is None: raise MvpError('generation_configuration', 'Runtime settings are local-only.')
        adapter, snapshot = configured_adapter(settings, session['token_hash'], 'planning', request.settings_revision)
        if adapter is None or not adapter.enabled or request.settings_revision != snapshot['revision']:
            raise MvpError('generation_configuration', 'Enable planning and provide the current session configuration/key in Settings.')
        selected = planning(mode).view(handle, plan_id).revision
        if selected.revision_id != request.expected_revision_id or selected.draft.original_question != request.original_question:
            raise MvpError('stale_search_plan', 'Save and review this exact question and current plan revision first.')
        return settings.prepare(session['token_hash'], snapshot['revision'], generation_binding(workspace_id, plan_id, request),
            disclosure(adapter, 'planning', {'original_question': request.original_question}, 1))

    @app.post(prefix+'/search-plan-suggestions', response_model=CoreConceptSuggestion, dependencies=dependencies)
    def core_suggestions(workspace_id: str, request: CoreConceptSuggestionRequest, session=Depends(session_for)):
        _, handle, engine = owned(workspace_id, session)
        engine.get_workspace(handle)
        return suggest_core_concepts(request.original_question)

    @app.get(prefix+'/search-plan-capabilities', response_model=SearchPlanCapabilities, dependencies=dependencies)
    def capabilities(workspace_id: str, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        result = for_session(mode, session).capabilities(handle)
        if getattr(getattr(app.state, "deployment", None), "hosted", False):
            result = result.model_copy(update={"planner": result.planner.model_copy(update={
                "reason": "AI search planning is unavailable in this hosted release. A local laptop model is not part of this deployment; manual search editing remains available."})})
        return result

    @app.get(prefix+'/search-plans', response_model=SearchPlanListing, dependencies=dependencies)
    def listing(workspace_id: str, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return for_session(mode, session).listing(handle)

    @app.post(prefix+'/search-plans', response_model=SearchPlanView, dependencies=dependencies)
    def create(workspace_id: str, request: CreateSearchPlanRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return for_session(mode, session).create(handle, request)

    @app.get(prefix+'/search-plans/{plan_id}', response_model=SearchPlanView, dependencies=dependencies)
    def view(workspace_id: str, plan_id: str, revision_id: str | None = None, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return for_session(mode, session).view(handle, plan_id, revision_id)

    @app.put(prefix+'/search-plans/{plan_id}', response_model=SearchPlanView, dependencies=dependencies)
    def update(workspace_id: str, plan_id: str, request: UpdateSearchPlanRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return for_session(mode, session).update(handle, plan_id, request)

    @app.post(prefix+'/search-plans/{plan_id}/approve', response_model=SearchApprovalReceipt, dependencies=dependencies)
    def approve(workspace_id: str, plan_id: str, request: ApproveSearchPlanRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return for_session(mode, session).approve(handle, plan_id, request)

    @app.post(prefix+'/search-plans/{plan_id}/diagnose', response_model=SearchPlanDiagnostic, dependencies=dependencies)
    def diagnose(workspace_id: str, plan_id: str, request: DiagnoseSearchPlanRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return for_session(mode, session).diagnose(handle, plan_id, request)

    @app.post(prefix+'/search-plans/{plan_id}/execute', response_model=PlannedSearchResult, dependencies=dependencies)
    def execute(workspace_id: str, plan_id: str, request: ExecuteSearchPlanRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return for_session(mode, session).execute(handle, plan_id, request)

    @app.post(prefix+'/search-plans/{plan_id}/propose', response_model=SearchPlanProposalReceipt, dependencies=dependencies)
    def propose(workspace_id: str, plan_id: str, request: RuntimePlanRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        selected = for_session(mode, session)
        settings = getattr(app.state, 'runtime_settings', None)
        if settings is None or not settings.snapshot(session['token_hash'])[0]['configured']:
            return selected.propose(handle, plan_id, core_request(request, ProposeSearchPlanRequest))
        snapshot, _ = settings.snapshot(session['token_hash'], request.settings_revision)
        if request.settings_revision != snapshot['revision']:
            raise MvpError('stale_settings', 'Review the current generation configuration.')
        with settings.generation_slot():
            settings.consume(session['token_hash'], snapshot['revision'], request.consent_id,
                             generation_binding(workspace_id, plan_id, request))
            return selected.propose(handle, plan_id, core_request(request, ProposeSearchPlanRequest))

    return planning
