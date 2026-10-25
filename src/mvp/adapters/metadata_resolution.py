"""Explicit, exact-ID metadata enrichment, separate from supplied import rows.

No title search, arbitrary URL, redirect or provider fallback is available. A
bounded daemon attempt may finish after a caller deadline; its late response is
discarded and this resolver admits no second attempt until that worker exits.
Only the returned receipt is suitable for publication by an authorized service.
"""
from hashlib import sha256
import json
import math
import re
import threading
import time

from pydantic import ValidationError
from ..contracts import StructuredError, now
from ..import_contracts import (
    CitationMetadata, ResolutionInput, ResolutionReceipt, ResolutionBatch,
    normalize_citation_doi, normalize_pmcid, MAX_METADATA_RESOLUTIONS,
    MAX_METADATA_RESPONSE_BYTES, MAX_METADATA_RUNTIME_SECONDS,
)
from src.review.identity import normalize_pmid
from ..ports import ProviderFailure
from .transport import BoundedTransport, safe_xml


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Ambiguous duplicate JSON field')
        result[key] = value
    return result


def _invalid_json_constant(value):
    raise ValueError('Unsupported non-finite JSON value')


def _ids(row, *, europe=False):
    values = {
        'doi': row.get('doi'),
        'pmid': row.get('pmid') or (row.get('id') if europe and row.get('source') == 'MED' else None),
        'pmcid': row.get('pmcid'),
    }
    result = {}
    for key, normalize in (('doi', normalize_citation_doi), ('pmid', normalize_pmid), ('pmcid', normalize_pmcid)):
        if values[key] is not None and values[key] != '':
            try:
                if not isinstance(values[key], str) or len(values[key]) > (4096 if key == 'doi' else 50):
                    raise ValueError('Identifier shape or size')
                identifier = normalize(values[key])
                if identifier:
                    result[key] = identifier
            except (TypeError, ValueError):
                raise ProviderFailure('invalid_returned_identifier', 'Provider returned a malformed identifier.') from None
    return result


def _identity(requested, returned):
    if any(key in returned and value != returned[key] for key, value in requested.items()):
        return 'conflict', StructuredError(code='identity_mismatch', message='Provider identifiers conflict with the requested paper.')
    if any(key not in returned for key in requested):
        return 'unresolved', StructuredError(code='identity_unconfirmed', message='Provider did not confirm every explicitly requested identifier.')
    return 'resolved', None


def _abstract(value):
    if value is None:
        return '', 'none'
    if not isinstance(value, str):
        raise ProviderFailure('malformed_metadata', 'Provider abstract has an unsupported shape.')
    if re.search(r'</?[A-Za-z][^>]*>', value) or '<!ENTITY' in value.upper() or '<!DOCTYPE' in value.upper():
        # Crossref frequently uses the JATS prefix without declaring it on the
        # fragment. The namespace binding is fixed data, never source supplied.
        root = safe_xml(('<abstract xmlns:jats="http://www.ncbi.nlm.nih.gov/JATS1">' + value + '</abstract>').encode('utf-8'), 'Metadata')
        return ' '.join(' '.join(root.itertext()).split()), 'metadata-xml-fragment-text-v1'
    return value, 'none'


def _crossref(message):
    titles = message.get('title', [])
    if not isinstance(titles, list) or not titles or not isinstance(titles[0], str):
        raise ProviderFailure('metadata_incomplete', 'Resolved metadata has no usable title; manual metadata remains necessary.')
    authors = []
    if not isinstance(message.get('author', []), list):
        raise ProviderFailure('malformed_metadata', 'Provider authors have an unsupported shape.')
    for item in message.get('author', []):
        if not isinstance(item, dict):
            raise ProviderFailure('malformed_metadata', 'Provider authors have an unsupported shape.')
        if any(item.get(key) is not None and not isinstance(item[key], str) for key in ('name', 'family', 'given')):
            raise ProviderFailure('malformed_metadata', 'Provider author names have an unsupported shape.')
        name = item.get('name') or ', '.join(item[key].strip() for key in ('family', 'given') if item.get(key))
        if name:
            authors.append(name)
    year = None
    for field in ('published', 'published-print', 'published-online', 'issued'):
        parts = (message.get(field) or {}).get('date-parts', [])
        if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
            value = parts[0][0]
            if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 9999:
                year = value
                break
    abstract, normalization = _abstract(message.get('abstract'))
    journals = message.get('container-title') or []
    if not isinstance(journals, list) or any(not isinstance(value, str) for value in journals):
        raise ProviderFailure('malformed_metadata', 'Provider journal title has an unsupported shape.')
    ids = _ids({'doi': message.get('DOI')})
    # DOI resolver URLs are fixed and do not inherit provider/source URLs.
    doi = ids.get('doi')
    metadata = CitationMetadata(title=titles[0], authors=authors, year=year, abstract=abstract,
                                url=('https://doi.org/' + doi) if doi else '',
                                publication_title=journals[0] if journals else '', **ids)
    return ids, metadata, normalization


def _europe(row):
    ids = _ids(row, europe=True)
    title = row.get('title')
    if not isinstance(title, str) or not title.strip():
        raise ProviderFailure('metadata_incomplete', 'Resolved metadata has no usable title; manual metadata remains necessary.')
    details = row.get('authorList') or {}
    authors = details.get('author', []) if isinstance(details, dict) else []
    if not isinstance(authors, list):
        raise ProviderFailure('malformed_metadata', 'Provider authors have an unsupported shape.')
    names = []
    for author in authors:
        if not isinstance(author, dict):
            raise ProviderFailure('malformed_metadata', 'Provider authors have an unsupported shape.')
        name = author.get('fullName') or author.get('collectiveName')
        if name:
            names.append(name)
    year_value = row.get('pubYear')
    year = int(year_value) if isinstance(year_value, str) and re.fullmatch(r'[1-9][0-9]{3}', year_value) else None
    abstract, normalization = _abstract(row.get('abstractText'))
    journal_info = row.get('journalInfo') or {}
    journal = journal_info.get('journal') or {} if isinstance(journal_info, dict) else {}
    publication = journal.get('title', '') if isinstance(journal, dict) else ''
    pmid = ids.get('pmid')
    metadata = CitationMetadata(title=title, authors=names, year=year, abstract=abstract,
                                publication_title=publication,
                                url=('https://pubmed.ncbi.nlm.nih.gov/' + pmid + '/') if pmid else '', **ids)
    return ids, metadata, normalization


class ExactMetadataResolver:
    """At most three exact singleton lookups within a <=45-second caller budget.

    Default HTTP has one attempt, a five-second socket timeout and a 2 MiB
    response bound. ``calls`` counts submitted fixed-endpoint requests; no
    hidden application retry or alternate-provider request is made. PMCID-only
    resolution is currently explicitly unsupported (manual metadata works).
    """
    def __init__(self, transport=None):
        self.transport = transport or BoundedTransport(timeout=5, max_attempts=1, max_response_bytes=MAX_METADATA_RESPONSE_BYTES)
        self._slot = threading.BoundedSemaphore(1)

    @staticmethod
    def _requested(item):
        return {name: getattr(item, name) for name in ('doi', 'pmid', 'pmcid') if getattr(item, name)}

    def _one(self, item):
        requested = self._requested(item)
        provider = 'europe_pmc' if item.pmid else 'crossref' if item.doi else 'none'
        base = dict(row_id=item.row_id, requested_identifiers=requested, provider=provider, retrieved_at=now())
        if provider == 'none':
            return ResolutionReceipt(**base, status='unresolved', error=StructuredError(code='unsupported_identifier', message='PMCID-only metadata resolution is not supported; supply a DOI/PMID or manual metadata.'))
        raw = None
        returned = {}
        try:
            if provider == 'crossref':
                raw = self.transport.request('crossref_work', {'doi': item.doi})
            else:
                raw = self.transport.request('europe_search', {'query': 'EXT_ID:' + item.pmid + ' AND SRC:MED', 'format': 'json', 'resultType': 'core', 'pageSize': '5'})
            if not isinstance(raw, bytes) or len(raw) > MAX_METADATA_RESPONSE_BYTES:
                raise ProviderFailure('response_too_large', 'Metadata response exceeds the permitted size.')
            response = json.loads(raw, object_pairs_hook=_unique_json, parse_constant=_invalid_json_constant)
            if not isinstance(response, dict):
                raise ProviderFailure('malformed_metadata', 'Provider returned unsupported metadata JSON.')
            if provider == 'crossref':
                message = response.get('message')
                if response.get('status') != 'ok' or not isinstance(message, dict):
                    raise ProviderFailure('unresolved_identifier', 'The exact DOI did not return supported Crossref metadata.')
                returned = _ids({'doi': message.get('DOI')})
                status, error = _identity(requested, returned)
                if status != 'resolved':
                    return ResolutionReceipt(**base, status=status, error=error, returned_identifiers=returned, response_sha256=sha256(raw).hexdigest())
                returned, metadata, normalization = _crossref(message)
            else:
                result_list = response.get('resultList') or {}
                rows = result_list.get('result') if isinstance(result_list, dict) else None
                if not isinstance(rows, list):
                    raise ProviderFailure('malformed_metadata', 'Provider returned unsupported exact-ID results.')
                if len(rows) != 1 or not isinstance(rows[0], dict):
                    raise ProviderFailure('ambiguous_resolution' if rows else 'unresolved_identifier', 'The exact identifier did not return one unambiguous paper.')
                returned = _ids(rows[0], europe=True)
                status, error = _identity(requested, returned)
                if status != 'resolved':
                    return ResolutionReceipt(**base, status=status, error=error, returned_identifiers=returned, response_sha256=sha256(raw).hexdigest())
                returned, metadata, normalization = _europe(rows[0])
            if not metadata.title.strip():
                raise ProviderFailure('metadata_incomplete', 'Resolved metadata has no usable title; manual metadata remains necessary.')
            return ResolutionReceipt(**base, status='resolved', returned_identifiers=returned, metadata=metadata,
                                     response_sha256=sha256(raw).hexdigest(), normalization=normalization,
                                     abstract_origin=(provider + '_metadata_abstract') if metadata.abstract else None)
        except ProviderFailure as error:
            failure = StructuredError(code=error.code, message='The fixed-provider metadata lookup did not establish usable metadata.', retryable=error.retryable)
        except (ValueError, TypeError, KeyError, AttributeError, ValidationError, RecursionError):
            failure = StructuredError(code='malformed_metadata', message='Provider returned malformed or out-of-policy metadata.')
        except Exception:
            failure = StructuredError(code='metadata_provider_failure', message='The fixed-provider metadata lookup failed.')
        return ResolutionReceipt(**base, status='unresolved', returned_identifiers=returned, error=failure,
                                 response_sha256=sha256(raw).hexdigest() if isinstance(raw, bytes) else None)

    def resolve(self, inputs: list[ResolutionInput], max_runtime_seconds=MAX_METADATA_RUNTIME_SECONDS) -> ResolutionBatch:
        if not isinstance(inputs, list) or not 1 <= len(inputs) <= MAX_METADATA_RESOLUTIONS:
            raise ValueError('Resolve between one and three explicitly selected rows at a time')
        if isinstance(max_runtime_seconds, bool) or not isinstance(max_runtime_seconds, (int, float)) or not math.isfinite(max_runtime_seconds) or not 0 < max_runtime_seconds <= MAX_METADATA_RUNTIME_SECONDS:
            raise ValueError('Metadata resolution runtime must be positive and at most 45 seconds')
        # Revalidate even model_copy() inputs before admitting any provider work.
        inputs = [ResolutionInput.model_validate(item.model_dump() if isinstance(item, ResolutionInput) else item) for item in inputs]
        if len({item.row_id for item in inputs}) != len(inputs):
            raise ValueError('Resolution rows must be distinct')
        started = time.monotonic()
        deadline = started + max_runtime_seconds
        finished, stop, mutex = threading.Event(), threading.Event(), threading.Lock()
        completed = {}
        calls = 0
        if not self._slot.acquire(blocking=False):
            return ResolutionBatch(items=[ResolutionReceipt(row_id=item.row_id, status='unresolved', provider='none',
                                   requested_identifiers=self._requested(item), retrieved_at=now(),
                                   error=StructuredError(code='resolver_busy', message='A prior bounded metadata attempt is still finishing; retry explicitly.', retryable=True)) for item in inputs],
                                   elapsed_seconds=time.monotonic() - started, calls=0)

        def work():
            nonlocal calls
            try:
                for item in inputs:
                    with mutex:
                        if stop.is_set() or time.monotonic() >= deadline:
                            break
                        if item.pmid or item.doi:
                            calls += 1
                    result = self._one(item)
                    with mutex:
                        if stop.is_set() or time.monotonic() >= deadline:
                            break
                        completed[item.row_id] = result
            finally:
                self._slot.release()
                finished.set()

        threading.Thread(target=work, name='mvp-exact-metadata-resolution', daemon=True).start()
        finished.wait(max(0, deadline - time.monotonic()))
        stop.set()
        with mutex:
            results, submitted = dict(completed), calls
        exhausted = len(results) != len(inputs)
        items = [results.get(item.row_id) or ResolutionReceipt(row_id=item.row_id, status='unresolved', provider='none',
                 requested_identifiers=self._requested(item), retrieved_at=now(),
                 error=StructuredError(code='resolution_runtime_limit', message='Metadata lookup exceeded its runtime budget; any late response is discarded.', retryable=True)) for item in inputs]
        return ResolutionBatch(items=items, elapsed_seconds=time.monotonic() - started, calls=submitted, budget_exhausted=exhausted)
