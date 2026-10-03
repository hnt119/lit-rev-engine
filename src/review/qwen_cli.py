"""Cloud retrieval entry point; existing ledger commands retain their frozen CLI."""

import argparse
import json
import os
import sqlite3
import sys

from . import cli as ledger_cli
from .cloud_retrieval import search_sources_cloud
from .qwen import QwenProfile
from .qwen import read_json
from .store import ReviewStore


def _command(argv):
    """Inspect only the global --db prefix, never query text or a file argument."""
    index = 0
    while index < len(argv):
        item = argv[index]
        if item == "--db":
            index += 2
        elif item.startswith("--db="):
            index += 1
        else:
            return item
    return None


def _parser():
    parser = argparse.ArgumentParser(description="Optional cloud Qwen source candidates; human verification remains explicit.")
    parser.add_argument("--db", metavar="PATH", help="Review SQLite ledger path")
    commands = parser.add_subparsers(dest="command", required=True)
    retrieve = commands.add_parser("retrieve-qwen", help="Cloud Qwen embeddings/hybrid/reranking or receipt replay")
    retrieve.add_argument("project_id")
    retrieve.add_argument("--query", required=True)
    retrieve.add_argument("--mode", choices=("qwen_hybrid", "qwen_rerank"), default="qwen_hybrid")
    retrieve.add_argument("--scope", choices=("included", "all_attached"), default="included")
    retrieve.add_argument("--top-k", type=int, default=5)
    retrieve.add_argument("--candidate-k", type=int, default=20)
    retrieve.add_argument("--index", help="Rebuildable project/source/profile embedding cache (hybrid only)")
    retrieve.add_argument("--rebuild-index", action="store_true", help="Explicitly replace a stale Qwen index")
    retrieve.add_argument("--receipt", help="New immutable cloud response/replay receipt path")
    retrieve.add_argument("--replay", help="Saved receipt: perform no network calls")
    retrieve.add_argument("--replay-sha256", help="Trusted receipt_sha256 from the original retrieval trace")
    retrieve.add_argument("--allow-paid-inference", action="store_true", help="Explicitly enable legacy paid DeepInfra inference")
    export = commands.add_parser("qwen-export", help="Export an offline source job for a free Kaggle GPU notebook")
    export.add_argument("project_id")
    export.add_argument("--queries", required=True, help="JSON list of {id, query}; no answers or credentials")
    export.add_argument("--job", required=True, help="New immutable job output path")
    export.add_argument("--scope", choices=("included", "all_attached"), default="included")
    export.add_argument("--top-k", type=int, default=5)
    export.add_argument("--candidate-k", type=int, default=20)
    imported = commands.add_parser("qwen-import", help="Validate Kaggle results locally without inference or credentials")
    imported.add_argument("project_id")
    imported.add_argument("--job", required=True)
    imported.add_argument("--job-sha256", required=True, help="Trusted hash retained when the job was exported")
    imported.add_argument("--results", required=True)
    imported.add_argument("--results-sha256", help="Expected saved result payload hash for replay")
    imported.add_argument("--receipt", required=True, help="New immutable validation receipt output path")
    return parser


def _redact(message):
    for name in ("DEEPINFRA_API_KEY", "NCBI_API_KEY", "AGNES_API_KEY"):
        key = os.environ.get(name)
        if key:
            message = message.replace(key, "[REDACTED]")
    return message


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if _command(argv) not in {"retrieve-qwen", "qwen-export", "qwen-import"}:
        if _command(argv) in {"--help", "-h"}:
            ledger_cli._parser().print_help()
            print("\nOptional Qwen commands: qwen-export, qwen-import, retrieve-qwen (run each with --help)")
            return 0
        return ledger_cli.main(argv)
    try:
        args = _parser().parse_args(argv)
        if args.command in {"qwen-export", "qwen-import"}:
            from pathlib import Path
            from .qwen_batch import export_job, import_results
            with ReviewStore(args.db) as store:
                if args.command == "qwen-export":
                    result = export_job(store, args.project_id, read_json(Path(args.queries).read_bytes()),
                                        output_path=args.job, scope=args.scope, top_k=args.top_k,
                                        candidate_k=args.candidate_k)
                    # Do not dump source text to stdout: retain the immutable job on disk.
                    result = {"status": "exported", "job_path": str(Path(args.job).resolve()),
                              "job_sha256": result["payload_sha256"]}
                else:
                    result = import_results(store, args.project_id, job_path=args.job,
                                            job_sha256=args.job_sha256, results_path=args.results,
                                            results_sha256=args.results_sha256, receipt_path=args.receipt)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
            return 0
        if args.replay is None:
            if not args.allow_paid_inference:
                raise ValueError("Paid inference is disabled even with DEEPINFRA_API_KEY configured; use qwen-export/qwen-import for Kaggle, or explicitly pass --allow-paid-inference")
            if args.receipt is None:
                raise ValueError("Live Qwen retrieval requires --receipt with a new output path")
            if args.mode == "qwen_hybrid" and args.index is None:
                raise ValueError("Live Qwen hybrid retrieval requires --index to retain document embeddings")
        with ReviewStore(args.db) as store:
            result = search_sources_cloud(store, args.project_id, args.query, mode=args.mode,
                                          scope=args.scope, top_k=args.top_k, candidate_k=args.candidate_k,
                                          profile=QwenProfile.from_env(), index_path=args.index,
                                          rebuild_index=args.rebuild_index, receipt_path=args.receipt,
                                          replay_path=args.replay, replay_sha256=args.replay_sha256)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
        return 0
    except (ValueError, OSError, sqlite3.Error, KeyboardInterrupt) as error:
        print("review: " + _redact(str(error) or "interrupted"), file=sys.stderr)
        return 1
