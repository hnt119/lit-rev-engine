#!/usr/bin/env python3
"""Independent, read-only audit of a prepared local-preview source archive.

Does not extract, install, run, publish or contact any external service.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import zipfile

VERSION = '0.3.0-local-preview.2'
PREFIX = 'lit-rev-engine-' + VERSION + '/'
TREES = ('src/mvp/', 'src/review/', 'src/web_api/', 'apps/web/app/', 'apps/web/components/',
         'apps/web/lib/', 'examples/mvp/offline_microbiome_30_v1/')
EXACT = {'README.md', 'DISTRIBUTION_TERMS.md', 'RELEASE.json', 'MANIFEST.json', 'requirements-hosted.txt', 'requirements-web-lock.txt',
         'scripts/run_web.py', 'scripts/local_preview.py', 'apps/web/package.json', 'apps/web/pnpm-lock.yaml',
         'apps/web/tsconfig.json', 'apps/web/next-env.d.ts', 'apps/web/next.config.ts', 'apps/streamlit/theme/tokens.css'}
BANNED = {'node_modules', '__pycache__', '.next', '.git', '.cache', 'tests', 'reports', 'evaluations',
          'workflow', 'data', '.mvp-web-state', '.mvp-state', 'browser-state', 'backups', 'private-exports',
          'model-cache', '.venv', '.venv-map', '.venv-preview', '.local-preview-setup.json'}
BAD_SUFFIXES = ('.sqlite', '.sqlite3', '.sqlite3-wal', '.sqlite3-shm', '.db', '.db-wal', '.db-shm',
                '.pem', '.key', '.crt', '.cer', '.p12', '.pfx', '.pyc', '.safetensors', '.gguf', '.pt', '.pth',
                '.tsbuildinfo', '.map', '.log', '.xlsx', '.zip', '.tar', '.tar.gz', '.bak')
PRIVATE = [rb'-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----',
           rb'(?:gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{24,}|AKIA[A-Z0-9]{16})',
           rb'/Users/[A-Za-z][A-Za-z0-9._-]+/',
           rb'/home/[A-Za-z][A-Za-z0-9._-]+/', rb'[A-Za-z]:\\{1,2}Users\\{1,2}[A-Za-z][A-Za-z0-9._-]+\\{1,2}']
LICENSE_NAME = re.compile(r'(?:LICEN[CS]E|COPYING|COPYRIGHT|NOTICE)(?:\.(?:md|txt|rst))?', re.I)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def audit(archive, expected_source_commit, source_checkout):
    assert re.fullmatch('[0-9a-f]{40}', expected_source_commit), 'Use the exact full source commit SHA'
    source_checkout = Path(source_checkout).resolve()
    def git(*arguments):
        return subprocess.check_output(['git', *arguments], cwd=source_checkout)
    assert git('rev-parse', 'HEAD').decode().strip() == expected_source_commit, 'Source checkout HEAD mismatch'
    assert not git('status', '--porcelain=v1', '--untracked-files=all'), 'Audit against a clean source checkout'
    tracked = set(git('ls-files', '-z').decode().split('\0')) - {''}
    licenses = {name for name in tracked if '/' not in name and LICENSE_NAME.fullmatch(name)}
    expected_names = {name for name in tracked if name in EXACT or name.startswith(TREES)} | EXACT | licenses
    # README is the dedicated installation guide in this purpose-built archive.
    translations = {'README.md': 'docs/local_preview.md', 'DISTRIBUTION_TERMS.md': 'docs/local_preview_distribution_terms.md'}
    archive = Path(archive)
    assert archive.suffix == '.zip' and archive.is_file() and not archive.is_symlink()
    names, payload = set(), {}
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.infolist():
            assert entry.filename.startswith(PREFIX), 'Archive has unexpected root'
            relative = entry.filename[len(PREFIX):]
            path = PurePosixPath(relative)
            assert relative and not entry.is_dir() and not path.is_absolute() and '..' not in path.parts
            assert '\\' not in relative and relative not in names, 'Unsafe or duplicate archive member'
            assert stat.S_IFMT(entry.external_attr >> 16) == stat.S_IFREG, 'Only ordinary files may be distributed'
            assert not (set(path.parts) & BANNED)
            assert not any(part.startswith('.env') for part in path.parts)
            assert not relative.lower().endswith(BAD_SUFFIXES)
            assert relative in EXACT or relative in licenses or relative.startswith(TREES), 'Unexpected source payload: ' + relative
            assert entry.file_size <= 20 * 1024 * 1024
            raw = bundle.read(entry)
            assert not any(re.search(pattern, raw) for pattern in PRIVATE), 'Possible private data in ' + relative
            names.add(relative); payload[relative] = raw
    assert sum(map(len, payload.values())) <= 100 * 1024 * 1024
    assert EXACT <= names, 'Required source entry missing'
    assert names == expected_names, 'Archive file list differs from the committed release allowlist'
    manifest_raw = payload['MANIFEST.json']; manifest = json.loads(manifest_raw)
    assert manifest['schema'] == 'litrev.local-preview.manifest.v1' and manifest['version'] == VERSION
    assert set(manifest['files']) == names - {'MANIFEST.json'}
    for name, record in manifest['files'].items():
        assert set(record) == {'bytes', 'sha256'}
        assert record == {'bytes': len(payload[name]), 'sha256': sha(payload[name])}, 'Manifest mismatch: ' + name
    release = json.loads(payload['RELEASE.json'])
    assert release['schema'] == 'litrev.local-preview.release.v1' and release['version'] == VERSION
    assert release['source_commit'] == expected_source_commit and release['source_state'] == 'clean committed checkout'
    assert release['label'] == 'Local preview — setup required'
    assert release['runtimes_bundled'] is False and release['models_bundled'] is False
    assert release['root_notice_files'] == sorted(licenses)
    assert release['code_license_present'] == any(re.fullmatch(r'(?:LICEN[CS]E|COPYING)(?:\.(?:md|txt|rst))?', name, re.I) for name in licenses)
    for name, raw in payload.items():
        if name in {'RELEASE.json', 'MANIFEST.json'}:
            continue
        original = translations.get(name, name)
        assert original in tracked, 'Archive input was never committed: ' + original
        assert git('show', expected_source_commit + ':' + original) == raw, 'Archive input differs from committed source: ' + name
    snapshot = {name: sha(raw) for name, raw in payload.items() if name not in {'RELEASE.json', 'MANIFEST.json'}}
    canonical = (json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode()
    assert release['source_snapshot_sha256'] == sha(canonical)
    sibling_manifest = archive.with_suffix('.manifest.json')
    assert sibling_manifest.read_bytes() == manifest_raw
    sums = archive.with_suffix('.SHA256SUMS')
    lines = sums.read_text().splitlines()
    assert lines == [sha(archive.read_bytes()) + '  ' + archive.name,
                     sha(manifest_raw) + '  ' + sibling_manifest.name]
    # Known public fixture only: every retained blob is identified by its own manifest.
    fixture_root = 'examples/mvp/offline_microbiome_30_v1/'
    fixture = json.loads(payload[fixture_root + 'manifest.json'])
    expected_fixture = {fixture_root+'manifest.json', fixture_root+'README.md'}
    for source in fixture['sources']:
        assert source['license'] in {'https://creativecommons.org/licenses/by/4.0/', 'http://creativecommons.org/licenses/by/4.0/',
                                     'https://creativecommons.org/publicdomain/zero/1.0/', 'http://creativecommons.org/publicdomain/zero/1.0/'}
        assert source['attribution'] and source['source_url'] and source['transformations'], 'Required public-source attribution missing'
        for field in ('xml', 'metadata'):
            key = source[field + '_file']; expected_fixture.add(fixture_root + key)
            assert sha(payload[fixture_root + key]) == source[field + '_sha256']
    fixture_files = {name for name in names if name.startswith(fixture_root)}
    # Query capture/vector files listed by the reviewed public manifest are also bounded and source-only.
    assert len(fixture['sources']) == 30 and len(fixture_files) == 67
    assert expected_fixture <= fixture_files
    readme = payload['README.md'].decode()
    assert 'setup' in readme.lower() and 'local' in readme.lower()
    return {'status': 'PASS', 'archive_sha256': sha(archive.read_bytes()), 'archive_bytes': archive.stat().st_size,
            'files': len(names), 'uncompressed_bytes': sum(map(len, payload.values())),
            'manifest_and_sidecar_exact': True, 'source_snapshot_exact': True, 'public_fixture_files': len(fixture_files),
            'public_papers': len(fixture['sources']), 'runtimes_or_models_bundled': False,
            'private_state_or_credentials_observed': False, 'source_commit': expected_source_commit,
            'all_payload_files_match_commit': True, 'code_license_present': release['code_license_present'],
            'distribution_terms_included': True,
            'source_state': release['source_state'], 'extract_install_or_publish': 'NOT_RUN_BY_AUDIT'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--expected-source-commit', required=True, help='Exact full source SHA selected for this release')
    parser.add_argument('--source-checkout', required=True, type=Path, help='Clean checkout at that exact source SHA')
    args = parser.parse_args()
    result = audit(args.archive, args.expected_source_commit, args.source_checkout)
    args.report.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
