"""Offline presentation checks for workflow scroll-reset scheduling.

AppTest can establish when the browser event is emitted and that project state
is unchanged. Actual scroll position, URL fragment clearing, and deliberate
in-page anchor navigation require the separate browser acceptance check.
"""

from pathlib import Path
import socket

import pytest

from src.mvp.contracts import (
    CreateWorkspaceRequest, PrepareSourcesRequest, RetrieveEvidenceRequest,
    SaveAssessmentRequest, SearchRequest,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def navigation_workspace(tmp_path, monkeypatch):
    pytest.importorskip("streamlit.testing.v1", reason="Navigation checks require focused MVP dependencies")
    from streamlit.testing.v1 import AppTest
    import src.mvp.bootstrap as bootstrap
    from src.mvp.adapters.saved_examples import SavedExampleProvider
    from src.mvp.adapters.storage import SQLiteWorkspaceStorage
    from src.mvp.service import MVPService

    def denied(*args, **kwargs):
        pytest.fail("Navigation regression attempted network access")

    monkeypatch.setattr(socket, "create_connection", denied)

    class CountedExample:
        searches = 0
        preparations = 0

        def __init__(self):
            self.provider = SavedExampleProvider()

        def search(self, request):
            self.searches += 1
            return self.provider.search(request)

        def prepare(self, record):
            self.preparations += 1
            return self.provider.prepare(record)

    example = CountedExample()
    service = MVPService(SQLiteWorkspaceStorage(tmp_path / "navigation.sqlite3"), example, example)
    handle = service.create_workspace(CreateWorkspaceRequest(question="microbiome"))
    search = service.search_literature(handle, SearchRequest(request_id="search", query="saved example"))
    service.prepare_sources(handle, PrepareSourcesRequest(
        request_id="prepare", search_id=search.id, paper_ids=[search.papers[0].id],
    ))
    run = service.retrieve_evidence(handle, RetrieveEvidenceRequest(request_id="retrieve", question="microbiome"))
    saved = service.save_assessment(handle, SaveAssessmentRequest(request_id="assessment", run_id=run.id))
    monkeypatch.setenv("MVP_MODE", "saved_example")
    monkeypatch.setattr(bootstrap, "build_service", lambda **kwargs: service)
    app = AppTest.from_file(str(ROOT / "apps/streamlit/app.py"), default_timeout=20)
    app.session_state["workspace_handle"] = handle.model_dump(mode="json")
    app.run()
    assert not app.exception
    return app, service, handle, run, saved, example


def _widget(app, group, label):
    matches = [item for item in getattr(app, group) if item.label == label]
    assert len(matches) == 1, (group, label)
    return matches[0]


def _reset_events(app):
    return [item for item in app.get("html") if "data-lre-navigation-reset=" in item.value]


def _assert_reset_after_content(app, screen, revision):
    events = _reset_events(app)
    assert len(events) == 1
    event = events[0]
    assert f'data-lre-navigation-reset="{revision}"' in event.value
    assert event.proto.unsafe_allow_javascript is True
    assert app.session_state["_rendered_workflow_screen"] == screen
    assert app.session_state["_workflow_navigation_revision"] == revision
    if screen == "Discover":
        last_control = _widget(app, "button", "Continue to source selection")
    elif screen == "Prepare sources":
        last_control = _widget(app, "button", "Continue to passage search")
    else:
        last_control = next(item for item in app.get("download_button") if item.label == "Download audit JSON")
    ordered = list(app.main)
    assert ordered.index(last_control) < ordered.index(event)


def test_sidebar_transitions_schedule_one_reset_after_the_new_screen(navigation_workspace):
    app, service, handle, _, _, provider = navigation_workspace
    before = service.get_workspace(handle)
    assert not _reset_events(app)  # Initial render leaves intentional deep links alone.
    assert app.session_state["_rendered_workflow_screen"] == "Discover"
    for revision, screen in enumerate(("Prepare sources", "Evidence & export", "Discover"), 1):
        _widget(app, "radio", "Workflow").set_value(screen).run()
        assert not app.exception
        _assert_reset_after_content(app, screen, revision)
        assert app.session_state["workspace_handle"] == handle.model_dump(mode="json")
        assert service.get_workspace(handle) == before
        app.run()
        assert not app.exception and not _reset_events(app)
        assert app.session_state["_workflow_navigation_revision"] == revision
    assert provider.searches == provider.preparations == 1


def test_continue_actions_reset_scroll_without_changing_saved_work(navigation_workspace):
    app, service, handle, _, _, provider = navigation_workspace
    before = service.get_workspace(handle)
    for revision, (label, screen) in enumerate((
        ("Continue to source selection", "Prepare sources"),
        ("Continue to passage search", "Evidence & export"),
    ), 1):
        _widget(app, "button", label).click().run()
        assert not app.exception
        _assert_reset_after_content(app, screen, revision)
        assert service.get_workspace(handle) == before
    assert app.session_state["workspace_handle"] == handle.model_dump(mode="json")
    assert provider.searches == provider.preparations == 1


def test_inspection_revision_and_save_do_not_reset_the_current_screen(navigation_workspace):
    app, service, handle, run, saved, provider = navigation_workspace
    _widget(app, "radio", "Workflow").set_value("Evidence & export").run()
    _assert_reset_after_content(app, "Evidence & export", 1)
    app.run()
    assert not _reset_events(app)

    passage = run.passages[1]
    app.button(key="inspect_" + run.id + passage.id).click().run()
    assert not app.exception and not _reset_events(app)
    assert _widget(app, "selectbox", "Inspect passage").value == passage.id
    assert any("[Read selected source context ↓](#verifiable-source-context)" in item.value for item in app.markdown)
    assert service.get_workspace(handle).assessments == [saved]

    _widget(app, "button", "Revise saved assessment").click().run()
    assert not app.exception and not _reset_events(app)
    draft = app.session_state["assessment_draft_" + run.id]
    assert draft["supersedes_id"] == saved.id
    first = run.passages[0]
    judgment = app.main.get_by_key("passage-judgment-" + first.id)
    judgment.text_area[0].set_value("Draft retained during same-screen navigation handling")
    judgment.selectbox[0].set_value("useful")
    _widget(app, "button", "Save assessment").click().run()
    assert not app.exception and not app.error and not _reset_events(app)
    assessments = service.get_workspace(handle).assessments
    assert len(assessments) == 2 and assessments[0] == saved
    assert assessments[1].supersedes_id == saved.id
    assert assessments[1].passages[0].notes == "Draft retained during same-screen navigation handling"
    assert assessments[1].passages[0].decision == "useful"
    assert app.session_state["_workflow_navigation_revision"] == 1
    assert app.session_state["workspace_handle"] == handle.model_dump(mode="json")
    assert provider.searches == provider.preparations == 1
