"""Independent protocol-pilot checks using fresh public/synthetic state only.

No model, provider request or original research database is used. Scripted
reviewer labels/actions are software fixtures, never independent human review.
"""
from copy import deepcopy
import base64
import hashlib
import io
import json
from pathlib import Path
import socket
from uuid import uuid4
import zipfile

from fastapi.testclient import TestClient
import pytest

from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.store import ReviewStore
from src.search.pubmed_search import capture_pubmed_search
from src.web_api.app import COOKIE_NAME, create_app
from tools.evaluate_review_pilot import audit_bundle, audit_entries, independent_counts


BASE = "http://127.0.0.1:8765"
ORIGIN = "http://127.0.0.1:3000"
P = "/api/v1"
QA_LABEL = "Software QA scripted label — not a human reviewer"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "pubmed"
PUBLIC_ROOT = Path(__file__).resolve().parents[2] / "examples" / "mvp" / "offline_microbiome_30_v1"


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Pilot evaluation attempted external network access")
    monkeypatch.setattr(socket, "create_connection", denied)
    for key in ("MVP_MAP_ENABLED", "MVP_PROPOSALS_ENABLED", "MVP_SEARCH_PLANNER_ENABLED"):
        monkeypatch.setenv(key, "0")


def project_export(store, project, destination):
    result = store.export_project(project, destination)
    return json.loads((Path(result["directory"]) / "project.json").read_text())


def test_independent_count_oracle_covers_all_unresolved_partitions_and_study_distinction(tmp_path):
    """The evaluator checks ordered original events, not projected states alone."""
    with ReviewStore(tmp_path / "fresh-review.sqlite3") as store:
        project = store.create_project("Software-only arithmetic fixture", "systematic", "Synthetic question")["id"]
        records = [BibliographicRecord(title=f"Synthetic report {index}", pmid=str(970001 + index)) for index in range(40)]
        store.import_records(project, SearchRunSpec("Synthetic supplied library"), records + records[:5])
        ids = [record["id"] for record in store.list_records(project)]
        for index in range(7):
            store.record_decision(project, ids[index], "title_abstract", "include", QA_LABEL, "Scripted state coverage")
        for index in range(4):
            store.set_full_text_status(project, ids[index], "retrieved", QA_LABEL, "Scripted retrieved declaration")
        for index, decision in enumerate(("include", "exclude", "uncertain")):
            store.record_decision(project, ids[index], "full_text", decision, QA_LABEL, "Scripted branch; no real eligibility finding")
        store.set_full_text_status(project, ids[4], "not_retrieved", QA_LABEL, "Scripted unavailable-source case")
        store.set_full_text_status(project, ids[5], "requested", QA_LABEL, "Scripted pending-source case")
        store.record_decision(project, ids[7], "title_abstract", "uncertain", QA_LABEL, "Scripted unresolved criteria")
        store.record_decision(project, ids[8], "title_abstract", "exclude", QA_LABEL, "Scripted exclusion branch")
        store.record_decision(project, ids[9], "title_abstract", "include", QA_LABEL, "Scripted conflict branch")
        store.record_decision(project, ids[9], "title_abstract", "exclude", "Second scripted label, same evaluator", "Not independent human review")
        bundle = project_export(store, project, tmp_path / "first-export")
        report = audit_bundle(bundle)
        counts = report["counts_independently_recomputed"]
        assert (counts["records_identified"], counts["unique_records"], counts["duplicate_records_removed"]) == (45, 40, 5)
        assert counts["records_awaiting_screening"] == 30
        assert counts["records_screening_unresolved"] == 2
        assert counts["reports_assessment_unresolved"] == 1
        assert counts["reports_included"] == 1 and counts["included_studies"] is None
        study = store.create_study(project, "Software study identity", QA_LABEL, "Explicit manual fixture association")
        still_unknown = project_export(store, project, tmp_path / "second-export")
        assert independent_counts(still_unknown)["included_studies"] is None
        store.record_study_links(project, ids[0], [study["id"]], QA_LABEL, "Explicit association; report IDs are not study IDs")
        linked = project_export(store, project, tmp_path / "third-export")
        assert audit_bundle(linked)["counts_independently_recomputed"]["included_studies"] == 1
        changed = deepcopy(linked)
        changed["counts"]["reports_included"] = 2
        with pytest.raises(AssertionError, match="Export count mismatch"):
            audit_bundle(changed)
        changed = deepcopy(linked)
        changed["records"][0]["title_abstract_state"] = "exclude"
        with pytest.raises(AssertionError, match="projection contradicts events"):
            audit_bundle(changed)


class PilotCase:
    def __init__(self, directory):
        self.directory = directory
        self.app = create_app(directory)
        self.client = TestClient(self.app, base_url=BASE)
        session = self.client.get(P + "/session").json()
        self.client.headers.update({"Origin": ORIGIN, "X-CSRF-Token": session["csrf_token"]})
        response = self.client.post(P + "/workspaces", json={"request_id": "new-isolated-pilot", "mode": "saved_example", "question": "Software usability sample only"})
        assert response.status_code == 200, response.text
        self.workspace = response.json()
        self.root = P + "/workspaces/" + self.workspace["id"]
        self.pilot = self.root + "/review-pilot"

    def initialize(self, *, purpose="software_usability"):
        response = self.client.post(self.pilot, json={
            "request_id": "pilot-init", "title": "Disclosed software-only protocol pilot",
            "question": "How does the retained-source workflow behave?", "review_type": "systematic",
            "purpose": purpose, "reviewer": QA_LABEL,
            "reason": "Synthetic actions only; actual sole-reviewer session not performed",
            "protocol": {"label": "software-v1", "reference": "Not registered; software QA only",
                         "content": "No scientific eligibility rules are approved by this fixture.",
                         "unresolved": ["Age limits", "Mixed populations", "Study designs", "Appraisal"],
                         "ready_for_screening": False}})
        assert response.status_code == 200, response.text
        return response.json()

    def view(self, **params):
        response = self.client.get(self.pilot, params=params)
        assert response.status_code == 200, response.text
        return response.json()

    def mutation(self, suffix, body, *, expected=200, request_id=None, state=None):
        state = state or self.view()
        payload = {"request_id": request_id or str(uuid4()),
                   "expected_protocol_id": state["current_protocol"]["id"],
                   "expected_ledger_digest": state["ledger_digest"],
                   "reviewer": QA_LABEL, "reason": "Scripted software evaluation; not a real screening judgment", **body}
        result = self.client.post(self.pilot + suffix, json=payload)
        assert result.status_code == expected, result.text
        return result


@pytest.fixture
def pilot(tmp_path):
    return PilotCase(tmp_path)


def _capture(tmp_path):
    oracle = json.loads((FIXTURE_ROOT / "manifest.json").read_text())
    responses = [(FIXTURE_ROOT / oracle["search_file"]).read_bytes()]
    responses += [(FIXTURE_ROOT / batch["response_file"]).read_bytes() for batch in oracle["batches"]]

    class OfflineClient:
        def request(self, endpoint, params):
            assert endpoint in {"esearch.fcgi", "efetch.fcgi"}
            return responses.pop(0)

    capture = capture_pubmed_search(oracle["query"], tmp_path / "synthetic-capture", client=OfflineClient(),
                                    filters=oracle["filters"], sort=oracle["sort"], batch_size=2)
    return {path.relative_to(capture["directory"]).as_posix(): base64.b64encode(path.read_bytes()).decode()
            for path in Path(capture["directory"]).rglob("*") if path.is_file()}


def _zip_entries(response):
    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        assert all(not name.startswith("/") and ".." not in Path(name).parts for name in names)
        return {name: archive.read(name) for name in names}


def _ledger(entries):
    paths = [name for name in entries if name == "project.json" or name.endswith("/project.json")]
    assert len(paths) == 1
    return json.loads(entries[paths[0]])


def _file_payload(count=40):
    records = [{"title": f"Synthetic library report {index}", "pmid": str(960001 + index),
                "abstract": f"Synthetic abstract {index}; no clinical findings."} for index in range(count)]
    raw = "  \n" + json.dumps(records + records[:2], ensure_ascii=False, indent=1) + "\n  "
    return {"filename": "synthetic-intake.json", "content_utf8": raw, "format": "json",
            "source": "Synthetic supplied export; no live provider", "query": "NOT A LIVE SEARCH",
            "searched_at": None, "filters": {}, "reported_count": 100,
            "scope": "exploratory_subset"}


def test_owned_pilot_initialization_and_all_writes_keep_existing_security(pilot):
    c = pilot
    unavailable = c.view()
    assert unavailable["available"] is False
    assert c.view() == unavailable
    initialized = c.initialize()
    assert c.view()["available"] is True
    assert c.view()["purpose"] == "software_usability"
    before = c.view()
    stranger = TestClient(c.app, base_url=BASE)
    csrf = stranger.get(P + "/session").json()["csrf_token"]
    stranger.headers.update({"Origin": ORIGIN, "X-CSRF-Token": csrf})
    for suffix in ("", "/exports", "/sources/unknown"):
        assert stranger.get(c.pilot + suffix).status_code == 404
    for suffix in ("", "/protocols", "/intakes/public-example", "/intakes/file", "/decisions", "/retrieval-status", "/sources", "/handoffs"):
        result = stranger.post(c.pilot + suffix, json={})
        assert result.status_code in {404, 422}, result.text
        # A valid ownership-bearing payload cannot use a workspace UUID as access.
        if suffix == "":
            assert stranger.post(c.pilot, json={"request_id": "intruder", "title": "Other", "question": "Other"}).status_code == 404
    c.client.headers.pop("X-CSRF-Token")
    assert c.client.post(c.pilot + "/intakes/public-example", json={}).status_code == 403
    assert c.view() == before


def test_protocol_history_cas_and_exact_retry_do_not_overwrite_unresolved_choices(pilot):
    c = pilot
    c.initialize()
    first = c.view()
    content = {**first["current_protocol"]["content"], "label": "software-v2",
               "unresolved": ["Age limits", "Study designs", "Actual reviewer availability"], "ready_for_screening": False}
    body = {"request_id": "protocol-retry", "expected_protocol_id": first["current_protocol"]["id"],
            "expected_ledger_digest": first["ledger_digest"], "reviewer": QA_LABEL,
            "reason": "Explicit software protocol revision, unknown choices retained", "content": content}
    response = c.client.post(c.pilot + "/protocols", json=body)
    assert response.status_code == 200, response.text
    assert c.client.post(c.pilot + "/protocols", json=body).json() == response.json()
    assert c.client.post(c.pilot + "/protocols", json={**body, "request_id": "stale", "content": {**content, "label": "stale-overwrite"}}).status_code == 409
    after = c.view()
    assert len(after["protocols"]) == 2
    assert after["protocols"][0] == first["current_protocol"]
    assert after["current_protocol"]["id"] != first["current_protocol"]["id"]
    assert after["current_protocol"]["content"]["unresolved"] == content["unresolved"]


def test_library_over_thirty_preserves_original_input_occurrences_and_export_after_reopen(pilot):
    c = pilot
    c.initialize()
    payload = _file_payload()
    response = c.mutation("/intakes/file", payload, request_id="forty-records")
    before = c.view()
    assert before["total_records"] == 40
    assert len(c.view(limit=50)["records"]) == 40
    assert len(c.view(offset=30, limit=10)["records"]) == 10
    assert before["counts"]["records_identified"] == 42
    assert before["counts"]["duplicate_records_removed"] == 2
    assert not before["decisions"] and not before["retrieval_events"] and not before["handoffs"]
    archive = _zip_entries(c.client.get(c.pilot + "/exports"))
    assert any(content == payload["content_utf8"].encode() for name, content in archive.items() if "/intakes/" in name)
    report = audit_bundle(_ledger(archive))
    assert report["counts_independently_recomputed"]["unique_records"] == 40
    invalid = {**payload, "scope": "complete_query"}
    c.mutation("/intakes/file", invalid, expected=422)
    assert c.view() == before
    restarted = TestClient(create_app(c.directory), base_url=BASE)
    restarted.cookies.set(COOKIE_NAME, c.client.cookies.get(COOKIE_NAME))
    restarted.get(P + "/session").raise_for_status()
    again = _zip_entries(restarted.get(c.pilot + "/exports"))
    assert archive == again


def test_complete_capture_is_verified_and_partial_or_changed_membership_rolls_back(pilot, tmp_path):
    c = pilot
    c.initialize()
    artifacts = _capture(tmp_path)
    response = c.mutation("/intakes/pubmed-capture", {"artifacts": artifacts})
    before = c.view()
    assert before["counts"]["unique_records"] == 5
    assert before["search_runs"][0]["execution"]["complete"] is True
    assert before["search_runs"][0]["execution"]["fetched_count"] == 5
    assert before["search_runs"][0]["execution"]["reported_count"] == 5
    partial = {name: content for name, content in artifacts.items() if name != "batches/0001.xml"}
    c.mutation("/intakes/pubmed-capture", {"artifacts": partial}, expected=422)
    changed = dict(artifacts)
    changed["records.xml"] = base64.b64encode(b"<PubmedArticleSet />").decode()
    c.mutation("/intakes/pubmed-capture", {"artifacts": changed}, expected=422)
    assert c.view() == before
    # Remove only this fixture's own original directory, after validating retention.
    import shutil
    shutil.rmtree(tmp_path / "synthetic-capture")
    entries = _zip_entries(c.client.get(c.pilot + "/exports"))
    assert all(any(name.endswith("/" + filename) and value == base64.b64decode(encoded)
                   for name, value in entries.items()) for filename, encoded in artifacts.items())
    assert audit_bundle(_ledger(entries))["status"] == "PASS"


def test_screening_reasons_history_status_prerequisites_and_stale_submission(pilot):
    c = pilot
    c.initialize()
    c.mutation("/intakes/public-example", {})
    record_id = c.view()["records"][0]["id"]
    body = {"record_id": record_id, "stage": "title_abstract", "decision": "exclude", "reason": " "}
    c.mutation("/decisions", body, expected=422)
    c.mutation("/decisions", {"record_id": record_id, "stage": "full_text", "decision": "include"}, expected=422)
    old = c.view()
    c.mutation("/decisions", {"record_id": record_id, "stage": "title_abstract", "decision": "uncertain"})
    c.mutation("/decisions", {"record_id": record_id, "stage": "title_abstract", "decision": "include"}, state=old, expected=409)
    c.mutation("/protocols", {"content": {**old["current_protocol"]["content"], "label": "software-revised-after-original-event"}})
    c.mutation("/decisions", {"record_id": record_id, "stage": "title_abstract", "decision": "include"})
    c.mutation("/retrieval-status", {"record_id": record_id, "status": "requested"})
    c.mutation("/decisions", {"record_id": record_id, "stage": "title_abstract", "decision": "exclude"}, expected=422)
    c.mutation("/retrieval-status", {"record_id": record_id, "status": "retrieved"}, expected=422)
    c.mutation("/sources", {"record_id": record_id, "kind": "public_jats"})
    c.mutation("/retrieval-status", {"record_id": record_id, "status": "retrieved"})
    c.mutation("/retrieval-status", {"record_id": record_id, "status": "requested"}, expected=422)
    c.mutation("/decisions", {"record_id": record_id, "stage": "full_text", "decision": "uncertain"})
    view = c.view()
    assert [row["decision"] for row in view["decisions"]] == ["uncertain", "include", "uncertain"]
    assert view["counts"]["reports_assessment_unresolved"] == 1
    assert view["counts"]["included_studies"] is None
    bindings = [row for row in view["event_bindings"] if row["event_kind"] == "screening"]
    assert [row["event_id"] for row in bindings] == [row["id"] for row in view["decisions"]]
    assert bindings[0]["protocol_id"] == old["current_protocol"]["id"]
    assert all(row["protocol_id"] == view["current_protocol"]["id"] for row in bindings[1:])
    assert audit_bundle(_ledger(_zip_entries(c.client.get(c.pilot + "/exports"))))["status"] == "PASS"


def test_research_purpose_cannot_screen_while_protocol_choices_are_unresolved(pilot):
    c = pilot
    c.initialize(purpose="research_pilot")
    c.mutation("/intakes/file", _file_payload(3))
    before = c.view()
    record_id = before["records"][0]["id"]
    c.mutation("/decisions", {"record_id": record_id, "stage": "title_abstract", "decision": "include"}, expected=422)
    assert c.view() == before
    c.mutation("/protocols", {"content": {**before["current_protocol"]["content"], "ready_for_screening": True}}, expected=422)
    assert c.view()["current_protocol"]["content"]["ready_for_screening"] is False


def test_public_sample_handoff_keeps_eligibility_and_exact_source_inspection_distinct(pilot):
    c = pilot
    c.initialize()
    c.mutation("/intakes/public-example", {})
    initial = c.view()
    manifest = json.loads((PUBLIC_ROOT / "manifest.json").read_text())
    assert len(initial["records"]) == initial["total_records"] == 30
    assert [record["pmid"] for record in initial["records"]] == [source["pmid"] for source in manifest["sources"]]
    assert initial["intakes"][0]["scope"] == "exploratory_subset"
    assert not initial["search_runs"][0].get("execution")
    assert not initial["decisions"]
    ids = [row["id"] for row in initial["records"][:3]]
    for record_id in ids:
        c.mutation("/decisions", {"record_id": record_id, "stage": "title_abstract", "decision": "include"})
    for record_id in ids[:2]:
        c.mutation("/sources", {"record_id": record_id, "kind": "public_jats"})
        c.mutation("/retrieval-status", {"record_id": record_id, "status": "retrieved"})
    c.mutation("/decisions", {"record_id": ids[0], "stage": "full_text", "decision": "include"})
    c.mutation("/decisions", {"record_id": ids[1], "stage": "full_text", "decision": "uncertain"})
    attribution = manifest["sources"][2]
    c.mutation("/sources", {"record_id": ids[2], "kind": "abstract", "license": attribution["license"],
                            "attribution": attribution["attribution"], "permission_note": "Deliberate abstract-only software coverage; full text exists in approved public fixture"})
    c.mutation("/retrieval-status", {"record_id": ids[2], "status": "retrieved"}, expected=422)
    view = c.view()
    assert view["counts"]["reports_included"] == 1
    assert view["counts"]["included_studies"] is None
    sources = [next(source for source in view["sources"] if source["record_id"] == record_id and source["active"]) for record_id in ids]
    snapshot = c.client.get(c.root).json()
    handoff = {"sources": [{key: source[key] for key in ("record_id", "source_sha256")} | {"document_id": source["id"]} for source in sources],
               "question": "Software-only selected retained sources; no eligibility inference",
               "fields": [{"id": "population", "label": "Population", "subquestion": "women population"},
                          {"id": "diet", "label": "Diet", "subquestion": "diet food"}],
               "acknowledge_provisional": False, "expected_source_revision": snapshot["source_revision"],
               "expected_preparation_id": snapshot["current_preparation_id"]}
    c.mutation("/handoffs", handoff, expected=422)
    wrong = deepcopy(handoff)
    wrong["acknowledge_provisional"] = True
    wrong["sources"][0]["document_id"] = sources[1]["id"]
    c.mutation("/handoffs", wrong, expected=422)
    changed_hash = deepcopy(handoff)
    changed_hash["acknowledge_provisional"] = True
    changed_hash["sources"][0]["source_sha256"] = "0" * 64
    c.mutation("/handoffs", changed_hash, expected=409)
    assert c.client.get(c.root).json() == snapshot
    before = c.view()
    response = c.mutation("/handoffs", {**handoff, "acknowledge_provisional": True})
    completed_request = json.loads(response.request.content)
    receipt = response.json()["result"]["receipt"]
    after = c.view()
    assert after["counts"] == before["counts"]
    assert after["decisions"] == before["decisions"]
    assert after["retrieval_events"] == before["retrieval_events"]
    board = c.root + "/boards/" + receipt["board_id"]
    definition = c.client.get(board).json()["definition"]
    assert len(definition["paper_ids"]) == 3
    assert definition["preparation_id"] == receipt["preparation_id"]
    assert all(cell["head"] is None for cell in c.client.get(board).json()["cells"])
    for binding, source in zip(receipt["bindings"], sources):
        assert binding["record_id"] == source["record_id"]
        assert binding["document_id"] == source["id"]
        assert binding["source_sha256"] == source["source_sha256"]
        assert binding["blocks_sha256"] == source["blocks_sha256"]
        ledger_source = c.client.get(c.pilot + "/sources/" + source["id"], params={"limit": 3}).json()
        exact = c.client.get(board + "/sources/" + binding["comparison_source_id"] + "/blocks", params={"revision_id": receipt["revision_id"], "limit": 3})
        assert exact.status_code == 200, exact.text
        assert [block["text"] for block in exact.json()["blocks"]] == [block["text"] for block in ledger_source["blocks"]]
    exported = _zip_entries(c.client.get(c.pilot + "/exports"))
    assert audit_bundle(_ledger(exported))["counts_independently_recomputed"]["reports_included"] == 1
    assert audit_entries(exported)["integrity"]["source_bound_comparison_exports"] == 1
    corrupted = dict(exported)
    source_file = _ledger(exported)["document_artifacts"][0]["export_file"]
    corrupted[source_file] += b"tampered"
    with pytest.raises(AssertionError, match="Retained source digest mismatch"):
        audit_entries(corrupted)
    audit_path = next(name for name in exported if name.endswith("pilot/pilot.json"))
    audit = json.loads(exported[audit_path])
    assert len(audit["handoffs"]) == 1
    assert audit["purpose"] == "software_usability"
    # New eligibility never silently reinterprets prior decisions as current review.
    before_protocol = c.view()
    c.mutation("/protocols", {"content": {**before_protocol["current_protocol"]["content"],
                                         "eligibility": {"software_revision": "Changed fixture eligibility; not scientific criteria"}}})
    revised = c.view()
    assert revised["counts"] == before_protocol["counts"]
    assert revised["decisions"] == before_protocol["decisions"]
    alignment = revised["protocol_alignment"]
    assert set(ids) <= set(alignment["record_ids_needing_review"])
    assert alignment["current_included_report_ids"] == []
    assert alignment["warning"]
    current = c.client.get(c.root).json()
    current_handoff = {**handoff, "acknowledge_provisional": True,
                       "expected_source_revision": current["source_revision"],
                       "expected_preparation_id": current["current_preparation_id"]}
    c.mutation("/handoffs", current_handoff, expected=409)
    assert c.client.get(c.root).json() == current
    for record_id in ids:
        c.mutation("/decisions", {"record_id": record_id, "stage": "title_abstract", "decision": "include"})
    for record_id, decision in zip(ids[:2], ("include", "uncertain")):
        c.mutation("/decisions", {"record_id": record_id, "stage": "full_text", "decision": decision})
    reviewed = c.view()
    assert reviewed["protocol_alignment"]["record_ids_needing_review"] == []
    assert reviewed["protocol_alignment"]["current_included_report_ids"] == [ids[0]]
    assert reviewed["counts"] == before_protocol["counts"]
    c.mutation("/handoffs", current_handoff)
    # Session ownership still controls valid requests carrying exact known IDs.
    stranger = TestClient(c.app, base_url=BASE)
    csrf = stranger.get(P + "/session").json()["csrf_token"]
    stranger.headers.update({"Origin": ORIGIN, "X-CSRF-Token": csrf})
    owned_state = c.view()
    valid_mutation = {"request_id": "intruder-valid", "expected_protocol_id": owned_state["current_protocol"]["id"],
                      "expected_ledger_digest": owned_state["ledger_digest"], "reviewer": QA_LABEL, "reason": "No authorization"}
    assert stranger.post(c.pilot + "/decisions", json={**valid_mutation, "record_id": ids[0], "stage": "title_abstract", "decision": "include"}).status_code == 404
    assert stranger.post(c.pilot + "/sources", json={**valid_mutation, "record_id": ids[0], "kind": "public_jats"}).status_code == 404
    assert stranger.get(c.pilot + "/sources/" + sources[0]["id"]).status_code == 404
    assert stranger.get(board).status_code == 404
    # A later source attachment makes the old explicit document selection stale.
    c.mutation("/sources", {"record_id": ids[0], "kind": "public_jats"})
    current = c.client.get(c.root).json()
    stale = {**handoff, "acknowledge_provisional": True, "expected_source_revision": current["source_revision"],
             "expected_preparation_id": current["current_preparation_id"]}
    c.mutation("/handoffs", stale, expected=409)
    replayed = c.client.post(c.pilot + "/handoffs", json=completed_request)
    assert replayed.status_code == 200, replayed.text
    assert replayed.json()["result"] == response.json()["result"]
    assert c.client.post(c.pilot + "/handoffs", json={**completed_request, "question": "Changed external request under same ID"}).status_code == 409
    assert c.client.delete(c.root).status_code == 200
    assert c.client.get(c.pilot).status_code == 404


def test_partial_handoff_retry_reuses_existing_preparation_and_does_not_duplicate_board(pilot, monkeypatch):
    c = pilot
    c.initialize()
    c.mutation("/intakes/public-example", {})
    record = c.view()["records"][0]
    c.mutation("/decisions", {"record_id": record["id"], "stage": "title_abstract", "decision": "include"})
    c.mutation("/sources", {"record_id": record["id"], "kind": "public_jats"})
    state = c.view()
    source = state["sources"][0]
    snapshot = c.client.get(c.root).json()
    body = {"request_id": "recoverable-handoff", "expected_protocol_id": state["current_protocol"]["id"],
            "expected_ledger_digest": state["ledger_digest"], "reviewer": QA_LABEL, "reason": "Controlled software interruption",
            "sources": [{"record_id": record["id"], "document_id": source["id"], "source_sha256": source["source_sha256"]}],
            "question": "Software partial publication recovery", "fields": [{"id": "diet", "label": "Diet", "subquestion": "diet"}],
            "acknowledge_provisional": True, "expected_source_revision": snapshot["source_revision"],
            "expected_preparation_id": snapshot["current_preparation_id"]}
    original = c.app.state.boards._create_under_lifecycle_guard
    called = 0

    def fail_once(*args, **kwargs):
        nonlocal called
        called += 1
        if called == 1:
            raise ValueError("Injected software-only interruption after preparation")
        return original(*args, **kwargs)

    monkeypatch.setattr(c.app.state.boards, "_create_under_lifecycle_guard", fail_once)
    failed = c.client.post(c.pilot + "/handoffs", json=body)
    assert failed.status_code == 422, failed.text
    partial = c.view()
    assert partial["handoffs"] == []
    operation = partial["handoff_operations"][0]
    assert operation["status"] == "failed" and operation["phase"] == "preparation"
    preparation_id = operation["partial_ids"]["preparation_id"]
    prepared = c.client.get(c.root).json()
    assert prepared["current_preparation_id"] == preparation_id
    retried = c.client.post(c.pilot + "/handoffs", json=body)
    assert retried.status_code == 200, retried.text
    assert retried.json()["result"]["receipt"]["preparation_id"] == preparation_id
    assert len(c.view()["handoffs"]) == 1
    assert c.view()["handoff_operations"][0]["status"] == "completed"
    assert c.client.get(c.root).json()["source_revision"] == prepared["source_revision"]
    assert len(c.client.get(c.root + "/boards").json()["boards"]) == 1
    assert c.client.post(c.pilot + "/handoffs", json=body).json()["result"] == retried.json()["result"]
    assert called == 2
