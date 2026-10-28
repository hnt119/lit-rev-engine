#!/usr/bin/env python3
"""Static Windows candidate audit. Never load or execute a target binary.

Host pip supplies its existing vendored packaging parser; no runtime dependency
is added. PASS is package/configuration evidence, never Windows qualification.
"""
from __future__ import annotations
import argparse
import ast
import base64
import csv
from email.parser import BytesParser
import hashlib
import io
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
    'resources/python/vcruntime140.dll', 'resources/python/vcruntime140_1.dll',
    'resources/python/Lib/site-packages/pywin32.pth',
    'resources/python/Lib/site-packages/pythoncom.py',
    'resources/python/Lib/site-packages/win32/_win32sysloader.pyd',
    'resources/python/Lib/site-packages/win32/lib/pywintypes.py',
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
EXCLUDED_PYTHON_APIS = ('pywin', 'win32ui', 'win32uiole', 'dde',
    'win32com.mapi', 'win32com.axdebug', 'win32comext.mapi', 'win32comext.axdebug')
SUBSET_POLICY = Path('apps/desktop/windows-core-pruning.json')
SUBSET_RECEIPT = 'resources/WINDOWS_PYWIN32_SUBSET.json'
PACKAGED_SUBSET_POLICY = 'resources/WINDOWS_PYWIN32_POLICY.json'
OPTIONAL_DIRECTORIES = ('resources/python/Lib/site-packages/pythonwin',
    'resources/python/Lib/site-packages/win32comext/mapi',
    'resources/python/Lib/site-packages/win32comext/axdebug')
PYWIN32_RECORD = 'resources/python/Lib/site-packages/pywin32-312.dist-info/RECORD'
REMOVED_PYWIN32_ENTRYPOINTS = ('../../bin/pywin32_postinstall', '../../bin/pywin32_postinstall.py',
    '../../bin/pywin32_testall', '../../bin/pywin32_testall.py')
TERMS_SOURCE = Path('apps/desktop/notices/windows-distribution')
TERMS_VERSION = '0.3.0-windows-experimental-beta.2'
TERMS_FILES = {'terms': 'resources/MICROSOFT_COMPONENT_TERMS.txt',
    'input_manifest': 'resources/MICROSOFT_COMPONENT_TERMS_INPUTS.json',
    'route_record': 'resources/MICROSOFT_COMPONENT_LICENSE_ROUTE.json',
    'displayed_and_retained': 'resources/MICROSOFT_COMPONENT_TERMS_WITH_LICENSES.txt'}


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): value.update(block)
    return value.hexdigest()


def ordinary(path):
    if path.is_symlink() or not path.is_file(): raise ValueError('Expected ordinary file: ' + path.name)
    return path


def source_import_guard(engine):
    """Reject direct/literal application imports of intentionally omitted APIs.

    This scans shipped application source, not every optional third-party demo.
    It is not a proof about arbitrary dynamically constructed module names.
    """
    scanned = 0
    def forbidden(name):
        return any(name == prefix or name.startswith(prefix + '.') for prefix in EXCLUDED_PYTHON_APIS)
    for directory in ('src', 'scripts'):
        root = engine / directory
        if not root.is_dir(): raise ValueError('Missing packaged application source: ' + directory)
        for path in sorted(root.rglob('*.py')):
            ordinary(path); scanned += 1
            try: tree = ast.parse(path.read_text(encoding='utf-8-sig'))
            except (SyntaxError, UnicodeError) as error: raise ValueError('Cannot inspect application imports: ' + path.relative_to(engine).as_posix()) from error
            literal_import_calls = {'__import__', 'import_module'}
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == 'importlib':
                    literal_import_calls.update(item.asname or item.name for item in node.names if item.name == 'import_module')
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import): names = [item.name for item in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module, *(node.module + '.' + item.name for item in node.names)]
                elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    call = node.func
                    if (isinstance(call, ast.Name) and call.id in literal_import_calls) or (isinstance(call, ast.Attribute) and call.attr == 'import_module'):
                        names = [node.args[0].value]
                if any(forbidden(name) for name in names):
                    raise ValueError('Application imports omitted optional API: ' + path.relative_to(engine).as_posix() + ':' + str(node.lineno))
    return {'status': 'PASS', 'files_scanned': scanned,
        'scope': 'Direct/from and literal import-module application source checks only; not arbitrary dynamic Python import closure'}


def inventory(root, relative_to):
    files = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink(): raise ValueError('Inventory contains a symlink')
        if path.is_file(): files[path.relative_to(relative_to).as_posix()] = {'bytes': path.stat().st_size, 'sha256': sha(path)}
    return files


def inventory_digest(files):
    return hashlib.sha256((json.dumps(files, indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode()).hexdigest()


def wheel_record_guard(payload, policy):
    """Check unchanged RECORD declarations against both retained and omitted files."""
    if policy.get('record_path') != PYWIN32_RECORD or policy.get('record_removed_entrypoints') != list(REMOVED_PYWIN32_ENTRYPOINTS):
        raise ValueError('Unexpected pywin32 RECORD/entrypoint policy')
    path = ordinary(payload / PYWIN32_RECORD)
    if path.stat().st_size > 1024 * 1024: raise ValueError('pywin32 RECORD exceeds bound')
    actual = {}; seen = set(); removed = set()
    for row in csv.reader(io.StringIO(path.read_text(encoding='utf-8'))):
        if len(row) != 3 or row[0] in seen: raise ValueError('Invalid/duplicate pywin32 RECORD row')
        name, encoded, size = row; seen.add(name)
        if name in REMOVED_PYWIN32_ENTRYPOINTS:
            removed.add(name); continue
        relative = PurePosixPath(name)
        if relative.is_absolute() or relative.as_posix() != name or '..' in relative.parts or '\\' in name or ':' in name:
            raise ValueError('Unsafe pywin32 RECORD row')
        full = 'resources/python/Lib/site-packages/' + name
        if full == PYWIN32_RECORD:
            if encoded or size: raise ValueError('pywin32 RECORD must retain its unhashed self entry')
            continue
        if not encoded.startswith('sha256=') or not re.fullmatch('[0-9]+', size): raise ValueError('Unbound pywin32 RECORD row')
        try: digest = base64.b64decode(encoded[7:] + '=' * (-len(encoded[7:]) % 4), altchars=b'-_', validate=True).hex()
        except ValueError as error: raise ValueError('Invalid pywin32 RECORD digest') from error
        if len(digest) != 64: raise ValueError('Invalid pywin32 RECORD SHA256')
        actual[full] = {'bytes': int(size), 'sha256': digest}
    if removed != set(REMOVED_PYWIN32_ENTRYPOINTS) or PYWIN32_RECORD.removeprefix('resources/python/Lib/site-packages/') not in seen or actual != policy.get('wheel_record_files'):
        raise ValueError('pywin32 RECORD keyset/digests differ from reviewed policy')
    omitted = policy['omitted_files']
    if not set(omitted) <= set(actual) or any(actual[name] != row for name, row in omitted.items()):
        raise ValueError('Omitted pywin32 bytes are not bound to RECORD')
    for name, row in actual.items():
        if name in omitted: continue
        path = ordinary(payload / name)
        if path.stat().st_size != row['bytes'] or sha(path) != row['sha256']:
            raise ValueError('Retained pywin32 RECORD-bound bytes differ: ' + name)
    return {'status': 'PASS', 'record_files': len(actual), 'retained_files': len(actual) - len(omitted),
        'scope': 'Original RECORD and pinned per-file bytes; not execution of every pywin32 API'}


def verify_pywin32_subset(payload, metadata):
    """Independently bind omissions to reviewed policy and retained Python bytes."""
    policy_file = ordinary(ROOT / SUBSET_POLICY)
    policy = json.loads(policy_file.read_text())
    if not isinstance(policy, dict) or set(policy) != {'schema', 'scope', 'wheel', 'omitted_directories', 'omitted_files',
            'protected_files', 'record_path', 'record_removed_entrypoints', 'wheel_record_files', 'unsupported_optional_apis'}:
        raise ValueError('Invalid optional Windows policy fields')
    if (policy.get('schema') != 'litrev.windows.optional-pywin32-policy.v1'
            or policy.get('wheel') != {'name': 'pywin32', 'version': '312',
                'filename': 'pywin32-312-cp312-cp312-win_amd64.whl',
                'sha256': 'b457f6d628a47e8a7346ce22acb7e1a46a4a78b52e1d17e1af56871bd19a93bc'}):
        raise ValueError('Optional Windows component wheel policy differs')
    directories = policy.get('omitted_directories')
    if not isinstance(directories, list) or len(directories) != 3 or set(directories) != set(OPTIONAL_DIRECTORIES):
        raise ValueError('Optional Windows component directory policy differs')
    omitted = policy.get('omitted_files'); protected = policy.get('protected_files')
    for records, optional in ((omitted, True), (protected, False)):
        if not isinstance(records, dict) or not records: raise ValueError('Invalid optional subset file policy')
        for name, row in records.items():
            path = PurePosixPath(name)
            if path.is_absolute() or path.as_posix() != name or '..' in path.parts or '\\' in name or ':' in name:
                raise ValueError('Unsafe optional subset policy path')
            inside = any(name.startswith(prefix + '/') for prefix in OPTIONAL_DIRECTORIES)
            if inside != optional or not name.startswith('resources/python/'):
                raise ValueError('Optional subset policy crosses protected boundary')
            if not isinstance(row, dict) or set(row) != {'bytes', 'sha256'} or type(row['bytes']) is not int or row['bytes'] < 0 or not re.fullmatch('[a-f0-9]{64}', row['sha256']):
                raise ValueError('Invalid optional subset file digest')
    if not {name for name in CORE_FILES if name.startswith('resources/python/')} <= set(protected):
        raise ValueError('Optional subset policy does not protect every Core loader/security file')
    for name, row in protected.items():
        path = ordinary(payload / name)
        if path.stat().st_size != row['bytes'] or sha(path) != row['sha256']:
            raise ValueError('Protected Core/bootstrap bytes differ: ' + name)
    record_check = wheel_record_guard(payload, policy)
    descriptor = metadata.get('windows_optional_pywin32_subset')
    if descriptor is None:
        # Historical candidates retained all optional components. Require their
        # exact original inventory, not merely three recreated empty folders.
        actual = {}
        for name in OPTIONAL_DIRECTORIES:
            root = payload / name
            if not root.is_dir() or root.is_symlink(): raise ValueError('Missing optional subset receipt for absent components')
            actual.update(inventory(root, payload))
        if actual != omitted: raise ValueError('Missing optional subset receipt for changed components')
        return {'status': 'NOT_APPLIED', 'wheel_record': record_check,
            'scope': 'Exact original optional component inventory retained; no omission accepted'}
    expected_keys = {'schema', 'receipt_path', 'receipt_sha256', 'omitted_file_count', 'runtime_execution'}
    if (not isinstance(descriptor, dict) or set(descriptor) != expected_keys
            or descriptor.get('schema') != 'litrev.windows.optional-pywin32-subset-binding.v1'
            or descriptor.get('receipt_path') != SUBSET_RECEIPT
            or descriptor.get('runtime_execution') != 'NOT_RUN'
            or type(descriptor.get('omitted_file_count')) is not int or descriptor['omitted_file_count'] != len(omitted)):
        raise ValueError('Invalid optional subset receipt binding')
    receipt_file = ordinary(payload / SUBSET_RECEIPT)
    if sha(receipt_file) != descriptor['receipt_sha256']: raise ValueError('Optional subset receipt digest differs')
    receipt = json.loads(receipt_file.read_text())
    if not isinstance(receipt, dict) or set(receipt) != {'schema', 'policy_path', 'policy_sha256',
            'packaged_policy_path', 'wheel', 'omitted_directories',
            'omitted_files', 'protected_files', 'preserved_python_inventory', 'unsupported_optional_apis', 'runtime_execution'}:
        raise ValueError('Invalid optional subset receipt fields')
    packaged_policy = ordinary(payload / PACKAGED_SUBSET_POLICY)
    if (receipt.get('schema') != 'litrev.windows.optional-pywin32-subset.v1'
            or receipt.get('policy_path') != SUBSET_POLICY.as_posix()
            or receipt.get('policy_sha256') != sha(policy_file)
            or receipt.get('packaged_policy_path') != PACKAGED_SUBSET_POLICY
            or packaged_policy.read_bytes() != policy_file.read_bytes()
            or receipt.get('wheel') != policy.get('wheel')
            or receipt.get('omitted_directories') != directories
            or receipt.get('omitted_files') != omitted
            or receipt.get('protected_files') != protected
            or receipt.get('unsupported_optional_apis') != policy.get('unsupported_optional_apis')
            or not receipt.get('unsupported_optional_apis')
            or receipt.get('runtime_execution') != 'NOT_RUN'):
        raise ValueError('Optional subset receipt differs from reviewed policy')
    for name in OPTIONAL_DIRECTORIES:
        if (payload / name).exists() or (payload / name).is_symlink(): raise ValueError('Omitted optional component remains in payload')
    retained = inventory(payload / 'resources/python', payload)
    expected_inventory = {'files': len(retained), 'bytes': sum(row['bytes'] for row in retained.values()), 'sha256': inventory_digest(retained)}
    if receipt.get('preserved_python_inventory') != expected_inventory:
        raise ValueError('Retained Python inventory differs from subset receipt')
    return {'status': 'PASS', 'receipt_path': SUBSET_RECEIPT, 'receipt_sha256': sha(receipt_file),
        'policy_sha256': sha(policy_file), 'omitted_files': len(omitted), 'protected_files': len(protected),
        'preserved_python_inventory': expected_inventory,
        'wheel_record': record_check,
        'scope': 'Exact reviewed omissions and unchanged protected/retained bytes; optional pywin32 GUI/MAPI/debug APIs unsupported, not Core or full Python API execution'}


def verify_component_terms(payload, metadata):
    """Verify exact approved text/route bytes; do not certify legal compliance."""
    record = metadata.get('microsoft_component_terms')
    required = str(metadata.get('version', '')).startswith('0.3.0-windows-experimental-') or str(metadata.get('native_build_number')) == '3003'
    if record is None:
        if required: raise ValueError('Missing approved Microsoft component terms receipt')
        if any((payload / name).exists() for name in TERMS_FILES.values()): raise ValueError('Unbound Microsoft component terms files')
        return {'status': 'NOT_APPLIED', 'scope': 'Historical product without the new active terms integration'}
    manifest_file = ordinary(ROOT / TERMS_SOURCE / 'MANIFEST.json')
    manifest = json.loads(manifest_file.read_text())
    roles = {'component_terms', 'complete_sdk_license_readable', 'complete_sdk_license_authoritative', 'complete_python_license'}
    if (not isinstance(manifest, dict) or set(manifest) != {'schema', 'inputs', 'route_record', 'terms_version'}
            or manifest.get('schema') != 'litrev.windows.microsoft-component-terms-inputs.v1'
            or not isinstance(manifest.get('inputs'), dict) or set(manifest['inputs']) != roles):
        raise ValueError('Unknown approved Microsoft component input manifest')
    inputs = {'component_terms': ROOT / TERMS_SOURCE / 'MICROSOFT_COMPONENT_TERMS.txt',
        'complete_sdk_license_readable': payload / 'resources/WINDOWS_DEPENDENCY_NOTICES/microsoft-sdk-10.0.28000.2270/LICENSE.rendered.txt',
        'complete_sdk_license_authoritative': payload / 'resources/WINDOWS_DEPENDENCY_NOTICES/microsoft-sdk-10.0.28000.2270/LICENSE.rtf',
        'complete_python_license': payload / 'resources/python/LICENSE.txt'}
    raw = {name: ordinary(path).read_bytes() for name, path in inputs.items()}
    actual = {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for name, data in raw.items()}
    if actual != manifest['inputs']: raise ValueError('Microsoft component input bytes differ from approved pins')
    route_file = ordinary(ROOT / TERMS_SOURCE / 'LICENSE_ROUTE.json')
    raw_route = route_file.read_bytes(); route = json.loads(raw_route)
    if (manifest['route_record'] != {'file': 'LICENSE_ROUTE.json', 'bytes': len(raw_route), 'sha256': sha(route_file)}
            or not isinstance(route, dict) or route.get('schema') != 'litrev.windows.microsoft-license-route.v1'):
        raise ValueError('Approved Microsoft license-route record differs')
    if (route.get('release_version') != TERMS_VERSION or route.get('native_build_number') != 3003
            or route.get('terms_version') != manifest.get('terms_version')
            or route.get('record_version') != manifest.get('terms_version')
            or not isinstance(manifest.get('terms_version'), str) or not manifest['terms_version']
            or route.get('windows_runtime_or_gui_validation') != 'NOT_RUN'):
        raise ValueError('Microsoft route product/version or observation scope differs')
    authorization = route.get('owner_authorization', {})
    if (authorization.get('author') != 'hnt119' or authorization.get('author_association') != 'OWNER'
            or authorization.get('comment_id') != 6458287082
            or authorization.get('comment_url') != 'https://github.com/hnt119/lit-rev-engine/issues/18#issuecomment-6458287082'):
        raise ValueError('Microsoft route does not retain the recorded owner authorization')
    assessment = route.get('assessment', {})
    for key, expected_flag in {'documented_conditional_routes_reviewed': True, 'owner_selected_downstream_routes': True,
            'personal_developer_license_claimed': False, 'private_upstream_contract_assent_independently_verified': False,
            'generic_runtime_or_buildtools_eula_used_as_redistribution_grant': False, 'legal_certification': False}.items():
        if assessment.get(key) is not expected_flag: raise ValueError('Microsoft route qualification claim differs')
    selected = route.get('selected_routes')
    if (not isinstance(selected, list) or len(selected) != 2 or any(not isinstance(row, dict) for row in selected)
            or {row.get('id') for row in selected} != {'electron45_sdk_d3d_downstream', 'python31215_crt_downstream'}):
        raise ValueError('Microsoft route selection differs')
    binaries = route.get('exact_binaries')
    if not isinstance(binaries, dict) or set(binaries) != {'d3dcompiler_47.dll', 'resources/python/vcruntime140.dll', 'resources/python/vcruntime140_1.dll'}:
        raise ValueError('Microsoft component binary scope differs')
    for name, row in binaries.items():
        path = ordinary(payload / name)
        if row != {'bytes': path.stat().st_size, 'sha256': sha(path)}: raise ValueError('Microsoft route binary bytes differ')
    combined = b'\xef\xbb\xbf'
    for title, data in [('Microsoft-component protective terms', raw['component_terms']),
            ('Complete retained Windows SDK license — readable conversion; original LICENSE.rtf retained alongside', raw['complete_sdk_license_readable']),
            ('Complete retained Python license, including Additional Conditions for this Windows binary build', raw['complete_python_license'])]:
        combined += ('\n\n===== ' + title + ' =====\n\n').encode() + data
    copies = {'terms': raw['component_terms'], 'input_manifest': manifest_file.read_bytes(),
        'route_record': raw_route, 'displayed_and_retained': combined}
    actual_names = {path.relative_to(payload).as_posix() for path in (payload / 'resources').iterdir()
        if path.name.casefold().startswith('microsoft_component_')}
    if actual_names != set(TERMS_FILES.values()): raise ValueError('Missing or extra Microsoft component terms outputs')
    for name, data in copies.items():
        if ordinary(payload / TERMS_FILES[name]).read_bytes() != data:
            raise ValueError('Packaged Microsoft component terms differ: ' + name)
    expected = {'schema': 'litrev.windows.microsoft-component-terms.v1',
        'scope': 'Microsoft components only; engine MIT, Python, FFmpeg and other independent terms unchanged',
        'inputs': actual, 'silent_installation': 'rejected; no unattended acceptance flag', 'windows_interaction': 'NOT_RUN'}
    for name, data in copies.items():
        expected[name + '_path'] = TERMS_FILES[name]
        expected[name + '_sha256'] = hashlib.sha256(data).hexdigest()
    expected['displayed_and_retained_bytes'] = len(combined)
    if record != expected: raise ValueError('Microsoft component receipt fields or hashes differ')
    return {'status': 'PASS', 'displayed_and_retained_bytes': len(combined),
        'displayed_and_retained_sha256': hashlib.sha256(combined).hexdigest(),
        'input_manifest_sha256': sha(manifest_file), 'route_record_sha256': sha(route_file),
        'terms_version': manifest['terms_version'], 'owner_authorization_recorded': authorization['comment_url'],
        'packaged_files': list(TERMS_FILES.values()), 'input_roles': sorted(roles),
        'scope': 'Exact owner-approved text, source pins and recorded downstream routes; not personal Visual Studio ownership, private upstream-contract certification or observed Windows acceptance',
        'windows_interaction': 'NOT_RUN'}


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
    subset = verify_pywin32_subset(payload, metadata)
    terms = verify_component_terms(payload, metadata)
    if metadata.get('version') == TERMS_VERSION:
        if (metadata.get('native_build_number') != '3003' or value.get('native_build_number') != '3003'
                or product.get('build_number') != 3003):
            raise ValueError('Windows component terms release build binding differs')
    site = payload / 'resources/python/Lib/site-packages'
    for package in ('fastapi', 'uvicorn', 'pydantic', 'pydantic_core', 'starlette', 'anyio'):
        ordinary(site / package / '__init__.py')
    if not list((site / 'pydantic_core').glob('*cp312-win_amd64.pyd')): raise ValueError('Missing Windows CPython pydantic-core extension')
    bootstrap = (site / 'win32/lib/pywin32_bootstrap.py').read_text()
    pth = (site / 'pywin32.pth').read_text().replace('\\', '/')
    if 'win32/lib' not in pth.splitlines() or 'import pywin32_bootstrap' not in pth: raise ValueError('Missing pywin32 startup path declaration')
    if 'pywin32_system32' not in bootstrap or 'add_dll_directory' not in bootstrap: raise ValueError('Missing pywin32 wheel-local DLL bootstrap')
    imports = source_import_guard(payload / 'resources/engine')
    deps = dependency_closure(site); native = native_closure(payload, value['files'])
    failures = deps['failures'] + ['Unresolved DLL: ' + row['path'] + ':' + row['dll'] for row in native['unresolved']]
    result = {'schema': 'litrev.windows.static-package-audit.v1', 'status': 'FAIL' if failures else 'PASS', 'source_commit': expected,
        'scope': 'Static byte/config/dependency/package audit only; not Windows or installation qualification',
        'payload_files': len(value['files']), 'manifest_sha256': sha(payload / 'INSTALLATION.json'),
        'core_required_files': {'status': 'PASS', 'scope': 'File presence and byte-bound headers only; not Core execution or complete dynamic loading', 'paths': ['LiteratureReviewEngine.exe', *CORE_FILES]},
        'application_imports': imports,
        'optional_pywin32_subset': subset,
        'microsoft_component_terms': terms,
        'declared_dependencies': {'status': 'FAIL' if deps['failures'] else 'PASS', 'scope': 'Windows CPython3.12 AMD64 distribution metadata/markers only'}, 'dependencies': deps, 'native': native,
        'retained_native_imports': {'status': 'FAIL' if native['unresolved'] else 'PASS',
            'scope': 'All retained non-auxiliary PE import and delay-import names; static search paths and explicit OS/API-set exceptions only, not runtime export/loader verification',
            'pe_files': len(native['files']), 'unresolved_edges': len(native['unresolved'])},
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
