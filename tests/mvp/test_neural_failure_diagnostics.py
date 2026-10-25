"""Mocked failure observability only; never a real-model or quality check."""
import errno
import re
import sqlite3
import subprocess
from types import SimpleNamespace

import pytest
from src.mvp.adapters import neural_retrieval as native
from src.mvp.ports import MvpError

PRIVATE = 'PRIVATE source/query/tensor and C:/Users/private/model.safetensors'
PREFIX = 'The selected local model failed to execute.'


def adapter(tmp_path, monkeypatch, *, loading_error=None):
    value = native.NeuralAdapter.__new__(native.NeuralAdapter)
    value.profile_id, value.device, value.manifest = native.QWEN_PROFILE, 'cpu', {'fixed': 'fixture'}
    value.dimension, value.dense_metric = 1024, 'normalized_inner_product'
    value._dirs = {'query': tmp_path}
    value._progress = value._cancelled = None
    value._executed = {'query_encoder': 0, 'document_encoder': 0, 'reranker': 0}
    value._timing = {'model_load_seconds': 0., 'query_encoder_seconds': 0., 'document_encoder_seconds': 0., 'reranker_seconds': 0.}
    value._token_counts = {'query_tokens': 0, 'document_tokens': 0, 'reranker_pair_tokens': 0}
    class Model:
        def to(self, **kwargs): return self
        def eval(self): return self
    def load(*args, **kwargs):
        if loading_error is not None: raise loading_error
        return Model()
    value._transformers = SimpleNamespace(AutoModel=SimpleNamespace(from_pretrained=load))
    value._torch = SimpleNamespace(float32='fixture-fp32')
    monkeypatch.setattr(native.time, 'monotonic', lambda: 1.)
    return value


def failure(value, error, phase):
    with pytest.raises(MvpError) as caught:
        with value._model('query'):
            assert phase == 'execution'
            raise error
    result = caught.value
    assert result.code == 'retrieval_model_failed'
    assert result.message.startswith(PREFIX)
    assert PRIVATE not in result.message
    assert re.fullmatch(re.escape(PREFIX) + r' Diagnostic: phase=(?:progress|weights|placing|cancel|execution); kind=[a-z_]+; category=(?:memory|permission|locking|storage|encoding|environment|unknown); os_code=[a-z0-9_]+\. Inspect the runtime check or select lexical explicitly; no fallback ran\.', result.message)
    assert result.__suppress_context__
    return result.message


@pytest.mark.parametrize('phase', ['weights', 'execution'])
def test_loading_and_forward_failures_are_separate_and_keep_metadata(tmp_path, monkeypatch, phase):
    error = RuntimeError(PRIVATE)
    value = adapter(tmp_path, monkeypatch, loading_error=error if phase == 'weights' else None)
    before = value.runtime_metadata()
    message = failure(value, error, phase)
    assert f'phase={phase}; kind=runtime_error; category=unknown; os_code=none' in message
    assert value.runtime_metadata() == before
    # A failure cannot leak the global single-component operation lease.
    value._transformers.AutoModel.from_pretrained = lambda *a, **k: SimpleNamespace(to=lambda **_: SimpleNamespace(eval=lambda: 'fixture'))
    with value._model('query') as model: assert model == 'fixture'


@pytest.mark.parametrize('code,category', [(1455,'memory'), (8,'memory'), (14,'memory'), (5,'permission'), (32,'locking'), (33,'locking')])
def test_known_windows_categories_are_static_and_private_path_is_not_returned(tmp_path, monkeypatch, code, category):
    error = OSError(PRIVATE); error.winerror = code
    message = failure(adapter(tmp_path, monkeypatch, loading_error=error), error, 'weights')
    assert f'category={category}; os_code=win{code}' in message


@pytest.mark.parametrize('code,category,label', [(errno.ENOMEM,'memory','errno_enomem'), (errno.EACCES,'permission','errno_eacces'),
    (errno.EPERM,'permission','errno_eperm'), (errno.EBUSY,'locking','errno_ebusy'), (errno.EAGAIN,'locking','errno_eagain')])
def test_portable_errno_categories_do_not_return_error_payload(tmp_path, monkeypatch, code, category, label):
    error = OSError(code, PRIVATE)
    message = failure(adapter(tmp_path, monkeypatch, loading_error=error), error, 'weights')
    assert f'category={category}; os_code={label}' in message


@pytest.mark.parametrize('text', ['DefaultCPUAllocator: not enough memory: '+PRIVATE, "DefaultCPUAllocator: can't allocate memory: "+PRIVATE,
    'CUDA out of memory. '+PRIVATE, 'MPS backend out of memory '+PRIVATE])
def test_known_allocator_phrases_only_return_memory_category(tmp_path, monkeypatch, text):
    error = RuntimeError(text)
    message = failure(adapter(tmp_path, monkeypatch), error, 'execution')
    assert 'category=memory; os_code=none' in message
    assert text not in message


def test_unknown_custom_class_and_untrusted_arguments_are_not_rendered(tmp_path, monkeypatch):
    def forbidden(*_): raise AssertionError('Never render an untrusted exception or argument')
    unknown = type('PRIVATE_UNKNOWN_EXCEPTION_CLASS', (Exception,), {'__str__': forbidden, '__repr__': forbidden})
    error = unknown({'PRIVATE': PRIVATE}, b'PRIVATE bytes', object(), PRIVATE * 1000)
    error.winerror = '1455'; error.errno = True
    message = failure(adapter(tmp_path, monkeypatch), error, 'execution')
    assert 'kind=unknown; category=unknown; os_code=none' in message
    assert 'PRIVATE' not in message and '1455' not in message


def test_raising_diagnostic_attributes_do_not_replace_original_failure(tmp_path, monkeypatch):
    class Unknown(Exception):
        @property
        def winerror(self): raise RuntimeError(PRIVATE)
        @property
        def errno(self): raise RuntimeError(PRIVATE)
        @property
        def args(self): raise RuntimeError(PRIVATE)
    error = Unknown()
    message = failure(adapter(tmp_path, monkeypatch, loading_error=error), error, 'weights')
    assert 'kind=unknown; category=unknown; os_code=none' in message


@pytest.mark.parametrize('phase', ['progress', 'execution'])
def test_progress_callback_failures_are_safely_classified(tmp_path, monkeypatch, phase):
    value = adapter(tmp_path, monkeypatch)
    def callback(**_): raise TypeError(PRIVATE)
    if phase == 'progress': value.set_progress(callback)
    with pytest.raises(MvpError) as caught:
        with value._model('query'):
            value.set_progress(callback); value._report('encoding_query', component='query')
    assert caught.value.code == 'retrieval_model_failed'
    assert f'phase={phase}; kind=type_error' in caught.value.message
    assert PRIVATE not in caught.value.message


@pytest.mark.parametrize('phase', ['weights', 'execution'])
def test_typed_mvp_errors_keep_identity_code_message_and_retryability(tmp_path, monkeypatch, phase):
    error = MvpError('existing_typed_code', 'Existing safe typed message', True)
    value = adapter(tmp_path, monkeypatch, loading_error=error if phase == 'weights' else None)
    with pytest.raises(MvpError) as caught:
        with value._model('query'): raise error
    assert caught.value is error
    assert (caught.value.code, caught.value.message, caught.value.retryable) == ('existing_typed_code', 'Existing safe typed message', True)


def test_builtin_memory_error_is_classified_without_rendering_it(tmp_path, monkeypatch):
    error = MemoryError(PRIVATE)
    message = failure(adapter(tmp_path, monkeypatch, loading_error=error), error, 'weights')
    assert 'kind=memory_error; category=memory; os_code=none' in message


def test_unknown_native_numbers_and_custom_metaclass_are_not_rendered(tmp_path, monkeypatch):
    class PrivateMeta(type):
        def __hash__(cls): raise AssertionError('Do not hash an untrusted exception class')
    class PrivateFailure(Exception, metaclass=PrivateMeta): pass
    error=PrivateFailure(PRIVATE); error.winerror=987654; error.errno=876543
    message=failure(adapter(tmp_path, monkeypatch), error, 'execution')
    assert 'kind=unknown; category=unknown; os_code=none' in message
    assert '987654' not in message and '876543' not in message


def test_complete_static_failure_json_stays_inside_existing_bounded_capture():
    import json
    error=PermissionError(errno.EACCES, PRIVATE)
    suffix=native._model_failure_diagnostic(error, 'execution')
    message=PREFIX+' Diagnostic: '+suffix+'. Inspect the runtime check or select lexical explicitly; no fallback ran.'
    body=json.dumps({'error':{'code':'retrieval_model_failed','message':message,'retryable':False}}).encode()
    assert len(suffix)<=90 and len(body)<=300


@pytest.mark.parametrize('error_class,kind', [(sqlite3.OperationalError,'sqlite_operational_error'),
    (sqlite3.DatabaseError,'sqlite_database_error')])
def test_progress_database_failures_have_static_kind_without_database_payload(tmp_path, monkeypatch, error_class, kind):
    value=adapter(tmp_path,monkeypatch)
    def callback(**_):raise error_class(PRIVATE)
    value.set_progress(callback)
    with pytest.raises(MvpError) as caught:
        with value._model('query'):pytest.fail('A failed progress callback cannot load a model')
    assert f'phase=progress; kind={kind}; category=storage; os_code=none' in caught.value.message
    assert PRIVATE not in caught.value.message


def test_longest_database_kind_and_native_code_fit_bounded_failure_capture():
    import json
    error=sqlite3.OperationalError(PRIVATE);error.errno=errno.EACCES
    suffix=native._model_failure_diagnostic(error,'execution')
    message=PREFIX+' Diagnostic: '+suffix+'. Inspect the runtime check or select lexical explicitly; no fallback ran.'
    body=json.dumps({'error':{'code':'retrieval_model_failed','message':message,'retryable':False}}).encode()
    assert len(suffix)<=90 and len(body)<=300


@pytest.mark.parametrize('error,kind', [
    (UnicodeEncodeError('PRIVATE_ENCODING', PRIVATE, 0, 1, 'PRIVATE_REASON'), 'unicode_encode_error'),
    (UnicodeDecodeError('PRIVATE_ENCODING', b'PRIVATE_SOURCE', 0, 1, 'PRIVATE_REASON'), 'unicode_decode_error')])
def test_encoding_diagnostics_never_return_encoding_source_offsets_or_reason(tmp_path, monkeypatch, error, kind):
    message=failure(adapter(tmp_path,monkeypatch),error,'execution')
    assert f'kind={kind}; category=encoding; os_code=none' in message
    assert 'PRIVATE' not in message


def test_all_fixed_kinds_and_possible_os_code_categories_fit_complete_capture():
    import json
    factories=[lambda cls=cls:cls(PRIVATE) for cls in (MemoryError,OSError,PermissionError,FileNotFoundError,
        BlockingIOError,RuntimeError,ValueError,TypeError,ImportError,ModuleNotFoundError,
        sqlite3.OperationalError,sqlite3.DatabaseError,KeyError,AttributeError,NameError,IndexError,NotImplementedError,AssertionError,StopIteration,Exception)]
    factories += [lambda:subprocess.CalledProcessError(1,['PRIVATE command'],output=PRIVATE,stderr=PRIVATE),
        lambda:subprocess.TimeoutExpired(['PRIVATE command'],1,output=PRIVATE,stderr=PRIVATE)]
    factories += [lambda:UnicodeEncodeError('PRIVATE_ENCODING',PRIVATE,0,1,'PRIVATE_REASON'),
        lambda:UnicodeDecodeError('PRIVATE_ENCODING',b'PRIVATE_SOURCE',0,1,'PRIVATE_REASON')]
    maximum=0
    for phase in ('progress','weights','placing','cancel','execution'):
        for factory in factories:
            for windows_code in (None,1455,8,14,5,32,33):
                for portable_code in (None,errno.ENOMEM,errno.EACCES,errno.EPERM,errno.EBUSY,errno.EAGAIN):
                    error=factory();error.winerror=windows_code;error.errno=portable_code
                    suffix=native._model_failure_diagnostic(error,phase)
                    message=PREFIX+' Diagnostic: '+suffix+'. Inspect the runtime check or select lexical explicitly; no fallback ran.'
                    payload=json.dumps({'error':{'code':'retrieval_model_failed','message':message,'retryable':False}}).encode()
                    assert len(suffix)<=90 and len(payload)<=300
                    assert 'PRIVATE' not in message
                    maximum=max(maximum,len(payload))
    assert maximum==299


@pytest.mark.parametrize('phase', ['progress','weights','placing','cancel','execution'])
def test_each_exact_model_substep_is_observable_without_changing_metadata_or_gate(tmp_path, monkeypatch, phase):
    error=NameError(PRIVATE)
    value=adapter(tmp_path,monkeypatch,loading_error=error if phase=='weights' else None)
    class Model:
        def to(self, **kwargs):
            if phase=='placing':raise error
            return self
        def eval(self):return self
    if phase!='weights':value._transformers.AutoModel.from_pretrained=lambda *a,**k:Model()
    if phase=='progress':
        def progress(**_):raise error
        value.set_progress(progress)
    if phase=='cancel':
        calls=[]
        def cancel():
            calls.append(True)
            if len(calls)==2:raise error
            return False
        value.set_cancelled(cancel)
    before=value.runtime_metadata()
    with pytest.raises(MvpError) as caught:
        with value._model('query'):
            assert phase=='execution'
            raise error
    assert caught.value.code=='retrieval_model_failed'
    assert f'phase={phase}; kind=name_error; category=unknown; os_code=none' in caught.value.message
    assert PRIVATE not in caught.value.message
    assert value.runtime_metadata()==before
    value.set_progress(None);value.set_cancelled(None)
    value._transformers.AutoModel.from_pretrained=lambda *a,**k:SimpleNamespace(to=lambda **_:SimpleNamespace(eval=lambda:'fixture'))
    with value._model('query') as observed:assert observed=='fixture'


@pytest.mark.parametrize('error,kind', [(KeyError(PRIVATE),'key_error'),(AttributeError(PRIVATE),'attribute_error'),
    (NameError(PRIVATE),'name_error'),(IndexError(PRIVATE),'index_error'),(NotImplementedError(PRIVATE),'not_implemented'),
    (AssertionError(PRIVATE),'assertion_error'),(StopIteration(PRIVATE),'stop_iteration'),
    (subprocess.CalledProcessError(1,['PRIVATE command'],output=PRIVATE,stderr=PRIVATE),'process_error'),
    (subprocess.TimeoutExpired(['PRIVATE command'],1,output=PRIVATE,stderr=PRIVATE),'process_timeout')])
def test_exact_additional_builtin_and_subprocess_kinds_suppress_all_payloads(tmp_path, monkeypatch, error, kind):
    message=failure(adapter(tmp_path,monkeypatch),error,'execution')
    assert f'kind={kind}; category=unknown; os_code=none' in message
    assert 'PRIVATE' not in message


@pytest.mark.parametrize('name,code', [('USERNAME','env_user'),('COMSPEC','env_shell'),('NUMBER_OF_PROCESSORS','env_cpu'),
    ('SYSTEMROOT','env_system'),('WINDIR','env_windows'),('APPDATA','env_app'),('LOCALAPPDATA','env_local'),
    ('TEMP','env_temp'),('TMP','env_tmp'),('USERPROFILE','env_profile'),('HOMEDRIVE','env_drive'),('HOMEPATH','env_home')])
def test_only_exact_allowlisted_os_key_produces_static_environment_code(tmp_path, monkeypatch, name, code):
    import json
    error=KeyError(name)
    message=failure(adapter(tmp_path,monkeypatch,loading_error=error),error,'weights')
    assert f'kind=key_error; category=environment; os_code={code}' in message
    assert name not in message
    assert len(json.dumps({'error':{'code':'retrieval_model_failed','message':message,'retryable':False}}).encode())<=300


@pytest.mark.parametrize('args', [(PRIVATE,),('username',),('OPENAI_API_KEY',),('USERNAME',PRIVATE),
    ('PRIVATE_'+str(i) for i in range(2)), (object(),)])
def test_unknown_or_malformed_key_errors_do_not_disclose_keys(tmp_path, monkeypatch, args):
    # A malformed iterable becomes only the exception argument tuple; no value is rendered.
    error=KeyError(*args)
    message=failure(adapter(tmp_path,monkeypatch,loading_error=error),error,'weights')
    assert 'kind=key_error; category=unknown; os_code=none' in message
    assert 'USERNAME' not in message and 'OPENAI_API_KEY' not in message and 'PRIVATE' not in message
