#!/usr/bin/env python3
"""Build an internal same-UI macOS arm64 bundle. No first-launch installers."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import plistlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.build_local_preview import clean_checkout, json_bytes, digest
from scripts.run_web import local_environment
from scripts.local_preview import reject_web_env_files

VERSION='0.3.0-desktop-preview.1'
APP='Literature Review Engine Desktop Preview.app'
EXECUTABLE='LiteratureReviewEngineDesktopPreview'

def run(args,**kwargs):
    subprocess.run([str(a) for a in args],check=True,**kwargs)


def verify_runtime(cache,spec):
    path=cache/spec['file']
    if not path.is_file() or path.is_symlink() or digest(path.read_bytes())!=spec['sha256']:
        raise ValueError('Supply the exact verified runtime archive: '+spec['file'])
    return path


def fetch(cache):
    lock=json.loads((ROOT/'apps/desktop/runtime-lock.json').read_text())
    cache.mkdir(parents=True,exist_ok=True)
    for name in ('electron','python','python_attribution'):
        spec=lock[name]; target=cache/spec['file']
        if not target.exists():
            temporary=target.with_suffix(target.suffix+'.partial')
            if temporary.exists():raise ValueError('A partial runtime download already exists; inspect it first')
            try:
                run(['/usr/bin/curl','--disable','--fail','--location','--proto','=https','--proto-redir','=https',spec['url'],'--output',temporary])
                if digest(temporary.read_bytes())!=spec['sha256']:raise ValueError('Runtime integrity mismatch; nothing was accepted')
                temporary.rename(target)
            finally:temporary.unlink(missing_ok=True)
        verify_runtime(cache,spec)
    return lock


def extract_source(archive,destination,expected):
    with zipfile.ZipFile(archive) as bundle:
        names=bundle.namelist(); prefix=names[0].split('/')[0]+'/'
        metadata=json.loads(bundle.read(prefix+'RELEASE.json'))
        manifest=json.loads(bundle.read(prefix+'MANIFEST.json'))
        if metadata['source_commit']!=expected or metadata['source_state']!='clean committed checkout' or metadata['product_track']!='A':
            raise ValueError('Desktop must reuse the exact clean Track A source package')
        for entry in bundle.infolist():
            relative=entry.filename.removeprefix(prefix); parsed=PurePosixPath(relative)
            if not relative or parsed.is_absolute() or '..' in parsed.parts or '\\' in relative or entry.is_dir():raise ValueError('Unsafe source archive')
            raw=bundle.read(entry)
            if relative!='MANIFEST.json' and manifest['files'].get(relative)!={'bytes':len(raw),'sha256':digest(raw)}:raise ValueError('Source manifest mismatch')
            target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    return metadata


def portable_web_build(web):
    """Replace only observed build-machine metadata with runtime-relative roots."""
    server=web/'apps/web/server.js'
    text=server.read_text()
    marker='const nextConfig = '
    start=text.index(marker)+len(marker)
    value,end=json.JSONDecoder().raw_decode(text[start:])
    for key in ('outputFileTracingRoot','repoRoot'):value.pop(key,None)
    if isinstance(value.get('turbopack'),dict):value['turbopack'].pop('root',None)
    replacement=json.dumps(value,separators=(',',':'))+"\nnextConfig.repoRoot = dir\nnextConfig.outputFileTracingRoot = path.resolve(dir, '../..')\nnextConfig.turbopack = {...nextConfig.turbopack, root:path.resolve(dir, '../..')}"
    server.write_text(text[:start]+replacement+text[start+end:])
    required=web/'apps/web/.next/required-server-files.json'
    value=json.loads(required.read_text())
    value['appDir']='.'
    for key in ('outputFileTracingRoot','repoRoot'):value['config'].pop(key,None)
    if isinstance(value['config'].get('turbopack'),dict):value['config']['turbopack'].pop('root',None)
    required.write_bytes(json_bytes(value))


def audit_generated_payload(resources,build_output):
    markers=[str(ROOT).encode(),(str(Path.home())+'/').encode(),str(build_output).encode()]
    for path in resources.rglob('*'):
        if path.is_file() and not path.is_symlink():
            raw=path.read_bytes()
            if any(marker in raw for marker in markers):
                raise ValueError('Generated bundle contains an owner/build-machine path: '+str(path.relative_to(resources)))


def build(args):
    if sys.platform!='darwin' or platform.machine()!='arm64':raise ValueError('This prototype builder is macOS arm64 only')
    reject_web_env_files(ROOT)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if args.expected_source_commit!=head:raise ValueError('Select the exact current reviewed source commit')
    clean_checkout(ROOT,head)
    output=args.output.absolute()
    if output.exists():raise ValueError('Use a fresh output directory; existing prototypes are never overwritten')
    lock=json.loads((ROOT/'apps/desktop/runtime-lock.json').read_text())
    electron=verify_runtime(args.runtime_cache,lock['electron']);python=verify_runtime(args.runtime_cache,lock['python'])
    attribution=verify_runtime(args.runtime_cache,lock['python_attribution'])
    node=Path(args.node).resolve();pnpm=Path(args.pnpm).resolve()
    if not node.is_file() or not pnpm.is_file():raise ValueError('Build-time Node and pnpm paths are required; they are not runtime dependencies')
    env=local_environment(os.environ,data_dir=output/'unused-build-state',api_port=48765,web_port=43000,node=node,isolated=True)
    env['LITREV_DESKTOP_STANDALONE']='1'
    run([pnpm,'build'],cwd=ROOT/'apps/web',env=env)
    standalone=ROOT/'apps/web/.next/standalone'
    if not (standalone/'apps/web/server.js').is_file():raise ValueError('The locked Next build did not produce its expected traced server')
    import importlib.util
    audit_spec=importlib.util.spec_from_file_location('desktop_source_audit', ROOT/'tests/local_distribution/audit_source_archive.py')
    audit_module=importlib.util.module_from_spec(audit_spec);audit_spec.loader.exec_module(audit_module)
    audit_module.audit(args.source_archive,head,ROOT)
    output.mkdir(parents=True)
    unpack=output/'electron-distribution';unpack.mkdir()
    run(['/usr/bin/ditto','-x','-k',electron,unpack])
    app=output/APP;shutil.move(str(unpack/'Electron.app'),app)
    resources=app/'Contents/Resources'
    default=resources/'default_app.asar';default.unlink(missing_ok=True)
    shell=resources/'app';shell.mkdir()
    for file in ('main.cjs','services.cjs','security.cjs','package.json','runtime-lock.json'):
        shutil.copy2(ROOT/'apps/desktop'/file,shell/file)
    engine=resources/'engine';engine.mkdir()
    source=extract_source(args.source_archive,engine,head)
    shutil.copy2(ROOT/'scripts/desktop_backend.py',engine/'scripts/desktop_backend.py')
    with tarfile.open(python,'r:gz') as archive:archive.extractall(resources,filter='data')
    with tempfile.TemporaryDirectory(prefix='litrev-python-notices-') as temporary:
        run(['/usr/bin/tar','-xf',attribution,'-C',temporary,'python/PYTHON.json','python/licenses'])
        upstream=Path(temporary)/'python';raw=(upstream/'PYTHON.json').read_bytes();metadata=json.loads(raw)
        if metadata['target_triple']!='aarch64-apple-darwin' or metadata['python_version']!='3.12.15':raise ValueError('Python notice metadata target mismatch')
        notices=resources/'python/UPSTREAM_LICENSES';shutil.copytree(upstream/'licenses',notices/'licenses')
        # Preserve rights/provenance without redistributing irrelevant upstream build-machine paths.
        projection={key:metadata[key] for key in ('version','target_triple','python_version','build_options','licenses','license_path')}
        projection.update(schema='litrev.python-runtime-license-provenance.v1',upstream_archive=lock['python_attribution'],upstream_metadata_sha256=digest(raw),
            extensions={name:[{key:part[key] for key in ('licenses','license_paths','license_public_domain','links') if key in part} for part in variants]
                        for name,variants in metadata['build_info']['extensions'].items()},
            retained_notice_files={path.name:digest(path.read_bytes()) for path in sorted((notices/'licenses').iterdir())},
            scope='All upstream notice files retained; unreferenced notices do not establish that a component is linked. Build-machine config/object-file fields omitted.')
        (notices/'PYTHON_LICENSE_PROVENANCE.json').write_bytes(json_bytes(projection))
    py=resources/'python/bin/python3.12'
    installenv={k:v for k,v in env.items() if k in {'HOME','PATH','TMPDIR','LANG','LC_ALL','LC_CTYPE'}}
    installenv.update(PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
    run([py,'-m','pip','install','--disable-pip-version-check','--no-input','--no-compile','-r',ROOT/'requirements-hosted.txt'],env=installenv)
    for unused in ('lib/python3.12/test','lib/python3.12/idlelib/idle_test','lib/python3.12/tkinter/test'):
        candidate=resources/'python'/unused
        if candidate.is_dir():shutil.rmtree(candidate)
    # These generated console scripts have non-relocatable build-prefix shebangs.
    # The application uses its packaged interpreter directly and does not expose them.
    for unused in ('idna','fastapi','uvicorn'):
        (resources/'python/bin'/unused).unlink(missing_ok=True)
    # Source distributions retain their notices; runtime distributions add their own.
    for file in unpack.iterdir():
        if file.is_file():shutil.copy2(file,resources/file.name)
    shutil.rmtree(unpack)
    shutil.copytree(standalone,resources/'web',symlinks=True,ignore=shutil.ignore_patterns('trace','*.map','*.tsbuildinfo'))
    target=resources/'web/apps/web'
    shutil.copytree(ROOT/'apps/web/.next/static',target/'.next/static',dirs_exist_ok=True)
    if (ROOT/'apps/web/public').is_dir():shutil.copytree(ROOT/'apps/web/public',target/'public',dirs_exist_ok=True)
    portable_web_build(resources/'web')
    # Do not include optional ML packages, source maps, workspace state or caches.
    for path in resources.rglob('__pycache__'):
        if path.is_dir():shutil.rmtree(path)
    # Electron derives packaged identity from its executable basename. Keep the
    # real check enabled and rename the product, rather than forcing its result.
    (app/'Contents/MacOS/Electron').rename(app/'Contents/MacOS'/EXECUTABLE)
    info=app/'Contents/Info.plist'
    value=plistlib.loads(info.read_bytes());value.update(CFBundleExecutable=EXECUTABLE,CFBundleName='Literature Review Engine Desktop Preview',CFBundleDisplayName='Literature Review Engine Desktop Preview',CFBundleIdentifier='org.hnt119.litrev.desktop-preview',CFBundleShortVersionString='0.3.0',CFBundleVersion='1',LitrevPrototypeVersion=VERSION,NSHighResolutionCapable=True)
    info.write_bytes(plistlib.dumps(value))
    notices='''# Desktop Preview runtime notices\n\nThe owner original engine code is MIT; LICENSE and THIRD_PARTY_NOTICES.md are in engine/. This internal macOS arm64 prototype bundles additional runtimes. Their terms remain separate.\n\nElectron45.0.0 includes Chromium/Node/V8 and upstream codecs; retain Resources/LICENSE and LICENSES.chromium.html and the framework license files. Python3.12.15+20261021 is the pinned python-build-standalone distribution; retain all Python licenses in python/ and the exact upstream binary-dependency license texts/provenance in python/UPSTREAM_LICENSES/. Installed Python/Next/React dependency license and dist-info files are retained. No model weights or ML stacks are included.\n\nThis bundle is ad-hoc signed for internal tests, not Developer ID signed or Apple-notarized. It is not approved for public distribution. A complete binary SBOM/license review and nested-code Developer ID signing/notarization must precede a trusted public desktop release. Do not disable operating-system protections.\n'''
    (resources/'DESKTOP_NOTICES.md').write_text(notices)
    metadata={'schema':'litrev.desktop-preview.release.v1','version':VERSION,'source_commit':head,'source_archive_sha256':digest(args.source_archive.read_bytes()),'source_snapshot_sha256':source['source_snapshot_sha256'],'platform':'macOS arm64','label':'Internal desktop prototype — not notarized','core_runtimes_bundled':True,'node_execution':'Electron utilityProcess; developer PATH is removed','python_execution':'Resources/python/bin/python3.12','runtimes':lock,'models_bundled':False,'optional_map_dependencies_bundled':False,'build_metadata_normalization':'Next repo/tracing/turbopack roots are derived from packaged server directory; required-server appDir is relative; unused pip console scripts omitted', 'signature':'ad-hoc; not Developer ID; not notarized','public_distribution':'not authorized','research_data':'external dedicated Desktop Preview root; no migration'}
    (resources/'DESKTOP_RELEASE.json').write_bytes(json_bytes(metadata))
    audit_generated_payload(resources,output)
    clean_checkout(ROOT,head)
    run(['/usr/bin/codesign','--force','--deep','--sign','-',app])
    run(['/usr/bin/codesign','--verify','--deep','--strict',app])
    manifest={}
    for path in sorted(app.rglob('*')):
        relative=path.relative_to(output).as_posix()
        if path.is_symlink():
            resolved=path.resolve()
            if not resolved.is_relative_to(app.resolve()):raise ValueError('A bundled symbolic link escapes the app')
            manifest[relative]={'symlink':os.readlink(path)}
        elif path.is_file():manifest[relative]={'bytes':path.stat().st_size,'sha256':digest(path.read_bytes())}
    manifest_path=output/f'lit-rev-engine-{VERSION}.manifest.json'
    manifest_path.write_bytes(json_bytes({'schema':'litrev.desktop-preview.manifest.v1','source_commit':head,'files':manifest}))
    archive=output/f'lit-rev-engine-{VERSION}-macos-arm64.zip'
    run(['/usr/bin/ditto','-c','-k','--keepParent','--sequesterRsrc',app,archive])
    checksums=output/f'lit-rev-engine-{VERSION}.SHA256SUMS'
    checksums.write_text(''.join(digest(p.read_bytes())+'  '+p.name+'\n' for p in (archive,manifest_path)))
    result={'source_commit':head,'app':str(app),'archive':str(archive),'zip_bytes':archive.stat().st_size,'installed_bytes':sum(p.stat().st_size for p in app.rglob('*') if p.is_file() and not p.is_symlink()),'archive_sha256':digest(archive.read_bytes()),'manifest_sha256':digest(manifest_path.read_bytes()),'checksums_sha256':digest(checksums.read_bytes()),'runtime_developer_tools_required':False,'signature':'ad-hoc','notarized':False}
    (output/'build-report.json').write_bytes(json_bytes(result))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-cache',required=True,type=Path)
    parser.add_argument('--fetch-runtimes',action='store_true',help='Explicit build-time runtime downloads only; never models')
    parser.add_argument('--source-archive',type=Path)
    parser.add_argument('--expected-source-commit')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--node')
    parser.add_argument('--pnpm')
    args=parser.parse_args()
    if args.fetch_runtimes:
        print(json.dumps(fetch(args.runtime_cache),indent=2));return
    if not all((args.source_archive,args.expected_source_commit,args.output,args.node,args.pnpm)):parser.error('Build requires exact reviewed source archive/commit, output, and explicit build tools')
    print(json.dumps(build(args),indent=2))

if __name__=='__main__':main()
