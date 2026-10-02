"""Independent CLI capture/replay and single-snapshot import acceptance."""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from urllib.parse import parse_qs

import pytest

import src.review.cli as cli
from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.store import ReviewStore
from src.search.pubmed_search import PubMedClient, capture_pubmed_search, verify_pubmed_capture


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "pubmed"
SECRET = "SYNTHETIC_CLI_KEY_NEVER_PERSIST"


@pytest.fixture(autouse=True)
def isolated_network_and_environment(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("CLI acceptance attempted live network or a real sleep")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr("time.sleep", denied)
    monkeypatch.delenv("NCBI_EMAIL", raising=False)
    monkeypatch.delenv("NCBI_API_KEY", raising=False)


@pytest.fixture
def oracle():
    return json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))


class ClientFactory:
    """Actual client configuration validation; deterministic fake transport/clock."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.configurations = []
        self.calls = []
        self.now = 0.0

    def __call__(self, email=None, api_key=None, **kwargs):
        self.configurations.append({"email": email, "api_key": api_key})
        return PubMedClient(email=email, api_key=api_key, transport=self.transport,
                            sleep=self.sleep, monotonic=lambda: self.now, **kwargs)

    def sleep(self, seconds):
        self.now += seconds

    def transport(self, url, data, timeout):
        self.calls.append({"endpoint": url.rsplit("/", 1)[-1], "params": parse_qs(data.decode())})
        assert self.responses, "Unexpected CLI network request"
        return self.responses.pop(0)


def responses_for(oracle):
    return [(FIXTURES / oracle["search_file"]).read_bytes(), *[
        (FIXTURES / batch["response_file"]).read_bytes() for batch in oracle["batches"]
    ]]


def project(database, title="CLI capture review"):
    with ReviewStore(database) as store:
        return store.create_project(title, "scoping", "Which synthetic records were captured?")["id"]


def invoke(capsys, arguments, success=True):
    try:
        status = cli.main(list(map(str, arguments)))
    except SystemExit as error:
        status = error.code
    output = capsys.readouterr()
    if success:
        assert status == 0, output.err
        assert output.err == ""
        return json.loads(output.out)
    assert status != 0
    assert output.out.strip() == "" and output.err.strip()
    assert "Traceback" not in output.err and SECRET not in output.err
    return output.err


def subprocess_cli(tmp_path, database, *arguments, success=True):
    environment = os.environ.copy()
    environment.pop("NCBI_EMAIL", None)
    environment.pop("NCBI_API_KEY", None)
    result = subprocess.run(
        [sys.executable, str(ROOT / "review.py"), "--db", str(database), *map(str, arguments)],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30,
    )
    if success:
        assert result.returncode == 0 and not result.stderr, result.stderr
        return json.loads(result.stdout)
    assert result.returncode != 0 and result.stderr.strip() and not result.stdout.strip()
    assert "Traceback" not in result.stderr and SECRET not in result.stderr
    return result.stderr


def ledger_state(database, project_id):
    with ReviewStore(database) as store:
        runs = store.list_search_runs(project_id)
        return deepcopy({"runs": runs, "records": store.list_records(project_id),
                         "occurrences": store.get_occurrences(project_id), "counts": store.counts(project_id),
                         "assets": {run["id"]: store.get_search_artifacts(project_id, run["id"]) for run in runs}})


@pytest.mark.parametrize("explicit_email,environment_email,expected_email", [
    (None, "environment@example.invalid", "environment@example.invalid"),
    ("explicit@example.invalid", "environment@example.invalid", "explicit@example.invalid"),
    ("explicit@example.invalid", None, "explicit@example.invalid"),
])
def test_search_cli_preserves_flags_provenance_and_credential_precedence(tmp_path, monkeypatch, capsys, oracle,
                                                                      explicit_email, environment_email, expected_email):
    database = tmp_path / "reviews.sqlite3"
    project_id = project(database)
    destination = tmp_path / "completed capture"
    factory = ClientFactory(responses_for(oracle))
    monkeypatch.setattr(cli, "PubMedClient", factory)
    monkeypatch.setenv("NCBI_API_KEY", SECRET)
    if environment_email:
        monkeypatch.setenv("NCBI_EMAIL", environment_email)
    args = ["--db", database, "search-pubmed", project_id, "--query", oracle["query"], "--output", destination,
            "--sort", "pub_date", "--datetype", "pdat", "--mindate", "2020/01/01", "--maxdate", "2025/12/31",
            "--batch-size", "2", "--import-key", "cli-capture-001"]
    if explicit_email:
        args += ["--email", explicit_email]
    result = invoke(capsys, args)
    assert set(result) == {"capture", "import"}
    assert result["import"]["identified"] == result["import"]["new_records"] == 5
    assert result["import"]["duplicates"] == 0
    assert factory.configurations == [{"email": expected_email, "api_key": SECRET}]
    assert len(factory.calls) == 4
    assert factory.calls[0]["params"]["term"] == [oracle["query"]]
    assert all(factory.calls[0]["params"][field] == [value] for field, value in oracle["filters"].items())
    assert all(call["params"]["api_key"] == [SECRET] for call in factory.calls)
    receipt = result["capture"]["receipt"]
    assert receipt["query"] == oracle["query"] and receipt["filters"] == oracle["filters"]
    assert receipt["pmids"] == oracle["ordered_pmids"] and receipt["complete"] is True
    assert SECRET not in json.dumps(result)
    state = ledger_state(database, project_id)
    assert state["runs"][0]["execution"] == receipt
    assert state["runs"][0]["searched_at"] == receipt["searched_at"]
    assert state["runs"][0]["query"] == oracle["query"]
    assert state["runs"][0]["filters"] == oracle["filters"]
    assert [record["pmid"] for record in state["records"]] == oracle["ordered_pmids"]
    assert len(state["assets"][result["import"]["search_run_id"]]) == 6
    assert state["counts"]["records_identified"] == state["counts"]["unique_records"] == 5
    assert state["counts"]["all_checks_passed"] is True
    exported = invoke(capsys, ["--db", database, "export", project_id, tmp_path / "exported"])
    assert len(exported["files"]) == 15
    bundle = json.loads((tmp_path / "exported" / "project.json").read_text())
    assert bundle["search_runs"][0]["execution"] == receipt and len(bundle["search_artifacts"]) == 6
    assert SECRET.encode() not in database.read_bytes()


def test_zero_result_search_cli_preserves_valid_execution_without_screening_records(tmp_path, monkeypatch, capsys, oracle):
    database = tmp_path / "reviews.sqlite3"
    project_id = project(database)
    zero = oracle["zero"]
    factory = ClientFactory([(FIXTURES / zero["search_file"]).read_bytes()])
    monkeypatch.setattr(cli, "PubMedClient", factory)
    monkeypatch.setenv("NCBI_EMAIL", "synthetic@example.invalid")
    result = invoke(capsys, ["--db", database, "search-pubmed", project_id, "--query", zero["query"],
                            "--output", tmp_path / "zero-capture"])
    assert len(factory.calls) == 1 and result["import"]["identified"] == 0
    assert result["capture"]["receipt"]["fetched_count"] == 0
    state = ledger_state(database, project_id)
    assert state["records"] == state["occurrences"] == []
    assert len(state["runs"]) == 1 and state["runs"][0]["execution"]["complete"] is True
    assert len(next(iter(state["assets"].values()))) == 3


@pytest.fixture
def saved_capture(tmp_path, oracle):
    responses = responses_for(oracle)
    class Client:
        def request(self, endpoint, params):
            return responses.pop(0)
    return capture_pubmed_search(oracle["query"], tmp_path / "saved-capture", client=Client(),
                                  filters=oracle["filters"], batch_size=2)


@pytest.mark.parametrize("database_option", ["none", "missing", "invalid_parent"])
def test_verify_cli_never_constructs_a_ledger_even_when_db_path_is_invalid(tmp_path, monkeypatch, capsys, saved_capture, database_option):
    def denied_store(*args, **kwargs):
        pytest.fail("verify-pubmed constructed a ledger")
    monkeypatch.setattr(cli, "ReviewStore", denied_store)
    arguments = ["verify-pubmed", saved_capture["directory"]]
    if database_option == "missing":
        path = tmp_path / "must-not-create.sqlite3"
        arguments = ["--db", path, *arguments]
    elif database_option == "invalid_parent":
        blocker = tmp_path / "blocker"
        blocker.write_text("File, not a database directory", encoding="utf-8")
        path = blocker / "must-not-open.sqlite3"
        arguments = ["--db", path, *arguments]
    verified = invoke(capsys, arguments)
    assert verified == saved_capture
    if database_option == "missing":
        assert not path.exists()


def test_saved_capture_subprocess_verify_import_export_deleted_source_and_portable_keyed_replay(tmp_path, saved_capture):
    database = tmp_path / "reviews.sqlite3"
    project_id = subprocess_cli(tmp_path, database, "create", "--title", "Offline CLI replay", "--type", "systematic", "--question", "Which records?")["id"]
    invalid_parent = tmp_path / "not-directory"
    invalid_parent.write_text("Sentinel", encoding="utf-8")
    assert subprocess_cli(tmp_path, invalid_parent / "not-db.sqlite3", "verify-pubmed", saved_capture["directory"]) == saved_capture
    imported = subprocess_cli(tmp_path, database, "import-pubmed", project_id, saved_capture["directory"], "--import-key", "portable-cli-key")
    before = ledger_state(database, project_id)
    directory = tmp_path / "offline-export"
    exported = subprocess_cli(tmp_path, database, "export", project_id, directory)
    assert len(exported["files"]) == 15
    shutil.rmtree(saved_capture["directory"])
    replay_directory = directory / "search_captures" / imported["search_run_id"]
    assert subprocess_cli(tmp_path, invalid_parent / "not-db.sqlite3", "verify-pubmed", replay_directory)["receipt"] == saved_capture["receipt"]
    assert subprocess_cli(tmp_path, database, "import-pubmed", project_id, replay_directory, "--import-key", "portable-cli-key") == imported
    assert ledger_state(database, project_id) == before
    assert before["runs"][0]["execution"] == saved_capture["receipt"]
    assert before["runs"][0]["source_file"] == saved_capture["xml_file"]


@pytest.mark.parametrize("invalid", ["unknown_project", "missing_email", "blank_email", "empty_query", "date_partial", "bad_date", "inverted_dates", "batch_zero", "batch_201", "existing_output", "empty_import_key", "blank_import_key"])
def test_search_validation_fails_before_any_request_and_preserves_prior_ledger(tmp_path, monkeypatch, capsys, invalid):
    database = tmp_path / "reviews.sqlite3"
    project_id = project(database)
    destination = tmp_path / "capture"
    before = ledger_state(database, project_id)
    factory = ClientFactory([])
    monkeypatch.setattr(cli, "PubMedClient", factory)
    if invalid != "missing_email":
        monkeypatch.setenv("NCBI_EMAIL", "synthetic@example.invalid")
    args = ["--db", database, "search-pubmed", "unknown-project" if invalid == "unknown_project" else project_id,
            "--query", "" if invalid == "empty_query" else "Synthetic query", "--output", destination, "--batch-size", "2"]
    if invalid == "blank_email":
        args += ["--email", "  "]
    elif invalid == "date_partial":
        args += ["--datetype", "pdat"]
    elif invalid == "bad_date":
        args += ["--datetype", "pdat", "--mindate", "2026/02/30", "--maxdate", "2026/12/31"]
    elif invalid == "inverted_dates":
        args += ["--datetype", "pdat", "--mindate", "2026", "--maxdate", "2020"]
    elif invalid in ("batch_zero", "batch_201"):
        args += ["--batch-size", "0" if invalid == "batch_zero" else "201"]
    elif invalid in ("empty_import_key", "blank_import_key"):
        args += ["--import-key", "" if invalid == "empty_import_key" else "  "]
    elif invalid == "existing_output":
        destination.mkdir()
        (destination / "sentinel.txt").write_text("Keep existing output", encoding="utf-8")
    invoke(capsys, args, success=False)
    assert factory.calls == []
    assert ledger_state(database, project_id) == before
    if invalid in ("unknown_project", "empty_import_key", "blank_import_key"):
        assert factory.configurations == []
    if invalid == "existing_output":
        assert (destination / "sentinel.txt").read_text() == "Keep existing output"
    else:
        assert not destination.exists()


def test_capture_failure_does_not_call_import_or_leave_a_success_receipt(tmp_path, monkeypatch, capsys):
    database = tmp_path / "reviews.sqlite3"
    project_id = project(database)
    before = ledger_state(database, project_id)
    factory = ClientFactory([(FIXTURES / "error-search.xml").read_bytes()])
    monkeypatch.setattr(cli, "PubMedClient", factory)
    monkeypatch.setenv("NCBI_EMAIL", "synthetic@example.invalid")
    def no_import(*args, **kwargs):
        pytest.fail("Failed capture was imported")
    monkeypatch.setattr(cli, "import_pubmed_capture", no_import)
    invoke(capsys, ["--db", database, "search-pubmed", project_id, "--query", "Synthetic query",
                   "--output", tmp_path / "failed-capture"], success=False)
    assert len(factory.calls) == 1 and not (tmp_path / "failed-capture").exists()
    assert ledger_state(database, project_id) == before


def test_late_ledger_failure_retains_complete_capture_and_provides_offline_recovery(tmp_path, monkeypatch, capsys, oracle):
    database = tmp_path / "reviews.sqlite3"
    project_id = project(database)
    with ReviewStore(database) as store:
        store.import_records(project_id, SearchRunSpec(source="Existing incompatible record"), [
            BibliographicRecord(title="Existing report with conflicting DOI", pmid="999999803", doi="10.5555/cli-conflict"),
        ])
    before = ledger_state(database, project_id)
    factory = ClientFactory(responses_for(oracle))
    monkeypatch.setattr(cli, "PubMedClient", factory)
    monkeypatch.setenv("NCBI_EMAIL", "synthetic@example.invalid")
    monkeypatch.setenv("NCBI_API_KEY", SECRET)
    destination = tmp_path / "retained complete capture"
    error = invoke(capsys, ["--db", database, "search-pubmed", project_id, "--query", oracle["query"],
                           "--output", destination, "--batch-size", "2"], success=False)
    assert str(destination) in error and "import-pubmed" in error and str(database) in error
    assert SECRET not in error
    assert len(factory.calls) == 4
    assert verify_pubmed_capture(destination)["receipt"]["complete"] is True
    assert ledger_state(database, project_id) == before
    recovered_project = project(database, "Independent recovery project")
    recovered = invoke(capsys, ["--db", database, "import-pubmed", recovered_project, destination])
    assert recovered["identified"] == recovered["new_records"] == 5
    assert len(factory.calls) == 4  # Recovery did not rerun live discovery.


def test_recovery_error_redacts_secret_bearing_import_exception(tmp_path, monkeypatch, capsys, oracle):
    database = tmp_path / "reviews.sqlite3"
    project_id = project(database)
    before = ledger_state(database, project_id)
    factory = ClientFactory(responses_for(oracle))
    monkeypatch.setattr(cli, "PubMedClient", factory)
    monkeypatch.setenv("NCBI_EMAIL", "synthetic@example.invalid")
    monkeypatch.setenv("NCBI_API_KEY", SECRET)
    def sensitive_failure(*args, **kwargs):
        raise ValueError("Synthetic failure included api_key=" + SECRET)
    monkeypatch.setattr(cli, "import_pubmed_capture", sensitive_failure)
    destination = tmp_path / "retained-on-error"
    error = invoke(capsys, ["--db", database, "search-pubmed", project_id, "--query", oracle["query"],
                           "--output", destination, "--batch-size", "2"], success=False)
    assert "import-pubmed" in error and SECRET not in error
    assert verify_pubmed_capture(destination)["receipt"]["complete"] is True
    assert ledger_state(database, project_id) == before


def test_import_pubmed_checks_project_before_reading_capture(tmp_path, monkeypatch, capsys, saved_capture):
    database = tmp_path / "reviews.sqlite3"
    existing = project(database)
    def denied_helper(*args, **kwargs):
        pytest.fail("Unknown project reached capture reader")
    monkeypatch.setattr(cli, "import_pubmed_capture", denied_helper)
    invoke(capsys, ["--db", database, "import-pubmed", "unknown-project", saved_capture["directory"]], success=False)
    assert ledger_state(database, existing)["runs"] == []


@pytest.mark.parametrize("explicit_format", [False, True])
def test_generic_import_parses_and_hashes_exactly_one_byte_snapshot_during_mutation(tmp_path, monkeypatch, capsys, explicit_format):
    database = tmp_path / "reviews.sqlite3"
    project_id = project(database)
    source = tmp_path / "generic.json"
    original = b'[{"title":"Original synthetic title","extra":"Original provenance"}]'
    source.write_bytes(original)
    read_bytes = Path.read_bytes
    reads = []
    def snapshot_then_change(path):
        content = read_bytes(path)
        if path.resolve() == source.resolve():
            reads.append(content)
            path.write_bytes(b'[{"title":"Changed after snapshot"}]')
        return content
    monkeypatch.setattr(Path, "read_bytes", snapshot_then_change)
    arguments = ["--db", database, "import", project_id, source, "--source", "Local export"]
    if explicit_format:
        arguments += ["--format", "json"]
    imported = invoke(capsys, arguments)
    assert len(reads) == 1 and imported["identified"] == imported["new_records"] == 1
    state = ledger_state(database, project_id)
    assert state["runs"][0]["source_sha256"] == hashlib.sha256(original).hexdigest()
    assert state["runs"][0]["execution"] is None
    assert state["records"][0]["title"] == "Original synthetic title"
    assert state["occurrences"][0]["record"]["raw"]["extra"] == "Original provenance"
    assert state["assets"][imported["search_run_id"]] == {}


def test_generic_unknown_extension_is_contextual_and_explicit_format_remains_supported(tmp_path, capsys):
    database = tmp_path / "reviews.sqlite3"
    project_id = project(database)
    source = tmp_path / "export.bin"
    source.write_bytes(b'[{"title":"Synthetic report"}]')
    error = invoke(capsys, ["--db", database, "import", project_id, source, "--source", "Local export"], success=False)
    assert str(source) in error and "format" in error.lower()
    assert ledger_state(database, project_id)["runs"] == []
    result = invoke(capsys, ["--db", database, "import", project_id, source, "--source", "Local export", "--format", "json"])
    assert result["new_records"] == 1


def test_cli_import_and_offline_verification_initialize_no_models_settings_or_dotenv(tmp_path, saved_capture):
    code = """
import socket, sys
sys.path.insert(0, sys.argv[1])
def denied(*args, **kwargs):
    raise AssertionError('Network initialized by CLI')
socket.create_connection = denied
import src.review.cli as cli
assert not {'torch','chromadb','sentence_transformers','dotenv','src.settings'}.intersection(sys.modules)
assert cli.main(['--db',sys.argv[2],'verify-pubmed',sys.argv[3]]) == 0
assert not {'torch','chromadb','sentence_transformers','dotenv','src.settings'}.intersection(sys.modules)
"""
    database = tmp_path / "never-created.sqlite3"
    result = subprocess.run([sys.executable, "-c", code, str(ROOT), str(database), saved_capture["directory"]],
                            cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0 and not result.stderr, result.stderr
    assert json.loads(result.stdout)["receipt"] == saved_capture["receipt"]
    assert not database.exists()
