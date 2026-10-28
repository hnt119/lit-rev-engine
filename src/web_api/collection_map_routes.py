"""Collection map routes with one shared pinned embedder/worker/cache."""
from fastapi import Depends, Query

from src.mvp.adapters.collection_map_storage import CollectionMapStore
from src.mvp.collection_map_jobs import CollectionMapService
from src.mvp.collection_mapping import (
    CollectionMapJobView, CollectionMapListing, CollectionMapSubmission,
    CollectionMapView, CreateCollectionMapRequest,
)
from src.mvp.mapping import Neighbors


def install_collection_map_routes(app, *, registry, service, owned, session_for,
                                  dependencies, legacy_maps=None, worker=None):
    """Call after install_map_routes and before its lifespan starts."""
    legacy = legacy_maps or app.state.maps
    shared_worker = worker or app.state.map_worker
    store = CollectionMapStore(legacy.store.path, **{
        key: getattr(legacy.store, key) for key in
        ('max_workspace_bytes', 'max_jobs', 'max_maps', 'max_embeddings', 'max_requests')})
    maps = CollectionMapService(registry, service, lambda mode: app.state.collections_for(mode), store, legacy.embedder)
    shared_worker.add_domain(maps)
    app.state.collection_maps = maps
    prefix = '/api/v1/workspaces/{workspace_id}'

    @app.post(prefix + '/collection-maps', response_model=CollectionMapSubmission, dependencies=dependencies)
    def submit(workspace_id: str, request: CreateCollectionMapRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        setup=getattr(app.state,'map_setup',None)
        selected=setup.bound_service(maps,session['token_hash']) if setup else maps
        result=selected.submit(mode, handle, request)
        if setup: setup.remember(result,selected.embedder)
        if setup: shared_worker.start(force=True)
        return result

    @app.get(prefix + '/collection-maps', response_model=CollectionMapListing, dependencies=dependencies)
    def listing(workspace_id: str, collection_id: str | None = Query(default=None, min_length=1, max_length=200),
                session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return maps.listing(mode, handle, collection_id)

    @app.get(prefix + '/collection-maps/{map_id}', response_model=CollectionMapView, dependencies=dependencies)
    def get_map(workspace_id: str, map_id: str, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return maps.map(mode, handle, map_id)

    @app.get(prefix + '/collection-maps/{map_id}/neighbors/{paper_id}', response_model=Neighbors, dependencies=dependencies)
    def neighbors(workspace_id: str, map_id: str, paper_id: str, limit: int = Query(default=5, ge=1, le=10),
                  session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return maps.neighbors(mode, handle, map_id, paper_id, limit)

    @app.get(prefix + '/collection-map-jobs/{job_id}', response_model=CollectionMapJobView, dependencies=dependencies)
    def job(workspace_id: str, job_id: str, session=Depends(session_for)):
        mode, handle, engine = owned(workspace_id, session)
        engine.get_workspace(handle)
        return maps.job(handle, job_id)

    @app.post(prefix + '/collection-map-jobs/{job_id}/cancel', response_model=CollectionMapJobView, dependencies=dependencies)
    def cancel(workspace_id: str, job_id: str, session=Depends(session_for)):
        mode, handle, engine = owned(workspace_id, session)
        engine.get_workspace(handle)
        return maps.cancel(handle, job_id)

    return maps
