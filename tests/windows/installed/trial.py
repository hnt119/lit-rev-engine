"""Issue 18 installed binary trial. Only public fixtures on disposable hosted Windows.

No environment dump, profile upload, security bypass, silent installation, or
renderer/API mutation shortcuts. Reports contain fixed check names and enums.
"""
from __future__ import annotations

import argparse
import csv
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import time
import urllib.request

VERSION = '0.3.0-windows-experimental-beta.2'
SOURCE = '664b86d4ed510c3d16982b5813b27e6bd1150129'
SHA = '75595d013fbdf4694301a00dd0e233a6b53e47c6cf5fb3713d0d0e7aa1e58359'
BYTES = 195492146
BASE = f'https://github.com/hnt119/lit-rev-engine/releases/download/v{VERSION}/'
CHECKS = ('native_desktop_control', 'installer_visible', 'agreement_unchecked',
          'decline_cancel', 'affirmative_install', 'installed_files', 'start_shortcut',
          'uninstall_registration', 'non_admin_install', 'start_shortcut_launch',
          'bundled_runtime_execution', 'installed_driver_compatibility',
          'saved_example_offline', 'source_preparation', 'three_papers_three_fields', 'exact_excerpt_attach',
          'interpretation_submit', 'missing_information', 'draft_distinct',
          'native_json_export', 'native_csv_export', 'independent_export_parse',
          'normal_quit_cleanup', 'reopen_persistence', 'single_instance',
          'foreign_listener_refusal', 'unicode_path', 'uninstall_preservation',
          'reinstall_preservation', 'permission_failure', 'parent_failure',
          'interrupted_optional_setup', 'cleared_cookie_recovery', 'upgrade',
          'non_ascii_username', 'consumer_windows_11', 'browser_download_trust')


class TrialFailure(Exception):
    pass


def wait(predicate, timeout=30):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(.2)
    raise TrialFailure('timeout')


def check(value):
    if not value:
        raise TrialFailure('assertion')


def digest(file):
    with Path(file).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def preflight_window():
    import win32con
    import win32gui
    cls = win32gui.WNDCLASS()
    cls.lpszClassName = 'Issue18NativePreflight'
    def proc(hwnd, msg, wp, lp):
        if msg == win32con.WM_DESTROY:
            win32gui.PostQuitMessage(0)
        return win32gui.DefWindowProc(hwnd, msg, wp, lp)
    cls.lpfnWndProc = proc
    atom = win32gui.RegisterClass(cls)
    hwnd = win32gui.CreateWindow(atom, 'Issue 18 native desktop preflight',
        win32con.WS_OVERLAPPEDWINDOW | win32con.WS_VISIBLE, 80, 80, 500, 200, 0, 0, 0, None)
    win32gui.CreateWindow('Button', 'Disposable control check',
        win32con.WS_CHILD | win32con.WS_VISIBLE | win32con.BS_AUTOCHECKBOX,
        20, 30, 350, 40, hwnd, 1034, 0, None)
    win32gui.PumpMessages()


def native_save(destination):
    from pywinauto import Desktop
    # Real app's dialog title is part of the tag-bound native export contract.
    dlg = Desktop(backend='win32').window(title='Save research export', class_name='#32770')
    dlg.wait('visible', timeout=45)
    # Standard Windows common file dialog, File name edit control.
    edit = dlg.child_window(class_name='Edit', control_id=1001)
    check(edit.exists())
    edit.set_edit_text(str(destination))
    dlg.child_window(control_id=1).click_input()
    wait(lambda: Path(destination).is_file(), 60)


def export_ack():
    from pywinauto import Desktop
    def find():
        for win in Desktop(backend='win32').windows(class_name='#32770'):
            if any('Research export saved' in text for text in win.texts()):
                return Desktop(backend='win32').window(handle=win.handle)
        return None
    dlg = wait(find, 45)
    dlg.child_window(control_id=1).click_input()


def parse_exports(output):
    expected = json.loads((output / 'private-expected-excerpt.json').read_text(encoding='utf-8'))
    folder = output / 'exports with spaces 亚洲'
    audit = json.loads((folder / 'comparison.json').read_text(encoding='utf-8'))
    with (folder / 'comparison.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    check(len(rows) == len(audit['table']) == 9)
    check(len({row['paper_id'] for row in rows}) == 3)
    check(len({row['field_id'] for row in rows}) == 3)
    check(len(audit['cell_revisions']) == 2)
    submitted = next(row for row in audit['table'] if row['value'] == expected['submitted'])
    check(submitted['semantic_assessment'] == 'unassessed')
    check(submitted['reference_integrity'] == 'checked')
    check(bool(submitted['references']))
    for reference in submitted['references']:
        check(reference['paper_id'] == submitted['paper_id'] if 'paper_id' in reference else True)
        check(reference['source_id'] == submitted['source_id'])
        check(reference['source_sha256'] == submitted['source_sha256'])
        check(reference['blocks_sha256'] == submitted['blocks_sha256'])
        check(bool(reference['quote']) and reference['quote'] in expected['excerpt'])
        # Match the export against the independent source-context response the
        # renderer actually read, including half-open Unicode code-point range.
        context = expected['inspectedResponse']
        check(isinstance(context, dict))
        source = context['source']
        check(source['source_id'] == reference['source_id'])
        check(source['version'] == reference['source_version'])
        for key in ('source_sha256', 'blocks_sha256'):
            check(source[key] == reference[key])
        blocks = context.get('blocks', [context.get('block')])
        block = next(b for b in blocks if b and b['block_id'] == reference['block_id'])
        start, end = reference['start'] - block['start'], reference['end'] - block['start']
        check(0 <= start < end <= len(block['text']))
        check(block['text'][start:end] == reference['quote'])
    unresolved = next(row for row in audit['table'] if row['missing_information'] == expected['missing'])
    check(unresolved['value'] is None and unresolved['scope_result'] == 'not_assessed')
    check(not unresolved['references'])
    check(all(row['value'] != expected['draft'] for row in audit['table']))
    check(next(row for row in rows if row['value'] == expected['submitted'])['source_sha256'] == submitted['source_sha256'])
    check(any(row['missing_information'] == expected['missing'] for row in rows))
    check(all(row['value'] != expected['draft'] for row in rows))


class Trial:
    def __init__(self, args):
        self.args = args
        self.report = {'schema': 'litrev.issue18.installed-trial.v1',
            'source_commit': SOURCE, 'installer_sha256': SHA, 'version': VERSION,
            'checks': {name: 'NOT_RUN' for name in CHECKS}, 'phase': 'initialization',
            'instrumentation': ['pywinauto 0.6.9 win32 native controls',
                'Playwright 1.62.1 connectOverCDP; no Electron launcher',
                '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=49228'],
            'model_downloads': 'disabled', 'live_pubmed': 'NOT_RUN', 'generation': 'NOT_RUN'}
        self.root = Path(os.environ['LOCALAPPDATA']) / 'Programs' / 'Literature Review Engine'
        self.app = self.root / f'app-{VERSION}' / 'LiteratureReviewEngine.exe'
        self.data = Path(os.environ['LOCALAPPDATA']) / 'LiteratureReviewEngineDesktop'
        self.owned = []
        self.owns_installation = False
        self.phase = 'initialization'
        self.args.output.mkdir(parents=True, exist_ok=True)

    def begin(self, name):
        self.phase = name
        self.report['phase'] = name
        print(json.dumps({'trial_phase': name}), flush=True)

    def passed(self, name):
        self.report['checks'][name] = 'PASS'

    def spawn(self, argv, **kw):
        proc = subprocess.Popen(list(map(str, argv)), stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, **kw)
        self.owned.append(proc)
        return proc

    def window(self, title):
        from pywinauto import Desktop
        dlg = Desktop(backend='win32').window(title_re=title)
        dlg.wait('visible', timeout=60)
        return dlg

    def installer(self, accept):
        self.spawn([self.installer_file])
        dlg = self.window(r'Literature Review Engine Setup')
        self.passed('installer_visible')
        dlg.child_window(control_id=1).click_input()
        agreement = dlg.child_window(control_id=1034)
        agreement.wait('visible', timeout=20)
        check(agreement.get_check_state() == 0)
        check(not dlg.child_window(control_id=1).is_enabled())
        self.passed('agreement_unchecked')
        if not accept:
            dlg.child_window(control_id=2).click_input()
            # MUI abort confirmation, if enabled, is also a real native control.
            time.sleep(.5)
            from pywinauto import Desktop
            for confirm in Desktop(backend='win32').windows(title='Literature Review Engine Setup', class_name='#32770'):
                yes = Desktop(backend='win32').window(handle=confirm.handle).child_window(control_id=6)
                if yes.exists() and yes.is_visible():
                    yes.click_input()
            wait(lambda: not dlg.exists())
            check(not self.app.exists())
            self.passed('decline_cancel')
            return
        agreement.click_input()
        check(agreement.get_check_state() == 1)
        check(dlg.child_window(control_id=1).is_enabled())
        dlg.child_window(control_id=1).click_input()
        wait(lambda: self.app.is_file(), 180)
        wait(lambda: dlg.child_window(control_id=1).is_enabled(), 180)
        # Finish page run checkbox must remain unselected.
        run = dlg.child_window(control_id=1204)
        if run.exists() and run.is_visible():
            check(run.get_check_state() == 0)
        dlg.child_window(control_id=1).click_input()
        wait(lambda: not dlg.exists())
        self.passed('affirmative_install')

    def app_window(self):
        from pywinauto import Desktop
        return Desktop(backend='win32').window(title='Literature Review Engine', class_name='Chrome_WidgetWin_1')

    def quit(self):
        self.begin('normal_quit_cleanup')
        dlg = self.app_window()
        dlg.wait('visible', timeout=30)
        dlg.close()  # WM_CLOSE follows the installed application's normal lifecycle.
        wait(lambda: not self.app_processes(), 40)
        self.passed('normal_quit_cleanup')

    def app_processes(self):
        import psutil
        result = []
        for proc in psutil.process_iter(['pid', 'exe']):
            try:
                exe = proc.info['exe']
                if exe and Path(exe).is_relative_to(self.root):
                    result.append(proc)
            except (psutil.AccessDenied, psutil.NoSuchProcess, ValueError):
                continue
        return result

    def launch(self, instrumented=True):
        # Keep system/user directory variables only. Developer tools remain on
        # the runner, but are not exposed through the app's inherited PATH.
        env = {k: os.environ[k] for k in ('SystemRoot', 'WINDIR', 'TEMP', 'TMP',
            'USERPROFILE', 'LOCALAPPDATA', 'APPDATA', 'USERNAME', 'HOMEDRIVE', 'HOMEPATH') if k in os.environ}
        env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
        flags = ['--remote-debugging-address=127.0.0.1', '--remote-debugging-port=49228'] if instrumented else []
        self.spawn([self.app, *flags], env=env, cwd=str(self.root))
        self.app_window().wait('visible', timeout=180)
        if instrumented:
            value = wait(self.cdp_version)
            self.report['cdp_browser'] = value.get('Browser', '')[:80]
            self.report['cdp_protocol'] = value.get('Protocol-Version', '')[:20]
        return env

    def cdp_version(self):
        try:
            with urllib.request.urlopen('http://127.0.0.1:49228/json/version', timeout=2) as response:
                return json.load(response)
        except OSError:
            return None

    def browser(self, mode):
        self.begin(mode)
        result = subprocess.run(['node.exe', str(Path(__file__).with_name('journey.cjs')),
            str(self.args.tools), str(self.args.output), mode, sys.executable],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
        # Never print raw driver stderr, URLs, headers or browser state.
        controlled = self.args.output / 'journey-result.json'
        if controlled.exists():
            value = json.loads(controlled.read_text(encoding='utf-8'))
            for name, state in value.get('checks', {}).items():
                if name in CHECKS and state in ('PASS', 'FAIL', 'BLOCKED', 'NOT_RUN'):
                    self.report['checks'][name] = state
            self.report['journey_phase'] = value.get('phase', 'unknown')
            self.report['journey_error_type'] = value.get('error_type', 'none')
        check(result.returncode == 0)

    def uninstall(self):
        self.spawn([self.root / 'Uninstall.exe'])
        dlg = self.window(r'Literature Review Engine Uninstall')
        dlg.child_window(control_id=1).click_input()
        wait(lambda: not self.app.exists(), 180)
        wait(lambda: dlg.child_window(control_id=1).is_enabled(), 180)
        dlg.child_window(control_id=1).click_input()
        wait(lambda: not dlg.exists())

    def run(self):
        import winreg
        from pywinauto import Desktop
        import win32api
        import win32con
        import win32security
        self.begin('native_desktop_control')
        token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
        elevated = bool(win32security.GetTokenInformation(token, win32security.TokenElevation))
        self.report['host'] = {'os': platform.platform(), 'edition': platform.win32_edition(),
            'architecture': platform.machine(), 'elevated': elevated,
            'runner_image_os': os.environ.get('ImageOS', 'unknown'),
            'runner_image_version': os.environ.get('ImageVersion', 'unknown'),
            'developer_tools_present': True}
        self.report['infrastructure_sha'] = os.environ.get('GITHUB_SHA', 'local-uncommitted')
        self.report['run_id'] = os.environ.get('GITHUB_RUN_ID', 'local')
        self.report['run_attempt'] = os.environ.get('GITHUB_RUN_ATTEMPT', 'local')
        self.begin('download_checksum')
        self.installer_file = Path(os.environ['RUNNER_TEMP']) / 'Issue 18 Setup.exe'
        urllib.request.urlretrieve(BASE + f'lit-rev-engine-{VERSION}-windows-x64-Setup.exe', self.installer_file)
        check(self.installer_file.stat().st_size == BYTES and digest(self.installer_file) == SHA)
        zone = Path(str(self.installer_file) + ':Zone.Identifier')
        self.report['scripted_download_has_zone_identifier'] = zone.exists()
        self.begin('native_desktop_control')
        from ctypes import wintypes
        ctypes.windll.user32.OpenInputDesktop.restype = wintypes.HANDLE
        ctypes.windll.user32.CloseDesktop.argtypes = [wintypes.HANDLE]
        ctypes.windll.user32.GetUserObjectInformationW.argtypes = [wintypes.HANDLE,
            ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        desktop = ctypes.windll.user32.OpenInputDesktop(0, False, 0x0101)
        check(bool(desktop))
        name = ctypes.create_unicode_buffer(256)
        needed = wintypes.DWORD()
        check(ctypes.windll.user32.GetUserObjectInformationW(desktop, 2, name, ctypes.sizeof(name), ctypes.byref(needed)))
        session = wintypes.DWORD()
        check(ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(session)))
        self.report['host']['input_desktop'] = name.value
        self.report['host']['session_id'] = session.value
        ctypes.windll.user32.CloseDesktop(desktop)
        preflight = self.spawn([sys.executable, __file__, '--preflight-window'])
        dlg = self.window('Issue 18 native desktop preflight')
        box = dlg.child_window(control_id=1034)
        check(box.get_check_state() == 0)
        box.click_input()
        check(box.get_check_state() == 1)
        dlg.close()
        check(preflight.wait(timeout=10) == 0)
        self.passed('native_desktop_control')
        self.report['host']['interactive_desktop_control'] = True
        check(not self.root.exists() and not self.data.exists())
        self.owns_installation = True
        self.begin('decline_cancel')
        self.installer(False)
        self.begin('affirmative_install')
        self.installer(True)
        if not elevated:
            self.passed('non_admin_install')
        else:
            self.report['checks']['non_admin_install'] = 'BLOCKED'
        resources = self.app.parent / 'resources'
        release = json.loads((resources / 'DESKTOP_RELEASE.json').read_text(encoding='utf-8'))
        check(release['source_commit'] == SOURCE)
        self.report['packaged_runtime_versions'] = {name: release['runtimes'][name]['version'] for name in ('electron', 'python')}
        manifest = json.loads((self.app.parent / 'INSTALLATION.json').read_text(encoding='utf-8'))
        self.report['installation_manifest_schema'] = manifest.get('schema', '')
        check(manifest['source_commit'] == SOURCE and manifest['version'] == VERSION)
        check(manifest['schema'] == 'litrev.desktop.installed-files.v1')
        for relative, identity in manifest['files'].items():
            target = self.app.parent / relative
            check(target.resolve().is_relative_to(self.app.parent.resolve()))
            check(target.stat().st_size == identity['bytes'] and digest(target) == identity['sha256'])
        check((resources / 'python' / 'python.exe').is_file())
        check(digest(resources / 'MICROSOFT_COMPONENT_TERMS_WITH_LICENSES.txt') ==
              'a50f7dbc673f7995358ba1b3c26dfafd963296a109ca449a29daa46d367fbf05')
        self.passed('installed_files')
        self.shortcut = Path(os.environ['APPDATA']) / 'Microsoft/Windows/Start Menu/Programs/Literature Review Engine/Literature Review Engine.lnk'
        check(self.shortcut.is_file())
        self.passed('start_shortcut')
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r'Software\Microsoft\Windows\CurrentVersion\Uninstall\org.hnt119.litrev.desktop') as key:
            check(winreg.QueryValueEx(key, 'DisplayVersion')[0] == VERSION)
        self.passed('uninstall_registration')
        self.begin('start_shortcut_launch')
        os.startfile(self.shortcut)
        self.app_window().wait('visible', timeout=180)
        self.passed('start_shortcut_launch')
        self.quit()
        self.launch()
        observed = json.loads((self.data / 'desktop-status.json').read_text(encoding='utf-8'))
        self.report['observed_runtime_versions'] = {key: observed.get(key) for key in ('electron', 'chrome', 'node')}
        self.report['observed_startup_ms'] = observed.get('startup_ms')
        executables = sorted({str(Path(proc.exe()).relative_to(self.app.parent)) for proc in self.app_processes()})
        check(any('python' in x.lower() for x in executables))
        check(all((self.app.parent / x).is_file() for x in executables))
        self.report['running_installed_executables'] = executables
        self.passed('bundled_runtime_execution')
        self.browser('create')
        self.begin('single_instance')
        before = len(self.app_processes())
        second = self.spawn([self.app])
        second.wait(timeout=30)
        check(second.returncode == 0)
        check(len(self.app_processes()) <= before)
        self.passed('single_instance')
        self.quit()
        self.launch()
        self.browser('verify')
        self.passed('reopen_persistence')
        self.quit()
        self.begin('uninstall_preservation')
        # Compare disposable retained bytes without uploading any of them.
        retained = {p.relative_to(self.data): digest(p) for p in self.data.rglob('*') if p.is_file()}
        check(bool(retained))
        self.uninstall()
        check(all((self.data / p).is_file() and digest(self.data / p) == h for p, h in retained.items()))
        self.passed('uninstall_preservation')
        self.begin('reinstall_preservation')
        self.installer(True)
        self.launch()
        self.browser('verify')
        self.passed('reinstall_preservation')
        self.quit()
        self.begin('foreign_listener_refusal')
        # Owned test listener; never kill/replace any foreign machine listener.
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 43000))
            listener.listen()
            proc = self.spawn([self.app])
            error = Desktop(backend='win32').window(title='Desktop Preview stopped', class_name='#32770')
            error.wait('visible', timeout=90)
            check(any('ports are in use' in x.lower() for x in error.texts()))
            error.child_window(control_id=1).click_input()
            proc.wait(timeout=40)
            check(listener.getsockname()[1] == 43000)
        self.passed('foreign_listener_refusal')

    def finish(self):
        # Fixed native labels only; never dump arbitrary window text, URLs or
        # renderer contents. Preserve control IDs for diagnosing automation.
        if 'failure' in self.report:
            try:
                from pywinauto import Desktop
                allowed = {'Literature Review Engine Setup', 'Literature Review Engine Uninstall',
                           'Issue 18 native desktop preflight', 'Desktop Preview stopped',
                           'Literature Review Engine'}
                labels = {'&Next >', 'Next >', 'Install', '&Install', 'Cancel', '&Cancel',
                          'Finish', '&Finish', 'OK', '&Yes', '&No'}
                self.report['native_failure_controls'] = [
                    {'window': win.window_text(), 'controls': [
                        {'id': child.control_id(), 'class': child.class_name(),
                         'visible': child.is_visible(), 'enabled': child.is_enabled(),
                         'label': child.window_text() if child.window_text() in labels else 'redacted'}
                        for child in win.descendants()[:40]]}
                    for win in Desktop(backend='win32').windows() if win.window_text() in allowed]
            except Exception:
                self.report['native_diagnostics'] = 'unavailable'
        # Cleanup is constrained to actual installed executable paths and our
        # child processes. No arbitrary PID kill or recursive research upload.
        remaining = self.app_processes() if self.owns_installation else []
        self.report['cleanup'] = {'installed_processes_remaining': len(remaining),
                                  'forced_owned_cleanup': bool(remaining)}
        for proc in remaining:
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except Exception:
                pass
        for proc in self.owned:
            if proc.poll() is None:
                proc.terminate()
        self.report['cleanup']['processes_after_cleanup'] = len(self.app_processes()) if self.owns_installation else 0
        try:
            installed_bytes = sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file())
        except OSError:
            installed_bytes = None
        self.report['resource_usage'] = {'elapsed_seconds': round(time.monotonic() - self.started, 1),
            'installer_bytes': BYTES, 'installed_file_bytes': installed_bytes}
        self.args.output.joinpath('report.json').write_text(json.dumps(self.report, indent=2), encoding='utf-8')
        lines = ['# Issue 18 installed Windows trial', '',
            f'Infrastructure: `{self.report.get("infrastructure_sha", "unknown")}`',
            f'Application source: `{SOURCE}`; version `{VERSION}`',
            f'Installer SHA-256: `{SHA}`', '',
            '```json', json.dumps({k: v for k, v in self.report.items() if k != 'checks'}, indent=2), '```', '',
            '| Acceptance check | Actual result |', '| --- | --- |']
        lines += [f'| {k} | {v} |' for k, v in self.report['checks'].items()]
        lines += ['', 'Windows Server hosted evidence only. Developer tools remain on the runner.',
            'Scripted download is not ordinary browser/SmartScreen qualification. No upgrade or human usefulness claim.',
            'No private profile, cookies, database, raw trace, model, or video is uploaded.']
        self.args.output.joinpath('summary.md').write_text('\n'.join(lines), encoding='utf-8')
        print(json.dumps(self.report), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preflight-window', action='store_true')
    parser.add_argument('--save-dialog', type=Path)
    parser.add_argument('--export-ack', action='store_true')
    parser.add_argument('--parse-exports', type=Path)
    parser.add_argument('--private-export-directory', type=Path)
    parser.add_argument('--tools', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.preflight_window:
        preflight_window()
        return 0
    if args.save_dialog:
        native_save(args.save_dialog)
        return 0
    if args.export_ack:
        export_ack()
        return 0
    if args.parse_exports:
        parse_exports(args.parse_exports)
        return 0
    if args.private_export_directory:
        destination = args.private_export_directory.resolve()
        expected = Path(os.environ['RUNNER_TEMP']).resolve() / 'issue18-report' / 'exports with spaces 亚洲'
        check(destination == expected and not destination.exists())
        # Create only our new disposable output directory with the current SID
        # and protected ACL. Never relax the native writer's destination checks.
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from src.platform_support import private_directory
        private_directory(destination)
        return 0
    if sys.platform != 'win32':
        parser.error('Native Windows required; Linux is not an acceptance substitute')
    trial = Trial(args)
    trial.started = time.monotonic()
    result = 0
    try:
        trial.run()
    except Exception as error:
        result = 1
        if trial.phase in CHECKS:
            trial.report['checks'][trial.phase] = 'FAIL'
        trial.report['failure'] = {'phase': trial.phase, 'type': type(error).__name__,
            'winerror': getattr(error, 'winerror', None),
            'category': 'runner/GUI limitation' if trial.phase == 'native_desktop_control' else 'unclassified; inspect before repair'}
    finally:
        trial.finish()
    return result


if __name__ == '__main__':
    raise SystemExit(main())
