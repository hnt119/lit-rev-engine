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
from scripts.desktop_notices import copy_web_dependency_notices
from scripts.desktop_native_inventory import copy_native_source_evidence

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


def copy_standalone(source,destination):
    shutil.copytree(source,destination,symlinks=True,ignore=shutil.ignore_patterns('*.map','*.tsbuildinfo'))


def portable_web_build(web, *, unoptimized_images=False):
    """Replace only observed build-machine metadata with runtime-relative roots."""
    server=web/'apps/web/server.js'
    text=server.read_text()
    marker='const nextConfig = '
    start=text.index(marker)+len(marker)
    value,end=json.JSONDecoder().raw_decode(text[start:])
    if unoptimized_images:value['images']={**value.get('images',{}),'unoptimized':True}
    for key in ('outputFileTracingRoot','repoRoot'):value.pop(key,None)
    if isinstance(value.get('turbopack'),dict):value['turbopack'].pop('root',None)
    replacement=json.dumps(value,separators=(',',':'))+"\nnextConfig.repoRoot = dir\nnextConfig.outputFileTracingRoot = path.resolve(dir, '../..')\nnextConfig.turbopack = {...nextConfig.turbopack, root:path.resolve(dir, '../..')}\nnextConfig.cacheHandler = path.resolve(dir, '../../../app/no-disk-cache.cjs')\nnextConfig.images = {...nextConfig.images, customCacheHandler:true}"
    server.write_text(text[:start]+replacement+text[start+end:])
    required=web/'apps/web/.next/required-server-files.json'
    value=json.loads(required.read_text())
    value['appDir']='.'
    if unoptimized_images:value['config']['images']={**value['config'].get('images',{}),'unoptimized':True}
    for key in ('outputFileTracingRoot','repoRoot'):value['config'].pop(key,None)
    if isinstance(value['config'].get('turbopack'),dict):value['config']['turbopack'].pop('root',None)
    required.write_bytes(json_bytes(value))


def prune_unused_image_optimizer(web):
    """Desktop-only unused sharp/libvips payload; Next image route is disabled."""
    omitted={}
    candidates=[]
    for metadata in web.rglob('package.json'):
        if metadata.is_symlink():continue
        try:value=json.loads(metadata.read_text())
        except (ValueError,UnicodeError):continue
        name=value.get('name','')
        if name=='sharp' or name.startswith('@img/sharp-'):
            candidates.append(metadata.parent)
    for directory in sorted(set(candidates),key=lambda p:len(p.parts),reverse=True):
        if not directory.exists():continue
        for path in directory.rglob('*'):
            if path.is_file() and not path.is_symlink():omitted[path.relative_to(web).as_posix()]=digest(path.read_bytes())
        shutil.rmtree(directory)
    # Remove only now-dangling links whose destinations were one of these roots.
    removed=[str(p.absolute()) for p in candidates]
    for path in web.rglob('*'):
        if path.is_symlink() and not path.exists() and any(str(path.resolve(strict=False)).startswith(p+os.sep) or str(path.resolve(strict=False))==p for p in removed):path.unlink()
    return omitted


def replace_client_boundary(web):
    """Replace all traced upstream marker packages with independent own code.

    Installed dependencies and source bundles remain unchanged. Retain exact
    removed/replacement hashes; this does not resolve upstream notice rights.
    """
    source=ROOT/'apps/desktop/client-boundary'
    expected={'package.json','index.js','error.js','LICENSE'}
    if {p.name for p in source.iterdir()}!=expected:raise ValueError('Unexpected project client-boundary input.')
    package=json.loads((source/'package.json').read_text())
    if package.get('name')!='@hnt119/litrev-client-boundary' or package.get('version')!='0.1.0' or list(package.get('exports',{}).get('.',{}))!=['react-server','default']:
        raise ValueError('Use the reviewed fail-closed project boundary contract.')
    reviewed=json.loads((ROOT/'apps/desktop/client-boundary-input.json').read_text())
    if reviewed.get('schema')!='litrev.desktop.client-boundary-input.v1' or set(reviewed.get('files',{}))!={'package.json','index.js','error.js'}:
        raise ValueError('The reviewed upstream client-boundary input is incomplete.')
    def verify_input(directory,allowed):
        if directory.is_symlink() or not directory.is_dir():raise ValueError('Unknown links in client-only removal input.')
        members=list(directory.rglob('*'))
        names={path.relative_to(directory).as_posix() for path in members}
        if any(path.is_symlink() or not path.is_file() for path in members) or names not in allowed:
            raise ValueError('Unknown files or links in client-only removal input.')
        for path in members:
            if reviewed['files'][path.relative_to(directory).as_posix()]!={'bytes':path.stat().st_size,'sha256':digest(path.read_bytes())}:
                raise ValueError('client-only removal input differs from reviewed exact bytes.')
        return members
    # Next's production trace legitimately omits the unused react-server guard.
    # Accept that exact projection only after proving all three installed inputs
    # against the same pin, including error.js that was not copied into the trace.
    installed=ROOT/'apps/web/node_modules/.pnpm/client-only@0.0.1/node_modules/client-only'
    upstream=verify_input(installed,[set(reviewed['files'])])
    upstream_hashes={path.name:digest(path.read_bytes()) for path in upstream}
    for directory in web.rglob('client-only'):
        if not directory.is_symlink() and directory.is_dir() and not (directory/'package.json').is_file():
            raise ValueError('Missing package metadata in client-only removal input.')
    records=[]
    for metadata in list(web.rglob('package.json')):
        if metadata.is_symlink():continue
        try:value=json.loads(metadata.read_text())
        except (ValueError,UnicodeError):continue
        if value.get('name')!='client-only':continue
        if value.get('version')!='0.0.1':raise ValueError('An unreviewed client-only dependency is present.')
        directory=metadata.parent
        members=verify_input(directory,[set(reviewed['files']),{'package.json','index.js'}])
        removed={path.relative_to(web).as_posix():digest(path.read_bytes()) for path in directory.rglob('*') if path.is_file() and not path.is_symlink()}
        shutil.rmtree(directory);shutil.copytree(source,directory)
        replacement={path.relative_to(web).as_posix():digest(path.read_bytes()) for path in directory.rglob('*') if path.is_file()}
        records.append({'alias_directory':directory.relative_to(web).as_posix(),'original_package':'client-only@0.0.1','verified_full_upstream_files':upstream_hashes,'traced_projection':sorted(path.name for path in members),'removed_files':removed,'replacement_package':'@hnt119/litrev-client-boundary@0.1.0','replacement_files':replacement,'scope':'Independent project implementation; no claim of an upstream copyright/license resolution'})
    return records


def web_inventory(directory):
    directory=Path(directory)
    if not directory.exists():return {}
    if directory.is_symlink() or not directory.is_dir():raise ValueError('Web input roots must be ordinary directories.')
    root=directory.resolve();result={}
    for path in sorted(directory.rglob('*')):
        relative=path.relative_to(directory).as_posix()
        if path.is_symlink():
            target=os.readlink(path)
            if os.path.isabs(target) or not path.resolve().is_relative_to(root) or not path.exists():
                raise ValueError('Web symlink escapes its verified payload closure.')
            result[relative]={'symlink':target}
        elif path.is_file():result[relative]={'bytes':path.stat().st_size,'sha256':digest(path.read_bytes())}
        elif not path.is_dir():raise ValueError('Unexpected web input file type.')
    return result


def web_build_binding(standalone,static,public,source_commit):
    return {'schema':'litrev.desktop.web-build-binding.v1','source_commit':source_commit,
        'standalone':web_inventory(standalone),'static':web_inventory(static),'public':web_inventory(public),
        'scope':'Complete clean production build input inventories before desktop transforms; not remote build attestation.'}


def verify_web_build(binding,standalone,static,public,source_commit):
    wanted=web_build_binding(standalone,static,public,source_commit)
    if binding!=wanted:raise ValueError('Standalone/static/public bytes or symlinks do not match the exact source-bound build inventory.')
    return wanted


def audit_generated_payload(resources,build_output):
    markers=[str(ROOT).encode(),(str(Path.home())+'/').encode(),str(build_output).encode()]
    for path in resources.rglob('*'):
        if path.is_file() and not path.is_symlink():
            raw=path.read_bytes()
            if any(marker in raw for marker in markers):
                raise ValueError('Generated bundle contains an owner/build-machine path: '+str(path.relative_to(resources)))



def native_build_number(product):
    """Apple numeric bundle identity is separate from the readable beta label."""
    value=product.get('build_number')
    if type(value) is not int or not 1<=value<=9999:
        raise ValueError('Native product requires a reviewed positive four-digit-or-shorter numeric build number.')
    return str(value)


def build(args):
    if sys.platform!='darwin' or platform.machine()!='arm64':raise ValueError('This prototype builder is macOS arm64 only')
    native=getattr(args,'desktop_distribution',False)
    product=json.loads((ROOT/'apps/desktop/product.json').read_text()) if native else None
    version=product['version'] if native else VERSION
    app_name=product['name']+'.app' if native else APP
    executable='LiteratureReviewEngine' if native else EXECUTABLE
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
    (output/'web-build-binding.json').write_bytes(json_bytes(web_build_binding(standalone,ROOT/'apps/web/.next/static',ROOT/'apps/web/public',head)))
    unpack=output/'electron-distribution';unpack.mkdir()
    run(['/usr/bin/ditto','-x','-k',electron,unpack])
    app=output/app_name;shutil.move(str(unpack/'Electron.app'),app)
    resources=app/'Contents/Resources'
    default=resources/'default_app.asar';default.unlink(missing_ok=True)
    shell=resources/'app';shell.mkdir()
    for file in ('main.cjs','services.cjs','security.cjs','native-exports.cjs','no-disk-cache.cjs','package.json','runtime-lock.json'):
        shutil.copy2(ROOT/'apps/desktop'/file,shell/file)
    if native:
        for name in ('product.json','optional-runtime.cjs','optional-runtime-catalog.json'):
            shutil.copy2(ROOT/'apps/desktop'/name,shell/name)
        package=json.loads((shell/'package.json').read_text());package.update(name='literature-review-engine',version=version,description='Local research application');(shell/'package.json').write_bytes(json_bytes(package))
    engine=resources/'engine';engine.mkdir()
    source=extract_source(args.source_archive,engine,head)
    shutil.copy2(ROOT/'scripts/desktop_backend.py',engine/'scripts/desktop_backend.py')
    shutil.copy2(ROOT/'scripts/desktop_native_export.py',engine/'scripts/desktop_native_export.py')
    if native:
        for helper in ('install_desktop_optional_runtime.py','desktop_runtime_supervisor.py'):shutil.copy2(ROOT/'scripts'/helper,engine/'scripts'/helper)
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
    copy_standalone(standalone,resources/'web')
    target=resources/'web/apps/web'
    shutil.copytree(ROOT/'apps/web/.next/static',target/'.next/static',dirs_exist_ok=True)
    if (ROOT/'apps/web/public').is_dir():shutil.copytree(ROOT/'apps/web/public',target/'public',dirs_exist_ok=True)
    portable_web_build(resources/'web',unoptimized_images=native)
    omitted=prune_unused_image_optimizer(resources/'web') if native else {}
    boundary=replace_client_boundary(resources/'web') if native else []
    web_notices=copy_web_dependency_notices(resources/'web',ROOT/'apps/web/node_modules',resources/'WEB_DEPENDENCY_NOTICES')
    native_source_evidence=copy_native_source_evidence(resources/'NATIVE_DEPENDENCY_NOTICES') if native else None
    # Do not include optional ML packages, source maps, workspace state or caches.
    for path in resources.rglob('__pycache__'):
        if path.is_dir():shutil.rmtree(path)
    # Electron derives packaged identity from its executable basename. Keep the
    # real check enabled and rename the product, rather than forcing its result.
    (app/'Contents/MacOS/Electron').rename(app/'Contents/MacOS'/executable)
    info=app/'Contents/Info.plist'
    value=plistlib.loads(info.read_bytes());value.update(CFBundleExecutable=executable,CFBundleName=product['name'] if native else 'Literature Review Engine Desktop Preview',CFBundleDisplayName=product['name'] if native else 'Literature Review Engine Desktop Preview',CFBundleIdentifier=product['app_id'] if native else 'org.hnt119.litrev.desktop-preview',CFBundleShortVersionString='0.3.0',CFBundleVersion=native_build_number(product) if native else '1',LitrevPrototypeVersion=version,NSHighResolutionCapable=True)
    info.write_bytes(plistlib.dumps(value))
    notices='''# Desktop Preview runtime notices\n\nThe owner original engine code is MIT; LICENSE and THIRD_PARTY_NOTICES.md are in engine/. This internal macOS arm64 prototype bundles additional runtimes. Their terms remain separate.\n\nElectron45.0.0 includes Chromium/Node/V8 and upstream codecs; retain Resources/LICENSE and LICENSES.chromium.html and the framework license files. Python3.12.15+20261021 is the pinned python-build-standalone distribution; retain all Python licenses in python/ and the exact upstream binary-dependency license texts/provenance in python/UPSTREAM_LICENSES/. Installed Python package license and dist-info files are retained. Exact locked Next/React/vendored/native web notices are preserved in WEB_DEPENDENCY_NOTICES/; its inventory explicitly records missing upstream full-notice files and source pointers. This is not legal clearance or a complete binary SBOM. No model weights or ML stacks are included.\n\nThis bundle is ad-hoc signed for internal tests, not Developer ID signed or Apple-notarized. It is not approved for public distribution. A complete binary SBOM/license review and nested-code Developer ID signing/notarization must precede a trusted public desktop release. Do not disable operating-system protections.\n'''
    (resources/'DESKTOP_NOTICES.md').write_text(notices)
    metadata={'schema':'litrev.desktop-preview.release.v1','version':version,'source_commit':head,'native_build_number':native_build_number(product) if native else None,'native_source_evidence':native_source_evidence,'source_archive_sha256':digest(args.source_archive.read_bytes()),'source_snapshot_sha256':source['source_snapshot_sha256'],'platform':'macOS arm64','label':('Private desktop candidate — unqualified for public distribution' if native else 'Internal desktop prototype — not notarized'),'web_dependency_notice_inventory':{'packages':len(web_notices['packages']),'notice_files':web_notices['unique_notice_files'],'missing_notice_sources':web_notices['missing_notice_sources'],'public_distribution_review':'pending complete binary SBOM/source obligations'},'derived_page_and_image_cache':'not persisted; signed application remains immutable','core_runtimes_bundled':True,'node_execution':'Electron utilityProcess; developer PATH is removed','python_execution':'Resources/python/bin/python3.12','runtimes':lock,'models_bundled':False,'optional_map_dependencies_bundled':False,'build_metadata_normalization':'Next repo/tracing/turbopack roots are derived from packaged server directory; required-server appDir is relative; unused pip console scripts omitted', 'signature':'ad-hoc; not Developer ID; not notarized','public_distribution':'not authorized','research_data':('external LiteratureReviewEngineDesktop root; no migration' if native else 'external dedicated Desktop Preview root; no migration'),'unused_image_optimizer':{'disabled':native,'omitted_files':omitted},'project_client_boundary':boundary,'shell_sources':{name:digest((ROOT/'apps/desktop'/name).read_bytes()) for name in ('main.cjs','services.cjs','security.cjs','native-exports.cjs','no-disk-cache.cjs','package.json','runtime-lock.json',*(('product.json','optional-runtime.cjs','optional-runtime-catalog.json') if native else ())) }}
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
    manifest_path=output/f'lit-rev-engine-{version}.manifest.json'
    manifest_path.write_bytes(json_bytes({'schema':'litrev.desktop-preview.manifest.v1','source_commit':head,'files':manifest}))
    archive=output/f'lit-rev-engine-{version}-macos-arm64.zip'
    run(['/usr/bin/ditto','-c','-k','--keepParent','--sequesterRsrc',app,archive])
    checksums=output/f'lit-rev-engine-{version}.SHA256SUMS'
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
    parser.add_argument('--desktop-distribution',action='store_true',help='Use the separately reviewed native product identity; never changes old preview assets')
    parser.add_argument('--node')
    parser.add_argument('--pnpm')
    args=parser.parse_args()
    if args.fetch_runtimes:
        print(json.dumps(fetch(args.runtime_cache),indent=2));return
    if not all((args.source_archive,args.expected_source_commit,args.output,args.node,args.pnpm)):parser.error('Build requires exact reviewed source archive/commit, output, and explicit build tools')
    print(json.dumps(build(args),indent=2))

if __name__=='__main__':main()
