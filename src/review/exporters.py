"""Deterministic, formula-safe ledger exports from an already captured snapshot."""

import csv
import io
import json
import os
import tempfile
from pathlib import Path


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def _csv_cell(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def _csv(rows, fields):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerows({field: _csv_cell(row.get(field)) for field in fields} for row in rows)
    return output.getvalue()


def write_export(bundle, exclusions, destination, *, artifacts=None):
    """Build every file before replacing known output paths; preserve other files."""
    record_fields = ["id", "project_id", "title", "authors", "year", "doi", "pmid", "abstract", "url", "source_id", "raw", "title_abstract_state", "full_text_status", "full_text_state"]
    search_fields = ["id", "project_id", "source", "query", "searched_at", "filters", "notes", "import_format", "source_file", "source_sha256", "reported_count", "execution", "identified", "new_records", "duplicates", "created_at"]
    count_rows = []
    for metric, value in bundle["counts"].items():
        if metric == "reconciliation":
            count_rows.extend({"metric": f"reconciliation.{key}", "value": item} for key, item in value.items())
        else:
            count_rows.append({"metric": metric, "value": value})
    contents = {
        "project.json": _json(bundle),
        "records.csv": _csv(bundle["records"], record_fields),
        "search_runs.csv": _csv(bundle["search_runs"], search_fields),
        "occurrences.csv": _csv(bundle["occurrences"], ["id", "project_id", "search_run_id", "record_id", "ordinal", "record"]),
        "decisions.csv": _csv(bundle["decisions"], ["id", "project_id", "record_id", "stage", "decision", "reviewer", "reason", "kind", "created_at"]),
        "retrieval_events.csv": _csv(bundle["retrieval_events"], ["id", "project_id", "record_id", "status", "reviewer", "reason", "created_at"]),
        "counts.json": _json(bundle["counts"]),
        "counts.csv": _csv(count_rows, ["metric", "value"]),
        "exclusions.csv": _csv(exclusions, ["record_id", "stage", "title", "reason", "reviewers", "kind"]),
    }
    if "studies" in bundle:
        contents.update({
            "studies.csv": _csv(bundle["studies"], ["id", "project_id", "label", "identifiers", "reviewer", "reason", "created_at"]),
            "study_links.csv": _csv(bundle["study_links"], ["project_id", "record_id", "state", "study_ids", "active_event_ids"]),
            "study_link_events.csv": _csv(bundle["study_link_events"], ["id", "project_id", "record_id", "study_ids", "reviewer", "reason", "kind", "created_at"]),
        })
    contents.update(artifacts or {})
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".review-export-", dir=destination) as staged:
        staged = Path(staged)
        for name, content in contents.items():
            path = staged / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(content, encoding="utf-8", newline="")
        for name in contents:
            (destination / name).parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged / name, destination / name)
    return {"directory": str(destination.resolve()), "files": list(contents), "counts": bundle["counts"]}
