#!/usr/bin/env python3
"""Operator-only whole-application stopped backup and separate-directory restore."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.web_api.deployment import DeploymentConfig
from src.web_api.hosted_operations import OperationError, create_backup, restore_backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    backup = commands.add_parser("backup", help="Stop the entire application before taking a consistent backup")
    backup.add_argument("--output", type=Path, required=True)
    restore = commands.add_parser("restore", help="Verify into a new directory; never overwrite live state")
    restore.add_argument("--archive", type=Path, required=True)
    restore.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    try:
        config = DeploymentConfig.from_environment()
        if config.mode != "hosted":
            raise OperationError("Stopped-app operations require explicit hosted configuration.")
        if args.operation == "backup":
            result = create_backup(config.persistent_root, config.data_dir, args.output, validate_storage=config.validate_storage)
        else:
            result = restore_backup(config.persistent_root, args.archive, args.destination, validate_storage=config.validate_storage)
        print(json.dumps({"operation": args.operation, **result}))
        return 0
    except (ValueError, OSError):
        # Files and archive errors can contain private stored paths. Keep CLI
        # output generic; the operator can diagnose with local trusted tools.
        print("Stopped-app operation refused. Check configuration, exclusive shutdown, paths and archive integrity.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
