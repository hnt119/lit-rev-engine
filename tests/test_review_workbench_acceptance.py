"""Independent, offline acceptance checks; temporary ratings are software fixtures.

These tests reuse exposed saved retrieval evidence. They do not conduct human or
clinical review, infer source answerability, or measure a new retrieval model.
"""

from copy import deepcopy
from contextlib import contextmanager
import hashlib
import http.client
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from threading import Thread

import pytest

from src.review_workbench.contracts import canonical, digest
from src.review_workbench.receipts import load_packet, public_packet


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/qwen_components_confirmation_run_v1"
ARCHIVE_SHA = "7756af917899a582ba2a9e9169620af113e8a6404f4f640d9652530670b77e22"
RECEIPT_SHA = "3ba4da317d497cc021a90e9dcc9f88b3667bbdba85e7f94b633f7427dc7a9c80"
JOB_SHA = "46cdb4be34507d170d656eeba19478bf493acdfe6315a352ae37bc941d0b19e5"
RESULTS_SHA = "8867d3da507dd32802f083be963e4799eca101a2f4d8afa47cf22f95688d3fbc"


def sha(body):
    return hashlib.sha256(body).hexdigest()


@pytest.fixture(scope="module")
def receipt_bytes():
    # Select one bounded flat original file; never extract an archive tree.
    compressed = (FIXTURE / "artifacts.tar.xz").read_bytes()
    assert len(compressed) == 2272864 and sha(compressed) == ARCHIVE_SHA
    with tarfile.open(fileobj=io.BytesIO(compressed), mode="r:xz") as archive:
        members = [member for member in archive if member.name == "validation.receipt.json"]
        assert len(members) == 1
        member = members[0]
        assert member.isreg() and member.size == 8597476
        body = archive.extractfile(member).read(member.size + 1)
    assert len(body) == member.size and sha(body) == RECEIPT_SHA
    return body


@pytest.fixture(scope="module")
def receipt_path(tmp_path_factory, receipt_bytes):
    path = tmp_path_factory.mktemp("workbench-original") / "validation.receipt.json"
    path.write_bytes(receipt_bytes)
    return path


@pytest.fixture(scope="module")
def packet(receipt_path):
    return load_packet(receipt_path, RECEIPT_SHA)


def draft_for(packet, bundle=None, reviewer="software-test-only"):
    bundle = bundle or packet["bundles"][0]
    question = next(row for row in packet["questions"] if row["id"] == bundle["question_id"])
    return {
        "packet_id": packet["packet_id"], "bundle_id": bundle["id"],
        "reviewer": reviewer, "status": "not_assessed", "reason": "",
        "ratings": [{"passage_id": passage["id"], "rating": None,
                     "component_ratings": {part["id"]: None for part in question["components"]}}
                    for passage in bundle["passages"]],
        "supporting_passage_ids": [], "missing_components": [], "contradiction": False,
        "source_inspected": False, "supersedes": None, "review_seconds": None,
    }


def save(packet, directory, draft):
    from src.review_workbench.assessments import save_assessment
    return save_assessment(packet, directory, draft)


def records(packet, directory):
    from src.review_workbench.assessments import list_assessments
    return list_assessments(packet, directory)


def summary(packet, rows):
    from src.review_workbench.evaluation import summarize
    return summarize(packet, rows)


def test_real_receipt_packet_binds_original_identity_and_retained_sources(packet):
    assert packet["binding"]["receipt_file_sha256"] == RECEIPT_SHA
    assert packet["binding"]["job_sha256"] == JOB_SHA
    assert packet["binding"]["results_sha256"] == RESULTS_SHA
    assert len(packet["questions"]) == 8
    assert len(packet["bundles"]) == 32
    assert len(packet["sources"]) == 2
    assert len({row["id"] for row in packet["bundles"]}) == 32
    assert sum(len(row["blocks"]) for row in packet["sources"]) == 100
    for bundle in packet["bundles"]:
        assert len(bundle["passages"]) == 5
        assert [row["rank"] for row in bundle["passages"]] == [1, 2, 3, 4, 5]
        for passage in bundle["passages"]:
            source = next(row for row in packet["sources"] if row["document_id"] == passage["document_id"])
            block = next(row for row in source["blocks"] if row["id"] == passage["anchor"]["block_id"])
            anchor = passage["anchor"]
            assert block["text"][anchor["start"]:anchor["end"]] == anchor["quote"]
            assert source["source_sha256"] == passage["source_sha256"]
            assert source["blocks_sha256"] == passage["blocks_sha256"]
    assert packet["source_answerability"] == "not_assessed"
    assert packet["verification"] == "NOT_RUN"
    assert packet["current_ledger_state"] == "not_checked"


def test_pinned_file_digest_required_not_its_envelope_digest(receipt_path, receipt_bytes):
    with pytest.raises(ValueError):
        load_packet(receipt_path, json.loads(receipt_bytes)["payload_sha256"])
    with pytest.raises(ValueError):
        load_packet(receipt_path, "A" * 64)


def test_receipt_tampering_rejected_even_with_unchanged_envelope(tmp_path, receipt_bytes):
    path = tmp_path / "changed.json"
    path.write_bytes(receipt_bytes + b" ")
    with pytest.raises(ValueError, match="trusted whole-file"):
        load_packet(path, RECEIPT_SHA)


def test_resigned_trace_tampering_rejected_by_frozen_recomputation(tmp_path, receipt_bytes):
    value = json.loads(receipt_bytes)
    value["payload"]["recomputed"]["traces"][0]["passages"][0]["anchor"]["quote"] += " changed"
    value["payload_sha256"] = digest(value["payload"])
    body = canonical(value).encode()
    path = tmp_path / "changed-trace.json"
    path.write_bytes(body)
    with pytest.raises(ValueError, match="reconstruction"):
        load_packet(path, sha(body))


@pytest.mark.parametrize("addition", [b',"payload_sha256":"duplicate"}', b',"x":NaN}'])
def test_duplicate_or_nonfinite_json_rejected(tmp_path, receipt_bytes, addition):
    body = receipt_bytes.rstrip()[:-1] + addition
    path = tmp_path / "bad-json.json"
    path.write_bytes(body)
    with pytest.raises(ValueError, match="JSON"):
        load_packet(path, sha(body))


def test_blinding_is_default_and_reveal_is_explicit_without_mutation(packet):
    before = deepcopy(packet)
    blinded = public_packet(packet)
    revealed = public_packet(packet, reveal=True)
    assert blinded["display_mode"] == "blinded"
    assert revealed["display_mode"] == "revealed"
    assert "shared_batch_runtime" not in blinded
    for bundle in blinded["bundles"]:
        assert "method_key" not in bundle
        for passage in bundle["passages"]:
            assert not ({"score", "query_scores", "selection_reasons"} & passage.keys())
    assert all("method_key" in bundle for bundle in revealed["bundles"])
    assert packet == before


@pytest.mark.parametrize("field,value", [
    ("packet_id", "0" * 64), ("bundle_id", "0" * 64), ("status", "complete"),
    ("status", True), ("contradiction", 1), ("source_inspected", 1),
    ("review_seconds", True), ("review_seconds", -1), ("review_seconds", float("inf")),
    ("reviewer", ""), ("reviewer", None), ("reason", []), ("supersedes", "../outside"),
])
def test_bad_assessment_types_or_identity_rejected_without_writes(packet, tmp_path, field, value):
    draft = draft_for(packet)
    draft[field] = value
    directory = tmp_path / "assessments"
    with pytest.raises(ValueError):
        save(packet, directory, draft)
    assert not list(directory.glob("*.json"))


@pytest.mark.parametrize("rating", [True, -1, 4, 1.0, "2", float("nan")])
def test_rating_requires_null_or_actual_integer_zero_to_three(packet, tmp_path, rating):
    draft = draft_for(packet)
    draft["ratings"][0]["rating"] = rating
    with pytest.raises(ValueError):
        save(packet, tmp_path / "assessments", draft)


@pytest.mark.parametrize("field", ["supporting_passage_ids", "missing_components"])
def test_foreign_support_and_component_references_rejected(packet, tmp_path, field):
    draft = draft_for(packet)
    draft[field] = ["foreign-reference"]
    with pytest.raises(ValueError):
        save(packet, tmp_path / "assessments", draft)


def test_foreign_passage_rating_rejected(packet, tmp_path):
    draft = draft_for(packet)
    foreign = next(p["id"] for b in packet["bundles"] for p in b["passages"]
                   if p["id"] not in {row["passage_id"] for row in draft["ratings"]})
    draft["ratings"][0]["passage_id"] = foreign
    with pytest.raises(ValueError):
        save(packet, tmp_path / "assessments", draft)


def test_duplicate_ratings_and_inexact_component_keys_rejected(packet, tmp_path):
    original = draft_for(packet)
    for alter in (lambda d: d["ratings"].append(deepcopy(d["ratings"][0])),
                  lambda d: d["ratings"][0]["component_ratings"].update({"invented": None})):
        draft = deepcopy(original)
        alter(draft)
        with pytest.raises(ValueError):
            save(packet, tmp_path / "assessments", draft)


def test_unassessed_null_ratings_round_trip_and_do_not_invent_verification(packet, tmp_path):
    directory = tmp_path / "assessments"
    record = save(packet, directory, draft_for(packet))
    assert records(packet, directory) == [record]
    assert all(row["rating"] is None for row in record["ratings"])
    assert all(value is None for row in record["ratings"] for value in row["component_ratings"].values())
    assert record["status"] == "not_assessed"
    assert record["source_answerability"] == "not_assessed"
    assert record["verification"] == "NOT_RUN"
    assert record["current_ledger_state"] == "not_checked"
    assert record["review_basis"] == "single_human"


def test_unknown_claim_fields_cannot_be_added_to_assessment(packet, tmp_path):
    for key, value in (("source_answerability", "answerable"), ("verification", "independent"),
                       ("binding", {}), ("method_key", "qwen_components_hybrid")):
        draft = draft_for(packet)
        draft[key] = value
        with pytest.raises(ValueError):
            save(packet, tmp_path / "assessments", draft)


def test_immutable_history_and_explicit_supersession_round_trip(packet, tmp_path):
    directory = tmp_path / "assessments"
    draft = draft_for(packet)
    first = save(packet, directory, draft)
    original_files = {path.name: path.read_bytes() for path in directory.glob("*.json")}
    revised = deepcopy(draft)
    revised.update(status="uncertain", reason="Synthetic software fixture; no substantive review.",
                   supersedes=first["id"], review_seconds=1.25)
    second = save(packet, directory, revised)
    assert second["id"] != first["id"]
    assert second["supersedes"] == first["id"]
    assert all((directory / name).read_bytes() == body for name, body in original_files.items())
    assert {row["id"] for row in records(packet, directory)} == {first["id"], second["id"]}
    with pytest.raises(ValueError):
        save(packet, directory, revised)  # stale branch cannot replace a newer head
    assert len(records(packet, directory)) == 2


def test_cross_reviewer_or_bundle_supersession_rejected(packet, tmp_path):
    directory = tmp_path / "assessments"
    first = save(packet, directory, draft_for(packet))
    for draft in (draft_for(packet, reviewer="different-reviewer"), draft_for(packet, packet["bundles"][1])):
        draft["supersedes"] = first["id"]
        with pytest.raises(ValueError):
            save(packet, directory, draft)


@pytest.mark.parametrize("kind", ["packet", "trace", "checksum"])
def test_reload_rejects_tampered_or_stale_record_bindings(packet, tmp_path, kind):
    directory = tmp_path / "assessments"
    record = save(packet, directory, draft_for(packet))
    path = next(directory.glob("*.json"))
    altered = deepcopy(record)
    if kind == "packet":
        altered["packet_id"] = "0" * 64
    elif kind == "trace":
        altered["binding"]["trace_sha256"] = "0" * 64
    else:
        altered["reason"] = "Tampering without a checksum update"
    if kind != "checksum":
        altered["record_sha256"] = digest({key: value for key, value in altered.items() if key != "record_sha256"})
    path.write_text(canonical(altered), encoding="utf-8")
    with pytest.raises(ValueError):
        records(packet, directory)


def test_no_symlink_receipt_file_or_parent(packet, receipt_path, tmp_path):
    linked_file = tmp_path / "receipt.json"
    linked_file.symlink_to(receipt_path)
    with pytest.raises(ValueError):
        load_packet(linked_file, RECEIPT_SHA)
    linked_parent = tmp_path / "receipt-directory"
    linked_parent.symlink_to(receipt_path.parent, target_is_directory=True)
    with pytest.raises(ValueError):
        load_packet(linked_parent / receipt_path.name, RECEIPT_SHA)


def test_no_assessment_symlink_directory_or_record(packet, tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError):
        save(packet, linked, draft_for(packet))
    record = save(packet, real, draft_for(packet))
    path = next(real.glob("*.json"))
    outside = tmp_path / "record.json"
    path.rename(outside)
    path.symlink_to(outside)
    with pytest.raises(ValueError):
        records(packet, real)
    assert json.loads(outside.read_text())["id"] == record["id"]


def test_parent_traversal_rejected_without_creating_assessment_target(packet, tmp_path):
    directory = tmp_path / "child" / ".." / "escape"
    with pytest.raises(ValueError):
        save(packet, directory, draft_for(packet))
    assert not (tmp_path / "escape").exists()


def test_no_human_records_produce_unknown_metrics_and_explicit_not_run(packet):
    report = summary(packet, [])
    assert report["assessment_records"] == report["current_assessment_records"] == 0
    assert report["source_answerability"] == "not_assessed"
    assert report["independent_verification"] == "NOT_RUN"
    for method in report["methods"].values():
        assert method["bundle_count"] == method["bundles_without_records"] == 8
        assert method["bundles_with_records"] == method["current_human_assessments"] == 0
        assert method["mean_observed_passage_grade"] is None
        assert method["mean_fully_rated_bundle_precision"] is None
        assert method["mean_precision_at_5"] is None
        assert method["mean_strict_precision_at_5"] is None
        assert method["known_review_seconds_total"] is None
        assert method["fully_rated_bundle_observations"] == 0
    assert "new model inference" in report["not_run"]
    assert "independent human verification" in report["not_run"]
    assert report["shared_saved_batch"]["attribution"].startswith("Shared saved batch")


def test_partial_ratings_keep_unknowns_out_of_precision_denominator(packet, tmp_path):
    bundle = packet["bundles"][0]
    draft = draft_for(packet, bundle)
    for row, grade in zip(draft["ratings"], [3, 2, 1, 0, None], strict=True):
        row["rating"] = grade
    draft["ratings"].pop()  # An omitted rating is unknown, like an explicit null.
    record = save(packet, tmp_path / "assessments", draft)
    method = summary(packet, [record])["methods"][bundle["method_key"]]
    assert method["rated_passages"] == 4
    assert method["unknown_passage_ratings_in_recorded_bundles"] == 1
    assert method["mean_observed_passage_grade"] == 1.5
    assert method["observed_grade_proportion_denominator"] == 4
    assert method["observed_useful_passage_proportion"] == 0.5
    assert method["observed_strict_passage_proportion"] == 0.25
    assert method["fully_rated_bundle_observations"] == 0
    assert method["mean_fully_rated_bundle_precision"] is None
    assert method["p5_fully_rated_bundle_observations"] == 0
    assert method["mean_precision_at_5"] is None
    assert method["mean_strict_precision_at_5"] is None
    assert method["bundle_support_counts"]["not_assessed"] == 1
    assert method["bundle_support_counts"]["sufficient"] == 0


def test_precision_uses_fully_rated_current_bundles_and_explicit_support_status(packet, tmp_path):
    bundle = packet["bundles"][0]
    directory = tmp_path / "assessments"
    draft = draft_for(packet, bundle)
    first = save(packet, directory, draft)
    draft.update(supersedes=first["id"], status="uncertain", reason="Synthetic arithmetic fixture.",
                 source_inspected=True, contradiction=True, review_seconds=2.5)
    for row, grade in zip(draft["ratings"], [3, 2, 1, 0, 2], strict=True):
        row["rating"] = grade
    second = save(packet, directory, draft)
    report = summary(packet, records(packet, directory))
    assert report["assessment_records"] == 2
    assert report["current_assessment_records"] == report["superseded_assessment_records"] == 1
    method = report["methods"][bundle["method_key"]]
    assert method["current_human_assessments"] == 1
    assert method["rated_passages"] == 5
    assert method["fully_rated_bundle_observations"] == 1
    assert method["mean_fully_rated_bundle_precision"] == pytest.approx(3 / 5)
    assert method["p5_fully_rated_bundle_observations"] == 1
    assert method["mean_precision_at_5"] == pytest.approx(3 / 5)
    assert method["mean_strict_precision_at_5"] == pytest.approx(1 / 5)
    assert method["observed_grade_proportion_denominator"] == 5
    assert method["mean_observed_passage_grade"] == pytest.approx(8 / 5)
    assert method["bundle_support_counts"]["uncertain"] == 1
    assert method["bundle_support_counts"]["sufficient"] == 0
    assert method["known_review_seconds_total"] == 2.5
    assert method["source_inspected_records"] == method["declared_contradictions"] == 1
    assert report["source_answerability"] == "not_assessed"
    assert report["independent_verification"] == "NOT_RUN"
    assert second["source_inspected"] is True


@contextmanager
def running_server(packet, directory, reveal=False):
    from src.review_workbench.server import create_server
    server = create_server(packet, directory, port=0, reveal_methods=reveal)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    try:
        assert server.server_address[0] == "127.0.0.1"
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


def request(server, method, path, body=None, headers=None, host=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
    data = canonical(body).encode() if isinstance(body, dict) else body
    connection.putrequest(method, path, skip_host=True)
    connection.putheader("Host", host or f"127.0.0.1:{server.server_port}")
    supplied = headers or []
    for key, value in supplied:
        connection.putheader(key, value)
    if data is not None and not any(key.lower() == "content-length" for key, _ in supplied):
        connection.putheader("Content-Length", str(len(data)))
    connection.endheaders(data)
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


def save_headers(server):
    return [("Origin", f"http://127.0.0.1:{server.server_port}"),
            ("X-Workbench-CSRF", server.csrf_token), ("Content-Type", "application/json")]


def test_loopback_session_and_page_have_blind_packet_and_strict_browser_headers(packet, tmp_path):
    with running_server(packet, tmp_path / "assessments") as server:
        status, headers, body = request(server, "GET", "/api/session")
        assert status == 200
        session = json.loads(body)
        assert session["csrf_token"] == server.csrf_token
        assert session["reveal_methods"] is False
        assert session["packet"]["display_mode"] == "blinded"
        assert session["assessments"] == []
        assert all("method_key" not in row for row in session["packet"]["bundles"])
        assert headers["Cache-Control"] == "no-store"
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["Referrer-Policy"] == "no-referrer"
        assert "Access-Control-Allow-Origin" not in headers
        csp = headers["Content-Security-Policy"]
        assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
        assert "base-uri 'none'" in csp and "'unsafe-inline'" not in csp and "'unsafe-eval'" not in csp
        status, _, body = request(server, "GET", "/")
        assert status == 200 and b"/assets/workbench.js" in body
        assert b"<script>" not in body


@pytest.mark.parametrize("path", ["/api/session?x=1", "/api/session/", "/api/assessments", "/.env",
                                  "/assets/../.env", "/assets/%2e%2e/.env", "/assets/workbench.js?x=1"])
def test_http_exact_routes_do_not_serve_arbitrary_files(packet, tmp_path, path):
    with running_server(packet, tmp_path / "assessments") as server:
        status, _, body = request(server, "GET", path)
        assert status == 404
        assert "Unknown local route" in json.loads(body)["error"]


@pytest.mark.parametrize("case", ["missing_origin", "foreign_origin", "null_origin", "missing_token",
                                  "wrong_token", "duplicate_origin", "duplicate_token", "foreign_host"])
def test_http_save_requires_exact_origin_host_and_one_csrf_token(packet, tmp_path, case):
    with running_server(packet, tmp_path / "assessments") as server:
        headers = save_headers(server)
        host = None
        if case == "missing_origin":
            headers = [(k, v) for k, v in headers if k != "Origin"]
        elif case in {"foreign_origin", "null_origin"}:
            headers[0] = ("Origin", "https://attacker.invalid" if case == "foreign_origin" else "null")
        elif case == "missing_token":
            headers = [(k, v) for k, v in headers if k != "X-Workbench-CSRF"]
        elif case == "wrong_token":
            headers[1] = ("X-Workbench-CSRF", "incorrect")
        elif case == "duplicate_origin":
            headers.append(headers[0])
        elif case == "duplicate_token":
            headers.append(headers[1])
        else:
            host = "attacker.invalid"
        status, _, _ = request(server, "POST", "/api/assessments", draft_for(packet), headers, host)
        assert status == 403
        assert records(packet, tmp_path / "assessments") == []


@pytest.mark.parametrize("case", ["wrong_type", "duplicate_length", "oversize", "transfer_encoding", "invalid_json"])
def test_http_save_rejects_malformed_or_unbounded_requests(packet, tmp_path, case):
    with running_server(packet, tmp_path / "assessments") as server:
        headers = save_headers(server)
        body = b"{}"
        if case == "wrong_type":
            headers[2] = ("Content-Type", "text/plain")
        elif case == "duplicate_length":
            headers += [("Content-Length", "2"), ("Content-Length", "2")]
        elif case == "oversize":
            headers.append(("Content-Length", str(1024 * 1024 + 1)))
        elif case == "transfer_encoding":
            headers.append(("Transfer-Encoding", "chunked"))
        else:
            body = b'{"packet_id":NaN}'
        status, _, _ = request(server, "POST", "/api/assessments", body, headers)
        assert status == 400
        assert records(packet, tmp_path / "assessments") == []


def test_http_save_reload_and_revealed_mode_are_bound_on_server(packet, tmp_path):
    directory = tmp_path / "assessments"
    with running_server(packet, directory, reveal=True) as server:
        draft = draft_for(packet)
        draft.update(status="uncertain", reason='<img src=x onerror="alert(1)"> Synthetic text only.')
        status, _, body = request(server, "POST", "/api/assessments", draft, save_headers(server))
        assert status == 201
        record = json.loads(body)["assessment"]
        assert record["display_mode"] == "revealed"
        assert record["reason"] == draft["reason"]
        status, _, body = request(server, "GET", "/api/session")
        session = json.loads(body)
        assert status == 200 and session["assessments"] == [record]
        assert session["packet"]["display_mode"] == "revealed"
        assert all("method_key" in row for row in session["packet"]["bundles"])
        status, _, html = request(server, "GET", "/")
        assert status == 200 and draft["reason"].encode() not in html
    assert records(packet, directory) == [record]


def test_cli_demo_copies_only_exact_pinned_receipt_and_refuses_reuse(tmp_path):
    from src.review_workbench.cli import demo
    destination = tmp_path / "demo"
    result = demo(destination)
    assert result["assessment_records_created"] == 0
    assert result["receipt_sha256"] == RECEIPT_SHA
    assert {path.name for path in destination.iterdir()} == {"validation.receipt.json"}
    assert sha((destination / "validation.receipt.json").read_bytes()) == RECEIPT_SHA
    with pytest.raises(ValueError):
        demo(destination)
    with pytest.raises(ValueError):
        demo(Path("relative-demo"))


def test_cli_evaluation_without_human_records_is_immutable_and_unknown(receipt_path, tmp_path):
    output = tmp_path / "report.json"
    command = [sys.executable, str(ROOT / "review_workbench.py"), "evaluate", "--receipt", str(receipt_path),
               "--receipt-sha256", RECEIPT_SHA, "--assessments", str(tmp_path / "assessments"), "--output", str(output)]
    first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert first.returncode == 0, first.stdout + first.stderr
    original = output.read_bytes()
    result = json.loads(original)
    assert result["current_assessment_records"] == 0
    assert result["independent_verification"] == "NOT_RUN"
    assert all(row["mean_fully_rated_bundle_precision"] is None for row in result["methods"].values())
    second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert second.returncode == 2
    assert output.read_bytes() == original


def test_demo_load_and_summary_never_open_ledger_env_or_model_or_network(tmp_path):
    script = r'''
import pathlib, sys
root = pathlib.Path(sys.argv[1])
destination = pathlib.Path(sys.argv[2])
forbidden_models = {"torch", "transformers", "sentence_transformers", "huggingface_hub", "chromadb"}
def audit(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = pathlib.Path(args[0].decode() if isinstance(args[0], bytes) else args[0])
        if path.name == ".env" or path.absolute().is_relative_to(root / "data"):
            raise AssertionError("Forbidden sensitive or ledger file access")
    if event == "import" and args[0].split(".")[0] in forbidden_models:
        raise AssertionError("Forbidden model library import")
    if event in {"sqlite3.connect", "socket.connect", "socket.bind", "socket.getaddrinfo", "subprocess.Popen"}:
        raise AssertionError("Forbidden database, network or child-process access")
sys.addaudithook(audit)
from src.review_workbench.cli import demo
from src.review_workbench.receipts import load_packet
from src.review_workbench.evaluation import summarize
result = demo(destination)
packet = load_packet(result["receipt"], result["receipt_sha256"])
report = summarize(packet, [])
assert report["current_assessment_records"] == 0
assert report["independent_verification"] == "NOT_RUN"
assert all(value["mean_fully_rated_bundle_precision"] is None for value in report["methods"].values())
print("offline-boundary-ok")
'''
    result = subprocess.run([sys.executable, "-c", script, str(ROOT), str(tmp_path / "demo")],
                            cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "offline-boundary-ok"
