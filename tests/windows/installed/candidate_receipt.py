"""Fail-closed run-bound identity checks, shared by builder and trial."""
import hashlib
import json
import os
from pathlib import Path
import re

CANDIDATE_ID = 'issue18-installer-root-rc2'
SOURCE = '664b86d4ed510c3d16982b5813b27e6bd1150129'
ORIGINAL_SHA = '75595d013fbdf4694301a00dd0e233a6b53e47c6cf5fb3713d0d0e7aa1e58359'
MANIFEST_SHA = '7c6a2627831f1082a9163e599415c1f1f239036a3713912609fd95e5a68e5e34'
COMPILER_SHA = 'ba63dffc4410ee89193e1cb5a41989991bd77c61068da17e3156d136b7b0b3d8'


def digest(file):
    with Path(file).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_candidate(receipt_path, *, environment=None, patch_path=None):
    env = os.environ if environment is None else environment
    work = Path(env['RUNNER_TEMP']).resolve() / 'issue18-candidate'
    receipt_path = Path(receipt_path)
    if receipt_path.is_symlink() or receipt_path.resolve() != work / 'candidate.json':
        raise ValueError('candidate_receipt_location')
    if not receipt_path.is_file() or receipt_path.stat().st_size > 12000:
        raise ValueError('candidate_receipt_missing_or_oversize')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('candidate_duplicate_key')
            result[key] = value
        return result
    value = json.loads(receipt_path.read_text(encoding='utf-8'), object_pairs_hook=unique)
    expected = {'schema': 'litrev.issue18.candidate.v2', 'candidate_id': CANDIDATE_ID,
        'application_source': SOURCE, 'application_version': '0.3.0-windows-experimental-beta.2',
        'original_installer_sha256': ORIGINAL_SHA, 'installation_manifest_sha256': MANIFEST_SHA,
        'compiler_zip_sha256': COMPILER_SHA, 'repair_infrastructure_sha': env['GITHUB_SHA'],
        'run_id': env['GITHUB_RUN_ID'], 'run_attempt': env['GITHUB_RUN_ATTEMPT'],
        'preprocessor': 'PASS', 'build': 'PASS', 'payload_verification': 'PASS',
        'native_root_regression': 'PASS'}
    if not isinstance(value, dict) or any(value.get(k) != v for k, v in expected.items()):
        raise ValueError('candidate_identity_mismatch')
    patch = Path(patch_path) if patch_path else Path(__file__).with_name('installer-root.patch')
    if value.get('repair_patch_sha256') != digest(patch):
        raise ValueError('candidate_patch_mismatch')
    candidate = work / (CANDIDATE_ID + '-Setup.exe')
    if value.get('candidate_path') != str(candidate) or candidate.is_symlink() or not candidate.is_file():
        raise ValueError('candidate_binary_missing')
    size, sha = value.get('installer_bytes'), value.get('installer_sha256')
    if type(size) is not int or size <= 0 or candidate.stat().st_size != size:
        raise ValueError('candidate_size_mismatch')
    if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha) or sha == ORIGINAL_SHA or digest(candidate) != sha:
        raise ValueError('candidate_checksum_mismatch')
    return value
