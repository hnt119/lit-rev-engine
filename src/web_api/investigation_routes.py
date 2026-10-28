"""Owned, CSRF-protected follow-up investigation endpoints."""
from copy import copy
from fastapi import Depends, Query
from src.mvp.adapters.investigation_storage import InvestigationStore
from src.mvp.adapters.search_diagnostics import PubMedSearchDiagnostics
from src.mvp.investigations import InvestigationService
from src.mvp.investigation_contracts import (
    CreateInvestigationRequest, InvestigationDecisionRequest, InvestigationView,
    InvestigationListing, InvestigationExport,
)
from src.mvp.search_plan_contracts import (
    UpdateSearchPlanRequest, ApproveSearchPlanRequest, DiagnoseSearchPlanRequest, ExecuteSearchPlanRequest,
)
from src.mvp.investigation_research import InvestigationResearchService
from src.mvp.investigation_research_contracts import (
    InvestigationHandoffRequest, InvestigationHandoffPreview, InvestigationHandoff,
    InvestigationInspectionRequest, InvestigationInspection, ResearchEvaluationNoteRequest,
    ResearchEvaluationNote, InvestigationResearchState,
)
from .settings_routes import engine_for


def install_investigation_routes(app, *, owned, session_for, dependencies):
    prefix = '/api/v1/workspaces/{workspace_id}/investigations'

    def selected(workspace_id, session):
        mode, handle, _ = owned(workspace_id, session)
        planning = copy(app.state.search_plans_for(mode))
        settings = getattr(app.state, 'runtime_settings', None)
        if settings is not None:
            # Engine selection handles enabled/disabled PubMed configuration and
            # session-only keys without exposing them in any public contract.
            planning.engine = engine_for(settings, session['token_hash'], mode, planning.engine)
            if planning.engine is not app.state.search_plans_for(mode).engine:
                planning.diagnostics = PubMedSearchDiagnostics.from_provider(planning.engine._discovery)
        store = InvestigationStore(planning.engine._storage)
        planning.store = store
        service = InvestigationService(app.state.boards, planning, store)
        service.research = InvestigationResearchService(service, app.state.collections_for(mode))
        return mode, handle, service

    @app.get(prefix, response_model=InvestigationListing, dependencies=dependencies)
    def listing(workspace_id: str, board_id: str | None = Query(default=None, max_length=200),
                paper_id: str | None = Query(default=None, max_length=200),
                field_id: str | None = Query(default=None, max_length=100), session=Depends(session_for)):
        _, handle, service = selected(workspace_id, session)
        return service.listing(handle, board_id, paper_id, field_id)

    @app.post(prefix, response_model=InvestigationView, dependencies=dependencies)
    def create(workspace_id: str, request: CreateInvestigationRequest, session=Depends(session_for)):
        mode, handle, service = selected(workspace_id, session)
        return service.create(mode, handle, request)

    @app.get(prefix+'/{investigation_id}', response_model=InvestigationView, dependencies=dependencies)
    def view(workspace_id: str, investigation_id: str, session=Depends(session_for)):
        _, handle, service = selected(workspace_id, session)
        return service.view(handle, investigation_id)

    @app.put(prefix+'/{investigation_id}/plan', response_model=InvestigationView, dependencies=dependencies)
    def update(workspace_id: str, investigation_id: str, request: UpdateSearchPlanRequest, session=Depends(session_for)):
        _, handle, service = selected(workspace_id, session)
        return service.operation(handle, investigation_id, 'update', request)

    @app.post(prefix+'/{investigation_id}/approve', response_model=InvestigationView, dependencies=dependencies)
    def approve(workspace_id: str, investigation_id: str, request: ApproveSearchPlanRequest, session=Depends(session_for)):
        _, handle, service = selected(workspace_id, session)
        return service.operation(handle, investigation_id, 'approve', request)

    @app.post(prefix+'/{investigation_id}/diagnose', response_model=InvestigationView, dependencies=dependencies)
    def diagnose(workspace_id: str, investigation_id: str, request: DiagnoseSearchPlanRequest, session=Depends(session_for)):
        _, handle, service = selected(workspace_id, session)
        return service.operation(handle, investigation_id, 'diagnose', request)

    @app.post(prefix+'/{investigation_id}/execute', response_model=InvestigationView, dependencies=dependencies)
    def execute(workspace_id: str, investigation_id: str, request: ExecuteSearchPlanRequest, session=Depends(session_for)):
        _, handle, service = selected(workspace_id, session)
        return service.operation(handle, investigation_id, 'execute', request)

    @app.post(prefix+'/{investigation_id}/decisions', response_model=InvestigationView, dependencies=dependencies)
    def decide(workspace_id: str, investigation_id: str, request: InvestigationDecisionRequest, session=Depends(session_for)):
        _, handle, service = selected(workspace_id, session)
        return service.decide(handle, investigation_id, request)

    @app.get(prefix+'/{investigation_id}/export', response_model=InvestigationExport, dependencies=dependencies)
    def export(workspace_id: str, investigation_id: str, session=Depends(session_for)):
        _, handle, service = selected(workspace_id, session)
        return service.export(handle, investigation_id)

    app.state.investigations_selected = selected

    @app.get(prefix+'/{investigation_id}/research', response_model=InvestigationResearchState, dependencies=dependencies)
    def research(workspace_id: str, investigation_id: str, session=Depends(session_for)):
        _, handle, service = selected(workspace_id, session)
        return service.research.state(handle, investigation_id)

    @app.post(prefix+'/{investigation_id}/handoff-preview', response_model=InvestigationHandoffPreview, dependencies=dependencies)
    def handoff_preview(workspace_id: str, investigation_id: str, request: InvestigationHandoffRequest, session=Depends(session_for)):
        mode, handle, service = selected(workspace_id, session)
        return service.research.preview(mode, handle, investigation_id, request)

    @app.post(prefix+'/{investigation_id}/handoffs', response_model=InvestigationHandoff, dependencies=dependencies)
    def handoff(workspace_id: str, investigation_id: str, request: InvestigationHandoffRequest, session=Depends(session_for)):
        mode, handle, service = selected(workspace_id, session)
        return service.research.commit(mode, handle, investigation_id, request)

    @app.post(prefix+'/{investigation_id}/inspections', response_model=InvestigationInspection, dependencies=dependencies)
    def inspect(workspace_id: str, investigation_id: str, request: InvestigationInspectionRequest, session=Depends(session_for)):
        mode, handle, service = selected(workspace_id, session)
        return service.research.inspect(mode, handle, investigation_id, request)

    @app.post(prefix+'/{investigation_id}/notes', response_model=ResearchEvaluationNote, dependencies=dependencies)
    def note(workspace_id: str, investigation_id: str, request: ResearchEvaluationNoteRequest, session=Depends(session_for)):
        mode, handle, service = selected(workspace_id, session)
        return service.research.note(mode, handle, investigation_id, request)
