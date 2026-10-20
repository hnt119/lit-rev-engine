#!/usr/bin/env python3
"""Explicit real local-embedding smoke; saved licensed metadata, no live search.

This is integration evidence, not a scientific retrieval benchmark. Normal tests
do not invoke it. Network connections are denied during the entire smoke.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import sys
import tempfile
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run(args):
    if not args.allow_local_model:
        raise ValueError("Supply --allow-local-model to explicitly run the optional pinned CPU model.")
    output = args.output.expanduser().absolute()
    if output.exists():
        raise ValueError("Choose a new output directory; existing evidence is not overwritten.")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    network_attempts = []

    def deny_network(sock, address):
        network_attempts.append(str(address))
        raise RuntimeError("Network disabled for this offline local-model smoke")

    socket.socket.connect = deny_network
    from src.mvp.bootstrap import build_service, public_runtime_info
    from src.mvp.contracts import CreateWorkspaceRequest, SearchRequest, digest
    from src.mvp.mapping import build_artifact, representations
    from src.mvp.adapters.paper_embeddings import LocalPaperEmbedder, REQUIRED_FILES

    embedder = LocalPaperEmbedder(enabled=True)
    ready, reason = embedder.readiness()
    if not ready:
        raise ValueError(reason)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="lre-real-map-") as directory:
        service = build_service("saved_example", directory)
        info = public_runtime_info()["saved_example"]
        handle = service.create_workspace(CreateWorkspaceRequest(question=info["question"]))
        search = service.search_literature(handle, SearchRequest(
            request_id=str(uuid4()), query=info["query"], research_question=info["question"], max_results=3))
        embedded = [embedder.embed(item, lambda: None) for item in representations(search)]
        artifact, vectors = build_artifact(handle.workspace_id, search, embedder.profile, embedded, [], str(uuid4()))
        if len(search.papers) != 1 or artifact.status != "single_paper":
            raise ValueError("This smoke expects the intact one-paper saved example.")
        if network_attempts:
            raise ValueError("A network connection was attempted during the offline smoke.")
        hashes = {}
        for name in REQUIRED_FILES:
            hashes[name] = hashlib.sha256((embedder.snapshot / name).read_bytes()).hexdigest()
        result = {
            "status": "TESTED", "kind": "real_local_embedding_integration",
            "mode": "saved_example_offline", "scientific_quality_validated": False,
            "model_revision": embedder.profile.model_revision,
            "profile_sha256": digest(embedder.profile.model_dump(mode="json")),
            "model_file_sha256": hashes, "profile": embedder.profile.model_dump(mode="json"),
            "papers": [{"id": p.id, "pmid": p.pmid} for p in search.papers],
            "vectors": [{"paper_id": e.paper_id, "dimension": len(e.vector),
                         "norm": math.sqrt(sum(v * v for v in e.vector)),
                         "token_count": e.token_count, "window_token_weights": e.window_token_weights,
                         "all_tokens_covered": sum(e.window_token_weights) == e.token_count,
                         "vector_sha256": digest(e.vector)} for e in vectors],
            "map_id": artifact.map_id, "projection_method": artifact.projection_method,
            "coordinates": artifact.coordinates_by_paper_id,
            "neighbors": [], "network_connections_attempted": len(network_attempts),
            "model_downloads": 0, "paid_inference_calls": 0,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        output.mkdir(parents=True, mode=0o700)
        (output / "artifact.json").write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-local-model", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        run(args)
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
