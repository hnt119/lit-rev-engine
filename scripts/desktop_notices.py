"""Retain exact locked web-runtime notices omitted by standalone tracing.

No downloads or legal inference. Inventory is deliberately overinclusive within
bundled package subtrees (including Next's vendored compiled modules), and is
not a complete binary SBOM or distribution clearance.
"""
from __future__ import annotations
from hashlib import sha256, sha1
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urlsplit

MAX_NOTICE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
_NOTICE_NAME = re.compile(r'(^|[._ -])(licen[cs]es?|copying|copyright|notices?|third[._ -]?party)([._ -]|$)', re.I)
SUPPLEMENTS = Path(__file__).resolve().parents[1] / 'apps/desktop/notices'
_SUPPLEMENT_NAMES = {'@edge-runtime/cookies', '@edge-runtime/ponyfill', '@edge-runtime/primitives', '@next/env', 'string-hash'}
_RUNTIME_SUFFIXES = {'.js', '.cjs', '.mjs', '.node', '.wasm'}
_SHA256 = re.compile(r'[0-9a-f]{64}')
_CODE_SUFFIXES = {'.js', '.cjs', '.mjs', '.ts', '.tsx', '.jsx', '.py', '.pyc', '.map', '.node', '.so', '.dylib', '.wasm', '.c', '.h'}


def _json(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
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



def _relative(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise ValueError('Supplement paths must be safe relative POSIX paths')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or path.as_posix() != value or value == '.':
        raise ValueError('Supplement paths must be safe relative POSIX paths')
    return Path(*path.parts)


def _hashed(path, expected, root):
    if not isinstance(expected, str) or not _SHA256.fullmatch(expected):
        raise ValueError('Supplement requires an exact SHA256 binding')
    resolved = _inside(path, root)
    if not resolved.is_file() or resolved.stat().st_size > MAX_NOTICE_BYTES:
        raise ValueError('Supplement input is missing or exceeds the bounded file size')
    raw = resolved.read_bytes()
    if sha256(raw).hexdigest() != expected:
        raise ValueError('Supplement source or notice hash mismatch')
    return raw


def _load_supplements(directory):
    directory = Path(directory)
    if directory.is_symlink() or directory.resolve() != directory.absolute():
        raise ValueError('Supplement input directory must not contain symlink parents')
    root = directory.resolve(strict=True)
    manifest_path = root / 'web-supplements.json'
    if manifest_path.is_symlink() or manifest_path.stat().st_size > 128 * 1024:
        raise ValueError('Invalid bounded supplemental notice manifest')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:raise ValueError('Duplicate supplemental manifest key')
            result[key] = value
        return result
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw, object_pairs_hook=unique)
    if manifest.get('schema') != 'litrev.desktop-web-notice-supplements.v1':
        raise ValueError('Unknown supplemental notice schema')
    entries, seen, inputs = {}, set(), {}
    rows = manifest.get('packages')
    if not isinstance(rows, list) or len(rows) > 5:raise ValueError('Invalid bounded supplement package list')
    def read_input(path, expected):
        content = _hashed(path, expected, root)
        inputs[str(path)] = len(content)
        if sum(inputs.values()) > MAX_TOTAL_BYTES:raise ValueError('Supplement inputs exceed the bounded total size')
        return content
    for item in rows:
        if not isinstance(item, dict):raise ValueError('Invalid supplemental package binding')
        name = item.get('name')
        if name not in _SUPPLEMENT_NAMES or name in seen:
            raise ValueError('Unknown or duplicate supplemental package binding')
        seen.add(name)
        if not isinstance(item.get('runtime_files'), dict) or not item['runtime_files']:
            raise ValueError('Supplement requires exact runtime source bindings')
        for relative, expected in item['runtime_files'].items():
            _relative(relative)
            if not isinstance(expected, str) or not _SHA256.fullmatch(expected):raise ValueError('Invalid supplemental runtime hash')
        kinds = [entry.get('kind') for entry in item.get('notices', [])]
        required = ({'upstream_dedication', 'standard_license_definition'} if name == 'string-hash' else
                    {'matching_monorepo_notice'} if name == '@next/env' else {'exact_published_package_notice'})
        if set(kinds) != required or len(kinds) != len(required):
            raise ValueError('Supplement needs its complete reviewed notice/dedication set')
        parent = item.get('parent')
        if not isinstance(parent, dict) or parent.get('name') != 'next' or parent.get('dependency_section') not in {'dependencies', 'devDependencies'}:
            raise ValueError('Supplement requires the reviewed Next parent context')
        dependency = parent['dependency_manifest']
        if dependency.get('source_url') != 'https://github.com/vercel/next.js/blob/v' + parent['version'] + '/packages/next/package.json':
            raise ValueError('Supplement upstream dependency source URL mismatch')
        dependency_path = root / _relative(dependency['file'])
        if any(parent.is_symlink() for parent in (dependency_path, *dependency_path.parents) if parent.is_relative_to(root)):
            raise ValueError('Supplement dependency manifest paths cannot be symlinks')
        dependency_raw = read_input(dependency_path, dependency['sha256'])
        blob = sha1(b'blob ' + str(len(dependency_raw)).encode() + b'\0' + dependency_raw).hexdigest()
        if blob != dependency.get('upstream_blob_sha1'):raise ValueError('Supplement upstream source blob mismatch')
        item['_dependency_metadata'] = json.loads(dependency_raw, object_pairs_hook=unique)
        context = item['_dependency_metadata']
        if context.get('name') != item['parent']['name'] or context.get('version') != item['parent']['version']:
            raise ValueError('Supplement upstream parent source version mismatch')
        notices = []
        for entry in item['notices']:
            relative = _relative(entry['file']); path = root / relative
            if any(parent.is_symlink() for parent in (path, *path.parents) if parent.is_relative_to(root)):
                raise ValueError('Supplement notice paths cannot be symlinks')
            content = read_input(path, entry['sha256'])
            parsed = urlsplit(entry.get('source_url', ''))
            if parsed.scheme != 'https' or parsed.hostname not in {'github.com', 'raw.githubusercontent.com', 'creativecommons.org'} or parsed.username or parsed.password or parsed.port not in (None, 443):
                raise ValueError('Supplement needs an approved public source URL')
            provenance = entry.get('provenance', {})
            if entry['kind'] == 'standard_license_definition':
                if provenance != {'license': 'CC0-1.0'} or entry['source_url'] != 'https://creativecommons.org/publicdomain/zero/1.0/legalcode.txt':
                    raise ValueError('Unknown standard license definition source')
            else:
                if provenance.get('package') != name or provenance.get('version') != item.get('reviewed_version'):
                    raise ValueError('Supplement provenance source identity mismatch')
                version = item['reviewed_version']; leaf = name.rsplit('/', 1)[-1]
                if provenance.get('tarball_url') != 'https://registry.npmjs.org/' + name + '/-/' + leaf + '-' + version + '.tgz':
                    raise ValueError('Supplement published artifact source identity mismatch')
                if not isinstance(provenance.get('tarball_sha256'), str) or not _SHA256.fullmatch(provenance['tarball_sha256']) or not re.fullmatch(r'sha512-[A-Za-z0-9+/]{86}==', provenance.get('tarball_integrity', '')):
                    raise ValueError('Supplement published artifact hash binding missing')
                if entry['kind'] == 'exact_published_package_notice':expected_url = 'https://github.com/vercel/edge-runtime/blob/@edge-runtime/' + leaf + '@' + version + '/LICENSE.md'
                elif entry['kind'] == 'matching_monorepo_notice':expected_url = 'https://github.com/vercel/next.js/blob/v' + parent['version'] + '/license.md'
                else:
                    commit = provenance.get('source_commit', '')
                    if not re.fullmatch(r'[a-f0-9]{40}', commit):raise ValueError('Supplement dedication source commit missing')
                    expected_url = 'https://github.com/darkskyapp/string-hash/blob/' + commit + '/README.md'
                if entry['source_url'] != expected_url:raise ValueError('Supplement notice source URL mismatch')
            notices.append((entry, content))
        entries[name] = (item, notices)
    if len(entries) > 5:raise ValueError('Supplement package limit exceeded')
    return entries, sha256(raw).hexdigest()


def _bound_supplement(item, source, bundled, installed, standalone):
    metadata = _json(source)
    if metadata.get('version') != item.get('package_version'):
        raise ValueError('Supplement package version mismatch')
    _hashed(source, item['package_json_sha256'], installed)
    _hashed(bundled, item['package_json_sha256'], standalone)
    parent = item['parent']; relative = parent.get('relative_package_json')
    if relative:
        relative = _relative(relative)
        source_parents = [p / 'package.json' for p in source.parents if p.is_relative_to(installed) and (p / relative).resolve() == source.resolve()]
        bundle_parents = [p / 'package.json' for p in bundled.parents if p.is_relative_to(standalone) and (p / relative).resolve() == bundled.resolve()]
    else:
        # @next/env is Next's explicit sibling dependency, including pnpm aliases.
        source_parents = [installed / 'next/package.json']
        bundle_parents = []
        for candidate in standalone.rglob('package.json'):
            _inside(candidate, standalone)
            if _json(candidate).get('name') == parent['name']:
                dependency = candidate.parent.parent / metadata['name'] / 'package.json'
                if dependency.exists() and dependency.resolve() == bundled.resolve():bundle_parents.append(candidate)
        if source_parents[0].exists():
            resolved_parent = _inside(source_parents[0], installed)
            dependency = resolved_parent.parent.parent / metadata['name'] / 'package.json'
            if not dependency.exists() or dependency.resolve() != source.resolve():
                raise ValueError('Supplement parent dependency source mismatch')
    if len(source_parents) != 1 or len(bundle_parents) != 1:
        raise ValueError('Supplement parent context is missing or ambiguous')
    for candidate, root in ((source_parents[0], installed), (bundle_parents[0], standalone)):
        _hashed(candidate, parent['package_json_sha256'], root)
        value = _json(candidate)
        if value.get('name') != parent['name'] or value.get('version') != parent['version']:
            raise ValueError('Supplement parent package version mismatch')
        declared = value.get(parent['dependency_section'], {}).get(item['name'])
        if declared is not None and declared != item['reviewed_version']:
            raise ValueError('Supplement parent dependency version mismatch')
        if item['_dependency_metadata'].get(parent['dependency_section'], {}).get(item['name']) != item['reviewed_version']:
            raise ValueError('Supplement upstream dependency source version mismatch')
    bundled_files = {}
    for package, root in ((source.parent, installed), (bundled.parent, standalone)):
        actual = {p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_file() and p.suffix in _RUNTIME_SUFFIXES and 'node_modules' not in p.relative_to(package).parts}
        expected = set(item['runtime_files'])
        if (root == installed and actual != expected) or (root == standalone and (not actual or not actual <= expected)):
            raise ValueError('Supplement runtime source file set mismatch')
        for relative in actual:_hashed(package / _relative(relative), item['runtime_files'][relative], root)
        if root == standalone:bundled_files = {relative:item['runtime_files'][relative] for relative in sorted(actual)}
    return {'reviewed_version': item['reviewed_version'], 'package_json_sha256': item['package_json_sha256'],
            'runtime_files': item['runtime_files'], 'bundled_runtime_files': bundled_files,
            'untraced_reviewed_runtime_files': sorted(set(item['runtime_files']) - set(bundled_files)), 'parent': parent}

def copy_web_dependency_notices(standalone_root, installed_node_modules, destination, *, supplemental_root=SUPPLEMENTS):
    """Copy notices from exact installed counterparts of traced package JSONs.

    Inputs are read-only. ``destination`` must be fresh and outside both input
    trees. Relative pnpm aliases may resolve only inside installed_node_modules.
    Missing sources/notices are recorded explicitly; mismatched package identity
    or unsafe links abort rather than silently copy another version's terms.
    Only the reviewed, hash-bound offline catalog may supplement missing texts;
    it does not qualify native/source obligations or trusted distribution.
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

    supplements, supplement_hash = _load_supplements(supplemental_root)
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
        if metadata['name'] in supplements:
            binding, supplied = supplements[metadata['name']]
            entry['supplement_binding'] = _bound_supplement(binding, counterpart, bundled, installed, standalone)
            entry['supplement_binding']['catalog_sha256'] = supplement_hash
            for item, raw in supplied:
                digest = sha256(raw).hexdigest()
                output = 'notices/' + digest + '-' + re.sub(r'[^A-Za-z0-9._-]', '_', Path(item['file']).name)
                if output not in notices:
                    notices[output] = raw; total += len(raw)
                    if total > MAX_TOTAL_BYTES:raise ValueError('Web dependency notices exceed the bounded total size')
                entry['notice_files'].append({'file': output, 'bytes': len(raw), 'sha256': digest,
                    'kind': item['kind'], 'supplement_relative_path': item['file'],
                    'source_url': item['source_url'], 'provenance': item['provenance']})
        # Native packages' published source/repository pointers and version
        # declarations are kept verbatim, without inventing license conclusions.
        versions = source_package / 'versions.json'
        if ('sharp' in str(metadata['name']) or 'vips' in str(metadata['name'])) and versions.is_file():
            _inside(versions, installed)
            entry['native_component_versions'] = _json(versions)
        supplemented = 'supplement_binding' in entry
        full_notice = supplemented or any(item['kind'] == 'upstream_notice_file' for item in entry['notice_files'])
        entry['notice_status'] = ('retained_hash_bound_supplemental_inputs' if supplemented else 'retained_exact_upstream_files' if full_notice else
            'upstream_declarations_only_full_notice_missing' if entry['notice_files'] else 'missing_notice_file')
        if not full_notice:
            missing.append({'package': relative.as_posix(), 'reason': entry['notice_status']})
        packages.append(entry)

    inventory = {
        'schema': 'litrev.web-runtime-notices.v1',
        'scope': 'Overinclusive exact notices from locked counterparts of bundled package trees, including vendored Next compiled/native packages; no unbundled dependency code copied.',
        'legal_status': 'Declared metadata and retained notices only; complete binary SBOM, source-obligation and public distribution review remain pending. No relicensing or legal clearance.',
        'packages': packages, 'missing_notice_sources': missing,
        'supplement_catalog_sha256': supplement_hash,
        'unresolved_distribution_reviews': [{'name': item['name'], 'status': 'blocked',
            'reason': 'full_notice_and_attribution_unresolved' if item['name'] == 'client-only' else 'native_component_notices_corresponding_source_and_relink_review_unresolved'}
            for item in packages if item['name'] in {'client-only', '@img/sharp-libvips-darwin-arm64'}],
        'public_distribution_gates': {'qualified': False, 'complete_transitive_sbom': 'pending',
            'native_source_obligations': 'pending', 'trusted_signing_notarization': 'pending',
            'external_optional_ml_runtime': 'not_implemented'},
        'skipped_application_or_unnamed_metadata': skipped,
        'unique_notice_files': len(notices), 'notice_bytes': total,
    }
    target.mkdir(parents=False, mode=0o755)
    (target/'notices').mkdir(mode=0o755)
    for relative, raw in sorted(notices.items()):
        (target/relative).write_bytes(raw)
    (target/'INVENTORY.json').write_text(json.dumps(inventory, ensure_ascii=False, sort_keys=True, indent=2)+'\n', encoding='utf-8')
    (target/'README.md').write_text(
        '# Web runtime dependency notices\n\n'
        'These exact upstream notice files accompany the traced production runtime. '
        'INVENTORY.json preserves package declarations, repository/source pointers and notice hashes. '
        'The inventory is overinclusive within included package trees; it does not prove every listed component is linked. '
        'Hash-bound supplements retain distinct published-package, monorepo, dedication and standard-text provenance. '
        'Client-only attribution and native source obligations remain explicitly blocked; copied notices are not distribution clearance. '
        'Missing notice sources are explicit. Native-library source/redistribution obligations and a complete binary SBOM '
        'must be reviewed before public desktop distribution. The owner engine remains MIT; third-party terms remain separate.\n', encoding='utf-8')
    return inventory
