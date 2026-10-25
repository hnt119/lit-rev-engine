"""Explicit citation import and immutable collection projections."""
from threading import Lock
from typing import Literal
from urllib.parse import unquote

from fastapi import Body, Depends, Header, Query

from src.mvp.adapters.collection_storage import CollectionStore
from src.mvp.collection_contracts import (
    CollectionListing, CollectionPaperDetail, CollectionPaperPage, CollectionSummary,
    CombineCollectionsPreview, CombineCollectionsRequest, ImportCommitRequest,
    ImportEditRowRequest, ImportListing, ImportMappingRequest, ImportResolveRequest,
    ImportRowPage, ImportSummary,
)
from src.mvp.collections import CollectionService


def install_collection_routes(app, *, service, owned, session_for, dependencies, metadata_resolver=None):
    stores, services, lock = {}, {}, Lock()
    app.state.collection_services = services

    def collections(mode):
        with lock:
            if mode not in services:
                engine = service(mode)
                path = str(engine._storage._path.absolute())
                if path not in stores:
                    stores[path] = CollectionStore(engine._storage)
                services[mode] = CollectionService(engine, stores[path], resolver=metadata_resolver,
                    registry=app.state.registry)
            return services[mode]

    app.state.collections_for = collections
    prefix = '/api/v1/workspaces/{workspace_id}'

    @app.post(prefix + '/imports/{format}', response_model=ImportSummary, dependencies=dependencies)
    def upload(workspace_id: str, format: Literal['csv', 'ris', 'identifiers'],
               payload: bytes = Body(media_type='application/octet-stream'),
               request_id: str = Header(alias='X-Request-ID', min_length=1, max_length=200),
               filename: str | None = Header(default=None, alias='X-Import-Filename', max_length=4096),
               session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return collections(mode).upload(handle, payload, format, request_id,
            filename=unquote(filename) if filename else None)

    @app.get(prefix + '/imports', response_model=ImportListing, dependencies=dependencies)
    def imports(workspace_id: str, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return collections(mode).imports(handle)

    @app.get(prefix + '/imports/{import_id}', response_model=ImportSummary, dependencies=dependencies)
    def summary(workspace_id: str, import_id: str, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return collections(mode).import_summary(handle, import_id)

    @app.get(prefix + '/imports/{import_id}/rows', response_model=ImportRowPage, dependencies=dependencies)
    def rows(workspace_id: str, import_id: str, offset: int = Query(default=0, ge=0),
             limit: int = Query(default=25, ge=1, le=50), session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return collections(mode).import_rows(handle, import_id, offset, limit)

    @app.post(prefix + '/imports/{import_id}/mapping', response_model=ImportSummary, dependencies=dependencies)
    def mapping(workspace_id: str, import_id: str, request: ImportMappingRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return collections(mode).remap(handle, import_id, request)

    @app.post(prefix + '/imports/{import_id}/resolve', response_model=ImportSummary, dependencies=dependencies)
    def resolve(workspace_id: str, import_id: str, request: ImportResolveRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return collections(mode).resolve_metadata(handle, import_id, request)

    @app.post(prefix + '/imports/{import_id}/edit-row', response_model=ImportSummary, dependencies=dependencies)
    def edit_row(workspace_id: str, import_id: str, request: ImportEditRowRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return collections(mode).edit_row(handle, import_id, request)

    @app.post(prefix + '/imports/{import_id}/commit', response_model=CollectionSummary, dependencies=dependencies)
    def commit(workspace_id: str, import_id: str, request: ImportCommitRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return collections(mode).commit_import(handle, import_id, request)

    @app.get(prefix + '/collections', response_model=CollectionListing, dependencies=dependencies)
    def listing(workspace_id: str, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return collections(mode).listing(handle)

    @app.post(prefix + '/collections/combine-preview', response_model=CombineCollectionsPreview, dependencies=dependencies)
    def combine_preview(workspace_id: str, request: CombineCollectionsRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return collections(mode).combine_preview(handle, request)

    @app.post(prefix + '/collections/combine', response_model=CollectionSummary, dependencies=dependencies)
    def combine(workspace_id: str, request: CombineCollectionsRequest, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return collections(mode).combine(handle, request)

    @app.get(prefix + '/collections/{collection_id}', response_model=CollectionSummary, dependencies=dependencies)
    def collection(workspace_id: str, collection_id: str, session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return collections(mode).collection(handle, collection_id)

    @app.get(prefix + '/collections/{collection_id}/papers', response_model=CollectionPaperPage, dependencies=dependencies)
    def papers(workspace_id: str, collection_id: str, offset: int = Query(default=0, ge=0),
               limit: int = Query(default=25, ge=1, le=50), filter: str = Query(default='', max_length=200),
               session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return collections(mode).papers(handle, collection_id, offset, limit, filter)

    @app.get(prefix + '/collections/{collection_id}/paper', response_model=CollectionPaperDetail, dependencies=dependencies)
    def paper(workspace_id: str, collection_id: str, paper_id: str = Query(min_length=1, max_length=4096),
              session=Depends(session_for)):
        mode, handle, _ = owned(workspace_id, session)
        return collections(mode).paper(handle, collection_id, paper_id)

    return collections
