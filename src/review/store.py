"""Transactional SQLite source of truth for reproducible review projects."""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .identity import fallback_compatible, fallback_identity, validate_record
from .models import SearchRunSpec


def _now():
    return datetime.now(timezone.utc).isoformat()


def _json(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("Fields must be JSON-compatible") from error


class ReviewStore:
    """A lightweight ledger; opening it never initializes embeddings or APIs."""

    def __init__(self, db_path=None):
        if db_path is None:
            db_path = Path(__file__).resolve().parents[2] / "data" / "reviews.sqlite3"
        if str(db_path) != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(db_path))
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        try:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, review_type TEXT NOT NULL,
                    question TEXT NOT NULL, protocol TEXT NOT NULL, eligibility TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS search_runs (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    spec TEXT NOT NULL, identified INTEGER NOT NULL, new_records INTEGER NOT NULL,
                    duplicates INTEGER NOT NULL, created_at TEXT NOT NULL,
                    idempotency_key TEXT, fingerprint TEXT NOT NULL,
                    UNIQUE(project_id, idempotency_key), UNIQUE(project_id, id)
                );
                CREATE TABLE IF NOT EXISTS records (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    payload TEXT NOT NULL, doi TEXT, pmid TEXT, fallback_key TEXT,
                    created_at TEXT NOT NULL, UNIQUE(project_id, id),
                    UNIQUE(project_id, doi), UNIQUE(project_id, pmid)
                );
                CREATE INDEX IF NOT EXISTS records_fallback ON records(project_id, fallback_key);
                CREATE TABLE IF NOT EXISTS occurrences (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    search_run_id TEXT NOT NULL, record_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL, record TEXT NOT NULL,
                    FOREIGN KEY(project_id, search_run_id) REFERENCES search_runs(project_id, id),
                    FOREIGN KEY(project_id, record_id) REFERENCES records(project_id, id),
                    UNIQUE(search_run_id, ordinal)
                );
                CREATE TABLE IF NOT EXISTS screening_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE, project_id TEXT NOT NULL,
                    record_id TEXT NOT NULL, stage TEXT NOT NULL,
                    decision TEXT NOT NULL, reviewer TEXT NOT NULL,
                    reason TEXT NOT NULL, kind TEXT NOT NULL, created_at TEXT NOT NULL,
                    FOREIGN KEY(project_id, record_id) REFERENCES records(project_id, id)
                );
                CREATE INDEX IF NOT EXISTS screening_events_record ON screening_events(project_id, record_id, sequence);
                CREATE TABLE IF NOT EXISTS retrieval_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE, project_id TEXT NOT NULL,
                    record_id TEXT NOT NULL, status TEXT NOT NULL,
                    reviewer TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL,
                    FOREIGN KEY(project_id, record_id) REFERENCES records(project_id, id)
                );
                CREATE INDEX IF NOT EXISTS retrieval_events_record ON retrieval_events(project_id, record_id, sequence);
                """
            )
        except Exception:
            self.close()
            raise

    def close(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    @contextmanager
    def _snapshot(self):
        """Explicit transaction keeps related reads on one SQLite snapshot."""
        if self._connection.in_transaction:
            yield
            return
        self._connection.execute("BEGIN")
        try:
            yield
        except BaseException:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()

    def _record(self, project_id, record_id):
        self._project(project_id)
        row = self._connection.execute(
            "SELECT * FROM records WHERE project_id = ? AND id = ?", (project_id, record_id)
        ).fetchone()
        if row is None:
            raise ValueError(f"Unknown record in project: {record_id}")
        return row

    def _project(self, project_id):
        row = self._connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown project: {project_id}")
        result = dict(row)
        result["eligibility"] = json.loads(result["eligibility"])
        return result

    def create_project(self, title, review_type, question, protocol="", eligibility=None):
        if not isinstance(title, str) or not title.strip():
            raise ValueError("Project title must be nonempty")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Project question must be nonempty")
        if not isinstance(review_type, str) or review_type not in {"systematic", "scoping"}:
            raise ValueError("Review type must be systematic or scoping")
        if not isinstance(protocol, str):
            raise ValueError("Project protocol must be a string")
        eligibility_json = _json(eligibility)
        project_id, created_at = str(uuid4()), _now()
        with self._connection:
            self._connection.execute(
                "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?)",
                (project_id, title, review_type, question, protocol, eligibility_json, created_at),
            )
        return self._project(project_id)

    def get_project(self, project_id):
        return self._project(project_id)

    def list_projects(self):
        return [self._project(row["id"]) for row in self._connection.execute(
            "SELECT id FROM projects ORDER BY rowid"
        ).fetchall()]

    @staticmethod
    def _validate_spec(spec):
        if not isinstance(spec, SearchRunSpec):
            raise ValueError("Search spec must be a SearchRunSpec instance")
        if not isinstance(spec.source, str) or not spec.source.strip():
            raise ValueError("Search source must be nonempty")
        for name in ("query", "searched_at"):
            if getattr(spec, name) is not None and not isinstance(getattr(spec, name), str):
                raise ValueError(f"Search {name} must be a string or None")
        for name in ("notes", "import_format", "source_file", "source_sha256"):
            if not isinstance(getattr(spec, name), str):
                raise ValueError(f"Search {name} must be a string")
        if not isinstance(spec.filters, dict):
            raise ValueError("Search filters must be a dictionary")
        if spec.reported_count is not None and (
            isinstance(spec.reported_count, bool)
            or not isinstance(spec.reported_count, int)
            or spec.reported_count < 0
        ):
            raise ValueError("Reported count must be a nonnegative integer or None")
        return asdict(spec)

    @staticmethod
    def _import_result(row):
        return {
            "search_run_id": row["id"], "identified": row["identified"],
            "new_records": row["new_records"], "duplicates": row["duplicates"],
        }

    def _matching_record(self, project_id, payload):
        matches = {}
        for identifier in ("doi", "pmid"):
            if payload[identifier]:
                row = self._connection.execute(
                    f"SELECT * FROM records WHERE project_id = ? AND {identifier} = ?",
                    (project_id, payload[identifier]),
                ).fetchone()
                if row is not None:
                    matches[row["id"]] = row
        if len(matches) > 1:
            raise ValueError("Conflicting identifiers point to different canonical records")
        if matches:
            row = next(iter(matches.values()))
            existing = json.loads(row["payload"])
            for identifier in ("doi", "pmid"):
                if existing[identifier] and payload[identifier] and existing[identifier] != payload[identifier]:
                    raise ValueError(f"Conflicting {identifier.upper()} for canonical record {row['id']}")
            return row
        key = fallback_identity(payload)
        if key is not None:
            for row in self._connection.execute(
                "SELECT * FROM records WHERE project_id = ? AND fallback_key = ? ORDER BY rowid",
                (project_id, key),
            ).fetchall():
                if fallback_compatible(json.loads(row["payload"]), payload):
                    return row
        return None

    def import_records(self, project_id, spec, records, idempotency_key=None):
        self._project(project_id)
        spec_payload = self._validate_spec(spec)
        if not isinstance(records, list):
            raise ValueError("Records must be a list")
        if spec.reported_count is not None and spec.reported_count < len(records):
            raise ValueError("Reported count cannot be smaller than the imported occurrence count")
        if idempotency_key is not None and (
            not isinstance(idempotency_key, str) or not idempotency_key.strip()
        ):
            raise ValueError("Idempotency key must be a nonempty string")
        payloads, originals = [], []
        for ordinal, record in enumerate(records, 1):
            try:
                payloads.append(validate_record(record))
                originals.append(asdict(record))
            except ValueError as error:
                raise ValueError(f"Record {ordinal}: {error}") from error
        fingerprint = hashlib.sha256(_json({"spec": spec_payload, "records": originals}).encode("utf-8")).hexdigest()
        with self._connection:
            # Serialize identity/idempotency reads with subsequent writes across clients.
            self._connection.execute("BEGIN IMMEDIATE")
            if idempotency_key is not None:
                existing = self._connection.execute(
                    "SELECT * FROM search_runs WHERE project_id = ? AND idempotency_key = ?",
                    (project_id, idempotency_key),
                ).fetchone()
                if existing is not None:
                    if existing["fingerprint"] != fingerprint:
                        raise ValueError("Idempotency key was already used with a different payload")
                    return self._import_result(existing)
            run_id, created_at = str(uuid4()), _now()
            self._connection.execute(
                "INSERT INTO search_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, project_id, _json(spec_payload), len(records), 0, 0, created_at, idempotency_key, fingerprint),
            )
            new_records = 0
            for ordinal, (payload, original) in enumerate(zip(payloads, originals), 1):
                try:
                    existing = self._matching_record(project_id, payload)
                except ValueError as error:
                    raise ValueError(f"Record {ordinal}: {error}") from error
                if existing is None:
                    record_id = str(uuid4())
                    self._connection.execute(
                        "INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (record_id, project_id, _json(payload), payload["doi"], payload["pmid"], fallback_identity(payload), created_at),
                    )
                    new_records += 1
                else:
                    record_id = existing["id"]
                    canonical = json.loads(existing["payload"])
                    for field, value in payload.items():
                        if canonical[field] in (None, "", [], {}) and value not in (None, "", [], {}):
                            canonical[field] = value
                    self._connection.execute(
                        "UPDATE records SET payload = ?, doi = ?, pmid = ?, fallback_key = ? WHERE id = ?",
                        (_json(canonical), canonical["doi"], canonical["pmid"], fallback_identity(canonical), record_id),
                    )
                self._connection.execute(
                    "INSERT INTO occurrences VALUES (?, ?, ?, ?, ?, ?)",
                    (str(uuid4()), project_id, run_id, record_id, ordinal, _json(original)),
                )
            duplicates = len(records) - new_records
            self._connection.execute(
                "UPDATE search_runs SET new_records = ?, duplicates = ? WHERE id = ?",
                (new_records, duplicates, run_id),
            )
        return {"search_run_id": run_id, "identified": len(records), "new_records": new_records, "duplicates": duplicates}

    def list_search_runs(self, project_id):
        self._project(project_id)
        results = []
        for row in self._connection.execute(
            "SELECT * FROM search_runs WHERE project_id = ? ORDER BY rowid", (project_id,)
        ).fetchall():
            result = {"id": row["id"], "search_run_id": row["id"], "project_id": project_id, **json.loads(row["spec"])}
            result.update({key: row[key] for key in ("identified", "new_records", "duplicates", "created_at")})
            results.append(result)
        return results

    def list_records(self, project_id):
        with self._snapshot():
            self._project(project_id)
            decisions = self._screening_rows(project_id)
            retrievals = self._retrieval_rows(project_id)
            by_record, retrieval_by_record = {}, {}
            for event in decisions:
                by_record.setdefault(event["record_id"], []).append(event)
            for event in retrievals:
                retrieval_by_record[event["record_id"]] = event["status"]
            results = []
            for row in self._connection.execute(
                "SELECT * FROM records WHERE project_id = ? ORDER BY rowid", (project_id,)
            ).fetchall():
                events = by_record.get(row["id"], [])
                results.append({
                    "id": row["id"], "project_id": project_id, **json.loads(row["payload"]),
                    "title_abstract_state": self._screening_state(events, "title_abstract"),
                    "full_text_status": retrieval_by_record.get(row["id"], "not_requested"),
                    "full_text_state": self._screening_state(events, "full_text"),
                })
            return results

    def get_occurrences(self, project_id, record_id=None):
        self._project(project_id)
        query = "SELECT * FROM occurrences WHERE project_id = ?"
        parameters = [project_id]
        if record_id is not None:
            existing = self._connection.execute(
                "SELECT id FROM records WHERE project_id = ? AND id = ?", (project_id, record_id)
            ).fetchone()
            if existing is None:
                raise ValueError(f"Unknown record in project: {record_id}")
            query += " AND record_id = ?"
            parameters.append(record_id)
        return [{**dict(row), "record": json.loads(row["record"])} for row in self._connection.execute(
            query + " ORDER BY rowid", parameters
        ).fetchall()]

    def counts(self, project_id):
        with self._snapshot():
            self._project(project_id)
            runs = self.list_search_runs(project_id)
            records = self.list_records(project_id)
            result = {
                "records_identified": sum(run["identified"] for run in runs),
                "duplicate_records_removed": sum(run["duplicates"] for run in runs),
                "unique_records": len(records),
                "records_awaiting_screening": 0, "records_screened": 0,
                "records_excluded": 0, "records_included_for_full_text": 0,
                "records_screening_unresolved": 0, "reports_awaiting_request": 0,
                "reports_sought_for_retrieval": 0, "reports_retrieved": 0,
                "reports_not_retrieved": 0, "reports_awaiting_retrieval": 0,
                "reports_awaiting_assessment": 0, "reports_assessed": 0,
                "reports_included": 0, "reports_excluded": 0,
                "reports_assessment_unresolved": 0,
                "included_studies": None, "study_linkage_available": False,
            }
            for record in records:
                ta_state = record["title_abstract_state"]
                if ta_state == "pending":
                    result["records_awaiting_screening"] += 1
                    continue
                result["records_screened"] += 1
                if ta_state == "exclude":
                    result["records_excluded"] += 1
                    continue
                if ta_state in {"uncertain", "conflict"}:
                    result["records_screening_unresolved"] += 1
                    continue
                result["records_included_for_full_text"] += 1
                status = record["full_text_status"]
                if status == "not_requested":
                    result["reports_awaiting_request"] += 1
                    continue
                result["reports_sought_for_retrieval"] += 1
                if status == "requested":
                    result["reports_awaiting_retrieval"] += 1
                    continue
                if status == "not_retrieved":
                    result["reports_not_retrieved"] += 1
                    continue
                result["reports_retrieved"] += 1
                ft_state = record["full_text_state"]
                if ft_state == "pending":
                    result["reports_awaiting_assessment"] += 1
                    continue
                result["reports_assessed"] += 1
                if ft_state == "include":
                    result["reports_included"] += 1
                elif ft_state == "exclude":
                    result["reports_excluded"] += 1
                else:
                    result["reports_assessment_unresolved"] += 1
            c = result
            result["reconciliation"] = {
                "identification": c["records_identified"] == c["duplicate_records_removed"] + c["unique_records"],
                "screening_progress": c["unique_records"] == c["records_awaiting_screening"] + c["records_screened"],
                "title_abstract": c["records_screened"] == c["records_excluded"] + c["records_included_for_full_text"] + c["records_screening_unresolved"],
                "retrieval_requests": c["records_included_for_full_text"] == c["reports_awaiting_request"] + c["reports_sought_for_retrieval"],
                "retrieval_progress": c["reports_sought_for_retrieval"] == c["reports_retrieved"] + c["reports_not_retrieved"] + c["reports_awaiting_retrieval"],
                "assessment_progress": c["reports_retrieved"] == c["reports_awaiting_assessment"] + c["reports_assessed"],
                "full_text": c["reports_assessed"] == c["reports_included"] + c["reports_excluded"] + c["reports_assessment_unresolved"],
            }
            result["all_checks_passed"] = all(result["reconciliation"].values())
            return result

    def _screening_rows(self, project_id, record_id=None):
        query = "SELECT * FROM screening_events WHERE project_id = ?"
        parameters = [project_id]
        if record_id is not None:
            query += " AND record_id = ?"
            parameters.append(record_id)
        return [dict(row) for row in self._connection.execute(query + " ORDER BY sequence", parameters).fetchall()]

    def _retrieval_rows(self, project_id, record_id=None):
        query = "SELECT * FROM retrieval_events WHERE project_id = ?"
        parameters = [project_id]
        if record_id is not None:
            query += " AND record_id = ?"
            parameters.append(record_id)
        return [dict(row) for row in self._connection.execute(query + " ORDER BY sequence", parameters).fetchall()]

    @staticmethod
    def _active_decisions(events, stage):
        reviews, adjudication = {}, None
        latest_review = 0
        for event in events:
            if event["stage"] != stage:
                continue
            if event["kind"] == "review":
                reviews[event["reviewer"]] = event
                latest_review = event["sequence"]
            else:
                adjudication = event
        if adjudication is not None and adjudication["sequence"] > latest_review:
            return [adjudication]
        return list(reviews.values())

    @classmethod
    def _screening_state(cls, events, stage):
        active = cls._active_decisions(events, stage)
        if not active:
            return "pending"
        values = {event["decision"] for event in active}
        return values.pop() if len(values) == 1 else "conflict"

    @staticmethod
    def _public_event(event):
        return {key: value for key, value in event.items() if key != "sequence"}

    def list_decisions(self, project_id, record_id=None):
        with self._snapshot():
            self._project(project_id)
            if record_id is not None:
                self._record(project_id, record_id)
            return [self._public_event(event) for event in self._screening_rows(project_id, record_id)]

    def list_retrieval_events(self, project_id, record_id=None):
        with self._snapshot():
            self._project(project_id)
            if record_id is not None:
                self._record(project_id, record_id)
            return [self._public_event(event) for event in self._retrieval_rows(project_id, record_id)]

    @staticmethod
    def _validate_reviewer_reason(reviewer, reason):
        if not isinstance(reviewer, str) or not reviewer.strip():
            raise ValueError("Reviewer must be nonempty")
        if not isinstance(reason, str):
            raise ValueError("Reason must be a string")

    def _append_decision(self, project_id, record_id, stage, decision, reviewer, reason, kind):
        self._record(project_id, record_id)
        if not isinstance(stage, str) or stage not in {"title_abstract", "full_text"}:
            raise ValueError("Stage must be title_abstract or full_text")
        if not isinstance(decision, str) or decision not in {"include", "exclude", "uncertain"}:
            raise ValueError("Decision must be include, exclude, or uncertain")
        self._validate_reviewer_reason(reviewer, reason)
        if (decision == "exclude" or kind == "adjudication") and not reason.strip():
            raise ValueError("Exclusions and adjudications require a reason")
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            events = self._screening_rows(project_id, record_id)
            retrievals = self._retrieval_rows(project_id, record_id)
            if kind == "adjudication" and not any(event["stage"] == stage and event["kind"] == "review" for event in events):
                raise ValueError("Adjudication requires existing review decisions in this stage")
            if stage == "full_text" and (
                self._screening_state(events, "title_abstract") != "include"
                or not retrievals or retrievals[-1]["status"] != "retrieved"
            ):
                raise ValueError("Full-text decisions require title/abstract inclusion and retrieved full text")
            event_id = str(uuid4())
            self._connection.execute(
                "INSERT INTO screening_events (id, project_id, record_id, stage, decision, reviewer, reason, kind, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (event_id, project_id, record_id, stage, decision, reviewer, reason, kind, _now()),
            )
            if stage == "title_abstract" and retrievals and self._screening_state(self._screening_rows(project_id, record_id), stage) != "include":
                raise ValueError("Title/abstract state must remain include after retrieval activity; reopening is not supported")
            event = dict(self._connection.execute("SELECT * FROM screening_events WHERE id = ?", (event_id,)).fetchone())
        return self._public_event(event)

    def record_decision(self, project_id, record_id, stage, decision, reviewer, reason=""):
        return self._append_decision(project_id, record_id, stage, decision, reviewer, reason, "review")

    def adjudicate(self, project_id, record_id, stage, decision, reviewer, reason=""):
        return self._append_decision(project_id, record_id, stage, decision, reviewer, reason, "adjudication")

    def set_full_text_status(self, project_id, record_id, status, reviewer, reason=""):
        self._record(project_id, record_id)
        if not isinstance(status, str) or status not in {"requested", "retrieved", "not_retrieved"}:
            raise ValueError("Full-text status must be requested, retrieved, or not_retrieved")
        self._validate_reviewer_reason(reviewer, reason)
        if status == "not_retrieved" and not reason.strip():
            raise ValueError("Full text not retrieved requires a reason")
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            if self._screening_state(self._screening_rows(project_id, record_id), "title_abstract") != "include":
                raise ValueError("Full-text retrieval requires title/abstract inclusion")
            retrievals = self._retrieval_rows(project_id, record_id)
            if retrievals and retrievals[-1]["status"] == "retrieved" and status != "retrieved":
                raise ValueError("Retrieved full text is terminal; reopening is not supported")
            event_id = str(uuid4())
            self._connection.execute(
                "INSERT INTO retrieval_events (id, project_id, record_id, status, reviewer, reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (event_id, project_id, record_id, status, reviewer, reason, _now()),
            )
            event = dict(self._connection.execute("SELECT * FROM retrieval_events WHERE id = ?", (event_id,)).fetchone())
        return self._public_event(event)

    def export_project(self, project_id, destination):
        from .exporters import write_export

        with self._snapshot():
            project = self._project(project_id)
            counts = self.counts(project_id)
            if not counts["all_checks_passed"]:
                raise ValueError("Cannot export: review counts do not reconcile")
            bundle = {
                "schema_version": 1, "project": project,
                "search_runs": self.list_search_runs(project_id),
                "records": self.list_records(project_id),
                "occurrences": self.get_occurrences(project_id),
                "decisions": self.list_decisions(project_id),
                "retrieval_events": self.list_retrieval_events(project_id),
                "counts": counts,
            }
            exclusions = []
            events_by_record = {}
            for event in self._screening_rows(project_id):
                events_by_record.setdefault(event["record_id"], []).append(event)
            for record in bundle["records"]:
                for stage, state_key in (("title_abstract", "title_abstract_state"), ("full_text", "full_text_state")):
                    if record[state_key] == "exclude":
                        active = self._active_decisions(events_by_record.get(record["id"], []), stage)
                        exclusions.append({
                            "record_id": record["id"], "stage": stage, "title": record["title"],
                            "reason": active[0]["reason"] if len(active) == 1 else "\n".join(f"{event['reviewer']}: {event['reason']}" for event in active),
                            "reviewers": [event["reviewer"] for event in active],
                            "kind": active[0]["kind"],
                        })
        return write_export(bundle, exclusions, destination)
