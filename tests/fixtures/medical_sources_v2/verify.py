"""Verify newly acquired v2 medical source snapshots offline; never rank/download."""

from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET


EXPECTED = {
    "singhypertension": ("10.1371/journal.pmed.1004026", "2022-06-13"),
    "czechia": ("10.1371/journal.pmed.1004422", "2024-07-15"),
    "enose": ("10.1371/journal.pone.0340276", "2026-01-07"),
}
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def element_text(element):
    return "".join(element.itertext()).strip() if element is not None else None


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
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    require(manifest.get("schema_version") == 1, "Unsupported fixture manifest version")
    sources = manifest["sources"]
    require([source["alias"] for source in sources] == list(EXPECTED), "Fixture source set/order differs")
    results = []
    for source in sources:
        alias = source["alias"]
        doi, published = EXPECTED[alias]
        require(source["file"] == alias + ".xml", f"{alias}: unexpected source filename")
        content = (directory / source["file"]).read_bytes()
        require(len(content) == source["size_bytes"], f"{alias}: byte length differs")
        require(hashlib.sha256(content).hexdigest() == source["sha256"], f"{alias}: SHA-256 differs")
        require(b"<!ENTITY" not in content.upper(), f"{alias}: entity declaration unsupported")
        # ElementTree does not load the external DTD. Entity declarations above
        # are rejected; predefined XML escapes still preserve ordinary text.
        article = ET.fromstring(content)
        require(article.tag == "article" and article.get("article-type") == "research-article", f"{alias}: expected research article XML")
        require(article.attrib == source["xml_root_attributes"], f"{alias}: root metadata differs")
        metadata = article.find("front/article-meta")
        require(metadata is not None, f"{alias}: own article metadata missing")
        own_dois = [element_text(element) for element in metadata.findall("article-id") if element.get("pub-id-type") == "doi"]
        require(own_dois == [doi] and source["doi"] == doi, f"{alias}: own DOI mismatch")
        require(element_text(metadata.find("title-group/article-title")) == source["title"], f"{alias}: own title mismatch")
        require(authors_of(metadata) == source["authors"], f"{alias}: author attribution differs")
        require(element_text(article.find("front/journal-meta/journal-title-group/journal-title")) == source["journal"], f"{alias}: journal differs")
        require(element_text(article.find("front/journal-meta/publisher/publisher-name")) == source["publisher"], f"{alias}: publisher differs")
        dates = [{"attributes": element.attrib, "fields": {child.tag: child.text for child in element}} for element in metadata.findall("pub-date")]
        require(dates == source["xml_publication_dates"], f"{alias}: publication metadata differs")
        epub = metadata.find("pub-date[@pub-type='epub']")
        require(epub is not None, f"{alias}: electronic publication date missing")
        actual_date = date(int(epub.findtext("year")), int(epub.findtext("month")), int(epub.findtext("day"))).isoformat()
        require(actual_date == published == source["publication_date"], f"{alias}: publication date mismatch")
        licenses = metadata.findall("permissions/license")
        require(len(licenses) == 1 and licenses[0].get(XLINK_HREF) == "http://creativecommons.org/licenses/by/4.0/", f"{alias}: own CC BY 4.0 license missing")
        require([{"attributes": element.attrib, "text": element_text(element)} for element in licenses] == source["xml_licenses"], f"{alias}: license metadata differs")
        require(source["license"]["spdx_id"] == "CC-BY-4.0" and source["license"]["xml_url"] == licenses[0].get(XLINK_HREF), f"{alias}: manifest license differs")
        require(source["copyright"] == {"year": element_text(metadata.find("permissions/copyright-year")), "holder": element_text(metadata.find("permissions/copyright-holder"))}, f"{alias}: copyright attribution differs")
        require([element_text(element) for element in metadata.findall("article-version")] == source["xml_article_versions"] == [], f"{alias}: explicit version metadata differs")
        require(bool(source["version_statement"].strip()), f"{alias}: version caveat missing")
        acquired = datetime.fromisoformat(source["acquired_at"].replace("Z", "+00:00"))
        require(source["acquired_at"].endswith("Z") and acquired.utcoffset().total_seconds() == 0, f"{alias}: acquisition time must be UTC")
        require(urlsplit(source["download_url"]).hostname == "journals.plos.org", f"{alias}: permanent source must be publisher URL")
        final_url = urlsplit(source["final_url"])
        require(final_url.hostname == "storage.googleapis.com" and not final_url.query and source["final_url_query_omitted"] is True, f"{alias}: signed redirect query must be omitted")
        require(article.find("body") is not None and article.findall("./body/sec"), f"{alias}: full article body missing")
        require(source["update_audit"].startswith("Limited original-page/known-notice observation"), f"{alias}: limited update-audit caveat missing")
        notices = source["observed_publisher_notices"]
        if alias == "enose":
            require(len(notices) == 1, "enose: known correction notice must be retained")
            notice = notices[0]
            require(notice["doi"] == "10.1371/journal.pone.0342238" and notice["published_at"] == "2026-02-02", "enose: correction identity/date differs")
            require(notice["publisher_url"] == "https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0342238", "enose: primary correction source differs")
            citation = notice["corrected_citation"]
            require(citation["authors_as_cited"] == ["Schoenaker IJH", "van Westreenen HL", "Finnema EJ", "Schrauwen R", "Brohet RM", "de Vos tot Nederveen Cappel, WH"], "enose: corrected citation authors differ")
            require(citation["corrected_author_ordinal"] == 6 and citation["corrected_author_as_cited"] == citation["authors_as_cited"][5], "enose: corrected sixth-author attribution differs")
            require(citation["doi"] == doi and citation["title"] == source["title"] and citation["journal"] == source["journal"] and citation["year"] == 2026, "enose: corrected citation identity differs")
            require(citation["volume"] == metadata.findtext("volume") and citation["issue"] == metadata.findtext("issue") and citation["article_number"] == metadata.findtext("elocation-id"), "enose: corrected citation publication fields differ")
            require("does not state a clinical-result correction" in notice["scope_as_stated"] and "Base article bytes remain unchanged" in notice["corpus_handling"], "enose: correction-scope/handling caveat missing")
        else:
            require(notices == [], f"{alias}: unexpected observed-notice metadata")
        results.append({"alias": alias, "doi": doi, "publication_date": published, "size_bytes": len(content), "sha256": source["sha256"], "license": "CC-BY-4.0"})
    return results


if __name__ == "__main__":
    try:
        print(json.dumps({"verified_sources": verify_sources()}, indent=2))
    except (ValueError, KeyError, OSError, ET.ParseError) as error:
        print(f"Medical source fixture verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
