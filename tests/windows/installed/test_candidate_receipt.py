"""Receipt regressions: stale or invalid metadata cannot select a baseline EXE."""
import hashlib
import importlib.util
import json
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('receipt', Path(__file__).with_name('candidate_receipt.py'))
receipt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(receipt)


@pytest.fixture
def candidate(tmp_path):
    work = tmp_path / 'issue18-candidate'
    work.mkdir()
    binary = work / (receipt.CANDIDATE_ID + '-Setup.exe')
    binary.write_bytes(b'synthetic test candidate')
    patch = tmp_path / 'repair.patch'
    patch.write_bytes(b'synthetic repair')
    env = {'RUNNER_TEMP': str(tmp_path), 'GITHUB_SHA': 'a' * 40,
           'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1'}
    value = {'schema': 'litrev.issue18.candidate.v2', 'candidate_id': receipt.CANDIDATE_ID,
        'application_source': receipt.SOURCE, 'application_version': '0.3.0-windows-experimental-beta.2',
        'original_installer_sha256': receipt.ORIGINAL_SHA,
        'installation_manifest_sha256': receipt.MANIFEST_SHA, 'compiler_zip_sha256': receipt.COMPILER_SHA,
        'repair_infrastructure_sha': env['GITHUB_SHA'], 'run_id': '123', 'run_attempt': '1',
        'preprocessor': 'PASS', 'build': 'PASS', 'payload_verification': 'PASS', 'native_root_regression': 'PASS',
        'repair_patch_sha256': receipt.digest(patch), 'candidate_path': str(binary),
        'installer_bytes': binary.stat().st_size, 'installer_sha256': receipt.digest(binary)}
    file = work / 'candidate.json'
    def write(): file.write_text(json.dumps(value))
    write()
    def load(): return receipt.load_candidate(file, environment=env, patch_path=patch)
    return value, file, binary, patch, write, load


def test_valid_run_bound_candidate(candidate):
    value, _, _, _, _, load = candidate
    assert load() == value


@pytest.mark.parametrize('field,new', [('run_id', 'old'), ('run_attempt', '2'),
    ('repair_infrastructure_sha', 'b' * 40), ('application_source', 'b' * 40),
    ('preprocessor', 'NOT_RUN'), ('native_root_regression', 'FAIL'), ('installer_sha256', receipt.ORIGINAL_SHA)])
def test_stale_or_wrong_identity_rejected(candidate, field, new):
    value, _, _, _, write, load = candidate
    value[field] = new
    write()
    with pytest.raises(ValueError): load()


def test_missing_receipt_has_no_fallback(candidate):
    _, file, _, _, _, load = candidate
    file.unlink()
    with pytest.raises(ValueError): load()


def test_modified_binary_rejected(candidate):
    _, _, binary, _, _, load = candidate
    binary.write_bytes(b'changed malicious bytes!')
    with pytest.raises(ValueError): load()


def test_modified_patch_rejected(candidate):
    _, _, _, patch, _, load = candidate
    patch.write_bytes(b'different patch')
    with pytest.raises(ValueError): load()


def test_duplicate_receipt_keys_rejected(candidate):
    _, file, _, _, _, load = candidate
    file.write_text('{"run_id":"123","run_id":"123"}')
    with pytest.raises(ValueError): load()
