"""Native adapter parity/boundary checks; mocks are not retrieval-quality evidence."""
from contextlib import contextmanager
from copy import deepcopy
import importlib
import json
import re
import subprocess
import sys
from types import SimpleNamespace

import pytest
from src.mvp.adapters import neural_retrieval as native
from src.mvp.ports import MvpError


class Tokenizer:
    """Deterministic whitespace tokenizer for policy tests, never a model substitute."""
    def __init__(self):
        self.calls = []

    def __call__(self, first, second=None, **kwargs):
        self.calls.append((deepcopy(first), deepcopy(second), dict(kwargs)))
        assert kwargs.get('truncation') is False
        def encode(text):
            return list(range(1, len(re.findall(r'\S+', text)) + 1))
        def ids(a, b=None):
            values = encode(a) + (encode(b) if b is not None else [])
            special = kwargs.get('add_special_tokens', True)
            return ([100] + values + [101] + ([102] if b is not None else [])) if special else values
        if isinstance(first, str):
            return {'input_ids': ids(first, second)}
        torch = pytest.importorskip('torch')
        rows = [ids(a, second[i] if second is not None else None) for i, a in enumerate(first)]
        size = max(map(len, rows))
        return {'input_ids': torch.tensor([row + [0] * (size-len(row)) for row in rows]),
            'attention_mask': torch.tensor([[1]*len(row)+[0]*(size-len(row)) for row in rows])}

    def num_special_tokens_to_add(self, pair=False):
        return 3 if pair else 2

    def convert_tokens_to_ids(self, token):
        return {'no': 0, 'yes': 1}[token]

    def pad(self, data, **kwargs):
        torch = pytest.importorskip('torch')
        rows=data['input_ids']; size=max(map(len,rows))
        return {'input_ids': torch.tensor([[0]*(size-len(row))+row for row in rows]),
            'attention_mask': torch.tensor([[0]*(size-len(row))+[1]*len(row) for row in rows])}


def adapter(profile=native.MEDCPT_PROFILE):
    value = native.NeuralAdapter.__new__(native.NeuralAdapter)
    value.profile_id, value.device, value.manifest = profile, 'cpu', {'pinned': 'fixture-not-weights'}
    value.dimension = 768 if profile == native.MEDCPT_PROFILE else 1024
    value.dense_metric = 'inner_product' if profile == native.MEDCPT_PROFILE else 'normalized_inner_product'
    value._tokenizers = {role: Tokenizer() for role in ('query','document','reranker')}
    value._executed = {'query_encoder': 0, 'document_encoder': 0, 'reranker': 0}
    value._timing = {'model_load_seconds': 0., 'query_encoder_seconds': 0., 'document_encoder_seconds': 0., 'reranker_seconds': 0.}
    value._token_counts = {'query_tokens': 0, 'document_tokens': 0, 'reranker_pair_tokens': 0}
    return value


def test_module_import_does_not_need_torch_or_transformers():
    script = """import builtins
original=builtins.__import__
def guarded(name,*args,**kwargs):
 if name.split('.')[0] in {'torch','transformers','sentence_transformers'}: raise AssertionError(name)
 return original(name,*args,**kwargs)
builtins.__import__=guarded
import src.mvp.adapters.neural_retrieval
"""
    subprocess.run([sys.executable, '-c', script], check=True, capture_output=True)


def test_native_qwen_instruction_and_document_templates():
    assert native.qwen_query('not absent') == 'Instruct: '+native.RETRIEVAL_INSTRUCTION+'\nQuery:not absent'
    assert native.qwen_document('Title qualifier', 'not absent') == 'Title qualifier\nnot absent'
    assert native.qwen_instruction('query','document') == '<Instruct>: '+native.RETRIEVAL_INSTRUCTION+'\n<Query>: query\n<Document>: document'
    assert native.QWEN_SUFFIX.endswith('<think>\n\n</think>\n\n')
    assert '"yes" or "no"' in native.QWEN_PREFIX


def test_medcpt_query_policy_counts_special_tokens_without_truncation():
    value=adapter()
    assert value.validate_query('word '*62)==64
    with pytest.raises(MvpError, match='64 query tokens') as error:
        value.validate_query('word '*63)
    assert error.value.code=='retrieval_query_budget'
    assert all(call[2]['truncation'] is False for call in value._tokenizers['query'].calls)


def test_medcpt_pair_window_reserves_all_query_tokens_and_retains_title():
    value=adapter()
    assert value.fits_document('title', 'passage '*443)
    assert not value.fits_document('title', 'passage '*445)
    assert not value.fits_document('constraint '*450, 'short evidence')
    with pytest.raises(MvpError) as error:
        value.encode_documents([('constraint '*450, 'not significant')])
    assert error.value.code=='retrieval_document_budget'
    article=value._tokenizers['document'].calls[0]
    assert article[0]=='title' and article[1]=='passage '*443


def test_qwen_long_question_rejected_before_any_forward():
    value=adapter(native.QWEN_PROFILE)
    with pytest.raises(MvpError) as error:
        value.encode_queries(['word '*260])
    assert error.value.code=='retrieval_query_budget'
    assert not any(value._executed.values())


@pytest.mark.parametrize('mask,expected', [
    ([[0,1,1],[1,1,1]], [2,5]), ([[1,1,0],[1,0,0]], [1,3])])
def test_qwen_last_valid_token_pool_matches_native_padding_rules(mask, expected):
    torch=pytest.importorskip('torch')
    hidden=torch.arange(6).reshape(2,3,1)
    assert native.last_token_pool(hidden,torch.tensor(mask)).flatten().tolist()==expected


def bind_forward(value, monkeypatch, *, reranker=False):
    torch=pytest.importorskip('torch'); value._torch=torch
    roles=[]
    class Model:
        def __call__(self, **batch):
            roles.append(batch)
            count, tokens=batch['input_ids'].shape
            if reranker:
                if value.profile_id==native.QWEN_PROFILE:
                    logits=torch.zeros((count,tokens,4)); logits[:,-1,0]=2; logits[:,-1,1]=3; logits[:,-1,3]=999
                    return SimpleNamespace(logits=logits)
                return SimpleNamespace(logits=torch.full((count,1),-7.5))
            # CLS is explicitly unnormalized for MedCPT; later tokens differ.
            hidden=torch.full((count,tokens,value.dimension),3.)
            hidden[:,0,:]=2.
            return SimpleNamespace(last_hidden_state=hidden)
    @contextmanager
    def model(role):
        roles.append(role); yield Model()
    monkeypatch.setattr(value,'_model',model)
    return roles


def test_medcpt_roles_cls_inner_product_and_document_pair(monkeypatch):
    value=adapter();roles=bind_forward(value,monkeypatch)
    query=value.encode_queries(['question'])[0]
    docs=value.encode_documents([('retained title','exact passage')])[0]
    assert query==docs==[2.]*768
    assert roles[0]=='query' and roles[2]=='document'
    assert value.dense_metric=='inner_product'
    assert value._tokenizers['document'].calls[-1][0]==['retained title']
    assert value._tokenizers['document'].calls[-1][1]==['exact passage']
    assert value._executed=={'query_encoder':1,'document_encoder':1,'reranker':0}


def test_qwen_normalizes_full1024_without_instructing_documents(monkeypatch):
    value=adapter(native.QWEN_PROFILE);bind_forward(value,monkeypatch)
    vectors=value.encode_documents([('title','exact passage')])
    assert len(vectors[0])==1024
    assert sum(x*x for x in vectors[0])==pytest.approx(1.)
    assert value._tokenizers['document'].calls[-1][0]==['title\nexact passage']


def test_qwen_yes_no_softmax_excludes_unrelated_vocabulary_logits(monkeypatch):
    value=adapter(native.QWEN_PROFILE);bind_forward(value,monkeypatch,reranker=True)
    scores=value.rerank('question',[('title','exact passage')])
    assert scores==pytest.approx([1/(1+__import__('math').exp(-1))])
    assert value._executed['reranker']==1


def test_medcpt_negative_raw_logit_preserved_and_query_document_order(monkeypatch):
    value=adapter();bind_forward(value,monkeypatch,reranker=True)
    assert value.rerank('question',[('title','not significant')])==[-7.5]
    assert value._tokenizers['reranker'].calls[-1][0]==['question']
    assert value._tokenizers['reranker'].calls[-1][1]==['title. not significant']


def test_unknown_profile_and_device_fail_before_optional_runtime(monkeypatch):
    monkeypatch.setattr(native,'_runtime',lambda: pytest.fail('invalid input imported model stack'))
    with pytest.raises(MvpError): native.NeuralAdapter('unknown',{}, {})
    with pytest.raises(MvpError): native.NeuralAdapter(native.QWEN_PROFILE,{}, {},device='auto')


def test_stable_signature_and_missing_dependencies_do_not_construct_models(monkeypatch):
    def absent(name):raise native.PackageNotFoundError(name)
    monkeypatch.setattr(native,'version',absent)
    metadata=native.native_runtime_signature(native.QWEN_PROFILE,'cpu')
    assert metadata['torch_version'] is None and metadata['transformers_version'] is None
    assert metadata['causal_logits']=='last-token-only' and metadata['kv_cache'] is False
    assert metadata['query_instruction']==native.RETRIEVAL_INSTRUCTION
    assert not {'executed_items','timings','token_usage'} & metadata.keys()


def test_cancellation_before_forward_never_publishes_partial_vectors(monkeypatch):
    value=adapter();bind_forward(value,monkeypatch)
    value.set_cancelled(lambda: True)
    with pytest.raises(MvpError) as error:value.encode_queries(['question'])
    assert error.value.code=='hybrid_cancelled'
    assert value._executed['query_encoder']==0
    value.set_cancelled(None)
    assert len(value.encode_queries(['question']))==1


def test_cancellation_after_first_batch_preserves_no_success_return(monkeypatch):
    value=adapter();roles=bind_forward(value,monkeypatch)
    value.set_cancelled(lambda: any(isinstance(item,dict) for item in roles))
    with pytest.raises(MvpError) as error:value.encode_documents([('title','first'),('title','second'),('title','third')])
    assert error.value.code=='hybrid_cancelled'
    assert value._executed['document_encoder']==0


def test_medcpt_cross_uses_restricted_local_tensor_loader(tmp_path):
    value=adapter();calls=[]
    class Model:
        def load_state_dict(self,state,strict):calls.append(('state',state,strict))
        def to(self,**kwargs):calls.append(('to',kwargs));return self
        def eval(self):return self
    model=Model()
    def load(path,**kwargs):calls.append(('load',path,kwargs));return {'weight':'tensor'}
    value._torch=SimpleNamespace(__version__='2.12.0',float32='fp32',is_tensor=lambda x:x=='tensor',load=load)
    value._transformers=SimpleNamespace(AutoConfig=SimpleNamespace(from_pretrained=lambda *a,**kw:calls.append(('config',a,kw)) or 'config'),
        AutoModelForSequenceClassification=SimpleNamespace(from_config=lambda *a,**kw:calls.append(('model',a,kw)) or model))
    value._dirs={'reranker':tmp_path}
    with value._model('reranker') as observed:assert observed is model
    assert next(c for c in calls if c[0]=='load')[2]=={'weights_only':True,'map_location':'cpu'}
    assert next(c for c in calls if c[0]=='config')[2]=={'local_files_only':True,'trust_remote_code':False}
    assert ('state',{'weight':'tensor'},True) in calls


def test_qwen_model_loading_explicitly_uses_local_safetensors_fp32(tmp_path):
    value=adapter(native.QWEN_PROFILE);calls=[]
    class Model:
        def to(self,**kwargs):calls.append(('to',kwargs));return self
        def eval(self):return self
    def load(*args,**kwargs):calls.append(('load',args,kwargs));return Model()
    value._torch=SimpleNamespace(float32='fp32')
    value._transformers=SimpleNamespace(AutoModel=SimpleNamespace(from_pretrained=load),AutoModelForCausalLM=SimpleNamespace(from_pretrained=load))
    value._dirs={'query':tmp_path}
    with value._model('query'):pass
    assert calls[0][2]=={'local_files_only':True,'trust_remote_code':False,'use_safetensors':True,'dtype':'fp32','attn_implementation':'eager'}
