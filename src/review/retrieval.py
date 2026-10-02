"""Deterministic lexical passage candidates from one project-source snapshot."""

import hashlib
import json
import math
import re
from collections import Counter


_TOKENIZER = "unicode-casefold-word-v1"
_STOP_WORDS = frozenset("a an and are as at be been by did do does for from had has have how in is it its of on or that the their there these this to was were what when where which who with would".split())
_WINDOW_WORDS = 200
_OVERLAP_WORDS = 40
_K1 = 1.2
_B = 0.75
_CONTEXT_WORDS = 80
_CONTEXT_RULE = "preceding-paragraph-same-xml-parent-v1"


def _tokens(text):
    return [token for token in re.findall(r"\w+", text.casefold()) if token not in _STOP_WORDS]


def _windows(text):
    words = list(re.finditer(r"\S+", text))
    previous_end = 0
    for start in range(0, len(words), _WINDOW_WORDS - _OVERLAP_WORDS):
        end = min(start + _WINDOW_WORDS, len(words))
        if end <= previous_end:
            break
        yield words[start].start(), words[end - 1].end()
        previous_end = end


def _snapshot_hash(manifest):
    try:
        serialized = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    except (TypeError, ValueError, UnicodeError):
        raise ValueError("Selected source manifest must contain finite valid JSON") from None


def _contexts(blocks, format):
    """Find one preceding accepted paragraph per target, within this document."""
    previous, contexts = {}, {}
    if format != "jats_xml":
        return contexts
    for block in blocks:
        locator = block["locator"]
        if locator["type"] != "xml_element" or locator.get("tag") not in {"p", "table-wrap"}:
            continue
        parent = locator["path"].rsplit("/", 1)[0]
        preceding = previous.get(parent)
        if preceding is not None:
            words = list(re.finditer(r"\S+", preceding["text"]))
            if words:
                start, end = words[max(0, len(words) - _CONTEXT_WORDS)].start(), words[-1].end()
                contexts[block["id"]] = {"anchor": {"block_id": preceding["id"], "start": start, "end": end, "quote": preceding["text"][start:end]}, "locator": preceding["locator"]}
        # Update after selecting context, so a paragraph cannot borrow from itself.
        if locator["tag"] == "p":
            previous[parent] = block
    return contexts


def _manifest(record, document, link):
    identifiers = document["source_identifiers"]
    if not isinstance(identifiers, dict):
        raise ValueError("Selected source identifiers are corrupt")
    if any(record[name] is not None and record[name] != identifiers[name] for name in ("doi", "pmid") if name in identifiers):
        raise ValueError("Selected source identity contradicts the current canonical report: source_identity_conflict")
    return {
        "document_id": document["id"], "record_id": record["id"],
        **{key: document[key] for key in ("version", "format", "source_sha256", "blocks_sha256", "parser_id", "parser_metadata", "source_identifiers", "source_url", "version_label")},
        "record_title": record["title"],
        **{key: record[key] for key in ("doi", "pmid", "title_abstract_state", "full_text_status", "full_text_state")},
        "study_link_state": link["state"], "study_ids": link["study_ids"],
    }


def _candidates(store, project_id, scope, method):
    records = store.list_records(project_id)
    active = {document["record_id"]: document for document in store.list_documents(project_id) if document["active"]}
    links = {link["record_id"]: link for link in store.list_study_links(project_id)}
    manifest, candidates = [], []
    for record_order, record in enumerate(records):
        if record["id"] not in active:
            continue
        if scope == "included" and (record["title_abstract_state"] != "include" or record["full_text_status"] != "retrieved" or record["full_text_state"] != "include"):
            continue
        document = active[record["id"]]
        metadata = _manifest(record, document, links[record["id"]])
        # This public read checks both retained source bytes and canonical block hashes.
        blocks = store.get_source_blocks(project_id, document["id"])
        manifest.append(metadata)
        contexts = _contexts(blocks, document["format"]) if method == "bm25_context" else {}
        for block in blocks:
            for start, end in _windows(block["text"]):
                quote = block["text"][start:end]
                frequencies = Counter(_tokens(quote))
                context = contexts.get(block["id"])
                if context is not None:
                    frequencies.update(_tokens(context["anchor"]["quote"]))
                passage = {
                    "project_id": project_id, "record_id": record["id"], "document_id": document["id"], "document_version": document["version"],
                    **{key: document[key] for key in ("source_sha256", "blocks_sha256", "parser_id")},
                    "anchor": {"block_id": block["id"], "start": start, "end": end, "quote": quote},
                    "locator": block["locator"], "full_text_state": record["full_text_state"],
                    "study_link_state": metadata["study_link_state"], "study_ids": metadata["study_ids"],
                }
                if method == "bm25_context":
                    passage["scoring_context"] = [] if context is None else [context]
                candidates.append({"passage": passage, "frequencies": frequencies, "length": sum(frequencies.values()), "tie": (record_order, block["ordinal"], start, end)})
    return manifest, candidates


def _score(candidates, query_tokens, method):
    if not candidates or not query_tokens:
        return []
    n = len(candidates)
    average = sum(candidate["length"] for candidate in candidates) / n
    df = Counter(token for candidate in candidates for token in candidate["frequencies"])
    scored = []
    for candidate in candidates:
        terms = candidate["frequencies"]
        if method == "token_overlap":
            score = sum(token in terms for token in query_tokens)
        else:
            score = 0.0
            for token in query_tokens:
                frequency = terms.get(token, 0)
                if frequency:
                    idf = math.log(1 + (n - df[token] + 0.5) / (df[token] + 0.5))
                    score += idf * frequency * (_K1 + 1) / (frequency + _K1 * (1 - _B + _B * candidate["length"] / average))
        if score > 0:
            scored.append((score, candidate))
    return sorted(scored, key=lambda item: (-item[0], item[1]["tie"]))


def search_sources(store, project_id, query, *, top_k=5, method="bm25", scope="included"):
    """Return candidate passages without writing search or evidence ledger events."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Source retrieval query must be a nonempty string")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
        raise ValueError("Source retrieval top_k must be a positive integer")
    if not isinstance(method, str) or method not in {"token_overlap", "bm25", "bm25_context"}:
        raise ValueError("Source retrieval method must be token_overlap, bm25, or bm25_context")
    if not isinstance(scope, str) or scope not in {"included", "all_attached"}:
        raise ValueError("Source retrieval scope must be included or all_attached")
    parameters = {"tokenizer_id": _TOKENIZER, "stop_words": sorted(_STOP_WORDS), "window_words": _WINDOW_WORDS, "overlap_words": _OVERLAP_WORDS}
    if method in {"bm25", "bm25_context"}:
        parameters.update(k1=_K1, b=_B)
    if method == "bm25_context":
        parameters.update(context_rule=_CONTEXT_RULE, context_max_words=_CONTEXT_WORDS)
    with store._snapshot():
        store._project(project_id)
        manifest, candidates = _candidates(store, project_id, scope, method)
        ranked = _score(candidates, sorted(set(_tokens(query))), method)
        return {
            "schema_version": 1, "status": "candidate_passages", "project_id": project_id, "query": query,
            "method": method, "method_version": "lit-rev-engine.project-retrieval." + ("v2." if method == "bm25_context" else "v1.") + method,
            "parameters": parameters, "scope": scope, "top_k": top_k,
            "source_manifest": manifest, "source_snapshot_sha256": _snapshot_hash(manifest),
            "indexed_passages": len(candidates), "matched_passages": len(ranked),
            "passages": [{"rank": rank, "score": score, **candidate["passage"]} for rank, (score, candidate) in enumerate(ranked[:top_k], 1)],
        }
