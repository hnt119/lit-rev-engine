"""Authorized small projections for persisted, in-process source preparation."""
from contextlib import asynccontextmanager
from threading import Lock

from fastapi import Depends, Query

from src.mvp.adapters.preparation_storage import PreparationStore
from src.mvp.preparation_contracts import (
    PreparationJobListing, PreparationJobRequest, PreparationJobView, PreparationSubmission,
)
from src.mvp.preparation_jobs import PreparationJobService, PreparationWorker


def install_preparation_routes(app, *, registry, service, owned, session_for, dependencies, additional_domains=()):
    stores, store_lock = {}, Lock()

    def store_for(mode):
        engine = service(mode)
        path = str(engine._storage._path.absolute())
        with store_lock:
            if path not in stores:
                stores[path] = PreparationStore(engine._storage)
            return stores[path]

    jobs = PreparationJobService(registry, service, store_for)
    worker = PreparationWorker(jobs, additional_domains=additional_domains)
    app.state.preparation_jobs = jobs
    app.state.preparation_worker = worker
    app.state.preparation_jobs_ready = False
    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with previous(application):
            app.state.preparation_jobs_ready = worker.start()
            try:
                yield
            finally:
                app.state.preparation_jobs_ready = False
                worker.stop()

    app.router.lifespan_context = lifespan
    prefix = "/api/v1/workspaces/{workspace_id}/preparation-jobs"

    @app.post(prefix, response_model=PreparationSubmission, status_code=202, dependencies=dependencies)
    def submit(workspace_id: str, request: PreparationJobRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return jobs.submit(mode, handle, request)

    @app.get(prefix, response_model=PreparationJobListing, dependencies=dependencies)
    def listing(workspace_id: str, search_id: str | None = Query(default=None, min_length=1, max_length=200),
                session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return jobs.listing(mode, handle, search_id)

    @app.get(prefix + "/{job_id}", response_model=PreparationJobView, dependencies=dependencies)
    def job(workspace_id: str, job_id: str, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return jobs.job(mode, handle, job_id)

    @app.post(prefix + "/{job_id}/cancel", response_model=PreparationJobView, dependencies=dependencies)
    def cancel(workspace_id: str, job_id: str, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return jobs.cancel(mode, handle, job_id)

    return jobs
