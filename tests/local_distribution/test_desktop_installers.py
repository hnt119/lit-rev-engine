"""Native packaging policy checks, not installed-device qualification."""
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import pytest
from scripts import build_desktop_preview as base
from scripts import build_desktop_installers as native


def test_native_product_identity_does_not_open_source_or_preview_data():
    value=native.product()
    assert value['name']=='Literature Review Engine'
    assert value['data_name']=='LiteratureReviewEngineDesktop'
    assert value['app_id']=='org.hnt119.litrev.desktop'
    assert value['require_installed_location'] is True



def test_successor_native_build_identity_is_numeric_and_separate_from_beta_label():
    value=native.product()
    assert value['version']=='0.3.0-desktop-beta.2'
    assert value['build_number']==3002
    assert base.native_build_number(value)=='3002'
    for invalid in (None,True,'3002',0,-1,10000):
        with pytest.raises(ValueError,match='numeric build number'):
            base.native_build_number({**value,'build_number':invalid})


def test_windows_inputs_bind_exact_official_target_and_digest():
    lock=json.loads((base.ROOT/'apps/desktop/runtime-lock.win32-x64.json').read_text())
    assert lock['target']=='win32-x64'
    assert 'win32-x64' in lock['electron']['file']
    assert 'x86_64-pc-windows-msvc' in lock['python']['file']
    for key in ('electron','python','python_attribution'):
        assert lock[key]['url'].startswith('https://github.com/')
        assert len(lock[key]['sha256'])==64


def test_prune_removes_only_unused_sharp_families_and_records_exact_files(tmp_path):
    web=tmp_path/'web';web.mkdir()
    for name,identity in [('sharp','sharp'),('libvips','@img/sharp-libvips-darwin-arm64'),('other','sharp-tools')]:
        d=web/name;d.mkdir();(d/'package.json').write_text(json.dumps({'name':identity,'version':'1'}));(d/'index.js').write_text('synthetic '+name)
    original=(web/'other/index.js').read_bytes()
    removed=base.prune_unused_image_optimizer(web)
    assert set(removed)=={'sharp/package.json','sharp/index.js','libvips/package.json','libvips/index.js'}
    assert not (web/'sharp').exists() and not (web/'libvips').exists()
    assert (web/'other/index.js').read_bytes()==original


def test_desktop_image_policy_does_not_change_source_configuration(tmp_path):
    web=tmp_path/'web';app=web/'apps/web';(app/'.next').mkdir(parents=True)
    cfg={'images':{'formats':['image/webp']},'turbopack':{'root':'/build'},'poweredByHeader':False}
    (app/'server.js').write_text("const path=require('path');const dir=__dirname;\nconst nextConfig = "+json.dumps(cfg)+"\nprocess.env.__NEXT_PRIVATE_STANDALONE_CONFIG=JSON.stringify(nextConfig)\n")
    (app/'.next/required-server-files.json').write_text(json.dumps({'appDir':'/build','config':cfg}))
    base.portable_web_build(web,unoptimized_images=True)
    actual=json.loads((app/'.next/required-server-files.json').read_text())['config']
    assert actual['images']=={'formats':['image/webp'],'unoptimized':True}
    assert actual['poweredByHeader'] is False


def test_project_boundary_replaces_complete_upstream_copy_with_bound_own_sources(tmp_path):
    web=tmp_path/'web';d=web/'node_modules/client-only';d.mkdir(parents=True)
    original=base.ROOT/'apps/web/node_modules/.pnpm/client-only@0.0.1/node_modules/client-only'
    for name in ('package.json','index.js','error.js'):shutil.copy2(original/name,d/name)
    result=base.replace_client_boundary(web)
    assert len(result)==1 and result[0]['original_package']=='client-only@0.0.1'
    assert set(result[0]['removed_files'])=={'node_modules/client-only/package.json','node_modules/client-only/index.js','node_modules/client-only/error.js'}
    assert (d/'index.js').read_bytes()==(base.ROOT/'apps/desktop/client-boundary/index.js').read_bytes()
    assert set(p.name for p in d.iterdir())=={'package.json','index.js','error.js','LICENSE'}
    assert json.loads((d/'package.json').read_text())['name']=='@hnt119/litrev-client-boundary'
    node=os.environ.get('LITREV_TEST_NODE') or shutil.which('node')
    if node is None:pytest.skip('Existing Node toolchain not available; no installation is performed')
    result=subprocess.run([node,'-e',"const x=require('client-only');if(Object.keys(x).length)throw Error('Unexpected capability');"],cwd=web,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    result=subprocess.run([node,'--conditions=react-server','-e',"require('client-only')"],cwd=web,capture_output=True,text=True)
    assert result.returncode!=0 and 'client boundary cannot run' in result.stderr


def test_cross_target_pe_check_rejects_renamed_archives_and_non_amd64(tmp_path):
    p=tmp_path/'app.exe';p.write_bytes(b'PK source zip, not Windows executable')
    with pytest.raises(ValueError,match='PE runtime'):native.require_windows_pe(p)
    blob=bytearray(128);blob[:2]=b'MZ';struct.pack_into('<I',blob,0x3c,64);blob[64:68]=b'PE\0\0';struct.pack_into('<H',blob,68,0xaa64);p.write_bytes(blob)
    with pytest.raises(ValueError,match='AMD64'):native.require_windows_pe(p)
    struct.pack_into('<H',blob,68,0x8664);p.write_bytes(blob);native.require_windows_pe(p)


def test_nsis_policy_is_per_user_preserves_data_and_binds_target():
    text=(base.ROOT/'apps/desktop/installer.nsi').read_text()
    assert 'RequestExecutionLevel user' in text
    assert '$SMPROGRAMS\\Literature Review Engine\\Literature Review Engine.lnk' in text
    assert 'GetNativeSystemInfo' in text and 'RtlGetVersion' in text
    assert 'RMDir /r "$LOCALAPPDATA' not in text
    assert 'taskkill' not in text and 'HKLM' not in text
    assert 'app-${PRODUCT_VERSION}' in text


def test_unknown_same_version_guard_bytes_or_extra_file_are_rejected(tmp_path):
    original=base.ROOT/'apps/web/node_modules/.pnpm/client-only@0.0.1/node_modules/client-only'
    for mutation in ('bytes','extra','link'):
        web=tmp_path/mutation;d=web/'node_modules/client-only';d.mkdir(parents=True)
        for name in ('package.json','index.js','error.js'):shutil.copy2(original/name,d/name)
        if mutation=='bytes':(d/'error.js').write_text('Unreviewed guard variant')
        elif mutation=='extra':(d/'unreviewed.txt').write_text('Unexpected runtime payload')
        else:(d/'index.js').unlink();(d/'index.js').symlink_to(original/'index.js')
        with pytest.raises(ValueError,match='removal input'):base.replace_client_boundary(web)


def test_web_binding_covers_every_chunk_static_file_and_safe_symlink(tmp_path):
    standalone=tmp_path/'standalone';static=tmp_path/'static';public=tmp_path/'public'
    for d in (standalone,static,public):d.mkdir()
    (standalone/'server.js').write_text('Unchanged wrapper')
    chunk=standalone/'chunk.js';chunk.write_text('Reviewed UI chunk')
    asset=static/'bundle.js';asset.write_text('Reviewed client UI')
    (public/'icon.svg').write_text('<svg/>')
    (standalone/'alias.js').symlink_to('chunk.js')
    binding=base.web_build_binding(standalone,static,public,'a'*40)
    base.verify_web_build(binding,standalone,static,public,'a'*40)
    for path in (chunk,asset):
        before=path.read_bytes();path.write_bytes(b'Stale or mixed UI')
        with pytest.raises(ValueError,match='inventory'):base.verify_web_build(binding,standalone,static,public,'a'*40)
        path.write_bytes(before)
    (standalone/'extra.js').write_text('unexpected')
    with pytest.raises(ValueError,match='inventory'):base.verify_web_build(binding,standalone,static,public,'a'*40)
    (standalone/'extra.js').unlink();(standalone/'alias.js').unlink();(standalone/'alias.js').symlink_to(tmp_path/'outside.js')
    (tmp_path/'outside.js').write_text('Foreign input')
    with pytest.raises(ValueError,match='closure'):base.web_inventory(standalone)


def test_exact_next_traced_entry_projection_uses_full_installed_upstream_pin(tmp_path,monkeypatch):
    original=base.ROOT/'apps/web/node_modules/.pnpm/client-only@0.0.1/node_modules/client-only'
    root=tmp_path/'source';upstream=root/'apps/web/node_modules/.pnpm/client-only@0.0.1/node_modules/client-only'
    upstream.parent.mkdir(parents=True);shutil.copytree(original,upstream)
    shutil.copytree(base.ROOT/'apps/desktop/client-boundary',root/'apps/desktop/client-boundary')
    shutil.copy2(base.ROOT/'apps/desktop/client-boundary-input.json',root/'apps/desktop/client-boundary-input.json')
    web=tmp_path/'web';traced=web/'node_modules/client-only';traced.mkdir(parents=True)
    for name in ('package.json','index.js'):shutil.copy2(original/name,traced/name)
    monkeypatch.setattr(base,'ROOT',root)
    result=base.replace_client_boundary(web)
    assert result[0]['traced_projection']==['index.js','package.json']
    assert set(result[0]['verified_full_upstream_files'])=={'error.js','index.js','package.json'}
    assert len(result[0]['removed_files'])==2 and (traced/'error.js').is_file()
    shutil.rmtree(traced);traced.mkdir()
    for name in ('package.json','index.js'):shutil.copy2(original/name,traced/name)
    (upstream/'error.js').write_text('Tampered unused upstream guard')
    with pytest.raises(ValueError,match='reviewed exact bytes'):base.replace_client_boundary(web)


@pytest.mark.parametrize('names',[('package.json',),('index.js',),('package.json','error.js')])
def test_missing_required_traced_entry_or_metadata_is_rejected(tmp_path,names):
    original=base.ROOT/'apps/web/node_modules/.pnpm/client-only@0.0.1/node_modules/client-only'
    web=tmp_path/'web';traced=web/'node_modules/client-only';traced.mkdir(parents=True)
    for name in names:shutil.copy2(original/name,traced/name)
    with pytest.raises(ValueError,match='removal input'):base.replace_client_boundary(web)


def test_only_known_windows_console_and_pywin32_test_entrypoints_are_removed(tmp_path):
    resources=tmp_path/'resources';console=resources/'python/Lib/site-packages/bin';console.mkdir(parents=True)
    names=['fastapi','uvicorn','idna','pywin32_postinstall','pywin32_postinstall.py','pywin32_testall','pywin32_testall.py']
    for name in names:(console/name).write_bytes(('Reviewed wheel-generated '+name).encode())
    runtime=console.parent/'pywin32_bootstrap.py';runtime.write_text('Wheel-local runtime bootstrap retained')
    removed=native.prune_windows_build_entrypoints(resources)
    assert set(removed)=={'python/Lib/site-packages/bin/'+name for name in names}
    assert all(len(record['sha256'])==64 and record['bytes']>0 for record in removed.values())
    assert runtime.exists() and not console.exists()
    console.mkdir();(console/'unknown-command').write_text('Reject unreviewed launcher')
    with pytest.raises(ValueError,match='Unexpected'):native.prune_windows_build_entrypoints(resources)
    assert (console/'unknown-command').exists()


def test_windows_python_notice_projection_matches_actual_sbom_contract(tmp_path,monkeypatch):
    import tarfile
    from scripts.desktop_sbom import collect_payload
    source=tmp_path/'upstream/python';(source/'licenses').mkdir(parents=True)
    (source/'licenses/LICENSE.cpython.txt').write_text('Synthetic fixture notice; not upstream license text')
    data={'version':'8','target_triple':'x86_64-pc-windows-msvc','python_version':'3.12.15','build_options':'pgo','licenses':['Python-2.0'],'license_path':'licenses/LICENSE.cpython.txt',
        'build_info':{'extensions':{'_ssl':[{'licenses':['Apache-2.0'],'license_paths':['licenses/LICENSE.cpython.txt'],'links':[{'name':'ssl','system':False}]}]}}}
    raw=json.dumps(data).encode();(source/'PYTHON.json').write_bytes(raw)
    archive=tmp_path/'synthetic-attribution.tar.gz'
    with tarfile.open(archive,'w:gz') as bundle:bundle.add(source,arcname='python')
    monkeypatch.setattr(base,'verify_runtime',lambda cache,spec:archive)
    resources=tmp_path/'payload/resources';(resources/'python').mkdir(parents=True)
    native.windows_notices(resources,tmp_path,{'python_attribution':{'file':archive.name,'sha256':base.digest(archive.read_bytes())}})
    value=json.loads((resources/'python/UPSTREAM_LICENSES/PYTHON_LICENSE_PROVENANCE.json').read_text())
    assert value['schema']=='litrev.python-runtime-license-provenance.v1' and value['upstream_metadata_sha256']==base.digest(raw)
    bom,review=collect_payload(resources,'a'*40,'win32-x64')
    components=review['upstream_component_review']['python_runtime_components']
    assert any(part['name']=='CPython' and part['version']=='3.12.15' for part in components)


def test_notices_bind_before_materialization_and_retained_paths_remain_exact(tmp_path):
    import inspect
    from scripts.desktop_notices import copy_web_dependency_notices
    source=inspect.getsource(native.assemble_windows)
    assert source.index('notices=copy_web_dependency_notices')<source.index('materialized=materialize_verified_web')
    web=tmp_path/'web';installed=tmp_path/'installed';out=tmp_path/'notices'
    package=web/'node_modules/.pnpm/fixture@1.0.0/node_modules/fixture';package.mkdir(parents=True)
    original=installed/'.pnpm/fixture@1.0.0/node_modules/fixture';original.mkdir(parents=True)
    raw=json.dumps({'name':'fixture','version':'1.0.0','license':'MIT'})
    for root in (package,original):
        (root/'package.json').write_text(raw);(root/'index.js').write_text('Reviewed exact runtime module')
    (original/'LICENSE').write_text('Synthetic fixture notice')
    (web/'node_modules/fixture').symlink_to('.pnpm/fixture@1.0.0/node_modules/fixture',target_is_directory=True)
    (installed/'fixture').symlink_to('.pnpm/fixture@1.0.0/node_modules/fixture',target_is_directory=True)
    notices=copy_web_dependency_notices(web,installed,out)
    before={p.relative_to(web).as_posix():base.digest(p.read_bytes()) for p in web.rglob('*') if p.is_file() and not p.is_symlink()}
    native.materialize_verified_web(web)
    assert all((web/name).is_file() and base.digest((web/name).read_bytes())==sha for name,sha in before.items())
    assert (web/'node_modules/fixture/index.js').is_file() and not (web/'node_modules/fixture').is_symlink()
    for entry in notices['packages']:
        assert (web/entry['bundled_package_json']).is_file()
        for note in entry['notice_files']:assert base.digest((out/note['file']).read_bytes())==note['sha256']


def test_native_packagers_copy_hash_verified_source_evidence_before_immutable_receipts(tmp_path):
    import inspect
    from scripts.desktop_native_inventory import copy_native_source_evidence
    assert base.copy_native_source_evidence is copy_native_source_evidence
    mac=inspect.getsource(base.build)
    windows=inspect.getsource(native.assemble_windows)
    assert "native_source_evidence=copy_native_source_evidence(resources/'NATIVE_DEPENDENCY_NOTICES') if native else None" in mac
    assert mac.index('native_source_evidence=copy_native_source_evidence')<mac.index("run(['/usr/bin/codesign'")
    assert "'native_source_evidence':native_source_evidence" in mac
    assert windows.index("metadata['native_source_evidence']=base.copy_native_source_evidence")<windows.index("(resources/'DESKTOP_RELEASE.json').write_bytes")<windows.index('files={')
    destination=tmp_path/'resources/NATIVE_DEPENDENCY_NOTICES';destination.parent.mkdir()
    receipt=base.copy_native_source_evidence(destination)
    assert receipt['schema']=='litrev.native.source-evidence-copy.v1'
    assert receipt['manifest_sha256']==base.digest((destination/'MANIFEST.json').read_bytes())
    assert receipt['files']>100 and receipt['bytes']>0
    assert 'legal qualification remain separate' in receipt['qualification']
