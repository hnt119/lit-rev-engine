"""Offline integration/safety tests. Fake scores do not establish model quality."""
from copy import deepcopy
import math
import pytest
from pydantic import ValidationError
from src.mvp.contracts import Block, PreparedSource, digest
from src.mvp.hybrid_contracts import HybridIndex, HybridInventory, HybridStage, QWEN_PROFILE
from src.mvp.hybrid_retrieval import HybridRetrieval
from src.mvp.hybrid_windows import build_inventory, source_binding
from src.mvp.ports import MvpError
from src.mvp.span_budget import budget_token_count


def source(*texts, paper='paper', identifier='source'):
    blocks = [Block(id=f'b{i}', ordinal=i+1, text=text, locator={'type':'text','index':i}) for i,text in enumerate(texts)]
    return PreparedSource(id=identifier, paper_id=paper, status='abstract_only', source_type='abstract',
        provider='synthetic-test', source_url='', source_sha256=digest(texts),
        blocks_sha256=digest([b.model_dump(mode='json') for b in blocks]), parser_id='synthetic.v1', blocks=blocks)


class Adapter:
    profile_id = QWEN_PROFILE
    manifest = {'fixture': 'NOT_A_MODEL_QUALITY_RESULT', 'revision': 'fixed'}
    dimension = 2
    dense_metric = 'inner_product'
    def __init__(self):
        self.encoded = []; self.reranked = []; self.query_calls=0
    def validate_query(self, query):
        if len(query) > 64:
            raise MvpError('hybrid_query_budget', 'Explicit short query required; no truncation.')
    def fits_document(self, title, text): return len(title)+len(text) <= 80
    def encode_documents(self, docs):
        self.encoded.extend(docs)
        return [[-float(i+1), 0.] for i,_ in enumerate(docs)]
    def encode_queries(self, queries):
        self.query_calls += 1
        return [[1.,0.] for _ in queries]
    def rerank(self, query, docs):
        self.reranked.extend(docs)
        return [-float(i+2) for i,_ in enumerate(docs)]
    def runtime_metadata(self): return {'device':'fake-cpu','dtype':'float32','model_execution':False}


def setup(retained=None, adapter=None, **kwargs):
    retained = retained or source('No lexical overlap occurs in this source.', 'Separate retained findings.')
    adapter = adapter or Adapter()
    runner = HybridRetrieval(adapter)
    auth = [source_binding(retained)]
    inventory = runner.build_inventory([retained], authorized_sources=auth, **kwargs)
    index = runner.build_index(inventory)
    return retained, adapter, runner, auth, inventory, index


def test_semantic_only_negative_scores_are_truthful_and_search_does_not_reencode_documents():
    retained, adapter, runner, auth, inventory, index = setup()
    before = deepcopy(adapter.encoded)
    result = runner.search('unmatched query', [retained], 'run', authorized_sources=auth, inventory=inventory, index=index)
    assert adapter.encoded == before
    assert result.schema_version == 'mvp.hybrid-retrieval.v1'
    assert result.candidates and result.candidates[0].score < 0
    for candidate in result.candidates:
        assert candidate.branch_membership == ['dense']
        assert candidate.stages[0].bm25.score is candidate.stages[0].bm25.rank is None
        assert candidate.stages[0].dense.score < 0
        assert candidate.stages[0].rerank.score < 0
    assert result.component_receipts[0].lexical_matches == 0


def test_source_scope_is_applied_before_windowization_and_model_encoding():
    allowed = source('Authorized exact text')
    wrong = source('SECRET UNAUTHORIZED TEXT', paper='other', identifier='other-source')
    # The unauthorized source deliberately has an invalid integrity hash. It is
    # filtered before its text is inspected by tokenizers or model methods.
    wrong = wrong.model_copy(update={'blocks_sha256':'invalid'})
    adapter = Adapter(); runner=HybridRetrieval(adapter)
    inv = runner.build_inventory([wrong, allowed], authorized_sources=[source_binding(allowed)])
    idx=runner.build_index(inv)
    result=runner.search('text', [wrong, allowed], 'r', authorized_sources=[source_binding(allowed)], inventory=inv, index=idx)
    assert all(c.reference.paper_id == allowed.paper_id for c in result.candidates)
    assert all('SECRET' not in text for _,text in adapter.encoded+adapter.reranked)


def test_unicode_exact_windows_cover_after_long_introduction_without_mutation():
    text = ('Introduction without findings. '*90)+'Woman 😀 e\u0301 cohort did not improve 42%.'
    retained=source(text); before=retained.model_dump(mode='json')
    inv=build_inventory([retained], authorized_sources=[source_binding(retained)], fits_document=lambda title,text: len(text)<=73)
    covered=set()
    for window in inv.windows:
        ref=window.reference
        assert ref.quote == text[ref.start:ref.end]
        assert ref.end-ref.start == len(ref.quote)
        covered.update(range(ref.start,ref.end))
    assert covered == set(range(len(text)))
    assert any('42%' in w.reference.quote for w in inv.windows)
    assert inv.coverage.complete and inv.coverage.unindexed_characters == 0
    assert retained.model_dump(mode='json') == before


def test_complete_title_is_never_silently_shortened():
    retained=source('passage')
    with pytest.raises(MvpError, match='complete title'):
        build_inventory([retained], authorized_sources=[source_binding(retained)], titles={'paper':'T'*100}, fits_document=Adapter().fits_document)


def test_oversize_query_rejected_before_any_encoder_or_reranker_call():
    retained, adapter, runner, auth, inventory, index=setup()
    with pytest.raises(MvpError, match='Explicit short query'):
        runner.search('x'*65,[retained],'r',authorized_sources=auth,inventory=inventory,index=index)
    assert adapter.query_calls == 0 and adapter.reranked == []


def test_explicit_components_preserve_total_operation_pair_caps():
    retained=source(*[f'unique passage {i}' for i in range(100)])
    retained,adapter,runner,auth,inventory,index=setup(retained)
    components=[{'id':str(i),'label':str(i),'query':f'query {i}'} for i in range(3)]
    result=runner.search('broad question',[retained],'r',3,authorized_sources=auth,requirements=components,operation='cell',inventory=inventory,index=index)
    assert len(adapter.reranked) == 20
    assert sum(c.lexical_candidates for c in result.component_receipts)<=20
    assert sum(c.dense_candidates for c in result.component_receipts)==20
    assert {component for c in result.candidates for component in c.component_ids} == {'0','1','2'}
    assert len(result.candidates)<=3


def test_bound_source_revision_cannot_be_replaced_by_current_preparation():
    retained,adapter,runner,auth,inventory,index=setup()
    altered=retained.model_copy(update={'version':'2'})
    with pytest.raises(MvpError, match='differs from the authorized'):
        runner.search('query',[altered],'r',authorized_sources=auth,inventory=inventory,index=index)
    assert adapter.query_calls==0


def test_index_profile_binding_rejects_manifest_change():
    retained,adapter,runner,auth,inventory,index=setup()
    adapter.manifest={'fixture':'new-revision'}
    with pytest.raises(MvpError, match='missing or stale'):
        runner.search('query',[retained],'r',authorized_sources=auth,inventory=inventory,index=index)
    assert adapter.query_calls==0


def test_cache_corruption_and_mutable_list_tampering_fail_validation():
    retained,adapter,runner,auth,inventory,index=setup()
    raw=index.model_dump(mode='json');raw['vectors'][0][0]+=1
    with pytest.raises(ValidationError, match='content hash'):
        HybridIndex.model_validate(raw)
    index.vectors[0][0]+=1
    with pytest.raises(ValidationError, match='content hash'):
        runner.search('query',[retained],'r',authorized_sources=auth,inventory=inventory,index=index)


def test_cancelled_index_never_publishes_partial_model_output():
    retained=source('Passage')
    adapter=Adapter(); runner=HybridRetrieval(adapter)
    inv=runner.build_inventory([retained],authorized_sources=[source_binding(retained)])
    with pytest.raises(MvpError, match='cancelled'):
        runner.build_index(inv,cancelled=lambda:True)
    assert adapter.encoded==[]


def test_reranker_failure_is_not_relabelled_as_lexical_success():
    retained,adapter,runner,auth,inventory,index=setup()
    def fail(query,docs): raise MvpError('model_failed','Explicit reranker failed')
    adapter.rerank=fail
    with pytest.raises(MvpError,match='reranker failed'):
        runner.search('text',[retained],'r',authorized_sources=auth,inventory=inventory,index=index)


def test_nonfinite_rerank_output_rejected():
    retained,adapter,runner,auth,inventory,index=setup()
    adapter.rerank=lambda q,docs:[math.nan for _ in docs]
    with pytest.raises(MvpError,match='finite raw relevance'):
        runner.search('text',[retained],'r',authorized_sources=auth,inventory=inventory,index=index)


def test_source_integrity_is_checked_before_model_input():
    retained=source('retained')
    altered=retained.model_copy(update={'blocks':[retained.blocks[0].model_copy(update={'text':'replaced'})]})
    with pytest.raises(MvpError,match='Canonical block bytes'):
        build_inventory([altered],authorized_sources=[source_binding(altered)])


def test_common_proxy_budget_keeps_existing_proposal_bounds():
    retained=source('! '*2000)
    inv=build_inventory([retained],authorized_sources=[source_binding(retained)])
    assert all(budget_token_count(w.reference.quote)<=400 for w in inv.windows)
    assert inv.coverage.complete


def test_stage_nulls_and_inventory_hash_are_strict():
    with pytest.raises(ValidationError): HybridStage(rank=1,score=None)
    retained,_,_,_,inventory,_=setup()
    raw=inventory.model_dump(mode='json');raw['windows'][0]['reference']['quote']='changed'
    with pytest.raises(ValidationError,match='hash'):
        HybridInventory.model_validate(raw)


def test_index_runtime_precision_and_query_template_bindings_are_not_interchangeable():
    retained,adapter,runner,auth,inventory,index=setup()
    original=adapter.runtime_metadata
    adapter.runtime_metadata=lambda:{**original(), 'query_template_version':'new-template'}
    with pytest.raises(MvpError,match='missing or stale'):
        runner.search('query',[retained],'r',authorized_sources=auth,inventory=inventory,index=index)
    assert adapter.query_calls==0


def test_title_metadata_change_invalidates_document_representation():
    retained,adapter,runner,auth,inventory,index=setup(titles={'paper':'Original title'})
    with pytest.raises(MvpError,match='exact retained evidence'):
        runner.search('query',[retained],'r',authorized_sources=auth,titles={'paper':'Changed title'},inventory=inventory,index=index)
    assert adapter.query_calls==0


def test_broad_question_without_explicit_components_returns_clear_unsupported_input():
    retained,adapter,runner,auth,inventory,index=setup()
    with pytest.raises(MvpError,match='Explicitly shorten'):
        runner.search('long query '*200,[retained],'r',authorized_sources=auth,inventory=inventory,index=index)
    assert adapter.query_calls==0


def test_leading_whitespace_does_not_masquerade_as_oversized_title():
    for text in (' '+('漢'*1000), (' '*1200)+('漢'*1000)):
        retained=source(text)
        def tokenizer_fit(title, passage):
            return bool(passage.strip()) and len(title)+len(passage)<=90
        inventory=build_inventory([retained],authorized_sources=[source_binding(retained)],
            titles={'paper':'Complete title'},fits_document=tokenizer_fit)
        assert inventory.coverage.complete and inventory.coverage.unindexed_characters==0
        assert all(tokenizer_fit(w.title,w.reference.quote) for w in inventory.windows)
        assert all(w.reference.quote==text[w.reference.start:w.reference.end] for w in inventory.windows)
        assert any('漢' in w.reference.quote for w in inventory.windows)
