"""Offline primary-source attribution, ownership and no-false-version checks."""
import base64
from hashlib import sha256
import json
from pathlib import Path
import shutil
import struct
import pytest
from scripts.desktop_native_inventory import (DEFAULT_SOURCE_EVIDENCE,collect_native_payload,copy_native_source_evidence)


def test_exact_notice_closure_copies_and_tampering_or_added_links_fail(tmp_path):
    destination=tmp_path/'notices';receipt=copy_native_source_evidence(destination)
    assert receipt['files']==198 and receipt['manifest_sha256']==sha256((destination/'MANIFEST.json').read_bytes()).hexdigest()
    source=tmp_path/'source';shutil.copytree(DEFAULT_SOURCE_EVIDENCE,source)
    path=source/'pydantic-core-2.46.4/LICENSE';path.write_bytes(b'tampered')
    with pytest.raises(ValueError,match='hash mismatch'):copy_native_source_evidence(tmp_path/'bad',source)
    shutil.rmtree(source);shutil.copytree(DEFAULT_SOURCE_EVIDENCE,source);(source/'unlisted').write_text('not approved')
    with pytest.raises(ValueError,match='closure'):copy_native_source_evidence(tmp_path/'bad-extra',source)
    (source/'unlisted').unlink();(source/'unlisted-link').symlink_to(tmp_path,target_is_directory=True)
    with pytest.raises(ValueError,match='Linked'):copy_native_source_evidence(tmp_path/'bad-link',source)


def test_parent_source_version_hints_do_not_fabricate_exact_bundled_versions(tmp_path):
    path=tmp_path/'node_modules/next/dist/compiled/busboy';path.mkdir(parents=True);(path/'package.json').write_text(json.dumps({'name':'busboy','license':'MIT'}));(path/'LICENSE').write_text('SYNTHETIC notice')
    bom,review=collect_native_payload(tmp_path,'a'*40,'darwin-arm64',source_evidence=DEFAULT_SOURCE_EVIDENCE)
    assert review['version_source_evidence']['state']=='external_audit_evidence_not_bundled'
    hint=review['version_source_evidence']['compiled_module_source_hints'][0];assert hint['source_declared_dependency']=='1.6.0'
    assert 'version' not in bom['components'][0] and review['unknown_version_components']
    copy_native_source_evidence(tmp_path/'NATIVE_DEPENDENCY_NOTICES')
    _,review=collect_native_payload(tmp_path,'a'*40,'darwin-arm64')
    assert review['version_source_evidence']['state']=='bundled_verified'
    assert review['public_distribution_qualified'] is False


def test_native_record_ownership_retains_actual_and_original_hashes_and_never_reads_outside(tmp_path):
    root=tmp_path/'payload';site=root/'python/lib/site-packages';binary=site/'win32/win32api.pyd';binary.parent.mkdir(parents=True)
    raw=b'MZ'+b'\0'*58+struct.pack('<I',64)+b'PE\0\0SYNTHETIC';binary.write_bytes(raw)
    dist=site/'pywin32-312.dist-info';dist.mkdir();(dist/'METADATA').write_text('Name: pywin32\nVersion: 312\nLicense: PSF\n');(dist/'LICENSE').write_text('SYNTHETIC notice')
    expected=base64.urlsafe_b64encode(sha256(raw).digest()).decode().rstrip('=')
    (dist/'RECORD').write_text('win32/win32api.pyd,sha256='+expected+','+str(len(raw))+'\n../../../../secret.dll,,\n')
    (tmp_path/'secret.dll').write_bytes(b'PRIVATE never include')
    _,review=collect_native_payload(root,'a'*40,'win32-x64');owner=review['native_wheel_ownership'][0]
    assert owner['name']=='pywin32' and owner['native_files'][0]['payload_matches_record'] is True
    assert review['wheel_record_entries_outside_payload']==1 and 'PRIVATE never include' not in json.dumps(review)
    binary.write_bytes(raw+b'signed-or-changed')
    _,review=collect_native_payload(root,'a'*40,'win32-x64')
    assert review['native_wheel_ownership'][0]['native_files'][0]['payload_matches_record'] is False
