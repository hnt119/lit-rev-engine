"""Opt-in protocol and intake bindings over the existing review ledger.

This is not a screening engine. Original occurrences, human decision events,
documents, study links and counts remain owned by ReviewStore. No operation
performs network access, inference, automatic selection or exclusion.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
from uuid import uuid4

from .importers import load_records_bytes
from .models import SearchRunSpec
from .store import _now


def _json(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        raise ValueError("Pilot fields must be finite JSON values") from None


def _hash(value):
    return hashlib.sha256(value if isinstance(value, bytes) else _json(value).encode()).hexdigest()


def _text(value, label, *, optional=False, maximum=10000):
    if not isinstance(value, str) or (not optional and not value.strip()) or len(value) > maximum:
        raise ValueError(f"Pilot {label} must be {'a' if optional else 'a nonempty'} string of at most {maximum} characters")
    return value


def _filename(value):
    _text(value, "filename", maximum=240)
    if value in {".", ".."} or "/" in value or "\\" in value or any(ord(c) < 32 for c in value):
        raise ValueError("Pilot filename must be a simple filename")
    return value


class PilotConflict(ValueError):
    """An expected immutable protocol or ledger head no longer matches."""


class PilotLedger:
    """Append-only pilot metadata sharing the authoritative ReviewStore database."""

    MAX_BYTES = 32 * 1024 * 1024

    def __init__(self, store):
        self.store = store
        store._connection.executescript("""
            CREATE TABLE IF NOT EXISTS pilot_bindings (
                workspace_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL UNIQUE REFERENCES projects(id),
                purpose TEXT NOT NULL, request_id TEXT NOT NULL,
                fingerprint TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pilot_protocols (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                number INTEGER NOT NULL, previous_id TEXT, content TEXT NOT NULL,
                sha256 TEXT NOT NULL, reviewer TEXT NOT NULL, reason TEXT NOT NULL,
                created_at TEXT NOT NULL, UNIQUE(project_id, number)
            );
            CREATE TABLE IF NOT EXISTS pilot_requests (
                project_id TEXT NOT NULL REFERENCES projects(id), request_id TEXT NOT NULL,
                action TEXT NOT NULL, fingerprint TEXT NOT NULL, result TEXT NOT NULL,
                created_at TEXT NOT NULL, PRIMARY KEY(project_id, request_id)
            );
            CREATE TABLE IF NOT EXISTS pilot_intakes (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                search_run_id TEXT NOT NULL, protocol_id TEXT NOT NULL REFERENCES pilot_protocols(id),
                filename TEXT NOT NULL, format TEXT NOT NULL, scope TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id, search_run_id) REFERENCES search_runs(project_id, id)
            );
            CREATE TABLE IF NOT EXISTS pilot_intake_assets (
                intake_id TEXT NOT NULL REFERENCES pilot_intakes(id), name TEXT NOT NULL,
                content BLOB NOT NULL, sha256 TEXT NOT NULL,
                PRIMARY KEY(intake_id, name)
            );
            CREATE TABLE IF NOT EXISTS pilot_event_bindings (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                protocol_id TEXT NOT NULL REFERENCES pilot_protocols(id),
                event_id TEXT NOT NULL, event_kind TEXT NOT NULL,
                ledger_digest_before TEXT NOT NULL, created_at TEXT NOT NULL,
                UNIQUE(project_id, event_id, event_kind)
            );
            CREATE TABLE IF NOT EXISTS pilot_source_metadata (
                document_id TEXT PRIMARY KEY REFERENCES source_documents(id),
                project_id TEXT NOT NULL REFERENCES projects(id),
                protocol_id TEXT NOT NULL REFERENCES pilot_protocols(id),
                source_kind TEXT NOT NULL, license TEXT NOT NULL, attribution TEXT NOT NULL,
                permission_note TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pilot_handoffs (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                protocol_id TEXT NOT NULL REFERENCES pilot_protocols(id),
                ledger_digest_before TEXT NOT NULL, receipt TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pilot_handoff_operations (
                project_id TEXT NOT NULL REFERENCES projects(id), request_id TEXT NOT NULL,
                fingerprint TEXT NOT NULL, status TEXT NOT NULL, phase TEXT NOT NULL,
                input TEXT NOT NULL, partial_ids TEXT NOT NULL, error_code TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                PRIMARY KEY(project_id, request_id)
            );
        """)

    def _binding(self, workspace_id):
        _text(workspace_id, "workspace identity", maximum=200)
        row = self.store._connection.execute("SELECT * FROM pilot_bindings WHERE workspace_id=?", (workspace_id,)).fetchone()
        if row is None:
            raise ValueError("No isolated review pilot is initialized for this workspace")
        return dict(row)

    def project(self, workspace_id):
        return self.store.get_project(self._binding(workspace_id)["project_id"])

    def _protocols(self, project_id):
        rows = self.store._connection.execute("SELECT * FROM pilot_protocols WHERE project_id=? ORDER BY number", (project_id,)).fetchall()
        history = []
        for row in rows:
            revision = {**dict(row), "content": json.loads(row["content"])}
            if revision["sha256"] != _hash(revision["content"]) or revision["number"] != len(history)+1 or revision["previous_id"] != (history[-1]["id"] if history else None):
                raise ValueError("Stored pilot protocol revision hash/history is corrupt")
            history.append(revision)
        return history

    @staticmethod
    def _protocol_content(value):
        if not isinstance(value, dict) or len(_json(value).encode()) > 65536:
            raise ValueError("Pilot protocol content must be a JSON object of at most 64 KiB")
        content = json.loads(_json(value))
        content.setdefault("reference", "")
        content.setdefault("eligibility", {})
        content.setdefault("reviewer_roles", {})
        content.setdefault("fields", [])
        content.setdefault("unresolved", ["Protocol choices have not been supplied"])
        content.setdefault("ready_for_screening", False)
        _text(content["reference"], "protocol reference", optional=True)
        if not isinstance(content["eligibility"], dict) or not isinstance(content["reviewer_roles"], (dict, list)):
            raise ValueError("Protocol eligibility and reviewer roles must be structured supplied choices")
        if not isinstance(content["fields"], list) or not isinstance(content["unresolved"], list) or any(not isinstance(x, str) or not x.strip() for x in content["unresolved"]):
            raise ValueError("Protocol fields and explicit unresolved choices must be arrays")
        if type(content["ready_for_screening"]) is not bool:
            raise ValueError("Protocol readiness must be an explicit boolean")
        if content["ready_for_screening"] and (content["unresolved"] or not content["reference"].strip() or not content["eligibility"] or not content["reviewer_roles"]):
            raise ValueError("Ready protocol requires a reference, supplied eligibility/reviewer roles, and no unresolved choices")
        return content

    def initialize(self, workspace_id, payload):
        if not isinstance(payload, dict):
            raise ValueError("Pilot initialization requires an object")
        _text(workspace_id, "workspace identity", maximum=200)
        request_id = _text(payload.get("request_id"), "request ID", maximum=200)
        purpose = payload.get("purpose")
        if purpose not in {"research_pilot", "software_usability"}:
            raise ValueError("Pilot purpose must explicitly be research_pilot or software_usability")
        protocol = self._protocol_content(payload.get("protocol", {}))
        fingerprint = _hash(payload)
        with self.store._write_transaction():
            prior = self.store._connection.execute("SELECT * FROM pilot_bindings WHERE workspace_id=?", (workspace_id,)).fetchone()
            if prior is not None:
                if prior["request_id"] != request_id or prior["fingerprint"] != fingerprint:
                    raise PilotConflict("This workspace already has an isolated pilot; initialization cannot replace it")
            else:
                project = self.store.create_project(payload.get("title"), payload.get("review_type", "systematic"), payload.get("question"), _json(protocol), protocol["eligibility"])
                self.store._connection.execute("INSERT INTO pilot_bindings VALUES(?,?,?,?,?,?)", (workspace_id, project["id"], purpose, request_id, fingerprint, _now()))
                self._append_protocol(project["id"], protocol, payload.get("reviewer", "Declared local operator"), payload.get("reason", "Initial supplied protocol; unresolved choices preserved"))
        return self.view(workspace_id)

    def _append_protocol(self, project_id, content, reviewer, reason):
        _text(reviewer, "reviewer"); _text(reason, "reason")
        history = self._protocols(project_id)
        revision = {"id": str(uuid4()), "project_id": project_id, "number": len(history)+1, "previous_id": history[-1]["id"] if history else None,
                    "content": content, "sha256": _hash(content), "reviewer": reviewer, "reason": reason, "created_at": _now()}
        self.store._connection.execute("INSERT INTO pilot_protocols VALUES(?,?,?,?,?,?,?,?,?)", (revision["id"], project_id, revision["number"], revision["previous_id"], _json(content), revision["sha256"], reviewer, reason, revision["created_at"]))
        return revision

    def _state(self, project_id):
        protocols = self._protocols(project_id)
        return {
            "protocol_id": protocols[-1]["id"],
            "records": self.store.list_records(project_id),
            "occurrences": self.store.get_occurrences(project_id),
            "search_runs": self.store.list_search_runs(project_id),
            "decisions": self.store.list_decisions(project_id),
            "retrieval_events": self.store.list_retrieval_events(project_id),
            "documents": self.store.list_documents(project_id),
            "studies": self.store.list_studies(project_id),
            "study_link_events": self.store.list_study_link_events(project_id),
            "intakes": [row["id"] for row in self.store._connection.execute("SELECT id FROM pilot_intakes WHERE project_id=? ORDER BY rowid", (project_id,))],
            "handoffs": [row["id"] for row in self.store._connection.execute("SELECT id FROM pilot_handoffs WHERE project_id=? ORDER BY rowid", (project_id,))],
        }

    def _mutate(self, workspace_id, payload, action, operation, *, extra=None, screening=False):
        if not isinstance(payload, dict):
            raise ValueError("Pilot mutation requires an object")
        request_id = _text(payload.get("request_id"), "request ID", maximum=200)
        reviewer = _text(payload.get("reviewer"), "reviewer")
        reason = _text(payload.get("reason"), "reason")
        fingerprint = _hash({"action": action, "payload": payload, "extra": extra})
        with self.store._write_transaction():
            binding = self._binding(workspace_id); project_id = binding["project_id"]
            prior = self.store._connection.execute("SELECT * FROM pilot_requests WHERE project_id=? AND request_id=?", (project_id, request_id)).fetchone()
            if prior is not None:
                if prior["fingerprint"] != fingerprint or prior["action"] != action:
                    raise PilotConflict("Pilot request ID was already used with different content")
                result = json.loads(prior["result"])
            else:
                protocol = self._protocols(project_id)[-1]
                digest = _hash(self._state(project_id))
                if payload.get("expected_protocol_id") != protocol["id"]:
                    raise PilotConflict("Pilot protocol changed; reload the current revision before editing")
                if payload.get("expected_ledger_digest") != digest:
                    raise PilotConflict("Pilot library or review history changed; reload before editing")
                if screening and binding["purpose"] == "research_pilot" and not protocol["content"]["ready_for_screening"]:
                    raise ValueError("Real research screening is blocked while protocol choices remain unresolved")
                result = operation(project_id, protocol, digest, reviewer, reason)
                result = {**result, "pilot_actor": reviewer, "pilot_reason": reason}
                self.store._connection.execute("INSERT INTO pilot_requests VALUES(?,?,?,?,?,?)", (project_id, request_id, action, fingerprint, _json(result), _now()))
        return {**self.view(workspace_id), "result": result}

    def revise_protocol(self, workspace_id, payload):
        content = self._protocol_content(payload.get("content"))
        return self._mutate(workspace_id, payload, "protocol", lambda pid, protocol, digest, reviewer, reason: self._append_protocol(pid, content, reviewer, reason))

    def _bind_event(self, project_id, protocol, digest, event, kind):
        self.store._connection.execute("INSERT INTO pilot_event_bindings VALUES(?,?,?,?,?,?,?)", (str(uuid4()), project_id, protocol["id"], event["id"], kind, digest, _now()))

    def _store_intake(self, project_id, protocol, imported, filename, format, scope, assets):
        intake_id = str(uuid4())
        self.store._connection.execute("INSERT INTO pilot_intakes VALUES(?,?,?,?,?,?,?,?)", (intake_id, project_id, imported["search_run_id"], protocol["id"], filename, format, scope, _now()))
        for name, content in assets.items():
            self.store._connection.execute("INSERT INTO pilot_intake_assets VALUES(?,?,?,?)", (intake_id, name, content, _hash(content)))
        return {**imported, "intake_id": intake_id, "scope": scope}

    def import_file(self, workspace_id, content, filename, payload, *, extra_assets=None):
        filename = _filename(filename)
        if not isinstance(content, bytes) or len(content) > self.MAX_BYTES:
            raise ValueError("Pilot input must be bytes of at most 32 MiB")
        scope = payload.get("scope", "supplied_file")
        if scope not in {"supplied_file", "exploratory_subset"}:
            raise ValueError("Ordinary imports cannot declare a complete query capture")
        records = load_records_bytes(content, payload.get("format"), source_name=filename)
        assets = {filename: content}
        if extra_assets is not None:
            if not isinstance(extra_assets, dict) or len(extra_assets) > 1000:
                raise ValueError("Additional pilot intake artifacts must be a bounded name/bytes map")
            for name, data in extra_assets.items():
                if not isinstance(name, str) or not name or "\\" in name or any(ord(c) < 32 for c in name):
                    raise ValueError("Additional pilot intake artifact path is unsafe")
                path = PurePosixPath(name)
                if path.is_absolute() or ".." in path.parts or path.as_posix() != name or name in assets or not isinstance(data, bytes):
                    raise ValueError("Additional pilot intake artifact path or bytes are unsafe")
                assets[name] = data
            if sum(map(len, assets.values())) > self.MAX_BYTES:
                raise ValueError("Combined pilot intake artifacts exceed 32 MiB")
        spec = SearchRunSpec(source=payload.get("source", "Supplied bibliography export"), query=payload.get("query"), searched_at=payload.get("searched_at"),
                             filters=payload.get("filters", {}), notes=payload.get("notes", "") + " [Pilot intake scope: " + scope + "; exact supplied bytes retained; query completeness not established]",
                             import_format=payload.get("format"), source_file=filename, source_sha256=_hash(content), reported_count=payload.get("reported_count"))
        def operation(project_id, protocol, digest, reviewer, reason):
            imported = self.store.import_records(project_id, spec, records, idempotency_key="pilot:"+payload["request_id"])
            return self._store_intake(project_id, protocol, imported, filename, payload["format"], scope, assets)
        return self._mutate(workspace_id, payload, "import_file", operation, extra={"filename": filename, "assets":{name:_hash(data) for name,data in assets.items()}})

    def import_capture(self, workspace_id, artifacts, payload):
        from src.search.pubmed_search import validate_pubmed_artifacts
        if not isinstance(artifacts, dict) or any(not isinstance(x, bytes) for x in artifacts.values()) or sum(map(len, artifacts.values())) > self.MAX_BYTES:
            raise ValueError("Pilot capture requires at most 32 MiB of exact artifact bytes")
        validated = validate_pubmed_artifacts(artifacts); receipt = validated["receipt"]
        spec = SearchRunSpec(source="PubMed", query=receipt["query"], searched_at=receipt["searched_at"], filters=receipt["filters"],
                             import_format="pubmed_xml", source_file="/retained-pilot-capture/records.xml", source_sha256=receipt["records_sha256"],
                             reported_count=receipt["reported_count"], execution=receipt,
                             notes="Offline verified complete saved PubMed capture; logical retained source path; no new live search performed")
        def operation(project_id, protocol, digest, reviewer, reason):
            imported = self.store.import_records(project_id, spec, validated["records"], idempotency_key="pilot:"+payload["request_id"], artifacts=artifacts)
            return self._store_intake(project_id, protocol, imported, "records.xml", "pubmed_xml", "complete_saved_capture", artifacts)
        return self._mutate(workspace_id, payload, "import_capture", operation, extra={name: _hash(content) for name, content in artifacts.items()})

    def record_decision(self, workspace_id, payload):
        def operation(project_id, protocol, digest, reviewer, reason):
            if type(payload.get("adjudication", False)) is not bool:
                raise ValueError("Adjudication must be explicit boolean")
            if payload.get("stage") == "full_text" and not any(source["record_id"] == payload.get("record_id") and source["active"] and source.get("source_kind") == "full_text" for source in self._sources(project_id)):
                raise ValueError("Full-text decisions require a current attached full-text source")
            method = self.store.adjudicate if payload.get("adjudication") else self.store.record_decision
            event = method(project_id, payload.get("record_id"), payload.get("stage"), payload.get("decision"), reviewer, reason)
            self._bind_event(project_id, protocol, digest, event, "screening")
            return event
        return self._mutate(workspace_id, payload, "decision", operation, screening=True)

    def set_status(self, workspace_id, payload):
        def operation(project_id, protocol, digest, reviewer, reason):
            if payload.get("status") == "retrieved":
                sources = self._sources(project_id)
                if not any(s["record_id"] == payload.get("record_id") and s["active"] and s.get("source_kind") == "full_text" for s in sources):
                    raise ValueError("Retrieved full-text status requires an attached current full-text source; abstract-only coverage is insufficient")
            event = self.store.set_full_text_status(project_id, payload.get("record_id"), payload.get("status"), reviewer, reason)
            self._bind_event(project_id, protocol, digest, event, "retrieval_status")
            return event
        return self._mutate(workspace_id, payload, "status", operation, screening=True)

    def attach_source(self, workspace_id, content, filename, payload):
        filename = _filename(filename)
        if not isinstance(content, bytes) or len(content) > self.MAX_BYTES:
            raise ValueError("Pilot source must be bytes of at most 32 MiB")
        kind = payload.get("source_kind")
        if kind not in {"abstract", "full_text"}:
            raise ValueError("Source kind must explicitly be abstract or full_text")
        for name in ("license", "attribution", "permission_note"):
            _text(payload.get(name), name)
        _text(payload.get("source_url", ""), "source URL", optional=True)
        def operation(project_id, protocol, digest, reviewer, reason):
            if kind == "abstract":
                record = self.store._record(project_id, payload.get("record_id")); canonical = json.loads(record["payload"])
                if payload.get("format") != "txt" or not canonical["abstract"] or content != canonical["abstract"].encode("utf-8"):
                    raise ValueError("Abstract-only source must exactly match this report's retained bibliography abstract bytes")
            document = self.store.attach_document(project_id, payload.get("record_id"), content, payload.get("format"), reviewer, reason, filename=filename, source_url=payload.get("source_url", ""), version_label=payload.get("version_label", ""))
            self.store._connection.execute("INSERT INTO pilot_source_metadata VALUES(?,?,?,?,?,?,?,?)", (document["id"], project_id, protocol["id"], kind, payload["license"], payload["attribution"], payload["permission_note"], _now()))
            self._bind_event(project_id, protocol, digest, document, "source_attachment")
            return {**document, "source_kind": kind}
        return self._mutate(workspace_id, payload, "source", operation, extra={"filename": filename, "sha256": _hash(content)})

    def _sources(self, project_id):
        metadata = {row["document_id"]: dict(row) for row in self.store._connection.execute("SELECT * FROM pilot_source_metadata WHERE project_id=?", (project_id,))}
        return [{**document, **{k:v for k,v in metadata.get(document["id"], {}).items() if k not in {"project_id", "created_at"}}} for document in self.store.list_documents(project_id)]

    def source(self, workspace_id, document_id):
        with self.store._snapshot():
            project_id = self._binding(workspace_id)["project_id"]
            documents = {d["id"]: d for d in self._sources(project_id)}
            if document_id not in documents:
                raise ValueError("Unknown source in this isolated pilot")
            return {"document": documents[document_id], "metadata": documents[document_id], "content": self.store.get_document_bytes(project_id, document_id), "blocks": self.store.get_source_blocks(project_id, document_id)}

    def record_handoff(self, workspace_id, payload):
        """Record a caller-validated existing comparison receipt without creating it."""
        def operation(project_id, protocol, digest, reviewer, reason):
            receipt = payload.get("receipt")
            self._validate_handoff_receipt(project_id, receipt)
            return self._insert_handoff(project_id, protocol, digest, receipt, reviewer, reason)
        return self._mutate(workspace_id, payload, "handoff", operation, screening=True)

    def publish_handoff(self, workspace_id, payload, callback):
        """Serialize source/CAS checks and publication; retain failed partial IDs.

        The callback receives ``progress(phase, partial_ids)`` and returns the
        existing comparison services' exact immutable receipt. No new screening
        or eligibility is inferred. Completed retries never invoke it again.
        External stores cannot be rolled back by SQLite: callers must report
        partial immutable IDs and reuse/clean them explicitly on retry.
        """
        request_id = _text(payload.get("request_id"), "request ID", maximum=200)
        fingerprint = _hash(payload)
        progress_state = {"phase": "validated", "partial_ids": {}}
        with self.store._write_transaction():
            project_id = self._binding(workspace_id)["project_id"]
            prior = self.store._connection.execute("SELECT * FROM pilot_handoff_operations WHERE project_id=? AND request_id=?", (project_id, request_id)).fetchone()
            if prior is not None and prior["fingerprint"] != fingerprint:
                raise PilotConflict("Handoff request ID was already used for different inputs")
            completed_request = self.store._connection.execute("SELECT * FROM pilot_requests WHERE project_id=? AND request_id=?", (project_id, request_id)).fetchone()
            if completed_request is None:
                _text(payload.get("reviewer"), "reviewer"); _text(payload.get("reason"), "reason")
                protocol = self._protocols(project_id)[-1]
                if payload.get("expected_protocol_id") != protocol["id"] or payload.get("expected_ledger_digest") != _hash(self._state(project_id)):
                    raise PilotConflict("Pilot changed before handoff; reload before publishing")
                self._validate_handoff_receipt(project_id, payload.get("receipt"))
            if prior is not None:
                progress_state["partial_ids"] = json.loads(prior["partial_ids"])
            else:
                self.store._connection.execute("INSERT INTO pilot_handoff_operations VALUES(?,?,?,?,?,?,?,?,?,?)", (project_id, request_id, fingerprint, "pending", "validated", _json(payload), "{}", None, _now(), _now()))

        def progress(phase, partial_ids=None):
            _text(phase, "handoff phase", maximum=200)
            progress_state["phase"] = phase
            if partial_ids is not None:
                if not isinstance(partial_ids, dict) or len(_json(partial_ids)) > 10000:
                    raise ValueError("Handoff partial IDs must be a bounded JSON object")
                progress_state["partial_ids"].update(partial_ids)

        def publish(project_id, protocol, digest, reviewer, reason):
            self._validate_handoff_receipt(project_id, payload.get("receipt"))
            completed = callback(progress)
            self._validate_handoff_receipt(project_id, completed)
            if completed["bindings"] != payload["receipt"]["bindings"]:
                # Comparison IDs may be added to the outer receipt, but source
                # bindings cannot be replaced after the pre-publication check.
                expected = payload["receipt"]["bindings"]
                if len(expected) != len(completed["bindings"]) or any(any(actual.get(key) != binding.get(key) for key in binding) for binding, actual in zip(expected, completed["bindings"])):
                    raise ValueError("Published handoff changed the selected report/source bindings")
            result = self._insert_handoff(project_id, protocol, digest, completed, reviewer, reason)
            self.store._connection.execute("UPDATE pilot_handoff_operations SET status='completed',phase='completed',partial_ids=?,error_code=NULL,updated_at=? WHERE project_id=? AND request_id=?", (_json(progress_state["partial_ids"]), _now(), project_id, request_id))
            return result
        try:
            return self._mutate(workspace_id, payload, "publish_handoff", publish, screening=True)
        except Exception as exc:
            with self.store._write_transaction():
                self.store._connection.execute("UPDATE pilot_handoff_operations SET status='failed',phase=?,partial_ids=?,error_code=?,updated_at=? WHERE project_id=? AND request_id=? AND status!='completed'", (progress_state["phase"], _json(progress_state["partial_ids"]), type(exc).__name__, _now(), project_id, request_id))
            raise

    def _validate_handoff_receipt(self, project_id, receipt):
        if not isinstance(receipt, dict) or not isinstance(receipt.get("bindings"), list) or not 1 <= len(receipt["bindings"]) <= 30:
            raise ValueError("Handoff requires 1–30 explicit source bindings; the library has no 30-record limit")
        documents = {d["id"]: d for d in self._sources(project_id)}; selected = set()
        alignment = {row["record_id"]:row for row in self._protocol_alignment(project_id)["records"]}
        for binding in receipt["bindings"]:
            if not isinstance(binding, dict):
                raise ValueError("Handoff source binding must be an object")
            document = documents.get(binding.get("document_id"))
            if document is None or not document["active"]:
                raise PilotConflict("Handoff source is unknown or superseded")
            if document.get("source_kind") not in {"abstract", "full_text"}:
                raise ValueError("Handoff requires explicitly typed source coverage and permission metadata")
            if any(binding.get(key) != document.get(key) for key in ("record_id", "source_sha256", "blocks_sha256", "source_kind")):
                raise ValueError("Handoff report/source identity, kind or hashes differ")
            review = alignment[document["record_id"]]
            if review["needs_review"]:
                raise PilotConflict("Selected report has screening decisions from another or unbound protocol; re-review under the current protocol before handoff")
            if review["title_abstract"]["state"] != "include":
                raise ValueError("Selected reports require current title/abstract inclusion; handoff does not set eligibility")
            if review["full_text"]["state"] in {"exclude", "conflict"}:
                raise ValueError("Excluded or conflicting full-text decisions cannot be handed off")
            if (document["source_kind"] == "abstract" or review["full_text"]["state"] != "include") and receipt.get("acknowledge_provisional") is not True:
                raise ValueError("Abstract-only or pending/uncertain full-text coverage requires explicit provisional acknowledgment; it is not formal review inclusion")
            if document["record_id"] in selected:
                raise ValueError("Handoff must select one exact source per report")
            selected.add(document["record_id"])
            self.store.get_document_bytes(project_id, document["id"]); self.store.get_source_blocks(project_id, document["id"])

    def _protocol_alignment(self, project_id):
        protocol_id = self._protocols(project_id)[-1]["id"]
        bindings = {row["event_id"]:row["protocol_id"] for row in self.store._connection.execute("SELECT event_id,protocol_id FROM pilot_event_bindings WHERE project_id=? AND event_kind='screening'", (project_id,))}
        events = self.store._screening_rows(project_id)
        rows = []
        for record in self.store.list_records(project_id):
            own = [event for event in events if event["record_id"] == record["id"]]
            row = {"record_id":record["id"]}
            for stage, state_key in (("title_abstract","title_abstract_state"), ("full_text","full_text_state")):
                active = self.store._active_decisions(own, stage)
                row[stage] = {"state":record[state_key], "active_event_ids":[event["id"] for event in active], "bound_protocol_ids":[bindings.get(event["id"]) for event in active], "needs_review":any(bindings.get(event["id"]) != protocol_id for event in active)}
            row["needs_review"] = row["title_abstract"]["needs_review"] or row["full_text"]["needs_review"]
            rows.append(row)
        return {"current_protocol_id":protocol_id, "records":rows, "record_ids_needing_review":[row["record_id"] for row in rows if row["needs_review"]],
                "current_included_report_ids":[row["record_id"] for row in rows if not row["needs_review"] and row["title_abstract"]["state"] == "include" and row["full_text"]["state"] == "include"],
                "warning":"Counts remain original ledger arithmetic. Old or unbound protocol decisions require explicit re-review; comparison handoff is not formal inclusion."}

    def _insert_handoff(self, project_id, protocol, digest, receipt, reviewer, reason):
        result = {"id": str(uuid4()), "project_id": project_id, "protocol_id": protocol["id"], "ledger_digest_before": digest, "receipt": receipt, "reviewer": reviewer, "reason": reason, "created_at": _now()}
        stored = {**receipt, "declared_reviewer": reviewer, "declared_reason": reason}
        self.store._connection.execute("INSERT INTO pilot_handoffs VALUES(?,?,?,?,?,?)", (result["id"], project_id, protocol["id"], digest, _json(stored), result["created_at"]))
        return result

    def view(self, workspace_id, *, offset=0, limit=50):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("Pilot library page requires offset>=0 and limit between 1 and 200")
        with self.store._snapshot():
            binding = self._binding(workspace_id); project_id = binding["project_id"]
            state = self._state(project_id); protocols = self._protocols(project_id)
            intakes = []
            for row in self.store._connection.execute("SELECT * FROM pilot_intakes WHERE project_id=? ORDER BY rowid", (project_id,)).fetchall():
                assets = [{"name": asset["name"], "sha256": asset["sha256"], "size_bytes": len(asset["content"])} for asset in self.store._connection.execute("SELECT * FROM pilot_intake_assets WHERE intake_id=? ORDER BY name", (row["id"],))]
                intakes.append({**dict(row), "assets": assets})
            handoffs = [{**dict(row), "receipt": json.loads(row["receipt"])} for row in self.store._connection.execute("SELECT * FROM pilot_handoffs WHERE project_id=? ORDER BY rowid", (project_id,))]
            return {"project": self.store.get_project(project_id), "purpose": binding["purpose"], "current_protocol": protocols[-1], "protocols": protocols,
                    "ledger_digest": _hash(state), "records": state["records"][offset:offset+limit], "total_records": len(state["records"]), "offset": offset, "limit": limit,
                    "counts": self.store.counts(project_id), "search_runs": state["search_runs"], "occurrences": state["occurrences"], "decisions": state["decisions"], "retrieval_events": state["retrieval_events"],
                    "sources": self._sources(project_id), "intakes": intakes, "handoffs": handoffs,
                    "protocol_alignment": self._protocol_alignment(project_id),
                    "request_audit": [{**dict(row), "result":json.loads(row["result"])} for row in self.store._connection.execute("SELECT project_id,request_id,action,fingerprint,result,created_at FROM pilot_requests WHERE project_id=? ORDER BY rowid", (project_id,))],
                    "handoff_operations": [{**dict(row), "input": json.loads(row["input"]), "partial_ids": json.loads(row["partial_ids"])} for row in self.store._connection.execute("SELECT * FROM pilot_handoff_operations WHERE project_id=? ORDER BY rowid", (project_id,))],
                    "event_bindings": [dict(row) for row in self.store._connection.execute("SELECT * FROM pilot_event_bindings WHERE project_id=? ORDER BY rowid", (project_id,))],
                    "limitations": ["Reviewer names are self-declared labels, not authenticated human identities.", "No independent or dual review is established by this software.", "Exploratory selections and comparison handoffs do not establish eligibility.", "Reports are not assumed to be independent studies.", "Title/abstract reopening after retrieval and retrieved-status downgrade are unsupported."]}

    def export(self, workspace_id, destination):
        with self.store._snapshot():
            view = self.view(workspace_id); project_id = view["project"]["id"]
            assets = {}
            for intake in view["intakes"]:
                for row in self.store._connection.execute("SELECT * FROM pilot_intake_assets WHERE intake_id=?", (intake["id"],)):
                    if not isinstance(row["content"], bytes) or _hash(row["content"]) != row["sha256"]:
                        raise ValueError("Retained pilot intake bytes/hash are corrupt")
                    path = PurePosixPath(row["name"])
                    if path.is_absolute() or ".." in path.parts or "\\" in row["name"]:
                        raise ValueError("Retained pilot intake asset path is unsafe")
                    assets[f"pilot/intakes/{intake['id']}/{path}"] = row["content"]
            result = self.store.export_project(project_id, destination)
            # The normal export schema is untouched. Opt-in metadata and original
            # bytes are additional files alongside it, never replacement records.
            destination = Path(destination)
            pilot = {k:view[k] for k in ("project", "purpose", "current_protocol", "protocols", "ledger_digest", "intakes", "event_bindings", "handoffs", "handoff_operations", "protocol_alignment", "request_audit", "sources", "limitations")}
            assets["pilot/pilot.json"] = (_json(pilot)+"\n").encode()
            with tempfile.TemporaryDirectory(prefix=".pilot-export-", dir=destination) as staged:
                staged = Path(staged)
                for name, content in assets.items():
                    path = staged/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
                for name in assets:
                    path = destination/name; path.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(staged/name, path)
            return {**result, "files": result["files"]+list(assets), "pilot": pilot}
