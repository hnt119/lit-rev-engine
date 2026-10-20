"""Local web sessions and durable UI drafts, separate from research snapshots.

This OS-private credential registry intentionally contains raw workspace handles.
Protect its backups like credentials. Session cookie values are stored only as
SHA-256 hashes. There is no workspace UUID recovery or public enumeration API.
Existing v0.1 workspace tables are neither rewritten nor migrated here.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import fcntl
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
from typing import Callable

from .contracts import WorkspaceHandle, canonical, digest, new_id, now
from .ports import MvpError

SESSION_SECONDS = 30 * 24 * 60 * 60


def _unavailable():
    return MvpError("workspace_access_denied", "Workspace is unavailable to this local browser session.")


def private_directory(path: Path) -> Path:
    path = path.expanduser().absolute()
    # The application owns only this dedicated directory; do not chmod parents.
    if any(item.is_symlink() for item in [path, *path.parents]):
        raise ValueError("Private web storage paths must not contain symlinks")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


class WorkspaceUIStore:
    def __init__(self, path: str | Path, *, max_draft_bytes=65536,
                 max_workspace_draft_bytes=2 * 1024 * 1024, max_drafts=100):
        self.path = Path(path).expanduser().absolute()
        private_directory(self.path.parent)
        for suffix in ("", "-wal", "-shm", "-journal"):
            if Path(str(self.path) + suffix).is_symlink():
                raise ValueError("Private web credential database must not be a symlink")
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.fchmod(descriptor, 0o600)
        os.close(descriptor)
        self._delete_locks = private_directory(self.path.parent / (self.path.name + ".delete-locks"))
        self.max_draft_bytes, self.max_workspace_draft_bytes = max_draft_bytes, max_workspace_draft_bytes
        self.max_drafts = max_drafts
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS web_schema(version INTEGER PRIMARY KEY);
                INSERT OR IGNORE INTO web_schema VALUES(1);
                CREATE TABLE IF NOT EXISTS web_sessions(
                    token_hash TEXT PRIMARY KEY, csrf TEXT NOT NULL,
                    created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS web_workspaces(
                    workspace_id TEXT PRIMARY KEY, session_hash TEXT NOT NULL,
                    capability TEXT NOT NULL, mode TEXT NOT NULL,
                    create_request_id TEXT NOT NULL, create_fingerprint TEXT NOT NULL,
                    UNIQUE(session_hash, create_request_id));
                CREATE TABLE IF NOT EXISTS web_create_requests(
                    session_hash TEXT NOT NULL, request_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, workspace_id TEXT NOT NULL,
                    PRIMARY KEY(session_hash, request_id));
                INSERT OR IGNORE INTO web_create_requests
                    SELECT session_hash, create_request_id, create_fingerprint, workspace_id
                    FROM web_workspaces;
                INSERT OR IGNORE INTO web_schema VALUES(2);
                CREATE TABLE IF NOT EXISTS web_drafts(
                    workspace_id TEXT NOT NULL, scope TEXT NOT NULL,
                    version INTEGER NOT NULL, data TEXT NOT NULL,
                    expected_assessment_head TEXT, updated_at TEXT NOT NULL,
                    PRIMARY KEY(workspace_id, scope));
                CREATE TABLE IF NOT EXISTS web_tombstones(
                    workspace_id TEXT PRIMARY KEY, deleted_at TEXT NOT NULL);
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(web_workspaces)")}
            if "ready" not in columns:
                db.execute("ALTER TABLE web_workspaces ADD COLUMN ready INTEGER NOT NULL DEFAULT 1")
            db.execute("INSERT OR IGNORE INTO web_schema VALUES(3)")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    @staticmethod
    def token_hash(token):
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            return None
        return hashlib.sha256(token.encode("ascii")).hexdigest()

    def resolve_session(self, token):
        token_hash = self.token_hash(token)
        if token_hash is None:
            return None
        with self.connection() as db:
            row = db.execute("SELECT * FROM web_sessions WHERE token_hash=? AND expires_at>?", (token_hash, now())).fetchone()
            return dict(row) if row else None

    def session(self, token=None):
        session = self.resolve_session(token)
        if session:
            return token, session
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        session = {"token_hash": self.token_hash(token), "csrf": csrf, "created_at": now(),
                   "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=SESSION_SECONDS)).isoformat()}
        with self.connection() as db:
            db.execute("INSERT INTO web_sessions VALUES(?,?,?,?)", tuple(session[key] for key in ("token_hash", "csrf", "created_at", "expires_at")))
        return token, session

    @staticmethod
    def check_csrf(session, supplied):
        return bool(session and supplied and hmac.compare_digest(session["csrf"], supplied))

    def workspace(self, session_hash, workspace_id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM web_workspaces WHERE session_hash=? AND workspace_id=? AND ready=1 AND workspace_id NOT IN (SELECT workspace_id FROM web_tombstones)", (session_hash, workspace_id)).fetchone()
            if row is None:
                raise _unavailable()
            return row["mode"], WorkspaceHandle(workspace_id=row["workspace_id"], token=row["capability"])

    def workspace_ids(self, session_hash):
        with self.connection() as db:
            return [row[0] for row in db.execute("SELECT workspace_id FROM web_workspaces WHERE session_hash=? AND ready=1 AND workspace_id NOT IN (SELECT workspace_id FROM web_tombstones) ORDER BY rowid DESC", (session_hash,))]

    def create_workspace(self, session_hash, request_id, payload, create: Callable[[WorkspaceHandle], WorkspaceHandle]):
        """Reserve credentials durably before an idempotent domain create.

        Pending reservations are private and not reopenable until publication.
        A crash at any point reuses this exact handle on same-request retry.
        """
        fingerprint = digest(payload)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                request_row = db.execute("SELECT * FROM web_create_requests WHERE session_hash=? AND request_id=?", (session_hash, request_id)).fetchone()
                if request_row:
                    if not hmac.compare_digest(request_row["fingerprint"], fingerprint):
                        raise MvpError("idempotency_conflict", "This workspace request key was used with different input.")
                    row = db.execute("SELECT * FROM web_workspaces WHERE workspace_id=? AND session_hash=?", (request_row["workspace_id"], session_hash)).fetchone()
                    if row is None or db.execute("SELECT 1 FROM web_tombstones WHERE workspace_id=?", (request_row["workspace_id"],)).fetchone():
                        raise _unavailable()
                    handle = WorkspaceHandle(workspace_id=row["workspace_id"], token=row["capability"])
                    ready = bool(row["ready"])
                else:
                    handle = WorkspaceHandle(workspace_id=new_id(), token=secrets.token_urlsafe(32))
                    ready = False
                    db.execute("INSERT INTO web_workspaces(workspace_id,session_hash,capability,mode,create_request_id,create_fingerprint,ready) VALUES(?,?,?,?,?,?,0)", (handle.workspace_id, session_hash, handle.token, payload["mode"], request_id, fingerprint))
                    db.execute("INSERT INTO web_create_requests VALUES(?,?,?,?)", (session_hash, request_id, fingerprint, handle.workspace_id))
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
        if not ready:
            # Creation and deletion share one OS lock, including after restart.
            # A delayed create cannot recreate a domain row deleted by a retry.
            with self._delete_lock(handle.workspace_id):
                with self.connection() as db:
                    row = db.execute("SELECT ready FROM web_workspaces WHERE workspace_id=? AND session_hash=?", (handle.workspace_id, session_hash)).fetchone()
                    if row is None or db.execute("SELECT 1 FROM web_tombstones WHERE workspace_id=?", (handle.workspace_id,)).fetchone():
                        raise _unavailable()
                    ready = bool(row["ready"])
                if not ready:
                    created = create(handle)
                    if created != handle:
                        raise MvpError("workspace_conflict", "Reserved workspace identity did not match its creation result.")
                    with self.connection() as db:
                        db.execute("BEGIN IMMEDIATE")
                        try:
                            if db.execute("SELECT 1 FROM web_tombstones WHERE workspace_id=?", (handle.workspace_id,)).fetchone():
                                raise _unavailable()
                            changed = db.execute("UPDATE web_workspaces SET ready=1 WHERE workspace_id=? AND session_hash=?", (handle.workspace_id, session_hash)).rowcount
                            if changed != 1:
                                raise _unavailable()
                            db.execute("COMMIT")
                        except BaseException:
                            if db.in_transaction:
                                db.execute("ROLLBACK")
                            raise
        return handle

    def draft(self, workspace_id, scope):
        with self.connection() as db:
            row = db.execute("SELECT * FROM web_drafts WHERE workspace_id=? AND scope=?", (workspace_id, scope)).fetchone()
        if row is None:
            return {"scope": scope, "version": 0, "data": {}, "expected_assessment_head": None, "updated_at": None}
        return {"scope": scope, "version": row["version"], "data": json.loads(row["data"]),
                "expected_assessment_head": row["expected_assessment_head"], "updated_at": row["updated_at"]}

    def put_draft(self, workspace_id, scope, *, version, data, expected_assessment_head=None):
        try:
            encoded = canonical(data)
        except (TypeError, ValueError, RecursionError):
            raise MvpError("invalid_draft", "Draft must contain bounded finite JSON values.") from None
        size = len(encoded.encode("utf-8"))
        if size > self.max_draft_bytes:
            raise MvpError("draft_limit", "This draft exceeds the 64 KiB local draft limit.")
        timestamp = now()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                if db.execute("SELECT 1 FROM web_tombstones WHERE workspace_id=?", (workspace_id,)).fetchone():
                    raise _unavailable()
                prior = db.execute("SELECT version FROM web_drafts WHERE workspace_id=? AND scope=?", (workspace_id, scope)).fetchone()
                if version != (prior[0] if prior else 0):
                    raise MvpError("stale_draft", "A newer saved draft exists. Your local edits were not overwritten; reload for comparison.")
                other = db.execute("SELECT COUNT(*), COALESCE(SUM(length(CAST(data AS BLOB))),0) FROM web_drafts WHERE workspace_id=? AND scope!=?", (workspace_id, scope)).fetchone()
                if other[0] + 1 > self.max_drafts or other[1] + size > self.max_workspace_draft_bytes:
                    raise MvpError("draft_limit", "This workspace reached its local draft storage limit.")
                db.execute("INSERT INTO web_drafts VALUES(?,?,?,?,?,?) ON CONFLICT(workspace_id,scope) DO UPDATE SET version=excluded.version,data=excluded.data,expected_assessment_head=excluded.expected_assessment_head,updated_at=excluded.updated_at", (workspace_id, scope, version + 1, encoded, expected_assessment_head, timestamp))
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
        return {"scope": scope, "version": version + 1, "data": data, "expected_assessment_head": expected_assessment_head, "updated_at": timestamp}

    @contextmanager
    def _delete_lock(self, workspace_id):
        name = hashlib.sha256(workspace_id.encode("utf-8")).hexdigest()
        descriptor = os.open(self._delete_locks / name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    @contextmanager
    def lifecycle_guard(self, workspace_id):
        """Internal short create/delete/publication guard; never hold for compute."""
        with self._delete_lock(workspace_id):
            yield

    def delete_workspace(self, session_hash, workspace_id, clear, after_clear=None):
        # A process interruption leaves the credential binding and tombstone.
        # The authorized browser can safely retry; UUID guessing cannot recover it.
        with self.connection() as db:
            if db.execute("SELECT 1 FROM web_create_requests WHERE workspace_id=? AND session_hash=?", (workspace_id, session_hash)).fetchone() is None:
                raise _unavailable()
        with self._delete_lock(workspace_id):
            with self.connection() as db:
                row = db.execute("SELECT * FROM web_workspaces WHERE workspace_id=? AND session_hash=? AND ready=1", (workspace_id, session_hash)).fetchone()
                tombstoned = db.execute("SELECT 1 FROM web_tombstones WHERE workspace_id=?", (workspace_id,)).fetchone() is not None
                if row is None:
                    owned_request = db.execute("SELECT 1 FROM web_create_requests WHERE workspace_id=? AND session_hash=?", (workspace_id, session_hash)).fetchone()
                    if tombstoned and owned_request:
                        return
                    raise _unavailable()
                handle = WorkspaceHandle(workspace_id=workspace_id, token=row["capability"])
                mode = row["mode"]
                db.execute("INSERT OR IGNORE INTO web_tombstones VALUES(?,?)", (workspace_id, now()))
            try:
                clear(mode, handle)
            except Exception:
                # A caught first-attempt failure is known not to have completed.
                # Interrupted deletions keep their guard until an explicit retry.
                if not tombstoned:
                    with self.connection() as db:
                        db.execute("DELETE FROM web_tombstones WHERE workspace_id=?", (workspace_id,))
                raise
            if after_clear is not None:
                after_clear(workspace_id)
            with self.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                try:
                    db.execute("DELETE FROM web_drafts WHERE workspace_id=?", (workspace_id,))
                    db.execute("DELETE FROM web_workspaces WHERE workspace_id=? AND session_hash=?", (workspace_id, session_hash))
                    db.execute("COMMIT")
                except BaseException:
                    if db.in_transaction:
                        db.execute("ROLLBACK")
                    raise

    def is_deleted(self, workspace_id):
        with self.connection() as db:
            return db.execute("SELECT 1 FROM web_tombstones WHERE workspace_id=?", (workspace_id,)).fetchone() is not None

    def get_bound_handle_for_worker(self, workspace_id):
        """Internal worker access only; never expose this capability in HTTP."""
        with self.connection() as db:
            row = db.execute("SELECT session_hash FROM web_workspaces WHERE workspace_id=?", (workspace_id,)).fetchone()
        if row is None:
            raise _unavailable()
        return self.workspace(row[0], workspace_id)
