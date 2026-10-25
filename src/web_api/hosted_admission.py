"""Bounded persisted beta admission; separate from workspace authorization.

Invitation codes and opaque cookie values never enter this database. Rotating
the configured digest invalidates outstanding admission grants on next access.
No IP/forwarded header is trusted for identity or rate accounting.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import os
from src.platform_support import open_private, restrict_fd, is_link
from pathlib import Path
import re
import secrets
import sqlite3
import time

from src.mvp.workspace_ui import private_directory

ADMISSION_COOKIE = "__Host-litrev_admission"
HOSTED_SESSION_COOKIE = "__Host-litrev_session"
ADMISSION_SECONDS = 8 * 60 * 60
LOGIN_WINDOW_SECONDS = 15 * 60
MAX_LOGIN_ATTEMPTS = 40
MAX_ACTIVE_GRANTS = 256
REQUEST_WINDOW_SECONDS = 60 * 60
MAX_REQUESTS = 2000
MAX_EXPENSIVE_JOBS = 60


class AdmissionDenied(Exception):
    def __init__(self, code="admission_required", status=401):
        self.code, self.status = code, status


class HostedAdmissionStore:
    def __init__(self, path: Path, invite_sha256: str, *, clock=time.time):
        self.path, self.invite_sha256, self.clock = Path(path), invite_sha256, clock
        private_directory(self.path.parent)
        for suffix in ("", "-wal", "-shm", "-journal"):
            if is_link(Path(str(self.path) + suffix)):
                raise ValueError("Admission storage must not contain symlinks.")
        descriptor = open_private(self.path, os.O_CREAT | os.O_RDWR | 0, 0o600)
        restrict_fd(descriptor, 0o600)
        os.close(descriptor)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS admission_grants(
                    token_hash TEXT PRIMARY KEY, invite_hash TEXT NOT NULL,
                    expires_at INTEGER NOT NULL, request_window INTEGER NOT NULL,
                    requests INTEGER NOT NULL, jobs INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS admission_attempts(
                    id INTEGER PRIMARY KEY CHECK(id=1), window INTEGER NOT NULL,
                    attempts INTEGER NOT NULL);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
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

    def login_attempt(self):
        timestamp = int(self.clock())
        window = timestamp // LOGIN_WINDOW_SECONDS
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO admission_attempts VALUES(1,?,1) ON CONFLICT(id) DO UPDATE SET window=excluded.window, attempts=CASE WHEN admission_attempts.window=excluded.window THEN admission_attempts.attempts+1 ELSE 1 END", (window,))
            attempts = db.execute("SELECT attempts FROM admission_attempts WHERE id=1").fetchone()[0]
            db.execute("COMMIT")
        if attempts > MAX_LOGIN_ATTEMPTS:
            raise AdmissionDenied("admission_rate_limit", 429)

    def issue(self, code):
        valid_code = isinstance(code, str) and 32 <= len(code) <= 256
        # Always compare a same-size digest; never echo the supplied credential.
        candidate = hashlib.sha256(code.encode("utf-8") if valid_code else b"").hexdigest()
        if not hmac.compare_digest(candidate, self.invite_sha256) or not valid_code:
            raise AdmissionDenied("admission_denied", 401)
        timestamp = int(self.clock())
        token = secrets.token_urlsafe(32)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM admission_grants WHERE expires_at<=? OR invite_hash!=?", (timestamp, self.invite_sha256))
            if db.execute("SELECT COUNT(*) FROM admission_grants").fetchone()[0] >= MAX_ACTIVE_GRANTS:
                raise AdmissionDenied("admission_capacity", 429)
            db.execute("INSERT INTO admission_grants VALUES(?,?,?,?,0,0)",
                (self.token_hash(token), self.invite_sha256, timestamp + ADMISSION_SECONDS,
                 timestamp // REQUEST_WINDOW_SECONDS))
            db.execute("COMMIT")
        return token, self.resolve(token)

    def resolve(self, token):
        hashed = self.token_hash(token)
        if hashed is None:
            return None
        with self.connection() as db:
            row = db.execute("SELECT * FROM admission_grants WHERE token_hash=? AND invite_hash=? AND expires_at>?",
                             (hashed, self.invite_sha256, int(self.clock()))).fetchone()
            return dict(row) if row else None

    def consume(self, token, *, expensive=False):
        hashed = self.token_hash(token)
        if hashed is None:
            raise AdmissionDenied()
        timestamp = int(self.clock())
        window = timestamp // REQUEST_WINDOW_SECONDS
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM admission_grants WHERE token_hash=? AND invite_hash=? AND expires_at>?",
                             (hashed, self.invite_sha256, timestamp)).fetchone()
            if row is None:
                raise AdmissionDenied()
            requests = row["requests"] if row["request_window"] == window else 0
            jobs = row["jobs"] if row["request_window"] == window else 0
            if requests >= MAX_REQUESTS or (expensive and jobs >= MAX_EXPENSIVE_JOBS):
                raise AdmissionDenied("admission_usage_limit", 429)
            db.execute("UPDATE admission_grants SET request_window=?, requests=?, jobs=? WHERE token_hash=?",
                       (window, requests + 1, jobs + int(expensive), hashed))
            db.execute("COMMIT")

    def revoke(self, token):
        with self.connection() as db:
            db.execute("DELETE FROM admission_grants WHERE token_hash=?", (self.token_hash(token),))

    @staticmethod
    def expires_at(grant):
        return datetime.fromtimestamp(grant["expires_at"], timezone.utc).isoformat()


def expensive_request(method, path):
    """Bound provider/CPU submissions while retaining 180 manual cell saves."""
    if method != "POST":
        return False
    return bool(re.search(r"/(?:searches|source-preparations|preparation-jobs|collection-preparation-jobs|evidence-runs|maps|collection-maps|candidates|proposal-runs|diagnose|execute|propose|resolve)$", path)
                or re.search(r"/imports/(?:csv|ris|identifiers)$", path))
