#!/usr/bin/env python3
"""Independent mechanical audit of a disclosed protocol-pilot export.

This evaluator never searches providers, loads models, infers eligibility or
counts software QA actions as human review. It derives arithmetic from retained
occurrences and ordered event histories rather than calling ReviewStore.counts.
The exported bundle can contain private material: keep inputs/reports local.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import sys
import time
from unittest.mock import patch
from uuid import uuid4
import zipfile


def _active(events, kind_key="kind"):
    """Fold ordered original decisions, keeping each declared label's latest."""
    labels, adjudication, last_review = {}, None, -1
    for index, event in enumerate(events):
        if event.get(kind_key) == "adjudication":
            adjudication = index, event
        else:
            labels[event["reviewer"]] = event
            last_review = index
    if adjudication is not None and adjudication[0] > last_review:
        return [adjudication[1]]
    return list(labels.values())


def _stage(events, stage):
    active = _active([event for event in events if event["stage"] == stage])
    decisions = {event["decision"] for event in active}
    if not decisions:
        return "pending"
    return next(iter(decisions)) if len(decisions) == 1 else "conflict"


def independent_counts(bundle):
    """Reconstruct ledger partitions independently, including unresolved states."""
    records = bundle["records"]
    occurrences = bundle["occurrences"]
    decisions = bundle["decisions"]
    retrievals = bundle["retrieval_events"]
    ids = {record["id"] for record in records}
    assert len(ids) == len(records), "Duplicate canonical record IDs"
    assert all(row["record_id"] in ids for row in occurrences), "Orphan occurrence"
    assert all(row["record_id"] in ids for row in decisions), "Orphan screening event"
    assert all(row["record_id"] in ids for row in retrievals), "Orphan retrieval event"
    assert all(row["reason"].strip() for row in decisions
               if row["decision"] == "exclude" or row.get("kind") == "adjudication"), "Missing exclusion/adjudication reason"
    assert all(row["reason"].strip() for row in retrievals
               if row["status"] == "not_retrieved"), "Missing not-retrieved reason"
    counts = {key: 0 for key in (
        "records_awaiting_screening", "records_screened", "records_excluded",
        "records_included_for_full_text", "records_screening_unresolved",
        "reports_awaiting_request", "reports_sought_for_retrieval", "reports_retrieved",
        "reports_not_retrieved", "reports_awaiting_retrieval", "reports_awaiting_assessment",
        "reports_assessed", "reports_included", "reports_excluded", "reports_assessment_unresolved")}
    counts.update(records_identified=len(occurrences), unique_records=len(records),
                  duplicate_records_removed=len(occurrences)-len(records))
    included = set()
    for record in records:
        events = [event for event in decisions if event["record_id"] == record["id"]]
        ta, ft = _stage(events, "title_abstract"), _stage(events, "full_text")
        assert record["title_abstract_state"] == ta, "Stored screening projection contradicts events"
        assert record["full_text_state"] == ft, "Stored full-text projection contradicts events"
        statuses = [event["status"] for event in retrievals if event["record_id"] == record["id"]]
        status = statuses[-1] if statuses else "not_requested"
        assert record["full_text_status"] == status, "Stored retrieval projection contradicts events"
        if ta == "pending":
            counts["records_awaiting_screening"] += 1
            continue
        counts["records_screened"] += 1
        if ta == "exclude":
            counts["records_excluded"] += 1
            continue
        if ta != "include":
            counts["records_screening_unresolved"] += 1
            continue
        counts["records_included_for_full_text"] += 1
        if status == "not_requested":
            counts["reports_awaiting_request"] += 1
            continue
        counts["reports_sought_for_retrieval"] += 1
        if status == "requested":
            counts["reports_awaiting_retrieval"] += 1
            continue
        if status == "not_retrieved":
            counts["reports_not_retrieved"] += 1
            continue
        counts["reports_retrieved"] += 1
        if ft == "pending":
            counts["reports_awaiting_assessment"] += 1
            continue
        counts["reports_assessed"] += 1
        if ft == "include":
            counts["reports_included"] += 1
            included.add(record["id"])
        elif ft == "exclude":
            counts["reports_excluded"] += 1
        else:
            counts["reports_assessment_unresolved"] += 1
    if "studies" not in bundle:
        counts.update(included_studies=None, study_linkage_available=False)
    else:
        linked, awaiting, conflicting, study_ids = 0, 0, 0, set()
        events = bundle["study_link_events"]
        valid_studies = {study["id"] for study in bundle["studies"]}
        for record_id in included:
            active = _active([event for event in events if event["record_id"] == record_id])
            proposed = {tuple(sorted(event["study_ids"])) for event in active}
            if not proposed or proposed == {()}:
                awaiting += 1
            elif len(proposed) != 1:
                conflicting += 1
            else:
                targets = set(next(iter(proposed)))
                assert targets <= valid_studies, "Unknown linked study"
                linked += 1
                study_ids.update(targets)
        counts.update(study_linkage_available=True, reports_included_linked=linked,
                      reports_included_awaiting_linkage=awaiting,
                      reports_included_linkage_unresolved=conflicting,
                      linked_included_studies=len(study_ids),
                      study_linkage_complete=linked == len(included),
                      included_studies=len(study_ids) if linked == len(included) else None)
    return counts


def audit_bundle(bundle):
    expected = independent_counts(bundle)
    observed = bundle["counts"]
    discrepancies = {key: {"events": value, "export": observed.get(key)}
                     for key, value in expected.items() if value != observed.get(key)}
    assert not discrepancies, "Export count mismatch: " + json.dumps(discrepancies, sort_keys=True)
    assert observed["all_checks_passed"] is True
    assert all(observed["reconciliation"].values())
    return {"status": "PASS", "counts_independently_recomputed": expected,
            "occurrences": len(bundle["occurrences"]), "screening_events": len(bundle["decisions"]),
            "retrieval_events": len(bundle["retrieval_events"]), "count_discrepancies": {},
            "scientific_or_human_usefulness_validation": False,
            "reviewer_identity": "self-declared labels; no independent identity claim",
            "live_provider_calls": 0, "model_calls": 0}


def read_export(path):
    """Read JSON or locate the one existing ledger project.json inside a ZIP."""
    path = Path(path)
    if path.suffix.lower() != ".zip":
        return json.loads(path.read_text(encoding="utf-8"))
    with zipfile.ZipFile(path) as archive:
        candidates = [name for name in archive.namelist() if name == "project.json" or name.endswith("/project.json")]
        assert len(candidates) == 1, "Expected one authoritative ledger project.json"
        return json.loads(archive.read(candidates[0]))


def audit_entries(entries):
    """Audit count, protocol, source, intake and comparison links in one export."""
    paths = [name for name in entries if name == "project.json" or name.endswith("/project.json")]
    assert len(paths) == 1, "Expected one authoritative ledger project.json"
    bundle = json.loads(entries[paths[0]])
    report = audit_bundle(bundle)
    metadata = json.loads(entries["pilot/pilot.json"])
    protocols = metadata["protocols"]
    ids = {revision["id"] for revision in protocols}
    previous = None
    for number, revision in enumerate(protocols, 1):
        assert revision["number"] == number and revision["previous_id"] == previous, "Broken protocol history"
        raw = json.dumps(revision["content"], ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        assert hashlib.sha256(raw).hexdigest() == revision["sha256"], "Protocol content digest mismatch"
        previous = revision["id"]
    assert previous == metadata["current_protocol"]["id"]
    events = {"screening": {row["id"] for row in bundle["decisions"]},
              "retrieval_status": {row["id"] for row in bundle["retrieval_events"]},
              "source_attachment": {row["id"] for row in bundle.get("documents", [])}}
    bound = {kind: set() for kind in events}
    for binding in metadata["event_bindings"]:
        assert binding["protocol_id"] in ids, "Unknown protocol binding"
        kind = binding["event_kind"]
        assert kind in events and binding["event_id"] in events[kind], "Unknown bound event"
        assert binding["event_id"] not in bound[kind], "Duplicate event binding"
        bound[kind].add(binding["event_id"])
    assert bound == events, "Review/source events missing protocol bindings"
    intake_files = 0
    for intake in metadata["intakes"]:
        assert intake["protocol_id"] in ids
        for asset in intake["assets"]:
            content = entries[f"pilot/intakes/{intake['id']}/{asset['name']}"]
            assert len(content) == asset["size_bytes"]
            assert hashlib.sha256(content).hexdigest() == asset["sha256"], "Retained intake digest mismatch"
            intake_files += 1
    document_files = {row["document_id"]: row for row in bundle.get("document_artifacts", [])}
    sources = {source["id"]: source for source in metadata["sources"]}
    for document_id, source in sources.items():
        manifest = document_files[document_id]
        content = entries[manifest["export_file"]]
        assert hashlib.sha256(content).hexdigest() == source["source_sha256"] == manifest["sha256"], "Retained source digest mismatch"
        assert len(content) == source["size_bytes"] == manifest["size_bytes"]
        blocks = [{key: value for key, value in block.items() if key != "document_id"}
                  for block in bundle.get("source_blocks", []) if block["document_id"] == document_id]
        raw = json.dumps(blocks, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        assert hashlib.sha256(raw).hexdigest() == source["blocks_sha256"], "Canonical block digest mismatch"
        assert source["license"] and source["attribution"] and source["permission_note"]
        if source["source_kind"] == "abstract":
            record = next(record for record in bundle["records"] if record["id"] == source["record_id"])
            assert content == record["abstract"].encode(), "Abstract source differs from retained bibliography"
    comparisons = 0
    for handoff in metadata["handoffs"]:
        assert handoff["protocol_id"] in ids
        receipt = handoff["receipt"]
        comparison = json.loads(entries[f"pilot/comparisons/{handoff['id']}/comparison.json"])
        assert f"pilot/comparisons/{handoff['id']}/comparison.csv" in entries
        assert comparison["board_id"] == receipt["board_id"]
        assert comparison["selected_revision_id"] == receipt["revision_id"]
        definition = next(definition for definition in comparison["definitions"] if definition["revision_id"] == receipt["revision_id"])
        assert definition["preparation_id"] == receipt["preparation_id"]
        for binding in receipt["bindings"]:
            source = sources[binding["document_id"]]
            for key in ("record_id", "source_sha256", "blocks_sha256", "source_kind"):
                assert source[key] == binding[key], "Handoff source binding mismatch"
            assert source["version"] == binding["document_version"]
            prepared = next(prepared for prepared in definition["sources"] if prepared["source_id"] == binding["comparison_source_id"])
            assert prepared["paper_id"] == binding["paper_id"]
            assert prepared["source_sha256"] == binding["source_sha256"]
            assert prepared["blocks_sha256"] == binding["blocks_sha256"]
        comparisons += 1
    report["integrity"] = {"protocol_revisions": len(protocols), "event_bindings": len(metadata["event_bindings"]),
                           "retained_intake_files": intake_files, "retained_source_files": len(sources),
                           "source_bound_comparison_exports": comparisons, "status": "PASS"}
    return report


def exercise_public_sample(directory):
    """Exercise 30 fixed public records through the real in-process API.

    All screening actions below are scripted state transitions by software.
    They are not judgments about the papers' real scientific eligibility.
    """
    directory = Path(directory).resolve()
    if directory.exists():
        raise ValueError("Use a new nonexistent sample-state directory; existing data is never opened")
    directory.mkdir(mode=0o700, parents=True)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from fastapi.testclient import TestClient
    from src.web_api.app import COOKIE_NAME, create_app

    root = Path(__file__).resolve().parents[1]
    public = root / "examples/mvp/offline_microbiome_30_v1"
    manifest = json.loads((public / "manifest.json").read_text())
    label = "Scripted software usability evaluator — NOT a human reviewer"
    environment = {"MVP_DEPLOYMENT_MODE": "local", "MVP_MAP_ENABLED": "0", "MVP_PROPOSALS_ENABLED": "0", "MVP_SEARCH_PLANNER_ENABLED": "0"}
    calls, expected_denials, stages = 0, [], []
    total_started = time.monotonic()

    def denied_network(*args, **kwargs):
        raise AssertionError("The sample attempted a network connection")

    with patch.dict(os.environ, environment), patch.object(socket, "create_connection", denied_network):
        app = create_app(directory / "research")
        client = TestClient(app, base_url="http://127.0.0.1:8765")

        def request(method, path, *, body=None, expected=200):
            nonlocal calls
            calls += 1
            response = client.request(method, path, json=body) if body is not None else client.request(method, path)
            if response.status_code != expected:
                raise AssertionError(f"{method} {path}: expected {expected}, got {response.status_code}: {response.text[:1200]}")
            if expected != 200:
                expected_denials.append({"method": method, "operation": path.rsplit("/", 1)[-1], "status": expected})
            return response

        session = request("GET", "/api/v1/session").json()
        client.headers.update({"Origin": "http://127.0.0.1:3000", "X-CSRF-Token": session["csrf_token"]})
        workspace = request("POST", "/api/v1/workspaces", body={"request_id": "sample-workspace", "mode": "saved_example", "question": "Disclosed software workflow sample"}).json()
        workspace_root = "/api/v1/workspaces/" + workspace["id"]
        pilot = workspace_root + "/review-pilot"

        def view():
            return request("GET", pilot).json()

        def mutate(suffix, body, *, expected=200, state=None, request_id=None):
            state = state or view()
            payload = {"request_id": request_id or str(uuid4()), "expected_protocol_id": state["current_protocol"]["id"],
                       "expected_ledger_digest": state["ledger_digest"], "reviewer": label,
                       "reason": "Scripted software state coverage; not a real eligibility decision", **body}
            return request("POST", pilot + suffix, body=payload, expected=expected)

        def stage(name, started):
            stages.append({"stage": name, "seconds": round(time.monotonic() - started, 3), "requests_so_far": calls})

        started = time.monotonic()
        request("POST", pilot, body={"request_id": "initialize", "title": "30-record software usability sample",
            "review_type": "systematic", "question": manifest["question"], "purpose": "software_usability",
            "reviewer": label, "reason": "No actual reviewer session; unresolved owner protocol choices retained",
            "protocol": {"reference": "Software-only sample, not registered or approved for scientific screening",
                "eligibility": {}, "reviewer_roles": {"declared_label": label, "actual_human_review": "NOT_RUN"},
                "fields": ["population", "design", "diet"],
                "unresolved": ["Age limits", "Mixed populations", "Study designs", "Search limits", "Appraisal"],
                "ready_for_screening": False}})
        mutate("/protocols", {"content": {**view()["current_protocol"]["content"], "software_revision_note": "Append-only revision before scripted decisions"}})
        mutate("/intakes/public-example", {})
        initial = view()
        assert [record["pmid"] for record in initial["records"]] == [source["pmid"] for source in manifest["sources"]]
        assert initial["total_records"] == 30
        assert initial["intakes"][0]["scope"] == "exploratory_subset"
        assert not initial["search_runs"][0]["execution"]
        # Two original occurrences are reimported to exercise deduplication.
        duplicate_rows = [{key: record[key] for key in ("title", "pmid", "doi", "authors", "year", "abstract", "url")}
                          for record in initial["records"][:2]]
        raw = (" \n" + json.dumps(duplicate_rows, ensure_ascii=False, indent=1) + "\n ").encode()
        original = directory / "original-supplied-two-records.json"
        original.write_bytes(raw)
        mutate("/intakes/file", {"filename": original.name, "format": "json", "content_utf8": raw.decode(),
                "source": "Disclosed duplicate software import of first two retained records", "scope": "exploratory_subset"})
        stage("protocol_and_complete_intake_of_supplied_subset_not_query", started)

        started = time.monotonic()
        records = view()["records"]
        for index, record in enumerate(records):
            decision = "include" if index < 6 else "exclude" if index < 20 else "uncertain"
            mutate("/decisions", {"record_id": record["id"], "stage": "title_abstract", "decision": decision})
        for decision in ("uncertain", "exclude"):
            mutate("/decisions", {"record_id": records[6]["id"], "stage": "title_abstract", "decision": decision})
        selected = records[:3]
        for record in selected[:2]:
            mutate("/sources", {"record_id": record["id"], "kind": "public_jats"})
            mutate("/retrieval-status", {"record_id": record["id"], "status": "retrieved"})
        source_meta = manifest["sources"][2]
        mutate("/sources", {"record_id": selected[2]["id"], "kind": "abstract", "license": source_meta["license"],
                "attribution": source_meta["attribution"], "permission_note": "Deliberately restricted to abstract for QA; approved full text exists"})
        mutate("/retrieval-status", {"record_id": selected[2]["id"], "status": "retrieved"}, expected=422)
        mutate("/retrieval-status", {"record_id": records[3]["id"], "status": "requested"})
        mutate("/retrieval-status", {"record_id": records[4]["id"], "status": "not_retrieved", "reason": "Scripted unavailable case, not an actual failed acquisition"})
        for record, decision in zip(selected[:2], ("include", "uncertain")):
            mutate("/decisions", {"record_id": record["id"], "stage": "full_text", "decision": decision})
        stage("scripted_screening_history_and_source_statuses", started)

        started = time.monotonic()
        before = view()
        sources = [next(source for source in before["sources"] if source["record_id"] == record["id"] and source["active"]) for record in selected]
        snapshot = request("GET", workspace_root).json()
        handoff = {"sources": [{"record_id": source["record_id"], "document_id": source["id"], "source_sha256": source["source_sha256"]} for source in sources],
            "question": "Software-only comparison of exact retained selected sources",
            "fields": [{"id": "population", "label": "Population", "subquestion": "women population"},
                       {"id": "design", "label": "Study design", "subquestion": "study design method"},
                       {"id": "diet", "label": "Diet", "subquestion": "diet food"}],
            "acknowledge_provisional": False, "expected_source_revision": snapshot["source_revision"],
            "expected_preparation_id": snapshot["current_preparation_id"]}
        mutate("/handoffs", handoff, expected=422)
        result = mutate("/handoffs", {**handoff, "acknowledge_provisional": True}).json()
        receipt = result["result"]["receipt"]
        board = workspace_root + "/boards/" + receipt["board_id"]
        board_view = request("GET", board).json()
        assert all(cell["head"] is None for cell in board_view["cells"])
        for binding, source in zip(receipt["bindings"], sources):
            assert binding["source_sha256"] == source["source_sha256"]
            assert binding["blocks_sha256"] == source["blocks_sha256"]
            ledger = request("GET", pilot + "/sources/" + source["id"] + "?limit=3").json()
            comparison = request("GET", board + "/sources/" + binding["comparison_source_id"] + "/blocks?revision_id=" + receipt["revision_id"] + "&limit=3").json()
            assert [block["text"] for block in ledger["blocks"]] == [block["text"] for block in comparison["blocks"]]
        after = view()
        assert before["counts"] == after["counts"] and before["decisions"] == after["decisions"]
        stage("explicit_provisional_handoff_and_exact_inspection", started)

        started = time.monotonic()

        def entries(response):
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                return {name: archive.read(name) for name in archive.namelist()}

        exported = request("GET", pilot + "/exports")
        archive = entries(exported)
        assert any(value == raw for name, value in archive.items() if "/intakes/" in name)
        original.unlink()  # Only this evaluator-created file, after retention verified.
        output = directory / "retained-audit-export.zip"
        output.write_bytes(exported.content)
        audit = audit_entries(archive)
        # Recreate the adapter and reuse only this same test session, not a browser cookie.
        old_cookie = client.cookies.get(COOKIE_NAME)
        client = TestClient(create_app(directory / "research"), base_url="http://127.0.0.1:8765")
        client.cookies.set(COOKIE_NAME, old_cookie)
        request("GET", "/api/v1/session")
        reopened = request("GET", pilot + "/exports")
        assert entries(reopened) == archive
        stage("input_removal_retained_export_and_adapter_reopen", started)

    return {"status": "PASS", "sample": {"unique_records": 30, "identified_occurrences": 32,
                "duplicate_occurrences": 2, "ordering": "All 30 approved public sources in retained manifest order; no score selection",
                "provider_reported_matches": manifest["total_reported"], "provider_returned_metadata": manifest["returned_metadata_count"],
                "complete_query_capture": False, "purpose": "software_usability", "scripted_actions": True,
                "abstract_only_case": "Deliberate restricted coverage; full text exists in source bundle"},
            "audit": audit, "api_requests": calls, "expected_denials": expected_denials, "stages": stages,
            "elapsed_seconds": round(time.monotonic() - total_started, 3),
            "retained_export_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "reopen_export_member_bytes_identical": True, "original_input_removed_after_retention_verified": True,
            "protocol_revisions": len(after["protocols"]), "prepared_sources": len(sources),
            "comparison_papers": len(board_view["definition"]["paper_ids"]), "comparison_cells": len(board_view["cells"]),
            "actual_browser": "NOT_RUN_BY_THIS_IN_PROCESS_API_EVALUATION", "actual_human_review": "NOT_RUN",
            "authenticated_independent_or_dual_review": False, "retrieval_accuracy_benchmark": False,
            "observed_workflow_costs": ["Explicit reason and expected revision required for every mutation",
                "Full-text acquisition, retrieval declaration, screening and comparison handoff are separate steps",
                "Unresolved and abstract-only selections require explicit provisional acknowledgment",
                "Review library totals and selected comparison subset are different denominators"],
            "live_provider_calls": 0, "model_calls": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--audit-export", type=Path)
    mode.add_argument("--exercise-public-sample", type=Path, metavar="NEW_STATE_DIRECTORY")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.exercise_public_sample:
        report = exercise_public_sample(args.exercise_public_sample)
    else:
        if args.audit_export.suffix.lower() == ".zip":
            with zipfile.ZipFile(args.audit_export) as archive:
                report = audit_entries({name: archive.read(name) for name in archive.namelist()})
        else:
            report = audit_bundle(read_export(args.audit_export))
        report["input_sha256"] = hashlib.sha256(args.audit_export.read_bytes()).hexdigest()
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
