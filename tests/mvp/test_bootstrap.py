"""Server configuration never exposes credentials or blocks the offline example."""
import pytest

from src.mvp.bootstrap import build_service, public_runtime_info
from src.mvp.contracts import CreateWorkspaceRequest
from src.mvp.ports import MvpError


def test_invalid_live_contact_leaves_saved_example_available(monkeypatch, tmp_path):
    monkeypatch.setenv("NCBI_EMAIL", "not-a-contact-email")
    monkeypatch.setenv("NCBI_API_KEY", "synthetic-private-key-do-not-render")
    public = public_runtime_info()
    assert public["live_available"] is False
    assert "synthetic-private-key" not in str(public) and "not-a-contact-email" not in str(public)
    service = build_service(mode="saved_example", data_dir=tmp_path)
    handle = service.create_workspace(CreateWorkspaceRequest(question="Software-only configuration check"))
    assert service.get_workspace(handle).question == "Software-only configuration check"
    with pytest.raises(MvpError, match="valid server contact"):
        build_service(mode="live", data_dir=tmp_path)


def test_separate_configured_stores_cannot_reuse_a_capability(tmp_path):
    first = build_service(data_dir=tmp_path / "first")
    second = build_service(data_dir=tmp_path / "second")
    handle = first.create_workspace(CreateWorkspaceRequest(question="Synthetic workspace isolation"))
    with pytest.raises(MvpError, match="unavailable"):
        second.get_workspace(handle)
