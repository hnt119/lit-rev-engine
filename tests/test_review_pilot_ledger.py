"""Pilot bindings exercise existing ledger behavior using invented local data."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest

from src.review.pilot import PilotConflict, PilotLedger
from src.review.store import ReviewStore
from src.search.pubmed_search import capture_pubmed_search, validate_pubmed_artifacts


def initialize(pilot, *, workspace="workspace", purpose="software_usability"):
    return pilot.initialize(workspace, {"request_id": str(uuid4()), "title": "Disclosed software usability", "question": "Can existing review records retain their provenance?", "review_type": "systematic", "purpose": purpose,
        "protocol": {"reference": "software-test-v1", "eligibility": {}, "reviewer_roles": {"sole_reviewer": "not yet performed"}, "unresolved": ["Owner eligibility and appraisal choices"], "ready_for_screening": False}})


def request(view, **extra):
    return {"request_id": str(uuid4()), "expected_protocol_id": view["current_protocol"]["id"], "expected_ledger_digest": view["ledger_digest"], "reviewer": "SCRIPTED SOFTWARE QA — not human review", "reason": "Exercise explicit software behavior only", **extra}


def imported(pilot, view, *, count=2, workspace="workspace"):
    data = [{"title": f"Invented software record {i}", "pmid": str(999970000+i), "abstract": f"Invented abstract {i}; no clinical findings."} for i in range(count)]
    content = ("  " + json.dumps(data, indent=3) + "\n").encode()
    payload = request(view, format="json", source="Invented test export", scope="supplied_file", reported_count=count)
    return pilot.import_file(workspace, content, "supplied.json", payload), content, payload


def source(pilot, view, index=0, *, kind="abstract", workspace="workspace"):
    record = view["records"][index]
    content = record["abstract"].encode() if kind == "abstract" else b"Invented complete supplied text, not a medical study."
    return pilot.attach_source(workspace, content, "source.txt", request(view, record_id=record["id"], format="txt", source_kind=kind, license="Software fixture only", attribution="Invented test source", permission_note="Invented source created for this test"))


def binding(view):
    d = view["sources"][-1]
    return {k:d[k] for k in ("record_id", "source_sha256", "blocks_sha256", "source_kind")} | {"document_id": d["id"]}


def handoff_ready(pilot, view):
    return pilot.record_decision("workspace", request(view, record_id=view["sources"][-1]["record_id"], stage="title_abstract", decision="include"))


def test_protocol_versions_retry_readiness_and_unknowns_survive_reopen(tmp_path):
    path = tmp_path/"isolated.sqlite3"
    with ReviewStore(path) as store:
        pilot = PilotLedger(store); view = initialize(pilot)
        initial = view["current_protocol"]
        payload = request(view, content={"reference": "owner-supplied-v2", "eligibility": {"design": "owner declared"}, "reviewer_roles": {"sole": "declared"}, "fields": [], "unresolved": [], "ready_for_screening": True})
        revised = pilot.revise_protocol("workspace", payload)
        assert revised["current_protocol"]["number"] == 2
        assert revised["protocols"][0] == initial
        assert pilot.revise_protocol("workspace", payload)["result"] == revised["result"]
        with pytest.raises(PilotConflict, match="protocol changed"):
            pilot.revise_protocol("workspace", request(view, content=payload["content"]))
        with pytest.raises(PilotConflict, match="different content"):
            pilot.revise_protocol("workspace", {**payload, "reason": "changed retry"})
    with ReviewStore(path) as store:
        reopened = PilotLedger(store).view("workspace")
        assert reopened["current_protocol"]["number"] == 2
        assert reopened["protocols"][0]["content"]["unresolved"] == ["Owner eligibility and appraisal choices"]


def test_intake_exact_bytes_dedup_complete_input_not_complete_query_and_large_library(tmp_path):
    with ReviewStore(tmp_path/"new.sqlite3") as store:
        pilot = PilotLedger(store); view = initialize(pilot)
        view, content, payload = imported(pilot, view, count=45)
        assert view["total_records"] == 45 and view["counts"]["unique_records"] == 45
        repeated = pilot.import_file("workspace", content, "supplied.json", payload)
        assert repeated["result"] == view["result"] and len(repeated["intakes"]) == 1
        view = pilot.import_file("workspace", content, "supplied.json", request(view, format="json", source="Invented duplicate export", scope="exploratory_subset", reported_count=60))
        assert view["counts"]["records_identified"] == 90
        assert view["counts"]["duplicate_records_removed"] == 45
        assert view["counts"]["all_checks_passed"] and len(view["occurrences"]) == 90
        assert len(pilot.view("workspace", offset=40, limit=20)["records"]) == 5
        with pytest.raises(ValueError, match="cannot declare"):
            pilot.import_file("workspace", content, "supplied.json", request(view, format="json", scope="complete_query_capture"))
        exported = pilot.export("workspace", tmp_path/"export")
        for intake in view["intakes"]:
            assert (tmp_path/"export"/"pilot"/"intakes"/intake["id"]/"supplied.json").read_bytes() == content
        assert len(exported["pilot"]["intakes"]) == 2
        assert "execution" not in view["search_runs"][0] or view["search_runs"][0]["execution"] is None


def test_all_new_decisions_require_reasons_and_bind_exact_protocol(tmp_path):
    with ReviewStore(tmp_path/"new.sqlite3") as store:
        pilot = PilotLedger(store); view, _, _ = imported(pilot, initialize(pilot))
        payload = request(view, record_id=view["records"][0]["id"], stage="title_abstract", decision="include")
        with pytest.raises(ValueError, match="reason"):
            pilot.record_decision("workspace", {**payload, "reason": ""})
        view = pilot.record_decision("workspace", payload)
        assert len(view["decisions"]) == 1
        assert view["event_bindings"][0]["event_id"] == view["decisions"][0]["id"]
        assert view["event_bindings"][0]["protocol_id"] == view["current_protocol"]["id"]
        view = pilot.record_decision("workspace", request(view, record_id=view["records"][0]["id"], stage="title_abstract", decision="uncertain"))
        assert len(view["decisions"]) == 2 and view["records"][0]["title_abstract_state"] == "uncertain"


def test_unknown_real_protocol_blocks_research_screening(tmp_path):
    with ReviewStore(tmp_path/"new.sqlite3") as store:
        pilot = PilotLedger(store); view, _, _ = imported(pilot, initialize(pilot, purpose="research_pilot"))
        with pytest.raises(ValueError, match="blocked"):
            pilot.record_decision("workspace", request(view, record_id=view["records"][0]["id"], stage="title_abstract", decision="include"))
        assert pilot.view("workspace")["decisions"] == []
        with pytest.raises(ValueError, match="Ready protocol"):
            pilot.revise_protocol("workspace", request(view, content={"ready_for_screening": True, "unresolved": []}))


def test_two_connections_and_legacy_writes_invalidate_cas(tmp_path):
    path = tmp_path/"new.sqlite3"
    with ReviewStore(path) as first, ReviewStore(path) as second:
        pilot = PilotLedger(first); other = PilotLedger(second)
        view, _, _ = imported(pilot, initialize(pilot))
        stale = request(view, record_id=view["records"][0]["id"], stage="title_abstract", decision="include")
        second.record_decision(view["project"]["id"], view["records"][1]["id"], "title_abstract", "uncertain", "Legacy declared label", "Requires owner review")
        with pytest.raises(PilotConflict, match="history changed"):
            pilot.record_decision("workspace", stale)
        assert len(other.view("workspace")["decisions"]) == 1


def test_event_binding_failure_rolls_back_authoritative_event(tmp_path, monkeypatch):
    with ReviewStore(tmp_path/"new.sqlite3") as store:
        pilot = PilotLedger(store); view, _, _ = imported(pilot, initialize(pilot))
        def fail(*args): raise RuntimeError("Injected metadata write failure")
        monkeypatch.setattr(pilot, "_bind_event", fail)
        with pytest.raises(RuntimeError):
            pilot.record_decision("workspace", request(view, record_id=view["records"][0]["id"], stage="title_abstract", decision="include"))
        assert store.list_decisions(view["project"]["id"]) == []
        assert pilot.view("workspace")["ledger_digest"] == view["ledger_digest"]


def test_source_attachment_failure_rolls_back_original_document(tmp_path, monkeypatch):
    with ReviewStore(tmp_path/"new.sqlite3") as store:
        pilot = PilotLedger(store); view, _, _ = imported(pilot, initialize(pilot))
        def fail(*args): raise RuntimeError("Injected metadata write failure")
        monkeypatch.setattr(pilot, "_bind_event", fail)
        with pytest.raises(RuntimeError): source(pilot, view)
        assert store.list_documents(view["project"]["id"]) == []
        assert pilot.view("workspace")["sources"] == []


def test_abstract_only_is_exact_and_never_retrieved_full_text(tmp_path):
    with ReviewStore(tmp_path/"new.sqlite3") as store:
        pilot = PilotLedger(store); view, _, _ = imported(pilot, initialize(pilot))
        view = pilot.record_decision("workspace", request(view, record_id=view["records"][0]["id"], stage="title_abstract", decision="include"))
        view = source(pilot, view)
        with pytest.raises(ValueError, match="abstract-only"):
            pilot.set_status("workspace", request(view, record_id=view["records"][0]["id"], status="retrieved"))
        with pytest.raises(ValueError, match="current attached full-text"):
            pilot.record_decision("workspace", request(view, record_id=view["records"][0]["id"], stage="full_text", decision="include"))
        wrong = request(view, record_id=view["records"][1]["id"], format="txt", source_kind="abstract", license="Fixture", attribution="Fixture", permission_note="Fixture")
        with pytest.raises(ValueError, match="exactly match"):
            pilot.attach_source("workspace", view["records"][0]["abstract"].encode(), "wrong.txt", wrong)
        inspected = pilot.source("workspace", view["sources"][0]["id"])
        assert inspected["content"] == view["records"][0]["abstract"].encode()


def test_full_text_attachment_status_screening_are_three_explicit_actions(tmp_path):
    with ReviewStore(tmp_path/"new.sqlite3") as store:
        pilot = PilotLedger(store); view, _, _ = imported(pilot, initialize(pilot))
        rid = view["records"][0]["id"]
        view = pilot.record_decision("workspace", request(view, record_id=rid, stage="title_abstract", decision="include"))
        view = source(pilot, view, kind="full_text")
        assert view["records"][0]["full_text_status"] == "not_requested"
        view = pilot.set_status("workspace", request(view, record_id=rid, status="retrieved"))
        assert view["records"][0]["full_text_state"] == "pending"
        view = pilot.record_decision("workspace", request(view, record_id=rid, stage="full_text", decision="include"))
        assert view["counts"]["reports_included"] == 1
        assert view["counts"]["included_studies"] is None


def test_handoff_navigation_never_changes_screening_and_rejects_wrong_paper(tmp_path):
    with ReviewStore(tmp_path/"new.sqlite3") as store:
        pilot = PilotLedger(store); view, _, _ = imported(pilot, initialize(pilot)); view = source(pilot, view); view = handoff_ready(pilot, view)
        b = binding(view); bad = {**b, "record_id": view["records"][1]["id"]}
        with pytest.raises(ValueError, match="identity"):
            pilot.record_handoff("workspace", request(view, receipt={"bindings": [bad], "acknowledge_provisional": True}))
        view = pilot.record_handoff("workspace", request(view, receipt={"bindings": [b], "board_id": "existing-board", "acknowledge_provisional": True}))
        assert view["counts"]["records_awaiting_screening"] == 1 and len(view["decisions"]) == 1
        assert len(view["handoffs"]) == 1


def test_publish_failure_retains_partial_ids_and_retry_is_explicit_idempotent(tmp_path):
    with ReviewStore(tmp_path/"new.sqlite3") as store:
        pilot = PilotLedger(store); view, _, _ = imported(pilot, initialize(pilot)); view = source(pilot, view); view = handoff_ready(pilot, view)
        payload = request(view, receipt={"bindings": [binding(view)], "acknowledge_provisional": True})
        calls=[]
        def failure(progress):
            calls.append("failure"); progress("collection", {"collection_id": "partial-public-collection"})
            raise RuntimeError("secret must not appear in journal")
        with pytest.raises(RuntimeError): pilot.publish_handoff("workspace", payload, failure)
        failed = pilot.view("workspace")
        assert not failed["handoffs"] and failed["ledger_digest"] == view["ledger_digest"]
        operation = failed["handoff_operations"][0]
        assert operation["status"] == "failed" and operation["partial_ids"] == {"collection_id": "partial-public-collection"}
        assert operation["error_code"] == "RuntimeError" and "secret must not appear" not in json.dumps(operation)
        def success(progress):
            calls.append("success"); progress("board", {"board_id": "existing-board"})
            return {**payload["receipt"], "board_id": "existing-board"}
        completed = pilot.publish_handoff("workspace", payload, success)
        assert completed["handoff_operations"][0]["status"] == "completed"
        assert len(completed["handoffs"]) == 1
        assert pilot.publish_handoff("workspace", payload, success)["result"] == completed["result"]
        assert calls == ["failure", "success"]


def test_stale_source_prevents_callback_and_cross_workspace_rejected(tmp_path):
    with ReviewStore(tmp_path/"new.sqlite3") as store:
        pilot = PilotLedger(store); view, _, _ = imported(pilot, initialize(pilot)); view = source(pilot, view); view = handoff_ready(pilot, view)
        old = binding(view); view = source(pilot, view)
        called=[]
        with pytest.raises(PilotConflict, match="superseded"):
            pilot.publish_handoff("workspace", request(view, receipt={"bindings": [old], "acknowledge_provisional": True}), lambda progress: called.append(True))
        assert not called and pilot.view("workspace")["handoff_operations"] == []
        other = initialize(pilot, workspace="other")
        with pytest.raises(ValueError, match="Unknown source"):
            pilot.source("other", old["document_id"])


def test_capture_retains_verified_exact_membership_and_replay_after_input_deleted(tmp_path):
    fixture = Path(__file__).parent/"fixtures/pubmed"
    manifest = json.loads((fixture/"manifest.json").read_text())
    class Client:
        def __init__(self): self.index = 0
        def request(self, endpoint, params):
            if endpoint == "esearch.fcgi": return (fixture/manifest["search_file"]).read_bytes()
            batch = manifest["batches"][self.index]; self.index += 1
            assert params["id"] == ",".join(batch["requested_pmids"])
            return (fixture/batch["response_file"]).read_bytes()
    capture = capture_pubmed_search(manifest["query"], tmp_path/"capture", client=Client(), sort=manifest["sort"], filters=manifest["filters"], batch_size=manifest["batch_size"])
    base = Path(capture["directory"])
    artifacts={str(p.relative_to(base)):p.read_bytes() for p in base.rglob('*') if p.is_file()}
    with ReviewStore(tmp_path/"new.sqlite3") as store:
        pilot = PilotLedger(store); view = initialize(pilot)
        view = pilot.import_capture("workspace", artifacts, request(view))
        assert view["counts"]["unique_records"] == 5
        assert view["search_runs"][0]["execution"]["complete"] is True
        assert view["intakes"][0]["scope"] == "complete_saved_capture"
        for p in base.rglob('*'):
            if p.is_file(): p.unlink()
        exported = pilot.export("workspace", tmp_path/"export")
        intake_dir=tmp_path/"export/pilot/intakes"/view["intakes"][0]["id"]
        replay={str(p.relative_to(intake_dir)):p.read_bytes() for p in intake_dir.rglob('*') if p.is_file()}
        assert validate_pubmed_artifacts(replay)["receipt"] == capture["receipt"]
        snapshot={name:(tmp_path/"export"/name).read_bytes() for name in exported["files"]}
        pilot.export("workspace", tmp_path/"again")
        assert snapshot == {name:(tmp_path/"again"/name).read_bytes() for name in exported["files"]}
        corrupted = dict(artifacts); corrupted["records.xml"] += b"changed"
        with pytest.raises(ValueError): pilot.import_capture("workspace", corrupted, request(view))


def test_retained_input_hash_corruption_blocks_export(tmp_path):
    with ReviewStore(tmp_path/"new.sqlite3") as store:
        pilot = PilotLedger(store); view, _, _ = imported(pilot, initialize(pilot))
        with store._connection: store._connection.execute("UPDATE pilot_intake_assets SET content=?", (b"changed",))
        with pytest.raises(ValueError, match="corrupt"): pilot.export("workspace", tmp_path/"export")
        assert not (tmp_path/"export").exists()


def test_upstream_sampling_metadata_is_retained_and_bound_to_request(tmp_path):
    with ReviewStore(tmp_path/"new.sqlite3") as store:
        pilot = PilotLedger(store); view = initialize(pilot)
        content=b'[{"title":"Invented sample record","pmid":"999970001"}]'
        assets={"upstream/manifest.json":b'{"sample":1,"total_reported":194}', "upstream/metadata.json":b'{"original":"bytes retained unchanged"}'}
        payload=request(view,format="json",scope="exploratory_subset",source="Invented bounded upstream capture")
        view=pilot.import_file("workspace",content,"derived.json",payload,extra_assets=assets)
        assert len(view["intakes"][0]["assets"]) == 3
        assert view["request_audit"][0]["result"]["pilot_reason"] == payload["reason"]
        with pytest.raises(PilotConflict,match="different content"):
            pilot.import_file("workspace",content,"derived.json",payload,extra_assets={**assets,"upstream/metadata.json":b'changed'})
        exported=pilot.export("workspace",tmp_path/"export")
        base=tmp_path/"export/pilot/intakes"/view["intakes"][0]["id"]
        assert (base/"derived.json").read_bytes()==content
        assert {name:(base/name).read_bytes() for name in assets}==assets
        assert exported["pilot"]["request_audit"][0]["result"]["pilot_actor"]==payload["reviewer"]


@pytest.mark.parametrize("name",["../private.json","/absolute.json","upstream/../private.json","upstream//double.json","derived.json","bad\\name.json"])
def test_extra_artifacts_never_escape_intake(tmp_path,name):
    with ReviewStore(tmp_path/"new.sqlite3") as store:
        pilot=PilotLedger(store);view=initialize(pilot)
        with pytest.raises(ValueError,match="unsafe"):
            pilot.import_file("workspace",b'[]',"derived.json",request(view,format="json"),extra_assets={name:b'x'})
        assert pilot.view("workspace")["intakes"]==[]


def test_protocol_revision_requires_rereview_without_rewriting_counts_or_history(tmp_path):
    with ReviewStore(tmp_path/"new.sqlite3") as store:
        pilot=PilotLedger(store);view,_,_=imported(pilot,initialize(pilot))
        rid=view["records"][0]["id"]
        view=pilot.record_decision("workspace",request(view,record_id=rid,stage="title_abstract",decision="include"))
        view=source(pilot,view,kind="full_text")
        view=pilot.set_status("workspace",request(view,record_id=rid,status="retrieved"))
        view=pilot.record_decision("workspace",request(view,record_id=rid,stage="full_text",decision="include"))
        old_binding=binding(view);old_counts=view["counts"];old_decisions=view["decisions"]
        assert view["protocol_alignment"]["current_included_report_ids"]==[rid]
        view=pilot.revise_protocol("workspace",request(view,content={"reference":"owner-draft-v2","eligibility":{},"reviewer_roles":{},"unresolved":["Still unresolved"],"ready_for_screening":False}))
        assert view["counts"]==old_counts and view["decisions"]==old_decisions
        assert view["protocol_alignment"]["record_ids_needing_review"]==[rid]
        assert view["protocol_alignment"]["current_included_report_ids"]==[]
        called=[]
        with pytest.raises(PilotConflict,match="re-review"):
            pilot.publish_handoff("workspace",request(view,receipt={"bindings":[old_binding]}),lambda progress:called.append(True))
        assert called==[]
        view=pilot.record_decision("workspace",request(view,record_id=rid,stage="title_abstract",decision="include"))
        assert view["protocol_alignment"]["record_ids_needing_review"]==[rid]
        view=pilot.record_decision("workspace",request(view,record_id=rid,stage="full_text",decision="uncertain"))
        assert view["protocol_alignment"]["record_ids_needing_review"]==[]
        with pytest.raises(ValueError,match="provisional"):
            pilot.record_handoff("workspace",request(view,receipt={"bindings":[old_binding]}))
        view=pilot.record_handoff("workspace",request(view,receipt={"bindings":[old_binding],"acknowledge_provisional":True}))
        assert view["counts"]["reports_included"]==0 and view["counts"]["reports_assessment_unresolved"]==1
        assert len(view["decisions"])==4 and len(view["handoffs"])==1
