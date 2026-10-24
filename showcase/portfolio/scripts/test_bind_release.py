"""Offline synthetic release-binding checks. No research data or website writes."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from bind_release import (
    bind, encoded, NAME, OVERLAY, sha, validate_release, VERSION,
    MIT_LICENSE_TEXT, MIT_LICENSE_SHA256,
)


COMMIT = 'a' * 40


def artifacts(root, *, commit=COMMIT, state='clean committed checkout', bad_hash=False,
              license_bytes=None, spdx_license='MIT', notices=True, track_b=False):
    payload = {'README.md': b'Synthetic setup-required source fixture.\n',
               'LICENSE': MIT_LICENSE_TEXT.encode() if license_bytes is None else license_bytes}
    if notices:
        payload.update({'DISTRIBUTION_TERMS.md': b'Synthetic separate article/dependency notices.\n',
            'THIRD_PARTY_NOTICES.md': b'Synthetic third-party notices.\n',
            'examples/mvp/offline_microbiome_30_v1/README.md': b'Synthetic public attribution only.\n',
            'examples/mvp/offline_microbiome_30_v1/manifest.json': b'{}\n'})
    if track_b:
        payload['src/review/pilot.py'] = b'# Synthetic forbidden Track B marker\n'
    release = {'schema': 'litrev.local-preview.release.v1', 'version': VERSION,
        'source_commit': commit, 'source_state': state, 'runtimes_bundled': False,
        'models_bundled': False, 'spdx_license': spdx_license,
        'license_sha256': sha(payload['LICENSE']),
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
        self.assertEqual(metadata['spdx_license'], 'MIT')
        self.assertEqual(metadata['license_sha256'], MIT_LICENSE_SHA256)
        self.assertEqual((output / 'public' / metadata['license_path'].removeprefix('/')).read_bytes(), MIT_LICENSE_TEXT.encode())
        self.assertEqual((output / 'public' / metadata['installation_path'].removeprefix('/')).read_bytes(), b'Synthetic setup-required source fixture.\n')
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

    def test_unlicensed_and_spoofed_mit_artifacts_are_refused_even_with_fresh_hashes(self):
        for values in ({'license_bytes': b'MIT\nAn incomplete fake grant.\n'},
                       {'spdx_license': None}, {'license_bytes': b''}):
            with self.subTest(values=values):
                files = artifacts(self.root, **values)
                with self.assertRaisesRegex(ValueError, 'standard MIT'):
                    validate_release(*files, COMMIT)

    def test_third_party_distribution_notices_cannot_be_omitted(self):
        files = artifacts(self.root, notices=False)
        with self.assertRaisesRegex(ValueError, 'distribution notices'):
            validate_release(*files, COMMIT)

    def test_template_is_beta_only_and_demo_does_not_call_research_services(self):
        template = json.loads((OVERLAY / 'src/data/local-preview-download.json').read_bytes())
        self.assertEqual(template['version'], '0.3.0-beta.1')
        self.assertEqual(template['spdx_license'], 'MIT')
        self.assertFalse(template['available'])
        for key in ('archive_path','manifest_path','checksums_path','license_path','installation_path'):
            self.assertEqual(template[key], '')
        component = (OVERLAY / 'src/components/LiteratureShowcase.tsx').read_text()
        for forbidden in ('fetch(', 'XMLHttpRequest', 'WebSocket(', 'EventSource(',
                          'localStorage', 'sessionStorage', 'sendBeacon(', 'dangerouslySetInnerHTML',
                          'localhost:', '127.0.0.1:', '.0-local-preview.2.zip'):
            self.assertNotIn(forbidden, component)
        for action in ('Try the demo', 'Download local beta', 'Installation', 'MIT license', 'View source'):
            self.assertIn(action, component)

    def test_track_b_pilot_is_refused_even_when_hashes_and_mit_match(self):
        files = artifacts(self.root, track_b=True)
        with self.assertRaisesRegex(ValueError, 'Track B'):
            validate_release(*files, COMMIT)


if __name__ == '__main__':
    unittest.main()
