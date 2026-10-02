"""Manual source-anchored findings, immutable revisions, and reviewer events."""

import hashlib
import json
import math
from datetime import datetime, timezone
from uuid import uuid4


_CONTEXT = {"population", "comparison", "outcome", "timepoint", "analysis", "units", "notes"}
_ANCHOR = {"block_id", "start", "end", "quote"}
_APPRAISAL = {"instrument", "instrument_version", "domain"}
_REVISION_FIELDS = {"id", "evidence_id", "project_id", "record_id", "revision", "kind", "study_id", "document_id", "field", "value", "context", "anchor", "appraisal", "source_sha256", "blocks_sha256", "reviewer", "reason", "created_at"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _required(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Evidence {field} must be a nonempty string")


def _finite(value, parents=None):
    parents = set() if parents is None else parents
    if isinstance(value, (dict, list)):
        if id(value) in parents:
            raise ValueError("Evidence values must not contain cycles")
        parents.add(id(value))
        if isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise ValueError("Evidence JSON objects require string keys")
            children = value.values()
        else:
            children = value
        for child in children:
            _finite(child, parents)
        parents.remove(id(value))
    elif value is None or isinstance(value, (str, bool, int)):
        return
    elif not isinstance(value, float) or not math.isfinite(value):
        raise ValueError("Evidence values must be finite JSON")


def _json(value):
    try:
        _finite(value)
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (RecursionError, UnicodeError, TypeError):
        raise ValueError("Evidence values must be finite JSON") from None


def _hash(value):
    try:
        return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()
    except UnicodeError:
        raise ValueError("Evidence values must use valid Unicode") from None


def _inputs(field, value, context, anchor, reviewer, reason, kind, appraisal):
    for name, item in (("field", field), ("reviewer", reviewer), ("reason", reason)):
        _required(item, name)
    if not isinstance(kind, str) or kind not in {"finding", "appraisal"}:
        raise ValueError("Evidence kind must be finding or appraisal")
    if not isinstance(context, dict) or any(key not in _CONTEXT for key in context):
        raise ValueError("Evidence context requires only the supported context fields")
    if not isinstance(anchor, dict) or set(anchor) != _ANCHOR:
        raise ValueError("Evidence anchor requires exactly block_id, start, end, and quote")
    _required(anchor["block_id"], "anchor block_id")
    _required(anchor["quote"], "anchor quote")
    if any(isinstance(anchor[name], bool) or not isinstance(anchor[name], int) for name in ("start", "end")):
        raise ValueError("Evidence anchor offsets must be integers")
    if anchor["start"] < 0 or anchor["end"] <= anchor["start"]:
        raise ValueError("Evidence anchor has invalid half-open bounds")
    if kind == "finding":
        if appraisal is not None:
            raise ValueError("Finding evidence cannot include appraisal metadata")
    else:
        _required(value, "appraisal judgment")
        if not isinstance(appraisal, dict) or set(appraisal) != _APPRAISAL:
            raise ValueError("Appraisal requires instrument, instrument_version, and domain")
        for name, item in appraisal.items():
            _required(item, "appraisal " + name)
    # Detach all caller-owned containers before the transaction stores a revision.
    return json.loads(_json({"field": field, "value": value, "context": context, "anchor": anchor, "reviewer": reviewer, "reason": reason, "appraisal": appraisal}))


class EvidenceLedger:
    """Evidence operations sharing the ledger connection and explicit snapshots."""

    def __init__(self, store):
        self.store = store
        store._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS evidence_entries (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
                project_id TEXT NOT NULL, record_id TEXT NOT NULL, kind TEXT NOT NULL,
                UNIQUE(project_id, id),
                FOREIGN KEY(project_id, record_id) REFERENCES records(project_id, id)
            );
            CREATE TABLE IF NOT EXISTS evidence_revisions (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
                project_id TEXT NOT NULL, evidence_id TEXT NOT NULL, revision INTEGER NOT NULL,
                payload TEXT NOT NULL, revision_sha256 TEXT NOT NULL,
                UNIQUE(project_id, id), UNIQUE(evidence_id, revision),
                FOREIGN KEY(project_id, evidence_id) REFERENCES evidence_entries(project_id, id)
            );
            CREATE INDEX IF NOT EXISTS evidence_revisions_entry ON evidence_revisions(project_id, evidence_id, revision);
            CREATE TABLE IF NOT EXISTS evidence_review_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
                project_id TEXT NOT NULL, evidence_id TEXT NOT NULL, revision_id TEXT NOT NULL,
                decision TEXT NOT NULL, reviewer TEXT NOT NULL, reason TEXT NOT NULL,
                kind TEXT NOT NULL, created_at TEXT NOT NULL,
                FOREIGN KEY(project_id, evidence_id) REFERENCES evidence_entries(project_id, id),
                FOREIGN KEY(project_id, revision_id) REFERENCES evidence_revisions(project_id, id)
            );
            CREATE INDEX IF NOT EXISTS evidence_review_events_entry ON evidence_review_events(project_id, evidence_id, sequence);
            """
        )

    def _entry(self, project_id, evidence_id):
        self.store._project(project_id)
        _required(evidence_id, "ID")
        entry = self.store._connection.execute("SELECT * FROM evidence_entries WHERE project_id = ? AND id = ?", (project_id, evidence_id)).fetchone()
        if entry is None:
            raise ValueError(f"Unknown evidence in project: {evidence_id}")
        return entry

    def _study(self, project_id, study_id):
        _required(study_id, "study ID")
        if self.store._connection.execute("SELECT id FROM studies WHERE project_id = ? AND id = ?", (project_id, study_id)).fetchone() is None:
            raise ValueError(f"Unknown study in project: {study_id}")

    def _document(self, project_id, record_id, document_id, cache=None):
        _required(document_id, "document ID")
        if cache is not None and document_id in cache:
            metadata, blocks = cache[document_id]
        else:
            row = self.store._connection.execute("SELECT * FROM source_documents WHERE project_id = ? AND id = ?", (project_id, document_id)).fetchone()
            if row is None:
                raise ValueError(f"Unknown source document in project: {document_id}")
            _, blocks = self.store._documents._checked(project_id, document_id)
            metadata = dict(row)
            if cache is not None:
                cache[document_id] = metadata, blocks
        if metadata["record_id"] != record_id:
            raise ValueError("Evidence source document belongs to a different report")
        return metadata, blocks

    @staticmethod
    def _anchor(anchor, blocks):
        block = next((block for block in blocks if block["id"] == anchor["block_id"]), None)
        if block is None:
            raise ValueError("Evidence anchor identifies an unknown source block")
        if anchor["end"] > len(block["text"]) or block["text"][anchor["start"]:anchor["end"]] != anchor["quote"]:
            raise ValueError("Evidence anchor quote does not match its source bounds")
        return {**anchor, "locator": block["locator"]}

    def _dependencies(self, revision):
        project, record = revision["project_id"], revision["record_id"]
        issues = []
        active = self.store._connection.execute("SELECT id FROM source_documents WHERE project_id = ? AND record_id = ? ORDER BY version DESC LIMIT 1", (project, record)).fetchone()
        if active is None or active["id"] != revision["document_id"]:
            issues.append("stale_source")
        source = self.store._connection.execute("SELECT source_identifiers FROM source_documents WHERE project_id = ? AND id = ?", (project, revision["document_id"])).fetchone()
        try:
            identifiers = json.loads(source["source_identifiers"])
            if not isinstance(identifiers, dict):
                raise ValueError("Invalid source identifiers")
        except (ValueError, TypeError):
            raise ValueError("Stored evidence source identifiers are corrupt") from None
        canonical = self.store._record(project, record)
        if any(canonical[name] is not None and canonical[name] != identifiers[name] for name in ("doi", "pmid") if name in identifiers):
            issues.append("source_identity_conflict")
        events = self.store._screening_rows(project, record)
        retrievals = self.store._retrieval_rows(project, record)
        if self.store._screening_state(events, "title_abstract") != "include" or not retrievals or retrievals[-1]["status"] != "retrieved" or self.store._screening_state(events, "full_text") != "include":
            issues.append("ineligible_report")
        linkage = self.store.list_study_links(project, record)[0]
        if linkage["state"] != "linked":
            issues.append("unresolved_linkage")
        elif revision["study_id"] not in linkage["study_ids"]:
            issues.append("study_not_linked")
        return issues

    def _append_revision(self, project_id, evidence_id, record_id, kind, study_id, document_id, inputs):
        self.store._record(project_id, record_id)
        self._study(project_id, study_id)
        document, blocks = self._document(project_id, record_id, document_id)
        inputs["anchor"] = self._anchor(inputs["anchor"], blocks)
        revision = {"id": str(uuid4()), "evidence_id": evidence_id, "project_id": project_id, "record_id": record_id, "revision": self.store._connection.execute("SELECT COALESCE(MAX(revision), 0) + 1 FROM evidence_revisions WHERE evidence_id = ?", (evidence_id,)).fetchone()[0], "kind": kind, "study_id": study_id, "document_id": document_id, **inputs, "source_sha256": document["source_sha256"], "blocks_sha256": document["blocks_sha256"], "created_at": _now()}
        issues = self._dependencies(revision)
        if issues:
            raise ValueError("Evidence requires current eligible source and study linkage: " + ", ".join(issues))
        revision_hash = _hash(revision)
        self.store._connection.execute("INSERT INTO evidence_revisions (id, project_id, evidence_id, revision, payload, revision_sha256) VALUES (?, ?, ?, ?, ?, ?)", (revision["id"], project_id, evidence_id, revision["revision"], _json(revision), revision_hash))
        return {**revision, "revision_sha256": revision_hash}

    def propose_evidence(self, project_id, record_id, study_id, document_id, field, value, context, anchor, reviewer, reason, *, kind="finding", appraisal=None):
        inputs = _inputs(field, value, context, anchor, reviewer, reason, kind, appraisal)
        with self.store._connection:
            self.store._connection.execute("BEGIN IMMEDIATE")
            self.store._record(project_id, record_id)
            evidence_id = str(uuid4())
            self.store._connection.execute("INSERT INTO evidence_entries (id, project_id, record_id, kind) VALUES (?, ?, ?, ?)", (evidence_id, project_id, record_id, kind))
            result = self._append_revision(project_id, evidence_id, record_id, kind, study_id, document_id, inputs)
        return result

    def revise_evidence(self, project_id, evidence_id, study_id, document_id, field, value, context, anchor, reviewer, reason, *, appraisal=None):
        with self.store._connection:
            self.store._connection.execute("BEGIN IMMEDIATE")
            entry = self._entry(project_id, evidence_id)
            self._revisions(project_id, evidence_id)
            inputs = _inputs(field, value, context, anchor, reviewer, reason, entry["kind"], appraisal)
            result = self._append_revision(project_id, evidence_id, entry["record_id"], entry["kind"], study_id, document_id, inputs)
        return result

    def _validated_revision(self, row, cache):
        try:
            revision = json.loads(row["payload"])
            if not isinstance(revision, dict) or set(revision) != _REVISION_FIELDS or _hash(revision) != row["revision_sha256"]:
                raise ValueError("Revision hash or payload mismatch")
            if any(revision[key] != row[key] for key in ("id", "project_id", "evidence_id", "revision")):
                raise ValueError("Revision storage identity mismatch")
            entry = self._entry(row["project_id"], row["evidence_id"])
            if revision["record_id"] != entry["record_id"] or revision["kind"] != entry["kind"] or isinstance(revision["revision"], bool) or not isinstance(revision["revision"], int) or revision["revision"] < 1:
                raise ValueError("Revision entry identity mismatch")
            if not isinstance(revision["anchor"], dict) or set(revision["anchor"]) != _ANCHOR | {"locator"}:
                raise ValueError("Revision anchor shape mismatch")
            inputs = _inputs(revision["field"], revision["value"], revision["context"], {key: revision["anchor"][key] for key in _ANCHOR}, revision["reviewer"], revision["reason"], revision["kind"], revision["appraisal"])
            self.store._record(row["project_id"], revision["record_id"])
            self._study(row["project_id"], revision["study_id"])
            document, blocks = self._document(row["project_id"], revision["record_id"], revision["document_id"], cache)
            if revision["source_sha256"] != document["source_sha256"] or revision["blocks_sha256"] != document["blocks_sha256"] or revision["anchor"] != self._anchor(inputs["anchor"], blocks):
                raise ValueError("Revision source hash or anchor mismatch")
        except (ValueError, TypeError, KeyError, RecursionError):
            raise ValueError("Stored evidence revision/hash/anchor or source integrity is corrupt") from None
        return {**revision, "revision_sha256": row["revision_sha256"]}

    def _revisions(self, project_id, evidence_id=None, record_id=None):
        query = "SELECT r.* FROM evidence_revisions r JOIN evidence_entries e ON e.id = r.evidence_id WHERE r.project_id = ?"
        params = [project_id]
        if evidence_id is not None:
            query += " AND r.evidence_id = ?"
            params.append(evidence_id)
        if record_id is not None:
            query += " AND e.record_id = ?"
            params.append(record_id)
        cache = {}
        return [self._validated_revision(row, cache) for row in self.store._connection.execute(query + " ORDER BY r.sequence", params).fetchall()]

    def _events(self, project_id, evidence_id=None):
        query, params = "SELECT * FROM evidence_review_events WHERE project_id = ?", [project_id]
        if evidence_id is not None:
            query += " AND evidence_id = ?"
            params.append(evidence_id)
        return [dict(row) for row in self.store._connection.execute(query + " ORDER BY sequence", params).fetchall()]

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

    def _review(self, project_id, revision_id, decision, reviewer, reason, kind):
        if not isinstance(decision, str) or decision not in {"confirm", "reject"}:
            raise ValueError("Evidence decision must be confirm or reject")
        _required(reviewer, "reviewer")
        _required(reason, "reason")
        with self.store._connection:
            self.store._connection.execute("BEGIN IMMEDIATE")
            self.store._project(project_id)
            row = self.store._connection.execute("SELECT * FROM evidence_revisions WHERE project_id = ? AND id = ?", (project_id, revision_id)).fetchone()
            if row is None:
                raise ValueError(f"Unknown evidence revision in project: {revision_id}")
            revisions = self._revisions(project_id, row["evidence_id"])
            revision = revisions[-1]
            if revision["id"] != revision_id:
                raise ValueError("Evidence verification requires the current revision")
            if reviewer == revision["reviewer"]:
                raise ValueError("Evidence verification requires a reviewer distinct from the revision author")
            issues = self._dependencies(revision)
            if issues:
                raise ValueError("Evidence verification requires current dependencies: " + ", ".join(issues))
            events = [event for event in self._events(project_id, row["evidence_id"]) if event["revision_id"] == revision_id]
            if kind == "adjudication" and not any(event["kind"] == "review" for event in events):
                raise ValueError("Evidence adjudication requires an existing review of this revision")
            event = {"id": str(uuid4()), "project_id": project_id, "evidence_id": row["evidence_id"], "revision_id": revision_id, "decision": decision, "reviewer": reviewer, "reason": reason, "kind": kind, "created_at": _now()}
            self.store._connection.execute("INSERT INTO evidence_review_events (id, project_id, evidence_id, revision_id, decision, reviewer, reason, kind, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(event.values()))
        return event

    def review_evidence(self, project_id, revision_id, decision, reviewer, reason):
        return self._review(project_id, revision_id, decision, reviewer, reason, "review")

    def adjudicate_evidence(self, project_id, revision_id, decision, reviewer, reason):
        return self._review(project_id, revision_id, decision, reviewer, reason, "adjudication")

    def list_evidence_revisions(self, project_id, evidence_id=None):
        with self.store._snapshot():
            self.store._project(project_id)
            if evidence_id is not None:
                self._entry(project_id, evidence_id)
            return self._revisions(project_id, evidence_id)

    def list_evidence_reviews(self, project_id, evidence_id=None):
        with self.store._snapshot():
            self.store._project(project_id)
            if evidence_id is not None:
                self._entry(project_id, evidence_id)
            self._revisions(project_id, evidence_id)
            return [{key: value for key, value in event.items() if key != "sequence"} for event in self._events(project_id, evidence_id)]

    def list_evidence(self, project_id, record_id=None, *, verified_only=False):
        with self.store._snapshot():
            self.store._project(project_id)
            if record_id is not None:
                self.store._record(project_id, record_id)
            current = {}
            for revision in self._revisions(project_id, record_id=record_id):
                current[revision["evidence_id"]] = revision
            events = {}
            for event in self._events(project_id):
                events.setdefault(event["revision_id"], []).append(event)
            results = []
            for evidence_id, revision in current.items():
                active = self._active(events.get(revision["id"], []))
                decisions = {event["decision"] for event in active}
                verification = "proposed" if not active else ("conflict" if len(decisions) > 1 else ("confirmed" if "confirm" in decisions else "rejected"))
                issues = self._dependencies(revision)
                result = {"evidence_id": evidence_id, "project_id": project_id, "record_id": revision["record_id"], "current_revision": revision, "verification_state": verification, "dependency_issues": issues, "state": issues[0] if issues else verification, "verified": verification == "confirmed" and not issues, "active_verification_event_ids": [event["id"] for event in active]}
                if not verified_only or result["verified"]:
                    results.append(result)
            return results
