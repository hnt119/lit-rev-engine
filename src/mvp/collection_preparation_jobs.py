"""Collection preparation through the existing provider-owning local worker."""
from .collection_contracts import CollectionInputRef
from .collection_preparation_contracts import CollectionPreparationInput, CollectionPreparationJobRequest
from .contracts import PreparedSource, StructuredError, digest
from .ports import MvpError, ProviderFailure
from .preparation_jobs import PreparationJobService
from .service import _abstract, _validated_source


class CollectionPreparationJobService(PreparationJobService):
    def __init__(self, registry, service_for, store_for, collections_for):
        super().__init__(registry, service_for, store_for)
        self.collections_for = collections_for

    def submit(self, mode, handle, request: CollectionPreparationJobRequest):
        fingerprint = digest({'mode': mode, 'request': request.model_dump(mode='json')})

        def record(state):
            store = self.store_for(mode)
            prior = store.replay(state.id, request.request_id, fingerprint)
            if prior is not None:
                return prior
            current = state.preparations[-1].id if state.preparations else None
            if request.expected_source_revision != state.source_revision or request.expected_preparation_id != current:
                raise MvpError('stale_source_revision', 'The current preparation changed. Review retained sources before submitting a new collection preparation.')
            resolved = self.collections_for(mode).resolve_collection(handle, request.collection_ref)
            members = {member.paper.id: member for member in resolved.members}
            if len(members) != len(resolved.members) or any(identifier not in members for identifier in request.paper_ids):
                raise MvpError('unknown_paper', 'Every selected paper must belong to this exact collection snapshot.')
            captured = CollectionPreparationInput(mode=mode, collection_ref=request.collection_ref,
                paper_ids=request.paper_ids, members=[members[identifier] for identifier in request.paper_ids],
                expected_source_revision=state.source_revision, expected_preparation_id=current)
            return store.submit(state.id, request.request_id, fingerprint, captured)

        return self._with(mode, handle, record)

    def listing(self, mode, handle, collection_id=None):
        def read(state):
            if collection_id is not None:
                summary = self.collections_for(mode).collection(handle, collection_id)
                if not isinstance(summary.origin, CollectionInputRef):
                    raise MvpError('unknown_collection', 'Collection preparation jobs require an imported or combined collection.')
            return self.store_for(mode).listing(state.id, collection_id)
        return self._read(mode, handle, read)

    def check_input(self, engine, handle, captured):
        state = engine.get_workspace(handle)
        current = state.preparations[-1].id if state.preparations else None
        if state.source_revision != captured.expected_source_revision or current != captured.expected_preparation_id:
            raise MvpError('preparation_stale_inputs', 'The current preparation changed; this collection job cannot replace it.')
        resolved = self.collections_for(captured.mode).resolve_collection(handle, captured.collection_ref)
        members = {member.paper.id: member for member in resolved.members}
        if (resolved.summary.origin != captured.collection_ref or len(members) != len(resolved.members)
                or any(identifier not in members for identifier in captured.paper_ids)
                or [members[identifier] for identifier in captured.paper_ids] != captured.members):
            raise MvpError('preparation_stale_inputs', 'The selected collection/member metadata changed; this job cannot publish.')

    def prepare(self, engine, paper, captured):
        try:
            prepare = getattr(engine._sources, 'prepare_collection_paper', None) or engine._sources.prepare
            source = _validated_source(PreparedSource.model_validate(prepare(paper)), paper)
        except ProviderFailure as error:
            safe = StructuredError(code=error.code[:120], message=error.message[:1000], retryable=error.retryable, paper_id=paper.id)
            source = _abstract(paper, status='permission_unresolved' if error.code == 'permission_unresolved' else 'fetch_failed', error=safe)
        except Exception:
            source = _abstract(paper, status='fetch_failed', error=StructuredError(code='source_preparation_failed',
                message='Source preparation failed; retained citation text remains available where possible.', retryable=True, paper_id=paper.id))
        retained_abstract = source.provider == 'pubmed_abstract' or source.parser_metadata.get('origin') == 'discovered_citation_abstract'
        if source.source_type in {'abstract', 'none'} and retained_abstract:
            member = next((member for member in captured.members if member.paper.id == paper.id), None)
            if member is None:
                raise MvpError('preparation_integrity', 'The retained abstract does not belong to the selected collection input.')
            version = member.metadata_version
            source = source.model_copy(update={
                'provider': version.abstract_provider,
                'parser_metadata': {**source.parser_metadata,
                    'origin': 'retained_collection_citation_abstract',
                    'collection_ref': captured.collection_ref.model_dump(mode='json'),
                    'metadata_version_id': version.id,
                    'metadata_snapshot_sha256': digest(version.model_dump(mode='json')),
                    'retrieval_attempt_provider': source.provider,
                    'abstract_field_origin': version.field_origins.get('abstract'),
                    'member_origins': [origin.model_dump(mode='json') for origin in member.origins],
                    'resolution_receipts': [{'provider': receipt.provider, 'response_sha256': receipt.response_sha256,
                        'receipt_sha256': digest(receipt.model_dump(mode='json')), 'retrieved_at': receipt.retrieved_at}
                        for receipt in version.resolution_receipts]}})
        return source

    def publish(self, engine, handle, captured, sources, store, job):
        # Recheck retained members immediately before the engine's own short
        # source-CAS transaction; the engine independently validates its input.
        self.check_input(engine, handle, captured)
        return engine.publish_collection_preparation_job(handle=handle, job_id=job['id'],
            expected_source_revision=captured.expected_source_revision, collection_ref=captured.collection_ref,
            paper_ids=captured.paper_ids, sources=sources, commit_guard=store.publication_guard(job),
            expected_preparation_id=captured.expected_preparation_id)
