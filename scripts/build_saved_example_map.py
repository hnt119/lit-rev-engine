#!/usr/bin/env python3
"""Explicitly compute a public saved-example map once, using pinned local weights.

Opening the application never invokes this maintenance command. No API key or
private workspace is read; all network connections are denied during generation.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, default=ROOT / "examples/mvp/offline_microbiome_30_v1")
    parser.add_argument("--allow-local-model", action="store_true", help="Explicitly approve CPU embedding and projection of the public pack")
    args = parser.parse_args()
    if not args.allow_local_model:
        parser.error("Pass --allow-local-model to run the pinned local model explicitly.")
    directory = args.pack.absolute()
    names = ("map-preview.json", "map-artifact.json", "map-embeddings.json", "map-generation.json")
    if any((directory / name).exists() for name in names):
        parser.error("Saved map files already exist. Create a new versioned pack instead of overwriting them.")
    manifest_path = directory / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    bundle = manifest["bundle_id"]
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    from src.mvp.adapters.saved_examples import SavedExampleProvider
    from src.mvp.adapters.paper_embeddings import LocalPaperEmbedder
    from src.mvp.contracts import SearchRequest, now
    from src.mvp.mapping import build_artifact, representations, validate_artifact

    provider = SavedExampleProvider(fixture_dir=directory)
    preview = provider.search(SearchRequest(request_id="public-map-generation", query=manifest["query"], max_results=30))
    preview = preview.model_copy(update={"id": bundle + "-preview", "research_question": manifest["question"]})
    if len(preview.papers) != 30:
        parser.error("The public pack must contain exactly 30 distinct papers before map generation.")
    embedder = LocalPaperEmbedder(enabled=True)
    ready, reason = embedder.readiness()
    if not ready:
        parser.error(reason)
    started, start_time, attempts = time.monotonic(), now(), []

    def deny_network(*unused, **unused_kwargs):
        attempts.append("blocked")
        raise RuntimeError("Network access is prohibited during bundled map generation.")

    with ExitStack() as stack:
        stack.enter_context(patch("socket.socket.connect", deny_network))
        stack.enter_context(patch("socket.create_connection", deny_network))
        profile = embedder.profile
        embeddings = []
        for index, representation in enumerate(representations(preview), 1):
            embeddings.append(embedder.embed(representation, lambda: None))
            print(f"Embedded public paper {index}/30", flush=True)
        artifact, embeddings = build_artifact(bundle + "-generation", preview, profile, embeddings, [], bundle + "-map")
        validate_artifact(artifact, preview, profile, embeddings)
    if attempts:
        raise RuntimeError("A network attempt was blocked; the pack was not written.")
    generation = {
        "schema_version": "mvp.saved-example-map-generation.v1", "bundle_id": bundle,
        "status": "REAL_PINNED_LOCAL_CPU_RUN", "started_at": start_time, "completed_at": now(),
        "elapsed_seconds": time.monotonic() - started,
        "elapsed_scope": "profile hashing, model loading, embedding, projection and validation; not isolated inference latency",
        "network_policy": "Python socket connections denied; Hugging Face offline and local-files-only",
        "blocked_connection_attempts": len(attempts), "paid_inference_calls": 0,
        "paper_count": len(embeddings), "dimension": profile.dimension,
        "token_count": sum(item.token_count for item in embeddings),
        "window_count": sum(len(item.window_token_weights) for item in embeddings),
        "multi_window_papers": sum(len(item.window_token_weights) > 1 for item in embeddings),
        "model": profile.model, "model_revision": profile.model_revision,
        "embedding_profile_sha256": artifact.embedding_profile_sha256,
        "coordinate_sha256": artifact.coordinate_sha256, "projection_method": artifact.projection_method,
        "scientific_relevance_and_map_usefulness": "NOT_ASSESSED",
    }
    values = {"map-preview.json": preview.model_dump(mode="json"),
              "map-artifact.json": artifact.model_dump(mode="json"),
              "map-embeddings.json": [item.model_dump(mode="json") for item in embeddings],
              "map-generation.json": generation}
    payloads = {name: (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
                for name, value in values.items()}
    manifest["semantic_map"] = {"schema_version": "mvp.saved-example-map-bundle.v1", "bundle_id": bundle}
    for label, name in zip(("preview", "artifact", "embeddings"), names):
        manifest["semantic_map"][label + "_file"] = name
        manifest["semantic_map"][label + "_sha256"] = hashlib.sha256(payloads[name]).hexdigest()
    manifest["semantic_map_generation"] = {"file": "map-generation.json", "sha256": hashlib.sha256(payloads["map-generation.json"]).hexdigest(),
                                            "status": generation["status"], "coordinate_sha256": artifact.coordinate_sha256}
    if manifest_path.read_bytes() != manifest_bytes:
        raise RuntimeError("The source pack changed during generation; no map files were written.")
    for name, payload in payloads.items():
        with (directory / name).open("xb") as file:
            file.write(payload)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": generation["status"], "papers": len(embeddings), "coordinates": len(artifact.coordinates_by_paper_id),
                      "coordinate_sha256": artifact.coordinate_sha256, "blocked_network_attempts": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
