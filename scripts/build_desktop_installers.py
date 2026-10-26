#!/usr/bin/env python3
"""Build private native candidates from exact reviewed Track A inputs.

macOS delegates the existing verified same-UI assembler, then creates a DMG.
Windows cross-assembly never pretends to execute its target runtime. NSIS is a
build-time tool; no setup/download/developer runtime runs on an installed core.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import plistlib
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import build_desktop_preview as base
from scripts.build_local_preview import clean_checkout,digest,json_bytes
from scripts.desktop_notices import copy_web_dependency_notices


def product():
    value=json.loads((ROOT/'apps/desktop/product.json').read_text())
    if value.get('schema')!='litrev.desktop.product.v1' or value.get('data_name')!='LiteratureReviewEngineDesktop':
        raise ValueError('Use the reviewed native product identity and its separate data location.')
    return value


def fetch_runtime_inputs(cache,target):
    if target=='darwin-arm64':return base.fetch(cache)
    if target!='win32-x64':raise ValueError('Only reviewed arm64 Mac and x64 Windows targets exist.')
    lock=json.loads((ROOT/'apps/desktop/runtime-lock.win32-x64.json').read_text())
    cache.mkdir(parents=True,exist_ok=True)
    for kind in ('electron','python','python_attribution'):
        spec=lock[kind];path=cache/spec['file']
        if not path.exists():
            temporary=path.with_suffix(path.suffix+'.partial')
            if temporary.exists():raise ValueError('Inspect an existing partial download first.')
            try:
                base.run(['/usr/bin/curl','--disable','--fail','--location','--proto','=https','--proto-redir','=https',spec['url'],'--output',temporary])
                if digest(temporary.read_bytes())!=spec['sha256']:raise ValueError('Official runtime digest mismatch.')
                temporary.rename(path)
            finally:temporary.unlink(missing_ok=True)
        base.verify_runtime(cache,spec)
    return lock


def build_dmg(app,output,expected):
    if sys.platform!='darwin':raise ValueError('DMG creation requires the target macOS builder.')
    app=app.resolve();output=output.absolute()
    if output.exists():raise ValueError('Never overwrite an existing candidate artifact.')
    value=product();metadata=json.loads((app/'Contents/Resources/DESKTOP_RELEASE.json').read_text())
    info=plistlib.loads((app/'Contents/Info.plist').read_bytes())
    if app.name!=value['name']+'.app' or metadata['source_commit']!=expected or info['CFBundleIdentifier']!=value['app_id']:
        raise ValueError('The app does not match this exact reviewed native source/identity.')
    base.run(['/usr/bin/codesign','--verify','--deep','--strict',app])
    with tempfile.TemporaryDirectory(prefix='litrev-dmg-staging-') as temporary:
        stage=Path(temporary)
        base.run(['/usr/bin/ditto',app,stage/app.name])
        (stage/'Applications').symlink_to('/Applications',target_is_directory=True)
        (stage/'INSTALL.txt').write_text('Literature Review Engine — private desktop candidate\n\nDrag Literature Review Engine.app to Applications. Eject this disk image, then open the installed application. Core Python/Node runtimes are bundled; no Terminal or model download is needed. Research and profile state stay outside application files.\n\nThis candidate is not Developer ID signed/notarized. Do not disable Gatekeeper, remove quarantine or bypass an operating-system refusal. Original engine code is MIT; retained third-party notices and license/source review limits remain in the application.\n')
        base.run(['/usr/bin/hdiutil','create','-quiet','-format','UDZO','-fs','HFS+','-volname',value['name'],'-srcfolder',stage,output])
    return {'file':output.name,'bytes':output.stat().st_size,'sha256':digest(output.read_bytes()),'signature':'private candidate; inspect app signature and notarization separately'}


def safe_zip_extract(archive,directory):
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.infolist():
            p=Path(entry.filename)
            if p.is_absolute() or '..' in p.parts or '\\' in entry.filename or ((entry.external_attr>>16)&0o170000)==0o120000:
                raise ValueError('Unsafe runtime ZIP member.')
        bundle.extractall(directory)


def require_windows_pe(path):
    data=path.read_bytes()
    if data[:2]!=b'MZ' or len(data)<64:raise ValueError('Missing Windows PE runtime: '+path.name)
    offset=struct.unpack_from('<I',data,0x3c)[0]
    if data[offset:offset+4]!=b'PE\0\0' or struct.unpack_from('<H',data,offset+4)[0]!=0x8664:
        raise ValueError('The application payload must contain an AMD64 PE runtime: '+path.name)


def windows_notices(resources,cache,lock):
    archive=base.verify_runtime(cache,lock['python_attribution'])
    with tempfile.TemporaryDirectory(prefix='litrev-win-python-notices-') as temporary:
        base.run(['/usr/bin/tar','-xf',archive,'-C',temporary,'python/PYTHON.json','python/licenses'])
        source=Path(temporary)/'python';metadata=json.loads((source/'PYTHON.json').read_text())
        if metadata['target_triple']!='x86_64-pc-windows-msvc' or metadata['python_version']!='3.12.15':raise ValueError('Wrong Windows Python notice target.')
        target=resources/'python/UPSTREAM_LICENSES';shutil.copytree(source/'licenses',target/'licenses')
        retained={p.name:digest(p.read_bytes()) for p in (target/'licenses').iterdir()}
        projection={k:metadata[k] for k in ('version','target_triple','python_version','build_options','licenses','license_path')}
        projection.update(upstream_archive=lock['python_attribution'],retained_notice_files=retained,
            extensions={name:[{key:part[key] for key in ('licenses','license_paths','license_public_domain','links') if key in part} for part in variants] for name,variants in metadata['build_info']['extensions'].items()})
        (target/'PYTHON_LICENSE_PROVENANCE.json').write_bytes(json_bytes(projection))


def materialize_verified_web(web):
    """Windows setup cannot depend on privileged POSIX symlink creation."""
    base.web_inventory(web)
    destination=web.with_name(web.name+'-materialized')
    if destination.exists():raise ValueError('Unexpected materialized output already exists.')
    root=web.resolve();count=0;total=0
    def copy(source,target,ancestors):
        nonlocal count,total
        actual=source.resolve()
        if not actual.is_relative_to(root):raise ValueError('A Windows web alias escapes its verified closure.')
        if source.is_dir():
            if actual in ancestors:raise ValueError('Cyclic web directory alias is unsupported.')
            target.mkdir()
            for child in sorted(source.iterdir()):copy(child,target/child.name,ancestors|{actual})
        elif source.is_file():
            count+=1;total+=source.stat().st_size
            if count>150000 or total>3*1024**3:raise ValueError('Windows web materialization exceeds its bound.')
            shutil.copy2(source,target,follow_symlinks=True)
        else:raise ValueError('Unexpected Windows web input type.')
    copy(web,destination,set())
    shutil.rmtree(web);destination.rename(web)
    return {'files':count,'bytes':total,'symlinks_materialized':True}


def assemble_windows(args):
    value=product();head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if args.expected_source_commit!=head:raise ValueError('Build the exact reviewed clean source commit.')
    clean_checkout(ROOT,head);base.reject_web_env_files(ROOT)
    out=args.output.absolute()
    if out.exists():raise ValueError('Use a new candidate output directory.')
    lock=json.loads((ROOT/'apps/desktop/runtime-lock.win32-x64.json').read_text())
    electron=base.verify_runtime(args.runtime_cache,lock['electron']);python=base.verify_runtime(args.runtime_cache,lock['python'])
    standalone=args.web_standalone.resolve()
    if not (standalone/'apps/web/server.js').is_file():raise ValueError('Supply the production standalone web build from this exact clean source.')
    # Recheck Next's own build revision through our external review binding.
    binding=json.loads(args.web_build_binding.read_text())
    base.verify_web_build(binding,standalone,ROOT/'apps/web/.next/static',ROOT/'apps/web/public',head)
    import importlib.util
    spec=importlib.util.spec_from_file_location('desktop_windows_source_audit',ROOT/'tests/local_distribution/audit_source_archive.py')
    audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
    audit.audit(args.source_archive,head,ROOT)
    out.mkdir(parents=True);app=out/'windows-x64-application';app.mkdir()
    safe_zip_extract(electron,app)
    (app/'electron.exe').rename(app/'LiteratureReviewEngine.exe');require_windows_pe(app/'LiteratureReviewEngine.exe')
    resources=app/'resources';(resources/'default_app.asar').unlink(missing_ok=True);shell=resources/'app';shell.mkdir()
    for name in ('main.cjs','services.cjs','security.cjs','native-exports.cjs','no-disk-cache.cjs','product.json','optional-runtime.cjs','optional-runtime-catalog.json'):
        shutil.copy2(ROOT/'apps/desktop'/name,shell/name)
    pkg=json.loads((ROOT/'apps/desktop/package.json').read_text());pkg.update(name='literature-review-engine',version=value['version'],description='Local research application');(shell/'package.json').write_bytes(json_bytes(pkg))
    engine=resources/'engine';engine.mkdir();source=base.extract_source(args.source_archive,engine,head)
    for name in ('desktop_backend.py','desktop_native_export.py','install_desktop_optional_runtime.py','desktop_uninstall.py','desktop_install_root.py','desktop_runtime_supervisor.py'):shutil.copy2(ROOT/'scripts'/name,engine/'scripts'/name)
    with tarfile.open(python,'r:gz') as archive:archive.extractall(resources,filter='data')
    # Foreign target wheels are installed at BUILD time only. Marker evaluation
    # is host-based, so the reviewed Windows pywin32 prerequisite is explicit.
    command=[args.build_python,'-m','pip','install','--disable-pip-version-check','--no-input','--no-compile','--only-binary=:all:','--platform','win_amd64','--python-version','3.12','--implementation','cp','--abi','cp312','--target',resources/'python/Lib/site-packages','--report',out/'windows-wheel-install-report.json','-r',ROOT/'requirements-hosted.txt','pywin32==312']
    env={k:v for k,v in os.environ.items() if k in ('HOME','PATH','TMPDIR','LANG','LC_ALL','LC_CTYPE','SSL_CERT_FILE','PIP_CERT')};env.update(PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
    base.run(command,env=env)
    console=resources/'python/Lib/site-packages/bin'
    if console.exists():
        if {file.name for file in console.iterdir()}-{'fastapi','uvicorn','idna'}:raise ValueError('Unexpected cross-target console entry point.')
        shutil.rmtree(console)
    windows_notices(resources,args.runtime_cache,lock)
    require_windows_pe(resources/'python/python.exe')
    base.copy_standalone(standalone,resources/'web');web=resources/'web/apps/web'
    shutil.copytree(ROOT/'apps/web/.next/static',web/'.next/static',dirs_exist_ok=True)
    if (ROOT/'apps/web/public').is_dir():shutil.copytree(ROOT/'apps/web/public',web/'public',dirs_exist_ok=True)
    base.portable_web_build(resources/'web',unoptimized_images=True)
    omitted=base.prune_unused_image_optimizer(resources/'web')
    boundary=base.replace_client_boundary(resources/'web')
    materialized=materialize_verified_web(resources/'web')
    # No foreign native code may hide in a cross-built JS server tree.
    for file in (resources/'web').rglob('*.node'):require_windows_pe(file)
    notices=copy_web_dependency_notices(resources/'web',ROOT/'apps/web/node_modules',resources/'WEB_DEPENDENCY_NOTICES')
    metadata={'schema':'litrev.desktop-distribution.release.v1','version':value['version'],'source_commit':head,'source_archive_sha256':digest(args.source_archive.read_bytes()),'source_snapshot_sha256':source['source_snapshot_sha256'],'target':'win32-x64','platform':'Windows 11 x64; execution NOT_RUN','core_runtimes_bundled':True,'runtimes':lock,'node_execution':'Electron utilityProcess bundled Node','python_execution':'resources/python/python.exe','signature':'unsigned private candidate; no Authenticode credentials','installed_execution':'NOT_RUN','public_distribution':'not qualified or authorized','data_root':'LOCALAPPDATA/LiteratureReviewEngineDesktop; separate from browser beta and Preview','web_dependency_notice_inventory':{'packages':len(notices['packages']),'notice_files':notices['unique_notice_files'],'missing_notice_sources':notices['missing_notice_sources']},'unused_image_optimizer':{'disabled':True,'omitted_files':omitted},'project_client_boundary':boundary,'web_build_binding':binding,'windows_web_materialization':materialized}
    sdk=args.nsis_dir.resolve()
    notices_dir=resources/'INSTALLER_NOTICES';notices_dir.mkdir()
    shutil.copy2(sdk/'COPYING',notices_dir/'NSIS-3.13-COPYING.txt')
    tool=json.loads((ROOT/'apps/desktop/installer-tool-lock.json').read_text())
    (notices_dir/'PROVENANCE.json').write_bytes(json_bytes({'schema':'litrev.desktop.installer-notices.v1','tool':tool,'runtime_modules':['NSIS Unicode zlib installer stub','Modern UI 2','System plugin','nsExec plugin'],'compression':'zlib; no LZMA module selected','notice_sha256':digest((sdk/'COPYING').read_bytes()),'scope':'Exact NSIS license text retained; component/source/signing review remains explicit, not inferred legal clearance.'}))
    metadata['installer_tool']=tool
    metadata['installer_compression']='zlib'
    (resources/'DESKTOP_RELEASE.json').write_bytes(json_bytes(metadata))
    (resources/'DESKTOP_NOTICES.md').write_text('Private Windows x64 candidate. Original engine MIT; retain engine/LICENSE, engine/THIRD_PARTY_NOTICES.md, Electron LICENSE and LICENSES.chromium.html, Python runtime licenses/UPSTREAM_LICENSES, installed package licenses/dist-info, WEB_DEPENDENCY_NOTICES. Complete native component/source obligations and signing remain separate gates; this is not legal clearance. No model weights are bundled.\n')
    base.audit_generated_payload(resources,out)
    files={path.relative_to(app).as_posix():{'bytes':path.stat().st_size,'sha256':digest(path.read_bytes())} for path in sorted(app.rglob('*')) if path.is_file() and not path.is_symlink()}
    if any(path.is_symlink() for path in app.rglob('*')):raise ValueError('Windows payload cannot depend on symbolic links.')
    installed={'schema':'litrev.desktop.installed-files.v1','app_id':value['app_id'],'version':value['version'],'source_commit':head,'files':files}
    (app/'INSTALLATION.json').write_bytes(json_bytes(installed))
    clean_checkout(ROOT,head)
    return app,metadata


def make_windows_installer(payload,output,makensis,nsis_dir):
    if output.exists():raise ValueError('Never overwrite a candidate installer.')
    value=product();require_windows_pe(payload/'LiteratureReviewEngine.exe')
    env=dict(os.environ);env['NSISDIR']=str(nsis_dir.resolve())
    base.run([makensis,'-V2','-NOCD','-DPRODUCT_VERSION='+value['version'],'-DPAYLOAD_MANIFEST_SHA='+digest((payload/'INSTALLATION.json').read_bytes()),'-DPAYLOAD='+str(payload.resolve()),'-DOUTPUT_FILE='+str(output.absolute()),ROOT/'apps/desktop/installer.nsi'],env=env)
    raw=output.read_bytes()
    if raw[:2]!=b'MZ' or b'Nullsoft' not in raw[:4096]:
        # NSIS metadata can be compressed; require at least a real PE and the
        # compiler's completed output, not a renamed ZIP/source archive.
        if raw[:2]!=b'MZ':raise ValueError('NSIS did not produce a Windows installer.')
    return {'file':output.name,'bytes':len(raw),'sha256':digest(raw),'target':'Windows 11 x64','execution':'NOT_RUN','signature':'unsigned private candidate'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--target',choices=['darwin-arm64','win32-x64'],required=True)
    p.add_argument('--runtime-cache',type=Path);p.add_argument('--fetch-runtimes',action='store_true')
    p.add_argument('--source-archive',type=Path);p.add_argument('--expected-source-commit');p.add_argument('--output',type=Path)
    p.add_argument('--node');p.add_argument('--pnpm');p.add_argument('--build-python',default=sys.executable)
    p.add_argument('--web-standalone',type=Path);p.add_argument('--web-build-binding',type=Path)
    p.add_argument('--makensis',type=Path);p.add_argument('--nsis-dir',type=Path)
    p.add_argument('--dmg-from-app',type=Path)
    a=p.parse_args()
    if a.fetch_runtimes:
        if a.runtime_cache is None:p.error('Supply an external --runtime-cache')
        print(json.dumps(fetch_runtime_inputs(a.runtime_cache,a.target),indent=2));return
    if a.dmg_from_app:
        if not a.output or not a.expected_source_commit:p.error('DMG requires output and exact source SHA')
        print(json.dumps(build_dmg(a.dmg_from_app,a.output,a.expected_source_commit),indent=2));return
    if not all((a.runtime_cache,a.source_archive,a.expected_source_commit,a.output)):p.error('Build requires verified runtimes, exact clean source package/SHA and fresh output')
    if a.target=='darwin-arm64':
        if not a.node or not a.pnpm:p.error('Supply reviewed build-time Node and pnpm')
        a.desktop_distribution=True;result=base.build(a)
        app=Path(result['app']);dmg=a.output/('lit-rev-engine-'+product()['version']+'-macos-arm64.dmg')
        result['dmg']=build_dmg(app,dmg,a.expected_source_commit)
    else:
        if not all((a.web_standalone,a.web_build_binding,a.makensis,a.nsis_dir)):p.error('Windows requires source-bound standalone server and reviewed NSIS SDK')
        app,metadata=assemble_windows(a)
        exe=a.output/('Literature Review Engine Setup '+product()['version']+'.exe')
        result={'source_commit':a.expected_source_commit,'application':str(app),'installer':make_windows_installer(app,exe,a.makensis,a.nsis_dir),'metadata':metadata}
    (a.output/'installer-build-report.json').write_bytes(json_bytes(result));print(json.dumps(result,indent=2))

if __name__=='__main__':main()
