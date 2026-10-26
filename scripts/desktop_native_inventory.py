"""Final native-header inventory layered over the capsule-pinned SBOM collector.

Read only bounded headers and hash identified native files. This separate
entrypoint preserves the exact optional-capsule recipe and its prior artifacts.
No payload code is executed and no inventory establishes legal clearance.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import struct
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.desktop_sbom import collect_payload, _hash

_CPUS={7,12,0x01000007,0x0100000c,0x0200000c,18,0x01000012}
_THIN={b'\xfe\xed\xfa\xce':'>',b'\xce\xfa\xed\xfe':'<',b'\xfe\xed\xfa\xcf':'>',b'\xcf\xfa\xed\xfe':'<'}
_FAT={b'\xca\xfe\xba\xbe':'>',b'\xbe\xba\xfe\xca':'<',b'\xca\xfe\xba\xbf':'>',b'\xbf\xba\xfe\xca':'<'}


def native_header_kind(path):
    """Reject incidental MZ text/Java class magic; never read full file content."""
    with Path(path).open('rb') as f:
        magic=f.read(4)
        if magic in _THIN:
            cpu=f.read(4)
            if len(cpu)==4 and struct.unpack(_THIN[magic]+'I',cpu)[0] in _CPUS:return 'Mach-O'
        elif magic in _FAT:
            raw=f.read(4)
            if len(raw)!=4:return None
            count=struct.unpack(_FAT[magic]+'I',raw)[0]
            cpu=f.read(4)
            if 1<=count<=32 and len(cpu)==4 and struct.unpack(_FAT[magic]+'I',cpu)[0] in _CPUS:return 'Mach-O universal'
        elif magic.startswith(b'MZ'):
            f.seek(0x3c);raw=f.read(4)
            if len(raw)!=4:return None
            offset=struct.unpack('<I',raw)[0]
            if 64<=offset<=1024*1024:
                f.seek(offset)
                if f.read(4)==b'PE\0\0':return 'PE'
        elif magic==b'\x7fELF':return 'ELF'
    return None


def collect_native_payload(payload,source_commit,target):
    root=Path(payload).resolve(strict=True)
    bom,review=collect_payload(root,source_commit,target)
    native={v['path']:v for v in review['native_files']}
    for path in sorted(root.rglob('*')):
        if path.is_symlink() or not path.is_file():continue
        kind=native_header_kind(path)
        if kind:
            rel=path.relative_to(root).as_posix()
            native[rel]={'path':rel,'bytes':path.stat().st_size,'sha256':_hash(path),'header_kind':kind}
    review['native_files']=[native[k] for k in sorted(native)]
    review['native_detection']='Exact suffix/name candidates plus bounded Mach-O thin/universal, PE signature and ELF header inspection. Header identification is not a complete static-link dependency analysis.'
    review['native_inventory_recipe_sha256']=_hash(Path(__file__))
    for prop in bom['properties']:
        if prop['name']=='litrev:native-file-inventory':prop['value']=json.dumps(review['native_files'],sort_keys=True)
    bom['properties'].append({'name':'litrev:native-inventory-recipe-sha256','value':review['native_inventory_recipe_sha256']})
    return bom,review


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--payload',required=True,type=Path);p.add_argument('--source',required=True)
    p.add_argument('--target',required=True,choices=['darwin-arm64','win32-x64']);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    root=a.payload.resolve(strict=True)
    if a.output.exists() or a.output.absolute().is_relative_to(root):raise ValueError('Use a fresh sidecar directory outside the immutable payload')
    bom,review=collect_native_payload(root,a.source,a.target);a.output.mkdir(parents=True)
    for name,value in [('SBOM.cdx.json',bom),('SBOM_REVIEW.json',review)]:
        (a.output/name).write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'components':review['component_count'],'native_files':len(review['native_files']),
                      'review_items':len(review['notice_review_items']),'public_qualified':False}))
if __name__=='__main__':main()
