"""Explicit, session-bound BGE setup; reads/saves never import model libraries."""
from contextlib import contextmanager
from copy import copy
from hashlib import sha256
from importlib.util import find_spec
import json
import os
from pathlib import Path
import secrets
import shutil
from threading import BoundedSemaphore, Lock
import time
from typing import Literal
from urllib.request import Request, build_opener, HTTPSHandler

from fastapi import Depends
from pydantic import Field
from src.mvp.contracts import Model, canonical, digest, now
from src.mvp.mapping import BGE_REVISION, PaperRepresentation, projection
from src.mvp.adapters.paper_embeddings import LocalPaperEmbedder, REQUIRED_FILES, runtime_versions
from src.mvp.ports import MvpError
from src.platform_support import assert_no_links, atomic_replace, open_private, owned_path

MANIFEST = json.loads((Path(__file__).parents[1] / 'mvp/map_model_manifest.json').read_text())
EXPECTED_VERSIONS = {'sentence-transformers':'5.5.1','torch':'2.12.0','transformers':'5.12.0',
    'huggingface-hub':'1.19.0','numpy':'2.4.6','scikit-learn':'1.9.0','umap-learn':'0.5.12',
    'scipy':'1.17.1','numba':'0.68.0','pynndescent':'0.6.0','llvmlite':'0.50.0','tokenizers':'0.22.2','safetensors':'0.8.0'}


class MapSetupAction(Model):
    expected_revision: int = Field(ge=0, strict=True)


class MapInstallAction(MapSetupAction):
    manifest_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    accept_download: Literal[True]


def runtime_status():
    versions = runtime_versions()
    modules={'sentence-transformers':'sentence_transformers','huggingface-hub':'huggingface_hub','scikit-learn':'sklearn','umap-learn':'umap'}
    def found(key):
        try: return find_spec(modules.get(key,key)) is not None
        except (ImportError,ValueError): return False
    missing = [key for key,value in versions.items() if value == 'not-installed' or not found(key)]
    incompatible = [key for key,value in versions.items() if key not in missing and value.split('+',1)[0] != EXPECTED_VERSIONS[key]]
    return dict(state='missing' if missing else 'incompatible' if incompatible else 'available', versions=versions,
        missing=missing, incompatible=incompatible, check_scope='metadata_only_not_execution',
        message=('This backend needs the pinned mapping runtime. A packaged desktop app needs a separately qualified build; it cannot install Python packages into its bundle. For a source installation, quit the app, run python3.12 scripts/local_preview.py setup --with-maps --with-retrieval, then relaunch with the same data directory. This preserves optional retrieval support; model weights and research data remain external.'
                 if missing or incompatible else 'Pinned mapping packages are present. Use Verify readiness to test actual local computation.'))


def safe_cache(value):
    path = Path(value).expanduser()
    if not path.is_absolute() or '..' in path.parts or any(part.lower().endswith('.app') for part in path.parts) or path.is_relative_to(Path(__file__).resolve().parents[2]):
        raise MvpError('map_cache', 'Choose an absolute model-cache directory outside the application folder.')
    try:
        assert_no_links(path)
        for parent in (path,*path.parents):
            if parent.exists():
                if not parent.is_dir(): raise ValueError()
                if parent == path and not owned_path(parent): raise ValueError()
                break
    except (OSError,ValueError):
        raise MvpError('map_cache', 'The model-cache directory must be owned and must not contain directory links.') from None
    return path


class PinnedSetupEmbedder(LocalPaperEmbedder):
    def _file_hashes(self):
        found = super()._file_hashes()
        expected = {item['path']:item['sha256'] for item in MANIFEST['files']}
        if found != expected:
            raise MvpError('map_weights_invalid', 'The cached BGE files do not match the pinned model manifest. Choose a different cache or explicitly reinstall the weights; existing files were preserved.')
        return found


class MapSetup:
    def __init__(self, settings, registry, base, *, embedder_factory=None):
        self.settings,self.registry,self.base = settings,registry,base
        self.factory = embedder_factory or PinnedSetupEmbedder
        self._adapters,self._submitted,self._tests = {},{},{}
        self._lock,self._slot = Lock(),BoundedSemaphore(1)

    def configuration(self, owner, expected=None):
        snap,_ = self.settings.snapshot(owner, expected)
        pref = snap['preferences']['maps']
        enabled = pref['enabled'] if pref['enabled'] is not None else self.base.enabled
        cache = safe_cache(pref['cache_dir'] or str(self.base.cache_dir))
        return snap,dict(enabled=enabled,source='settings' if pref['enabled'] is not None else 'launch_configuration',cache_dir=str(cache))

    def adapter(self, owner, expected=None):
        snap,config = self.configuration(owner, expected)
        snapshot=Path(config['cache_dir'])/'models--BAAI--bge-small-en-v1.5'/'snapshots'/BGE_REVISION
        def stamp(path):
            try:
                info=path.stat();return (info.st_size,info.st_mtime_ns)
            except OSError:return None
        key=(config['enabled'],config['cache_dir'],tuple(stamp(snapshot/name) for name in REQUIRED_FILES))
        with self._lock:
            adapter=self._adapters.get(key)
            if adapter is None:
                adapter=self.factory(enabled=config['enabled'],cache_dir=config['cache_dir'])
                self._adapters[key]=adapter
        return adapter,snap,config

    def status(self, owner):
        cache_error=None
        try:
            adapter,snap,config = self.adapter(owner)
        except MvpError as error:
            if error.code!='map_cache': raise
            cache_error=error.message
            snap,_=self.settings.snapshot(owner)
            config=dict(enabled=False,source='invalid_cache',cache_dir=snap['preferences']['maps']['cache_dir'])
            adapter=LocalPaperEmbedder(enabled=False,cache_dir=Path.home()/'.cache/huggingface/hub')
        runtime=runtime_status()
        files=[]
        for item in MANIFEST['files']:
            path=adapter.snapshot/item['path']
            try: present=not cache_error and path.is_file() and path.stat().st_size == item['bytes']
            except OSError: present=False
            if not present: files.append(item['path'])
        signature=None if cache_error else self._signature(owner)
        test=self._tests.get(owner)
        computation=test['result'] if test and test['signature']==signature else dict(state='not_tested',tested_at=None,message='No computation has been tested for these settings. Verify readiness runs BGE and projection on synthetic text only.')
        ready = not cache_error and config['enabled'] and not files and runtime['state']=='available'
        reason=(cache_error if cache_error else 'Enable Semantic Maps and save settings.' if not config['enabled'] else runtime['message'] if runtime['state']!='available' else
            'Pinned BGE weights are missing or incomplete. Review and authorize the download.' if files else 'Configured for explicit BGE map calculation. '+computation['message'])
        return dict(schema_version='mvp.map-setup.v1',settings_revision=snap['revision'],profile_id='paper_bge_v1',model=MANIFEST['model'],revision=BGE_REVISION,
            runtime=runtime,weights=dict(state='unavailable' if cache_error else 'missing' if files else 'present',snapshot='' if cache_error else str(adapter.snapshot),missing=files,
                message='Files are present; the explicit verification or map calculation checks their SHA-256 hashes.' if not files else 'No download is performed until you authorize it.'),
            configuration=config,computation=computation,ready=ready,reason=reason,
            download=dict(model=MANIFEST['model'],revision=BGE_REVISION,source=MANIFEST['source'],destination='' if cache_error else str(adapter.snapshot),
                bytes=sum(item['bytes'] for item in MANIFEST['files']),manifest_sha256=digest(MANIFEST),license=MANIFEST['license'],
                supported=not cache_error and runtime['state']=='available',message='Downloads only the pinned BGE model files. Existing Qwen files are never changed.'))

    @contextmanager
    def operation(self):
        if not self._slot.acquire(blocking=False):
            raise MvpError('map_setup_busy','A semantic-map setup operation is already running; wait and retry explicitly.',True)
        try: yield
        finally: self._slot.release()

    def verify(self,owner,expected):
        with self.operation():
            with self.settings._lock:
                adapter,snap,_=self.adapter(owner,expected)
                before=self.status(owner)
                if not before['ready']:
                    raise MvpError('map_setup_required',before['reason'])
                signature=self._signature(owner)
            try:
                # Recheck current bytes even when the profile/model is warm.
                # These reads and all model/projection work stay outside locks.
                adapter._file_hashes()
                vectors=[]
                # Synthetic, bounded input only; no workspace/source content.
                for index,text in enumerate(('Synthetic plant growth experiment.','Synthetic astronomy spectrum measurement.','Synthetic coastal water monitoring.')):
                    representation=PaperRepresentation(paper_id=f'setup-synthetic-{index}',input_text=text,input_sha256=sha256(text.encode()).hexdigest(),representation='title_only')
                    vectors.append(adapter.embed(representation,lambda:None).vector)
                projection(vectors)
                # Verify the large-collection dependency path too, without extra model input.
                import numpy as np
                import umap
                values=np.random.default_rng(42).normal(size=(20,384))
                projection(values.tolist())
                result=dict(state='succeeded',tested_at=now(),message='CPU BGE encoding, small-collection projection and UMAP projection succeeded using synthetic inputs. This is an integration check, not scientific validation.')
            except MvpError as error:
                safe=error.message if error.code in {'map_weights_invalid','embedding_profile_mismatch','embedding_profile_changed','map_setup_required'} else 'Local BGE verification failed; review the runtime and weights, then retry explicitly.'
                result=dict(state='failed',tested_at=now(),error_code=error.code,message=safe)
            except Exception:
                result=dict(state='failed',tested_at=now(),message='Local BGE/projection verification failed. No model fallback was attempted. Research data and saved maps are unchanged; review the runtime and cached weights, then retry explicitly.')
            with self.settings._lock:
                self.settings.assert_current(owner,snap['revision'])
                if self._signature(owner)!=signature:
                    raise MvpError('stale_map_setup','The local model cache changed during verification. Review readiness and retry explicitly; no result was published.')
                self._tests[owner]={'signature':signature,'result':result}
                return self.status(owner)

    def _signature(self,owner):
        adapter,snap,config=self.adapter(owner)
        def stamp(path):
            try:
                info=path.stat();return (info.st_size,info.st_mtime_ns)
            except OSError:return None
        return digest({'revision':snap['revision'],'configuration':config,'runtime':runtime_versions(),
            'files':[(item['path'],stamp(adapter.snapshot/item['path'])) for item in MANIFEST['files']]})

    def install(self,owner,request):
        with self.operation():
            adapter,snap,_=self.adapter(owner,request.expected_revision)
            if request.manifest_sha256 != digest(MANIFEST) or request.accept_download is not True:
                raise MvpError('map_download_consent','Review and authorize the current pinned BGE download first.')
            if runtime_status()['state']!='available':
                raise MvpError('map_setup_required',runtime_status()['message'])
            safe_cache(str(adapter.cache_dir))
            # Do not overwrite an existing snapshot or mutate another model cache.
            if adapter.snapshot.exists():
                try: adapter._file_hashes()
                except (MvpError,OSError):
                    raise MvpError('map_weights_invalid','Existing BGE files are incomplete or invalid and were preserved. Choose another model-cache directory and save settings before retrying the download.') from None
                with self.settings._lock:
                    self.settings.assert_current(owner,snap['revision'])
                    return self.status(owner)
            from src.mvp.retrieval_packs import _Redirects
            opener=build_opener(HTTPSHandler(),_Redirects())
            repository=adapter.snapshot.parent.parent
            repository.mkdir(parents=True,exist_ok=True,mode=0o700)
            assert_no_links(repository)
            staging=repository/('.map-setup-'+secrets.token_hex(12))
            staging.mkdir(mode=0o700)
            deadline=time.monotonic()+90
            try:
                for item in MANIFEST['files']:
                    self.settings.assert_current(owner,snap['revision'])
                    target=staging/item['path'];target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                    url=f"https://huggingface.co/{MANIFEST['model']}/resolve/{BGE_REVISION}/{item['path']}"
                    fd=open_private(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
                    count,hasher=0,sha256()
                    with os.fdopen(fd,'wb') as out,opener.open(Request(url,headers={'User-Agent':'litrev-semantic-map-setup/1'}),timeout=15) as response:
                        while block:=response.read(1024*1024):
                            count+=len(block)
                            if count>item['bytes'] or time.monotonic()>deadline:
                                raise MvpError('map_download_failed','The bounded BGE download exceeded its declared size or time limit. Retry explicitly.')
                            hasher.update(block);out.write(block)
                        out.flush();os.fsync(out.fileno())
                    if count!=item['bytes'] or hasher.hexdigest()!=item['sha256']:
                        raise MvpError('map_download_failed','A BGE download did not match the declared bytes/hash. No snapshot was installed; retry explicitly.')
                adapter.snapshot.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                assert_no_links(adapter.snapshot.parent)
                # Downloading/hashing precedes this short publication fence.
                with self.settings._lock:
                    self.settings.assert_current(owner,snap['revision'])
                    if adapter.snapshot.exists(): raise MvpError('map_setup_busy','Another process installed this BGE snapshot; refresh readiness.',True)
                    atomic_replace(staging,adapter.snapshot)
            except MvpError: raise
            except Exception:
                raise MvpError('map_download_failed','The BGE download failed. No complete snapshot was installed and no research data changed. Retry explicitly when the network is available.') from None
            finally:
                if staging.exists(): shutil.rmtree(staging)
            return self.status(owner)

    def bound_service(self,service,owner):
        adapter,_,_=self.adapter(owner)
        if runtime_status()['state']!='available':
            raise MvpError('map_setup_required',runtime_status()['message'])
        ready,reason=adapter.readiness()
        if not ready: raise MvpError('map_setup_required',reason)
        adapter._file_hashes()  # always recheck warm-cache bytes outside research locks
        adapter.profile
        result=copy(service);result.embedder=adapter
        return result

    def remember(self,submission,adapter):
        with self._lock: self._submitted[submission.job.id]=adapter

    def for_job(self,job):
        with self._lock: adapter=self._submitted.get(job['id'])
        if adapter is not None: return adapter
        with self.registry.connection() as db:
            row=db.execute('SELECT session_hash FROM web_workspaces WHERE workspace_id=?',(job['workspace_id'],)).fetchone()
        if row is None: raise MvpError('unknown_workspace','The map workspace is unavailable.')
        return self.adapter(row['session_hash'])[0]


def install_map_setup_routes(app,*,registry,session_for,dependencies):
    if app.state.deployment.hosted or not isinstance(app.state.maps.embedder,LocalPaperEmbedder):
        app.state.map_setup=None
        return
    setup=MapSetup(app.state.runtime_settings,registry,app.state.maps.embedder)
    app.state.map_setup=setup
    app.state.maps.embedder_for_job=setup.for_job
    app.state.collection_maps.embedder_for_job=setup.for_job

    @app.get('/api/v1/settings/maps',dependencies=dependencies)
    def status(session=Depends(session_for)):
        return setup.status(session['token_hash'])

    @app.post('/api/v1/settings/maps/verify',dependencies=dependencies)
    def verify(request:MapSetupAction,session=Depends(session_for)):
        return setup.verify(session['token_hash'],request.expected_revision)

    @app.post('/api/v1/settings/maps/install',dependencies=dependencies)
    def install(request:MapInstallAction,session=Depends(session_for)):
        return setup.install(session['token_hash'],request)
