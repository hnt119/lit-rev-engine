"""Explicit opt-in, revision-pinned, local-only paper embedding adapter.

No optional library import or model construction happens during core/API import.
The legitimate Hugging Face cache uses symlinks; resolve only the exact pinned
snapshot and let local-files-only loading consume its recorded files.
"""
from importlib import metadata
import os
import hashlib
import json
from pathlib import Path
from threading import Lock

from ..mapping import BGE_REVISION, EmbeddedPaper, EmbeddingProfile, validate_vector
from ..ports import MvpError

REQUIRED_FILES = ("config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json", "modules.json", "1_Pooling/config.json", "sentence_bert_config.json", "config_sentence_transformers.json", "special_tokens_map.json", "vocab.txt")


def runtime_versions():
    versions = {}
    for name in ("sentence-transformers", "torch", "transformers", "huggingface-hub", "numpy", "scikit-learn", "umap-learn", "scipy", "numba", "pynndescent", "llvmlite", "tokenizers", "safetensors"):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    return versions


class LocalPaperEmbedder:
    def __init__(self, *, enabled=False, cache_dir=None):
        self.enabled = enabled
        self.cache_dir = Path(cache_dir or os.environ.get("HF_HUB_CACHE") or Path(os.environ.get("HF_HOME", Path.home() / ".cache/huggingface")) / "hub")
        self.snapshot = self.cache_dir / "models--BAAI--bge-small-en-v1.5" / "snapshots" / BGE_REVISION
        self._versions = runtime_versions()
        self._profile = None
        self._model, self._lock = None, Lock()

    def readiness(self):
        if not self.enabled:
            return False, "Setup required: enable Semantic Maps in Settings, then check the mapping runtime and pinned BGE weights."
        if any(self._versions[name] == "not-installed" for name in self._versions):
            return False, "Setup required: install the isolated optional mapping requirements."
        if not all((self.snapshot / name).is_file() for name in REQUIRED_FILES):
            return False, "Setup required: the exact pinned local BGE model/tokenizer snapshot is missing. No automatic download is performed."
        return True, "Pinned local paper_bge_v1 profile is configured; models load only on explicit map work."

    def _file_hashes(self):
        result = {}
        for name in REQUIRED_FILES:
            path = (self.snapshot / name).resolve(strict=True)
            repository = self.snapshot.parent.parent.resolve()
            if not (path.is_relative_to(repository / "blobs") or path.is_relative_to(self.snapshot.resolve())):
                raise MvpError("embedding_profile_mismatch", "Pinned snapshot references a file outside its local model cache.")
            hasher = hashlib.sha256()
            with path.open("rb") as file:
                for chunk in iter(lambda: file.read(1024 * 1024), b""):
                    hasher.update(chunk)
            result[name] = hasher.hexdigest()
        return result

    @property
    def profile(self):
        if self._profile is None:
            ready, reason = self.readiness()
            if not ready:
                raise MvpError("map_setup_required", reason)
            self._profile = EmbeddingProfile(runtime_versions=self._versions, files_sha256=self._file_hashes())
        return self._profile

    def _load(self):
        ready, reason = self.readiness()
        if not ready:
            raise MvpError("map_setup_required", reason)
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer
                # Fixed snapshot path avoids resolving remote refs. Revision is
                # still recorded and explicitly passed for both model/tokenizer.
                if self._file_hashes() != self.profile.files_sha256:
                    raise MvpError("embedding_profile_changed", "Local model files changed after this map profile was bound.")
                model = SentenceTransformer(str(self.snapshot), revision=BGE_REVISION,
                    local_files_only=True, trust_remote_code=False, device="cpu")
                if model.get_embedding_dimension() != self.profile.dimension or model.max_seq_length != self.profile.max_sequence_tokens:
                    raise MvpError("embedding_profile_mismatch", "Local model dimensions or sequence policy differ from the pinned profile.")
                self._model = model
        return self._model

    def embed(self, representation, checkpoint):
        model = self._load()
        import torch
        tokenizer = model.tokenizer
        ids = tokenizer.encode(representation.input_text, add_special_tokens=False, truncation=False, verbose=False)
        if not ids:
            raise MvpError("embedding_empty", "This paper has no usable representation tokens.")
        content_size = self.profile.max_sequence_tokens - tokenizer.num_special_tokens_to_add(pair=False)
        if content_size != self.profile.content_window_tokens:
            raise MvpError("embedding_profile_mismatch", "Tokenizer special-token policy differs from the recorded profile.")
        vectors, weights = [], []
        model.eval()
        with torch.inference_mode():
            for start in range(0, len(ids), content_size):
                checkpoint()
                window = ids[start:start + content_size]
                # Preserve every original token ID; decoding/re-encoding can
                # change WordPiece boundaries and silently lose coverage.
                processor = json.loads(tokenizer.backend_tokenizer.post_processor.__getstate__())
                expected_single = [{"SpecialToken": {"id": "[CLS]", "type_id": 0}}, {"Sequence": {"id": "A", "type_id": 0}}, {"SpecialToken": {"id": "[SEP]", "type_id": 0}}]
                if tokenizer.cls_token_id != 101 or tokenizer.sep_token_id != 102 or processor.get("single") != expected_single:
                    raise MvpError("embedding_profile_mismatch", "Pinned BERT tokenizer special-token template changed.")
                complete = [tokenizer.cls_token_id, *window, tokenizer.sep_token_id]
                if len(complete) > self.profile.max_sequence_tokens:
                    raise MvpError("embedding_window_limit", "A tokenizer window exceeded the pinned model limit.")
                features = {"input_ids": torch.tensor([complete], dtype=torch.long),
                            "attention_mask": torch.ones((1, len(complete)), dtype=torch.long),
                            "token_type_ids": torch.zeros((1, len(complete)), dtype=torch.long)}
                result = model(features)["sentence_embedding"][0].detach().cpu().tolist()
                vectors.append(validate_vector(result, self.profile.dimension))
                weights.append(len(window))
        checkpoint()
        total = sum(weights)
        combined = [sum(vector[index] * weight for vector, weight in zip(vectors, weights)) / total for index in range(self.profile.dimension)]
        return EmbeddedPaper(paper_id=representation.paper_id, input_sha256=representation.input_sha256,
                             representation=representation.representation,
                             vector=validate_vector(combined, self.profile.dimension),
                             window_token_weights=weights, token_count=len(ids))
