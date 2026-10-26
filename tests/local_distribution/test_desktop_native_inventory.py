"""Bounded header inspection catches extensionless native files without execution."""
from hashlib import sha256
import json
import struct
from scripts.desktop_native_inventory import native_header_kind,collect_native_payload


def test_extensionless_macho_fat_and_pe_headers_are_hash_bound(tmp_path):
    bodies={'Electron Framework':b'\xcf\xfa\xed\xfe'+struct.pack('<I',0x0100000c)+b'SYNTHETIC',
        'helper':b'\xca\xfe\xba\xbe'+struct.pack('>II',1,0x0100000c)+b'SYNTHETIC',
        'windows-no-suffix':b'MZ'+b'\0'*58+struct.pack('<I',64)+b'PE\0\0SYNTHETIC'}
    for name,raw in bodies.items():(tmp_path/name).write_bytes(raw)
    bom,r=collect_native_payload(tmp_path,'a'*40,'darwin-arm64')
    assert len(r['native_files'])==3
    assert {v['header_kind'] for v in r['native_files']}=={'Mach-O','Mach-O universal','PE'}
    for item in r['native_files']:assert item['sha256']==sha256(bodies[item['path']]).hexdigest()
    assert str(tmp_path) not in json.dumps(bom)+json.dumps(r)


def test_short_text_java_magic_and_unbounded_pe_offset_do_not_claim_native(tmp_path):
    bodies=[b'',b'MZ this is text',b'\xca\xfe\xba\xbe\x00\x00\x00\x41Java',
        b'\xcf\xfa\xed\xfeTEXT',b'MZ'+b'\0'*58+struct.pack('<I',0xffffffff)]
    for index,raw in enumerate(bodies):
        path=tmp_path/str(index);path.write_bytes(raw);assert native_header_kind(path) is None
