#!/usr/bin/env python3
"""Read-only offline source/path/quote and accepted-parser reconciliation check."""

import argparse
import collections
import copy
import shutil
import tempfile
from urllib.parse import urlsplit
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[2]
INPUT_FILES = ("manifest.json", "passages.json", "held-out.json")
STATUS = "anchor-reconciled; fresh source-first held-out pilot unfrozen; independent semantic review and coordinator freeze pending"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(content):
    return hashlib.sha256(content).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def load_json(path):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"{path.name}: duplicate JSON key {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f"{path.name}: nonfinite JSON constant {value}")

    result = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs, parse_constant=invalid_constant)
    canonical(result)  # Also rejects overflowed finite-looking number spellings.
    return result


def local_tag(element):
    return element.tag.rsplit("}", 1)[-1]


def inline(element):
    return " ".join("".join(element.itertext()).split())


def children(element, tag):
    return [child for child in element if local_tag(child) == tag]


def resolve_original(root, path):
    """Resolve declared paths directly; never use operational parser helpers."""
    components = path.strip("/").split("/")
    matches = [re.fullmatch(r"([^/\[\]]+)\[([1-9][0-9]*)\]", item) for item in components]
    require(all(matches), f"Invalid declared XML path: {path}")
    parts = [(match.group(1), int(match.group(2))) for match in matches]
    require(parts[0] == ("article", 1) and local_tag(root) == "article", f"Not an article path: {path}")
    require(parts[1][0] in {"front", "body"}, f"Not main-article support: {path}")
    require(not any(tag in {"back", "ref-list", "ref", "sub-article"} for tag, _ in parts), f"Excluded support branch: {path}")
    element = root
    section_title = None
    for tag, index in parts[1:]:
        siblings = children(element, tag)
        require(index <= len(siblings), f"Original XML path does not exist: {path}")
        element = siblings[index - 1]
        if tag == "sec":
            titles = children(element, "title")
            if titles and inline(titles[0]):
                section_title = inline(titles[0])
    return element, section_title, [tag for tag, _ in parts]


def original_table_text(element):
    lines = []
    for name in ("label", "caption"):
        for item in children(element, name):
            text = inline(item)
            if text:
                lines.append(text)
    for row in element.iter():
        if local_tag(row) == "tr":
            cells = [inline(cell) for cell in row if local_tag(cell) in {"td", "th"}]
            text = "\t".join(cells)
            if text.strip():
                lines.append(text)
    for foot in children(element, "table-wrap-foot"):
        if inline(foot):
            lines.append(inline(foot))
    return "\n".join(lines)


def original_blocks(root):
    """Independently enumerate the entire main-root canonical XML inventory."""
    blocks = []

    def visit(element, path, ancestry, section=None):
        tag = local_tag(element)
        if tag in {"back", "ref-list", "ref", "sub-article"}:
            return
        if tag == "sec":
            titles = children(element, "title")
            if titles and inline(titles[0]):
                section = inline(titles[0])
        is_table = tag == "table-wrap" and "body" in ancestry
        is_paragraph = tag == "p" and ("body" in ancestry or "abstract" in ancestry) and "table-wrap" not in ancestry
        is_title = tag == "article-title" and ancestry[-3:] == ["front", "article-meta", "title-group"]
        if is_table or is_paragraph or is_title:
            text = original_table_text(element) if is_table else inline(element)
            if text:
                locator = {"type": "xml_element", "path": path, "tag": tag}
                if element.get("id") is not None:
                    locator["element_id"] = element.get("id")
                if section:
                    locator["section_title"] = section
                if is_table:
                    labels = children(element, "label")
                    if labels and inline(labels[0]):
                        locator["table_label"] = inline(labels[0])
                blocks.append({"id": "xml:" + path, "ordinal": len(blocks) + 1, "text": text, "locator": locator})
            if is_table:
                return
        counts = collections.Counter()
        for child in element:
            name = local_tag(child)
            counts[name] += 1
            visit(child, path + f"/{name}[{counts[name]}]", ancestry + [tag], section)

    visit(root, "/article[1]", [])
    return blocks


def source_metadata(root):
    meta = root.find("front/article-meta")
    publication = meta.find("pub-date[@pub-type='epub']")
    permissions = meta.find("permissions")
    return {
        "doi": inline(meta.find("article-id[@pub-id-type='doi']")),
        "title": inline(meta.find("title-group/article-title")),
        "authors": [{"surname": inline(n.find("name/surname")), "given_names": inline(n.find("name/given-names"))} for n in meta.findall("contrib-group/contrib[@contrib-type='author']")],
        "journal": inline(root.find("front/journal-meta/journal-title-group/journal-title")),
        "publisher": inline(root.find("front/journal-meta/publisher/publisher-name")),
        "publication_date": "-".join([inline(publication.find("year")), inline(publication.find("month")).zfill(2), inline(publication.find("day")).zfill(2)]),
        "copyright": {"year": inline(permissions.find("copyright-year")), "holder": inline(permissions.find("copyright-holder"))},
        "xml_licenses": [{"attributes": dict(n.attrib), "text": inline(n)} for n in permissions.findall("license")],
        "xml_root_attributes": dict(root.attrib),
        "main_article_table_count": len(root.findall("body//table-wrap")),
    }


def selected_acquisitions(base, manifest):
    pins = manifest["source_manifest_pins"]
    require(len(pins) == 2, "Expected two acquisition-manifest pins")
    require({p["file"] for p in pins} == {"../medical_sources_v3/manifest.json", "../medical_sources_v3_imaging/manifest.json"}, "Unexpected acquisition archive")
    selected = {}
    for pin in pins:
        content = (base / pin["file"]).read_bytes()
        require(len(content) == pin["size_bytes"] and digest(content) == pin["sha256"], "Acquisition manifest pin changed")
        expected_aliases = {"mri"} if "v3_imaging/" in pin["file"] else {"cbti", "ckm"}
        require(set(pin["selected_aliases"]) == expected_aliases, "Excluded or missing acquisition alias")
        # Only selected rows are inspected. Never open an excluded raw source.
        rows = [row for row in load_json(base / pin["file"])["sources"] if row.get("alias") in expected_aliases]
        require(len(rows) == len(expected_aliases), "Selected acquisition source missing")
        for row in rows:
            require(row["alias"] not in selected, "Duplicate selected acquisition alias")
            selected[row["alias"]] = (pin["file"], row)
    return selected


def independently_validate(base):
    """Complete source, split, path, normalization and quote checks before parsing."""
    data = {name: load_json(base / name) for name in INPUT_FILES}
    manifest = data["manifest.json"]
    acquisition_rows = selected_acquisitions(base, manifest)
    require(manifest["corpus_handling_decision"].startswith("Coordinator accepted the three original XML snapshots"), "Source handling decision missing")
    sources = {}
    require(len(manifest["sources"]) == 3, "Expected exactly three pinned sources")
    for source in manifest["sources"]:
        alias = source["alias"]
        require(alias not in sources, f"Duplicate source alias: {alias}")
        require(alias in {"cbti", "ckm", "mri"}, "Excluded source alias")
        acquisition_file, acquisition = acquisition_rows[alias]
        require(source["acquisition_manifest_file"] == acquisition_file and source["acquisition_record"] == acquisition, f"Historical acquisition provenance changed: {alias}")
        captured = acquisition["acquisition"] if alias == "mri" else acquisition
        captured_size = captured["byte_length"] if alias == "mri" else captured["size_bytes"]
        require(source["source_sha256"] == captured["sha256"] and source["size_bytes"] == captured_size, f"Gold/source pin differs from accepted acquisition bytes: {alias}")
        final_url = captured["resolved_url_sanitized"] if alias == "mri" else captured["final_url"]
        sanitized = urlsplit(final_url)
        require(not sanitized.query and not sanitized.fragment and not sanitized.username and not sanitized.password, f"Signed or unsanitized redirect provenance: {alias}")
        folder = "medical_sources_v3_imaging" if alias == "mri" else "medical_sources_v3"
        require(source["file"] == f"../{folder}/{alias}.xml", f"Wrong selected raw path: {alias}")
        content = (base / source["file"]).read_bytes()
        require(len(content) == source["size_bytes"] and digest(content) == source["source_sha256"], f"Pinned source bytes changed: {alias}")
        require(not re.search(rb"<!ENTITY\b", content, re.I), f"Entity declaration: {alias}")
        root = ET.fromstring(content)
        direct = source_metadata(root)
        require(source["original_xml_metadata"] == direct, f"Original XML metadata/authors/date/notice mismatch: {alias}")
        for key in ("doi", "title", "authors", "journal", "publisher", "publication_date"):
            require(source[key] == direct[key], f"Source metadata mismatch: {alias}/{key}")
        for caveat in source["source_caveats"]:
            for observation in caveat["source_observations"]:
                selected = root.findall(observation["xml_path"])
                require(len(selected) == 1 and observation["literal_fragment"] in "".join(selected[0].itertext()), f"Source caveat path/fragment mismatch: {alias}")
        own_dois = root.findall("./front/article-meta/article-id[@pub-id-type='doi']")
        require(own_dois and all(inline(item) == source["doi"] for item in own_dois), f"Own article DOI changed: {alias}")
        require(inline(root.find("./front/article-meta/title-group/article-title")) == source["title"], f"Own title changed: {alias}")
        license_urls = [element.get("{http://www.w3.org/1999/xlink}href") for element in root.findall("./front/article-meta/permissions/license")]
        require(source["license"]["xml_url"] in license_urls and source["license"]["spdx_id"] == "CC-BY-4.0", f"Own license changed: {alias}")
        sources[alias] = {"metadata": source, "content": content, "root": root}
    prior_dois = {"10.1371/journal.pmed.1004019", "10.1371/journal.pmed.1004109", "10.1371/journal.pmed.1004026", "10.1371/journal.pmed.1004422", "10.1371/journal.pone.0329611", "10.1371/journal.pone.0340276"}
    selected_dois = {source["metadata"]["doi"] for source in sources.values()}
    require(len(selected_dois) == 3 and not selected_dois & prior_dois, "Selected DOIs overlap prior pilots or each other")

    passages = {}
    path_keys = set()
    for passage in data["passages.json"]["passages"]:
        pid = passage["id"]
        alias = passage["article_alias"]
        require(pid not in passages and alias in sources, f"Invalid passage binding: {pid}")
        source = sources[alias]
        require(passage["source_sha256"] == source["metadata"]["source_sha256"], f"Passage source hash changed: {pid}")
        element, section, ancestors = resolve_original(source["root"], passage["element_path"])
        require((alias, passage["element_path"]) not in path_keys, f"Duplicate passage path: {pid}")
        path_keys.add((alias, passage["element_path"]))
        require(local_tag(element) == passage["element_tag"] and element.get("id") == passage["element_id"], f"Element metadata mismatch: {pid}")
        require(section == passage["section_title"], f"Nearest section title mismatch: {pid}")
        require("".join(element.itertext()) == passage["exact_joined_source_text"], f"Original joined XML text mismatch: {pid}")
        tag = local_tag(element)
        require((tag == "p" and ("body" in ancestors or "abstract" in ancestors) and "table-wrap" not in ancestors) or (tag == "table-wrap" and "body" in ancestors), f"Not a finding paragraph/table: {pid}")
        text = original_table_text(element) if tag == "table-wrap" else inline(element)
        require(text == passage["provisional_canonical_text"], f"Draft normalization mismatch: {pid}")
        require(passage["provisional_block_id"] == "xml:" + passage["element_path"], f"Draft block ID mismatch: {pid}")
        locator = {"type": "xml_element", "path": passage["element_path"], "tag": tag}
        if element.get("id") is not None:
            locator["element_id"] = element.get("id")
        if section:
            locator["section_title"] = section
        if tag == "table-wrap":
            labels = children(element, "label")
            if labels and inline(labels[0]):
                locator["table_label"] = inline(labels[0])
        passages[pid] = {"draft": passage, "text": text, "locator": locator}
    require(len(passages) == manifest["expected_counts"]["passages"], "Declared distinct support/context passage count changed")

    questions = []
    all_ids = set()
    all_questions = set()
    quote_count = 0
    for split, spec in manifest["splits"].items():
        rows = data[spec["file"]]["questions"]
        require(len(rows) == spec["questions"] == 12, f"Split count mismatch: {split}")
        require([q["id"] for q in rows] == spec["ids"], f"Split membership/order mismatch: {split}")
        require(collections.Counter(q["article_alias"] for q in rows) == {"cbti": 4, "ckm": 4, "mri": 4}, f"Article balance mismatch: {split}")
        require(sum(q["answerability"] == "no_answer" for q in rows) == spec["no_answer_questions"] == 3, f"No-answer count mismatch: {split}")
        require(collections.Counter(q["article_alias"] for q in rows if q["answerability"] == "answerable") == {"cbti": 3, "ckm": 3, "mri": 3}, "Expected three answerable questions per source")
        require(collections.Counter(q["article_alias"] for q in rows if q["answerability"] == "no_answer") == {"cbti": 1, "ckm": 1, "mri": 1}, "Expected one no-answer question per source")
        for question in rows:
            qid = question["id"]
            require(qid not in all_ids and question["question"] not in all_questions, f"Duplicate question: {qid}")
            all_ids.add(qid)
            all_questions.add(question["question"])
            require(question["answerability"] in {"answerable", "no_answer"}, f"Unknown answerability: {qid}")
            supports = question["sufficient_support_sets"]
            require(bool(supports) == (question["answerability"] == "answerable"), f"Support/answerability mismatch: {qid}")
            require((question["expected_answer_as_reported"] is None) == (question["answerability"] == "no_answer"), f"Answer note mismatch: {qid}")
            required_ids = set()
            for group in supports:
                require(group and len(group) == len(set(group)), f"Empty/duplicate support group: {qid}")
                required_ids.update(group)
            declared = required_ids | set(question["context_only_passage_ids"]) | set(question["hard_negative_passage_ids"])
            for pid in declared:
                require(pid in passages and passages[pid]["draft"]["article_alias"] == question["article_alias"], f"Cross-article/unknown support: {qid}/{pid}")
            spanned = set()
            for span in question["provisional_spans"]:
                pid = span["passage_id"]
                require(pid in declared, f"Undeclared quote passage: {qid}/{pid}")
                text = passages[pid]["text"]
                start, end = span["start"], span["end"]
                require(type(start) is int and type(end) is int and 0 <= start < end <= len(text), f"Invalid code-point bounds: {qid}/{pid}")
                require(text[start:end] == span["quote"], f"Original canonical quote mismatch: {qid}/{pid}")
                spanned.add(pid)
                quote_count += 1
            require(required_ids <= spanned, f"Positive support lacks quote truth: {qid}")
            require(set(question["context_only_passage_ids"]) <= spanned or question["answerability"] == "answerable", f"No-answer context lacks quotation: {qid}")
            require(all(span["unit"] == "Unicode code points, half-open [start,end)" for span in question["provisional_spans"]), f"Invalid offset unit: {qid}")
            questions.append((split, question))
    require(len(questions) == 12 and quote_count == manifest["expected_counts"]["quotes"], "Question/quotation count mismatch")
    require(sum(q["answerability"] == "answerable" for _, q in questions) == 9, "Expected nine answerable questions")
    require(sum("quantitative_estimate_interval_denominator" in q["challenge_tags"] for _, q in questions) >= 5, "Expected at least five quantitative questions")
    and_count = sum(bool(q["sufficient_support_sets"]) and all(len({(passages[pid]["draft"]["article_alias"], passages[pid]["draft"]["provisional_block_id"]) for pid in group}) >= 2 for group in q["sufficient_support_sets"]) for _, q in questions)
    require(and_count >= 6, "Expected at least six questions with necessary distinct-block AND support in every alternative")
    quant_count = sum("quantitative_estimate_interval_denominator" in q["challenge_tags"] for _, q in questions)
    require(quant_count == manifest["expected_counts"]["quantitative_questions"] and and_count == manifest["expected_counts"]["AND_questions"], "Declared quantitative/necessary-AND counts changed")
    for _, q in questions:
        necessary = bool(q["sufficient_support_sets"]) and all(len({(passages[pid]["draft"]["article_alias"], passages[pid]["draft"]["provisional_block_id"]) for pid in group}) >= 2 for group in q["sufficient_support_sets"])
        require(("necessary_distinct_block_AND" in q["challenge_tags"]) == necessary, f"Necessary-AND annotation/alternatives disagree: {q['id']}")
    require(set(manifest["splits"]) == {"held-out"}, "Only the fresh held-out split is permitted")
    return data, sources, passages, questions


def reconciled_anchors(base):
    data, sources, passages, questions = independently_validate(base)
    # Import the public parser only after the independent XML/quote/split checks.
    sys.path.insert(0, str(REPOSITORY))
    from src.review.documents import parse_source_bytes

    source_rows = []
    parsed_by_alias = {}
    for alias, source in sources.items():
        parsed = parse_source_bytes(source["content"], "jats_xml")
        blocks = parsed["blocks"]
        require(blocks == original_blocks(source["root"]), f"Complete original XML block/path/text/ordinal reconciliation mismatch: {alias}")
        by_id = {block["id"]: block for block in blocks}
        require(len(by_id) == len(blocks), f"Operational duplicate block IDs: {alias}")
        require(parsed["parser_id"] == "lit-rev-engine.source.v1.jats_xml", f"Unexpected parser version: {alias}")
        require(parsed["source_identifiers"].get("doi") == source["metadata"]["doi"], f"Parser own DOI mismatch: {alias}")
        parsed_by_alias[alias] = by_id
        source_rows.append({"article_alias": alias, "source_file": source["metadata"]["file"], "source_sha256": digest(source["content"]), "size_bytes": len(source["content"]), "blocks_sha256": digest(canonical(blocks)), "block_count": len(blocks), "parser_id": parsed["parser_id"], "parser_metadata": parsed["parser_metadata"], "source_identifiers": parsed["source_identifiers"]})
    passage_rows = []
    source_rows_by_alias = {row["article_alias"]: row for row in source_rows}
    for pid, passage in passages.items():
        draft = passage["draft"]
        alias = draft["article_alias"]
        block = parsed_by_alias[alias].get(draft["provisional_block_id"])
        require(block is not None and block["text"] == passage["text"] and block["locator"] == passage["locator"], f"Accepted-parser reconciliation mismatch: {pid}")
        source = source_rows_by_alias[alias]
        passage_rows.append({"passage_id": pid, "article_alias": alias, "source_sha256": source["source_sha256"], "blocks_sha256": source["blocks_sha256"], "parser_id": source["parser_id"], "block_id": block["id"], "block_ordinal": block["ordinal"], "block_text_sha256": digest(block["text"].encode("utf-8")), "block_text_code_points": len(block["text"]), "locator": block["locator"]})
    quote_rows = []
    for split, question in questions:
        for number, span in enumerate(question["provisional_spans"], 1):
            passage = passages[span["passage_id"]]["draft"]
            block = parsed_by_alias[question["article_alias"]][passage["provisional_block_id"]]
            require(block["text"][span["start"]:span["end"]] == span["quote"], f"Accepted-parser quote mismatch: {question['id']}/{number}")
            quote_rows.append({"question_id": question["id"], "split": split, "span_ordinal": number, "passage_id": span["passage_id"], "article_alias": question["article_alias"], "anchor": {"block_id": block["id"], "start": span["start"], "end": span["end"], "quote": span["quote"]}})
    return {"schema_version": 1, "status": STATUS, "offset_unit": "Unicode code points, half-open [start,end)", "block_text_hash_rule": "SHA-256 of exact canonical block text encoded UTF-8; no additional normalization", "full_blocks_hash_rule": "SHA-256 of sorted-key compact finite UTF-8 JSON with ensure_ascii=False over the complete parser blocks array", "draft_file_pins": [{"file": name, "sha256": digest((base / name).read_bytes()), "size_bytes": (base / name).stat().st_size} for name in INPUT_FILES], "counts": {"sources": 3, "passages": len(passages), "questions": 12, "quotes": sum(len(q["provisional_spans"]) for _, q in questions), "development_questions": 0, "held_out_questions": 12, "answerable_questions": 9, "no_answer_questions": 3, "quantitative_questions": sum("quantitative_estimate_interval_denominator" in q["challenge_tags"] for _, q in questions), "AND_questions": sum(bool(q["sufficient_support_sets"]) and all(len({(passages[pid]["draft"]["article_alias"], passages[pid]["draft"]["provisional_block_id"]) for pid in group}) >= 2 for group in q["sufficient_support_sets"]) for _, q in questions)}, "sources": source_rows, "passages": passage_rows, "question_quotes": quote_rows}


def compare_recorded(expected, actual):
    """Retain historical provenance; allow only a consistent Python-version delta."""
    def runtime_version(value, label):
        require(len(value["sources"]) == 3, f"{label}: expected three source runtime fields")
        versions = [row["parser_metadata"]["python_version"] for row in value["sources"]]
        require(all(isinstance(version, str) and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[a-zA-Z]+[0-9]+)?", version) for version in versions), f"{label}: invalid Python runtime version")
        require(len(set(versions)) == 1, f"{label}: inconsistent Python runtime metadata across three sources")
        return versions[0]

    historical = runtime_version(expected, "Historical anchors")
    effective = runtime_version(actual, "Effective parser")
    # Compare copied representations without mutating either captured metadata set.
    comparable = []
    for value in (expected, actual):
        copy = json.loads(canonical(value))
        for row in copy["sources"]:
            del row["parser_metadata"]["python_version"]
        comparable.append(copy)
    require(comparable[0] == comparable[1], "Recorded anchor/source/parser-options/draft-file provenance differs; do not rewrite questions or anchors to hide a mismatch.")
    return {"historical_python_version": historical, "effective_python_version": effective, "python_version_differs": historical != effective}


def verify_freeze(base):
    freeze_path = base / "freeze.json"
    if not freeze_path.exists():
        return False
    declaration = load_json(freeze_path)
    require(declaration["status"] == "frozen_before_v3_ranking", "Invalid coordinator freeze status")
    require(type(declaration["ranking_runs_before_freeze"]) is int and declaration["ranking_runs_before_freeze"] == 0, "Medical ranking preceded coordinator freeze")
    prefix = "tests/fixtures/medical_retrieval_v3/"
    pins = declaration["held_out"]["frozen_files"]
    required = {prefix + name for name in (*INPUT_FILES, "anchors.json", "verify.py", "README.md")}
    require(required <= set(pins), "Incomplete coordinator held-out file pins")
    for repository_path, pin in pins.items():
        if not repository_path.startswith(prefix):
            continue
        name = repository_path.removeprefix(prefix)
        require(name in {*INPUT_FILES, "anchors.json", "verify.py", "README.md"}, "Unexpected coordinator held-out fixture pin")
        content = (base / name).read_bytes()
        require(digest(content) == pin["sha256"] and len(content) == pin["size_bytes"], f"Coordinator-frozen file changed: {name}")
    return True


def audit(base):
    expected = load_json(base / "anchors.json")
    actual = reconciled_anchors(base)
    runtime = compare_recorded(expected, actual)
    return actual, runtime, verify_freeze(base)


def self_test(base):
    """Guarded copied-fixture negatives; actual archives and freeze are read-only."""
    rejected = []
    positive = []
    names = (*INPUT_FILES, "anchors.json", "verify.py", "README.md")
    with tempfile.TemporaryDirectory(prefix="r23-audit-") as scratch:
        template = Path(scratch) / "template" / "medical_retrieval_v3"
        template.mkdir(parents=True)
        for name in names:
            shutil.copyfile(base / name, template / name)
        if (base / "freeze.json").exists():
            shutil.copyfile(base / "freeze.json", template / "freeze.json")
        for folder, aliases in (("medical_sources_v3", ("cbti", "ckm")), ("medical_sources_v3_imaging", ("mri",))):
            target = template.parent / folder
            target.mkdir()
            # Preserve manifest bytes as opaque archive history; inspect only
            # the whitelisted rows during verification. Excluded XML is absent.
            shutil.copyfile(base / ".." / folder / "manifest.json", target / "manifest.json")
            for alias in aliases:
                shutil.copyfile(base / ".." / folder / (alias + ".xml"), target / (alias + ".xml"))

        def case(label):
            parent = Path(scratch) / ("case-" + str(len(rejected) + len(positive)))
            shutil.copytree(template.parent, parent)
            return parent / "medical_retrieval_v3"

        def mutate(directory, name, callback):
            value = load_json(directory / name)
            callback(value)
            (directory / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        def negative(label, callback, expected_message=None):
            directory = case(label)
            callback(directory)
            try:
                audit(directory)
            except (ValueError, OSError, KeyError, TypeError, ET.ParseError) as error:
                require(expected_message is None or expected_message in str(error), f"Wrong rejection for {label}: {error}")
                rejected.append(label)
            else:
                raise ValueError("Tamper case accepted: " + label)

        negative("shifted Unicode span", lambda d: mutate(d, "held-out.json", lambda x: x["questions"][0]["provisional_spans"][0].update(start=x["questions"][0]["provisional_spans"][0]["start"] + 1)))

        def ascii_quote(value):
            span = next(s for q in value["questions"] for s in q["provisional_spans"] if "−" in s["quote"])
            span["quote"] = span["quote"].replace("−", "-")
        negative("Unicode minus changed to ASCII", lambda d: mutate(d, "held-out.json", ascii_quote))
        negative("cross-source passage binding", lambda d: mutate(d, "passages.json", lambda x: x["passages"][0].update(article_alias="ckm")))
        negative("passage source hash", lambda d: mutate(d, "passages.json", lambda x: x["passages"][0].update(source_sha256="0" * 64)))
        negative("absent original XML locator", lambda d: mutate(d, "passages.json", lambda x: x["passages"][0].update(element_path="/article[1]/body[1]/sec[999]/p[1]")))
        negative("canonical block text", lambda d: mutate(d, "passages.json", lambda x: x["passages"][0].update(provisional_canonical_text=x["passages"][0]["provisional_canonical_text"] + " ")))
        negative("block ordinal", lambda d: mutate(d, "anchors.json", lambda x: x["passages"][0].update(block_ordinal=x["passages"][0]["block_ordinal"] + 1)))
        negative("block text SHA-256", lambda d: mutate(d, "anchors.json", lambda x: x["passages"][0].update(block_text_sha256="0" * 64)))
        negative("complete blocks SHA-256", lambda d: mutate(d, "anchors.json", lambda x: x["sources"][0].update(blocks_sha256="0" * 64)))
        negative("omitted sufficient OR alternative", lambda d: mutate(d, "held-out.json", lambda x: x["questions"][0]["sufficient_support_sets"].pop()))
        negative("sufficient singleton added to declared AND", lambda d: mutate(d, "held-out.json", lambda x: x["questions"][0]["sufficient_support_sets"].append(["cbti_primary"])))

        def duplicate_block(value):
            row = copy.deepcopy(value["passages"][0])
            row["id"] = "same-block-different-passage-name"
            value["passages"].append(row)
        negative("duplicate canonical block with another passage ID", lambda d: mutate(d, "passages.json", duplicate_block))
        negative("null relabelled with positive support", lambda d: mutate(d, "held-out.json", lambda x: x["questions"][3]["sufficient_support_sets"].append(["cbti_primary"])))
        negative("inconsistent historical Python runtime", lambda d: mutate(d, "anchors.json", lambda x: x["sources"][0]["parser_metadata"].update(python_version="3.12.6")))
        negative("parser normalization option", lambda d: mutate(d, "anchors.json", lambda x: x["sources"][0]["parser_metadata"].update(normalization="changed")))
        negative("acquisition-manifest pin", lambda d: mutate(d, "manifest.json", lambda x: x["source_manifest_pins"][0].update(sha256="0" * 64)))

        def rewritten_source_and_gold(directory):
            raw_path = directory / "../medical_sources_v3_imaging/mri.xml"
            raw = raw_path.read_bytes()
            changed = raw.replace(b'encoding="utf-8"', b'encoding="UTF-8"', 1)
            require(changed != raw and len(changed) == len(raw), "Same-size original-byte tamper setup failed")
            raw_path.write_bytes(changed)
            new_hash = digest(changed)
            def change_manifest(value):
                next(s for s in value["sources"] if s["alias"] == "mri")["source_sha256"] = new_hash
            mutate(directory, "manifest.json", change_manifest)
            mutate(directory, "passages.json", lambda x: [p.update(source_sha256=new_hash) for p in x["passages"] if p["article_alias"] == "mri"])
            def change_anchors(value):
                for row in value["sources"] + value["passages"]:
                    if row["article_alias"] == "mri":
                        row["source_sha256"] = new_hash
                for pin in value["draft_file_pins"]:
                    content = (directory / pin["file"]).read_bytes()
                    pin.update(sha256=digest(content), size_bytes=len(content))
            mutate(directory, "anchors.json", change_anchors)
        negative("changed raw with rewritten gold/anchor hashes and unchanged acquisition", rewritten_source_and_gold, "differs from accepted acquisition bytes")

        def frozen_readme_tamper(directory):
            pins = {}
            for name in names:
                raw = (directory / name).read_bytes()
                pins["tests/fixtures/medical_retrieval_v3/" + name] = {"sha256": digest(raw), "size_bytes": len(raw)}
            declaration = {"status": "frozen_before_v3_ranking", "ranking_runs_before_freeze": 0, "held_out": {"frozen_files": pins}}
            # This simulated freeze lives only in the disposable copied fixture.
            (directory / "freeze.json").write_text(json.dumps(declaration), encoding="utf-8")
            audit(directory)
            with (directory / "README.md").open("a", encoding="utf-8") as handle:
                handle.write("\nchanged after simulated freeze\n")
        negative("after-freeze own README pin", frozen_readme_tamper, "Coordinator-frozen file changed")

        directory = case("runtime preservation")
        if (directory / "freeze.json").exists():
            (directory / "freeze.json").unlink()
        current_versions = {s["parser_metadata"]["python_version"] for s in load_json(directory / "anchors.json")["sources"]}
        prior = "3.12.6" if current_versions != {"3.12.6"} else "3.12.5"
        mutate(directory, "anchors.json", lambda x: [s["parser_metadata"].update(python_version=prior) for s in x["sources"]])
        before = (directory / "anchors.json").read_bytes()
        _, runtime, _ = audit(directory)
        require(runtime["historical_python_version"] == prior and runtime["python_version_differs"], "Consistent historical runtime delta was not reported")
        require((directory / "anchors.json").read_bytes() == before, "Historical runtime anchors were rewritten")
        positive.append("consistent historical runtime delta reported without rewriting anchors")
    return {"negative_cases_rejected": rejected, "positive_cases_passed": positive}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-dir", type=Path, default=HERE, help="Optional copied fixture directory; checks remain read-only")
    parser.add_argument("--self-test", action="store_true", help="Run guarded disposable-copy tamper and runtime-preservation cases")
    args = parser.parse_args()
    base = args.fixture_dir.resolve()
    try:
        actual, runtime, frozen = audit(base)
        tests = self_test(base) if args.self_test else None
    except (ValueError, OSError, KeyError, TypeError, ET.ParseError) as error:
        raise SystemExit(f"FAIL: {error}") from None
    counts = actual["counts"]
    status = "Coordinator freeze verified" if frozen else "Anchor reconciliation ready; pilot remains unfrozen"
    print(f"PASS: {counts['sources']} pinned sources; {counts['passages']} exact main-article passages; {counts['questions']} fresh held-out questions ({counts['answerable_questions']} answerable, {counts['no_answer_questions']} no-answer; {counts['quantitative_questions']} quantitative, {counts['AND_questions']} necessary distinct-block AND); {counts['quotes']} exact Unicode quote spans. {status}. No ranking/model/index/network.")
    print(f"Runtime provenance: historical Python {runtime['historical_python_version']}; effective current Python {runtime['effective_python_version']}; version differs={str(runtime['python_version_differs']).lower()}. Historical anchors unchanged.")
    if tests is not None:
        print(json.dumps({"tamper_audit": tests}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
