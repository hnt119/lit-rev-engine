"""Offline pack lifecycle/security tests. These do not claim model quality."""
import importlib
import json
from pathlib import Path
import sys
from hashlib import sha256
import pytest
from src.mvp.contracts import digest
from src.mvp.ports import MvpError
from src.mvp import retrieval_packs as packs

PROFILE='hybrid_qwen3_06b_rrf_rerank_v1'


def test_registry_five_exact_official_revisions_and_nonempty_sha256():
    models=[model for pack in packs.REGISTRY.values() for model in pack['models']]
    assert len(models)==5
    for model in models:
        assert len(model['revision'])==40
        assert model['selected_bytes']==sum(f['bytes'] for f in model['files'])
        for item in model['files']:
            assert len(item['sha256'])==64
            assert f"/resolve/{model['revision']}/" in item['url']
            assert packs._safe_host(item['url'])
            assert not item['path'].endswith('.py')


def test_caps_do_not_import_neural_stack_or_call_network(tmp_path,monkeypatch):
    import urllib.request
    monkeypatch.setattr(urllib.request.OpenerDirector,'open',lambda *a,**k:pytest.fail('network on capabilities'))
    original=__import__('builtins').__import__
    def restricted(name,*a,**k):
        if name.split('.')[0] in {'torch','transformers','huggingface_hub','numpy'}:pytest.fail('neural import on core caps')
        return original(name,*a,**k)
    monkeypatch.setattr('builtins.__import__',restricted)
    manager=packs.PackManager(tmp_path/'external')
    assert len(manager.capabilities())==2
    assert not manager.status(PROFILE)['installed']
    with pytest.raises(MvpError,match='Install this exact'): manager.adapter(PROFILE)


def test_cache_symlinks_and_app_tree_refused(tmp_path):
    external=tmp_path/'real';external.mkdir()
    symbolic=tmp_path/'link';symbolic.symlink_to(external)
    with pytest.raises(MvpError):packs.PackManager(symbolic)
    with pytest.raises(MvpError):packs.PackManager(Path(packs.__file__).parent/'bad-cache')


def test_redirect_allowlist_no_credentials_or_arbitrary_remote_code():
    for url in ('http://huggingface.co/x','https://huggingface.co.evil/x','https://evil.invalid/x','https://secret@huggingface.co/x','https://huggingface.co:444/x'):
        assert not packs._safe_host(url)
    assert packs._safe_host('https://cas-bridge.xethub.hf.co/x?signature=123')


def fake_pack(tmp_path,monkeypatch):
    data=b'verified software fixture'
    manifest={'pack_id':'synthetic-v1','label':'synthetic','license':'synthetic','quality_status':'not_evaluated',
        'download_bytes':len(data),'models':[{'repo':'ncbi/synthetic','revision':'a'*40,'selected_bytes':len(data),
        'files':[{'path':'model.safetensors','bytes':len(data),'sha256':sha256(data).hexdigest(),'url':'https://huggingface.co/ncbi/synthetic/resolve/'+ 'a'*40 +'/model.safetensors'}]}]}
    monkeypatch.setitem(packs.REGISTRY,PROFILE,manifest)
    manager=packs.PackManager(tmp_path/'cache')
    return manager,manifest,data


def test_verified_install_marker_and_hash_recheck(tmp_path,monkeypatch):
    manager,manifest,data=fake_pack(tmp_path,monkeypatch)
    pack,target,partial=manager._paths(PROFILE)
    directory=target/'ncbi--synthetic';directory.mkdir(parents=True)
    file=directory/'model.safetensors';file.write_bytes(data)
    (target/'INSTALL.json').write_text(json.dumps({'manifest_sha256':digest(pack)}))
    assert manager.status(PROFILE)['installed']
    assert manager.verify(PROFILE)['ncbi/synthetic']==directory
    file.write_bytes(b'x'*len(data))
    with pytest.raises(MvpError,match='hash verification'):manager.verify(PROFILE)
    assert not (manager.root/'source.sqlite3').exists()


def test_remove_preserves_history_indexes_and_owned_sources(tmp_path,monkeypatch):
    manager,_,_=fake_pack(tmp_path,monkeypatch)
    history=manager.root/'history.json';history.write_text('saved exact anchors')
    indexes=manager.root/'indexes';indexes.mkdir();(indexes/'old.json').write_text('derived old index')
    assert manager.remove(PROFILE)['state']=='not_installed'
    assert history.read_text()=='saved exact anchors'
    assert (indexes/'old.json').read_text()=='derived old index'


def test_partial_is_never_installed_and_dead_worker_visible(tmp_path,monkeypatch):
    manager,_,_=fake_pack(tmp_path,monkeypatch)
    _,target,partial=manager._paths(PROFILE);partial.mkdir()
    packs._write(manager._state_path(PROFILE),{'state':'downloading','pid':999999999})
    status=manager.status(PROFILE)
    assert not status['installed'] and status['state']=='interrupted'
    with pytest.raises(MvpError):manager.adapter(PROFILE)


def test_single_pack_operation_cancel_no_fallback(tmp_path,monkeypatch):
    manager,_,_=fake_pack(tmp_path,monkeypatch)
    with manager._lease(PROFILE,'install') as event:
        with pytest.raises(MvpError):
            with manager._lease(PROFILE,'remove'):pass
        manager.cancel(PROFILE)
        assert event.is_set()
