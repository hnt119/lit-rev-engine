"""Build one run-bound installer-only candidate; always emit sanitized evidence."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import zipfile

from trial import BASE, VERSION, SOURCE, SHA, BYTES, check
from candidate_receipt import CANDIDATE_ID, COMPILER_SHA, MANIFEST_SHA, digest, load_candidate

REPORT = {'schema': 'litrev.issue18.build.v2', 'phase': 'initialization',
          'checks': {x: 'NOT_RUN' for x in ('source', 'original_installer', 'compiler',
              'native_path_regression', 'payload', 'agreement_include', 'preprocessor', 'build', 'receipt')},
          'infrastructure_sha': os.environ.get('GITHUB_SHA', 'missing'),
          'run_id': os.environ.get('GITHUB_RUN_ID', 'missing')}


def phase(name):
    REPORT['phase'] = name


def passed(name):
    REPORT['checks'][name] = 'PASS'


def command(args, **kwargs):
    result = subprocess.run(list(map(str, args)), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=kwargs.pop('timeout', 180), **kwargs)
    if result.returncode:
        REPORT['command_exit_code'] = result.returncode
        raw = result.stdout + result.stderr
        REPORT['diagnostic'] = ('include_resolution' if b'could not find:' in raw else
            'compiler_error' if b'Error in script' in raw else 'command_failed')
        raise RuntimeError('build_command_failed')
    return result.stdout


def build():
    work = Path(os.environ['RUNNER_TEMP']).resolve() / 'issue18-candidate'
    work.mkdir()  # Reject stale directories/receipts; no overwrite or reuse.
    release = Path(sys.argv[1]).resolve()
    phase('source')
    check(command(['git', '-C', release, 'rev-parse', 'HEAD']).decode().strip() == SOURCE)
    check(not command(['git', '-C', release, 'status', '--porcelain']).strip())
    passed('source')
    phase('original_installer')
    installer = work / 'published-Setup.exe'
    urllib.request.urlretrieve(BASE + f'lit-rev-engine-{VERSION}-windows-x64-Setup.exe', installer)
    check(installer.stat().st_size == BYTES and digest(installer) == SHA)
    REPORT['original_download_zone_identifier'] = Path(str(installer) + ':Zone.Identifier').exists()
    passed('original_installer')
    phase('compiler')
    sdk_zip = work / 'nsis-3.13.zip'
    urllib.request.urlretrieve('https://prdownloads.sourceforge.net/nsis/nsis-3.13.zip', sdk_zip)
    check(digest(sdk_zip) == COMPILER_SHA)
    with zipfile.ZipFile(sdk_zip) as archive:
        check(all(not Path(x.filename).is_absolute() and '..' not in Path(x.filename).parts for x in archive.infolist()))
        archive.extractall(work / 'sdk')
    sdk = work / 'sdk' / 'nsis-3.13'
    compiler = sdk / 'makensis.exe'
    check(compiler.is_file())
    env = dict(os.environ, NSISDIR=str(sdk))
    check(command([compiler, '-VERSION'], env=env).decode().strip() == 'v3.13')
    passed('compiler')
    phase('native_path_regression')
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
    command([compiler, '-V2', probe], cwd=work, env=env)
    command([work / 'root-regression.exe'], timeout=30)
    passed('native_path_regression')
    phase('payload')
    payload_dir = work / 'extracted'
    command(['7z.exe', 'x', installer, '-o' + str(payload_dir), '-y'])
    manifests = list(payload_dir.rglob('INSTALLATION.json'))
    check(len(manifests) == 1 and digest(manifests[0]) == MANIFEST_SHA)
    payload = manifests[0].parent
    manifest = json.loads(manifests[0].read_text(encoding='utf-8'))
    check(manifest['source_commit'] == SOURCE and manifest['version'] == VERSION)
    check({p.relative_to(payload).as_posix() for p in payload.rglob('*') if p.is_file()} == set(manifest['files']) | {'INSTALLATION.json'})
    for name, entry in manifest['files'].items():
        file = payload / name
        check(file.resolve().is_relative_to(payload.resolve()))
        check(file.stat().st_size == entry['bytes'] and digest(file) == entry['sha256'])
    REPORT['payload_file_count'] = len(manifest['files'])
    passed('payload')
    phase('agreement_include')
    source_file = release / 'apps/desktop/installer.nsi'
    include = source_file.with_name('windows-license-page.nsh')
    original_hash = digest(source_file)
    committed_include = command(['git', '-C', release, 'show', SOURCE + ':apps/desktop/windows-license-page.nsh'])
    check(include.read_bytes() == committed_include)
    terms = payload / 'resources/MICROSOFT_COMPONENT_TERMS_WITH_LICENSES.txt'
    check(digest(terms) == 'a50f7dbc673f7995358ba1b3c26dfafd963296a109ca449a29daa46d367fbf05')
    patch = Path(__file__).with_name('installer-root.patch').resolve()
    command(['git', '-C', release, 'apply', '--check', patch])
    command(['git', '-C', release, 'apply', patch])
    check(include.read_bytes() == committed_include)
    passed('agreement_include')
    candidate = work / (CANDIDATE_ID + '-Setup.exe')
    # Exactly the release helper's options/defines/script, with -PPO added.
    # Both preprocessor and full helper run from the actual include directory.
    args = [compiler, '-V2', '-NOCD', '-DPRODUCT_VERSION=' + VERSION,
        '-DPAYLOAD_MANIFEST_SHA=' + MANIFEST_SHA, '-DPAYLOAD=' + str(payload),
        '-DOUTPUT_FILE=' + str(candidate), source_file]
    phase('preprocessor')
    preprocessed = command([*args[:-1], '-PPO', args[-1]], cwd=source_file.parent, env=env)
    for required in (b'LitRevMicrosoftTermsShow', b'LitRevMicrosoftTermsLeave',
                     b'GetFullPathNameW', b'root_invalid_', b'GetFileAttributesW'):
        check(required in preprocessed)
    passed('preprocessor')
    phase('build')
    # Invoke the existing release helper in a bounded child so a compiler error
    # cannot publish raw output/tracebacks. The application payload is untouched.
    code = ('import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);'
            'from scripts.build_desktop_installers import make_windows_installer;'
            'make_windows_installer(*map(Path,sys.argv[2:]))')
    command([sys.executable, '-c', code, release, payload, candidate, compiler, sdk],
            cwd=source_file.parent, env=env, timeout=900)
    check(candidate.is_file())
    passed('build')
    receipt = {'schema': 'litrev.issue18.candidate.v2', 'candidate_id': CANDIDATE_ID,
        'candidate_path': str(candidate), 'installer_sha256': digest(candidate),
        'installer_bytes': candidate.stat().st_size, 'application_source': SOURCE,
        'application_version': VERSION, 'installer_base_source': SOURCE,
        'repair_infrastructure_sha': os.environ['GITHUB_SHA'],
        'run_id': os.environ['GITHUB_RUN_ID'], 'run_attempt': os.environ['GITHUB_RUN_ATTEMPT'],
        'original_nsis_sha256': original_hash, 'repaired_nsis_sha256': digest(source_file),
        'original_installer_sha256': SHA, 'payload_files_verified_unchanged': len(manifest['files']),
        'installation_manifest_sha256': MANIFEST_SHA, 'repair_patch_sha256': digest(patch),
        'agreement_include_sha256': digest(include), 'terms_sha256': digest(terms),
        'compiler': 'official NSIS 3.13 Windows portable', 'compiler_zip_sha256': COMPILER_SHA,
        'compiler_executable_sha256': digest(sdk / 'Bin/makensis.exe'),
        'native_root_regression': 'PASS', 'preprocessor': 'PASS', 'payload_verification': 'PASS',
        'build': 'PASS', 'upgrade': 'NOT_RUN; same application version',
        'distribution': 'ephemeral test candidate only; not published'}
    phase('receipt')
    with (work / 'candidate.json').open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream)
    load_candidate(work / 'candidate.json')
    REPORT['candidate'] = {k: v for k, v in receipt.items() if k != 'candidate_path'}
    passed('receipt')


def main():
    started = time.monotonic()
    result = 0
    try:
        build()
    except Exception as error:
        result = 1
        REPORT['checks'][REPORT['phase']] = 'FAIL'
        REPORT['failure_type'] = type(error).__name__
    finally:
        REPORT['elapsed_seconds'] = round(time.monotonic() - started, 1)
        folder = Path(os.environ['RUNNER_TEMP']) / 'issue18-report'
        folder.mkdir(exist_ok=True)
        (folder / 'build-report.json').write_text(json.dumps(REPORT, indent=2), encoding='utf-8')
        (folder / 'build-summary.md').write_text('# Candidate build\n\n```json\n' + json.dumps(REPORT, indent=2) + '\n```', encoding='utf-8')
        print(json.dumps(REPORT), flush=True)
    return result


if __name__ == '__main__':
    raise SystemExit(main())
