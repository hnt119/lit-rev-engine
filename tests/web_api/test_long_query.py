"""Offline long-query transport checks with synthetic text, never PubMed results."""

import io
import socket
from itertools import count
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.adapters.transport import BoundedTransport
from src.mvp.contracts import SearchPreview
from src.mvp.service import MVPService
from src.web_api.app import create_app


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Long-query software tests must not make network calls")
    monkeypatch.setattr(socket, "create_connection", denied)


def synthetic_query(length):
    prefix = '("SOFTWARE TEST gut microbiota"[tiab] OR "SOFTWARE TEST women"[tiab]) AND '
    return prefix + "x" * (length - len(prefix))


@pytest.mark.parametrize("length", [5000, 20000])
def test_pubmed_transport_uses_post_and_preserves_long_form_term(length):
    """URL limits do not truncate the exact form-encoded term in this transport."""
    query = synthetic_query(length)
    requests = []

    class Response(io.BytesIO):
        status = 200
        headers = {}

        def geturl(self):
            return "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

    def opener(request, *, timeout):
        requests.append(request)
        assert request.method == "POST"
        assert urlsplit(request.full_url).query == ""
        assert request.full_url.endswith("/esearch.fcgi")
        fields = parse_qs(request.data.decode("ascii"))
        assert fields["term"] == [query]
        assert fields["email"] == ["software-test@example.invalid"]
        assert fields["retmax"] == ["30"]
        return Response(b"SOFTWARE TEST RESPONSE")

    ticks = count(1000000, 1000)
    transport = BoundedTransport(opener=opener, monotonic=lambda: next(ticks), sleep=lambda _: None)
    result = transport.request("pubmed_search", {
        "db": "pubmed", "term": query, "retmax": 30,
        "email": "software-test@example.invalid", "tool": "software-test",
    })
    assert result == b"SOFTWARE TEST RESPONSE" and len(requests) == 1


def test_api_preserves_twenty_thousand_character_draft_and_search_without_rewriting(tmp_path):
    class SyntheticDiscovery:
        def __init__(self):
            self.calls = []

        def search(self, request):
            self.calls.append(request)
            return SearchPreview(
                query=request.query, research_question=request.research_question,
                total_reported=0, fetched_count=0, ordered_identifiers=[], papers=[],
                sort=request.sort, mode="test", provider="synthetic-software-test", truncated=False,
            )

    class NoSourceCalls:
        def prepare(self, record):
            pytest.fail("Editing and searching a query must not prepare sources")

    discovery = SyntheticDiscovery()
    engine = MVPService(SQLiteWorkspaceStorage(tmp_path / "workspaces.sqlite3"), discovery, NoSourceCalls())
    app = create_app(tmp_path, services={"live": engine})
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    session = client.get("/api/v1/session").json()
    client.headers.update({"Origin": "http://127.0.0.1:3000", "X-CSRF-Token": session["csrf_token"]})
    created = client.post("/api/v1/workspaces", json={
        "request_id": "software-test-create", "question": "SOFTWARE TEST question", "mode": "live",
    })
    assert created.status_code == 200, created.text
    base = f'/api/v1/workspaces/{created.json()["id"]}'
    query = synthetic_query(20000)
    draft = client.put(base + "/drafts/discover", json={"version": 0, "data": {"query": query}})
    assert draft.status_code == 200, draft.text
    assert client.get(base + "/drafts/discover").json()["data"]["query"] == query
    searched = client.post(base + "/searches", json={
        "request_id": "software-test-search", "query": query,
        "research_question": "SOFTWARE TEST question", "max_results": 30,
    })
    assert searched.status_code == 200, searched.text
    assert searched.json()["query"] == query
    assert len(discovery.calls) == 1 and discovery.calls[0].query == query
    assert client.get(base + f'/searches/{searched.json()["id"]}/papers').json()["query"] == query
    rejected = client.post(base + "/searches", json={
        "request_id": "software-test-too-long", "query": query + "x", "max_results": 30,
    })
    assert rejected.status_code == 422 and len(discovery.calls) == 1
