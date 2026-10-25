"""Optional offline native adapters. No model-stack imports or calls at module import.

PackManager verifies immutable local files before construction. This module never
truncates, downloads, executes remote code, or substitutes a generation service.
"""
from contextlib import contextmanager
from copy import deepcopy
import errno
import gc
from importlib.metadata import version, PackageNotFoundError
import math
from pathlib import Path
import sqlite3
import subprocess
import threading
import time
from ..ports import MvpError

QWEN_PROFILE = 'hybrid_qwen3_06b_rrf_rerank_v1'
MEDCPT_PROFILE = 'hybrid_medcpt_passage_rrf_rerank_v1'
QWEN_EMBEDDING = 'Qwen/Qwen3-Embedding-0.6B'
QWEN_RERANKER = 'Qwen/Qwen3-Reranker-0.6B'
MEDCPT_QUERY = 'ncbi/MedCPT-Query-Encoder'
MEDCPT_ARTICLE = 'ncbi/MedCPT-Article-Encoder'
MEDCPT_CROSS = 'ncbi/MedCPT-Cross-Encoder'
RETRIEVAL_INSTRUCTION = 'Given a web search query, retrieve relevant passages that answer the query'
QWEN_INPUT_TOKENS, QWEN_QUERY_TOKENS = 1024, 256
MEDCPT_QUERY_TOKENS, MEDCPT_INPUT_TOKENS = 64, 512
DOCUMENT_BATCH_SIZE = 2
QWEN_PREFIX = ('<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct provided. '
               'Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n')
QWEN_SUFFIX = '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'
_MODEL_GATE = threading.BoundedSemaphore(1)


def _model_failure_diagnostic(error, phase):
    """Static operational classification; exception payloads stay private.

    Unknown subclasses/codes remain unknown. Even source text, paths, tensor
    values or custom exception names in an error cannot enter the public suffix.
    """
    kinds = ((MemoryError, 'memory_error'), (OSError, 'os_error'), (PermissionError, 'permission_error'),
        (FileNotFoundError, 'file_not_found'), (BlockingIOError, 'blocking_io_error'),
        (RuntimeError, 'runtime_error'), (ValueError, 'value_error'), (TypeError, 'type_error'),
        (ImportError, 'import_error'), (ModuleNotFoundError, 'module_not_found'),
        (KeyError, 'key_error'), (AttributeError, 'attribute_error'), (NameError, 'name_error'),
        (IndexError, 'index_error'), (NotImplementedError, 'not_implemented'),
        (AssertionError, 'assertion_error'), (StopIteration, 'stop_iteration'),
        (subprocess.CalledProcessError, 'process_error'), (subprocess.TimeoutExpired, 'process_timeout'),
        (UnicodeEncodeError, 'unicode_encode_error'), (UnicodeDecodeError, 'unicode_decode_error'),
        (sqlite3.OperationalError, 'sqlite_operational_error'), (sqlite3.DatabaseError, 'sqlite_database_error'))
    kind = next((name for cls, name in kinds if type(error) is cls), 'unknown')
    category, code = 'unknown', 'none'
    if type(error) is MemoryError:
        category = 'memory'
    elif type(error) is sqlite3.OperationalError or type(error) is sqlite3.DatabaseError:
        category = 'storage'
    elif type(error) is UnicodeEncodeError or type(error) is UnicodeDecodeError:
        category = 'encoding'
    if type(error) is KeyError:
        names = {'USERNAME': 'env_user', 'COMSPEC': 'env_shell', 'NUMBER_OF_PROCESSORS': 'env_cpu',
            'SYSTEMROOT': 'env_system', 'WINDIR': 'env_windows', 'APPDATA': 'env_app',
            'LOCALAPPDATA': 'env_local', 'TEMP': 'env_temp', 'TMP': 'env_tmp',
            'USERPROFILE': 'env_profile', 'HOMEDRIVE': 'env_drive', 'HOMEPATH': 'env_home'}
        args = error.args
        if type(args) is tuple and len(args) == 1 and type(args[0]) is str and args[0] in names:
            category, code = 'environment', names[args[0]]
    windows = {1455: ('memory', 'win1455'), 8: ('memory', 'win8'), 14: ('memory', 'win14'),
        5: ('permission', 'win5'), 32: ('locking', 'win32'), 33: ('locking', 'win33')}
    portable = {errno.ENOMEM: ('memory', 'errno_enomem'), errno.EACCES: ('permission', 'errno_eacces'),
        errno.EPERM: ('permission', 'errno_eperm'), errno.EBUSY: ('locking', 'errno_ebusy'),
        errno.EAGAIN: ('locking', 'errno_eagain')}
    for attribute, allowed in (('winerror', windows), ('errno', portable)):
        try:
            value = getattr(error, attribute, None)
        except Exception:
            value = None
        if type(value) is int and value in allowed:
            category, code = allowed[value]
            break
    if category == 'unknown':
        # Inspect bounded plain-string arguments only; never call str/repr on
        # an exception, an argument or a source-controlled custom object.
        try:
            args = error.args
        except Exception:
            args = ()
        if type(args) is tuple:
            phrases = ('defaultcpuallocator: not enough memory', "defaultcpuallocator: can't allocate memory",
                'cuda out of memory', 'mps backend out of memory')
            if any(phrase in value[:4096].lower() for value in args[:4] if type(value) is str for phrase in phrases):
                category = 'memory'
    safe_phase = phase if phase in {'loading', 'progress', 'weights', 'placing', 'cancel', 'execution'} else 'unknown'
    return f'phase={safe_phase}; kind={kind}; category={category}; os_code={code}'


def qwen_query(query):
    return f'Instruct: {RETRIEVAL_INSTRUCTION}\nQuery:{query}'


def qwen_instruction(query, document):
    return f'<Instruct>: {RETRIEVAL_INSTRUCTION}\n<Query>: {query}\n<Document>: {document}'


def qwen_document(title, text):
    return title + '\n' + text if title else text


def medcpt_document(title, text):
    # Official article text concatenation; replacing abstract with retained passage
    # is the explicitly versioned experimental passage adaptation.
    return title + '. ' + text if title else text


def last_token_pool(hidden, attention_mask):
    """Publisher's last-valid-token pooling for left OR right padding."""
    import torch
    if bool((attention_mask[:, -1].sum() == attention_mask.shape[0]).item()):
        return hidden[:, -1]
    lengths = attention_mask.sum(dim=1) - 1
    return hidden[torch.arange(hidden.shape[0], device=hidden.device), lengths]


def _runtime():
    try:
        import torch
        import transformers
    except ImportError:
        raise MvpError('retrieval_runtime_missing', 'Install the optional pinned neural retrieval runtime explicitly; core lexical remains available.') from None
    return torch, transformers


def _nonblank(value):
    return isinstance(value, str) and bool(value.strip())


class NeuralAdapter:
    """A concrete Qwen adapter or complete three-component MedCPT adapter.

    Every forward pass uses explicit float32, eager attention and inference mode.
    Each method unloads its model before loading another component. Returned
    vectors contain CPU floats; the caller owns the persistent exact index.
    """
    def __init__(self, profile_id, model_dirs, manifest, device='cpu'):
        if profile_id not in {QWEN_PROFILE, MEDCPT_PROFILE}:
            raise MvpError('retrieval_profile_unknown', 'Select an allowlisted immutable retrieval profile.')
        if device not in {'cpu', 'mps'}:
            raise MvpError('retrieval_device_unsupported', 'Select CPU or explicitly tested Apple MPS; automatic backend fallback is disabled.')
        self.profile_id, self.manifest, self.device = profile_id, deepcopy(manifest), device
        self.dimension = 1024 if profile_id == QWEN_PROFILE else 768
        self.dense_metric = 'normalized_inner_product' if profile_id == QWEN_PROFILE else 'inner_product'
        self._torch, self._transformers = _runtime()
        if device == 'mps' and not self._torch.backends.mps.is_available():
            raise MvpError('retrieval_mps_unsupported', 'Apple MPS is unavailable; select CPU explicitly. No backend was substituted.')
        self._repos = ({'query': QWEN_EMBEDDING, 'document': QWEN_EMBEDDING, 'reranker': QWEN_RERANKER}
            if profile_id == QWEN_PROFILE else {'query': MEDCPT_QUERY, 'document': MEDCPT_ARTICLE, 'reranker': MEDCPT_CROSS})
        if not set(self._repos.values()) <= set(model_dirs):
            raise MvpError('retrieval_pack_incomplete', 'The selected profile requires every pinned encoder and reranker.')
        self._dirs = {role: Path(model_dirs[repo]).resolve() for role, repo in self._repos.items()}
        if any(not path.is_dir() for path in self._dirs.values()):
            raise MvpError('retrieval_pack_missing', 'Install and verify the complete selected pack before retrieval.')
        self._tokenizers, by_repo = {}, {}
        for role, repo in self._repos.items():
            if repo not in by_repo:
                try:
                    by_repo[repo] = self._transformers.AutoTokenizer.from_pretrained(str(self._dirs[role]),
                        local_files_only=True, trust_remote_code=False,
                        **({'padding_side': 'left'} if profile_id == QWEN_PROFILE else {}))
                except Exception:
                    raise MvpError('retrieval_tokenizer_invalid', 'The installed pinned tokenizer could not be opened locally. No fallback ran.') from None
            self._tokenizers[role] = by_repo[repo]
        self._cancelled = None
        self._progress = None
        self._executed = {'query_encoder': 0, 'document_encoder': 0, 'reranker': 0}
        self._timing = {'model_load_seconds': 0.0, 'query_encoder_seconds': 0.0, 'document_encoder_seconds': 0.0, 'reranker_seconds': 0.0}
        self._token_counts = {'query_tokens': 0, 'document_tokens': 0, 'reranker_pair_tokens': 0}

    def set_cancelled(self, callback):
        if callback is not None and not callable(callback):
            raise MvpError('retrieval_cancellation_invalid', 'Use an explicit cancellation predicate or guard callback.')
        self._cancelled = callback

    def set_progress(self, callback):
        """Operational notifications only; never part of model/profile metadata."""
        if callback is not None and not callable(callback):
            raise MvpError('retrieval_progress_invalid', 'Use an explicit progress callback.')
        self._progress = callback

    def _report(self, phase, **counters):
        callback = getattr(self, '_progress', None)
        if callback is not None:
            callback(phase=phase, **counters)

    def _check_cancelled(self):
        callback = getattr(self, '_cancelled', None)
        if callback is not None and callback():
            raise MvpError('hybrid_cancelled', 'Neural work was cancelled; no completed result or fallback was published.', True)

    @staticmethod
    def _ids(tokenizer, first, second=None, *, special=True):
        args = (first,) if second is None else (first, second)
        return tokenizer(*args, add_special_tokens=special, truncation=False, padding=False)['input_ids']

    def _qwen_pair_ids(self, query, document):
        tokenizer = self._tokenizers['reranker']
        return (self._ids(tokenizer, QWEN_PREFIX, special=False)
                + self._ids(tokenizer, qwen_instruction(query, document), special=False)
                + self._ids(tokenizer, QWEN_SUFFIX, special=False))

    def validate_query(self, query):
        if not _nonblank(query):
            raise MvpError('retrieval_query_invalid', 'Use a nonblank explicit query; no query was inferred.')
        query.encode('utf-8')
        if self.profile_id == QWEN_PROFILE:
            count = len(self._ids(self._tokenizers['query'], qwen_query(query)))
            if count > QWEN_QUERY_TOKENS or len(self._qwen_pair_ids(query, '')) > QWEN_INPUT_TOKENS:
                raise MvpError('retrieval_query_budget', 'This Qwen profile allows 256 instructed query tokens. Explicitly shorten the question or supply approved component queries; no truncation ran.')
        else:
            count = len(self._ids(self._tokenizers['query'], query))
            cross_count = len(self._ids(self._tokenizers['reranker'], query))
            if count > MEDCPT_QUERY_TOKENS or cross_count > MEDCPT_QUERY_TOKENS:
                raise MvpError('retrieval_query_budget', 'This MedCPT passage profile allows 64 query tokens including special tokens. Explicitly shorten the question or supply approved component queries; no truncation ran.')
        return count

    def fits_document(self, title, text):
        """Query-independent full-input checks, reserving the entire query policy."""
        if not isinstance(title, str) or not _nonblank(text):
            return False
        title.encode('utf-8'); text.encode('utf-8')
        if self.profile_id == QWEN_PROFILE:
            doc = qwen_document(title, text)
            return (len(self._ids(self._tokenizers['document'], doc)) <= QWEN_INPUT_TOKENS
                and len(self._qwen_pair_ids('', doc)) + QWEN_QUERY_TOKENS <= QWEN_INPUT_TOKENS)
        article = len(self._ids(self._tokenizers['document'], title, text))
        cross_document = len(self._ids(self._tokenizers['reranker'], medcpt_document(title, text), special=False))
        special = self._tokenizers['reranker'].num_special_tokens_to_add(pair=True)
        # Conservative: reserve full 64 incl query special tokens plus pair specials.
        return article <= MEDCPT_INPUT_TOKENS and cross_document + MEDCPT_QUERY_TOKENS + special <= MEDCPT_INPUT_TOKENS

    def _documents(self, docs):
        if not isinstance(docs, (list, tuple)) or any(not isinstance(doc, (list, tuple)) or len(doc) != 2 for doc in docs):
            raise MvpError('retrieval_documents_invalid', 'Use exact title/passage input pairs.')
        if any(not self.fits_document(title, text) for title, text in docs):
            raise MvpError('retrieval_document_budget', 'A complete title/passage/template exceeds the model budget. Split the canonical passage with exact offsets or revise the explicit input; no evidence was truncated.')

    @contextmanager
    def _model(self, role):
        self._check_cancelled()
        if not _MODEL_GATE.acquire(blocking=False):
            raise MvpError('retrieval_runtime_busy', 'Another neural component is executing. Retry this explicit local operation.', True)
        model = None
        phase = 'progress'
        try:
            started = time.monotonic()
            self._report("loading_model", component=role)
            phase = 'weights'
            path, tx, torch = self._dirs[role], self._transformers, self._torch
            if self.profile_id == MEDCPT_PROFILE and role == 'reranker':
                major_minor = tuple(int(part) for part in torch.__version__.split('+')[0].split('.')[:2])
                if major_minor < (2, 6):
                    raise MvpError('retrieval_runtime_unsafe', 'The pinned MedCPT Cross Encoder requires Torch 2.6 or later for restricted weights-only loading.')
                config = tx.AutoConfig.from_pretrained(str(path), local_files_only=True, trust_remote_code=False)
                model = tx.AutoModelForSequenceClassification.from_config(config, trust_remote_code=False, attn_implementation='eager')
                state = torch.load(path / 'pytorch_model.bin', weights_only=True, map_location='cpu')
                if not isinstance(state, dict) or not state or any(not isinstance(key, str) or not torch.is_tensor(value) for key, value in state.items()):
                    raise MvpError('retrieval_weights_invalid', 'The verified model did not contain a plain tensor state dictionary.')
                model.load_state_dict(state, strict=True)
                del state
            else:
                cls = tx.AutoModelForCausalLM if role == 'reranker' else tx.AutoModel
                model = cls.from_pretrained(str(path), local_files_only=True, trust_remote_code=False,
                    use_safetensors=True, dtype=torch.float32, attn_implementation='eager')
            phase = 'placing'
            model = model.to(device=self.device, dtype=torch.float32).eval()
            self._timing['model_load_seconds'] += time.monotonic() - started
            phase = 'cancel'
            self._check_cancelled()
            phase = 'execution'
            yield model
        except MvpError:
            raise
        except Exception as error:
            diagnostic = _model_failure_diagnostic(error, phase)
            raise MvpError('retrieval_model_failed', 'The selected local model failed to execute. '
                + 'Diagnostic: ' + diagnostic + '. Inspect the runtime check or select lexical explicitly; no fallback ran.') from None
        finally:
            if model is not None:
                del model
            gc.collect()
            try:
                if self.device == 'mps':
                    self._torch.mps.synchronize()
                    self._torch.mps.empty_cache()
            finally:
                _MODEL_GATE.release()

    def _batch(self, role, items, *, paired=False):
        tokenizer = self._tokenizers[role]
        args = ([item[0] for item in items], [item[1] for item in items]) if paired else (items,)
        encoded = tokenizer(*args, padding=True, truncation=False, return_tensors='pt')
        return {key: value.to(self.device) for key, value in encoded.items()}

    def _vectors(self, role, inputs, *, paired=False):
        vectors, stage, started = [], 'query_encoder' if role == 'query' else 'document_encoder', time.monotonic()
        total_batches = (len(inputs) + DOCUMENT_BATCH_SIZE - 1) // DOCUMENT_BATCH_SIZE
        with self._model(role) as model, self._torch.inference_mode():
            self._report('embedding' if role == 'document' else 'encoding_query', component=role, completed_batches=0, total_batches=total_batches, processed_items=0, total_items=len(inputs))
            for begin in range(0, len(inputs), DOCUMENT_BATCH_SIZE):
                self._check_cancelled()
                batch = self._batch(role, inputs[begin:begin + DOCUMENT_BATCH_SIZE], paired=paired)
                hidden = model(**batch, **({'use_cache': False} if self.profile_id == QWEN_PROFILE else {})).last_hidden_state
                self._check_cancelled()
                values = last_token_pool(hidden, batch['attention_mask']) if self.profile_id == QWEN_PROFILE else hidden[:, 0, :]
                if self.profile_id == QWEN_PROFILE:
                    values = self._torch.nn.functional.normalize(values, p=2, dim=1)
                if values.shape[-1] != self.dimension or not bool(self._torch.isfinite(values).all().item()):
                    raise MvpError('retrieval_vectors_invalid', 'The model returned nonfinite values or an unexpected dimension.')
                vectors.extend(values.detach().cpu().float().tolist())
                self._executed[stage] += len(inputs[begin:begin + DOCUMENT_BATCH_SIZE])
                self._token_counts['query_tokens' if role == 'query' else 'document_tokens'] += int(batch['attention_mask'].sum().item())
                del batch, hidden, values
                self._report('embedding' if role == 'document' else 'encoding_query', component=role, completed_batches=begin // DOCUMENT_BATCH_SIZE + 1, total_batches=total_batches, processed_items=min(begin + DOCUMENT_BATCH_SIZE,len(inputs)), total_items=len(inputs))
        self._timing[stage + '_seconds'] += time.monotonic() - started
        return vectors

    def encode_queries(self, queries):
        if not isinstance(queries, (list, tuple)):
            raise MvpError('retrieval_query_invalid', 'Supply explicit queries as a list.')
        if not queries:
            return []
        for query in queries:
            self.validate_query(query)
        return self._vectors('query', [qwen_query(query) for query in queries] if self.profile_id == QWEN_PROFILE else list(queries))

    def encode_documents(self, docs):
        self._documents(docs)
        if not docs:
            return []
        inputs = [qwen_document(*doc) for doc in docs] if self.profile_id == QWEN_PROFILE else list(docs)
        return self._vectors('document', inputs, paired=self.profile_id == MEDCPT_PROFILE)

    def rerank(self, query, docs):
        self.validate_query(query)
        self._documents(docs)
        if not docs:
            return []
        tokenizer = self._tokenizers['reranker']
        if self.profile_id == QWEN_PROFILE:
            ids = [self._qwen_pair_ids(query, qwen_document(*doc)) for doc in docs]
            if any(len(item) > QWEN_INPUT_TOKENS for item in ids):
                raise MvpError('retrieval_pair_budget', 'The complete Qwen query/document template exceeds 1024 tokens; no truncation ran.')
            no_id, yes_id = (tokenizer.convert_tokens_to_ids(token) for token in ('no', 'yes'))
            if no_id == yes_id or no_id is None or yes_id is None:
                raise MvpError('retrieval_tokenizer_invalid', 'The pinned reranker tokenizer lacks distinct native yes/no tokens.')
        else:
            pairs = [(query, medcpt_document(*doc)) for doc in docs]
            if any(len(self._ids(tokenizer, *pair)) > MEDCPT_INPUT_TOKENS for pair in pairs):
                raise MvpError('retrieval_pair_budget', 'The complete MedCPT query/document pair exceeds 512 tokens; no truncation ran.')
        result, started = [], time.monotonic()
        total_batches = (len(docs) + DOCUMENT_BATCH_SIZE - 1) // DOCUMENT_BATCH_SIZE
        with self._model('reranker') as model, self._torch.inference_mode():
            self._report('reranking', component='reranker', completed_batches=0, total_batches=total_batches, processed_items=0, total_items=len(docs))
            for begin in range(0, len(docs), DOCUMENT_BATCH_SIZE):
                self._check_cancelled()
                if self.profile_id == QWEN_PROFILE:
                    batch = tokenizer.pad({'input_ids': ids[begin:begin + DOCUMENT_BATCH_SIZE]}, padding=True, return_tensors='pt')
                    batch = {key: value.to(self.device) for key, value in batch.items()}
                    logits = model(**batch, use_cache=False, logits_to_keep=1).logits[:, -1, :]
                    scores = self._torch.stack([logits[:, no_id], logits[:, yes_id]], dim=1).softmax(dim=1)[:, 1]
                else:
                    batch = self._batch('reranker', pairs[begin:begin + DOCUMENT_BATCH_SIZE], paired=True)
                    scores = model(**batch).logits.squeeze(dim=1)
                self._check_cancelled()
                values = scores.detach().cpu().float().tolist()
                if any(not math.isfinite(value) for value in values):
                    raise MvpError('retrieval_scores_invalid', 'The reranker returned nonfinite scores.')
                result.extend(values)
                self._executed['reranker'] += len(values)
                self._token_counts['reranker_pair_tokens'] += int(batch['attention_mask'].sum().item())
                del batch, scores
                if self.profile_id == QWEN_PROFILE:
                    del logits
                self._report('reranking', component='reranker', completed_batches=begin // DOCUMENT_BATCH_SIZE + 1, total_batches=total_batches, processed_items=min(begin + DOCUMENT_BATCH_SIZE,len(docs)), total_items=len(docs))
        self._timing['reranker_seconds'] += time.monotonic() - started
        return result

    def runtime_metadata(self):
        return {**native_runtime_signature(self.profile_id, self.device),
            'executed_items': dict(self._executed), 'timings': dict(self._timing), 'token_usage': dict(self._token_counts)}


def native_runtime_signature(profile_id, device):
    """Stable cache/runtime binding; reads package metadata without importing models."""
    if profile_id not in {QWEN_PROFILE, MEDCPT_PROFILE} or device not in {'cpu', 'mps'}:
        raise MvpError('retrieval_profile_unknown', 'Use a known profile and explicit device.')
    qwen = profile_id == QWEN_PROFILE
    def installed(name):
        try: return version(name)
        except PackageNotFoundError: return None
    return {'implementation': 'native-transformers-offline.v1', 'device': device, 'dtype': 'float32',
            'attention': 'eager', 'causal_logits': 'last-token-only' if qwen else 'not-applicable',
            'kv_cache': False if qwen else 'not-applicable',
            'cancellation_policy': 'cooperative-before-after-component-load-and-forward-batches.v1',
            'document_batch_size': DOCUMENT_BATCH_SIZE, 'torch_version': installed('torch'),
            'transformers_version': installed('transformers'), 'tokenizers_version': installed('tokenizers'),
            'dimension': (1024 if qwen else 768), 'pooling': 'last-valid-token' if qwen else 'CLS-last-hidden-state',
            'normalization': 'L2' if qwen else 'none', 'dense_metric': ('normalized_inner_product' if qwen else 'inner_product'),
            'reranker_score_type': 'normalized_yes_no_relevance' if qwen else 'raw_relevance_logit',
            'query_template_version': 'qwen-native-instruct.v1' if qwen else 'medcpt-short-query.v1',
            'document_template_version': 'qwen-title-newline-passage.v1' if qwen else 'medcpt-title-passage-adaptation.v1',
            'reranker_template_version': 'qwen-native-yes-no.v1' if qwen else 'medcpt-query-title-passage-adaptation.v1',
            'query_instruction': RETRIEVAL_INSTRUCTION if qwen else None,
            'query_token_limit': QWEN_QUERY_TOKENS if qwen else MEDCPT_QUERY_TOKENS,
            'input_token_limit': QWEN_INPUT_TOKENS if qwen else MEDCPT_INPUT_TOKENS,
            'experimental_passage_adaptation': not qwen}
