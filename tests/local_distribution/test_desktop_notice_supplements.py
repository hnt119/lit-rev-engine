"""Offline binding checks; synthetic code is not a rebuilt/qualified desktop."""
from copy import deepcopy
from hashlib import sha1, sha256
import json
from pathlib import Path
import shutil
import socket

import pytest
from scripts import desktop_notices as notices
from test_desktop_notices import trees, package, write, metadata


def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **kw: pytest.fail('Collector must remain offline'))
    standalone, installed, target = trees(tmp_path)
    supplements = tmp_path / 'supplements'
    shutil.copytree(notices.SUPPLEMENTS, supplements)
    manifest = json.loads((supplements / 'web-supplements.json').read_text())
    dependencies = {item['name']: item['reviewed_version'] for item in manifest['packages']}
    parent_raw = metadata('next', '16.4.2', dependencies={'@next/env': '16.4.2'})
    parent_source, parent_bundle = package(standalone, installed, 'next', parent_raw)
    write(parent_source / 'LICENSE', 'SYNTHETIC parent permission\n')
    context_raw = metadata('next', '16.4.2', dependencies=dependencies, devDependencies=dependencies, fixture='SYNTHETIC SOURCE CONTEXT')
    context_path = supplements / 'next-16.4.2-upstream-package.json'; context_path.write_bytes(context_raw)
    sources, bundles = {}, {}
    for item in manifest['packages']:
        relative = item['parent']['relative_package_json']
        if relative:
            source, bundled = parent_source / relative, parent_bundle / relative
        else:
            source, bundled = installed / item['name'] / 'package.json', standalone / 'apps/web/node_modules' / item['name'] / 'package.json'
        raw = metadata(item['name'], item['package_version'], 'CC0-1.0' if item['name'] == 'string-hash' else 'MIT')
        write(source, raw); write(bundled, raw)
        runtime = {'dist/index.js': b'SYNTHETIC env runtime\n'} if item['name'] == '@next/env' else {'index.js': b'SYNTHETIC compiled runtime\n'}
        if item['name'] == '@edge-runtime/primitives':runtime['unused.js'] = b'SYNTHETIC omitted runtime\n'
        for path, content in runtime.items():write(source.parent / path, content); write(bundled.parent / path, content)
        item['package_json_sha256'] = sha256(raw).hexdigest()
        item['runtime_files'] = {path: sha256(raw).hexdigest() for path, raw in runtime.items()}
        item['parent']['package_json_sha256'] = sha256(parent_raw).hexdigest()
        item['parent']['dependency_manifest'].update(sha256=sha256(context_raw).hexdigest(), upstream_blob_sha1=sha1(b'blob ' + str(len(context_raw)).encode() + b'\0' + context_raw).hexdigest())
        sources[item['name']], bundles[item['name']] = source, bundled
    for name in ('client-only', '@img/sharp-libvips-darwin-arm64', 'unknown-no-notice'):
        package(standalone, installed, name)
    def save(): (supplements / 'web-supplements.json').write_text(json.dumps(manifest))
    save()
    return standalone, installed, target, supplements, manifest, sources, bundles, parent_source, parent_bundle, save


def collect(case):return notices.copy_web_dependency_notices(case[0], case[1], case[2], supplemental_root=case[3])


def test_five_exact_inputs_preserve_text_provenance_and_keep_other_gaps_blocked(tmp_path, monkeypatch):
    c=fixture(tmp_path, monkeypatch);before={p:p.read_bytes() for directory in (c[0],c[1]) for p in directory.rglob('*') if p.is_file()}
    value=collect(c)
    assert len([x for x in value['packages'] if 'supplement_binding' in x])==5
    for item in value['packages']:
        for notice in item['notice_files']:
            if 'supplement_relative_path' in notice:
                assert (c[2]/notice['file']).read_bytes()==(c[3]/notice['supplement_relative_path']).read_bytes()
                assert 'installed_relative_path' not in notice and notice['source_url'].startswith('https://')
    string=next(x for x in value['packages'] if x['name']=='string-hash')
    assert {x['kind'] for x in string['notice_files']}=={'upstream_dedication','standard_license_definition'}
    assert string['version'] is None and string['supplement_binding']['reviewed_version']=='1.1.3'
    assert len(value['missing_notice_sources'])==3
    assert {x['name'] for x in value['unresolved_distribution_reviews']}=={'client-only','@img/sharp-libvips-darwin-arm64'}
    assert value['public_distribution_gates']=={'qualified':False,'complete_transitive_sbom':'pending','native_source_obligations':'pending','trusted_signing_notarization':'pending','external_optional_ml_runtime':'not_implemented'}
    assert all(p.read_bytes()==raw for p,raw in before.items())
    second=notices.copy_web_dependency_notices(c[0],c[1],tmp_path/'second',supplemental_root=c[3])
    assert second==value


@pytest.mark.parametrize('change',['parent_version','parent_hash','compiled_source','compiled_bundle','env_version','env_source','extra_source','extra_bundle','dependency_source','dependency_provenance','notice_hash','notice_source_identity','notice_source_url','published_artifact_identity','standard_definition_source'])
def test_wrong_parent_version_hash_payload_or_source_fails_before_output(tmp_path,monkeypatch,change):
    c=fixture(tmp_path,monkeypatch);manifest=c[4];item=manifest['packages'][0]
    if change=='parent_version':
        raw=metadata('next','16.4.3',dependencies={'@next/env':'16.4.2'})
        write(c[7]/'package.json',raw);write(c[8]/'package.json',raw)
        for row in manifest['packages']:row['parent']['package_json_sha256']=sha256(raw).hexdigest()
    elif change=='parent_hash':write(c[7]/'package.json',(c[7]/'package.json').read_bytes()+b'\n')
    elif change in {'compiled_source','compiled_bundle'}:
        table=c[5] if change.endswith('source') else c[6];write(table['@edge-runtime/cookies'].parent/'index.js','SYNTHETIC changed code')
    elif change=='env_version':
        row=next(x for x in manifest['packages'] if x['name']=='@next/env');raw=metadata('@next/env','16.4.3');write(c[5]['@next/env'],raw);write(c[6]['@next/env'],raw);row['package_json_sha256']=sha256(raw).hexdigest()
    elif change=='env_source':write(c[5]['@next/env'].parent/'dist/index.js','SYNTHETIC wrong env code')
    elif change in {'extra_source','extra_bundle'}:write((c[5] if change=='extra_source' else c[6])['@edge-runtime/cookies'].parent/'unexpected.js','SYNTHETIC extra code')
    elif change=='dependency_source':(c[3]/'next-16.4.2-upstream-package.json').write_bytes(b'{}')
    elif change=='dependency_provenance':item['parent']['dependency_manifest']['source_url']='https://github.com/unrelated/other/blob/main/package.json'
    elif change=='notice_hash':(c[3]/item['notices'][0]['file']).write_bytes(b'SYNTHETIC changed permission')
    elif change=='notice_source_identity':item['notices'][0]['provenance']['package']='another-package'
    elif change=='notice_source_url':item['notices'][0]['source_url']=item['notices'][0]['source_url'].replace('@6.0.0/','@5.0.0/')
    elif change=='published_artifact_identity':item['notices'][0]['provenance']['tarball_url']='https://registry.npmjs.org/another-package/-/another-package-6.0.0.tgz'
    else:
        row=next(x for x in manifest['packages'] if x['name']=='string-hash');row['notices'][1]['source_url']='https://github.com/vercel/next.js/blob/v16.4.2/license.md'
    c[9]()
    with pytest.raises(ValueError):collect(c)
    assert not c[2].exists()


def test_reduced_trace_subset_is_explicit_and_every_retained_payload_is_bound(tmp_path,monkeypatch):
    c=fixture(tmp_path,monkeypatch);(c[6]['@edge-runtime/primitives'].parent/'unused.js').unlink()
    item=next(x for x in collect(c)['packages'] if x['name']=='@edge-runtime/primitives')
    assert item['supplement_binding']['untraced_reviewed_runtime_files']==['unused.js']
    assert set(item['supplement_binding']['bundled_runtime_files'])=={'index.js'}


@pytest.mark.parametrize('path',['../outside','/private/outside','C:\\outside','folder\\outside','a/../../outside','notice:stream'])
def test_supplement_notice_paths_cannot_escape(tmp_path,monkeypatch,path):
    c=fixture(tmp_path,monkeypatch);c[4]['packages'][0]['notices'][0]['file']=path;c[9]()
    with pytest.raises(ValueError,match='relative POSIX'):collect(c)
    assert not c[2].exists()


@pytest.mark.parametrize('change',['missing_dedication','duplicate_binding','unknown_binding','symlink_notice','oversize_file','total_size'])
def test_missing_or_ambiguous_notice_sets_and_bounds_never_publish(tmp_path,monkeypatch,change):
    c=fixture(tmp_path,monkeypatch);manifest=c[4]
    if change=='missing_dedication':
        row=next(x for x in manifest['packages'] if x['name']=='string-hash');row['notices']=[n for n in row['notices'] if n['kind']!='upstream_dedication']
    elif change=='duplicate_binding':manifest['packages'].append(deepcopy(manifest['packages'][0]))
    elif change=='unknown_binding':manifest['packages'][0]['name']='client-only'
    elif change=='symlink_notice':
        path=c[3]/manifest['packages'][0]['notices'][0]['file'];path.unlink();outside=write(tmp_path/'outside.txt','SYNTHETIC forbidden input');path.symlink_to(outside)
    elif change=='oversize_file':monkeypatch.setattr(notices,'MAX_NOTICE_BYTES',128)
    else:monkeypatch.setattr(notices,'MAX_TOTAL_BYTES',128)
    c[9]()
    with pytest.raises(ValueError):collect(c)
    assert not c[2].exists()


def test_a_generic_notice_never_qualifies_native_source_or_client_attribution(tmp_path,monkeypatch):
    c=fixture(tmp_path,monkeypatch)
    for name in ('client-only','@img/sharp-libvips-darwin-arm64'):write(c[1]/name/'LICENSE','SYNTHETIC generic notice is not source clearance')
    value=collect(c)
    assert all(x['status']=='blocked' for x in value['unresolved_distribution_reviews'])
    assert value['public_distribution_gates']['qualified'] is False
