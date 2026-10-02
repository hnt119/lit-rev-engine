"""Small unit cases complement independent saved-response acceptance fixtures."""

import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs

import pytest

from src.review.importers import load_records
from src.search.pubmed_search import PubMedClient, PubMedError, capture_pubmed_search


def search(pmids=("1", "2"), count=None):
    count = len(pmids) if count is None else count
    ids = "".join(f"<Id>{pmid}</Id>" for pmid in pmids)
    history = "<WebEnv>synthetic</WebEnv><QueryKey>1</QueryKey>" if count else ""
    return f"<eSearchResult><Count>{count}</Count><RetStart>0</RetStart><RetMax>{len(pmids)}</RetMax><IdList>{ids}</IdList><QueryTranslation>synthetic</QueryTranslation>{history}</eSearchResult>".encode()


def fetch(pmids=("2", "1")):
    records = "".join(f"<PubmedArticle><MedlineCitation><PMID>{pmid}</PMID><Article><ArticleTitle>Synthetic software fixture {pmid}</ArticleTitle></Article></MedlineCitation></PubmedArticle>" for pmid in pmids)
    return f"<PubmedArticleSet>{records}</PubmedArticleSet>".encode()


class Client:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, endpoint, params):
        self.calls.append((endpoint, params))
        response = next(self.responses)
        if isinstance(response, BaseException):
            raise response
        return response


def test_capture_saved_hashes_and_search_order(tmp_path):
    original_search, original_fetch = search(), fetch()
    client = Client(original_search, original_fetch)
    result = capture_pubmed_search("  synthetic\nquery  ", tmp_path / "capture", client=client, filters={"datetype": "edat", "mindate": "2024/02", "maxdate": "2024/02/29"})
    destination = Path(result["directory"])
    assert (destination / "search.xml").read_bytes() == original_search
    assert (destination / "batches/0001.xml").read_bytes() == original_fetch
    receipt = json.loads((destination / "receipt.json").read_text())
    assert receipt == result["receipt"]
    assert receipt["query"] == "  synthetic\nquery  "
    assert receipt["pmids"] == ["1", "2"]
    assert [record.pmid for record in load_records(result["xml_file"])] == ["1", "2"]
    assert receipt["records_sha256"] == hashlib.sha256((destination / "records.xml").read_bytes()).hexdigest()
    for request in receipt["requests"]:
        assert request["response_sha256"] == hashlib.sha256((destination / request["response_file"]).read_bytes()).hexdigest()
    assert client.calls[0][1]["retmax"] == 10000
    assert client.calls[1][1]["id"] == "1,2"


def test_zero_capture_without_fetch_or_history(tmp_path):
    client = Client(search(()))
    result = capture_pubmed_search("synthetic", tmp_path / "zero", client=client)
    assert len(client.calls) == 1
    assert load_records(result["xml_file"]) == []
    assert result["receipt"]["history"] == {"webenv": None, "query_key": None}
    assert result["receipt"]["complete"] is True
    assert result["receipt"]["reported_count"] == result["receipt"]["fetched_count"] == 0


@pytest.mark.parametrize("response", [search(count=10001), search(("1", "1")), search(count=3), b"<eSearchResult><ERROR>secret</ERROR></eSearchResult>", b"<invalid>", b'<!DOCTYPE eSearchResult [<!ENTITY leak "secret">]><eSearchResult />'])
def test_invalid_search_cleans_staging_without_fetch(tmp_path, response):
    client = Client(response)
    with pytest.raises(PubMedError):
        capture_pubmed_search("synthetic", tmp_path / "failed", client=client)
    assert len(client.calls) == 1
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("response", [fetch(("1",)), fetch(("1", "3")), fetch(("1", "1")), b"<PubmedArticleSet><ERROR>secret</ERROR></PubmedArticleSet>", KeyboardInterrupt()])
def test_invalid_or_interrupted_fetch_publishes_nothing(tmp_path, response):
    with pytest.raises((PubMedError, KeyboardInterrupt)):
        capture_pubmed_search("synthetic", tmp_path / "failed", client=Client(search(), response))
    assert list(tmp_path.iterdir()) == []


def test_existing_and_concurrently_created_destinations_are_preserved(tmp_path):
    destination = tmp_path / "capture"
    destination.mkdir()
    marker = destination / "keep"
    marker.write_text("original")
    with pytest.raises(PubMedError, match="absent"):
        capture_pubmed_search("synthetic", destination, client=Client())
    assert marker.read_text() == "original"
    marker.unlink()
    destination.rmdir()

    class ConcurrentDestination(Client):
        def request(self, endpoint, params):
            if endpoint == "efetch.fcgi":
                destination.mkdir()
                marker.write_text("concurrent")
            return super().request(endpoint, params)

    with pytest.raises(PubMedError, match="absent"):
        capture_pubmed_search("synthetic", destination, client=ConcurrentDestination(search(), fetch()))
    assert marker.read_text() == "concurrent"
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize("filters", [
    {"datetype": "mdat", "mindate": "2024", "maxdate": "2025"},
    {"mindate": "2024"},
    {"datetype": "pdat", "mindate": "2024/02/30", "maxdate": "2025"},
    {"datetype": "pdat", "mindate": "2025/01", "maxdate": "2024/12"},
])
def test_invalid_filters_fail_before_creating_capture(tmp_path, filters):
    client = Client()
    with pytest.raises(PubMedError):
        capture_pubmed_search("synthetic", tmp_path / "invalid", client=client, filters=filters)
    assert client.calls == []
    assert list(tmp_path.iterdir()) == []


def test_client_configuration_only_enters_transport_not_input_or_errors():
    sent = []
    client = PubMedClient("synthetic@example.invalid", "test-secret", transport=lambda url, data, timeout: sent.append((url, parse_qs(data.decode()), timeout)) or b"xml")
    params = {"db": "pubmed", "term": "synthetic"}
    assert client.request("esearch.fcgi", params) == b"xml"
    assert params == {"db": "pubmed", "term": "synthetic"}
    assert sent[0][1]["api_key"] == ["test-secret"]
    assert sent[0][1]["email"] == ["synthetic@example.invalid"]
    assert sent[0][1]["tool"] == ["lit-rev-engine"]
    with pytest.raises(PubMedError):
        client.request("https://example.com/test-secret", params)
    assert len(sent) == 1


def test_nonbyte_transport_and_unexpected_error_are_not_retried():
    calls = []
    client = PubMedClient("synthetic@example.invalid", transport=lambda *args: calls.append(args) or "malformed")
    with pytest.raises(PubMedError, match="bytes"):
        client.request("esearch.fcgi", {})
    assert len(calls) == 1

    def broken(*args):
        raise RuntimeError("test-secret synthetic@example.invalid")

    client = PubMedClient("synthetic@example.invalid", "test-secret", transport=broken)
    with pytest.raises(PubMedError) as failure:
        client.request("esearch.fcgi", {})
    assert "test-secret" not in str(failure.value)
    assert "synthetic@example.invalid" not in str(failure.value)
