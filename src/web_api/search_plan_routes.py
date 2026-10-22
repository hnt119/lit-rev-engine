"""Authorized planning operations over the existing application services."""
from threading import Lock

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

    @app.get(prefix+'/search-plan-capabilities', response_model=SearchPlanCapabilities, dependencies=dependencies)
    def capabilities(workspace_id: str, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return planning(mode).capabilities(handle)

    @app.get(prefix+'/search-plans', response_model=SearchPlanListing, dependencies=dependencies)
    def listing(workspace_id: str, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return planning(mode).listing(handle)

    @app.post(prefix+'/search-plans', response_model=SearchPlanView, dependencies=dependencies)
    def create(workspace_id: str, request: CreateSearchPlanRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return planning(mode).create(handle, request)

    @app.get(prefix+'/search-plans/{plan_id}', response_model=SearchPlanView, dependencies=dependencies)
    def view(workspace_id: str, plan_id: str, revision_id: str | None = None, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return planning(mode).view(handle, plan_id, revision_id)

    @app.put(prefix+'/search-plans/{plan_id}', response_model=SearchPlanView, dependencies=dependencies)
    def update(workspace_id: str, plan_id: str, request: UpdateSearchPlanRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return planning(mode).update(handle, plan_id, request)

    @app.post(prefix+'/search-plans/{plan_id}/approve', response_model=SearchApprovalReceipt, dependencies=dependencies)
    def approve(workspace_id: str, plan_id: str, request: ApproveSearchPlanRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return planning(mode).approve(handle, plan_id, request)

    @app.post(prefix+'/search-plans/{plan_id}/diagnose', response_model=SearchPlanDiagnostic, dependencies=dependencies)
    def diagnose(workspace_id: str, plan_id: str, request: DiagnoseSearchPlanRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return planning(mode).diagnose(handle, plan_id, request)

    @app.post(prefix+'/search-plans/{plan_id}/execute', response_model=PlannedSearchResult, dependencies=dependencies)
    def execute(workspace_id: str, plan_id: str, request: ExecuteSearchPlanRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return planning(mode).execute(handle, plan_id, request)

    @app.post(prefix+'/search-plans/{plan_id}/propose', response_model=SearchPlanProposalReceipt, dependencies=dependencies)
    def propose(workspace_id: str, plan_id: str, request: ProposeSearchPlanRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return planning(mode).propose(handle, plan_id, request)

    return planning
