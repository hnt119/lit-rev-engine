"""Local sidecars only: synthetic judgments never become clinical findings."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from src.review_workbench import assessments, contracts, evaluation, receipts
from src.review_workbench.cli import DEMO_RECEIPT_SHA256, demo


@pytest.fixture(scope="module")
def saved(tmp_path_factory):
    target = tmp_path_factory.mktemp("workbench-core") / "demo"
    copied = demo(target)
    return target / "validation.receipt.json", receipts.load_packet(copied["receipt"], copied["receipt_sha256"])


def draft(packet):
    bundle = packet["bundles"][0]
    return {"packet_id": packet["packet_id"], "bundle_id": bundle["id"], "reviewer": "synthetic-test-only",
            "status": "uncertain", "reason": "Synthetic software test; no clinical interpretation.", "ratings": [],
            "supporting_passage_ids": [], "missing_components": [], "contradiction": False,
            "source_inspected": False, "supersedes": None, "review_seconds": None}


def test_trust_is_external_whole_file_not_envelope_checksum(saved):
    path, packet = saved
    assert len(packet["questions"]) == 8 and len(packet["bundles"]) == 32
    assert packet["binding"]["receipt_file_sha256"] == DEMO_RECEIPT_SHA256
    own_payload_hash = json.loads(path.read_text())["payload_sha256"]
    with pytest.raises(ValueError, match="whole-file"):
        receipts.load_packet(path, own_payload_hash)


def test_recomputed_quotation_is_checked_after_all_envelopes_are_rehashed(saved, tmp_path):
    path, _ = saved
    envelope = json.loads(path.read_text())
    envelope["payload"]["recomputed"]["traces"][0]["passages"][0]["anchor"]["quote"] = "Synthetic forged quotation"
    envelope["payload_sha256"] = contracts.digest(envelope["payload"])
    changed = tmp_path / "forged.json"
    data = contracts.canonical(envelope).encode()
    changed.write_bytes(data)
    with pytest.raises(ValueError, match="reconstruction"):
        receipts.load_packet(changed, contracts.sha256(data))


def test_retained_canonical_source_is_exact_and_complete(saved):
    path, packet = saved
    job = json.loads(path.read_text())["payload"]["job"]["payload"]
    assert all(contracts.digest(source["blocks"]) == source["blocks_sha256"] for source in packet["sources"])
    job["candidates"][0]["passage"]["anchor"]["quote"] += " synthetic mutation"
    with pytest.raises(ValueError, match="canonical source blocks"):
        receipts._sources(job)


def test_blind_packet_hides_machine_method_information(saved):
    _, packet = saved
    blind = receipts.public_packet(packet)
    for bundle in blind["bundles"]:
        assert "method_key" not in bundle
        assert all(not ({"score", "query_scores", "selection_reasons"} & set(row)) for row in bundle["passages"])
    assert "shared_batch_runtime" not in blind
    revealed = receipts.public_packet(packet, reveal=True)
    assert all("method_key" in bundle for bundle in revealed["bundles"])
    assert blind["sources"] == packet["sources"]


def test_explicit_supersession_is_append_only_and_binding_changes_are_rejected(saved, tmp_path):
    _, packet = saved
    initial = draft(packet)
    first = assessments.save_assessment(packet, tmp_path, initial)
    original = (tmp_path / (first["id"] + ".json")).read_bytes()
    with pytest.raises(ValueError, match="latest"):
        assessments.save_assessment(packet, tmp_path, initial)
    changed = deepcopy(initial)
    changed["supersedes"] = first["id"]
    changed["reason"] += " Explicit synthetic correction."
    second = assessments.save_assessment(packet, tmp_path, changed)
    records = assessments.list_assessments(packet, tmp_path)
    assert len(records) == 2 and assessments.current_assessments(packet, records) == [second]
    assert (tmp_path / (first["id"] + ".json")).read_bytes() == original
    rebound = deepcopy(packet)
    rebound["binding"]["source_snapshot_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="stale"):
        assessments.list_assessments(rebound, tmp_path)


@pytest.mark.parametrize("mutation", ["bool_grade", "unknown_passage", "unknown_component", "sufficient_no_refs", "partial_no_missing", "nonfinite_time", "unknown_field", "wrong_packet"])
def test_invalid_synthetic_judgments_do_not_write(saved, tmp_path, mutation):
    _, packet = saved
    own = draft(packet)
    bundle = packet["bundles"][0]
    question = next(row for row in packet["questions"] if row["id"] == bundle["question_id"])
    rating = {"passage_id": bundle["passages"][0]["id"], "rating": 3,
              "component_ratings": {part["id"]: None for part in question["components"]}}
    own["ratings"] = [rating]
    if mutation == "bool_grade": rating["rating"] = True
    if mutation == "unknown_passage": rating["passage_id"] = "0" * 64
    if mutation == "unknown_component": rating["component_ratings"]["invented"] = 2
    if mutation == "sufficient_no_refs": own["status"] = "sufficient"
    if mutation == "partial_no_missing": own["status"] = "partial"
    if mutation == "nonfinite_time": own["review_seconds"] = float("nan")
    if mutation == "unknown_field": own["verified"] = True
    if mutation == "wrong_packet": own["packet_id"] = "0" * 64
    with pytest.raises(ValueError):
        assessments.save_assessment(packet, tmp_path, own)
    assert not list(tmp_path.glob("*.json"))


def test_null_ratings_remain_unknown_and_never_make_precision_or_support(saved, tmp_path):
    _, packet = saved
    record = assessments.save_assessment(packet, tmp_path, draft(packet))
    summary = evaluation.summarize(packet, [record])
    method = packet["bundles"][0]["method_key"]
    own = summary["methods"][method]
    assert own["rated_passages"] == 0 and own["mean_observed_passage_grade"] is None
    assert own["mean_fully_rated_bundle_precision"] is None and own["mean_precision_at_5"] is None
    assert own["unknown_passage_ratings_in_recorded_bundles"] == len(packet["bundles"][0]["passages"])
    assert own["bundle_support_counts"]["uncertain"] == 1
    assert summary["independent_verification"] == "NOT_RUN" and summary["source_answerability"] == "not_assessed"


def test_no_symlinks_in_receipt_or_assessment_ancestors(saved, tmp_path):
    path, packet = saved
    receipt_link = tmp_path / "receipt.json"
    receipt_link.symlink_to(path)
    with pytest.raises(ValueError, match="non-symlink"):
        receipts.load_packet(receipt_link, DEMO_RECEIPT_SHA256)
    actual = tmp_path / "actual"
    actual.mkdir()
    (tmp_path / "linked").symlink_to(actual, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        assessments.save_assessment(packet, tmp_path / "linked" / "records", draft(packet))
    assert not list(actual.iterdir())


def test_two_processes_cannot_create_two_current_roots(saved, tmp_path):
    _, packet = saved
    packet_file, draft_file = tmp_path / "packet.txt", tmp_path / "draft.txt"
    packet_file.write_text(contracts.canonical(packet))
    draft_file.write_text(contracts.canonical(draft(packet)))
    directory = tmp_path / "records"
    code = """import json,sys
from src.review_workbench.assessments import save_assessment
try:
 save_assessment(json.load(open(sys.argv[1])),sys.argv[3],json.load(open(sys.argv[2])))
except ValueError:
 sys.exit(2)
"""
    arguments = [sys.executable, "-c", code, str(packet_file), str(draft_file), str(directory)]
    left, right = subprocess.Popen(arguments), subprocess.Popen(arguments)
    assert sorted([left.wait(timeout=10), right.wait(timeout=10)]) == [0, 2]
    assert len(assessments.list_assessments(packet, directory)) == 1
