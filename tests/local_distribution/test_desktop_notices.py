"""Notice packaging preserves runtime/source bytes; no network or legal claims."""
from pathlib import Path
from hashlib import sha256
import json

import pytest
from scripts.desktop_notices import copy_web_dependency_notices


def write(path, raw):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(raw if isinstance(raw,bytes) else raw.encode())
    return path


def metadata(name, version='1.0.0', license='MIT', **extra):
    result={'name':name,'license':license,**extra}
    if version is not None:result['version']=version
    return json.dumps(result,sort_keys=True).encode()


def trees(tmp_path):
    standalone=tmp_path/'standalone';installed=tmp_path/'installed/node_modules'
    standalone.mkdir();installed.mkdir(parents=True)
    return standalone,installed,tmp_path/'notices'


def package(standalone,installed,name='fixture-runtime',raw=None):
    raw=raw or metadata(name)
    source=installed/name
    target=standalone/'apps/web/node_modules'/name
    write(source/'package.json',raw);write(target/'package.json',raw)
    return source,target


def test_pnpm_alias_preserves_exact_notice_and_required_runtime_module(tmp_path):
    standalone,installed,target=trees(tmp_path)
    source=installed/'.pnpm/fixture-runtime@1.0.0/node_modules/fixture-runtime'
    raw=metadata('fixture-runtime',homepage='https://example.invalid/runtime')
    write(source/'package.json',raw)
    (installed/'fixture-runtime').symlink_to('.pnpm/fixture-runtime@1.0.0/node_modules/fixture-runtime',target_is_directory=True)
    bundled=standalone/'apps/web/node_modules/fixture-runtime'
    write(bundled/'package.json',raw)
    module=write(bundled/'dist/trace/required.cjs','module.exports = 42;\n')
    license=write(source/'LICENSE','SYNTHETIC UPSTREAM MIT COPYRIGHT AND PERMISSION\n')
    module_before=module.read_bytes();source_before=license.read_bytes()
    result=copy_web_dependency_notices(standalone,installed,target)
    assert module.read_bytes()==module_before and license.read_bytes()==source_before
    assert result['missing_notice_sources']==[]
    item=result['packages'][0]
    assert item['name']=='fixture-runtime' and item['upstream_homepage']=='https://example.invalid/runtime'
    notice=item['notice_files'][0]
    assert (target/notice['file']).read_bytes()==source_before
    assert notice['sha256']==sha256(source_before).hexdigest()
    assert notice['installed_relative_path'].startswith('.pnpm/')
    assert not any(path.suffix in {'.js','.cjs'} for path in target.rglob('*'))


def test_vendored_compiled_notices_native_links_and_unknown_versions_retained(tmp_path):
    standalone,installed,target=trees(tmp_path)
    outer,bundled=package(standalone,installed,'next',metadata('next','16.4.2'))
    write(outer/'LICENSE','SYNTHETIC Next permission\n')
    nested=metadata('vendored-compiler',None,license='BSD-3-Clause')
    write(outer/'dist/compiled/compiler/package.json',nested)
    write(bundled/'dist/compiled/compiler/package.json',nested)
    write(outer/'dist/compiled/compiler/LICENSE.txt','SYNTHETIC compiler copyright\n')
    native,native_bundle=package(standalone,installed,'@img/sharp-libvips-darwin-arm64',
        metadata('@img/sharp-libvips-darwin-arm64','1.0.0','LGPL-3.0-or-later',
            repository={'url':'https://example.invalid/exact-native-source','type':'git'}))
    write(native/'COPYING.LESSER','SYNTHETIC native-library terms and source offer\n')
    write(native/'versions.json',json.dumps({'vips':'SYNTHETIC-1'}))
    result=copy_web_dependency_notices(standalone,installed,target)
    compiler=next(item for item in result['packages'] if item['name']=='vendored-compiler')
    assert compiler['version'] is None and compiler['notice_files']
    included=next(item for item in result['packages'] if item['name']=='@img/sharp-libvips-darwin-arm64')
    assert included['declared_license']=='LGPL-3.0-or-later'
    assert included['upstream_repository']['url']=='https://example.invalid/exact-native-source'
    assert included['native_component_versions']=={'vips':'SYNTHETIC-1'}
    assert any(entry['package_relative_path']=='COPYING.LESSER' for entry in included['notice_files'])
    assert result['unique_notice_files']==3  # Vendored compiler notice deduplicated across parent/child inventories.
    assert 'No relicensing or legal clearance' in result['legal_status']


def test_missing_notice_and_missing_locked_source_are_explicit(tmp_path):
    standalone,installed,target=trees(tmp_path)
    package(standalone,installed,'no-notice')
    write(standalone/'apps/web/node_modules/no-installed-source/package.json',metadata('no-installed-source'))
    result=copy_web_dependency_notices(standalone,installed,target)
    assert {entry['reason'] for entry in result['missing_notice_sources']}=={'missing_notice_file','missing_locked_source'}
    assert result['unique_notice_files']==0
    assert (target/'INVENTORY.json').is_file()


def test_mismatched_version_refuses_to_copy_another_versions_terms(tmp_path):
    standalone,installed,target=trees(tmp_path)
    source,bundled=package(standalone,installed)
    write(source/'package.json',metadata('fixture-runtime','2.0.0'))
    write(source/'LICENSE','Wrong version terms')
    with pytest.raises(ValueError,match='identity/version'):
        copy_web_dependency_notices(standalone,installed,target)
    assert not target.exists()


def test_same_version_modified_metadata_is_not_silently_accepted(tmp_path):
    standalone,installed,target=trees(tmp_path)
    source,bundled=package(standalone,installed)
    write(source/'package.json',metadata('fixture-runtime',license='Apache-2.0'))
    with pytest.raises(ValueError,match='metadata bytes'):
        copy_web_dependency_notices(standalone,installed,target)
    assert not target.exists()


def test_package_and_notice_symlinks_cannot_read_outside_installed_inputs(tmp_path):
    standalone,installed,target=trees(tmp_path)
    source,bundled=package(standalone,installed)
    outside=write(tmp_path/'outside-private.txt','SYNTHETIC secret outside approved input')
    (source/'LICENSE').symlink_to(outside)
    with pytest.raises(ValueError,match='escapes'):
        copy_web_dependency_notices(standalone,installed,target)
    assert not target.exists()
    (source/'LICENSE').unlink()
    (source/'package.json').unlink()
    (source/'package.json').symlink_to(outside)
    with pytest.raises(ValueError,match='escapes'):
        copy_web_dependency_notices(standalone,installed,target)
    assert not target.exists()


def test_output_never_overwrites_or_writes_inside_build_inputs(tmp_path):
    standalone,installed,target=trees(tmp_path)
    package(standalone,installed)
    target.mkdir();write(target/'keep','existing notices')
    with pytest.raises(ValueError,match='fresh'):
        copy_web_dependency_notices(standalone,installed,target)
    assert (target/'keep').read_text()=='existing notices'
    with pytest.raises(ValueError,match='outside'):
        copy_web_dependency_notices(standalone,installed,installed/'new-output')


def test_notice_symlink_inside_pnpm_input_is_copied_not_followed_in_output(tmp_path):
    standalone,installed,target=trees(tmp_path)
    source,bundled=package(standalone,installed)
    shared=write(installed/'shared-license.txt','SYNTHETIC shared permission\n')
    (source/'LICENSE').symlink_to('../shared-license.txt')
    result=copy_web_dependency_notices(standalone,installed,target)
    notice=target/result['packages'][0]['notice_files'][0]['file']
    assert notice.is_file() and not notice.is_symlink() and notice.read_bytes()==shared.read_bytes()


def test_notice_code_named_files_are_not_copied_and_inventory_is_reproducible(tmp_path):
    standalone,installed,target=trees(tmp_path)
    source,bundled=package(standalone,installed)
    write(source/'LICENSE','SYNTHETIC permission\n')
    write(source/'dist/notice-tracker.js','SYNTHETIC runtime implementation, not a license')
    first=copy_web_dependency_notices(standalone,installed,target)
    second=copy_web_dependency_notices(standalone,installed,tmp_path/'second')
    assert first==second and first['unique_notice_files']==1
    assert (target/'INVENTORY.json').read_bytes()==(tmp_path/'second/INVENTORY.json').read_bytes()


def test_native_readme_license_source_links_are_preserved_without_claiming_full_terms(tmp_path):
    standalone,installed,target=trees(tmp_path)
    source,bundled=package(standalone,installed,'@img/sharp-libvips-darwin-arm64',
        metadata('@img/sharp-libvips-darwin-arm64','1.3.4','LGPL-3.0-or-later'))
    raw='## Licensing\nExact upstream library terms/source links: https://example.invalid/libvips/source\n'
    write(source/'README.md',raw)
    result=copy_web_dependency_notices(standalone,installed,target)
    entry=result['packages'][0]
    assert entry['notice_status']=='upstream_declarations_only_full_notice_missing'
    assert result['missing_notice_sources'][0]['reason']==entry['notice_status']
    assert entry['notice_files'][0]['kind']=='upstream_readme_license_declarations_and_links'
    assert (target/entry['notice_files'][0]['file']).read_text()==raw
