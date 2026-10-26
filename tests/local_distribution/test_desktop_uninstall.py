"""Uninstall plan safety; these tests do not execute a Windows installer."""
import json
from pathlib import Path
import pytest
from scripts import desktop_uninstall as removal
from scripts.build_local_preview import digest,json_bytes


def installed(tmp_path):
    root=tmp_path/'Programs/Literature Review Engine';app=root/'app-0.3.0-test.1';(app/'resources').mkdir(parents=True)
    owned=app/'LiteratureReviewEngine.exe';owned.write_bytes(b'Synthetic owned executable fixture')
    other=app/'resources/reviewed.txt';other.write_text('Reviewed own app resource')
    files={p.relative_to(app).as_posix():{'bytes':p.stat().st_size,'sha256':digest(p.read_bytes())} for p in (owned,other)}
    value={'schema':'litrev.desktop.installed-files.v1','app_id':removal.PRODUCT,'version':'0.3.0-test.1','source_commit':'a'*40,'files':files}
    manifest=app/'INSTALLATION.json';manifest.write_bytes(json_bytes(value))
    return root,app,manifest,value


def test_foreign_root_or_symlinked_root_rejected_before_cleanup(tmp_path):
    root,app,manifest,value=installed(tmp_path)
    data=tmp_path/'Research';data.mkdir();(data/'private.txt').write_text('Synthetic research data')
    with pytest.raises(ValueError):removal.validate_root(data,root)
    link=tmp_path/'alias';link.symlink_to(root,target_is_directory=True)
    with pytest.raises(ValueError):removal.validate_root(link,root)
    assert (data/'private.txt').read_text()=='Synthetic research data'


def test_uninstall_removes_only_registered_original_files_preserves_unknown_and_modified(tmp_path):
    root,app,manifest,value=installed(tmp_path)
    unknown=app/'user-note.txt';unknown.write_text('Unexpected user data is retained')
    empty=app/'unexpected-empty-directory';empty.mkdir()
    modified=app/'resources/reviewed.txt';modified.write_text('Modified resource must be retained')
    plan=removal.plan_version(root,'0.3.0-test.1',digest(manifest.read_bytes()))
    result=removal.remove_plans([plan])
    assert not (app/'LiteratureReviewEngine.exe').exists()
    assert unknown.exists() and modified.exists() and empty.is_dir()
    assert manifest.exists() and result['preserved_modified_or_unexpected_entries']>0


def test_tampered_manifest_escape_or_reparse_member_never_deletes_data(tmp_path):
    root,app,manifest,value=installed(tmp_path)
    data=tmp_path/'Research';data.mkdir();secret=data/'private.txt';secret.write_text('Keep data')
    checksum=digest(manifest.read_bytes());manifest.write_text('tampered')
    with pytest.raises(ValueError,match='manifest changed'):removal.plan_version(root,'0.3.0-test.1',checksum)
    value['files']['../../Research/private.txt']={'bytes':secret.stat().st_size,'sha256':digest(secret.read_bytes())};manifest.write_bytes(json_bytes(value))
    with pytest.raises(ValueError,match='Unsafe'):removal.plan_version(root,'0.3.0-test.1',digest(manifest.read_bytes()))
    value['files'].pop('../../Research/private.txt');target=app/'resources/reviewed.txt';target.unlink();target.symlink_to(secret);manifest.write_bytes(json_bytes(value))
    with pytest.raises(ValueError,match='reparse'):removal.plan_version(root,'0.3.0-test.1',digest(manifest.read_bytes()))
    assert secret.read_text()=='Keep data'


def test_exact_owned_tree_can_be_removed_without_recursing_foreign_directories(tmp_path):
    root,app,manifest,value=installed(tmp_path)
    plan=removal.plan_version(root,'0.3.0-test.1',digest(manifest.read_bytes()))
    assert removal.remove_plans([plan])['preserved_modified_or_unexpected_entries']==0
    assert not app.exists() and root.exists()


def test_file_modified_after_planning_is_preserved(tmp_path):
    root,app,manifest,value=installed(tmp_path)
    plan=removal.plan_version(root,'0.3.0-test.1',digest(manifest.read_bytes()))
    modified=app/'resources/reviewed.txt';modified.write_text('Edited after plan was created')
    removal.remove_plans([plan])
    assert modified.read_text()=='Edited after plan was created' and manifest.exists()
