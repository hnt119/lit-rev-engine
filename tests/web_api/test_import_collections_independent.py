"""Independent raw-upload, authority and immutable-collection HTTP checks."""
from urllib.parse import quote
import csv
import io
import json
import socket
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.mvp.adapters.storage import SQLiteWorkspaceStorage
from src.mvp.contracts import Paper, SearchPreview
from src.mvp.import_contracts import MAX_IMPORT_BYTES, CitationMetadata, ResolutionBatch, ResolutionReceipt
from src.mvp.service import MVPService
from src.web_api.app import COOKIE_NAME, create_app


class LocalProviders:
    def __init__(self):
        self.search_calls = self.source_calls = 0
        self.paper = Paper(pmid="820001", title="SYNTHETIC ORIGINAL SEARCH", abstract="Original search abstract.")

    def search(self, request):
        self.search_calls += 1
        return SearchPreview(query=request.query, papers=[self.paper], total_reported=1, fetched_count=1,
            ordered_identifiers=[self.paper.id], truncated=False, mode="test", provider="synthetic-import-http")

    def prepare(self, paper):
        self.source_calls += 1
        raise AssertionError("C1 upload/commit must not prepare evidence")


class StubResolver:
    def __init__(self):
        self.calls = []
        self.failure = None

    def resolve(self, inputs):
        self.calls.append([item.model_dump(mode="json") for item in inputs])
        if self.failure == "exception":
            raise RuntimeError("PRIVATE_PROVIDER_ERROR_SENTINEL")
        if self.failure == "malformed":
            return {"items": "malformed", "elapsed_seconds": 0, "calls": 1}
        receipts = []
        for item in inputs:
            ids = {name: getattr(item, name) for name in ("doi", "pmid", "pmcid") if getattr(item, name)}
            receipts.append(ResolutionReceipt(row_id=item.row_id, status="resolved", provider="crossref",
                requested_identifiers=ids, returned_identifiers=ids,
                metadata=CitationMetadata(title="Explicitly resolved metadata", abstract="Resolved bibliographic abstract.", **ids),
                response_sha256="b" * 64, retrieved_at="2026-10-22T00:00:00+00:00", abstract_origin="crossref_metadata_abstract"))
        return ResolutionBatch(items=receipts, calls=len(inputs), elapsed_seconds=.001)


@pytest.fixture
def http_case(tmp_path, monkeypatch):
    monkeypatch.setenv("MVP_MAP_ENABLED", "0")
    monkeypatch.setenv("MVP_PROPOSALS_ENABLED", "0")
    monkeypatch.delenv("NCBI_EMAIL", raising=False)
    def denied(*args, **kwargs):
        pytest.fail("Import HTTP tests attempted a provider network call")
    monkeypatch.setattr(socket, "create_connection", denied)
    provider = LocalProviders()
    resolver = StubResolver()
    engine = MVPService(SQLiteWorkspaceStorage(tmp_path / "research.sqlite3"), provider, provider)
    app = create_app(tmp_path, services={"saved_example": engine}, metadata_resolver=resolver)
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    csrf = client.get("/api/v1/session").json()["csrf_token"]
    client.headers.update({"Origin": "http://127.0.0.1:3000", "X-CSRF-Token": csrf})
    created = client.post("/api/v1/workspaces", json={"request_id": "workspace", "mode": "saved_example"})
    created.raise_for_status()
    root = "/api/v1/workspaces/" + created.json()["id"]
    searched = client.post(root + "/searches", json={"request_id": "search", "query": "synthetic preserved query"})
    searched.raise_for_status()
    return SimpleNamespace(app=app, client=client, root=root, provider=provider, engine=engine,
        path=tmp_path, search=searched.json(), resolver=resolver)


def csv_bytes(headers, rows):
    text = io.StringIO(newline="")
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return text.getvalue().encode()


def upload(case, payload=None, key="upload", format="csv", **headers):
    payload = payload if payload is not None else csv_bytes(["Title", "DOI", "Abstract Note"], [["Imported title", "10.1234/http", "Imported abstract."]])
    response = case.client.post(case.root + "/imports/" + format, content=payload,
        headers={"Content-Type": "application/octet-stream", "X-Request-ID": key,
            "X-Import-Filename": quote("citations.csv", safe=""), **headers})
    assert response.status_code in (200, 201), response.text
    return response.json()


def import_rows(case, summary):
    response = case.client.get(case.root + "/imports/" + summary["id"] + "/rows")
    response.raise_for_status()
    return response.json()["rows"]


def commit(case, imported, key="commit", rows=None, **kwargs):
    rows = [row["id"] for row in import_rows(case, imported)] if rows is None else rows
    return case.client.post(case.root + "/imports/" + imported["id"] + "/commit", json={
        "request_id": key, "expected_revision": imported["revision"], "name": "Synthetic collection",
        "accepted_row_ids": rows, **kwargs})


def test_imported_projections_never_expose_notes_attachments_or_local_paths(http_case):
    case = http_case
    before = case.client.get(case.root).json()
    secret = "PRIVATE_NOTE_SENTINEL_INGESTION_DO_NOT_PROJECT"
    payload = csv_bytes(["Key", "Title", "DOI", "Abstract Note", "Notes", "File Attachments", "Link Attachments"],
        [["ZOTEROKEY", "Quoted title", "10.1234/http", "Imported bibliographic abstract.", secret,
          "/Users/private/unrelated.pdf", "http://127.0.0.1:9999/private"]])
    imported = upload(case, payload, **{"X-Import-Filename": quote("/Users/private/references.csv", safe="")})
    assert imported["filename"] == "references.csv" and imported["row_count"] == 1
    rows_response = case.client.get(case.root + "/imports/" + imported["id"] + "/rows")
    assert rows_response.json()["rows"][0]["metadata"]["pmid"] is None
    saved = commit(case, imported)
    assert saved.status_code in (200, 201), saved.text
    collection = saved.json()
    assert collection["origin"]["collection_id"] == collection["id"]
    assert all(value is None for value in collection["search_metadata"].values())
    papers = case.client.get(case.root + "/collections/" + collection["id"] + "/papers")
    detail = case.client.get(case.root + "/collections/" + collection["id"] + "/paper", params={"paper_id": papers.json()["papers"][0]["id"]})
    detail.raise_for_status()
    assert detail.json()["member"]["metadata_version"]["abstract_provider"] == "imported_abstract"
    projections = [imported, rows_response.json(), collection, papers.json(), detail.json(),
        case.client.get(case.root + "/imports").json(), case.client.get(case.root + "/collections").json()]
    text = json.dumps(projections)
    for private in (secret, "/Users/private", "127.0.0.1:9999", "raw_payload", '"token"'):
        assert private not in text
    assert case.client.get(case.root).json() == before
    assert case.provider.search_calls == 1 and case.provider.source_calls == 0


def test_raw_upload_has_its_own_five_mib_bound_and_json_keeps_one_mib(http_case):
    case = http_case
    rows = [[f"Synthetic {index}", "x" * 10400] for index in range(500)]
    payload = csv_bytes(["Title", "Notes"], rows)
    rows[-1][1] += "x" * (MAX_IMPORT_BYTES - len(payload))
    exact = csv_bytes(["Title", "Notes"], rows)
    assert len(exact) == MAX_IMPORT_BYTES
    imported = upload(case, exact, key="exact-five-mib")
    assert imported["byte_count"] == MAX_IMPORT_BYTES and imported["row_count"] == 500
    response = case.client.post(case.root + "/imports/csv", content=exact + b"\n",
        headers={"Content-Type": "text/csv", "X-Request-ID": "too-large"})
    assert response.status_code == 413, response.text
    assert case.client.post(case.root + "/searches", json={"request_id": "json-limit", "query": "x" * (1024 * 1024)}).status_code == 413
    assert len(case.client.get(case.root + "/imports").json()["imports"]) == 1
    assert case.provider.search_calls == 1 and case.provider.source_calls == 0


def test_streamed_upload_also_enforces_actual_bytes_without_content_length(http_case):
    case = http_case
    def chunks():
        yield b"Title,Notes\n"
        for _ in range(21):
            yield b"x" * (256 * 1024)
    response = case.client.post(case.root + "/imports/csv", content=chunks(),
        headers={"Content-Type": "text/csv", "X-Request-ID": "streamed-limit"})
    assert response.status_code == 413, response.text
    assert case.client.get(case.root + "/imports").json()["imports"] == []


def test_all_import_and_collection_routes_require_owned_session_and_mutation_csrf(http_case):
    case = http_case
    imported = upload(case)
    row = import_rows(case, imported)[0]
    saved = commit(case, imported)
    saved.raise_for_status()
    collection = saved.json()
    other = TestClient(case.app, base_url="http://127.0.0.1:8765")
    csrf = other.get("/api/v1/session").json()["csrf_token"]
    other.headers.update({"Origin": "http://127.0.0.1:3000", "X-CSRF-Token": csrf})
    for path in ("/imports", "/imports/" + imported["id"] + "/rows", "/collections",
                 "/collections/" + collection["id"] + "/papers"):
        assert other.get(case.root + path).status_code == 404
    assert other.post(case.root + "/imports/csv", content=b"Title\nOther\n",
        headers={"X-Request-ID": "other", "Content-Type": "text/csv"}).status_code == 404
    assert other.post(case.root + "/imports/" + imported["id"] + "/commit", json={"request_id": "other", "expected_revision": imported["revision"],
        "name": "Other", "accepted_row_ids": [row["id"]]}).status_code == 404
    assert case.client.post(case.root + "/imports/csv", content=b"Title\nOther\n",
        headers={"X-Request-ID": "csrf", "X-CSRF-Token": "wrong", "Content-Type": "text/csv"}).status_code == 403
    for mutation, body in (("mapping", {"request_id": "csrf-map", "expected_revision": imported["revision"], "mapping": {"title": "Title"}}),
                           ("resolve", {"request_id": "csrf-resolve", "expected_revision": imported["revision"], "row_ids": [row["id"]]}),
                           ("edit-row", {"request_id": "csrf-edit", "expected_revision": imported["revision"], "row_id": row["id"], "metadata": row["metadata"]})):
        assert case.client.post(case.root + "/imports/" + imported["id"] + "/" + mutation, json=body,
            headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert case.resolver.calls == []


def test_exact_metadata_resolution_is_explicit_bounded_idempotent_and_keeps_supplied_values(http_case):
    case = http_case
    imported = upload(case, csv_bytes(["Title", "DOI"], [["Preserve supplied title", "10.1234/resolved"]]))
    row = import_rows(case, imported)[0]
    assert case.resolver.calls == []
    url = case.root + "/imports/" + imported["id"] + "/resolve"
    request = {"request_id": "resolve", "expected_revision": imported["revision"], "row_ids": [row["id"]]}
    assert case.client.post(url, json={**request, "row_ids": ["foreign-row"]}).status_code in (404, 422)
    assert case.client.post(url, json={**request, "row_ids": [row["id"]] * 4}).status_code == 422
    assert case.resolver.calls == []
    resolved = case.client.post(url, json=request)
    resolved.raise_for_status()
    current = import_rows(case, resolved.json())[0]
    assert current["metadata"]["title"] == current["supplied_metadata"]["title"] == "Preserve supplied title"
    assert current["metadata"]["abstract"] == "Resolved bibliographic abstract."
    assert current["resolution_receipts"][0]["metadata"]["title"] == "Explicitly resolved metadata"
    assert current["field_origins"]["title"] == "supplied" and current["field_origins"]["abstract"].startswith("resolution:")
    assert case.client.post(url, json=request).json() == resolved.json()
    assert len(case.resolver.calls) == 1 and set(case.resolver.calls[0][0]) == {"row_id", "doi", "pmid", "pmcid"}
    saved = commit(case, resolved.json())
    saved.raise_for_status()
    collection_id = saved.json()["id"]
    paper = case.client.get(case.root + "/collections/" + collection_id + "/papers").json()["papers"][0]
    member = case.client.get(case.root + "/collections/" + collection_id + "/paper", params={"paper_id": paper["id"]}).json()["member"]
    assert member["metadata_version"]["abstract_provider"] == "crossref_metadata_abstract"


@pytest.mark.parametrize("failure", ["exception", "malformed"])
def test_provider_failure_or_malformed_receipt_preserves_import_and_hides_provider_details(http_case, failure):
    case = http_case
    imported = upload(case, b"10.1234/not-resolved\n", format="identifiers")
    before = case.client.get(case.root + "/imports/" + imported["id"] + "/rows").json()
    case.resolver.failure = failure
    response = case.client.post(case.root + "/imports/" + imported["id"] + "/resolve", json={
        "request_id": "failed-resolve", "expected_revision": imported["revision"], "row_ids": [before["rows"][0]["id"]]})
    assert response.status_code == 503 and response.json()["error"]["code"] == "metadata_resolution_failed"
    assert "PRIVATE_PROVIDER_ERROR_SENTINEL" not in response.text
    assert case.client.get(case.root + "/imports/" + imported["id"] + "/rows").json() == before
    assert len(case.resolver.calls) == 1 and case.provider.search_calls == 1 and case.provider.source_calls == 0


def test_pending_duplicate_and_file_error_rows_cannot_be_silently_committed(http_case):
    case = http_case
    pending = upload(case, b"10.1234/pending\n", key="pending", format="identifiers")
    assert import_rows(case, pending)[0]["metadata"]["title"] == ""
    assert commit(case, pending, key="pending-commit").status_code in (409, 422)
    duplicates = upload(case, csv_bytes(["Title", "DOI"], [["Same", "10.1234/same"], ["Same", "10.1234/same"]]), key="duplicates")
    assert duplicates["row_count"] == 2 and duplicates["duplicate_groups"]
    assert commit(case, duplicates, key="unreviewed-duplicate").status_code in (409, 422)
    merged = commit(case, duplicates, key="reviewed-duplicate", duplicate_policy="merge_exact")
    assert merged.status_code in (200, 201) and merged.json()["member_count"] == 1
    oversized = case.client.post(case.root + "/imports/csv", content=csv_bytes(["Title"], [[f"Row {index}"] for index in range(501)]),
        headers={"X-Request-ID": "rows-overflow", "Content-Type": "text/csv"})
    assert oversized.status_code in (400, 422), oversized.text
    assert oversized.json()["error"]["code"] == "import_parse_error"
    assert len(case.client.get(case.root + "/imports").json()["imports"]) == 2


def test_reopen_original_cookie_pagination_and_cas_keep_original_collection_snapshot(http_case):
    case = http_case
    imported = upload(case, csv_bytes(["Title"], [[f"Imported record {index:03}"] for index in range(55)]))
    all_rows = []
    for offset in (0, 50):
        page = case.client.get(case.root + "/imports/" + imported["id"] + "/rows", params={"offset": offset, "limit": 50})
        page.raise_for_status()
        assert page.json()["total"] == 55
        all_rows.extend(page.json()["rows"])
    assert len(all_rows) == 55
    saved = commit(case, imported, rows=[row["id"] for row in all_rows])
    saved.raise_for_status()
    collection = saved.json()
    paper_url = case.root + "/collections/" + collection["id"] + "/papers"
    first = case.client.get(paper_url, params={"limit": 50}).json()
    assert first["total"] == 55 and len(first["papers"]) == 50 and first["next_offset"] == 50
    assert case.client.get(paper_url, params={"limit": 51}).status_code == 422
    assert case.client.get(case.root + "/imports/" + imported["id"] + "/rows", params={"limit": 51}).status_code == 422
    edit_body = {"request_id": "edit", "expected_revision": imported["revision"], "row_id": all_rows[0]["id"],
        "metadata": {**all_rows[0]["metadata"], "title": "Explicit edited metadata"}}
    edited = case.client.post(case.root + "/imports/" + imported["id"] + "/edit-row", json=edit_body)
    edited.raise_for_status()
    stale = case.client.post(case.root + "/imports/" + imported["id"] + "/edit-row", json={**edit_body, "request_id": "stale"})
    assert stale.status_code == 409
    assert case.client.get(paper_url, params={"limit": 50}).json() == first
    restarted = TestClient(create_app(case.path, services={"saved_example": case.engine}), base_url="http://127.0.0.1:8765")
    restarted.cookies.set(COOKIE_NAME, case.client.cookies.get(COOKIE_NAME))
    assert restarted.get(paper_url, params={"offset": 50, "limit": 50}).json() == case.client.get(paper_url, params={"offset": 50, "limit": 50}).json()
    assert restarted.get(case.root + "/imports/" + imported["id"] + "/rows").json()["revision"] == edited.json()["revision"]


def test_other_workspace_and_deleted_workspace_cannot_retrieve_imports_or_members(http_case):
    case = http_case
    imported = upload(case)
    saved = commit(case, imported)
    saved.raise_for_status()
    other = case.client.post("/api/v1/workspaces", json={"request_id": "other", "mode": "saved_example"}).json()
    other_root = "/api/v1/workspaces/" + other["id"]
    assert case.client.get(other_root + "/imports/" + imported["id"] + "/rows").status_code == 404
    assert case.client.get(other_root + "/collections/" + saved.json()["id"] + "/papers").status_code == 404
    deleted = case.client.delete(case.root)
    deleted.raise_for_status()
    assert case.client.get(case.root + "/imports").status_code == 404
    assert case.client.get(case.root + "/collections/" + saved.json()["id"] + "/papers").status_code == 404
    with case.engine._storage._connection() as db:
        for table in ("mvp_ingestion_imports", "mvp_ingestion_versions", "mvp_collections", "mvp_ingestion_requests"):
            assert db.execute(f"SELECT COUNT(*) FROM {table} WHERE workspace_id=?", (case.root.rsplit("/", 1)[1],)).fetchone()[0] == 0
