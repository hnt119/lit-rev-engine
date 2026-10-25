"""Independent map contracts on explicitly synthetic software vectors only.

No publication, embedding model, inference provider, or network is used. Real
NumPy/UMAP exercise projection integration; passing does not establish semantic
quality, corpus coverage, or a real-model embedding result.
"""
from math import cos, isfinite, sin, sqrt
import socket

import pytest
from pydantic import ValidationError

from src.mvp.contracts import Paper, SearchPreview, digest
from src.mvp.mapping import (
    EmbeddedPaper, EmbeddingProfile, ExcludedPaper, MAP_WARNING, build_artifact,
    counts, representations, validate_vector,
)
from src.mvp.ports import MvpError


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Synthetic map acceptance attempted network access")
    monkeypatch.setattr(socket, "create_connection", denied)


def preview(number):
    papers = [Paper(
        id=f"synthetic-paper-{index:03}",
        title=f"SOFTWARE FIXTURE {index}; not publication evidence",
        abstract=f"Synthetic metadata paragraph {index} for map contract tests.",
    ) for index in range(number)]
    # Two duplicate fetched identifiers deliberately distinguish raw fetches
    # from distinct retained records. This is synthetic provider bookkeeping.
    ordered = [paper.id for paper in papers] + ([papers[0].id] * 2 if papers else [])
    return SearchPreview(
        id="synthetic-search", query="SYNTHETIC MAP SOFTWARE TEST", papers=papers,
        ordered_identifiers=ordered, fetched_count=len(ordered), total_reported=1001,
        truncated=True, mode="test", provider="synthetic-software-fixture",
    )


def fixture_profile(**changes):
    return EmbeddingProfile(
        model="synthetic/software-vectors", model_revision="synthetic-v1",
        tokenizer_revision="synthetic-v1", dimension=3,
        runtime_versions={"software-fixture": "1"}, **changes,
    )


def embedded(search, vectors=None):
    rows = representations(search)
    if vectors is None:
        vectors = [[cos(index * .37), sin(index * .37), .1 + index * .03]
                   for index in range(len(rows))]
    return [EmbeddedPaper(
        paper_id=row.paper_id, input_sha256=row.input_sha256,
        representation=row.representation, vector=vector,
        window_token_weights=[3], token_count=3,
    ) for row, vector in zip(rows, vectors)]


def artifact(search, rows=None, excluded=(), profile=None):
    return build_artifact(
        "synthetic-workspace", search, profile or fixture_profile(),
        embedded(search) if rows is None else rows, list(excluded), "synthetic-map",
    )


@pytest.mark.parametrize("number,status,method", [
    (0, "empty", "none_empty"),
    (1, "single_paper", "none_single_paper"),
    (2, "ready", "pca_small_corpus_v1"),
    (19, "ready", "pca_small_corpus_v1"),
])
def test_zero_one_and_small_corpora_have_honest_saved_states(number, status, method):
    pytest.importorskip("numpy", reason="Optional mapping projection dependency")
    search = preview(number)
    result, vectors = artifact(search)
    assert result.status == status and result.projection_method == method
    assert result.ordered_paper_ids == [paper.id for paper in search.papers]
    assert set(result.coordinates_by_paper_id) == set(result.ordered_paper_ids)
    assert result.warning == MAP_WARNING
    assert all(len(point) == 2 and all(isfinite(value) for value in point)
               for point in result.coordinates_by_paper_id.values())
    assert result.coordinate_sha256 == digest(result.coordinates_by_paper_id)
    if number == 1:
        assert list(result.coordinates_by_paper_id.values()) == [[0.0, 0.0]]
    tally = counts(search, result)
    assert tally.provider_reported == 1001
    assert tally.fetched_records == number + (2 if number else 0)
    assert tally.distinct_records == tally.embedded_papers == tally.map_points == number
    assert tally.excluded_papers == 0 and len(vectors) == number


@pytest.mark.parametrize("number", [20, 24])
def test_twenty_and_larger_nondegenerate_corpora_use_real_cosine_umap(number):
    pytest.importorskip("umap", reason="Optional real UMAP integration dependency")
    result, _ = artifact(preview(number))
    assert result.projection_method == "umap_cosine_v1"
    assert result.projection_parameters["metric"] == "cosine"
    assert result.projection_parameters["n_neighbors"] == 15
    assert result.projection_parameters["random_state"] == 42
    assert result.projection_parameters["n_jobs"] == 1
    assert result.projection_parameters["rank"] >= 2
    assert result.dependency_versions["umap-learn"]
    assert len(result.coordinates_by_paper_id) == number
    assert all(len(point) == 2 and all(isfinite(value) for value in point)
               for point in result.coordinates_by_paper_id.values())
    assert result.coordinate_sha256 == digest(result.coordinates_by_paper_id)


@pytest.mark.parametrize("number", [4, 22])
def test_identical_vectors_retain_visible_overlap_without_fabricated_jitter(number):
    pytest.importorskip("numpy", reason="Optional mapping projection dependency")
    search = preview(number)
    result, _ = artifact(search, embedded(search, [[1., 0., 0.]] * number))
    assert result.projection_parameters["rank"] == 0
    assert result.projection_parameters["unique_vectors"] == 1
    assert result.projection_parameters["overlap_groups"] == [list(range(number))]
    assert set(tuple(point) for point in result.coordinates_by_paper_id.values()) == {(0., 0.)}
    assert result.projection_method == ("pca_small_corpus_v1" if number < 20 else "pca_degenerate_corpus_v1")


def test_rank_deficiency_and_duplicate_vectors_preserve_identity_and_zero_axis():
    pytest.importorskip("numpy", reason="Optional mapping projection dependency")
    search = preview(4)
    rows = embedded(search, [[-1., 0., 0.], [1., 0., 0.], [2., 0., 0.], [-3., 0., 0.]])
    result, _ = artifact(search, rows)
    points = result.coordinates_by_paper_id
    assert result.projection_parameters["rank"] == 1
    assert points[search.papers[0].id] == points[search.papers[3].id]
    assert points[search.papers[1].id] == points[search.papers[2].id]
    assert points[search.papers[0].id] != points[search.papers[1].id]
    assert all(point[1] == 0. for point in points.values())


@pytest.mark.parametrize("vector,code", [
    ([1., 0.], "embedding_dimension"),
    ([float("nan"), 0., 1.], "embedding_nonfinite"),
    ([float("inf"), 0., 1.], "embedding_nonfinite"),
    ([float("-inf"), 0., 1.], "embedding_nonfinite"),
    ([True, 0., 1.], "embedding_nonfinite"),
    (["invalid", 0., 1.], "embedding_nonfinite"),
    ([0., 0., 0.], "embedding_zero_norm"),
])
def test_invalid_vectors_fail_with_structured_reasons(vector, code):
    with pytest.raises(MvpError) as failure:
        validate_vector(vector, 3)
    assert failure.value.code == code


def test_normalization_accepts_finite_large_vectors_without_arithmetic_overflow():
    assert validate_vector([1e200, 0., 0.], 3) == pytest.approx([1., 0., 0.])
    result = validate_vector([3., 4., 0.], 3)
    assert sum(value * value for value in result) == pytest.approx(1.)


def test_saved_metadata_input_and_profile_digests_have_distinct_bindings():
    pytest.importorskip("numpy", reason="Optional mapping projection dependency")
    search = preview(2)
    rows = embedded(search)
    original, _ = artifact(search, rows)
    assert original.search_snapshot_sha256 == digest(search.model_dump(mode="json"))
    assert original.embedding_profile_sha256 == digest(fixture_profile().model_dump(mode="json"))
    # Provenance-only change retains representation identity but changes corpus binding.
    changed_provenance = search.model_copy(update={"query_translation": "SYNTHETIC DIFFERENT TRANSLATION"})
    second, _ = artifact(changed_provenance, rows)
    assert second.search_snapshot_sha256 != original.search_snapshot_sha256
    assert second.paper_input_hashes == original.paper_input_hashes
    assert second.embedding_set_sha256 == original.embedding_set_sha256
    assert second.coordinate_sha256 == original.coordinate_sha256
    # Same stable paper ID with changed abstract cannot reuse the old input binding.
    changed = search.model_copy(update={"papers": [
        search.papers[0].model_copy(update={"abstract": "SYNTHETIC CHANGED ABSTRACT"}), search.papers[1],
    ]})
    with pytest.raises(MvpError, match="input"):
        artifact(changed, rows)
    third, _ = artifact(changed)
    assert third.paper_input_hashes[search.papers[0].id] != original.paper_input_hashes[search.papers[0].id]
    revised_profile = fixture_profile().model_copy(update={"model_revision": "synthetic-v2"})
    fourth, _ = artifact(search, rows, profile=revised_profile)
    assert fourth.embedding_profile_sha256 != original.embedding_profile_sha256
    assert fourth.embedding_profile.model_revision == "synthetic-v2"


def test_recorded_input_template_reconstructs_the_actual_trimmed_representation():
    search = preview(1)
    paper = search.papers[0].model_copy(update={"title": "  SYNTHETIC TITLE  ", "abstract": "  SYNTHETIC ABSTRACT\n  "})
    search = search.model_copy(update={"papers": [paper]})
    result = representations(search)[0]
    assert result.input_text == EmbeddingProfile().input_template.format(title=paper.title.strip(), abstract=paper.abstract.strip())
    title_only = representations(search.model_copy(update={"papers": [paper.model_copy(update={"abstract": " \n "})]}))[0]
    assert title_only.representation == "title_only"
    assert title_only.input_sha256 != result.input_sha256


@pytest.mark.parametrize("case", ["missing", "foreign", "input_hash", "duplicate_embedding", "duplicate_exclusion", "both"])
def test_map_membership_reconciles_once_per_saved_paper(case):
    search = preview(2)
    rows = embedded(search)
    excluded = []
    if case == "missing":
        rows = rows[:1]
    elif case == "foreign":
        rows[1] = rows[1].model_copy(update={"paper_id": "synthetic-foreign-paper"})
    elif case == "input_hash":
        rows[1] = rows[1].model_copy(update={"input_sha256": "0" * 64})
    elif case == "duplicate_embedding":
        rows = [rows[0], rows[0], rows[1]]
    elif case == "duplicate_exclusion":
        rows = rows[:1]
        excluded = [ExcludedPaper(paper_id=search.papers[1].id, code="synthetic", reason="SOFTWARE TEST EXCLUSION")] * 2
    else:
        excluded = [ExcludedPaper(paper_id=search.papers[0].id, code="synthetic", reason="SOFTWARE TEST EXCLUSION")]
    with pytest.raises(MvpError):
        artifact(search, rows, excluded)


@pytest.mark.parametrize("weights,token_count", [([], 3), ([2], 3), ([1, 0, 2], 3), ([4, -1], 3), ([], 0)])
def test_window_provenance_must_account_for_all_declared_tokens(weights, token_count):
    search = preview(1)
    with pytest.raises((MvpError, ValidationError)):
        row = EmbeddedPaper(
            paper_id=search.papers[0].id, input_sha256=representations(search)[0].input_sha256,
            representation="title_abstract", vector=[1., 0., 0.],
            window_token_weights=weights, token_count=token_count,
        )
        artifact(search, [row])


def test_excluded_papers_remain_counted_without_invented_coordinates():
    pytest.importorskip("numpy", reason="Optional mapping projection dependency")
    search = preview(3)
    rows = embedded(search)[:1]
    excluded = [ExcludedPaper(paper_id=paper.id, code="synthetic_embedding_failure", reason="SOFTWARE TEST EXCLUSION") for paper in search.papers[1:]]
    result, _ = artifact(search, rows, excluded)
    tally = counts(search, result)
    assert result.status == "single_paper"
    assert set(result.coordinates_by_paper_id) == {search.papers[0].id}
    assert result.ordered_paper_ids == [paper.id for paper in search.papers]
    assert tally.provider_reported == 1001 and tally.fetched_records == 5
    assert tally.distinct_records == 3 and tally.embedded_papers == tally.map_points == 1 and tally.excluded_papers == 2


def _persistable_map(tmp_path, search=None, vectors=None):
    from src.mvp.adapters.map_storage import MapStore
    from src.mvp.mapping import CreateMapRequest
    search = search or preview(4)
    profile = fixture_profile()
    store = MapStore(tmp_path / "synthetic-maps.sqlite3")
    submission = store.submit("synthetic-workspace", search, profile,
                              CreateMapRequest(request_id="synthetic-request", search_id=search.id))
    job = store.claim("synthetic-worker")
    assert job["id"] == submission.job.id
    rows = [store.put_embedding("synthetic-workspace", profile, row) for row in embedded(search, vectors)]
    result, rows = build_artifact("synthetic-workspace", search, profile, rows, [], job["map_id"])
    return store, job, search, result, rows


@pytest.mark.parametrize("corruption", ["ordered_ids", "input_hash", "representation", "profile_hash", "coordinate_dimension", "status", "exclusions", "counts"])
def test_publication_rejects_inconsistent_metadata_before_committing(tmp_path, corruption):
    pytest.importorskip("numpy", reason="Optional mapping projection dependency")
    store, job, search, result, rows = _persistable_map(tmp_path)
    tally = counts(search, result)
    first = search.papers[0].id
    if corruption == "ordered_ids":
        result = result.model_copy(update={"ordered_paper_ids": []})
    elif corruption == "input_hash":
        result = result.model_copy(update={"paper_input_hashes": {**result.paper_input_hashes, first: "0" * 64}})
    elif corruption == "representation":
        result = result.model_copy(update={"representation_by_paper_id": {**result.representation_by_paper_id, first: "title_only"}})
    elif corruption == "profile_hash":
        result = result.model_copy(update={"embedding_profile_sha256": "0" * 64})
    elif corruption == "coordinate_dimension":
        points = {**result.coordinates_by_paper_id, first: [0., 0., 0.]}
        result = result.model_copy(update={"coordinates_by_paper_id": points, "coordinate_sha256": digest(points)})
    elif corruption == "status":
        result = result.model_copy(update={"status": "empty"})
    elif corruption == "exclusions":
        result = result.model_copy(update={"excluded_papers_with_reasons": [ExcludedPaper(paper_id="synthetic-foreign", code="synthetic", reason="SOFTWARE TEST EXCLUSION")]})
    else:
        tally = tally.model_copy(update={"provider_reported": 0, "map_points": 0})
    with pytest.raises((MvpError, ValidationError)):
        store.publish(job, result, rows, tally)
    with pytest.raises(MvpError):
        store.map("synthetic-workspace", job["map_id"])
    assert store.job("synthetic-workspace", job["id"]).status == "running"


def test_neighbor_ranking_uses_original_cosine_even_when_screen_distance_disagrees(tmp_path):
    from types import SimpleNamespace
    from src.mvp.map_jobs import PaperMapService
    pytest.importorskip("numpy", reason="Optional mapping projection dependency")
    search = preview(4)
    # Deliberately reverse the equal-score papers in the saved search. Stable
    # lexical-ID ties must not depend on an incidental SQLite iteration order.
    search = search.model_copy(update={"papers": [search.papers[index] for index in (0, 3, 2, 1)]})
    vectors_by_id = {
        "synthetic-paper-000": [1., 0., 0.],
        "synthetic-paper-001": [.8, .6, 0.],
        "synthetic-paper-002": [.8, -.6, 0.],
        "synthetic-paper-003": [-1., 0., 0.],
    }
    vectors = [vectors_by_id[paper.id] for paper in search.papers]
    store, job, search, result, rows = _persistable_map(tmp_path, search, vectors)
    # Synthetic persisted viewport: the least similar paper is visually closest.
    # The coordinate hash is valid; these are explicitly software-test positions.
    points = {"synthetic-paper-000": [0., 0.], "synthetic-paper-001": [1000., 1000.],
              "synthetic-paper-002": [999., 999.], "synthetic-paper-003": [.001, 0.]}
    result = result.model_copy(update={"coordinates_by_paper_id": points, "coordinate_sha256": digest(points)})
    store.publish(job, result, rows, counts(search, result))
    engine = SimpleNamespace(get_workspace=lambda handle: SimpleNamespace(searches=[search]))
    maps = PaperMapService(None, lambda mode: engine, store, None)
    handle = SimpleNamespace(workspace_id="synthetic-workspace")
    neighbors = maps.neighbors("synthetic", handle, result.map_id, "synthetic-paper-000", limit=3)
    assert [item.paper_id for item in neighbors.neighbors] == ["synthetic-paper-001", "synthetic-paper-002", "synthetic-paper-003"]
    assert [item.cosine_similarity for item in neighbors.neighbors] == pytest.approx([.8, .8, -1.])
    assert store.map("synthetic-workspace", result.map_id).artifact.coordinate_sha256 == result.coordinate_sha256


@pytest.mark.parametrize("field,value", [("model_revision", "synthetic-v2"), ("tokenizer_revision", "synthetic-v2"), ("normalization", "synthetic-other-normalization"), ("content_window_tokens", 509)])
def test_embedding_cache_key_binds_input_and_profile_policy(field, value):
    from src.mvp.adapters.map_storage import MapStore
    profile = fixture_profile()
    assert MapStore.cache_key(profile, "a" * 64) != MapStore.cache_key(profile, "b" * 64)
    changed = profile.model_copy(update={field: value})
    assert MapStore.cache_key(profile, "a" * 64) != MapStore.cache_key(changed, "a" * 64)


@pytest.mark.parametrize("token_count", [1, 510, 511, 1531])
def test_token_windows_preserve_every_original_id_and_token_weight(token_count, monkeypatch):
    import json
    from types import SimpleNamespace
    torch = pytest.importorskip("torch", reason="Optional tensor runtime for synthetic adapter fixture")
    from src.mvp.adapters.paper_embeddings import LocalPaperEmbedder
    expected_ids = list(range(1000, 1000 + token_count))
    processor = {"single": [{"SpecialToken": {"id": "[CLS]", "type_id": 0}}, {"Sequence": {"id": "A", "type_id": 0}}, {"SpecialToken": {"id": "[SEP]", "type_id": 0}}]}

    class PostProcessor:
        def __getstate__(self):
            return json.dumps(processor)

    class SyntheticTokenizer:
        cls_token_id, sep_token_id = 101, 102
        backend_tokenizer = SimpleNamespace(post_processor=PostProcessor())
        def encode(self, text, **kwargs):
            assert kwargs["add_special_tokens"] is False and kwargs["truncation"] is False
            return expected_ids[:]
        def num_special_tokens_to_add(self, pair=False):
            assert pair is False
            return 2

    class SyntheticEncoder:
        tokenizer = SyntheticTokenizer()
        def __init__(self):
            self.windows = []
        def eval(self):
            return self
        def __call__(self, features):
            ids = features["input_ids"][0].tolist()
            assert ids[0] == 101 and ids[-1] == 102 and len(ids) <= 512
            assert features["attention_mask"][0].tolist() == [1] * len(ids)
            assert features["token_type_ids"][0].tolist() == [0] * len(ids)
            self.windows.append(ids[1:-1])
            return {"sentence_embedding": torch.tensor([[1., 0., 0.] if len(self.windows) == 1 else [0., 1., 0.]])}

    encoder = SyntheticEncoder()
    adapter = LocalPaperEmbedder(enabled=False)
    adapter._profile = fixture_profile()
    monkeypatch.setattr(adapter, "_load", lambda: encoder)  # Never load real weights.
    calls = []
    row = adapter.embed(representations(preview(1))[0], lambda: calls.append("checkpoint"))
    assert [item for window in encoder.windows for item in window] == expected_ids
    expected_weights = [min(510, token_count - start) for start in range(0, token_count, 510)]
    assert row.window_token_weights == expected_weights and row.token_count == token_count
    assert sum(row.window_token_weights) == token_count
    assert len(calls) == len(expected_weights) + 1
    first, rest = expected_weights[0], sum(expected_weights[1:])
    norm = sqrt(first * first + rest * rest)
    assert row.vector == pytest.approx([first / norm, rest / norm, 0.])
