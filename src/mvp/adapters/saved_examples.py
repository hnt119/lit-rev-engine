"""Rights-checked real offline example; never a replay of an arbitrary query."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.mvp.contracts import Paper, SearchPreview, SearchRequest
from src.mvp.ports import ProviderFailure

from .europe_pmc import _child, _children, _text, fallback_source, prepare_permitted_xml
from .transport import safe_xml

_DEFAULT_FIXTURES = Path(__file__).resolve().parents[3] / "examples" / "mvp" / "offline_microbiome_30_v1"


def _checked_manifest(root: Path) -> dict:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    entries = manifest["sources"]
    if manifest["schema_version"] != "mvp.saved-example-manifest.v1" or not isinstance(entries, list) or not entries:
        raise ValueError()
    for key in ("label", "question", "query", "searched_at", "sort", "provider", "mode", "curation_warning", "population_note"):
        if not isinstance(manifest[key], str) or not manifest[key].strip():
            raise ValueError()
    if manifest["mode"] != "saved_example" or manifest["provider"] != "europe_pmc":
        raise ValueError()
    count = manifest["fetched_count"]
    if type(count) is not int or count != len(entries) or type(manifest["total_reported"]) is not int or manifest["total_reported"] < count:
        raise ValueError()
    if type(manifest.get("returned_metadata_count")) is not int or manifest["returned_metadata_count"] < count:
        raise ValueError()
    if manifest.get("bundle_id") == "offline-microbiome-30-v1" and count != 30:
        raise ValueError()
    if "capture_candidates_file" in manifest:
        filename = manifest["capture_candidates_file"]
        if Path(filename).name != filename:
            raise ValueError()
        candidate_bytes = (root / filename).read_bytes()
        if hashlib.sha256(candidate_bytes).hexdigest() != manifest["capture_candidates_sha256"]:
            raise ValueError()
        audit = json.loads(candidate_bytes)
        candidates = audit["candidates"]
        retained = [item for item in candidates if item["status"] == "RETAINED"]
        if (audit["query"] != manifest["query"] or audit["searched_at"] != manifest["searched_at"]
                or audit["total_reported"] != manifest["total_reported"]
                or audit["returned_metadata_count"] != manifest["returned_metadata_count"]
                or len(candidates) != manifest["returned_metadata_count"] or audit["retained_count"] != count
                or [item["pmid"] for item in retained] != [item["pmid"] for item in entries]
                or [item["pmcid"] for item in retained] != [item["pmcid"] for item in entries]):
            raise ValueError()
    return manifest


def _paper_from_xml_metadata(raw: bytes, row: dict, entry: dict) -> Paper:
    """Use only the permitted article's own abstract, never its references."""
    root = safe_xml(raw, "Saved example")
    article_meta = _child(_child(root, "front"), "article-meta")
    sections = []
    for abstract in _children(article_meta, "abstract"):
        sections.extend(_text(node) for node in abstract.iter() if str(node.tag).rsplit("}", 1)[-1] == "p")
    authors = row.get("authorList", {}).get("author", [])
    return Paper(title=row["title"], pmid=entry["pmid"], doi=entry["doi"], pmcid=entry["pmcid"],
                 authors=[item["fullName"] for item in authors if item.get("fullName")],
                 year=int(row["pubYear"]) if row.get("pubYear") else None,
                 abstract="\n\n".join(filter(None, sections)),
                 url=f"https://pubmed.ncbi.nlm.nih.gov/{entry['pmid']}/")


def saved_example_info(*, fixture_dir=None) -> dict:
    """Public provenance, safe for the UI; no private workspace paths."""
    root = Path(fixture_dir) if fixture_dir is not None else _DEFAULT_FIXTURES
    try:
        manifest = _checked_manifest(root)
    except (OSError, ValueError, KeyError, TypeError):
        raise ProviderFailure("saved_example_unavailable", "The saved example is unavailable or invalid.") from None
    result = {key: manifest[key] for key in ("label", "question", "query", "searched_at", "sort", "total_reported",
                                           "fetched_count", "provider", "mode", "curation_warning", "population_note")}
    return {**result, "bundle_id": manifest.get("bundle_id", "legacy-offline-example-v1"), "paper_count": len(manifest["sources"])}


class SavedExampleProvider:
    """Both discovery/source ports, backed only by the checked fixture manifest."""

    def __init__(self, *, fixture_dir=None):
        self._root = Path(fixture_dir) if fixture_dir is not None else _DEFAULT_FIXTURES
        try:
            self._manifest = _checked_manifest(self._root)
            self._entries = self._manifest["sources"]
            self._papers, self._sources = [], {}
            seen_pmids, seen_pmcids, seen_dois = set(), set(), set()
            for entry in self._entries:
                # Manifest files are local application data, never user-selected paths.
                if any(Path(entry[key]).name != entry[key] for key in ("metadata_file", "xml_file")):
                    raise ValueError()
                raw = (self._root / entry["xml_file"]).read_bytes()
                metadata_raw = (self._root / entry["metadata_file"]).read_bytes()
                if hashlib.sha256(raw).hexdigest() != entry["xml_sha256"] or hashlib.sha256(metadata_raw).hexdigest() != entry["metadata_sha256"]:
                    raise ValueError()
                row = json.loads(metadata_raw)
                paper = _paper_from_xml_metadata(raw, row, entry)
                if not paper.pmid or not paper.pmcid or paper.pmid in seen_pmids or paper.pmcid in seen_pmcids or (paper.doi and paper.doi in seen_dois):
                    raise ValueError()
                prepared = prepare_permitted_xml(paper, raw, row, retrieved_at=entry["retrieved_at"], provider="europe_pmc_saved_example")
                if entry.get("license") != prepared.license or entry.get("title") != paper.title:
                    raise ValueError()
                for key, value in (("pmid", paper.pmid), ("pmcid", paper.pmcid), ("doi", paper.doi)):
                    if value is not None and prepared.source_identifiers.get(key) != value:
                        raise ValueError()
                seen_pmids.add(paper.pmid)
                seen_pmcids.add(paper.pmcid)
                if paper.doi:
                    seen_dois.add(paper.doi)
                prepared = prepared.model_copy(update={"warnings": [self._manifest["curation_warning"]]})
                self._papers.append(paper)
                self._sources[paper.id] = prepared
        except (OSError, ValueError, KeyError, TypeError, ProviderFailure):
            raise ProviderFailure("saved_example_unavailable", "The saved example is unavailable, modified, or invalid.") from None

    def search(self, request: SearchRequest) -> SearchPreview:
        warnings = [self._manifest["curation_warning"], self._manifest["population_note"],
                    "Offline saved example: the supplied query, dates, and sort were not executed. The recorded Europe PMC query and capture time are shown."]
        papers = self._papers[:request.max_results]
        return SearchPreview(query=self._manifest["query"], query_translation=None,
                             searched_at=self._manifest["searched_at"], sort=self._manifest["sort"],
                             total_reported=self._manifest["total_reported"], fetched_count=len(papers),
                             ordered_identifiers=[paper.pmid for paper in papers], papers=papers,
                             warnings=warnings, truncated=True, provider="europe_pmc_saved_example", mode="saved_example")

    def prepare(self, paper: Paper):
        actual = next((candidate for candidate in self._papers if candidate.id == paper.id), None)
        if actual is None or actual.pmid != paper.pmid or actual.doi != paper.doi or actual.pmcid != paper.pmcid:
            return fallback_source(paper, "identity_mismatch", "This paper is not part of the checked offline saved example.",
                                   provider="europe_pmc_saved_example")
        return self._sources[paper.id].model_copy(deep=True)
