#!/usr/bin/env python3
"""Prepare a reviewed optional native runtime ZIP at BUILD time, never on first launch.

The input is a complete target Python prefix with frozen core/neural dependencies
already installed by the packager. No pip, model weights, cloud calls or user
research data are collected here. An application must pin the emitted binding
before signing; copying an arbitrary capsule into a cache grants no authority.
"""
from pathlib import Path
import argparse
from email.parser import BytesParser
from hashlib import sha256
import json
import os
import re
import stat
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.install_desktop_optional_runtime import (MANIFEST,MAX_FILES,MAX_UNPACKED,EXPECTED,ID,
    canonical,digest_file,relative,self_test)


def inventory(prefix):
    entries={};folded=set();versions={}
    for path in sorted(prefix.rglob('*')):
        if path.is_dir():continue
        name=path.relative_to(prefix).as_posix()
        if (name.startswith('bin/') and Path(name).name not in {'python','python3','python3.12'}) or name.startswith('Scripts/'):
            continue
        if any(x in {'__pycache__','.git','.pytest_cache','.mypy_cache'} for x in path.relative_to(prefix).parts) or path.suffix in {'.pyc','.pyo'}:continue
        if path.suffix in {'.safetensors','.ckpt','.gguf','.sqlite','.sqlite3'} or path.name in {'.env','direct_url.json'}:
            raise ValueError('Runtime prefix contains a weight, private state or machine-specific install record; prepare a clean runtime first.')
        source=path.resolve(strict=True)
        if not source.is_relative_to(prefix):raise ValueError('Runtime input links must stay within the prepared prefix.')
        if not source.is_file():raise ValueError('Runtime prefix must contain only ordinary files.')
        relative(name)
        if name.casefold() in folded:raise ValueError('Runtime prefix has case-colliding platform paths.')
        folded.add(name.casefold())
        entry={'bytes':source.stat().st_size,'sha256':digest_file(source),'mode':0o500 if os.access(source,os.X_OK) else 0o400}
        entries['python/'+name]=entry
        if path.name=='METADATA' and path.parent.name.endswith('.dist-info') and path.parent.parent.name.lower()=='site-packages':
            meta=BytesParser().parsebytes(source.read_bytes());package=re.sub(r'[-_.]+','-',meta['Name'].lower())
            if package in versions and versions[package]!=meta['Version']:raise ValueError('Runtime has conflicting distribution versions.')
            versions[package]=meta['Version']
    if not 1<=len(entries)<=MAX_FILES or sum(x['bytes'] for x in entries.values())>MAX_UNPACKED:raise ValueError('Runtime prefix exceeds capsule bounds.')
    for package,version in EXPECTED.items():
        if versions.get(package,'').split('+',1)[0]!=version:raise ValueError('Runtime lacks exact frozen dependency: '+package+'=='+version)
    return entries,versions


def build(prefix,output,target,runtime_id,*,runner=self_test):
    prefix=Path(prefix).absolute()
    if prefix.is_symlink() or prefix.resolve()!=prefix:raise ValueError('Use a resolved clean prepared Python prefix.')
    if not ID.fullmatch(runtime_id):raise ValueError('Use a bounded path-safe runtime ID.')
    if target not in {'darwin-arm64','win32-x64'}:raise ValueError('Unsupported runtime target.')
    if (sys.platform,os.uname().machine if hasattr(os,'uname') else '') not in {('darwin','arm64')} and target=='darwin-arm64':
        raise ValueError('Build and execute the macOS optional runtime on macOS arm64.')
    if target=='win32-x64' and (sys.platform!='win32' or os.environ.get('PROCESSOR_ARCHITECTURE','').lower() not in {'amd64','x86_64'}):
        raise ValueError('Windows x64 capsules require an actual Windows x64 build/check.')
    python_relative='python/python.exe' if target=='win32-x64' else 'python/bin/python3.12'
    interpreter=prefix/relative(python_relative.removeprefix('python/'))
    if not interpreter.is_file():raise ValueError('Prepared runtime lacks its platform interpreter.')
    runner(interpreter)
    files,versions=inventory(prefix)
    recipe_files=['scripts/build_desktop_optional_runtime.py','scripts/install_desktop_optional_runtime.py','scripts/desktop_sbom.py',
                  'requirements-web.txt','requirements-web-lock.txt','requirements-retrieval.txt','requirements-map-lock.txt','apps/desktop/runtime-lock.json']
    recipe={name:digest_file(ROOT/name) for name in recipe_files}
    manifest={'recipe_file_sha256':recipe,'schema':MANIFEST,'id':runtime_id,'target':target,'python_relative':python_relative,
              'distributions':versions,'files':files,'model_weights_bundled':False,
              'source_review':'Required separately; package metadata and notices do not establish native distribution clearance.'}
    raw=(canonical(manifest)+'\n').encode()
    output=Path(output).absolute()
    if output.exists() or output.is_symlink():raise ValueError('Use a fresh capsule path; existing artifacts are never overwritten.')
    output.parent.mkdir(parents=True,exist_ok=True)
    try:
        with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            def add(name,content,mode):
                info=zipfile.ZipInfo(name,(2026,1,1,0,0,0));info.create_system=3;info.external_attr=(stat.S_IFREG|mode)<<16;info.compress_type=zipfile.ZIP_DEFLATED
                z.writestr(info,content)
            add('RUNTIME.json',raw,0o400)
            for name,entry in files.items():
                source=prefix/relative(name.removeprefix('python/'));content=source.read_bytes()
                if len(content)!=entry['bytes'] or sha256(content).hexdigest()!=entry['sha256']:raise ValueError('Runtime input changed during capsule build.')
                add(name,content,entry['mode'])
    except BaseException:
        output.unlink(missing_ok=True);raise
    binding={'availability':'available','id':runtime_id,'format':'zip','archive_sha256':digest_file(output),
             'archive_bytes':output.stat().st_size,'manifest_sha256':sha256(raw).hexdigest(),'python_relative':python_relative}
    sidecar=output.with_suffix(output.suffix+'.binding.json')
    if sidecar.exists():raise ValueError('Binding sidecar already exists; retain existing artifacts.')
    sidecar.write_text(json.dumps(binding,indent=2,sort_keys=True)+'\n')
    return binding


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--python-prefix',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--target',choices=['darwin-arm64','win32-x64'],required=True);p.add_argument('--runtime-id',required=True);a=p.parse_args()
    value=build(a.python_prefix,a.output,a.target,a.runtime_id);print(json.dumps(value,sort_keys=True))
if __name__=='__main__':main()
