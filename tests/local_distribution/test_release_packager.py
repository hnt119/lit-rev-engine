"""Release provenance checks with disposable synthetic Git repositories only."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

import pytest

from scripts import build_local_preview as package


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('release_archive_audit', Path(__file__).with_name('audit_source_archive.py'))
archive_audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive_audit)


def git(root, *args):
    env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    return subprocess.check_output(['git', '-c', 'commit.gpgsign=false', *args], cwd=root, env=env,
                                   stderr=subprocess.STDOUT)


def commit(root):
    git(root, 'add', '--all')  # This helper's root is a new disposable synthetic repository.
    git(root, 'commit', '-m', 'Synthetic release fixture')
    return git(root, 'rev-parse', 'HEAD').decode().strip()


@pytest.fixture
def source(tmp_path):
    root = tmp_path / 'synthetic-source'; root.mkdir()
    git(root, 'init', '-q')
    git(root, 'config', 'user.name', 'Synthetic software test')
    git(root, 'config', 'user.email', 'software-qa@example.invalid')
    for name in package.EXACT | package.TASK_FILES | set(package.DOCUMENTS.values()):
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('Synthetic local preview setup fixture.\n')
    path = root / 'src/mvp/example.py'; path.parent.mkdir(parents=True)
    path.write_text('VALUE = "synthetic"\n')
    commit(root)
    return root


def release(result):
    with zipfile.ZipFile(result['archive']) as bundle:
        return json.loads(bundle.read(package.NAME + '/RELEASE.json'))


def test_clean_release_records_exact_commit_and_is_reproducible(source, tmp_path):
    head = git(source, 'rev-parse', 'HEAD').decode().strip()
    first = package.build(source, tmp_path/'first', expected_source_commit=head)
    second = package.build(source, tmp_path/'second', expected_source_commit=head)
    assert Path(first['archive']).read_bytes() == Path(second['archive']).read_bytes()
    metadata = release(first)
    assert metadata['source_commit'] == head
    assert metadata['source_state'] == 'clean committed checkout'
    assert metadata['code_license_present'] is False and metadata['root_notice_files'] == []
    assert metadata['runtimes_bundled'] is False and metadata['models_bundled'] is False
    with zipfile.ZipFile(first['archive']) as bundle:
        assert bundle.read(package.NAME+'/DISTRIBUTION_TERMS.md') == (source/package.DOCUMENTS['DISTRIBUTION_TERMS.md']).read_bytes()


@pytest.mark.parametrize('state', ['tracked', 'staged', 'untracked'])
def test_release_refuses_dirty_or_uncommitted_source(source, tmp_path, state):
    if state == 'untracked':
        (source/'src/mvp/unreviewed.json').write_text('{"private":"synthetic"}')
    else:
        (source/'src/mvp/example.py').write_text('VALUE = "edited"\n')
        if state == 'staged':git(source, 'add', 'src/mvp/example.py')
    with pytest.raises(ValueError, match='clean committed checkout'):
        package.build(source, tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_wrong_source_commit_and_missing_committed_required_files_are_refused(source, tmp_path):
    with pytest.raises(ValueError, match='explicitly selected source commit'):
        package.build(source, tmp_path/'out', expected_source_commit='0'*40)
    git(source, 'rm', 'docs/local_preview_distribution_terms.md')
    git(source, 'commit', '-m', 'Synthetic omitted terms fixture')
    with pytest.raises(ValueError, match='Missing required release inputs'):
        package.build(source, tmp_path/'missing')


def test_existing_license_and_notice_are_copied_without_selecting_new_terms(source, tmp_path):
    license_bytes = b'Existing synthetic terms; software fixture only.\n'
    (source/'LICENSE.txt').write_bytes(license_bytes)
    (source/'NOTICE').write_text('Existing synthetic attribution.\n')
    commit(source)
    result = package.build(source, tmp_path/'out')
    assert release(result)['root_notice_files'] == ['LICENSE.txt', 'NOTICE']
    assert release(result)['code_license_present'] is True
    with zipfile.ZipFile(result['archive']) as bundle:
        assert bundle.read(package.NAME+'/LICENSE.txt') == license_bytes
        assert bundle.read(package.NAME+'/NOTICE') == (source/'NOTICE').read_bytes()


def test_explicit_review_archive_never_claims_clean_commit_and_excludes_untracked_canary(source, tmp_path):
    (source/'src/mvp/example.py').write_text('VALUE = "review only"\n')
    (source/'src/mvp/untracked-private.json').write_text('{"private":"synthetic"}')
    result = package.build(source, tmp_path/'review', allow_working_tree=True)
    assert release(result)['source_state'] == 'review working tree; not for publication'
    with zipfile.ZipFile(result['archive']) as bundle:
        assert not any('untracked-private' in name for name in bundle.namelist())


@pytest.mark.parametrize('name', ['src/mvp/cookies.json', 'src/mvp/backup.bak', 'src/mvp/model.gguf',
                                  'src/mvp/.env.secret', 'src/mvp/debug.log'])
def test_committed_private_runtime_or_model_paths_are_refused(source, tmp_path, name):
    path = source/name; path.write_text('synthetic fixture')
    commit(source)
    with pytest.raises(ValueError, match='Private/runtime release path'):
        package.build(source, tmp_path/'out')


def test_committed_secret_shape_and_symlink_are_refused(source, tmp_path):
    (source/'src/mvp/example.py').write_text('TOKEN = "'+'ghp_'+'x'*32+'"\n')
    commit(source)
    with pytest.raises(ValueError, match='possible credential'):
        package.build(source, tmp_path/'secret')
    (source/'src/mvp/example.py').unlink()
    (source/'src/mvp/example.py').symlink_to(source/'requirements-hosted.txt')
    commit(source)
    with pytest.raises(ValueError, match='non-symlink'):
        package.build(source, tmp_path/'symlink')


@pytest.mark.parametrize('platform', ['mac', 'linux', 'windows'])
def test_personal_home_paths_are_refused(source, tmp_path, platform):
    # Construct a synthetic path rather than storing a real user's path in tests.
    path = {'mac': '/'+ 'Users' + '/synthetic-qa/private',
            'linux': '/'+ 'home' + '/synthetic-qa/private',
            'windows': 'C:'+ '\\Users' + '\\synthetic-qa\\private'}[platform]
    (source/'src/mvp/example.py').write_text('PATH = '+repr(path)+'\n')
    commit(source)
    with pytest.raises(ValueError, match='personal|private machine path'):
        package.build(source, tmp_path/'out')


def test_independent_audit_checks_all_files_against_selected_commit(source, tmp_path):
    fixture = 'examples/mvp/offline_microbiome_30_v1'
    shutil.copytree(ROOT/fixture, source/fixture)
    head = commit(source)
    result = package.build(source, tmp_path/'out', expected_source_commit=head)
    audited = archive_audit.audit(result['archive'], head, source)
    assert audited['all_payload_files_match_commit'] is True
    assert audited['distribution_terms_included'] is True
    assert audited['public_papers'] == 30 and audited['public_fixture_files'] == 67
    # Even fully recomputed archive checksums cannot forge committed provenance.
    with zipfile.ZipFile(result['archive']) as bundle:
        entries = bundle.infolist()
        payload = {entry.filename: bundle.read(entry) for entry in entries}
    prefix = package.NAME + '/'
    payload[prefix+'src/mvp/example.py'] = b'VALUE = "not the committed source"\n'
    metadata = json.loads(payload[prefix+'RELEASE.json'])
    metadata['source_snapshot_sha256'] = package.digest(package.json_bytes({
        name[len(prefix):]: package.digest(raw) for name, raw in payload.items()
        if name not in {prefix+'RELEASE.json', prefix+'MANIFEST.json'}}))
    payload[prefix+'RELEASE.json'] = package.json_bytes(metadata)
    manifest = json.loads(payload[prefix+'MANIFEST.json'])
    manifest['files'] = {name[len(prefix):]: {'bytes': len(raw), 'sha256': package.digest(raw)}
                         for name, raw in payload.items() if name != prefix+'MANIFEST.json'}
    payload[prefix+'MANIFEST.json'] = package.json_bytes(manifest)
    forged = tmp_path/'forged'/Path(result['archive']).name; forged.parent.mkdir()
    with zipfile.ZipFile(forged, 'w') as bundle:
        for entry in entries:bundle.writestr(entry, payload[entry.filename])
    forged.with_suffix('.manifest.json').write_bytes(payload[prefix+'MANIFEST.json'])
    forged.with_suffix('.SHA256SUMS').write_text(package.digest(forged.read_bytes())+'  '+forged.name+'\n'+
        package.digest(payload[prefix+'MANIFEST.json'])+'  '+forged.with_suffix('.manifest.json').name+'\n')
    with pytest.raises(AssertionError, match='differs from committed source'):
        archive_audit.audit(forged, head, source)
    with pytest.raises(AssertionError, match='HEAD mismatch'):
        archive_audit.audit(result['archive'], '0'*40, source)
    (source/'src/mvp/example.py').write_text('VALUE = "not committed"\n')
    with pytest.raises(AssertionError, match='clean source checkout'):
        archive_audit.audit(result['archive'], head, source)
