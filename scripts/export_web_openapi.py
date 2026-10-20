#!/usr/bin/env python3
"""Generate credential-free OpenAPI without reading or creating real user state."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.web_api.app import create_app


def main():
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "apps/web/lib/openapi.json"
    with TemporaryDirectory(prefix="lre-openapi-") as directory:
        schema = create_app(Path(directory).resolve()).openapi()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(destination)


if __name__ == "__main__":
    main()
