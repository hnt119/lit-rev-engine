"""Frozen, source-first development comparison; no model or provider calls.

These exact-anchor metrics are deliberately narrower than semantic usefulness.
Model-reported component matches never count as independently checked coverage.
"""
from collections import defaultdict
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import time

from .contracts import PreparedSource, SearchRequest, digest, now

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "tests/fixtures/span_retrieval_v1/manifest.json"
FROZEN_MANIFEST_SHA256 = "437888582ab4fb82ee647b24b4e40f9a2c1ca9b4ff34a5bd6120fa28fb81390e"
TOKENIZER_ID = "unicode-word-or-nonspace-punctuation-v1"
TRANSPORT_CAP_ID = "evaluation_only.max3-ref1200chars400proxyTokens.v1"
_BUDGET_TOKEN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def budget_tokens(text):
    return len(_BUDGET_TOKEN.findall(text))


def load_frozen_cases(path=DEFAULT_MANIFEST, *, expected_sha256=FROZEN_MANIFEST_SHA256):
    """Read only synthetic fixtures and the checked, already local public pack."""
    raw = Path(path).read_bytes()
    if sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Source-first manifest changed; create an explicitly versioned evaluation.")
    manifest = json.loads(raw)
    if (manifest.get("schema_version") != "mvp.span-source-first-development.v1"
            or manifest.get("label_status") != "synthetic_and_agent_authored_public_development_not_human_gold"
            or not manifest.get("frozen_before_b1_runs")):
        raise ValueError("Unknown source-first development manifest or label provenance.")
    budgets = manifest["budgets"]
    if budgets != {"max_references": 3, "max_characters": 3600, "max_budget_tokens": 1200,
            "max_characters_per_reference": 1200, "max_tokens_per_reference": 400, "budget_tokenizer": TOKENIZER_ID}:
        raise ValueError("This comparison requires its exact frozen common budget.")
    sources = {}
    public = None
    for entry in manifest["sources"]:
        if entry["id"] in sources or entry["split"] != "development":
            raise ValueError("Duplicate source or undeclared held-out split.")
        if entry["kind"] == "synthetic":
            source = PreparedSource.model_validate(entry["source"])
        elif entry["kind"] == "public_development":
            if public is None:
                from .adapters.saved_examples import SavedExampleProvider
                provider = SavedExampleProvider()
                papers = provider.search(SearchRequest(request_id="span-development-source-read",
                    query="Not executed: checked local licensed development fixtures", max_results=30)).papers
                public = {paper.pmcid: provider.prepare(paper) for paper in papers}
            source = public[entry["pmcid"]].model_copy(update={"id": entry["id"]})
            for name in ("paper_id", "source_sha256", "blocks_sha256", "parser_id", "license"):
                if getattr(source, name) != entry[name]:
                    raise ValueError("The checked public development source changed.")
        else:
            raise ValueError("Only synthetic and checked local public development sources are supported.")
        if source.id != entry["id"] or source.blocks_sha256 != digest([block.model_dump(mode="json") for block in source.blocks]):
            raise ValueError("Development source blocks or identity changed.")
        if source.retained_content_utf8 is None or sha256(source.retained_content_utf8.encode()).hexdigest() != source.source_sha256:
            raise ValueError("Development retained source bytes changed.")
        sources[source.id] = source
    seen = set()
    for case in manifest["cases"]:
        if case["id"] in seen or case["split"] != "development" or case["label_status"] != "agent_authored_development":
            raise ValueError("Duplicate case or unsupported label/split claim.")
        seen.add(case["id"])
        source = sources[case["source_id"]]
        if case["paper_id"] != source.paper_id:
            raise ValueError("An evaluation case belongs to the wrong paper.")
        blocks = {block.id: block for block in source.blocks}
        anchors = {anchor["id"]: anchor for anchor in case["anchors"]}
        if len(anchors) != len(case["anchors"]):
            raise ValueError("Duplicate fixed anchor.")
        for anchor in anchors.values():
            block = blocks[anchor["block_id"]]
            if not 0 <= anchor["start"] < anchor["end"] <= len(block.text) or block.text[anchor["start"]:anchor["end"]] != anchor["quote"]:
                raise ValueError("A fixed anchor no longer matches exact canonical source text.")
        for requirement in case["requirements"]:
            if not requirement["anchor_ids"] or not set(requirement["anchor_ids"]) <= set(anchors):
                raise ValueError("A declared component must point to its frozen source-first anchors.")
    return manifest, sources


def common_transport_cap(spans):
    """Named evaluation-only post-ranking cap; native output remains in receipt."""
    delivered = []
    for span in spans[:3]:
        quote = span["quote"][:1200]
        tokens = list(_BUDGET_TOKEN.finditer(quote))
        if len(tokens) > 400:
            quote = quote[:tokens[399].end()]
        if quote:
            delivered.append({**span, "end": span["start"] + len(quote), "quote": quote})
    return delivered


def _native_budget_violations(spans):
    return {"reference_count": max(0, len(spans) - 3),
        "references_over_character_cap": sum(len(span["quote"]) > 1200 for span in spans),
        "references_over_token_cap": sum(budget_tokens(span["quote"]) > 400 for span in spans),
        "aggregate_characters_over_cap": max(0, sum(len(span["quote"]) for span in spans) - 3600),
        "aggregate_tokens_over_cap": max(0, sum(budget_tokens(span["quote"]) for span in spans) - 1200)}


def measure_case(case, source, spans):
    """Check actual quotations against independently fixed canonical anchors."""
    blocks = {block.id: block for block in source.blocks}
    for span in spans:
        if span["source_id"] != source.id or span["paper_id"] != source.paper_id or span["block_id"] not in blocks:
            raise ValueError("Delivered evidence belongs to a different source or paper.")
        block = blocks[span["block_id"]]
        if (not 0 <= span["start"] < span["end"] <= len(block.text)
                or block.text[span["start"]:span["end"]] != span["quote"]
                or not math.isfinite(span["score"]) or span["score"] <= 0):
            raise ValueError("Delivered evidence is not the exact scored canonical span.")
    if any(_native_budget_violations(spans).values()):
        raise ValueError("Delivered evidence exceeds the common evaluation transport budget.")
    covered = [anchor["id"] for anchor in case["anchors"] if any(span["block_id"] == anchor["block_id"]
        and span["start"] <= anchor["start"] and span["end"] >= anchor["end"] for span in spans)]
    components = [requirement["id"] for requirement in case["requirements"] if set(requirement["anchor_ids"]) <= set(covered)]
    unique = {(span["source_id"], span["block_id"], span["start"], span["end"]) for span in spans}
    intervals = defaultdict(list)
    max_overlap_ratio = 0.
    for index, span in enumerate(spans):
        intervals[span["block_id"]].append((span["start"], span["end"]))
        for other in spans[:index]:
            if span["block_id"] == other["block_id"]:
                overlap = max(0, min(span["end"], other["end"]) - max(span["start"], other["start"]))
                max_overlap_ratio = max(max_overlap_ratio, overlap / min(len(span["quote"]), len(other["quote"])))
    distinct = 0
    for values in intervals.values():
        merged = []
        for start, end in sorted(values):
            if merged and start <= merged[-1][1]: merged[-1][1] = max(end, merged[-1][1])
            else: merged.append([start, end])
        distinct += sum(end - start for start, end in merged)
    return {"anchors_covered": len(covered), "anchors_expected": len(case["anchors"]), "covered_anchor_ids": covered,
        "components_covered": len(components), "components_expected": len(case["requirements"]), "covered_component_ids": components,
        "all_answerable_components_covered": bool(case["requirements"]) and len(components) == len(case["requirements"]),
        "returned_references": len(spans), "delivered_characters": sum(len(span["quote"]) for span in spans),
        "delivered_budget_tokens": sum(budget_tokens(span["quote"]) for span in spans),
        "duplicate_exact_references": len(spans) - len(unique), "overlapping_characters": sum(len(span["quote"]) for span in spans) - distinct,
        "maximum_pairwise_shorter_span_overlap": max_overlap_ratio,
        "insufficient_context_nonempty_candidates": bool(spans) if case["answerability"] != "answerable" else None,
        "meaning": "fixed_development_anchor_coverage_not_semantic_recall_or_human_support"}


def _span_view(selection):
    return {name: getattr(selection, name) for name in ("source_id", "paper_id", "block_id", "start", "end", "quote", "score", "matched_requirement_ids")}


def run_comparison(path=DEFAULT_MANIFEST, *, expected_sha256=FROZEN_MANIFEST_SHA256):
    """Three explicit lanes; no embeddings, generation or network retrieval."""
    manifest, sources = load_frozen_cases(path, expected_sha256=expected_sha256)
    from .adapters.retrieval import LexicalRetrieval
    from .adapters.span_retrieval import LexicalSpanRetrieval, span_retrieval_profile
    from .span_retrieval_contracts import SpanRequirement
    code_paths = ["src/mvp/adapters/retrieval.py", "src/review/retrieval.py", "src/mvp/adapters/span_retrieval.py",
        "src/mvp/span_retrieval_contracts.py", "src/mvp/span_budget.py", "src/mvp/span_evaluation.py"]
    code_hashes = {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in code_paths}
    baseline, spans = LexicalRetrieval(), LexicalSpanRetrieval()
    records = []
    for case in manifest["cases"]:
        source = sources[case["source_id"]]
        for lane in ("B0_question_prefix", "B1_question_only", "B1_explicit_components"):
            started = time.perf_counter()
            if lane == "B0_question_prefix":
                passages, indexed, matched = baseline.search(case["question"], [source], "span-eval:" + case["id"], top_k=3)
                native = [{"source_id": passage.source_id, "paper_id": passage.paper_id, "block_id": passage.anchor.block_id,
                    "start": 0, "end": min(1200, len(passage.anchor.quote)), "quote": passage.anchor.quote[:1200],
                    "score": passage.score, "matched_requirement_ids": []} for passage in passages]
                stats = {"indexed_blocks": indexed, "matched_blocks": matched, "indexed_windows": None, "matched_windows": None,
                    "total_source_blocks": len(source.blocks), "total_source_characters": sum(len(block.text) for block in source.blocks),
                    "unindexed_blocks": 0, "partially_indexed_blocks": 0, "unindexed_characters": 0,
                    "meaning": "whole_block_scoring_with_native_prefix_delivery_no_window_counts"}
                profile = {"method": baseline.method, "parameters": baseline.parameters, "native_prefix_characters": 1200}
            else:
                requirements = [SpanRequirement(id=item["id"], label=item["id"], query=item["text"]) for item in case["requirements"]] if lane == "B1_explicit_components" and case["requirements"] else None
                result = spans.search(case["question"], [source], "span-eval:" + case["id"], top_k=3, requirements=requirements)
                native = [_span_view(selection) for selection in result.selections]
                stats = result.model_dump(mode="json", exclude={"selections"})
                profile = span_retrieval_profile()
                if hasattr(profile, "model_dump"): profile = profile.model_dump(mode="json")
            elapsed = time.perf_counter() - started
            delivered = common_transport_cap(native)
            records.append({"case_id": case["id"], "paper_id": source.paper_id, "field_id": case["field_id"],
                "related_study_group": case["related_study_group"], "source_kind": next(item["kind"] for item in manifest["sources"] if item["id"] == source.id),
                "lane": lane, "question": case["question"], "explicit_requirements": case["requirements"] if lane == "B1_explicit_components" else [],
                "source_sha256": source.source_sha256, "blocks_sha256": source.blocks_sha256, "profile": profile,
                "native_selections": native, "native_budget_violations": _native_budget_violations(native),
                "transport_cap_id": TRANSPORT_CAP_ID, "transport_cap_changed_delivery": delivered != native,
                "delivered_selections": delivered, "retrieval_stats": stats, "elapsed_seconds": elapsed,
                "metrics": measure_case(case, source, delivered)})
    summaries = []
    for lane in ("B0_question_prefix", "B1_question_only", "B1_explicit_components"):
        for kind in ("synthetic", "public_development"):
            selected = [record for record in records if record["lane"] == lane and record["source_kind"] == kind]
            groups = defaultdict(list)
            for record in selected: groups[record["related_study_group"]].append(record)
            summaries.append({"lane": lane, "source_kind": kind, "case_count": len(selected), "related_study_group_count": len(groups),
                "answerable_cases": sum(record["metrics"]["components_expected"] > 0 for record in selected),
                "all_components_covered_cases": sum(record["metrics"]["all_answerable_components_covered"] for record in selected),
                **{name: sum(record["metrics"][name] for record in selected) for name in ("anchors_covered", "anchors_expected", "components_covered", "components_expected", "overlapping_characters")},
                "insufficient_context_nonempty_candidates": sum(record["metrics"]["insufficient_context_nonempty_candidates"] is True for record in selected),
                "insufficient_context_cases": sum(record["metrics"]["insufficient_context_nonempty_candidates"] is not None for record in selected),
                "groups": [{"related_study_group": group, "case_ids": [record["case_id"] for record in members],
                    "anchors_covered": sum(record["metrics"]["anchors_covered"] for record in members), "anchors_expected": sum(record["metrics"]["anchors_expected"] for record in members)} for group, members in groups.items()]})
    integrity = all(not record["metrics"]["duplicate_exact_references"] and record["metrics"]["maximum_pairwise_shorter_span_overlap"] < .5
        and (record["lane"] == "B0_question_prefix" or not any(record["native_budget_violations"].values())) for record in records)
    synthetic_target = [record for record in records if record["lane"] == "B1_explicit_components" and record["source_kind"] == "synthetic" and record["metrics"]["components_expected"]]
    regressions = []
    for case in manifest["cases"]:
        b0, b1 = [next(record for record in records if record["case_id"] == case["id"] and record["lane"] == lane) for lane in ("B0_question_prefix", "B1_question_only")]
        if b1["metrics"]["anchors_covered"] < b0["metrics"]["anchors_covered"]:
            regressions.append({"case_id": case["id"], "source_kind": b1["source_kind"], "B0_anchors": b0["metrics"]["anchors_covered"], "B1_anchors": b1["metrics"]["anchors_covered"], "denominator": b0["metrics"]["anchors_expected"]})
    if code_hashes != {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in code_paths}:
        raise ValueError("Retrieval/evaluation code changed during measurement; rerun against stable code.")
    return {"schema_version": "mvp.span-development-comparison.v1", "created_at": now(), "manifest_sha256": expected_sha256,
        "code_artifact_sha256": code_hashes, "input_manifest": manifest,
        "actual_source_inputs": [source.model_dump(mode="json") for source in sources.values()],
        "label_status": manifest["label_status"], "budgets": manifest["budgets"], "transport_cap_id": TRANSPORT_CAP_ID,
        "primary_comparison": ["B0_question_prefix", "B1_question_only"], "supplementary_extra_query_lane": "B1_explicit_components",
        "records": records, "summaries": summaries, "primary_per_case_anchor_regressions": regressions,
        "gates": {"exact_identity_quotation_and_budget_checks": True, "no_duplicate_or_high_overlap_references": integrity,
            "mandatory_synthetic_explicit_component_target": all(record["metrics"]["all_answerable_components_covered"] for record in synthetic_target),
            "mandatory_late_span_repair": all(record["metrics"]["all_answerable_components_covered"] for record in records if record["case_id"] == "late-participant-qualifiers" and record["lane"] == "B1_question_only"),
            "index_scope_complete_for_frozen_bounded_cases": all(not record["retrieval_stats"].get("unindexed_characters", 0) for record in records)},
        "limitations": [*manifest["limitations"], "B1 explicit components uses extra frozen component queries; its gains cannot be attributed solely to span selection.",
            "Development groups preserve shared-source fields; cross-report study relatedness still requires human adjudication before a held-out evaluation.",
            "The named common transport cap is evaluator-only after ranking. Native B0 prefixes, violations and any changed delivery remain recorded."],
        "live_pubmed": "NOT_RUN", "generation": "NOT_RUN", "embeddings": "NOT_RUN", "human_usefulness": "NOT_RUN", "held_out_validation": "NOT_RUN"}
