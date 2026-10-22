import threading
import time

import pytest

from src.mvp.adapters.search_diagnostics import PubMedSearchDiagnostics, parse_diagnostic_esearch
from src.mvp.ports import ProviderFailure
from src.mvp.search_plan_contracts import DiagnosticSeed


def response(ids=(), count=None, extra=''):
    return (f'<eSearchResult><Count>{len(ids) if count is None else count}</Count>'
            f'<RetMax>{len(ids)}</RetMax><RetStart>0</RetStart><IdList>'
            + ''.join(f'<Id>{value}</Id>' for value in ids)
            + '</IdList><QueryTranslation>translated</QueryTranslation>' + extra + '</eSearchResult>').encode()


class Transport:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def request(self, endpoint, params):
        self.calls.append((endpoint, dict(params)))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def test_disabled_diagnostics_and_construction_never_call_transport():
    transport = Transport()
    adapter = PubMedSearchDiagnostics(transport=transport)
    assert not adapter.capability()['enabled']
    assert adapter.check('women').status == 'not_run'
    assert transport.calls == []


def test_esearch_errors_are_retained_not_hidden_by_legacy_parser():
    value = parse_diagnostic_esearch(b'<eSearchResult><ErrorList><FieldNotFound>bad field</FieldNotFound></ErrorList></eSearchResult>')
    assert value['status'] == 'provider_error'
    assert value['messages'][0].code == 'FieldNotFound'
    assert value['reported_count'] is None


def test_zero_results_warnings_and_exact_filters():
    transport = Transport(response(extra='<WarningList><PhraseIgnored>x</PhraseIgnored></WarningList>'))
    value = PubMedSearchDiagnostics(email='test@example.org', transport=transport).check('  x  ',
        date_from='2020-01-01', date_to='2024-12-31', sort='pub_date')
    assert value.status == 'succeeded' and value.reported_count == 0
    assert value.query == '  x  ' and value.query_translation == 'translated'
    assert value.messages[0].severity == 'warning' and len(value.response_sha256) == 64
    endpoint, params = transport.calls[0]
    assert endpoint == 'pubmed_search' and params['term'] == '  x  '
    assert params['sort'] == 'pub_date' and params['mindate'] == '2020/01/01'
    assert 'usehistory' not in params and len(transport.calls) == 1


def test_seed_query_membership_is_separate_from_preview_recovery_and_tuning_role():
    transport = Transport(response(['10'], 100), response(['20']))
    seeds = [DiagnosticSeed(id='known', pmid='20', purpose='construction', approved=True),
             DiagnosticSeed(id='held', pmid='30', purpose='held_out', approved=True),
             DiagnosticSeed(id='doi', doi='10.1234/a', purpose='held_out', approved=True)]
    value = PubMedSearchDiagnostics(email='test@example.org', transport=transport).check('women', seeds=seeds, preview_pmids=['30'])
    assert value.status == 'succeeded' and value.calls == 2 and value.truncated_sample
    assert '20[UID]' in transport.calls[1][1]['term'] and '30[UID]' in transport.calls[1][1]['term']
    assert value.seed_results[0].query_membership == 'matched'
    assert value.seed_results[0].preview_recovery == 'absent'
    assert value.seed_results[0].seed.purpose == 'construction'
    assert value.seed_results[1].query_membership == 'not_matched'
    assert value.seed_results[1].preview_recovery == 'present'
    assert value.seed_results[2].query_membership == 'unresolved'
    assert value.seed_results[2].preview_recovery == 'not_checked'


@pytest.mark.parametrize('payload', [b'bad', b'<wrong/>',
    b'<!DOCTYPE x [<!ENTITY y "x">]><eSearchResult>&y;</eSearchResult>',
    response(['10', '10']), response(['10'], 0),
    response(['10']).replace(b'<RetStart>0', b'<RetStart>1')])
def test_unsafe_or_inconsistent_xml_fails_without_fetch(payload):
    transport = Transport(payload)
    result = PubMedSearchDiagnostics(email='test@example.org', transport=transport).check('women')
    assert result.status == 'failed' and result.error
    assert len(transport.calls) == 1


def test_provider_failure_has_no_fallback_or_raw_error_body():
    transport = Transport(ProviderFailure('timeout', 'private credential', True))
    result = PubMedSearchDiagnostics(email='test@example.org', transport=transport).check('women')
    assert result.status == 'failed' and result.error.retryable
    assert 'private credential' not in result.model_dump_json()
    assert result.calls == 1


def test_provider_failure_preserves_each_approved_seed_and_independent_preview_binding():
    transport = Transport(ProviderFailure('timeout', 'private', True))
    seeds = [DiagnosticSeed(id='s', pmid='1', purpose='held_out', approved=True),
             DiagnosticSeed(id='doi', doi='10.1234/a', purpose='construction', approved=True)]
    result = PubMedSearchDiagnostics(email='test@example.org', transport=transport).check('women', seeds=seeds, preview_pmids=['1'])
    assert [item.seed for item in result.seed_results] == seeds
    assert result.seed_results[0].query_membership == 'not_checked'
    assert result.seed_results[0].preview_recovery == 'present'
    assert result.seed_results[1].query_membership == 'unresolved'


def test_absolute_runtime_and_busy_slot_prevent_more_requests_after_timeout():
    release = threading.Event()

    class Blocked(Transport):
        def request(self, endpoint, params):
            self.calls.append((endpoint, params))
            release.wait(2)
            return response(['1'])

    transport = Blocked()
    adapter = PubMedSearchDiagnostics(email='test@example.org', transport=transport, max_runtime_seconds=.02)
    seed = DiagnosticSeed(id='s', pmid='1', purpose='held_out', approved=True)
    started = time.monotonic()
    result = adapter.check('women', seeds=[seed])
    assert time.monotonic() - started < .5 and result.error.code == 'query_diagnostics_timeout'
    assert adapter.check('women').error.code == 'query_diagnostics_busy'
    release.set()
    for _ in range(100):
        if adapter._slot.acquire(False):
            adapter._slot.release()
            break
        time.sleep(.002)
    assert len(transport.calls) == 1
