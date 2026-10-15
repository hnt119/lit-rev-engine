"""Immutable human judgments bound to one exact receipt, question and trace."""

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import os
import stat
from uuid import UUID, uuid4

from .contracts import (MAX_ASSESSMENT_BYTES, MAX_HISTORY_BYTES, MAX_RECORDS, STATUSES, canonical, digest, directory_fd,
                        finite_seconds, read_at, read_json, require, write_at_new)

DRAFT_FIELDS = {"packet_id", "bundle_id", "reviewer", "status", "reason", "ratings", "supporting_passage_ids",
                "missing_components", "contradiction", "source_inspected", "supersedes", "review_seconds"}
RECORD_FIELDS = DRAFT_FIELDS | {"schema_version", "kind", "id", "created_at", "display_mode", "binding",
                               "judgment_scope", "review_basis", "source_answerability", "verification",
                               "current_ledger_state", "record_sha256"}


def _uuid(value):
    try:
        return isinstance(value, str) and str(UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def _bound(packet, draft):
    require(isinstance(draft, dict) and set(draft) == DRAFT_FIELDS, "Assessment draft has unknown or missing fields")
    require(draft["packet_id"] == packet["packet_id"], "Assessment packet is stale or belongs to another receipt")
    bundle = next((row for row in packet["bundles"] if row["id"] == draft["bundle_id"]), None)
    require(bundle is not None, "Unknown bundle reference")
    question = next(row for row in packet["questions"] if row["id"] == bundle["question_id"])
    require(isinstance(draft["reviewer"], str) and draft["reviewer"].strip() == draft["reviewer"]
            and 1 <= len(draft["reviewer"]) <= 160, "Declare a nonempty human reviewer (at most 160 characters)")
    require(isinstance(draft["status"], str) and draft["status"] in STATUSES, "Unknown bundle support status")
    require(isinstance(draft["reason"], str) and len(draft["reason"].encode("utf-8")) <= 20000, "Reason must be bounded text")
    require(draft["status"] == "not_assessed" or draft["reason"].strip(), "An assessed status requires a reason")
    require(type(draft["contradiction"]) is bool and type(draft["source_inspected"]) is bool,
            "Contradiction and source inspection must be explicit booleans")
    require(finite_seconds(draft["review_seconds"]), "Review duration must be null or a finite nonnegative number")
    require(draft["supersedes"] is None or _uuid(draft["supersedes"]), "Invalid superseded assessment ID")
    passage_ids = {row["id"] for row in bundle["passages"]}
    component_ids = {part["id"] for part in question["components"]}
    require(isinstance(draft["ratings"], list) and len(draft["ratings"]) <= len(passage_ids), "Invalid passage ratings")
    seen = set()
    def grade(value):
        return value is None or (type(value) is int and 0 <= value <= 3)
    for row in draft["ratings"]:
        require(isinstance(row, dict) and set(row) == {"passage_id", "rating", "component_ratings"}, "Unknown passage rating fields")
        require(isinstance(row["passage_id"], str) and row["passage_id"] in passage_ids and row["passage_id"] not in seen,
                "Unknown or duplicate passage rating reference")
        seen.add(row["passage_id"])
        require(grade(row["rating"]), "Passage rating must be null or an integer from 0 to 3")
        require(isinstance(row["component_ratings"], dict) and set(row["component_ratings"]) == component_ids
                and all(grade(value) for value in row["component_ratings"].values()),
                "Component ratings must explicitly contain each question component with null or integer 0 to 3")
    for name, allowed in (("supporting_passage_ids", passage_ids), ("missing_components", component_ids or {"whole_question"})):
        values = draft[name]
        require(isinstance(values, list) and all(isinstance(value, str) for value in values)
                and len(values) == len(set(values)) and set(values) <= allowed, "Unknown or duplicate " + name + " reference")
    if draft["status"] == "sufficient":
        require(draft["supporting_passage_ids"] and not draft["missing_components"],
                "Sufficient requires supporting passages and no declared missing components")
    if draft["status"] in {"partial", "insufficient"}:
        require(draft["missing_components"], "Partial or insufficient requires declared missing components")
    return bundle, question


def _binding(packet, bundle, question):
    return {**packet["binding"], "question_sha256": question["question_sha256"], "trace_sha256": bundle["trace_sha256"]}


def validate_record(packet, record):
    require(isinstance(record, dict) and set(record) == RECORD_FIELDS, "Assessment record schema mismatch")
    draft = {key: record[key] for key in DRAFT_FIELDS}
    bundle, question = _bound(packet, draft)
    require(type(record["schema_version"]) is int and record["schema_version"] == 1
            and record["kind"] == "review-workbench-assessment-v1" and _uuid(record["id"]), "Invalid assessment identity")
    require(isinstance(record["display_mode"], str) and record["display_mode"] in {"blinded", "revealed"}, "Unknown assessment display mode")
    require(isinstance(record["created_at"], str), "Missing assessment time")
    try:
        timestamp = datetime.fromisoformat(record["created_at"])
    except ValueError:
        raise ValueError("Invalid assessment time") from None
    require(timestamp.tzinfo is not None and timestamp.utcoffset().total_seconds() == 0, "Assessment time must be UTC")
    require(canonical(record["binding"]) == canonical(_binding(packet, bundle, question)),
            "Assessment source, question, method trace or receipt binding is stale")
    fixed = {"judgment_scope": "retrieved_bundle", "review_basis": "single_human", "source_answerability": "not_assessed",
             "verification": "NOT_RUN", "current_ledger_state": "not_checked"}
    require(all(record[name] == expected for name, expected in fixed.items()), "Assessment cannot assert source answerability or independent verification")
    require(record["record_sha256"] == digest({key: value for key, value in record.items() if key != "record_sha256"}),
            "Assessment record checksum mismatch")
    return record


def _history(packet, records):
    require(isinstance(records, list) and len(records) <= MAX_RECORDS, "Too many assessment records")
    by_id, children, groups = {}, {}, {}
    for record in records:
        validate_record(packet, record)
        require(record["id"] not in by_id, "Duplicate assessment ID")
        by_id[record["id"]] = record
        groups.setdefault((record["bundle_id"], record["reviewer"]), []).append(record)
    for record in records:
        old_id = record["supersedes"]
        if old_id is not None:
            require(old_id in by_id and old_id != record["id"], "Missing superseded assessment")
            old = by_id[old_id]
            require((record["bundle_id"], record["reviewer"]) == (old["bundle_id"], old["reviewer"]),
                    "Supersession requires the same bundle and reviewer")
            require(old_id not in children and record["created_at"] >= old["created_at"], "Branched or out-of-order assessment history")
            children[old_id] = record["id"]
    latest = {}
    for key, rows in groups.items():
        roots = [row for row in rows if row["supersedes"] is None]
        require(len(roots) == 1, "Assessment history requires one root per bundle and reviewer")
        cursor, visited = roots[0]["id"], set()
        while cursor not in visited:
            visited.add(cursor)
            if cursor not in children:
                break
            cursor = children[cursor]
        require(len(visited) == len(rows) and cursor not in children, "Cyclic or disconnected assessment history")
        latest[key] = by_id[cursor]
    return latest


@contextmanager
def _locked_directory(path):
    with directory_fd(path, create=True) as fd:
        try:
            lock = os.open(".workbench.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=fd)
        except OSError as error:
            raise ValueError("Assessment lock must be a regular non-symlink file") from error
        try:
            require(stat.S_ISREG(os.fstat(lock).st_mode) and os.fstat(lock).st_nlink == 1, "Unsafe assessment lock")
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield fd
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            os.close(lock)


def _read_records(packet, fd):
    names = [name for name in os.listdir(fd) if name.endswith(".json")]
    require(len(names) <= MAX_RECORDS, "Too many assessment records")
    records, total_bytes = [], 0
    for name in sorted(names):
        require(_uuid(name[:-5]), "Unexpected assessment filename")
        data = read_at(fd, name, MAX_ASSESSMENT_BYTES)
        total_bytes += len(data)
        require(total_bytes <= MAX_HISTORY_BYTES, "Assessment history exceeds its aggregate size bound")
        record = read_json(data)
        validate_record(packet, record)
        require(name == record["id"] + ".json", "Assessment filename and identity mismatch")
        records.append(record)
    _history(packet, records)
    return sorted(records, key=lambda row: (row["created_at"], row["id"])), total_bytes


def list_assessments(packet, directory):
    with _locked_directory(directory) as fd:
        return _read_records(packet, fd)[0]


def current_assessments(packet, records):
    return list(_history(packet, records).values())


def save_assessment(packet, directory, draft, display_mode="blinded"):
    bundle, question = _bound(packet, draft)
    require(isinstance(display_mode, str) and display_mode in {"blinded", "revealed"}, "Unknown assessment display mode")
    with _locked_directory(directory) as fd:
        records, history_bytes = _read_records(packet, fd)
        require(len(records) < MAX_RECORDS, "Assessment record limit reached")
        latest = _history(packet, records).get((draft["bundle_id"], draft["reviewer"]))
        require(draft["supersedes"] == (latest["id"] if latest else None),
                "Explicitly supersede the latest assessment for this bundle and reviewer")
        record = {"schema_version": 1, "kind": "review-workbench-assessment-v1", "id": str(uuid4()),
                  "created_at": datetime.now(timezone.utc).isoformat(), **deepcopy(draft), "display_mode": display_mode,
                  "binding": _binding(packet, bundle, question), "judgment_scope": "retrieved_bundle", "review_basis": "single_human",
                  "source_answerability": "not_assessed", "verification": "NOT_RUN", "current_ledger_state": "not_checked"}
        record["record_sha256"] = digest(record)
        validate_record(packet, record)
        data = (canonical(record) + "\n").encode("utf-8")
        require(history_bytes + len(data) <= MAX_HISTORY_BYTES, "Assessment history exceeds its aggregate size bound")
        write_at_new(fd, record["id"] + ".json", data)
        return record
