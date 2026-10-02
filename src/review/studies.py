"""Manual study identities and append-only report association proposals."""

import json
import math
from datetime import datetime, timezone
from uuid import uuid4


def _now():
    return datetime.now(timezone.utc).isoformat()


def _required(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Study linkage {field} must be nonempty")


def _json_value(value, parents=None):
    parents = set() if parents is None else parents
    if isinstance(value, (dict, list)):
        if id(value) in parents:
            raise ValueError("Study identifiers must not contain cyclic values")
        parents.add(id(value))
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("Study identifiers require string object keys")
        for child in value.values():
            _json_value(child, parents)
    elif isinstance(value, list):
        for child in value:
            _json_value(child, parents)
    elif value is None or isinstance(value, (str, bool, int)):
        return
    elif isinstance(value, float) and math.isfinite(value):
        return
    else:
        raise ValueError("Study identifiers must be finite JSON values")
    if isinstance(value, (dict, list)):
        parents.remove(id(value))


class StudyLedger:
    """Linkage operations sharing ReviewStore's connection and read snapshots."""

    def __init__(self, store):
        self.store = store
        store._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS studies (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                label TEXT NOT NULL, identifiers TEXT NOT NULL, reviewer TEXT NOT NULL,
                reason TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(project_id, id)
            );
            CREATE TABLE IF NOT EXISTS study_link_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                id TEXT NOT NULL UNIQUE, project_id TEXT NOT NULL, record_id TEXT NOT NULL,
                reviewer TEXT NOT NULL, reason TEXT NOT NULL, kind TEXT NOT NULL,
                created_at TEXT NOT NULL, UNIQUE(project_id, id),
                FOREIGN KEY(project_id, record_id) REFERENCES records(project_id, id)
            );
            CREATE INDEX IF NOT EXISTS study_link_events_record ON study_link_events(project_id, record_id, sequence);
            CREATE TABLE IF NOT EXISTS study_link_targets (
                project_id TEXT NOT NULL, event_id TEXT NOT NULL, study_id TEXT NOT NULL,
                PRIMARY KEY(project_id, event_id, study_id),
                FOREIGN KEY(project_id, event_id) REFERENCES study_link_events(project_id, id),
                FOREIGN KEY(project_id, study_id) REFERENCES studies(project_id, id)
            );
            """
        )

    def create_study(self, project_id, label, reviewer, reason, identifiers=None):
        self.store._project(project_id)
        for value, field in ((label, "label"), (reviewer, "reviewer"), (reason, "reason")):
            _required(value, field)
        if identifiers is None:
            identifiers = {}
        if not isinstance(identifiers, dict):
            raise ValueError("Study identifiers must be a JSON object")
        _json_value(identifiers)
        serialized = json.dumps(identifiers, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        event = {"id": str(uuid4()), "project_id": project_id, "label": label, "identifiers": json.loads(serialized), "reviewer": reviewer, "reason": reason, "created_at": _now()}
        with self.store._connection:
            self.store._connection.execute("BEGIN IMMEDIATE")
            self.store._connection.execute(
                "INSERT INTO studies VALUES (?, ?, ?, ?, ?, ?, ?)",
                (event["id"], project_id, label, serialized, reviewer, reason, event["created_at"]),
            )
        return event

    def list_studies(self, project_id):
        with self.store._snapshot():
            self.store._project(project_id)
            return [{**dict(row), "identifiers": json.loads(row["identifiers"])} for row in self.store._connection.execute(
                "SELECT * FROM studies WHERE project_id = ? ORDER BY rowid", (project_id,)
            ).fetchall()]

    def available(self, project_id):
        return bool(self.store._connection.execute(
            "SELECT EXISTS(SELECT 1 FROM studies WHERE project_id = ?) OR EXISTS(SELECT 1 FROM study_link_events WHERE project_id = ?)",
            (project_id, project_id),
        ).fetchone()[0])

    def _rows(self, project_id, record_id=None):
        query = "SELECT * FROM study_link_events WHERE project_id = ?"
        params = [project_id]
        if record_id is not None:
            query += " AND record_id = ?"
            params.append(record_id)
        events = [dict(row) for row in self.store._connection.execute(query + " ORDER BY sequence", params).fetchall()]
        targets = {}
        for row in self.store._connection.execute(
            "SELECT event_id, study_id FROM study_link_targets WHERE project_id = ? ORDER BY study_id", (project_id,)
        ).fetchall():
            targets.setdefault(row["event_id"], []).append(row["study_id"])
        for event in events:
            event["study_ids"] = targets.get(event["id"], [])
        return events

    @staticmethod
    def _public(event):
        return {key: value for key, value in event.items() if key != "sequence"}

    @staticmethod
    def _active(events):
        reviewers, adjudication, latest_review = {}, None, 0
        for event in events:
            if event["kind"] == "review":
                reviewers[event["reviewer"]] = event
                latest_review = event["sequence"]
            else:
                adjudication = event
        if adjudication is not None and adjudication["sequence"] > latest_review:
            return [adjudication]
        return sorted(reviewers.values(), key=lambda event: event["sequence"])

    def _append(self, project_id, record_id, study_ids, reviewer, reason, kind):
        self.store._record(project_id, record_id)
        _required(reviewer, "reviewer")
        _required(reason, "reason")
        if not isinstance(study_ids, list) or any(not isinstance(study_id, str) or not study_id.strip() for study_id in study_ids):
            raise ValueError("Study IDs must be a list of nonempty strings")
        if len(set(study_ids)) != len(study_ids):
            raise ValueError("Study IDs must be distinct")
        study_ids = sorted(study_ids)
        with self.store._connection:
            self.store._connection.execute("BEGIN IMMEDIATE")
            if kind == "adjudication" and not any(event["kind"] == "review" for event in self._rows(project_id, record_id)):
                raise ValueError("Study linkage adjudication requires an existing review event")
            for study_id in study_ids:
                if self.store._connection.execute(
                    "SELECT id FROM studies WHERE project_id = ? AND id = ?", (project_id, study_id)
                ).fetchone() is None:
                    raise ValueError(f"Unknown study in project: {study_id}")
            event = {"id": str(uuid4()), "project_id": project_id, "record_id": record_id, "study_ids": study_ids, "reviewer": reviewer, "reason": reason, "kind": kind, "created_at": _now()}
            self.store._connection.execute(
                "INSERT INTO study_link_events (id, project_id, record_id, reviewer, reason, kind, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (event["id"], project_id, record_id, reviewer, reason, kind, event["created_at"]),
            )
            self.store._connection.executemany(
                "INSERT INTO study_link_targets VALUES (?, ?, ?)",
                [(project_id, event["id"], study_id) for study_id in study_ids],
            )
        return event

    def record_study_links(self, project_id, record_id, study_ids, reviewer, reason):
        return self._append(project_id, record_id, study_ids, reviewer, reason, "review")

    def adjudicate_study_links(self, project_id, record_id, study_ids, reviewer, reason):
        return self._append(project_id, record_id, study_ids, reviewer, reason, "adjudication")

    def list_study_link_events(self, project_id, record_id=None):
        with self.store._snapshot():
            self.store._project(project_id)
            if record_id is not None:
                self.store._record(project_id, record_id)
            return [self._public(event) for event in self._rows(project_id, record_id)]

    def list_study_links(self, project_id, record_id=None):
        with self.store._snapshot():
            self.store._project(project_id)
            if record_id is not None:
                self.store._record(project_id, record_id)
            query = "SELECT id FROM records WHERE project_id = ?"
            params = [project_id]
            if record_id is not None:
                query += " AND id = ?"
                params.append(record_id)
            records = self.store._connection.execute(query + " ORDER BY rowid", params).fetchall()
            by_record = {}
            for event in self._rows(project_id, record_id):
                by_record.setdefault(event["record_id"], []).append(event)
            results = []
            for record in records:
                active = self._active(by_record.get(record["id"], []))
                sets = {tuple(event["study_ids"]) for event in active}
                if not active:
                    state, study_ids = "pending", []
                elif len(sets) > 1:
                    state, study_ids = "conflict", []
                else:
                    study_ids = list(next(iter(sets)))
                    state = "linked" if study_ids else "unlinked"
                results.append({"project_id": project_id, "record_id": record["id"], "state": state, "study_ids": study_ids, "active_event_ids": [event["id"] for event in active]})
            return results

    @staticmethod
    def add_counts(counts, records, links):
        """Count only associations on current eligible full-text inclusions."""
        included = {record["id"] for record in records if record["title_abstract_state"] == "include" and record["full_text_status"] == "retrieved" and record["full_text_state"] == "include"}
        current = [link for link in links if link["record_id"] in included]
        linked = [link for link in current if link["state"] == "linked"]
        study_ids = {study_id for link in linked for study_id in link["study_ids"]}
        counts.update({
            "study_linkage_available": True,
            "reports_included_linked": len(linked),
            "reports_included_awaiting_linkage": sum(link["state"] in {"pending", "unlinked"} for link in current),
            "reports_included_linkage_unresolved": sum(link["state"] == "conflict" for link in current),
            "linked_included_studies": len(study_ids),
            "study_linkage_complete": len(linked) == counts["reports_included"],
        })
        counts["included_studies"] = len(study_ids) if counts["study_linkage_complete"] else None
        counts["reconciliation"]["study_linkage"] = counts["reports_included"] == counts["reports_included_linked"] + counts["reports_included_awaiting_linkage"] + counts["reports_included_linkage_unresolved"]
