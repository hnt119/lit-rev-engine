"""Policy-only preflight tests; native Windows ACL execution is NOT_RUN."""
from pathlib import Path
import pytest
from scripts import desktop_install_root as preflight


def test_acl_requires_current_owner_and_no_foreign_writer():
    user='S-1-5-21-fixture'
    preflight.validate_acl(user,user,[(user,0x1f01ff,False),('S-1-5-18',0x1f01ff,False),('S-1-1-0',0x1200a9,False)])
    with pytest.raises(ValueError,match='owned'):preflight.validate_acl('S-1-5-21-other',user,[])
    for mask in [2,4,16,64,256,0x10000,0x40000,0x80000,0x10000000,0x40000000]:
        with pytest.raises(ValueError,match='another principal'):preflight.validate_acl(user,user,[('S-1-1-0',mask,False)])


def test_preflight_runs_temp_core_python_before_final_payload_extraction():
    source=(Path(__file__).parents[2]/'apps/desktop/installer.nsi').read_text()
    section=source.split('Section "Application"',1)[1].split('SectionEnd',1)[0]
    assert section.index('desktop_install_root.py')<section.index('SetOutPath "$INSTDIR')
    assert '-I -S -B' in section and '$PLUGINSDIR\\python\\python.exe' in section
    assert 'No research directory' not in preflight.__doc__  # no data cleanup helper
