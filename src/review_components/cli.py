"""New component commands, delegating every old command unchanged."""

import argparse
import json
from pathlib import Path
import sqlite3
import sys

from ..review import qwen_cli
from ..review.store import ReviewStore
from . import core
from .ledger import execution_paths, export_job, import_results


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    command = qwen_cli._command(argv)
    if command not in {"components-export", "components-import"}:
        if command in {"--help", "-h"}:
            try:
                qwen_cli.main(argv)
            except SystemExit as error:
                if error.code not in (0, None):
                    raise
            print("\nComponent experiment: components-export, components-import (run each with --help)")
            return 0
        return qwen_cli.main(argv)
    parser = argparse.ArgumentParser(description="Component retrieval candidates for independent human review")
    parser.add_argument("--db")
    commands = parser.add_subparsers(dest="command", required=True)
    exported = commands.add_parser("components-export")
    exported.add_argument("project_id")
    exported.add_argument("--queries", required=True)
    exported.add_argument("--job", required=True)
    exported.add_argument("--scope", choices=("included", "all_attached"), default="included")
    imported = commands.add_parser("components-import")
    imported.add_argument("project_id")
    imported.add_argument("--job", required=True)
    imported.add_argument("--job-sha256", required=True)
    imported.add_argument("--results", required=True)
    imported.add_argument("--results-sha256")
    imported.add_argument("--receipt", required=True)
    args = parser.parse_args(argv)
    try:
        with ReviewStore(args.db) as store:
            if args.command == "components-export":
                envelope = export_job(store, args.project_id, core.read_json(Path(args.queries).read_bytes()), output_path=args.job, scope=args.scope)
                result = {"status": "exported", "job_path": str(Path(args.job).resolve()), "job_sha256": envelope["payload_sha256"],
                          "files_to_upload": [{"path": str(Path(args.job).resolve()), "filename": "job.json"},
                                              *[{"path": str(path.resolve()), "filename": name, **envelope["payload"]["execution_files"][name]} for name, path in execution_paths().items()]]}
            else:
                result = import_results(store, args.project_id, job_path=args.job, job_sha256=args.job_sha256,
                                        results_path=args.results, results_sha256=args.results_sha256, receipt_path=args.receipt)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
        return 0
    except (ValueError, OSError, sqlite3.Error, KeyboardInterrupt) as error:
        print("review-components: " + qwen_cli._redact(str(error) or "interrupted"), file=sys.stderr)
        return 1
