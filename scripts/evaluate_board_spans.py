#!/usr/bin/env python3
"""Run the frozen offline development comparison; keep detailed output local."""
from argparse import ArgumentParser
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.mvp.span_evaluation import DEFAULT_MANIFEST, FROZEN_MANIFEST_SHA256, run_comparison


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--expected-sha256", default=FROZEN_MANIFEST_SHA256)
    parser.add_argument("--output", type=Path, required=True, help="Local JSON receipt; use an ignored acceptance directory.")
    args = parser.parse_args()
    report = run_comparison(args.manifest, expected_sha256=args.expected_sha256)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"manifest_sha256": report["manifest_sha256"], "gates": report["gates"],
        "summaries": [{key: value for key, value in summary.items() if key != "groups"} for summary in report["summaries"]],
        "primary_regressions": report["primary_per_case_anchor_regressions"], "human_usefulness": "NOT_RUN"}, indent=2))


if __name__ == "__main__":
    main()
