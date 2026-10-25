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


def _model_http_failure(*, phase='loading', kind='os_error', category='memory', os_code='win1455', code='retrieval_model_failed', extra=None):
    import json
    message=('The selected local model failed to execute. Diagnostic: '
        f'phase={phase}; kind={kind}; category={category}; os_code={os_code}'
        '. Inspect the runtime check or select lexical explicitly; no fallback ran.')
    value={'error':{'code':code,'message':message,'retryable':False}}
    if extra:value.update(extra)
    body=json.dumps(value).encode('utf-8')
    return AssertionError(('POST','/PRIVATE/path?credential=PRIVATE_CANARY',422,200,body))


@pytest.mark.parametrize('kind', ['memory_error','os_error','permission_error','file_not_found',
    'blocking_io_error','runtime_error','value_error','type_error','import_error','module_not_found',
    'sqlite_operational_error','sqlite_database_error','unicode_encode_error','unicode_decode_error','unknown'])
def test_http_model_diagnostics_only_project_known_exception_kinds(kind):
    from tests.windows.run_source_acceptance import model_failure_diagnostic
    error=_model_http_failure(phase='execution',kind=kind,category='unknown',os_code='none')
    assert len(error.args[0][-1])<=300
    assert model_failure_diagnostic(error)=={'phase':'execution','kind':kind,'category':'unknown','os_code':'none'}


@pytest.mark.parametrize('phase,kind,category,os_code', [
    ('loading','os_error','memory','win1455'),('execution','runtime_error','memory','none'),
    ('loading','sqlite_operational_error','storage','none'),('execution','sqlite_database_error','storage','none'),
    ('execution','unicode_encode_error','encoding','none'),('loading','unicode_decode_error','encoding','none'),
    ('unknown','unknown','unknown','none')])
def test_http_model_diagnostics_keep_phase_category_and_code_separate(phase,kind,category,os_code):
    from tests.windows.run_source_acceptance import model_failure_diagnostic
    assert model_failure_diagnostic(_model_http_failure(phase=phase,kind=kind,category=category,os_code=os_code))=={
        'phase':phase,'kind':kind,'category':category,'os_code':os_code}


@pytest.mark.parametrize('field',['phase','kind','category','os_code'])
def test_http_model_diagnostics_reject_private_or_unknown_tokens(field):
    import json
    from tests.windows.run_source_acceptance import model_failure_diagnostic,abort_validation
    error=_model_http_failure(**{field:'PRIVATE_CANARY'})
    assert model_failure_diagnostic(error) is None
    report={}
    with pytest.raises(SystemExit) as stopped:abort_validation(report,error)
    assert stopped.value.code==1 and report['status']=='FAIL'
    assert 'model_failure_diagnostic' not in report and 'PRIVATE' not in json.dumps(report)


@pytest.mark.parametrize('change',['truncated_tail','truncated_message','malformed','duplicate','wrong_code','appended_text','oversize','body_string','body_mutable','wrong_method','wrong_status','wrong_expected','wrong_shape','not_http_assertion'])
def test_http_model_diagnostics_fail_closed_for_malformed_or_truncated_packets(change):
    import json
    from tests.windows.run_source_acceptance import model_failure_diagnostic
    error=_model_http_failure();packet=list(error.args[0]);body=packet[-1]
    if change=='truncated_tail':packet[-1]=body[:-1]
    elif change=='truncated_message':packet[-1]=body[:150]
    elif change=='malformed':packet[-1]=b'{"error": [PRIVATE CANARY}'
    elif change=='duplicate':packet[-1]=b'{"error":{},"error":{}}'
    elif change=='wrong_code':return assert_no_model_diagnostic(_model_http_failure(code='other_failure'))
    elif change=='appended_text':
        value=json.loads(body);value['error']['message']+=' PRIVATE_CANARY';packet[-1]=json.dumps(value).encode()
    elif change=='oversize':packet[-1]=body+b' '*(301-len(body))
    elif change=='body_string':packet[-1]=body.decode()
    elif change=='body_mutable':packet[-1]=bytearray(body)
    elif change=='wrong_method':packet[0]='GET'
    elif change=='wrong_status':packet[2]=503
    elif change=='wrong_expected':packet[3]=202
    elif change=='wrong_shape':packet=packet[:-1]
    elif change=='not_http_assertion':return assert_no_model_diagnostic(RuntimeError(tuple(packet)))
    assert model_failure_diagnostic(AssertionError(tuple(packet))) is None


def assert_no_model_diagnostic(error):
    from tests.windows.run_source_acceptance import model_failure_diagnostic
    assert model_failure_diagnostic(error) is None


def test_http_model_diagnostics_never_compare_or_render_untrusted_packet_objects():
    from tests.windows.run_source_acceptance import model_failure_diagnostic,abort_validation
    def forbidden(*_):raise AssertionError('Untrusted object must not be rendered/compared/hashed')
    class Method:
        __eq__=__ne__=__str__=__repr__=forbidden
    packet=list(_model_http_failure().args[0]);packet[0]=Method()
    assert model_failure_diagnostic(AssertionError(tuple(packet))) is None
    class ErrorMeta(type):__hash__=forbidden
    class PrivateError(Exception,metaclass=ErrorMeta):__str__=__repr__=forbidden
    report={}
    with pytest.raises(SystemExit):abort_validation(report,PrivateError('PRIVATE_CANARY'))
    assert report['failure_type']=='OtherError' and 'model_failure_diagnostic' not in report


def test_http_model_diagnostics_do_not_read_a_subclass_error_detail():
    from tests.windows.run_source_acceptance import ValidationCommandError,abort_validation
    class PrivateError(ValidationCommandError):
        @property
        def detail(self):raise AssertionError('Untrusted detail must not be accessed')
    error=PrivateError.__new__(PrivateError);report={}
    with pytest.raises(SystemExit):abort_validation(report,error)
    assert report['failure_type']=='OtherError' and 'command_failure' not in report


def test_failed_exit_publishes_static_diagnostic_without_body_path_or_traceback(tmp_path):
    import json,os,subprocess,sys
    from pathlib import Path
    source=Path(__file__).resolve().parents[2]
    error=_model_http_failure(kind='value_error',category='unknown',os_code='none',extra={'x':'PRIVATE_CANARY'})
    assert len(error.args[0][-1])<=300
    script=("import json\nfrom tests.windows.run_source_acceptance import abort_validation\nreport={}\ntry:\n raise AssertionError("+repr(error.args[0])+")\nexcept BaseException as error:\n try: abort_validation(report,error)\n finally: print(json.dumps(report))\n")
    from scripts.run_web import SAFE_ENVIRONMENT
    env={key:value for key,value in os.environ.items() if key in SAFE_ENVIRONMENT}
    env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
    result=subprocess.run([sys.executable,'-c',script],cwd=source,env=env,capture_output=True,text=True,timeout=10)
    assert result.returncode==1 and not result.stderr
    value=json.loads(result.stdout)
    assert value['status']=='FAIL' and value['failure_type']=='AssertionError'
    assert value['model_failure_diagnostic']=={'phase':'loading','kind':'value_error','category':'unknown','os_code':'none'}
    assert all(text not in result.stdout+result.stderr for text in ['PRIVATE_CANARY','/PRIVATE/','Traceback','credential=','retryable','message'])
