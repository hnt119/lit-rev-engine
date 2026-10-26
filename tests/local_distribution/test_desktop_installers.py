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
