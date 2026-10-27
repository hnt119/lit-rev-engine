#!/usr/bin/env python3
"""Static Windows candidate audit. Never load or execute a target binary.

Host pip supplies its existing vendored packaging parser; no runtime dependency
is added. PASS is package/configuration evidence, never Windows qualification.
"""
from __future__ import annotations
import argparse
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
SKIP_REASON = 'Owner explicitly skipped all Windows runtime, VM, GUI and installed end-to-end tests.'
# Declared Windows 11 OS dependencies, not evidence that a target OS was read.
SYSTEM_DLLS = frozenset('''advapi32.dll avrt.dll bcrypt.dll bthprops.cpl cabinet.dll cfgmgr32.dll clbcatq.dll combase.dll comctl32.dll comdlg32.dll credui.dll crypt32.dll cryptbase.dll cryptnet.dll cryptsp.dll d2d1.dll d3d11.dll d3d12.dll dbghelp.dll dhcpcsvc.dll dnsapi.dll dsound.dll dwmapi.dll dwrite.dll dxgi.dll dxva2.dll gdi32.dll hid.dll imm32.dll iphlpapi.dll kernel32.dll kernelbase.dll ksuser.dll mf.dll mfplat.dll mfreadwrite.dll mfuuid.dll mpr.dll msacm32.dll msdmo.dll msimg32.dll msvcrt.dll ncrypt.dll netapi32.dll normaliz.dll ntdll.dll ole32.dll oleacc.dll oleaut32.dll powrprof.dll propsys.dll psapi.dll rasapi32.dll rpcrt4.dll secur32.dll setupapi.dll shell32.dll shlwapi.dll sspicli.dll ucrtbase.dll urlmon.dll user32.dll userenv.dll usp10.dll uxtheme.dll version.dll winhttp.dll wininet.dll winmm.dll winspool.drv winsta.dll wintrust.dll ws2_32.dll wsock32.dll wtsapi32.dll'''.split())
SYSTEM_DLLS = SYSTEM_DLLS | frozenset('''uiautomationcore.dll cryptui.dll pdh.dll mmdevapi.dll wevtapi.dll tbs.dll dcomp.dll bcryptprimitives.dll winusb.dll msi.dll odbc32.dll loadperf.dll mswsock.dll sfc.dll lz32.dll ntdsapi.dll ktmw32.dll activeds.dll aclui.dll query.dll'''.split())
API_SET = re.compile(r'(?:api|ext)-ms-win-[a-z0-9-]+\.dll\Z')
AUXILIARY = {f'resources/python/Lib/site-packages/pip/_vendor/distlib/{name}.exe': machine
             for name, machine in [('t32', 0x14c), ('w32', 0x14c), ('t64', 0x8664), ('w64', 0x8664), ('t64-arm', 0xaa64), ('w64-arm', 0xaa64)]}
CORE_FILES = ('resources/python/python.exe', 'resources/python/python312.dll',
    'resources/python/Lib/site-packages/pywin32.pth',
    'resources/python/Lib/site-packages/win32/lib/pywin32_bootstrap.py',
    'resources/python/Lib/site-packages/pywin32_system32/pywintypes312.dll',
    'resources/python/Lib/site-packages/pywin32_system32/pythoncom312.dll',
    'resources/python/Lib/site-packages/win32/win32api.pyd',
    'resources/python/Lib/site-packages/win32/win32file.pyd',
    'resources/python/Lib/site-packages/win32/win32security.pyd',
    'resources/python/Lib/site-packages/win32/win32event.pyd',
    'resources/python/Lib/site-packages/win32/win32process.pyd',
    'resources/python/Lib/site-packages/win32/win32job.pyd',
    'resources/python/Lib/site-packages/win32/win32pipe.pyd',
    'resources/python/Lib/site-packages/win32/lib/win32con.py',
    'resources/python/Lib/site-packages/win32/lib/ntsecuritycon.py',
    'resources/engine/scripts/desktop_backend.py', 'resources/web/apps/web/server.js',
    'resources/web/apps/web/.next/BUILD_ID')


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): value.update(block)
    return value.hexdigest()


def ordinary(path):
    if path.is_symlink() or not path.is_file(): raise ValueError('Expected ordinary file: ' + path.name)
    return path


def pe_info(raw):
    """Bounded PE/import/delay-import parsing using file bytes only."""
    if len(raw) < 64 or raw[:2] != b'MZ': raise ValueError('Not a PE executable')
    offset = struct.unpack_from('<I', raw, 60)[0]
    if offset < 64 or offset + 24 > len(raw) or raw[offset:offset + 4] != b'PE\0\0': raise ValueError('Invalid PE header offset')
    machine, sections = struct.unpack_from('<HH', raw, offset + 4)
    size = struct.unpack_from('<H', raw, offset + 20)[0]; optional = offset + 24
    if not 0 < sections <= 96 or optional + size + sections * 40 > len(raw): raise ValueError('Invalid PE section table')
    magic = struct.unpack_from('<H', raw, optional)[0]
    if magic not in (0x10b, 0x20b) or size < (96 if magic == 0x10b else 112): raise ValueError('Invalid PE optional header')
    directories = optional + (96 if magic == 0x10b else 112)
    directory_count = struct.unpack_from('<I', raw, directories - 4)[0]
    image_base = struct.unpack_from('<I' if magic == 0x10b else '<Q', raw, optional + (28 if magic == 0x10b else 24))[0]
    header_size = struct.unpack_from('<I', raw, optional + 60)[0]
    spans = []
    for index in range(sections):
        start = optional + size + index * 40
        virtual_size, address, raw_size, raw_offset = struct.unpack_from('<IIII', raw, start + 8)
        if raw_size and raw_offset + raw_size > len(raw): raise ValueError('Section leaves PE file')
        spans.append((address, max(virtual_size, raw_size), raw_offset, raw_size))
    def file_offset(rva, count=1):
        if rva < header_size and rva + count <= min(header_size, len(raw)): return rva
        for address, length, start, raw_size in spans:
            if address <= rva and rva + count <= address + length and rva - address + count <= raw_size:
                return start + rva - address
        raise ValueError('Unmapped PE RVA')
    def name(rva):
        start = file_offset(rva); end = raw.find(b'\0', start, min(len(raw), start + 512))
        if end < 0: raise ValueError('Unterminated DLL import')
        value = raw[start:end].decode('ascii').lower()
        if not re.fullmatch(r'[a-z0-9_.-]+\.(?:dll|drv|pyd|cpl)', value): raise ValueError('Unsafe DLL import name: ' + repr(value))
        return value
    imports = []
    for index, width, delayed in ((1, 20, False), (13, 32, True)):
        if index >= directory_count or directories + (index + 1) * 8 > optional + size: continue
        rva, length = struct.unpack_from('<II', raw, directories + index * 8)
        if not rva: continue
        if length < width or length > 1024 * 1024: raise ValueError('Invalid import directory size')
        terminated = False
        for relative in range(0, length, width):
            entry = struct.unpack_from('<' + 'I' * (width // 4), raw, file_offset(rva + relative, width))
            if not any(entry): terminated = True; break
            target = entry[1] if delayed else entry[3]
            if delayed and not (entry[0] & 1):
                if target < image_base: raise ValueError('Invalid delay-import address')
                target -= image_base
            imports.append({'dll': name(target), 'delay': delayed})
        if not terminated: raise ValueError('Unterminated import directory')
    return {'machine': machine, 'optional_magic': magic, 'imports': imports}


def check_manifest(payload, expected):
    manifest = ordinary(payload / 'INSTALLATION.json')
    if manifest.stat().st_size > 16 * 1024 * 1024: raise ValueError('Manifest exceeds bound')
    value = json.loads(manifest.read_text())
    if value.get('schema') != 'litrev.desktop.installed-files.v1' or value.get('source_commit') != expected or value.get('app_id') != 'org.hnt119.litrev.desktop': raise ValueError('Installed source/product binding mismatch')
    files = value.get('files')
    if not isinstance(files, dict) or not 0 < len(files) <= 150000: raise ValueError('Invalid installed file inventory')
    actual = set()
    for path in payload.rglob('*'):
        if path.is_symlink(): raise ValueError('Payload contains a symlink')
        if path.is_file(): actual.add(path.relative_to(payload).as_posix())
    if actual != set(files) | {'INSTALLATION.json'}: raise ValueError('Payload has missing or extra files')
    for name, record in files.items():
        p = PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or p.as_posix() != name or '\\' in name or ':' in name: raise ValueError('Unsafe manifest path')
        if set(record) != {'bytes', 'sha256'} or type(record['bytes']) is not int or record['bytes'] < 0 or not re.fullmatch('[a-f0-9]{64}', record['sha256']): raise ValueError('Invalid manifest digest')
        path = ordinary(payload / name)
        if path.stat().st_size != record['bytes'] or sha(path) != record['sha256']: raise ValueError('Payload digest mismatch: ' + name)
    return value


def marker_environment():
    return {'implementation_name': 'cpython', 'implementation_version': '3.12.15', 'os_name': 'nt',
        'platform_machine': 'AMD64', 'platform_python_implementation': 'CPython', 'platform_release': '11',
        'platform_system': 'Windows', 'platform_version': '10.0.22000', 'python_full_version': '3.12.15',
        'python_version': '3.12', 'sys_platform': 'win32', 'extra': ''}


def dependency_closure(site):
    from pip._vendor.packaging.requirements import Requirement
    from pip._vendor.packaging.specifiers import SpecifierSet
    from pip._vendor.packaging.tags import parse_tag, cpython_tags, compatible_tags
    normalize = lambda name: re.sub('[-_.]+', '-', name).lower()
    installed = {}; extras = {}; failures = []
    compatible = set(cpython_tags((3, 12), platforms=['win_amd64'])) | set(compatible_tags((3, 12), interpreter='cp312', platforms=['win_amd64']))
    for path in sorted(site.glob('*.dist-info')):
        msg = BytesParser().parsebytes(ordinary(path / 'METADATA').read_bytes())
        key = normalize(msg['Name'] or '')
        if not key or key in installed: raise ValueError('Missing/duplicate distribution identity')
        if msg['Requires-Python'] and not SpecifierSet(msg['Requires-Python']).contains('3.12.15'): failures.append(key + ': incompatible Requires-Python')
        wheel = BytesParser().parsebytes(ordinary(path / 'WHEEL').read_bytes())
        tags = set().union(*(parse_tag(tag) for tag in wheel.get_all('Tag', [])))
        if not tags & compatible: failures.append(key + ': incompatible or missing target wheel tag')
        installed[key] = {'version': msg['Version'], 'requirements': msg.get_all('Requires-Dist', [])}
        extras[key] = set()
    for line in (ROOT / 'requirements-hosted.txt').read_text().splitlines():
        line = line.split('#', 1)[0].strip()
        if not line or line.startswith('-'): continue
        req = Requirement(line)
        if req.marker and not req.marker.evaluate(marker_environment()): continue
        key = normalize(req.name)
        if key not in installed or not req.specifier.contains(installed[key]['version']): failures.append('Required runtime pin missing/mismatched: ' + key)
        if key in extras: extras[key].update(req.extras)
    # Follow explicitly selected dependency extras; do not activate optional extras.
    changed = True
    while changed:
        changed = False
        for parent, record in installed.items():
            for raw in record['requirements']:
                req = Requirement(raw)
                active = req.marker is None or any(req.marker.evaluate({**marker_environment(), 'extra': extra}) for extra in {''} | extras[parent])
                if not active: continue
                key = normalize(req.name)
                if key not in installed or not req.specifier.contains(installed[key]['version']): failures.append(parent + ': missing/incompatible target dependency ' + key)
                elif not req.extras <= extras[key]: extras[key].update(req.extras); changed = True
    return {'environment': marker_environment(), 'distributions': {key: row['version'] for key, row in installed.items()}, 'selected_extras': {key: sorted(v) for key, v in extras.items() if v}, 'failures': sorted(set(failures))}


def native_closure(payload, files):
    records = []; unresolved = []; exceptions = []
    python = payload / 'resources/python'
    search = [payload, python, python / 'DLLs', python / 'Lib/site-packages/pywin32_system32']
    for relative in files:
        path = payload / relative
        with path.open('rb') as stream: magic = stream.read(4)
        if magic in {b'\x7fELF', b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf'}: raise ValueError('Foreign native runtime: ' + relative)
        if magic == b'\xca\xfe\xba\xbe':
            head = path.read_bytes()[:8]
            if len(head) == 8 and 0 < struct.unpack_from('>I', head, 4)[0] <= 64: raise ValueError('Foreign Mach-O universal runtime: ' + relative)
        if magic[:2] != b'MZ':
            if path.suffix.lower() in {'.exe', '.dll', '.pyd', '.node'}: raise ValueError('Named native runtime is not PE: ' + relative)
            continue
        try: info = pe_info(path.read_bytes())
        except (ValueError, UnicodeError, struct.error) as error: raise ValueError('PE inspection failed: ' + relative + ': ' + str(error)) from error
        auxiliary = relative in AUXILIARY
        expected = AUXILIARY.get(relative, 0x8664)
        if info['machine'] != expected: raise ValueError('Wrong PE architecture: ' + relative)
        if info['optional_magic'] != (0x10b if expected == 0x14c else 0x20b): raise ValueError('PE architecture/optional header mismatch: ' + relative)
        records.append({'path': relative, 'sha256': files[relative]['sha256'], 'machine': hex(info['machine']), 'auxiliary_not_core': auxiliary, 'imports': info['imports']})
        if auxiliary: continue  # exact named pip/distlib templates, never a core launch path
        for item in info['imports']:
            dll = item['dll']
            if dll in SYSTEM_DLLS or API_SET.fullmatch(dll):
                exceptions.append({'path': relative, 'dll': dll, 'reason': 'Declared Windows 11 OS/API-set dependency; availability/exports NOT_RUN'})
                continue
            choices = [p for directory in [path.parent, *search] if directory.is_dir() for p in directory.iterdir() if p.is_file() and p.name.casefold() == dll]
            if not choices: unresolved.append({'path': relative, **item})
    return {'files': records, 'unresolved': unresolved, 'system_exceptions': exceptions, 'system_allowlist': sorted(SYSTEM_DLLS), 'api_set_pattern': API_SET.pattern}


def extracted_matches(extracted, payload):
    checksum = sha(payload / 'INSTALLATION.json')
    candidates = [p.parent for p in extracted.rglob('INSTALLATION.json') if p.is_file() and not p.is_symlink() and sha(p) == checksum]
    if len(candidates) != 1: raise ValueError('Installer extraction lacks one exact payload manifest')
    value = json.loads((payload / 'INSTALLATION.json').read_text())
    check_manifest(candidates[0], value['source_commit'])
    for name, row in value['files'].items():
        path = ordinary(candidates[0] / name)
        if path.stat().st_size != row['bytes'] or sha(path) != row['sha256']: raise ValueError('Installer extraction payload mismatch: ' + name)
    return {'status': 'PASS', 'files': len(value['files']), 'manifest_sha256': checksum}


def audit(payload, expected, *, installer=None, extracted=None):
    if not re.fullmatch('[a-f0-9]{40}', expected): raise ValueError('Require an exact source SHA')
    if payload.is_symlink() or not payload.is_dir(): raise ValueError('Require an ordinary payload directory')
    value = check_manifest(payload, expected)
    metadata = json.loads(ordinary(payload / 'resources/DESKTOP_RELEASE.json').read_text())
    if metadata.get('source_commit') != expected or metadata.get('target') != 'win32-x64' or metadata.get('core_runtimes_bundled') is not True: raise ValueError('Wrong desktop source/target/runtime binding')
    product = json.loads(ordinary(payload / 'resources/app/product.json').read_text())
    if product.get('data_name') != 'LiteratureReviewEngineDesktop' or product.get('version') != value['version'] or metadata.get('version') != value['version']: raise ValueError('Product/data/version binding differs')
    if metadata.get('web_build_binding', {}).get('source_commit') != expected: raise ValueError('Production web binding source differs')
    for name in ('LiteratureReviewEngine.exe', *CORE_FILES): ordinary(payload / name)
    site = payload / 'resources/python/Lib/site-packages'
    for package in ('fastapi', 'uvicorn', 'pydantic', 'pydantic_core', 'starlette', 'anyio'):
        ordinary(site / package / '__init__.py')
    if not list((site / 'pydantic_core').glob('*cp312-win_amd64.pyd')): raise ValueError('Missing Windows CPython pydantic-core extension')
    bootstrap = (site / 'win32/lib/pywin32_bootstrap.py').read_text()
    pth = (site / 'pywin32.pth').read_text().replace('\\', '/')
    if 'win32/lib' not in pth.splitlines() or 'import pywin32_bootstrap' not in pth: raise ValueError('Missing pywin32 startup path declaration')
    if 'pywin32_system32' not in bootstrap or 'add_dll_directory' not in bootstrap: raise ValueError('Missing pywin32 wheel-local DLL bootstrap')
    deps = dependency_closure(site); native = native_closure(payload, value['files'])
    failures = deps['failures'] + ['Unresolved DLL: ' + row['path'] + ':' + row['dll'] for row in native['unresolved']]
    result = {'schema': 'litrev.windows.static-package-audit.v1', 'status': 'FAIL' if failures else 'PASS', 'source_commit': expected,
        'scope': 'Static byte/config/dependency/package audit only; not Windows or installation qualification',
        'payload_files': len(value['files']), 'manifest_sha256': sha(payload / 'INSTALLATION.json'),
        'core_required_files': {'status': 'PASS', 'scope': 'File presence and byte-bound headers only; not Core execution or complete dynamic loading', 'paths': ['LiteratureReviewEngine.exe', *CORE_FILES]},
        'declared_dependencies': {'status': 'FAIL' if deps['failures'] else 'PASS', 'scope': 'Windows CPython3.12 AMD64 distribution metadata/markers only'}, 'dependencies': deps, 'native': native,
        'failures': failures, 'runtime_execution': 'NOT_RUN', 'vm_execution': 'NOT_RUN', 'gui_execution': 'NOT_RUN', 'installed_execution': 'NOT_RUN', 'owner_skip_reason': SKIP_REASON,
        'installer_extraction': extracted_matches(extracted, payload) if extracted else {'status': 'NOT_RUN', 'reason': 'No host-extracted installer tree supplied'}}
    if installer:
        ordinary(installer); info = pe_info(installer.read_bytes())
        if info['machine'] != 0x14c or info['optional_magic'] != 0x10b: raise ValueError('Expected pinned x86 NSIS bootstrap, distinct from AMD64 app')
        result['installer'] = {'bytes': installer.stat().st_size, 'sha256': sha(installer), 'machine': '0x14c', 'kind': 'x86 NSIS bootstrap; app payload independently AMD64'}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True); parser.add_argument('--source-sha', required=True)
    parser.add_argument('--report', type=Path, required=True); parser.add_argument('--installer', type=Path); parser.add_argument('--extracted', type=Path)
    args = parser.parse_args()
    if any(args.report.resolve().is_relative_to(path.resolve()) for path in (args.payload, args.extracted) if path is not None):
        parser.error('Audit reports must remain outside the audited payload and extracted tree')
    if args.report.exists(): parser.error('Use a new audit report; historical evidence is never overwritten')
    try: report = audit(args.payload, args.source_sha, installer=args.installer, extracted=args.extracted)
    except Exception as error:
        report = {'schema': 'litrev.windows.static-package-audit.v1', 'status': 'FAIL', 'error': str(error),
            'runtime_execution': 'NOT_RUN', 'vm_execution': 'NOT_RUN', 'gui_execution': 'NOT_RUN', 'installed_execution': 'NOT_RUN', 'owner_skip_reason': SKIP_REASON}
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'scope': 'static only', 'runtime_execution': 'NOT_RUN'}))
    raise SystemExit(0 if report['status'] == 'PASS' else 1)


if __name__ == '__main__': main()
