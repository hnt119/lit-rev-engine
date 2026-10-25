"""Collection map software checks with deterministic, explicitly synthetic vectors."""
from types import SimpleNamespace
import csv
import io
import socket

import pytest

from src.mvp.adapters.collection_map_storage import CollectionMapStore
from src.mvp.adapters.collection_storage import CollectionStore
from src.mvp.adapters.map_storage import MapStore
from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.collection_contracts import (CollectionSourceSelection, CombineCollectionsRequest, ImportCommitRequest,
    ImportEditRowRequest)
from src.mvp.collection_map_jobs import CollectionMapService
from src.mvp.collection_mapping import CreateCollectionMapRequest
from src.mvp.collections import CollectionService
from src.mvp.contracts import CreateWorkspaceRequest, Paper, SearchPreview, SearchRequest, digest
from src.mvp.map_jobs import MapWorker, PaperMapService
from src.mvp.mapping import CreateMapRequest, EmbeddedPaper, EmbeddingProfile, validate_vector
from src.mvp.ports import MvpError
from src.mvp.service import MVPService
from src.mvp.workspace_ui import WorkspaceUIStore


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Collection map tests attempted provider/model networking")
    monkeypatch.setattr(socket, "create_connection", denied)


class LocalDiscovery:
    def search(self, request):
        papers = [Paper(pmid=str(860000 + index), title=f"Synthetic legacy map paper {index}", abstract="Legacy map metadata.") for index in range(3)]
        return SearchPreview(query=request.query, papers=papers, total_reported=3, fetched_count=3,
            ordered_identifiers=[paper.id for paper in papers], provider="synthetic-map", mode="test", truncated=False)

    def prepare(self, paper):
        pytest.fail("A collection map attempted source preparation")


class SoftwareVectors:
    profile = EmbeddingProfile(model="SOFTWARE TEST VECTORS", model_revision="synthetic-v1", tokenizer_revision="synthetic-v1",
        dimension=3, runtime_versions={"fixture": "deterministic synthetic vectors; no real-model evaluation"})

    def __init__(self):
        self.calls = []

    def readiness(self):
        return True, "Synthetic software adapter only"

    def embed(self, representation, checkpoint):
        self.calls.append(representation.paper_id)
        checkpoint()
        value = int(representation.input_sha256[:8], 16)
        vector = validate_vector([1., (value % 997) / 997, ((value // 997) % 991) / 991], 3)
        return EmbeddedPaper(paper_id=representation.paper_id, input_sha256=representation.input_sha256,
            representation=representation.representation, vector=vector, window_token_weights=[1], token_count=1)


def make_case(path, count=3):
    provider, embedder = LocalDiscovery(), SoftwareVectors()
    storage = SQLiteWorkspaceStorage(path / "research.sqlite3")
    engine = MVPService(storage, provider, provider)
    registry = WorkspaceUIStore(path / "registry.sqlite3")
    _, session = registry.session()
    handle = registry.create_workspace(session["token_hash"], "workspace", {"mode": "saved_example"},
        lambda reserved: engine.create_reserved_workspace(reserved, CreateWorkspaceRequest()))
    search = engine.search_literature(handle, SearchRequest(request_id="search", query="Synthetic old map strategy"))
    collections = CollectionService(engine, CollectionStore(storage))
    text = io.StringIO(newline="")
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(["Title", "DOI", "Abstract Note"])
    for index in range(count):
        writer.writerow([f"Synthetic map import {index:03}", f"10.1234/map-{index}", f"Synthetic microbiome metadata {index}."])
    imported = collections.upload(handle, text.getvalue().encode(), "csv", "upload")
    rows = [row for offset in range(0, count, 50) for row in collections.import_rows(handle, imported.id, offset=offset, limit=50).rows]
    summary = collections.commit_import(handle, imported.id, ImportCommitRequest(request_id="commit", expected_revision=imported.revision,
        name="Synthetic map input", accepted_row_ids=[row.id for row in rows]))
    sidecar = path / "paper-maps.sqlite3"
    store, old_store = CollectionMapStore(sidecar), MapStore(sidecar)
    maps = CollectionMapService(registry, lambda mode: engine, lambda mode: collections, store, embedder)
    old_maps = PaperMapService(registry, lambda mode: engine, old_store, embedder)
    worker = MapWorker(maps)
    return SimpleNamespace(path=path, provider=provider, embedder=embedder, storage=storage, engine=engine,
        registry=registry, handle=handle, search=search, collections=collections, imported=imported, rows=rows,
        collection=summary, store=store, old_store=old_store, maps=maps, old_maps=old_maps, worker=worker)


def request_for(case, key="map"):
    return CreateCollectionMapRequest(request_id=key, collection_ref=case.collection.origin)


def test_fifty_record_collection_is_fitted_completely_without_fabricating_provider_counts(tmp_path):
    case = make_case(tmp_path, 50)
    before = [search.model_dump_json() for search in case.engine.get_workspace(case.handle).searches]
    queued = case.maps.submit("saved_example", case.handle, request_for(case))
    assert queued.job.status == "queued" and case.embedder.calls == []
    assert case.worker.run_once()
    job = case.maps.job(case.handle, queued.job.id)
    assert job.status == "succeeded", job.model_dump_json()
    view = case.maps.map("saved_example", case.handle, job.map_id)
    assert view.artifact.schema_version == "mvp.collection-paper-map.v2"
    assert len(view.artifact.ordered_paper_ids) == len(view.artifact.coordinates_by_paper_id) == len(case.embedder.calls) == 50
    assert view.counts.provider_reported is None and view.counts.fetched_records is None
    assert view.counts.distinct_records == view.counts.map_points == 50
    assert view.artifact.collection_ref == case.collection.origin
    assert view.artifact.coordinate_sha256 == digest(view.artifact.coordinates_by_paper_id)
    assert [search.model_dump_json() for search in case.engine.get_workspace(case.handle).searches] == before


def test_fifty_one_requires_an_explicit_saved_subset_and_is_not_silently_truncated(tmp_path):
    case = make_case(tmp_path, 51)
    with pytest.raises(MvpError) as failure:
        case.maps.submit("saved_example", case.handle, request_for(case))
    assert failure.value.code == "map_input_limit" and case.embedder.calls == []
    assert case.maps.listing("saved_example", case.handle, case.collection.id).jobs == []
    ids = [paper.id for paper in case.collections.papers(case.handle, case.collection.id, limit=50).papers[:3]]
    subset = case.collections.combine(case.handle, CombineCollectionsRequest(request_id="explicit-subset", name="Explicit three-paper subset",
        sources=[CollectionSourceSelection(origin=case.collection.origin, paper_ids=ids)]))
    assert subset.kind == "subset" and subset.member_count == 3
    queued = case.maps.submit("saved_example", case.handle, CreateCollectionMapRequest(request_id="subset-map", collection_ref=subset.origin))
    assert case.worker.run_once()
    assert case.maps.job(case.handle, queued.job.id).status == "succeeded"
    view = case.maps.map("saved_example", case.handle, queued.job.map_id)
    assert view.artifact.ordered_paper_ids == ids and set(view.artifact.coordinates_by_paper_id) == set(ids)


def test_map_hashes_survive_filter_selection_new_metadata_revision_and_reopen(tmp_path):
    case = make_case(tmp_path)
    queued = case.maps.submit("saved_example", case.handle, request_for(case))
    assert case.worker.run_once()
    original = case.maps.map("saved_example", case.handle, queued.job.map_id)
    encoded = original.model_dump_json()
    calls = list(case.embedder.calls)
    case.registry.put_draft(case.handle.workspace_id, "collection-selection:" + case.collection.id, version=0,
        data={"selected_paper_ids": [original.artifact.ordered_paper_ids[-1]]})
    assert case.collections.papers(case.handle, case.collection.id, filter="000").total == 1
    assert case.maps.listing("saved_example", case.handle, case.collection.id).maps
    assert case.maps.neighbors("saved_example", case.handle, queued.job.map_id, original.artifact.ordered_paper_ids[0]).neighbors
    row = case.rows[0]
    case.collections.edit_row(case.handle, case.imported.id, ImportEditRowRequest(request_id="edit-later", expected_revision=case.imported.revision,
        row_id=row.id, metadata=row.metadata.model_copy(update={"title": "A later metadata revision"})))
    assert case.maps.map("saved_example", case.handle, queued.job.map_id).model_dump_json() == encoded
    reopened = CollectionMapService(case.registry, lambda mode: case.engine, lambda mode: case.collections,
        CollectionMapStore(case.path / "paper-maps.sqlite3"), case.embedder)
    assert reopened.map("saved_example", case.handle, queued.job.map_id).model_dump_json() == encoded
    assert case.embedder.calls == calls


def test_wrong_collection_snapshot_digest_is_rejected_before_embedding(tmp_path):
    case = make_case(tmp_path)
    request = request_for(case).model_copy(update={"collection_ref": case.collection.origin.model_copy(update={"collection_snapshot_sha256": "0" * 64})})
    with pytest.raises(MvpError):
        case.maps.submit("saved_example", case.handle, request)
    assert case.embedder.calls == [] and case.maps.listing("saved_example", case.handle, case.collection.id).jobs == []


def test_legacy_and_collection_map_workers_share_one_os_owner_and_job_budget(tmp_path):
    case = make_case(tmp_path)
    mixed = MapWorker(case.old_maps, additional_domains=(case.maps,))
    contender = MapWorker(case.maps)
    try:
        assert mixed._acquire()
        assert not contender._acquire()
    finally:
        mixed.stop()
        contender.stop()
    case.old_store.max_jobs = case.store.max_jobs = 2
    legacy = case.old_maps.submit("saved_example", case.handle, CreateMapRequest(request_id="old-map", search_id=case.search.id))
    case.maps.submit("saved_example", case.handle, request_for(case))
    with pytest.raises(MvpError):
        case.old_maps.submit("saved_example", case.handle, CreateMapRequest(request_id="old-over-budget", search_id=case.search.id, rebuild=True))
    assert case.old_maps.job(case.handle, legacy.job.id).status == "queued" and case.embedder.calls == []


def test_new_collection_artifact_does_not_rewrite_existing_legacy_map(tmp_path):
    case = make_case(tmp_path)
    legacy = case.old_maps.submit("saved_example", case.handle, CreateMapRequest(request_id="old-map", search_id=case.search.id))
    assert MapWorker(case.old_maps).run_once()
    old_encoded = case.old_maps.map("saved_example", case.handle, legacy.job.map_id).model_dump_json()
    queued = case.maps.submit("saved_example", case.handle, request_for(case))
    assert case.worker.run_once()
    assert case.maps.job(case.handle, queued.job.id).status == "succeeded"
    assert case.old_maps.map("saved_example", case.handle, legacy.job.map_id).model_dump_json() == old_encoded
