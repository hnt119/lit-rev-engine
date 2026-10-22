"""Offline exact-identifier resolver checks; no scholarly or model requests."""
import json
import threading
import time
from urllib.parse import urlsplit, unquote

import pytest

from src.mvp.adapters.metadata_resolution import ExactMetadataResolver
from src.mvp.adapters.transport import endpoint_url
from src.mvp.import_contracts import ResolutionInput
from src.mvp.ports import ProviderFailure


class Transport:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def request(self, endpoint, params):
        self.requests.append((endpoint, params))
        if isinstance(self.payload, Exception):
            raise self.payload
        return json.dumps(self.payload).encode() if isinstance(self.payload, dict) else self.payload


def crossref(doi='10.1234/example', **updates):
    return {'status': 'ok', 'message': {'DOI': doi, 'title': ['Reported title'],
            'author': [{'family': 'Lee', 'given': 'H.'}, {'name': 'Asian Women Cohort'}],
            'published': {'date-parts': [[2024, 1]]}, 'container-title': ['Journal'], **updates}}


def test_exact_crossref_enrichment_is_separate_and_reports_origin():
    transport = Transport(crossref(abstract='<jats:p>Exact <jats:italic>source</jats:italic>.</jats:p>'))
    supplied = ResolutionInput(row_id='row1', doi='https://doi.org/10.1234/EXAMPLE')
    result = ExactMetadataResolver(transport).resolve([supplied])
    receipt = result.items[0]
    assert result.calls == 1 and not result.budget_exhausted
    assert transport.requests == [('crossref_work', {'doi': '10.1234/example'})]
    assert receipt.status == 'resolved'
    assert receipt.metadata.title == 'Reported title'
    assert receipt.metadata.authors == ['Lee, H.', 'Asian Women Cohort']
    assert receipt.metadata.abstract == 'Exact source .'
    assert receipt.abstract_origin == 'crossref_metadata_abstract'
    assert receipt.normalization == 'metadata-xml-fragment-text-v1'
    assert receipt.response_sha256 and receipt.requested_identifiers == receipt.returned_identifiers
    assert supplied.doi == '10.1234/example'


@pytest.mark.parametrize('payload,code', [
    (crossref(doi='10.1234/wrong'), 'identity_mismatch'),
    (crossref(DOI=None), 'identity_unconfirmed'),
    (crossref(title=[]), 'metadata_incomplete'),
    (b'not JSON', 'malformed_metadata'),
    (b'{"status":"ok","message":{"DOI":"10.1234/wrong","DOI":"10.1234/example","title":["Title"]}}', 'malformed_metadata'),
    (b'{"status":"ok","message":{"DOI":"10.1234/example","title":["Title"],"score":NaN}}', 'malformed_metadata'),
    (b'x' * (2 * 1024 * 1024 + 1), 'response_too_large'),
    (ProviderFailure('redirect_rejected', 'untrusted secret response'), 'redirect_rejected'),
])
def test_failed_identity_or_shape_never_returns_enriched_metadata(payload, code):
    result = ExactMetadataResolver(Transport(payload)).resolve([ResolutionInput(row_id='r', doi='10.1234/example')])
    item = result.items[0]
    assert item.status in {'conflict', 'unresolved'}
    assert item.metadata is None and item.error.code == code
    assert 'secret' not in item.model_dump_json()


def test_pmid_exact_query_checks_all_requested_ids_and_never_falls_back():
    transport = Transport({'resultList': {'result': [{'id': '123', 'source': 'MED', 'doi': '10.1234/wrong',
                           'title': 'Wrong DOI', 'abstractText': 'Reported abstract'}]}})
    receipt = ExactMetadataResolver(transport).resolve([ResolutionInput(row_id='r', pmid='123', doi='10.1234/example')]).items[0]
    assert receipt.status == 'conflict' and receipt.metadata is None
    assert transport.requests == [('europe_search', {'query': 'EXT_ID:123 AND SRC:MED', 'format': 'json', 'resultType': 'core', 'pageSize': '5'})]


def test_pmcid_only_is_explicitly_unsupported_without_a_request():
    transport = Transport({})
    result = ExactMetadataResolver(transport).resolve([ResolutionInput(row_id='r', pmcid='PMC123')])
    assert result.calls == 0 and transport.requests == []
    assert result.items[0].error.code == 'unsupported_identifier'


def test_no_hidden_calls_on_invalid_batch():
    transport = Transport({})
    resolver = ExactMetadataResolver(transport)
    with pytest.raises(ValueError):
        resolver.resolve([ResolutionInput(row_id=str(n), doi='10.1234/example') for n in range(4)])
    with pytest.raises(ValueError):
        resolver.resolve([ResolutionInput(row_id='same', doi='10.1234/example')] * 2)
    assert transport.requests == []


def test_runtime_returns_discards_late_response_and_does_not_pile_up():
    entered, release = threading.Event(), threading.Event()

    class BlockingTransport(Transport):
        def request(self, endpoint, params):
            entered.set()
            release.wait(1)
            return super().request(endpoint, params)

    transport = BlockingTransport(crossref())
    resolver = ExactMetadataResolver(transport)
    inputs = [ResolutionInput(row_id='r', doi='10.1234/example')]
    started = time.monotonic()
    try:
        timed = resolver.resolve(inputs, max_runtime_seconds=.03)
        assert entered.is_set() and time.monotonic() - started < .5
        assert timed.budget_exhausted and timed.calls == 1
        assert timed.items[0].metadata is None and timed.items[0].error.code == 'resolution_runtime_limit'
        busy = resolver.resolve(inputs, max_runtime_seconds=.03)
        assert busy.calls == 0 and busy.items[0].error.code == 'resolver_busy'
        assert timed.items[0].metadata is None
    finally:
        release.set()


def test_fixed_crossref_endpoint_encodes_entire_doi_path_and_rejects_other_params():
    doi = '10.1234/a;literal.(1)/nested?still-doi'
    url, query, host = endpoint_url('crossref_work', {'doi': doi})
    parsed = urlsplit(url)
    assert host == 'api.crossref.org' and query == {} and not parsed.query
    assert unquote(parsed.path) == '/works/' + doi
    with pytest.raises(ProviderFailure):
        endpoint_url('crossref_work', {'url': 'https://localhost/private'})
