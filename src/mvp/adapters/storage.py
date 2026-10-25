"""Private local SQLite snapshots and transactional request idempotency.

An OS lock serializes operations within one workspace across processes. Provider
calls happen outside SQLite transactions so separate workspaces remain usable.
"""

from contextlib import contextmanager
import hashlib
import hmac
from src.platform_support import locks as fcntl
import os
from src.platform_support import open_private, restrict_path, private_directory as platform_private_directory
from pathlib import Path
import secrets
import sqlite3

from ..contracts import WorkspaceHandle, WorkspaceSnapshot, canonical, new_id
from ..ports import MvpError


class SQLiteWorkspaceStorage:
    def __init__(self, path, max_workspace_bytes=64 * 1024 * 1024):
        self._path = Path(path)
        self._max_workspace_bytes = max_workspace_bytes
        platform_private_directory(self._path.parent)
        self._locks = platform_private_directory(self._path.parent / (self._path.name + ".locks"))
        descriptor = open_private(self._path, os.O_CREAT | os.O_RDWR)
        os.close(descriptor)
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
        restrict_path(self._path, 0o600)

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
        from ..workspace_versions import decode_workspace
        return decode_workspace(row["snapshot"])

    def create(self, question):
        handle = WorkspaceHandle(workspace_id=new_id(), token=secrets.token_urlsafe(32))
        return self.create_reserved(handle, question)

    def create_reserved(self, handle, question):
        """Materialize an internal durable reservation, or reopen that exact ID."""
        state = WorkspaceSnapshot(id=handle.workspace_id, question=question)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                prior = connection.execute("SELECT id FROM mvp_workspaces WHERE id=?", (handle.workspace_id,)).fetchone()
                if prior:
                    self._authorized(connection, handle)
                else:
                    connection.execute("INSERT INTO mvp_workspaces VALUES (?, ?, ?)",
                                       (handle.workspace_id, self._token_hash(handle), state.model_dump_json()))
                connection.execute("COMMIT")
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
        return handle

    def read(self, handle):
        with self._connection() as connection:
            return self._authorized(connection, handle)

    def read_serialized(self, handle, callback):
        """Coordinate additive state with research writes without new history rows."""
        self.read(handle)
        with self._workspace_lock(handle), self._connection() as connection:
            return callback(self._authorized(connection, handle))

    @contextmanager
    def _workspace_lock(self, handle):
        # Hash the untrusted ID; no external identifier becomes a filesystem path.
        name = hashlib.sha256(handle.workspace_id.encode("utf-8")).hexdigest()
        descriptor = open_private(self._locks / name, os.O_CREAT | os.O_RDWR | 0, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def transact(self, handle, operation, request_id, fingerprint, callback):
        return self._transact(handle, operation, request_id, fingerprint, callback)

    def transact_guarded(self, handle, operation, request_id, fingerprint, callback, commit_guard):
        """Publish auxiliary job state and research state in the same DB commit.

        The callback must do no provider work. The guard receives the actual
        SQLite write transaction, the result and whether this is an exact replay.
        Cancellation either precedes this transaction or observes its result.
        """
        return self._transact(handle, operation, request_id, fingerprint, callback, commit_guard)

    @staticmethod
    def _auxiliary_bytes(connection, workspace_id):
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        total = 0
        if {'preparation_jobs', 'collection_preparation_jobs'} & tables:
            from .preparation_storage import preparation_auxiliary_bytes
            total += preparation_auxiliary_bytes(connection, workspace_id)
        if 'mvp_ingestion_imports' in tables:
            from .collection_storage import ingestion_auxiliary_bytes
            total += ingestion_auxiliary_bytes(connection, workspace_id)
        if 'mvp_workspace_compatibility_backups' in tables:
            from ..workspace_versions import compatibility_backup_bytes
            total += compatibility_backup_bytes(connection, workspace_id)
        from .search_plan_storage import search_plan_auxiliary_bytes
        total += search_plan_auxiliary_bytes(connection, workspace_id)
        return total

    def _transact(self, handle, operation, request_id, fingerprint, callback, commit_guard=None):
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
                    result = json.loads(prior["result"])
                    if commit_guard is not None:
                        connection.execute("BEGIN IMMEDIATE")
                        self._authorized(connection, handle)
                        commit_guard(connection, result, True)
                        connection.execute("COMMIT")
                    return result
                updated, result = callback(state)
                if updated.id != handle.workspace_id:
                    raise MvpError("workspace_conflict", "Workspace update did not match the active workspace.")
                encoded = canonical(result)
                encoded_snapshot = updated.model_dump_json()
                connection.execute("BEGIN IMMEDIATE")
                self._authorized(connection, handle)
                if commit_guard is not None:
                    commit_guard(connection, result, False)
                from ..workspace_versions import retain_original_workspace
                retain_original_workspace(connection, handle.workspace_id, updated)
                prior_bytes = connection.execute(
                    "SELECT COALESCE(SUM(length(CAST(result AS BLOB))), 0) FROM mvp_requests WHERE workspace_id=?",
                    (handle.workspace_id,)).fetchone()[0]
                total_bytes = (len(encoded_snapshot.encode("utf-8")) + len(encoded.encode("utf-8"))
                               + prior_bytes + self._auxiliary_bytes(connection, handle.workspace_id))
                if total_bytes > self._max_workspace_bytes:
                    raise MvpError("workspace_limit", "This local workspace reached its storage limit. Export it, then clear the session or start a new workspace.")
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
        return self._clear(handle, missing_ok=False)

    def clear_if_present(self, handle):
        """Finish an internally authorized pending deletion after interruption."""
        return self._clear(handle, missing_ok=True)

    def _clear(self, handle, *, missing_ok):
        with self._connection() as connection:
            exists = connection.execute("SELECT id FROM mvp_workspaces WHERE id=?", (handle.workspace_id,)).fetchone()
            if exists is None and missing_ok:
                return
            self._authorized(connection, handle)
        with self._workspace_lock(handle), self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                exists = connection.execute("SELECT id FROM mvp_workspaces WHERE id=?", (handle.workspace_id,)).fetchone()
                if exists is None and missing_ok:
                    connection.execute("COMMIT")
                    return
                self._authorized(connection, handle)
                connection.execute("DELETE FROM mvp_workspaces WHERE id=?", (handle.workspace_id,))
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
