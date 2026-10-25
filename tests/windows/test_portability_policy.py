"""Policy/unit boundaries; these are never represented as native Windows proof."""
from types import SimpleNamespace
import pytest


def test_mapped_network_ntfs_is_rejected_before_volume_query_or_file_access(monkeypatch):
    from src.platform_support import windows
    calls = []
    api = SimpleNamespace(GetVolumeInformation=lambda *_: pytest.fail('Remote-drive rejection must precede volume metadata and files'))
    con = SimpleNamespace(DRIVE_FIXED=3)
    file = SimpleNamespace(GetDriveType=lambda drive: calls.append(drive) or 4)
    monkeypatch.setattr(windows, 'require_runtime', lambda: (None, api, con, file, None, None, None, None, None))
    with pytest.raises(ValueError, match='fixed local drive'): windows._require_ntfs('Z:\\')
    assert calls == ['Z:\\']


def test_only_fixed_ntfs_is_accepted_and_drive_type_is_not_cached(monkeypatch):
    from src.platform_support import windows
    drive_type = [3]
    calls = []
    api = SimpleNamespace(GetVolumeInformation=lambda drive: calls.append(drive) or ('label', 1, 255, 0, 'NTFS'))
    con = SimpleNamespace(DRIVE_FIXED=3)
    file = SimpleNamespace(GetDriveType=lambda drive: drive_type[0])
    monkeypatch.setattr(windows, 'require_runtime', lambda: (None, api, con, file, None, None, None, None, None))
    windows._require_ntfs('Z:\\')
    drive_type[0] = 4
    with pytest.raises(ValueError): windows._require_ntfs('Z:\\')
    assert calls == ['Z:\\']


class NativeError(Exception):
    def __init__(self, code):
        self.winerror = code
        super().__init__(code, 'synthetic native API error')


def test_pywintypes_error_categories_are_translated_without_paths_or_unsafe_fallback(monkeypatch):
    from src.platform_support import windows
    monkeypatch.setattr(windows, 'require_runtime', lambda: (SimpleNamespace(error=NativeError),))
    @windows.native_errors
    def operation(code): raise NativeError(code)
    for code, expected in [(2,FileNotFoundError),(3,FileNotFoundError),(5,PermissionError),
            (183,FileExistsError),(33,BlockingIOError),(87,OSError)]:
        with pytest.raises(expected) as error: operation(code)
        assert error.value.winerror == code


def test_missing_attributes_are_not_interpreted_as_reparse_flags(monkeypatch, tmp_path):
    from src.platform_support import windows
    def attributes(path):
        if path == str(tmp_path / 'new-private-directory'): raise NativeError(2)
        return 0
    types = SimpleNamespace(error=NativeError)
    api = SimpleNamespace(GetFileAttributes=attributes)
    con = SimpleNamespace(FILE_ATTRIBUTE_REPARSE_POINT=0x400)
    file = SimpleNamespace(GetFileAttributes=lambda *_: pytest.fail('Do not use the raw DWORD sentinel wrapper'))
    monkeypatch.setattr(windows, 'require_runtime', lambda: (types,api,con,file))
    monkeypatch.setattr(windows, '_full', lambda path:path)
    monkeypatch.setattr(windows, '_native', str)
    path = tmp_path / 'new-private-directory'
    assert windows.assert_no_reparse(path) == path
    api.GetFileAttributes = lambda *_: 0x400
    with pytest.raises(ValueError): windows.assert_no_reparse(path)


def test_job_uses_a_random_protected_name_for_pinned_string_only_api(monkeypatch):
    from src.platform_support import windows, processes
    calls=[]
    class Job:
        JobObjectExtendedLimitInformation=9
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE=0x2000
        def CreateJobObject(self,attributes,name):
            assert attributes == 'protected-SID-fixture'
            assert isinstance(name,str) and name.startswith('Local\\litrev-owned-')
            calls.append(name);return 'handle-fixture'
        def QueryInformationJobObject(self,*_):return {'BasicLimitInformation':{'LimitFlags':0}}
        def SetInformationJobObject(self,handle,kind,limits):assert limits['BasicLimitInformation']['LimitFlags']==0x2000
    monkeypatch.setattr(windows, 'require_runtime', lambda: (SimpleNamespace(error=NativeError),None,None,None,None,None,None,Job(),None))
    monkeypatch.setattr(windows, 'security_attributes', lambda:'protected-SID-fixture')
    processes.WindowsJob();processes.WindowsJob()
    assert len(calls)==2 and calls[0]!=calls[1]


def test_windowless_attached_console_is_not_reallocated():
    from tests.windows.run_source_acceptance import ensure_terminal_console
    kernel = SimpleNamespace(GetConsoleProcessList=lambda *_: 3,
        AllocConsole=lambda: pytest.fail('An attached console must not be replaced'))
    assert ensure_terminal_console(kernel, get_error=lambda: 0, error_factory=lambda code:OSError(code,'fixture')) == (False,3)


def test_only_an_explicitly_absent_console_can_be_allocated():
    from tests.windows.run_source_acceptance import ensure_terminal_console
    states = iter([0,1]); called=[]
    kernel = SimpleNamespace(GetConsoleProcessList=lambda *_: next(states),
        AllocConsole=lambda: called.append('allocate') or True,
        FreeConsole=lambda: pytest.fail('Do not free the successfully attached fixture early'))
    assert ensure_terminal_console(kernel, get_error=lambda:6, error_factory=lambda code:OSError(code,'fixture')) == (True,1)
    assert called == ['allocate']


def test_console_access_denial_is_not_treated_as_absence():
    from tests.windows.run_source_acceptance import ensure_terminal_console
    kernel = SimpleNamespace(GetConsoleProcessList=lambda *_: 0,
        AllocConsole=lambda:pytest.fail('Unknown/denied console state must fail closed'))
    with pytest.raises(OSError) as error:
        ensure_terminal_console(kernel, get_error=lambda:5, error_factory=lambda code:OSError(code,'fixture'))
    assert error.value.errno == 5


def test_browser_failure_report_keeps_only_static_substep_status_and_counts():
    import json
    from tests.windows.run_source_acceptance import ValidationCommandError
    raw = {'status':'FAIL','browser_step':'prepare-three-selected-papers','last_preparation_status':'failed',
        'error_type':'Error','error_code':'preparation-ui-failure',
        'question':'PRIVATE_FIXTURE_MUST_NOT_APPEAR','cookie':'PRIVATE_FIXTURE_COOKIE',
        'diagnostics':{'page':'discover','alert_count':1,'board_form_present':False,
            'ready_action_present':True,'url':'http://private.invalid/secret'}}
    error = ValidationCommandError(SimpleNamespace(returncode=1,stderr=json.dumps(raw).encode()))
    assert error.detail['browser_step']=='prepare-three-selected-papers'
    assert error.detail['browser_error_type']=='Error'
    assert error.detail['browser_error_code']=='preparation-ui-failure'
    assert error.detail['last_preparation_status']=='failed'
    assert error.detail['browser_state']=={'page':'discover','alert_count':1,'board_form_present':False,'ready_action_present':True}
    assert 'PRIVATE_FIXTURE' not in json.dumps(error.detail) and 'private.invalid' not in json.dumps(error.detail)


@pytest.mark.parametrize('unsafe_code',[{'private':'PRIVATE_FIXTURE'},'PRIVATE_FIXTURE_ERROR'])
def test_browser_failure_report_rejects_nonstatic_error_codes(unsafe_code):
    import json
    from tests.windows.run_source_acceptance import ValidationCommandError
    error=ValidationCommandError(SimpleNamespace(returncode=1,stderr=json.dumps({
        'status':'FAIL','error_type':'PRIVATE_FIXTURE_TYPE','error_code':unsafe_code}).encode()))
    assert 'browser_error_code' not in error.detail
    assert 'browser_error_type' not in error.detail
    assert 'PRIVATE' not in json.dumps(error.detail)
