"""Policy/unit boundaries; these are never represented as native Windows proof."""
from types import SimpleNamespace
import pytest


def test_mapped_network_ntfs_is_rejected_before_volume_query_or_file_access(monkeypatch):
    from src.platform_support import windows
    calls = []
    api = SimpleNamespace(GetVolumeInformation=lambda *_: pytest.fail('Remote-drive rejection must precede volume metadata and files'))
    con = SimpleNamespace(DRIVE_FIXED=3)
    file = SimpleNamespace(GetDriveType=lambda drive: calls.append(drive) or 4)
    monkeypatch.setattr(windows, 'require_runtime', lambda: (None, api, con, file, None, None, None, None, None))
    with pytest.raises(ValueError, match='fixed local drive'): windows._require_ntfs('Z:\\')
    assert calls == ['Z:\\']


def test_only_fixed_ntfs_is_accepted_and_drive_type_is_not_cached(monkeypatch):
    from src.platform_support import windows
    drive_type = [3]
    calls = []
    api = SimpleNamespace(GetVolumeInformation=lambda drive: calls.append(drive) or ('label', 1, 255, 0, 'NTFS'))
    con = SimpleNamespace(DRIVE_FIXED=3)
    file = SimpleNamespace(GetDriveType=lambda drive: drive_type[0])
    monkeypatch.setattr(windows, 'require_runtime', lambda: (None, api, con, file, None, None, None, None, None))
    windows._require_ntfs('Z:\\')
    drive_type[0] = 4
    with pytest.raises(ValueError): windows._require_ntfs('Z:\\')
    assert calls == ['Z:\\']
