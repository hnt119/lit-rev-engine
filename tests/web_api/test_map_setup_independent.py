"""Offline setup/lifecycle regressions. Synthetic files/vectors are not BGE execution."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import socket
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from src.mvp.adapters.paper_embeddings import LocalPaperEmbedder, REQUIRED_FILES
from src.mvp.mapping import BGE_REVISION, EmbeddedPaper, EmbeddingProfile, validate_vector
from src.mvp.ports import MvpError
from src.web_api.app import COOKIE_NAME, create_app
import src.web_api.map_setup_routes as maps
from src.web_api.runtime_settings import RuntimeSettings, SettingsPut

P='/api/v1'


def client_for(app,cookie=None):
    client=TestClient(app,base_url='http://127.0.0.1:8765')
    if cookie: client.cookies.set(COOKIE_NAME,cookie)
    session=client.get(P+'/session').json()
    client.headers.update({'Origin':'http://127.0.0.1:3000','X-CSRF-Token':session['csrf_token']})
    return client


def save(client,*,enabled=True,cache_dir='',revision=None):
    old=client.get(P+'/settings').json()
    pref=deepcopy(old['preferences']);pref['maps'].update(enabled=enabled,cache_dir=str(cache_dir))
    return client.put(P+'/settings',json={'expected_revision':old['revision'] if revision is None else revision,'preferences':pref})


def snapshot(cache):
    path=cache/'models--BAAI--bge-small-en-v1.5'/'snapshots'/BGE_REVISION
    for item in maps.MANIFEST['files']:
        file=path/item['path'];file.parent.mkdir(parents=True,exist_ok=True)
        # Sparse synthetic files satisfy metadata only. They never reach a real loader.
        with file.open('wb') as stream: stream.truncate(item['bytes'])
    return path


@pytest.fixture
def offline(monkeypatch):
    calls=[]
    def deny(*args,**kwargs):
        calls.append(1);raise AssertionError('No networking is allowed in offline semantic-map tests')
    monkeypatch.setattr(socket.socket,'connect',deny)
    monkeypatch.setattr(socket,'create_connection',deny)
    return calls


def available():
    return dict(state='available',versions=maps.EXPECTED_VERSIONS,missing=[],incompatible=[],message='Synthetic metadata fixture',check_scope='metadata_only_not_execution')


class SyntheticEmbedder(LocalPaperEmbedder):
    calls=[]
    @property
    def profile(self):
        return EmbeddingProfile(model='SYNTHETIC SOFTWARE TEST',model_revision='fixture',tokenizer_revision='fixture',dimension=3)
    def embed(self,representation,checkpoint):
        self.calls.append(representation.paper_id);checkpoint()
        value=int(representation.input_sha256[:8],16)
        return EmbeddedPaper(paper_id=representation.paper_id,input_sha256=representation.input_sha256,representation=representation.representation,
            vector=validate_vector([1.,value%997,(value//997)%991],3),window_token_weights=[1],token_count=1)


def test_read_and_save_do_not_load_models_or_download_and_enable_is_per_session(tmp_path,monkeypatch,offline):
    monkeypatch.setattr(maps,'runtime_status',available)
    app=create_app(tmp_path/'app');client=client_for(app);second=client_for(app)
    cache=tmp_path/'cache';snapshot(cache)
    first=client.get(P+'/settings/maps').json()
    assert first['configuration']['enabled'] is False
    response=save(client,cache_dir=cache)
    assert response.status_code==200,response.text
    state=client.get(P+'/settings/maps').json()
    assert state['ready'] is True and state['computation']['state']=='not_tested'
    assert client.get(P+'/capabilities').json()['map']['ready'] is True
    assert second.get(P+'/settings/maps').json()['configuration']['enabled'] is False
    assert second.get(P+'/capabilities').json()['map']['ready'] is False
    assert offline==[]


def test_missing_dependencies_and_weights_are_independent_and_actions_fail_closed(tmp_path,monkeypatch,offline):
    state=available();state.update(state='missing',missing=['umap-learn'])
    monkeypatch.setattr(maps,'runtime_status',lambda:state)
    app=create_app(tmp_path/'app');client=client_for(app)
    assert save(client,cache_dir=tmp_path/'empty').status_code==200
    status=client.get(P+'/settings/maps').json()
    assert status['runtime']['missing']==['umap-learn'] and status['weights']['state']=='missing'
    assert status['download']['supported'] is False
    for action,extra in [('verify',{}),('install',{'manifest_sha256':status['download']['manifest_sha256'],'accept_download':True})]:
        response=client.post(P+'/settings/maps/'+action,json={'expected_revision':1,**extra})
        assert response.status_code==422
    assert offline==[]


def test_stale_revision_csrf_download_consent_and_invalid_cache_preserve_saved_settings(tmp_path,monkeypatch,offline):
    monkeypatch.setattr(maps,'runtime_status',available)
    client=client_for(create_app(tmp_path/'app'))
    old=client.get(P+'/settings').json()
    response=save(client,cache_dir='relative/cache')
    assert response.status_code==422 and client.get(P+'/settings').json()==old
    assert client.get(P+'/capabilities').status_code==200
    assert save(client,cache_dir=tmp_path/'models').status_code==200
    response=client.post(P+'/settings/maps/verify',json={'expected_revision':0})
    assert response.status_code==409
    response=client.post(P+'/settings/maps/install',json={'expected_revision':1,'manifest_sha256':'a'*64,'accept_download':True})
    assert response.status_code==422 and response.json()['error']['code']=='map_download_consent'
    response=client.post(P+'/settings/maps/install',json={'expected_revision':1,'manifest_sha256':'a'*64,'accept_download':False})
    assert response.status_code==422
    response=client.post(P+'/settings/maps/verify',json={'expected_revision':1},headers={'X-CSRF-Token':'wrong'})
    assert response.status_code==403
    assert offline==[]


def test_historic_inert_invalid_cache_does_not_break_core_capabilities(tmp_path,monkeypatch,offline):
    monkeypatch.setattr(maps,'runtime_status',available)
    app=create_app(tmp_path/'app');client=client_for(app)
    assert save(client).status_code==200
    store=app.state.runtime_settings
    owner=next(store.directory.glob('*.json')).stem
    value=store._read(owner);value['preferences']['maps']['cache_dir']='old/relative/cache'
    store._path(owner).write_text(__import__('json').dumps(value))
    status=client.get(P+'/settings/maps')
    assert status.status_code==200 and status.json()['configuration']['source']=='invalid_cache'
    response=client.get(P+'/capabilities')
    assert response.status_code==200 and response.json()['map']['ready'] is False
    assert client.get(P+'/workspaces').status_code==200
    assert save(client,cache_dir='').status_code==200


def test_verify_failure_is_retained_and_retry_success_is_invalidated_by_settings_change(tmp_path,monkeypatch,offline):
    monkeypatch.setattr(maps,'runtime_status',available)
    app=create_app(tmp_path/'app');client=client_for(app);cache=tmp_path/'models';snapshot(cache)
    save(client,cache_dir=cache)
    setup=app.state.map_setup;setup.factory=SyntheticEmbedder;setup._adapters.clear()
    monkeypatch.setattr(maps,'projection',lambda vectors:(_ for _ in ()).throw(RuntimeError('SYNTHETIC failure secret must be redacted')))
    response=client.post(P+'/settings/maps/verify',json={'expected_revision':1})
    assert response.status_code==200 and response.json()['computation']['state']=='failed'
    assert 'secret' not in response.text
    assert client.get(P+'/settings/maps').json()['computation']['state']=='failed'
    monkeypatch.setattr(maps,'projection',lambda vectors:None)
    response=client.post(P+'/settings/maps/verify',json={'expected_revision':1})
    assert response.status_code==200 and response.json()['computation']['state']=='succeeded'
    assert save(client,cache_dir=cache,enabled=False).status_code==200
    assert client.get(P+'/settings/maps').json()['computation']['state']=='not_tested'
    assert offline==[]


def test_download_failure_cleans_only_owned_staging_and_retry_is_explicit(tmp_path,monkeypatch,offline):
    monkeypatch.setattr(maps,'runtime_status',available)
    app=create_app(tmp_path/'app');client=client_for(app);cache=tmp_path/'models'
    save(client,cache_dir=cache)
    untouched=cache/'models--Qwen--Qwen3-Embedding-0.6B'/'receipt.txt';untouched.parent.mkdir(parents=True);untouched.write_text('Synthetic Qwen sentinel')
    calls=[]
    class Broken:
        def open(self,*args,**kwargs): calls.append(1);raise OSError('SYNTHETIC failure credential redaction')
    monkeypatch.setattr(maps,'build_opener',lambda *args:Broken())
    status=client.get(P+'/settings/maps').json()
    request=dict(expected_revision=1,manifest_sha256=status['download']['manifest_sha256'],accept_download=True)
    for count in (1,2):
        response=client.post(P+'/settings/maps/install',json=request)
        assert response.status_code==422 and response.json()['error']['code']=='map_download_failed'
        assert 'credential' not in response.text and len(calls)==count
        assert not list(cache.rglob('.map-setup-*'))
        assert not Path(status['download']['destination']).exists()
    assert untouched.read_text()=='Synthetic Qwen sentinel'
    assert offline==[]


def test_saved_enabled_settings_start_worker_and_saved_map_reopens_without_refit(tmp_path,monkeypatch,offline):
    monkeypatch.setattr(maps,'runtime_status',available)
    path=tmp_path/'app';app=create_app(path);client=client_for(app);cache=tmp_path/'models';snapshot(cache)
    save(client,cache_dir=cache)
    app.state.map_setup.factory=SyntheticEmbedder;app.state.map_setup._adapters.clear()
    workspace=client.post(P+'/workspaces',json={'request_id':'workspace','question':'Synthetic map setup','mode':'saved_example'}).json()
    base=f'{P}/workspaces/{workspace["id"]}'
    search=client.post(base+'/searches',json={'request_id':'search','query':'Synthetic saved public subset','max_results':3}).json()
    created=client.post(base+'/maps',json={'request_id':'map','search_id':search['id']})
    assert created.status_code==200,created.text
    job=created.json()['job'];deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        result=client.get(base+'/jobs/'+job['id']).json()
        if result['status'] in {'succeeded','failed'}:break
        time.sleep(.02)
    assert result['status']=='succeeded',result
    first=client.get(base+'/maps/'+job['map_id']).json()
    assert len(first['artifact']['coordinates_by_paper_id'])==3
    app.state.map_worker.stop()
    calls=len(SyntheticEmbedder.calls)
    reopened=create_app(path);other=client_for(reopened,client.cookies.get(COOKIE_NAME))
    assert other.get(base+'/maps/'+job['map_id']).json()==first
    assert len(SyntheticEmbedder.calls)==calls
    assert other.get(P+'/settings/maps').json()['configuration']['enabled'] is True
    assert offline==[]


def test_hash_checked_install_is_atomic_idempotent_and_never_touches_qwen(tmp_path,monkeypatch,offline):
    import io
    monkeypatch.setattr(maps,'runtime_status',available)
    payloads={name:('SYNTHETIC MODEL FILE '+name).encode() for name in REQUIRED_FILES}
    manifest=deepcopy(maps.MANIFEST)
    manifest['files']=[dict(path=name,bytes=len(data),sha256=sha256(data).hexdigest()) for name,data in payloads.items()]
    monkeypatch.setattr(maps,'MANIFEST',manifest)
    app=create_app(tmp_path/'app');client=client_for(app);cache=tmp_path/'models'
    save(client,cache_dir=cache)
    sentinel=cache/'models--Qwen--Qwen3-Embedding-0.6B'/'sentinel';sentinel.parent.mkdir(parents=True);sentinel.write_bytes(b'Qwen retained')
    calls=[]
    class Files:
        def open(self,request,**kwargs):
            calls.append(request.full_url)
            assert '/resolve/'+BGE_REVISION+'/' in request.full_url
            name=request.full_url.split('/'+BGE_REVISION+'/',1)[1]
            return io.BytesIO(payloads[name])
    monkeypatch.setattr(maps,'build_opener',lambda *args:Files())
    current=client.get(P+'/settings/maps').json()
    request=dict(expected_revision=1,manifest_sha256=current['download']['manifest_sha256'],accept_download=True)
    response=client.post(P+'/settings/maps/install',json=request)
    assert response.status_code==200,response.text
    assert response.json()['weights']['state']=='present' and len(calls)==len(REQUIRED_FILES)
    assert response.json()['computation']['state']=='not_tested'
    assert sentinel.read_bytes()==b'Qwen retained'
    assert client.post(P+'/settings/maps/install',json=request).status_code==200
    assert len(calls)==len(REQUIRED_FILES)  # explicit retry reuses verified existing bytes
    assert not list(cache.rglob('.map-setup-*'))
    # Same-size corruption is detected before a real loader can see these synthetic bytes.
    target=Path(response.json()['weights']['snapshot'])/'config.json'
    target.write_bytes(b'x'*target.stat().st_size)
    failed=client.post(P+'/settings/maps/verify',json={'expected_revision':1})
    assert failed.status_code==200
    assert failed.json()['computation']['error_code']=='map_weights_invalid'
    assert 'different cache' in failed.json()['computation']['message']


def test_authorized_pending_job_recovers_at_backend_restart_without_new_submit(tmp_path,monkeypatch,offline):
    monkeypatch.setattr(maps,'runtime_status',available)
    directory=tmp_path/'app';cache=tmp_path/'models';snapshot(cache)
    app=create_app(directory);client=client_for(app);save(client,cache_dir=cache)
    app.state.map_setup.factory=SyntheticEmbedder;app.state.map_setup._adapters.clear()
    monkeypatch.setattr(app.state.map_worker,'start',lambda **kwargs:False)
    work=client.post(P+'/workspaces',json={'request_id':'recovery-work','question':'Synthetic recovery','mode':'saved_example'}).json()
    base=f'{P}/workspaces/{work["id"]}'
    search=client.post(base+'/searches',json={'request_id':'search','query':'Synthetic public subset','max_results':3}).json()
    created=client.post(base+'/maps',json={'request_id':'recovery-map','search_id':search['id']}).json()
    assert created['job']['status']=='queued' and app.state.map_worker._thread is None
    reopened=create_app(directory);reopened.state.map_setup.factory=SyntheticEmbedder
    with TestClient(reopened,base_url='http://127.0.0.1:8765'):
        other=client_for(reopened,client.cookies.get(COOKIE_NAME))
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            result=other.get(base+'/jobs/'+created['job']['id']).json()
            if result['status'] in {'succeeded','failed'}:break
            time.sleep(.02)
        assert result['status']=='succeeded',result
        assert other.get(base+'/maps/'+created['job']['map_id']).status_code==200
    assert offline==[]
