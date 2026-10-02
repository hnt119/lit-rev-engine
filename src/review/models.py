"""Shared, dependency-free data contracts for review imports."""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class BibliographicRecord:
    title: str
    authors: list[str] = field(default_factory=list)
    year: Optional[int] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    abstract: str = ""
    url: str = ""
    source_id: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchRunSpec:
    source: str
    query: Optional[str] = None
    searched_at: Optional[str] = None
    filters: dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    import_format: str = ""
    source_file: str = ""
    source_sha256: str = ""
    reported_count: Optional[int] = None
    execution: Optional[dict[str, Any]] = None
