"""Explicit local pack/index actions; GET never performs inference or download."""
from typing import Literal
from fastapi import Depends, Response
from pydantic import Field
from src.mvp.contracts import Model
from src.mvp.ports import MvpError
from src.mvp.hybrid_app_contracts import HybridScopeRequest, HybridSearchRequest, HybridSavedRun, HybridRunListing, HybridSourceContext

class UnavailablePacks:
    """Read-only pinned metadata when the optional external cache is unsafe.

    This wrapper never selects another retrieval method or touches the rejected
    path. Existing saved evidence and the core/manual workflow stay available.
    """
    available = False
    root = None
    unavailable_reason = ('Optional retrieval cache is unavailable or unsafe. Configure an owned private external '
        'LITREV_RETRIEVAL_CACHE directory and restart; no models were loaded and no lexical fallback was selected.')

    @staticmethod
    def manifest(profile_id):
        from src.mvp.retrieval_packs import _manifest
        from src.mvp.contracts import canonical
        import json
        return json.loads(canonical(_manifest(profile_id)))

    def status(self,profile_id):
        from src.mvp.contracts import digest
        pack=self.manifest(profile_id)
        return dict(profile_id=profile_id,pack_id=pack['pack_id'],label=pack['label'],state='cache_unavailable',
            installed=False,download_bytes=pack['download_bytes'],downloaded_bytes=0,
            manifest_sha256=digest(pack),models=[{'repo':m['repo'],'revision':m['revision'],'bytes':m['selected_bytes']} for m in pack['models']],
            license=pack['license'],quality_status=pack['quality_status'],runtime=None,runtime_by_device={},
            index_state='cache_unavailable',message=self.unavailable_reason)

    def capabilities(self):
        from src.mvp.retrieval_packs import REGISTRY
        return [self.status(profile_id) for profile_id in REGISTRY]

    def _unavailable(self,*args,**kwargs):
        raise MvpError('retrieval_cache_unavailable',self.unavailable_reason)

    install = _unavailable
    check_runtime = _unavailable
    adapter = _unavailable
    cancel = _unavailable
    remove = _unavailable


class RetrievalPackAction(Model):
    expected_revision: int = Field(ge=0, strict=True)
    profile_id: Literal['hybrid_qwen3_06b_rrf_rerank_v1','hybrid_medcpt_passage_rrf_rerank_v1']
    device: Literal['cpu','mps'] = 'cpu'


def install_retrieval_routes(app, *, directory, registry, service, owned, session_for, dependencies, packs=None):
    if app.state.deployment.hosted:
        app.state.hybrid_retrieval=None
        return
    from src.mvp.retrieval_packs import PackManager
    from src.mvp.hybrid_service import HybridEvidenceService
    if packs is None:
        try:
            packs=PackManager()
        except (MvpError,OSError):
            # Optional cache configuration cannot take manual research offline.
            # Preserve the rejected path as-is; never create a cache in the app.
            packs=UnavailablePacks()
    runtime=HybridEvidenceService(registry,service,app.state.boards,directory,packs)
    app.state.hybrid_retrieval=runtime
    app.state.boards.hybrid_retrieval=runtime
    app.state.retrieval_packs=packs
    prefix='/api/v1/workspaces/{workspace_id}'

    @app.get('/api/v1/settings/retrieval', dependencies=dependencies)
    def capabilities(session=Depends(session_for)):
        return {'schema_version':'mvp.retrieval-capabilities.v1','core_lexical_available':True,
            'packs':packs.capabilities(),'default_changes':'future_explicit_operations_only',
            'quality_status':'experimental_not_evidence_of_support'}

    def checked(request,session):
        app.state.runtime_settings.assert_current(session['token_hash'],request.expected_revision)

    @app.post('/api/v1/settings/retrieval/install', dependencies=dependencies)
    def install(request:RetrievalPackAction,session=Depends(session_for)):
        checked(request,session)
        return packs.install(request.profile_id)

    @app.post('/api/v1/settings/retrieval/cancel', dependencies=dependencies)
    def cancel_pack(request:RetrievalPackAction,session=Depends(session_for)):
        checked(request,session);packs.cancel(request.profile_id)
        return packs.status(request.profile_id)

    @app.post('/api/v1/settings/retrieval/check-runtime', dependencies=dependencies)
    def check(request:RetrievalPackAction,session=Depends(session_for)):
        checked(request,session)
        return packs.check_runtime(request.profile_id,request.device)

    @app.post('/api/v1/settings/retrieval/remove', dependencies=dependencies)
    def remove(request:RetrievalPackAction,session=Depends(session_for)):
        checked(request,session);packs.remove(request.profile_id)
        return packs.status(request.profile_id)

    @app.post(prefix+'/hybrid-index/status', dependencies=dependencies)
    def index_status(workspace_id:str,request:HybridScopeRequest,session=Depends(session_for)):
        mode,handle,_=owned(workspace_id,session)
        return runtime.index_state(mode,handle,request)

    @app.post(prefix+'/hybrid-index', dependencies=dependencies)
    def index(workspace_id:str,request:HybridScopeRequest,session=Depends(session_for)):
        mode,handle,_=owned(workspace_id,session)
        return runtime.build_index(mode,handle,request)

    @app.post(prefix+'/hybrid-runs', response_model=HybridSavedRun, dependencies=dependencies)
    def retrieve(workspace_id:str,request:HybridSearchRequest,session=Depends(session_for)):
        mode,handle,_=owned(workspace_id,session)
        return runtime.search(mode,handle,request)

    @app.get(prefix+'/hybrid-runs', response_model=HybridRunListing, dependencies=dependencies)
    def runs(workspace_id:str,session=Depends(session_for)):
        _,handle,_=owned(workspace_id,session)
        return HybridRunListing(runs=runtime.runs(handle.workspace_id))

    @app.get(prefix+'/hybrid-runs/{run_id}', response_model=HybridSavedRun, dependencies=dependencies)
    def get_run(workspace_id:str,run_id:str,session=Depends(session_for)):
        _,handle,_=owned(workspace_id,session)
        return runtime.get(handle.workspace_id,run_id)

    @app.get(prefix+'/hybrid-runs/{run_id}/candidates/{candidate_id}/context', response_model=HybridSourceContext, dependencies=dependencies)
    def context(workspace_id:str,run_id:str,candidate_id:str,session=Depends(session_for)):
        mode,handle,_=owned(workspace_id,session)
        return runtime.inspect(mode,handle,run_id,candidate_id)

    @app.get(prefix+'/hybrid-exports', dependencies=dependencies)
    def export(workspace_id:str,session=Depends(session_for)):
        from src.mvp.contracts import canonical
        _,handle,_=owned(workspace_id,session)
        body=canonical({'schema_version':'mvp.hybrid-export.v1','workspace_id':workspace_id,
            'runs':[run.model_dump(mode='json') for run in runtime.runs(handle.workspace_id)]})
        return Response(body,media_type='application/json',headers={'Content-Disposition':'attachment; filename="hybrid-evidence.json"'})

    @app.get(prefix+'/hybrid-jobs/{job_id}', dependencies=dependencies)
    def job(workspace_id:str,job_id:str,session=Depends(session_for)):
        _,handle,_=owned(workspace_id,session)
        return runtime.job(handle.workspace_id,job_id)

    @app.post(prefix+'/hybrid-jobs/{job_id}/cancel', dependencies=dependencies)
    def cancel(workspace_id:str,job_id:str,session=Depends(session_for)):
        _,handle,_=owned(workspace_id,session)
        return runtime.cancel(handle.workspace_id,job_id)
