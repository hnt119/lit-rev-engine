#!/usr/bin/env python3
"""Explicit optional map worker. No provider calls or model downloads."""
import argparse
import os
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("MVP_WEB_DATA_DIR", ROOT / ".mvp-web-state")))
    parser.add_argument("--check-setup", action="store_true", help="Inspect dependency/snapshot availability without loading weights")
    args = parser.parse_args()
    from src.mvp.adapters.paper_embeddings import LocalPaperEmbedder
    embedder = LocalPaperEmbedder(enabled=os.environ.get("MVP_MAP_ENABLED") == "1")
    ready, reason = embedder.readiness()
    if args.check_setup:
        print(reason)
        return 0 if ready else 2
    if not ready:
        parser.error(reason)
    from src.mvp.adapters.storage import SQLiteWorkspaceStorage
    from src.mvp.adapters.map_storage import MapStore
    from src.mvp.workspace_ui import WorkspaceUIStore
    from src.mvp.service import MVPService
    from src.mvp.map_jobs import MapWorker, PaperMapService
    directory = args.data_dir.expanduser().absolute()
    # This reader has no provider capability; it can only inspect/guard existing
    # saved workspaces while the API remains the sole provider-owning process.
    reader = MVPService(SQLiteWorkspaceStorage(directory / "workspaces.sqlite3"), None, None)
    maps = PaperMapService(WorkspaceUIStore(directory / "web-credentials.sqlite3"), lambda mode: reader,
                          MapStore(directory / "paper-maps.sqlite3"), embedder)
    MapWorker(maps).run_forever()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
