"""Immutable source bytes and deterministic version-specific quotation blocks."""

import hashlib
import json
import platform
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from uuid import uuid4

from .identity import normalize_doi, normalize_pmid


_FORMATS = {"txt", "jats_xml", "pdf"}
_DEFAULT_NAMES = {"txt": "source.txt", "jats_xml": "source.xml", "pdf": "source.pdf"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(content):
    return hashlib.sha256(content).hexdigest()


def _tag(element):
    return element.tag.rsplit("}", 1)[-1]


def _inline(element):
    return " ".join("".join(element.itertext()).split()) if element is not None else ""


def _children(element, tag):
    return [child for child in element if _tag(child) == tag]


def _child(element, tag):
    return next((child for child in element if _tag(child) == tag), None)


def _decode(content, label):
    try:
        return content.decode("utf-8-sig")
    except UnicodeError:
        raise ValueError(f"{label} source must use valid UTF-8") from None


def _table_text(element):
    lines = []
    for name in ("label", "caption"):
        text = _inline(_child(element, name))
        if text:
            lines.append(text)
    for row in element.iter():
        if _tag(row) == "tr":
            cells = [_inline(cell) for cell in row if _tag(cell) in {"th", "td"}]
            text = "\t".join(cells)
            if text.strip():
                lines.append(text)
    for foot in _children(element, "table-wrap-foot"):
        text = _inline(foot)
        if text:
            lines.append(text)
    return "\n".join(lines)


def _source_identifiers(root):
    values = {}
    for front in _children(root, "front"):
        for metadata in _children(front, "article-meta"):
            for element in _children(metadata, "article-id"):
                kind = element.get("pub-id-type", "").strip().lower()
                normalizer = {"doi": normalize_doi, "pmid": normalize_pmid}.get(kind)
                if normalizer is None:
                    continue
                try:
                    normalized = normalizer("".join(element.itertext()))
                except ValueError:
                    raise ValueError(f"JATS source has invalid own {kind.upper()}") from None
                if normalized is None or (kind in values and values[kind] != normalized):
                    raise ValueError(f"JATS source has missing or conflicting own {kind.upper()}")
                values[kind] = normalized
    return values


def _jats(content):
    text = _decode(content, "JATS XML")
    if re.search(r"<!ENTITY\b", text, re.I):
        raise ValueError("JATS XML source ENTITY declarations are unsupported")
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        raise ValueError("JATS XML source is malformed") from None
    if _tag(root) != "article":
        raise ValueError("JATS XML source requires an article root")
    if any(_tag(element).lower() in {"error", "errorlist"} for element in root.iter()):
        raise ValueError("JATS XML source contains an error element")
    identifiers = _source_identifiers(root)
    blocks = []

    def visit(element, path, ancestors, section_title=None):
        tag = _tag(element)
        if tag in {"ref-list", "ref", "sub-article"}:
            return
        if tag == "sec":
            section_title = _inline(_child(element, "title")) or section_title
        in_body = "body" in ancestors
        selected = (tag == "article-title" and "front" in ancestors) or (tag == "p" and (in_body or "abstract" in ancestors)) or (tag == "table-wrap" and in_body)
        if selected:
            canonical = _table_text(element) if tag == "table-wrap" else _inline(element)
            if canonical:
                locator = {"type": "xml_element", "path": path, "tag": tag}
                if element.get("id") is not None:
                    locator["element_id"] = element.get("id")
                if section_title:
                    locator["section_title"] = section_title
                if tag == "table-wrap":
                    label = _inline(_child(element, "label"))
                    if label:
                        locator["table_label"] = label
                blocks.append({"id": "xml:" + path, "ordinal": len(blocks) + 1, "text": canonical, "locator": locator})
            # A selected table is one complete block; its paragraphs never duplicate it.
            if tag == "table-wrap":
                return
        siblings = {}
        for child in element:
            child_tag = _tag(child)
            siblings[child_tag] = siblings.get(child_tag, 0) + 1
            visit(child, f"{path}/{child_tag}[{siblings[child_tag]}]", ancestors + [tag], section_title)

    visit(root, "/article[1]", [])
    if not blocks:
        raise ValueError("JATS XML source has no nonempty extractable blocks")
    return blocks, identifiers


def _pdf(content):
    try:
        import fitz
    except ImportError:
        raise ValueError("PDF source parsing requires the existing PyMuPDF dependency") from None
    try:
        with fitz.open(stream=content, filetype="pdf") as document:
            if not document.is_pdf or document.is_encrypted or document.needs_pass or (document.metadata or {}).get("encryption"):
                raise ValueError("PDF source is encrypted or unreadable")
            blocks = [{"id": f"pdf:page:{page.number + 1}", "ordinal": page.number + 1, "text": page.get_text("text", sort=True), "locator": {"type": "pdf_page", "page": page.number + 1}} for page in document]
    except Exception:
        raise ValueError("PDF source is corrupt, encrypted, or unreadable") from None
    if not any(block["text"].strip() for block in blocks):
        raise ValueError("PDF source has no extracted text; OCR is unavailable")
    return blocks, fitz.VersionBind


def parse_source_bytes(content, format):
    """Parse one byte snapshot without source paths, network, models, or settings."""
    if not isinstance(content, bytes) or not content:
        raise ValueError("Source content must be nonempty bytes")
    if not isinstance(format, str) or format not in _FORMATS:
        raise ValueError("Source format must be txt, jats_xml, or pdf")
    metadata = {"python_version": platform.python_version()}
    identifiers = {}
    if format == "txt":
        text = _decode(content, "TXT")
        if not text.strip():
            raise ValueError("TXT source is empty or whitespace only")
        blocks = [{"id": "text:1", "ordinal": 1, "text": text, "locator": {"type": "text_block", "ordinal": 1}}]
        metadata.update(encoding="utf-8-sig", normalization="none")
    elif format == "jats_xml":
        blocks, identifiers = _jats(content)
        metadata.update(normalization="xml-whitespace-v1", tables="rows-tab-separated-v1", external_dtd="ignored", entities="rejected")
    else:
        blocks, version = _pdf(content)
        metadata.update(pymupdf_version=version, sort=True, normalization="none")
    return {"parser_id": f"lit-rev-engine.source.v1.{format}", "parser_metadata": metadata, "source_identifiers": identifiers, "blocks": blocks}


def _filename(value):
    if not isinstance(value, str) or not value.strip() or value in {".", ".."} or "/" in value or "\\" in value or any(unicodedata.category(char) in {"Cc", "Cf", "Cs"} for char in value):
        raise ValueError("Source filename must be a safe single basename without traversal or controls")
    return value


class DocumentLedger:
    """Document version persistence on the existing review connection."""

    def __init__(self, store):
        self.store = store
        store._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS source_documents (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL, record_id TEXT NOT NULL,
                version INTEGER NOT NULL, format TEXT NOT NULL, filename TEXT NOT NULL,
                source_url TEXT NOT NULL, version_label TEXT NOT NULL,
                source_sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL,
                parser_id TEXT NOT NULL, parser_metadata TEXT NOT NULL,
                source_identifiers TEXT NOT NULL, blocks_sha256 TEXT NOT NULL,
                block_count INTEGER NOT NULL, reviewer TEXT NOT NULL, reason TEXT NOT NULL,
                created_at TEXT NOT NULL, content BLOB NOT NULL, blocks_json TEXT NOT NULL,
                UNIQUE(project_id, id), UNIQUE(project_id, record_id, version),
                FOREIGN KEY(project_id, record_id) REFERENCES records(project_id, id)
            );
            CREATE INDEX IF NOT EXISTS source_documents_record ON source_documents(project_id, record_id, version);
            """
        )

    @staticmethod
    def _metadata(row, active):
        result = {key: row[key] for key in row.keys() if key not in {"content", "blocks_json"}}
        result["parser_metadata"] = json.loads(result["parser_metadata"])
        result["source_identifiers"] = json.loads(result["source_identifiers"])
        result["active"] = active
        return result

    def attach_document(self, project_id, record_id, content, format, reviewer, reason, *, filename=None, source_url="", version_label=""):
        self.store._record(project_id, record_id)
        for field, value in (("reviewer", reviewer), ("reason", reason)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Source {field} must be nonempty")
        if not isinstance(source_url, str) or not isinstance(version_label, str):
            raise ValueError("Source URL and version label must be strings")
        parsed = parse_source_bytes(content, format)
        filename = _filename(_DEFAULT_NAMES[format] if filename is None else filename)
        blocks_json = _canonical_json(parsed["blocks"])
        with self.store._connection:
            self.store._connection.execute("BEGIN IMMEDIATE")
            canonical = self.store._record(project_id, record_id)
            for identifier, value in parsed["source_identifiers"].items():
                if canonical[identifier] is not None and canonical[identifier] != value:
                    raise ValueError(f"Source {identifier.upper()} contradicts the canonical report")
            version = self.store._connection.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM source_documents WHERE project_id = ? AND record_id = ?", (project_id, record_id)
            ).fetchone()[0]
            document_id = str(uuid4())
            self.store._connection.execute(
                "INSERT INTO source_documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (document_id, project_id, record_id, version, format, filename, source_url, version_label, _hash(content), len(content), parsed["parser_id"], _canonical_json(parsed["parser_metadata"]), _canonical_json(parsed["source_identifiers"]), _hash(blocks_json.encode("utf-8")), len(parsed["blocks"]), reviewer, reason, _now(), content, blocks_json),
            )
            row = self.store._connection.execute("SELECT * FROM source_documents WHERE id = ?", (document_id,)).fetchone()
        return self._metadata(row, True)

    def list_documents(self, project_id, record_id=None):
        with self.store._snapshot():
            self.store._project(project_id)
            query, params = "SELECT * FROM source_documents WHERE project_id = ?", [project_id]
            if record_id is not None:
                self.store._record(project_id, record_id)
                query += " AND record_id = ?"
                params.append(record_id)
            rows = self.store._connection.execute(query + " ORDER BY rowid", params).fetchall()
            latest = {}
            for row in rows:
                latest[row["record_id"]] = row["id"]
            return [self._metadata(row, latest[row["record_id"]] == row["id"]) for row in rows]

    def _checked(self, project_id, document_id):
        self.store._project(project_id)
        row = self.store._connection.execute(
            "SELECT * FROM source_documents WHERE project_id = ? AND id = ?", (project_id, document_id)
        ).fetchone()
        if row is None:
            raise ValueError(f"Unknown source document in project: {document_id}")
        content = row["content"]
        if not isinstance(content, bytes) or _hash(content) != row["source_sha256"] or len(content) != row["size_bytes"]:
            raise ValueError("Stored source document bytes/hash are corrupt")
        try:
            blocks = json.loads(row["blocks_json"])
            blocks_json = _canonical_json(blocks)
        except (ValueError, TypeError, RecursionError):
            raise ValueError("Stored source document blocks are corrupt") from None
        if not isinstance(blocks, list) or _hash(blocks_json.encode("utf-8")) != row["blocks_sha256"] or len(blocks) != row["block_count"]:
            raise ValueError("Stored source document blocks/hash are corrupt")
        return content, blocks

    def get_document_bytes(self, project_id, document_id):
        with self.store._snapshot():
            return self._checked(project_id, document_id)[0]

    def get_source_blocks(self, project_id, document_id):
        with self.store._snapshot():
            return self._checked(project_id, document_id)[1]
