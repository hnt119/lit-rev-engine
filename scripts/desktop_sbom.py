"""Inventory actual native payloads; metadata is evidence, not legal clearance.

Emit sidecars after signing. Nothing is written into the inspected application.
No network, imported payload code, model weights or developer environment scan.
"""
from __future__ import annotations
from email.parser import BytesParser
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import quote

_NOTICE=re.compile(r'(^|[._ -])(licen[cs]es?|copying|copyright|notice|third[._ -]?party)([._ -]|$)',re.I)
_NATIVE={'.node','.dylib','.so','.dll','.exe','.wasm'}


def _hash(path):
    h=sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def _read_json(path):
    if path.stat().st_size>16*1024*1024:raise ValueError('Oversized packaged metadata')
    return json.loads(path.read_text())


class _ChromiumCredits(HTMLParser):
    """Read upstream credit sections without rendering their links or scripts."""
    def __init__(self):
        super().__init__(convert_charrefs=True);self.sections=[];self.depth=0;self.section=None;self.capture=None
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='div':
            self.depth+=1
            if attrs.get('class')=='product':self.section={'name':'','homepage':None,'notice':''};self.start=self.depth
        if self.section is not None:
            if tag=='span' and attrs.get('class')=='title':self.capture='name'
            elif tag=='pre':self.capture='notice'
            elif tag=='a' and self.section['homepage'] is None:self.section['homepage']=attrs.get('href')
    def handle_endtag(self,tag):
        if tag in {'span','pre'}:self.capture=None
        if tag=='div':
            if self.section is not None and self.depth==self.start:
                if not self.section['name'].strip() or not self.section['notice'].strip():raise ValueError('Incomplete upstream Chromium credit section')
                self.sections.append(self.section);self.section=None
            self.depth-=1
    def handle_data(self,data):
        if self.section is not None and self.capture:self.section[self.capture]+=data


def _source_review(text):
    """Textual flags are review prompts, never license/compliance conclusions."""
    flags=[]
    for label,pattern in [('copyleft_terms_present',r'GNU (?:LESSER |LIBRARY |AFFERO )?GENERAL PUBLIC LICENSE|Mozilla Public License|MPL-2\.0|LGPL|GPL-[123]'),
                          ('source_offer_or_relink_terms_present',r'corresponding source|offer.{0,40}source|relink|re-link'),
                          ('patent_or_exception_terms_present',r'patent|exception')]:
        if re.search(pattern,text,re.I|re.S):flags.append(label)
    return flags


def _upstream_inventories(root,files):
    """Inventory observable vendor declarations; do not infer all are linked."""
    vendor=[];python=[];native_reviews=[];inputs=[]
    for path in files:
        rel=path.relative_to(root).as_posix()
        if path.name=='LICENSES.chromium.html':
            if path.stat().st_size>32*1024*1024:raise ValueError('Oversized Chromium credits')
            parser=_ChromiumCredits();parser.feed(path.read_text());parser.close()
            if parser.section is not None or not parser.sections:raise ValueError('Invalid Chromium credits')
            input={'path':rel,'sha256':_hash(path),'credit_sections':len(parser.sections)};inputs.append(input)
            for index,item in enumerate(parser.sections):
                name=item['name'].strip();text=item['notice'];flags=_source_review(text)
                vendor.append({'name':name,'version':None,'version_status':'not stated in bundled credits',
                    'homepage':item['homepage'],'input':input,'section_index':index,
                    'notice_text_sha256':sha256(text.encode()).hexdigest(),'review_flags':flags,
                    'linkage_status':'Upstream credit declaration; exact inclusion/version requires upstream build mapping.'})
        elif path.name=='PYTHON_LICENSE_PROVENANCE.json':
            data=_read_json(path)
            if data.get('schema')!='litrev.python-runtime-license-provenance.v1':raise ValueError('Unknown bundled Python license provenance')
            input={'path':rel,'sha256':_hash(path),'upstream_metadata_sha256':data.get('upstream_metadata_sha256'),
                   'upstream_archive':data.get('upstream_archive')};inputs.append(input)
            notices={}
            for name,expected in data.get('retained_notice_files',{}).items():
                if Path(name).name!=name:raise ValueError('Unsafe Python upstream notice name')
                actual=path.parent/'licenses'/name
                if not actual.is_file() or actual.is_symlink() or _hash(actual)!=expected:raise ValueError('Python upstream notice hash mismatch')
                notices['licenses/'+name]={'path':actual.relative_to(root).as_posix(),'sha256':expected}
            python.append({'name':'CPython','version':data['python_version'],'licenses':data.get('licenses',[]),
                'input':input,'notice_inputs':[notices[v] for v in [data.get('license_path')] if v in notices],
                'linkage_status':'Exact runtime-build provenance retained; binary hashes listed separately.'})
            for extension,variants in sorted(data.get('extensions',{}).items()):
                for variant_index,part in enumerate(variants):
                    # No source/build-machine absolute paths are copied from upstream link fields.
                    links=[{'name':v.get('name'),'system':bool(v.get('system')),'framework':bool(v.get('framework')),
                            'static':bool(v.get('path_static')),'dynamic':bool(v.get('path_dynamic'))} for v in part.get('links',[])]
                    license_inputs=[notices[v] for v in part.get('license_paths',[]) if v in notices]
                    missing=[v for v in part.get('license_paths',[]) if v not in notices]
                    if missing:raise ValueError('Python extension notice reference is not retained')
                    if not links and not license_inputs:continue
                    text='\n'.join((root/v['path']).read_text(errors='replace') for v in license_inputs)
                    python.append({'name':'CPython extension '+extension,'version':None,'version_status':'Extension-linked library versions not declared in projected upstream metadata',
                        'variant':variant_index,'licenses':part.get('licenses',[]),'declared_public_domain':part.get('license_public_domain'),
                        'links':links,'notice_inputs':license_inputs,'input':input,'review_flags':_source_review(text),
                        'linkage_status':'Declared upstream extension linkage; platform system/framework libraries are not assumed redistributed.'})
        elif path.name=='LICENSE' and path.parent.name=='licenses' and path.parent.parent.name.startswith('torch-'):
            text=path.read_text(errors='replace');input={'path':rel,'sha256':_hash(path)};inputs.append(input)
            # PyTorch supplies a structured Name/License inventory inside its exact wheel notice.
            entries=list(re.finditer(r'^Name: ([^\n]+)\nLicense: ([^\n]+)',text,re.M))
            for index,match in enumerate(entries):
                end=entries[index+1].start() if index+1<len(entries) else len(text)
                native_reviews.append({'name':match[1].strip(),'version':None,'version_status':'not stated in wheel third-party notice',
                    'declared_license':match[2].strip(),'input':input,'inventory_index':index,
                    'review_flags':_source_review(match[2]),
                    'linkage_status':'Declared in PyTorch repository/source notice; matching wheel binary linkage/version requires upstream mapping.',
                    'notice_section_sha256':sha256(text[match.start():end].encode()).hexdigest()})
    return {'notice_inputs':inputs,'chromium_credit_components':vendor,'python_runtime_components':python,'torch_declared_components':native_reviews}


def collect_payload(payload,source_commit,target):
    root=Path(payload).resolve(strict=True)
    if not root.is_dir():raise ValueError('Use an actual payload directory')
    if not re.fullmatch(r'(?:[a-f0-9]{40}|recipe:[a-f0-9]{64})',source_commit):raise ValueError('Bind an exact source commit or recipe SHA256')
    if target not in {'darwin-arm64','win32-x64'}:raise ValueError('Use the qualified payload target')
    files=[];links=[];native=[];components=[];unknown=[];missing=[]
    for path in sorted(root.rglob('*')):
        rel=path.relative_to(root).as_posix()
        if path.is_symlink():
            if not path.resolve(strict=True).is_relative_to(root):raise ValueError('Payload link leaves the application')
            links.append(rel);continue
        if not path.is_file():continue
        files.append(path)
        if len(files)>250000:raise ValueError('Payload inventory exceeds bounded file count')
        if path.suffix.lower() in _NATIVE or path.name in {'Electron','LiteratureReviewEngine','python3.12'}:
            native.append({'path':rel,'bytes':path.stat().st_size,'sha256':_hash(path)})
        if path.name=='package.json':
            data=_read_json(path)
            if not isinstance(data,dict) or not data.get('name'):continue
            name=str(data['name']);version=data.get('version');bom='file:'+rel
            notices=[]
            for entry in sorted(path.parent.iterdir()):
                if entry.is_file() and not entry.is_symlink() and _NOTICE.search(entry.name) and entry.stat().st_size<8*1024*1024:
                    notices.append({'path':entry.relative_to(root).as_posix(),'sha256':_hash(entry)})
            component={'type':'library','bom-ref':bom,'name':name,'hashes':[{'alg':'SHA-256','content':_hash(path)}],
                'properties':[{'name':'litrev:metadata-path','value':rel},
                    {'name':'litrev:declared-license','value':json.dumps(data.get('license'),sort_keys=True)},
                    {'name':'litrev:upstream-repository','value':json.dumps(data.get('repository'),sort_keys=True)},
                    {'name':'litrev:notice-inputs','value':json.dumps(notices,sort_keys=True)}]}
            if version:
                component.update(version=str(version),purl='pkg:npm/'+quote(name,safe='@/')+'@'+quote(str(version),safe=''))
            else:unknown.append({'name':name,'path':rel,'reason':'No exact version in bundled upstream metadata; retained file hash identifies bytes.'})
            if name=='client-only':missing.append({'name':name,'path':rel,'reason':'Published MIT declaration has no verified copyright/permission notice; publisher clarification remains required.'})
            components.append(component)
        elif path.name=='METADATA' and path.parent.name.endswith('.dist-info'):
            meta=BytesParser().parsebytes(path.read_bytes());name=meta.get('Name');version=meta.get('Version')
            if not name or not version:raise ValueError('Packaged Python distribution lacks its identity')
            normalized=re.sub(r'[-_.]+','-',name.lower());notices=[]
            for entry in path.parent.rglob('*'):
                if entry.is_file() and not entry.is_symlink() and _NOTICE.search(entry.name):notices.append({'path':entry.relative_to(root).as_posix(),'sha256':_hash(entry)})
            if not notices:
                for parent in path.parents:
                    if not parent.is_relative_to(root):break
                    extra=parent/'UPSTREAM_LICENSES'/f'{normalized}-{version}'
                    provenance=extra/'PROVENANCE.json';license_file=extra/'LICENSE'
                    if provenance.is_file() and license_file.is_file():
                        info=_read_json(provenance)
                        if info.get('name')==normalized and info.get('version')==version and info.get('license_sha256')==_hash(license_file):
                            notices.append({'path':license_file.relative_to(root).as_posix(),'sha256':_hash(license_file),
                                            'provenance':provenance.relative_to(root).as_posix(),'source_url':info.get('source_url')})
            components.append({'type':'library','bom-ref':'file:'+rel,'name':name,'version':version,
                'purl':'pkg:pypi/'+quote(normalized,safe='')+'@'+quote(version,safe=''),
                'hashes':[{'alg':'SHA-256','content':_hash(path)}],
                'properties':[{'name':'litrev:metadata-path','value':rel},
                    {'name':'litrev:declared-license','value':meta.get('License-Expression') or meta.get('License') or 'NOASSERTION'},
                    {'name':'litrev:requires-dist','value':json.dumps(meta.get_all('Requires-Dist') or [])},
                    {'name':'litrev:notice-inputs','value':json.dumps(notices,sort_keys=True)}]})
            if not notices:missing.append({'name':name,'path':rel,'reason':'No distribution-local notice file; review package tree and upstream runtime notice inventory.'})
    upstream=_upstream_inventories(root,files)
    native_review=[]
    for component in components:
        properties={v['name']:v['value'] for v in component['properties']}
        metadata=properties['litrev:metadata-path'];base=metadata.split('.dist-info/',1)[0] if '.dist-info/' in metadata else metadata.rsplit('/',1)[0]
        normalized=re.sub(r'[-_.]+','-',component['name'].lower())
        if normalized in {'torch','numpy','tokenizers','safetensors','pydantic-core','psutil','regex','pyyaml','zstandard'}:
            notices=json.loads(properties['litrev:notice-inputs'])
            native_review.append({'name':component['name'],'version':component.get('version'),'metadata_input':{'path':metadata,'sha256':component['hashes'][0]['content']},
                'notice_inputs':notices,'review_status':'Retained upstream notices; native transitive source/version mapping and applicable obligations require review.',
                'review_flags':sorted({f for v in notices for f in _source_review((root/v['path']).read_text(errors='replace'))})})
    gates=[]
    if any(c['name']=='client-only' for c in components):gates.append('Publisher-specific client-only full notice remains unresolved for bundled upstream bytes')
    if upstream['chromium_credit_components']:gates.append('Electron/Chromium credit-component exact version/source and applicable codec/patent obligation review')
    if upstream['python_runtime_components']:gates.append('CPython linked native-library version/source and applicable redistribution obligation review')
    if native_review:gates.append('Native Python wheel vendored component/source/exception review')
    if any(c['name'].startswith('@img/sharp-libvips') for c in components):gates.append('Bundled libvips corresponding-source/relink obligations require review')
    gates.append('Authorized signing/notarization and target installed-artifact acceptance')
    review={'schema':'litrev.desktop-payload-review.v1','source_identifier':source_commit,'target':target,
        'scope':'Actual payload files and bundled npm/Python metadata; upstream-vendored binary components need separate notice/source review.',
        'file_count':len(files),'symlinks':links,'component_count':len(components),
        'unknown_version_components':unknown,'notice_review_items':missing,'native_files':native,
        'native_hash_scope':'Exact bytes at collection time. Collect delivery sidecar after all signing/stapling mutations; do not reuse pre-sign hashes.',
        'public_distribution_qualified':False,
        'upstream_component_review':upstream,'native_distribution_review':native_review,
        'remaining_gates':gates}
    bom={'bomFormat':'CycloneDX','specVersion':'1.6','version':1,
        'metadata':{'component':{'type':'application','name':'Literature Review Engine','version':source_commit}},
        'components':components,
        'properties':[{'name':'litrev:target','value':target},{'name':'litrev:source-identifier','value':source_commit},
            {'name':'litrev:review-status','value':'Inventory generated; legal/native/signing gates remain explicit.'},
            {'name':'litrev:native-file-inventory','value':json.dumps(native,sort_keys=True)}]}
    return bom,review


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--payload',required=True,type=Path);p.add_argument('--source',required=True)
    p.add_argument('--target',required=True,choices=['darwin-arm64','win32-x64']);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    if a.output.exists():raise ValueError('Use a fresh SBOM sidecar directory')
    root=a.payload.resolve(strict=True)
    if a.output.absolute().is_relative_to(root):raise ValueError('Write final SBOM sidecars outside the immutable payload')
    bom,review=collect_payload(root,a.source,a.target);a.output.mkdir(parents=True)
    for name,value in [('SBOM.cdx.json',bom),('SBOM_REVIEW.json',review)]:
        (a.output/name).write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'components':review['component_count'],'native_files':len(review['native_files']),
                      'review_items':len(review['notice_review_items']),'public_qualified':False}))
if __name__=='__main__':main()
