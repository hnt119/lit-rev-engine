"""Independent desktop source/runtime integrity checks; no binaries or network."""
from hashlib import sha256
import json
from types import SimpleNamespace
import zipfile

import pytest

from scripts import build_desktop_preview as desktop
from scripts.run_web import LocalLaunchError

SOURCE = 'a' * 40


def source_archive(tmp_path, **changes):
    metadata = {'source_commit': SOURCE, 'source_state': 'clean committed checkout',
                'product_track': 'A', **changes}
    files = {'RELEASE.json': json.dumps(metadata).encode(), 'LICENSE': b'Synthetic license audit fixture\n'}
    manifest = {'files': {name: {'bytes': len(data), 'sha256': sha256(data).hexdigest()}
                          for name, data in files.items()}}
    archive = tmp_path / 'source.zip'
    with zipfile.ZipFile(archive, 'w') as bundle:
        for name, data in files.items(): bundle.writestr('source/' + name, data)
        bundle.writestr('source/MANIFEST.json', json.dumps(manifest))
    return archive


@pytest.mark.parametrize('name', ['.env', '.env.local', '.env.production', '.env.production.local'])
def test_desktop_build_rejects_ignored_next_environment_before_build_or_git(tmp_path, monkeypatch, name):
    web = tmp_path / 'apps/web'; web.mkdir(parents=True)
    (web / name).write_text('NEXT_PUBLIC_SYNTHETIC_PRIVATE_VALUE=must-not-be-baked\n')
    monkeypatch.setattr(desktop, 'ROOT', tmp_path)
    monkeypatch.setattr(desktop.sys, 'platform', 'darwin')
    monkeypatch.setattr(desktop.platform, 'machine', lambda: 'arm64')
    monkeypatch.setattr(desktop.subprocess, 'check_output', lambda *a, **kw: pytest.fail('Environment validation must precede Git/build'))
    monkeypatch.setattr(desktop, 'run', lambda *a, **kw: pytest.fail('No build/install/sign operation is permitted'))
    with pytest.raises(LocalLaunchError, match='Next.js .env'):
        desktop.build(SimpleNamespace())


@pytest.mark.parametrize('changes', [
    {'source_commit': 'b' * 40}, {'source_state': 'review working tree; not for publication'}, {'product_track': 'B'},
])
def test_desktop_rejects_wrong_source_dirty_package_and_track_b_before_extract(tmp_path, changes):
    archive = source_archive(tmp_path, **changes)
    destination = tmp_path / 'destination'
    with pytest.raises(ValueError, match='exact clean Track A'):
        desktop.extract_source(archive, destination, SOURCE)
    assert not destination.exists()


def test_desktop_extraction_checks_every_source_file_against_manifest(tmp_path):
    archive = source_archive(tmp_path)
    destination = tmp_path / 'extracted'
    result = desktop.extract_source(archive, destination, SOURCE)
    assert result['source_commit'] == SOURCE
    assert (destination / 'LICENSE').read_bytes() == b'Synthetic license audit fixture\n'
    # A fresh corrupted archive must fail instead of accepting modified bytes.
    corrupted = tmp_path / 'corrupted.zip'
    with zipfile.ZipFile(archive) as original, zipfile.ZipFile(corrupted, 'w') as altered:
        for name in original.namelist():
            altered.writestr(name, b'Altered bytes' if name.endswith('/LICENSE') else original.read(name))
    with pytest.raises(ValueError, match='Source manifest mismatch'):
        desktop.extract_source(corrupted, tmp_path / 'refused', SOURCE)


def test_runtime_archive_must_be_exact_ordinary_file_with_pinned_digest(tmp_path):
    path = tmp_path / 'runtime.zip'
    data = b'Synthetic runtime archive fixture; never executable'
    path.write_bytes(data)
    spec = {'file': path.name, 'sha256': sha256(data).hexdigest()}
    assert desktop.verify_runtime(tmp_path, spec) == path
    path.write_bytes(data + b'mutated')
    with pytest.raises(ValueError, match='exact verified runtime'):
        desktop.verify_runtime(tmp_path, spec)
    path.unlink(); target = tmp_path / 'target'; target.write_bytes(data); path.symlink_to(target)
    with pytest.raises(ValueError, match='exact verified runtime'):
        desktop.verify_runtime(tmp_path, spec)


def test_pinned_runtime_metadata_is_specific_to_one_arm64_target():
    lock = json.loads((desktop.ROOT / 'apps/desktop/runtime-lock.json').read_text())
    assert lock['target'] == 'darwin-arm64'
    assert set(lock) == {'schema', 'target', 'electron', 'python', 'python_attribution'}
    for kind in ('electron', 'python'):
        value = lock[kind]
        assert value['url'].startswith('https://github.com/')
        assert '/releases/download/' in value['url']
        assert len(value['sha256']) == 64 and set(value['sha256']) <= set('0123456789abcdef')
        assert value['version'] in value['file']


def test_generated_next_build_roots_are_portable_and_other_configuration_is_preserved(tmp_path):
    web=tmp_path/'web';app=web/'apps/web';(app/'.next').mkdir(parents=True)
    config={'repoRoot':'/synthetic/build/app','outputFileTracingRoot':'/synthetic/build',
            'turbopack':{'root':'/synthetic/build','fixture_option':True},
            'env':{},'poweredByHeader':False,'experimental':{'preserved':True}}
    server="const path = require('path')\nconst dir=__dirname\nconst nextConfig = "+json.dumps(config)+"\nprocess.env.__NEXT_PRIVATE_STANDALONE_CONFIG = JSON.stringify(nextConfig)\n"
    (app/'server.js').write_text(server)
    (app/'.next/required-server-files.json').write_text(json.dumps({'version':1,'appDir':'/synthetic/build/app','relativeAppDir':'apps/web','config':config,'files':['.next/BUILD_ID']}))
    desktop.portable_web_build(web)
    result=(app/'server.js').read_text()
    assert '/synthetic/build' not in result
    assert 'nextConfig.repoRoot = dir' in result
    value=json.loads((app/'.next/required-server-files.json').read_text())
    assert value['appDir']=='.' and value['files']==['.next/BUILD_ID']
    assert value['config']['poweredByHeader'] is False
    assert value['config']['experimental']=={'preserved':True}
    assert value['config']['turbopack']=={'fixture_option':True}


def test_generated_bundle_rejects_checkout_and_install_prefix_paths(tmp_path,monkeypatch):
    resources=tmp_path/'resources';resources.mkdir()
    root=tmp_path/'source';monkeypatch.setattr(desktop,'ROOT',root)
    output=tmp_path/'output'
    candidate=resources/'unexpected-generated.txt'
    for marker in (root,output):
        candidate.write_text(str(marker)+'/private-generated-input')
        with pytest.raises(ValueError,match='Generated bundle contains'):
            desktop.audit_generated_payload(resources,output)
    candidate.write_text('Portable public fixture')
    desktop.audit_generated_payload(resources,output)


def test_standalone_dependency_copy_retains_runtime_trace_module(tmp_path):
    standalone=tmp_path/'standalone';module=standalone/'node_modules/next/dist/trace/shared.js'
    module.parent.mkdir(parents=True);module.write_text('module.exports={runtime:true};\n')
    (standalone/'debug.map').write_text('unneeded source map')
    # This is the exact production copy operation; trace is a required JS
    # dependency directory, not permission to discard matching path names.
    target=tmp_path/'packaged'
    desktop.copy_standalone(standalone,target)
    assert (target/'node_modules/next/dist/trace/shared.js').read_bytes()==module.read_bytes()
    assert not (target/'debug.map').exists()
