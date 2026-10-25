#!/usr/bin/env python3
"""Actual Windows extracted-source gate. Only public/synthetic disposable data.

Never uploads its private QA root. Prints a bounded nonsecret status report;
cookies, source payloads, exports, model files and subprocess output stay local.
"""
import argparse
from hashlib import sha256
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.platform_support import private_directory, owned_path, is_process_alive, venv_python
from src.platform_support.processes import pnpm_argv

PHASE = 'initialization'


def phase(name):
    global PHASE
    PHASE = name
    print(json.dumps({'windows_validation_phase': name}), flush=True)


class ValidationCommandError(RuntimeError):
    def __init__(self, result):
        raw = result.stderr[-32768:]
        self.detail = {'phase': PHASE, 'exit_code': result.returncode,
            'software_error_types': sorted(set(value.decode() for value in re.findall(
                rb'\b(?:ModuleNotFoundError|AttributeError|PermissionError|UnicodeEncodeError|UnicodeDecodeError|ValueError|RuntimeError|OSError|TimeoutError)\b', raw))),
            'windows_error_codes': sorted(set(int(value) for value in re.findall(rb'\[WinError ([0-9]{1,6})\]', raw)))}
        super().__init__('Owned validation command failed; see the sanitized phase/exit-code report.')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def command(argv, *, cwd=ROOT, timeout=1200, env=None, output=None):
    result = subprocess.run([str(v) for v in argv], cwd=cwd, env=env, capture_output=True, timeout=timeout)
    if output: Path(output).write_bytes(result.stdout + b'\n' + result.stderr)
    # Never echo a backend packet, cookie, credential or private machine path.
    if result.returncode: raise ValidationCommandError(result)
    return result.stdout


def free_pair():
    sockets = [socket.socket(), socket.socket()]
    try:
        for item in sockets: item.bind(('127.0.0.1', 0))
        return [item.getsockname()[1] for item in sockets]
    finally:
        for item in sockets: item.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', action='store_true', help='Explicit official pinned existing-pack downloads and CPU checks')
    parser.add_argument('--playwright-dir', type=Path, help='Explicit disposable pinned browser-test tools; never an app dependency')
    args = parser.parse_args()
    if os.name != 'nt': parser.error('Actual Windows execution required; this is not a cross-platform simulation.')
    from src.platform_support.windows import require_runtime
    require_runtime()
    # GitHub's worker may have no console. Explicitly create this disposable
    # terminal fixture so CTRL_BREAK tests the source CLI's normal terminal
    # route. This is test-only, never hidden production-console allocation.
    import ctypes
    console_fixture = False
    if not ctypes.windll.kernel32.GetConsoleWindow():
        if not ctypes.windll.kernel32.AllocConsole(): raise ctypes.WinError()
        console_fixture = True
    commit = command(['git', 'rev-parse', 'HEAD']).decode().strip()
    qa = private_directory(Path(tempfile.mkdtemp(prefix='litrev-windows-', dir=os.environ['RUNNER_TEMP'])))
    report = {'schema': 'litrev.windows-source-acceptance.v1', 'source_commit': commit,
        'status': 'FAIL', 'platform': sys.platform, 'architecture': __import__('platform').machine(),
        'models': [], 'live_providers': 'NOT_RUN', 'generation': 'NOT_RUN',
        'research_usefulness': 'NOT_RUN', 'native_desktop': 'NOT_RUN', 'actual_browser': 'NOT_RUN',
        'private_artifacts_uploaded': False, 'checks': {}}
    report['terminal_console_fixture_allocated'] = console_fixture
    process = None; log = None; started = time.monotonic()
    try:
        phase('clean-source-package-and-independent-audit')
        package = load('windows_package', ROOT / 'scripts/build_local_preview.py')
        built = package.build(ROOT, qa / 'assets', expected_source_commit=commit)
        audit = load('windows_audit', ROOT / 'tests/local_distribution/audit_source_archive.py')
        checked = audit.audit(built['archive'], commit, ROOT)
        report['package'] = {k: checked[k] for k in ('archive_sha256', 'archive_bytes', 'files', 'source_snapshot_exact', 'all_payload_files_match_commit')}
        app_parent = private_directory(qa / 'Extracted 应用 with spaces')
        with zipfile.ZipFile(built['archive']) as archive: archive.extractall(app_parent)
        app = app_parent / package.NAME
        script = app / 'scripts/local_preview.py'
        env = dict(os.environ)
        for name in ('PYTHONHOME', 'PYTHONPATH', 'NODE_OPTIONS', 'NODE_EXTRA_CA_CERTS'):
            env.pop(name, None)
        env.update(MVP_DEPLOYMENT_MODE='hosted', MVP_PUBLIC_ORIGIN='https://invalid.example.test',
            MVP_MAP_ENABLED='1', MVP_SEARCH_PLANNER_ENABLED='1', MVP_PROPOSALS_ENABLED='1',
            OPENAI_API_KEY='PUBLIC_SOFTWARE_FIXTURE_NOT_A_KEY', NCBI_EMAIL='')
        setup = [sys.executable, script, 'setup'] + (['--with-retrieval'] if args.models else [])
        phase('fresh-extracted-production-setup')
        setup_start = time.monotonic(); command(setup, cwd=app, env=env, output=qa / 'setup.log', timeout=1800)
        report['checks']['fresh_setup_seconds'] = round(time.monotonic() - setup_start, 3)
        app_python = venv_python(app / '.venv-preview')
        assert app_python.is_file()
        data = qa / 'Research 数据 with spaces'; api, web = free_pair()
        origin, api_origin = f'http://localhost:{web}', f'http://127.0.0.1:{api}'
        log = (qa / 'launcher.log').open('ab')
        launch_args = [sys.executable, script, 'launch', '--no-browser', '--data-dir', data,
            '--api-port', str(api), '--web-port', str(web)]
        def start(path=script):
            nonlocal process
            argv = [str(v) for v in launch_args]; argv[1] = str(path)
            process = subprocess.Popen(argv, cwd=path.parents[1], env=env, stdout=log, stderr=log)
            deadline = time.monotonic() + 90
            from scripts.run_web import health_ready
            while time.monotonic() < deadline:
                if process.poll() is not None: raise RuntimeError('Owned launcher exited before readiness.')
                if health_ready(api, '/readyz', {'ready': True}) and health_ready(web, '/healthz', {'status': 'ok'}, 'localhost'):
                    return
                time.sleep(.15)
            raise RuntimeError('Owned production services missed readiness deadline.')
        def stop(path=script):
            command([sys.executable, path, 'stop', '--data-dir', data], cwd=path.parents[1], env=env, timeout=35)
            assert process.wait(timeout=10) == 0
            log.flush()
            summaries = []
            for line in (qa / 'launcher.log').read_text(encoding='utf-8', errors='replace').splitlines():
                try: value = json.loads(line)
                except ValueError: continue
                if isinstance(value, dict) and value.get('windows_owned_shutdown'):
                    summaries.append(value['windows_owned_shutdown'])
            assert summaries and summaries[-1]['forced_primaries'] == 0
            assert summaries[-1]['ctrl_break_sent'] == 2 and summaries[-1]['exit_codes'] == [0, 0]
            report['checks']['terminal_graceful_shutdown_without_job_fallback'] = 'PASS'
        phase('production-start-and-owned-readiness')
        ready = time.monotonic(); start()
        report['checks']['production_startup_seconds'] = round(time.monotonic() - ready, 3)
        assert owned_path(data, private=True)
        # Import the existing public acceptance client; do not persist its
        # session cookies or print the returned workspace/source identifiers.
        sys.path.insert(0, str(ROOT / 'tests/local_distribution'))
        acceptance = load('windows_installed_acceptance', ROOT / 'tests/local_distribution/check_installed_preview.py')
        first, second = acceptance.Browser(origin), acceptance.Browser(origin)
        phase('public-production-http-research-and-authorization')
        state = acceptance.create(first, second, api_origin)
        report['checks']['production_http_public_30_papers_3_prepared_9_cells_revision_exports'] = 'PASS'
        report['checks']['host_origin_csrf_separate_session_denials'] = 'PASS'
        def browser_check(mode):
            if args.playwright_dir is None: return
            phase('actual-browser-' + mode)
            node = shutil.which('node')
            raw = command([node, ROOT / 'tests/windows/source_browser.cjs', args.playwright_dir,
                origin, qa, mode], cwd=ROOT, env=env, output=qa / ('browser-' + mode + '.log'), timeout=360)
            assert json.loads(raw.splitlines()[-1])['status'] == 'PASS'
            report['actual_browser'] = 'Chromium via pinned test-only Playwright 1.62.1'
            report['checks']['browser_' + mode] = 'PASS'
        browser_check('create')
        # One process owns this data root; an additional launch must not attach.
        phase('single-instance-and-authenticated-graceful-stop')
        second_launch = subprocess.Popen([str(v) for v in launch_args], cwd=app, env=env, stdout=log, stderr=log)
        assert second_launch.wait(timeout=15) != 0 and process.poll() is None
        report['checks']['single_instance_no_attachment'] = 'PASS'
        saved = first.saved(), second.saved()
        stopped = time.monotonic(); stop()
        report['checks']['authenticated_shutdown_seconds'] = round(time.monotonic() - stopped, 3)
        # Same cookie/session across a genuine process restart.
        phase('restart-reopen-drafts-and-exports')
        start()
        first, second = acceptance.Browser(origin, saved[0]), acceptance.Browser(origin, saved[1])
        acceptance.verify(first, second, state, api_origin)
        browser_check('verify')
        report['checks']['restart_drafts_exports_exact_sources'] = 'PASS'
        # Kill only this owned Popen handle. Its native Job Object must release
        # both service listeners; no stored PID or port is signalled.
        phase('owned-parent-crash-cleanup')
        process.kill(); process.wait(timeout=10)
        from scripts.run_web import check_ports_available
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            try: check_ports_available(api, web); break
            except ValueError: time.sleep(.1)
        check_ports_available(api, web)
        report['checks']['launcher_crash_owned_job_cleanup'] = 'PASS'
        # A foreign listener must not be attached, contacted, or terminated.
        phase('foreign-listener-no-attach-no-kill')
        with socket.socket() as foreign:
            foreign.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            foreign.bind(('127.0.0.1', web)); foreign.listen()
            conflict = subprocess.Popen([str(v) for v in launch_args], cwd=app, env=env, stdout=log, stderr=log)
            assert conflict.wait(timeout=15) != 0
            foreign.settimeout(.5)
            try: foreign.accept(); raise AssertionError('Foreign listener was contacted.')
            except socket.timeout: pass
        report['checks']['foreign_listener_fail_closed'] = 'PASS'
        # Replace every app file by extracting the exact reviewed ZIP afresh,
        # keep data external, then perform the required new-folder setup.
        phase('fresh-replacement-files-production-setup')
        replacement_parent = private_directory(qa / 'Replacement 应用')
        with zipfile.ZipFile(built['archive']) as archive: archive.extractall(replacement_parent)
        replacement = replacement_parent / package.NAME
        replacement_script = replacement / 'scripts/local_preview.py'
        command([sys.executable, replacement_script, 'setup'], cwd=replacement, env=env,
            output=qa / 'replacement-setup.log', timeout=1800)
        start(replacement_script)
        first, second = acceptance.Browser(origin, saved[0]), acceptance.Browser(origin, saved[1])
        acceptance.verify(first, second, state, api_origin)
        browser_check('verify')
        stop(replacement_script)
        report['checks']['replacement_files_external_data_drafts_exports'] = 'PASS'
        # Existing stopped backup engine, private archive, fresh sibling restore.
        phase('stopped-protected-backup-and-new-copy-restore')
        backup_parent = private_directory(qa.parent / (qa.name + '-backups'))
        backup = backup_parent / 'research.tar.gz'; restored = qa / 'Restored 数据'
        command([sys.executable, replacement_script, 'backup', '--data-dir', data, '--output', backup], cwd=replacement, env=env)
        command([sys.executable, replacement_script, 'restore', '--data-dir', data, '--archive', backup,
            '--destination', restored], cwd=replacement, env=env)
        assert owned_path(backup, private=True) and owned_path(restored, private=True)
        report['checks']['stopped_backup_integrity_new_directory_restore'] = 'PASS'
        if args.models:
            cache = qa / 'Optional model cache'
            for profile in ('hybrid_qwen3_06b_rrf_rerank_v1', 'hybrid_medcpt_passage_rrf_rerank_v1'):
                phase('explicit-pinned-cpu-pack-' + profile)
                model_script = app / 'scripts/retrieval_pack.py'
                begin = time.monotonic()
                command([app_python, model_script, 'install', '--cache', cache, '--profile', profile], cwd=app, timeout=2400, output=qa / (profile + '-install.log'))
                raw = command([app_python, model_script, 'check', '--cache', cache, '--profile', profile, '--device', 'cpu'],
                    cwd=app, timeout=1800, output=qa / (profile + '-check.log'))
                status = json.loads(raw); runtime = status['runtime']
                assert status['state'] == 'runtime_passed' and runtime['encoder_executed'] and runtime['reranker_executed']
                report['models'].append({'profile_id': profile, 'status': 'PASS', 'device': 'cpu',
                    'download_and_check_seconds': round(time.monotonic() - begin, 3), 'runtime': runtime})
                command([app_python, model_script, 'remove', '--cache', cache, '--profile', profile], cwd=app, timeout=120)
        report['status'] = 'PASS'
    except BaseException as error:
        report['failure_type'] = type(error).__name__
        report['failure_phase'] = PHASE
        if isinstance(error, ValidationCommandError): report['command_failure'] = error.detail
        if (qa / 'launcher.log').exists():
            raw = (qa / 'launcher.log').read_bytes()[-32768:]
            report['launcher_error_codes'] = sorted(set(v.decode() for v in re.findall(
                rb'\b(?:MODULE_NOT_FOUND|EADDRINUSE|EACCES|EPERM|ModuleNotFoundError|AttributeError|PermissionError|UnicodeEncodeError|UnicodeDecodeError|TimeoutError)\b', raw)))
        raise
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        if log: log.close()
        if console_fixture: ctypes.windll.kernel32.FreeConsole()
        report['seconds'] = round(time.monotonic() - started, 3)
        # Only this sanitized report enters ordinary public CI logs. Runtime
        # metadata contains model IDs/hashes/versions, never cookies/source text.
        print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == '__main__': main()
