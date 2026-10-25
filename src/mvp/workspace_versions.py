"""Explicit readers for mixed legacy and collection research histories.

New collection operations opt into a v2 workspace payload. Existing Paper,
SearchPreview, preparation/run and citation serializers remain unchanged.
"""
from typing import Literal
import hashlib
import json
import zlib

from .collection_contracts import CollectionInputRef
from .collection_preparation_contracts import CollectionPreparationResult
from .contracts import EvidenceRun, PreparationResult, WorkspaceSnapshot
from .ports import MvpError


class CollectionEvidenceRun(EvidenceRun):
    schema_version: Literal['mvp.collection-lexical-evidence.v2'] = 'mvp.collection-lexical-evidence.v2'
    search_id: None = None
    collection_ref: CollectionInputRef
    member_snapshot_sha256: str


class WorkspaceSnapshotV2(WorkspaceSnapshot):
    schema_version: Literal['mvp.workspace.v2'] = 'mvp.workspace.v2'
    preparations: list[PreparationResult | CollectionPreparationResult]
    runs: list[EvidenceRun | CollectionEvidenceRun]


class EvidenceRunReader:
    @staticmethod
    def model_validate(value):
        model = CollectionEvidenceRun if value.get('schema_version') == 'mvp.collection-lexical-evidence.v2' else EvidenceRun
        return model.model_validate(value)


def decode_workspace(payload):
    try:
        version = json.loads(payload).get('schema_version', 'mvp.workspace.v1')
        model = {'mvp.workspace.v1': WorkspaceSnapshot, 'mvp.workspace.v2': WorkspaceSnapshotV2}.get(version)
        if model is None:
            raise ValueError('unsupported version')
        return model.model_validate_json(payload)
    except Exception:
        raise MvpError('workspace_integrity', 'The retained workspace version is unsupported or invalid. Original data was not modified.') from None


def collection_workspace(state):
    if isinstance(state, WorkspaceSnapshotV2):
        return state
    payload = state.model_dump(mode='json')
    payload['schema_version'] = 'mvp.workspace.v2'
    return WorkspaceSnapshotV2.model_validate(payload)


def retain_original_workspace(db, workspace_id, updated):
    """Called inside the same research/job commit, never on ordinary reads."""
    row = db.execute('SELECT snapshot FROM mvp_workspaces WHERE id=?', (workspace_id,)).fetchone()
    original = row['snapshot']
    if json.loads(original).get('schema_version', 'mvp.workspace.v1') != 'mvp.workspace.v1' or updated.schema_version != 'mvp.workspace.v2':
        return
    db.execute('''CREATE TABLE IF NOT EXISTS mvp_workspace_compatibility_backups(
        workspace_id TEXT PRIMARY KEY, from_schema TEXT NOT NULL, to_schema TEXT NOT NULL,
        original_payload BLOB NOT NULL, original_sha256 TEXT NOT NULL,
        FOREIGN KEY(workspace_id) REFERENCES mvp_workspaces(id) ON DELETE CASCADE)''')
    raw = original.encode('utf-8')
    db.execute('INSERT INTO mvp_workspace_compatibility_backups VALUES(?,?,?,?,?)',
        (workspace_id, 'mvp.workspace.v1', 'mvp.workspace.v2', zlib.compress(raw, 6), hashlib.sha256(raw).hexdigest()))


def compatibility_backup_bytes(db, workspace_id):
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mvp_workspace_compatibility_backups'").fetchone() is None:
        return 0
    return db.execute('SELECT COALESCE(SUM(length(original_payload)+length(original_sha256)+length(from_schema)+length(to_schema)),0) FROM mvp_workspace_compatibility_backups WHERE workspace_id=?', (workspace_id,)).fetchone()[0]


def original_workspace_bytes(storage, handle):
    """Read an authorized compatibility copy for an explicit local backup check."""
    storage.read(handle)
    with storage._connection() as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mvp_workspace_compatibility_backups'").fetchone() is None:
            return None
        row = db.execute('SELECT * FROM mvp_workspace_compatibility_backups WHERE workspace_id=?', (handle.workspace_id,)).fetchone()
        if row is None:
            return None
        try:
            decoder = zlib.decompressobj()
            raw = decoder.decompress(row['original_payload'], storage._max_workspace_bytes + 1)
            if len(raw) > storage._max_workspace_bytes or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                raise ValueError('invalid backup size')
            if hashlib.sha256(raw).hexdigest() != row['original_sha256']:
                raise ValueError('backup checksum')
            WorkspaceSnapshot.model_validate_json(raw)
            return raw
        except Exception:
            raise MvpError('workspace_integrity', 'The retained original workspace copy failed its integrity check.') from None
