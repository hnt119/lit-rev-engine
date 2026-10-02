"""Manual quotation-backed revisions and independent reviewer state changes."""

import csv
import hashlib
import json
from pathlib import Path

import pytest

from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.store import ReviewStore


FIXTURES = Path(__file__).parent / "fixtures/evidence"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text())
TEXT = MANIFEST["fixtures"][0]
QUOTE = TEXT["quotes"][0]
ANCHOR = {key: QUOTE[key] for key in ("block_id", "start", "end", "quote")}


def scenario(store, *, doi=None):
    project = store.create_project("Synthetic evidence", "systematic", "Software question")["id"]
    store.import_records(project, SearchRunSpec("invented"), [BibliographicRecord(title="Software source report", doi=doi)])
    record = store.list_records(project)[0]["id"]
    study = store.create_study(project, "Invented study", "curator", "Manual software association")["id"]
    store.record_decision(project, record, "title_abstract", "include", "screener")
    store.set_full_text_status(project, record, "retrieved", "librarian")
    store.record_decision(project, record, "full_text", "include", "screener")
    store.record_study_links(project, record, [study], "linker", "Source relationship")
    document = store.attach_document(project, record, (FIXTURES / TEXT["file"]).read_bytes(), "txt", "librarian", "Report association")["id"]
    return project, record, study, document


def propose(store, targets, **overrides):
    data = {"field": "follow_up", "value": 6, "context": {"timepoint": "weeks", "notes": "Invented software truth"}, "anchor": dict(ANCHOR), "reviewer": "Alice", "reason": "Exact source quotation", **overrides}
    return store.propose_evidence(*targets, **data)


def revise(store, targets, previous, **overrides):
    project, _, study, document = targets
    data = {"field": "follow_up", "value": 6, "context": {}, "anchor": dict(ANCHOR), "reviewer": "Alice", "reason": "Complete corrected proposal", **overrides}
    return store.revise_evidence(project, previous["evidence_id"], study, document, **data)


def current(store, project):
    return store.list_evidence(project)[0]


def test_revision_is_full_fidelity_hashed_and_detached_from_caller_containers():
    with ReviewStore(":memory:") as store:
        targets = scenario(store)
        values = {"counts": [6, None, True], "label": "α 🧪"}
        context = {"notes": ["Source context"]}
        anchor = dict(ANCHOR)
        before = store.counts(targets[0])
        revision = propose(store, targets, value=values, context=context, anchor=anchor)
        values["counts"].append(9)
        context["notes"].append("Later edit")
        anchor["quote"] = "wrong"
        assert revision["value"] == {"counts": [6, None, True], "label": "α 🧪"}
        assert revision["context"] == {"notes": ["Source context"]}
        assert revision["anchor"] == {**ANCHOR, "locator": {"type": "text_block", "ordinal": 1}}
        assert revision["source_sha256"] == TEXT["source_sha256"]
        assert revision["blocks_sha256"] == TEXT["expected_blocks_sha256"]
        payload = {key: value for key, value in revision.items() if key != "revision_sha256"}
        assert revision["revision_sha256"] == hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        assert store.list_evidence_revisions(targets[0]) == [revision]
        assert current(store, targets[0])["state"] == "proposed"
        assert store.list_evidence(targets[0], verified_only=True) == []
        assert store.counts(targets[0]) == before


def test_latest_votes_conflict_adjudication_and_later_review_invalidation(monkeypatch):
    monkeypatch.setattr("src.review.evidence._now", lambda: "2026-10-03T00:00:00+00:00")
    with ReviewStore(":memory:") as store:
        targets = scenario(store)
        project = targets[0]
        revision = propose(store, targets)
        first = store.review_evidence(project, revision["id"], "confirm", "Bob", "Checked quotation and value")
        assert current(store, project)["state"] == "confirmed"
        assert current(store, project)["verified"]
        second = store.review_evidence(project, revision["id"], "reject", "Carol", "Value needs correction")
        assert current(store, project)["state"] == "conflict"
        revised_vote = store.review_evidence(project, revision["id"], "reject", "Bob", "Rechecked")
        assert current(store, project)["state"] == "rejected"
        assert current(store, project)["active_verification_event_ids"] == [second["id"], revised_vote["id"]]
        resolution = store.adjudicate_evidence(project, revision["id"], "confirm", "Lead", "Resolved source interpretation")
        assert current(store, project)["state"] == "confirmed"
        assert current(store, project)["active_verification_event_ids"] == [resolution["id"]]
        later = store.review_evidence(project, revision["id"], "confirm", "Bob", "Later independent check")
        assert current(store, project)["state"] == "conflict"
        assert current(store, project)["active_verification_event_ids"] == [second["id"], later["id"]]
        assert store.list_evidence_reviews(project) == [first, second, revised_vote, resolution, later]


def test_complete_revision_and_source_replacement_invalidate_old_verification(tmp_path):
    database = tmp_path / "review.sqlite3"
    with ReviewStore(database) as store:
        targets = scenario(store)
        project, record, study, document = targets
        first = propose(store, targets)
        store.review_evidence(project, first["id"], "confirm", "Bob", "Checked")
        second = revise(store, targets, first, value={"duration": 6}, reviewer="Carol")
        assert second["evidence_id"] == first["evidence_id"] and second["id"] != first["id"]
        assert second["revision"] == 2 and second["context"] == {}
        assert current(store, project)["verification_state"] == "proposed"
        assert current(store, project)["active_verification_event_ids"] == []
        with pytest.raises(ValueError, match="current revision"):
            store.review_evidence(project, first["id"], "confirm", "Other", "Old revision")
        # The former author can review another author's current complete replacement.
        store.review_evidence(project, second["id"], "confirm", "Alice", "Independent of Carol")
        replacement = store.attach_document(project, record, (FIXTURES / "source-v2.txt").read_bytes(), "txt", "librarian", "Source replacement")
        assert current(store, project)["verification_state"] == "confirmed"
        assert current(store, project)["dependency_issues"] == ["stale_source"]
        assert not current(store, project)["verified"]
        with pytest.raises(ValueError, match="stale_source"):
            store.review_evidence(project, second["id"], "confirm", "Other", "Old source")
        third = revise(store, (project, record, study, replacement["id"]), second, value=8, anchor={**ANCHOR, "quote": "8 weeks, not 12 months."})
        assert third["revision"] == 3 and current(store, project)["state"] == "proposed"
        revisions, reviews = store.list_evidence_revisions(project), store.list_evidence_reviews(project)
    with ReviewStore(database) as store:
        assert store.list_evidence_revisions(project) == revisions == [first, second, third]
        assert store.list_evidence_reviews(project) == reviews


def test_same_byte_new_document_stales_confirmation_and_dependencies_can_restore():
    with ReviewStore(":memory:") as store:
        targets = scenario(store)
        project, record, study, document = targets
        proposal = propose(store, targets)
        store.review_evidence(project, proposal["id"], "confirm", "Bob", "Checked")
        other_study = store.create_study(project, "Other", "curator", "Software association")["id"]
        store.record_study_links(project, record, [other_study], "linker", "Replaced association")
        assert current(store, project)["dependency_issues"] == ["study_not_linked"]
        store.record_study_links(project, record, [], "linker", "No resolved association")
        assert current(store, project)["state"] == "unresolved_linkage"
        store.record_study_links(project, record, [study], "linker", "Restored association")
        assert current(store, project)["verified"]
        store.record_decision(project, record, "full_text", "exclude", "screener", "Reconsidered eligibility")
        assert current(store, project)["state"] == "ineligible_report"
        assert store.list_evidence(project, verified_only=True) == []
        store.record_decision(project, record, "full_text", "include", "screener", "Restored eligibility")
        assert current(store, project)["verified"]
        store.attach_document(project, record, store.get_document_bytes(project, document), "txt", "librarian", "Same bytes new source version")
        store.record_decision(project, record, "full_text", "exclude", "screener", "Excluded")
        store.record_study_links(project, record, [], "linker", "Unlinked")
        assert current(store, project)["dependency_issues"] == ["stale_source", "ineligible_report", "unresolved_linkage"]
        assert current(store, project)["state"] == "stale_source"
        assert len(store.list_evidence_reviews(project)) == 1


def test_duplicate_fields_remain_distinct_and_appraisals_remain_manual():
    with ReviewStore(":memory:") as store:
        targets = scenario(store)
        first = propose(store, targets)
        duplicate = propose(store, targets, value=12, reason="Disagreement retained")
        appraisal = {"instrument": "Invented software checklist", "instrument_version": "test-1", "domain": "Source accounting"}
        judgment = propose(store, targets, field="domain judgment", value="Manual judgment", kind="appraisal", appraisal=appraisal)
        replaced = revise(store, targets, judgment, value="Corrected judgment", appraisal={**appraisal, "domain": "Another domain"})
        assert first["evidence_id"] != duplicate["evidence_id"]
        assert replaced["kind"] == "appraisal" and replaced["appraisal"]["domain"] == "Another domain"
        assert len(store.list_evidence(targets[0])) == 3


def test_later_identifier_enrichment_suppresses_an_earlier_confirmed_source(tmp_path):
    with ReviewStore(":memory:") as store:
        targets = scenario(store, doi="10.1234/software")
        project, record, study, _ = targets
        xml = b'<article><front><article-meta><article-id pub-id-type="doi">10.1234/software</article-id><article-id pub-id-type="pmid">123</article-id></article-meta></front><body><p>Invented source.</p></body></article>'
        document = store.attach_document(project, record, xml, "jats_xml", "librarian", "Known DOI, source PMID")
        block = store.get_source_blocks(project, document["id"])[0]
        anchor = {"block_id": block["id"], "start": 0, "end": 8, "quote": "Invented"}
        revision = propose(store, (project, record, study, document["id"]), anchor=anchor)
        review = store.review_evidence(project, revision["id"], "confirm", "Bob", "Source checked")
        assert store.list_evidence(project, record)[0]["verified"]
        store.import_records(project, SearchRunSpec("Later matched DOI"), [BibliographicRecord(title="Software source report", doi="10.1234/software", pmid="124")])
        row = store.list_evidence(project, record)[0]
        assert row["verification_state"] == "confirmed"
        assert row["dependency_issues"] == ["source_identity_conflict"]
        assert row["state"] == "source_identity_conflict" and not row["verified"]
        assert store.list_evidence(project, verified_only=True) == []
        for method in (store.review_evidence, store.adjudicate_evidence):
            with pytest.raises(ValueError, match="source_identity_conflict"):
                method(project, revision["id"], "confirm", "Other", "Conflicting identity")
        with pytest.raises(ValueError, match="source_identity_conflict"):
            propose(store, (project, record, study, document["id"]), anchor=anchor)
        with pytest.raises(ValueError, match="source_identity_conflict"):
            revise(store, (project, record, study, document["id"]), revision, anchor=anchor)
        assert store.list_evidence_revisions(project) == [revision]
        assert store.list_evidence_reviews(project) == [review]
        assert next(item for item in store.list_documents(project, record) if item["id"] == document["id"])["source_identifiers"]["pmid"] == "123"
        store.export_project(project, tmp_path)
        assert json.loads((tmp_path / "verified_evidence.json").read_text()) == []


@pytest.mark.parametrize("overrides", [{"value": float("nan")}, {"value": float("inf")}, {"value": {1: "numeric key"}}, {"value": [{"nested": {1: "numeric key"}}]}, {"value": (1, 2)}, {"value": {1, 2}}, {"context": []}, {"context": {"unsupported": "value"}}, {"context": {"notes": {1: "numeric key"}}}, {"context": {"units": float("inf")}}, {"field": " "}, {"reviewer": ""}, {"reason": " "}, {"kind": []}, {"appraisal": {}}, {"kind": "appraisal", "value": 1, "appraisal": {"instrument": "X", "instrument_version": "1", "domain": "Y"}}, {"kind": "appraisal", "value": "Judgment", "appraisal": {"instrument": "X", "domain": "Y"}}, {"kind": "appraisal", "value": "Judgment", "appraisal": {"instrument": " ", "instrument_version": "1", "domain": "Y"}}])
def test_invalid_finite_json_and_proposal_metadata_are_atomic(overrides):
    with ReviewStore(":memory:") as store:
        targets = scenario(store)
        with pytest.raises(ValueError):
            propose(store, targets, **overrides)
        assert store.list_evidence(targets[0]) == []
        assert store._connection.execute("SELECT COUNT(*) FROM evidence_entries").fetchone()[0] == 0


def test_cyclic_json_rejects_without_rows():
    value = []
    value.append({"cycle": value})
    with ReviewStore(":memory:") as store:
        targets = scenario(store)
        with pytest.raises(ValueError, match="cycles"):
            propose(store, targets, value=value)
        assert store.list_evidence_revisions(targets[0]) == []


@pytest.mark.parametrize("anchor", [{**ANCHOR, "block_id": "unknown"}, {**ANCHOR, "start": True}, {**ANCHOR, "end": 144.0}, {**ANCHOR, "start": -1}, {**ANCHOR, "end": ANCHOR["start"]}, {**ANCHOR, "end": 10000}, {**ANCHOR, "quote": "wrong"}, {**ANCHOR, "quote": " "}, {**ANCHOR, "locator": {"type": "pdf_page", "page": 1}}, {key: value for key, value in ANCHOR.items() if key != "quote"}])
def test_invalid_exact_quote_anchors_are_atomic(anchor):
    with ReviewStore(":memory:") as store:
        targets = scenario(store)
        with pytest.raises(ValueError):
            propose(store, targets, anchor=anchor)
        assert store.list_evidence_revisions(targets[0]) == []


def test_cross_project_report_document_study_and_unknown_targets_fail():
    with ReviewStore(":memory:") as store:
        targets, other = scenario(store), scenario(store)
        project, record, study, document = targets
        for wrong in [(project, record, other[2], document), (project, record, study, other[3]), (other[0], record, other[2], other[3]), (project, record, "unknown", document), (project, record, study, "unknown")]:
            with pytest.raises(ValueError):
                propose(store, wrong)
        # Even a valid source from another report in the same project is unsuitable.
        store.import_records(project, SearchRunSpec("other"), [BibliographicRecord(title="Other report")])
        other_record = store.list_records(project)[1]["id"]
        other_doc = store.attach_document(project, other_record, b"Another report source", "txt", "librarian", "Association")["id"]
        with pytest.raises(ValueError, match="different report"):
            propose(store, (project, record, study, other_doc))
        revision = propose(store, targets)
        for method in (store.list_evidence_revisions, store.list_evidence_reviews):
            with pytest.raises(ValueError, match="Unknown evidence"):
                method(other[0], revision["evidence_id"])
            with pytest.raises(ValueError, match="Unknown evidence"):
                method(project, "unknown")
        with pytest.raises(ValueError, match="Unknown record"):
            store.list_evidence(other[0], record)
        with pytest.raises(ValueError, match="Unknown evidence revision"):
            store.review_evidence(other[0], revision["id"], "confirm", "Bob", "Wrong project")


def test_verification_guards_and_failed_revisions_do_not_append():
    with ReviewStore(":memory:") as store:
        targets = scenario(store)
        project, record, study, document = targets
        revision = propose(store, targets)
        for method in (store.review_evidence, store.adjudicate_evidence):
            for decision, reviewer, reason in [("confirm", "Alice", "Self review"), ("include", "Bob", "Wrong decision"), ("confirm", " ", "Reason"), ("confirm", "Bob", " ")]:
                with pytest.raises(ValueError):
                    method(project, revision["id"], decision, reviewer, reason)
        with pytest.raises(ValueError, match="existing review"):
            store.adjudicate_evidence(project, revision["id"], "confirm", "Lead", "No reviews")
        store.record_study_links(project, record, [], "linker", "Unlinked")
        for method in (store.review_evidence, store.adjudicate_evidence):
            with pytest.raises(ValueError, match="unresolved_linkage"):
                method(project, revision["id"], "confirm", "Bob", "Invalid dependencies")
        with pytest.raises(ValueError, match="unresolved_linkage"):
            revise(store, targets, revision)
        assert store.list_evidence_revisions(project) == [revision]
        assert store.list_evidence_reviews(project) == []


@pytest.mark.parametrize("target", ["revision", "source", "blocks"])
def test_corruption_rejects_all_evidence_reads_and_export_before_replacement(tmp_path, target):
    with ReviewStore(":memory:") as store:
        targets = scenario(store)
        project = targets[0]
        revision = propose(store, targets)
        store.review_evidence(project, revision["id"], "confirm", "Bob", "Checked")
        result = store.export_project(project, tmp_path)
        original = {name: (tmp_path / name).read_bytes() for name in result["files"]}
        with store._connection:
            if target == "revision":
                payload = {key: value for key, value in revision.items() if key != "revision_sha256"}
                payload["value"] = 100
                store._connection.execute("UPDATE evidence_revisions SET payload = ?", (json.dumps(payload),))
            else:
                column, value = ("content", b"tampered") if target == "source" else ("blocks_json", "[]")
                store._connection.execute(f"UPDATE source_documents SET {column} = ?", (value,))
        for read in (store.list_evidence, store.list_evidence_revisions, store.list_evidence_reviews):
            with pytest.raises(ValueError, match="corrupt"):
                read(project)
        with pytest.raises(ValueError, match="corrupt"):
            store.export_project(project, tmp_path)
        with pytest.raises(ValueError, match="corrupt"):
            store.review_evidence(project, revision["id"], "reject", "Other", "Corrupt source")
        assert {name: (tmp_path / name).read_bytes() for name in result["files"]} == original


def test_recomputed_revision_hash_does_not_hide_an_invalid_source_anchor():
    with ReviewStore(":memory:") as store:
        targets = scenario(store)
        revision = propose(store, targets)
        payload = {key: value for key, value in revision.items() if key != "revision_sha256"}
        payload["anchor"]["quote"] = "wrong"
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with store._connection:
            store._connection.execute("UPDATE evidence_revisions SET payload = ?, revision_sha256 = ?", (serialized, hashlib.sha256(serialized.encode()).hexdigest()))
        with pytest.raises(ValueError, match="anchor"):
            store.list_evidence_revisions(targets[0])


def test_conditional_full_audit_and_verified_exports_are_deterministic_formula_safe(tmp_path):
    with ReviewStore(":memory:") as store:
        targets = scenario(store)
        project = targets[0]
        baseline = store.export_project(project, tmp_path / "before")
        assert "evidence" not in json.loads((tmp_path / "before/project.json").read_text())
        first = propose(store, targets, field="=field", value="+manual value", reviewer="@author", reason="-source reason", context={"notes": "=nested original"})
        confirmed = store.review_evidence(project, first["id"], "confirm", "@verifier", "=checked")
        pending = propose(store, targets, value=12, reason="Conflicting proposal retained")
        rejected = propose(store, targets, value=8)
        store.review_evidence(project, rejected["id"], "reject", "Bob", "Unsupported value")
        destination = tmp_path / "after"
        result = store.export_project(project, destination)
        assert result["counts"] == baseline["counts"]
        assert len(result["files"]) == len(baseline["files"]) + 5
        bundle = json.loads((destination / "project.json").read_text())
        assert len(bundle["evidence"]) == len(bundle["evidence_revisions"]) == 3
        assert [row["current_revision"] for row in bundle["verified_evidence"]] == [first]
        assert json.loads((destination / "verified_evidence.json").read_text()) == bundle["verified_evidence"]
        assert bundle["evidence_reviews"][0] == confirmed
        assert bundle["evidence_revisions"] == [first, pending, rejected]
        with (destination / "verified_evidence.csv").open(newline="") as file:
            row = next(csv.DictReader(file))
        assert row["field"] == "'=field" and row["value"] == "'+manual value"
        assert row["reviewer"] == "'@author" and row["reason"] == "'-source reason"
        assert json.loads(row["context"])["notes"] == "=nested original"
        assert json.loads(row["anchor"])["locator"] == {"type": "text_block", "ordinal": 1}
        assert json.loads(row["active_verification_event_ids"]) == [confirmed["id"]]
        assert row["state"] == "confirmed" and row["verified"].lower() == "true"
        original = {name: (destination / name).read_bytes() for name in result["files"]}
        assert store.export_project(project, destination) == result
        assert {name: (destination / name).read_bytes() for name in result["files"]} == original
