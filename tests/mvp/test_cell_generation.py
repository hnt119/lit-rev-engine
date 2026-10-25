"""Software-only packet/HTTP checks. No model or provider endpoint is called."""
import json
import socket
import time

import pytest

from src.mvp.adapters.cell_generation import (
    ConfiguredCellGenerationAdapter, MAX_INPUT_BYTES, build_packet, strict_json_loads,
)
from src.mvp.board_contracts import (
    BoardCandidate, BoardCandidates, BoardField, BoardPaper, BoardReference,
    BoardRevision, BoardSourceBinding,
)
from src.mvp.contracts import canonical, digest
from src.mvp.ports import MvpError
from src.mvp.proposal_contracts import MAX_PACKET_BYTES, ProposalPacket


def case(*, fields=3, quote='Women in a dietary cohort 😀.', question='What population was studied?'):
    profile = {'method': 'existing-lexical-fixture', 'version': 'one'}
    definition = BoardRevision(board_id='board', revision_id='revision', workspace_id='workspace',
        search_id='search', search_sha256='a' * 64, question=question,
        question_sha256=digest(question), preparation_id='preparation', source_revision=1,
        source_manifest_sha256='b' * 64, retrieval_profile=profile,
        retrieval_profile_sha256=digest(profile), paper_ids=['paper'],
        papers=[BoardPaper(id='paper', title='Software fixture', authors=[], url='')],
        sources=[BoardSourceBinding(source_id='source', paper_id='paper', version='v1',
            source_sha256='c' * 64, blocks_sha256='d' * 64, parser_id='fixture-v1',
            source_type='abstract', status='abstract_only', block_count=1)],
        fields=[BoardField(id='field' + str(i), label='Population', subquestion='Women diet cohort',
                          revision_id='field-revision' + str(i)) for i in range(fields)])
    reference = BoardReference(id='reference', source_id='source', paper_id='paper',
        source_version='v1', source_sha256='c' * 64, blocks_sha256='d' * 64,
        block_id='block', start=0, end=len(quote), quote=quote, locator={'type': 'abstract'})
    runs = [BoardCandidates(id='candidates' + str(i), board_id='board', board_revision_id='revision',
        paper_id='paper', field_id=field.id, field_revision_id=field.revision_id,
        preparation_id='preparation', source_manifest_sha256='b' * 64,
        retrieval_profile=profile, retrieval_profile_sha256=digest(profile), indexed_blocks=1,
        matched_blocks=1, returned_count=1, omitted_matched_blocks=0,
        candidates=[BoardCandidate(rank=1, score=1.0, reference=reference,
            total_block_characters=len(quote), omitted_characters=0)]) for i, field in enumerate(definition.fields)]
    return definition, runs


def packet():
    definition, runs = case()
    return build_packet(definition, 'paper', runs)


class FakeSocket:
    def __init__(self):
        self.timeouts = []
    def settimeout(self, timeout):
        self.timeouts.append(timeout)
    def shutdown(self, _how):
        pass
    def close(self):
        pass


class Response:
    def __init__(self, payload, *, status=200, headers=None):
        self.payload = payload
        self.status = status
        self.headers = headers or {}
    def getheader(self, name, default=None):
        return self.headers.get(name, default)
    def read1(self, size):
        result, self.payload = self.payload[:size], self.payload[size:]
        return result


class Connection:
    def __init__(self, response):
        self.response = response
        self.sock = FakeSocket()
        self.requests = []
        self.closed = False
    def request(self, method, path, body, headers):
        self.requests.append((method, path, body, headers))
    def getresponse(self):
        return self.response
    def close(self):
        self.closed = True


def outer(**changes):
    output = {'cells': [{'field_id': 'field0', 'value': None, 'references': [],
        'reason': 'Software fixture only; incomplete retrieved context.',
        'missing_information': 'No supporting information in this packet.',
        'context_scope': 'retrieved_context_only'}]}
    value = {'model': 'fixture-model', 'choices': [{'finish_reason': 'stop',
        'message': {'role': 'assistant', 'content': json.dumps(output)}}],
        'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120}}
    value.update(changes)
    return json.dumps(value).encode()


def adapter(response=None, **kwargs):
    connection = Connection(response or Response(outer()))
    values = dict(enabled=True, url='http://127.0.0.1:19999/v1/chat/completions',
        model='fixture-model', model_revision='fixture-revision',
        _connection_factory=lambda *args, **kwargs: connection)
    values.update(kwargs)
    return ConfiguredCellGenerationAdapter(**values), connection


def test_packet_deduplicates_cross_field_anchors_and_retains_field_authority():
    value = packet()
    assert len(value.evidence) == 1 and value.evidence_characters == len(value.evidence[0].reference.quote)
    assert value.evidence[0].field_ids == ['field0', 'field1', 'field2']
    assert all(field.evidence_ids == [value.evidence[0].evidence_id] for field in value.fields)
    assert value.evidence[0].evidence_id.startswith('e:')
    assert [field.candidate_run_id for field in value.fields] == ['candidates0', 'candidates1', 'candidates2']
    assert value.source_type == 'abstract' and value.source_status == 'abstract_only'
    assert value.context_scope == 'retrieved_context_only'
    assert value.evidence[0].total_block_characters == len(value.evidence[0].reference.quote)
    assert value.evidence[0].omitted_characters == 0
    assert value == packet()  # Opaque evidence IDs and ordering are reproducible.


def test_identical_quote_in_another_paper_has_a_distinct_evidence_id():
    definition, runs = case(fields=1)
    first = build_packet(definition, 'paper', runs)
    other = definition.model_copy(update={'paper_ids': ['other-paper'],
        'papers': [definition.papers[0].model_copy(update={'id': 'other-paper'})],
        'sources': [definition.sources[0].model_copy(update={'paper_id': 'other-paper'})]})
    candidate = runs[0].candidates[0]
    other_run = runs[0].model_copy(update={'paper_id': 'other-paper', 'candidates': [candidate.model_copy(update={
        'reference': candidate.reference.model_copy(update={'paper_id': 'other-paper'})})]})
    second = build_packet(other, 'other-paper', [other_run])
    assert first.evidence[0].reference.quote == second.evidence[0].reference.quote
    assert first.evidence[0].evidence_id != second.evidence[0].evidence_id


def test_same_anchor_with_conflicting_equal_length_text_is_not_deduplicated():
    definition, runs = case(fields=2)
    candidate = runs[1].candidates[0]
    changed = candidate.reference.model_copy(update={'quote': 'x' * len(candidate.reference.quote)})
    runs[1] = runs[1].model_copy(update={'candidates': [candidate.model_copy(update={'reference': changed})]})
    with pytest.raises(MvpError, match='Candidate evidence'):
        build_packet(definition, 'paper', runs)


@pytest.mark.parametrize('attribute,value', [
    ('paper_id', 'other'), ('board_id', 'other'), ('board_revision_id', 'other'),
    ('field_revision_id', 'other'), ('preparation_id', 'other'),
    ('source_manifest_sha256', 'e' * 64), ('retrieval_profile_sha256', 'f' * 64),
])
def test_packet_rejects_mismatching_candidate_bindings(attribute, value):
    definition, runs = case(fields=1)
    with pytest.raises(MvpError) as error:
        build_packet(definition, 'paper', [runs[0].model_copy(update={attribute: value})])
    assert error.value.code == 'proposal_invalid_evidence'


@pytest.mark.parametrize('attribute,value', [
    ('paper_id', 'other'), ('source_id', 'other'), ('source_version', 'other'),
    ('source_sha256', 'e' * 64), ('blocks_sha256', 'f' * 64), ('quote', 'changed'),
])
def test_packet_rejects_reference_bindings_or_mismatching_offsets(attribute, value):
    definition, runs = case(fields=1)
    candidate = runs[0].candidates[0]
    reference = candidate.reference.model_copy(update={attribute: value})
    run = runs[0].model_copy(update={'candidates': [candidate.model_copy(update={'reference': reference})]})
    with pytest.raises(MvpError, match='Candidate evidence'):
        build_packet(definition, 'paper', [run])


def test_packet_omits_whole_evidence_at_character_or_utf8_budget():
    definition, runs = case(fields=6, quote='汉' * 1200)
    runs = [run.model_copy(update={'candidates': [run.candidates[0].model_copy(update={
        'reference': run.candidates[0].reference.model_copy(update={'block_id': f'block-{i}-{j}'})})
        for j in range(3)], 'returned_count': 3}) for i, run in enumerate(runs)]
    value = build_packet(definition, 'paper', runs)
    assert value.omitted_evidence > 0
    assert len(canonical(value.model_dump(mode='json')).encode()) <= MAX_PACKET_BYTES
    assert all(item.reference.quote == '汉' * 1200 for item in value.evidence)
    allowed = {item.evidence_id for item in value.evidence}
    assert all(set(field.evidence_ids) <= allowed for field in value.fields)
    assert sum(field.omitted_evidence for field in value.fields) == value.omitted_evidence


def test_packet_rejects_oversized_question_without_silent_truncation():
    definition, runs = case(fields=1, question='漢' * 10000)
    with pytest.raises(MvpError) as error:
        build_packet(definition, 'paper', runs)
    assert error.value.code == 'proposal_context_limit'


def test_partial_canonical_block_is_explicit_in_packet_for_model():
    definition, runs = case(fields=1, quote='x' * 1200)
    runs = [runs[0].model_copy(update={'candidates': [runs[0].candidates[0].model_copy(update={
        'total_block_characters': 9500, 'omitted_characters': 8300})]})]
    value = build_packet(definition, 'paper', runs)
    assert value.evidence[0].total_block_characters == 9500
    assert value.evidence[0].omitted_characters == 8300 and value.omitted_evidence == 0


def test_disabled_by_default_and_ignores_unrelated_provider_configuration():
    value = ConfiguredCellGenerationAdapter.from_environment({'DEEPINFRA_API_KEY': 'do-not-use',
        'OPENAI_API_KEY': 'do-not-use', 'OPENAI_BASE_URL': 'https://example.invalid'})
    assert not value.enabled and value.profile is None
    with pytest.raises(MvpError) as error:
        value.generate(packet(), timeout_seconds=10)
    assert error.value.code == 'proposal_generation_disabled'


@pytest.mark.parametrize('url', [
    'https://127.0.0.1:99/v1/chat/completions', 'http://localhost:99/v1/chat/completions',
    'http://127.1:99/v1/chat/completions', 'http://127.0.0.2:99/v1/chat/completions',
    'http://example.invalid:99/v1/chat/completions', 'http://user:key@127.0.0.1:99/v1/chat/completions',
    'http://127.0.0.1:99/v1/chat/completions?api_key=secret',
    'http://127.0.0.1:99/v1/chat/completions#fragment', 'http://127.0.0.1/v1/chat/completions',
    'http://127.0.0.1:99/other', 'http://[::ffff:127.0.0.1]:99/v1/chat/completions',
])
def test_only_exact_literal_loopback_endpoint_is_permitted(url):
    with pytest.raises(MvpError) as error:
        adapter(url=url)
    assert error.value.code == 'proposal_configuration'
    assert 'secret' not in error.value.message


def test_explicit_local_configuration_and_zero_spend_only():
    env = {'MVP_PROPOSALS_ENABLED': '1', 'MVP_PROPOSALS_URL': 'http://[::1]:19999/v1/chat/completions',
        'MVP_PROPOSALS_MODEL': 'local-model', 'MVP_PROPOSALS_MODEL_REVISION': 'explicit-revision'}
    value = ConfiguredCellGenerationAdapter.from_environment(env)
    assert value.enabled and value.profile.model_revision == 'explicit-revision'
    assert value.profile.revision_status == 'configured_not_weight_verified'
    assert len(value.profile.system_prompt_sha256) == len(value.profile.output_schema_sha256) == 64
    assert value.profile.spend_cap_usd == 0 and value.profile.retries == 0
    for changed in ({'MVP_PROPOSALS_SPEND_CAP_USD': '1'}, {'MVP_PROPOSALS_MODEL_REVISION': ''}, {'MVP_PROPOSALS_ENABLED': 'true'}):
        with pytest.raises(MvpError):
            ConfiguredCellGenerationAdapter.from_environment({**env, **changed})


def test_generate_has_no_action_tools_auth_proxies_or_fallback_and_reports_actual_usage():
    value, connection = adapter()
    result = value.generate(packet(), timeout_seconds=10)
    assert strict_json_loads(result.output_text)['cells'][0]['value'] is None
    assert result.usage.input_tokens == 100 and result.usage.output_tokens == 20
    assert result.usage.total_tokens == 120 and result.usage.measured
    assert result.usage.cost_usd is None
    method, path, body, headers = connection.requests[0]
    request = json.loads(body)
    assert method == 'POST' and path == '/v1/chat/completions' and len(connection.requests) == 1
    assert len(body) <= MAX_INPUT_BYTES and request['temperature'] == 0 and request['max_tokens'] <= 2048
    assert request['response_format'] == {'type': 'json_object'} and request['stream'] is False
    assert 'UNTRUSTED DATA' in request['messages'][0]['content']
    assert set(request) == {'model', 'temperature', 'max_tokens', 'stream', 'response_format', 'messages'}
    assert 'Authorization' not in headers and connection.closed
    assert all(0 < timeout <= 10 for timeout in connection.sock.timeouts)


def test_usage_unknown_remains_null_and_zero_is_not_unknown():
    for metadata, measured in [(None, False), ({'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}, True)]:
        value, _ = adapter(Response(outer(usage=metadata)))
        result = value.generate(packet(), timeout_seconds=10)
        assert result.usage.measured is measured and result.usage.cost_usd is None
        assert result.usage.total_tokens == (0 if measured else None)


@pytest.mark.parametrize('payload', [
    b'{"model":"fixture-model","model":"fixture-model"}', b'{"model":NaN}', b'{"value":1e999}',
    b'{"value":"\\ud800"}', b'```json\n{}\n```', b'{',
    outer(model='unexpected'), outer(choices=[]), outer(choices=[{'finish_reason': 'length', 'message': {'role': 'assistant', 'content': '{}'}}]),
    outer(choices=[{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': '{}', 'tool_calls': [{'id': 'action'}]}}]),
    outer(choices=[{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': '{"cells":[],"cells":[]}'}}]),
    outer(choices=[{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': '```json\n{}\n```'}}]),
    outer(usage={'prompt_tokens': True}), outer(usage={'prompt_tokens': 1, 'completion_tokens': 2, 'total_tokens': 9}),
])
def test_malformed_ambiguous_truncated_or_unexpected_outputs_rejected(payload):
    value, connection = adapter(Response(payload))
    with pytest.raises(MvpError) as error:
        value.generate(packet(), timeout_seconds=10)
    assert error.value.code == 'proposal_invalid_output' and connection.closed


@pytest.mark.parametrize('response', [
    Response(outer(), status=302), Response(outer(), status=500),
    Response(outer(), headers={'Content-Encoding': 'gzip'}),
    Response(outer(), headers={'Content-Length': '32769'}),
    Response(outer(), headers={'Content-Length': 'x'}),
    Response(b' ' * 32769), Response(outer(), headers={'Content-Length': '32768'}),
])
def test_status_size_compression_incomplete_body_rejected_without_retry(response):
    value, connection = adapter(response)
    with pytest.raises(MvpError):
        value.generate(packet(), timeout_seconds=10)
    assert len(connection.requests) == 1 and connection.closed


def test_failure_is_sanitized_and_not_retried():
    def failure(*args, **kwargs):
        raise OSError('secret endpoint body private key')
    value, _ = adapter(_connection_factory=failure)
    with pytest.raises(MvpError) as error:
        value.generate(packet(), timeout_seconds=10)
    assert error.value.code == 'proposal_provider_failure'
    assert 'secret' not in error.value.message and 'private' not in error.value.message


def test_absolute_deadline_stops_slow_fragmented_response():
    class SlowResponse(Response):
        def read1(self, size):
            time.sleep(.012)
            return super().read1(1)
    value, connection = adapter(SlowResponse(outer()))
    start = time.monotonic()
    with pytest.raises(MvpError) as error:
        value.generate(packet(), timeout_seconds=.04)
    assert error.value.code == 'proposal_generation_timeout'
    assert time.monotonic() - start < .5 and connection.closed


@pytest.mark.parametrize('timeout', [0, -1, 11, True, float('nan'), float('inf')])
def test_call_runtime_cannot_be_unbounded(timeout):
    value, connection = adapter()
    with pytest.raises(MvpError):
        value.generate(packet(), timeout_seconds=timeout)
    assert not connection.requests
