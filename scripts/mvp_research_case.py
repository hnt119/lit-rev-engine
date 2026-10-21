#!/usr/bin/env python3
"""Audit one explicit saved research case without provider calls or model loads."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "audit"))
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New private output directory; never overwrites")
    parser.add_argument("--data-dir", type=Path, help="Existing explicit web data directory (audit only)")
    parser.add_argument("--workspace-id")
    parser.add_argument("--search-id")
    parser.add_argument("--preparation-id")
    parser.add_argument("--map-id")
    args = parser.parse_args(argv)
    from pydantic import ValidationError
    from src.mvp.ports import MvpError
    from src.mvp.research_case import ResearchCaseProtocol, audit_saved_case, readiness_manifest, write_private_manifest
    try:
        protocol = ResearchCaseProtocol.model_validate_json(args.protocol.read_text(encoding="utf-8"))
        if args.command == "check":
            if any((args.data_dir, args.workspace_id, args.search_id, args.preparation_id, args.map_id)):
                parser.error("check does not read a workspace; use audit for named saved records")
            manifest = readiness_manifest(protocol)
        else:
            if not all((args.data_dir, args.workspace_id, args.search_id)):
                parser.error("audit requires --data-dir, --workspace-id and --search-id")
            directory = args.data_dir.expanduser().absolute()
            required = [directory / "web-credentials.sqlite3", directory / "workspaces.sqlite3"]
            if args.map_id:
                required.append(directory / "paper-maps.sqlite3")
            if any(not path.is_file() or path.is_symlink() for path in required):
                raise ValueError("Expected existing private MVP databases were not found")
            from src.mvp.adapters.storage import SQLiteWorkspaceStorage
            from src.mvp.service import MVPService
            from src.mvp.workspace_ui import WorkspaceUIStore
            registry = WorkspaceUIStore(directory / "web-credentials.sqlite3")
            _, handle = registry.get_bound_handle_for_worker(args.workspace_id)
            # A reader has no provider capability. It cannot discover/fetch even
            # if a future audit accidentally attempts to call one of them.
            service = MVPService(SQLiteWorkspaceStorage(directory / "workspaces.sqlite3"), None, None)
            maps = None
            if args.map_id:
                from src.mvp.adapters.map_storage import MapStore
                maps = MapStore(directory / "paper-maps.sqlite3")
            manifest = audit_saved_case(service, handle, protocol, search_id=args.search_id,
                preparation_id=args.preparation_id, map_store=maps, map_id=args.map_id)
        path = write_private_manifest(args.output, manifest)
        print(json.dumps({"manifest_path": str(path), "case_id": protocol.case_id,
            "provider_status": manifest["provider_execution"]["status"],
            "model_status": manifest["model_execution"]["status"],
            "human_usefulness": manifest["human_usefulness"],
            "publication": manifest["publication"]["status"]}))
    except MvpError as error:
        print(json.dumps({"status": "FAILED", "error_code": error.code}), file=sys.stderr)
        return 2
    except (ValueError, OSError, ValidationError):
        # Pydantic errors can echo private inputs; report the category only.
        print(json.dumps({"status": "FAILED", "error_code": "invalid_case_input_or_output"}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
