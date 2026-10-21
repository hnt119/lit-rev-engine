"""Offline question-to-keyword API checks; never discovery or inference."""

import socket

import pytest
from fastapi.testclient import TestClient

from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.service import MVPService
from src.web_api.app import create_app


QUESTION = (
    "What does this source report about diet, gut microbiota, and gestational "
    "diabetes among the studied Chinese pregnant women?"
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Query suggestions must not contact a provider or model")

    monkeypatch.setattr(socket, "create_connection", denied)

    class NoProviderCalls:
        search = prepare = denied

    engine = MVPService(
        SQLiteWorkspaceStorage(tmp_path / "engine" / "workspaces.sqlite3"),
        NoProviderCalls(), NoProviderCalls(),
    )
    app = create_app(tmp_path / "web", services={"saved_example": engine})
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        session = client.get("/api/v1/session").json()
        client.headers.update({"Origin": "http://127.0.0.1:3000", "X-CSRF-Token": session["csrf_token"]})
        yield client


def test_proposal_extracts_sample_concepts_without_changing_draft_or_research_state(client):
    created = client.post("/api/v1/workspaces", json={
        "request_id": "query-only", "mode": "saved_example", "question": QUESTION,
    })
    assert created.status_code == 200, created.text
    base = "/api/v1/workspaces/" + created.json()["id"]
    retained = client.put(base + "/drafts/discover", json={
        "version": 0, "data": {"question": QUESTION, "query": "existing reviewer strategy"},
    })
    assert retained.status_code == 200, retained.text
    result = client.post(base + "/query-suggestions", json={"question": QUESTION})
    assert result.status_code == 200, result.text
    query = result.json()["query"]
    assert all(term in query.casefold() for term in (
        "diet", "gut microbiota", "gestational diabetes", "chinese", "pregnant women",
    ))
    assert not any(term in query.casefold().split() for term in ("source", "report", "studied", "what"))
    assert len(query) < len(QUESTION)
    assert "no live PubMed call" in result.json()["explanation"]
    assert client.get(base + "/drafts/discover").json() == retained.json()
    assert client.get(base).json() == created.json()


@pytest.mark.parametrize("question", ["What does this source report about?", "   "])
def test_insufficient_question_has_no_query_instead_of_searching_filler(client, question):
    created = client.post("/api/v1/workspaces", json={
        "request_id": "empty-question-proposal", "mode": "saved_example", "question": question,
    }).json()
    base = "/api/v1/workspaces/" + created["id"]
    result = client.post(base + "/query-suggestions", json={"question": question})
    assert result.status_code == 200, result.text
    assert result.json()["query"] == ""
    assert client.get(base).json() == created
