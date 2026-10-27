"""Copy reviewed Windows-only notices after verifying exact runtime bytes.

Build-time, offline and fail closed. This does not execute foreign binaries,
accept an upstream agreement or qualify a public Windows distribution.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import shutil

DEFAULT_SOURCE = Path(__file__).resolve().parents[1] / 'apps/desktop/notices/windows-runtime'
_BINARY_PATHS = frozenset({'ffmpeg.dll', 'dxcompiler.dll', 'd3dcompiler_47.dll',
    'resources/python/vcruntime140.dll', 'resources/python/vcruntime140_1.dll'})
_NOTICE_PATHS = frozenset({'LICENSES.chromium.html', 'resources/python/LICENSE.txt'})
_MAX_FILES = 64
_MAX_TOTAL = 2 * 1024 * 1024


def _hash(path):
    h = sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _relative(name):
    if not isinstance(name, str):
        raise ValueError('Invalid Windows-notice path')
    p = PurePosixPath(name)
    if not name or p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name or p.as_posix() != name:
        raise ValueError('Unsafe Windows-notice path')
    return Path(*p.parts)


def _plain(path, root):
    if any(p.is_symlink() for p in (path, *path.parents) if p.is_relative_to(root)):
        raise ValueError('Linked Windows-notice input or payload path')
    if not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError('Missing or escaping Windows-notice input')
    return path


def _binding(root, name, spec, *, maximum):
    if not isinstance(spec, dict) or type(spec.get('bytes')) is not int or not 0 <= spec['bytes'] <= maximum:
        raise ValueError('Invalid bounded Windows-notice binding')
    if not re.fullmatch('[a-f0-9]{64}', spec.get('sha256', '')):
        raise ValueError('Invalid Windows-notice digest')
    path = _plain(root / _relative(name), root)
    if path.stat().st_size != spec['bytes'] or _hash(path) != spec['sha256']:
        raise ValueError('Windows-notice or runtime hash mismatch: ' + name)
    return path


def _reviewed_inputs(source):
    root = Path(source).absolute()
    if root.is_symlink() or root.resolve() != root or not root.is_dir():
        raise ValueError('Windows-notice source must be an ordinary directory')
    if any(p.is_symlink() for p in root.rglob('*')):
        raise ValueError('Linked Windows-notice input')
    manifest = _plain(root / 'MANIFEST.json', root)
    if manifest.stat().st_size > 64 * 1024:
        raise ValueError('Oversized Windows-notice manifest')
    record = json.loads(manifest.read_text())
    expected = record.get('files')
    if record.get('schema') != 'litrev.desktop.windows-notices.manifest.v1' or not isinstance(expected, dict) or not 1 <= len(expected) <= _MAX_FILES:
        raise ValueError('Unknown or unbounded Windows-notice manifest')
    for name, spec in expected.items():
        _binding(root, name, spec, maximum=512 * 1024)
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual != set(expected) | {'MANIFEST.json'} or sum(s['bytes'] for s in expected.values()) > _MAX_TOTAL:
        raise ValueError('Windows-notice closure differs or exceeds bounds')
    provenance = root / 'SOURCE_PROVENANCE.json'
    if 'SOURCE_PROVENANCE.json' not in expected or _hash(provenance) != record.get('source_provenance_sha256'):
        raise ValueError('Windows-notice source identity mismatch')
    facts = json.loads(provenance.read_text())
    if facts.get('schema') != 'litrev.desktop.windows-notices.provenance.v1' or facts.get('target') != 'win32-x64':
        raise ValueError('Unknown Windows-notice source identity')
    if set(facts.get('reviewed_binaries', {})) != _BINARY_PATHS or set(facts.get('required_existing_files', {})) != _NOTICE_PATHS:
        raise ValueError('Unreviewed Windows runtime binding set')
    if facts.get('public_distribution_qualified') is not False or not facts.get('remaining_owner_actions'):
        raise ValueError('Do not infer public Windows qualification from a notice copy')
    return root, record, facts


def copy_windows_dependency_notices(payload_root, source=DEFAULT_SOURCE):
    """Verify the complete reviewed closure, then copy notices, never DLLs.

    The source directory is trusted reviewed build input bound by the clean
    source commit. Custom source is only for isolated fixture tests/reviewed
    recipes; this is not a runtime import or an authorization endpoint.
    """
    source, record, facts = _reviewed_inputs(source)
    root = Path(payload_root).absolute()
    if root.is_symlink() or root.resolve() != root or not root.is_dir():
        raise ValueError('Windows payload must be an ordinary directory')
    resources = root / 'resources'
    if resources.is_symlink() or not resources.is_dir():
        raise ValueError('Windows payload resources must be an ordinary directory')
    # A new CRT/API-set file changes the reviewed distribution and needs an
    # explicit source/notice binding, rather than silently inheriting this one.
    for path in root.rglob('*'):
        if not path.name.lower().endswith('.dll'):
            continue
        name = path.name.lower()
        related = name.startswith(('api-ms-', 'ucrtbase', 'ucrtbased', 'msvcp', 'msvcr', 'concrt', 'vcruntime'))
        if related and path.relative_to(root).as_posix() not in _BINARY_PATHS:
            raise ValueError('Unreviewed Windows runtime family member')
    for name, spec in {**facts['reviewed_binaries'], **facts['required_existing_files']}.items():
        _binding(root, name, spec, maximum=64 * 1024 * 1024)
    destination = resources / 'WINDOWS_DEPENDENCY_NOTICES'
    if destination.exists() or destination.is_symlink():
        raise ValueError('Never overwrite a Windows-notice payload')
    shutil.copytree(source, destination, symlinks=False)
    _reviewed_inputs(destination)
    return {'schema': 'litrev.desktop.windows-notices-copy.v1',
        'directory': 'resources/WINDOWS_DEPENDENCY_NOTICES',
        'manifest_sha256': _hash(destination / 'MANIFEST.json'),
        'source_provenance_sha256': record['source_provenance_sha256'],
        'files': len(record['files']) + 1,
        'bytes': sum(v['bytes'] for v in record['files'].values()),
        'verified_binary_files': len(facts['reviewed_binaries']),
        'verified_existing_notice_files': len(facts['required_existing_files']),
        'external_source_companions': facts.get('ffmpeg', {}).get('required_companions', []),
        'remaining_owner_actions': facts['remaining_owner_actions'],
        'public_distribution_qualified': False,
        'scope': 'Exact offline input/runtime notice-copy verification; no Windows execution, agreement acceptance or legal certification.'}
