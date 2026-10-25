#!/usr/bin/env python3
"""Headless opt-in smoke, using the same typed services as the browser.

Default: rights-checked saved article, offline, unreviewed exports. No Streamlit
import, model execution or paid inference. Live calls require --allow-live.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.mvp.bootstrap import build_service, public_runtime_info
from src.mvp.contracts import (
    BundleJudgment, CreateWorkspaceRequest, PrepareSourcesRequest,
    RetrieveEvidenceRequest, SaveAssessmentRequest, SearchRequest,
    SourceContextRequest,
)
from src.mvp.ports import MvpError


def run(args):
    output = Path(args.output).expanduser().absolute()
    if output.exists():
        raise ValueError("Choose a new output directory; existing output is never overwritten.")
    if args.mode == "live" and (not args.allow_live or not args.query):
        raise ValueError("Live smoke requires both --allow-live and an explicit --query.")
    info = public_runtime_info()["saved_example"]
    question = args.question or info["question"]
    query = args.query if args.mode == "live" else info["query"]
    with tempfile.TemporaryDirectory(prefix="lre-mvp-smoke-") as temporary:
        service = build_service(mode=args.mode, data_dir=args.data_dir or Path(temporary))
        handle = service.create_workspace(CreateWorkspaceRequest(question=question))
        search = service.search_literature(handle, SearchRequest(request_id=str(uuid4()), query=query, max_results=3, research_question=question))
        if not search.papers:
            raise ValueError("The bounded search returned no papers; no source or judgment was fabricated.")
        preparation = service.prepare_sources(handle, PrepareSourcesRequest(request_id=str(uuid4()), search_id=search.id, paper_ids=[search.papers[0].id]))
        run = service.retrieve_evidence(handle, RetrieveEvidenceRequest(request_id=str(uuid4()), question=question))
        for passage in run.passages:
            context = service.get_source_context(handle, SourceContextRequest(run_id=run.id, passage_id=passage.id))
            assert context.block.text[passage.anchor.start:passage.anchor.end] == passage.anchor.quote
        if args.save_example_judgment:
            service.save_assessment(handle, SaveAssessmentRequest(request_id=str(uuid4()), run_id=run.id,
                bundle=BundleJudgment(status="uncertain", reason="Synthetic software smoke only; this is not a human evidence assessment.")))
        exported = service.export_workspace(handle)
        output.mkdir(parents=True, exist_ok=False)
        (output / "evidence.csv").write_text(exported.csv_text, encoding="utf-8", newline="")
        (output / "audit.json").write_text(exported.json_text, encoding="utf-8")
        assert "streamlit" not in sys.modules, "Headless workflow must not import Streamlit"
        print(json.dumps({"mode": args.mode, "search_provider": search.provider, "reported": search.total_reported,
                          "fetched": search.fetched_count, "source_types": [source.source_type for source in preparation.sources],
                          "passages": len(run.passages), "synthetic_judgment": args.save_example_judgment,
                          "output": str(output), "streamlit_imported": False, "paid_inference_calls": 0}))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["saved_example", "live"], default="saved_example")
    parser.add_argument("--allow-live", action="store_true")
    parser.add_argument("--query")
    parser.add_argument("--question")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--output", required=True)
    parser.add_argument("--save-example-judgment", action="store_true", help="Append an explicitly synthetic uncertain software-test record")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (MvpError, ValueError, OSError) as error:
        print(json.dumps({"error": str(error) if isinstance(error, (MvpError, ValueError)) else "Local smoke output failed."}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
