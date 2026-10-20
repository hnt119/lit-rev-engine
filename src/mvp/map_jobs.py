"""Small durable map use cases and one cooperative local worker.

Only immutable saved paper metadata enters map jobs. No provider calls, source
preparation, passage retrieval, assessments or exports are performed here.
"""
from __future__ import annotations
import fcntl
import math
import os
from pathlib import Path
import secrets
import threading

from .contracts import SearchPreview, digest
from .mapping import (EmbeddingProfile, ExcludedPaper, Neighbor, Neighbors,
                      build_artifact, counts, representations, validate_vector)
from .ports import MvpError
from .adapters.map_storage import MapStore, unavailable


def find_search(state, search_id):
    search = next((item for item in state.searches if item.id == search_id), None)
    if search is None:
        raise unavailable("search")
    return search


class PaperMapService:
    def __init__(self, registry, service_for, store: MapStore, embedder):
        self.registry, self.service_for, self.store, self.embedder = registry, service_for, store, embedder

    def readiness(self):
        return self.embedder.readiness()

    def submit(self, mode, handle, request):
        ready, reason = self.readiness()
        if not ready:
            raise MvpError("map_setup_required", reason)
        profile = self.embedder.profile
        def record(state):
            if self.registry.is_deleted(state.id):
                raise unavailable("workspace")
            search = find_search(state, request.search_id)
            if len(search.papers) > 50:
                raise MvpError("map_input_limit", "A map is limited to the existing 50-record search preview.")
            return self.store.submit(handle.workspace_id, search, profile, request)
        with self.registry.lifecycle_guard(handle.workspace_id):
            return self.service_for(mode).with_workspace_state(handle, record)

    def listing(self, mode, handle, search_id):
        find_search(self.service_for(mode).get_workspace(handle), search_id)
        return self.store.listing(handle.workspace_id, search_id)

    def map(self, mode, handle, map_id):
        result = self.store.map(handle.workspace_id, map_id)
        search = find_search(self.service_for(mode).get_workspace(handle), result.artifact.search_id)
        if digest(search.model_dump(mode="json")) != result.artifact.search_snapshot_sha256:
            raise MvpError("map_integrity", "The map's saved bibliography no longer matches its immutable search binding.")
        return result

    def neighbors(self, mode, handle, map_id, paper_id, limit=5):
        self.map(mode, handle, map_id)
        vectors = self.store.vectors(handle.workspace_id, map_id)
        if paper_id not in vectors:
            raise unavailable("paper")
        query = vectors[paper_id]
        ordered = []
        for identifier, vector in vectors.items():
            if identifier != paper_id:
                value = max(-1.0, min(1.0, sum(a * b for a, b in zip(query, vector))))
                ordered.append(Neighbor(paper_id=identifier, cosine_similarity=value))
        ordered.sort(key=lambda item: (-item.cosine_similarity, item.paper_id))
        return Neighbors(map_id=map_id, paper_id=paper_id, neighbors=ordered[:limit])

    def job(self, handle, job_id):
        return self.store.job(handle.workspace_id, job_id)

    def cancel(self, handle, job_id):
        return self.store.cancel(handle.workspace_id, job_id)

    def delete_workspace(self, workspace_id):
        self.store.delete_workspace(workspace_id)


class MapWorker:
    def __init__(self, maps: PaperMapService, *, poll_seconds=0.5, heartbeat_seconds=10, lease_seconds=120):
        self.maps = maps
        self.poll_seconds, self.heartbeat_seconds, self.lease_seconds = poll_seconds, heartbeat_seconds, lease_seconds
        self._stop, self._thread, self._descriptor = threading.Event(), None, None

    def _acquire(self):
        path = self.maps.store.path.parent / "paper-map-worker.lock"
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(descriptor)
            return False
        self._descriptor = descriptor
        self.maps.store.recover()
        return True

    def _release(self):
        if self._descriptor is not None:
            fcntl.flock(self._descriptor, fcntl.LOCK_UN)
            os.close(self._descriptor)
            self._descriptor = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return True
        if not self.maps.readiness()[0] or not self._acquire():
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="paper-map-worker", daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            # A running native projection cannot be forcibly interrupted. Keep
            # its OS lock while that cooperative worker still owns the attempt.
            if self._thread.is_alive():
                return
        self._release()

    def _loop(self):
        try:
            while not self._stop.is_set():
                if not self.run_once():
                    self._stop.wait(self.poll_seconds)
        finally:
            self._release()

    def run_forever(self):
        if not self.maps.readiness()[0]:
            raise MvpError("map_setup_required", self.maps.readiness()[1])
        if not self._acquire():
            raise MvpError("map_worker_busy", "Another local map worker already owns this data directory.")
        try:
            self._loop()
        except KeyboardInterrupt:
            self._stop.set()

    def run_once(self):
        """One deterministic worker step; production launch owns the OS lock."""
        job = self.maps.store.claim(secrets.token_urlsafe(24), self.lease_seconds)
        if job is None:
            return False
        self._process(job)
        return True

    def _process(self, job):
        finished, heartbeat_errors = threading.Event(), []
        def checkpoint(completed=None):
            if self._stop.is_set():
                raise MvpError("map_worker_interrupted", "The local map worker is stopping. This attempt can be recovered after restart.", True)
            if heartbeat_errors:
                raise heartbeat_errors[0]
            if self.maps.registry.is_deleted(job["workspace_id"]):
                raise unavailable("workspace")
            self.maps.store.checkpoint(job, completed=completed, lease_seconds=self.lease_seconds)
        def heartbeat():
            while not finished.wait(self.heartbeat_seconds):
                try:
                    checkpoint()
                except MvpError as error:
                    heartbeat_errors.append(error)
                    return
        pulse = threading.Thread(target=heartbeat, name="paper-map-lease", daemon=True)
        pulse.start()
        try:
            mode, handle = self.maps.registry.get_bound_handle_for_worker(job["workspace_id"])
            engine = self.maps.service_for(mode)
            search = SearchPreview.model_validate_json(job["search_json"])
            profile = EmbeddingProfile.model_validate_json(job["profile_json"])
            actual = find_search(engine.get_workspace(handle), job["search_id"])
            if digest(actual.model_dump(mode="json")) != digest(search.model_dump(mode="json")):
                raise MvpError("map_integrity", "Saved search no longer matches this map job.")
            if self.maps.embedder.profile != profile:
                raise MvpError("embedding_profile_changed", "Configured local embedding profile changed; explicitly build a new map.")
            embedded, excluded = [], []
            for index, representation in enumerate(representations(search)):
                checkpoint(index)
                try:
                    item = self.maps.store.embedding(handle.workspace_id, profile, representation)
                    if item is None:
                        item = self.maps.embedder.embed(representation, checkpoint)
                        if item.paper_id != representation.paper_id or item.input_sha256 != representation.input_sha256 or item.representation != representation.representation:
                            raise MvpError("embedding_identity", "Embedding output did not match its exact paper input.")
                        validate_vector(item.vector, profile.dimension)
                        item = self.maps.store.put_embedding(handle.workspace_id, profile, item)
                    embedded.append(item)
                except MvpError as error:
                    if error.code in {"map_cancelled", "map_attempt_lost", "unknown_workspace", "map_worker_interrupted", "map_storage_limit", "map_integrity", "embedding_profile_changed", "embedding_profile_mismatch", "map_setup_required"}:
                        raise
                    excluded.append(ExcludedPaper(paper_id=representation.paper_id, code=error.code, reason=error.message))
                except Exception:
                    excluded.append(ExcludedPaper(paper_id=representation.paper_id, code="embedding_failed", reason="This paper's embedding failed validation or local calculation; no position was invented."))
                checkpoint(index + 1)
            artifact, embedded = build_artifact(handle.workspace_id, search, profile, embedded, excluded, job["map_id"])
            checkpoint(len(search.papers))
            def publish(state):
                if self.maps.registry.is_deleted(state.id):
                    raise unavailable("workspace")
                retained = find_search(state, search.id)
                if digest(retained.model_dump(mode="json")) != artifact.search_snapshot_sha256:
                    raise MvpError("map_integrity", "Map search binding changed before publication.")
                self.maps.store.publish(job, artifact, embedded, counts(search, artifact))
            # Match deletion's lifecycle -> research-lock order. Publication
            # linearizes before deletion, or observes its persistent tombstone.
            with self.maps.registry.lifecycle_guard(handle.workspace_id):
                engine.with_workspace_state(handle, publish)
        except MvpError as error:
            if error.code == "map_worker_interrupted":
                # Keep running/lease evidence for bounded restart recovery.
                return
            self.maps.store.finish_failure(job, error)
        except Exception:
            self.maps.store.finish_failure(job, MvpError("map_build_failed", "The local map calculation failed. Existing evidence and drafts are unchanged."))
        finally:
            finished.set()
            pulse.join(timeout=1)
