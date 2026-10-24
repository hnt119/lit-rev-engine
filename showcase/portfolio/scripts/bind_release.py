#!/usr/bin/env python3
"""Bind verified local release files to a separate, unpublished portfolio overlay.

No website checkout is modified, no URL is invented, and nothing is uploaded.
Generated metadata and ZIP bytes are outputs, never inputs to their source commit.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import runpy
import stat
import zipfile


OVERLAY = Path(__file__).resolve().parents[1]
ENGINE_ROOT = OVERLAY.parents[1]
LICENSE_POLICY = runpy.run_path(str(ENGINE_ROOT / 'scripts/license_policy.py'))
MIT_LICENSE_TEXT = LICENSE_POLICY['MIT_LICENSE_TEXT']
MIT_LICENSE_SHA256 = LICENSE_POLICY['MIT_LICENSE_SHA256']
VERSION = '0.3.0-beta.1'
NAME = 'lit-rev-engine-' + VERSION
SOURCE_FILES = (
    'README.md', 'src/components/LiteratureShowcase.tsx',
    'src/components/LiteratureShowcase.module.css',
    'src/content/projects/literature-review-engine.mdx',
    'src/data/literature-showcase.json', 'src/data/local-preview-download.json',
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode()


def ordinary(path, limit):
    path = Path(path)
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError('Use ordinary local artifact files without symlink paths.')
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError('The local artifact is missing or exceeds its bound: ' + path.name)
    return path.read_bytes()


def validate_release(archive, manifest_path, checksums_path, source_commit):
    if not re.fullmatch('[a-f0-9]{40}', source_commit):
        raise ValueError('Supply the exact full lowercase source commit SHA.')
    archive, manifest_path, checksums_path = map(Path, (archive, manifest_path, checksums_path))
    if (archive.name, manifest_path.name, checksums_path.name) != (
            NAME + '.zip', NAME + '.manifest.json', NAME + '.SHA256SUMS'):
        raise ValueError('Use the purpose-built versioned ZIP, manifest and checksum filenames.')
    raw = ordinary(archive, 30 * 1024 * 1024)
    manifest_raw = ordinary(manifest_path, 1024 * 1024)
    checksums_raw = ordinary(checksums_path, 4096)
    expected = ''.join(sha(value) + '  ' + name + '\n' for name, value in
        ((archive.name, raw), (manifest_path.name, manifest_raw))).encode()
    if checksums_raw != expected:
        raise ValueError('The supplied checksum file does not exactly match both artifacts.')
    payload = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
        entries = bundle.infolist()
        if not 1 <= len(entries) <= 500:
            raise ValueError('Unexpected archive entry count.')
        total = 0
        for entry in entries:
            if not entry.filename.startswith(NAME + '/'):
                raise ValueError('Unexpected archive root.')
            relative = entry.filename[len(NAME) + 1:]
            path = PurePosixPath(relative)
            total += entry.file_size
            if (not relative or entry.is_dir() or path.is_absolute() or '..' in path.parts
                    or '\\' in relative or relative in payload
                    or stat.S_IFMT(entry.external_attr >> 16) != stat.S_IFREG
                    or entry.file_size > 20 * 1024 * 1024 or total > 100 * 1024 * 1024):
                raise ValueError('Unsafe or oversized archive contents.')
            payload[relative] = bundle.read(entry)
    if payload.get('MANIFEST.json') != manifest_raw:
        raise ValueError('The manifest sidecar differs from the archive manifest.')
    manifest = json.loads(manifest_raw)
    if (manifest.get('schema') != 'litrev.local-preview.manifest.v1'
            or manifest.get('version') != VERSION
            or not isinstance(manifest.get('files'), dict)
            or set(manifest['files']) != set(payload) - {'MANIFEST.json'}):
        raise ValueError('The manifest does not enumerate this exact release payload.')
    for name, record in manifest['files'].items():
        if record != {'bytes': len(payload[name]), 'sha256': sha(payload[name])}:
            raise ValueError('Packaged file mismatch: ' + name)
    if {'src/review/pilot.py', 'src/web_api/pilot_routes.py',
            'apps/web/components/review-pilot.tsx'} & set(payload):
        raise ValueError('The Track B researcher pilot is not part of this Track A beta download.')
    release = json.loads(payload.get('RELEASE.json', b'null'))
    if (not isinstance(release, dict) or release.get('schema') != 'litrev.local-preview.release.v1'
            or release.get('version') != VERSION or release.get('source_commit') != source_commit
            or release.get('source_state') != 'clean committed checkout'
            or release.get('runtimes_bundled') is not False or release.get('models_bundled') is not False):
        raise ValueError('Bind only the exact clean-commit, source-only local beta release.')
    if (release.get('spdx_license') != 'MIT'
            or release.get('license_sha256') != MIT_LICENSE_SHA256
            or payload.get('LICENSE') != MIT_LICENSE_TEXT.encode('utf-8')
            or not payload.get('README.md')
            or not payload.get('DISTRIBUTION_TERMS.md')
            or not payload.get('THIRD_PARTY_NOTICES.md')):
        raise ValueError('Bind only the approved standard MIT beta with its separate distribution notices.')
    # The code grant does not relicense the public articles or their attribution.
    if (not payload.get('examples/mvp/offline_microbiome_30_v1/README.md')
            or not payload.get('examples/mvp/offline_microbiome_30_v1/manifest.json')):
        raise ValueError('The beta must retain its public-source attribution and license manifest.')
    snapshot = {name: sha(value) for name, value in payload.items()
                if name not in {'RELEASE.json', 'MANIFEST.json'}}
    if release.get('source_snapshot_sha256') != sha(encoded(snapshot)):
        raise ValueError('The release source snapshot digest is inconsistent.')
    metadata = {
        'schema': 'litrev.portfolio.local-preview-download.v1', 'version': VERSION,
        'available': True, 'source_commit': source_commit,
        'archive_path': '/downloads/' + archive.name,
        'manifest_path': '/downloads/' + manifest_path.name,
        'checksums_path': '/downloads/' + checksums_path.name,
        'archive_sha256': sha(raw), 'archive_bytes': len(raw),
        'spdx_license': 'MIT',
        'license_path': '/downloads/' + NAME + '.LICENSE.txt',
        'installation_path': '/downloads/' + NAME + '.INSTALL.md',
        'license_sha256': sha(payload['LICENSE']),
        'installation_sha256': sha(payload['README.md']),
    }
    return metadata, {archive.name: raw, manifest_path.name: manifest_raw,
                      checksums_path.name: checksums_raw,
                      NAME + '.LICENSE.txt': payload['LICENSE'],
                      NAME + '.INSTALL.md': payload['README.md']}


def bind(archive, manifest_path, checksums_path, source_commit, output):
    metadata, assets = validate_release(archive, manifest_path, checksums_path, source_commit)
    output = Path(output).expanduser().absolute()
    if output.exists() or any(item.is_symlink() for item in (output, *output.parents)):
        raise ValueError('Choose a new ordinary output directory outside all Git checkouts.')
    if not output.parent.is_dir() or any((parent / '.git').exists() for parent in output.parents):
        raise ValueError('The output parent must exist outside every Git checkout.')
    source = {name: ordinary(OVERLAY / name, 1024 * 1024) for name in SOURCE_FILES}
    if json.loads(source['src/data/local-preview-download.json']).get('available') is not False:
        raise ValueError('The committed overlay must retain its unbound metadata template.')
    output.mkdir(mode=0o700)
    for name, data in source.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (output / 'src/data/local-preview-download.json').write_bytes(encoded(metadata))
    downloads = output / 'public/downloads'
    downloads.mkdir(parents=True)
    for name, raw in assets.items():
        (downloads / name).write_bytes(raw)
    receipt = {'schema': 'litrev.portfolio.release-binding.v1', 'status': 'PREPARED_LOCAL_ONLY',
        'source_commit': source_commit, 'archive_sha256': metadata['archive_sha256'],
        'version': VERSION, 'spdx_license': 'MIT',
        'license_sha256': metadata['license_sha256'],
        'installation_sha256': metadata['installation_sha256'],
        'files': [*SOURCE_FILES, *['public/downloads/' + name for name in assets]],
        'published': False,
        'distribution_approval': 'Owner selected MIT; separate release-upload and portfolio publication approval still required.'}
    (output / 'RELEASE_BINDING.json').write_bytes(encoded(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--checksums', required=True, type=Path)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--output', required=True, type=Path,
                        help='New separate overlay output, outside Git checkouts; never the actual website')
    args = parser.parse_args()
    try:
        result = bind(args.archive, args.manifest, args.checksums, args.source_commit, args.output)
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile) as error:
        parser.exit(2, 'Release binding refused: ' + str(error) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
