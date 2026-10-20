"""Private local SQLite snapshots and transactional request idempotency.

An OS lock serializes operations within one workspace across processes. Provider
calls happen outside SQLite transactions so separate workspaces remain usable.
"""

from contextlib import contextmanager
import hashlib
import hmac
import fcntl
import os
from pathlib import Path
import secrets
import sqlite3

from ..contracts import WorkspaceHandle, WorkspaceSnapshot, canonical, new_id
from ..ports import MvpError


class SQLiteWorkspaceStorage:
    def __init__(self, path, max_workspace_bytes=64 * 1024 * 1024):
        self._path = Path(path)
        self._max_workspace_bytes = max_workspace_bytes
        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._locks = self._path.parent / (self._path.name + ".locks")
        self._locks.mkdir(mode=0o700, exist_ok=True)
        self._locks.chmod(0o700)
        if self._path.is_symlink():
            raise ValueError("Workspace database must not be a symlink")
        self._path.touch(mode=0o600, exist_ok=True)
        self._path.chmod(0o600)
        with self._connection() as connection:
            connection.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS mvp_workspaces (
                    id TEXT PRIMARY KEY,
                    token_hash TEXT NOT NULL,
                    snapshot TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mvp_requests (
                    workspace_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    result TEXT NOT NULL,
                    PRIMARY KEY(workspace_id, operation, request_id),
                    FOREIGN KEY(workspace_id) REFERENCES mvp_workspaces(id) ON DELETE CASCADE
                );
            """)
        self._path.chmod(0o600)

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self._path, timeout=300, isolation_level=None)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _token_hash(handle):
        return hashlib.sha256((handle.workspace_id + ":" + handle.token).encode("utf-8")).hexdigest()

    def _authorized(self, connection, handle):
        row = connection.execute("SELECT token_hash, snapshot FROM mvp_workspaces WHERE id=?", (handle.workspace_id,)).fetchone()
        if row is None or not hmac.compare_digest(row["token_hash"], self._token_hash(handle)):
            raise MvpError("workspace_access_denied", "Workspace is unavailable or its handle is invalid.")
        return WorkspaceSnapshot.model_validate_json(row["snapshot"])

    def create(self, question):
        handle = WorkspaceHandle(workspace_id=new_id(), token=secrets.token_urlsafe(32))
        state = WorkspaceSnapshot(id=handle.workspace_id, question=question)
        with self._connection() as connection:
            connection.execute("INSERT INTO mvp_workspaces VALUES (?, ?, ?)",
                               (handle.workspace_id, self._token_hash(handle), state.model_dump_json()))
        return handle

    def read(self, handle):
        with self._connection() as connection:
            return self._authorized(connection, handle)

    @contextmanager
    def _workspace_lock(self, handle):
        # Hash the untrusted ID; no external identifier becomes a filesystem path.
        name = hashlib.sha256(handle.workspace_id.encode("utf-8")).hexdigest()
        descriptor = os.open(self._locks / name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def transact(self, handle, operation, request_id, fingerprint, callback):
        import json

        # Validate capability before creating a lock file for an arbitrary ID.
        self.read(handle)
        with self._workspace_lock(handle), self._connection() as connection:
            try:
                state = self._authorized(connection, handle)
                prior = connection.execute(
                    "SELECT fingerprint, result FROM mvp_requests WHERE workspace_id=? AND operation=? AND request_id=?",
                    (handle.workspace_id, operation, request_id)).fetchone()
                if prior is not None:
                    if not hmac.compare_digest(prior["fingerprint"], fingerprint):
                        raise MvpError("idempotency_conflict", "This request key was already used with different input. Submit a new request.")
                    return json.loads(prior["result"])
                updated, result = callback(state)
                if updated.id != handle.workspace_id:
                    raise MvpError("workspace_conflict", "Workspace update did not match the active workspace.")
                encoded = canonical(result)
                encoded_snapshot = updated.model_dump_json()
                prior_bytes = connection.execute(
                    "SELECT COALESCE(SUM(length(CAST(result AS BLOB))), 0) FROM mvp_requests WHERE workspace_id=?",
                    (handle.workspace_id,)).fetchone()[0]
                if len(encoded_snapshot.encode("utf-8")) + len(encoded.encode("utf-8")) + prior_bytes > self._max_workspace_bytes:
                    raise MvpError("workspace_limit", "This local workspace reached its storage limit. Export it, then clear the session or start a new workspace.")
                connection.execute("BEGIN IMMEDIATE")
                self._authorized(connection, handle)
                connection.execute("UPDATE mvp_workspaces SET snapshot=? WHERE id=?", (encoded_snapshot, handle.workspace_id))
                connection.execute("INSERT INTO mvp_requests VALUES (?, ?, ?, ?, ?)",
                                   (handle.workspace_id, operation, request_id, fingerprint, encoded))
                connection.execute("COMMIT")
                return result
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    def clear(self, handle):
        self.read(handle)
        with self._workspace_lock(handle), self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._authorized(connection, handle)
                connection.execute("DELETE FROM mvp_workspaces WHERE id=?", (handle.workspace_id,))
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
