#!/usr/bin/env python3
"""Read-only offline source/path/quote and accepted-parser reconciliation check."""

import argparse
import collections
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[2]
INPUT_FILES = ("manifest.json", "passages.json", "held-out.json")
STATUS = "anchor-reconciled; fresh held-out pilot unfrozen; independent semantic review and coordinator freeze pending"


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


def independently_validate(base):
    """Complete source, split, path, normalization and quote checks before parsing."""
    data = {name: load_json(base / name) for name in INPUT_FILES}
    manifest = data["manifest.json"]
    source_pin = manifest["source_manifest_pin"]
    source_manifest_bytes = (base / source_pin["file"]).read_bytes()
    require(len(source_manifest_bytes) == source_pin["size_bytes"] and digest(source_manifest_bytes) == source_pin["sha256"], "Acquisition manifest pin changed")
    require(manifest["corpus_handling_decision"].startswith("Coordinator accepted the original eNose bytes"), "Known correction handling decision missing")
    sources = {}
    require(len(manifest["sources"]) == 3, "Expected exactly three pinned sources")
    for source in manifest["sources"]:
        alias = source["alias"]
        require(alias not in sources, f"Duplicate source alias: {alias}")
        content = (base / source["file"]).read_bytes()
        require(len(content) == source["size_bytes"] and digest(content) == source["source_sha256"], f"Pinned source bytes changed: {alias}")
        require(not re.search(rb"<!ENTITY\b", content, re.I), f"Entity declaration: {alias}")
        root = ET.fromstring(content)
        own_dois = root.findall("./front/article-meta/article-id[@pub-id-type='doi']")
        require(own_dois and all(inline(item) == source["doi"] for item in own_dois), f"Own article DOI changed: {alias}")
        require(inline(root.find("./front/article-meta/title-group/article-title")) == source["title"], f"Own title changed: {alias}")
        license_urls = [element.get("{http://www.w3.org/1999/xlink}href") for element in root.findall("./front/article-meta/permissions/license")]
        require(source["license"]["xml_url"] in license_urls and source["license"]["spdx_id"] == "CC-BY-4.0", f"Own license changed: {alias}")
        sources[alias] = {"metadata": source, "content": content, "root": root}

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
    require(len(passages) == 24, "Expected exactly 24 distinct support/context passages")

    questions = []
    all_ids = set()
    all_questions = set()
    quote_count = 0
    for split, spec in manifest["splits"].items():
        rows = data[spec["file"]]["questions"]
        require(len(rows) == spec["questions"] == 12, f"Split count mismatch: {split}")
        require([q["id"] for q in rows] == spec["ids"], f"Split membership/order mismatch: {split}")
        require(collections.Counter(q["article_alias"] for q in rows) == {"singhypertension": 4, "czechia": 4, "enose": 4}, f"Article balance mismatch: {split}")
        require(sum(q["answerability"] == "no_answer" for q in rows) == spec["no_answer_questions"] == 3, f"No-answer count mismatch: {split}")
        require(collections.Counter(q["article_alias"] for q in rows if q["answerability"] == "answerable") == {"singhypertension": 3, "czechia": 3, "enose": 3}, "Expected three answerable questions per source")
        require(collections.Counter(q["article_alias"] for q in rows if q["answerability"] == "no_answer") == {"singhypertension": 1, "czechia": 1, "enose": 1}, "Expected one no-answer question per source")
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
    require(len(questions) == 12 and quote_count == 31, "Expected 12 questions and 31 exact quote spans")
    require(sum(q["answerability"] == "answerable" for _, q in questions) == 9, "Expected nine answerable questions")
    require(sum("quantitative_estimate_interval_denominator" in q["challenge_tags"] for _, q in questions) == 5, "Expected five quantitative questions")
    and_count = sum(bool(q["sufficient_support_sets"]) and all(len(group) >= 2 for group in q["sufficient_support_sets"]) for _, q in questions)
    require(and_count == 6, "Expected six questions requiring multiple necessary passages")
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
    return {"schema_version": 1, "status": STATUS, "offset_unit": "Unicode code points, half-open [start,end)", "block_text_hash_rule": "SHA-256 of exact canonical block text encoded UTF-8; no additional normalization", "full_blocks_hash_rule": "SHA-256 of sorted-key compact finite UTF-8 JSON with ensure_ascii=False over the complete parser blocks array", "draft_file_pins": [{"file": name, "sha256": digest((base / name).read_bytes()), "size_bytes": (base / name).stat().st_size} for name in INPUT_FILES], "counts": {"sources": 3, "passages": 24, "questions": 12, "quotes": 31, "development_questions": 0, "held_out_questions": 12, "answerable_questions": 9, "no_answer_questions": 3, "quantitative_questions": 5, "AND_questions": 6}, "sources": source_rows, "passages": passage_rows, "question_quotes": quote_rows}


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-dir", type=Path, default=HERE, help="Optional copied fixture directory; checks remain read-only")
    args = parser.parse_args()
    base = args.fixture_dir.resolve()
    try:
        expected = load_json(base / "anchors.json")
        actual = reconciled_anchors(base)
        runtime = compare_recorded(expected, actual)
        freeze_path = base / "freeze.json"
        frozen = freeze_path.exists()
        if frozen:
            declaration = load_json(freeze_path)
            require(declaration["status"] == "frozen_before_v2_ranking", "Invalid coordinator freeze status")
            require(type(declaration["ranking_runs_before_freeze"]) is int and declaration["ranking_runs_before_freeze"] == 0, "Medical ranking preceded coordinator freeze")
            prefix = "tests/fixtures/medical_retrieval_v2/"
            pins = declaration["held_out"]["frozen_files"]
            required = {prefix + name for name in (*INPUT_FILES, "anchors.json")}
            require(required <= set(pins), "Incomplete coordinator held-out file pins")
            for repository_path, pin in pins.items():
                if not repository_path.startswith(prefix):
                    continue
                name = repository_path.removeprefix(prefix)
                require(name in {*INPUT_FILES, "anchors.json", "verify.py", "README.md"}, "Unexpected coordinator held-out fixture pin")
                content = (base / name).read_bytes()
                require(digest(content) == pin["sha256"] and len(content) == pin["size_bytes"], f"Coordinator-frozen file changed: {name}")
    except (ValueError, OSError, KeyError, TypeError, ET.ParseError) as error:
        raise SystemExit(f"FAIL: {error}") from None
    counts = actual["counts"]
    status = "Coordinator freeze verified" if frozen else "Anchor reconciliation ready; pilot remains unfrozen"
    print(f"PASS: {counts['sources']} pinned sources; {counts['passages']} exact main-article passages; {counts['questions']} fresh held-out questions (9 answerable, 3 no-answer; 5 quantitative, 6 AND); {counts['quotes']} exact Unicode quote spans. {status}. No ranking/model/index/network.")
    print(f"Runtime provenance: historical Python {runtime['historical_python_version']}; effective current Python {runtime['effective_python_version']}; version differs={str(runtime['python_version_differs']).lower()}. Historical anchors unchanged.")


if __name__ == "__main__":
    main()
