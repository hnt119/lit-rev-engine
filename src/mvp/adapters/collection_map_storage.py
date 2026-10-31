"""Collection map tables on the existing map/cache platform, with shared quotas."""
from ..collection_contracts import CollectionInputRef
from ..collection_mapping import (
    CollectionMapInput, CollectionPaperMap, CollectionMapCounts, CollectionMapView,
    CollectionMapJobView, CollectionMapListing, CollectionMapSubmission, CollectionMapSummary,
    collection_counts, validate_collection_artifact,
)
from ..contracts import StructuredError, digest, new_id, now
from ..mapping import EmbeddingProfile
from ..ports import MvpError
from .map_storage import MapStore, unavailable


class CollectionMapStore(MapStore):
    job_table = 'collection_map_jobs'
    artifact_table = 'collection_maps'
    vector_table = 'collection_map_vectors'
    artifact_model = CollectionPaperMap
    counts_model = CollectionMapCounts
    view_model = CollectionMapView

    def __init__(self, path, **limits):
        super().__init__(path, **limits)
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS collection_map_jobs(
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL,
                    collection_id TEXT NOT NULL, collection_snapshot_sha256 TEXT NOT NULL,
                    map_id TEXT NOT NULL, logical_key TEXT NOT NULL,
                    input_json TEXT NOT NULL, input_sha256 TEXT NOT NULL, profile_json TEXT NOT NULL,
                    status TEXT NOT NULL, attempt INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 2, lease_owner TEXT, lease_expires TEXT,
                    progress_completed INTEGER NOT NULL DEFAULT 0, progress_total INTEGER NOT NULL,
                    interrupted_count INTEGER NOT NULL DEFAULT 0, error_json TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS collection_map_requests(
                    workspace_id TEXT NOT NULL, request_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, job_id TEXT NOT NULL, PRIMARY KEY(workspace_id,request_id));
                CREATE TABLE IF NOT EXISTS collection_maps(
                    map_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, collection_id TEXT NOT NULL,
                    artifact_json TEXT NOT NULL, artifact_sha256 TEXT NOT NULL, counts_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS collection_map_vectors(
                    map_id TEXT NOT NULL, paper_id TEXT NOT NULL, cache_key TEXT NOT NULL,
                    PRIMARY KEY(map_id,paper_id));
                CREATE INDEX IF NOT EXISTS collection_map_queue ON collection_map_jobs(status,created_at,id);
            ''')
        with self.transaction() as db:
            if 'adapter_config_json' not in {row['name'] for row in db.execute('PRAGMA table_info(collection_map_jobs)')}:
                db.execute('ALTER TABLE collection_map_jobs ADD COLUMN adapter_config_json TEXT')

    @staticmethod
    def input(job):
        captured = CollectionMapInput.model_validate_json(job['input_json'])
        if (digest(captured.model_dump(mode='json')) != job['input_sha256']
                or captured.collection_ref.collection_id != job['collection_id']
                or captured.collection_ref.collection_snapshot_sha256 != job['collection_snapshot_sha256']
                or len(captured.members) != job['progress_total']):
            raise MvpError('map_integrity', 'The immutable collection map input failed its identity/digest check.')
        return captured

    @staticmethod
    def view(row):
        fields = {key: row[key] for key in CollectionMapJobView.model_fields if key not in {'schema_version', 'collection_ref', 'error'}}
        return CollectionMapJobView(**fields,
            collection_ref=CollectionInputRef(collection_id=row['collection_id'], collection_snapshot_sha256=row['collection_snapshot_sha256']),
            error=StructuredError.model_validate_json(row['error_json']) if row['error_json'] else None)

    def submit(self, workspace_id, captured, profile, request, adapter_config_json=None):
        timestamp = now()
        checksum = digest(captured.model_dump(mode='json'))
        logical = digest({'collection_input': checksum, 'profile': digest(profile.model_dump(mode='json'))})
        fingerprint = digest(request.model_dump(mode='json'))
        with self.transaction() as db:
            self._alive(db, workspace_id)
            prior = db.execute('SELECT * FROM collection_map_requests WHERE workspace_id=? AND request_id=?', (workspace_id, request.request_id)).fetchone()
            if prior:
                if prior['fingerprint'] != fingerprint:
                    raise MvpError('idempotency_conflict', 'This map request key was used with different input.')
                job = db.execute('SELECT * FROM collection_map_jobs WHERE id=? AND workspace_id=?', (prior['job_id'], workspace_id)).fetchone()
                if job is None:
                    raise unavailable('job')
                return CollectionMapSubmission(job=self.view(job), map_id=job['map_id'] if job['status'] == 'succeeded' else None, reused=True)
            reusable = None if request.rebuild else db.execute("SELECT * FROM collection_map_jobs WHERE workspace_id=? AND logical_key=? AND status IN ('queued','running','cancel_requested','succeeded') ORDER BY created_at DESC,id DESC LIMIT 1", (workspace_id, logical)).fetchone()
            if reusable:
                identifier, reused = reusable['id'], True
            else:
                identifier, reused = new_id(), False
                db.execute('''INSERT INTO collection_map_jobs(id,workspace_id,collection_id,collection_snapshot_sha256,
                    map_id,logical_key,input_json,input_sha256,profile_json,adapter_config_json,status,progress_total,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,'queued',?,?,?)''',
                    (identifier, workspace_id, captured.collection_ref.collection_id, captured.collection_ref.collection_snapshot_sha256,
                     new_id(), logical, captured.model_dump_json(), checksum, profile.model_dump_json(), adapter_config_json, len(captured.members), timestamp, timestamp))
            db.execute('INSERT INTO collection_map_requests VALUES(?,?,?,?)', (workspace_id, request.request_id, fingerprint, identifier))
            self._limits(db, workspace_id)
            job = db.execute('SELECT * FROM collection_map_jobs WHERE id=?', (identifier,)).fetchone()
            return CollectionMapSubmission(job=self.view(job), map_id=job['map_id'] if job['status'] == 'succeeded' else None, reused=reused)

    def listing(self, workspace_id, collection_id=None):
        with self.connection() as db:
            self._alive(db, workspace_id)
            suffix = ' AND collection_id=?' if collection_id is not None else ''
            args = (workspace_id, collection_id) if collection_id is not None else (workspace_id,)
            jobs = [self.view(row) for row in db.execute('SELECT * FROM collection_map_jobs WHERE workspace_id=?' + suffix + ' ORDER BY created_at DESC,id DESC', args)]
            maps = []
            for row in db.execute('SELECT artifact_json,artifact_sha256 FROM collection_maps WHERE workspace_id=?' + suffix + ' ORDER BY rowid DESC', args):
                artifact = self._artifact(row)
                maps.append(CollectionMapSummary(map_id=artifact.map_id, collection_ref=artifact.collection_ref,
                    created_at=artifact.created_at, status=artifact.status, projection_method=artifact.projection_method,
                    embedded_count=len(artifact.coordinates_by_paper_id), excluded_count=len(artifact.excluded_papers_with_reasons),
                    paper_count=len(artifact.ordered_paper_ids)))
            return CollectionMapListing(maps=maps, jobs=jobs)

    def _embedded(self, workspace_id, map_id):
        with self.connection() as db:
            self._alive(db, workspace_id)
            artifact_row = db.execute('SELECT * FROM collection_maps WHERE workspace_id=? AND map_id=?', (workspace_id, map_id)).fetchone()
            if artifact_row is None:
                raise unavailable()
            artifact = self._artifact(artifact_row)
            result = {}
            for row in db.execute('''SELECT v.paper_id,e.payload_json,e.payload_sha256 FROM collection_map_vectors v
                    JOIN paper_embeddings e ON e.workspace_id=? AND e.cache_key=v.cache_key WHERE v.map_id=?''', (workspace_id, map_id)):
                result[row['paper_id']] = self._embedding(row, artifact.embedding_profile).model_copy(update={'paper_id': row['paper_id']})
            return [result[identifier] for identifier in artifact.ordered_paper_ids if identifier in result]

    def captured_for_map(self, workspace_id, map_id):
        with self.connection() as db:
            self._alive(db, workspace_id)
            row = db.execute("SELECT * FROM collection_map_jobs WHERE workspace_id=? AND map_id=? AND status='succeeded'", (workspace_id, map_id)).fetchone()
            if row is None:
                raise unavailable()
            return self.input(row)

    def map(self, workspace_id, map_id):
        result = super().map(workspace_id, map_id)
        captured = self.captured_for_map(workspace_id, map_id)
        validate_collection_artifact(result.artifact, captured, result.artifact.embedding_profile, self._embedded(workspace_id, map_id))
        if result.counts != collection_counts(captured, result.artifact):
            raise MvpError('map_integrity', 'Collection map counts do not reconcile to the immutable input.')
        return result

    def publish(self, job, artifact, embedded, map_counts):
        artifact = CollectionPaperMap.model_validate(artifact.model_dump(mode='json'))
        captured = self.input(job)
        profile = EmbeddingProfile.model_validate_json(job['profile_json'])
        validate_collection_artifact(artifact, captured, profile, embedded)
        if (map_counts != collection_counts(captured, artifact) or artifact.workspace_id != job['workspace_id']
                or artifact.map_id != job['map_id']):
            raise MvpError('map_integrity', 'Collection map publication differs from its immutable job input.')
        with self.transaction() as db:
            self._alive(db, job['workspace_id'])
            row = self._active_publication(db, job)
            if row['input_sha256'] != job['input_sha256'] or row['profile_json'] != job['profile_json']:
                raise MvpError('map_integrity', 'Collection map input changed during the active attempt.')
            self._write_vectors(db, job, artifact, embedded, profile)
            db.execute('INSERT INTO collection_maps VALUES(?,?,?,?,?,?)', (artifact.map_id, artifact.workspace_id,
                artifact.collection_ref.collection_id, artifact.model_dump_json(), digest(artifact.model_dump(mode='json')), map_counts.model_dump_json()))
            self._limits(db, artifact.workspace_id)
            db.execute("UPDATE collection_map_jobs SET status='succeeded',progress_completed=progress_total,error_json=NULL,lease_owner=NULL,lease_expires=NULL,updated_at=? WHERE id=?", (now(), job['id']))
