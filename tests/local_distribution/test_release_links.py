"""Public links are version-bound metadata, never guessed latest URLs."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from scripts.release_links import validate, block, ROOT


def published():
    return json.loads((ROOT / "config/public_release.json").read_text())


def test_published_link_block_and_readme_are_bound():
    value = published()
    assert validate(value) == value
    assert block(value) in (ROOT / "README.md").read_text()
    assert "/releases/latest" not in block(value)


@pytest.mark.parametrize("key,value", [
    ("download_url", "https://github.com/hnt119/lit-rev-engine/releases/latest"),
    ("download_url", "https://example.com/unverified.zip"),
    ("tag", "main"),
    ("source_commit", "21096d7"),
    ("publication_verified", False),
    ("source_status", "standalone"),
    ("demo_url", "https://example.com/"),
])
def test_unbound_or_unverified_destinations_are_rejected(key, value):
    record = published(); record[key] = value
    with pytest.raises(ValueError): validate(record)


def test_unexpected_metadata_and_platform_claims_are_rejected():
    record = published(); record["secret"] = "not-an-allowed-field"
    with pytest.raises(ValueError): validate(record)
    record = published(); record["platforms"]["windows_arm"] = "tested"
    with pytest.raises(ValueError): validate(record)
    record = deepcopy(published()); record["platforms"]["windows_x64_source"] = "standalone"
    with pytest.raises(ValueError): validate(record)


def test_primary_download_and_quick_start_are_readable_versioned_destinations():
    value = published()
    primary, secondary = block(value).split('\n\n', 1)
    assert primary.startswith('**[Download — source beta ' + value['version'] + '](' + value['release_url'] + ')')
    assert '[Quick start](' + value['quick_start_url'] + ')' in primary
    assert '/blob/' + value['tag'] + '/docs/local_preview.md' in primary
    assert '/releases/download/' not in primary
    for label, key in [('Direct source ZIP','download_url'), ('Manifest','manifest_url'),
                       ('SHA-256 checksums','checksums_url'), ('Download installation guide','install_url')]:
        assert '[' + label + '](' + value[key] + ')' in secondary


@pytest.mark.parametrize('key,value', [
    ('quick_start_url','https://github.com/hnt119/lit-rev-engine/blob/main/docs/local_preview.md'),
    ('quick_start_url','https://github.com/hnt119/lit-rev-engine/releases/download/v0.3.0-beta.4/INSTALL.md'),
    ('manifest_url','https://example.com/manifest.json'),
    ('checksums_url','https://github.com/hnt119/lit-rev-engine/releases/download/v0.3.0-beta.1/lit-rev-engine-0.3.0-beta.1.SHA256SUMS'),
])
def test_rendered_guide_and_integrity_destinations_cannot_drift(key, value):
    record = published(); record[key] = value
    with pytest.raises(ValueError): validate(record)


def test_readme_regeneration_keeps_the_repaired_actions_and_other_documentation(tmp_path):
    import subprocess
    import sys
    metadata = tmp_path / 'config'; metadata.mkdir()
    scripts = tmp_path / 'scripts'; scripts.mkdir()
    (metadata / 'public_release.json').write_text(json.dumps(published()))
    (scripts / 'release_links.py').write_bytes((ROOT / 'scripts/release_links.py').read_bytes())
    before = '# Product\n\n<!-- published-release:start -->\nOLD ATTACHMENT-ONLY LINKS\n<!-- published-release:end -->\n\n<a id="requirements-and-installation"></a>\nArchitecture and archived paths stay here.\n'
    readme = tmp_path / 'README.md'; readme.write_text(before)
    command = [sys.executable, str(scripts / 'release_links.py'), '--write-readme']
    subprocess.run(command, check=True, capture_output=True)
    generated = readme.read_text()
    assert block(published()) in generated
    assert generated.startswith('# Product\n\n<!-- published-release:start -->')
    assert generated.endswith('<a id="requirements-and-installation"></a>\nArchitecture and archived paths stay here.\n')
    subprocess.run(command, check=True, capture_output=True)
    assert readme.read_text() == generated
