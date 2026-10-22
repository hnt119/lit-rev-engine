"""One cooperative local preparation worker using existing source providers.

Fetching/parsing never holds a lifecycle guard, workspace flock, or database
transaction. Validated per-paper stages survive restart. Only a short atomic
research transaction can replace the previously usable preparation.
"""
from __future__ import annotations

import fcntl
import hashlib
import os
import secrets
import threading
import time

from .contracts import PreparedSource, StructuredError, digest
from .ports import MvpError, ProviderFailure
from .preparation_contracts import PreparationInput, PreparationJobRequest
from .service import _abstract, _assert_source_integrity, _find, _validated_source


class PreparationJobService:
    def __init__(self, registry, service_for, store_for):
        self.registry, self.service_for, self.store_for = registry, service_for, store_for

    def _with(self, mode, handle, callback):
        with self.registry.lifecycle_guard(handle.workspace_id):
            if self.registry.is_deleted(handle.workspace_id):
                raise MvpError('unknown_workspace', 'This workspace is unavailable.')
            return self.service_for(mode).with_workspace_state(handle, callback)

    def _read(self, mode, handle, callback):
        # Immutable input/progress reads and a job's own cancellation CAS need
        # capability/deletion checks, not the research mutation flock. Legacy
        # provider operations may still hold that flock while doing network I/O.
        with self.registry.lifecycle_guard(handle.workspace_id):
            if self.registry.is_deleted(handle.workspace_id):
                raise MvpError('unknown_workspace', 'This workspace is unavailable.')
            return callback(self.service_for(mode).get_workspace(handle))

    def submit(self, mode, handle, request: PreparationJobRequest):
        fingerprint = digest({'mode': mode, 'request': request.model_dump(mode='json')})
        def record(state):
            store = self.store_for(mode)
            prior = store.replay(state.id, request.request_id, fingerprint)
            if prior is not None:
                return prior
            current = state.preparations[-1].id if state.preparations else None
            if request.expected_source_revision != state.source_revision or request.expected_preparation_id != current:
                raise MvpError('stale_source_revision', 'The current preparation changed. Review the saved sources before submitting a new preparation job.')
            search = _find(state.searches, request.search_id, 'search')
            papers = [_find(search.papers, identifier, 'paper') for identifier in request.paper_ids]
            captured = PreparationInput(mode=mode, search_id=search.id,
                search_snapshot_sha256=digest(search.model_dump(mode='json')), search_provider=search.provider,
                paper_ids=request.paper_ids, papers=papers, expected_source_revision=state.source_revision,
                expected_preparation_id=current)
            return store.submit(state.id, request.request_id, fingerprint, captured)
        return self._with(mode, handle, record)

    def listing(self, mode, handle, search_id=None):
        def read(state):
            if search_id is not None:
                _find(state.searches, search_id, 'search')
            return self.store_for(mode).listing(state.id, search_id)
        return self._read(mode, handle, read)

    def job(self, mode, handle, job_id):
        return self._read(mode, handle, lambda state: self.store_for(mode).job(state.id, job_id))

    def cancel(self, mode, handle, job_id):
        return self._read(mode, handle, lambda state: self.store_for(mode).cancel(state.id, job_id))

    def check_input(self, engine, handle, captured):
        return PreparationWorker._check_input(engine, handle, captured)

    def prepare(self, engine, paper, captured):
        return PreparationWorker._prepare(engine, paper, captured)

    def publish(self, engine, handle, captured, sources, store, job):
        return engine.publish_preparation_job(handle=handle, job_id=job['id'],
            expected_source_revision=captured.expected_source_revision, search_id=captured.search_id,
            search_snapshot_sha256=captured.search_snapshot_sha256, paper_ids=captured.paper_ids, sources=sources,
            commit_guard=store.publication_guard(job), expected_preparation_id=captured.expected_preparation_id)

    def delete_workspace(self, workspace_id):
        # Research deletion normally cascades these rows already. Retrying this
        # trusted cleanup never creates a workspace or revives a former job.
        seen = set()
        for mode in ('saved_example', 'live'):
            try:
                store = self.store_for(mode)
            except MvpError:
                continue
            path = str(store.path.absolute())
            if path not in seen:
                store.delete_workspace(workspace_id)
                seen.add(path)


class PreparationWorker:
    def __init__(self, jobs: PreparationJobService, *, modes=('saved_example', 'live'),
                 poll_seconds=.5, heartbeat_seconds=20, lease_seconds=90, additional_domains=()):
        self.jobs, self.modes = jobs, tuple(modes)
        self.domains = (jobs, *tuple(additional_domains))
        if any(domain.registry is not jobs.registry for domain in self.domains):
            raise ValueError('Preparation domains must share one lifecycle/session registry')
        self.poll_seconds = max(.01, float(poll_seconds))
        self.heartbeat_seconds = max(.01, float(heartbeat_seconds))
        self.lease_seconds = max(.05, float(lease_seconds))
        if self.heartbeat_seconds >= self.lease_seconds:
            raise ValueError('Preparation heartbeat must be shorter than its lease')
        self._stop, self._thread = threading.Event(), None
        self._descriptors, self._owned_stores, self._owned_bindings = [], [], []
        self._queue_cursor = 0

    def _bindings(self):
        bindings, identities = [], set()
        for domain in self.domains:
            for mode in self.modes:
                try:
                    store = domain.store_for(mode)
                except MvpError as error:
                    if error.code in {'live_not_configured', 'invalid_configuration', 'invalid_mode'}:
                        continue
                    raise
                identity = (str(store.path.absolute()), store.job_table)
                if identity not in identities:
                    identities.add(identity)
                    bindings.append((domain, store))
        return bindings

    def _stores(self):
        return [store for _, store in self._bindings()]

    def _acquire(self):
        bindings = self._bindings()
        stores = [store for _, store in bindings]
        if not stores:
            return False
        locked = set()
        for store in stores:
            identity = str(store.path.absolute())
            if identity in locked:
                continue
            locked.add(identity)
            name = hashlib.sha256(identity.encode()).hexdigest()[:20]
            path = store.path.parent / ('preparation-worker-' + name + '.lock')
            descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(descriptor)
                self._release()
                return False
            self._descriptors.append(descriptor)
        self._owned_stores = stores
        self._owned_bindings = bindings
        try:
            for store in stores:
                store.recover()
        except BaseException:
            self._release()
            raise
        return True

    def _release(self):
        for descriptor in self._descriptors:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)
        self._descriptors, self._owned_stores, self._owned_bindings = [], [], []

    def start(self):
        if self._thread and self._thread.is_alive():
            return not self._stop.is_set()
        if not self._acquire():
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name='source-preparation-worker', daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            if self._thread.is_alive():
                # A bounded HTTP operation is cooperative: retain ownership
                # until its thread actually exits, preventing a second worker.
                return
        self._release()

    def _loop(self):
        try:
            while not self._stop.is_set():
                if not self.run_once():
                    self._stop.wait(self.poll_seconds)
        finally:
            self._release()

    def run_once(self):
        """One deterministic test/worker step; start() owns the production lock."""
        bindings = self._owned_bindings or self._bindings()
        if not bindings:
            return False
        start = self._queue_cursor % len(bindings)
        for offset in range(len(bindings)):
            index = (start + offset) % len(bindings)
            domain, store = bindings[index]
            job = store.claim(secrets.token_urlsafe(24), self.lease_seconds)
            if job is not None:
                self._queue_cursor = (index + 1) % len(bindings)
                self._process(store, job, domain)
                return True
        return False

    @staticmethod
    def _check_input(engine, handle, captured):
        state = engine.get_workspace(handle)
        search = _find(state.searches, captured.search_id, 'search')
        current = state.preparations[-1].id if state.preparations else None
        if (state.source_revision != captured.expected_source_revision or current != captured.expected_preparation_id
                or digest(search.model_dump(mode='json')) != captured.search_snapshot_sha256
                or [_find(search.papers, identifier, 'paper') for identifier in captured.paper_ids] != captured.papers):
            raise MvpError('preparation_stale_inputs', 'The retained search or current source preparation changed. This job cannot replace current sources.')

    @staticmethod
    def _prepare(engine, paper, captured):
        try:
            source = _validated_source(PreparedSource.model_validate(engine._sources.prepare(paper)), paper)
        except ProviderFailure as error:
            safe = StructuredError(code=error.code[:120], message=error.message[:1000], retryable=error.retryable, paper_id=paper.id)
            source = _abstract(paper, status='permission_unresolved' if error.code == 'permission_unresolved' else 'fetch_failed', error=safe)
        except Exception:
            source = _abstract(paper, status='fetch_failed', error=StructuredError(code='source_preparation_failed',
                message='Source preparation failed; the retained citation abstract is available where possible.', retryable=True, paper_id=paper.id))
        if source.provider == 'pubmed_abstract' and captured.search_provider != 'pubmed':
            source = source.model_copy(update={'provider': captured.search_provider + '_abstract',
                'parser_metadata': {**source.parser_metadata, 'origin': 'retained_search_citation_abstract',
                                    'search_id': captured.search_id, 'search_snapshot_sha256': captured.search_snapshot_sha256}})
        return source

    def _process(self, store, job, domain=None):
        jobs = domain or self.jobs
        finished, heartbeat_errors = threading.Event(), []
        started = time.monotonic()
        previous_elapsed = job['elapsed_seconds']
        def elapsed():
            return previous_elapsed + time.monotonic() - started
        def checkpoint(active_paper_id=None):
            if self._stop.is_set():
                raise MvpError('preparation_worker_interrupted', 'The preparation worker is stopping; validated stages can be resumed after restart.')
            if heartbeat_errors:
                raise heartbeat_errors[0]
            if jobs.registry.is_deleted(job['workspace_id']):
                raise MvpError('unknown_workspace', 'This workspace was deleted; preparation cannot publish.')
            store.checkpoint(job, elapsed_seconds=elapsed(), active_paper_id=active_paper_id, lease_seconds=self.lease_seconds)
        def heartbeat():
            while not finished.wait(self.heartbeat_seconds):
                try:
                    checkpoint()
                except MvpError as error:
                    heartbeat_errors.append(error)
                    return
        pulse = threading.Thread(target=heartbeat, name='source-preparation-lease', daemon=True)
        pulse.start()
        try:
            mode, handle = jobs.registry.get_bound_handle_for_worker(job['workspace_id'])
            captured = store.input(job)
            if mode != captured.mode:
                raise MvpError('preparation_integrity', 'The preparation workspace mode changed.')
            engine = jobs.service_for(mode)
            if engine._storage._path.absolute() != store.path.absolute():
                raise MvpError('preparation_integrity', 'The preparation job is bound to a different research store.')
            jobs.check_input(engine, handle, captured)
            papers = {paper.id: paper for paper in captured.papers}
            retained = {}
            for source in store.staged(job):
                if source.paper_id not in papers:
                    raise MvpError('preparation_integrity', 'A staged source does not belong to this input snapshot.')
                _assert_source_integrity([source])
                checked = _validated_source(source, papers[source.paper_id])
                if checked != source:
                    raise MvpError('preparation_integrity', 'A staged source no longer satisfies the recorded source contract.')
                retained[source.paper_id] = source
            for paper in captured.papers:
                checkpoint()
                if paper.id in retained:
                    continue
                checkpoint(paper.id)
                source = jobs.prepare(engine, paper, captured)
                checkpoint(paper.id)
                store.stage(job, source, elapsed_seconds=elapsed())
                retained[paper.id] = source
            checkpoint()
            sources = [retained[identifier] for identifier in captured.paper_ids]
            with jobs.registry.lifecycle_guard(handle.workspace_id):
                if jobs.registry.is_deleted(handle.workspace_id):
                    raise MvpError('unknown_workspace', 'This workspace was deleted; preparation cannot publish.')
                jobs.publish(engine, handle, captured, sources, store, job)
        except MvpError as error:
            if error.code == 'preparation_worker_interrupted':
                return
            store.finish_failure(job, error)
        except Exception:
            store.finish_failure(job, MvpError('preparation_failed', 'The bounded preparation job failed. Previously current sources and validated staged outcomes remain available.'))
        finally:
            finished.set()
            pulse.join(timeout=1)
