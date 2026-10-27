"""Final native-header inventory layered over the capsule-pinned SBOM collector.

Read only bounded headers and hash identified native files. This separate
entrypoint preserves the exact optional-capsule recipe and its prior artifacts.
No payload code is executed and no inventory establishes legal clearance.
"""
from __future__ import annotations
import argparse
import base64
import csv
import json
import re
from pathlib import Path, PurePosixPath
import struct
import shutil
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


DEFAULT_SOURCE_EVIDENCE=Path(__file__).resolve().parents[1]/'apps/desktop/notices/native'


def _evidence_files(directory):
    root=Path(directory).absolute()
    if root.is_symlink() or root.resolve()!=root:raise ValueError('Source evidence cannot contain linked directory parents')
    manifest=root/'MANIFEST.json'
    if manifest.is_symlink() or manifest.stat().st_size>256*1024:raise ValueError('Invalid bounded source-evidence manifest')
    record=json.loads(manifest.read_text())
    if record.get('schema')!='litrev.native.source-evidence-files.v1' or not isinstance(record.get('files'),dict):raise ValueError('Unknown source-evidence schema')
    expected=record['files'];total=0
    if any(p.is_symlink() for p in root.rglob('*')):raise ValueError('Linked source-evidence input')
    for name,value in expected.items():
        relative=PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name or relative.as_posix()!=name:raise ValueError('Unsafe source-evidence path')
        if not isinstance(value,dict) or type(value.get('bytes')) is not int or not 0<=value['bytes']<=512*1024 or not re.fullmatch(r'[a-f0-9]{64}',value.get('sha256','')):raise ValueError('Invalid source-evidence file binding')
        path=root/Path(*relative.parts)
        if any(p.is_symlink() for p in (path,*path.parents) if p.is_relative_to(root)):raise ValueError('Linked source-evidence input')
        if not path.is_file() or path.stat().st_size!=value['bytes'] or _hash(path)!=value['sha256']:raise ValueError('Source-evidence input hash mismatch')
        total+=value['bytes']
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual!=set(expected)|{'MANIFEST.json'} or len(expected)>1024 or total>8*1024*1024:raise ValueError('Source-evidence closure differs or exceeds bounds')
    evidence=json.loads((root/'SOURCE_EVIDENCE.json').read_text())
    if evidence.get('schema')!='litrev.native.source-evidence.v1' or _hash(root/'SOURCE_EVIDENCE.json')!=record['source_evidence_sha256']:raise ValueError('Source-evidence identity mismatch')
    return root,record,evidence


def copy_native_source_evidence(destination,source=DEFAULT_SOURCE_EVIDENCE):
    """Build-time only: retain the reviewed source/notice closure, no download."""
    root,record,_=_evidence_files(source);destination=Path(destination)
    if destination.exists() or destination.is_symlink():raise ValueError('Never overwrite an existing native-notice payload')
    shutil.copytree(root,destination,symlinks=False)
    _evidence_files(destination)
    return {'schema':'litrev.native.source-evidence-copy.v1','manifest_sha256':_hash(destination/'MANIFEST.json'),
            'files':len(record['files'])+1,'bytes':sum(v['bytes'] for v in record['files'].values()),
            'qualification':'Retained exact source/notice evidence; component linkage and legal qualification remain separate.'}


def _wheel_ownership(root,bom,native):
    """Associate actual native bytes with RECORD claims; signing may change bytes."""
    groups=[];claimed=set();outside=0
    for component in bom['components']:
        props={v['name']:v['value'] for v in component['properties']};meta=root/props['litrev:metadata-path']
        if meta.name!='METADATA':continue
        record=meta.parent/'RECORD'
        if not record.is_file() or record.is_symlink():continue
        if record.stat().st_size>8*1024*1024:raise ValueError('Oversized wheel RECORD')
        entries=[]
        for row in csv.reader(record.read_text().splitlines()):
            if len(row)!=3:raise ValueError('Malformed wheel RECORD')
            relative=PurePosixPath(row[0])
            if relative.is_absolute() or '\\' in row[0] or ':' in row[0]:continue
            actual=(meta.parent.parent/Path(*relative.parts)).resolve()
            if not actual.is_relative_to(root):outside+=1;continue
            path=actual.relative_to(root).as_posix()
            if path not in native:continue
            expected=None
            if row[1].startswith('sha256='):
                value=row[1].split('=',1)[1]
                try:
                    raw=base64.urlsafe_b64decode(value+'='*((-len(value))%4))
                    if len(raw)==32:expected=raw.hex()
                except ValueError:pass
            entries.append({'path':path,'payload_sha256':native[path]['sha256'],'record_sha256':expected,
                'payload_matches_record':expected==native[path]['sha256'] if expected else None})
            claimed.add(path)
        if entries:groups.append({'name':component['name'],'version':component.get('version'),
            'metadata':{'path':meta.relative_to(root).as_posix(),'sha256':_hash(meta)},
            'record':{'path':record.relative_to(root).as_posix(),'sha256':_hash(record)},
            'notice_inputs':json.loads(props['litrev:notice-inputs']),'native_files':entries,
            'scope':'Wheel RECORD ownership declaration; actual signed payload hashes remain independent. A mismatch is not silently treated as equivalence and needs signing/build receipt context.'})
    return groups,[native[k] for k in sorted(set(native)-claimed)],outside


def _source_context(root,bom,source_evidence):
    candidates=[root/'Contents/Resources/NATIVE_DEPENDENCY_NOTICES',root/'resources/NATIVE_DEPENDENCY_NOTICES',root/'NATIVE_DEPENDENCY_NOTICES']
    bundled=next((p for p in candidates if p.exists()),None)
    selected=bundled or source_evidence
    if selected is None:return {'state':'not_bundled','version_claims':'Unknown version fields were retained; no source hint inferred.'}
    directory,manifest,evidence=_evidence_files(selected)
    parent=evidence['components']['next']
    if parent.get('version')!='16.4.2' or parent.get('source_manifest')!='next-16.4.2/package.json' or parent['source_manifest'] not in manifest['files']:raise ValueError('Unreviewed Next source evidence identity')
    upstream=json.loads((directory/parent['source_manifest']).read_text())
    if upstream.get('name')!='next' or upstream.get('version')!=parent['version']:raise ValueError('Next source evidence metadata mismatch')
    pins={**upstream.get('dependencies',{}),**upstream.get('devDependencies',{})};hints=[]
    for component in bom['components']:
        if component.get('version') or component['name'] not in pins:continue
        props={v['name']:v['value'] for v in component['properties']};path=props['litrev:metadata-path']
        if '/next/dist/compiled/' not in path:continue
        hints.append({'name':component['name'],'metadata_path':path,'metadata_sha256':component['hashes'][0]['content'],
            'parent_version':parent['version'],'source_declared_dependency':pins[component['name']],
            'source_manifest_sha256':_hash(directory/parent['source_manifest']),
            'version_scope':'Parent source-build declaration, not an independently established exact bundled component version.'})
    names={re.sub(r'[-_.]+','-',c['name'].lower()) for c in bom['components']}
    available=evidence['components'];present={}
    if 'next' in names or hints:present['next']=available['next']
    if 'pydantic-core' in names:present['pydantic_core']=available['pydantic_core']
    if any(root.rglob('PYTHON_LICENSE_PROVENANCE.json')):present['python_build_standalone']=available['python_build_standalone']
    if any(root.rglob('LICENSES.chromium.html')):present['electron']=available['electron']
    return {'state':'bundled_verified' if bundled else 'external_audit_evidence_not_bundled',
            'manifest_sha256':_hash(directory/'MANIFEST.json'),'verified_files':len(manifest['files']),
            'source_components':present,'compiled_module_source_hints':hints,
            'source_package_review_items':evidence['pending_gates'],
            'review_item_scope':'Source-package checklist; only component-specific applicable conditions are delivery gates, not absent components or unknown-version labels.',
            'legal_clearance':False}


def collect_native_payload(payload,source_commit,target,*,source_evidence=None):
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
    ownership,unmapped,outside=_wheel_ownership(root,bom,native)
    review['native_wheel_ownership']=ownership;review['native_files_without_wheel_record']=unmapped
    review['wheel_record_entries_outside_payload']=outside
    review['version_source_evidence']=_source_context(root,bom,source_evidence)
    review['native_detection']='Exact suffix/name candidates plus bounded Mach-O thin/universal, PE signature and ELF header inspection. Header identification is not a complete static-link dependency analysis.'
    review['native_inventory_recipe_sha256']=_hash(Path(__file__))
    for prop in bom['properties']:
        if prop['name']=='litrev:native-file-inventory':prop['value']=json.dumps(review['native_files'],sort_keys=True)
    bom['properties'].append({'name':'litrev:native-inventory-recipe-sha256','value':review['native_inventory_recipe_sha256']})
    return bom,review


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--payload',required=True,type=Path);p.add_argument('--source',required=True)
    p.add_argument('--source-evidence',type=Path,help='Optional external audit evidence; never mislabeled as bundled notices')
    p.add_argument('--target',required=True,choices=['darwin-arm64','win32-x64']);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    root=a.payload.resolve(strict=True)
    if a.output.exists() or a.output.absolute().is_relative_to(root):raise ValueError('Use a fresh sidecar directory outside the immutable payload')
    bom,review=collect_native_payload(root,a.source,a.target,source_evidence=a.source_evidence);a.output.mkdir(parents=True)
    for name,value in [('SBOM.cdx.json',bom),('SBOM_REVIEW.json',review)]:
        (a.output/name).write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'components':review['component_count'],'native_files':len(review['native_files']),
                      'review_items':len(review['notice_review_items']),'public_qualified':False}))
if __name__=='__main__':main()
