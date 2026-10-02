"""Verify source-only v3 publisher snapshots offline, without retrieval or imports."""

import argparse
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
from urllib.parse import parse_qs, urlsplit
import xml.etree.ElementTree as ET


EXPECTED = {
    "cbti": {
        "doi": "10.1371/journal.pmed.1004510",
        "date": "2025-01-21", "journal_path": "plosmedicine",
        "design": "randomized_trial", "tables": 2,
        "title": "Effectiveness of app-based cognitive behavioral therapy for insomnia on preventing major depressive disorder in youth with insomnia and subclinical depression: A randomized clinical trial",
    },
    "ckm": {
        "doi": "10.1371/journal.pmed.1004629",
        "date": "2025-06-26", "journal_path": "plosmedicine",
        "design": "observational_cohort", "tables": 4,
        "title": "Cardiovascular–kidney–metabolic syndrome and all-cause and cardiovascular mortality: A retrospective cohort study",
    },
    "truenat": {
        "doi": "10.1371/journal.pone.0327936",
        "date": "2025-12-22", "journal_path": "plosone",
        "design": "diagnostic_accuracy", "tables": 4,
        "title": "Diagnostic accuracy of the TrueNat™ MTB plus assay for detecting pulmonary tuberculosis in adults",
    },
}
PRIOR_DOIS = [
    "10.1371/journal.pmed.1004019", "10.1371/journal.pmed.1004109",
    "10.1371/journal.pone.0329611", "10.1371/journal.pmed.1004026",
    "10.1371/journal.pmed.1004422", "10.1371/journal.pone.0340276",
]
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def element_text(element):
    return "".join(element.itertext()).strip() if element is not None else None


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate manifest key: {key}")
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError(f"Nonfinite manifest value: {value}")


def authors_of(metadata):
    authors = []
    for contributor in metadata.findall("contrib-group/contrib"):
        if contributor.get("contrib-type") != "author":
            continue
        name = contributor.find("name")
        authors.append(
            {"surname": element_text(name.find("surname")), "given_names": element_text(name.find("given-names"))}
            if name is not None else {"collective_name": element_text(contributor.find("collab"))}
        )
    return authors


def verify_sources(directory=None):
    directory = Path(directory) if directory is not None else Path(__file__).resolve().parent
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"),
                          object_pairs_hook=unique_pairs, parse_constant=invalid_constant)
    require(manifest.get("schema_version") == 1, "Unsupported source manifest version")
    require(manifest.get("status") == "acquired_sources_pending_coordinator_approval_before_gold", "Unexpected acquisition stage")
    require(manifest["prior_source_dois"] == PRIOR_DOIS, "Prior DOI set differs")
    sources = manifest["sources"]
    require([source["alias"] for source in sources] == list(EXPECTED), "Source set/order differs")
    require(len({source["doi"] for source in sources}) == 3, "Repeated source DOI")
    require(not {source["doi"] for source in sources}.intersection(PRIOR_DOIS), "Source overlaps prior corpus")
    results = []
    for source in sources:
        alias = source["alias"]
        expected = EXPECTED[alias]
        doi = expected["doi"]
        require(source["file"] == alias + ".xml", f"{alias}: unexpected filename")
        content = (directory / source["file"]).read_bytes()
        require(type(source["size_bytes"]) is int and len(content) == source["size_bytes"], f"{alias}: byte length differs")
        require(hashlib.sha256(content).hexdigest() == source["sha256"], f"{alias}: SHA-256 differs")
        require(b"<!ENTITY" not in content.upper(), f"{alias}: entity declaration unsupported")
        # ElementTree does not fetch the publisher's external DTD. Declared
        # entities are rejected before parsing; standard XML escapes are allowed.
        article = ET.fromstring(content)
        require(article.tag == "article" and article.get("article-type") == "research-article", f"{alias}: expected primary research XML, not HTML")
        require(article.attrib == source["xml_root_attributes"], f"{alias}: root metadata differs")
        metadata = article.find("front/article-meta")
        require(metadata is not None, f"{alias}: own article metadata missing")
        own_dois = [element_text(e) for e in metadata.findall("article-id") if e.get("pub-id-type") == "doi"]
        require(own_dois == [doi] and source["doi"] == doi, f"{alias}: own DOI mismatch")
        require(element_text(metadata.find("title-group/article-title")) == source["title"] == expected["title"], f"{alias}: own title mismatch")
        require(authors_of(metadata) == source["authors"] and bool(source["authors"]), f"{alias}: author attribution differs")
        require(element_text(article.find("front/journal-meta/journal-title-group/journal-title")) == source["journal"], f"{alias}: journal differs")
        require(element_text(article.find("front/journal-meta/publisher/publisher-name")) == source["publisher"] == "Public Library of Science", f"{alias}: publisher differs")
        dates = [{"attributes": e.attrib, "fields": {child.tag: child.text for child in e}} for e in metadata.findall("pub-date")]
        require(dates == source["xml_publication_dates"], f"{alias}: publication metadata differs")
        epub = metadata.find("pub-date[@pub-type='epub']")
        require(epub is not None, f"{alias}: electronic publication date missing")
        actual_date = date(int(epub.findtext("year")), int(epub.findtext("month")), int(epub.findtext("day"))).isoformat()
        require(actual_date == source["publication_date"] == expected["date"], f"{alias}: publication date mismatch")
        licenses = metadata.findall("permissions/license")
        require(len(licenses) == 1 and licenses[0].get(XLINK_HREF) == "http://creativecommons.org/licenses/by/4.0/", f"{alias}: own CC BY 4.0 license missing")
        require([{"attributes": e.attrib, "text": element_text(e)} for e in licenses] == source["xml_licenses"], f"{alias}: own license metadata differs")
        require(source["license"] == {"spdx_id": "CC-BY-4.0", "xml_url": licenses[0].get(XLINK_HREF), "publisher_link_resolves_to": "https://creativecommons.org/licenses/by/4.0/"}, f"{alias}: manifest license differs")
        require(source["copyright"] == {"year": element_text(metadata.find("permissions/copyright-year")), "holder": element_text(metadata.find("permissions/copyright-holder"))}, f"{alias}: copyright attribution differs")
        require([element_text(e) for e in metadata.findall("article-version")] == source["xml_article_versions"] == [], f"{alias}: explicit version metadata differs")
        require("no formal version is inferred" in source["version_statement"] and "not asserted to be latest" in source["version_statement"], f"{alias}: version caveat missing")
        acquired = datetime.fromisoformat(source["acquired_at"].replace("Z", "+00:00"))
        require(source["acquired_at"].endswith("Z") and acquired.tzinfo is not None and acquired.utcoffset().total_seconds() == 0, f"{alias}: acquisition time must be UTC")
        require(acquired.date() >= date.fromisoformat(actual_date), f"{alias}: acquisition predates publication")
        publisher_url = f"https://journals.plos.org/{expected['journal_path']}/article?id={doi}"
        require(source["publisher_url"] == publisher_url, f"{alias}: primary publication URL differs")
        download = urlsplit(source["download_url"])
        require(download.scheme == "https" and download.hostname == "journals.plos.org" and download.path == f"/{expected['journal_path']}/article/file", f"{alias}: permanent publisher download differs")
        require(parse_qs(download.query) == {"id": [doi], "type": ["manuscript"]} and not download.fragment, f"{alias}: download article/type differs")
        final = urlsplit(source["final_url"])
        require(final.scheme == "https" and final.hostname == "storage.googleapis.com" and final.path.startswith(f"/plos-corpus-prod/{doi}/") and final.path.endswith(".xml") and not final.query and not final.fragment, f"{alias}: sanitized redirect provenance differs")
        require(source["final_url_query_omitted"] is True and "Ephemeral signed access parameters omitted" in source["final_url_query_omission_reason"], f"{alias}: signed-query omission caveat missing")
        require(article.find("body") is not None and article.findall("./body/sec"), f"{alias}: full article body missing")
        tables = article.findall("./body//table-wrap")
        require(len(tables) == source["main_article_table_count"] == expected["tables"], f"{alias}: main table count differs")
        require(all(table.findall(".//table//tr") for table in tables), f"{alias}: inspectable main table rows missing")
        require(source["design_category"] == expected["design"], f"{alias}: selected design differs")
        require(source["observed_publisher_notices"] == [], f"{alias}: notice observation changed")
        require(source["update_audit"].startswith("Limited original-page/known-notice observation") and "Not a comprehensive update audit" in source["update_audit"], f"{alias}: limited update observation caveat missing")
        # Caveats preserve observations, not clinical gold labels. Their XML paths
        # and literal source fragments must independently resolve to the snapshot.
        require(bool(source["source_caveats"]), f"{alias}: known source caveats omitted")
        for caveat in source["source_caveats"]:
            require(bool(caveat["description"].strip()), f"{alias}: empty caveat description")
            for observation in caveat["source_observations"]:
                element = article.find(observation["xml_path"])
                require(element is not None and observation["literal_fragment"] in element_text(element), f"{alias}: source caveat does not resolve")
        results.append({"alias": alias, "doi": doi, "publication_date": actual_date,
                        "size_bytes": len(content), "sha256": source["sha256"],
                        "license": "CC-BY-4.0", "main_article_tables": len(tables)})
    return results


def self_test(directory=None):
    """Tamper copied fixtures only; semantic cases update hash/size deliberately."""
    base = Path(directory) if directory is not None else Path(__file__).resolve().parent
    verify_sources(base)
    rejected = []

    def attempt(name, transform):
        with tempfile.TemporaryDirectory(prefix="r20-source-tamper-") as temporary:
            copy = Path(temporary) / "fixtures"
            shutil.copytree(base, copy)
            manifest = json.loads((copy / "manifest.json").read_text(encoding="utf-8"))
            transform(copy, manifest)
            (copy / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            try:
                verify_sources(copy)
            except (ValueError, KeyError, TypeError, OSError, ET.ParseError):
                rejected.append(name)
            else:
                raise AssertionError(f"Tamper escaped detection: {name}")

    def changed_bytes(transform, rehash=True):
        def mutate(copy, manifest):
            source = manifest["sources"][0]
            path = copy / source["file"]
            content = transform(path.read_bytes())
            path.write_bytes(content)
            if rehash:
                source["size_bytes"] = len(content)
                source["sha256"] = hashlib.sha256(content).hexdigest()
        return mutate

    def changed_xml(transform):
        def mutate(content):
            article = ET.fromstring(content)
            transform(article)
            return ET.tostring(article, encoding="utf-8", xml_declaration=True)
        return changed_bytes(mutate)

    attempt("changed_raw_bytes", changed_bytes(lambda b: b + b" ", rehash=False))
    attempt("wrong_article_doi_after_rehash", changed_xml(lambda a: setattr(a.find("front/article-meta/article-id[@pub-id-type='doi']"), "text", PRIOR_DOIS[0])))
    attempt("wrong_title_after_rehash", changed_xml(lambda a: setattr(a.find("front/article-meta/title-group/article-title"), "text", "Wrong article")))
    attempt("wrong_author_after_rehash", changed_xml(lambda a: setattr(a.find("front/article-meta/contrib-group/contrib/name/surname"), "text", "Wrong Author")))
    attempt("wrong_license_after_rehash", changed_xml(lambda a: a.find("front/article-meta/permissions/license").set(XLINK_HREF, "http://creativecommons.org/publicdomain/zero/1.0/")))
    attempt("wrong_publication_date_after_rehash", changed_xml(lambda a: setattr(a.find("front/article-meta/pub-date[@pub-type='epub']/year"), "text", "1999")))
    attempt("html_after_rehash", changed_bytes(lambda _: b"<html><body>Publisher error page</body></html>"))
    attempt("entity_declaration_after_rehash", changed_bytes(lambda b: b"<!DOCTYPE article [<!ENTITY external SYSTEM 'https://invalid.example/entity'>]>\n" + b))
    attempt("no_main_tables_after_rehash", changed_xml(lambda a: [parent.remove(child) for parent in a.iter() for child in list(parent) if child.tag == "table-wrap"]))
    attempt("signed_redirect_query", lambda _, m: m["sources"][0].__setitem__("final_url", m["sources"][0]["final_url"] + "?temporary-signature=redacted"))
    attempt("wrong_download_article", lambda _, m: m["sources"][0].__setitem__("download_url", m["sources"][0]["download_url"].replace("1004510", "1004019")))
    attempt("missing_known_caveats", lambda _, m: m["sources"][2].__setitem__("source_caveats", []))
    attempt("altered_caveat_fragment", lambda _, m: m["sources"][2]["source_caveats"][0]["source_observations"][0].__setitem__("literal_fragment", "This invented quotation is absent."))
    attempt("duplicate_sources", lambda _, m: m["sources"].__setitem__(1, deepcopy(m["sources"][0])))
    return rejected


if __name__ == "__main__":
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument("--fixture-dir", type=Path)
    arguments.add_argument("--self-test", action="store_true")
    args = arguments.parse_args()
    try:
        result = {"verified_sources": verify_sources(args.fixture_dir)}
        if args.self_test:
            result["rejected_tamper_cases"] = self_test(args.fixture_dir)
        print(json.dumps(result, indent=2))
    except (ValueError, KeyError, TypeError, OSError, ET.ParseError, AssertionError) as error:
        print(f"Medical source v3 verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
