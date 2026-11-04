"""Recompile only the NSIS wrapper around the verified, unchanged public payload.

No payload/source substitution, extraction launch, release upload, or silent
agreement. The separate tiny regression executable installs nothing.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import zipfile

from trial import BASE, VERSION, SOURCE, SHA, BYTES, digest, check

work = Path(os.environ['RUNNER_TEMP']) / 'issue18-candidate'
work.mkdir()
release = Path(sys.argv[1]).resolve()
check(subprocess.check_output(['git', '-C', str(release), 'rev-parse', 'HEAD'], text=True).strip() == SOURCE)
installer = work / 'published-Setup.exe'
urllib.request.urlretrieve(BASE + f'lit-rev-engine-{VERSION}-windows-x64-Setup.exe', installer)
check(installer.stat().st_size == BYTES and digest(installer) == SHA)
sdk_zip = work / 'nsis-3.13.zip'
urllib.request.urlretrieve('https://prdownloads.sourceforge.net/nsis/nsis-3.13.zip', sdk_zip)
check(digest(sdk_zip) == 'ba63dffc4410ee89193e1cb5a41989991bd77c61068da17e3156d136b7b0b3d8')
with zipfile.ZipFile(sdk_zip) as archive:
    check(all(not Path(x.filename).is_absolute() and '..' not in Path(x.filename).parts for x in archive.infolist()))
    archive.extractall(work / 'sdk')
sdk = work / 'sdk' / 'nsis-3.13'
compiler = sdk / 'makensis.exe'
check(compiler.is_file())
env = dict(os.environ, NSISDIR=str(sdk))

probe = work / 'root-regression.nsi'
probe.write_text(r'''Unicode true
!include "WinMessages.nsh"
Name "Issue 18 path regression only"
OutFile "root-regression.exe"
RequestExecutionLevel user
Function .onInit
  StrCpy $2 "$TEMP\issue18 absent regression leaf"
  IfFileExists "$2" failed
  GetFullPathName $0 "$2"
  StrCmp $0 "" 0 failed
  System::Call 'kernel32::GetFullPathNameW(w r2, i ${NSIS_MAX_STRLEN}, w .r1, p 0)i.r5'
  IntCmp $5 0 failed failed +1
  IntCmp $5 ${NSIS_MAX_STRLEN} failed +1 failed
  StrCmp $1 $2 0 failed
  ; Also exercise an existing directory; no creation or permission changes.
  System::Call 'kernel32::GetFullPathNameW(w "$TEMP", i ${NSIS_MAX_STRLEN}, w .r1, p 0)i.r5'
  StrCmp $1 "$TEMP" 0 failed
  SetErrorLevel 0
  Quit
  failed:
  SetErrorLevel 31
  Quit
FunctionEnd
Section
SectionEnd
''', encoding='utf-8-sig')
subprocess.run([compiler, '-V2', probe], cwd=work, env=env, check=True, timeout=120)
subprocess.run([work / 'root-regression.exe'], check=True, timeout=30)
print('PASS: native NSIS original missing-leaf reproduction; Windows API missing/existing-path regression', flush=True)

payload_dir = work / 'extracted'
subprocess.run(['7z.exe', 'x', str(installer), '-o' + str(payload_dir), '-y'],
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=180)
manifests = list(payload_dir.rglob('INSTALLATION.json'))
check(len(manifests) == 1)
payload = manifests[0].parent
manifest = json.loads(manifests[0].read_text(encoding='utf-8'))
check(manifest['source_commit'] == SOURCE and manifest['version'] == VERSION)
check({p.relative_to(payload).as_posix() for p in payload.rglob('*') if p.is_file()} == set(manifest['files']) | {'INSTALLATION.json'})
for name, entry in manifest['files'].items():
    file = payload / name
    check(file.resolve().is_relative_to(payload.resolve()))
    check(file.stat().st_size == entry['bytes'] and digest(file) == entry['sha256'])
source_file = release / 'apps/desktop/installer.nsi'
original_hash = digest(source_file)
patch = Path(__file__).with_name('installer-root.patch').resolve()
subprocess.run(['git', '-C', release, 'apply', '--check', patch], check=True)
subprocess.run(['git', '-C', release, 'apply', patch], check=True)
sys.path.insert(0, str(release))
from scripts.build_desktop_installers import make_windows_installer
candidate = work / 'issue18-installer-root-rc1-Setup.exe'
make_windows_installer(payload, candidate, compiler, sdk)
receipt = {'candidate_id': 'issue18-installer-root-rc1', 'candidate_path': str(candidate),
    'installer_sha256': digest(candidate), 'installer_bytes': candidate.stat().st_size,
    'application_source': SOURCE, 'application_version': VERSION,
    'installer_base_source': SOURCE, 'repair_infrastructure_sha': os.environ['GITHUB_SHA'],
    'original_nsis_sha256': original_hash, 'repaired_nsis_sha256': digest(source_file),
    'original_installer_sha256': SHA, 'payload_files_verified_unchanged': len(manifest['files']),
    'installation_manifest_sha256': digest(manifests[0]), 'repair_patch_sha256': digest(patch),
    'compiler': 'official NSIS 3.13 Windows portable', 'compiler_zip_sha256': digest(sdk_zip),
    'native_root_regression': 'PASS', 'upgrade': 'NOT_RUN; same application version',
    'distribution': 'ephemeral test candidate only; not published'}
(work / 'candidate.json').write_text(json.dumps(receipt), encoding='utf-8')
print(json.dumps({k: v for k, v in receipt.items() if k != 'candidate_path'}), flush=True)
