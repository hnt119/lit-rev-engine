"""Noninteractive review ledger, offline replay, and explicit PubMed searches."""

import argparse
import hashlib
import json
import math
import os
import shlex
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from src.search.pubmed_search import PubMedClient, capture_pubmed_search, import_pubmed_capture, verify_pubmed_capture

from .importers import load_records_bytes
from .models import SearchRunSpec
from .store import ReviewStore


def _redact(message):
    key = os.environ.get("NCBI_API_KEY")
    return message.replace(key, "[REDACTED]") if key else message


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        super().error(_redact(message))


def _json_argument(value, name, dictionary=False):
    def pairs(entries):
        result = {}
        for key, item in entries:
            if key in result:
                raise ValueError(f"duplicate object key {key!r}")
            result[key] = item
        return result

    def constant(token):
        raise ValueError("nonfinite JSON value")

    def number(token):
        parsed = float(token)
        if not math.isfinite(parsed):
            raise ValueError("nonfinite JSON number")
        return parsed

    try:
        parsed = json.loads(value, object_pairs_hook=pairs, parse_constant=constant, parse_float=number)
    except (ValueError, RecursionError) as error:
        raise ValueError(f"Invalid {name}: {error}") from error
    if dictionary and not isinstance(parsed, dict):
        raise ValueError(f"{name} must be a JSON object")
    return parsed


def _evidence_payload(path, *, proposal):
    payload = _json_argument(Path(path).read_text(encoding="utf-8"), "evidence payload JSON", dictionary=True)
    required = {"study_id", "document_id", "field", "value", "context", "anchor"}
    allowed = required | ({"kind", "appraisal"} if proposal else {"appraisal"})
    if set(payload) - allowed:
        raise ValueError("Evidence payload has unknown keys: " + ", ".join(sorted(set(payload) - allowed)))
    if required - set(payload):
        raise ValueError("Evidence payload is missing required keys: " + ", ".join(sorted(required - set(payload))))
    return payload


def _parser():
    parser = _ArgumentParser(
        description="Review ledger: import citation records, explicitly search PubMed, screen reports, and export reconciled counts. Included reports are not linked into studies automatically.",
    )
    parser.add_argument("--db", metavar="PATH", help="SQLite ledger path (default: repository data/reviews.sqlite3)")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="Create a systematic or scoping review project")
    create.add_argument("--title", required=True)
    create.add_argument("--type", choices=("systematic", "scoping"), required=True)
    create.add_argument("--question", required=True)
    create.add_argument("--protocol", default="")
    create.add_argument("--eligibility-json", default="null")
    commands.add_parser("projects", help="List review projects")
    imported = commands.add_parser("import", help="Import JSON, RIS, or PubMed XML without external requests")
    imported.add_argument("project_id")
    imported.add_argument("file")
    imported.add_argument("--format", choices=("json", "ris", "pubmed_xml"))
    imported.add_argument("--source", required=True)
    imported.add_argument("--query")
    imported.add_argument("--searched-at", metavar="ISO")
    imported.add_argument("--filters-json", default="{}")
    imported.add_argument("--notes", default="")
    imported.add_argument("--reported-count", type=int)
    imported.add_argument("--import-key")
    search = commands.add_parser("search-pubmed", help="Capture one explicit PubMed search and import its verified records")
    search.add_argument("project_id")
    search.add_argument("--query", required=True)
    search.add_argument("--output", required=True, metavar="DIRECTORY")
    search.add_argument("--email", help="NCBI contact email (otherwise NCBI_EMAIL); optional API key uses NCBI_API_KEY only")
    search.add_argument("--sort", choices=("pub_date", "relevance"), default="pub_date")
    search.add_argument("--datetype", choices=("pdat", "edat"))
    search.add_argument("--mindate", metavar="DATE")
    search.add_argument("--maxdate", metavar="DATE")
    search.add_argument("--batch-size", type=int, default=200)
    search.add_argument("--import-key")
    verify = commands.add_parser("verify-pubmed", help="Verify saved PubMed artifacts offline without opening a ledger")
    verify.add_argument("directory")
    replay = commands.add_parser("import-pubmed", help="Import a complete verified PubMed capture offline")
    replay.add_argument("project_id")
    replay.add_argument("directory")
    replay.add_argument("--import-key")
    study = commands.add_parser("study-create", help="Create a manual study identity; identifiers are descriptive metadata")
    study.add_argument("project_id")
    study.add_argument("--label", required=True)
    study.add_argument("--reviewer", required=True)
    study.add_argument("--reason", required=True)
    study.add_argument("--identifiers-json", default="{}")
    studies = commands.add_parser("studies", help="List the manual study inventory, including unused entries")
    studies.add_argument("project_id")
    for name in ("link-studies", "adjudicate-links"):
        linked = commands.add_parser(name, help="Propose a complete report-study association set" if name == "link-studies" else "Resolve existing report-study proposals")
        linked.add_argument("project_id")
        linked.add_argument("record_id")
        association = linked.add_mutually_exclusive_group(required=True)
        association.add_argument("--study-id", dest="study_ids", action="append", help="Repeat for each associated study; replaces the reviewer's complete set")
        association.add_argument("--clear", action="store_true", help="Explicitly record no established association")
        linked.add_argument("--reviewer", required=True)
        linked.add_argument("--reason", required=True)
    links = commands.add_parser("links", help="Show current associations and their append-only history in one snapshot")
    links.add_argument("project_id")
    links.add_argument("--record-id")
    attached = commands.add_parser("attach-source", help="Attach one retained source version and exact quotation blocks")
    attached.add_argument("project_id")
    attached.add_argument("record_id")
    attached.add_argument("path")
    attached.add_argument("--format", choices=("txt", "jats_xml", "pdf"), required=True)
    attached.add_argument("--reviewer", required=True)
    attached.add_argument("--reason", required=True)
    attached.add_argument("--filename")
    attached.add_argument("--source-url", default="")
    attached.add_argument("--version-label", default="")
    documents = commands.add_parser("documents", help="List retained source versions and the active version per report")
    documents.add_argument("project_id")
    documents.add_argument("--record-id")
    blocks = commands.add_parser("source-blocks", help="Show source metadata and exact blocks in one snapshot")
    blocks.add_argument("project_id")
    blocks.add_argument("document_id")
    for name in ("propose-evidence", "revise-evidence"):
        evidence = commands.add_parser(name, help="Create a manual quotation-backed proposal" if name == "propose-evidence" else "Append a complete replacement evidence revision")
        evidence.add_argument("project_id")
        evidence.add_argument("record_id" if name == "propose-evidence" else "evidence_id")
        evidence.add_argument("--payload", required=True, metavar="FILE")
        evidence.add_argument("--reviewer", required=True)
        evidence.add_argument("--reason", required=True)
    for name in ("review-evidence", "adjudicate-evidence"):
        reviewed = commands.add_parser(name, help="Independently confirm or reject one current revision" if name == "review-evidence" else "Resolve existing verification reviews with an explicit reason")
        reviewed.add_argument("project_id")
        reviewed.add_argument("revision_id")
        reviewed.add_argument("--decision", choices=("confirm", "reject"), required=True)
        reviewed.add_argument("--reviewer", required=True)
        reviewed.add_argument("--reason", required=True)
    evidence = commands.add_parser("evidence", help="List current manual findings and appraisal states")
    evidence.add_argument("project_id")
    evidence.add_argument("--record-id")
    evidence.add_argument("--verified-only", action="store_true")
    evidence_history = commands.add_parser("evidence-history", help="Show immutable revisions and verification reviews in one snapshot")
    evidence_history.add_argument("project_id")
    evidence_history.add_argument("--evidence-id")
    retrieved = commands.add_parser("retrieve-sources", help="Retrieve exact source passage candidates without creating verified findings")
    retrieved.add_argument("project_id")
    retrieved.add_argument("--query", required=True)
    retrieved.add_argument("--top-k", type=int, default=5)
    retrieved.add_argument("--method", choices=("token_overlap", "bm25", "bm25_context"), default="bm25")
    retrieved.add_argument("--scope", choices=("included", "all_attached"), default="included")
    for name, help_text in (
        ("records", "List canonical records and current screening/retrieval states"),
        ("history", "List immutable search/import runs"),
        ("decisions", "List append-only screening and retrieval histories"),
        ("counts", "Show report counts with pending/unresolved states and reconciliation"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("project_id")
    for name in ("screen", "adjudicate"):
        command = commands.add_parser(name, help="Append a reviewer decision" if name == "screen" else "Resolve existing review decisions with an explicit reason")
        command.add_argument("project_id")
        command.add_argument("record_id")
        command.add_argument("--stage", choices=("title_abstract", "full_text"), required=True)
        command.add_argument("--decision", choices=("include", "exclude", "uncertain"), required=True)
        command.add_argument("--reviewer", required=True)
        command.add_argument("--reason", required=name == "adjudicate", default="")
    fulltext = commands.add_parser("fulltext", help="Append full-text retrieval status for a TA-included report")
    fulltext.add_argument("project_id")
    fulltext.add_argument("record_id")
    fulltext.add_argument("--status", choices=("requested", "retrieved", "not_retrieved"), required=True)
    fulltext.add_argument("--reviewer", required=True)
    fulltext.add_argument("--reason", default="")
    exported = commands.add_parser("export", help="Export a consistent snapshot to JSON and formula-safe CSV")
    exported.add_argument("project_id")
    exported.add_argument("directory")
    return parser


def _execute(store, args):
    command = args.command
    if command == "create":
        return store.create_project(args.title, args.type, args.question, args.protocol, _json_argument(args.eligibility_json, "eligibility JSON"))
    if command == "projects":
        return store.list_projects()
    if command == "study-create":
        store.get_project(args.project_id)
        identifiers = _json_argument(args.identifiers_json, "study identifiers JSON", dictionary=True)
        return store.create_study(args.project_id, args.label, args.reviewer, args.reason, identifiers)
    if command == "studies":
        return store.list_studies(args.project_id)
    if command in {"link-studies", "adjudicate-links"}:
        method = store.record_study_links if command == "link-studies" else store.adjudicate_study_links
        return method(args.project_id, args.record_id, [] if args.clear else args.study_ids, args.reviewer, args.reason)
    if command == "links":
        with store._snapshot():
            return {"links": store.list_study_links(args.project_id, args.record_id), "events": store.list_study_link_events(args.project_id, args.record_id)}
    if command == "attach-source":
        store.get_project(args.project_id)
        path = Path(args.path)
        content = path.read_bytes()
        return store.attach_document(args.project_id, args.record_id, content, args.format, args.reviewer, args.reason, filename=path.name if args.filename is None else args.filename, source_url=args.source_url, version_label=args.version_label)
    if command == "documents":
        return store.list_documents(args.project_id, args.record_id)
    if command == "source-blocks":
        with store._snapshot():
            document = next((row for row in store.list_documents(args.project_id) if row["id"] == args.document_id), None)
            if document is None:
                raise ValueError(f"Unknown source document in project: {args.document_id}")
            return {"document": document, "blocks": store.get_source_blocks(args.project_id, args.document_id)}
    if command in {"propose-evidence", "revise-evidence"}:
        store.get_project(args.project_id)
        proposal = command == "propose-evidence"
        payload = _evidence_payload(args.payload, proposal=proposal)
        method = store.propose_evidence if proposal else store.revise_evidence
        return method(args.project_id, args.record_id if proposal else args.evidence_id, **payload, reviewer=args.reviewer, reason=args.reason)
    if command in {"review-evidence", "adjudicate-evidence"}:
        method = store.review_evidence if command == "review-evidence" else store.adjudicate_evidence
        return method(args.project_id, args.revision_id, args.decision, args.reviewer, args.reason)
    if command == "evidence":
        return store.list_evidence(args.project_id, args.record_id, verified_only=args.verified_only)
    if command == "evidence-history":
        with store._snapshot():
            return {"revisions": store.list_evidence_revisions(args.project_id, args.evidence_id), "reviews": store.list_evidence_reviews(args.project_id, args.evidence_id)}
    if command == "retrieve-sources":
        return store.search_sources(args.project_id, args.query, top_k=args.top_k, method=args.method, scope=args.scope)
    if command == "import":
        store.get_project(args.project_id)
        filters = _json_argument(args.filters_json, "filters JSON", dictionary=True)
        if args.searched_at is not None:
            try:
                datetime.fromisoformat(args.searched_at)
            except ValueError as error:
                raise ValueError("searched-at must be an ISO date or datetime") from error
        path = Path(args.file)
        content = path.read_bytes()
        records = load_records_bytes(content, args.format or path.suffix.lstrip("."), source_name=str(path))
        imported_format = args.format or {".json": "json", ".ris": "ris", ".xml": "pubmed_xml"}.get(path.suffix.lower(), "")
        spec = SearchRunSpec(
            source=args.source, query=args.query, searched_at=args.searched_at,
            filters=filters, notes=args.notes, import_format=imported_format,
            source_file=args.file, source_sha256=hashlib.sha256(content).hexdigest(),
            reported_count=args.reported_count,
        )
        return store.import_records(args.project_id, spec, records, args.import_key)
    if command == "import-pubmed":
        store.get_project(args.project_id)
        return import_pubmed_capture(store, args.project_id, args.directory, args.import_key)
    if command == "search-pubmed":
        store.get_project(args.project_id)
        if args.import_key is not None and not args.import_key.strip():
            raise ValueError("Idempotency key must be a nonempty string")
        email = args.email if args.email is not None else os.environ.get("NCBI_EMAIL")
        client = PubMedClient(email=email, api_key=os.environ.get("NCBI_API_KEY") or None)
        filters = {field: getattr(args, field) for field in ("datetype", "mindate", "maxdate") if getattr(args, field) is not None}
        capture = capture_pubmed_search(args.query, args.output, client=client, sort=args.sort, filters=filters, batch_size=args.batch_size)
        try:
            imported = import_pubmed_capture(store, args.project_id, capture["directory"], args.import_key)
        except (Exception, KeyboardInterrupt) as error:
            recovery = [sys.executable, str(Path(__file__).resolve().parents[2] / "review.py")]
            if args.db is not None:
                recovery.extend(["--db", str(Path(args.db).absolute())])
            recovery.extend(["import-pubmed", args.project_id, capture["directory"]])
            if args.import_key is not None:
                recovery.extend(["--import-key", args.import_key])
            detail = str(error) or "interrupted"
            raise ValueError(f"Capture retained at {capture['directory']}. Ledger import failed: {detail}. Recover with: {shlex.join(recovery)}") from None
        return {"capture": capture, "import": imported}
    if command == "records":
        return store.list_records(args.project_id)
    if command == "history":
        return store.list_search_runs(args.project_id)
    if command == "decisions":
        # Capture the two histories together rather than mixing concurrent versions.
        with store._snapshot():
            return {"decisions": store.list_decisions(args.project_id), "retrieval_events": store.list_retrieval_events(args.project_id)}
    if command in {"screen", "adjudicate"}:
        method = store.record_decision if command == "screen" else store.adjudicate
        return method(args.project_id, args.record_id, args.stage, args.decision, args.reviewer, args.reason)
    if command == "fulltext":
        return store.set_full_text_status(args.project_id, args.record_id, args.status, args.reviewer, args.reason)
    if command == "counts":
        return store.counts(args.project_id)
    if command == "export":
        return store.export_project(args.project_id, args.directory)
    raise ValueError(f"Unknown command: {command}")


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.command == "verify-pubmed":
            # Offline verification is independent of even an invalid supplied DB path.
            result = verify_pubmed_capture(args.directory)
        else:
            with ReviewStore(args.db) as store:
                result = _execute(store, args)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    except (ValueError, OSError, sqlite3.Error, KeyboardInterrupt) as error:
        print(f"review: {_redact(str(error) or 'interrupted')}", file=sys.stderr)
        return 1
    return 0
