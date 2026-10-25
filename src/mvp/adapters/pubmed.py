"""Capped exploratory PubMed previews, separate from complete CLI captures."""

from __future__ import annotations

import re

from src.mvp.contracts import Paper, SearchPreview, SearchRequest, StructuredError, now
from src.mvp.ports import ProviderFailure
from src.review.identity import normalize_doi, normalize_pmid
from src.review.importers import load_records_bytes

from .transport import BoundedTransport, safe_xml


def parse_esearch_preview(payload: bytes, max_results: int) -> dict:
    root = safe_xml(payload, "PubMed ESearch")
    if root.tag != "eSearchResult":
        raise ProviderFailure("malformed_xml", "PubMed ESearch returned an unexpected root.")
    def single(name):
        nodes = root.findall(name)
        if len(nodes) != 1:
            raise ProviderFailure("malformed_xml", f"PubMed ESearch requires one {name}.")
        return nodes[0]
    def integer(name):
        value = single(name)
        if list(value) or not re.fullmatch(r"[0-9]+", value.text or ""):
            raise ProviderFailure("malformed_xml", "PubMed ESearch returned invalid counts.")
        return int(value.text)
    total, retmax, start = integer("Count"), integer("RetMax"), integer("RetStart")
    if start != 0 or retmax > max_results:
        raise ProviderFailure("invalid_membership", "PubMed returned an unexpected preview range.")
    identifiers, warnings = [], []
    for node in single("IdList"):
        try:
            pmid = normalize_pmid(node.text or "")
        except ValueError:
            pmid = None
        if node.tag != "Id" or list(node) or pmid is None:
            raise ProviderFailure("invalid_membership", "PubMed returned an invalid preview PMID.")
        if pmid in identifiers:
            warnings.append("Duplicate PMID in the provider preview was shown once.")
        else:
            identifiers.append(pmid)
    if len(identifiers) > min(max_results, total) or len(single("IdList")) != retmax:
        raise ProviderFailure("invalid_membership", "PubMed preview identifiers do not match its returned range.")
    if total and not identifiers:
        warnings.append("PubMed reported matches but returned no preview identifiers.")
    for warning_list in root.findall("WarningList"):
        for warning in warning_list:
            text = " ".join("".join(warning.itertext()).split())
            if text:
                warnings.append(f"PubMed {warning.tag}: {text[:2000]}")
    translation = root.find("QueryTranslation")
    return {"total_reported": total, "ordered_identifiers": identifiers,
            "query_translation": "".join(translation.itertext()) if translation is not None else None,
            "warnings": warnings, "truncated": total > len(identifiers)}


def deduplicate_papers(papers: list[Paper]) -> tuple[list[Paper], list[str]]:
    """Use identifiers only, preserving distinct PMIDs even if a DOI is shared."""
    result, warnings = [], []
    for paper in papers:
        duplicate = None
        for index, previous in enumerate(result):
            if paper.pmid and previous.pmid and paper.pmid != previous.pmid:
                if paper.doi and paper.doi == previous.doi:
                    warnings.append("A DOI is shared by distinct PMIDs; both reports were retained.")
                continue
            same_pmid = paper.pmid and paper.pmid == previous.pmid
            same_doi = paper.doi and paper.doi == previous.doi
            if same_pmid or same_doi:
                if paper.doi and previous.doi and paper.doi != previous.doi:
                    raise ProviderFailure("identity_mismatch", "Duplicate PMID records have conflicting DOI identifiers.")
                duplicate = index
                break
        if duplicate is None:
            result.append(paper)
        else:
            warnings.append("A repeated PMID/DOI citation was shown once.")
            if paper.pmid and not result[duplicate].pmid:
                result[duplicate] = paper
    return result, list(dict.fromkeys(warnings))


def _parse_pubmed_sample(payload: bytes, ordered_pmids: list[str]) -> tuple[list[Paper], list[str], int]:
    safe_xml(payload, "PubMed EFetch")
    try:
        records = load_records_bytes(payload, "pubmed_xml", source_name="PubMed preview")
    except ValueError:
        raise ProviderFailure("malformed_xml", "PubMed returned an invalid citation XML record.") from None
    papers, fetched_ids = [], []
    for record in records:
        pmid = normalize_pmid(record.pmid)
        if not pmid or pmid not in ordered_pmids:
            raise ProviderFailure("identity_mismatch", "Fetched PubMed citation does not belong to the requested preview.")
        fetched_ids.append(pmid)
        pmcids = []
        root = safe_xml(record.raw["xml"].encode("utf-8"), "PubMed citation")
        for element in root.findall("./PubmedData/ArticleIdList/ArticleId") + root.findall("./PubmedBookData/ArticleIdList/ArticleId"):
            if element.get("IdType", "").lower() == "pmc" and re.fullmatch(r"PMC[1-9][0-9]*", (element.text or "").strip()):
                pmcids.append(element.text.strip())
        papers.append(Paper(title=record.title, authors=record.authors, year=record.year,
                            doi=normalize_doi(record.doi), pmid=pmid, pmcid=pmcids[0] if len(set(pmcids)) == 1 else None,
                            abstract=record.abstract, url=record.url))
    if set(fetched_ids) != set(ordered_pmids):
        raise ProviderFailure("identity_mismatch", "Fetched PubMed membership is incomplete or differs from the requested preview.")
    papers, warnings = deduplicate_papers(papers)
    order = {pmid: index for index, pmid in enumerate(ordered_pmids)}
    papers.sort(key=lambda paper: order[paper.pmid])
    return papers, warnings, len(records)


def parse_pubmed_sample(payload: bytes, ordered_pmids: list[str]) -> tuple[list[Paper], list[str]]:
    papers, warnings, _ = _parse_pubmed_sample(payload, ordered_pmids)
    return papers, warnings


class PubMedPreviewProvider:
    """No complete-capture claims, even when a preview happens to fit the cap."""

    def __init__(self, email: str, *, api_key: str | None = None, tool: str = "lit-rev-engine-mvp", transport=None):
        if not isinstance(email, str) or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise ValueError("Configure a valid NCBI contact email for live PubMed discovery")
        if not isinstance(tool, str) or not tool or any(char.isspace() for char in tool):
            raise ValueError("NCBI tool name must be nonempty without spaces")
        self._email, self._api_key, self._tool = email, api_key, tool
        self._transport = transport or BoundedTransport()

    def search(self, request: SearchRequest) -> SearchPreview:
        timestamp = now()
        operational = {"email": self._email, "tool": self._tool}
        if self._api_key:
            operational["api_key"] = self._api_key
        params = {"db": "pubmed", "term": request.query, "retmax": request.max_results,
                  "retstart": 0, "retmode": "xml", "sort": request.sort, **operational}
        if request.date_from or request.date_to:
            params["datetype"] = "pdat"
            if request.date_from:
                params["mindate"] = request.date_from.replace("-", "/")
            if request.date_to:
                params["maxdate"] = request.date_to.replace("-", "/")
        result = parse_esearch_preview(self._transport.request("pubmed_search", params), request.max_results)
        papers, errors, fetched_count = [], [], 0
        if result["ordered_identifiers"]:
            try:
                papers, warnings, fetched_count = _parse_pubmed_sample(self._transport.request("pubmed_fetch", {
                    "db": "pubmed", "id": ",".join(result["ordered_identifiers"]), "retmode": "xml", **operational,
                }), result["ordered_identifiers"])
                if fetched_count > request.max_results:
                    papers, fetched_count = [], 0
                    raise ProviderFailure("invalid_membership", "PubMed returned more citation records than the preview cap.")
                result["warnings"].extend(warnings)
            except ProviderFailure as error:
                errors.append(StructuredError(code=error.code, message=error.message, retryable=error.retryable))
                result["warnings"].append("Preview identifiers were discovered, but citation retrieval failed; no unverified citations were added.")
        result["warnings"].append("Exploratory preview only; this is not a complete PubMed capture or a comprehensive review.")
        return SearchPreview(query=request.query, searched_at=timestamp, sort=request.sort,
                             requested_max_results=request.max_results,
                             configuration_profile=getattr(self, 'configuration_profile', None),
                             date_from=request.date_from, date_to=request.date_to,
                             fetched_count=fetched_count, papers=papers, errors=errors, **result)
