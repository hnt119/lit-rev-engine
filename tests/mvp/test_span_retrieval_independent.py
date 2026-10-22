"""Source-first development regressions and independent exact-quotation metrics."""
from copy import deepcopy
from hashlib import sha256
import json
import socket

import pytest

from src.mvp.adapters.retrieval import LexicalRetrieval
from src.mvp.adapters.span_retrieval import LexicalSpanRetrieval
from src.mvp.span_evaluation import (DEFAULT_MANIFEST, FROZEN_MANIFEST_SHA256, budget_tokens,
    common_transport_cap, load_frozen_cases, measure_case, run_comparison)
from src.mvp.span_retrieval_contracts import SpanRequirement


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Source-first span evaluation attempted external networking")
    monkeypatch.setattr(socket, "create_connection", denied)


@pytest.fixture(scope="module")
def frozen():
    return load_frozen_cases()


def selection(source, block, start=0, end=None, **extra):
    end = len(block.text) if end is None else end
    return {"source_id": source.id, "paper_id": source.paper_id, "block_id": block.id, "start": start,
        "end": end, "quote": block.text[start:end], "score": 1., "matched_requirement_ids": [], **extra}


def test_manifest_is_frozen_source_first_and_has_no_human_or_heldout_labels(frozen):
    manifest, sources = frozen
    assert sha256(DEFAULT_MANIFEST.read_bytes()).hexdigest() == FROZEN_MANIFEST_SHA256
    assert len(sources) == 11 and len(manifest["cases"]) == 12
    assert sum(len(case["anchors"]) for case in manifest["cases"]) == 21
    assert {case["split"] for case in manifest["cases"]} == {"development"}
    assert {case["label_status"] for case in manifest["cases"]} == {"agent_authored_development"}
    splits = json.loads(DEFAULT_MANIFEST.with_name("split_manifest.json").read_text())
    assert splits["held_out_groups"] == [] and splits["future_human_evaluation"]["status"] == "NOT_RUN"
    assert len({case["related_study_group"] for case in manifest["cases"]}) == 11


def test_late_prefix_regression_repairs_exact_delivered_region_without_changing_b0(frozen):
    manifest, sources = frozen
    case = next(case for case in manifest["cases"] if case["id"] == "late-participant-qualifiers")
    source = sources[case["source_id"]]
    assert all(anchor["start"] > 1200 for anchor in case["anchors"])
    baseline, indexed, matched = LexicalRetrieval().search(case["question"], [source], "unchanged-B0", top_k=3)
    assert indexed == matched == 1 and baseline[0].anchor.start == 0 and baseline[0].anchor.end == len(source.blocks[0].text)
    native_prefix = selection(source, source.blocks[0], end=1200)
    assert measure_case(case, source, [native_prefix])["anchors_covered"] == 0
    found = LexicalSpanRetrieval().search(case["question"], [source], "exact-delivered-B1", top_k=3)
    delivered = [item.model_dump(mode="json") for item in found.selections]
    metrics = measure_case(case, source, delivered)
    assert metrics["anchors_covered"] == metrics["components_covered"] == 3
    assert any(item.start > 0 for item in found.selections)
    assert found.indexed_windows > 1 and found.indexed_blocks == 1


@pytest.mark.parametrize("case_id", ["late-participant-qualifiers", "unicode-crlf-negation", "negation-outcome",
    "population-not-author-affiliation", "external-validation-cohort", "table-heading-row-footnote", "abstract-population"])
def test_explicit_frozen_synthetic_components_retain_all_required_exact_anchors(frozen, case_id):
    manifest, sources = frozen
    case = next(case for case in manifest["cases"] if case["id"] == case_id)
    source = sources[case["source_id"]]
    before = source.model_dump_json()
    requirements = [SpanRequirement(id=value["id"], label=value["id"], query=value["text"]) for value in case["requirements"]]
    result = LexicalSpanRetrieval().search(case["question"], [source], case_id, top_k=3, requirements=requirements)
    metrics = measure_case(case, source, [value.model_dump(mode="json") for value in result.selections])
    assert metrics["all_answerable_components_covered"]
    assert metrics["duplicate_exact_references"] == 0 and metrics["maximum_pairwise_shorter_span_overlap"] < .5
    assert source.model_dump_json() == before and result.meaning == "potential_relevance_not_inspected_support"
    assert not result.unindexed_characters and len(result.selections) <= 3
    if case_id == "unicode-crlf-negation":
        assert "\r\n" in source.blocks[0].text and "🧬" in source.blocks[0].text
        assert any("did not increase" in value.quote and "−0.7" in value.quote for value in result.selections)


@pytest.mark.parametrize("change", ["paper", "source", "block", "quote", "start"])
def test_independent_measurement_rejects_wrong_ownership_or_inexact_anchors(frozen, change):
    manifest, sources = frozen
    case = next(case for case in manifest["cases"] if case["id"] == "negation-outcome")
    source = sources[case["source_id"]]
    span = selection(source, source.blocks[0])
    span.update({"paper": {"paper_id": "wrong-paper"}, "source": {"source_id": "wrong-source"},
        "block": {"block_id": "unknown"}, "quote": {"quote": span["quote"] + "invented"}, "start": {"start": 1}}[change])
    with pytest.raises(ValueError):
        measure_case(case, source, [span])


def test_exact_but_irrelevant_quote_and_self_reported_component_ids_do_not_earn_coverage(frozen):
    manifest, sources = frozen
    case = next(case for case in manifest["cases"] if case["id"] == "population-not-author-affiliation")
    source = sources[case["source_id"]]
    affiliation = selection(source, source.blocks[0], matched_requirement_ids=["origin", "setting"])
    metrics = measure_case(case, source, [affiliation])
    assert metrics["anchors_covered"] == metrics["components_covered"] == 0
    assert metrics["returned_references"] == 1


def test_removing_negation_can_still_be_an_exact_quote_but_fails_the_fixed_qualifier_anchor(frozen):
    manifest, sources = frozen
    case = next(case for case in manifest["cases"] if case["id"] == "negation-outcome")
    source = sources[case["source_id"]]
    block = source.blocks[0]
    start = block.text.index("improve ovarian reserve")
    fragment = selection(source, block, start=start, end=start + len("improve ovarian reserve"))
    metrics = measure_case(case, source, [fragment])
    assert metrics["anchors_covered"] == 0 and not metrics["all_answerable_components_covered"]


def test_shared_span_covers_multiple_components_without_duplicate_context_and_duplicates_are_measured(frozen):
    manifest, sources = frozen
    case = next(case for case in manifest["cases"] if case["id"] == "late-participant-qualifiers")
    source = sources[case["source_id"]]
    start = min(anchor["start"] for anchor in case["anchors"]) - len("The intervention cohort comprised ")
    one = selection(source, source.blocks[0], start=start)
    metrics = measure_case(case, source, [one])
    assert metrics["components_covered"] == 3 and metrics["returned_references"] == 1 and metrics["overlapping_characters"] == 0
    duplicate = measure_case(case, source, [one, one])
    assert duplicate["duplicate_exact_references"] == 1 and duplicate["maximum_pairwise_shorter_span_overlap"] == 1
    assert duplicate["overlapping_characters"] == len(one["quote"])


def test_evaluation_only_transport_cap_is_explicit_and_does_not_change_native_input():
    native = [{"source_id": "s", "paper_id": "p", "block_id": "b", "start": 15, "end": 1015,
        "quote": "!" * 1000, "score": 1., "matched_requirement_ids": []}]
    saved = deepcopy(native)
    delivered = common_transport_cap(native)
    assert native == saved and len(delivered[0]["quote"]) == budget_tokens(delivered[0]["quote"]) == 400
    assert delivered[0]["start"] == 15 and delivered[0]["end"] == 415


def test_abstract_and_no_answer_candidates_do_not_claim_absence_or_support(frozen):
    manifest, sources = frozen
    for case in manifest["cases"]:
        if case["answerability"] == "answerable": continue
        source = sources[case["source_id"]]
        result = LexicalSpanRetrieval().search(case["question"], [source], case["id"], top_k=3)
        metrics = measure_case(case, source, [value.model_dump(mode="json") for value in result.selections])
        assert metrics["anchors_expected"] == metrics["components_expected"] == 0
        assert metrics["insufficient_context_nonempty_candidates"] is True
        assert metrics["meaning"] == "fixed_development_anchor_coverage_not_semantic_recall_or_human_support"


def test_frozen_comparison_reports_correlated_denominators_native_budgets_and_remaining_misses():
    report = run_comparison()
    assert len(report["records"]) == 36 and all(report["gates"].values())
    totals = {}
    for lane in ("B0_question_prefix", "B1_question_only", "B1_explicit_components"):
        rows = [item for item in report["summaries"] if item["lane"] == lane]
        totals[lane] = tuple(sum(row[key] for row in rows) for key in ("anchors_covered", "anchors_expected", "all_components_covered_cases", "answerable_cases"))
    assert totals == {"B0_question_prefix": (12, 21, 5, 10), "B1_question_only": (15, 21, 6, 10), "B1_explicit_components": (21, 21, 10, 10)}
    assert report["primary_comparison"] == ["B0_question_prefix", "B1_question_only"]
    assert report["primary_per_case_anchor_regressions"] == []
    assert all(not row["transport_cap_changed_delivery"] and not any(row["native_budget_violations"].values()) for row in report["records"])
    assert report["human_usefulness"] == report["held_out_validation"] == report["generation"] == "NOT_RUN"


def test_manifest_tampering_is_rejected_before_retrieval(tmp_path):
    path = tmp_path / "altered.json"
    path.write_bytes(DEFAULT_MANIFEST.read_bytes() + b" ")
    with pytest.raises(ValueError, match="manifest changed"):
        load_frozen_cases(path)
