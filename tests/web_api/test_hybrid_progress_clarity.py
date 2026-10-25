"""Operational progress only: synthetic vectors, no model/provider execution."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import json
import pytest
from test_hybrid_retrieval_independent import flow, post
from src.mvp.hybrid_contracts import QWEN_PROFILE
from src.mvp.ports import MvpError
from src.mvp import retrieval_packs
from src.mvp.adapters import neural_retrieval as native


def test_actual_job_batches_are_visible_while_compute_runs_and_receipts_stay_separate(flow):
    c=flow;adapter=c.packs.adapters[QWEN_PROFILE];started,release=Event(),Event();callback={'value':None}
    adapter.set_progress=lambda value:callback.update(value=value)
    original=adapter.encode_documents
    def encode(docs):
        callback['value'](phase='embedding',component='document',completed_batches=1,total_batches=2,processed_items=2,total_items=len(docs),quotation='PRIVATE MUST NEVER BE STORED',path='/private/example')
        started.set();assert release.wait(5)
        return original(docs)
    adapter.encode_documents=encode
    with ThreadPoolExecutor() as pool:
        pending=pool.submit(c.client.post,c.base+'/hybrid-index',json=c.payload)
        try:
            assert started.wait(3)
            job=c.client.get(c.base+'/hybrid-jobs/index').json()
            assert job['state']=='running' and job['progress']['phase']=='embedding'
            assert job['progress']['completed_batches']==1 and job['progress']['total_batches']==2
            assert job['progress']['total_windows']==3
            assert 'PRIVATE MUST' not in json.dumps(job) and '/private/example' not in json.dumps(job)
            # A workspace read and a second connection do not wait for neural compute.
            assert c.client.get(c.base).status_code==200
            with c.app.state.hybrid_retrieval.db() as db:assert db.execute('SELECT COUNT(*) FROM hybrid_jobs_v1').fetchone()[0]==1
        finally:release.set()
        result=pending.result(timeout=5);assert result.status_code==200,result.text
    final=c.client.get(c.base+'/hybrid-jobs/index').json()
    assert final['state']=='completed' and final['progress']['phase']=='completed'
    assert final['progress']['completed_batches']==1 and callback['value'] is None
    assert 'progress' not in result.text and 'callback' not in result.text
    assert c.client.get(c.base+'/hybrid-exports').json()['runs']==[]


def test_cancel_records_request_then_terminal_state_and_explicit_new_request(flow):
    c=flow;adapter=c.packs.adapters[QWEN_PROFILE];started,release=Event(),Event();callback={'value':None}
    adapter.set_progress=lambda value:callback.update(value=value)
    original=adapter.encode_documents
    def encode(docs):
        callback['value'](phase='embedding',component='document',completed_batches=0,total_batches=2,processed_items=0,total_items=len(docs))
        started.set();assert release.wait(5);return original(docs)
    adapter.encode_documents=encode
    with ThreadPoolExecutor() as pool:
        pending=pool.submit(c.client.post,c.base+'/hybrid-index',json=c.payload)
        try:
            assert started.wait(3)
            cancelling=c.client.post(c.base+'/hybrid-jobs/index/cancel').json()
            assert cancelling['progress']['phase']=='cancelling'
        finally:release.set()
        result=pending.result(timeout=5);assert result.status_code==503 and result.json()['error']['code']=='hybrid_cancelled'
    job=c.client.get(c.base+'/hybrid-jobs/index').json()
    assert job['state']=='cancelled' and job['retry_allowed'] is True
    assert callback['value'] is None
    assert list(c.packs.root.rglob('*.json'))==[]
    replay=c.client.post(c.base+'/hybrid-index',json=c.payload)
    assert replay.status_code==422 and replay.json()['error']['code']=='retrieval_already_attempted'
    adapter.encode_documents=original
    assert post(c,'/hybrid-index',{**c.payload,'request_id':'explicit-retry'})['state']=='ready'


def test_progress_counters_reject_bad_values_without_changing_saved_status(flow):
    runtime=flow.app.state.hybrid_retrieval
    with runtime.operation(flow.workspace['id'],'bounded','index','fingerprint'):
        runtime._progress(flow.workspace['id'],'bounded',phase='embedding',completed_batches=0,total_batches=1)
        for value in (-1,1000001,True,3.5,'secret'):
            with pytest.raises(MvpError):runtime._progress(flow.workspace['id'],'bounded',phase='embedding',completed_batches=value)
        with pytest.raises(MvpError):runtime._progress(flow.workspace['id'],'bounded',phase='private question')
        assert runtime.job(flow.workspace['id'],'bounded')['progress']['completed_batches']==0


def test_progress_callback_never_enters_stable_runtime_metadata_or_hash():
    from src.mvp.hybrid_retrieval import adapter_profile_hash
    adapter=native.NeuralAdapter.__new__(native.NeuralAdapter)
    adapter.profile_id=QWEN_PROFILE;adapter.device='cpu';adapter.manifest={'software':'mock'}
    adapter._executed={};adapter._timing={};adapter._token_counts={}
    before=adapter_profile_hash(adapter);seen=[];adapter.set_progress(lambda **value:seen.append(value))
    adapter._report('embedding',completed_batches=1,total_batches=1)
    assert seen==[{'phase':'embedding','completed_batches':1,'total_batches':1}]
    assert before==adapter_profile_hash(adapter)
    assert 'progress' not in json.dumps(adapter.runtime_metadata())


def test_dependency_status_uses_specs_metadata_without_import_or_execution(monkeypatch):
    import builtins,importlib.util,importlib.metadata
    original=builtins.__import__;calls=[]
    def guarded(name,*args,**kwargs):
        if name.split('.')[0] in {'torch','transformers','tokenizers','numpy','safetensors','huggingface_hub'}:pytest.fail('Heavy import during metadata check')
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',guarded)
    monkeypatch.setattr(importlib.util,'find_spec',lambda name:calls.append(name) or None)
    value=retrieval_packs.runtime_dependencies()
    assert value['state']=='needed' and len(value['missing'])==6 and len(calls)==6
    assert value['check_scope']=='metadata_only_not_execution'
    assert '--with-retrieval' in value['install_hint']


def test_restart_marks_interrupted_but_preserves_only_sanitized_last_counters(flow):
    from src.mvp.hybrid_service import HybridEvidenceService
    c=flow;runtime=c.app.state.hybrid_retrieval
    with runtime.db() as db:
        db.execute('INSERT INTO hybrid_jobs_v1 VALUES(?,?,?,?,?,?)',(c.workspace['id'],'stopped-index','index','running',json.dumps({'message':'','progress':{'phase':'embedding','completed_batches':4,'total_batches':10,'processed_items':8,'total_items':20,'quotation':'PRIVATE','source_path':'/private/secret','unknown':42}}),'fingerprint'))
    restarted=HybridEvidenceService(runtime.registry,runtime.service_for,runtime.boards,c.root,c.packs)
    job=restarted.job(c.workspace['id'],'stopped-index')
    assert job['state']=='interrupted' and job['retry_allowed'] is True
    assert job['progress']=={'phase':'interrupted','completed_batches':4,'total_batches':10,'processed_items':8,'total_items':20}
    assert 'PRIVATE' not in json.dumps(job) and '/private/secret' not in json.dumps(job)
