"""Noninteractive review ledger, offline replay, and explicit PubMed searches."""

import argparse
import hashlib
import json
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
    try:
        parsed = json.loads(value, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(f"Invalid JSON constant {token}")))
    except ValueError as error:
        raise ValueError(f"Invalid {name}: {error}") from error
    if dictionary and not isinstance(parsed, dict):
        raise ValueError(f"{name} must be a JSON object")
    return parsed


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
