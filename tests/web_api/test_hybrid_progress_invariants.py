"""Independent operational-progress checks; synthetic vectors, no real models."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event
import json
import pytest
from fastapi.testclient import TestClient
from test_hybrid_retrieval_independent import flow, post, search
from src.mvp.hybrid_contracts import QWEN_PROFILE
from src.mvp.ports import MvpError


def _progress_adapter(case):
    adapter=case.packs.adapters[QWEN_PROFILE]
    callback={'value':None}
    adapter.set_progress=lambda value:callback.update(value=value)
    return adapter,callback


def test_cancellation_intent_stays_visible_after_an_inflight_batch_callback(flow):
    runtime=flow.app.state.hybrid_retrieval;workspace=flow.workspace['id']
    with runtime.operation(workspace,'sticky-cancel','index','synthetic') as cancelled:
        runtime._progress(workspace,'sticky-cancel',phase='embedding',component='document',completed_batches=0,total_batches=2)
        assert runtime.cancel(workspace,'sticky-cancel')['progress']['phase']=='cancelling'
        # A forward pass already in flight may finish and report its last batch.
        runtime._progress(workspace,'sticky-cancel',phase='embedding',component='document',completed_batches=1,total_batches=2)
        state=runtime.job(workspace,'sticky-cancel')
        assert cancelled() is True
        assert state['progress']['phase']=='cancelling'
        assert state['progress']['completed_batches']==1


def test_progress_reads_and_foreign_session_cannot_execute_or_cancel_owned_work(flow):
    c=flow;runtime=c.app.state.hybrid_retrieval;workspace=c.workspace['id']
    with runtime.operation(workspace,'private-job','index','synthetic') as cancelled:
        before=deepcopy(c.packs.adapters[QWEN_PROFILE].calls)
        for _ in range(3):
            assert c.client.get(c.base+'/hybrid-jobs/private-job').status_code==200
        with TestClient(c.app,base_url='http://127.0.0.1:8765') as stranger:
            csrf=stranger.get('/api/v1/session').json()['csrf_token']
            stranger.headers.update({'Origin':'http://127.0.0.1:3000','X-CSRF-Token':csrf})
            assert stranger.get(c.base+'/hybrid-jobs/private-job').status_code==404
            assert stranger.post(c.base+'/hybrid-jobs/private-job/cancel').status_code==404
        assert cancelled() is False
        assert c.packs.adapters[QWEN_PROFILE].calls==before


def test_deleted_workspace_fences_late_callbacks_and_never_recreates_operational_rows(flow):
    c=flow;adapter,callback=_progress_adapter(c);started,release=Event(),Event();encode=adapter.encode_documents
    def blocked(documents):
        callback['value'](phase='embedding',component='document',completed_batches=0,total_batches=1)
        started.set();assert release.wait(5)
        # Callback arrives after the researcher deleted the workspace.
        callback['value'](phase='embedding',component='document',completed_batches=1,total_batches=1)
        return encode(documents)
    adapter.encode_documents=blocked
    with ThreadPoolExecutor() as pool:
        pending=pool.submit(c.client.post,c.base+'/hybrid-index',json=c.payload)
        try:
            assert started.wait(3)
            assert c.client.delete(c.base).status_code==200
        finally:release.set()
        response=pending.result(timeout=5)
    assert response.status_code in {404,422,503},response.text
    assert callback['value'] is None
    with c.app.state.hybrid_retrieval.db() as db:
        assert db.execute('SELECT COUNT(*) FROM hybrid_jobs_v1').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM hybrid_runs').fetchone()[0]==0
    assert not list(c.packs.root.rglob('*.json'))
    assert c.client.get(c.base+'/hybrid-jobs/index').status_code==404


def test_failure_sanitizes_operational_detail_and_clears_adapter_callback(flow):
    c=flow;adapter,callback=_progress_adapter(c)
    def failed(documents):
        callback['value'](phase='embedding',completed_batches=0,total_batches=1,quotation='PRIVATE QUOTE')
        raise MvpError('PRIVATE path / source text','Synthetic failure; no fallback')
    adapter.encode_documents=failed
    response=c.client.post(c.base+'/hybrid-index',json=c.payload)
    assert response.status_code==422,response.text
    job=c.client.get(c.base+'/hybrid-jobs/index').json()
    assert job['state']=='failed' and job['progress']['phase']=='failed'
    assert job['detail']=='retrieval_failure'
    assert job['retry_allowed'] is True
    assert 'PRIVATE' not in json.dumps(job)
    assert callback['value'] is None
    assert c.client.get(c.base+'/hybrid-exports').json()['runs']==[]
    assert not list(c.packs.root.rglob('*.json'))


def test_late_callbacks_do_not_change_terminal_jobs_or_saved_receipt_bytes(flow):
    c=flow;post(c,'/hybrid-index',c.payload);saved=search(c);runtime=c.app.state.hybrid_retrieval
    exported=c.client.get(c.base+'/hybrid-exports').content
    with runtime.db() as db:
        before=tuple(db.execute('SELECT payload,sha256 FROM hybrid_runs WHERE id=?',(saved['id'],)).fetchone())
    completed=c.client.get(c.base+'/hybrid-jobs/run').json()
    runtime._progress(c.workspace['id'],'run',phase='embedding',completed_batches=999,total_batches=1000)
    assert c.client.get(c.base+'/hybrid-jobs/run').json()==completed
    assert c.client.get(c.base+'/hybrid-exports').content==exported
    with runtime.db() as db:
        assert tuple(db.execute('SELECT payload,sha256 FROM hybrid_runs WHERE id=?',(saved['id'],)).fetchone())==before
    assert 'progress' not in json.dumps(saved)
    assert c.client.get(c.base+'/hybrid-runs/'+saved['id']).json()==saved


def test_metadata_dependency_versions_handle_missing_mismatch_and_build_suffix(monkeypatch):
    from src.mvp.retrieval_packs import runtime_dependencies
    import importlib.util,importlib.metadata
    versions={'torch':'2.12.0+cpu','transformers':'5.12.0','tokenizers':'0.22.2','safetensors':'0.8.0','huggingface-hub':'1.19.0','numpy':'2.4.6'}
    monkeypatch.setattr(importlib.util,'find_spec',lambda name:object())
    monkeypatch.setattr(importlib.metadata,'version',lambda name:versions[name])
    assert runtime_dependencies()['state']=='available'
    versions['torch']='2.11.0';assert runtime_dependencies()['incompatible']==['torch']
    def version(name):
        if name=='numpy':raise importlib.metadata.PackageNotFoundError(name)
        return versions[name]
    monkeypatch.setattr(importlib.metadata,'version',version)
    value=runtime_dependencies()
    assert value['missing']==['numpy'] and value['incompatible']==['torch']
    assert value['check_scope']=='metadata_only_not_execution'


def test_caller_held_lifecycle_guard_supports_exact_capture_without_reacquiring(flow, monkeypatch):
    """The platform/progress union must retain its guard=False context path."""
    from src.mvp.hybrid_app_contracts import HybridScopeRequest
    c=flow;runtime=c.app.state.hybrid_retrieval
    session=c.app.state.registry.resolve_session(c.client.cookies.get('litrev_local_session'))
    mode,handle=c.app.state.registry.workspace(session['token_hash'],c.workspace['id'])
    request=HybridScopeRequest.model_validate(c.payload)
    expected=runtime.capture(mode,handle,request)
    with runtime.registry.lifecycle_guard(handle.workspace_id):
        monkeypatch.setattr(runtime.registry,'lifecycle_guard',lambda *_:pytest.fail('A caller-held guard must not be reacquired'))
        captured=runtime.capture(mode,handle,request,guard=False)
        assert captured==expected
        runtime._revalidate(mode,handle,request,captured,guard=False)
    assert c.packs.adapters[QWEN_PROFILE].calls==[]
