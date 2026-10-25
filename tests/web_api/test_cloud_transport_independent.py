"""Independent synthetic HTTPS checks; no cloud account or model is contacted."""
import json
import socket

import pytest

from src.mvp.adapters.cloud_generation import CloudJSONTransport, SessionCloudAdapter
from src.mvp.contracts import canonical
from src.mvp.ports import MvpError
from src.mvp.search_plan_contracts import SearchPlanDraft

KEY = 'SYNTHETIC-cloud-key-never-real'
MODEL = 'synthetic-explicit-model'


class FakeSocket:
    def __init__(self): self.timeouts = []
    def settimeout(self, value): self.timeouts.append(value)
    def shutdown(self, _): pass
    def close(self): pass


class FakeResponse:
    def __init__(self, raw=b'{}', status=200, headers=None):
        self.raw, self.status = raw, status
        self.headers = headers or {'Content-Length': str(len(raw))}
    def getheader(self, key, default=None): return self.headers.get(key, default)
    def read1(self, amount):
        value, self.raw = self.raw[:amount], self.raw[amount:]
        return value


class FakeConnection:
    def __init__(self, response=None, error=None):
        self.sock = FakeSocket()
        self.response, self.error = response or FakeResponse(), error
        self.requests, self.closed = [], False
    def request(self, *args, **kwargs):
        self.requests.append((args, kwargs))
        if self.error: raise self.error
    def getresponse(self): return self.response
    def close(self): self.closed = True


def transport(provider='openai', *, response=None, error=None):
    connection, created = FakeConnection(response, error), []
    def factory(*args, **kwargs):
        created.append((args, kwargs))
        return connection
    return CloudJSONTransport(provider, KEY, connection_factory=factory), connection, created


@pytest.mark.parametrize('provider,host,path', [
    ('openai', 'api.openai.com', '/v1/chat/completions'),
    ('deepseek', 'api.deepseek.com', '/chat/completions'),
])
def test_fixed_destinations_are_the_only_credential_recipients(provider, host, path, monkeypatch):
    monkeypatch.setenv('HTTPS_PROXY', 'https://untrusted-proxy.invalid')
    subject, connection, created = transport(provider)
    assert subject.request(b'{}', 1) == b'{}'
    assert created[0][0] == (host, 443)
    args, kwargs = connection.requests[0]
    assert args == ('POST', path)
    assert kwargs['headers']['Authorization'] == 'Bearer ' + KEY
    assert connection.closed and len(created) == len(connection.requests) == 1


@pytest.mark.parametrize('status', [301, 302, 307, 308, 401, 403, 429, 500])
def test_redirect_auth_rate_limit_and_server_failure_never_retry_or_echo(status):
    subject, connection, created = transport(response=FakeResponse(b'secret-provider-body-' + KEY.encode(), status))
    with pytest.raises(MvpError) as raised:
        subject.request(b'{}', 1)
    assert KEY not in str(raised.value) and 'secret-provider-body' not in str(raised.value)
    assert len(created) == len(connection.requests) == 1
    assert connection.closed


@pytest.mark.parametrize('error', [TimeoutError(KEY), socket.timeout(KEY), OSError(KEY)])
def test_transport_errors_redact_credentials_and_do_not_fallback(error):
    subject, connection, created = transport(error=error)
    with pytest.raises(MvpError) as raised:
        subject.request(b'{}', 1)
    assert KEY not in str(raised.value)
    assert len(created) == len(connection.requests) == 1 and connection.closed


@pytest.mark.parametrize('headers,raw', [
    ({'Content-Length':'65537'}, b''),
    ({'Content-Length':'NaN'}, b''),
    ({'Content-Length':'4'}, b'{}'),
    ({'Content-Encoding':'gzip'}, b'{}'),
    ({}, b'x' * 65537),
])
def test_response_bounds_compression_and_truncation_fail_closed(headers, raw):
    # The fake intentionally permits a missing Content-Length.
    response = FakeResponse(raw)
    response.headers = headers
    subject, connection, _ = transport(response=response)
    with pytest.raises(MvpError):
        subject.request(b'{}', 1)
    assert connection.closed


def test_no_connection_is_constructed_for_oversize_input():
    subject, connection, created = transport()
    with pytest.raises(MvpError):
        subject.request(b'x' * 65537, 1)
    assert created == [] and connection.requests == []


@pytest.mark.parametrize('provider', ['http://127.0.0.1', 'other', 'https://api.openai.com', 'OPENAI'])
def test_arbitrary_cloud_destinations_rejected_at_configuration(provider):
    with pytest.raises(MvpError): CloudJSONTransport(provider, KEY)


class FakeModelTransport:
    def __init__(self, value): self.value, self.calls = value, []
    def request(self, body, timeout):
        self.calls.append((json.loads(body), timeout))
        return canonical(self.value).encode()


def envelope(content, **message_changes):
    return {'model': MODEL, 'choices':[{'finish_reason':'stop', 'message':{
        'role':'assistant', 'content':content, **message_changes}}]}


def adapter(provider='openai', *, response=None, still_current=lambda: None):
    tx = FakeModelTransport(response or envelope(canonical(SearchPlanDraft(original_question='Synthetic question?').model_dump(mode='json'))))
    subject = SessionCloudAdapter(provider=provider, model=MODEL, model_revision='synthetic-profile.v1',
        key=KEY, task='planning', settings_revision=1, still_current=still_current, transport=tx)
    return subject, tx


@pytest.mark.parametrize('provider', ['openai', 'deepseek'])
def test_provider_payloads_are_bounded_no_tools_and_preserve_usage_unknown(provider):
    subject, tx = adapter(provider)
    value = subject.propose('Synthetic question?')
    assert value.draft.original_question == 'Synthetic question?'
    assert value.usage.measured is False and value.usage.cost_usd is None
    body, timeout = tx.calls[0]
    assert 0 < timeout <= 30 and body['stream'] is False
    assert not any(key in body for key in ('tools','functions','api_key','temperature'))
    assert KEY not in canonical(body)
    assert body['response_format'] == {'type':'json_object'}
    if provider == 'openai':
        assert body['max_completion_tokens'] == 4096 and 'max_tokens' not in body
    else:
        assert body['max_tokens'] == 4096 and body['thinking'] == {'type':'disabled'}


@pytest.mark.parametrize('kind', ['empty', 'refusal', 'tools', 'truncated', 'wrong_model', 'duplicate_json', 'bad_schema'])
def test_invalid_cloud_outputs_cannot_publish_a_plan(kind):
    value = envelope(canonical(SearchPlanDraft(original_question='Synthetic question?').model_dump(mode='json')))
    if kind == 'empty': value['choices'][0]['message']['content'] = ''
    elif kind == 'refusal': value['choices'][0]['message']['refusal'] = 'SYNTHETIC refusal'
    elif kind == 'tools': value['choices'][0]['message']['tool_calls'] = [{'id':'bad'}]
    elif kind == 'truncated': value['choices'][0]['finish_reason'] = 'length'
    elif kind == 'wrong_model': value['model'] = 'different-model'
    elif kind == 'duplicate_json': value['choices'][0]['message']['content'] = '{"original_question":"x","original_question":"y"}'
    else: value['choices'][0]['message']['content'] = '{"original_question":"different-question"}'
    subject, tx = adapter(response=value)
    with pytest.raises(MvpError): subject.propose('Synthetic question?')
    assert len(tx.calls) == 1


def test_setting_change_after_response_rejects_publication():
    calls = []
    def current():
        calls.append(True)
        if len(calls) > 1: raise MvpError('stale_settings', 'Synthetic setting changed')
    subject, tx = adapter(still_current=current)
    with pytest.raises(MvpError): subject.propose('Synthetic question?')
    assert len(calls) == 2 and len(tx.calls) == 1


def test_absolute_cloud_deadline_bounds_a_connect_phase_without_socket():
    # DNS/connect can block before HTTPConnection exposes a socket. A socket
    # timeout/watchdog alone cannot provide the application's wall-clock bound.
    import threading
    import time
    entered, release, ended = threading.Event(), threading.Event(), threading.Event()
    class Connecting(FakeConnection):
        def __init__(self):
            super().__init__()
            self.sock = None
        def request(self, *args, **kwargs):
            entered.set()
            release.wait(timeout=.35)
            raise TimeoutError('synthetic connect timeout')
        def close(self):
            super().close()
            ended.set()
    connection = Connecting()
    subject = CloudJSONTransport('openai',KEY,connection_factory=lambda *a,**kw: connection)
    started = time.monotonic()
    try:
        with pytest.raises(MvpError): subject.request(b'{}',.05)
        elapsed = time.monotonic() - started
        assert entered.is_set() and elapsed < .25, f'Cloud operation exceeded its absolute deadline: {elapsed:.3f}s'
        # A second provider cannot consume another credential/call slot while
        # the timed-out operation's connect phase is still genuinely running.
        other, second_connection, created = transport('deepseek')
        with pytest.raises(MvpError): other.request(b'{}',.05)
        assert created == [] and second_connection.requests == []
    finally:
        release.set()
        assert ended.wait(timeout=1)
