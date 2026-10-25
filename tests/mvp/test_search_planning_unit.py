import json

import pytest

from src.mvp.adapters.search_planning import ConfiguredSearchPlanningAdapter
from src.mvp.ports import MvpError
from src.mvp.search_plan_compiler import compile_search_plan


QUESTION = 'women and microbiome'


def output():
    return dict(original_question=QUESTION, concepts=[dict(id='women', label='women', role='population',
        source_span=dict(start=0, end=5, text='women'), requirement='required', retrieval_use='query',
        terms=[dict(id='t1', text='women', state='approved', origin='manual')])], variants=[dict(
        id='focused', label='Focused', kind='focused', expression=dict(op='concept_ref', concept_id='women'))])


def envelope(value=None, **extra):
    return json.dumps(dict(model='fixture', choices=[dict(finish_reason='stop', message=dict(role='assistant',
        content=json.dumps(output() if value is None else value)))], **extra)).encode()


class Socket:
    def settimeout(self, value):
        pass


class Response:
    def __init__(self, body, status=200, headers=None):
        self.body, self.status, self.headers = body, status, headers or {}

    def getheader(self, key, default=None):
        return self.headers.get(key, default)

    def read1(self, size):
        chunk, self.body = self.body[:size], self.body[size:]
        return chunk


class Connection:
    def __init__(self, response):
        self.response, self.sock, self.requests, self.closed = response, Socket(), [], False

    def request(self, *args, **kwargs):
        self.requests.append((args, kwargs))

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


def adapter(response):
    connection = Connection(response)
    value = ConfiguredSearchPlanningAdapter(enabled=True, url='http://127.0.0.1:11434/v1/chat/completions',
        model='fixture', model_revision='frozen', _connection_factory=lambda *a, **k: connection)
    return value, connection


def test_disabled_default_and_factory_perform_no_model_call():
    value = ConfiguredSearchPlanningAdapter.from_environment({})
    assert not value.capability().enabled and value.profile is None
    with pytest.raises(MvpError, match='disabled'):
        value.propose(QUESTION)


@pytest.mark.parametrize('url', ['https://example.org/v1/chat/completions', 'http://localhost:11434/v1/chat/completions',
    'http://127.0.0.1/v1/chat/completions', 'http://user:pass@127.0.0.1:11434/v1/chat/completions',
    'http://127.0.0.1:11434/v1/chat/completions?key=secret', 'http://127.0.0.1:11434/wrong'])
def test_remote_credentials_dns_and_unapproved_paths_rejected(url):
    with pytest.raises(MvpError) as failure:
        ConfiguredSearchPlanningAdapter(enabled=True, url=url, model='fixture', model_revision='r')
    assert failure.value.code == 'search_planner_configuration'


def test_separate_typed_output_never_approves_model_terms_or_claims_unknown_usage():
    value, connection = adapter(Response(envelope()))
    result = value.propose(QUESTION)
    term = result.draft.concepts[0].terms[0]
    assert term.state == 'proposed' and term.origin == 'model_proposed'
    assert compile_search_plan(result.draft).candidates[0].status == 'blocked'
    assert not result.usage.measured and result.usage.total_tokens is None
    assert result.prompt_version == 'mvp.search-intent-proposal.v1'
    assert len(result.response_sha256) == 64 and connection.closed
    request = json.loads(connection.requests[0][1]['body'])
    assert len(connection.requests) == 1 and 'tools' not in request
    assert 'cell' not in request['messages'][0]['content']
    assert request['messages'][1]['content'] == json.dumps({'original_question': QUESTION}, separators=(',', ':'), sort_keys=True)


@pytest.mark.parametrize('body,status,headers', [
    (b'{}', 200, {}), (b'bad', 200, {}), (envelope(), 302, {}),
    (envelope(), 200, {'Content-Encoding': 'gzip'}),
    (envelope(), 200, {'Content-Length': '999999'}),
    (envelope(dict(output(), original_question='changed')), 200, {}),
    (envelope(usage={'prompt_tokens': 1, 'completion_tokens': 2, 'total_tokens': 99}), 200, {}),
    (envelope().replace(b'"model": "fixture"', b'"model":"fixture","model":"fixture"'), 200, {}),
])
def test_bad_responses_have_no_retry_or_fallback(body, status, headers):
    value, connection = adapter(Response(body, status, headers))
    with pytest.raises(MvpError) as failure:
        value.propose(QUESTION)
    assert failure.value.code in {'search_planner_invalid_output', 'search_planner_provider_failure'}
    assert len(connection.requests) == 1 and connection.closed


def test_context_limit_is_checked_before_http():
    value, connection = adapter(Response(envelope()))
    with pytest.raises(MvpError) as failure:
        value.propose('漢' * 9000)
    assert failure.value.code == 'search_planner_context_limit'
    assert connection.requests == []


def test_measured_usage_and_no_paid_configuration():
    value, _ = adapter(Response(envelope(usage={'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15})))
    result = value.propose(QUESTION)
    assert result.usage.measured and result.usage.total_tokens == 15 and result.usage.cost_usd is None
    with pytest.raises(MvpError):
        ConfiguredSearchPlanningAdapter.from_environment({'MVP_SEARCH_PLANNER_ENABLED': '1', 'MVP_SEARCH_PLANNER_SPEND_CAP_USD': '1'})
