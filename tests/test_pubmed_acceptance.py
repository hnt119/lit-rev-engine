"""Independent offline acceptance evidence for captured PubMed membership."""

from copy import deepcopy
from datetime import datetime, timezone
from email.message import Message
import hashlib
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs
import xml.etree.ElementTree as ET

import pytest

from src.review.importers import load_records
from src.search.pubmed_search import PubMedClient, capture_pubmed_search


FIXTURES = Path(__file__).parent / "fixtures" / "pubmed"
ROOT = Path(__file__).resolve().parents[1]
QUERY = '("Postoperative Care"[MeSH Terms])\nAND synthetic[Title/Abstract]'
EMAIL = "synthetic-reviewer@example.invalid"
SECRET = "SYNTHETIC_ACCEPTANCE_KEY_7f319"
NOW = datetime(2026, 10, 3, 4, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def forbid_live_requests_and_sleeps(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Acceptance attempted a live request or a real sleep")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr("time.sleep", denied)


class FixtureClient:
    def __init__(self, responses, on_call=None):
        self.responses = list(responses)
        self.calls = []
        self.on_call = on_call

    def request(self, endpoint, params):
        self.calls.append({"endpoint": endpoint, "params": deepcopy(params)})
        assert self.responses, "Unexpected adapter request"
        outcome = self.responses.pop(0)
        if self.on_call is not None:
            self.on_call(len(self.calls))
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def xml_bytes(root):
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def change_search(response, field, value):
    root = ET.fromstring(response)
    element = root.find(field)
    assert element is not None
    if value is None:
        root.remove(element)
    else:
        element.text = value
    return xml_bytes(root)


def change_record_pmid(response, old, new):
    root = ET.fromstring(response)
    changed = 0
    for element in root.iter():
        if element.tag == "PMID" or (element.tag == "ArticleId" and element.get("IdType") in ("pubmed", "pmid")):
            if element.text == old:
                element.text = new
                changed += 1
    assert changed
    return xml_bytes(root)


def assert_capture_absent_and_staging_clean(tmp_path, destination, before):
    assert not destination.exists()
    assert set(tmp_path.iterdir()) == before


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        assert seconds >= 0
        self.sleeps.append(seconds)
        self.now += seconds


class ScriptedTransport:
    def __init__(self, outcomes, clock=None):
        self.outcomes = list(outcomes)
        self.clock = clock or FakeClock()
        self.calls = []

    def __call__(self, url, data, timeout):
        self.calls.append({
            "url": url, "params": parse_qs(data.decode("utf-8")),
            "timeout": timeout, "at": self.clock.now,
        })
        assert self.outcomes, "Unexpected transport request"
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def client_for(outcomes, api_key=None, max_attempts=3):
    clock = FakeClock()
    transport = ScriptedTransport(outcomes, clock)
    client = PubMedClient(EMAIL, api_key=api_key, transport=transport,
                          sleep=clock.sleep, monotonic=clock.monotonic, max_attempts=max_attempts)
    return client, clock, transport


def http_error(status, retry_after=None):
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return HTTPError(
        "https://example.invalid/?api_key=" + SECRET, status, "Message " + SECRET,
        headers, io.BytesIO(("Response body " + SECRET).encode()),
    )


@pytest.mark.parametrize("api_key,interval", [(None, 1 / 3), (SECRET, 0.1)])
def test_client_throttles_every_attempt_and_posts_only_to_fixed_ncbi_endpoints(api_key, interval):
    client, clock, transport = client_for([b"<ok />"] * 12, api_key=api_key)
    for index in range(12):
        endpoint = "esearch.fcgi" if index % 2 == 0 else "efetch.fcgi"
        assert client.request(endpoint, {"db": "pubmed", "term": QUERY}) == b"<ok />"
    times = [call["at"] for call in transport.calls]
    assert all(later - earlier >= interval - 1e-9 for earlier, later in zip(times, times[1:]))
    assert len(transport.calls) == 12 and len(clock.sleeps) >= 11
    for call in transport.calls:
        assert call["url"] in {
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
        }
        assert call["params"]["term"] == [QUERY]
        assert call["params"]["tool"] == ["lit-rev-engine"]
        assert call["params"]["email"] == [EMAIL]
        assert call["timeout"] > 0
        assert call["params"].get("api_key") == ([api_key] if api_key else None)
    before = len(transport.calls)
    with pytest.raises(ValueError):
        client.request("https://example.invalid/collect", {"db": "pubmed"})
    assert len(transport.calls) == before


@pytest.mark.parametrize("transient", [http_error(429), http_error(500), http_error(503), URLError("temporary"), TimeoutError("temporary")])
def test_transient_failures_retry_with_bounded_attempts_and_throttle(transient):
    client, clock, transport = client_for([transient, transient, b"success"])
    assert client.request("esearch.fcgi", {"db": "pubmed"}) == b"success"
    assert len(transport.calls) == 3
    times = [call["at"] for call in transport.calls]
    assert times[1] - times[0] >= 1 / 3
    assert times[2] - times[1] >= 1 / 3
    assert times[2] - times[1] >= times[1] - times[0]
    assert clock.sleeps
    failed_client, _, failed_transport = client_for([transient] * 4)
    with pytest.raises(ValueError):
        failed_client.request("esearch.fcgi", {"db": "pubmed"})
    assert len(failed_transport.calls) == 3


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_permanent_http_errors_are_not_retried_and_secrets_are_redacted(status):
    client, _, transport = client_for([http_error(status), b"Must not be requested"], api_key=SECRET)
    with pytest.raises(ValueError) as failure:
        client.request("esearch.fcgi", {"db": "pubmed"})
    assert len(transport.calls) == 1
    assert SECRET not in str(failure.value)
    assert EMAIL not in str(failure.value)
    assert "api_key=" not in str(failure.value)


def test_secret_bearing_transport_error_is_redacted_after_retry_exhaustion():
    client, _, transport = client_for([URLError(f"email={EMAIL}&api_key={SECRET}")] * 3, api_key=SECRET)
    with pytest.raises(ValueError) as failure:
        client.request("esearch.fcgi", {"db": "pubmed"})
    assert len(transport.calls) == 3
    assert SECRET not in str(failure.value) and EMAIL not in str(failure.value)


@pytest.mark.parametrize("retry_after,expected_minimum", [("7", 7), ("Sat, 03 Oct 2026 04:00:09 GMT", 9)])
def test_retry_after_seconds_and_http_date_use_injected_clock(monkeypatch, retry_after, expected_minimum):
    monkeypatch.setattr("src.search.pubmed_search._utc_now", lambda: NOW)
    client, _, transport = client_for([http_error(429, retry_after), b"success"])
    assert client.request("esearch.fcgi", {"db": "pubmed"}) == b"success"
    assert transport.calls[1]["at"] - transport.calls[0]["at"] >= expected_minimum


@pytest.mark.parametrize("overrides", [
    {"email": ""}, {"email": "  "}, {"tool": ""}, {"timeout": 0},
    {"timeout": float("inf")}, {"timeout": float("nan")},
    {"max_attempts": 0}, {"max_attempts": True}, {"max_attempts": 1.5},
])
def test_invalid_client_configuration_fails_without_network(overrides):
    fields = {"email": EMAIL, "transport": lambda *args: pytest.fail("Network attempted")}
    fields.update(overrides)
    with pytest.raises(ValueError):
        PubMedClient(**fields)


@pytest.fixture
def capture_oracle():
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    # Literal hand-computed truth, independently documented by R4, not production output.
    assert manifest["ordered_pmids"] == ["999999803", "999999801", "999999805", "999999802", "999999804"]
    assert manifest["reported_count"] == 5
    responses = [(FIXTURES / manifest["search_file"]).read_bytes()]
    responses.extend((FIXTURES / batch["response_file"]).read_bytes() for batch in manifest["batches"])
    return manifest, responses


def run_fixture_capture(tmp_path, capture_oracle, responses=None, client=None, **overrides):
    manifest, originals = capture_oracle
    fields = {
        "client": client or FixtureClient(responses if responses is not None else originals),
        "sort": manifest["sort"], "filters": deepcopy(manifest["filters"]),
        "batch_size": manifest["batch_size"],
    }
    fields.update(overrides)
    destination = tmp_path / "capture"
    return capture_pubmed_search(manifest["query"], destination, **fields), fields["client"]


def test_complete_capture_proves_membership_order_source_bytes_and_offline_replay(tmp_path, monkeypatch, capture_oracle):
    monkeypatch.setattr("src.search.pubmed_search._utc_now", lambda: NOW)
    manifest, responses = capture_oracle
    result, client = run_fixture_capture(tmp_path, capture_oracle)
    destination = tmp_path / "capture"
    assert Path(result["directory"]) == destination.resolve()
    assert Path(result["xml_file"]) == (destination / "records.xml").resolve()
    assert Path(result["receipt_file"]) == (destination / "receipt.json").resolve()
    receipt = result["receipt"]
    assert json.loads((destination / "receipt.json").read_text(encoding="utf-8")) == receipt
    assert set(receipt) == {
        "schema_version", "source", "adapter", "query", "query_translation", "sort", "filters",
        "started_at", "searched_at", "completed_at", "reported_count", "pmids", "fetched_count",
        "complete", "warnings", "history", "requests", "records_file", "records_sha256",
    }
    assert receipt["schema_version"] == 1 and receipt["source"] == "PubMed"
    assert receipt["adapter"] == "lit-rev-engine.pubmed.v1"
    assert receipt["query"] == manifest["query"]  # Deliberate leading/trailing spaces survive.
    assert receipt["query_translation"] == manifest["query_translation"]
    assert receipt["filters"] == manifest["filters"] and receipt["sort"] == manifest["sort"]
    assert receipt["reported_count"] == receipt["fetched_count"] == 5
    assert receipt["pmids"] == manifest["ordered_pmids"]
    assert receipt["complete"] is True
    assert receipt["warnings"] == manifest["warnings"] and receipt["history"] == manifest["history"]
    timestamps = [datetime.fromisoformat(receipt[key].replace("Z", "+00:00")) for key in ("started_at", "searched_at", "completed_at")]
    assert timestamps == [NOW] * 3
    assert all(value.utcoffset().total_seconds() == 0 for value in timestamps)
    expected_params = {
        "db": "pubmed", "term": manifest["query"], "retmode": "xml", "retstart": "0",
        "retmax": "10000", "usehistory": "y", "sort": "pub_date", **manifest["filters"],
    }
    assert client.calls[0]["endpoint"] == "esearch.fcgi"
    assert {key: str(value) for key, value in client.calls[0]["params"].items()} == expected_params
    assert len(client.calls) == len(receipt["requests"]) == 4
    for index, batch in enumerate(manifest["batches"], 1):
        assert client.calls[index]["endpoint"] == "efetch.fcgi"
        assert client.calls[index]["params"] == {
            "db": "pubmed", "retmode": "xml", "id": ",".join(batch["requested_pmids"]),
        }
    for index, (request, call, source_bytes) in enumerate(zip(receipt["requests"], client.calls, responses)):
        name = "search.xml" if index == 0 else f"batches/{index:04}.xml"
        assert request == {
            "endpoint": call["endpoint"], "params": call["params"], "response_file": name,
            "response_sha256": hashlib.sha256(source_bytes).hexdigest(),
        }
        assert (destination / name).read_bytes() == source_bytes
    combined = (destination / "records.xml").read_bytes()
    assert receipt["records_file"] == "records.xml"
    assert receipt["records_sha256"] == hashlib.sha256(combined).hexdigest()
    records = load_records(destination / "records.xml")
    assert [record.pmid for record in records] == manifest["ordered_pmids"]
    assert [record.year for record in records] == [2025, 2024, 2024, 2023, 2022]
    assert [element.tag for element in ET.fromstring(combined)].count("PubmedBookArticle") == 1
    record_a = next(record for record in records if record.pmid == "999999801")
    assert record_a.title == "Synthetic capture record A: nested-text exercise"
    assert record_a.authors == ["Example, Ada", "Synthetic Fixture Consortium"]
    assert record_a.abstract == "PURPOSE: Preserve synthetic bibliography metadata.\nNOTE: No clinical results or actual research participants are described."
    assert "999999899" not in receipt["pmids"]  # Cited-reference ID is not capture membership.
    assert set(tmp_path.iterdir()) == {destination}


def test_capture_with_real_client_injected_transport_never_saves_operational_credentials(tmp_path, capture_oracle):
    _, responses = capture_oracle
    client, _, transport = client_for(responses, api_key=SECRET)
    result, _ = run_fixture_capture(tmp_path, capture_oracle, client=client)
    assert len(transport.calls) == 4
    assert all(call["params"]["api_key"] == [SECRET] for call in transport.calls)
    serialized = json.dumps(result)
    assert SECRET not in serialized and EMAIL not in serialized
    assert all(not {"api_key", "email", "tool"}.intersection(request["params"]) for request in result["receipt"]["requests"])
    assert SECRET.encode() not in (tmp_path / "capture" / "receipt.json").read_bytes()


def test_zero_results_preserve_translation_warning_and_make_no_fetch(tmp_path, capture_oracle):
    manifest, _ = capture_oracle
    zero = manifest["zero"]
    source = (FIXTURES / zero["search_file"]).read_bytes()
    client = FixtureClient([source])
    result = capture_pubmed_search(zero["query"], tmp_path / "capture", client=client)
    receipt = result["receipt"]
    assert len(client.calls) == len(receipt["requests"]) == 1
    assert receipt["reported_count"] == receipt["fetched_count"] == 0
    assert receipt["pmids"] == [] and receipt["complete"] is True
    assert receipt["history"] == {"webenv": None, "query_key": None}
    assert receipt["warnings"] == zero["warnings"] and receipt["query_translation"] == zero["query_translation"]
    assert receipt["filters"] == {}
    assert load_records(result["xml_file"]) == []
    assert (tmp_path / "capture" / "search.xml").read_bytes() == source
    assert not list((tmp_path / "capture").glob("batches/*.xml"))


@pytest.mark.parametrize("field,value", [
    ("Count", "10001"), ("Count", "-1"), ("Count", "5x"), ("Count", None),
    ("RetStart", "1"), ("RetStart", None), ("RetMax", "4"), ("RetMax", None),
    ("QueryTranslation", None), ("QueryKey", None), ("WebEnv", None),
])
def test_invalid_search_metadata_fails_before_fetch_and_leaves_no_capture(tmp_path, capture_oracle, field, value):
    _, responses = capture_oracle
    client = FixtureClient([change_search(responses[0], field, value)])
    before = set(tmp_path.iterdir())
    with pytest.raises(ValueError) as failure:
        run_fixture_capture(tmp_path, capture_oracle, client=client)
    assert len(client.calls) == 1
    if field == "Count" and value == "10001":
        assert any(term in str(failure.value).lower() for term in ("10,000", "10000", "10k", "limit"))
    assert_capture_absent_and_staging_clean(tmp_path, tmp_path / "capture", before)


@pytest.mark.parametrize("variant", ["short", "duplicate", "malformed_id", "missing_list", "wrong_root", "error_list", "entity", "malformed"])
def test_search_membership_and_http200_failures_are_never_successful_zero_searches(tmp_path, capture_oracle, variant):
    _, responses = capture_oracle
    root = ET.fromstring(responses[0])
    ids = root.find("IdList")
    if variant == "short":
        ids.remove(ids[-1])
        root.find("RetMax").text = "4"
    elif variant == "duplicate":
        ids[-1].text = ids[0].text
    elif variant == "malformed_id":
        ids[-1].text = "99999x"
    elif variant == "missing_list":
        root.remove(ids)
    elif variant == "wrong_root":
        root.tag = "PubmedArticleSet"
    bad = xml_bytes(root)
    if variant == "error_list":
        bad = (FIXTURES / "error-search.xml").read_bytes()
    elif variant == "entity":
        bad = b'<!DOCTYPE eSearchResult [<!ENTITY fake "invented">]>' + ET.tostring(root)
    elif variant == "malformed":
        bad = b"<eSearchResult><Count>5"
    client = FixtureClient([bad])
    before = set(tmp_path.iterdir())
    with pytest.raises(ValueError):
        run_fixture_capture(tmp_path, capture_oracle, client=client)
    assert len(client.calls) == 1
    assert_capture_absent_and_staging_clean(tmp_path, tmp_path / "capture", before)


@pytest.mark.parametrize("variant", [
    "same_count_wrong_set", "short", "duplicate", "absent_pmid", "conflicting_pmid",
    "invalid_pmid", "unexpected_root", "http200_error", "malformed", "entity",
])
def test_each_fetch_batch_must_have_exact_membership_not_only_matching_count(tmp_path, capture_oracle, variant):
    _, responses = capture_oracle
    bad = responses[1]
    root = ET.fromstring(bad)
    first = root[0]  # Own PMID801, returned out of requested order.
    if variant == "same_count_wrong_set":
        bad = change_record_pmid(bad, "999999801", "999999899")
    elif variant == "duplicate":
        bad = change_record_pmid(bad, "999999801", "999999803")
    elif variant == "invalid_pmid":
        bad = change_record_pmid(bad, "999999801", "bad-id")
    elif variant == "short":
        root.remove(first)
        bad = xml_bytes(root)
    elif variant == "absent_pmid":
        citation = first.find("MedlineCitation")
        citation.remove(citation.find("PMID"))
        id_list = first.find("PubmedData/ArticleIdList")
        for element in list(id_list):
            if element.get("IdType") in ("pubmed", "pmid"):
                id_list.remove(element)
        bad = xml_bytes(root)
    elif variant == "conflicting_pmid":
        first.find("MedlineCitation/PMID").text = "999999899"
        bad = xml_bytes(root)
    elif variant == "unexpected_root":
        root.tag = "UnrelatedSet"
        bad = xml_bytes(root)
    elif variant == "http200_error":
        bad = (FIXTURES / "error-fetch.xml").read_bytes()
    elif variant == "malformed":
        bad = b"<PubmedArticleSet><PubmedArticle>"
    elif variant == "entity":
        bad = b'<!DOCTYPE PubmedArticleSet [<!ENTITY fake "invented">]>' + ET.tostring(root)
    client = FixtureClient([responses[0], bad, *responses[2:]])
    before = set(tmp_path.iterdir())
    with pytest.raises(ValueError):
        run_fixture_capture(tmp_path, capture_oracle, client=client)
    assert len(client.calls) == 2
    assert_capture_absent_and_staging_clean(tmp_path, tmp_path / "capture", before)


def test_final_batch_cannot_substitute_prior_batch_report_and_keep_total_count(tmp_path, capture_oracle):
    _, responses = capture_oracle
    altered = [*responses[:3], change_record_pmid(responses[3], "999999804", "999999803")]
    client = FixtureClient(altered)
    before = set(tmp_path.iterdir())
    with pytest.raises(ValueError):
        run_fixture_capture(tmp_path, capture_oracle, client=client)
    assert len(client.calls) == 4
    assert_capture_absent_and_staging_clean(tmp_path, tmp_path / "capture", before)


@pytest.mark.parametrize("destination_kind", ["file", "directory"])
def test_existing_destination_is_preserved_without_searching(tmp_path, capture_oracle, destination_kind):
    destination = tmp_path / "capture"
    if destination_kind == "directory":
        destination.mkdir()
        existing = destination / "receipt.json"
    else:
        existing = destination
    existing.write_bytes(b"Existing capture or unrelated content")
    client = FixtureClient(capture_oracle[1])
    with pytest.raises(ValueError):
        run_fixture_capture(tmp_path, capture_oracle, client=client)
    assert client.calls == []
    assert existing.read_bytes() == b"Existing capture or unrelated content"
    assert set(tmp_path.iterdir()) == {destination}


def test_destination_created_during_fetch_is_never_overwritten(tmp_path, capture_oracle):
    destination = tmp_path / "capture"
    def create_competing_capture(request_number):
        if request_number == 4:
            destination.mkdir()
            (destination / "receipt.json").write_text("Competing capture", encoding="utf-8")
    client = FixtureClient(capture_oracle[1], on_call=create_competing_capture)
    with pytest.raises(ValueError):
        run_fixture_capture(tmp_path, capture_oracle, client=client)
    assert (destination / "receipt.json").read_text(encoding="utf-8") == "Competing capture"
    assert set(tmp_path.iterdir()) == {destination}


def test_interrupted_fetch_cleans_staging_without_touching_any_ledger(tmp_path, capture_oracle):
    ledger = tmp_path / "reviews.sqlite3"
    ledger.write_bytes(b"Unrelated ledger sentinel; capture has no ledger interface")
    _, responses = capture_oracle
    client = FixtureClient([responses[0], responses[1], KeyboardInterrupt("Synthetic interruption")])
    before = set(tmp_path.iterdir())
    with pytest.raises(KeyboardInterrupt):
        run_fixture_capture(tmp_path, capture_oracle, client=client)
    assert ledger.read_bytes() == b"Unrelated ledger sentinel; capture has no ledger interface"
    assert len(client.calls) == 3
    assert_capture_absent_and_staging_clean(tmp_path, tmp_path / "capture", before)
    result, rerun_client = run_fixture_capture(tmp_path, capture_oracle)
    assert result["receipt"]["complete"] is True and len(rerun_client.calls) == 4


def test_malformed_response_data_is_not_retried_and_error_text_never_exposes_key(tmp_path):
    source = f"<eSearchResult><ERROR>Invalid api_key={SECRET}; email={EMAIL}</ERROR></eSearchResult>".encode()
    client, _, transport = client_for([source, b"Should not retry malformed response"], api_key=SECRET)
    with pytest.raises(ValueError) as failure:
        capture_pubmed_search(QUERY, tmp_path / "capture", client=client)
    assert len(transport.calls) == 1
    assert SECRET not in str(failure.value) and EMAIL not in str(failure.value)
    assert not (tmp_path / "capture").exists()


@pytest.mark.parametrize("overrides", [
    {"query": ""}, {"query": "  "}, {"query": None}, {"sort": "random"},
    {"batch_size": 0}, {"batch_size": 201}, {"batch_size": True},
    {"filters": []}, {"filters": {"language": "English"}},
    {"filters": {"datetype": "pdat"}},
    {"filters": {"datetype": "mdat", "mindate": "2020", "maxdate": "2026"}},
    {"filters": {"datetype": "pdat", "mindate": "2026/02/30", "maxdate": "2026/03/01"}},
    {"filters": {"datetype": "pdat", "mindate": "2026", "maxdate": "2020"}},
])
def test_invalid_capture_inputs_fail_before_any_request(tmp_path, overrides):
    fields = {"query": QUERY, "sort": "pub_date", "batch_size": 2, "filters": {}}
    fields.update(overrides)
    client = FixtureClient([])
    with pytest.raises(ValueError):
        capture_pubmed_search(destination=tmp_path / "capture", client=client, **fields)
    assert client.calls == [] and not (tmp_path / "capture").exists()


def test_month_date_filters_and_relevance_are_preserved_exactly(tmp_path, capture_oracle):
    filters = {"datetype": "edat", "mindate": "2020/01", "maxdate": "2026/10"}
    result, client = run_fixture_capture(tmp_path, capture_oracle, filters=filters, sort="relevance")
    assert result["receipt"]["sort"] == "relevance" and result["receipt"]["filters"] == filters
    assert all(client.calls[0]["params"][key] == value for key, value in filters.items())
    assert client.calls[0]["params"]["sort"] == "relevance"


def test_standalone_capture_has_no_model_settings_or_dotenv_imports(tmp_path):
    code = """
import json, pathlib, socket, sys
sys.path.insert(0, sys.argv[1])
def denied(*args, **kwargs):
    raise AssertionError('Live network attempted')
socket.create_connection = denied
from src.search.pubmed_search import capture_pubmed_search
fixture = pathlib.Path(sys.argv[2])
manifest = json.loads((fixture / 'manifest.json').read_text())
responses = [(fixture / manifest['search_file']).read_bytes()]
responses += [(fixture / b['response_file']).read_bytes() for b in manifest['batches']]
class Client:
    def request(self, endpoint, params):
        return responses.pop(0)
result = capture_pubmed_search(manifest['query'], sys.argv[3], client=Client(), batch_size=2)
assert result['receipt']['pmids'] == ['999999803','999999801','999999805','999999802','999999804']
assert not {'torch','chromadb','sentence_transformers','dotenv','src.settings'}.intersection(sys.modules)
"""
    result = subprocess.run([sys.executable, "-c", code, str(ROOT), str(FIXTURES), str(tmp_path / "capture")],
                            cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
