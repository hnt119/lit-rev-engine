"""Provider-specific offline tests; synthetic records never power saved mode."""

from hashlib import sha256
import json
from pathlib import Path
import socket
from urllib.error import HTTPError, URLError

import pytest
from pydantic import ValidationError

from src.mvp.adapters.europe_pmc import EuropePmcSourceProvider, prepare_permitted_xml, supported_license
from src.mvp.adapters.pubmed import PubMedPreviewProvider, parse_esearch_preview, parse_pubmed_sample
from src.mvp.adapters.saved_examples import SavedExampleProvider, saved_example_info
from src.mvp.adapters.transport import BoundedTransport, safe_xml
from src.mvp.contracts import Paper, SearchRequest
from src.mvp.ports import ProviderFailure


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Normal provider tests must remain offline")
    monkeypatch.setattr(socket, "create_connection", forbidden)


class Transport:
    def __init__(self, *responses):
        self.responses, self.calls = iter(responses), []
    def request(self, endpoint, params):
        self.calls.append((endpoint, params))
        response = next(self.responses)
        if isinstance(response, BaseException):
            raise response
        return response


def esearch(ids=("1",), total=1):
    return (f"<eSearchResult><Count>{total}</Count><RetMax>{len(ids)}</RetMax><RetStart>0</RetStart>"
            "<IdList>" + "".join(f"<Id>{i}</Id>" for i in ids) + "</IdList>"
            "<QueryTranslation>synthetic exact translation</QueryTranslation>"
            "<WarningList><PhraseIgnored>synthetic warning</PhraseIgnored></WarningList></eSearchResult>").encode()


def citation(pmid="1", doi="10.1234/software.1"):
    return (f"<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>{pmid}</PMID><Article>"
            "<ArticleTitle>Synthetic test article, not a real publication</ArticleTitle>"
            "<Abstract><AbstractText>女人 😀 microbiome.</AbstractText></Abstract>"
            "</Article></MedlineCitation><PubmedData><ArticleIdList>"
            f'<ArticleId IdType="doi">{doi}</ArticleId>'
            '<ArticleId IdType="pmc">PMC1</ArticleId>'
            "</ArticleIdList></PubmedData></PubmedArticle></PubmedArticleSet>").encode()


def test_large_reported_count_does_not_inherit_complete_capture_10000_limit():
    preview = parse_esearch_preview(esearch(total=123456), 30)
    assert preview["total_reported"] == 123456
    assert preview["ordered_identifiers"] == ["1"] and preview["truncated"]
    assert "synthetic warning" in " ".join(preview["warnings"])


@pytest.mark.parametrize("identifiers", [("0",), ("abc",), ("1", "2")])
def test_invalid_or_over_cap_membership_is_rejected(identifiers):
    with pytest.raises(ProviderFailure):
        parse_esearch_preview(esearch(identifiers, total=2), 1)


def test_repeated_provider_id_is_reported_and_never_fetched_twice():
    transport = Transport(esearch(("1", "1"), total=2), citation())
    result = PubMedPreviewProvider("software@example.org", transport=transport).search(
        SearchRequest(request_id="dedup", query="synthetic test only"))
    assert result.ordered_identifiers == ["1"] and result.fetched_count == 1
    assert transport.calls[1][1]["id"] == "1"
    assert any("Duplicate PMID" in warning for warning in result.warnings)
    assert result.papers[0].pmcid == "PMC1"


def test_fetched_record_count_preserved_separately_from_unique_papers():
    single = citation()
    row = single.removeprefix(b"<PubmedArticleSet>").removesuffix(b"</PubmedArticleSet>")
    transport = Transport(esearch(), b"<PubmedArticleSet>" + row + row + b"</PubmedArticleSet>")
    result = PubMedPreviewProvider("software@example.org", transport=transport).search(
        SearchRequest(request_id="duplicate-citations", query="synthetic test only", max_results=30))
    assert result.fetched_count == 2 and len(result.papers) == 1
    assert any("repeated" in warning for warning in result.warnings)


@pytest.mark.parametrize("date_from,date_to", [
    ("2020-01-01", None), (None, "2021-12-31"),
])
def test_one_sided_dates_rejected_instead_of_silently_ignored_or_invented(date_from, date_to):
    transport = Transport(esearch((), 0))
    with pytest.raises(ValidationError, match="both start and end dates"):
        PubMedPreviewProvider("software@example.org", transport=transport).search(
            SearchRequest(request_id="dates", query="synthetic test", date_from=date_from, date_to=date_to))
    assert not transport.calls


def test_missing_own_pmid_cannot_be_rescued_by_requested_pmid_in_an_abstract():
    payload = citation().replace(b"<PMID>1</PMID>", b"").replace(b"microbiome.", b"microbiome PMID 1.")
    with pytest.raises(ProviderFailure) as error:
        parse_pubmed_sample(payload, ["1"])
    assert error.value.code == "identity_mismatch"


@pytest.mark.parametrize("license", [None, "", "CC BY-NC", "CC BY-SA", "CC BY-ND", "open access", "CC BY-NC-ND 4.0"])
def test_open_or_restricted_strings_do_not_grant_retention(license):
    assert supported_license(license) is None


@pytest.mark.parametrize("license", ["cc by", "CC-BY-4.0", "CC0", "https://creativecommons.org/licenses/by/4.0/",
                                    "https://creativecommons.org/publicdomain/zero/1.0/"])
def test_only_explicit_supported_licenses_grant_retention(license):
    assert supported_license(license)


def test_wrong_metadata_identity_stops_before_xml_download():
    transport = Transport(json.dumps({"resultList": {"result": [{
        "source": "MED", "pmid": "2", "doi": "10.1234/wrong", "pmcid": "PMC2",
        "isOpenAccess": "Y", "license": "CC BY",
    }]}}).encode())
    paper = Paper(title="Synthetic test", pmid="1", doi="10.1234/software.1", abstract="Original abstract.")
    source = EuropePmcSourceProvider(transport=transport).prepare(paper)
    assert len(transport.calls) == 1
    assert source.status == "identity_mismatch" and source.source_type == "abstract"
    assert source.blocks[0].text == paper.abstract and source.retained_content_utf8 is None


def test_metadata_service_error_is_structured_without_echoing_response_body():
    transport = Transport(b'{"error":"secret-provider-detail"}')
    source = EuropePmcSourceProvider(transport=transport).prepare(Paper(title="Synthetic test", pmid="1"))
    assert source.status == "fetch_failed" and source.source_type == "none"
    assert source.error.code == "malformed_metadata"
    assert "secret-provider-detail" not in source.model_dump_json()


def test_core_metadata_abstract_is_available_when_discovery_has_none():
    payload = json.dumps({"resultList": {"result": [{
        "source": "MED", "pmid": "1", "doi": "10.1234/software.1", "isOpenAccess": "N",
        "abstractText": "<h4>Background</h4>Synthetic 女人 😀 microbiome abstract.",
    }]}}).encode()
    paper = Paper(title="Synthetic test", pmid="1", doi="10.1234/software.1")
    source = EuropePmcSourceProvider(transport=Transport(payload)).prepare(paper)
    assert source.status == "permission_unresolved" and source.source_type == "abstract"
    assert source.blocks[0].text == "Background Synthetic 女人 😀 microbiome abstract."
    assert source.parser_metadata["origin"] == "europe_pmc_core_abstract"
    assert source.parser_metadata["metadata_response_sha256"] == sha256(payload).hexdigest()
    assert source.retained_content_utf8 is None


def test_xml_external_doctype_is_ignored_without_network_but_entities_rejected():
    root = safe_xml(b'<!DOCTYPE x SYSTEM "https://untrusted.invalid/doctype"><x>safe</x>')
    assert root.text == "safe"
    with pytest.raises(ProviderFailure):
        safe_xml(b'<!DOCTYPE x [<!ENTITY a "expanded">]><x>&a;</x>')


@pytest.mark.parametrize("value", ["https://provider.invalid/?api_key=secret", "secret-network-error"])
def test_network_errors_never_expose_secret_or_url(value):
    def opener(request, timeout):
        raise URLError(value)
    transport = BoundedTransport(opener=opener, max_attempts=1, sleep=lambda _: None)
    with pytest.raises(ProviderFailure) as error:
        transport.request("pubmed_search", {"api_key": "secret"})
    assert value not in str(error.value) and "secret" not in str(error.value)


def test_long_retry_after_ends_operation_instead_of_unbounded_wait():
    calls, sleeps = [], []
    def opener(request, timeout):
        calls.append(request)
        raise HTTPError(request.full_url, 429, "secret", {"Retry-After": "3600"}, None)
    transport = BoundedTransport(opener=opener, sleep=sleeps.append)
    with pytest.raises(ProviderFailure) as error:
        transport.request("pubmed_search", {})
    assert len(calls) == 1 and error.value.code == "rate_limited" and error.value.retryable
    assert all(delay < 3 for delay in sleeps)


def test_real_saved_example_integrity_provenance_and_no_query_substitution():
    provider = SavedExampleProvider()
    info = saved_example_info()
    preview = provider.search(SearchRequest(request_id="offline", query="ARBITRARY NOT EXECUTED",
                                            date_from="1900-01-01", date_to="1901-01-01"))
    assert preview.mode == "saved_example" and preview.provider == "europe_pmc_saved_example"
    assert preview.query == info["query"] and preview.query != "ARBITRARY NOT EXECUTED"
    assert preview.searched_at == info["searched_at"]
    assert preview.total_reported == 9 and preview.fetched_count == len(preview.papers) == 1
    assert preview.date_from is None and preview.date_to is None
    assert preview.truncated and any("not executed" in warning for warning in preview.warnings)
    paper = preview.papers[0]
    source = provider.prepare(paper)
    assert paper.pmid == "42051515" and paper.pmcid == "PMC13110953"
    assert source.source_type == "full_text" and source.status == "full_text_retrieved"
    assert source.source_identifiers["pmid"] == paper.pmid
    assert source.source_identifiers["doi"] == paper.doi
    assert source.source_identifiers["pmcid"] == paper.pmcid
    assert source.source_sha256 == sha256(source.retained_content_utf8.encode()).hexdigest()
    assert source.license == "https://creativecommons.org/licenses/by/4.0/"
    assert "Zheng" in source.attribution and "Chinese" in paper.title
    assert all("page" not in block.locator for block in source.blocks)


def test_tampered_saved_source_is_not_treated_as_checked_example(tmp_path):
    root = Path(__file__).resolve().parents[1] / "fixtures" / "mvp"
    for file in root.iterdir():
        if file.is_file():
            (tmp_path / file.name).write_bytes(file.read_bytes())
    xml = tmp_path / "PMC13110953.xml"
    xml.write_bytes(xml.read_bytes() + b"\n")
    with pytest.raises(ProviderFailure) as error:
        SavedExampleProvider(fixture_dir=tmp_path)
    assert error.value.code == "saved_example_unavailable"


def test_saved_provider_rejects_publication_outside_curated_membership():
    provider = SavedExampleProvider()
    outside = provider.prepare(Paper(title="Synthetic outside fixture", pmid="1", abstract="Synthetic abstract."))
    assert outside.status == "identity_mismatch" and outside.retained_content_utf8 is None
