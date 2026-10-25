import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tarfile

import pytest

from src.web_api.hosted_operations import OperationError, create_backup, hosted_lock, restore_backup


def stores(tmp_path):
    root = tmp_path / "disk"
    data = root / "litrev"
    data.mkdir(parents=True)
    for name in ("workspaces", "web-credentials", "evidence-boards", "paper-maps", "hosted-admission"):
        with sqlite3.connect(data / (name + ".sqlite3")) as db:
            db.execute("CREATE TABLE state(id INTEGER PRIMARY KEY, payload TEXT)")
            db.execute("INSERT INTO state VALUES(1, ?)", ("synthetic-" + name,))
    artifact = data / "artifacts" / "source.json"
    artifact.parent.mkdir()
    artifact.write_text('{"synthetic":true}')
    return root, data


def test_whole_directory_roundtrip_is_exact_and_private(tmp_path):
    root, data = stores(tmp_path)
    archive = tmp_path / "protected.tar.gz"
    before = {p.relative_to(data): p.read_bytes() for p in data.rglob("*") if p.is_file()}
    assert create_backup(root, data, archive)["files"] == 6
    assert archive.stat().st_mode & 0o777 == 0o600
    target = root / "restored-new"
    assert restore_backup(root, archive, target)["files"] == 6
    assert {p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()} == before
    assert all(p.stat().st_mode & 0o777 == (0o700 if p.is_dir() else 0o600) for p in target.rglob("*"))
    assert target.stat().st_mode & 0o777 == 0o700
    # Original only-copy data is untouched; publishing never replaces it.
    assert {p.relative_to(data): p.read_bytes() for p in data.rglob("*") if p.is_file()} == before
    with pytest.raises(OperationError):
        restore_backup(root, archive, data)
    with pytest.raises(OperationError):
        create_backup(root, data, archive)


def test_live_supervisor_lock_refuses_both_operations(tmp_path):
    root, data = stores(tmp_path)
    archive = tmp_path / "backup.tar.gz"
    create_backup(root, data, archive)
    with hosted_lock(root):
        with pytest.raises(OperationError, match="stop the entire"):
            create_backup(root, data, tmp_path / "second.tar.gz")
        with pytest.raises(OperationError, match="stop the entire"):
            restore_backup(root, archive, root / "new")
    assert not (root / "new").exists()


def test_crash_retained_wal_is_included_without_touching_original(tmp_path):
    root, data = stores(tmp_path)
    db_path = data / "crash.sqlite3"
    subprocess.run([sys.executable, "-c",
        "import os,sqlite3,sys; db=sqlite3.connect(sys.argv[1]); db.execute('PRAGMA journal_mode=WAL'); "
        "db.execute('CREATE TABLE committed(value TEXT)'); db.execute(\"INSERT INTO committed VALUES('retained')\"); db.commit(); os._exit(0)",
        str(db_path)], check=True)
    assert Path(str(db_path) + "-wal").stat().st_size > 0
    before = {p.relative_to(data): p.read_bytes() for p in data.rglob("*") if p.is_file()}
    archive = tmp_path / "crash.tar.gz"
    create_backup(root, data, archive)
    assert {p.relative_to(data): p.read_bytes() for p in data.rglob("*") if p.is_file()} == before
    restore_backup(root, archive, root / "crash-restored")
    with sqlite3.connect(root / "crash-restored" / "crash.sqlite3") as db:
        assert db.execute('SELECT value FROM committed').fetchall() == [('retained',)]


def test_backup_refuses_symlinks_special_files_and_bad_database(tmp_path):
    root, data = stores(tmp_path)
    link = data / "escape"
    link.symlink_to(tmp_path)
    with pytest.raises(OperationError):
        create_backup(root, data, tmp_path / "link.tar.gz")
    link.unlink()
    fifo = data / "pipe"
    os.mkfifo(fifo)
    with pytest.raises(OperationError):
        create_backup(root, data, tmp_path / "fifo.tar.gz")
    fifo.unlink()
    (data / "workspaces.sqlite3").write_bytes(b"corrupt database")
    with pytest.raises(OperationError, match="integrity"):
        create_backup(root, data, tmp_path / "corrupt.tar.gz")


def test_output_must_be_off_disk_and_input_data_must_exist(tmp_path):
    root, data = stores(tmp_path)
    with pytest.raises(OperationError):
        create_backup(root, data, root / "backup.tar.gz")
    with pytest.raises(OperationError):
        create_backup(root, root / "missing", tmp_path / "backup.tar.gz")
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(OperationError):
        create_backup(alias, alias / "litrev", tmp_path / "backup.tar.gz")


@pytest.mark.parametrize("name,kind", [("../escape", "file"), ("/absolute", "file"), ("data/link", "link"), ("data/../escape", "file")])
def test_restore_rejects_traversal_and_links_without_publishing(tmp_path, name, kind):
    root, _ = stores(tmp_path)
    archive = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        entry = tarfile.TarInfo(name)
        if kind == "link":
            entry.type, entry.linkname = tarfile.SYMTYPE, "../../outside"
            tar.addfile(entry)
        else:
            entry.size = 1
            tar.addfile(entry, io.BytesIO(b"x"))
    with pytest.raises(OperationError):
        restore_backup(root, archive, root / "new")
    assert not (root / "new").exists()
    assert not list(root.glob(".litrev-restore-*"))


def test_manifest_tampering_rejected(tmp_path):
    root, _ = stores(tmp_path)
    archive = tmp_path / "tampered.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        payload = json.dumps({"schema": "litrev.stopped-backup.v1", "files": {"a": {"size": 1, "sha256": "bad"}}}).encode()
        info = tarfile.TarInfo("litrev-backup-manifest.json")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
        info = tarfile.TarInfo("data/a")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(OperationError, match="manifest"):
        restore_backup(root, archive, root / "new")
    assert not (root / "new").exists()
