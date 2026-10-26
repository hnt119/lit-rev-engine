"""Owned, explicit evidence-view operations; reads never generate or retrieve."""
from typing import Literal
from fastapi import Depends, Query, Response
from src.mvp.evidence_views import EvidenceViewService
from src.mvp.evidence_view_contracts import (
    DimensionPut, DimensionDefinition, AttributePut, AttributeRevision,
    EvidenceViewConfig, SavedViewPut, SavedEvidenceView, EvidenceProfileSet, EvidenceViewResult, DimensionId, AttributeHistory, SavedViewHistory,
)

def install_evidence_view_routes(app, *, boards, owned, session_for, dependencies):
    service = EvidenceViewService(boards)
    app.state.evidence_views = service
    prefix = '/api/v1/workspaces/{workspace_id}/boards/{board_id}/evidence-views'

    @app.get(prefix+'/profiles',response_model=EvidenceProfileSet,dependencies=dependencies)
    def profiles(workspace_id:str,board_id:str,revision_id:str=Query(min_length=1,max_length=200),session=Depends(session_for)):
        mode,handle,_=owned(workspace_id,session)
        return service.profiles(mode,handle,board_id,revision_id)

    @app.post(prefix+'/dimensions',response_model=DimensionDefinition,dependencies=dependencies)
    def dimension(workspace_id:str,board_id:str,request:DimensionPut,revision_id:str=Query(min_length=1,max_length=200),session=Depends(session_for)):
        mode,handle,_=owned(workspace_id,session)
        return service.bind_dimension(mode,handle,board_id,revision_id,request)

    @app.post(prefix+'/attributes',response_model=AttributeRevision,dependencies=dependencies)
    def classify(workspace_id:str,board_id:str,request:AttributePut,revision_id:str=Query(min_length=1,max_length=200),session=Depends(session_for)):
        mode,handle,_=owned(workspace_id,session)
        return service.classify(mode,handle,board_id,revision_id,request)

    @app.get(prefix+'/saved',response_model=list[SavedEvidenceView],dependencies=dependencies)
    def listing(workspace_id:str,board_id:str,revision_id:str=Query(min_length=1,max_length=200),session=Depends(session_for)):
        mode,handle,_=owned(workspace_id,session)
        return service.views(mode,handle,board_id,revision_id)

    @app.post(prefix+'/saved',response_model=SavedEvidenceView,dependencies=dependencies)
    def create(workspace_id:str,board_id:str,request:SavedViewPut,revision_id:str=Query(min_length=1,max_length=200),session=Depends(session_for)):
        mode,handle,_=owned(workspace_id,session)
        return service.save_view(mode,handle,board_id,revision_id,request)

    @app.put(prefix+'/saved/{view_id}',response_model=SavedEvidenceView,dependencies=dependencies)
    def update(workspace_id:str,board_id:str,view_id:str,request:SavedViewPut,revision_id:str=Query(min_length=1,max_length=200),session=Depends(session_for)):
        mode,handle,_=owned(workspace_id,session)
        return service.save_view(mode,handle,board_id,revision_id,request,view_id)

    @app.post(prefix+'/query',response_model=EvidenceViewResult,dependencies=dependencies)
    def query(workspace_id:str,board_id:str,request:EvidenceViewConfig,revision_id:str=Query(min_length=1,max_length=200),session=Depends(session_for)):
        mode,handle,_=owned(workspace_id,session)
        return service.query(mode,handle,board_id,revision_id,request)

    @app.post(prefix+'/exports',dependencies=dependencies)
    def export(workspace_id:str,board_id:str,request:EvidenceViewConfig,revision_id:str=Query(min_length=1,max_length=200),format:Literal['csv','json']='json',session=Depends(session_for)):
        mode,handle,_=owned(workspace_id,session)
        return Response(service.export(mode,handle,board_id,revision_id,request,format),
            media_type='text/csv' if format=='csv' else 'application/json',
            headers={'Content-Disposition':'attachment; filename="evidence-view.'+format+'"'})
    @app.get(prefix+'/attributes/history',response_model=AttributeHistory,dependencies=dependencies)
    def attribute_history(workspace_id:str,board_id:str,paper_id:str,dimension_id:DimensionId,revision_id:str=Query(min_length=1,max_length=200),offset:int=Query(default=0,ge=0),limit:int=Query(default=20,ge=1,le=50),session=Depends(session_for)):
        mode,handle,_=owned(workspace_id,session)
        return service.attribute_history(mode,handle,board_id,revision_id,paper_id,dimension_id,offset,limit)

    @app.get(prefix+'/saved/{view_id}/history',response_model=SavedViewHistory,dependencies=dependencies)
    def view_history(workspace_id:str,board_id:str,view_id:str,revision_id:str=Query(min_length=1,max_length=200),offset:int=Query(default=0,ge=0),limit:int=Query(default=20,ge=1,le=50),session=Depends(session_for)):
        mode,handle,_=owned(workspace_id,session)
        return service.view_history(mode,handle,board_id,revision_id,view_id,offset,limit)
    return service
