"""Offline synthetic release-binding checks. No research data or website writes."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from bind_release import bind, encoded, NAME, OVERLAY, sha, validate_release, VERSION


COMMIT = 'a' * 40


def artifacts(root, *, commit=COMMIT, state='clean committed checkout', bad_hash=False):
    payload = {'README.md': b'Synthetic setup-required source fixture.\n'}
    release = {'schema': 'litrev.local-preview.release.v1', 'version': VERSION,
        'source_commit': commit, 'source_state': state, 'runtimes_bundled': False,
        'models_bundled': False,
        'source_snapshot_sha256': sha(encoded({name: sha(raw) for name, raw in payload.items()}))}
    payload['RELEASE.json'] = encoded(release)
    manifest = {'schema': 'litrev.local-preview.manifest.v1', 'version': VERSION,
        'files': {name: {'bytes': len(raw), 'sha256': sha(raw)} for name, raw in payload.items()}}
    if bad_hash:
        manifest['files']['README.md']['sha256'] = '0' * 64
    payload['MANIFEST.json'] = encoded(manifest)
    archive, sidecar, checksums = [root / (NAME + suffix) for suffix in
                                  ('.zip', '.manifest.json', '.SHA256SUMS')]
    with zipfile.ZipFile(archive, 'w') as bundle:
        for name, raw in payload.items():
            entry = zipfile.ZipInfo(NAME + '/' + name)
            entry.create_system = 3; entry.external_attr = 0o100644 << 16
            bundle.writestr(entry, raw)
    sidecar.write_bytes(payload['MANIFEST.json'])
    checksums.write_text(sha(archive.read_bytes()) + '  ' + archive.name + '\n' +
                        sha(sidecar.read_bytes()) + '  ' + sidecar.name + '\n')
    return archive, sidecar, checksums


class ReleaseBindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='litrev-overlay-bind-', dir='/private/tmp')
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_clean_artifact_binds_separate_output_without_changing_source_template(self):
        files = artifacts(self.root)
        original = (OVERLAY / 'src/data/local-preview-download.json').read_bytes()
        result = bind(*files, COMMIT, self.root / 'prepared-overlay')
        self.assertEqual(result['status'], 'PREPARED_LOCAL_ONLY')
        output = self.root / 'prepared-overlay'
        metadata = json.loads((output / 'src/data/local-preview-download.json').read_bytes())
        self.assertTrue(metadata['available']); self.assertEqual(metadata['source_commit'], COMMIT)
        self.assertEqual(metadata['archive_path'], '/downloads/' + files[0].name)
        for file in files:
            self.assertEqual((output / 'public/downloads' / file.name).read_bytes(), file.read_bytes())
        self.assertEqual((OVERLAY / 'src/data/local-preview-download.json').read_bytes(), original)
        self.assertFalse(json.loads(original)['available'])

    def test_old_working_tree_and_wrong_commit_are_refused(self):
        files = artifacts(self.root, state='review working tree; historical fixture')
        with self.assertRaisesRegex(ValueError, 'clean-commit'):
            validate_release(*files, COMMIT)
        files = artifacts(self.root)
        with self.assertRaisesRegex(ValueError, 'clean-commit'):
            validate_release(*files, 'b' * 40)

    def test_manifest_and_checksum_mismatches_are_refused(self):
        files = artifacts(self.root, bad_hash=True)
        with self.assertRaisesRegex(ValueError, 'Packaged file mismatch'):
            validate_release(*files, COMMIT)
        files = artifacts(self.root)
        files[2].write_text('0' * 64 + '  ' + files[0].name + '\n')
        with self.assertRaisesRegex(ValueError, 'checksum file'):
            validate_release(*files, COMMIT)

    def test_existing_output_and_checkout_output_are_refused_without_writes(self):
        files = artifacts(self.root)
        output = self.root / 'existing'; output.mkdir()
        with self.assertRaisesRegex(ValueError, 'new ordinary output'):
            bind(*files, COMMIT, output)
        self.assertEqual(list(output.iterdir()), [])
        (self.root / '.git').mkdir()
        with self.assertRaisesRegex(ValueError, 'outside every Git checkout'):
            bind(*files, COMMIT, self.root / 'inside-checkout')
        self.assertFalse((self.root / 'inside-checkout').exists())

    def test_symlink_artifact_is_refused(self):
        files = artifacts(self.root)
        other = self.root / 'elsewhere'; other.mkdir()
        link = other / files[0].name; link.symlink_to(files[0])
        with self.assertRaisesRegex(ValueError, 'without symlink'):
            validate_release(link, files[1], files[2], COMMIT)


if __name__ == '__main__':
    unittest.main()
