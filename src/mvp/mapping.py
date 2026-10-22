"""Paper-level maps of one immutable exploratory search, never evidence ranking.

Pure contracts and validation import no optional numerical/model dependency.
Projection imports NumPy/UMAP only inside an explicit map calculation.
"""
from __future__ import annotations
import math
from typing import Any, Literal, Protocol
from pydantic import Field, model_validator
from .contracts import Model, SearchPreview, StructuredError, canonical, digest, new_id, now
from .ports import MvpError

BGE_REVISION = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
MAP_WARNING = "Approximate semantic layout of this search preview; not all literature and not evidence quality."

class EmbeddingProfile(Model):
    id: str = "paper_bge_v1"
    model: str = "BAAI/bge-small-en-v1.5"
    model_revision: str = BGE_REVISION
    tokenizer_revision: str = BGE_REVISION
    dimension: int = Field(default=384, ge=1, le=4096)
    max_sequence_tokens: int = 512
    content_window_tokens: int = 510
    input_template: str = "title: {title}\nabstract: {abstract}"
    input_preprocessing: str = "str.strip on title and abstract; paper-title-abstract-v1"
    files_sha256: dict[str, str] = Field(default_factory=dict)
    length_policy: str = "all-token-id-windows-disjoint-v1"
    normalization: str = "unit-window-vectors; content-token-weighted-mean; final-unit-l2-v1"
    runtime_versions: dict[str, str] = Field(default_factory=dict)
    trust_remote_code: Literal[False] = False
    local_files_only: Literal[True] = True

class PaperRepresentation(Model):
    paper_id: str
    input_text: str
    input_sha256: str
    representation: Literal["title_abstract", "title_only"]

class EmbeddedPaper(Model):
    paper_id: str
    input_sha256: str
    representation: Literal["title_abstract", "title_only"]
    vector: list[float]
    window_token_weights: list[int] = Field(min_length=1)
    token_count: int = Field(ge=1)

    @model_validator(mode="after")
    def covered_tokens(self):
        if any(weight <= 0 for weight in self.window_token_weights) or sum(self.window_token_weights) != self.token_count:
            raise ValueError("Window weights must cover every recorded token exactly once")
        return self

class ExcludedPaper(Model):
    paper_id: str
    code: str
    reason: str

class PaperMap(Model):
    schema_version: Literal["mvp.paper-map.v1"] = "mvp.paper-map.v1"
    map_id: str = Field(default_factory=new_id)
    workspace_id: str
    search_id: str
    search_snapshot_sha256: str
    ordered_paper_ids: list[str]
    paper_input_hashes: dict[str, str]
    representation_by_paper_id: dict[str, str]
    embedding_profile: EmbeddingProfile
    embedding_profile_sha256: str
    embedding_set_sha256: str
    projection_method: str
    projection_parameters: dict[str, Any]
    dependency_versions: dict[str, str]
    coordinates_by_paper_id: dict[str, list[float]]
    coordinate_sha256: str
    excluded_papers_with_reasons: list[ExcludedPaper]
    created_at: str = Field(default_factory=now)
    status: Literal["ready", "empty", "single_paper"]
    warning: str = MAP_WARNING

class MapCounts(Model):
    provider_reported: int
    fetched_records: int
    distinct_records: int
    embedded_papers: int
    excluded_papers: int
    map_points: int

class MapView(Model):
    artifact: PaperMap
    counts: MapCounts

class MapSummary(Model):
    map_id: str
    search_id: str
    created_at: str
    status: str
    projection_method: str
    embedded_count: int
    excluded_count: int
    paper_count: int

class MapJobView(Model):
    id: str
    workspace_id: str
    search_id: str
    map_id: str
    status: Literal["queued", "running", "succeeded", "failed", "cancel_requested", "cancelled"]
    attempt: int
    max_attempts: int
    progress_completed: int
    progress_total: int
    interrupted_count: int
    created_at: str
    updated_at: str
    error: StructuredError | None = None

class CreateMapRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    search_id: str
    profile_id: Literal["paper_bge_v1"] = "paper_bge_v1"
    rebuild: bool = False

class MapSubmission(Model):
    job: MapJobView
    map_id: str | None = None
    reused: bool = False

class MapListing(Model):
    maps: list[MapSummary]
    jobs: list[MapJobView]

class Neighbor(Model):
    paper_id: str
    cosine_similarity: float

class Neighbors(Model):
    map_id: str
    paper_id: str
    neighbors: list[Neighbor]

class PaperEmbeddingPort(Protocol):
    profile: EmbeddingProfile
    def readiness(self) -> tuple[bool, str]: ...
    def embed(self, representation: PaperRepresentation, checkpoint) -> EmbeddedPaper: ...


def representations(search: SearchPreview):
    return representations_for_papers(search.papers)


def representations_for_papers(papers):
    """The existing exact representation policy, independent of input origin."""
    result = []
    for paper in papers:
        abstract = paper.abstract.strip()
        text = "title: " + paper.title.strip() + "\nabstract: " + abstract
        result.append(PaperRepresentation(paper_id=paper.id, input_text=text,
                      input_sha256=digest({"template": "paper-title-abstract-v1", "text": text}),
                      representation="title_abstract" if abstract else "title_only"))
    return result


def validate_vector(vector, dimension):
    if len(vector) != dimension:
        raise MvpError("embedding_dimension", "Embedding has the wrong recorded dimension.")
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in vector):
        raise MvpError("embedding_nonfinite", "Embedding contains a non-finite or invalid value.")
    norm = math.hypot(*vector)
    if not math.isfinite(norm) or norm <= 1e-12:
        raise MvpError("embedding_zero_norm", "Embedding has no usable vector norm.")
    return [float(value) for value in vector] if abs(norm - 1.0) <= 1e-12 else [float(value) / norm for value in vector]


def projection(vectors: list[list[float]]):
    """Persist results once; UI filters never call this function."""
    if not vectors:
        return [], "none_empty", {"rank": 0, "overlap_groups": []}, {}
    if len(vectors) == 1:
        return [[0.0, 0.0]], "none_single_paper", {"rank": 0, "overlap_groups": [[0]]}, {}
    import numpy as np
    data = np.asarray(vectors, dtype=np.float64)
    unique, inverse = np.unique(data, axis=0, return_inverse=True)
    centered = unique - unique.mean(axis=0)
    rank = int(np.linalg.matrix_rank(centered))
    groups = [[int(item) for item in np.flatnonzero(inverse == index)] for index in range(len(unique))]
    parameters = {"rank": rank, "unique_vectors": len(unique), "overlap_groups": [group for group in groups if len(group) > 1],
                  "duplicate_policy": "identical vectors share one saved coordinate; no jitter"}
    versions = {"numpy": np.__version__}
    if len(vectors) >= 20 and len(unique) >= 20 and rank >= 2:
        import umap
        import importlib.metadata
        parameters.update({"metric": "cosine", "random_state": 42, "transform_seed": 42,
                           "n_neighbors": min(15, len(unique) - 1), "min_dist": 0.1,
                           "n_components": 2, "n_jobs": 1, "init": "random"})
        settings = {key: parameters[key] for key in ("metric", "random_state", "transform_seed", "n_neighbors", "min_dist", "n_components", "n_jobs", "init")}
        coordinates = umap.UMAP(**settings).fit_transform(unique).astype(float)
        versions["umap-learn"] = importlib.metadata.version("umap-learn")
        versions["scikit-learn"] = importlib.metadata.version("scikit-learn")
        method = "umap_cosine_v1"
    else:
        coordinates = np.zeros((len(unique), 2))
        if rank:
            u, singular, vt = np.linalg.svd(centered, full_matrices=False)
            axes = min(2, rank)
            for axis in range(axes):
                pivot = int(np.argmax(np.abs(vt[axis])))
                sign = 1.0 if vt[axis, pivot] >= 0 else -1.0
                coordinates[:, axis] = u[:, axis] * singular[axis] * sign
        parameters.update({"orientation": "largest-loading-positive; earliest-feature tie", "rank_deficient_axes": "zero", "small_corpus": len(vectors) < 20})
        method = "pca_small_corpus_v1" if len(vectors) < 20 else "pca_degenerate_corpus_v1"
    result = coordinates[inverse].tolist()
    if not all(len(point) == 2 and all(math.isfinite(item) for item in point) for point in result):
        raise MvpError("projection_invalid", "Projection did not produce finite two-dimensional coordinates.")
    return result, method, parameters, versions


def build_artifact(workspace_id, search, profile, embedded, excluded, map_id):
    inputs = representations(search)
    allowed = {item.paper_id: item for item in inputs}
    if len({item.paper_id for item in embedded}) != len(embedded):
        raise MvpError("map_integrity", "Map contains duplicate embedded paper identities.")
    prepared = []
    for item in embedded:
        item = EmbeddedPaper.model_validate(item.model_dump(mode="json"))
        if item.paper_id not in allowed or item.input_sha256 != allowed[item.paper_id].input_sha256 or item.representation != allowed[item.paper_id].representation:
            raise MvpError("map_integrity", "Embedding input does not match the saved search.")
        prepared.append(item.model_copy(update={"vector": validate_vector(item.vector, profile.dimension)}))
    embedded = sorted(prepared, key=lambda item: list(allowed).index(item.paper_id))
    exclusions = {item.paper_id: item for item in excluded}
    if len(exclusions) != len(excluded):
        raise MvpError("map_integrity", "Map contains duplicate excluded paper identities.")
    good = {item.paper_id for item in embedded}
    if good & exclusions.keys() or good | exclusions.keys() != allowed.keys():
        raise MvpError("map_integrity", "Map exclusions and embeddings do not reconcile to the saved search.")
    points, method, parameters, versions = projection([item.vector for item in embedded])
    coordinates = {item.paper_id: point for item, point in zip(embedded, points)}
    vector_manifest = [{"paper_id": item.paper_id, "input_sha256": item.input_sha256, "vector_sha256": digest(item.vector)} for item in embedded]
    artifact = PaperMap(workspace_id=workspace_id, search_id=search.id, map_id=map_id,
        search_snapshot_sha256=digest(search.model_dump(mode="json")), ordered_paper_ids=list(allowed),
        paper_input_hashes={key: value.input_sha256 for key, value in allowed.items()},
        representation_by_paper_id={key: value.representation for key, value in allowed.items()},
        embedding_profile=profile, embedding_profile_sha256=digest(profile.model_dump(mode="json")),
        embedding_set_sha256=digest(vector_manifest), projection_method=method, projection_parameters=parameters,
        dependency_versions={**profile.runtime_versions, **versions}, coordinates_by_paper_id=coordinates,
        coordinate_sha256=digest(coordinates), excluded_papers_with_reasons=list(exclusions.values()),
        status="empty" if not embedded else "single_paper" if len(embedded) == 1 else "ready")
    validate_artifact(artifact, search, profile, embedded)
    return artifact, embedded


def counts(search, artifact):
    return MapCounts(provider_reported=search.total_reported, fetched_records=search.fetched_count,
                     distinct_records=len(search.papers), embedded_papers=len(artifact.coordinates_by_paper_id),
                     excluded_papers=len(artifact.excluded_papers_with_reasons), map_points=len(artifact.coordinates_by_paper_id))


def validate_artifact(artifact, search, profile, embedded):
    inputs = representations(search)
    identifiers = [item.paper_id for item in inputs]
    by_id = {item.paper_id: item for item in embedded}
    excluded = [item.paper_id for item in artifact.excluded_papers_with_reasons]
    if (artifact.search_id != search.id or artifact.search_snapshot_sha256 != digest(search.model_dump(mode="json"))
            or artifact.ordered_paper_ids != identifiers or len(set(identifiers)) != len(identifiers)
            or artifact.paper_input_hashes != {item.paper_id: item.input_sha256 for item in inputs}
            or artifact.representation_by_paper_id != {item.paper_id: item.representation for item in inputs}
            or artifact.embedding_profile != profile or artifact.embedding_profile_sha256 != digest(profile.model_dump(mode="json"))
            or len(by_id) != len(embedded) or len(set(excluded)) != len(excluded)
            or set(by_id) & set(excluded) or set(by_id) | set(excluded) != set(identifiers)
            or set(artifact.coordinates_by_paper_id) != set(by_id)
            or artifact.coordinate_sha256 != digest(artifact.coordinates_by_paper_id)
            or not all(len(point) == 2 and all(math.isfinite(value) for value in point) for point in artifact.coordinates_by_paper_id.values())
            or artifact.status != ("empty" if not embedded else "single_paper" if len(embedded) == 1 else "ready")):
        raise MvpError("map_integrity", "Map identities, coordinates, counts or source/profile digests failed validation.")
    manifest = []
    for identifier in identifiers:
        if identifier in by_id:
            item = EmbeddedPaper.model_validate(by_id[identifier].model_dump(mode="json"))
            if item.input_sha256 != artifact.paper_input_hashes[identifier] or item.representation != artifact.representation_by_paper_id[identifier]:
                raise MvpError("map_integrity", "A retained embedding differs from its map input binding.")
            validate_vector(item.vector, profile.dimension)
            manifest.append({"paper_id": identifier, "input_sha256": item.input_sha256, "vector_sha256": digest(item.vector)})
    if digest(manifest) != artifact.embedding_set_sha256:
        raise MvpError("map_integrity", "Map embedding-set digest failed validation.")
