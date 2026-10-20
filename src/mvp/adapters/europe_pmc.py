"""Exact-identity Europe PMC sources with a conservative CC BY/CC0 gate."""

from __future__ import annotations

import hashlib
import json
import re

from src.mvp.contracts import Block, Paper, PreparedSource, StructuredError, digest, now
from src.mvp.ports import ProviderFailure
from src.review.documents import parse_source_bytes
from src.review.identity import normalize_doi, normalize_pmid

from .transport import BoundedTransport, MAX_RESPONSE_BYTES, safe_xml


def _pmcid(value):
    if not value:
        return None
    normalized = str(value).strip().upper()
    if not re.fullmatch(r"PMC[1-9][0-9]*", normalized):
        raise ValueError("Invalid PMCID")
    return normalized


def _text(element):
    return " ".join("".join(element.itertext()).split()) if element is not None else ""


def _tag(element):
    return str(element.tag).rsplit("}", 1)[-1]


def _children(element, name):
    return [] if element is None else [node for node in element if _tag(node) == name]


def _child(element, name):
    return next(iter(_children(element, name)), None)


def supported_license(value: str | None) -> str | None:
    """A deliberately small allowlist; OA alone is never a reuse license."""
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if re.fullmatch(r"cc[ -]?by(?:[ -]?(?:[1-4]\.0))?", normalized):
        return "CC BY"
    if re.fullmatch(r"cc[ -]?0(?:[ -]?1\.0)?", normalized):
        return "CC0"
    if re.fullmatch(r"https?://creativecommons\.org/licenses/by/[1-4]\.0/?", normalized):
        return normalized.replace("http://", "https://")
    if re.fullmatch(r"https?://creativecommons\.org/publicdomain/zero/1\.0/?", normalized):
        return normalized.replace("http://", "https://")
    return None


def _metadata_ids(row):
    try:
        return {key: value for key, value in {
            "pmid": normalize_pmid(row.get("pmid") or (row.get("id") if row.get("source") == "MED" else None)),
            "doi": normalize_doi(row.get("doi")), "pmcid": _pmcid(row.get("pmcid")),
        }.items() if value}
    except (ValueError, TypeError):
        raise ProviderFailure("identity_mismatch", "Europe PMC returned invalid article identifiers.") from None


def _expected_ids(paper):
    try:
        return {key: value for key, value in {"pmid": paper.pmid, "doi": paper.doi, "pmcid": _pmcid(paper.pmcid)}.items() if value}
    except ValueError:
        raise ProviderFailure("identity_mismatch", "The selected paper has an invalid PMCID.") from None


def _validate_identity(expected, actual):
    shared = set(expected).intersection(actual)
    if not shared or any(expected[key] != actual[key] for key in shared):
        raise ProviderFailure("identity_mismatch", "Retrieved source identity does not match the selected paper.")


def fallback_source(paper: Paper, status: str, reason: str, *, error: ProviderFailure | None = None,
                    provider: str = "europe_pmc", license: str | None = None,
                    retrieved_at: str | None = None, abstract_provenance: dict | None = None) -> PreparedSource:
    """Keep the attempt outcome and the usable text kind as separate facts."""
    text = paper.abstract
    blocks = [Block(id="abstract:1", ordinal=1, text=text,
                    locator={"type": "abstract_block", "section_title": "Abstract", "ordinal": 1})] if text.strip() else []
    content = text.encode("utf-8") if blocks else b""
    identifiers = {key: value for key, value in {"pmid": paper.pmid, "doi": paper.doi, "pmcid": paper.pmcid}.items() if value}
    source_url = f"https://pubmed.ncbi.nlm.nih.gov/{paper.pmid}/" if paper.pmid else (
        f"https://europepmc.org/articles/{paper.pmcid}" if paper.pmcid else "")
    raw_hash = hashlib.sha256(content).hexdigest() if blocks else ""
    return PreparedSource(
        paper_id=paper.id, status=status, source_type="abstract" if blocks else "none",
        provider=provider, source_url=source_url, retrieved_at=retrieved_at or now(), license=license,
        attribution=f"{'; '.join(paper.authors)}. {paper.title}", version=raw_hash or "none",
        source_sha256=raw_hash, blocks_sha256=digest([block.model_dump() for block in blocks]) if blocks else "",
        parser_id="lit-rev-engine.mvp.abstract.v1" if blocks else "",
        parser_metadata={"normalization": "none", "origin": "discovered_citation_abstract", "fallback_reason": reason,
                         **(abstract_provenance or {})},
        source_identifiers=identifiers, blocks=blocks, warnings=[reason],
        error=StructuredError(code=error.code, message=error.message, retryable=error.retryable, paper_id=paper.id) if error else None,
    )


def prepare_permitted_xml(paper: Paper, payload: bytes, metadata: dict, *,
                          retrieved_at: str | None = None, provider: str = "europe_pmc") -> PreparedSource:
    """Validate only the article's own front matter, never its references."""
    expected = _expected_ids(paper)
    resolved = _metadata_ids(metadata)
    _validate_identity(expected, resolved)
    if metadata.get("isOpenAccess") != "Y" or not supported_license(metadata.get("license")):
        raise ProviderFailure("permission_unresolved", "Full-text reuse permission is unresolved or outside the supported CC BY/CC0 licenses.")
    root = safe_xml(payload, "Europe PMC full text")
    if _tag(root) != "article":
        raise ProviderFailure("malformed_xml", "Europe PMC full text requires a JATS article root.")
    fronts = _children(root, "front")
    metas = [meta for front in fronts for meta in _children(front, "article-meta")]
    if len(metas) != 1:
        raise ProviderFailure("identity_mismatch", "Europe PMC full text lacks unambiguous own article metadata.")
    article_meta = metas[0]
    own = {}
    for node in _children(article_meta, "article-id"):
        kind = node.get("pub-id-type", "").strip().lower()
        kind = "pmcid" if kind in {"pmc", "pmcid"} else kind
        if kind not in {"pmid", "doi", "pmcid"}:
            continue
        try:
            value = {"pmid": normalize_pmid, "doi": normalize_doi, "pmcid": _pmcid}[kind](_text(node))
        except ValueError:
            value = None
        if value is None or (kind in own and own[kind] != value):
            raise ProviderFailure("identity_mismatch", "Europe PMC XML has invalid or conflicting own article identifiers.")
        own[kind] = value
    _validate_identity(expected, own)
    _validate_identity(resolved, own)
    if resolved.get("pmcid") and own.get("pmcid") != resolved["pmcid"]:
        raise ProviderFailure("identity_mismatch", "Europe PMC XML does not identify the resolved PMCID in its own metadata.")
    permissions = _child(article_meta, "permissions")
    license_nodes = _children(permissions, "license")
    allowed, restricted = [], False
    for license_node in license_nodes:
        # An embedded license URL is stronger than an OA flag or a free-text hint.
        for node in license_node.iter():
            values = [node.text or "", *node.attrib.values()]
            for value in values:
                if re.search(r"creativecommons\.org/licenses/by-(?:nc|nd|sa)", value, re.I):
                    restricted = True
                match = supported_license(value.strip())
                if match:
                    allowed.append(match)
    if not allowed or restricted:
        raise ProviderFailure("permission_unresolved", "The article XML does not provide an unambiguous supported CC BY/CC0 reuse license.")
    try:
        parsed = parse_source_bytes(payload, "jats_xml")
    except ValueError:
        raise ProviderFailure("malformed_xml", "Europe PMC full text could not be parsed safely.") from None
    # Title/abstract front matter alone must never be presented as full text.
    useful_body = [block for block in parsed["blocks"] if "/body[" in block["locator"].get("path", "")]
    if not useful_body:
        raise ProviderFailure("no_usable_text", "Permitted XML contains no usable article-body text; only an available abstract can be used.")
    blocks = [Block(**block) for block in parsed["blocks"]]
    raw_hash = hashlib.sha256(payload).hexdigest()
    attribution = " ".join(filter(None, [_text(_child(permissions, "copyright-statement")),
        f"{'; '.join(paper.authors)}. {paper.title}", f"DOI: {paper.doi}" if paper.doi else ""]))
    return PreparedSource(
        paper_id=paper.id, status="full_text_retrieved", source_type="full_text", provider=provider,
        source_url=f"https://www.ebi.ac.uk/europepmc/webservices/rest/{resolved['pmcid']}/fullTextXML",
        retrieved_at=retrieved_at or now(), license=next((value for value in allowed if value.startswith("https://")), allowed[0]),
        attribution=attribution, version=raw_hash, source_sha256=raw_hash,
        blocks_sha256=digest([block.model_dump() for block in blocks]), parser_id=parsed["parser_id"],
        parser_metadata={**parsed["parser_metadata"], "reuse_policy": "cc-by-or-cc0-v1",
                         "metadata_license": metadata.get("license"), "identity_scope": "own-front-article-meta-only"},
        source_identifiers=own, blocks=blocks, retained_content_utf8=payload.decode("utf-8"),
    )


class EuropePmcSourceProvider:
    def __init__(self, *, transport=None):
        self._transport = transport or BoundedTransport()

    def prepare(self, paper: Paper) -> PreparedSource:
        timestamp, metadata, abstract_provenance = now(), None, {}
        def fallback(status, reason, *, error=None, license=None):
            return fallback_source(paper, status, reason, error=error, license=license,
                                   retrieved_at=timestamp, abstract_provenance=abstract_provenance)
        try:
            expected = _expected_ids(paper)
            if paper.pmid:
                query = f"EXT_ID:{paper.pmid} AND SRC:MED"
            elif paper.doi:
                escaped = paper.doi.replace("\\", "\\\\").replace('"', '\\"')
                query = f'DOI:"{escaped}"'
            else:
                return fallback("abstract_only" if paper.abstract.strip() else "no_usable_text",
                                "No PMID or DOI is available for exact Europe PMC resolution.")
            payload = self._transport.request("europe_search", {
                "query": query, "format": "json", "resultType": "core", "pageSize": 5,
            })
            if not isinstance(payload, bytes) or len(payload) > MAX_RESPONSE_BYTES:
                raise ProviderFailure("response_too_large", "Europe PMC response exceeds the permitted size.")
            try:
                data = json.loads(payload)
                rows = data["resultList"]["result"]
                if not isinstance(rows, list) or len(rows) > 5 or any(not isinstance(row, dict) for row in rows):
                    raise ValueError()
            except (ValueError, KeyError, TypeError):
                raise ProviderFailure("malformed_metadata", "Europe PMC returned malformed article metadata.") from None
            if not rows:
                return fallback("abstract_only" if paper.abstract.strip() else "no_usable_text",
                                "Europe PMC has no exact metadata match; available citation abstract only.")
            candidates = []
            for row in rows:
                identifiers = _metadata_ids(row)
                _validate_identity(expected, identifiers)
                candidates.append(row)
            # A DOI can return MED and PMC manifestations of the same article.
            identities = {tuple(sorted(_metadata_ids(row).items())) for row in candidates}
            if len(identities) > 1:
                raise ProviderFailure("identity_mismatch", "Europe PMC resolution returned ambiguous article identities.")
            metadata = candidates[0]
            if not paper.abstract.strip() and isinstance(metadata.get("abstractText"), str) and metadata["abstractText"].strip():
                original = metadata["abstractText"]
                if "<" in original:
                    try:
                        fragment = safe_xml(("<abstract>" + original + "</abstract>").encode("utf-8"), "Europe PMC abstract")
                        abstract = " ".join(" ".join(fragment.itertext()).split())
                    except ProviderFailure:
                        abstract = ""
                else:
                    abstract = original
                if abstract.strip():
                    paper = paper.model_copy(update={"abstract": abstract})
                    abstract_provenance = {
                        "origin": "europe_pmc_core_abstract", "normalization": "xml-fragment-text-v1" if "<" in original else "none",
                        "metadata_response_sha256": hashlib.sha256(payload).hexdigest(),
                        "metadata_provider": "europe_pmc", "identity_scope": "exact-own-metadata-identifiers",
                    }
            if metadata.get("isOpenAccess") != "Y" or not supported_license(metadata.get("license")):
                return fallback("permission_unresolved", "Full text is unavailable for reuse or has no supported CC BY/CC0 license; available citation abstract only.",
                                license=metadata.get("license"))
            pmcid = _metadata_ids(metadata).get("pmcid")
            if not pmcid:
                return fallback("abstract_only" if paper.abstract.strip() else "no_usable_text",
                                "Europe PMC has no full-text PMCID; available citation abstract only.", license=metadata.get("license"))
            payload = self._transport.request("europe_fulltext", {"pmcid": pmcid})
            return prepare_permitted_xml(paper, payload, metadata, retrieved_at=timestamp)
        except ProviderFailure as error:
            status = error.code if error.code in {"identity_mismatch", "permission_unresolved", "no_usable_text"} else "fetch_failed"
            if status == "no_usable_text" and paper.abstract.strip():
                status = "abstract_only"
            return fallback(status, error.message + (" Available citation abstract is used." if paper.abstract.strip() else " No usable citation abstract is available."),
                            error=error, license=metadata.get("license") if metadata else None)


# A conventional acronym spelling is convenient for dependency construction.
EuropePMCSourceProvider = EuropePmcSourceProvider
