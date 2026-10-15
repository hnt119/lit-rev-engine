"""Descriptive summaries of recorded human judgments, with unknowns retained."""

from collections import Counter
import math
from .assessments import current_assessments
from .contracts import STATUSES, digest


def summarize(packet, records):
    current = current_assessments(packet, records)
    methods = {}
    for bundle in packet["bundles"]:
        methods.setdefault(bundle["method_key"], []).append(bundle)
    summaries = {}
    for method, bundles in sorted(methods.items()):
        ids = {row["id"] for row in bundles}
        own = [row for row in current if row["bundle_id"] in ids]
        by_bundle = {row["id"]: row for row in bundles}
        statuses = Counter(row["status"] for row in own)
        grades, unknown, complete_precision, durations, p5, strict_p5 = [], 0, [], [], [], []
        component_grades, component_unknowns = Counter(), 0
        for record in own:
            bundle = by_bundle[record["bundle_id"]]
            rating_map = {row["passage_id"]: row for row in record["ratings"]}
            full = []
            for passage in bundle["passages"]:
                row = rating_map.get(passage["id"])
                value = row["rating"] if row else None
                full.append(value)
                if value is None:
                    unknown += 1
                else:
                    grades.append(value)
                question = next(q for q in packet["questions"] if q["id"] == bundle["question_id"])
                for component in question["components"]:
                    component_value = row["component_ratings"][component["id"]] if row else None
                    if component_value is None:
                        component_unknowns += 1
                    else:
                        component_grades[component_value] += 1
            if full and all(value is not None for value in full):
                complete_precision.append(sum(value >= 2 for value in full) / len(full))
                if len(full) == 5:
                    p5.append(sum(value >= 2 for value in full) / 5)
                    strict_p5.append(sum(value == 3 for value in full) / 5)
            if record["review_seconds"] is not None:
                durations.append(record["review_seconds"])
        covered = {row["bundle_id"] for row in own}
        duration_total = sum(durations) if durations else None
        duration_overflow = duration_total is not None and not math.isfinite(duration_total)
        summaries[method] = {"anonymous_label": bundles[0]["label"], "bundle_count": len(bundles),
                             "bundles_with_records": len(covered), "bundles_without_records": len(bundles) - len(covered),
                             "current_human_assessments": len(own),
                             "bundle_support_counts": {status: statuses[status] for status in sorted(STATUSES)},
                             "rated_passages": len(grades), "unknown_passage_ratings_in_recorded_bundles": unknown,
                             "passage_grade_counts": {str(grade): grades.count(grade) for grade in range(4)},
                             "mean_observed_passage_grade": sum(grades) / len(grades) if grades else None,
                             "observed_useful_passage_proportion": sum(grade >= 2 for grade in grades) / len(grades) if grades else None,
                             "observed_strict_passage_proportion": sum(grade == 3 for grade in grades) / len(grades) if grades else None,
                             "observed_grade_proportion_denominator": len(grades),
                             "component_grade_counts": {str(grade): component_grades[grade] for grade in range(4)},
                             "unknown_component_ratings_in_recorded_bundles": component_unknowns,
                             "fully_rated_bundle_observations": len(complete_precision),
                             "mean_fully_rated_bundle_precision": sum(complete_precision) / len(complete_precision) if complete_precision else None,
                             "p5_fully_rated_bundle_observations": len(p5),
                             "mean_precision_at_5": sum(p5) / len(p5) if p5 else None,
                             "mean_strict_precision_at_5": sum(strict_p5) / len(strict_p5) if strict_p5 else None,
                             "declared_contradictions": sum(row["contradiction"] for row in own),
                             "source_inspected_records": sum(row["source_inspected"] for row in own),
                             "known_review_seconds_total": duration_total if not duration_overflow else None,
                             "known_review_seconds_total_overflow": duration_overflow,
                             "records_with_unknown_review_seconds": len(own) - len(durations)}
    report = {"schema_version": 1, "kind": "review-workbench-evaluation-v1", "packet_id": packet["packet_id"],
              "binding": packet["binding"], "assessment_records": len(records), "current_assessment_records": len(current),
              "superseded_assessment_records": len(records) - len(current),
              "assessment_record_sha256s": sorted(row["record_sha256"] for row in records),
              "reviewers": sorted({row["reviewer"] for row in current}), "review_basis": "single_human",
              "source_answerability": "not_assessed", "independent_verification": "NOT_RUN", "current_ledger_state": "not_checked",
              "methods": summaries,
              "precision_definition": "Fully rated bundle precision: fraction graded 2 or 3, macro mean across observations with every displayed passage explicitly rated. Precision at 5 additionally requires exactly five displayed passages; strict precision at 5 counts only grade 3. Observed useful/strict proportions divide by rated_passages only. No null rating is treated as zero.",
              "support_definition": "Explicit human judgment of the retrieved bundle; no support status is inferred from passage averages.",
              "shared_saved_batch": {"elapsed_seconds": packet["shared_batch_runtime"]["elapsed_seconds"],
                                     "distinct_rerank_pairs": packet["distinct_rerank_pairs"],
                                     "attribution": "Shared saved batch; not an independent runtime for any method."},
              "not_run": ["source-first reference annotation", "answer accuracy", "nDCG", "fresh confirmation", "independent human verification", "new model inference"],
              "limitations": ["Descriptive saved-regression exercise; no new effectiveness or clinical claim.",
                              "Reviewer familiarity, carryover and self-reported inspection are not independently checked.",
                              "No independently annotated common candidate universe or ideal ranking is available.",
                              "Anonymous labels are deterministic, not a guarantee of reviewer blinding."]}
    report["report_sha256"] = digest(report)
    return report
