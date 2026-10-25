"""Actual Streamlit controls with the existing public offline thirty-full-text pack."""
from pathlib import Path
import socket
import time

import pytest

from src.mvp.adapters.saved_examples import SavedExampleProvider
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.contracts import SearchRequest
from src.mvp.service import MVPService


def test_streamlit_thirty_selection_submits_persisted_job_and_reopens_sources(tmp_path, monkeypatch):
    AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
    import src.mvp.bootstrap as bootstrap
    provider = SavedExampleProvider()
    engine = MVPService(SQLiteWorkspaceStorage(tmp_path / "workspaces.sqlite3"), provider, provider)
    handle = engine.create_workspace()
    search = engine.search_literature(handle, SearchRequest(request_id="streamlit-search", query="offline", max_results=30))
    monkeypatch.setattr(bootstrap, "build_service", lambda **kwargs: engine)
    monkeypatch.setattr(bootstrap, "public_runtime_info", lambda: {"live_available": False,
        "saved_example": {"query": search.query}, "default_mode": "saved_example"})
    monkeypatch.setattr(socket, "create_connection", lambda *a, **kw: pytest.fail("Offline Streamlit check attempted network"))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[2] / "apps/streamlit/app.py"), default_timeout=15)
    app.session_state["workspace_handle"] = handle.model_dump()
    app.session_state["screen"] = "Prepare sources"
    app.run()
    assert not app.exception
    choices = next(item for item in app.multiselect if item.label == "Papers for exploration (maximum 30)")
    choices.set_value([paper.id for paper in search.papers])
    next(item for item in app.button if item.label == "Prepare selected papers").click()
    app.run()
    assert not app.exception
    runtime = app.session_state["_preparation_runtime"]
    try:
        job_id = app.session_state["_preparation_job_id"]
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            job = runtime.jobs.job("saved_example", handle, job_id)
            if job.status in {"succeeded", "failed", "stale", "cancelled"}:
                break
            time.sleep(.05)
        assert job.status == "succeeded", job.error
        next(item for item in app.button if item.label == "Update preparation progress").click()
        app.run()
        assert not app.exception
        assert len(engine.get_workspace(handle).sources) == 30
        assert all(source.source_type == "full_text" for source in engine.get_workspace(handle).sources)
        assert any("30/30 processed" in item.value for item in app.caption)
    finally:
        runtime.worker.stop()
