"""Explicit pinned local packs. Importing/reading capabilities never uses a network.

Only this allowlisted downloader contacts official model artifact hosts. Model
inference always reads locally hash-verified bytes, with remote code disabled.
"""
from __future__ import annotations
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from src.platform_support import atomic_replace
from src.platform_support import private_directory, open_private, owned_fd, owned_path, is_link, is_process_alive
from src.platform_support.processes import peak_rss_bytes
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

REGISTRY = json.loads(Path(__file__).with_name('retrieval_pack_manifest.json').read_text(encoding='utf-8'))
NOTICES = json.loads(Path(__file__).with_name('retrieval_pack_notices.json').read_text(encoding='utf-8'))
LOCK = Lock()
EVENTS: dict[str, Event] = {}


def _manifest(profile_id):
    if profile_id not in REGISTRY:
        raise MvpError('retrieval_profile', 'Select an allowlisted local retrieval pack.')
    return REGISTRY[profile_id]


def _write(path, value):
    tmp = path.with_suffix('.new-' + str(os.getpid()) + '-' + str(time.monotonic_ns()))
    fd = open_private(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(canonical(value)); stream.flush(); os.fsync(stream.fileno())
        atomic_replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _hash(path):
    value = sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024): value.update(block)
    return value.hexdigest()


def _alive(pid):
    return is_process_alive(pid)


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


def runtime_dependencies():
    """Inspect distribution metadata/specs only: no model-stack imports or I/O."""
    from importlib.metadata import version, PackageNotFoundError
    from importlib.util import find_spec
    expected = {'torch': ('torch', '2.12.0'), 'transformers': ('transformers', '5.12.0'),
                'tokenizers': ('tokenizers', '0.22.2'), 'safetensors': ('safetensors', '0.8.0'),
                'huggingface-hub': ('huggingface_hub', '1.19.0'), 'numpy': ('numpy', '2.4.6')}
    missing, incompatible = [], []
    for package, (module, pinned) in expected.items():
        try:
            found = find_spec(module) is not None
            installed = version(package) if found else None
        except (ImportError, ValueError, PackageNotFoundError):
            installed = None
        if installed is None:
            missing.append(package)
        elif installed.split('+', 1)[0] != pinned:
            incompatible.append(package)
    return {'state': 'needed' if missing or incompatible else 'available', 'missing': missing,
            'incompatible': incompatible, 'check_scope': 'metadata_only_not_execution',
            'distribution': 'desktop' if os.environ.get('LITREV_DESKTOP_RUNTIME_MODE') == 'managed' else 'source',
            'install_hint': ('Application menu → Install optional research libraries…; restart after the verified capsule is installed.'
                             if os.environ.get('LITREV_DESKTOP_RUNTIME_MODE') == 'managed'
                             else 'python3 scripts/local_preview.py setup --with-retrieval')}


class PackManager:
    def __init__(self, root=None):
        self.root = Path(root or os.environ.get('LITREV_RETRIEVAL_CACHE') or
                         Path.home() / '.cache' / 'litrev-evidence-retrieval').expanduser().absolute()
        app = Path(__file__).resolve().parents[2]
        if self.root.is_relative_to(app) or '..' in self.root.parts:
            raise MvpError('pack_cache', 'Use a private absolute retrieval cache outside application files.')
        try: private_directory(self.root)
        except (OSError, ValueError):
            raise MvpError('pack_cache', 'Retrieval cache must be an owned private directory without links.') from None

    def _paths(self, profile_id):
        pack = _manifest(profile_id)
        return pack, self.root / pack['pack_id'], self.root / (pack['pack_id'] + '.partial')

    def _state_path(self, profile_id):
        return self.root / (_manifest(profile_id)['pack_id'] + '.state.json')

    def _state(self, profile_id, **value):
        previous = {}
        try: previous = json.loads(self._state_path(profile_id).read_text(encoding='utf-8'))
        except (OSError, ValueError): pass
        runtimes = previous.get('runtimes', {})
        if value.get('runtime'):
            runtimes[value['runtime']['device']] = value['runtime']
        if runtimes: value['runtimes'] = runtimes
        _write(self._state_path(profile_id), dict(value, pid=os.getpid(), updated_at=time.time()))

    def status(self, profile_id):
        pack, target, partial = self._paths(profile_id)
        if is_link(target) or is_link(partial) or is_link(self._state_path(profile_id)):
            raise MvpError('pack_cache', 'Pack paths cannot contain symlinks.')
        state = {}
        try: state = json.loads(self._state_path(profile_id).read_text(encoding='utf-8'))
        except (OSError, ValueError): pass
        installed = False
        try:
            if is_link((target / 'INSTALL.json')) or any(is_link((target / m['repo'].replace('/', '--'))) for m in pack['models']):
                raise MvpError('pack_cache', 'Installed pack paths cannot contain symlinks.')
            marker = json.loads((target / 'INSTALL.json').read_text(encoding='utf-8'))
            installed = marker['manifest_sha256'] == digest(pack) and all(
                (target / model['repo'].replace('/', '--') / item['path']).is_file() and
                not is_link((target / model['repo'].replace('/', '--') / item['path'])) and
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
            runtime_by_device=state.get('runtimes', {}), dependencies=runtime_dependencies(), index_state='scope_required', message=state.get('message','Install explicitly; opening settings performs no model or provider call.'))

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
            if is_link(path): raise MvpError('pack_cache', 'Unsafe pack operation lock.')
            if path.exists():
                try: pid = int(path.read_text(encoding='utf-8'))
                except (ValueError, OSError): pid = None
                if _alive(pid): raise MvpError('pack_busy', 'A pack operation is already active.', True)
                path.unlink(missing_ok=True)
            fd = open_private(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
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
            private_directory(partial)
            if is_link(partial): raise MvpError('pack_cache', 'Pack staging cannot be a symlink.')
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
                    private_directory(directory)
                    if is_link(directory): raise MvpError('pack_cache','Unsafe pack directory.')
                    for item in model['files']:
                        if event.is_set() or cancelled and cancelled(): raise MvpError('pack_cancelled','Pack installation cancelled; verified partial bytes retained.')
                        destination = directory / item['path']
                        if is_link(destination): raise MvpError('pack_cache','Unsafe pack file.')
                        if destination.exists():
                            info = destination.lstat()
                            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not owned_path(destination):
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
                            fd = open_private(destination, os.O_WRONLY | os.O_CREAT)
                            info = os.fstat(fd)
                            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not owned_fd(fd, private=True):
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
                atomic_replace(partial,target)
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
                if is_link(path) or _hash(path) != item['sha256']:
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
                runtime = dict(adapter.runtime_metadata(),elapsed_seconds=time.monotonic()-started,
                    encoder_executed=True,reranker_executed=True,dimension=adapter.dimension,
                    reranker_scores=ranks,peak_process_rss_bytes=peak_rss_bytes(),
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
                if is_link(directory): raise MvpError('pack_cache','Unsafe pack directory.')
                if directory.exists(): shutil.rmtree(directory)
            self._state(profile_id,state='not_installed',message='Pack removed. Saved source evidence, results, judgments and indexes remain readable.')
        return self.status(profile_id)
