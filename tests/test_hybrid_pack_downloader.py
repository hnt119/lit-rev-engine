"""Independent bounded-download tests with synthetic bytes and no model network.

These validate the installer mechanism only; no fake model fixture establishes
encoder/reranker execution or evidence quality.
"""
from hashlib import sha256
import json
from pathlib import Path
import threading
import pytest
from src.mvp import retrieval_packs as packs
from src.mvp.contracts import digest
from src.mvp.ports import MvpError

PROFILE='hybrid_qwen3_06b_rrf_rerank_v1'

class Response:
    def __init__(self,chunks,*,status=200,headers=None,url='https://huggingface.co/official'):
        self.chunks=list(chunks);self.status=status;self.headers=headers or {};self.url=url
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def geturl(self):return self.url
    def read(self,size):
        if not self.chunks:return b''
        value=self.chunks.pop(0)
        if isinstance(value,BaseException):raise value
        return value

class Opener:
    def __init__(self,*responses):self.responses=list(responses);self.requests=[]
    def open(self,request,timeout):
        self.requests.append(request)
        if not self.responses:pytest.fail('Unexpected extra artifact request')
        return self.responses.pop(0)

@pytest.fixture
def fixture_pack(tmp_path,monkeypatch):
    data=b'0123456789 verified synthetic model bytes'
    revision='a'*40
    manifest={'pack_id':'independent-synthetic-v1','label':'synthetic test','license':'test fixture',
        'quality_status':'NOT_MODEL_EVIDENCE','download_bytes':len(data),'models':[
        {'repo':'ncbi/synthetic','revision':revision,'selected_bytes':len(data),'files':[
        {'path':'model.safetensors','bytes':len(data),'sha256':sha256(data).hexdigest(),
         'url':f'https://huggingface.co/ncbi/synthetic/resolve/{revision}/model.safetensors'}]}]}
    monkeypatch.setitem(packs.REGISTRY,PROFILE,manifest)
    manager=packs.PackManager(tmp_path/'private-cache')
    return manager,manifest,data


def test_verified_explicit_install_is_atomic_and_keeps_private_modes(fixture_pack,monkeypatch):
    manager,manifest,data=fixture_pack
    opener=Opener(Response([data[:10],data[10:]]))
    monkeypatch.setattr(packs,'build_opener',lambda *a:opener)
    result=manager.install(PROFILE)
    _,target,partial=manager._paths(PROFILE)
    assert result['installed'] and not partial.exists()
    assert len(opener.requests)==1
    assert opener.requests[0].get_header('Accept-encoding')=='identity'
    assert json.loads((target/'INSTALL.json').read_text())['verified_bytes']==len(data)
    assert (target/'INSTALL.json').stat().st_mode&0o777==0o600
    assert manager.verify(PROFILE)['ncbi/synthetic'].joinpath('model.safetensors').read_bytes()==data
    # Already installed is a no-network operation.
    assert manager.install(PROFILE)['installed']
    assert len(opener.requests)==1


def test_partial_bytes_resume_only_with_exact_range_and_final_hash(fixture_pack,monkeypatch):
    manager,manifest,data=fixture_pack
    _,target,partial=manager._paths(PROFILE)
    directory=partial/'ncbi--synthetic';directory.mkdir(parents=True)
    (directory/'model.safetensors').write_bytes(data[:10])
    opener=Opener(Response([data[10:]],status=206,headers={'Content-Range':f'bytes 10-{len(data)-1}/{len(data)}'}))
    monkeypatch.setattr(packs,'build_opener',lambda *a:opener)
    assert manager.install(PROFILE)['installed']
    assert opener.requests[0].get_header('Range')=='bytes=10-'
    assert target.joinpath('ncbi--synthetic/model.safetensors').read_bytes()==data


def test_server_ignoring_range_restarts_complete_artifact(fixture_pack,monkeypatch):
    manager,_,data=fixture_pack
    _,target,partial=manager._paths(PROFILE)
    directory=partial/'ncbi--synthetic';directory.mkdir(parents=True)
    (directory/'model.safetensors').write_bytes(b'incorrect-prefix')
    opener=Opener(Response([data],status=200))
    monkeypatch.setattr(packs,'build_opener',lambda *a:opener)
    assert manager.install(PROFILE)['installed']
    assert target.joinpath('ncbi--synthetic/model.safetensors').read_bytes()==data


@pytest.mark.parametrize('chunks,code',[
    ([b'wrong length content'],'pack_hash'),
    ([b'x'*1000],'pack_size'),
])
def test_mismatch_or_overrun_never_creates_installed_pack(fixture_pack,monkeypatch,chunks,code):
    manager,_,_=fixture_pack
    opener=Opener(Response(chunks))
    monkeypatch.setattr(packs,'build_opener',lambda *a:opener)
    with pytest.raises(MvpError) as caught:manager.install(PROFILE)
    assert caught.value.code==code
    _,target,partial=manager._paths(PROFILE)
    assert not target.exists() and not manager.status(PROFILE)['installed']
    assert not partial.joinpath('INSTALL.json').exists()


def test_malformed_resume_response_is_rejected_before_any_file_write(fixture_pack,monkeypatch):
    manager,_,data=fixture_pack
    _,target,partial=manager._paths(PROFILE)
    directory=partial/'ncbi--synthetic';directory.mkdir(parents=True)
    file=directory/'model.safetensors';file.write_bytes(data[:10])
    opener=Opener(Response([data[10:]],status=206,headers={'Content-Range':'bytes 9-39/40'}))
    monkeypatch.setattr(packs,'build_opener',lambda *a:opener)
    with pytest.raises(MvpError) as caught:manager.install(PROFILE)
    assert caught.value.code=='pack_resume'
    assert file.read_bytes()==data[:10] and not target.exists()


def test_network_interruption_retains_only_uninstalled_resumable_bytes(fixture_pack,monkeypatch):
    manager,_,data=fixture_pack
    opener=Opener(Response([data[:10],OSError('synthetic disconnection')]))
    monkeypatch.setattr(packs,'build_opener',lambda *a:opener)
    with pytest.raises(OSError):manager.install(PROFILE)
    _,target,partial=manager._paths(PROFILE)
    assert not target.exists() and not manager.status(PROFILE)['installed']
    assert partial.joinpath('ncbi--synthetic/model.safetensors').read_bytes()==data[:10]
    opener.responses=[Response([data[10:]],status=206,headers={'Content-Range':f'bytes 10-{len(data)-1}/{len(data)}'})]
    assert manager.install(PROFILE)['installed']


def test_cancel_after_final_hash_prevents_atomic_publication(fixture_pack,monkeypatch):
    manager,_,data=fixture_pack
    opener=Opener(Response([data]));monkeypatch.setattr(packs,'build_opener',lambda *a:opener)
    cancelled=threading.Event();original=packs._hash
    def hash_then_cancel(path):
        result=original(path);cancelled.set();return result
    monkeypatch.setattr(packs,'_hash',hash_then_cancel)
    with pytest.raises(MvpError) as caught:manager.install(PROFILE,cancelled=cancelled.is_set)
    assert caught.value.code=='pack_cancelled'
    _,target,_=manager._paths(PROFILE)
    assert not target.exists() and not manager.status(PROFILE)['installed']


def test_install_never_follows_symlink_or_hardlink_partial_artifact(fixture_pack,monkeypatch,tmp_path):
    manager,_,data=fixture_pack
    _,target,partial=manager._paths(PROFILE)
    directory=partial/'ncbi--synthetic';directory.mkdir(parents=True)
    victim=tmp_path/'original-private-file';victim.write_bytes(b'private unrelated original')
    file=directory/'model.safetensors';file.symlink_to(victim)
    opener=Opener(Response([data]));monkeypatch.setattr(packs,'build_opener',lambda *a:opener)
    with pytest.raises(MvpError):manager.install(PROFILE)
    assert victim.read_bytes()==b'private unrelated original'
    file.unlink();file.hardlink_to(victim)
    with pytest.raises(MvpError):manager.install(PROFILE)
    assert victim.read_bytes()==b'private unrelated original' and not target.exists()


def test_installed_model_directory_symlink_is_not_hash_verified_in_place(fixture_pack,tmp_path):
    manager,manifest,data=fixture_pack
    _,target,_=manager._paths(PROFILE);target.mkdir()
    external=tmp_path/'outside-pack';external.mkdir();(external/'model.safetensors').write_bytes(data)
    (target/'ncbi--synthetic').symlink_to(external)
    (target/'INSTALL.json').write_text(json.dumps({'manifest_sha256':digest(manifest)}))
    with pytest.raises(MvpError):manager.verify(PROFILE)


def test_install_marker_symlink_is_rejected(fixture_pack,tmp_path):
    manager,manifest,data=fixture_pack
    _,target,_=manager._paths(PROFILE);target.mkdir()
    directory=target/'ncbi--synthetic';directory.mkdir();(directory/'model.safetensors').write_bytes(data)
    marker=tmp_path/'outside-marker';marker.write_text(json.dumps({'manifest_sha256':digest(manifest)}))
    (target/'INSTALL.json').symlink_to(marker)
    with pytest.raises(MvpError):manager.verify(PROFILE)


def test_untrusted_redirect_is_rejected_without_writing_response(fixture_pack,monkeypatch):
    manager,_,data=fixture_pack
    opener=Opener(Response([data],url='https://not-the-official-host.invalid/weights'))
    monkeypatch.setattr(packs,'build_opener',lambda *a:opener)
    with pytest.raises(MvpError) as caught:manager.install(PROFILE)
    assert caught.value.code=='pack_host'
    _,target,partial=manager._paths(PROFILE)
    assert not target.exists() and not partial.joinpath('ncbi--synthetic/model.safetensors').exists()


def test_explicit_runtime_cancel_stops_before_next_component_and_has_no_passed_badge(fixture_pack,monkeypatch):
    manager,_,_=fixture_pack
    calls=[]
    class Adapter:
        dimension=2
        def set_cancelled(self,callback):self.cancelled=callback
        def check(self):
            if self.cancelled():raise MvpError('pack_cancelled','Synthetic runtime cancelled between components')
        def validate_query(self,query):self.check()
        def encode_queries(self,queries):
            self.check();calls.append('query');manager.cancel(PROFILE);self.check()
            return [[1.,0.]]
        def encode_documents(self,docs):
            self.check();calls.append('document');return [[1.,0.] for _ in docs]
        def rerank(self,query,docs):
            self.check();calls.append('reranker');return [0. for _ in docs]
        def runtime_metadata(self):return {'device':'fake','not_model_execution':True}
    monkeypatch.setattr(manager,'adapter',lambda *args:Adapter())
    with pytest.raises(MvpError) as caught:manager.check_runtime(PROFILE)
    assert caught.value.code=='pack_cancelled' and calls==['query']
    assert manager.status(PROFILE)['state']=='cancelled'
    assert manager.status(PROFILE)['runtime'] is None
