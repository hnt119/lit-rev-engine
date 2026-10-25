"""Verified precomputed map for the public thirty-paper offline example.

Reading or rebinding this bundle does not load a model, import a numerical
library, or calculate a projection. The original vectors and coordinates are
retained; only the current workspace/search identities are rebound.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
import re

from ..contracts import SearchPreview, canonical, digest
from ..mapping import (BGE_REVISION, EmbeddedPaper, EmbeddingProfile, PaperMap,
                       validate_artifact)
from ..ports import MvpError
from .paper_embeddings import REQUIRED_FILES

BUNDLE_ID = "offline-microbiome-30-v1"
_ROOT = Path(__file__).resolve().parents[3] / "examples" / "mvp" / "offline_microbiome_30_v1"
_FILES = {"preview": "map-preview.json", "artifact": "map-artifact.json", "embeddings": "map-embeddings.json"}
_MAX_BYTES = 4 * 1024 * 1024


def _invalid():
    return MvpError("saved_example_map_integrity", "The bundled offline semantic map is unavailable, modified, or invalid. No replacement positions were calculated.")


def _json(raw):
    def reject_constant(value):
        raise ValueError("Nonfinite JSON constant")
    return json.loads(raw, parse_constant=reject_constant)


def _snapshot(search):
    # A researcher can give the same public collection a different question.
    # Every other saved capture field and every paper remains exactly bound.
    return search.model_dump(mode="json", exclude={"id", "research_question"})


class SavedExampleMap:
    def __init__(self, *, fixture_dir=None):
        self.root = Path(fixture_dir) if fixture_dir is not None else _ROOT
        try:
            manifest_path = self.root / "manifest.json"
            if manifest_path.is_symlink():
                raise ValueError()
            manifest_raw = manifest_path.read_bytes()
            if len(manifest_raw) > _MAX_BYTES:
                raise ValueError()
            manifest = _json(manifest_raw)
            seed = manifest["semantic_map"]
            if (manifest["bundle_id"] != BUNDLE_ID or seed["bundle_id"] != BUNDLE_ID
                    or seed["schema_version"] != "mvp.saved-example-map-bundle.v1"):
                raise ValueError()
            payloads = {}
            for key, filename in _FILES.items():
                if seed[key + "_file"] != filename:
                    raise ValueError()
                path = self.root / filename
                if path.is_symlink():
                    raise ValueError()
                raw = path.read_bytes()
                if len(raw) > _MAX_BYTES or sha256(raw).hexdigest() != seed[key + "_sha256"]:
                    raise ValueError()
                payloads[key] = _json(raw)
            self.preview = SearchPreview.model_validate(payloads["preview"])
            self.artifact = PaperMap.model_validate(payloads["artifact"])
            self.embedded = [EmbeddedPaper.model_validate(row) for row in payloads["embeddings"]]
            self.seed = {key: seed[key] for key in ("bundle_id", "preview_sha256", "artifact_sha256", "embeddings_sha256")}
            self._validate(manifest, payloads)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, MvpError):
            raise _invalid() from None

    def _validate(self, manifest, payloads):
        search, artifact = self.preview, self.artifact
        profile = artifact.embedding_profile
        default = EmbeddingProfile()
        if (len(search.papers) != 30 or len({paper.id for paper in search.papers}) != 30
                or search.mode != "saved_example" or search.provider != "europe_pmc_saved_example"
                or search.fetched_count != 30 or search.errors
                or manifest["fetched_count"] != 30
                or search.query != manifest["query"] or search.searched_at != manifest["searched_at"]
                or search.sort != manifest["sort"] or search.total_reported != manifest["total_reported"]
                or search.date_from is not None or search.date_to is not None
                or search.ordered_identifiers != [paper.pmid for paper in search.papers]
                or len(self.embedded) != 30 or artifact.excluded_papers_with_reasons
                or [row.paper_id for row in self.embedded] != [paper.id for paper in search.papers]
                or artifact.projection_method != "umap_cosine_v1"
                or not artifact.workspace_id or not artifact.map_id
                or profile.model_revision != BGE_REVISION or profile.tokenizer_revision != BGE_REVISION):
            raise ValueError()
        for name in EmbeddingProfile.model_fields:
            if name not in {"files_sha256", "runtime_versions"} and getattr(profile, name) != getattr(default, name):
                raise ValueError()
        if (set(profile.files_sha256) != set(REQUIRED_FILES)
                or not all(re.fullmatch(r"[0-9a-f]{64}", value) for value in profile.files_sha256.values())
                or not profile.runtime_versions or any(value == "not-installed" for value in profile.runtime_versions.values())):
            raise ValueError()
        # Reject coercible malformed vector/token input as well as nonfinite,
        # nonunit and out-of-window vectors. Keep original JSON numbers exact.
        if (canonical(search.model_dump(mode="json")) != canonical(payloads["preview"])
                or canonical(artifact.model_dump(mode="json")) != canonical(payloads["artifact"])
                or canonical([row.model_dump(mode="json") for row in self.embedded]) != canonical(payloads["embeddings"])):
            raise ValueError()
        for item in self.embedded:
            if (len(item.vector) != profile.dimension or abs(math.hypot(*item.vector) - 1.0) > 1e-12
                    or any(weight > profile.content_window_tokens for weight in item.window_token_weights)):
                raise ValueError()
        validate_artifact(artifact, search, profile, self.embedded)

    def matches(self, search):
        return _snapshot(search) == _snapshot(self.preview)

    def rebind(self, workspace_id, search, map_id):
        if not self.matches(search):
            raise MvpError("saved_example_map_mismatch", "This saved search does not exactly match the bundled thirty-paper map.")
        origin = {**self.seed, "generated_map_id": self.artifact.map_id,
                  "generated_workspace_id": self.artifact.workspace_id,
                  "generated_search_id": self.preview.id, "generated_at": self.artifact.created_at}
        artifact = self.artifact.model_copy(update={
            "workspace_id": workspace_id, "search_id": search.id, "map_id": map_id,
            "search_snapshot_sha256": digest(search.model_dump(mode="json")),
            "projection_parameters": {**self.artifact.projection_parameters, "saved_example_bundle": origin},
        })
        validate_artifact(artifact, search, artifact.embedding_profile, self.embedded)
        return artifact, [row.model_copy(deep=True) for row in self.embedded]
