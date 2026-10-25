#!/usr/bin/env python3
"""Build/check a tiny public excerpt projection. No network, model or database.

Run from the lit-rev-engine checkout. Source paragraphs use its existing JATS
parser; offsets are Unicode code points within one normalized canonical block.
This is a curated display, not an executed retrieval or reviewer assessment.
"""
import argparse
import hashlib
import html
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
OVERLAY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.review.documents import parse_source_bytes

WEBSITE_BASE = "3a03ea54b84d2658901522613641c054e5096637"
SOURCE_COMMIT = "9891ac352d39c66395e21af2e9732a76b076d002"
BUNDLE = ROOT / "examples/mvp/offline_microbiome_30_v1"
DESTINATION = OVERLAY / "src/data/literature-showcase.json"
FIELDS = [
    {"id": "population", "label": "Population / design"},
    {"id": "diet", "label": "Diet / exposure"},
    {"id": "longevity", "label": "Reproductive lifespan"},
]
SELECTIONS = [
    {
        "id": "PMC11058859", "label": "Singapore pregnancy cohort",
        "tags": ["Singapore", "pregnancy", "cohort", "diet"],
        "population": ["This pilot prospective cohort study examined the impact of ethnicity on gut dysbiosis in GDM among three Asian ethnic groups (Chinese, Malay, Indian) living in Singapore, and investigated the potential modulatory roles of diet and lifestyle modifications on gut microbiome post-GDM diagnosis. Women with GDM (n = 53) and without GDM (n = 16) were recruited.", "53 women with GDM; 16 without. Pilot cohort in Singapore."],
        "diet": ["All women with GDM underwent dietary counselling and lifestyle modifications to control glucose levels during pregnancy.", "Dietary counselling and lifestyle modifications following GDM diagnosis."],
        "longevity": ["Analyses here were restricted to the 39 (72%) women with GDM who provided paired samples across both time points: at 24–28 weeks soon after GDM diagnosis, and at 36–40 weeks after dietary modification for 2–3 months.", None],
    },
    {
        "id": "PMC11820775", "label": "Cheonggukjang trial",
        "tags": ["menopause", "fermented soybeans", "randomized trial", "diet"],
        "population": ["In this randomized, double-blind clinical trial, 60 postmenopausal women were assigned to three groups: high-beneficial-microorganism content Cheonggukjang (HTC), low-beneficial-microorganism content Cheonggukjang (LTC), and commercially available Cheonggukjang (CC).", "60 postmenopausal women; randomized, double-blind trial."],
        "diet": ["Participants consumed 3.3 g of Cheonggukjang tablets daily for 8 weeks.", "3.3 g/day of Cheonggukjang tablets for 8 weeks."],
        "longevity": ["This study was designed as a randomized, double-blind clinical trial conducted over an 8-week period (Registration Number KCT 0010017).", None],
    },
    {
        "id": "PMC12567037", "label": "Japanese women / body weight",
        "tags": ["Japan", "young women", "observational", "dietary patterns"],
        "population": ["We enrolled 40 women aged 20–39 years who visited a nutrition evaluation clinic with a BMI < 17.5 at their first consultation (underweight group) and 40 age-matched women with 18.5 ≤ BMI < 25 (control group).", "40 underweight women and 40 controls, aged 20–39 years."],
        "diet": ["Dietary patterns were assessed based on ten major food categories (meat, fish, eggs, dairy products, soybeans, green and yellow vegetables, seaweed, fruit, tubers, and fats and oil) based on the Food Frequency Questionnaire based on Food Groups.", "Food-frequency questionnaire covering ten food categories."],
        "longevity": ["This study was conducted as a cross-sectional observational study to compare the dietary pattern and gut microbiota profiles between normal weight and underweight groups in Japanese young adult women aged 20–39 years.", None],
    },
]


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def build():
    manifest_bytes = (BUNDLE / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    sources = {source["pmcid"]: source for source in manifest["sources"]}
    papers = []
    for selection in SELECTIONS:
        source = sources[selection["id"]]
        assert source["license"] == "https://creativecommons.org/licenses/by/4.0/"
        xml = (BUNDLE / source["xml_file"]).read_bytes()
        metadata_bytes = (BUNDLE / source["metadata_file"]).read_bytes()
        assert digest(xml) == source["xml_sha256"], "Retained source hash changed"
        assert digest(metadata_bytes) == source["metadata_sha256"], "Metadata hash changed"
        metadata = json.loads(metadata_bytes)
        parsed = parse_source_bytes(xml, "jats_xml")
        assert parsed["source_identifiers"]["pmid"] == source["pmid"]
        assert parsed["source_identifiers"]["doi"] == source["doi"]
        excerpts, cells = [], []
        for field in FIELDS:
            quote, value = selection[field["id"]]
            matches = [block for block in parsed["blocks"] if block["text"].count(quote) == 1]
            assert len(matches) == 1, "Quotation must have one unambiguous canonical block"
            block = matches[0]
            start = block["text"].index(quote)
            end = start + len(quote)
            context_start = max(0, start - 160)
            context_end = min(len(block["text"]), end + 180)
            context = block["text"][context_start:context_end]
            assert context[start-context_start:end-context_start] == quote
            assert len(context) <= 900, "Keep browser evidence packets bounded"
            excerpt_id = selection["id"] + "-" + field["id"]
            excerpts.append({
                "id": excerpt_id, "fieldId": field["id"], "quote": quote,
                "blockId": block["id"], "section": block["locator"].get("section_title", "Abstract"),
                "sourceType": "abstract" if "/abstract[" in block["id"] else "full_text",
                "quoteStart": start, "quoteEnd": end,
                "contextStart": context_start, "contextEnd": context_end,
                "blockLength": len(block["text"]), "context": context,
            })
            cells.append({"fieldId": field["id"], "excerptId": excerpt_id, "value": value,
                          "state": "not_established" if value is None else "illustrative_note"})
        title = html.unescape(metadata["title"])
        papers.append({
            "id": selection["id"], "label": selection["label"], "title": title,
            "tags": selection["tags"], "year": str(metadata["pubYear"]),
            "citation": f'{metadata["authorString"]} {title} {metadata["journalInfo"]["journal"]["title"]}. {metadata["pubYear"]}. DOI: {source["doi"]}',
            "pmid": source["pmid"], "doi": source["doi"],
            "sourceUrl": f'https://europepmc.org/articles/{selection["id"]}',
            "retainedXmlUrl": f'https://github.com/hnt119/lit-rev-engine/blob/{SOURCE_COMMIT}/examples/mvp/offline_microbiome_30_v1/{source["xml_file"]}',
            "licenseUrl": source["license"], "attribution": source["attribution"],
            "sourceSha256": source["xml_sha256"], "metadataSha256": source["metadata_sha256"],
            "parserId": parsed["parser_id"], "cells": cells, "excerpts": excerpts,
        })
    return {
        "schemaVersion": 1, "websiteBaseSha": WEBSITE_BASE, "sourceCommit": SOURCE_COMMIT,
        "bundleId": manifest["bundle_id"], "bundleManifestSha256": digest(manifest_bytes),
        "capturedAt": manifest["searched_at"], "provider": manifest["provider"],
        "question": "How do dietary exposures relate to gut microbiome findings in Asian women?",
        "notice": "Three curated papers from a saved 30-paper public collection. Illustrative comparison notes are not submitted researcher judgments, independent verification or review inclusion decisions.",
        "fields": FIELDS, "papers": papers,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify exact projection without writing")
    args = parser.parse_args()
    payload = (json.dumps(build(), ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    assert len(payload) < 30_000, "Static demonstration must stay small"
    if args.check:
        assert DESTINATION.read_bytes() == payload, "Generated projection differs; inspect sources before regenerating"
        print("PASS: 3 public CC BY sources, 9 exact canonical anchors, 3 explicit missing-information cells; no network/model/database.")
    else:
        DESTINATION.parent.mkdir(parents=True, exist_ok=True)
        DESTINATION.write_bytes(payload)
        print(f"Wrote public projection ({len(payload)} bytes).")


if __name__ == "__main__":
    main()
