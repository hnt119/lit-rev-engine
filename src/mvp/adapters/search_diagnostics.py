"""Explicit PubMed ESearch diagnostics; never EFetch or a retained capture."""
from hashlib import sha256
import os
import re
import threading
import time
import xml.etree.ElementTree as ET

from ..contracts import SearchRequest, StructuredError
from ..ports import ProviderFailure
from ..search_plan_contracts import (
    DiagnosticSeed, DiagnosticSeedResult, QueryDiagnosticMessage, QueryDiagnosticReceipt,
)
from .transport import BoundedTransport

MAX_DIAGNOSTIC_BYTES = 2 * 1024 * 1024
MAX_DIAGNOSTIC_SECONDS = 12


def _unchecked_seeds(seeds, preview):
    return [DiagnosticSeedResult(seed=seed,
        query_membership='unresolved' if seed.pmid is None else 'not_checked',
        preview_recovery=('not_checked' if preview is None or seed.pmid is None
                          else 'present' if seed.pmid in preview else 'absent'),
        reason=('This DOI has no established PMID; no identity guess was performed.'
                if seed.pmid is None else 'Explicit query membership was not established; diagnostic samples are not a recall denominator.'))
        for seed in seeds]


def parse_diagnostic_esearch(payload: bytes, sample_limit: int = 5):
    """Allow typed ESearch errors without weakening the existing provider parser."""
    if not isinstance(payload, bytes) or len(payload) > MAX_DIAGNOSTIC_BYTES:
        raise ProviderFailure('diagnostic_response_limit', 'Query diagnostic response exceeded its size bound.')
    try:
        text = payload.decode('utf-8-sig')
        if re.search(r'<!ENTITY\b', text, re.I):
            raise ProviderFailure('unsafe_xml', 'Query diagnostic XML entity declarations are unsupported.')
        root = ET.fromstring(text)
    except (UnicodeError, ET.ParseError, ValueError):
        raise ProviderFailure('diagnostic_malformed_xml', 'Query diagnostic response was not valid UTF-8 XML.') from None
    if root.tag != 'eSearchResult':
        raise ProviderFailure('diagnostic_response_mismatch', 'Query diagnostic response was not an ESearch result.')
    messages = []
    for tag, severity in (('ErrorList', 'error'), ('WarningList', 'warning')):
        groups = root.findall(tag)
        if len(groups) > 1:
            raise ProviderFailure('diagnostic_response_mismatch', 'Query diagnostic response contained duplicate message groups.')
        for group in groups:
            for child in group:
                message = ''.join(child.itertext()).strip()
                if len(message) > 2000 or len(str(child.tag)) > 100 or len(messages) >= 50:
                    raise ProviderFailure('diagnostic_response_limit', 'Query diagnostic messages exceeded their size bound.')
                messages.append(QueryDiagnosticMessage(code=str(child.tag), message=message, severity=severity))
    for child in root.findall('ERROR') + root.findall('Error'):
        message = ''.join(child.itertext()).strip()
        if len(message) > 2000 or len(messages) >= 50:
            raise ProviderFailure('diagnostic_response_limit', 'Query diagnostic messages exceeded their size bound.')
        messages.append(QueryDiagnosticMessage(code='ERROR', message=message, severity='error'))
    errors = any(item.severity == 'error' for item in messages)

    def one(tag, optional=False):
        items = root.findall(tag)
        if len(items) > 1 or (not items and not optional):
            raise ProviderFailure('diagnostic_response_mismatch', 'Query diagnostic response had missing or duplicate result metadata.')
        return items[0] if items else None

    translation_node = one('QueryTranslation', optional=True)
    translation = ''.join(translation_node.itertext()) if translation_node is not None else None
    if translation is not None and len(translation) > 20000:
        raise ProviderFailure('diagnostic_response_limit', 'Query translation exceeded its size bound.')
    count_node = one('Count', optional=errors)
    if count_node is None:
        return dict(reported_count=None, sample_pmids=[], query_translation=translation,
                    messages=messages, status='provider_error', truncated_sample=None)

    def integer(node):
        value = node.text or ''
        if not re.fullmatch(r'[0-9]{1,20}', value):
            raise ProviderFailure('diagnostic_response_mismatch', 'Query diagnostic result counts were invalid.')
        return int(value)

    total = integer(count_node)
    retmax, start = integer(one('RetMax')), integer(one('RetStart'))
    ids_node = one('IdList')
    ids = [child.text or '' for child in ids_node]
    if (start != 0 or retmax > sample_limit or len(ids) != retmax
        or len(ids) > min(total, sample_limit)
        or any(child.tag != 'Id' for child in ids_node)
        or any(not re.fullmatch(r'[1-9][0-9]{0,19}', value) for value in ids)
        or len(set(ids)) != len(ids)):
        raise ProviderFailure('diagnostic_response_mismatch', 'Query diagnostic sample metadata or PubMed identifiers did not match.')
    return dict(reported_count=total, sample_pmids=ids, query_translation=translation,
                messages=messages, status='provider_error' if errors else 'succeeded',
                truncated_sample=total > len(ids))


class PubMedSearchDiagnostics:
    """One main request and at most one explicit, bounded seed-membership request."""
    def __init__(self, *, email=None, api_key=None, tool='lit-rev-engine-mvp',
                 transport=None, enabled=None, monotonic=time.monotonic,
                 max_runtime_seconds=MAX_DIAGNOSTIC_SECONDS):
        from .pubmed import PubMedPreviewProvider
        self.enabled = bool(email) if enabled is None else bool(enabled)
        self.reason = ('Explicit PubMed ESearch diagnostics are configured; they run only when requested.'
                       if self.enabled else 'Configure NCBI_EMAIL to enable explicit live query diagnostics.')
        if not isinstance(max_runtime_seconds, (int, float)) or isinstance(max_runtime_seconds, bool) or not 0 < max_runtime_seconds <= MAX_DIAGNOSTIC_SECONDS:
            raise ValueError('Diagnostic runtime must be positive and at most twelve seconds')
        self._monotonic, self._runtime = monotonic, max_runtime_seconds
        self._slot = threading.BoundedSemaphore(1)
        self._transport = transport
        self._email, self._api_key, self._tool = email, api_key, tool
        if self.enabled:
            # Reuse operational validation, without a provider search or EFetch.
            provider = PubMedPreviewProvider(email=email, api_key=api_key, tool=tool,
                transport=transport or BoundedTransport(timeout=5, max_attempts=1,
                                                       max_response_bytes=MAX_DIAGNOSTIC_BYTES))
            self._transport = provider._transport

    @classmethod
    def from_environment(cls, environ=None):
        values = os.environ if environ is None else environ
        return cls(email=values.get('NCBI_EMAIL'), api_key=values.get('NCBI_API_KEY'),
                   tool=values.get('NCBI_TOOL', 'lit-rev-engine-mvp'))

    @classmethod
    def from_provider(cls, provider):
        from .pubmed import PubMedPreviewProvider
        if not isinstance(provider, PubMedPreviewProvider):
            return cls(enabled=False)
        # The diagnostic budget uses its own one-attempt transport while sharing
        # the same fixed hosts and process/cross-process provider rate gates.
        return cls(email=provider._email, api_key=provider._api_key, tool=provider._tool)

    def capability(self):
        return dict(enabled=self.enabled, reason=self.reason, max_calls=2,
            max_sample_pmids=5, max_seeds=3, max_runtime_seconds=self._runtime,
            max_response_bytes=MAX_DIAGNOSTIC_BYTES, max_attempts=1,
            endpoint='pubmed_esearch', creates_search_capture=False)

    def check(self, query: str, *, date_from=None, date_to=None, sort='relevance',
              seeds=(), preview_pmids=None) -> QueryDiagnosticReceipt:
        request = SearchRequest(request_id='diagnostic-validation', query=query, date_from=date_from,
                                date_to=date_to, sort=sort, max_results=5)
        if len(seeds) > 3:
            raise ValueError('At most three approved diagnostic seeds are permitted')
        seeds = [item if isinstance(item, DiagnosticSeed) else DiagnosticSeed.model_validate(item) for item in seeds]
        if len({seed.id for seed in seeds}) != len(seeds):
            raise ValueError('Seed IDs must be unique')
        identities = set()
        for seed in seeds:
            supplied = {('pmid', seed.pmid)} if seed.pmid else set()
            if seed.doi:
                supplied.add(('doi', seed.doi))
            if identities.intersection(supplied):
                raise ValueError('Known seed identities cannot be counted twice or relabeled as held-out')
            identities.update(supplied)
        preview = None if preview_pmids is None else set(preview_pmids)
        if preview is not None and (len(preview) > 50 or any(not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]{0,19}', value) for value in preview)):
            raise ValueError('Preview membership requires at most fifty established PubMed identifiers')
        base = dict(query=query, query_sha256=sha256(query.encode('utf-8')).hexdigest(),
                    date_from=date_from, date_to=date_to, sort=sort)
        if not self.enabled:
            return QueryDiagnosticReceipt(**base, status='not_run', calls=0,
                seed_results=_unchecked_seeds(seeds, preview),
                error=StructuredError(code='query_diagnostics_disabled', message=self.reason))
        if not self._slot.acquire(blocking=False):
            return QueryDiagnosticReceipt(**base, status='failed', calls=0,
                seed_results=_unchecked_seeds(seeds, preview),
                error=StructuredError(code='query_diagnostics_busy', message='A bounded diagnostic call is still finishing; no additional call was started.', retryable=True))
        deadline, done, result, calls = self._monotonic() + self._runtime, threading.Event(), [], [0]

        def perform():
            try:
                result.append(self._run(request, seeds, preview, deadline, calls, base))
            except Exception:
                result.append(QueryDiagnosticReceipt(**base, status='failed', calls=calls[0],
                    seed_results=_unchecked_seeds(seeds, preview),
                    error=StructuredError(code='query_diagnostics_failure', message='Query diagnostics failed without creating a search capture.')))
            finally:
                self._slot.release()
                done.set()

        thread = threading.Thread(target=perform, daemon=True, name='bounded-query-diagnostic')
        thread.start()
        if not done.wait(max(0.0, deadline - self._monotonic())):
            return QueryDiagnosticReceipt(**base, status='failed', calls=calls[0],
                seed_results=_unchecked_seeds(seeds, preview),
                error=StructuredError(code='query_diagnostics_timeout', message='Query diagnostics exceeded their bounded runtime; no search capture was created.', retryable=True))
        return result[0]

    def _run(self, request, seeds, preview, deadline, calls, base):
        def fetch(query, limit):
            if self._monotonic() >= deadline:
                raise ProviderFailure('query_diagnostics_timeout', 'Query diagnostics exceeded their bounded runtime.', True)
            params = dict(db='pubmed', term=query, retmax=limit, retstart=0, retmode='xml',
                          sort=request.sort, email=self._email, tool=self._tool)
            if self._api_key:
                params['api_key'] = self._api_key
            if request.date_from:
                params.update(datetype='pdat', mindate=request.date_from.replace('-', '/'),
                              maxdate=request.date_to.replace('-', '/'))
            calls[0] += 1
            payload = self._transport.request('pubmed_search', params)
            if self._monotonic() >= deadline:
                raise ProviderFailure('query_diagnostics_timeout', 'Query diagnostics exceeded their bounded runtime.', True)
            response_sha = sha256(payload).hexdigest()
            try:
                return parse_diagnostic_esearch(payload, limit), response_sha
            except ProviderFailure as failure:
                failure.diagnostic_response_sha256 = response_sha
                raise

        response_sha = None
        try:
            parsed, response_sha = fetch(request.query, 5)
        except ProviderFailure as failure:
            return QueryDiagnosticReceipt(**base, status='failed', calls=calls[0],
                response_sha256=getattr(failure, 'diagnostic_response_sha256', response_sha),
                seed_results=_unchecked_seeds(seeds, preview),
                error=StructuredError(code=failure.code, message='PubMed query diagnostics failed; no search capture was created.', retryable=failure.retryable))
        seed_results, membership_sha, membership_error = [], None, None
        pmids = list(dict.fromkeys(seed.pmid for seed in seeds if seed.pmid))
        member_ids = None
        if pmids and parsed['status'] == 'succeeded':
            membership_query = '(' + request.query + ') AND (' + ' OR '.join(pmid + '[UID]' for pmid in pmids) + ')'
            try:
                membership, membership_sha = fetch(membership_query, len(pmids))
                if membership['status'] != 'succeeded' or membership['reported_count'] != len(membership['sample_pmids']) or not set(membership['sample_pmids']).issubset(pmids):
                    raise ProviderFailure('seed_membership_mismatch', 'Seed membership response did not match the requested PubMed identifiers.')
                member_ids = set(membership['sample_pmids'])
            except ProviderFailure:
                membership_error = StructuredError(code='seed_membership_failed', message='The optional seed membership check failed; diagnostic samples are not a substitute for membership.')
        for seed in seeds:
            if not seed.pmid:
                state, reason = 'unresolved', 'This DOI has no established PMID. No title search or DOI-to-PMID guess was performed.'
            elif member_ids is None:
                state, reason = 'not_checked', 'Explicit seed membership was not established; the diagnostic sample is not a recall denominator.'
            else:
                state = 'matched' if seed.pmid in member_ids else 'not_matched'
                reason = 'Membership in this query was checked with a separate ESearch restricted to the approved seed PMIDs; this does not establish relevance or recall.'
            recovery = 'not_checked' if preview is None or not seed.pmid else ('present' if seed.pmid in preview else 'absent')
            seed_results.append(DiagnosticSeedResult(seed=seed, query_membership=state,
                                                     preview_recovery=recovery, reason=reason))
        return QueryDiagnosticReceipt(**base, **parsed, response_sha256=response_sha,
            membership_response_sha256=membership_sha, seed_results=seed_results,
            calls=calls[0], error=membership_error)
