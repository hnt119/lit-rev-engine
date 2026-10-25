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
    'sqlite_operational_error','sqlite_database_error','unicode_encode_error','unicode_decode_error',
    'key_error','attribute_error','name_error','index_error','not_implemented','assertion_error',
    'stop_iteration','process_error','process_timeout','unknown'])
def test_http_model_diagnostics_only_project_known_exception_kinds(kind):
    from tests.windows.run_source_acceptance import model_failure_diagnostic
    error=_model_http_failure(phase='execution',kind=kind,category='unknown',os_code='none')
    assert len(error.args[0][-1])<=300
    assert model_failure_diagnostic(error)=={'phase':'execution','kind':kind,'category':'unknown','os_code':'none'}


@pytest.mark.parametrize('phase,kind,category,os_code', [
    ('loading','os_error','memory','win1455'),('execution','runtime_error','memory','none'),
    ('loading','sqlite_operational_error','storage','none'),('execution','sqlite_database_error','storage','none'),
    ('execution','unicode_encode_error','encoding','none'),('loading','unicode_decode_error','encoding','none'),
    ('unknown','unknown','unknown','none'),('progress','type_error','unknown','none'),
    ('weights','key_error','environment','env_user'),('placing','runtime_error','memory','none'),
    ('cancel','key_error','unknown','none')])
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


@pytest.mark.parametrize('code',['env_user','env_shell','env_cpu','env_system','env_windows','env_app',
    'env_local','env_temp','env_tmp','env_profile','env_drive','env_home'])
def test_http_model_diagnostics_retain_static_environment_tokens_only(code):
    import json
    from tests.windows.run_source_acceptance import model_failure_diagnostic
    error=_model_http_failure(phase='weights',kind='key_error',category='environment',os_code=code)
    assert len(error.args[0][-1])<=300
    result=model_failure_diagnostic(error)
    assert result=={'phase':'weights','kind':'key_error','category':'environment','os_code':code}
    assert all(value not in json.dumps(result) for value in ['PRIVATE','USERNAME','USERPROFILE','LOCALAPPDATA','SYSTEMROOT'])


def _model_profile_callbacks(errors=None, *, fail_prepare=None, fail_start=None, fail_stop=None, fail_remove=None):
    errors=errors or {};events=[]
    def prepare(profile):
        events.append(('prepare',profile))
        if fail_prepare is not None:raise fail_prepare
        return {'download_and_check_seconds':0.0,'runtime':{'encoder_executed':True,'reranker_executed':True}}
    def start(profile):
        events.append(('start',profile))
        if fail_start is not None:raise fail_start
    def evaluate(profile):
        events.append(('http',profile))
        if profile in errors:raise errors[profile]
        return {'status':'PASS','source_scope':'synthetic software fixture only'}
    def stop(profile):
        events.append(('stop',profile))
        if fail_stop is not None:raise fail_stop
    def remove(profile):
        events.append(('remove',profile))
        if fail_remove is not None:raise fail_remove
    return dict(prepare=prepare,start=start,evaluate=evaluate,stop=stop,remove=remove),events


@pytest.mark.parametrize('failed_indices',[[],[0],[1],[0,1]])
def test_requested_model_profiles_are_independent_once_and_any_failure_remains_failure(failed_indices):
    import json
    from tests.windows.run_source_acceptance import run_requested_model_profiles,_REQUESTED_MODEL_PROFILES
    profiles=_REQUESTED_MODEL_PROFILES
    failures={profiles[i]:_model_http_failure(kind='unknown',category='unknown',os_code='none') for i in failed_indices}
    callbacks,events=_model_profile_callbacks(failures);report={'models':[]}
    passed=run_requested_model_profiles(report,**callbacks)
    assert passed is (not failed_indices)
    assert events==[(action,profile) for profile in profiles for action in ['prepare','start','http','stop','remove']]
    assert report['failed_model_profiles']==[profiles[i] for i in failed_indices]
    for i,row in enumerate(report['models']):
        assert row['profile_id']==profiles[i] and row['runtime_status']=='PASS'
        assert row['owned_stop_status']==row['pack_cleanup_status']=='PASS'
        assert row['status']==row['application_http']['status']==('FAIL' if i in failed_indices else 'PASS')
        if i in failed_indices:assert row['application_http']['model_failure_diagnostic']=={
            'phase':'loading','kind':'unknown','category':'unknown','os_code':'none'}
    assert 'PRIVATE' not in json.dumps(report)


@pytest.mark.parametrize('error',[AssertionError('PRIVATE source integrity failure'),
    TimeoutError('PRIVATE timeout'),RuntimeError('PRIVATE unknown failure'),
    PermissionError('PRIVATE ownership failure'),KeyboardInterrupt(),SystemExit(1),
    _model_http_failure(code='retrieval_integrity'),_model_http_failure(kind='private_canary')])
def test_non_model_security_timeout_and_unknown_failures_never_start_second_profile(error):
    from tests.windows.run_source_acceptance import run_requested_model_profiles,_REQUESTED_MODEL_PROFILES,abort_validation
    first=_REQUESTED_MODEL_PROFILES[0];callbacks,events=_model_profile_callbacks({first:error});report={'models':[]}
    with pytest.raises(type(error)) as caught:run_requested_model_profiles(report,**callbacks)
    assert caught.value is error
    assert events==[(action,first) for action in ['prepare','start','http','stop','remove']]
    assert len(report['models'])==1 and report['models'][0]['status']=='FAIL'
    assert report['models'][0]['runtime_status']=='PASS'
    assert report['models'][0]['application_http']=={'status':'FAIL',
        'failure_phase':'real-production-hybrid-http-'+first}
    with pytest.raises(SystemExit) as failed:abort_validation(report,error)
    assert failed.value.code==1 and report['status']=='FAIL'


@pytest.mark.parametrize('stage',['prepare','start','stop','remove'])
def test_profile_cleanup_or_start_failure_prevents_continuation(stage):
    from tests.windows.run_source_acceptance import run_requested_model_profiles,_REQUESTED_MODEL_PROFILES
    first=_REQUESTED_MODEL_PROFILES[0];error=RuntimeError('PRIVATE failed '+stage)
    callbacks,events=_model_profile_callbacks({first:_model_http_failure()},**{'fail_'+stage:error});report={'models':[]}
    with pytest.raises(RuntimeError) as caught:run_requested_model_profiles(report,**callbacks)
    assert caught.value is error
    expected={'prepare':['prepare','remove'],'start':['prepare','start','stop','remove'],
        'stop':['prepare','start','http','stop'],'remove':['prepare','start','http','stop','remove']}[stage]
    assert events==[(action,first) for action in expected]
    assert len(report['models'])==1 and report['models'][0]['status']=='FAIL'
    assert report['models'][0]['runtime_status']==('INCOMPLETE' if stage=='prepare' else 'PASS')
    if stage in {'prepare','start'}:assert report['models'][0]['application_http']=={'status':'NOT_RUN'}
    else:assert report['models'][0]['application_http']['status']=='FAIL'
    if stage=='stop':assert report['models'][0]['pack_cleanup_status']=='NOT_RUN'
    if stage=='remove':assert report['models'][0]['pack_cleanup_status']=='FAIL'


def test_aggregate_failure_keeps_exit_one_and_each_profile_result(capsys):
    import json
    from tests.windows.run_source_acceptance import run_requested_model_profiles,_REQUESTED_MODEL_PROFILES,abort_validation
    first=_REQUESTED_MODEL_PROFILES[0];callbacks,_=_model_profile_callbacks({first:_model_http_failure()});report={'models':[]}
    passed=run_requested_model_profiles(report,**callbacks)
    with pytest.raises(SystemExit) as stopped:
        try:
            if not passed:raise RuntimeError('At least one requested model failed')
        except RuntimeError as error:abort_validation(report,error)
    assert stopped.value.code==1 and report['status']=='FAIL'
    assert [item['status'] for item in report['models']]==['FAIL','PASS']
    assert report['failed_model_profiles']==[first]
    assert 'PRIVATE' not in json.dumps(report)+capsys.readouterr().out


def test_longest_producer_diagnostic_stays_complete_and_parseable_within_300_bytes():
    import errno,json,sqlite3
    from src.mvp.adapters.neural_retrieval import _model_failure_diagnostic
    from tests.windows.run_source_acceptance import model_failure_diagnostic
    error=sqlite3.OperationalError('PRIVATE_CANARY source and machine path')
    error.errno=errno.EACCES
    suffix=_model_failure_diagnostic(error,'execution')
    message=('The selected local model failed to execute. Diagnostic: '+suffix+
        '. Inspect the runtime check or select lexical explicitly; no fallback ran.')
    body=json.dumps({'error':{'code':'retrieval_model_failed','message':message,'retryable':False}}).encode()
    assert len(body)==299 and len(body[:300])==len(body)
    parsed=model_failure_diagnostic(AssertionError(('POST','/PRIVATE_CANARY',422,200,body[:300])))
    assert parsed=={'phase':'execution','kind':'sqlite_operational_error','category':'permission','os_code':'errno_eacces'}
    assert 'PRIVATE' not in json.dumps(parsed)
