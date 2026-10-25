"""Immutable collection maps, independent of provider search/capture counts."""
import math
from typing import Any, Literal

from pydantic import Field, model_validator

from .collection_contracts import CollectionInputRef, CollectionMember
from .contracts import Model, StructuredError, digest, new_id, now
from .limits import MAX_COLLECTION_MAP_PAPERS
from .mapping import EmbeddingProfile, EmbeddedPaper, ExcludedPaper, projection, representations_for_papers, validate_vector
from .ports import MvpError

COLLECTION_MAP_WARNING = 'Approximate semantic layout of this explicit saved collection; not all literature and not evidence quality.'


class CollectionMapInput(Model):
    schema_version: Literal['mvp.collection-map-input.v2'] = 'mvp.collection-map-input.v2'
    collection_ref: CollectionInputRef
    members: list[CollectionMember] = Field(min_length=1, max_length=MAX_COLLECTION_MAP_PAPERS)

    @property
    def papers(self):
        return [member.paper for member in self.members]

    @model_validator(mode='after')
    def distinct(self):
        ids = [member.paper.id for member in self.members]
        if len(set(ids)) != len(ids):
            raise ValueError('Collection map members must have unique paper identities')
        return self


class CollectionPaperMap(Model):
    schema_version: Literal['mvp.collection-paper-map.v2'] = 'mvp.collection-paper-map.v2'
    map_id: str = Field(default_factory=new_id)
    workspace_id: str
    collection_ref: CollectionInputRef
    ordered_paper_ids: list[str]
    member_snapshot_hashes: dict[str, str]
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
    status: Literal['ready', 'empty', 'single_paper']
    warning: str = COLLECTION_MAP_WARNING


class CollectionMapCounts(Model):
    provider_reported: None = None
    fetched_records: None = None
    distinct_records: int
    embedded_papers: int
    excluded_papers: int
    map_points: int


class CollectionMapView(Model):
    artifact: CollectionPaperMap
    counts: CollectionMapCounts


class CollectionMapSummary(Model):
    map_id: str
    collection_ref: CollectionInputRef
    created_at: str
    status: str
    projection_method: str
    embedded_count: int
    excluded_count: int
    paper_count: int


class CollectionMapJobView(Model):
    schema_version: Literal['mvp.collection-map-job.v2'] = 'mvp.collection-map-job.v2'
    id: str
    workspace_id: str
    collection_ref: CollectionInputRef
    map_id: str
    status: Literal['queued', 'running', 'succeeded', 'failed', 'cancel_requested', 'cancelled']
    attempt: int
    max_attempts: int
    progress_completed: int
    progress_total: int
    interrupted_count: int
    created_at: str
    updated_at: str
    error: StructuredError | None = None


class CreateCollectionMapRequest(Model):
    request_id: str = Field(min_length=1, max_length=200)
    collection_ref: CollectionInputRef
    profile_id: Literal['paper_bge_v1'] = 'paper_bge_v1'
    rebuild: bool = False


class CollectionMapSubmission(Model):
    job: CollectionMapJobView
    map_id: str | None = None
    reused: bool = False


class CollectionMapListing(Model):
    maps: list[CollectionMapSummary]
    jobs: list[CollectionMapJobView]


def collection_counts(captured, artifact):
    return CollectionMapCounts(distinct_records=len(captured.members), embedded_papers=len(artifact.coordinates_by_paper_id),
        excluded_papers=len(artifact.excluded_papers_with_reasons), map_points=len(artifact.coordinates_by_paper_id))


def validate_collection_artifact(artifact, captured, profile, embedded):
    inputs = representations_for_papers(captured.papers)
    identifiers = [item.paper_id for item in inputs]
    by_id = {item.paper_id: item for item in embedded}
    excluded = [item.paper_id for item in artifact.excluded_papers_with_reasons]
    if (artifact.collection_ref != captured.collection_ref or artifact.ordered_paper_ids != identifiers
            or artifact.member_snapshot_hashes != {member.paper.id: digest(member.model_dump(mode='json')) for member in captured.members}
            or artifact.paper_input_hashes != {item.paper_id: item.input_sha256 for item in inputs}
            or artifact.representation_by_paper_id != {item.paper_id: item.representation for item in inputs}
            or artifact.embedding_profile != profile or artifact.embedding_profile_sha256 != digest(profile.model_dump(mode='json'))
            or len(by_id) != len(embedded) or len(set(excluded)) != len(excluded)
            or set(by_id) & set(excluded) or set(by_id) | set(excluded) != set(identifiers)
            or set(artifact.coordinates_by_paper_id) != set(by_id)
            or artifact.coordinate_sha256 != digest(artifact.coordinates_by_paper_id)
            or not all(len(point) == 2 and all(math.isfinite(value) for value in point) for point in artifact.coordinates_by_paper_id.values())
            or artifact.status != ('empty' if not embedded else 'single_paper' if len(embedded) == 1 else 'ready')):
        raise MvpError('map_integrity', 'Collection map identity, metadata, coordinates or profile bindings failed validation.')
    manifest = []
    for identifier in identifiers:
        if identifier in by_id:
            item = EmbeddedPaper.model_validate(by_id[identifier].model_dump(mode='json'))
            if item.input_sha256 != artifact.paper_input_hashes[identifier] or item.representation != artifact.representation_by_paper_id[identifier]:
                raise MvpError('map_integrity', 'A collection embedding differs from its immutable metadata input.')
            validate_vector(item.vector, profile.dimension)
            manifest.append({'paper_id': identifier, 'input_sha256': item.input_sha256, 'vector_sha256': digest(item.vector)})
    if digest(manifest) != artifact.embedding_set_sha256:
        raise MvpError('map_integrity', 'Collection map embedding-set digest failed validation.')


def build_collection_artifact(workspace_id, captured, profile, embedded, excluded, map_id):
    inputs = representations_for_papers(captured.papers)
    allowed = {item.paper_id: item for item in inputs}
    if len({item.paper_id for item in embedded}) != len(embedded):
        raise MvpError('map_integrity', 'Map contains duplicate embedded paper identities.')
    prepared = []
    for item in embedded:
        item = EmbeddedPaper.model_validate(item.model_dump(mode='json'))
        if item.paper_id not in allowed or item.input_sha256 != allowed[item.paper_id].input_sha256 or item.representation != allowed[item.paper_id].representation:
            raise MvpError('map_integrity', 'Embedding input does not match the retained collection.')
        prepared.append(item.model_copy(update={'vector': validate_vector(item.vector, profile.dimension)}))
    embedded = sorted(prepared, key=lambda item: list(allowed).index(item.paper_id))
    exclusions = {item.paper_id: item for item in excluded}
    good = {item.paper_id for item in embedded}
    if len(exclusions) != len(excluded) or good & exclusions.keys() or good | exclusions.keys() != allowed.keys():
        raise MvpError('map_integrity', 'Collection embeddings and exclusions do not reconcile to every retained member.')
    points, method, parameters, versions = projection([item.vector for item in embedded])
    coordinates = {item.paper_id: point for item, point in zip(embedded, points)}
    manifest = [{'paper_id': item.paper_id, 'input_sha256': item.input_sha256, 'vector_sha256': digest(item.vector)} for item in embedded]
    artifact = CollectionPaperMap(workspace_id=workspace_id, map_id=map_id, collection_ref=captured.collection_ref,
        ordered_paper_ids=list(allowed), member_snapshot_hashes={member.paper.id: digest(member.model_dump(mode='json')) for member in captured.members},
        paper_input_hashes={key: value.input_sha256 for key, value in allowed.items()},
        representation_by_paper_id={key: value.representation for key, value in allowed.items()},
        embedding_profile=profile, embedding_profile_sha256=digest(profile.model_dump(mode='json')),
        embedding_set_sha256=digest(manifest), projection_method=method, projection_parameters=parameters,
        dependency_versions={**profile.runtime_versions, **versions}, coordinates_by_paper_id=coordinates,
        coordinate_sha256=digest(coordinates), excluded_papers_with_reasons=list(exclusions.values()),
        status='empty' if not embedded else 'single_paper' if len(embedded) == 1 else 'ready')
    validate_collection_artifact(artifact, captured, profile, embedded)
    return artifact, embedded
