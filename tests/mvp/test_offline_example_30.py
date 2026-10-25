"""Public saved-example acceptance; no provider or model execution.

These checks inspect real, openly licensed retained publications. They do not
rate scientific relevance, ethnicity, evidence quality, or map usefulness.
"""
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import socket
import xml.etree.ElementTree as ET

import pytest

from src.mvp.adapters.saved_examples import SavedExampleProvider, saved_example_info
from src.mvp.adapters.transport import BoundedTransport
from src.mvp.contracts import SearchRequest, digest
from src.mvp.ports import ProviderFailure


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "examples/mvp/offline_microbiome_30_v1"
LEGACY = ROOT / "tests/fixtures/mvp"


@pytest.fixture(autouse=True)
def no_provider_or_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Saved-example acceptance must not call a provider or network")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(BoundedTransport, "request", forbidden)


def manifest(root=PACK):
    return json.loads((root / "manifest.json").read_text(encoding="utf-8"))


def preview(provider=None, *, cap=30, request_id="offline-thirty"):
    return (provider or SavedExampleProvider()).search(SearchRequest(
        request_id=request_id, query="UNEXECUTED USER QUERY", max_results=cap,
        date_from="1900-01-01", date_to="1900-01-02", sort="pub_date"))


def children(element, name):
    return [item for item in element if item.tag.rsplit("}", 1)[-1] == name]


def own_ids(raw):
    root = ET.fromstring(raw)
    fronts = children(root, "front")
    assert len(fronts) == 1
    metas = children(fronts[0], "article-meta")
    assert len(metas) == 1
    return {item.attrib["pub-id-type"]: "".join(item.itertext()).strip()
            for item in children(metas[0], "article-id")}, metas[0]


def write_manifest(root, value):
    (root / "manifest.json").write_text(json.dumps(value), encoding="utf-8")


def test_default_pack_has_thirty_distinct_real_reports_and_honest_saved_provenance():
    provider = SavedExampleProvider()
    info, recorded, result = saved_example_info(), manifest(), preview(provider)
    assert recorded["bundle_id"] == "offline-microbiome-30-v1"
    assert recorded["fetched_count"] == len(recorded["sources"]) == 30
    assert result.fetched_count == len(result.papers) == 30
    assert len({paper.id for paper in result.papers}) == 30
    assert len({paper.pmid for paper in result.papers}) == 30
    assert len({paper.pmcid for paper in result.papers}) == 30
    assert all(paper.pmid and paper.pmcid and paper.title.strip() and paper.abstract.strip()
               and paper.authors and paper.year for paper in result.papers)
    assert result.mode == "saved_example" and result.provider == "europe_pmc_saved_example"
    assert result.query == info["query"] == recorded["query"] != "UNEXECUTED USER QUERY"
    assert result.searched_at == recorded["searched_at"]
    assert result.total_reported == recorded["total_reported"] >= 30
    assert recorded["returned_metadata_count"] >= 30
    assert result.sort == recorded["sort"]
    assert result.date_from is result.date_to is None
    assert result.ordered_identifiers == [paper.pmid for paper in result.papers]
    assert result.truncated and any("not executed" in item for item in result.warnings)
    assert recorded["curation_warning"] in result.warnings
    assert recorded["population_note"] in result.warnings
    assert not {"directory", "capability", "csrf_token", "token", "contact"}.intersection(info)


def test_all_thirty_sources_have_matching_own_identities_bytes_and_permitted_rights():
    provider = SavedExampleProvider()
    result = preview(provider)
    for entry, paper in zip(manifest()["sources"], result.papers, strict=True):
        raw = (PACK / entry["xml_file"]).read_bytes()
        metadata_bytes = (PACK / entry["metadata_file"]).read_bytes()
        metadata = json.loads(metadata_bytes)
        assert sha256(raw).hexdigest() == entry["xml_sha256"]
        assert sha256(metadata_bytes).hexdigest() == entry["metadata_sha256"]
        identifiers, meta = own_ids(raw)
        assert identifiers["pmid"] == entry["pmid"] == paper.pmid
        assert (identifiers.get("pmcid") or identifiers.get("pmc", "")).removeprefix("PMC") == entry["pmcid"].removeprefix("PMC")
        if paper.doi:
            assert identifiers["doi"].lower() == entry["doi"] == paper.doi
        assert metadata["title"] == paper.title
        assert metadata["isOpenAccess"] == "Y"
        license_url = entry["license"].lower().replace("http://", "https://")
        assert re.fullmatch(r"https://creativecommons\.org/(?:licenses/by/[1-4]\.0|publicdomain/zero/1\.0)/?", license_url)
        permissions = children(meta, "permissions")
        assert permissions and entry["attribution"].strip()
        license_links = {value.lower().replace("http://", "https://").rstrip("/")
                         for permission in permissions for element in permission.iter()
                         for name, value in element.attrib.items() if name.rsplit("}", 1)[-1] == "href"}
        license_links.update("".join(element.itertext()).strip().lower().replace("http://", "https://").rstrip("/")
                             for permission in permissions for element in permission.iter()
                             if element.tag.rsplit("}", 1)[-1] == "license_ref")
        assert license_url.rstrip("/") in license_links
        source = provider.prepare(paper)
        assert source.source_type == "full_text" and source.status == "full_text_retrieved"
        assert source.source_identifiers["pmid"] == paper.pmid
        assert source.source_identifiers["pmcid"] == paper.pmcid
        assert source.source_sha256 == entry["xml_sha256"]
        assert sha256(source.retained_content_utf8.encode()).hexdigest() == source.source_sha256
        assert source.blocks and source.blocks_sha256 == digest([block.model_dump(mode="json") for block in source.blocks])
        assert source.license.lower().replace("http://", "https://").rstrip("/") == license_url.rstrip("/")
        assert source.attribution.strip()
        assert all("page" not in block.locator for block in source.blocks)


def test_offline_caps_preserve_prefix_without_inventing_more_than_thirty():
    provider = SavedExampleProvider()
    full = preview(provider)
    for cap in (1, 10, 29, 50):
        result = preview(provider, cap=cap)
        expected = full.papers[:cap]
        assert result.papers == expected
        assert result.fetched_count == len(expected)
        assert result.total_reported == full.total_reported
        assert result.query == full.query


def test_public_capture_audit_records_exclusions_without_publishing_excluded_sources():
    recorded = manifest()
    audit_bytes = (PACK / recorded["capture_candidates_file"]).read_bytes()
    assert sha256(audit_bytes).hexdigest() == recorded["capture_candidates_sha256"]
    audit = json.loads(audit_bytes)
    assert audit["query"] == recorded["query"]
    assert audit["searched_at"] == recorded["searched_at"]
    assert audit["total_reported"] == recorded["total_reported"]
    candidates = audit["candidates"]
    assert len(candidates) == audit["returned_metadata_count"] == recorded["returned_metadata_count"]
    assert [row["capture_rank"] for row in candidates] == list(range(1, len(candidates) + 1))
    retained = [row for row in candidates if row["status"] == "RETAINED"]
    assert len(retained) == audit["retained_count"] == 30
    assert [row["pmid"] for row in retained] == [row["pmid"] for row in recorded["sources"]]
    assert [row["capture_rank"] for row in retained] == [row["capture_rank"] for row in recorded["sources"]]
    assert all(row["status"] in {"RETAINED", "EXCLUDED", "NOT_EVALUATED"} for row in candidates)
    assert any(row["status"] == "EXCLUDED" for row in candidates)
    assert any(row["status"] == "NOT_EVALUATED" for row in candidates)
    assert all(not {"abstract", "abstractText", "full_text", "fullText", "xml", "content"}.intersection(row)
               for row in candidates)
    expected = {row["pmcid"] for row in retained}
    assert {path.name.removesuffix(".xml") for path in PACK.glob("*.xml")} == expected
    assert {path.name.removesuffix(".metadata.json") for path in PACK.glob("*.metadata.json")} == expected
    assert not any("/Users/hunt/" in path.read_text(encoding="utf-8") or ".mvp-web-state" in path.read_text(encoding="utf-8")
                   for path in PACK.glob("*.json"))


@pytest.mark.parametrize("mutation", ["xml_bytes", "metadata_bytes", "duplicate_identity", "fetched_count", "unsupported_rights", "wrong_metadata_identity"])
def test_tampered_or_self_inconsistent_public_pack_fails_closed(tmp_path, mutation):
    root = tmp_path / "pack"
    shutil.copytree(PACK, root)
    record = manifest(root)
    entry = record["sources"][0]
    if mutation in {"xml_bytes", "metadata_bytes"}:
        path = root / entry["xml_file" if mutation == "xml_bytes" else "metadata_file"]
        path.write_bytes(path.read_bytes() + b"\n")
    elif mutation == "duplicate_identity":
        record["sources"][-1] = dict(entry)
    elif mutation == "fetched_count":
        record["fetched_count"] = 29
    else:
        path = root / entry["metadata_file"]
        metadata = json.loads(path.read_bytes())
        if mutation == "unsupported_rights":
            metadata["license"] = "cc by-nc"
        else:
            metadata["pmid"] = metadata["id"] = "99999999"
        path.write_text(json.dumps(metadata), encoding="utf-8")
        entry["metadata_sha256"] = sha256(path.read_bytes()).hexdigest()
    write_manifest(root, record)
    with pytest.raises(ProviderFailure):
        SavedExampleProvider(fixture_dir=root)


def test_historical_one_paper_fixture_remains_explicitly_readable_and_unchanged():
    provider = SavedExampleProvider(fixture_dir=LEGACY)
    result = preview(provider)
    assert len(result.papers) == result.fetched_count == 1
    assert result.total_reported == 9
    assert result.papers[0].pmid == "42051515"
    assert result.papers[0].pmcid == "PMC13110953"
    assert sha256((LEGACY / "manifest.json").read_bytes()).hexdigest() == "fe705ae7994686727055efc125b81a1e1843ef544d88fe6e54b0b229580ca5ff"
    assert sha256((LEGACY / "PMC13110953.xml").read_bytes()).hexdigest() == "5995273b1ec0f90910375b24ace3856f4a7bdf974e0fcaca68e9d4f00f336404"
