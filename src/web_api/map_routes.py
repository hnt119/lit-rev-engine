"""Authorized optional map endpoints; no raw model vectors in browser JSON."""
from contextlib import asynccontextmanager
import os
from fastapi import Depends, Query
from src.mvp.adapters.map_storage import MapStore
from src.mvp.adapters.paper_embeddings import LocalPaperEmbedder
from src.mvp.map_jobs import MapWorker, PaperMapService
from src.mvp.mapping import CreateMapRequest, MapJobView, MapListing, MapSubmission, MapView, Neighbors


def install_map_routes(app, *, directory, registry, service, owned, session_for, dependencies, embedder=None):
    hosted = getattr(getattr(app.state, "deployment", None), "hosted", False)
    class HostedDisabledEmbedder(LocalPaperEmbedder):
        def readiness(self):
            return False, "Hosted map computation is disabled. Saved example maps remain available."
    embedding = HostedDisabledEmbedder(enabled=False) if hosted else embedder or LocalPaperEmbedder(enabled=os.environ.get("MVP_MAP_ENABLED") == "1")
    maps = PaperMapService(registry, service, MapStore(directory / "paper-maps.sqlite3"), embedding)
    worker = MapWorker(maps)
    app.state.maps, app.state.map_worker = maps, worker
    previous_lifespan = app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(application):
        async with previous_lifespan(application):
            if not hosted:
                worker.start()
            try:
                yield
            finally:
                if not hosted:
                    worker.stop()
    app.router.lifespan_context = lifespan
    prefix = "/api/v1/workspaces/{workspace_id}"

    @app.post(prefix + "/maps", response_model=MapSubmission, dependencies=dependencies)
    def submit(workspace_id: str, request: CreateMapRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return maps.submit(mode, handle, request)

    @app.get(prefix + "/maps", response_model=MapListing, dependencies=dependencies)
    def listing(workspace_id: str, search_id: str, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return maps.listing(mode, handle, search_id)

    @app.get(prefix + "/maps/{map_id}", response_model=MapView, dependencies=dependencies)
    def get_map(workspace_id: str, map_id: str, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return maps.map(mode, handle, map_id)

    @app.get(prefix + "/maps/{map_id}/neighbors/{paper_id}", response_model=Neighbors, dependencies=dependencies)
    def neighbors(workspace_id: str, map_id: str, paper_id: str, limit: int = Query(default=5, ge=1, le=10), session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return maps.neighbors(mode, handle, map_id, paper_id, limit)

    @app.get(prefix + "/jobs/{job_id}", response_model=MapJobView, dependencies=dependencies)
    def job(workspace_id: str, job_id: str, session=Depends(session_for)):
        _, handle, _ = owned(workspace_id, session)
        return maps.job(handle, job_id)

    @app.post(prefix + "/jobs/{job_id}/cancel", response_model=MapJobView, dependencies=dependencies)
    def cancel(workspace_id: str, job_id: str, session=Depends(session_for)):
        _, handle, _ = owned(workspace_id, session)
        return maps.cancel(handle, job_id)
    return maps
