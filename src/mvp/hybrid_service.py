"""Explicit hybrid indexing and receipts beside immutable research histories.

Compute runs outside research/lifecycle/SQLite locks. Publication revalidates the
exact captured scope; deleting a workspace fences late work. No automatic index,
download, provider call or lexical fallback is performed.
"""
from contextlib import contextmanager, nullcontext
from pathlib import Path
from threading import BoundedSemaphore, Event, RLock
import json
import os
import sqlite3
from .contracts import canonical, digest, new_id, now
from .ports import MvpError
from .service import _find, _assert_source_integrity
from .origin_resolver import resolve_preparation
from .hybrid_contracts import HybridSourceBinding, HybridInventory, HybridIndex, HybridResult
from .hybrid_app_contracts import HybridSavedRun, HybridBoardCandidates, HybridScopeRequest, HybridSourceContext
from .board_contracts import BoardReferenceInput, BoardSourceBinding, BoardPaper

class HybridEvidenceService:
    def __init__(self, registry, service_for, boards, directory, packs):
        self.registry, self.service_for, self.boards, self.packs = registry, service_for, boards, packs
        self.path = Path(boards.store.path)  # Additive tables in the existing comparison sidecar.
        self._slot, self._lock, self._cancel = BoundedSemaphore(1), RLock(), {}
        fd=os.open(self.path, os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW, 0o600);os.fchmod(fd,0o600);os.close(fd)
        with self.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS hybrid_runs(workspace_id TEXT NOT NULL,id TEXT PRIMARY KEY,request_id TEXT NOT NULL,fingerprint TEXT NOT NULL,payload TEXT NOT NULL,sha256 TEXT NOT NULL,UNIQUE(workspace_id,request_id));
                CREATE TABLE IF NOT EXISTS hybrid_jobs_v1(workspace_id TEXT NOT NULL,id TEXT NOT NULL,kind TEXT NOT NULL,state TEXT NOT NULL,detail TEXT NOT NULL,fingerprint TEXT NOT NULL,PRIMARY KEY(workspace_id,id));
                CREATE TABLE IF NOT EXISTS hybrid_deleted(workspace_id TEXT PRIMARY KEY);''')
            db.execute("UPDATE hybrid_jobs_v1 SET state='interrupted',detail='Backend restarted; explicitly start a new operation.' WHERE state='running'")
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=15);db.row_factory=sqlite3.Row
        try:
            yield db;db.commit()
        finally:db.close()
    @staticmethod
    def bindings(sources):
        return [HybridSourceBinding(source_id=s.id,paper_id=s.paper_id,version=s.version,source_sha256=s.source_sha256,
            blocks_sha256=s.blocks_sha256,parser_id=s.parser_id,source_type=s.source_type) for s in sources]
    def _alive(self,db,workspace):
        if db.execute('SELECT 1 FROM hybrid_deleted WHERE workspace_id=?',(workspace,)).fetchone():
            raise MvpError('unknown_workspace','This workspace was deleted; no late retrieval can publish.')
    def capture(self,mode,handle,request,*,current=True,guard=True,publish=None):
        def read(state):
            if self.registry.is_deleted(state.id):raise MvpError('unknown_workspace','Workspace unavailable.')
            prep=_find(state.preparations,request.expected_preparation_id,'preparation')
            if prep.source_revision!=request.expected_source_revision:
                raise MvpError('stale_source_revision','The requested preparation/source revision does not agree.')
            if request.board_context:
                with self.boards.store.connection() as db:
                    context,sources=self.boards._passage_search_context(state,db,request.board_context,require_current=current)
                    definition=self.boards.store.definition(db,state.id,request.board_context.board_id,request.board_context.board_revision_id)
                if context.preparation_id!=prep.id or context.source_revision!=request.expected_source_revision:
                    raise MvpError('stale_source_revision','The comparison keeps different retained source bindings.')
                if definition.retrieval_profile.get('profile_id')!=request.profile_id:
                    raise MvpError('unsupported_board_profile','Use this board definition’s explicitly pinned retrieval profile.')
                if current:
                    from .hybrid_retrieval import hybrid_profile
                    expected=hybrid_profile(request.profile_id,self.packs.manifest(request.profile_id))
                    if request.device!=definition.retrieval_profile.get('device','cpu') or any(definition.retrieval_profile.get(k)!=v for k,v in expected.items()):
                        raise MvpError('unsupported_board_profile','The requested model, device or retrieval implementation differs from this board’s pinned profile. Create an explicit definition revision; no substitution was made.')
                papers=context.papers
            else:
                if current and (not state.preparations or state.preparations[-1].id!=prep.id or state.source_revision!=prep.source_revision):
                    raise MvpError('stale_source_revision','Sources changed; inspect the preparation and explicitly retry.')
                sources=prep.sources
                papers=resolve_preparation(state,prep).papers
            _assert_source_integrity(sources)
            bindings=self.bindings(sources)
            scope={'workspace_id':state.id,'preparation_id':prep.id,'source_revision':prep.source_revision,
                'board_context':request.board_context.model_dump(mode='json') if request.board_context else None,
                'sources':[s.model_dump(mode='json') for s in bindings]}
            value={'scope':scope,'sources':[s.model_copy(deep=True) for s in sources],
                'titles':{p.id:p.title for p in papers},'papers':{p.id:p.model_dump(mode='json') for p in papers},'bindings':bindings}
            return publish(value) if publish else value
        with (self.registry.lifecycle_guard(handle.workspace_id) if guard else nullcontext()):
            return self.service_for(mode).with_workspace_state(handle,read)
    def _revalidate(self,mode,handle,request,captured,*,guard=True):
        fresh=self.capture(mode,handle,request,guard=guard)
        if fresh['scope']!=captured['scope'] or fresh['sources']!=captured['sources'] or fresh['titles']!=captured['titles']:
            raise MvpError('retrieval_stale_inputs','Source or scope bindings changed; no result was published.')
    def _key(self,captured,request,manifest):
        from .hybrid_windows import WINDOWIZER
        from .hybrid_retrieval import profile_binding_hash
        try:
            from .adapters.neural_retrieval import native_runtime_signature
            runtime=native_runtime_signature(request.profile_id,request.device)
        except ImportError:
            runtime={'device':request.device,'dtype':'float32'}
        return digest([captured['scope'],captured['titles'],request.profile_id,request.device,manifest,WINDOWIZER,profile_binding_hash(request.profile_id,manifest,runtime),'mvp.hybrid-cache.v1'])
    def _require_cache(self):
        if getattr(self.packs,'available',True) is False:
            raise MvpError('retrieval_cache_unavailable',self.packs.unavailable_reason)

    def _index_path(self,key):
        self._require_cache()
        return Path(self.packs.root)/'indexes'/key[:2]/(key+'.json')
    def _load(self,key):
        path=self._index_path(key)
        if not path.is_file() or path.is_symlink():
            raise MvpError('retrieval_index_missing','Index missing or stale for these exact sources/profile/device. Choose Index these sources explicitly.')
        try:
            value=json.loads(path.read_text());inventory=HybridInventory.model_validate(value['inventory']);index=HybridIndex.model_validate(value['index'])
            if digest({'inventory':value['inventory'],'index':value['index']})!=value['sha256']:raise ValueError()
            return inventory,index
        except (ValueError,KeyError,TypeError):raise MvpError('retrieval_index_corrupt','The derived index failed validation; explicitly rebuild it.') from None
    def index_state(self,mode,handle,request):
        captured=self.capture(mode,handle,request)
        if getattr(self.packs,'available',True) is False:
            return {'state':'cache_unavailable','reason':self.packs.unavailable_reason}
        key=self._key(captured,request,self.packs.manifest(request.profile_id))
        try:
            inventory,index=self._load(key)
            return {'state':'ready','index_key':index.index_key,'coverage':inventory.coverage.model_dump(mode='json')}
        except MvpError as e:return {'state':'missing_or_stale','reason':e.message}
    @contextmanager
    def operation(self,workspace,identifier,kind,fingerprint):
        if not self._slot.acquire(blocking=False):raise MvpError('retrieval_busy','Another neural retrieval operation is active; explicitly retry later.',True)
        event=Event()
        try:
            with self._lock:self._cancel[(workspace,identifier)]=event
            with self.db() as db:
                self._alive(db,workspace)
                old=db.execute('SELECT * FROM hybrid_jobs_v1 WHERE workspace_id=? AND id=?',(workspace,identifier)).fetchone()
                if old is not None:
                    if old['fingerprint']!=fingerprint or old['kind']!=kind:
                        raise MvpError('idempotency_conflict','This retrieval job key was used with a different operation or input.')
                    raise MvpError('retrieval_already_attempted','This job was already attempted. Inspect its retained state; start a new explicit request to retry.')
                db.execute('INSERT INTO hybrid_jobs_v1 VALUES(?,?,?,?,?,?)',(workspace,identifier,kind,'running','',fingerprint))
                self.boards.store.limits(db,workspace)
            try:
                yield event.is_set
            except BaseException as e:
                with self.db() as db:db.execute('UPDATE hybrid_jobs_v1 SET state=?,detail=? WHERE workspace_id=? AND id=?',
                    ('cancelled' if event.is_set() else 'failed',getattr(e,'code','retrieval_failure'),workspace,identifier))
                raise
            else:
                with self.db() as db:db.execute("UPDATE hybrid_jobs_v1 SET state='completed',detail='' WHERE workspace_id=? AND id=?",(workspace,identifier))
        finally:
            with self._lock:self._cancel.pop((workspace,identifier),None)
            self._slot.release()
    def cancel(self,workspace,identifier):
        with self._lock:
            event=self._cancel.get((workspace,identifier))
            if event:event.set()
        return self.job(workspace,identifier)
    def job(self,workspace,identifier):
        with self.db() as db:
            self._alive(db,workspace);row=db.execute('SELECT * FROM hybrid_jobs_v1 WHERE workspace_id=? AND id=?',(workspace,identifier)).fetchone()
            if row is None:raise MvpError('unknown_retrieval_job','The job does not belong to this workspace.')
            return dict(row)
    def build_index(self,mode,handle,request):
        self._require_cache()
        from .hybrid_windows import build_inventory
        from .hybrid_retrieval import HybridRetrieval
        captured=self.capture(mode,handle,request)
        manifest=self.packs.manifest(request.profile_id);key=self._key(captured,request,manifest)
        fingerprint=digest({'kind':'index','request':request.model_dump(mode='json')})
        with self.db() as db:
            old=db.execute('SELECT * FROM hybrid_jobs_v1 WHERE workspace_id=? AND id=?',(handle.workspace_id,request.request_id)).fetchone()
            if old is not None:
                if old['kind']!='index' or old['fingerprint']!=fingerprint:
                    raise MvpError('idempotency_conflict','This retrieval job key has different inputs.')
                if old['state']=='completed':
                    inventory,index=self._load(key)
                    return {'state':'ready','index_key':index.index_key,'coverage':inventory.coverage.model_dump(mode='json'),'elapsed_seconds':index.elapsed_seconds,'runtime':index.runtime}
        with self.operation(handle.workspace_id,request.request_id,'index',fingerprint) as cancelled:
            adapter=self.packs.adapter(request.profile_id,request.device)
            inventory=build_inventory(captured['sources'],authorized_sources=captured['bindings'],titles=captured['titles'],fits_document=adapter.fits_document,cancelled=cancelled)
            index=HybridRetrieval(adapter).build_index(inventory,cancelled=cancelled)
            self._revalidate(mode,handle,request,captured)
            if cancelled():raise MvpError('retrieval_cancelled','Indexing cancelled; no index was published.')
            path=self._index_path(key);path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            data={'inventory':inventory.model_dump(mode='json'),'index':index.model_dump(mode='json')};data['sha256']=digest(data)
            tmp=path.with_suffix('.partial-'+new_id())
            try:
                fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                with os.fdopen(fd,'w') as f:f.write(canonical(data));f.flush();os.fsync(f.fileno())
                def publish(fresh):
                    with self._lock:
                        if fresh['scope']!=captured['scope'] or fresh['sources']!=captured['sources'] or fresh['titles']!=captured['titles']:
                            raise MvpError('retrieval_stale_inputs','Source bindings changed; index not published.')
                        if cancelled():raise MvpError('retrieval_cancelled','Indexing cancelled; no index published.')
                        with self.db() as db:self._alive(db,handle.workspace_id)
                        os.replace(tmp,path)
                self.capture(mode,handle,request,publish=publish)
            finally:tmp.unlink(missing_ok=True)
            return {'state':'ready','index_key':index.index_key,'coverage':inventory.coverage.model_dump(mode='json'),'elapsed_seconds':index.elapsed_seconds,'runtime':index.runtime}
    def _prior(self,workspace,request,fingerprint):
        with self.db() as db:
            self._alive(db,workspace);row=db.execute('SELECT * FROM hybrid_runs WHERE workspace_id=? AND request_id=?',(workspace,request.request_id)).fetchone()
            if row is None:return None
            if row['fingerprint']!=fingerprint:raise MvpError('idempotency_conflict','This retrieval request key was used with different inputs.')
            return self._decode(row)
    @staticmethod
    def _decode(row):
        result=HybridSavedRun.model_validate_json(row['payload'])
        if digest(result.model_dump(mode='json'))!=row['sha256']:raise MvpError('retrieval_integrity','Saved hybrid receipt integrity failure.')
        return result
    def search(self,mode,handle,request,*,operation='search',requirements=None):
        from .hybrid_retrieval import HybridRetrieval
        fingerprint=digest({'operation':operation,'request':request.model_dump(mode='json'),'requirements':[v.model_dump(mode='json') if hasattr(v,'model_dump') else v for v in requirements] if requirements is not None else None})
        prior=self._prior(handle.workspace_id,request,fingerprint)
        if prior:return prior
        self._require_cache()
        captured=self.capture(mode,handle,request)
        manifest=self.packs.manifest(request.profile_id);key=self._key(captured,request,manifest)
        inventory,index=self._load(key)
        with self.operation(handle.workspace_id,request.request_id,'search',fingerprint) as cancelled:
            adapter=self.packs.adapter(request.profile_id,request.device)
            result=HybridRetrieval(adapter).search(request.question,captured['sources'],new_id(),request.top_k,
                authorized_sources=captured['bindings'],titles=captured['titles'],requirements=requirements,operation=operation,index=index,inventory=inventory,cancelled=cancelled)
            result=HybridResult.model_validate(result.model_dump(mode='json'))
            saved=HybridSavedRun(id=result.run_id,workspace_id=handle.workspace_id,preparation_id=request.expected_preparation_id,
                source_revision=request.expected_source_revision,board_context=request.board_context,request_sha256=fingerprint,result=result)
            def publish(fresh):
                with self._lock:
                    if fresh['scope']!=captured['scope'] or fresh['sources']!=captured['sources'] or fresh['titles']!=captured['titles']:
                        raise MvpError('retrieval_stale_inputs','Source bindings changed; no run was published.')
                    if cancelled():raise MvpError('retrieval_cancelled','Retrieval cancelled; no result was published.')
                    with self.db() as db:
                        self._alive(db,handle.workspace_id)
                        if db.execute('SELECT COUNT(*) FROM hybrid_runs WHERE workspace_id=?',(handle.workspace_id,)).fetchone()[0]>=200:
                            raise MvpError('retrieval_storage_limit','This workspace reached 200 hybrid receipts; export existing history before starting another workspace.')
                        db.execute('INSERT INTO hybrid_runs VALUES(?,?,?,?,?,?)',(handle.workspace_id,saved.id,request.request_id,saved.request_sha256,saved.model_dump_json(),digest(saved.model_dump(mode='json'))))
                        self.boards.store.limits(db,handle.workspace_id)
            self.capture(mode,handle,request,publish=publish)
            return saved
    def runs(self,workspace):
        with self.db() as db:
            self._alive(db,workspace)
            return [self._decode(row) for row in db.execute('SELECT * FROM hybrid_runs WHERE workspace_id=? ORDER BY rowid DESC',(workspace,))]
    def get(self,workspace,identifier):
        return _find(self.runs(workspace),identifier,'hybrid_run')
    def inspect(self,mode,handle,identifier,candidate_id):
        saved=self.get(handle.workspace_id,identifier);candidate=next((v for v in saved.result.candidates if v.candidate_id==candidate_id),None)
        if candidate is None:raise MvpError('unknown_candidate','Candidate unavailable in this exact receipt.')
        request=HybridScopeRequest(request_id='inspect',profile_id=saved.result.profile_id,expected_preparation_id=saved.preparation_id,expected_source_revision=saved.source_revision,board_context=saved.board_context)
        captured=self.capture(mode,handle,request,current=False)
        source=_find(captured['sources'],candidate.reference.source_id,'source');block=_find(source.blocks,candidate.reference.block_id,'block');ref=candidate.reference
        if (ref.source_version!=source.version or ref.source_sha256!=source.source_sha256 or ref.blocks_sha256!=source.blocks_sha256 or ref.quote!=block.text[ref.start:ref.end]):
            raise MvpError('retrieval_integrity','Saved quotation no longer matches its exact retained source.')
        # Reuse canonical board chunk/reference types and the same source range resolver.
        from .board_contracts import BoardBlockChunk
        start=max(0,ref.start-1000);end=min(len(block.text),start+4000)
        chunk_ref=ref.model_copy(update={'id':'source-context:'+digest([source.id,block.id,start,end]),'start':start,'end':end,'quote':block.text[start:end]})
        chunk=BoardBlockChunk(source_id=source.id,paper_id=source.paper_id,block_id=block.id,ordinal=block.ordinal,locator=block.locator,start=start,end=end,total_characters=len(block.text),text=block.text[start:end],omitted_before=start,omitted_after=len(block.text)-end,reference=chunk_ref)
        paper=BoardPaper.model_validate({k:v for k,v in captured['papers'][source.paper_id].items() if k in BoardPaper.model_fields})
        binding=BoardSourceBinding(source_id=source.id,paper_id=source.paper_id,version=source.version,source_sha256=source.source_sha256,blocks_sha256=source.blocks_sha256,parser_id=source.parser_id,source_type=source.source_type,status=source.status,block_count=len(source.blocks))
        return HybridSourceContext(reference=ref,paper=paper,source=binding,freshness='historical',block=chunk,run_id=saved.id,candidate_id=candidate_id)
    def delete_workspace(self,workspace):
        with self._lock:
            for (owner,_),event in self._cancel.items():
                if owner==workspace:event.set()
        with self.db() as db:
            db.execute('INSERT OR IGNORE INTO hybrid_deleted VALUES(?)',(workspace,))
            db.execute('DELETE FROM hybrid_runs WHERE workspace_id=?',(workspace,));db.execute('DELETE FROM hybrid_jobs_v1 WHERE workspace_id=?',(workspace,))
