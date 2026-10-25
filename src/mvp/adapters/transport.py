"""Small, bounded HTTP transport restricted to fixed literature providers.

Default live HTTP additionally shares same-user host gates across local
processes. Web preparation remains in the provider-owning API process. Custom
test openers retain the deterministic in-process clock gates.
No request URL or exception body is exposed to callers (URLs may carry keys).
"""

from __future__ import annotations

import math
import re
import socket
import ssl
import threading
import time
import xml.etree.ElementTree as ET
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPSHandler, HTTPRedirectHandler, Request, build_opener

from src.mvp.ports import ProviderFailure

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_HOST_INTERVALS = {"eutils.ncbi.nlm.nih.gov": 0.4, "www.ebi.ac.uk": 0.25, "api.crossref.org": 1.0}
_HOST_LOCKS = {host: threading.Lock() for host in _HOST_INTERVALS}
_HOST_LAST: dict[str, float] = {}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderFailure("redirect_rejected", "Provider redirects are not followed.")


def endpoint_url(endpoint: str, params: dict) -> tuple[str, dict, str]:
    """Build URLs from a fixed allowlist, never from caller/source URLs."""
    if endpoint in {"pubmed_search", "pubmed_fetch"}:
        name = "esearch.fcgi" if endpoint == "pubmed_search" else "efetch.fcgi"
        return "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/" + name, dict(params), "eutils.ncbi.nlm.nih.gov"
    if endpoint == "europe_search":
        return "https://www.ebi.ac.uk/europepmc/webservices/rest/search", dict(params), "www.ebi.ac.uk"
    if endpoint == "crossref_work" and set(params) == {"doi"}:
        from ..import_contracts import normalize_citation_doi
        try:
            doi = normalize_citation_doi(params["doi"])
            if doi and len(doi) <= 4096:
                return "https://api.crossref.org/works/" + quote(doi, safe=""), {}, "api.crossref.org"
        except (TypeError, ValueError):
            pass
    if endpoint == "europe_fulltext" and set(params) == {"pmcid"}:
        pmcid = params["pmcid"]
        if isinstance(pmcid, str) and re.fullmatch(r"PMC[1-9][0-9]*", pmcid):
            return f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML", {}, "www.ebi.ac.uk"
    raise ProviderFailure("invalid_endpoint", "Unsupported provider endpoint or identifier.")


def safe_xml(payload: bytes, label: str = "Provider") -> ET.Element:
    """Parse UTF-8 XML without expanding declared entities or resolving DTDs."""
    if not isinstance(payload, bytes) or len(payload) > MAX_RESPONSE_BYTES:
        raise ProviderFailure("response_too_large", f"{label} response exceeds the permitted size.")
    try:
        value = payload.decode("utf-8-sig")
    except UnicodeError:
        raise ProviderFailure("malformed_xml", f"{label} response is not UTF-8 XML.") from None
    if re.search(r"<!ENTITY\b", value, re.I):
        raise ProviderFailure("unsafe_xml", f"{label} XML entity declarations are unsupported.")
    try:
        root = ET.fromstring(value)
    except (ET.ParseError, ValueError):
        raise ProviderFailure("malformed_xml", f"{label} returned malformed XML.") from None
    if any(str(e.tag).rsplit("}", 1)[-1].lower() in {"error", "errorlist"} for e in root.iter()):
        raise ProviderFailure("provider_error", f"{label} returned a provider error.")
    return root


class BoundedTransport:
    """Fixed HTTPS endpoints; <=15s attempts, <=2 attempts, <=8MiB responses."""

    def __init__(self, *, timeout: float = 12, max_attempts: int = 2,
                 max_response_bytes: int = MAX_RESPONSE_BYTES, opener=None,
                 sleep=time.sleep, monotonic=time.monotonic):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 15:
            raise ValueError("Provider timeout must be greater than zero and at most 15 seconds")
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= 2:
            raise ValueError("Provider attempts must be one or two")
        if isinstance(max_response_bytes, bool) or not isinstance(max_response_bytes, int) or not 1 <= max_response_bytes <= MAX_RESPONSE_BYTES:
            raise ValueError("Provider response limit must be at most 8 MiB")
        self.timeout, self.max_attempts, self.max_response_bytes = timeout, max_attempts, max_response_bytes
        self._sleep, self._monotonic = sleep, monotonic
        self._shared_gate = opener is None
        if opener is None:
            # macOS framework Python may have no default CA bundle installed.
            # certifi is a small CPU-only MVP dependency, with verified TLS kept on.
            try:
                import certifi
                context = ssl.create_default_context(cafile=certifi.where())
            except ImportError:
                context = ssl.create_default_context()
            opener = build_opener(_NoRedirect(), HTTPSHandler(context=context)).open
        self._open = opener

    def _gate(self, host):
        with _HOST_LOCKS[host]:
            if self._shared_gate:
                from .provider_rate_gate import wait_for_provider
                wait_for_provider(host, _HOST_INTERVALS[host])
                _HOST_LAST[host] = self._monotonic()
                return
            current = self._monotonic()
            remaining = _HOST_INTERVALS[host] - (current - _HOST_LAST.get(host, float("-inf")))
            if remaining > 0:
                self._sleep(remaining)
            _HOST_LAST[host] = self._monotonic()

    def request(self, endpoint: str, params: dict) -> bytes:
        url, query, host = endpoint_url(endpoint, params)
        encoded = urlencode(query).encode("utf-8")
        method = "POST" if endpoint.startswith("pubmed_") else "GET"
        if method == "GET" and encoded:
            url += "?" + encoded.decode("ascii")
        request = Request(url, data=encoded if method == "POST" else None, method=method,
                          headers={"User-Agent": "lit-rev-engine-mvp/0.1", "Accept-Encoding": "identity",
                                   "Content-Type": "application/x-www-form-urlencoded"})
        for attempt in range(self.max_attempts):
            self._gate(host)
            retry_delay = 1
            try:
                with self._open(request, timeout=self.timeout) as response:
                    # Custom openers must not smuggle a redirect response through.
                    if response.geturl() != request.full_url:
                        raise ProviderFailure("redirect_rejected", "Provider redirects are not followed.")
                    status = getattr(response, "status", 200)
                    if status != 200:
                        raise ProviderFailure("http_error", f"Provider HTTP request failed (status {int(status)}).", status == 429 or status >= 500)
                    length = response.headers.get("Content-Length")
                    if length and (not length.isdigit() or int(length) > self.max_response_bytes):
                        raise ProviderFailure("response_too_large", "Provider response exceeds the permitted size.")
                    if response.headers.get("Content-Encoding", "identity").lower() not in {"identity", ""}:
                        raise ProviderFailure("unsupported_encoding", "Provider returned unsupported response compression.")
                    payload = response.read(self.max_response_bytes + 1)
                    if not isinstance(payload, bytes) or len(payload) > self.max_response_bytes:
                        raise ProviderFailure("response_too_large", "Provider response exceeds the permitted size.")
                    return payload
            except ProviderFailure:
                raise
            except HTTPError as error:
                retryable = error.code == 429 or 500 <= error.code <= 599
                if not retryable or attempt + 1 >= self.max_attempts:
                    code = "redirect_rejected" if 300 <= error.code < 400 else "http_error"
                    raise ProviderFailure(code, f"Provider HTTP request failed (status {error.code}).", retryable) from None
                retry_after = error.headers.get("Retry-After") if error.headers else None
                if retry_after and (not retry_after.isdigit() or int(retry_after) > 2):
                    raise ProviderFailure("rate_limited", "Provider rate limit reached; retry this operation later.", True) from None
                if retry_after:
                    retry_delay = max(retry_delay, int(retry_after))
            except (TimeoutError, socket.timeout):
                if attempt + 1 >= self.max_attempts:
                    raise ProviderFailure("timeout", "Provider request timed out after bounded attempts.", True) from None
            except (URLError, OSError):
                if attempt + 1 >= self.max_attempts:
                    raise ProviderFailure("transport_error", "Provider request failed after bounded attempts.", True) from None
            except Exception:
                raise ProviderFailure("transport_error", "Provider request failed.") from None
            self._sleep(retry_delay)
        raise ProviderFailure("transport_error", "Provider request did not complete.")
