"""Independent public-API evidence for reproducible review ledger acceptance."""

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys

import pytest

from src.review.importers import load_records
from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.store import ReviewStore


FIXTURES = Path(__file__).parent / "fixtures" / "review"
ROOT = Path(__file__).resolve().parents[1]


def project(store, title="Postoperative monitoring", review_type="systematic"):
    return store.create_project(
        title=title,
        review_type=review_type,
        question="Which monitoring strategies improve postoperative outcomes?",
        protocol="Prospective review protocol version 1",
        eligibility={"population": "Adults", "designs": ["randomized", "cohort"]},
    )


def spec(source="PubMed", **overrides):
    fields = {
        "source": source,
        "query": '("Postoperative Care"[MeSH Terms]) AND monitoring',
        "searched_at": "2026-10-03T01:23:45+08:00",
        "filters": {"year": {"from": 2020, "to": 2026}, "language": ["English"]},
        "notes": "Exported first eight results of 42 reported hits",
        "import_format": "json",
        "source_file": "medical_records.json",
        "source_sha256": "1" * 64,
        "reported_count": 42,
    }
    fields.update(overrides)
    return SearchRunSpec(**fields)


def snapshot(store, project_id):
    return deepcopy({
        "runs": store.list_search_runs(project_id),
        "records": store.list_records(project_id),
        "occurrences": store.get_occurrences(project_id),
        "counts": store.counts(project_id),
    })


def assert_counts(store, project_id, identified, duplicates, unique):
    counts = store.counts(project_id)
    assert counts["records_identified"] == identified
    assert counts["duplicate_records_removed"] == duplicates
    assert counts["unique_records"] == unique
    assert identified == duplicates + unique
    return counts


def test_known_bibliography_reconciles_and_preserves_conflicting_occurrences(tmp_path):
    records = load_records(FIXTURES / "medical_records.json")
    followup = load_records(FIXTURES / "medical_followup.json")
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = project(store)["id"]
        first = store.import_records(project_id, spec(), records)
        assert {key: first[key] for key in ("identified", "new_records", "duplicates")} == {
            "identified": 8, "new_records": 6, "duplicates": 2,
        }
        assert_counts(store, project_id, 8, 2, 6)
        second = store.import_records(project_id, spec(source_file="medical_followup.json"), followup)
        assert {key: second[key] for key in ("identified", "new_records", "duplicates")} == {
            "identified": 2, "new_records": 1, "duplicates": 1,
        }
        assert_counts(store, project_id, 10, 3, 7)

        canonical = store.list_records(project_id)
        renal = next(row for row in canonical if row["pmid"] == "39001001")
        assert renal["doi"] == "10.5555/renal-a"
        assert renal["title"] == records[0].title
        assert renal["authors"] == records[0].authors
        assert renal["year"] == 2024
        assert renal["abstract"] == records[1].abstract
        assert renal["url"] == records[1].url
        assert len([row for row in canonical if row["title"] == records[2].title]) == 2
        renal_occurrences = store.get_occurrences(project_id, renal["id"])
        assert len(renal_occurrences) == 3
        assert [row["record"] for row in renal_occurrences] == [
            asdict(records[0]), asdict(records[1]), asdict(followup[0]),
        ]
        occurrences = store.get_occurrences(project_id)
        assert len(occurrences) == 10
        original_occurrences = [row for row in occurrences if row["search_run_id"] == first["search_run_id"]]
        assert len({row["ordinal"] for row in original_occurrences}) == 8
        assert [row["record"] for row in original_occurrences] == [asdict(row) for row in records]
        assert all(row["record_id"] in {record["id"] for record in canonical} for row in occurrences)
        assert original_occurrences[0]["record"]["raw"]["database_note"].startswith("First indexed")


def test_persistence_search_history_and_inputs_are_snapshotted(tmp_path):
    database = tmp_path / "nested" / "reviews.sqlite3"
    with ReviewStore(database) as store:
        created = project(store)
        project_id = created["id"]
        original_spec = spec()
        records = load_records(FIXTURES / "medical_records.json")
        expected_spec = deepcopy(asdict(original_spec))
        store.import_records(project_id, original_spec, records)
        original_spec.filters["language"].append("Changed after import")
        records[0].raw["database_note"] = "Changed after import"
        stored_run = store.list_search_runs(project_id)[0]
        for field, expected in expected_spec.items():
            assert stored_run[field] == expected
        assert stored_run["identified"] == 8
        assert stored_run["reported_count"] == 42
        timestamp = datetime.fromisoformat(stored_run["created_at"].replace("Z", "+00:00"))
        assert timestamp.utcoffset().total_seconds() == 0
        stored_run["filters"]["language"].append("Changed returned data")
        before = snapshot(store, project_id)
        store.import_records(project_id, spec(query=None, searched_at=None, reported_count=0), [])
        runs = store.list_search_runs(project_id)
        assert runs[0] == before["runs"][0]
        assert runs[1]["query"] is None
        assert runs[1]["searched_at"] is None
        assert {key: runs[1][key] for key in ("identified", "new_records", "duplicates")} == {
            "identified": 0, "new_records": 0, "duplicates": 0,
        }
        expected = snapshot(store, project_id)
    with ReviewStore(database) as reopened:
        assert reopened.get_project(project_id) == created
        assert reopened.list_projects() == [created]
        assert snapshot(reopened, project_id) == expected
        assert_counts(reopened, project_id, 8, 2, 6)
        assert reopened.get_occurrences(project_id)[0]["record"]["raw"]["database_note"].startswith("First indexed")


def test_two_projects_have_independent_identifiers_and_idempotency_keys(tmp_path):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        first_id = project(store)["id"]
        second_id = project(store, "Oxygen scoping review", "scoping")["id"]
        records = load_records(FIXTURES / "medical_records.json")
        first = store.import_records(first_id, spec(), records, idempotency_key="import-001")
        second = store.import_records(second_id, spec(), records, idempotency_key="import-001")
        assert first["search_run_id"] != second["search_run_id"]
        assert_counts(store, first_id, 8, 2, 6)
        assert_counts(store, second_id, 8, 2, 6)
        first_records = store.list_records(first_id)
        second_records = store.list_records(second_id)
        assert {row["id"] for row in first_records}.isdisjoint({row["id"] for row in second_records})
        assert all(row["project_id"] == first_id for row in first_records)
        with pytest.raises(ValueError):
            store.get_occurrences(first_id, second_records[0]["id"])
        assert len(store.list_projects()) == 2


@pytest.mark.parametrize("mutation", ["query", "metadata", "raw"])
def test_idempotency_replays_only_an_identical_payload(tmp_path, mutation):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = project(store)["id"]
        records = load_records(FIXTURES / "medical_records.json")
        original_spec = spec()
        first = store.import_records(project_id, original_spec, records, idempotency_key="stable")
        before = snapshot(store, project_id)
        assert store.import_records(project_id, original_spec, records, idempotency_key="stable") == first
        assert snapshot(store, project_id) == before
        changed_records = deepcopy(records)
        changed_spec = original_spec
        if mutation == "query":
            changed_spec = replace(original_spec, query="Different exact search")
        elif mutation == "metadata":
            changed_records[0] = replace(changed_records[0], abstract="New payload")
        else:
            changed_records[0].raw["database_note"] = "Changed raw provenance only"
        with pytest.raises(ValueError):
            store.import_records(project_id, changed_spec, changed_records, idempotency_key="stable")
        assert snapshot(store, project_id) == before
        store.import_records(project_id, original_spec, records)
        # The no-ID/no-author row cannot safely fallback-match even on a replay.
        # A caller must supply an idempotency key to avoid treating it as a new run.
        assert_counts(store, project_id, 16, 9, 7)
        assert len(store.list_search_runs(project_id)) == 2


@pytest.mark.parametrize("bad_record", [
    BibliographicRecord(title=""),
    BibliographicRecord(title="Invalid DOI", doi="not a DOI"),
    BibliographicRecord(title="Invalid PMID", pmid="39001x"),
])
def test_invalid_later_record_rolls_back_complete_import(tmp_path, bad_record):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = project(store)["id"]
        store.import_records(project_id, spec(), [BibliographicRecord(title="Prior record", doi="10.5555/prior")])
        before = snapshot(store, project_id)
        with pytest.raises(ValueError):
            store.import_records(project_id, spec(), [BibliographicRecord(title="Valid new row", doi="10.5555/new"), bad_record])
        assert snapshot(store, project_id) == before


@pytest.mark.parametrize("conflicting", [
    BibliographicRecord(title="Bridge", doi="10.5555/bridge-a", pmid="39002002"),
    BibliographicRecord(title="Conflicting DOI on matching PMID", doi="10.5555/other", pmid="39002001"),
    BibliographicRecord(title="Conflicting PMID on matching DOI", doi="10.5555/bridge-a", pmid="39002003"),
])
def test_identifier_conflicts_never_merge_reports_or_mutate_prior_data(tmp_path, conflicting):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = project(store)["id"]
        store.import_records(project_id, spec(), [
            BibliographicRecord(title="Existing A", doi="10.5555/bridge-a", pmid="39002001"),
            BibliographicRecord(title="Existing B", doi="10.5555/bridge-b", pmid="39002002"),
        ])
        before = snapshot(store, project_id)
        with pytest.raises(ValueError):
            store.import_records(project_id, spec(), [BibliographicRecord(title="Valid new first", doi="10.5555/new"), conflicting])
        assert snapshot(store, project_id) == before


def test_conflicting_identifiers_within_first_import_roll_back_everything(tmp_path):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = project(store)["id"]
        before = snapshot(store, project_id)
        with pytest.raises(ValueError):
            store.import_records(project_id, spec(), [
                BibliographicRecord(title="A", doi="10.5555/same", pmid="39002001"),
                BibliographicRecord(title="B", doi="10.5555/same", pmid="39002002"),
            ])
        assert snapshot(store, project_id) == before


@pytest.mark.parametrize("shared_doi,expected_unique", [(None, 2), ("10.5555/preprint", 1)])
def test_arxiv_version_identity_overrides_weak_title_fallback(tmp_path, shared_doi, expected_unique):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = project(store)["id"]
        records = [
            BibliographicRecord(title="Monitoring preprint", authors=["Ada Ng"], year=2025,
                                doi=shared_doi, source_id=f"https://arxiv.org/abs/2501.12345v{version}")
            for version in (1, 2)
        ]
        store.import_records(project_id, spec(source="arXiv"), records)
        assert_counts(store, project_id, 2, 2 - expected_unique, expected_unique)


def test_incomplete_fallback_does_not_merge_title_only_records(tmp_path):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = project(store)["id"]
        records = [
            BibliographicRecord(title="Same medical title"),
            BibliographicRecord(title="Same medical title"),
            BibliographicRecord(title="Same medical title", authors=["Ada Ng"]),
            BibliographicRecord(title="Same medical title", authors=["Ada Ng"]),
            BibliographicRecord(title="Same medical title", year=2024),
            BibliographicRecord(title="Same medical title", year=2024),
        ]
        store.import_records(project_id, spec(), records)
        assert_counts(store, project_id, 6, 0, 6)


def test_missing_identifier_can_be_filled_without_overwriting_first_metadata(tmp_path):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = project(store)["id"]
        store.import_records(project_id, spec(), [BibliographicRecord(title="First title", doi="10.5555/fill")])
        store.import_records(project_id, spec(), [
            BibliographicRecord(title="Conflicting later title", doi="10.5555/fill", pmid="39004001",
                                authors=["Ada Ng"], year=2024, abstract="Filled abstract"),
        ])
        canonical = store.list_records(project_id)[0]
        assert canonical["title"] == "First title"
        assert canonical["pmid"] == "39004001"
        assert canonical["authors"] == ["Ada Ng"]
        assert canonical["year"] == 2024
        assert canonical["abstract"] == "Filled abstract"
        store.import_records(project_id, spec(), [BibliographicRecord(title="Third", pmid="39004001")])
        assert_counts(store, project_id, 3, 2, 1)


def test_zero_results_and_reported_total_do_not_invent_imported_records(tmp_path):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = project(store)["id"]
        result = store.import_records(project_id, spec(query=None, searched_at=None, reported_count=12), [])
        assert result["identified"] == result["new_records"] == result["duplicates"] == 0
        assert_counts(store, project_id, 0, 0, 0)
        assert store.list_records(project_id) == store.get_occurrences(project_id) == []
        runs = store.list_search_runs(project_id)
        assert len(runs) == 1 and runs[0]["reported_count"] == 12
        before = snapshot(store, project_id)
        with pytest.raises(ValueError):
            store.import_records(project_id, spec(reported_count=0), [BibliographicRecord(title="One occurrence")])
        assert snapshot(store, project_id) == before


def test_unknown_projects_and_records_are_rejected(tmp_path):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        project_id = project(store)["id"]
        for call in (
            lambda: store.get_project("unknown"),
            lambda: store.list_search_runs("unknown"),
            lambda: store.list_records("unknown"),
            lambda: store.get_occurrences("unknown"),
            lambda: store.counts("unknown"),
            lambda: store.import_records("unknown", spec(), []),
            lambda: store.get_occurrences(project_id, "unknown-record"),
        ):
            with pytest.raises(ValueError):
                call()
        assert_counts(store, project_id, 0, 0, 0)


@pytest.mark.parametrize("title,review_type,question", [
    ("", "systematic", "Question"),
    ("Title", "rapid", "Question"),
    ("Title", "scoping", "  "),
])
def test_invalid_projects_cannot_create_partial_entries(tmp_path, title, review_type, question):
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        with pytest.raises(ValueError):
            store.create_project(title, review_type, question)
        assert store.list_projects() == []


def test_ris_pubmed_xml_preserve_metadata_and_identifier_authority(monkeypatch):
    def no_network(*args, **kwargs):
        pytest.fail("Offline XML/RIS import attempted network access")
    monkeypatch.setattr("socket.create_connection", no_network)
    ris = load_records(FIXTURES / "medical_exports.ris")
    xml = load_records(FIXTURES / "medical_exports.xml")
    assert len(ris) == len(xml) == 2
    assert [record.title for record in ris] == [record.title for record in xml] == [
        "Oxygen targets in acute care", "Safety of discharge counselling",
    ]
    assert [record.year for record in ris] == [record.year for record in xml] == [2021, 2020]
    assert ris[0].pmid == xml[0].pmid == "39003001"
    assert ris[1].pmid is None and ris[1].source_id == "39003002"
    assert xml[1].pmid == "39003002"
    for record in (ris[0], xml[0]):
        assert "Compare oxygen targets." in record.abstract
        assert "Mortality was assessed at 30 days." in record.abstract
        assert "Oxygen Collaboration" in record.authors
        assert any("Ada" in author and "Ng" in author for author in record.authors)
        assert "39003001" in record.url
        assert record.raw
    assert "acute" in json.dumps(xml[0].raw)
    assert "Local Research Archive" in json.dumps(ris[1].raw)


@pytest.mark.parametrize("suffix,content", [
    ("json", "[]"),
    ("xml", "<PubmedArticleSet />"),
])
def test_zero_result_import_files_are_valid(tmp_path, suffix, content):
    path = tmp_path / f"zero.{suffix}"
    path.write_text(content, encoding="utf-8")
    assert load_records(path) == []


@pytest.mark.parametrize("suffix,content", [
    ("json", '[{"title":"Good"},{"title":"Bad DOI","doi":"broken"}]'),
    ("json", '[{"title":"Good"},{"title":"Bad PMID","pmid":"12x"}]'),
    ("json", '[{"title":"Good"},{"title":""}]'),
    ("json", '{"title":"Not a record array"}'),
    ("json", '[{"title":'),
    ("ris", "TY  - JOUR\nTI  - Missing ER\n"),
    ("ris", "TY  - JOUR\nTI  - Bad DOI\nDO  - broken\nER  -\n"),
    ("xml", "<PubmedArticleSet><PubmedArticle>"),
    ("xml", '<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///etc/passwd">]><PubmedArticleSet />'),
    ("xml", "<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>12x</PMID><Article><ArticleTitle>Title</ArticleTitle></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"),
])
def test_malformed_inputs_fail_contextually_without_returning_partial_records(tmp_path, suffix, content):
    path = tmp_path / f"malformed.{suffix}"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError) as failure:
        load_records(path)
    message = str(failure.value)
    assert message.strip()
    assert any(context in message.lower() for context in ("record", "line", "xml", "json", "ris", "entity"))


def test_explicit_format_and_unsupported_extension_are_unambiguous(tmp_path):
    path = tmp_path / "export.bin"
    path.write_text('[{"title":"Synthetic report","extra_field":"Retain me"}]', encoding="utf-8")
    with pytest.raises(ValueError):
        load_records(path)
    records = load_records(path, format="json")
    assert len(records) == 1
    assert records[0].raw["extra_field"] == "Retain me"
    with pytest.raises(ValueError):
        load_records(path, format="xlsx")


def test_review_workflow_loads_without_embedding_models_keys_or_network(tmp_path):
    # A fresh interpreter catches accidental third-party imports hidden by the main suite.
    code = """
import socket, sys
sys.path.insert(0, sys.argv[1])
def denied(*args, **kwargs):
    raise AssertionError('Review workflow attempted a network call')
socket.create_connection = denied
from src.review.store import ReviewStore
from src.review.importers import load_records
from src.review.models import SearchRunSpec
with ReviewStore(sys.argv[2]) as store:
    pid = store.create_project('Synthetic review', 'scoping', 'What evidence exists?')['id']
    store.import_records(pid, SearchRunSpec(source='Local export'), load_records(sys.argv[3]))
    assert store.counts(pid)['unique_records'] == 6
assert not {'torch', 'chromadb', 'sentence_transformers', 'dotenv'}.intersection(sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(ROOT), str(tmp_path / "isolated.sqlite3"), str(FIXTURES / "medical_records.json")],
        cwd=tmp_path, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
