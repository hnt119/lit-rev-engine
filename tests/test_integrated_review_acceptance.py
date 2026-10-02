"""Independent one-review provenance-chain acceptance; no medical-quality claim."""

from copy import deepcopy
import csv
from dataclasses import asdict
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys

import pytest

from src.review.importers import load_records_bytes
from src.review.models import SearchRunSpec
from src.review.store import ReviewStore
from src.search.pubmed_search import capture_pubmed_search, import_pubmed_capture, verify_pubmed_capture


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
STUDIES = json.loads((FIXTURES / "studies" / "manifest.json").read_text())
INPUT_ROWS = json.loads((FIXTURES / "studies" / "records.json").read_text())
PUBMED = json.loads((FIXTURES / "pubmed" / "manifest.json").read_text())
SOURCES = {source["alias"]: source for source in json.loads((FIXTURES / "evidence" / "manifest.json").read_text())["fixtures"]}
EXTRACTIONS = json.loads((FIXTURES / "evidence" / "extractions.json").read_text())
PROPOSALS = {proposal["id"]: proposal for proposal in EXTRACTIONS["proposals"]}
REVISIONS = {revision["id"]: revision for revision in EXTRACTIONS["revisions"]}
CHECKS = ("identification", "screening_progress", "title_abstract", "retrieval_requests", "retrieval_progress", "assessment_progress", "full_text", "study_linkage")
COUNTS = {
    "records_identified": 21, "duplicate_records_removed": 8, "unique_records": 13,
    "records_awaiting_screening": 1, "records_screened": 12, "records_excluded": 5,
    "records_included_for_full_text": 7, "records_screening_unresolved": 0,
    "reports_awaiting_request": 0, "reports_sought_for_retrieval": 7, "reports_retrieved": 7,
    "reports_not_retrieved": 0, "reports_awaiting_retrieval": 0, "reports_awaiting_assessment": 0,
    "reports_assessed": 7, "reports_included": 6, "reports_excluded": 1, "reports_assessment_unresolved": 0,
    "study_linkage_available": True, "reports_included_linked": 6, "reports_included_awaiting_linkage": 0,
    "reports_included_linkage_unresolved": 0, "linked_included_studies": 3, "study_linkage_complete": True,
    "included_studies": 3, "reconciliation": {name: True for name in CHECKS}, "all_checks_passed": True,
}


@pytest.fixture(autouse=True)
def no_live_dependencies(monkeypatch):
    def denied(*args, **kwargs): pytest.fail("Integrated review attempted network or sleep")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr("time.sleep", denied)


def digest(content): return hashlib.sha256(content).hexdigest()


def canonical_hash(value):
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def ledger_hash(store): return digest("\n".join(store._connection.iterdump()).encode())


def run_cli(tmp_path, database, *args):
    environment = os.environ.copy()
    environment.pop("NCBI_EMAIL", None); environment.pop("NCBI_API_KEY", None)
    environment.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    result = subprocess.run([sys.executable, str(ROOT / "review.py"), "--db", str(database), *map(str, args)],
                            cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0 and result.stderr == "", result.stderr
    return json.loads(result.stdout)


class FixtureClient:
    def __init__(self): self.calls = []
    def request(self, endpoint, parameters):
        self.calls.append((endpoint, deepcopy(parameters)))
        if len(self.calls) == 1:
            assert endpoint == "esearch.fcgi" and parameters["term"] == PUBMED["query"]
            return (FIXTURES / "pubmed" / PUBMED["search_file"]).read_bytes()
        batch = PUBMED["batches"][len(self.calls) - 2]
        assert endpoint == "efetch.fcgi" and parameters["id"] == ",".join(batch["requested_pmids"])
        return (FIXTURES / "pubmed" / batch["response_file"]).read_bytes()


def enter(store, environment, template, record_alias, source_alias, *, evidence_id=None):
    payload = deepcopy(template["input"])
    payload.pop("kind", None)
    payload["study_id"] = environment["studies"]["A"]
    payload["document_id"] = environment["documents"][(record_alias, source_alias)]["id"]
    if evidence_id is None:
        revision = store.propose_evidence(environment["project_id"], environment["reports"][record_alias],
                                          **payload, kind=template["input"].get("kind", "finding"))
    else:
        revision = store.revise_evidence(environment["project_id"], evidence_id, **payload)
    event = store.review_evidence(environment["project_id"], revision["id"], "confirm", "Fixture Reviewer Bo", "Independent literal synthetic source check")
    return revision, event


def attach_copy(store, environment, tmp_path, record_alias, source_alias):
    source = SOURCES[source_alias]
    copied = tmp_path / f"{record_alias}-{source_alias}" / source["file"]
    copied.parent.mkdir()
    copied.write_bytes((FIXTURES / "evidence" / source["file"]).read_bytes())
    content = copied.read_bytes()
    document = store.attach_document(environment["project_id"], environment["reports"][record_alias], content, source["format"],
                                     "Fixture Custodian", "Explicit invented report/source association", filename=copied.name,
                                     version_label=source_alias, source_url="https://example.invalid/independent-software-fixture")
    assert document["source_sha256"] == source["source_sha256"] and document["blocks_sha256"] == source["expected_blocks_sha256"]
    environment["documents"][(record_alias, source_alias)] = document
    environment["copied_sources"].append(copied)
    return document


def integrated_review(tmp_path):
    database = tmp_path / "integrated review" / "reviews.sqlite3"
    input_bytes = (FIXTURES / "studies" / "records.json").read_bytes()
    paths = [tmp_path / "search-one.json", tmp_path / "search-two.json"]
    for path in paths: path.write_bytes(input_bytes)
    records = load_records_bytes(input_bytes, "json")
    specifications = [SearchRunSpec(source="Independent bibliography export", query="  invented cohort sources v1  ", searched_at="2026-01-01T10:30:00+00:00", filters={"fixture_version": 1}, notes="First preserved search", import_format="json", source_file=str(paths[0]), source_sha256=digest(input_bytes), reported_count=8),
                      SearchRunSpec(source="Independent bibliography export", query="invented companion sources v2", searched_at="2026-02-01", filters={"fixture_version": 2}, notes="Second distinct search, same exported rows", import_format="json", source_file=str(paths[1]), source_sha256=digest(input_bytes), reported_count=8)]
    with ReviewStore(database) as store:
        p = store.create_project("Integrated invented review", "systematic", "Which source-supported software declarations?", protocol="No clinical inference; independent synthetic audit")["id"]
        first = store.import_records(p, specifications[0], records, "integrated-json-first")
        second = store.import_records(p, specifications[1], records, "integrated-json-second")
        assert (first["identified"], first["new_records"], first["duplicates"]) == (8, 8, 0)
        assert (second["identified"], second["new_records"], second["duplicates"]) == (8, 0, 8)
        unchanged = ledger_hash(store)
        assert store.import_records(p, specifications[0], records, "integrated-json-first") == first and ledger_hash(store) == unchanged
        reports = {row["source_id"]: row["id"] for row in store.list_records(p)}
        client = FixtureClient()
        capture = capture_pubmed_search(PUBMED["query"], tmp_path / "original capture", client=client, sort=PUBMED["sort"], filters=PUBMED["filters"], batch_size=2)
        assert len(client.calls) == 4
        capture_directory = Path(capture["directory"])
        artifacts = {path.relative_to(capture_directory).as_posix(): path.read_bytes() for path in capture_directory.rglob("*") if path.is_file()}
        assert len(artifacts) == 6
        pubmed_import = import_pubmed_capture(store, p, capture["directory"], idempotency_key="integrated-pubmed")
        assert (pubmed_import["identified"], pubmed_import["new_records"], pubmed_import["duplicates"]) == (5, 5, 0)
        pubmed_records = [row for row in store.list_records(p) if row["pmid"] in PUBMED["ordered_pmids"]]
        assert [row["pmid"] for row in pubmed_records] == PUBMED["ordered_pmids"]
        studies = {study["alias"]: store.create_study(p, study["label"], study["reviewer"], study["reason"], study["identifiers"])["id"] for study in STUDIES["studies"]}
        screening = STUDIES["screening"]
        for alias in screening["title_abstract_included"]: store.record_decision(p, reports[alias], "title_abstract", "include", screening["reviewer"])
        for alias in screening["full_text_retrieved"]: store.set_full_text_status(p, reports[alias], "retrieved", screening["reviewer"])
        for alias in screening["full_text_included"]: store.record_decision(p, reports[alias], "full_text", "include", screening["reviewer"])
        for excluded in screening["full_text_excluded"]: store.record_decision(p, reports[excluded["report"]], "full_text", "exclude", screening["reviewer"], excluded["reason"])
        for row in pubmed_records: store.record_decision(p, row["id"], "title_abstract", "exclude", screening["reviewer"], "Synthetic integration excludes the invented capture membership; no medical conclusion.")
        for event in STUDIES["initial"]["events"] + STUDIES["final"]["events"]:
            method = store.adjudicate_study_links if event["kind"] == "adjudication" else store.record_study_links
            method(p, reports[event["report"]], [studies[alias] for alias in event["studies"]], event["reviewer"], event["reason"])
        assert store.counts(p) == COUNTS
        environment = {"database": database, "project_id": p, "reports": reports, "studies": studies, "documents": {}, "copied_sources": [],
                       "capture": capture, "capture_artifacts": artifacts, "pubmed_import": pubmed_import, "specifications": specifications,
                       "generic_imports": [first, second], "input_paths": paths, "input_bytes": input_bytes}
        attach_copy(store, environment, tmp_path, "r1", "jats_v1")
        attach_copy(store, environment, tmp_path, "r2", "text_v1")
        attach_copy(store, environment, tmp_path, "r7", "text_v1")
        finding, finding_review = enter(store, environment, PROPOSALS["follow_up_jats_v1"], "r1", "jats_v1")
        appraisal, appraisal_review = enter(store, environment, PROPOSALS["appraisal_jats"], "r1", "jats_v1")
        negation, negation_review = enter(store, environment, PROPOSALS["unmeasured_text"], "r2", "text_v1")
        assert len(store.list_evidence(p, verified_only=True)) == 3
        attach_copy(store, environment, tmp_path, "r1", "jats_v2")
        stale = store.list_evidence(p)
        assert [row["state"] for row in stale] == ["stale_source", "stale_source", "confirmed"]
        assert [row["evidence_id"] for row in store.list_evidence(p, verified_only=True)] == [negation["evidence_id"]]
        updated_finding, finding_review_2 = enter(store, environment, REVISIONS["follow_up_8weeks_v2"], "r1", "jats_v2", evidence_id=finding["evidence_id"])
        amended_appraisal = deepcopy(PROPOSALS["appraisal_jats"])
        amended_appraisal["input"]["reason"] = "Complete appraisal replacement anchored to the explicit v2 source"
        updated_appraisal, appraisal_review_2 = enter(store, environment, amended_appraisal, "r1", "jats_v2", evidence_id=appraisal["evidence_id"])
        assert store.counts(p) == COUNTS
        environment["revisions"] = [finding, appraisal, negation, updated_finding, updated_appraisal]
        environment["reviews"] = [finding_review, appraisal_review, negation_review, finding_review_2, appraisal_review_2]
        environment["current_revisions"] = [updated_finding, updated_appraisal, negation]
        return environment


def assert_bundle_truth(bundle, environment, output):
    p, reports, studies = environment["project_id"], environment["reports"], environment["studies"]
    assert bundle["counts"] == COUNTS and bundle["project"]["id"] == p
    assert len(bundle["search_runs"]) == 3 and len(bundle["occurrences"]) == 21 and len(bundle["records"]) == 13
    assert sum(run["identified"] for run in bundle["search_runs"]) == 21 and sum(run["duplicates"] for run in bundle["search_runs"]) == 8
    for run, spec in zip(bundle["search_runs"][:2], environment["specifications"], strict=True):
        for key, value in asdict(spec).items(): assert run[key] == value
    assert bundle["search_runs"][2]["execution"] == environment["capture"]["receipt"]
    for run in bundle["search_runs"][:2]:
        occurrences = [row for row in bundle["occurrences"] if row["search_run_id"] == run["id"]]
        assert [row["ordinal"] for row in occurrences] == list(range(1, 9))
        assert [row["record"]["raw"] for row in occurrences] == INPUT_ROWS
    pub_occurrences = [row for row in bundle["occurrences"] if row["search_run_id"] == environment["pubmed_import"]["search_run_id"]]
    assert [row["record"]["pmid"] for row in pub_occurrences] == PUBMED["ordered_pmids"]
    records = {row["id"]: row for row in bundle["records"]}
    assert sum(row["title_abstract_state"] == "pending" for row in records.values()) == 1
    assert sum(row["title_abstract_state"] == "exclude" for row in records.values()) == 5
    assert sum(row["title_abstract_state"] == "include" for row in records.values()) == 7
    assert sum(row["full_text_state"] == "include" for row in records.values()) == 6
    assert sum(row["full_text_state"] == "exclude" for row in records.values()) == 1
    assert sum(row["full_text_status"] == "retrieved" for row in records.values()) == 7
    assert {row["id"] for row in records.values() if row["full_text_state"] == "include"} == {reports[alias] for alias in ("r1", "r2", "r3", "r4", "r5", "r8")}
    links = {row["record_id"]: row for row in bundle["study_links"]}
    for alias, expected in STUDIES["final"]["links"].items():
        assert links[reports[alias]]["state"] == expected["state"]
        assert set(links[reports[alias]]["study_ids"]) == {studies[study] for study in expected["studies"]}
    included_studies = {study for record in records.values() if record["full_text_state"] == "include" for study in links[record["id"]]["study_ids"]}
    assert included_studies == {studies[alias] for alias in ("A", "B", "C")}
    assert len(bundle["studies"]) == 5 and len(bundle["study_link_events"]) == 10
    for event, expected in zip(bundle["study_link_events"], STUDIES["initial"]["events"] + STUDIES["final"]["events"], strict=True):
        assert event["record_id"] == reports[expected["report"]]
        assert set(event["study_ids"]) == {studies[alias] for alias in expected["studies"]}
        assert all(event[key] == expected[key] for key in ("kind", "reviewer", "reason"))
    assert studies["D"] in links[reports["r6"]]["study_ids"] and studies["D"] not in included_studies
    assert all(studies["E"] not in row["study_ids"] for row in links.values())
    assert len(links[reports["r3"]]["study_ids"]) == 2
    assert {record for record, link in links.items() if studies["A"] in link["study_ids"]} == {reports["r1"], reports["r2"], reports["r8"]}
    assert len(bundle["documents"]) == 4 and len(bundle["document_artifacts"]) == 4 and len(bundle["source_blocks"]) == 16
    documents = {doc["id"]: doc for doc in bundle["documents"]}
    for (record_alias, source_alias), expected_document in environment["documents"].items():
        document = documents[expected_document["id"]]
        source = SOURCES[source_alias]
        blocks = [{key: value for key, value in block.items() if key != "document_id"} for block in bundle["source_blocks"] if block["document_id"] == document["id"]]
        assert blocks == source["expected_blocks"] and canonical_hash(blocks) == document["blocks_sha256"]
        artifact = next(asset for asset in bundle["document_artifacts"] if asset["document_id"] == document["id"])
        content = (output / artifact["export_file"]).read_bytes()
        assert content == (FIXTURES / "evidence" / source["file"]).read_bytes()
        assert digest(content) == artifact["sha256"] == document["source_sha256"] and len(content) == artifact["size_bytes"]
    assert bundle["evidence_revisions"] == environment["revisions"] and bundle["evidence_reviews"] == environment["reviews"]
    assert len(bundle["evidence"]) == len(bundle["verified_evidence"]) == 3
    assert [row["current_revision"] for row in bundle["verified_evidence"]] == environment["current_revisions"]
    for revision in bundle["evidence_revisions"]:
        assert revision["revision_sha256"] == canonical_hash({key: value for key, value in revision.items() if key != "revision_sha256"})
        document = documents[revision["document_id"]]
        assert revision["source_sha256"] == document["source_sha256"] and revision["blocks_sha256"] == document["blocks_sha256"]
        block = next(block for block in bundle["source_blocks"] if block["document_id"] == document["id"] and block["id"] == revision["anchor"]["block_id"])
        assert block["text"][revision["anchor"]["start"]:revision["anchor"]["end"]] == revision["anchor"]["quote"] and revision["anchor"]["locator"] == block["locator"]
    for row in bundle["verified_evidence"]:
        revision = row["current_revision"]
        assert documents[revision["document_id"]]["active"] and records[revision["record_id"]]["full_text_state"] == "include"
        assert links[revision["record_id"]]["state"] == "linked" and revision["study_id"] in links[revision["record_id"]]["study_ids"]
        assert row["state"] == row["verification_state"] == "confirmed" and row["dependency_issues"] == []
    assert [row["value"].get("duration") for row in bundle["evidence_revisions"] if row["field"] == "fixture.follow_up"] == [6, 8]
    assert bundle["verified_evidence"][0]["current_revision"]["value"] == {"duration": 8, "unit": "weeks"}
    assert bundle["verified_evidence"][0]["current_revision"]["context"]["timepoint"] == "8 weeks"
    assert bundle["verified_evidence"][1]["current_revision"]["appraisal"] == PROPOSALS["appraisal_jats"]["input"]["appraisal"]
    assert bundle["verified_evidence"][2]["current_revision"]["value"] == {"measured": False, "estimate": None}
    assert len(bundle["search_artifacts"]) == 6
    for asset in bundle["search_artifacts"]:
        expected = environment["capture_artifacts"][asset["name"]]
        assert (output / asset["export_file"]).read_bytes() == expected
        assert digest(expected) == asset["sha256"] and len(expected) == asset["size_bytes"]
    assert json.loads((output / "counts.json").read_text()) == COUNTS
    flattened_counts = {key: str(value) for key, value in COUNTS.items() if key != "reconciliation"}
    flattened_counts.update({"reconciliation." + key: "True" for key in CHECKS})
    assert {row["metric"]: row["value"] for row in csv.DictReader(io.StringIO((output / "counts.csv").read_text()))} == flattened_counts
    assert json.loads((output / "verified_evidence.json").read_text()) == bundle["verified_evidence"]
    assert json.loads((output / "source_blocks.json").read_text()) == bundle["source_blocks"]
    verified_csv = list(csv.DictReader(io.StringIO((output / "verified_evidence.csv").read_text())))
    assert len(verified_csv) == 3
    for exported, expected in zip(verified_csv, bundle["verified_evidence"], strict=True):
        revision = expected["current_revision"]
        assert all(exported[key] == revision[key] for key in ("id", "evidence_id", "record_id", "study_id", "document_id", "source_sha256", "blocks_sha256", "revision_sha256"))
        exported_value = json.loads(exported["value"]) if isinstance(revision["value"], (dict, list)) else exported["value"]
        assert exported_value == revision["value"]
        assert all(json.loads(exported[key]) == revision[key] for key in ("context", "anchor"))
        assert (json.loads(exported["appraisal"]) if exported["appraisal"] else None) == revision["appraisal"]
        assert exported["state"] == "confirmed" and exported["verified"] == "True" and json.loads(exported["dependency_issues"]) == []
    revisions_csv = list(csv.DictReader(io.StringIO((output / "evidence_revisions.csv").read_text())))
    assert [row["id"] for row in revisions_csv] == [row["id"] for row in bundle["evidence_revisions"]]
    for exported, revision in zip(revisions_csv, bundle["evidence_revisions"], strict=True):
        exported_value = json.loads(exported["value"]) if isinstance(revision["value"], (dict, list)) else exported["value"]
        assert exported_value == revision["value"]
    assert [row["id"] for row in csv.DictReader(io.StringIO((output / "evidence_reviews.csv").read_text()))] == [row["id"] for row in bundle["evidence_reviews"]]
    exclusions = list(csv.DictReader(io.StringIO((output / "exclusions.csv").read_text())))
    assert len(exclusions) == 6 and sum(row["stage"] == "title_abstract" for row in exclusions) == 5
    assert next(row for row in exclusions if row["stage"] == "full_text")["reason"] == STUDIES["screening"]["full_text_excluded"][0]["reason"]


def retrievals(store, environment):
    p = environment["project_id"]
    before = ledger_hash(store)
    results = {}
    for scope, aliases in (("included", ["r1", "r2"]), ("all_attached", ["r1", "r2", "r7"])):
        trace = store.search_sources(p, "fixture follow-up weeks", scope=scope, top_k=100)
        assert trace["status"] == "candidate_passages"
        assert [row["record_id"] for row in trace["source_manifest"]] == [environment["reports"][alias] for alias in aliases]
        assert trace["source_snapshot_sha256"] == canonical_hash(trace["source_manifest"])
        assert environment["documents"][("r1", "jats_v1")]["id"] not in {row["document_id"] for row in trace["source_manifest"]}
        selected = {row["document_id"]: row for row in trace["source_manifest"]}
        for manifest, alias in zip(trace["source_manifest"], aliases, strict=True):
            source_alias = "jats_v2" if alias == "r1" else "text_v1"
            expected = environment["documents"][(alias, source_alias)]
            assert manifest["document_id"] == expected["id"]
            assert all(manifest[key] == expected[key] for key in ("version", "format", "source_sha256", "blocks_sha256", "parser_id", "parser_metadata", "source_identifiers", "source_url", "version_label"))
            assert manifest["source_sha256"] == SOURCES[source_alias]["source_sha256"] and manifest["blocks_sha256"] == SOURCES[source_alias]["expected_blocks_sha256"]
            assert manifest["full_text_state"] == ("pending" if alias == "r7" else "include")
            assert set(manifest["study_ids"]) == (set() if alias == "r7" else {environment["studies"]["A"]})
        for passage in trace["passages"]:
            assert passage["project_id"] == p and passage["document_id"] in selected
            metadata = selected[passage["document_id"]]
            assert passage["document_version"] == metadata["version"]
            assert all(passage[key] == metadata[key] for key in ("record_id", "source_sha256", "blocks_sha256", "parser_id", "full_text_state", "study_link_state", "study_ids"))
            block = next(block for block in store.get_source_blocks(p, passage["document_id"]) if block["id"] == passage["anchor"]["block_id"])
            assert block["text"][passage["anchor"]["start"]:passage["anchor"]["end"]] == passage["anchor"]["quote"] and block["locator"] == passage["locator"]
        results[scope] = trace
    assert ledger_hash(store) == before
    return results


def test_one_review_import_screen_link_source_extract_export_delete_reopen_and_portable_pubmed_replay(tmp_path):
    environment = integrated_review(tmp_path)
    p, database = environment["project_id"], environment["database"]
    output = tmp_path / "complete export"
    with ReviewStore(database) as store:
        traces = retrievals(store, environment)
        before = ledger_hash(store)
        result = store.export_project(p, output)
        assert len(result["files"]) == 29 and result["counts"] == COUNTS
        bundle = json.loads((output / "project.json").read_text())
        assert_bundle_truth(bundle, environment, output)
        assert ledger_hash(store) == before
        expected_bytes = {name: (output / name).read_bytes() for name in result["files"]}
    for scope in ("included", "all_attached"):
        assert run_cli(tmp_path, database, "retrieve-sources", p, "--query", "fixture follow-up weeks", "--scope", scope, "--top-k", 100) == traces[scope]
    for path in environment["copied_sources"] + environment["input_paths"]: path.unlink()
    shutil.rmtree(environment["capture"]["directory"])
    with ReviewStore(database) as store:
        assert ledger_hash(store) == before and store.counts(p) == COUNTS
        assert retrievals(store, environment) == traces
        assert store.export_project(p, output) == result
        assert {name: (output / name).read_bytes() for name in result["files"]} == expected_bytes
        capture_root = output / "search_captures" / environment["pubmed_import"]["search_run_id"]
        verified = verify_pubmed_capture(capture_root)
        assert verified["receipt"] == environment["capture"]["receipt"] and verified["receipt"]["pmids"] == PUBMED["ordered_pmids"]
        assert import_pubmed_capture(store, p, capture_root, idempotency_key="integrated-pubmed") == environment["pubmed_import"]
        assert ledger_hash(store) == before and store.counts(p) == COUNTS
        assert store.export_project(p, output) == result
        assert {name: (output / name).read_bytes() for name in result["files"]} == expected_bytes


def test_complete_export_uses_one_wal_snapshot_across_new_search_screening_links_source_and_evidence(tmp_path, monkeypatch):
    environment = integrated_review(tmp_path)
    p, database = environment["project_id"], environment["database"]
    with ReviewStore(database) as store:
        assert store._connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        expected_result = store.export_project(p, tmp_path / "old snapshot")
        expected = {name: (tmp_path / "old snapshot" / name).read_bytes() for name in expected_result["files"]}
        original = store.list_records
        changed = False
        def concurrent_changes(project_id):
            nonlocal changed
            records = original(project_id)
            if project_id == p and not changed:
                assert store._connection.in_transaction
                changed = True
                with ReviewStore(database) as writer:
                    writer.import_records(p, SearchRunSpec("Concurrent distinct bibliography run"), load_records_bytes(environment["input_bytes"], "json"))
                    writer.record_decision(p, environment["reports"]["r1"], "full_text", "exclude", STUDIES["screening"]["reviewer"], "Concurrent eligibility change")
                    writer.record_study_links(p, environment["reports"]["r3"], [environment["studies"]["B"]], "linker-one", "Concurrent complete association revision")
                    writer.attach_document(p, environment["reports"]["r1"], (FIXTURES / "evidence" / "article-v1.xml").read_bytes(), "jats_xml", "Custodian", "Concurrent explicit third source version")
                    negation = environment["current_revisions"][2]
                    inputs = {key: deepcopy(negation[key]) for key in ("study_id", "document_id", "field", "value", "context", "anchor")}
                    inputs["anchor"].pop("locator")
                    inputs["context"]["notes"] = "Concurrent complete negation revision"
                    revision = writer.revise_evidence(p, negation["evidence_id"], **inputs, reviewer="Carol", reason="Concurrent revision")
                    writer.review_evidence(p, revision["id"], "confirm", "Bob", "Concurrent independent review")
            return records
        monkeypatch.setattr(store, "list_records", concurrent_changes)
        result = store.export_project(p, tmp_path / "concurrent snapshot")
        assert changed and result["counts"] == COUNTS and result["files"] == expected_result["files"]
        assert {name: (tmp_path / "concurrent snapshot" / name).read_bytes() for name in result["files"]} == expected
        after = store.counts(p)
        assert after["records_identified"] == 29 and after["duplicate_records_removed"] == 16 and after["unique_records"] == 13
        assert after["reports_included"] == 5 and after["all_checks_passed"] is True
        assert len(store.list_search_runs(p)) == 4 and len(store.list_documents(p)) == 5
        assert len(store.list_evidence_revisions(p)) == len(store.list_evidence_reviews(p)) == 6
        verified = store.list_evidence(p, verified_only=True)
        assert len(verified) == 1 and verified[0]["record_id"] == environment["reports"]["r2"]
