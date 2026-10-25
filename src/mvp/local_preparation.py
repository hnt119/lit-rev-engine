"""Private standalone UI binding for the same durable preparation service.

This is not another engine or HTTP authorization route. A valid local handle is
verified before it is retained in a private worker vault for restart recovery.
"""
from pathlib import Path
from threading import Lock

from .adapters.preparation_storage import PreparationStore
from .bootstrap import build_service
from .preparation_jobs import PreparationJobService, PreparationWorker
from .workspace_ui import WorkspaceUIStore


class LocalPreparationRuntime:
    def __init__(self, storage_path):
        self.directory = Path(storage_path).absolute().parent
        # A shared data directory must also share the private worker vault.
        # Browser ownership remains session-bound; this issues no HTTP session.
        self.registry = WorkspaceUIStore(self.directory / "web-credentials.sqlite3")
        self.engines, self.stores, self.lock = {}, {}, Lock()
        self.collection_stores, self.collection_services = {}, {}
        self.jobs = PreparationJobService(self.registry, self.service_for, self.store_for)
        from .collection_preparation_jobs import CollectionPreparationJobService
        self.collection_jobs = CollectionPreparationJobService(self.registry, self.service_for,
            self.collection_store_for, self.collections_for)
        self.worker = PreparationWorker(self.jobs, additional_domains=(self.collection_jobs,))

    def bind(self, mode, handle, engine):
        if Path(engine._storage._path).absolute().parent != self.directory:
            from .ports import MvpError
            raise MvpError("preparation_integrity", "Local preparation must use the existing research data directory.")
        with self.lock:
            self.engines[mode] = engine
        self.registry.register_local_handle_for_worker(mode, handle, engine.get_workspace)
        self.worker.start()

    def service_for(self, mode):
        with self.lock:
            if mode not in self.engines:
                self.engines[mode] = build_service(mode, self.directory)
            return self.engines[mode]

    def store_for(self, mode):
        engine = self.service_for(mode)
        path = str(engine._storage._path.absolute())
        with self.lock:
            if path not in self.stores:
                self.stores[path] = PreparationStore(engine._storage)
            return self.stores[path]

    def clear(self, mode, handle, engine):
        engine.get_workspace(handle)
        with self.registry.connection() as db:
            row = db.execute("SELECT session_hash FROM web_workspaces WHERE workspace_id=?", (handle.workspace_id,)).fetchone()
        if row is None:
            return engine.clear_workspace(handle)
        self.registry.delete_workspace(row["session_hash"], handle.workspace_id,
            lambda bound_mode, bound_handle: engine.clear_workspace_if_present(bound_handle),
            lambda identifier: (self.jobs.delete_workspace(identifier), self.collection_jobs.delete_workspace(identifier)))

    def collection_store_for(self, mode):
        from .adapters.collection_preparation_storage import CollectionPreparationStore
        engine = self.service_for(mode)
        path = str(engine._storage._path.absolute())
        with self.lock:
            if path not in self.collection_stores:
                self.collection_stores[path] = CollectionPreparationStore(engine._storage)
            return self.collection_stores[path]

    def collections_for(self, mode):
        from .collections import CollectionService
        from .adapters.collection_storage import CollectionStore
        engine = self.service_for(mode)
        with self.lock:
            if mode not in self.collection_services:
                self.collection_services[mode] = CollectionService(engine, CollectionStore(engine._storage))
            return self.collection_services[mode]
