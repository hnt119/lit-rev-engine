"""Install only an application-pinned native runtime capsule outside the app.

Invoked with the bundled CORE interpreter. No pip, model download, URLs, provider
keys or arbitrary archive code. An app catalog hash binds every executable byte.
"""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import signal
import shutil
import stat
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.platform_support.files import (private_directory, assert_no_links, open_private,
    owned_path, publish_new, sync_directory)

SCHEMA='litrev.desktop.optional-runtime-catalog.v1'
MANIFEST='litrev.desktop.optional-runtime.v1'
MAX_ARCHIVE=4*1024**3
MAX_UNPACKED=8*1024**3
MAX_FILES=100000
EXPECTED={'torch':'2.12.0','transformers':'5.12.0','tokenizers':'0.22.2',
          'safetensors':'0.8.0','huggingface-hub':'1.19.0','numpy':'2.4.6',
          'pydantic':'2.13.4','certifi':'2026.10.18','fastapi':'0.153.0',
          'starlette':'1.3.1','uvicorn':'0.54.0'}
HASH=re.compile(r'^[a-f0-9]{64}$')
ID=re.compile(r'^[a-z0-9][a-z0-9._-]{0,79}$')

class RuntimeRejected(ValueError):
    pass


def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)


def digest_file(path):
    h=sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def _json(raw):
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result:raise RuntimeRejected('Duplicate runtime metadata key.')
            result[k]=v
        return result
    try:return json.loads(raw,object_pairs_hook=unique)
    except (ValueError,UnicodeError):raise RuntimeRejected('Runtime metadata is not valid JSON.') from None


def relative(value):
    if not isinstance(value,str) or not value or '\\' in value or ':' in value or any(ord(c)<32 for c in value):
        raise RuntimeRejected('Unsafe runtime file path.')
    p=PurePosixPath(value)
    if p.is_absolute() or '..' in p.parts or p.as_posix()!=value or value=='.':
        raise RuntimeRejected('Unsafe runtime file path.')
    if any(x.endswith((' ','.')) for x in p.parts):raise RuntimeRejected('Unsafe platform filename.')
    return Path(*p.parts)


def catalog_entry(catalog_path,target):
    path=Path(catalog_path)
    if path.is_symlink() or path.stat().st_size>128*1024:raise RuntimeRejected('Invalid application runtime catalog.')
    catalog=_json(path.read_bytes())
    if catalog.get('schema')!=SCHEMA:raise RuntimeRejected('Unknown application runtime catalog.')
    entry=catalog.get('targets',{}).get(target)
    if not isinstance(entry,dict) or entry.get('availability')!='available':
        return None,(entry or {}).get('reason','This target has no reviewed optional runtime.')
    if (not ID.fullmatch(entry.get('id','')) or not HASH.fullmatch(entry.get('archive_sha256',''))
            or not HASH.fullmatch(entry.get('manifest_sha256',''))
            or entry.get('format')!='zip' or type(entry.get('archive_bytes')) is not int
            or not 0<entry['archive_bytes']<=MAX_ARCHIVE):
        raise RuntimeRejected('Incomplete application-pinned runtime identity.')
    relative(entry.get('python_relative'))
    return entry,''


def parse_manifest(raw,entry,target):
    if len(raw)>32*1024*1024 or sha256(raw).hexdigest()!=entry['manifest_sha256']:
        raise RuntimeRejected('Runtime manifest does not match the application catalog.')
    m=_json(raw)
    if (m.get('schema')!=MANIFEST or m.get('id')!=entry['id'] or m.get('target')!=target
            or m.get('python_relative')!=entry['python_relative']):
        raise RuntimeRejected('Runtime manifest belongs to another app or target.')
    files=m.get('files');versions=m.get('distributions')
    if not isinstance(files,dict) or not 1<=len(files)<=MAX_FILES or not isinstance(versions,dict):
        raise RuntimeRejected('Invalid runtime inventory.')
    folded=set();total=0
    for path,v in files.items():
        relative(path)
        if path.casefold() in folded:raise RuntimeRejected('Duplicate platform runtime path.')
        folded.add(path.casefold())
        if (not isinstance(v,dict) or not HASH.fullmatch(v.get('sha256',''))
                or type(v.get('bytes')) is not int or not 0<=v['bytes']<=MAX_UNPACKED
                or v.get('mode') not in (0o400,0o500)):
            raise RuntimeRejected('Invalid runtime file digest, size or mode.')
        total+=v['bytes']
    if total>MAX_UNPACKED or entry['python_relative'] not in files:
        raise RuntimeRejected('Runtime inventory exceeds bounds or lacks its interpreter.')
    for name,version in EXPECTED.items():
        if versions.get(name,'').split('+',1)[0]!=version:
            raise RuntimeRejected('Runtime dependency versions do not match the frozen profiles.')
    return m


def roots(data_root):
    root=private_directory(data_root)
    return private_directory(root/'optional-runtimes')


def verify_slot(slot,manifest,entry,target):
    slot=assert_no_links(slot)
    if not owned_path(slot,private=True):raise RuntimeRejected('Optional runtime is not privately owned.')
    recorded=slot/'RUNTIME.json'
    if recorded.is_symlink() or not recorded.is_file():raise RuntimeRejected('Installed runtime has no bound manifest.')
    m=parse_manifest(recorded.read_bytes(),entry,target)
    if manifest is not None and m!=manifest:raise RuntimeRejected('Installed runtime manifest changed.')
    expected=set(m['files'])|{'RUNTIME.json','INSTALL.json'}
    actual=set()
    for path in slot.rglob('*'):
        assert_no_links(path)
        if path.is_file():actual.add(path.relative_to(slot).as_posix())
    if actual!=expected:raise RuntimeRejected('Installed runtime contains missing or unapproved files.')
    for name,record in m['files'].items():
        p=slot/relative(name)
        if p.stat().st_size!=record['bytes'] or digest_file(p)!=record['sha256']:
            raise RuntimeRejected('Installed runtime failed its per-file integrity check.')
    install=_json((slot/'INSTALL.json').read_bytes())
    if install!={'schema':'litrev.desktop.optional-install.v1','archive_sha256':entry['archive_sha256'],
                 'manifest_sha256':entry['manifest_sha256'],'target':target,'runtime_id':entry['id']}:
        raise RuntimeRejected('Installed runtime receipt does not match this application catalog.')
    return {'state':'installed_verified','id':entry['id'],'python':str(slot/relative(entry['python_relative'])),
            'target':target,'message':'Pinned neural libraries installed; model execution remains a separate explicit runtime check.'}


def status(catalog,data_root,target):
    entry,reason=catalog_entry(catalog,target)
    if entry is None:return {'state':'unavailable','target':target,'message':reason}
    slot=roots(data_root)/entry['id']
    if not slot.exists():return {'state':'not_installed','id':entry['id'],'target':target,'message':'Install the exact optional runtime capsule explicitly from the application menu.'}
    return verify_slot(slot,None,entry,target)


def self_test(python):
    code="""import socket
socket.socket.connect=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('No network in runtime verification'))
import torch,transformers,tokenizers,safetensors,huggingface_hub,numpy,pydantic,fastapi,uvicorn
from importlib.metadata import version
assert torch.zeros(1,device='cpu').shape==(1,)
"""
    env={k:v for k,v in os.environ.items() if k in {'SystemRoot','WINDIR','TMP','TEMP','TMPDIR','HOME','USERPROFILE'}}
    env.update(PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    try:
        child=subprocess.Popen([str(python),'-I','-B','-c',code],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            child.communicate(timeout=120)
        except BaseException:
            child.terminate()
            try:child.wait(timeout=3)
            except subprocess.TimeoutExpired:child.kill();child.wait(timeout=3)
            raise
    except (OSError,subprocess.TimeoutExpired):raise RuntimeRejected('Optional runtime could not execute its bounded library check.') from None
    if child.returncode:raise RuntimeRejected('Optional runtime failed its bounded library check; Core remains available.')


def install(archive_path,catalog,data_root,target,*,runner=self_test):
    entry,reason=catalog_entry(catalog,target)
    if entry is None:raise RuntimeRejected(reason)
    archive=assert_no_links(archive_path)
    if (not archive.is_file() or archive.stat().st_size!=entry['archive_bytes']
            or digest_file(archive)!=entry['archive_sha256']):
        raise RuntimeRejected('Select the exact runtime capsule pinned by this application build.')
    root=roots(data_root);slot=root/entry['id']
    if slot.exists():return verify_slot(slot,None,entry,target)
    lock=root/'.runtime-install.lock';token=secrets.token_hex(16)
    try:fd=open_private(lock,os.O_WRONLY|os.O_CREAT|os.O_EXCL)
    except FileExistsError:raise RuntimeRejected('Another or interrupted runtime installation exists. Close the app and inspect its optional-runtime recovery guide; no active lock was bypassed.') from None
    temporary=root/('.runtime-partial-'+entry['id']+'-'+token)
    try:
        with os.fdopen(fd,'w') as f:f.write(token);f.flush();os.fsync(f.fileno())
        with zipfile.ZipFile(archive) as z:
            entries=z.infolist();names=[i.filename for i in entries]
            if len(names)!=len(set(names)) or len(names)>MAX_FILES+1 or 'RUNTIME.json' not in names:
                raise RuntimeRejected('Invalid bounded runtime archive.')
            if z.getinfo('RUNTIME.json').file_size>32*1024*1024:raise RuntimeRejected('Runtime manifest exceeds its bound.')
            manifest=parse_manifest(z.read('RUNTIME.json'),entry,target)
            if set(names)!=set(manifest['files'])|{'RUNTIME.json'}:raise RuntimeRejected('Runtime archive differs from its approved manifest.')
            for info in entries:
                relative(info.filename)
                if info.is_dir() or stat.S_ISLNK(info.external_attr>>16):raise RuntimeRejected('Runtime archives cannot contain links or directory entries.')
                expected=len(z.read(info)) if info.filename=='RUNTIME.json' else manifest['files'][info.filename]['bytes']
                if info.file_size!=expected:raise RuntimeRejected('Runtime entry size does not match its manifest.')
            private_directory(temporary)
            for info in entries:
                destination=temporary/relative(info.filename)
                private_directory(destination.parent)
                with os.fdopen(open_private(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL),'wb') as out,z.open(info) as source:
                    copied=0;h=sha256()
                    while chunk:=source.read(1024*1024):
                        copied+=len(chunk)
                        if copied>info.file_size:raise RuntimeRejected('Runtime entry exceeded its bound.')
                        h.update(chunk);out.write(chunk)
                    out.flush();os.fsync(out.fileno())
                if info.filename!='RUNTIME.json':
                    record=manifest['files'][info.filename]
                    if copied!=record['bytes'] or h.hexdigest()!=record['sha256']:raise RuntimeRejected('Runtime entry failed its digest check.')
                    if os.name!='nt':destination.chmod(record['mode'])
            runner(temporary/relative(entry['python_relative']))
            receipt={'schema':'litrev.desktop.optional-install.v1','archive_sha256':entry['archive_sha256'],
                     'manifest_sha256':entry['manifest_sha256'],'target':target,'runtime_id':entry['id']}
            with os.fdopen(open_private(temporary/'INSTALL.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL),'w') as f:
                json.dump(receipt,f,sort_keys=True);f.flush();os.fsync(f.fileno())
            verify_slot(temporary,manifest,entry,target)
            publish_new(temporary,slot,directory=True);sync_directory(root)
        return verify_slot(slot,None,entry,target)
    except (zipfile.BadZipFile,KeyError,UnicodeError):raise RuntimeRejected('Runtime archive is malformed; Core remains available.') from None
    finally:
        if temporary.exists():shutil.rmtree(temporary)
        try:
            if lock.read_text()==token:lock.unlink()
        except OSError:pass


def main():
    def interrupted(*_):raise RuntimeRejected('Optional runtime installation interrupted; Core remains available.')
    signal.signal(signal.SIGTERM,interrupted)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['status','install'])
    parser.add_argument('--catalog',required=True,type=Path)
    parser.add_argument('--data-root',required=True,type=Path)
    parser.add_argument('--target',required=True,choices=['darwin-arm64','win32-x64'])
    parser.add_argument('--archive',type=Path)
    args=parser.parse_args()
    if args.operation=='install' and args.archive is None:parser.error('Install requires an exact local archive.')
    try:
        result=(install(args.archive,args.catalog,args.data_root,args.target) if args.operation=='install' else status(args.catalog,args.data_root,args.target))
        print(canonical(result))
    except (ValueError,OSError,RuntimeRejected):
        print(canonical({'state':'invalid','message':'Optional runtime installation/verification failed. Core remains available; use the runtime recovery guide.'}))
        raise SystemExit(1)

if __name__=='__main__':main()
