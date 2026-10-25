"""Standalone worker credentials and shared live-transport gate: offline checks."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from src.mvp.adapters.provider_rate_gate import wait_for_provider
from src.mvp.adapters.saved_examples import SavedExampleProvider
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.contracts import SearchRequest, WorkspaceHandle
from src.mvp.local_preparation import LocalPreparationRuntime
from src.mvp.ports import MvpError, ProviderFailure
from src.mvp.preparation_contracts import PreparationJobRequest
from src.mvp.service import MVPService


def case(tmp_path):
    provider = SavedExampleProvider()
    engine = MVPService(SQLiteWorkspaceStorage(tmp_path / "workspaces.sqlite3"), provider, provider)
    handle = engine.create_workspace()
    search = engine.search_literature(handle, SearchRequest(request_id="local-search", query="saved offline source", max_results=30))
    return engine, handle, search


def test_local_handle_is_verified_and_never_issues_a_browser_session(tmp_path):
    engine, handle, _ = case(tmp_path)
    runtime = LocalPreparationRuntime(engine._storage._path)
    invalid = WorkspaceHandle(workspace_id=handle.workspace_id, token="invalid")
    with pytest.raises(MvpError):
        runtime.registry.register_local_handle_for_worker("saved_example", invalid, engine.get_workspace)
    runtime.registry.register_local_handle_for_worker("saved_example", handle, engine.get_workspace)
    assert runtime.registry.get_bound_handle_for_worker(handle.workspace_id) == ("saved_example", handle)
    _, unrelated = runtime.registry.session(None)
    assert runtime.registry.workspace_ids(unrelated["token_hash"]) == []
    with pytest.raises(MvpError):
        runtime.registry.workspace(unrelated["token_hash"], handle.workspace_id)
    with runtime.registry.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM web_sessions").fetchone()[0] == 1


def test_local_worker_reopens_private_binding_and_cannot_restore_deleted_sources(tmp_path):
    engine, handle, search = case(tmp_path)
    runtime = LocalPreparationRuntime(engine._storage._path)
    runtime.bind("saved_example", handle, engine)
    runtime.worker.stop()
    submitted = runtime.jobs.submit("saved_example", handle, PreparationJobRequest(request_id="local-job",
        search_id=search.id, paper_ids=[search.papers[0].id], expected_source_revision=0))
    reopened = LocalPreparationRuntime(engine._storage._path)
    reopened.engines["saved_example"] = engine
    assert reopened.worker.run_once()
    assert reopened.jobs.job("saved_example", handle, submitted.job.id).status == "succeeded"
    reopened.clear("saved_example", handle, engine)
    with pytest.raises(MvpError):
        engine.get_workspace(handle)
    with pytest.raises(MvpError):
        reopened.registry.register_local_handle_for_worker("saved_example", handle, engine.get_workspace)
    with reopened.registry.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM web_workspaces").fetchone()[0] == 0
    with engine._storage._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM preparation_jobs").fetchone()[0] == 0


def test_provider_gate_spaces_two_independent_processes_without_network(tmp_path):
    folder = tmp_path / "shared-gates"
    program = ("import sys,time;from src.mvp.adapters.provider_rate_gate import wait_for_provider;"
               "wait_for_provider('eutils.ncbi.nlm.nih.gov',.4,directory=sys.argv[1]);print(time.monotonic(),flush=True)")
    processes = [subprocess.Popen([sys.executable, "-c", program, str(folder)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    times = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 0, stderr
        times.append(float(stdout.strip()))
    assert abs(times[1] - times[0]) >= .37
    assert (folder.stat().st_mode & 0o777) == 0o700
    assert ((folder / "eutils.ncbi.nlm.nih.gov.gate").stat().st_mode & 0o777) == 0o600


def test_invalid_or_symlink_gate_fails_closed(tmp_path):
    folder = tmp_path / "gates"
    folder.mkdir()
    gate = folder / "eutils.ncbi.nlm.nih.gov.gate"
    gate.write_text("nan")
    with pytest.raises(ProviderFailure, match="timing record"):
        wait_for_provider("eutils.ncbi.nlm.nih.gov", .4, directory=folder)
    gate.unlink()
    other = tmp_path / "untouched"
    other.write_text("private unchanged")
    gate.symlink_to(other)
    with pytest.raises(ProviderFailure):
        wait_for_provider("eutils.ncbi.nlm.nih.gov", .4, directory=folder)
    assert other.read_text() == "private unchanged"


@pytest.mark.skipif(os.name == "nt", reason="POSIX system temporary-directory symlink regression")
def test_default_gate_resolves_system_temp_alias_without_network(tmp_path, monkeypatch):
    from src.mvp.adapters import provider_rate_gate
    actual = tmp_path / "system-temp"
    actual.mkdir()
    alias = tmp_path / "system-temp-alias"
    alias.symlink_to(actual, target_is_directory=True)
    monkeypatch.setattr(provider_rate_gate.tempfile, "gettempdir", lambda: str(alias))
    monkeypatch.setattr(provider_rate_gate, "current_user_key", lambda: "isolated-test-user")
    wait_for_provider("eutils.ncbi.nlm.nih.gov", .01)
    assert (actual / "lit-rev-provider-gates-isolated-test-user" / "eutils.ncbi.nlm.nih.gov.gate").is_file()


@pytest.mark.skipif(os.name == "nt", reason="POSIX explicit-path symlink rejection")
def test_explicit_gate_directory_alias_still_fails_closed(tmp_path):
    actual = tmp_path / "system-temp"
    actual.mkdir()
    alias = tmp_path / "system-temp-alias"
    alias.symlink_to(actual, target_is_directory=True)
    with pytest.raises(ProviderFailure, match="private shared provider gate"):
        wait_for_provider("eutils.ncbi.nlm.nih.gov", .01, directory=alias / "caller-selected-gates")
    assert not (actual / "caller-selected-gates").exists()
