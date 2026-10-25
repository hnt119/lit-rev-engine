"""One bounded hybrid coordinator with explicit indexing and no neural imports.

Search requires an already-built exact-snapshot index. Missing or failed optional
models are errors, never lexical success under a hybrid profile identifier.
"""
from collections import Counter
import math
import threading
import time
from src.review.retrieval import _B, _K1, _tokens
from .contracts import digest
from .hybrid_contracts import (HybridCandidate, HybridComponentReceipt, HybridComponentStages,
    HybridIndex, HybridInventory, HybridResult, HybridStage, MEDCPT_PROFILE, QWEN_PROFILE)
from .hybrid_windows import build_inventory, check_cancelled, scoped_sources, source_binding, WINDOWIZER
from .ports import MvpError
from .span_retrieval_contracts import SpanRequirement
from .span_budget import budget_token_count

_NEURAL_GATE = threading.BoundedSemaphore(1)
RRF_C = 60
MAX_RUNTIME_SECONDS = 600


def hybrid_profile(profile_id, manifest=None):
    if profile_id not in {QWEN_PROFILE, MEDCPT_PROFILE}:
        raise MvpError('hybrid_profile', 'Choose an allowlisted immutable retrieval profile.')
    return dict(profile_id=profile_id, profile_revision=1, method='bm25_dense_rrf_cross_encoder',
        method_version='mvp.hybrid-retrieval.v1', experimental=True,
        model_manifest=manifest or {}, parameters=dict(windowizer=WINDOWIZER,
        rrf_c=RRF_C, branch_weights={'bm25': 1, 'dense': 1}, cell_branch_depth=20,
        search_branch_depth=50, cell_rerank_cap=20, search_rerank_cap=50,
        cell_max_output=3, search_max_output=30,
        component_budget='equal-declared-order-allocation-within-total-operation-caps.v1',
        selection='component-reservation-then-best-rerank-rank-and-fusion.v1',
        tie_break='immutable-window-identity', overlap_dedup_threshold=.5,
        max_runtime_seconds=MAX_RUNTIME_SECONDS,
        scope='exact-authorized-source-snapshot-before-all-ranking',
        score_meaning='retrieval_relevance_not_support_probability',
        passage_adaptation=profile_id == MEDCPT_PROFILE))


def profile_binding_hash(profile_id, manifest, runtime):
    """Bind immutable models, pipeline policy and full stable runtime semantics.

    Dynamic counters/timing never enter a cache key. Native adapters expose the
    same stable metadata without loading a tokenizer/model for status queries.
    """
    stable = {k: v for k, v in runtime.items() if k not in {'executed_items', 'timings', 'token_usage'}}
    return digest({'models': manifest, 'profile': hybrid_profile(profile_id), 'runtime': stable})


def adapter_profile_hash(adapter):
    return profile_binding_hash(adapter.profile_id, adapter.manifest, adapter.runtime_metadata())


def _vectors(value, count, dimension, stage):
    if (not isinstance(value, (list, tuple)) or len(value) != count or
        any(not isinstance(row, (list, tuple)) or len(row) != dimension or
            any(isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x) for x in row)
            for row in value)):
        raise MvpError('hybrid_vector_contract', 'The '+stage+' vectors failed count, dimension or finite-value validation.')
    return [[float(x) for x in row] for row in value]


def _quotas(total, n):
    return [total//n + (i < total % n) for i in range(n)]


def _overlap(a, b):
    x, y = a.reference, b.reference
    if (x.source_id, x.block_id) != (y.source_id, y.block_id):
        return False
    return max(0, min(x.end, y.end)-max(x.start, y.start))/min(x.end-x.start, y.end-y.start) >= .5


def _lexical(windows, query):
    frequencies = [Counter(_tokens(w.reference.quote)) for w in windows]
    query_tokens = set(_tokens(query))
    df = Counter(token for row in frequencies for token in query_tokens.intersection(row))
    lengths = [sum(row.values()) for row in frequencies]
    average = sum(lengths)/len(lengths) if lengths else 0
    scores = {}
    for i, row in enumerate(frequencies):
        score = 0.0
        for token in sorted(query_tokens.intersection(row)):
            freq = row[token]
            idf = math.log(1+(len(windows)-df[token]+.5)/(df[token]+.5))
            score += idf * freq * (_K1+1)/(freq+_K1*(1-_B+_B*lengths[i]/average))
        if score > 0:
            scores[i] = score
    return scores


class HybridRetrieval:
    def __init__(self, adapter, *, monotonic=time.monotonic):
        self.adapter, self.monotonic = adapter, monotonic
        hybrid_profile(adapter.profile_id)

    def build_inventory(self, sources, **kwargs):
        kwargs.setdefault('fits_document', self.adapter.fits_document)
        return build_inventory(sources, **kwargs)

    def _guard(self, started, cancelled):
        check_cancelled(cancelled)
        if self.monotonic()-started > MAX_RUNTIME_SECONDS:
            raise MvpError('hybrid_runtime_budget', 'The hybrid runtime budget was exhausted. No completed profile or lexical fallback was published.', True)

    def build_index(self, inventory, *, cancelled=None):
        inventory = HybridInventory.model_validate(inventory.model_dump(mode='json') if isinstance(inventory, HybridInventory) else inventory)
        if not _NEURAL_GATE.acquire(blocking=False):
            raise MvpError('hybrid_busy', 'Another local neural operation is active. Retry this explicit operation.', True)
        try:
            started = self.monotonic()
            if hasattr(self.adapter, 'set_cancelled'):
                self.adapter.set_cancelled(lambda: self._guard(started, cancelled))
            self._guard(started, cancelled)
            docs = [(w.title, w.reference.quote) for w in inventory.windows]
            if any(not self.adapter.fits_document(*doc) for doc in docs):
                raise MvpError('hybrid_document_budget', 'An exact inventory document exceeds this profile template; rebuild explicitly using the declared common token policy.')
            dimension = self.adapter.dimension
            vectors = _vectors(self.adapter.encode_documents(docs) if docs else [], len(docs), dimension, 'document')
            self._guard(started, cancelled)
            manifest_hash = adapter_profile_hash(self.adapter)
            key = digest([self.adapter.profile_id, manifest_hash, inventory.manifest_sha256, dimension, 'float32'])
            return HybridIndex(profile_id=self.adapter.profile_id, profile_manifest_sha256=manifest_hash,
                window_manifest_sha256=inventory.manifest_sha256, dimension=dimension,
                vectors=vectors, vectors_sha256=digest(vectors), elapsed_seconds=self.monotonic()-started,
                runtime=self.adapter.runtime_metadata(), index_key=key)
        finally:
            if hasattr(self.adapter, 'set_cancelled'):
                self.adapter.set_cancelled(None)
            _NEURAL_GATE.release()

    def search(self, question, sources, run_id, top_k=5, *, authorized_sources,
               titles=None, requirements=None, operation='search', index,
               inventory=None, cancelled=None):
        if (not isinstance(question, str) or not question.strip() or len(question) > 10000 or
            not isinstance(run_id, str) or not 1 <= len(run_id) <= 200 or
            operation not in {'cell', 'search'} or type(top_k) is not int or
            not (1 <= top_k <= 3 if operation == 'cell' else 5 <= top_k <= 30)):
            raise MvpError('hybrid_input', 'Use a bounded explicit query and 1–3 cell candidates or 5–30 search candidates.')
        if requirements is None:
            if len(question) > 2000:
                raise MvpError('hybrid_query_budget', 'The complete query exceeds this profile input contract. Explicitly shorten it or supply approved bounded component queries; no truncation ran.')
            required = [SpanRequirement(id='field', label='Field question', query=question)]
        else:
            try:
                required = [v if isinstance(v, SpanRequirement) else SpanRequirement.model_validate(v) for v in requirements]
            except (TypeError, ValueError):
                raise MvpError('hybrid_components', 'Use one to three explicitly declared component queries.') from None
            if not 1 <= len(required) <= 3 or len({v.id for v in required}) != len(required):
                raise MvpError('hybrid_components', 'Use one to three unique explicitly declared component queries.')
        # Validate every selected query before any model execution. The original
        # broad question is retained; only approved components may replace it.
        for component in required:
            self.adapter.validate_query(component.query)
        selected = scoped_sources(sources, authorized_sources)
        if inventory is None:
            inventory = self.build_inventory(selected, authorized_sources=authorized_sources,
                titles=titles, cancelled=cancelled)
        inventory = HybridInventory.model_validate(inventory.model_dump(mode='json') if isinstance(inventory, HybridInventory) else inventory)
        index = HybridIndex.model_validate(index.model_dump(mode='json') if isinstance(index, HybridIndex) else index)
        manifest = [source_binding(v) for v in selected]
        if (inventory.source_manifest != manifest or inventory.source_snapshot_sha256 != digest([v.model_dump(mode='json') for v in selected])):
            raise MvpError('hybrid_index_stale', 'The index inventory is bound to different authorized sources. Explicitly index this exact snapshot.')
        source_map = {v.id: v for v in selected}
        for window in inventory.windows:
            source = source_map.get(window.reference.source_id)
            block = next((b for b in source.blocks if b.id == window.reference.block_id), None) if source else None
            ref = window.reference
            if (block is None or ref.paper_id != source.paper_id or ref.source_version != source.version or
                ref.source_sha256 != source.source_sha256 or ref.blocks_sha256 != source.blocks_sha256 or
                block.text[ref.start:ref.end] != ref.quote or window.total_block_characters != len(block.text) or
                (titles is not None and window.title != titles.get(ref.paper_id, '')) or
                not self.adapter.fits_document(window.title, ref.quote)):
                raise MvpError('hybrid_anchor_stale', 'An indexed window does not match the exact retained evidence and full input budget.')
        if (index.profile_id != self.adapter.profile_id or index.profile_manifest_sha256 != adapter_profile_hash(self.adapter) or
            index.window_manifest_sha256 != inventory.manifest_sha256 or index.dimension != self.adapter.dimension or
            len(index.vectors) != len(inventory.windows)):
            raise MvpError('hybrid_index_stale', 'This exact model/profile/source index is missing or stale; no replacement or lexical fallback was attempted.')
        _vectors(index.vectors, len(inventory.windows), self.adapter.dimension, 'index')
        if not _NEURAL_GATE.acquire(blocking=False):
            raise MvpError('hybrid_busy', 'Another local neural operation is active. Retry this explicit operation.', True)
        try:
            return self._search(question, required, run_id, top_k, operation, inventory, index, cancelled)
        finally:
            if hasattr(self.adapter, 'set_cancelled'):
                self.adapter.set_cancelled(None)
            _NEURAL_GATE.release()

    def _search(self, question, required, run_id, top_k, operation, inventory, index, cancelled):
        started = self.monotonic()
        if hasattr(self.adapter, 'set_cancelled'):
            self.adapter.set_cancelled(lambda: self._guard(started, cancelled))
        self._guard(started, cancelled)
        windows = inventory.windows
        branch_depth = 20 if operation == 'cell' else 50
        rerank_cap = branch_depth
        quotas = _quotas(branch_depth, len(required))
        timing = {}
        t = self.monotonic()
        vectors = _vectors(self.adapter.encode_queries([v.query for v in required]), len(required), self.adapter.dimension, 'query')
        timing['query_encoding_seconds'] = self.monotonic()-t
        self._guard(started, cancelled)
        stages, component_counts = {}, []
        for component, qvec, quota in zip(required, vectors, quotas):
            self._guard(started, cancelled)
            t = self.monotonic()
            lexical = _lexical(windows, component.query)
            lex_order = sorted(lexical, key=lambda i: (-lexical[i], windows[i].id))[:quota]
            dense = {i: sum(a*b for a, b in zip(qvec, row)) for i, row in enumerate(index.vectors)}
            if any(not math.isfinite(v) for v in dense.values()):
                raise MvpError('hybrid_dense_score', 'Dense scoring produced non-finite relevance scores.')
            dense_order = sorted(dense, key=lambda i: (-dense[i], windows[i].id))[:quota]
            lex_rank, dense_rank = ({i: r for r, i in enumerate(values, 1)} for values in (lex_order, dense_order))
            union = set(lex_order)|set(dense_order)
            fused = {i: sum(1/(RRF_C+ranks[i]) for ranks in (lex_rank, dense_rank) if i in ranks) for i in union}
            fusion_order = sorted(union, key=lambda i: (-fused[i], windows[i].id))
            fusion_rank = {i: r for r, i in enumerate(fusion_order, 1)}
            retained = fusion_order[:quota]
            timing['candidate_ranking_seconds'] = timing.get('candidate_ranking_seconds', 0)+self.monotonic()-t
            t = self.monotonic()
            scores = self.adapter.rerank(component.query, [(windows[i].title, windows[i].reference.quote) for i in retained]) if retained else []
            if (len(scores) != len(retained) or any(isinstance(s, bool) or not isinstance(s, (int, float)) or not math.isfinite(s) for s in scores)):
                raise MvpError('hybrid_rerank_contract', 'The reranker did not return one finite raw relevance score for every bounded pair. No partial success was published.')
            timing['reranking_seconds'] = timing.get('reranking_seconds', 0)+self.monotonic()-t
            self._guard(started, cancelled)
            reranked = sorted(zip(retained, scores), key=lambda pair: (-pair[1], windows[pair[0]].id))
            for rank, (i, score) in enumerate(reranked, 1):
                stage = HybridComponentStages(component_id=component.id,
                    bm25=HybridStage(rank=lex_rank[i], score=lexical[i]) if i in lex_rank else HybridStage(),
                    dense=HybridStage(rank=dense_rank[i], score=dense[i]) if i in dense_rank else HybridStage(),
                    fusion=HybridStage(rank=fusion_rank[i], score=fused[i]),
                    rerank=HybridStage(rank=rank, score=score))
                stages.setdefault(i, []).append(stage)
            component_counts.append(dict(requirement=component, lexical_matches=len(lexical),
                lexical_candidates=len(lex_order), dense_candidates=len(dense_order),
                fusion_candidates=len(fusion_order), reranked_candidates=len(reranked)))
        # Reserve one distinct candidate per declared component. The remaining
        # order uses within-component rerank ranks, never a universal cutoff or
        # a claim that logits for different component queries are calibrated.
        selected = []
        def add(i):
            if (len(selected) < top_k and i not in selected and not any(_overlap(windows[i], windows[j]) for j in selected)
                and (operation != 'cell' or
                     (sum(len(windows[j].reference.quote) for j in selected)+len(windows[i].reference.quote) <= 3600 and
                      sum(budget_token_count(windows[j].reference.quote) for j in selected)+budget_token_count(windows[i].reference.quote) <= 1200))):
                selected.append(i)
        for component in required:
            choices = [(stage.rerank.rank, windows[i].id, i) for i, values in stages.items() for stage in values if stage.component_id == component.id]
            for _, _, i in sorted(choices):
                before = len(selected); add(i)
                if len(selected) != before: break
        order = sorted(stages, key=lambda i: (min(s.rerank.rank for s in stages[i]),
            -sum(s.fusion.score for s in stages[i]), windows[i].id))
        for i in order: add(i)
        candidates = []
        for rank, i in enumerate(selected, 1):
            window, values = windows[i], stages[i]
            branches = [name for name in ('bm25', 'dense') if any(getattr(s, name).rank is not None for s in values)]
            candidates.append(HybridCandidate(candidate_id='hybrid-candidate:'+digest([run_id, window.id]),
                rank=rank, reference=window.reference, source_type=window.source_type,
                total_block_characters=window.total_block_characters,
                omitted_before=window.reference.start, omitted_after=window.total_block_characters-window.reference.end,
                component_ids=[s.component_id for s in values], branch_membership=branches, stages=values,
                score=max(s.rerank.score for s in values)))
        receipts = [HybridComponentReceipt(**v, selected_candidates=sum(v['requirement'].id in c.component_ids for c in candidates)) for v in component_counts]
        if sum(v.reranked_candidates for v in receipts) > rerank_cap:
            raise MvpError('hybrid_pair_budget', 'The total operation reranking budget was exceeded.')
        timing['total_seconds'] = self.monotonic()-started
        self._guard(started, cancelled)
        return HybridResult(run_id=run_id, profile_id=self.adapter.profile_id,
            original_query=question, requirements=required, candidates=candidates,
            requested_count=top_k, returned_count=len(candidates), operation=operation,
            source_manifest=inventory.source_manifest, source_snapshot_sha256=inventory.source_snapshot_sha256,
            window_manifest_sha256=inventory.manifest_sha256, coverage=inventory.coverage,
            model_manifest=self.adapter.manifest, profile_parameters=hybrid_profile(self.adapter.profile_id)['parameters'],
            component_receipts=receipts, index_key=index.index_key, timings=timing,
            runtime={**self.adapter.runtime_metadata(), 'dimension': self.adapter.dimension,
                'dense_metric': self.adapter.dense_metric, 'index_runtime': index.runtime})
