"""No Windows execution: bounded notice/runtime identity and copy failures."""
from hashlib import sha256
import json
import shutil
import pytest
from scripts.desktop_windows_notices import (
    DEFAULT_SOURCE, _BINARY_PATHS, _NOTICE_PATHS, _reviewed_inputs,
    copy_windows_dependency_notices,
)


def _write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')


def _fixture(tmp_path):
    source = tmp_path / 'source';source.mkdir()
    root = tmp_path / 'payload';(root / 'resources').mkdir(parents=True)
    facts = {'schema': 'litrev.desktop.windows-notices.provenance.v1', 'target': 'win32-x64',
        'reviewed_binaries': {}, 'required_existing_files': {},
        'public_distribution_qualified': False,
        'remaining_owner_actions': ['SYNTHETIC owner permission not supplied.']}
    for group, names in [('reviewed_binaries', _BINARY_PATHS), ('required_existing_files', _NOTICE_PATHS)]:
        for name in names:
            raw = ('SYNTHETIC inert fixture: ' + name).encode()
            path = root / name;path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(raw)
            facts[group][name] = {'bytes': len(raw), 'sha256': sha256(raw).hexdigest()}
    _write_json(source / 'SOURCE_PROVENANCE.json', facts)
    (source / 'NOTICE.txt').write_text('SYNTHETIC fixture notice only.\n')
    _manifest(source)
    return source, root


def _manifest(source):
    files = {p.name: {'bytes': p.stat().st_size, 'sha256': sha256(p.read_bytes()).hexdigest()}
        for p in source.iterdir() if p.is_file() and p.name != 'MANIFEST.json'}
    _write_json(source / 'MANIFEST.json', {'schema': 'litrev.desktop.windows-notices.manifest.v1',
        'source_provenance_sha256': files['SOURCE_PROVENANCE.json']['sha256'], 'files': files})


def test_real_reviewed_source_closure_and_no_private_machine_paths():
    root, record, facts = _reviewed_inputs(DEFAULT_SOURCE)
    assert len(record['files']) == 14
    assert len(facts['reviewed_binaries']) == 5
    assert facts['dxc']['complete_license_matches_retained_chromium_credit'] is True
    for path in root.rglob('*'):
        if path.is_file():
            assert b'/Users/' not in path.read_bytes()
            assert b'/private/tmp/' not in path.read_bytes()


def test_copy_is_hash_bound_and_does_not_change_runtime_or_claim_permission(tmp_path):
    source, payload = _fixture(tmp_path)
    before = {p.relative_to(payload): p.read_bytes() for p in payload.rglob('*') if p.is_file()}
    receipt = copy_windows_dependency_notices(payload, source)
    assert receipt['verified_binary_files'] == 5
    assert receipt['verified_existing_notice_files'] == 2
    assert receipt['public_distribution_qualified'] is False
    assert receipt['remaining_owner_actions']
    assert str(tmp_path) not in json.dumps(receipt)
    assert all((payload / p).read_bytes() == raw for p, raw in before.items())
    with pytest.raises(ValueError, match='Never overwrite'):
        copy_windows_dependency_notices(payload, source)


@pytest.mark.parametrize('name', sorted(_BINARY_PATHS | _NOTICE_PATHS))
def test_wrong_or_missing_runtime_or_notice_rejected_before_copy(tmp_path, name):
    source, payload = _fixture(tmp_path)
    (payload / name).write_bytes(b'changed')
    with pytest.raises(ValueError, match='hash mismatch'):
        copy_windows_dependency_notices(payload, source)
    assert not (payload / 'resources/WINDOWS_DEPENDENCY_NOTICES').exists()


@pytest.mark.parametrize('mode', ['tamper', 'unlisted', 'link', 'traversal', 'oversize'])
def test_unreviewed_source_closure_fails(tmp_path, mode):
    source, payload = _fixture(tmp_path)
    if mode == 'tamper':
        (source / 'NOTICE.txt').write_text('changed')
    elif mode == 'unlisted':
        (source / 'extra').write_text('not listed')
    elif mode == 'link':
        (source / 'linked').symlink_to(payload, target_is_directory=True)
    else:
        record = json.loads((source / 'MANIFEST.json').read_text())
        if mode == 'traversal':record['files']['../outside'] = record['files']['NOTICE.txt']
        else:record['files']['NOTICE.txt']['bytes'] = 512 * 1024 + 1
        _write_json(source / 'MANIFEST.json', record)
    with pytest.raises(ValueError):copy_windows_dependency_notices(payload, source)
    assert not (payload / 'resources/WINDOWS_DEPENDENCY_NOTICES').exists()


@pytest.mark.parametrize('name', ['api-ms-win-crt-runtime-l1-1-0.dll', 'ucrtbase.dll', 'vcruntime999.dll'])
def test_new_unreviewed_crt_family_fails(tmp_path, name):
    source, payload = _fixture(tmp_path);(payload / name).write_bytes(b'SYNTHETIC')
    with pytest.raises(ValueError, match='Unreviewed Windows runtime family'):
        copy_windows_dependency_notices(payload, source)


def test_payload_symlink_or_escape_is_rejected(tmp_path):
    source, payload = _fixture(tmp_path)
    linked = tmp_path / 'linked';linked.symlink_to(payload, target_is_directory=True)
    with pytest.raises(ValueError, match='ordinary directory'):
        copy_windows_dependency_notices(linked, source)
    binary = payload / 'ffmpeg.dll';raw = binary.read_bytes();binary.unlink()
    foreign = tmp_path / 'outside.dll';foreign.write_bytes(raw);binary.symlink_to(foreign)
    with pytest.raises(ValueError, match='Linked'):
        copy_windows_dependency_notices(payload, source)
