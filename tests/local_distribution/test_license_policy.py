"""Distribution license is actual approved text, not a filename-only gate."""
import importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("license_policy",ROOT/"scripts/license_policy.py")
policy=importlib.util.module_from_spec(spec);spec.loader.exec_module(policy)

def valid(root):
    (root/"LICENSE").write_text(policy.MIT_LICENSE_TEXT)
    (root/"THIRD_PARTY_NOTICES.md").write_text(policy.THIRD_PARTY_BOUNDARY)
    (root/"DISTRIBUTION_TERMS.md").write_text("SPDX-License-Identifier: MIT\n"+policy.THIRD_PARTY_BOUNDARY)

def test_exact_mit_owner_and_third_party_boundaries(tmp_path):
    valid(tmp_path)
    assert policy.validate_distribution_license(tmp_path)["license_sha256"]==policy.MIT_LICENSE_SHA256
    assert "Copyright (c) 2026 Yixuan Huang" in (tmp_path/"LICENSE").read_text()

@pytest.mark.parametrize("name",["LICENSE","THIRD_PARTY_NOTICES.md","DISTRIBUTION_TERMS.md"])
def test_missing_notice_is_not_replaced_by_another_filename(tmp_path,name):
    valid(tmp_path);(tmp_path/name).unlink()
    with pytest.raises(ValueError):policy.validate_distribution_license(tmp_path)

@pytest.mark.parametrize("change",["owner","restriction","notice"])
def test_modified_grant_or_lost_third_party_boundary_is_rejected(tmp_path,change):
    valid(tmp_path)
    if change=="owner":(tmp_path/"LICENSE").write_text(policy.MIT_LICENSE_TEXT.replace("Yixuan Huang","Someone Else"))
    elif change=="restriction":(tmp_path/"LICENSE").write_text(policy.MIT_LICENSE_TEXT+"Noncommercial beta only.\n")
    else:(tmp_path/"THIRD_PARTY_NOTICES.md").write_text("All bundled content is MIT")
    with pytest.raises(ValueError):policy.validate_distribution_license(tmp_path)

def test_linked_license_rejected(tmp_path):
    valid(tmp_path);target=tmp_path/"other";target.write_text(policy.MIT_LICENSE_TEXT)
    (tmp_path/"LICENSE").unlink();(tmp_path/"LICENSE").symlink_to(target)
    with pytest.raises(ValueError):policy.validate_distribution_license(tmp_path)
