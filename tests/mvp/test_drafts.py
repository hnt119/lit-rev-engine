"""Streamlit control drafts survive hidden-widget cleanup within one session.

Synthetic providers only. These checks do not establish hard-reload/session
recovery; the v0.2 web session and persisted-draft boundary covers that separately.
"""

from hashlib import sha256
from pathlib import Path
import socket

import pytest

from src.mvp.contracts import (
    Block, CreateWorkspaceRequest, Paper, PreparedSource, PrepareSourcesRequest,
    RetrieveEvidenceRequest, SearchPreview, SearchRequest, digest,
)

ROOT = Path(__file__).resolve().parents[2]
CUSTOM_QUESTION = "How do diet and gut microbiome diversity differ in Southeast Asian women?"
CUSTOM_QUERY = '("gut microbiota"[Title/Abstract] OR diet[Title/Abstract]) AND "Southeast Asia"[Title/Abstract]'
CUSTOM_EVIDENCE_QUESTION = "Which microbiome diversity measurements were reported for women?"


@pytest.fixture
def draft_app(tmp_path, monkeypatch):
    pytest.importorskip("streamlit.testing.v1", reason="Draft regression needs focused MVP dependencies")
    from streamlit.testing.v1 import AppTest
    import src.mvp.bootstrap as bootstrap
    from src.mvp.adapters.storage import SQLiteWorkspaceStorage
    from src.mvp.service import MVPService

    def denied(*args, **kwargs):
        pytest.fail("Draft regression attempted network access")

    monkeypatch.setattr(socket, "create_connection", denied)

    class SyntheticProvider:
        searches = 0
        preparations = 0
        record = Paper(
            title="Synthetic microbiome software fixture; not publication evidence",
            authors=["Software fixture"], year=2020, pmid="99999998",
            abstract="Synthetic microbiome diversity measurements for women and diet.",
            url="https://pubmed.ncbi.nlm.nih.gov/99999998/",
        )

        def search(self, request):
            self.searches += 1
            return SearchPreview(
                query=request.query, total_reported=1, fetched_count=1,
                ordered_identifiers=[self.record.pmid], papers=[self.record],
                truncated=False, mode="test", provider="synthetic-draft-fixture",
            )

        def prepare(self, record):
            self.preparations += 1
            block = Block(id="abstract:1", ordinal=1, text=record.abstract,
                          locator={"type": "abstract", "ordinal": 1})
            return PreparedSource(
                paper_id=record.id, status="abstract_only", source_type="abstract",
                provider="synthetic-draft-fixture", source_url=record.url,
                source_sha256=sha256(record.abstract.encode()).hexdigest(),
                blocks_sha256=digest([block.model_dump(mode="json")]),
                parser_id="synthetic-draft-fixture.v1", blocks=[block],
                source_identifiers={"pmid": record.pmid},
            )

    def make(mode="saved_example"):
        provider = SyntheticProvider()
        service = MVPService(SQLiteWorkspaceStorage(tmp_path / (mode + ".sqlite3")), provider, provider)
        handle = service.create_workspace(CreateWorkspaceRequest(question="microbiome"))
        search = service.search_literature(handle, SearchRequest(request_id="fixture-search", query="microbiome"))
        service.prepare_sources(handle, PrepareSourcesRequest(
            request_id="fixture-prepare", search_id=search.id, paper_ids=[provider.record.id],
        ))
        service.retrieve_evidence(handle, RetrieveEvidenceRequest(request_id="fixture-run", question="microbiome"))
        monkeypatch.setenv("MVP_MODE", mode)
        monkeypatch.setattr(bootstrap, "build_service", lambda **kwargs: service)
        monkeypatch.setattr(bootstrap, "public_runtime_info", lambda: {
            "live_available": True, "saved_example": {"query": "Synthetic saved example query"},
        })
        app = AppTest.from_file(str(ROOT / "apps/streamlit/app.py"), default_timeout=20)
        app.session_state["workspace_handle"] = handle.model_dump(mode="json")
        app.run()
        assert not app.exception
        return app, service, handle, provider

    return make


def widget(app, group, label):
    matches = [item for item in getattr(app, group) if item.label == label]
    assert len(matches) == 1, (group, label)
    return matches[0]


def navigate(app, *screens):
    for screen in screens:
        widget(app, "radio", "Workflow").set_value(screen).run()
        assert not app.exception


def test_edited_research_question_survives_hidden_screens_without_searching(draft_app):
    app, service, handle, provider = draft_app()
    widget(app, "text_area", "Research question").set_value(CUSTOM_QUESTION).run()
    before = service.get_workspace(handle)
    navigate(app, "Prepare sources", "Evidence & export", "Discover")
    assert widget(app, "text_area", "Research question").value == CUSTOM_QUESTION
    assert service.get_workspace(handle) == before
    assert provider.searches == provider.preparations == 1


def test_edited_live_query_survives_navigation_after_explicit_mocked_search(draft_app):
    app, service, handle, provider = draft_app("live")
    widget(app, "text_area", "PubMed query").set_value(CUSTOM_QUERY)
    widget(app, "button", "Search literature").click().run()
    assert not app.exception and not app.error
    before = service.get_workspace(handle)
    assert before.searches[-1].query == CUSTOM_QUERY
    navigate(app, "Prepare sources", "Evidence & export", "Discover")
    assert widget(app, "text_area", "PubMed query").value == CUSTOM_QUERY
    assert service.get_workspace(handle) == before
    assert provider.searches == 2 and provider.preparations == 1


def test_evidence_question_remains_distinct_from_research_question(draft_app):
    app, service, handle, provider = draft_app()
    widget(app, "text_area", "Research question").set_value(CUSTOM_QUESTION).run()
    navigate(app, "Evidence & export")
    widget(app, "text_area", "Question for selected sources").set_value(CUSTOM_EVIDENCE_QUESTION)
    widget(app, "button", "Search passages").click().run()
    assert not app.exception and not app.error
    before = service.get_workspace(handle)
    assert before.runs[-1].question == CUSTOM_EVIDENCE_QUESTION
    navigate(app, "Discover", "Prepare sources", "Evidence & export")
    assert widget(app, "text_area", "Question for selected sources").value == CUSTOM_EVIDENCE_QUESTION
    navigate(app, "Discover")
    assert widget(app, "text_area", "Research question").value == CUSTOM_QUESTION
    assert service.get_workspace(handle) == before
    assert provider.searches == provider.preparations == 1


def test_incomplete_empty_question_is_preserved_as_a_draft(draft_app):
    app, service, handle, provider = draft_app()
    widget(app, "text_area", "Research question").set_value("").run()
    before = service.get_workspace(handle)
    navigate(app, "Prepare sources", "Evidence & export", "Discover")
    assert widget(app, "text_area", "Research question").value == ""
    assert service.get_workspace(handle) == before
    assert provider.searches == provider.preparations == 1
