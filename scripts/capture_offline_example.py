#!/usr/bin/env python3
"""Explicitly capture the public, rights-checked thirty-paper offline pack.

This opt-in maintenance command makes bounded Europe PMC calls. Application
startup and normal tests never call it. It uses no private workspace or contact.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.mvp.adapters.europe_pmc import _child, _text, prepare_permitted_xml, supported_license
from src.mvp.adapters.saved_examples import _paper_from_xml_metadata
from src.mvp.adapters.transport import BoundedTransport, safe_xml
from src.mvp.contracts import now
from src.mvp.ports import ProviderFailure

QUERY = '(TITLE_ABS:"gut microbiota" OR TITLE_ABS:"gut microbiome" OR TITLE_ABS:"intestinal microbiota") AND (TITLE_ABS:women OR TITLE_ABS:female) AND (TITLE_ABS:Asian OR TITLE_ABS:Chinese OR TITLE_ABS:Japanese OR TITLE_ABS:Korean OR TITLE_ABS:Singapore OR TITLE_ABS:Thai OR TITLE_ABS:Vietnamese OR TITLE_ABS:Malaysian OR TITLE_ABS:Indonesian OR TITLE_ABS:Filipino) AND OPEN_ACCESS:Y'
QUESTION = "What do these sources report about gut microbiome, reproductive and healthy aging outcomes, gynecological conditions, and diet among the studied women in Asian populations?"


def encoded_json(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def capture(output: Path, *, transport=None):
    output.mkdir(parents=True, exist_ok=False)
    transport = transport or BoundedTransport(timeout=15, max_attempts=2)
    params = {"query": QUERY, "format": "json", "resultType": "core", "pageSize": 100}
    raw_search = transport.request("europe_search", params)
    searched_at = now()
    response = json.loads(raw_search)
    rows = response["resultList"]["result"]
    if not isinstance(rows, list) or len(rows) > 100 or type(response["hitCount"]) is not int:
        raise ValueError("Unexpected bounded CORE response.")
    sources, candidates = [], []
    seen_pmids, seen_pmcids, seen_dois = set(), set(), set()
    for rank, row in enumerate(rows, 1):
        pmid, pmcid, doi = row.get("pmid") or (row.get("id") if row.get("source") == "MED" else None), row.get("pmcid"), row.get("doi")
        candidate = {"capture_rank": rank, "pmid": pmid, "pmcid": pmcid, "doi": doi,
                     "title": row.get("title"), "metadata_license": row.get("license"), "is_open_access": row.get("isOpenAccess")}
        candidates.append(candidate)
        if len(sources) == 30:
            candidate.update(status="NOT_EVALUATED", reason="Thirty eligible sources already retained in returned order.")
            continue
        if not pmid or not pmcid:
            candidate.update(status="EXCLUDED", reason="Missing required PMID or PMCID.")
            continue
        if pmid in seen_pmids or pmcid in seen_pmcids or (doi and doi.lower() in seen_dois):
            candidate.update(status="EXCLUDED", reason="Duplicate retained article identity.")
            continue
        if row.get("isOpenAccess") != "Y" or not supported_license(row.get("license")):
            candidate.update(status="EXCLUDED", reason="Metadata has no supported CC BY/CC0 reuse license.")
            continue
        try:
            payload = transport.request("europe_fulltext", {"pmcid": pmcid})
            retrieved_at = now()
            entry = {"pmid": pmid, "pmcid": pmcid, "doi": doi}
            paper = _paper_from_xml_metadata(payload, row, entry)
            prepared = prepare_permitted_xml(paper, payload, row, retrieved_at=retrieved_at, provider="europe_pmc_saved_example")
            if any(value is not None and prepared.source_identifiers.get(key) != value
                   for key, value in (("pmid", paper.pmid), ("pmcid", paper.pmcid), ("doi", paper.doi))):
                raise ValueError("Own XML identifiers must cover the retained bibliography.")
        except (ProviderFailure, ValueError, KeyError, TypeError) as error:
            candidate.update(status="EXCLUDED", reason=getattr(error, "code", "malformed_metadata_or_xml"))
            print(json.dumps({"rank": rank, "pmcid": pmcid, "status": "EXCLUDED", "reason": candidate["reason"]}), flush=True)
            continue
        metadata_bytes = encoded_json(row)
        metadata_file, xml_file = f"{pmcid}.metadata.json", f"{pmcid}.xml"
        (output / metadata_file).write_bytes(metadata_bytes)
        (output / xml_file).write_bytes(payload)
        article_meta = _child(_child(safe_xml(payload), "front"), "article-meta")
        permissions = _child(article_meta, "permissions")
        entry.update(title=paper.title, capture_rank=rank, metadata_file=metadata_file, xml_file=xml_file,
                     metadata_sha256=hashlib.sha256(metadata_bytes).hexdigest(), xml_sha256=hashlib.sha256(payload).hexdigest(),
                     xml_size_bytes=len(payload), retrieved_at=retrieved_at, source_url=prepared.source_url,
                     license=prepared.license, attribution=prepared.attribution,
                     copyright_statement=_text(_child(permissions, "copyright-statement")),
                     identity_verification="Expected PMID, PMCID and available DOI agree between CORE metadata and own front/article-meta; references excluded.",
                     rights_verification="CORE open-access flag and supported CC BY/CC0 metadata license agree with an unambiguous permitted license in own XML permissions. Images are not downloaded.",
                     transformations=["XML bytes retained unchanged from the Europe PMC fullTextXML response.",
                                      "Only licensed retained CORE result serialized as UTF-8 sorted indented JSON.",
                                      "Citation abstract extracted from this same permitted own XML front matter.",
                                      "Canonical blocks parsed by existing lit-rev-engine.source.v1.jats_xml; whitespace normalized and table rows tab-separated."])
        sources.append(entry)
        seen_pmids.add(pmid)
        seen_pmcids.add(pmcid)
        if doi:
            seen_dois.add(doi.lower())
        candidate.update(status="RETAINED", reason="Own identities and supported metadata/XML reuse licenses checked.", license=prepared.license)
        print(json.dumps({"rank": rank, "pmcid": pmcid, "status": "RETAINED", "retained": len(sources)}), flush=True)
    audit = {"schema_version": "mvp.offline-capture-candidates.v1", "query": QUERY, "searched_at": searched_at,
             "search_response_sha256": hashlib.sha256(raw_search).hexdigest(), "total_reported": response["hitCount"],
             "returned_metadata_count": len(rows), "retained_count": len(sources), "candidates": candidates,
             "omitted_content": "Complete search response and excluded candidate abstracts/full texts are not bundled. Only bibliographic identifiers, titles and license/outcome fields retained here."}
    (output / "capture_candidates.json").write_bytes(encoded_json(audit))
    if len(sources) != 30:
        raise ValueError(f"Only {len(sources)} eligible sources among {len(rows)} records; query not broadened. Review capture_candidates.json before any follow-up.")
    manifest = {"schema_version": "mvp.saved-example-manifest.v1", "bundle_id": "offline-microbiome-30-v1",
                "label": "30-paper saved Europe PMC example (offline; curated, not a live PubMed search)",
                "mode": "saved_example", "provider": "europe_pmc", "question": QUESTION, "query": QUERY,
                "query_url": "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urlencode(params),
                "searched_at": searched_at, "search_timestamp_precision": "UTC client receipt time immediately after the actual CORE response; no server search timestamp assumed.",
                "sort": "Europe PMC default relevance order", "total_reported": response["hitCount"],
                "returned_metadata_count": len(rows), "fetched_count": len(sources),
                "curation_warning": "Thirty real, permitted CC BY/CC0 articles were retained in returned order after identity and license checks from a bounded Europe PMC metadata capture. This curated offline example is not a fresh PubMed search, complete capture, formal inclusion decision or scientific benchmark.",
                "population_note": "Geography and sex keywords may occur anywhere in title/abstract. They do not establish participant ethnicity, eligibility, women-only samples or applicability to all Asian women. Review each original source.",
                "capture_candidates_file": "capture_candidates.json", "capture_candidates_sha256": hashlib.sha256(encoded_json(audit)).hexdigest(),
                "sources": sources}
    (output / "manifest.json").write_bytes(encoded_json(manifest))
    lines = ["# Thirty-paper offline microbiome example", "", manifest["curation_warning"], "", manifest["population_note"], "",
             f"Captured {searched_at}. The provider reported **{response['hitCount']}** matches and returned **{len(rows)}** metadata records; **30** licensed sources were retained.", "",
             "The original one-paper example remains unchanged in `tests/fixtures/mvp/`. This bundle has a separate identifier and does not rewrite historical workspaces.", "",
             "`manifest.json` records exact query, capture time, source URLs, author/copyright attribution, licenses, transformations and per-file SHA-256. `capture_candidates.json` records all returned candidate identities and selection/exclusion outcomes; it omits excluded abstracts and full texts. XML bytes are unchanged. No images or PDFs are bundled.", "",
             "Creating this pack used live public Europe PMC calls. Opening it later requires no provider request, contact or model download. This command does not create a semantic map; any bundled map must have its own real-model provenance.", "", "## Sources and attribution", ""]
    for source in sources:
        lines.extend([f"- **{source['title']}** [PMID {source['pmid']}](https://pubmed.ncbi.nlm.nih.gov/{source['pmid']}/), [{source['pmcid']}](https://europepmc.org/articles/{source['pmcid']}). {source['attribution']} License: {source['license']}"])
    (output / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": "COMPLETE", "papers": len(sources), "reported": response["hitCount"], "returned": len(rows),
                      "licenses": dict(Counter(source["license"] for source in sources)), "xml_bytes": sum(source["xml_size_bytes"] for source in sources),
                      "manifest_sha256": hashlib.sha256(encoded_json(manifest)).hexdigest()}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New public pack directory; an existing directory is never overwritten.")
    args = parser.parse_args()
    capture(args.output)
