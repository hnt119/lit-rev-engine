"""Explicit pinned local packs. Importing/reading capabilities never uses a network.

Only this allowlisted downloader contacts official model artifact hosts. Model
inference always reads locally hash-verified bytes, with remote code disabled.
"""
from __future__ import annotations
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import ssl
import stat
from threading import Event, Lock
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler

from .contracts import canonical, digest
from .ports import MvpError

REGISTRY = json.loads(Path(__file__).with_name('retrieval_pack_manifest.json').read_text())
NOTICES = json.loads(Path(__file__).with_name('retrieval_pack_notices.json').read_text())
LOCK = Lock()
EVENTS: dict[str, Event] = {}


def _manifest(profile_id):
    if profile_id not in REGISTRY:
        raise MvpError('retrieval_profile', 'Select an allowlisted local retrieval pack.')
    return REGISTRY[profile_id]


def _write(path, value):
    tmp = path.with_suffix('.new-' + str(os.getpid()) + '-' + str(time.monotonic_ns()))
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(canonical(value)); stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _hash(path):
    value = sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024): value.update(block)
    return value.hexdigest()


def _alive(pid):
    try: os.kill(pid, 0); return True
    except (OSError, TypeError): return False


def _safe_host(url):
    parsed = urlsplit(url)
    host = parsed.hostname or ''
    return (parsed.scheme == 'https' and parsed.port in (None, 443) and not parsed.username
        and not parsed.password and (host == 'huggingface.co' or host.endswith('.huggingface.co')
        or host.endswith('.hf.co') or host == 'hf.co' or host.endswith('.xethub.hf.co')))


class _Redirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if not _safe_host(newurl): raise MvpError('pack_host', 'Artifact redirect left the official model artifact hosts.')
        return super().redirect_request(request, fp, code, msg, headers, newurl)


class PackManager:
    def __init__(self, root=None):
        self.root = Path(root or os.environ.get('LITREV_RETRIEVAL_CACHE') or
                         Path.home() / '.cache' / 'litrev-evidence-retrieval').expanduser().absolute()
        app = Path(__file__).resolve().parents[2]
        if self.root.is_relative_to(app) or '..' in self.root.parts:
            raise MvpError('pack_cache', 'Use a private absolute retrieval cache outside application files.')
        for path in (self.root, *self.root.parents):
            if path.is_symlink(): raise MvpError('pack_cache', 'Retrieval cache paths cannot contain symlinks.')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = self.root.stat()
        if info.st_uid != os.getuid() or not stat.S_ISDIR(info.st_mode):
            raise MvpError('pack_cache', 'Retrieval cache must be an owned private directory.')
        self.root.chmod(0o700)

    def _paths(self, profile_id):
        pack = _manifest(profile_id)
        return pack, self.root / pack['pack_id'], self.root / (pack['pack_id'] + '.partial')

    def _state_path(self, profile_id):
        return self.root / (_manifest(profile_id)['pack_id'] + '.state.json')

    def _state(self, profile_id, **value):
        previous = {}
        try: previous = json.loads(self._state_path(profile_id).read_text())
        except (OSError, ValueError): pass
        runtimes = previous.get('runtimes', {})
        if value.get('runtime'):
            runtimes[value['runtime']['device']] = value['runtime']
        if runtimes: value['runtimes'] = runtimes
        _write(self._state_path(profile_id), dict(value, pid=os.getpid(), updated_at=time.time()))

    def status(self, profile_id):
        pack, target, partial = self._paths(profile_id)
        if target.is_symlink() or partial.is_symlink() or self._state_path(profile_id).is_symlink():
            raise MvpError('pack_cache', 'Pack paths cannot contain symlinks.')
        state = {}
        try: state = json.loads(self._state_path(profile_id).read_text())
        except (OSError, ValueError): pass
        installed = False
        try:
            if (target / 'INSTALL.json').is_symlink() or any((target / m['repo'].replace('/', '--')).is_symlink() for m in pack['models']):
                raise MvpError('pack_cache', 'Installed pack paths cannot contain symlinks.')
            marker = json.loads((target / 'INSTALL.json').read_text())
            installed = marker['manifest_sha256'] == digest(pack) and all(
                (target / model['repo'].replace('/', '--') / item['path']).is_file() and
                not (target / model['repo'].replace('/', '--') / item['path']).is_symlink() and
                (target / model['repo'].replace('/', '--') / item['path']).stat().st_size == item['bytes']
                for model in pack['models'] for item in model['files'])
        except (OSError, ValueError, KeyError): pass
        phase = state.get('state', 'not_installed')
        if phase in {'downloading', 'runtime_testing'} and not _alive(state.get('pid')): phase = 'interrupted'
        if installed and phase not in {'runtime_testing', 'runtime_failed', 'runtime_passed'}: phase = 'installed'
        if not installed and phase in {'installed', 'runtime_passed', 'runtime_failed'}: phase = 'corrupt_or_missing'
        runtime = state.get('runtime')
        if installed and phase == 'runtime_passed' and runtime:
            from .adapters.neural_retrieval import native_runtime_signature
            signature = native_runtime_signature(profile_id, runtime.get('device', 'cpu'))
            if any(runtime.get(k) != v for k, v in signature.items()): phase = 'runtime_test_needed'
        return dict(profile_id=profile_id, pack_id=pack['pack_id'], label=pack['label'], state=phase,
            installed=installed, download_bytes=pack['download_bytes'], downloaded_bytes=pack['download_bytes'] if installed else state.get('downloaded_bytes', 0),
            manifest_sha256=digest(pack), models=[{'repo':m['repo'],'revision':m['revision'],'bytes':m['selected_bytes']} for m in pack['models']],
            license=pack['license'], quality_status=pack['quality_status'], runtime=state.get('runtime'),
            runtime_by_device=state.get('runtimes', {}), index_state='scope_required', message=state.get('message','Install explicitly; opening settings performs no model or provider call.'))

    def manifest(self, profile_id):
        return json.loads(canonical(_manifest(profile_id)))

    def capabilities(self):
        return [self.status(profile_id) for profile_id in REGISTRY]

    @contextmanager
    def _lease(self, profile_id, operation):
        key = str(self.root) + ':' + profile_id
        path = self.root / (_manifest(profile_id)['pack_id'] + '.lock')
        with LOCK:
            if key in EVENTS: raise MvpError('pack_busy', 'A pack operation is already active.', True)
            if path.is_symlink(): raise MvpError('pack_cache', 'Unsafe pack operation lock.')
            if path.exists():
                try: pid = int(path.read_text())
                except (ValueError, OSError): pid = None
                if _alive(pid): raise MvpError('pack_busy', 'A pack operation is already active.', True)
                path.unlink(missing_ok=True)
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(fd, str(os.getpid()).encode()); os.close(fd)
            event = Event(); EVENTS[key] = event
        try: yield event
        finally:
            with LOCK:
                EVENTS.pop(key, None); path.unlink(missing_ok=True)

    def cancel(self, profile_id):
        _manifest(profile_id)
        with LOCK:
            event = EVENTS.get(str(self.root) + ':' + profile_id)
            if event: event.set()
        return self.status(profile_id)

    def install(self, profile_id, cancelled=None):
        pack, target, partial = self._paths(profile_id)
        if self.status(profile_id)['installed']:
            if pack['pack_id'] in NOTICES: _write(target / 'NOTICES.json', NOTICES[pack['pack_id']])
            return self.status(profile_id)
        if target.exists():
            raise MvpError('pack_corrupt', 'Remove the incomplete or corrupt pack explicitly before reinstalling.')
        with self._lease(profile_id, 'install') as event:
            partial.mkdir(mode=0o700, exist_ok=True)
            if partial.is_symlink(): raise MvpError('pack_cache', 'Pack staging cannot be a symlink.')
            self._state(profile_id, state='downloading', downloaded_bytes=0)
            total, started = 0, time.monotonic()
            try:
                try:
                    import certifi
                    context = ssl.create_default_context(cafile=certifi.where())
                except ImportError: context = ssl.create_default_context()
                opener = build_opener(_Redirects(), HTTPSHandler(context=context))
                for model in pack['models']:
                    directory = partial / model['repo'].replace('/', '--')
                    directory.mkdir(mode=0o700, exist_ok=True)
                    if directory.is_symlink(): raise MvpError('pack_cache','Unsafe pack directory.')
                    for item in model['files']:
                        if event.is_set() or cancelled and cancelled(): raise MvpError('pack_cancelled','Pack installation cancelled; verified partial bytes retained.')
                        destination = directory / item['path']
                        if destination.is_symlink(): raise MvpError('pack_cache','Unsafe pack file.')
                        if destination.exists():
                            info = destination.lstat()
                            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
                                raise MvpError('pack_cache','Pack artifacts must be owned ordinary files with one link.')
                        if destination.exists() and destination.stat().st_size == item['bytes'] and _hash(destination) == item['sha256']:
                            total += item['bytes']; continue
                        offset = destination.stat().st_size if destination.exists() else 0
                        if offset >= item['bytes'] and item['bytes']:
                            destination.unlink(); offset = 0
                        headers = {'User-Agent':'litrev-explicit-model-pack/1','Accept-Encoding':'identity'}
                        if offset: headers['Range'] = 'bytes=' + str(offset) + '-'
                        if not _safe_host(item['url']): raise MvpError('pack_host','Invalid pinned model URL.')
                        with opener.open(Request(item['url'], headers=headers), timeout=30) as response:
                            if not _safe_host(response.geturl()): raise MvpError('pack_host','Invalid artifact host.')
                            if offset and response.status != 206: offset = 0
                            if offset and not response.headers.get('Content-Range','').startswith('bytes '+str(offset)+'-'):
                                raise MvpError('pack_resume','Server did not honor the exact resume range.')
                            written = offset
                            fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
                            info = os.fstat(fd)
                            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
                                os.close(fd); raise MvpError('pack_cache','Pack artifacts must be owned ordinary files with one link.')
                            if offset: os.lseek(fd, offset, os.SEEK_SET)
                            else: os.ftruncate(fd, 0)
                            with os.fdopen(fd,'wb') as stream:
                                while block := response.read(1024 * 1024):
                                    if event.is_set() or cancelled and cancelled(): raise MvpError('pack_cancelled','Pack installation cancelled; partial bytes retained.')
                                    written += len(block)
                                    if written > item['bytes']: raise MvpError('pack_size','Pinned artifact exceeded its declared byte length.')
                                    stream.write(block)
                                    self._state(profile_id, state='downloading', downloaded_bytes=total+written)
                                stream.flush(); os.fsync(stream.fileno())
                        if destination.stat().st_size != item['bytes'] or _hash(destination) != item['sha256']:
                            destination.unlink(missing_ok=True)
                            raise MvpError('pack_hash','Pinned artifact length or SHA-256 verification failed; no pack was installed.')
                        total += item['bytes']
                if event.is_set() or cancelled and cancelled():
                    raise MvpError('pack_cancelled','Installation cancelled before atomic publication; partial bytes retained.')
                if pack['pack_id'] in NOTICES: _write(partial / 'NOTICES.json', NOTICES[pack['pack_id']])
                _write(partial / 'INSTALL.json', {'manifest_sha256':digest(pack),'verified_bytes':total,'elapsed_seconds':time.monotonic()-started})
                os.replace(partial,target)
                self._state(profile_id,state='installed',downloaded_bytes=total)
            except Exception as exc:
                self._state(profile_id,state='cancelled' if isinstance(exc,MvpError) and exc.code=='pack_cancelled' else 'failed',
                    downloaded_bytes=total, message='Installation did not complete. No fallback or model substitution occurred.')
                raise
        return self.status(profile_id)

    def verify(self, profile_id):
        pack, target, _ = self._paths(profile_id)
        if not self.status(profile_id)['installed']:
            raise MvpError('pack_missing','Install this exact retrieval pack explicitly before indexing or searching. No lexical fallback was run.')
        for model in pack['models']:
            for item in model['files']:
                path = target / model['repo'].replace('/', '--') / item['path']
                if path.is_symlink() or _hash(path) != item['sha256']:
                    raise MvpError('pack_hash','A pinned model file failed hash verification. No inference or fallback was run.')
        return {model['repo']:target/model['repo'].replace('/', '--') for model in pack['models']}

    def adapter(self, profile_id, device='cpu'):
        paths = self.verify(profile_id)
        from .adapters.neural_retrieval import NeuralAdapter
        return NeuralAdapter(profile_id, paths, _manifest(profile_id), device=device)

    def check_runtime(self, profile_id, device='cpu'):
        with self._lease(profile_id, 'runtime') as event:
            self._state(profile_id,state='runtime_testing')
            started = time.monotonic()
            try:
                adapter = self.adapter(profile_id,device)
                if hasattr(adapter, 'set_cancelled'): adapter.set_cancelled(event.is_set)
                if event.is_set(): raise MvpError('pack_cancelled','Runtime test cancelled before model execution.')
                query = 'What treatment reduced blood pressure?'
                documents = [('Synthetic integration fixture','The treatment reduced blood pressure.'),('Synthetic integration fixture','The experiment measured forest canopy height.')]
                adapter.validate_query(query)
                queries = adapter.encode_queries([query])
                docs = adapter.encode_documents(documents)
                ranks = adapter.rerank(query, documents)
                if event.is_set(): raise MvpError('pack_cancelled','Runtime test cancelled; no passed badge was published.')
                if len(queries)!=1 or len(docs)!=2 or len(ranks)!=2 or any(len(v)!=adapter.dimension for v in queries+docs):
                    raise MvpError('runtime_shape','The model runtime returned an incompatible output.')
                import resource
                runtime = dict(adapter.runtime_metadata(),elapsed_seconds=time.monotonic()-started,
                    encoder_executed=True,reranker_executed=True,dimension=adapter.dimension,
                    reranker_scores=ranks,peak_process_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if __import__('sys').platform=='darwin' else 1024),
                    measurement_scope='whole-process high-water RSS converted to bytes; integration synthetic text only')
                self._state(profile_id,state='runtime_passed',runtime=runtime)
            except Exception:
                self._state(profile_id,state='cancelled' if event.is_set() else 'runtime_failed',message='Runtime test failed. No backend, precision, model or lexical fallback occurred.')
                raise
        return self.status(profile_id)

    def remove(self, profile_id):
        pack, target, partial = self._paths(profile_id)
        with self._lease(profile_id, 'remove'):
            for directory in (target,partial):
                if directory.is_symlink(): raise MvpError('pack_cache','Unsafe pack directory.')
                if directory.exists(): shutil.rmtree(directory)
            self._state(profile_id,state='not_installed',message='Pack removed. Saved source evidence, results, judgments and indexes remain readable.')
        return self.status(profile_id)
