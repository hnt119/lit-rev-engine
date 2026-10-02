#!/usr/bin/env python3
"""Offline R22 original-XML verifier; no project imports or network access."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET


PIN_SHA256 = "051c0e8c5e44dd3f7ce85647623d1aed8582fff4dcd2d0a5103b0e9c6cf1a7dd"
PIN_BYTES = 76039
XLINK = "{http://www.w3.org/1999/xlink}"
DOWNLOAD_URL = (
    "https://journals.plos.org/plosone/article/file?"
    "id=10.1371/journal.pone.0188679&type=manuscript"
)
ARTICLE_URL = "https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0188679"
ACQUISITION = {
    "download_url": DOWNLOAD_URL,
    "resolved_url_sanitized": (
        "https://storage.googleapis.com/plos-corpus-prod/"
        "10.1371/journal.pone.0188679/1/pone.0188679.xml"
    ),
    "resolved_url_query_removed": True,
    "retrieved_at_utc": "2026-10-02T20:58:29Z",
    "http_status": 200,
    "content_type": "application/xml",
    "byte_length": PIN_BYTES,
    "sha256": PIN_SHA256,
}


class VerificationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def literal(node: ET.Element | None) -> str:
    """Concatenate XML character data without correcting spelling or numbers."""
    require(node is not None, "required XML element is missing")
    return "".join(node.itertext()).strip()


def flat(node: ET.Element | None) -> str:
    return " ".join(literal(node).split())


def extract(raw: bytes) -> tuple[ET.Element, dict]:
    # ElementTree does not retrieve the external DTD. Reject entity declarations
    # rather than permit an internal entity expansion in a substituted source.
    require(b"<!ENTITY" not in raw.upper(), "XML entity declarations are forbidden")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise VerificationError("invalid XML") from error
    require(root.tag == "article", "expected a JATS article root")
    meta = root.find("front/article-meta")
    require(meta is not None, "article metadata is missing")
    date = meta.find("pub-date[@pub-type='epub']")
    require(date is not None, "epub publication date is missing")
    permissions = meta.find("permissions")
    require(permissions is not None, "permissions notice is missing")
    license_node = permissions.find("license")
    require(license_node is not None, "license is missing")
    license_links = license_node.findall("license-p/ext-link")
    tables = []
    for table in root.findall("body//table-wrap"):
        tables.append({
            "id": table.get("id"),
            "doi": flat(table.find("object-id[@pub-id-type='doi']")),
            "label": flat(table.find("label")),
            "caption": flat(table.find("caption/title")),
            "header_columns": len(table.findall(".//table/thead/tr/th")),
            "data_rows": len(table.findall(".//table/tbody/tr")),
        })
    metadata = {
        "article_type": root.get("article-type"),
        "jats_dtd_version": root.get("dtd-version"),
        "doi": flat(meta.find("article-id[@pub-id-type='doi']")),
        "publisher_article_id": flat(meta.find("article-id[@pub-id-type='publisher-id']")),
        "title": flat(meta.find("title-group/article-title")),
        "authors": [
            {"given_names": flat(author.find("name/given-names")),
             "surname": flat(author.find("name/surname"))}
            for author in meta.findall("contrib-group/contrib[@contrib-type='author']")
        ],
        "journal": flat(root.find("front/journal-meta/journal-title-group/journal-title")),
        "publisher": flat(root.find("front/journal-meta/publisher/publisher-name")),
        "publication_date": "-".join([
            flat(date.find("year")), flat(date.find("month")).zfill(2),
            flat(date.find("day")).zfill(2),
        ]),
        "collection_year": flat(meta.find("pub-date[@pub-type='collection']/year")),
        "volume": flat(meta.find("volume")),
        "issue": flat(meta.find("issue")),
        "elocation_id": flat(meta.find("elocation-id")),
        "copyright_year": flat(permissions.find("copyright-year")),
        "copyright_holder": flat(permissions.find("copyright-holder")),
        "license_url_as_published": license_node.get(XLINK + "href"),
        "license_ext_link_urls_as_published": [n.get(XLINK + "href") for n in license_links],
        "license_notice": flat(license_node.find("license-p")),
        "main_tables": tables,
        "raw_xml_counts": {
            "body_sections": len(root.findall("body//sec")),
            "body_paragraph_elements": len(root.findall("body//p")),
            "abstract_paragraph_elements": len(root.findall("front/article-meta/abstract//p")),
            "main_table_wraps": len(tables),
            "figure_references": len(root.findall("body//fig")),
            "supplementary_material_references": len(root.findall("body//supplementary-material")),
            "bibliographic_references": len(root.findall("back/ref-list/ref")),
        },
        "direct_related_article_nodes": [
            {"attributes": dict(n.attrib), "text": flat(n)}
            for n in root.findall(".//related-article")
        ],
        "front_article_notes_count": len(root.findall("front/article-meta/article-notes")),
    }
    return root, metadata


def verify(raw: bytes, manifest: dict) -> dict:
    require(manifest.get("schema_version") == 1, "unsupported manifest schema")
    require(manifest.get("ticket") == "R22", "wrong acquisition ticket")
    sources = manifest.get("sources")
    require(isinstance(sources, list) and len(sources) == 1, "expected one source")
    source = sources[0]
    require(source.get("alias") == "mri", "wrong source alias")
    require(source.get("file") == "mri.xml", "wrong XML filename")
    require(source.get("publisher_article_url") == ARTICLE_URL, "wrong publisher article URL")
    require(source.get("acquisition") == ACQUISITION, "acquisition snapshot differs from the frozen record")
    final = urlsplit(source["acquisition"]["resolved_url_sanitized"])
    require(not final.query and not final.fragment and not final.username and not final.password,
            "resolved URL is not sanitized")
    require(len(raw) == PIN_BYTES, "XML byte length differs from the frozen original")
    require(hashlib.sha256(raw).hexdigest() == PIN_SHA256, "XML SHA-256 differs from the frozen original")
    root, metadata = extract(raw)
    require(source.get("metadata") == metadata, "manifest metadata differs from the original XML")
    require(metadata["license_url_as_published"] == "http://creativecommons.org/licenses/by/4.0/",
            "source is not the required CC BY 4.0 license")
    require(metadata["license_ext_link_urls_as_published"] == [metadata["license_url_as_published"]],
            "license link mismatch")
    require(metadata["article_type"] == "research-article", "expected a primary research article")
    require(metadata["direct_related_article_nodes"] == [], "unexpected related article notice")
    require(metadata["front_article_notes_count"] == 0, "unexpected front article note")
    require(len(metadata["main_tables"]) == 3, "expected three main tables")
    table = root.find("body//table-wrap[@id='pone.0188679.t003']/alternatives/table")
    require(table is not None, "Table 3 must contain an inspectable XML table")
    require([flat(n) for n in table.findall("thead/tr/th")] == [
        "First author", "year", "lesions", "prevalence", "sensitivity", "specificity", "PPV", "NPV",
    ], "Table 3 headers changed")
    require([literal(n) for n in table.findall("tbody/tr")[-1].findall("td")] == [
        "this study", "2016", "248", "0.43(0.37–0.50)", "0.96(0.91–0.99)",
        "0.82(0.75–0.88)", "0.81(0.73–0.87)", "0.97(0.92–0.99)",
    ], "Table 3 own-study row changed")
    caveats = source.get("source_discrepancies")
    require(isinstance(caveats, list) and len(caveats) == 4, "expected four disclosed source discrepancies")
    for caveat in caveats:
        evidence = caveat.get("evidence")
        require(isinstance(evidence, list) and evidence, "caveat evidence is missing")
        for item in evidence:
            require(isinstance(item.get("xml_path"), str), "caveat XML path is missing")
            nodes = root.findall(item["xml_path"])
            require(len(nodes) == 1, "caveat XML path must select exactly one node")
            require(isinstance(item.get("literal_fragment"), str) and
                    item["literal_fragment"] in literal(nodes[0]),
                    "caveat literal fragment is not present at its original XML path")
    return {
        "ticket": "R22", "alias": "mri", "bytes": len(raw), "sha256": PIN_SHA256,
        "doi": metadata["doi"], "publication_date": metadata["publication_date"],
        "authors": len(metadata["authors"]), "main_tables": len(metadata["main_tables"]),
        "table_3_data_rows": len(table.findall("tbody/tr")), "source_discrepancies": len(caveats),
        "raw_xml_counts": metadata["raw_xml_counts"],
    }


def self_test(raw: bytes, manifest: dict) -> list[str]:
    """In-memory negative cases never edit the archive or depend on project code."""
    passed = []

    def rejected(name: str, candidate_raw: bytes, candidate_manifest: dict) -> None:
        try:
            verify(candidate_raw, candidate_manifest)
        except VerificationError:
            passed.append(name)
            return
        raise VerificationError("tamper case was accepted: " + name)

    rejected("truncated XML", raw[:-1], manifest)
    changed_raw = raw.replace(b"MRI for the assessment", b"XXX for the assessment", 1)
    require(changed_raw != raw and len(changed_raw) == len(raw), "tamper setup failed")
    rejected("same-size XML change", changed_raw, manifest)
    for field, value in [
        ("sha256", "0" * 64), ("byte_length", PIN_BYTES + 1),
        ("download_url", ARTICLE_URL), ("retrieved_at_utc", "2017-11-30T00:00:00Z"),
        ("resolved_url_sanitized", ACQUISITION["resolved_url_sanitized"] + "?token=redacted"),
    ]:
        candidate = copy.deepcopy(manifest)
        candidate["sources"][0]["acquisition"][field] = value
        rejected("manifest acquisition " + field, raw, candidate)
    for field, value in [
        ("doi", "10.1371/journal.pone.0000000"), ("title", "Changed title"),
        ("publication_date", "2016-11-30"), ("copyright_holder", "Changed holder"),
        ("license_url_as_published", "http://creativecommons.org/licenses/by-nc/4.0/"),
    ]:
        candidate = copy.deepcopy(manifest)
        candidate["sources"][0]["metadata"][field] = value
        rejected("manifest metadata " + field, raw, candidate)
    candidate = copy.deepcopy(manifest)
    candidate["sources"][0]["metadata"]["authors"][0]["surname"] = "Changed author"
    rejected("manifest author", raw, candidate)
    candidate = copy.deepcopy(manifest)
    candidate["sources"][0]["metadata"]["main_tables"][2]["data_rows"] = 4
    rejected("manifest table row count", raw, candidate)
    candidate = copy.deepcopy(manifest)
    candidate["sources"][0]["source_discrepancies"][0]["evidence"][0]["literal_fragment"] = "72.6% (95%-CI 65.1–79.2%)"
    rejected("clinically corrected source fragment", raw, candidate)
    candidate = copy.deepcopy(manifest)
    candidate["sources"][0]["source_discrepancies"][0]["evidence"][0]["xml_path"] = "body/sec[@id='absent']/p"
    rejected("absent source-fragment path", raw, candidate)
    candidate = copy.deepcopy(manifest)
    candidate["sources"][0]["acquisition"]["sha256"] = hashlib.sha256(changed_raw).hexdigest()
    rejected("changed XML with rewritten recorded hash", changed_raw, candidate)
    candidate = copy.deepcopy(manifest)
    candidate["sources"][0]["file"] = "../elsewhere.xml"
    rejected("source path traversal", raw, candidate)
    return passed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="also run in-memory tamper cases")
    args = parser.parse_args()
    directory = Path(__file__).resolve().parent
    try:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        raw = (directory / "mri.xml").read_bytes()
        report = verify(raw, manifest)
        if args.self_test:
            report["tamper_cases_rejected"] = self_test(raw, manifest)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except (VerificationError, OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, "verification failed: " + str(error) + "\n")


if __name__ == "__main__":
    main()
