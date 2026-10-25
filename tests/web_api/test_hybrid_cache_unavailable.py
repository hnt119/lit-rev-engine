"""An unsafe optional model cache cannot take core/manual research offline."""
import socket
import pytest
from fastapi.testclient import TestClient
from test_hybrid_retrieval_independent import SyntheticSources
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.hybrid_contracts import QWEN_PROFILE,MEDCPT_PROFILE
from src.mvp.service import MVPService
from src.mvp.retrieval_packs import PackManager
from src.web_api.app import create_app

@pytest.mark.parametrize('failure',['symlink','permission'])
def test_optional_cache_failure_keeps_core_manual_flow_available(tmp_path,monkeypatch,failure):
    monkeypatch.setattr(socket,'create_connection',lambda *a,**kw:pytest.fail('Optional cache failure must not trigger external access'))
    target=tmp_path/'private-external-cache';target.mkdir()
    if failure=='symlink':
        unsafe=tmp_path/'cache-link';unsafe.symlink_to(target,target_is_directory=True)
        monkeypatch.setenv('LITREV_RETRIEVAL_CACHE',str(unsafe))
    else:
        # OS permission bits are not reliable under privileged CI, so inject the
        # real constructor's narrow filesystem failure without network/models.
        monkeypatch.setattr(PackManager,'__init__',lambda *a,**kw:(_ for _ in ()).throw(PermissionError('synthetic denied cache')))
    sources=SyntheticSources();engine=MVPService(SQLiteWorkspaceStorage(tmp_path/'research.sqlite3'),sources,sources)
    app=create_app(tmp_path/'app-data',services={'saved_example':engine})
    client=TestClient(app,base_url='http://127.0.0.1:8765')
    csrf=client.get('/api/v1/session').json()['csrf_token']
    client.headers.update({'Origin':'http://127.0.0.1:3000','X-CSRF-Token':csrf})
    assert client.get('/api/v1/capabilities').status_code==200
    capability=client.get('/api/v1/settings/retrieval');assert capability.status_code==200,capability.text
    packs=capability.json()['packs']
    assert capability.json()['core_lexical_available'] is True
    assert {p['profile_id'] for p in packs}=={QWEN_PROFILE,MEDCPT_PROFILE}
    assert all(p['state']=='cache_unavailable' and p['installed'] is False and p['models'] for p in packs)
    assert app.state.retrieval_packs.root is None
    assert app.state.retrieval_packs.manifest(QWEN_PROFILE)['models']
    workspace=client.post('/api/v1/workspaces',json={'request_id':'workspace','mode':'saved_example'}).json()
    root='/api/v1/workspaces/'+workspace['id']
    search=client.post(root+'/searches',json={'request_id':'search','query':'synthetic'}).json()
    prep=client.post(root+'/source-preparations',json={'request_id':'prep','search_id':search['id'],'paper_ids':[p.id for p in sources.papers]}).json()
    common={'expected_preparation_id':prep['id'],'expected_source_revision':prep['source_revision']}
    lexical=client.post(root+'/evidence-runs',json={**common,'request_id':'core','question':'cohort','top_k':5})
    assert lexical.status_code==200,lexical.text
    assert lexical.json()['method']=='bm25_context_blocks' and lexical.json()['passages']
    assert client.get(root+'/exports?format=json').status_code==200
    profile={**common,'profile_id':QWEN_PROFILE,'device':'cpu','request_id':'index'}
    state=client.post(root+'/hybrid-index/status',json=profile)
    assert state.status_code==200 and state.json()['state']=='cache_unavailable'
    for path,body in [('/hybrid-index',profile),('/hybrid-runs',{**profile,'request_id':'hybrid','question':'cohort','top_k':5})]:
        response=client.post(root+path,json=body)
        assert response.status_code==422,response.text
        assert response.json()['error']['code']=='retrieval_cache_unavailable'
    for action in ('install','check-runtime','remove','cancel'):
        response=client.post('/api/v1/settings/retrieval/'+action,json={'expected_revision':0,'profile_id':QWEN_PROFILE,'device':'cpu'})
        assert response.status_code==422,response.text
        assert response.json()['error']['code']=='retrieval_cache_unavailable'
    assert len(client.get(root).json()['runs'])==1
    assert client.get(root+'/hybrid-runs').json()['runs']==[]
    assert list(target.iterdir())==[]
    assert not (tmp_path/'app-data'/'indexes').exists()
