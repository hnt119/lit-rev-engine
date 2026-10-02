"""Focused PubMed CLI cases with synthetic offline responses only."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.review import cli
from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.store import ReviewStore
from src.search.pubmed_search import PubMedClient, capture_pubmed_search, verify_pubmed_capture


FIXTURES = Path(__file__).parent / "fixtures/pubmed"
SCRIPT = Path(__file__).resolve().parents[1] / "review.py"


def project(database):
    with ReviewStore(database) as store:
        return store.create_project("Synthetic CLI review", "scoping", "Software question")["id"]


def fixture_factory(monkeypatch, zero=False):
    clients = []

    class Client:
        def __init__(self, email, api_key=None):
            # Retain real constructor validation while replacing all transport activity.
            PubMedClient(email, api_key)
            self.email, self.api_key = email, api_key
            self.calls = []
            self.responses = ["search-zero.xml"] if zero else ["search-five.xml", "fetch-0001.xml", "fetch-0002.xml", "fetch-0003.xml"]
            clients.append(self)

        def request(self, endpoint, params):
            self.calls.append((endpoint, dict(params)))
            return (FIXTURES / self.responses.pop(0)).read_bytes()

    monkeypatch.setattr(cli, "PubMedClient", Client)
    return clients


def invoke(capsys, *args, success=True):
    code = cli.main(list(args))
    output = capsys.readouterr()
    assert (code == 0) is success, output.err
    if success:
        assert output.err == ""
        return json.loads(output.out)
    assert output.out == ""
    assert "Traceback" not in output.err
    return output.err


def test_search_flags_environment_and_verified_import(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("NCBI_EMAIL", "env@example.invalid")
    monkeypatch.setenv("NCBI_API_KEY", "synthetic-api-secret")
    clients = fixture_factory(monkeypatch)
    database = tmp_path / "ledger.sqlite3"
    project_id = project(database)
    directory = tmp_path / "capture"
    query = "  synthetic\nCLI query  "
    result = invoke(capsys, "--db", str(database), "search-pubmed", project_id, "--query", query, "--output", str(directory), "--email", "flag@example.invalid", "--sort", "relevance", "--datetype", "edat", "--mindate", "2024/02", "--maxdate", "2025", "--batch-size", "2", "--import-key", "once")
    assert clients[0].email == "flag@example.invalid"
    assert clients[0].api_key == "synthetic-api-secret"
    assert result["import"]["identified"] == 5
    receipt = result["capture"]["receipt"]
    assert receipt["query"] == query
    assert receipt["sort"] == "relevance"
    assert receipt["filters"] == {"datetype": "edat", "mindate": "2024/02", "maxdate": "2025"}
    assert "synthetic-api-secret" not in json.dumps(result)
    assert invoke(capsys, "--db", str(database), "import-pubmed", project_id, str(directory), "--import-key", "once") == result["import"]
    with ReviewStore(database) as store:
        history = store.list_search_runs(project_id)
        assert len(history) == 1
        assert history[0]["searched_at"] == receipt["searched_at"]
        assert history[0]["execution"] == receipt
        assert store.counts(project_id)["unique_records"] == 5


def test_zero_search_uses_environment_email_and_one_request(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("NCBI_EMAIL", "env@example.invalid")
    monkeypatch.delenv("NCBI_API_KEY", raising=False)
    clients = fixture_factory(monkeypatch, zero=True)
    database = tmp_path / "ledger.sqlite3"
    project_id = project(database)
    result = invoke(capsys, "--db", str(database), "search-pubmed", project_id, "--query", "synthetic zero", "--output", str(tmp_path / "zero"))
    assert clients[0].email == "env@example.invalid" and clients[0].api_key is None
    assert len(clients[0].calls) == 1
    assert result["import"]["identified"] == 0


@pytest.mark.parametrize("extra", [
    ["--query", " "], ["--batch-size", "0"], ["--datetype", "pdat"],
    ["--datetype", "pdat", "--mindate", "2024/02/30", "--maxdate", "2025"],
    ["--import-key", ""], ["--import-key", " "],
])
def test_invalid_search_inputs_make_no_requests(monkeypatch, tmp_path, capsys, extra):
    monkeypatch.setenv("NCBI_EMAIL", "env@example.invalid")
    clients = fixture_factory(monkeypatch)
    database = tmp_path / "ledger.sqlite3"
    project_id = project(database)
    output = tmp_path / "capture"
    invoke(capsys, "--db", str(database), "search-pubmed", project_id, "--query", "synthetic", "--output", str(output), *extra, success=False)
    assert all(not client.calls for client in clients)
    if "--import-key" in extra:
        assert clients == []
    assert not output.exists()
    with ReviewStore(database) as store:
        assert store.list_search_runs(project_id) == []


def test_invalid_project_and_configuration_precede_requests(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("NCBI_EMAIL", raising=False)
    monkeypatch.delenv("NCBI_API_KEY", raising=False)
    clients = fixture_factory(monkeypatch)
    database = tmp_path / "ledger.sqlite3"
    project_id = project(database)
    unknown = invoke(capsys, "--db", str(database), "search-pubmed", "unknown", "--query", "synthetic", "--output", str(tmp_path / "capture"), success=False)
    assert "Unknown project" in unknown and clients == []
    missing_email = invoke(capsys, "--db", str(database), "search-pubmed", project_id, "--query", "synthetic", "--output", str(tmp_path / "capture"), success=False)
    assert "email" in missing_email and clients == []
    unknown_replay = invoke(capsys, "--db", str(database), "import-pubmed", "unknown", str(tmp_path / "absent"), success=False)
    assert "Unknown project" in unknown_replay


def test_verify_is_db_free_and_works_as_portable_subprocess(monkeypatch, tmp_path, capsys):
    clients = fixture_factory(monkeypatch)
    directory = tmp_path / "capture"
    capture_pubmed_search("synthetic", directory, client=cli.PubMedClient("fixture@example.invalid"), batch_size=2)
    invalid_parent = tmp_path / "file"
    invalid_parent.write_text("keep")

    def forbidden(*args, **kwargs):
        pytest.fail("Offline verifier attempted to open a ledger")

    monkeypatch.setattr(cli, "ReviewStore", forbidden)
    result = invoke(capsys, "--db", str(invalid_parent / "impossible.sqlite3"), "verify-pubmed", str(directory))
    assert result["receipt"]["complete"] is True
    assert invalid_parent.read_text() == "keep"
    assert len(clients) == 1
    process = subprocess.run([sys.executable, str(SCRIPT), "--db", str(invalid_parent / "impossible.sqlite3"), "verify-pubmed", str(directory)], cwd=tmp_path, text=True, capture_output=True)
    assert process.returncode == 0 and process.stderr == ""
    assert json.loads(process.stdout) == result


def test_late_identity_failure_retains_verified_capture_and_rolls_back(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("NCBI_EMAIL", "env@example.invalid")
    monkeypatch.setenv("NCBI_API_KEY", "synthetic-api-secret")
    fixture_factory(monkeypatch)
    database = tmp_path / "ledger.sqlite3"
    project_id = project(database)
    with ReviewStore(database) as store:
        store.import_records(project_id, SearchRunSpec("seed"), [BibliographicRecord(title="Synthetic existing record", pmid="999999803", doi="10.1234/conflict")])
        prior = store.counts(project_id), store.list_search_runs(project_id)
    directory = tmp_path / "capture with spaces"
    failure = invoke(capsys, "--db", str(database), "search-pubmed", project_id, "--query", "synthetic", "--output", str(directory), "--batch-size", "2", "--import-key", "retry key", success=False)
    assert "import-pubmed" in failure and str(directory) in failure
    assert "retry key" in failure
    assert "synthetic-api-secret" not in failure
    assert verify_pubmed_capture(directory)["receipt"]["complete"]
    with ReviewStore(database) as store:
        assert (store.counts(project_id), store.list_search_runs(project_id)) == prior
        assert store._connection.execute("SELECT COUNT(*) FROM search_artifacts").fetchone()[0] == 0


def test_recovery_errors_redact_configured_key(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("NCBI_EMAIL", "env@example.invalid")
    monkeypatch.setenv("NCBI_API_KEY", "synthetic-api-secret")
    fixture_factory(monkeypatch, zero=True)
    database = tmp_path / "ledger.sqlite3"
    project_id = project(database)

    def failed_import(*args, **kwargs):
        raise ValueError("synthetic-api-secret: late operational error")

    monkeypatch.setattr(cli, "import_pubmed_capture", failed_import)
    failure = invoke(capsys, "--db", str(database), "search-pubmed", project_id, "--query", "synthetic", "--output", str(tmp_path / "capture"), success=False)
    assert "synthetic-api-secret" not in failure and "[REDACTED]" in failure
    assert "import-pubmed" in failure


def test_generic_import_parses_and_hashes_single_snapshot_during_mutation(monkeypatch, tmp_path, capsys):
    database = tmp_path / "ledger.sqlite3"
    project_id = project(database)
    source = tmp_path / "records.json"
    original = b'[{"title":"Original synthetic record","pmid":"1","custom":"original"}]'
    source.write_bytes(original)
    reader, reads = Path.read_bytes, []

    def read(path):
        content = reader(path)
        if path == source:
            reads.append(path)
            source.write_bytes(b'[{"title":"Changed synthetic record","pmid":"2"}]')
        return content

    monkeypatch.setattr(Path, "read_bytes", read)
    result = invoke(capsys, "--db", str(database), "import", project_id, str(source), "--source", "PubMed")
    assert len(reads) == 1 and result["identified"] == 1
    with ReviewStore(database) as store:
        record = store.list_records(project_id)[0]
        assert record["title"] == "Original synthetic record" and record["pmid"] == "1"
        assert record["raw"]["custom"] == "original"
        assert store.list_search_runs(project_id)[0]["source_sha256"] == hashlib.sha256(original).hexdigest()
