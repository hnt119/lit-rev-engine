"""Private additive map artifacts, embedding cache, durable jobs and leases."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from src.platform_support import open_private, restrict_fd, is_link
from pathlib import Path
import sqlite3

from ..contracts import canonical, digest, new_id, now, SearchPreview, StructuredError
from ..mapping import (EmbeddedPaper, EmbeddingProfile, MapCounts, MapJobView, MapListing,
                       MapSubmission, MapSummary, MapView, PaperMap, counts, validate_artifact, validate_vector)
from ..ports import MvpError
from ..workspace_ui import private_directory


def unavailable(kind="map"):
    return MvpError("unknown_" + kind, "The requested map resource does not belong to this workspace.")


def later(seconds):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


class MapStore:
    job_table = 'paper_map_jobs'
    artifact_table = 'paper_maps'
    vector_table = 'paper_map_vectors'
    artifact_model = PaperMap
    counts_model = MapCounts
    view_model = MapView

    def __init__(self, path, *, max_workspace_bytes=32 * 1024 * 1024, max_jobs=200, max_maps=100, max_embeddings=5000, max_requests=1000):
        self.path = Path(path)
        private_directory(self.path.parent)
        if any(is_link(Path(str(self.path) + suffix)) for suffix in ("", "-wal", "-shm", "-journal")):
            raise ValueError("Map storage must not be a symlink")
        descriptor = open_private(self.path, os.O_CREAT | os.O_RDWR | 0, 0o600)
        restrict_fd(descriptor, 0o600)
        os.close(descriptor)
        self.max_workspace_bytes, self.max_jobs = max_workspace_bytes, max_jobs
        self.max_maps, self.max_embeddings, self.max_requests = max_maps, max_embeddings, max_requests
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS map_schema(version INTEGER PRIMARY KEY);
                INSERT OR IGNORE INTO map_schema VALUES(1);
                CREATE TABLE IF NOT EXISTS paper_map_jobs(
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, search_id TEXT NOT NULL,
                    map_id TEXT NOT NULL, logical_key TEXT NOT NULL,
                    search_json TEXT NOT NULL, profile_json TEXT NOT NULL,
                    status TEXT NOT NULL, attempt INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 2, lease_owner TEXT,
                    lease_expires TEXT, progress_completed INTEGER NOT NULL DEFAULT 0,
                    progress_total INTEGER NOT NULL, interrupted_count INTEGER NOT NULL DEFAULT 0,
                    error_json TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS paper_map_requests(
                    workspace_id TEXT NOT NULL, request_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, job_id TEXT NOT NULL,
                    PRIMARY KEY(workspace_id,request_id));
                CREATE TABLE IF NOT EXISTS paper_maps(
                    map_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, search_id TEXT NOT NULL,
                    artifact_json TEXT NOT NULL, artifact_sha256 TEXT NOT NULL,
                    counts_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS paper_embeddings(
                    workspace_id TEXT NOT NULL, cache_key TEXT NOT NULL,
                    payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
                    PRIMARY KEY(workspace_id,cache_key));
                CREATE TABLE IF NOT EXISTS paper_map_vectors(
                    map_id TEXT NOT NULL, paper_id TEXT NOT NULL, cache_key TEXT NOT NULL,
                    PRIMARY KEY(map_id,paper_id));
                CREATE TABLE IF NOT EXISTS paper_map_deleted(workspace_id TEXT PRIMARY KEY);
            ''')
        with self.transaction() as db:
            if 'adapter_config_json' not in {row['name'] for row in db.execute('PRAGMA table_info(paper_map_jobs)')}:
                db.execute('ALTER TABLE paper_map_jobs ADD COLUMN adapter_config_json TEXT')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    def _alive(self, db, workspace_id):
        if db.execute("SELECT 1 FROM paper_map_deleted WHERE workspace_id=?", (workspace_id,)).fetchone():
            raise unavailable("workspace")

    def _limits(self, db, workspace_id):
        # Count all serialized auxiliary payload, including requests reusing one
        # logical map and metadata/link rows. Reserve bounded future lease/error
        # metadata so a quota failure itself can always be recorded safely.
        tables = {
            "paper_map_jobs": "id workspace_id search_id map_id logical_key search_json profile_json adapter_config_json status attempt max_attempts lease_owner lease_expires progress_completed progress_total interrupted_count error_json created_at updated_at",
            "paper_maps": "map_id workspace_id search_id artifact_json artifact_sha256 counts_json",
            "paper_embeddings": "workspace_id cache_key payload_json payload_sha256",
            "paper_map_requests": "workspace_id request_id fingerprint job_id",
            "collection_map_jobs": "id workspace_id collection_id collection_snapshot_sha256 map_id logical_key input_json input_sha256 profile_json adapter_config_json status attempt max_attempts lease_owner lease_expires progress_completed progress_total interrupted_count error_json created_at updated_at",
            "collection_maps": "map_id workspace_id collection_id artifact_json artifact_sha256 counts_json",
            "collection_map_requests": "workspace_id request_id fingerprint job_id",
        }
        existing = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        sizes, numbers = {}, {}
        for table, names in tables.items():
            if table not in existing:
                numbers[table], sizes[table] = 0, 0
                continue
            columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
            expression = "+".join("COALESCE(length(CAST(" + name + " AS BLOB)),0)" for name in names.split() if name in columns)
            row = db.execute("SELECT COUNT(*),COALESCE(SUM(" + expression + "),0) FROM " + table + " WHERE workspace_id=?", (workspace_id,)).fetchone()
            numbers[table], sizes[table] = row
        links = 0
        for vectors, artifacts in (('paper_map_vectors', 'paper_maps'), ('collection_map_vectors', 'collection_maps')):
            if vectors in existing and artifacts in existing:
                links += db.execute(f"SELECT COALESCE(SUM(length(CAST(v.map_id AS BLOB))+length(CAST(v.paper_id AS BLOB))+length(CAST(v.cache_key AS BLOB))),0) FROM {vectors} v JOIN {artifacts} m ON m.map_id=v.map_id WHERE m.workspace_id=?", (workspace_id,)).fetchone()[0]
        jobs = numbers['paper_map_jobs'] + numbers['collection_map_jobs']
        payload_bytes = sum(sizes.values()) + links + jobs * 2048
        if (jobs > self.max_jobs or numbers["paper_maps"] + numbers['collection_maps'] > self.max_maps
                or numbers["paper_embeddings"] > self.max_embeddings or numbers["paper_map_requests"] + numbers['collection_map_requests'] > self.max_requests
                or payload_bytes > self.max_workspace_bytes):
            raise MvpError("map_storage_limit", "This workspace reached its auxiliary map storage limit. Existing research and exports remain available.")

    @staticmethod
    def view(row):
        return MapJobView(**{key: row[key] for key in MapJobView.model_fields if key != "error"},
                          error=StructuredError.model_validate_json(row["error_json"]) if row["error_json"] else None)

    def submit(self, workspace_id, search, profile, request, adapter_config_json=None):
        timestamp = now()
        logical = digest({"search": digest(search.model_dump(mode="json")), "profile": digest(profile.model_dump(mode="json"))})
        fingerprint = digest(request.model_dump(mode="json"))
        with self.transaction() as db:
            self._alive(db, workspace_id)
            prior = db.execute("SELECT * FROM paper_map_requests WHERE workspace_id=? AND request_id=?", (workspace_id, request.request_id)).fetchone()
            if prior:
                if prior["fingerprint"] != fingerprint:
                    raise MvpError("idempotency_conflict", "This map request key was used with different input.")
                job = db.execute("SELECT * FROM paper_map_jobs WHERE id=? AND workspace_id=?", (prior["job_id"], workspace_id)).fetchone()
                if job is None:
                    raise unavailable("job")
                return MapSubmission(job=self.view(job), map_id=job["map_id"] if job["status"] == "succeeded" else None, reused=True)
            reusable = None if request.rebuild else db.execute("SELECT * FROM paper_map_jobs WHERE workspace_id=? AND logical_key=? AND status IN ('queued','running','cancel_requested','succeeded') ORDER BY created_at DESC,id DESC LIMIT 1", (workspace_id, logical)).fetchone()
            if reusable:
                identifier, reused = reusable["id"], True
            else:
                identifier, reused = new_id(), False
                db.execute("INSERT INTO paper_map_jobs(id,workspace_id,search_id,map_id,logical_key,search_json,profile_json,adapter_config_json,status,progress_total,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,'queued',?,?,?)",
                    (identifier, workspace_id, search.id, new_id(), logical, search.model_dump_json(), profile.model_dump_json(), adapter_config_json, len(search.papers), timestamp, timestamp))
            db.execute("INSERT INTO paper_map_requests VALUES(?,?,?,?)", (workspace_id, request.request_id, fingerprint, identifier))
            self._limits(db, workspace_id)
            job = db.execute("SELECT * FROM paper_map_jobs WHERE id=?", (identifier,)).fetchone()
            return MapSubmission(job=self.view(job), map_id=job["map_id"] if job["status"] == "succeeded" else None, reused=reused)

    def job(self, workspace_id, job_id):
        with self.connection() as db:
            self._alive(db, workspace_id)
            row = db.execute(f"SELECT * FROM {self.job_table} WHERE id=? AND workspace_id=?", (job_id, workspace_id)).fetchone()
            if row is None:
                raise unavailable("job")
            return self.view(row)

    def listing(self, workspace_id, search_id):
        with self.connection() as db:
            self._alive(db, workspace_id)
            jobs = [self.view(row) for row in db.execute("SELECT * FROM paper_map_jobs WHERE workspace_id=? AND search_id=? ORDER BY created_at DESC,id DESC", (workspace_id, search_id))]
            maps = []
            for row in db.execute("SELECT artifact_json,artifact_sha256 FROM paper_maps WHERE workspace_id=? AND search_id=? ORDER BY rowid DESC", (workspace_id, search_id)):
                artifact = self._artifact(row)
                maps.append(MapSummary(map_id=artifact.map_id, search_id=artifact.search_id, created_at=artifact.created_at,
                    status=artifact.status, projection_method=artifact.projection_method,
                    embedded_count=len(artifact.coordinates_by_paper_id), excluded_count=len(artifact.excluded_papers_with_reasons), paper_count=len(artifact.ordered_paper_ids)))
            return MapListing(maps=maps, jobs=jobs)

    @classmethod
    def _artifact(cls, row):
        artifact = cls.artifact_model.model_validate_json(row["artifact_json"])
        if (digest(artifact.model_dump(mode="json")) != row["artifact_sha256"]
                or digest(artifact.coordinates_by_paper_id) != artifact.coordinate_sha256
                or digest(artifact.embedding_profile.model_dump(mode="json")) != artifact.embedding_profile_sha256):
            raise MvpError("map_integrity", "Saved map artifact failed its integrity checks.")
        return artifact

    def map(self, workspace_id, map_id):
        with self.connection() as db:
            self._alive(db, workspace_id)
            row = db.execute(f"SELECT * FROM {self.artifact_table} WHERE map_id=? AND workspace_id=?", (map_id, workspace_id)).fetchone()
            if row is None:
                raise unavailable()
            return self.view_model(artifact=self._artifact(row), counts=self.counts_model.model_validate_json(row["counts_json"]))

    @staticmethod
    def cache_key(profile, input_sha256):
        return digest({"profile": profile.model_dump(mode="json"), "input_sha256": input_sha256})

    def _embedding(self, row, profile):
        item = EmbeddedPaper.model_validate_json(row["payload_json"])
        if digest(item.model_dump(mode="json")) != row["payload_sha256"]:
            raise MvpError("map_integrity", "Saved embedding failed its integrity check.")
        validate_vector(item.vector, profile.dimension)
        if any(weight > profile.content_window_tokens for weight in item.window_token_weights):
            raise MvpError("map_integrity", "Saved embedding window exceeds its pinned length policy.")
        return item

    def embedding(self, workspace_id, profile, representation):
        key = self.cache_key(profile, representation.input_sha256)
        with self.connection() as db:
            self._alive(db, workspace_id)
            row = db.execute("SELECT * FROM paper_embeddings WHERE workspace_id=? AND cache_key=?", (workspace_id, key)).fetchone()
            if row is None:
                return None
            item = self._embedding(row, profile)
            # Identical text can belong to different paper IDs; the cached
            # representation is reused while point identity remains search-bound.
            return item.model_copy(update={"paper_id": representation.paper_id})

    def put_embedding(self, workspace_id, profile, item):
        vector = validate_vector(item.vector, profile.dimension)
        if not item.window_token_weights or any(weight <= 0 or weight > profile.content_window_tokens for weight in item.window_token_weights) or sum(item.window_token_weights) != item.token_count:
            raise MvpError("embedding_window_manifest", "Embedding window weights do not cover the recorded input tokens.")
        item = item.model_copy(update={"vector": vector})
        key = self.cache_key(profile, item.input_sha256)
        with self.transaction() as db:
            self._alive(db, workspace_id)
            prior = db.execute("SELECT * FROM paper_embeddings WHERE workspace_id=? AND cache_key=?", (workspace_id, key)).fetchone()
            if prior:
                return self._embedding(prior, profile).model_copy(update={"paper_id": item.paper_id})
            db.execute("INSERT INTO paper_embeddings VALUES(?,?,?,?)", (workspace_id, key, item.model_dump_json(), digest(item.model_dump(mode="json"))))
            self._limits(db, workspace_id)
        return item

    def recover(self):
        """Call only after acquiring the single-worker OS lock."""
        with self.transaction() as db:
            rows = db.execute(f"SELECT * FROM {self.job_table} WHERE status IN ('running','cancel_requested')").fetchall()
            for row in rows:
                status = "cancelled" if row["status"] == "cancel_requested" else "failed" if row["attempt"] >= row["max_attempts"] else "queued"
                error = StructuredError(code="map_interrupted", message="A local worker was interrupted; its recorded attempt was recovered.", retryable=status == "queued").model_dump_json()
                db.execute(f"UPDATE {self.job_table} SET status=?,lease_owner=NULL,lease_expires=NULL,interrupted_count=interrupted_count+1,error_json=?,updated_at=? WHERE id=?", (status, error, now(), row["id"]))

    def claim(self, owner, lease_seconds=120):
        with self.transaction() as db:
            # An expired lease is never allowed to publish. Recovery is bounded.
            for row in db.execute(f"SELECT * FROM {self.job_table} WHERE status IN ('running','cancel_requested') AND lease_expires<?", (now(),)).fetchall():
                status = "cancelled" if row["status"] == "cancel_requested" else "failed" if row["attempt"] >= row["max_attempts"] else "queued"
                error = StructuredError(code="map_interrupted", message="A local worker lease expired; the attempt was recovered with a bounded retry policy.", retryable=status == "queued").model_dump_json()
                db.execute(f"UPDATE {self.job_table} SET status=?,lease_owner=NULL,lease_expires=NULL,interrupted_count=interrupted_count+1,error_json=?,updated_at=? WHERE id=?", (status, error, now(), row["id"]))
            row = db.execute(f"SELECT * FROM {self.job_table} WHERE status='queued' AND attempt<max_attempts AND workspace_id NOT IN (SELECT workspace_id FROM paper_map_deleted) ORDER BY created_at,id LIMIT 1").fetchone()
            if row is None:
                return None
            db.execute(f"UPDATE {self.job_table} SET status='running',attempt=attempt+1,lease_owner=?,lease_expires=?,updated_at=? WHERE id=?", (owner, later(lease_seconds), now(), row["id"]))
            return dict(db.execute(f"SELECT * FROM {self.job_table} WHERE id=?", (row["id"],)).fetchone())

    def checkpoint(self, job, *, completed=None, lease_seconds=120):
        with self.transaction() as db:
            self._alive(db, job["workspace_id"])
            row = db.execute(f"SELECT * FROM {self.job_table} WHERE id=?", (job["id"],)).fetchone()
            if row is None or row["lease_owner"] != job["lease_owner"] or row["attempt"] != job["attempt"] or row["lease_expires"] < now() or row["status"] not in {"running", "cancel_requested"}:
                raise MvpError("map_attempt_lost", "This map worker attempt no longer owns publication.")
            if row["status"] == "cancel_requested":
                raise MvpError("map_cancelled", "Map cancellation was requested.")
            db.execute(f"UPDATE {self.job_table} SET lease_expires=?,updated_at=?,progress_completed=? WHERE id=?", (later(lease_seconds), now(), completed if completed is not None else row["progress_completed"], job["id"]))

    def finish_failure(self, job, error):
        with self.transaction() as db:
            row = db.execute(f"SELECT status,lease_expires FROM {self.job_table} WHERE id=? AND lease_owner=? AND attempt=?", (job["id"], job["lease_owner"], job["attempt"])).fetchone()
            if row is None or row["lease_expires"] is None or row["lease_expires"] < now():
                return
            status = "cancelled" if error.code == "map_cancelled" or row["status"] == "cancel_requested" else "failed"
            db.execute(f"UPDATE {self.job_table} SET status=?,error_json=?,lease_owner=NULL,lease_expires=NULL,updated_at=? WHERE id=? AND lease_owner=? AND attempt=? AND status IN ('running','cancel_requested')",
                       (status, StructuredError(code=error.code[:96], message=error.message[:500], retryable=error.retryable).model_dump_json(), now(), job["id"], job["lease_owner"], job["attempt"]))

    def cancel(self, workspace_id, job_id):
        with self.transaction() as db:
            self._alive(db, workspace_id)
            row = db.execute(f"SELECT * FROM {self.job_table} WHERE id=? AND workspace_id=?", (job_id, workspace_id)).fetchone()
            if row is None:
                raise unavailable("job")
            status = "cancelled" if row["status"] == "queued" else "cancel_requested" if row["status"] == "running" else row["status"]
            db.execute(f"UPDATE {self.job_table} SET status=?,updated_at=? WHERE id=?", (status, now(), job_id))
            return self.view(db.execute(f"SELECT * FROM {self.job_table} WHERE id=?", (job_id,)).fetchone())

    def publish(self, job, artifact, embedded, map_counts):
        try:
            artifact = PaperMap.model_validate(artifact.model_dump(mode="json"))
        except (ValueError, TypeError):
            raise MvpError("map_integrity", "Map artifact fields failed publication validation.") from None
        search = SearchPreview.model_validate_json(job["search_json"])
        profile = EmbeddingProfile.model_validate_json(job["profile_json"])
        validate_artifact(artifact, search, profile, embedded)
        if map_counts != counts(search, artifact):
            raise MvpError("map_integrity", "Map publication counts do not reconcile to its saved search.")
        if (artifact.workspace_id != job["workspace_id"] or artifact.map_id != job["map_id"] or artifact.search_id != job["search_id"]
                or artifact.search_snapshot_sha256 != digest(search.model_dump(mode="json"))
                or artifact.embedding_profile != profile or artifact.coordinate_sha256 != digest(artifact.coordinates_by_paper_id)
                or set(artifact.coordinates_by_paper_id) != {item.paper_id for item in embedded}):
            raise MvpError("map_integrity", "Map publication did not match its immutable job input.")
        with self.transaction() as db:
            self._alive(db, job["workspace_id"])
            self._active_publication(db, job)
            self._write_vectors(db, job, artifact, embedded, profile)
            db.execute("INSERT INTO paper_maps VALUES(?,?,?,?,?,?)", (artifact.map_id, artifact.workspace_id, artifact.search_id, artifact.model_dump_json(), digest(artifact.model_dump(mode="json")), map_counts.model_dump_json()))
            self._limits(db, artifact.workspace_id)
            db.execute("UPDATE paper_map_jobs SET status='succeeded',progress_completed=progress_total,error_json=NULL,lease_owner=NULL,lease_expires=NULL,updated_at=? WHERE id=?", (now(), job["id"]))

    def _active_publication(self, db, job):
        row = db.execute(f'SELECT * FROM {self.job_table} WHERE id=?', (job['id'],)).fetchone()
        if (row is None or row['workspace_id'] != job['workspace_id'] or row['status'] != 'running'
                or row['lease_owner'] != job['lease_owner'] or row['attempt'] != job['attempt']
                or not row['lease_expires'] or row['lease_expires'] < now()):
            raise MvpError('map_attempt_lost', 'Only the active non-cancelled map attempt may publish.')
        return row

    def _write_vectors(self, db, job, artifact, embedded, profile):
        manifest = []
        for item in embedded:
            key = self.cache_key(profile, item.input_sha256)
            cached = db.execute('SELECT * FROM paper_embeddings WHERE workspace_id=? AND cache_key=?', (job['workspace_id'], key)).fetchone()
            if cached is None:
                raise MvpError('map_integrity', 'Map publication is missing its retained embedding.')
            retained = self._embedding(cached, profile)
            if retained.vector != item.vector or retained.input_sha256 != item.input_sha256 or retained.representation != item.representation:
                raise MvpError('map_integrity', 'Map publication vector differs from its cache binding.')
            manifest.append({'paper_id': item.paper_id, 'input_sha256': item.input_sha256, 'vector_sha256': digest(item.vector)})
            db.execute(f'INSERT INTO {self.vector_table} VALUES(?,?,?)', (artifact.map_id, item.paper_id, key))
        if digest(manifest) != artifact.embedding_set_sha256:
            raise MvpError('map_integrity', 'Map embedding set failed its publication hash check.')

    def import_artifact(self, search, artifact, embedded):
        """Atomically retain one verified bundled map, without inventing a job.

        The caller owns the existing lifecycle/research locks. These auxiliary
        rows use the same artifact, cache, vector, quota and deletion contracts
        as worker publication; no search/source/reviewer record is changed.
        """
        try:
            artifact = PaperMap.model_validate(artifact.model_dump(mode="json"))
            embedded = [EmbeddedPaper.model_validate(item.model_dump(mode="json")) for item in embedded]
            validate_artifact(artifact, search, artifact.embedding_profile, embedded)
            origin = artifact.projection_parameters["saved_example_bundle"]
            if (not isinstance(origin, dict) or not origin.get("bundle_id")
                    or not artifact.workspace_id or not artifact.map_id):
                raise ValueError()
            for item in embedded:
                if (validate_vector(item.vector, artifact.embedding_profile.dimension) != item.vector
                        or any(weight > artifact.embedding_profile.content_window_tokens for weight in item.window_token_weights)):
                    raise ValueError()
        except (ValueError, TypeError, KeyError, AttributeError):
            raise MvpError("map_integrity", "Bundled map fields failed import validation.") from None
        map_counts = counts(search, artifact)
        profile = artifact.embedding_profile
        with self.transaction() as db:
            self._alive(db, artifact.workspace_id)
            for row in db.execute("SELECT * FROM paper_maps WHERE workspace_id=? AND search_id=? ORDER BY rowid DESC", (artifact.workspace_id, search.id)):
                prior = self._artifact(row)
                prior_origin = prior.projection_parameters.get("saved_example_bundle", {})
                if not isinstance(prior_origin, dict) or prior_origin.get("bundle_id") != origin["bundle_id"]:
                    continue
                validate_artifact(prior, search, profile, embedded)
                prior_counts = MapCounts.model_validate_json(row["counts_json"])
                if (prior_origin != origin or prior.coordinate_sha256 != artifact.coordinate_sha256
                        or prior.embedding_set_sha256 != artifact.embedding_set_sha256
                        or prior_counts != map_counts):
                    raise MvpError("map_integrity", "The retained bundled map differs from its original import binding.")
                links = {entry["paper_id"]: entry for entry in db.execute(
                    "SELECT v.paper_id,v.cache_key,e.payload_json,e.payload_sha256 FROM paper_map_vectors v "
                    "JOIN paper_embeddings e ON e.workspace_id=? AND e.cache_key=v.cache_key WHERE v.map_id=?",
                    (artifact.workspace_id, prior.map_id))}
                if set(links) != {item.paper_id for item in embedded}:
                    raise MvpError("map_integrity", "The retained bundled map is missing an embedding link.")
                for item in embedded:
                    link = links[item.paper_id]
                    retained = self._embedding(link, profile)
                    if (link["cache_key"] != self.cache_key(profile, item.input_sha256)
                            or retained.input_sha256 != item.input_sha256 or retained.representation != item.representation
                            or retained.vector != item.vector or retained.window_token_weights != item.window_token_weights
                            or retained.token_count != item.token_count):
                        raise MvpError("map_integrity", "The retained bundled embedding differs from its original import binding.")
                return MapView(artifact=prior, counts=prior_counts)
            for item in embedded:
                key = self.cache_key(profile, item.input_sha256)
                cached = db.execute("SELECT * FROM paper_embeddings WHERE workspace_id=? AND cache_key=?", (artifact.workspace_id, key)).fetchone()
                if cached is not None:
                    retained = self._embedding(cached, profile)
                    if (retained.input_sha256 != item.input_sha256 or retained.representation != item.representation
                            or retained.vector != item.vector or retained.window_token_weights != item.window_token_weights
                            or retained.token_count != item.token_count):
                        raise MvpError("map_integrity", "Bundled map vectors differ from their retained input/profile cache binding.")
                else:
                    db.execute("INSERT INTO paper_embeddings VALUES(?,?,?,?)", (artifact.workspace_id, key, item.model_dump_json(), digest(item.model_dump(mode="json"))))
                db.execute("INSERT INTO paper_map_vectors VALUES(?,?,?)", (artifact.map_id, item.paper_id, key))
            db.execute("INSERT INTO paper_maps VALUES(?,?,?,?,?,?)", (artifact.map_id, artifact.workspace_id, artifact.search_id,
                artifact.model_dump_json(), digest(artifact.model_dump(mode="json")), map_counts.model_dump_json()))
            self._limits(db, artifact.workspace_id)
        return MapView(artifact=artifact, counts=map_counts)

    def vectors(self, workspace_id, map_id):
        artifact = self.map(workspace_id, map_id).artifact
        with self.connection() as db:
            result = {}
            for row in db.execute(f"SELECT v.paper_id,e.payload_json,e.payload_sha256 FROM {self.vector_table} v JOIN paper_embeddings e ON e.workspace_id=? AND e.cache_key=v.cache_key WHERE v.map_id=?", (workspace_id, map_id)):
                result[row["paper_id"]] = self._embedding(row, artifact.embedding_profile).vector
        if result.keys() != artifact.coordinates_by_paper_id.keys():
            raise MvpError("map_integrity", "Saved map vector identities did not reconcile.")
        vector_manifest = [{"paper_id": paper_id, "input_sha256": artifact.paper_input_hashes[paper_id], "vector_sha256": digest(result[paper_id])} for paper_id in artifact.ordered_paper_ids if paper_id in result]
        if digest(vector_manifest) != artifact.embedding_set_sha256:
            raise MvpError("map_integrity", "Saved map embedding set failed its integrity check.")
        return result

    def delete_workspace(self, workspace_id):
        with self.transaction() as db:
            db.execute("INSERT OR IGNORE INTO paper_map_deleted VALUES(?)", (workspace_id,))
            existing = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for vectors, artifacts in (('paper_map_vectors', 'paper_maps'), ('collection_map_vectors', 'collection_maps')):
                if vectors in existing and artifacts in existing:
                    db.execute(f'DELETE FROM {vectors} WHERE map_id IN (SELECT map_id FROM {artifacts} WHERE workspace_id=?)', (workspace_id,))
            for table in ('paper_maps', 'paper_embeddings', 'paper_map_requests', 'paper_map_jobs',
                          'collection_maps', 'collection_map_requests', 'collection_map_jobs'):
                if table in existing:
                    db.execute('DELETE FROM ' + table + ' WHERE workspace_id=?', (workspace_id,))
