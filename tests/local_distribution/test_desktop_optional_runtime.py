"""Capsule authority, path safety and atomicity. No actual models/downloads."""
from hashlib import sha256
import json
from pathlib import Path
import stat
import zipfile

import pytest
from scripts import install_desktop_optional_runtime as r


def fixture(tmp_path,files=None):
    root=tmp_path.resolve();source=files or {'python/bin/python3.12':b'SYNTHETIC non-executable runtime fixture\n','python/lib/site.py':b'SYNTHETIC module\n'}
    entries={name:{'bytes':len(raw),'sha256':sha256(raw).hexdigest(),'mode':0o500 if 'bin/' in name else 0o400} for name,raw in source.items()}
    m={'schema':r.MANIFEST,'id':'software-fixture-v1','target':'darwin-arm64','python_relative':'python/bin/python3.12','files':entries,'distributions':r.EXPECTED}
    raw=(r.canonical(m)+'\n').encode();archive=root/'capsule.zip'
    def write(content,items=source):
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('RUNTIME.json',content)
            for name,b in items.items():
                info=zipfile.ZipInfo(name);info.external_attr=(stat.S_IFREG|0o600)<<16;z.writestr(info,b)
    write(raw)
    entry={'availability':'available','id':m['id'],'format':'zip','archive_sha256':r.digest_file(archive),'archive_bytes':archive.stat().st_size,'manifest_sha256':sha256(raw).hexdigest(),'python_relative':m['python_relative']}
    catalog=root/'catalog.json'
    def catalog_write():catalog.write_text(json.dumps({'schema':r.SCHEMA,'targets':{'darwin-arm64':entry}}))
    catalog_write()
    return root,archive,catalog,entry,m,write,catalog_write


def test_unavailable_catalog_does_not_download_install_or_claim_ready(tmp_path):
    c=tmp_path/'catalog.json';c.write_text(json.dumps({'schema':r.SCHEMA,'targets':{'darwin-arm64':{'availability':'unavailable','reason':'No reviewed target artifact'}}}))
    assert r.status(c,tmp_path/'data','darwin-arm64')['state']=='unavailable'
    assert not (tmp_path/'data').exists()


def test_exact_artifact_installs_outside_app_replays_and_rechecks_all_files(tmp_path):
    root,archive,catalog,entry,m,_,_=fixture(tmp_path);calls=[]
    first=r.install(archive,catalog,root/'data','darwin-arm64',runner=lambda p:calls.append(p))
    assert first['state']=='installed_verified' and len(calls)==1
    assert Path(first['python']).is_relative_to(root/'data')
    assert r.status(catalog,root/'data','darwin-arm64')==first
    assert r.install(archive,catalog,root/'data','darwin-arm64',runner=lambda _:pytest.fail('Repeated import must not execute again'))==first
    p=Path(first['python']);p.chmod(0o600);p.write_bytes(b'tampered')
    with pytest.raises(ValueError,match='integrity'):r.status(catalog,root/'data','darwin-arm64')


@pytest.mark.parametrize('change',['hash','target','manifest','extra','traversal','dependency','symlink'])
def test_unapproved_changed_unsafe_or_wrong_target_artifact_is_rejected(tmp_path,change):
    root,a,c,e,m,write,save=fixture(tmp_path)
    if change=='hash':a.write_bytes(a.read_bytes()+b'changed')
    elif change=='target':m['target']='win32-x64'
    elif change=='manifest':m['id']='other'
    elif change=='dependency':m['distributions']={**r.EXPECTED,'torch':'0.0.0'}
    elif change=='extra':
        with zipfile.ZipFile(a,'a') as z:z.writestr('unexpected.py',b'forbidden')
    elif change=='traversal':m['files']['../outside']={'bytes':1,'sha256':sha256(b'x').hexdigest(),'mode':0o400}
    elif change=='symlink':
        with zipfile.ZipFile(a,'a') as z:
            info=zipfile.ZipInfo('unexpected-link');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(info,b'/etc/passwd')
    if change in {'target','manifest','dependency','traversal'}:
        raw=(r.canonical(m)+'\n').encode();write(raw);e['manifest_sha256']=sha256(raw).hexdigest()
    if change!='hash':e['archive_sha256']=r.digest_file(a);e['archive_bytes']=a.stat().st_size
    save()
    with pytest.raises((ValueError,RuntimeError)):
        r.install(a,c,root/'data','darwin-arm64',runner=lambda _:pytest.fail('Unsafe artifact executed'))
    assert not (root/'data/optional-runtimes/software-fixture-v1').exists()
    assert not (root/'outside').exists()


def test_failed_native_self_check_cleans_partial_and_preserves_core_state(tmp_path):
    root,a,c,*_=fixture(tmp_path);core=root/'data/core-research';core.parent.mkdir();core.write_text('preserve')
    def failed(_):raise r.RuntimeRejected('Native check failed')
    with pytest.raises(ValueError):r.install(a,c,root/'data','darwin-arm64',runner=failed)
    assert core.read_text()=='preserve'
    assert list((root/'data/optional-runtimes').iterdir())==[]


def test_owned_install_lease_is_not_bypassed_or_overwritten(tmp_path):
    root,a,c,*_=fixture(tmp_path);data=r.roots(root/'data');(data/'.runtime-install.lock').write_text('another operation')
    with pytest.raises(ValueError,match='interrupted'):r.install(a,c,root/'data','darwin-arm64',runner=lambda _:None)
    assert (data/'.runtime-install.lock').read_text()=='another operation'


def test_symlinked_destination_never_writes_into_other_state(tmp_path):
    root,a,c,*_=fixture(tmp_path);other=root/'other';other.mkdir();(root/'data').symlink_to(other,target_is_directory=True)
    with pytest.raises(ValueError):r.install(a,c,root/'data','darwin-arm64',runner=lambda _:None)
    assert list(other.iterdir())==[]


def test_capsule_uses_installed_distribution_versions_not_pips_vendored_metadata(tmp_path):
    from scripts.build_desktop_optional_runtime import inventory
    prefix=tmp_path/'python';(prefix/'bin').mkdir(parents=True);(prefix/'bin/python3.12').write_bytes(b'SYNTHETIC interpreter')
    site=prefix/'lib/python3.12/site-packages'
    for name,version in r.EXPECTED.items():
        p=site/(name+'-'+version+'.dist-info');p.mkdir(parents=True);(p/'METADATA').write_text('Name: '+name+'\nVersion: '+version+'\n')
    vendor=site/'pip/_vendor/torch-0.0.0.dist-info';vendor.mkdir(parents=True);(vendor/'METADATA').write_text('Name: torch\nVersion: 0.0.0\n')
    files,versions=inventory(prefix.resolve())
    assert versions['torch']==r.EXPECTED['torch']
    assert any('/pip/_vendor/' in path for path in files)  # Actual bundled vendored bytes remain inventoried.


def test_desktop_hint_is_managed_and_never_runs_import_or_pip(monkeypatch):
    from src.mvp.retrieval_packs import runtime_dependencies
    import importlib.util
    monkeypatch.setenv('LITREV_DESKTOP_RUNTIME_MODE','managed')
    monkeypatch.setattr(importlib.util,'find_spec',lambda _:None)
    result=runtime_dependencies()
    assert result['distribution']=='desktop' and result['state']=='needed'
    assert 'Application menu' in result['install_hint']
    assert 'pip' not in result['install_hint'] and 'setup' not in result['install_hint']
