"""Independent prospective pilot metrics and harness checks; no live ranking."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket
import xml.etree.ElementTree as ET

import pytest

from src.review.models import BibliographicRecord, SearchRunSpec
from src.review.qwen import QwenProfile, embedding_request
from src.review.store import ReviewStore
from tools import evaluate_qwen_pilot as pilot

PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_paid_or_live_calls(monkeypatch):
    def denied(*args, **kwargs): pytest.fail("Qwen pilot acceptance attempted network or sleep")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr("time.sleep", denied)


def span(block, quote, text):
    start = text.index(quote)
    return {"block_id": block, "start": start, "end": start + len(quote), "quote": quote}


def row(block, text, *, document="own", rank=1, start=0, end=None):
    end = len(text) if end is None else end
    return {"document_id": document, "rank": rank, "anchor": {"block_id": block, "start": start, "end": end, "quote": text[start:end]}}


def metric_truth():
    population = "Adults n=120 at 12 months."
    result = "Change −3.1; 95% CI −4.8 to −1.4."
    alternative = "Adults n=120 at 12 months: change −3.1; 95% CI −4.8 to −1.4."
    required = [span("population", "Adults n=120", population), span("result", "Change −3.1", result), span("result", "95% CI −4.8 to −1.4", result)]
    question = {"id": "independent-positive", "support_sets": [required]}
    return question, population, result, alternative


def test_quote_level_AND_context_exclusion_and_OR_alternative_semantics():
    question, population, result, alternative = metric_truth()
    alone = row("result", result)
    alone["scoring_context"] = [{"anchor": row("population", population)["anchor"]}]
    partial = pilot.assess({"passages": [alone]}, question, "own")
    assert partial["coverage"] == pytest.approx(2 / 3) and partial["complete"] is False
    clipped = row("result", result, end=result.index(";"))
    partial = pilot.assess({"passages": [row("population", population), clipped]}, question, "own")
    assert partial["coverage"] == pytest.approx(2 / 3) and partial["complete"] is False
    complete = pilot.assess({"passages": [row("population", population), row("result", result, rank=2)]}, question, "own")
    assert complete["coverage"] == 1.0 and complete["complete"] is True
    question["support_sets"].append([span("alternative", alternative, alternative)])
    complete = pilot.assess({"passages": [row("alternative", alternative)]}, question, "own")
    assert complete["coverage"] == 1.0 and complete["complete"] is True


@pytest.mark.parametrize("wrong", ["document", "block", "partial", "literal", "rank_six"])
def test_support_needs_exact_own_identity_full_literal_and_top_five(wrong):
    question, population, result, alternative = metric_truth()
    anchor = question["support_sets"][0][0]
    candidate = row("population", population)
    trace = {"passages": [candidate]}
    if wrong == "document": candidate["document_id"] = "foreign"
    elif wrong == "block": candidate["anchor"]["block_id"] = "wrong"
    elif wrong == "partial": candidate["anchor"]["end"] = anchor["end"] - 1
    elif wrong == "literal": candidate["anchor"]["quote"] = "Adults n=999 at 12 months."
    elif wrong == "rank_six":
        candidate["rank"] = 6
        trace["passages"] = [row("unrelated", "filler", rank=number) for number in range(1, 6)] + [candidate]
    assert pilot.supported(trace, "own", anchor) is False


def test_nulls_never_receive_positive_credit_and_context_is_own_only():
    question, population, result, alternative = metric_truth()
    positive = pilot.assess({"passages": [row("population", population), row("result", result, rank=2)]}, question, "own")
    null = {"id": "independent-null", "support_sets": [], "context_anchors": [span("population", "Adults n=120", population)]}
    context_only = row("result", result)
    context_only["scoring_context"] = [{"anchor": row("population", population)["anchor"]}]
    null_row = pilot.assess({"passages": [context_only]}, null, "own")
    assert null_row["coverage"] is null_row["complete"] is None and null_row["context_covered"] == 0
    recovered = pilot.assess({"passages": [row("population", population)]}, null, "own")
    assert recovered["context_covered"] == recovered["context_total"] == 1 and recovered["answerable"] is False
    aggregate = pilot.aggregate([positive, null_row, recovered])
    assert aggregate["answerable"] == aggregate["complete_positives"] == 1 and aggregate["mean_support_coverage"] == 1
    assert len(aggregate["nulls"]) == 2


@pytest.mark.parametrize("invalid", [[], [[]]])
def test_empty_support_denominators_fail_explicitly(invalid):
    if invalid == []:
        with pytest.raises(ValueError): pilot.aggregate([{"answerable": False}])
    else:
        with pytest.raises(ValueError): pilot.assess({"passages": []}, {"id": "invalid-gold", "support_sets": invalid}, "own")


@pytest.fixture
def canonical_review(tmp_path):
    with ReviewStore(tmp_path / "pilot-acceptance.sqlite3") as store:
        project = store.create_project("Independent pilot provenance", "systematic", "Exact current sources?")["id"]
        store.import_records(project, SearchRunSpec("Independent synthetic pilot input"), [BibliographicRecord(title="Independent XML")])
        record = store.list_records(project)[0]["id"]
        store.record_decision(project, record, "title_abstract", "include", "Synthetic curator")
        store.set_full_text_status(project, record, "retrieved", "Synthetic curator")
        store.record_decision(project, record, "full_text", "include", "Synthetic curator")
        document = store.attach_document(project, record, b"<article><body><sec><p>Adults n=120 at 12 months.</p><p>Difference -3.1 (95% CI -4.8 to -1.4).</p></sec></body></article>", "jats_xml", "Synthetic curator", "Exact independent provenance")
        trace = store.search_sources(project, "adults difference", method="bm25_context_blocks")
        yield store, project, record, document, trace


@pytest.mark.parametrize("defect", [None, "scope", "method", "top_k", "rank", "score_nan", "source_hash", "blocks_hash", "parser", "manifest_record", "manifest_missing", "excluded", "context_bounds", "boolean_offset"])
def test_harness_trace_validation_covers_scope_full_provenance_and_exact_context(canonical_review, defect):
    store, project, record, document, original = canonical_review
    trace = deepcopy(original)
    if defect == "scope": trace["scope"] = "all_attached"
    elif defect == "method": trace["method"] = "unselected"
    elif defect == "top_k": trace["top_k"] = 6
    elif defect == "rank": trace["passages"][0]["rank"] = 2
    elif defect == "score_nan": trace["passages"][0]["score"] = float("nan")
    elif defect == "source_hash": trace["passages"][0]["source_sha256"] = "0" * 64
    elif defect == "blocks_hash": trace["passages"][0]["blocks_sha256"] = "0" * 64
    elif defect == "parser": trace["passages"][0]["parser_id"] = "invented-parser"
    elif defect == "manifest_record": trace["source_manifest"][0]["record_id"] = "foreign-record"
    elif defect == "manifest_missing": trace["source_manifest"] = []
    elif defect == "excluded": store.record_decision(project, record, "full_text", "exclude", "Synthetic curator", "Changed scope")
    elif defect == "context_bounds":
        target = next(value for value in trace["passages"] if value["scoring_context"])
        context = target["scoring_context"][0]["anchor"]
        context["end"] += 100
    elif defect == "boolean_offset": trace["passages"][0]["anchor"]["start"] = False
    trace["source_snapshot_sha256"] = pilot.digest(trace["source_manifest"])
    if defect is None:
        pilot.validate_trace(store, project, trace)
    else:
        with pytest.raises((ValueError, AssertionError, KeyError)):
            pilot.validate_trace(store, project, trace)


def provider_response(cost=0.02):
    return {"embeddings": [[1.0] + [0.0] * 31], "input_tokens": 3, "inference_status": {"status": "succeeded", "cost": cost}}


def test_observed_cost_exceeds_budget_stops_and_keeps_nonsecret_receipt(monkeypatch, tmp_path):
    monkeypatch.setattr(pilot.QwenClient, "_post", lambda self, url, request: (provider_response(), 0.01))
    profile = QwenProfile(dimension=32)
    client = pilot.MeasuredClient(profile, "independent-offline-secret", tmp_path, 0.03)
    request = embedding_request(profile, ["exact input"])
    client._post(profile.embedding_url, request)
    with pytest.raises(ValueError, match="cost"):
        client._post(profile.embedding_url, request)
    assert len(client.calls) == 2 and client.cost == pytest.approx(0.04)
    with pytest.raises(ValueError, match="stopped"): client._post(profile.embedding_url, request)
    client.begin_query(60)
    with pytest.raises(ValueError, match="stopped"): client._post(profile.embedding_url, request)
    assert len(client.calls) == 2
    retained = (tmp_path / "provider-calls.json").read_text()
    assert "independent-offline-secret" not in retained
    assert len(json.loads(retained)["payload"]["calls"]) == 2


@pytest.mark.parametrize("defect", ["negative", "string", "missing", "failed"])
def test_invalid_or_unknown_observed_billing_and_status_stop_explicitly(monkeypatch, tmp_path, defect):
    response = provider_response()
    if defect == "negative": response["inference_status"]["cost"] = -0.01
    elif defect == "string": response["inference_status"]["cost"] = "unknown"
    elif defect == "missing": response.pop("inference_status")
    elif defect == "failed": response["inference_status"]["status"] = "failed"
    monkeypatch.setattr(pilot.QwenClient, "_post", lambda self, url, request: (response, 0.01))
    profile = QwenProfile(dimension=32)
    client = pilot.MeasuredClient(profile, "independent-offline-secret", tmp_path, 0.25)
    with pytest.raises(ValueError): client._post(profile.embedding_url, embedding_request(profile, ["exact input"]))


def freeze_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(pilot, "ROOT", tmp_path)
    (tmp_path / "sources").mkdir()
    (tmp_path / "gold").mkdir()
    (tmp_path / "tools").mkdir()
    (tmp_path / "sources" / "new.xml").write_text("<article><body><p>Exact input.</p></body></article>")
    (tmp_path / "sources" / "manifest.json").write_text(json.dumps({"sources": [{"id": "new", "file": "new.xml"}]}))
    (tmp_path / "gold" / "questions.json").write_text('{"questions":[]}')
    (tmp_path / "tools" / "evaluate_qwen_pilot.py").write_text("Pinned harness input")
    required_code = ["tools/evaluate_qwen_pilot.py", "src/review/qwen.py", "src/review/cloud_retrieval.py", "src/review/qwen_cli.py",
                     "src/review/cli.py", "src/review/store.py", "src/review/retrieval.py", "src/review/documents.py",
                     "review.py", "tests/test_qwen_cloud_acceptance.py", "tests/test_qwen_pilot_evaluation.py", "docs/qwen-milestone.md"]
    for name in required_code:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((PROJECT / name).read_bytes())
    files = {str(path.relative_to(tmp_path)): pilot.pin(path) for path in tmp_path.rglob("*") if path.is_file()}
    freeze = {"schema_version": 1, "status": "frozen_before_first_live_qwen_ranking", "live_ranking_runs_before_freeze": 0,
              "profile": QwenProfile.from_env().metadata(), "files": files, "source_dir": "sources",
              "source_manifest": "sources/manifest.json", "questions_file": "gold/questions.json",
              "gate": {"min_mean_support_coverage": 0.85, "min_complete_positives": 4, "max_reported_cost_usd": 0.25,
                       "max_cold_seconds": 900, "max_warm_p95_seconds": 60}}
    path = tmp_path / "freeze.json"
    return freeze, path


@pytest.mark.parametrize("defect", ["false_count", "empty_pins", "unlisted_gold", "unlisted_source", "absolute", "traversal", "symlink_escape", "profile", "file_change"])
def test_freeze_requires_explicit_complete_contained_pins_and_exact_profile(tmp_path, monkeypatch, defect):
    freeze, path = freeze_fixture(tmp_path, monkeypatch)
    path.write_text(json.dumps(freeze))
    assert pilot.verify_freeze(path) == freeze
    if defect == "false_count": freeze["live_ranking_runs_before_freeze"] = False
    elif defect == "empty_pins": freeze["files"] = {}
    elif defect == "unlisted_gold": freeze["files"].pop("gold/questions.json")
    elif defect == "unlisted_source": freeze["files"].pop("sources/new.xml")
    elif defect == "absolute": freeze["files"][str(tmp_path / "sources/new.xml")] = freeze["files"].pop("sources/new.xml")
    elif defect == "traversal": freeze["files"]["sources/../sources/new.xml"] = freeze["files"].pop("sources/new.xml")
    elif defect == "symlink_escape":
        outside = tmp_path.parent / (tmp_path.name + "-outside.xml")
        outside.write_text("Outside source")
        (tmp_path / "sources/new.xml").unlink()
        (tmp_path / "sources/new.xml").symlink_to(outside)
        freeze["files"]["sources/new.xml"] = pilot.pin(outside)
    elif defect == "profile": freeze["profile"]["dimension"] = 32
    elif defect == "file_change": (tmp_path / "sources/new.xml").write_text("Changed source")
    path.write_text(json.dumps(freeze))
    with pytest.raises(ValueError) as caught: pilot.verify_freeze(path)
    expected_guard = {"false_count": "Prospective", "empty_pins": "nonempty", "unlisted_gold": "omits", "unlisted_source": "omits",
                      "absolute": "omits", "traversal": "omits", "symlink_escape": "changed", "profile": "Configured", "file_change": "changed"}
    assert expected_guard[defect] in str(caught.value)


@pytest.mark.parametrize("bad_later_quote", [False, True])
def test_all_gold_validated_before_constructing_paid_client(tmp_path, monkeypatch, bad_later_quote):
    freeze, path = freeze_fixture(tmp_path, monkeypatch)
    source = {"id": "new", "file": "new.xml", "title": "Independent new source", "doi": "10.9999/independent-pilot", "publisher_xml_url": "https://example.test/new.xml"}
    (tmp_path / "sources/manifest.json").write_text(json.dumps({"sources": [source]}))
    raw = b"<article><body><p>Adults n=120.</p><p>Difference -3.1.</p></body></article>"
    (tmp_path / "sources/new.xml").write_bytes(raw)
    blocks = pilot.parse_source_bytes(raw, "jats_xml")["blocks"]
    anchors = [{"block_id": block["id"], "start": 0, "end": len(block["text"]), "quote": block["text"]} for block in blocks]
    # A bad later quote must be found before any earlier question can incur a call.
    questions = [{"id": "positive-" + str(number), "source_id": "new", "query": "Exact input " + str(number), "answerable": True,
                  "support_sets": [deepcopy(anchors)], "expected_answer": "Difference -3.1 among 120 adults", "quantitative": True} for number in range(6)]
    if bad_later_quote: questions[-1]["support_sets"][0][0]["quote"] = "Changed later gold"
    questions += [{"id": "null-" + str(number), "source_id": "new", "query": "Absent result", "answerable": False,
                  "support_sets": [], "context_anchors": [deepcopy(anchors[0])], "null_reason": "Unreported source-scoped result"} for number in range(2)]
    (tmp_path / "gold/questions.json").write_text(json.dumps({"questions": questions}))
    monkeypatch.setattr(pilot, "verify_freeze", lambda ignored: freeze)
    constructed = []
    def denied(*args, **kwargs):
        constructed.append(True)
        raise RuntimeError("Preflight passed")
    monkeypatch.setattr(pilot, "MeasuredClient", denied)
    monkeypatch.setattr(pilot, "api_key_from_env", lambda: "")
    if bad_later_quote:
        with pytest.raises(ValueError, match="quotation"): pilot.evaluate(path, tmp_path / "prospective-result")
        assert constructed == []
    else:
        with pytest.raises(RuntimeError, match="Preflight passed"): pilot.evaluate(path, tmp_path / "prospective-result")
        assert constructed == [True]


@pytest.mark.parametrize("overrun", ["before_call", "after_response"])
def test_phase_deadline_stops_next_call_and_retains_observed_response(monkeypatch, tmp_path, overrun):
    clock = [0.0]
    monkeypatch.setattr(pilot.time, "monotonic", lambda: clock[0])
    observed = []
    def fake_post(self, url, request):
        observed.append(True)
        clock[0] = 61.0
        return provider_response(), 61.0
    monkeypatch.setattr(pilot.QwenClient, "_post", fake_post)
    profile = QwenProfile(dimension=32)
    client = pilot.MeasuredClient(profile, "independent-offline-secret", tmp_path, 0.25)
    client.begin_query(60)
    if overrun == "before_call": clock[0] = 61.0
    request = embedding_request(profile, ["exact input"])
    with pytest.raises(ValueError, match="time"): client._post(profile.embedding_url, request)
    with pytest.raises(ValueError, match="stopped"): client._post(profile.embedding_url, request)
    assert len(observed) == len(client.calls) == (0 if overrun == "before_call" else 1)
    if overrun == "after_response":
        retained = json.loads((tmp_path / "provider-calls.json").read_text())["payload"]
        assert len(retained["calls"]) == 1 and client.cost == 0.02


@pytest.mark.parametrize("defect", ["singleton_alternative", "same_block_spans", "unquantitative", "duplicate", "null_support", "null_reason", "source", "boolean_bound"])
def test_preflight_counts_true_distinct_block_ANDs_and_rejects_invalid_gold(canonical_review, defect):
    store, project, record, document, trace = canonical_review
    blocks = store.get_source_blocks(project, document["id"])
    anchors = [{"block_id": block["id"], "start": 0, "end": len(block["text"]), "quote": block["text"]} for block in blocks]
    questions = [{"id": "positive-" + str(number), "source_id": "own", "query": "Difference among adults", "answerable": True,
                  "quantitative": True, "support_sets": [deepcopy(anchors)]} for number in range(6)]
    questions += [{"id": "null-" + str(number), "source_id": "own", "query": "Unreported outcome", "answerable": False,
                   "support_sets": [], "null_reason": "The requested outcome is absent", "context_anchors": [deepcopy(anchors[0])]} for number in range(2)]
    bindings = {"own": document["id"]}
    pilot.validate_gold(store, project, questions, bindings)
    if defect == "singleton_alternative":
        for question in questions[:4]: question["support_sets"].append([deepcopy(anchors[0])])
    elif defect == "same_block_spans":
        for question in questions[:6]: question["support_sets"] = [[deepcopy(anchors[0]), deepcopy(anchors[0])]]
    elif defect == "unquantitative": questions[0]["quantitative"] = False
    elif defect == "duplicate": questions[5]["id"] = questions[0]["id"]
    elif defect == "null_support": questions[6]["support_sets"] = [deepcopy(anchors)]
    elif defect == "null_reason": questions[6].pop("null_reason")
    elif defect == "source": questions[0]["source_id"] = "foreign"
    elif defect == "boolean_bound": questions[0]["support_sets"][0][0]["start"] = False
    with pytest.raises(ValueError): pilot.validate_gold(store, project, questions, bindings)


def test_failed_provider_call_stops_and_reports_unknown_charge_without_secret(monkeypatch, tmp_path):
    attempted = []
    def unavailable(*args, **kwargs):
        attempted.append(True)
        raise ValueError("Endpoint unavailable")
    monkeypatch.setattr(pilot.QwenClient, "_post", unavailable)
    profile = QwenProfile(dimension=32)
    client = pilot.MeasuredClient(profile, "independent-offline-secret", tmp_path, 0.25)
    request = embedding_request(profile, ["exact permitted text"])
    with pytest.raises(ValueError, match="unavailable"): client._post(profile.embedding_url, request)
    with pytest.raises(ValueError, match="stopped"): client._post(profile.embedding_url, request)
    assert attempted == [True] and client.calls == []
    retained = (tmp_path / "provider-calls.json").read_text()
    saved = json.loads(retained)["payload"]
    assert saved["status"] == "provider_call_failed_charge_unknown" and saved["calls"] == []
    assert saved["failed_request"] == {"url": profile.embedding_url, "request": request}
    assert "independent-offline-secret" not in retained


def original_xml_blocks(content):
    """Source-first independent XPath/text/locator reconciliation, without the parser."""
    root = ET.fromstring(content)
    found = []
    def tag(element): return element.tag.rsplit("}", 1)[-1]
    def inline(element): return " ".join("".join(element.itertext()).split()) if element is not None else ""
    def child(element, name): return next((node for node in element if tag(node) == name), None)
    def walk(element, path, ancestors, section=""):
        kind = tag(element)
        if kind in {"ref-list", "ref", "sub-article"}: return
        if kind == "sec": section = inline(child(element, "title")) or section
        selected = ((kind == "article-title" and "front" in ancestors)
                    or (kind == "p" and bool({"body", "abstract"} & set(ancestors)))
                    or (kind == "table-wrap" and "body" in ancestors))
        if selected:
            if kind == "table-wrap":
                parts = [inline(child(element, name)) for name in ("label", "caption")]
                parts = [part for part in parts if part]
                for tr in element.iter():
                    if tag(tr) == "tr":
                        text = "\t".join(inline(cell) for cell in tr if tag(cell) in {"td", "th"})
                        if text.strip(): parts.append(text)
                parts.extend(inline(node) for node in element if tag(node) == "table-wrap-foot" and inline(node))
                text = "\n".join(parts)
            else: text = inline(element)
            if text:
                locator = {"type": "xml_element", "path": path, "tag": kind}
                if element.get("id") is not None: locator["element_id"] = element.get("id")
                if section: locator["section_title"] = section
                if kind == "table-wrap" and inline(child(element, "label")): locator["table_label"] = inline(child(element, "label"))
                found.append({"source_path": path, "block_id": "xml:" + path, "ordinal": len(found) + 1, "text": text,
                              "sha256": hashlib.sha256(text.encode()).hexdigest(), "locator": locator})
            if kind == "table-wrap": return
        positions = {}
        for node in element:
            name = tag(node)
            positions[name] = positions.get(name, 0) + 1
            walk(node, path + "/" + name + "[" + str(positions[name]) + "]", ancestors + [kind], section)
    walk(root, "/article[1]", [])
    return root, found


def test_fresh_pilot_raw_xml_all_blocks_hashes_spans_counts_and_metadata_disjointness():
    source_dir = PROJECT / "tests/fixtures/qwen_pilot_sources"
    gold_dir = PROJECT / "tests/fixtures/qwen_pilot_gold"
    sources = json.loads((source_dir / "manifest.json").read_text())
    gold = json.loads((gold_dir / "manifest.json").read_text())
    declared = json.loads((gold_dir / "blocks.json").read_text())["blocks"]
    questions = json.loads((gold_dir / "questions.json").read_text())["questions"]
    originals = {}
    dois = set()
    table_count = 0
    for source in sources["sources"]:
        content = (source_dir / source["file"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == source["source_sha256"] and len(content) == source["size_bytes"]
        root, blocks = original_xml_blocks(content)
        front = root.find("front/article-meta")
        assert front is not None
        own_dois = [node.text for node in front.findall("article-id") if node.get("pub-id-type") == "doi"]
        assert own_dois == [source["doi"]]
        assert " ".join("".join(front.find("title-group/article-title").itertext()).split()) == source["title"]
        licenses = front.findall("permissions/license")
        assert len(licenses) == 1 and licenses[0].get("{http://www.w3.org/1999/xlink}href") == source["license"]["url"]
        dois.add(source["doi"])
        truth = [block for block in declared if block["source_id"] == source["id"]]
        assert len(blocks) == len(truth) == source["block_count"]
        for actual, expected in zip(blocks, truth, strict=True):
            for key in actual: assert expected[key] == actual[key]
            originals[source["id"], actual["block_id"]] = actual
        table_count += sum(block["locator"]["tag"] == "table-wrap" for block in blocks)
        for caveat in source["caveats"]:
            for observation in caveat["observations"]:
                assert observation["canonical_fragment"] in originals[source["id"], observation["block_id"]]["text"]
    assert len(originals) == 102 and table_count == 9
    for excluded in sources["exclusion_manifest_checks"]:
        content = (PROJECT / excluded["manifest"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == excluded["sha256"] and len(content) == excluded["size_bytes"]
        legacy_dois = {source.get("doi") or source.get("metadata", {}).get("doi") for source in json.loads(content)["sources"]}
        assert None not in legacy_dois
        assert dois.isdisjoint(legacy_dois)
    positives = [question for question in questions if question["answerable"]]
    necessary = [question for question in positives if all(len({anchor["block_id"] for anchor in support}) >= 2 for support in question["support_sets"])]
    assert len(questions) == 8 and len(positives) == 6 and len(necessary) == 4 and all(question["quantitative"] for question in positives)
    support_spans = context_spans = alternatives = 0
    for question in questions:
        assert question["necessary_and"] == (question in necessary)
        alternatives += len(question["support_sets"])
        for group in question["support_sets"] + [question["context_anchors"]]:
            for anchor in group:
                block = originals[question["source_id"], anchor["block_id"]]
                assert anchor["source_id"] == question["source_id"] and anchor["source_path"] == block["source_path"]
                assert anchor["block_sha256"] == block["sha256"]
                assert type(anchor["start"]) is type(anchor["end"]) is int
                assert 0 <= anchor["start"] < anchor["end"] <= len(block["text"])
                assert anchor["quote"] == block["text"][anchor["start"]:anchor["end"]]
        support_spans += sum(len(group) for group in question["support_sets"])
        context_spans += len(question["context_anchors"])
    assert alternatives == gold["counts"]["support_alternatives"] == 9
    assert support_spans == gold["counts"]["support_spans"] and context_spans == gold["counts"]["context_spans"] == 4
