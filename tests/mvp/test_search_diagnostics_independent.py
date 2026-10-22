"""Offline diagnostic receipts do not constitute captures or recall validation."""
from hashlib import sha256
import socket
from xml.sax.saxutils import escape

import pytest

from src.mvp.adapters.search_diagnostics import PubMedSearchDiagnostics
from src.mvp.search_plan_contracts import DiagnosticSeed


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Independent search diagnostics attempted external network access")
    monkeypatch.setattr(socket, "create_connection", denied)


def esearch(count, ids=(), translation="translated query", extra=""):
    return (f"<eSearchResult><Count>{count}</Count><RetMax>{len(ids)}</RetMax><RetStart>0</RetStart>"
        f"<IdList>{''.join(f'<Id>{value}</Id>' for value in ids)}</IdList>"
        f"<QueryTranslation>{escape(translation)}</QueryTranslation>{extra}</eSearchResult>").encode()


class Transport:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def request(self, endpoint, params):
        self.calls.append((endpoint, dict(params)))
        assert endpoint == "pubmed_search", "Diagnostics must not perform EFetch, history or metadata resolution"
        return self.responses.pop(0)


def adapter(transport):
    return PubMedSearchDiagnostics(email="fixture@example.org", transport=transport)


def test_exact_strategy_and_filters_are_not_rewritten_and_diagnostic_is_not_a_capture():
    query = '  ("gut flora"[tiab])\r\n  AND women[tiab]  '
    transport = Transport(esearch(200, ["111", "333"], '"gut flora"[Title/Abstract] AND "women"[Title/Abstract]'))
    result = adapter(transport).check(query, date_from="2010-01-01", date_to="2025-12-31", sort="pub_date")
    assert result.query == transport.calls[0][1]["term"] == query
    assert result.query_sha256 == sha256(query.encode()).hexdigest()
    assert result.date_from == "2010-01-01" and result.date_to == "2025-12-31" and result.sort == "pub_date"
    params = transport.calls[0][1]
    assert params["mindate"] == "2010/01/01" and params["maxdate"] == "2025/12/31" and params["datetype"] == "pdat"
    assert params["retmax"] == 5 and "usehistory" not in params
    assert result.status == "succeeded" and result.reported_count == 200
    assert result.sample_pmids == ["111", "333"] and result.truncated_sample
    assert result.meaning == "diagnostic_not_capture_relevance_or_recall" and result.calls == 1
    assert "search_id" not in result.model_dump()


def test_seed_purpose_query_membership_and_capped_preview_recovery_are_separate():
    transport = Transport(esearch(200, ["111", "333"]), esearch(1, ["111"]))
    seeds = [DiagnosticSeed(id="construction", pmid="111", purpose="construction", approved=True),
        DiagnosticSeed(id="held-out", pmid="222", purpose="held_out", approved=True),
        DiagnosticSeed(id="unresolved-doi", doi="10.1234/known-doi", purpose="held_out", approved=True)]
    result = adapter(transport).check("reviewed query", seeds=seeds, preview_pmids=["222"])
    assert result.calls == len(transport.calls) == 2
    assert "111[UID]" in transport.calls[1][1]["term"] and "222[UID]" in transport.calls[1][1]["term"]
    assert "known-doi" not in transport.calls[1][1]["term"]
    construction, held_out, unresolved = result.seed_results
    assert construction.seed.purpose == "construction" and construction.query_membership == "matched" and construction.preview_recovery == "absent"
    assert held_out.seed.purpose == "held_out" and held_out.query_membership == "not_matched" and held_out.preview_recovery == "present"
    assert unresolved.query_membership == "unresolved" and unresolved.preview_recovery == "not_checked"
    assert all("recall" in item.reason for item in [construction, held_out])


def test_provider_errors_preserve_translation_count_and_warnings_without_membership_call():
    extra = "<ErrorList><FieldNotFound>imaginary-field</FieldNotFound></ErrorList><WarningList><PhraseNotFound>unknown phrase</PhraseNotFound></WarningList>"
    transport = Transport(esearch(0, translation="exact provider translation", extra=extra))
    result = adapter(transport).check("bad query", seeds=[DiagnosticSeed(id="seed", pmid="111", purpose="construction", approved=True)])
    assert result.status == "provider_error" and result.reported_count == 0
    assert result.query_translation == "exact provider translation" and result.sample_pmids == []
    assert [(item.code, item.message, item.severity) for item in result.messages] == [
        ("FieldNotFound", "imaginary-field", "error"), ("PhraseNotFound", "unknown phrase", "warning")]
    assert len(transport.calls) == 1 and result.seed_results[0].query_membership == "not_checked"


def test_error_only_esearch_preserves_available_translation_even_without_count():
    payload = b"<eSearchResult><ERROR>Cannot parse strategy</ERROR><QueryTranslation>partial provider translation</QueryTranslation></eSearchResult>"
    result = adapter(Transport(payload)).check("bad query")
    assert result.status == "provider_error" and result.reported_count is None
    assert result.query_translation == "partial provider translation"
    assert [(item.code, item.message) for item in result.messages] == [("ERROR", "Cannot parse strategy")]


def test_diagnostic_sample_cannot_substitute_for_failed_seed_membership():
    transport = Transport(esearch(100, ["111"]), esearch(1, ["999"]))
    result = adapter(transport).check("reviewed query", seeds=[DiagnosticSeed(id="seed", pmid="111", purpose="held_out", approved=True)])
    assert result.status == "succeeded" and result.sample_pmids == ["111"]
    assert result.error.code == "seed_membership_failed"
    assert result.seed_results[0].query_membership == "not_checked" and result.seed_results[0].preview_recovery == "not_checked"


def test_disabled_diagnostics_and_excess_seed_inputs_make_no_transport_call():
    transport = Transport()
    result = PubMedSearchDiagnostics(enabled=False, transport=transport).check("reviewed query")
    assert result.status == "not_run" and result.calls == 0 and transport.calls == []
    with pytest.raises(ValueError):
        adapter(transport).check("reviewed query", seeds=[DiagnosticSeed(id=f"seed-{index}", pmid=str(111 + index), purpose="held_out", approved=True) for index in range(4)])
    assert transport.calls == []
