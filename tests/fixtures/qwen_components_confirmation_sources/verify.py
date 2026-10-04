#!/usr/bin/env python3
"""Offline original-XML-first checks for the two prospective component acquisitions."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
from urllib.parse import parse_qs, urlsplit
import xml.etree.ElementTree as ET

EXPECTED = {'thyroid': ('10.1371/journal.pone.0312121', 102942, '16fa9e8b026a4d1ef4bba69ce3c128eb4a297d655107b4e3776b63a12b8c3b73', 40, 5), 'copcov': ('10.1371/journal.pmed.1004428', 258039, '636e4d4a87c84cc256d565fe10f48ec134d2c6af201973f439778771ba97f04d', 60, 3)}
SPLIT = 'confirmation'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def tag(element):
    return element.tag.rsplit("}", 1)[-1]


def inline(element):
    return " ".join("".join(element.itertext()).split()) if element is not None else ""


def first(element, name):
    return next((e for e in element if tag(e) == name), None)


def independent_blocks(raw, source_id):
    """Reconstruct from raw elements before consulting saved canonical blocks."""
    text = raw.decode("utf-8-sig")
    require(not re.search(r"<!ENTITY\b", text, re.I), "XML entity unsupported")
    root = ET.fromstring(text)
    require(tag(root) == "article", "Own article root required")
    output = []

    def walk(element, path, ancestors, section=""):
        name = tag(element)
        if name in ("ref-list", "ref", "sub-article"):
            return
        if name == "sec":
            section = inline(first(element, "title")) or section
        selected = (name == "article-title" and "front" in ancestors) or (name == "p" and ("body" in ancestors or "abstract" in ancestors)) or (name == "table-wrap" and "body" in ancestors)
        if selected:
            if name == "table-wrap":
                lines = [inline(first(element, n)) for n in ("label", "caption")]
                lines = [line for line in lines if line]
                for row in element.iter():
                    if tag(row) == "tr":
                        line = "\t".join(inline(cell) for cell in row if tag(cell) in ("td", "th"))
                        if line.strip():
                            lines.append(line)
                lines.extend(inline(e) for e in element if tag(e) == "table-wrap-foot" and inline(e))
                value = "\n".join(lines)
            else:
                value = inline(element)
            if value:
                locator = {"type": "xml_element", "path": path, "tag": name}
                if element.get("id") is not None:
                    locator["element_id"] = element.get("id")
                if section:
                    locator["section_title"] = section
                if name == "table-wrap" and inline(first(element, "label")):
                    locator["table_label"] = inline(first(element, "label"))
                output.append({"source_id": source_id, "block_id": "xml:" + path, "ordinal": len(output) + 1, "source_path": path, "kind": name, "section": section, "text": value, "sha256": digest(value.encode("utf-8")), "locator": locator})
            if name == "table-wrap":
                return
        siblings = {}
        for child in element:
            child_name = tag(child)
            siblings[child_name] = siblings.get(child_name, 0) + 1
            walk(child, f"{path}/{child_name}[{siblings[child_name]}]", ancestors + (name,), section)

    walk(root, "/article[1]", ())
    return root, output


def verify(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_text())
    require(manifest["schema_version"] == 1 and manifest["ticket"] == "KR4B" and manifest["split"] == SPLIT, "Source manifest identity")
    require([s["id"] for s in manifest["sources"]] == list(EXPECTED), "Exact fresh source set/order")
    reconstructions = {}
    for source in manifest["sources"]:
        alias = source["id"]
        doi, size, sha, block_count, tables = EXPECTED[alias]
        file = directory / source["file"]
        require(source["file"] == alias + ".xml" and not file.is_symlink() and file.resolve().parent == directory, "Source path scope")
        raw = file.read_bytes()
        require(len(raw) == size and digest(raw) == sha, "Original acquisition byte pins")
        require(source["source_sha256"] == sha and source["size_bytes"] == size, "Source byte metadata")
        require(source["acquisition"]["sha256"] == sha and source["acquisition"]["size_bytes"] == size, "Raw-to-acquisition pin binding")
        require(source["acquisition"]["id"] == alias and source["acquisition"]["file"] == source["file"] and source["acquisition"]["http_status"] == 200, "Acquisition identity/status")
        root, blocks = independent_blocks(raw, alias)
        metadata = root.find("./front/article-meta")
        require(metadata is not None, "Own metadata required")
        require(metadata.findtext('./article-id[@pub-id-type="doi"]') == doi == source["doi"], "Own DOI binding")
        require(inline(metadata.find("./title-group/article-title")) == source["title"], "Own title")
        authors = [{"given_names":e.findtext("./name/given-names"), "surname":e.findtext("./name/surname")} if e.find("./name") is not None else {"collaboration":inline(e.find("./collab"))} for e in metadata.findall('./contrib-group/contrib[@contrib-type="author"]')]
        require(authors == source["authors"], "Ordered original authors")
        publication = metadata.find('./pub-date[@pub-type="epub"]')
        date = f"{int(publication.findtext('year')):04}-{int(publication.findtext('month')):02}-{int(publication.findtext('day')):02}"
        require(date == source["published_date"], "Original e-publication date")
        require(source["journal"] == inline(root.find("./front/journal-meta/journal-title-group/journal-title")), "Original journal")
        permission = metadata.find("./permissions")
        license_element = permission.find("./license")
        license_url = license_element.get("{http://www.w3.org/1999/xlink}href")
        require(license_url == source["license"]["url"] and license_url in ("http://creativecommons.org/licenses/by/4.0/", "https://creativecommons.org/licenses/by/4.0/"), "Direct CC BY4 license")
        require(source["license"]["name"] == "Creative Commons Attribution 4.0 International", "License name")
        require(source["license"]["literal_notice"] == inline(license_element.find("./license-p")), "Full original license notice")
        require(source["license"]["copyright_year"] == permission.findtext("./copyright-year") and source["license"]["copyright_holder"] == permission.findtext("./copyright-holder"), "Copyright notice")
        require(source["publisher_article_url"] == "https://journals.plos.org/" + ("plosmedicine" if ".pmed." in doi else "plosone") + "/article?id=" + doi, "Primary article URL")
        permanent = source["publisher_xml_url"]
        u = urlsplit(permanent)
        require(u.scheme == "https" and u.netloc == "journals.plos.org" and u.path == "/" + ("plosmedicine" if ".pmed." in doi else "plosone") + "/article/file" and parse_qs(u.query) == {"id":[doi], "type":["manuscript"]}, "Permanent main-XML URL")
        require(permanent == source["acquisition"]["permanent_download_url"], "Download provenance equality")
        final = urlsplit(source["acquisition"]["sanitized_final_redirect_url"])
        require(final.scheme == "https" and final.netloc == "storage.googleapis.com" and final.path == f"/plos-corpus-prod/{doi}/1/{doi.split('.')[-2]}.{doi.rsplit('.',1)[-1]}.xml" and not final.query and not final.fragment, "Sanitized publisher version URL")
        require(source["version_label"] == final.path, "Original version label")
        require(source["acquisition"]["final_redirect_query_omitted"] is True and re.fullmatch(r"2026-10-04T.*\+00:00", source["acquisition"]["acquired_at_utc"]), "Acquisition UTC/query notice")
        require(len(blocks) == block_count == source["block_count"] and sum(b["kind"] == "table-wrap" for b in blocks) == tables == source["main_table_count"], "Raw block/table inventory")
        require(digest(canonical(blocks)) == source["canonical_blocks_sha256"], "Whole independent block inventory hash")
        require(source["format"] == "jats_xml" and source["parser_id"] == "lit-rev-engine.source.v1.jats_xml", "Parser identity")
        historical = source["parser_metadata"]
        require(set(historical) == {"python_version", "normalization", "tables", "external_dtd", "entities"} and isinstance(historical["python_version"], str) and bool(historical["python_version"]), "Historical runtime metadata preserved")
        require({k:v for k,v in historical.items() if k != "python_version"} == {"normalization":"xml-whitespace-v1", "tables":"rows-tab-separated-v1", "external_dtd":"ignored", "entities":"rejected"}, "Historical canonicalization rules")
        by_path = {b["source_path"]:b for b in blocks}
        for caveat in source["caveats"]:
            require(bool(caveat["summary"]) and bool(caveat["observations"]) and "no clinical or numerical correction" in caveat["treatment"], "Caveat treatment")
            for observation in caveat["observations"]:
                b = by_path.get(observation["source_path"])
                require(b is not None and observation["block_id"] == b["block_id"] and observation["canonical_fragment"] in b["text"], "Original discrepancy path/fragment")
        reconstructions[alias] = blocks
    require(all(e["candidate_doi_overlap"] is False and re.fullmatch(r"[a-f0-9]{64}", e["sha256"]) and isinstance(e["size_bytes"],int) and e["size_bytes"] > 0 for e in manifest["exclusion_manifest_checks"]), "Metadata-only exclusion provenance")
    require(manifest["limits"] == {"scope":"main_articles_only","paid_inference_calls":0,"rankings_observed":0}, "Prospective original archive limits")
    return manifest, reconstructions


def self_test(directory):
    original = json.loads((Path(directory) / "manifest.json").read_text())
    mutations = {
        "source hash": lambda m: m["sources"][0].update(source_sha256="0"*64),
        "acquisition length": lambda m: m["sources"][0]["acquisition"].update(size_bytes=1),
        "own DOI": lambda m: m["sources"][0].update(doi="10.1371/journal.pone.0000001"),
        "author order": lambda m: m["sources"][0]["authors"].reverse(),
        "license URL": lambda m: m["sources"][0]["license"].update(url="https://creativecommons.org/licenses/by-nc/4.0/"),
        "license notice": lambda m: m["sources"][0]["license"].update(literal_notice="changed"),
        "publication date": lambda m: m["sources"][0].update(published_date="2000-01-01"),
        "source title": lambda m: m["sources"][0].update(title="changed"),
        "signed redirect retained": lambda m: m["sources"][0]["acquisition"].update(sanitized_final_redirect_url=m["sources"][0]["acquisition"]["sanitized_final_redirect_url"]+"?signature=secret"),
        "supplement download": lambda m: m["sources"][0].update(publisher_xml_url=m["sources"][0]["publisher_xml_url"].replace("manuscript","supplement")),
        "block digest": lambda m: m["sources"][0].update(canonical_blocks_sha256="0"*64),
        "discrepancy fragment": lambda m: m["sources"][0].update(caveats=[{"summary":"invented", "treatment":"no clinical or numerical correction", "observations":[{"source_path":"/invented", "block_id":"xml:/invented", "canonical_fragment":"invented source fact"}]}]),
    }
    with tempfile.TemporaryDirectory(prefix="qwen-source-audit-") as tmp:
        target = Path(tmp)
        for alias in EXPECTED:
            shutil.copyfile(Path(directory)/(alias+".xml"), target/(alias+".xml"))
        for name, mutate in mutations.items():
            changed = copy.deepcopy(original); mutate(changed)
            (target/"manifest.json").write_text(json.dumps(changed))
            try:
                verify(target)
            except (ValueError, KeyError, TypeError):
                continue
            raise AssertionError("Tamper accepted: " + name)
        (target/"manifest.json").write_text(json.dumps(original))
        file=target/(next(iter(EXPECTED))+".xml"); file.write_bytes(file.read_bytes()+b"\n")
        try:
            verify(target)
        except ValueError:
            pass
        else:
            raise AssertionError("Changed original bytes accepted")
        shutil.copyfile(Path(directory)/(next(iter(EXPECTED))+".xml"),file)
        historical=copy.deepcopy(original)
        historical["sources"][0]["parser_metadata"]["python_version"]="historical-runtime-record"
        (target/"manifest.json").write_text(json.dumps(historical))
        verify(target)
    return len(mutations)+1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    directory = Path(__file__).resolve().parent
    try:
        manifest, rebuilt = verify(directory)
        print(f"PASS: {len(rebuilt)} original XML sources, {sum(map(len,rebuilt.values()))} blocks, {sum(s['main_table_count'] for s in manifest['sources'])} main tables")
        if args.self_test:
            print(f"PASS: {self_test(directory)} source tamper negatives; 1 historical-runtime positive")
    except Exception as exc:
        print(f"FAIL: {exc}",file=sys.stderr); sys.exit(1)
