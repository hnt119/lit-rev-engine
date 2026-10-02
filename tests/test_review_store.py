import sqlite3
from dataclasses import replace

import pytest

from src.review.identity import normalize_doi, normalize_pmid
from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.store import ReviewStore


def project(store, title="Review"):
    return store.create_project(title, "systematic", "What is the evidence?", eligibility={"population": "adults"})["id"]


def record(**changes):
    return replace(BibliographicRecord(title="A trial", authors=["Smith A"], year=2023), **changes)


def test_persistence_and_context_cleanup(tmp_path):
    path = tmp_path / "nested" / "ledger.sqlite3"
    with ReviewStore(path) as store:
        project_id = project(store)
        result = store.import_records(project_id, SearchRunSpec("PubMed", query="trial"), [record(pmid="123")])
        assert store._connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert store._connection is None
    store.close()
    with ReviewStore(path) as reopened:
        assert reopened.get_project(project_id)["eligibility"] == {"population": "adults"}
        assert reopened.list_search_runs(project_id)[0]["id"] == result["search_run_id"]
        assert reopened.list_records(project_id)[0]["pmid"] == "123"


def test_runs_provenance_fill_only_and_reconciled_counts():
    with ReviewStore(":memory:") as store:
        project_id = project(store)
        original = record(doi="https://doi.org/10.1234/Trial", abstract="", raw={"export_note": "original"})
        spec = SearchRunSpec("PubMed", query="(trial AND adults)", searched_at="2026-10-02", filters={"language": "English"}, reported_count=50)
        first = store.import_records(project_id, spec, [original, record(doi="10.1234/trial", title="Conflicting title", abstract="Evidence", raw={"v": 2})])
        frozen_run = store.list_search_runs(project_id)[0]
        second = store.import_records(project_id, SearchRunSpec("Embase"), [record(doi="DOI:10.1234/TRIAL", pmid="999", abstract="Revised evidence")])
        assert first["new_records"] == 1 and first["duplicates"] == 1
        assert second["new_records"] == 0
        canonical = store.list_records(project_id)[0]
        assert canonical["title"] == "A trial"
        assert canonical["abstract"] == "Evidence"
        assert canonical["pmid"] == "999"
        assert canonical["raw"] == {"export_note": "original"}
        occurrences = store.get_occurrences(project_id, canonical["id"])
        assert [occurrence["ordinal"] for occurrence in occurrences] == [1, 2, 1]
        assert occurrences[0]["record"]["doi"] == "https://doi.org/10.1234/Trial"
        assert occurrences[1]["record"]["title"] == "Conflicting title"
        assert store.list_search_runs(project_id)[0] == frozen_run
        assert frozen_run["query"] == spec.query
        assert frozen_run["reported_count"] == 50
        counts = store.counts(project_id)
        assert {key: counts[key] for key in ("records_identified", "duplicate_records_removed", "unique_records")} == {"records_identified": 3, "duplicate_records_removed": 2, "unique_records": 1}
        assert counts["all_checks_passed"]


def test_project_isolation_and_record_validation():
    with ReviewStore(":memory:") as store:
        first, second = project(store), project(store, "Second")
        for project_id in (first, second):
            store.import_records(project_id, SearchRunSpec("PubMed"), [record(pmid="100")], "same-key")
        first_record = store.list_records(first)[0]["id"]
        assert first_record != store.list_records(second)[0]["id"]
        with pytest.raises(ValueError, match="Unknown record"):
            store.get_occurrences(second, first_record)
        for method in (store.get_project, store.list_records, store.list_search_runs, store.get_occurrences, store.counts):
            with pytest.raises(ValueError, match="Unknown project"):
                method("missing")


@pytest.mark.parametrize("bad", [record(title=" "), record(year=True), record(year=0), record(authors=[""]), record(doi="bad"), record(pmid="abc"), record(raw={"score": float("nan")})])
def test_invalid_import_is_atomic(bad):
    with ReviewStore(":memory:") as store:
        project_id = project(store)
        with pytest.raises(ValueError, match="Record 2"):
            store.import_records(project_id, SearchRunSpec("PubMed"), [record(pmid="100"), bad])
        assert store.list_records(project_id) == []
        assert store.list_search_runs(project_id) == []
        assert store.get_occurrences(project_id) == []


def test_identifier_bridge_and_matching_identifier_conflicts_roll_back():
    with ReviewStore(":memory:") as store:
        project_id = project(store)
        store.import_records(project_id, SearchRunSpec("initial"), [record(doi="10.1234/a", pmid="1"), record(doi="10.1234/b", pmid="2")])
        baseline = store.list_records(project_id), store.list_search_runs(project_id), store.get_occurrences(project_id)
        for conflict in [record(doi="10.1234/a", pmid="2"), record(doi="10.1234/a", pmid="3"), record(doi="10.1234/c", pmid="1")]:
            with pytest.raises(ValueError, match="Conflicting"):
                store.import_records(project_id, SearchRunSpec("conflict"), [record(title="Other", doi="10.1234/valid-new"), conflict])
            assert (store.list_records(project_id), store.list_search_runs(project_id), store.get_occurrences(project_id)) == baseline


def test_fallback_requires_complete_metadata_and_absence_of_strong_identifiers():
    with ReviewStore(":memory:") as store:
        project_id = project(store)
        result = store.import_records(project_id, SearchRunSpec("export"), [
            record(), record(title=" A  TRIAL ", authors=[" SMITH A "]),
            record(year=None), record(year=None),
            record(authors=[]), record(authors=[]),
            record(doi="10.1234/a"), record(doi="10.1234/b"),
            record(pmid="1"), record(pmid="2"),
        ])
        assert result["new_records"] == 9
        assert result["duplicates"] == 1


def test_arxiv_versions_stay_distinct_but_same_version_can_match():
    with ReviewStore(":memory:") as store:
        project_id = project(store)
        result = store.import_records(project_id, SearchRunSpec("arXiv"), [
            record(source_id="arxiv:2401.12345v1"), record(source_id="arxiv:2401.12345v2"),
            record(url="https://arxiv.org/pdf/2401.12345v1.pdf"),
            record(source_id="arxiv:2402.12345v1"),
        ])
        assert result["new_records"] == 3 and result["duplicates"] == 1
        identified = store.import_records(project_id, SearchRunSpec("arXiv"), [
            record(source_id="arxiv:2403.12345v1", doi="10.1234/shared"),
            record(source_id="arxiv:2403.12345v2", doi="10.1234/shared"),
        ])
        assert identified["new_records"] == 1 and identified["duplicates"] == 1


def test_empty_runs_idempotency_and_changed_payload():
    with ReviewStore(":memory:") as store:
        project_id = project(store)
        empty = store.import_records(project_id, SearchRunSpec("PubMed", query="no matches", reported_count=0), [])
        assert empty["identified"] == empty["new_records"] == empty["duplicates"] == 0
        spec = SearchRunSpec("PubMed", query="trials")
        result = store.import_records(project_id, spec, [record()], "key")
        assert store.import_records(project_id, spec, [record()], "key") == result
        assert len(store.list_search_runs(project_id)) == 2
        for changed_spec, changed_records in [(replace(spec, query="different"), [record()]), (spec, [record(raw={"changed": True})])]:
            with pytest.raises(ValueError, match="different payload"):
                store.import_records(project_id, changed_spec, changed_records, "key")
        store.import_records(project_id, spec, [record()])
        counts = store.counts(project_id)
        assert {key: counts[key] for key in ("records_identified", "duplicate_records_removed", "unique_records")} == {"records_identified": 2, "duplicate_records_removed": 1, "unique_records": 1}
        assert counts["all_checks_passed"]


def test_reported_count_does_not_understate_import():
    with ReviewStore(":memory:") as store:
        project_id = project(store)
        with pytest.raises(ValueError, match="smaller"):
            store.import_records(project_id, SearchRunSpec("PubMed", reported_count=0), [record()])
        assert not store.list_search_runs(project_id)


@pytest.mark.parametrize("value", ["10.1234/ABC", "doi: 10.1234/ABC", "HTTPS://DOI.ORG/10.1234/ABC", "http://dx.doi.org/10.1234/ABC"])
def test_doi_forms(value):
    assert normalize_doi(value) == "10.1234/abc"


@pytest.mark.parametrize("value", ["00123", "PMID: 123", "https://pubmed.ncbi.nlm.nih.gov/123/", "http://www.ncbi.nlm.nih.gov/pubmed/123"])
def test_pmid_forms(value):
    assert normalize_pmid(value) == "123"


@pytest.mark.parametrize("value", ["abc", "10.123/a", "https://example.com/10.1234/a", "10.1234/a b"])
def test_bad_doi(value):
    with pytest.raises(ValueError):
        normalize_doi(value)


@pytest.mark.parametrize("value", ["abc", "0", "https://pubmed.ncbi.nlm.nih.gov/123/extra", "https://example.com/123"])
def test_bad_pmid(value):
    with pytest.raises(ValueError):
        normalize_pmid(value)


def test_foreign_keys_enforce_project_pairing():
    with ReviewStore(":memory:") as store:
        first, second = project(store), project(store, "Second")
        result = store.import_records(first, SearchRunSpec("PubMed"), [record()])
        record_id = store.list_records(first)[0]["id"]
        with pytest.raises(sqlite3.IntegrityError):
            with store._connection:
                store._connection.execute("INSERT INTO occurrences VALUES (?, ?, ?, ?, ?, ?)", ("bad", second, result["search_run_id"], record_id, 2, "{}"))


def one_record(store):
    project_id = project(store)
    store.import_records(project_id, SearchRunSpec("PubMed"), [record()])
    return project_id, store.list_records(project_id)[0]["id"]


def state(store, project_id, key="title_abstract_state"):
    return store.list_records(project_id)[0][key]


def test_reviewer_revisions_disagreement_and_adjudication_are_append_only(monkeypatch):
    monkeypatch.setattr("src.review.store._now", lambda: "2026-10-03T00:00:00+00:00")
    with ReviewStore(":memory:") as store:
        project_id, record_id = one_record(store)
        assert state(store, project_id) == "pending"
        first = store.record_decision(project_id, record_id, "title_abstract", "include", "Alice")
        assert state(store, project_id) == "include"
        store.record_decision(project_id, record_id, "title_abstract", "exclude", "Bob", "Wrong population")
        assert state(store, project_id) == "conflict"
        store.adjudicate(project_id, record_id, "title_abstract", "include", "Lead", "Population verified")
        assert state(store, project_id) == "include"
        store.record_decision(project_id, record_id, "title_abstract", "uncertain", "Alice", "Need full text")
        assert state(store, project_id) == "conflict"
        store.record_decision(project_id, record_id, "title_abstract", "uncertain", "Bob", "Need full text too")
        assert state(store, project_id) == "uncertain"
        events = store.list_decisions(project_id, record_id)
        assert len(events) == 5
        assert events[0] == first
        assert [event["kind"] for event in events] == ["review", "review", "adjudication", "review", "review"]
        assert len({event["created_at"] for event in events}) == 1
        assert store.counts(project_id)["records_screening_unresolved"] == 1
        assert store.counts(project_id)["records_excluded"] == 0


@pytest.mark.parametrize("method,args", [
    ("record_decision", ("invalid", "include", "Alice", "")),
    ("record_decision", ("title_abstract", "invalid", "Alice", "")),
    ("record_decision", ("title_abstract", "include", " ", "")),
    ("record_decision", ("title_abstract", "exclude", "Alice", " ")),
    ("adjudicate", ("title_abstract", "include", "Alice", "")),
    ("adjudicate", ("title_abstract", "include", "Alice", "No decisions yet")),
    ("record_decision", ("full_text", "include", "Alice", "")),
    ("set_full_text_status", ("requested", "Alice", "")),
])
def test_invalid_screening_activity_leaves_no_events(method, args):
    with ReviewStore(":memory:") as store:
        project_id, record_id = one_record(store)
        with pytest.raises(ValueError):
            getattr(store, method)(project_id, record_id, *args)
        assert store.list_decisions(project_id) == []
        assert store.list_retrieval_events(project_id) == []


def test_retrieval_prerequisites_terminality_and_ta_rollback():
    with ReviewStore(":memory:") as store:
        project_id, record_id = one_record(store)
        store.record_decision(project_id, record_id, "title_abstract", "include", "Alice")
        store.set_full_text_status(project_id, record_id, "requested", "Librarian")
        with pytest.raises(ValueError, match="retrieved"):
            store.record_decision(project_id, record_id, "full_text", "include", "Alice")
        store.set_full_text_status(project_id, record_id, "not_retrieved", "Librarian", "Unavailable")
        store.set_full_text_status(project_id, record_id, "requested", "Librarian", "Retry")
        store.set_full_text_status(project_id, record_id, "retrieved", "Librarian")
        for status in ("requested", "not_retrieved"):
            with pytest.raises(ValueError, match="terminal"):
                store.set_full_text_status(project_id, record_id, status, "Librarian", "Attempt downgrade")
        initial_decisions = store.list_decisions(project_id)
        for decision in ("uncertain", "exclude"):
            with pytest.raises(ValueError, match="remain include"):
                store.record_decision(project_id, record_id, "title_abstract", decision, "Bob", "Late conflict")
            assert store.list_decisions(project_id) == initial_decisions
        store.record_decision(project_id, record_id, "title_abstract", "include", "Bob")
        store.record_decision(project_id, record_id, "full_text", "exclude", "Alice", "Outcome ineligible")
        assert state(store, project_id, "full_text_state") == "exclude"
        assert len(store.list_retrieval_events(project_id)) == 4
        counts = store.counts(project_id)
        assert counts["reports_assessed"] == counts["reports_excluded"] == 1
        assert counts["included_studies"] is None
        assert counts["study_linkage_available"] is False
        assert counts["all_checks_passed"]


def test_late_review_cannot_invalidate_adjudicated_ta_inclusion_after_retrieval():
    with ReviewStore(":memory:") as store:
        project_id, record_id = one_record(store)
        store.record_decision(project_id, record_id, "title_abstract", "include", "Alice")
        store.record_decision(project_id, record_id, "title_abstract", "exclude", "Bob", "Population")
        store.adjudicate(project_id, record_id, "title_abstract", "include", "Lead", "Resolved")
        store.set_full_text_status(project_id, record_id, "requested", "Librarian")
        with pytest.raises(ValueError, match="remain include"):
            store.record_decision(project_id, record_id, "title_abstract", "include", "Charlie")
        assert state(store, project_id) == "include"
        assert len(store.list_decisions(project_id)) == 3
        store.record_decision(project_id, record_id, "title_abstract", "include", "Bob")
        assert state(store, project_id) == "include"


def test_all_flow_buckets_reconcile_independently():
    with ReviewStore(":memory:") as store:
        project_id = project(store)
        store.import_records(project_id, SearchRunSpec("PubMed"), [record(title=f"Paper {i}", pmid=str(i + 1)) for i in range(9)])
        ids = [item["id"] for item in store.list_records(project_id)]
        # One pending, one excluded, one unresolved; six TA-included reports.
        store.record_decision(project_id, ids[1], "title_abstract", "exclude", "Alice", "Ineligible")
        store.record_decision(project_id, ids[2], "title_abstract", "uncertain", "Alice")
        for record_id in ids[3:]:
            store.record_decision(project_id, record_id, "title_abstract", "include", "Alice")
        # Included report buckets: unrequested, requested, unavailable, retrieved pending,
        # retrieved included, retrieved unresolved.
        store.set_full_text_status(project_id, ids[4], "requested", "Librarian")
        store.set_full_text_status(project_id, ids[5], "not_retrieved", "Librarian", "Unavailable")
        for record_id in ids[6:]:
            store.set_full_text_status(project_id, record_id, "retrieved", "Librarian")
        store.record_decision(project_id, ids[7], "full_text", "include", "Alice")
        store.record_decision(project_id, ids[8], "full_text", "uncertain", "Alice")
        expected = {
            "records_identified": 9, "duplicate_records_removed": 0, "unique_records": 9,
            "records_awaiting_screening": 1, "records_screened": 8, "records_excluded": 1,
            "records_screening_unresolved": 1, "records_included_for_full_text": 6,
            "reports_awaiting_request": 1, "reports_sought_for_retrieval": 5,
            "reports_awaiting_retrieval": 1, "reports_not_retrieved": 1, "reports_retrieved": 3,
            "reports_awaiting_assessment": 1, "reports_assessed": 2, "reports_included": 1,
            "reports_excluded": 0, "reports_assessment_unresolved": 1,
        }
        counts = store.counts(project_id)
        assert {key: counts[key] for key in expected} == expected
        assert counts["reconciliation"] == {key: True for key in ("identification", "screening_progress", "title_abstract", "retrieval_requests", "retrieval_progress", "assessment_progress", "full_text")}
        assert counts["all_checks_passed"]


def test_screening_and_retrieval_history_reject_cross_project_records():
    with ReviewStore(":memory:") as store:
        project_id, record_id = one_record(store)
        other = project(store, "Other")
        for method, arguments in [
            (store.record_decision, ("title_abstract", "include", "Alice")),
            (store.adjudicate, ("title_abstract", "include", "Lead", "Reason")),
            (store.set_full_text_status, ("requested", "Librarian")),
            (store.list_decisions, ()), (store.list_retrieval_events, ()),
        ]:
            with pytest.raises(ValueError, match="Unknown record"):
                method(other, record_id, *arguments)
        assert store.counts(project_id)["records_awaiting_screening"] == 1
