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
