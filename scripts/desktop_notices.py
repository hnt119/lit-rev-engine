"""Retain exact locked web-runtime notices omitted by standalone tracing.

No downloads or legal inference. Inventory is deliberately overinclusive within
bundled package subtrees (including Next's vendored compiled modules), and is
not a complete binary SBOM or distribution clearance.
"""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
import re

MAX_NOTICE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
_NOTICE_NAME = re.compile(r'(^|[._ -])(licen[cs]es?|copying|copyright|notices?|third[._ -]?party)([._ -]|$)', re.I)
_CODE_SUFFIXES = {'.js', '.cjs', '.mjs', '.ts', '.tsx', '.jsx', '.py', '.pyc', '.map', '.node', '.so', '.dylib', '.wasm', '.c', '.h'}


def _json(path):
    try:
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise ValueError('Expected package metadata')
        return value
    except (OSError, UnicodeError, ValueError):
        raise ValueError('Invalid locked package metadata') from None


def _inside(path, root):
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError('A notice or package link escapes the approved installed dependency input')
    return resolved


def _notice(path):
    return bool(_NOTICE_NAME.search(path.name)) and path.suffix.lower() not in _CODE_SUFFIXES


def _notices(package, installed):
    # pathlib does not descend directory symlinks. Explicitly exclude nested
    # node_modules, which are separate dependencies rather than this package's
    # vendored notice tree. Next/dist/compiled remains included.
    found = []
    for path in sorted(package.rglob('*')):
        relative = path.relative_to(package)
        if 'node_modules' in relative.parts:
            continue
        named_notice = _notice(path)
        readme = path.name.lower().startswith('readme') and path.suffix.lower() in {'', '.md', '.txt', '.rst'}
        if not named_notice and not readme:
            continue
        resolved = _inside(path, installed)
        if resolved.is_file():
            if resolved.stat().st_size > MAX_NOTICE_BYTES:
                raise ValueError('An upstream notice exceeds the bounded copy limit')
            if named_notice or re.search(rb'licens|copyright|source.{0,20}offer', resolved.read_bytes(), re.I):
                found.append((path, resolved, named_notice))
    return found


def copy_web_dependency_notices(standalone_root, installed_node_modules, destination):
    """Copy notices from exact installed counterparts of traced package JSONs.

    Inputs are read-only. ``destination`` must be fresh and outside both input
    trees. Relative pnpm aliases may resolve only inside installed_node_modules.
    Missing sources/notices are recorded explicitly; mismatched package identity
    or unsafe links abort rather than silently copy another version's terms.
    """
    standalone = Path(standalone_root).resolve(strict=True)
    installed = Path(installed_node_modules).resolve(strict=True)
    target = Path(destination).absolute()
    if not standalone.is_dir() or not installed.is_dir():
        raise ValueError('Use existing standalone and installed dependency directories')
    if target.exists() or target.is_symlink():
        raise ValueError('Use a fresh web dependency notice destination')
    if target.parent.resolve() != target.parent or any(target.is_relative_to(root) for root in (standalone, installed)):
        raise ValueError('Notice output must be outside the dependency inputs and have no symbolic-link parents')

    packages, missing, skipped = [], [], []
    notices = {}
    total = 0
    # Collect/validate everything before making an output directory.
    for bundled in sorted(standalone.rglob('package.json')):
        if not bundled.is_file():
            continue
        _inside(bundled, standalone)
        metadata = _json(bundled)
        relative = bundled.relative_to(standalone)
        positions = [i for i, value in enumerate(relative.parts) if value == 'node_modules']
        if not positions:
            skipped.append(relative.as_posix())  # Application metadata already has engine MIT notices.
            continue
        if not metadata.get('name'):
            skipped.append(relative.as_posix())
            continue
        counterpart = None
        for index in positions:
            candidate = installed.joinpath(*relative.parts[index+1:])
            if not candidate.exists() and not candidate.is_symlink():
                continue
            resolved = _inside(candidate, installed)
            if not resolved.is_file():
                continue
            source = _json(resolved)
            if (source.get('name'), source.get('version')) != (metadata.get('name'), metadata.get('version')):
                raise ValueError('Bundled and installed package identity/version differ')
            counterpart = resolved
            break
        entry = {
            'bundled_package_json': relative.as_posix(),
            'name': metadata['name'], 'version': metadata.get('version'),
            'declared_license': metadata.get('license'),
            'upstream_homepage': metadata.get('homepage'),
            'upstream_repository': metadata.get('repository'),
            'notice_files': [],
        }
        if counterpart is None:
            entry['notice_status'] = 'missing_locked_source'
            missing.append({'package': relative.as_posix(), 'reason': entry['notice_status']})
            packages.append(entry)
            continue
        entry['source_package_json'] = counterpart.relative_to(installed).as_posix()
        # Exact metadata bytes are checked too, so matching names/versions cannot
        # hide a modified source declaration or another build's package content.
        if counterpart.read_bytes() != bundled.read_bytes():
            raise ValueError('Bundled and locked package metadata bytes differ')
        source_package = counterpart.parent
        for original, resolved, named_notice in _notices(source_package, installed):
            if resolved.stat().st_size > MAX_NOTICE_BYTES:
                raise ValueError('An upstream notice exceeds the bounded copy limit')
            raw = resolved.read_bytes()
            digest = sha256(raw).hexdigest()
            key = digest + '-' + re.sub(r'[^A-Za-z0-9._-]', '_', original.name)
            output = 'notices/' + key
            if output not in notices:
                notices[output] = raw
                total += len(raw)
                if total > MAX_TOTAL_BYTES:
                    raise ValueError('Web dependency notices exceed the bounded total size')
            entry['notice_files'].append({'package_relative_path': original.relative_to(source_package).as_posix(),
                'installed_relative_path': original.relative_to(installed).as_posix(),
                'file': output, 'bytes': len(raw), 'sha256': digest,
                'kind': 'upstream_notice_file' if named_notice else 'upstream_readme_license_declarations_and_links'})
        # Native packages' published source/repository pointers and version
        # declarations are kept verbatim, without inventing license conclusions.
        versions = source_package / 'versions.json'
        if ('sharp' in str(metadata['name']) or 'vips' in str(metadata['name'])) and versions.is_file():
            _inside(versions, installed)
            entry['native_component_versions'] = _json(versions)
        full_notice = any(item['kind'] == 'upstream_notice_file' for item in entry['notice_files'])
        entry['notice_status'] = ('retained_exact_upstream_files' if full_notice else
            'upstream_declarations_only_full_notice_missing' if entry['notice_files'] else 'missing_notice_file')
        if not full_notice:
            missing.append({'package': relative.as_posix(), 'reason': entry['notice_status']})
        packages.append(entry)

    inventory = {
        'schema': 'litrev.web-runtime-notices.v1',
        'scope': 'Overinclusive exact notices from locked counterparts of bundled package trees, including vendored Next compiled/native packages; no unbundled dependency code copied.',
        'legal_status': 'Declared metadata and retained notices only; complete binary SBOM, source-obligation and public distribution review remain pending. No relicensing or legal clearance.',
        'packages': packages, 'missing_notice_sources': missing,
        'skipped_application_or_unnamed_metadata': skipped,
        'unique_notice_files': len(notices), 'notice_bytes': total,
    }
    target.mkdir(parents=False, mode=0o755)
    (target/'notices').mkdir(mode=0o755)
    for relative, raw in sorted(notices.items()):
        (target/relative).write_bytes(raw)
    (target/'INVENTORY.json').write_text(json.dumps(inventory, ensure_ascii=False, sort_keys=True, indent=2)+'\n')
    (target/'README.md').write_text(
        '# Web runtime dependency notices\n\n'
        'These exact upstream notice files accompany the traced production runtime. '
        'INVENTORY.json preserves package declarations, repository/source pointers and notice hashes. '
        'The inventory is overinclusive within included package trees; it does not prove every listed component is linked. '
        'Missing notice sources are explicit. Native-library source/redistribution obligations and a complete binary SBOM '
        'must be reviewed before public desktop distribution. The owner engine remains MIT; third-party terms remain separate.\n')
    return inventory
