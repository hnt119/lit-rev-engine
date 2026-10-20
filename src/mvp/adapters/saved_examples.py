"""Rights-checked real offline example; never a replay of an arbitrary query."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.mvp.contracts import Paper, SearchPreview, SearchRequest
from src.mvp.ports import ProviderFailure

from .europe_pmc import _child, _children, _text, fallback_source, prepare_permitted_xml
from .transport import safe_xml

_DEFAULT_FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "mvp"


def saved_example_info(*, fixture_dir=None) -> dict:
    """Public provenance, safe for the UI; no private workspace paths."""
    root = Path(fixture_dir) if fixture_dir is not None else _DEFAULT_FIXTURES
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ProviderFailure("saved_example_unavailable", "The saved example is unavailable or invalid.") from None
    return {key: manifest[key] for key in ("label", "question", "query", "searched_at", "sort", "total_reported",
                                         "fetched_count", "provider", "mode", "curation_warning", "population_note")}


class SavedExampleProvider:
    """Both discovery/source ports, backed only by the checked fixture manifest."""

    def __init__(self, *, fixture_dir=None):
        self._root = Path(fixture_dir) if fixture_dir is not None else _DEFAULT_FIXTURES
        try:
            self._manifest = json.loads((self._root / "manifest.json").read_text(encoding="utf-8"))
            if self._manifest["schema_version"] != "mvp.saved-example-manifest.v1":
                raise ValueError()
            self._entries = self._manifest["sources"]
            self._papers, self._sources = [], {}
            for entry in self._entries:
                # Manifest files are local application data, never user-selected paths.
                if any(Path(entry[key]).name != entry[key] for key in ("metadata_file", "xml_file")):
                    raise ValueError()
                raw = (self._root / entry["xml_file"]).read_bytes()
                metadata_raw = (self._root / entry["metadata_file"]).read_bytes()
                if hashlib.sha256(raw).hexdigest() != entry["xml_sha256"] or hashlib.sha256(metadata_raw).hexdigest() != entry["metadata_sha256"]:
                    raise ValueError()
                row = json.loads(metadata_raw)
                root = safe_xml(raw, "Saved example")
                article_meta = _child(_child(root, "front"), "article-meta")
                sections = []
                for abstract in _children(article_meta, "abstract"):
                    # Reuse the same canonical whitespace convention as JATS blocks.
                    sections.extend(_text(node) for node in abstract.iter() if str(node.tag).rsplit("}", 1)[-1] == "p")
                authors = row.get("authorList", {}).get("author", [])
                paper = Paper(title=row["title"], pmid=entry["pmid"], doi=entry["doi"], pmcid=entry["pmcid"],
                              authors=[item["fullName"] for item in authors if item.get("fullName")],
                              year=int(row["pubYear"]) if row.get("pubYear") else None,
                              abstract="\n\n".join(filter(None, sections)),
                              url=f"https://pubmed.ncbi.nlm.nih.gov/{entry['pmid']}/")
                prepared = prepare_permitted_xml(paper, raw, row, retrieved_at=entry["retrieved_at"], provider="europe_pmc_saved_example")
                prepared = prepared.model_copy(update={"warnings": [self._manifest["curation_warning"]]})
                self._papers.append(paper)
                self._sources[paper.id] = prepared
        except (OSError, ValueError, KeyError, TypeError):
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
