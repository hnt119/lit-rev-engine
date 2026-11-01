"""Collection map use cases sharing the pinned embedder and existing worker."""
from .collection_contracts import CollectionInputRef
from .collection_mapping import CollectionMapInput, build_collection_artifact, collection_counts
from .limits import MAX_COLLECTION_MAP_PAPERS
from .mapping import representations_for_papers
from .map_jobs import PaperMapService
from .ports import MvpError
from .adapters.map_storage import unavailable


class CollectionMapService(PaperMapService):
    def __init__(self, registry, service_for, collections_for, store, embedder):
        super().__init__(registry, service_for, store, embedder)
        self.collections_for = collections_for

    def submit(self, mode, handle, request):
        def record(state):
            if self.registry.is_deleted(state.id):
                raise unavailable('workspace')
            resolved = self.collections_for(mode).resolve_collection(handle, request.collection_ref)
            if len(resolved.members) > MAX_COLLECTION_MAP_PAPERS:
                raise MvpError('map_input_limit', 'A collection map is limited to 50 papers. Explicitly create a smaller collection snapshot; no records were truncated or embedded.')
            # Membership/size validation precedes readiness and any computation.
            ready, reason = self.readiness()
            if not ready:
                raise MvpError('map_setup_required', reason)
            captured = CollectionMapInput(collection_ref=request.collection_ref, members=list(resolved.members))
            return self.store.submit(handle.workspace_id, captured, self.embedder.profile, request, getattr(self, "adapter_config_json", None))
        with self.registry.lifecycle_guard(handle.workspace_id):
            return self.service_for(mode).with_workspace_state(handle, record)

    def listing(self, mode, handle, collection_id=None):
        self.service_for(mode).get_workspace(handle)
        if collection_id is not None:
            summary = self.collections_for(mode).collection(handle, collection_id)
            if not isinstance(summary.origin, CollectionInputRef):
                raise unavailable('collection')
        return self.store.listing(handle.workspace_id, collection_id)

    def map(self, mode, handle, map_id):
        self.service_for(mode).get_workspace(handle)
        result = self.store.map(handle.workspace_id, map_id)
        resolved = self.collections_for(mode).resolve_collection(handle, result.artifact.collection_ref)
        captured = self.store.captured_for_map(handle.workspace_id, map_id)
        if list(resolved.members) != captured.members or resolved.summary.origin != captured.collection_ref:
            raise MvpError('map_integrity', 'The collection map no longer matches its exact retained member snapshot.')
        return result

    def input_for_job(self, engine, handle, job):
        engine.get_workspace(handle)
        captured = self.store.input(job)
        resolved = self.collections_for(self.registry.get_bound_handle_for_worker(handle.workspace_id)[0]).resolve_collection(handle, captured.collection_ref)
        if resolved.summary.origin != captured.collection_ref or list(resolved.members) != captured.members:
            raise MvpError('map_integrity', 'The retained collection no longer matches this immutable map input.')
        return captured

    @staticmethod
    def representations_for_job(captured):
        return representations_for_papers(captured.papers)

    @staticmethod
    def build_for_job(workspace_id, captured, profile, embedded, excluded, map_id):
        return build_collection_artifact(workspace_id, captured, profile, embedded, excluded, map_id)

    def publish_job(self, engine, handle, job, captured, artifact, embedded):
        def publish(state):
            if self.registry.is_deleted(state.id):
                raise unavailable('workspace')
            retained = self.input_for_job(engine, handle, job)
            if retained != captured:
                raise MvpError('map_integrity', 'The collection map input changed before publication.')
            self.store.publish(job, artifact, embedded, collection_counts(captured, artifact))
        engine.with_workspace_state(handle, publish)
