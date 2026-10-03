"""Bounded cloud Qwen transport. No model download, SDK or ledger dependency."""

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


def api_key_from_env():
    """Read only this provider's credential; never execute dotenv text."""
    if os.environ.get("DEEPINFRA_API_KEY"):
        return os.environ["DEEPINFRA_API_KEY"]
    path = Path(__file__).resolve().parents[2] / ".env"
    if not path.exists():
        return ""
    selected = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        name, separator, value = stripped.partition("=")
        if separator and name.strip() == "DEEPINFRA_API_KEY":
            try:
                words = shlex.split(value, comments=True, posix=True)
            except ValueError:
                raise ValueError("Invalid local DEEPINFRA_API_KEY assignment") from None
            if len(words) > 1:
                raise ValueError("Invalid local DEEPINFRA_API_KEY assignment")
            selected.append(words[0] if words else "")
    if len(selected) > 1:
        raise ValueError("Duplicate local DEEPINFRA_API_KEY assignments")
    return selected[0] if selected else ""


def canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, UnicodeError):
        raise ValueError("Qwen data must be finite valid JSON") from None


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def read_json(content):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    try:
        result = json.loads(content, object_pairs_hook=pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
        canonical(result)
        return result
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise ValueError("Invalid Qwen JSON") from None


@dataclass(frozen=True)
class QwenProfile:
    embedding_model: str = "Qwen/Qwen3-Embedding-4B"
    reranker_model: str = "Qwen/Qwen3-Reranker-4B"
    embedding_url: str = "https://api.deepinfra.com/v1/inference/Qwen/Qwen3-Embedding-4B"
    reranker_url: str = "https://api.deepinfra.com/v1/inference/Qwen/Qwen3-Reranker-4B"
    dimension: int = 2560
    query_instruction: str = "Retrieve source passages relevant to the research question."
    rerank_instruction: str = "Retrieve source passages relevant to the research question."
    max_document_bytes: int = 6000
    max_query_bytes: int = 2000
    batch_size: int = 16
    max_representations: int = 1000
    timeout_seconds: float = 60.0

    def __post_init__(self):
        if self.embedding_model != "Qwen/Qwen3-Embedding-4B" or self.reranker_model != "Qwen/Qwen3-Reranker-4B":
            raise ValueError("This adapter supports the declared Qwen 4B pair only")
        for url in (self.embedding_url, self.reranker_url):
            parts = urlsplit(url)
            if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
                raise ValueError("Qwen endpoints must be HTTPS URLs without credentials, queries or fragments")
        for name, low, high in (("dimension", 32, 2560), ("max_document_bytes", 32, 6000),
                                ("max_query_bytes", 32, 2000), ("batch_size", 1, 16),
                                ("max_representations", 1, 1000)):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError("Invalid Qwen profile " + name)
        if isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, (int, float)) or not math.isfinite(self.timeout_seconds) or not 0 < self.timeout_seconds <= 60:
            raise ValueError("Qwen timeout must be finite and within 60 seconds")
        if not isinstance(self.query_instruction, str) or not self.query_instruction.strip() or len(self.query_instruction.encode("utf-8")) > 512:
            raise ValueError("Qwen query instruction must be nonempty and at most 512 UTF-8 bytes")
        if not isinstance(self.rerank_instruction, str) or not self.rerank_instruction.strip() or len(self.rerank_instruction.encode("utf-8")) > 512:
            raise ValueError("Qwen rerank instruction must be nonempty and at most 512 UTF-8 bytes")

    @classmethod
    def from_env(cls):
        return cls(embedding_url=os.getenv("QWEN_EMBEDDING_URL", cls.embedding_url),
                   reranker_url=os.getenv("QWEN_RERANKER_URL", cls.reranker_url))

    def metadata(self):
        return {"schema_version": 1, **asdict(self), "provider_contract": "deepinfra-qwen4b-v1",
                "embedding_revision": None, "reranker_revision": None,
                "revision_limit": "Managed model aliases; immutable revision is not supplied by this API contract",
                "document_encoding": "unprefixed-within-block-utf8-spans-v1",
                "query_encoding": "Instruct: {instruction}\\nQuery: {query}",
                "pooling": "provider-managed-last-token", "normalization": "local-l2",
                "distance": "cosine", "rerank_encoding": "explicit-instruction-query-document-pairs",
                "length_policy": "Explicit UTF-8 byte ceiling; no client truncation; server tokenization/truncation is not exposed",
                "embedding_order": "one input per native request; no assumed batch ordering"}

    def format_query(self, query):
        validate_text(query, self.max_query_bytes, "query")
        formatted = f"Instruct: {self.query_instruction}\nQuery: {query}"
        validate_text(formatted, self.max_query_bytes, "formatted query")
        return formatted


def validate_text(text, limit, label):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Qwen " + label + " must be nonempty text")
    if len(text.encode("utf-8")) > limit:
        raise ValueError("Qwen " + label + " exceeds its explicit UTF-8 byte budget")


def normalize_vector(vector, dimension):
    if not isinstance(vector, list) or len(vector) != dimension:
        raise ValueError("Qwen embedding dimension mismatch")
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in vector):
        raise ValueError("Qwen embeddings must contain finite numbers")
    norm = math.hypot(*vector)
    if not math.isfinite(norm) or norm == 0:
        raise ValueError("Qwen embedding must have a finite nonzero norm")
    return [value / norm for value in vector]


def embedding_request(profile, texts):
    return {"inputs": texts, "custom_instruction": "", "normalize": False, "dimensions": profile.dimension,
            "service_tier": "default", "fail_fast": True}


def rerank_request(profile, query, texts):
    return {"queries": [query] * len(texts), "documents": texts, "instruction": profile.rerank_instruction,
            "service_tier": "default", "fail_fast": True}


def parse_embeddings(profile, response, count):
    if not isinstance(response, dict) or response.get("model", profile.embedding_model) != profile.embedding_model:
        raise ValueError("Qwen embedding response model mismatch")
    _status(response)
    data = response.get("embeddings")
    if not isinstance(data, list) or len(data) != count:
        raise ValueError("Qwen embedding response count mismatch")
    return [normalize_vector(vector, profile.dimension) for vector in data]


def _status(response):
    if type(response.get("input_tokens")) is not int or response["input_tokens"] < 0:
        raise ValueError("Qwen response must report nonnegative input_tokens")
    status = response.get("inference_status")
    if status is not None:
        if not isinstance(status, dict) or status.get("status", "succeeded") != "succeeded":
            raise ValueError("Qwen inference status is unsuccessful")
        cost = status.get("cost")
        if type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0:
            raise ValueError("Qwen inference cost must be finite and nonnegative")


def parse_scores(profile, response, count):
    if not isinstance(response, dict) or response.get("model", profile.reranker_model) != profile.reranker_model:
        raise ValueError("Qwen reranker response model mismatch")
    _status(response)
    values = response.get("scores")
    if not isinstance(values, list) or len(values) != count or any(type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1 for value in values):
        raise ValueError("Qwen reranker scores must have one finite value per pair")
    return values


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class QwenClient:
    def __init__(self, profile, api_key):
        if not isinstance(profile, QwenProfile):
            raise ValueError("QwenClient requires a QwenProfile")
        if not isinstance(api_key, str) or not api_key.strip() or any(c in api_key for c in "\r\n"):
            raise ValueError("Set DEEPINFRA_API_KEY locally for live Qwen calls")
        self.profile, self._api_key = profile, api_key
        self._opener = build_opener(_NoRedirect())

    def _post(self, url, request):
        serialized = canonical(request)
        if self._api_key in serialized:
            raise ValueError("Qwen request contains the configured credential")
        req = Request(url, data=serialized.encode("utf-8"), method="POST",
                      headers={"Content-Type": "application/json", "Authorization": "Bearer " + self._api_key})
        start = time.monotonic()
        try:
            with self._opener.open(req, timeout=self.profile.timeout_seconds) as stream:
                body = stream.read(8 * 1024 * 1024 + 1)
        except HTTPError as error:
            raise ValueError(f"Qwen endpoint returned HTTP {error.code}; no automatic retry") from None
        except (URLError, TimeoutError, OSError):
            raise ValueError("Qwen endpoint unavailable or timed out; no automatic retry") from None
        if len(body) > 8 * 1024 * 1024:
            raise ValueError("Qwen response exceeds the bounded response size")
        response = read_json(body)
        if self._api_key in canonical(response):
            raise ValueError("Qwen response contains the configured credential")
        return response, time.monotonic() - start

    def embed_documents(self, texts):
        if not isinstance(texts, list) or len(texts) != 1:
            raise ValueError("Native Qwen embeddings use one input per call to bind order explicitly")
        for text in texts:
            validate_text(text, self.profile.max_document_bytes, "document")
        request = embedding_request(self.profile, texts)
        response, elapsed = self._post(self.profile.embedding_url, request)
        return {"request": request, "response": response, "elapsed_seconds": elapsed,
                "values": parse_embeddings(self.profile, response, len(texts))}

    def embed_query(self, query):
        request = embedding_request(self.profile, [self.profile.format_query(query)])
        response, elapsed = self._post(self.profile.embedding_url, request)
        return {"request": request, "response": response, "elapsed_seconds": elapsed,
                "values": parse_embeddings(self.profile, response, 1)}

    def rerank(self, query, texts):
        validate_text(query, self.profile.max_query_bytes, "query")
        if not isinstance(texts, list) or not 1 <= len(texts) <= self.profile.batch_size:
            raise ValueError("Qwen reranker batch size is invalid")
        for text in texts:
            validate_text(text, self.profile.max_document_bytes, "document")
        request = rerank_request(self.profile, query, texts)
        response, elapsed = self._post(self.profile.reranker_url, request)
        return {"request": request, "response": response, "elapsed_seconds": elapsed,
                "values": parse_scores(self.profile, response, len(texts))}
