"""Authorized collection queue projections; worker ownership stays shared."""
from threading import Lock

from fastapi import Depends, Query

from src.mvp.adapters.collection_preparation_storage import CollectionPreparationStore
from src.mvp.collection_preparation_contracts import (
    CollectionPreparationJobListing, CollectionPreparationJobRequest,
    CollectionPreparationJobView, CollectionPreparationSubmission,
)
from src.mvp.collection_preparation_jobs import CollectionPreparationJobService


def install_collection_preparation_routes(app, *, registry, service, owned, session_for,
                                          dependencies, collections_for=None):
    """Install before the shared worker; pass returned jobs as an extra domain."""
    stores, lock = {}, Lock()

    def store_for(mode):
        engine = service(mode)
        path = str(engine._storage._path.absolute())
        with lock:
            if path not in stores:
                stores[path] = CollectionPreparationStore(engine._storage)
            return stores[path]

    def resolve_collections(mode):
        return (collections_for or app.state.collections_for)(mode)

    jobs = CollectionPreparationJobService(registry, service, store_for, resolve_collections)
    app.state.collection_preparation_jobs = jobs
    prefix = '/api/v1/workspaces/{workspace_id}/collection-preparation-jobs'

    @app.post(prefix, response_model=CollectionPreparationSubmission, status_code=202, dependencies=dependencies)
    def submit(workspace_id: str, request: CollectionPreparationJobRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return jobs.submit(mode, handle, request)

    @app.get(prefix, response_model=CollectionPreparationJobListing, dependencies=dependencies)
    def listing(workspace_id: str, collection_id: str | None = Query(default=None, min_length=1, max_length=200),
                session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return jobs.listing(mode, handle, collection_id)

    @app.get(prefix + '/{job_id}', response_model=CollectionPreparationJobView, dependencies=dependencies)
    def job(workspace_id: str, job_id: str, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return jobs.job(mode, handle, job_id)

    @app.post(prefix + '/{job_id}/cancel', response_model=CollectionPreparationJobView, dependencies=dependencies)
    def cancel(workspace_id: str, job_id: str, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return jobs.cancel(mode, handle, job_id)

    return jobs
