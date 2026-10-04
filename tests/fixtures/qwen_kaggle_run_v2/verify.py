"""Read-only, stdlib verification and replay of the first real Kaggle failure."""

import argparse
from collections import Counter
import hashlib
import io
import json
import lzma
import math
from pathlib import Path
import re
import tarfile


FREEZE_SHA = "04f0a961eb0f7d91626a72e93f68c5d4f8cc77f4ff0f78fbb72063219d878b62"
JOB_SHA = "ab6e06ca37d89f95800fc09100f2c8a41c595f3b76c0497fb9f2679850672a8f"
RESULTS_SHA = "0f5aa688f5382ddbfae3260bc1d832ba6d81aa2222a716feae07395887ea42be"
ARCHIVE_SHA = "87c3dff55b968f4f91e9e8f5598854a4d8dd5418f9c134026953861f57e0f101"
EXPECTED_FILES = {
    "job.json": (238789, "e3121ebc9edae944ad4b522763ecd41dbf5eec6f27391746d05e59cb0eaf1635"),
    "results.json": (6058684, "5e6a7e5b3da9dc541298a2b409bdf3cd200440be85b190a598c37b29f30c1874"),
    "preparation.json": (98794, "edd2d69f3806460c3f8610c73ee7ea3a0baeef1efa1bfd1dafa7eee8d487d810"),
    "result.json": (101944, "f6e77ccd61d6a0eb294f69061c9c72043a76a9118039888c1eb40b815aec968f"),
    "validation.receipt.json": (6397765, "5bb15a1a01ba878ec23a2172d31bc679716a5eba86917862cca4223389d583f5"),
}
_STOP = frozenset("a an and are as at be been by did do does for from had has have how in is it its of on or that the their there these this to was were what when where which who with would".split())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    value = json.loads(data, object_pairs_hook=pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
    canonical(value)
    return value


def envelope(value, expected=None):
    require(isinstance(value, dict) and set(value) == {"payload", "payload_sha256"}, "Invalid envelope schema")
    require(value["payload_sha256"] == digest(value["payload"]), "Envelope checksum mismatch")
    require(expected is None or value["payload_sha256"] == expected, "Trusted envelope checksum mismatch")
    return value["payload"]


def read_files(directory):
    """Return the five original JSON byte streams without extracting any paths."""
    directory = Path(directory)
    manifest = read_json((directory / "manifest.json").read_bytes())
    require(type(manifest["schema_version"]) is int and manifest["schema_version"] == 1
            and manifest["ticket"] == "K3A" and manifest["status"] == "preserved_first_actual_kaggle_failure", "Archive manifest identity changed")
    require(type(manifest["saved_script_version"]) is int and manifest["saved_script_version"] == 355104707, "Saved Kaggle script version changed")
    require(manifest["freeze"]["sha256"] == FREEZE_SHA and manifest["trusted_job_payload_sha256"] == JOB_SHA
            and manifest["trusted_results_payload_sha256"] == RESULTS_SHA, "Manifest trusted bindings changed")
    require(set(manifest["files"]) == set(EXPECTED_FILES), "Archive file list changed")
    for name, (size, expected) in EXPECTED_FILES.items():
        require(manifest["files"][name]["sha256"] == expected and manifest["files"][name]["size_bytes"] == size,
                "Manifest original file digest changed: " + name)
    archive = manifest["archive"]
    require(archive["file"] == "artifacts.tar.xz" and archive["sha256"] == ARCHIVE_SHA, "Archive binding changed")
    path = directory / archive["file"]
    require(path.stat().st_size == archive["size_bytes"] and path.stat().st_size <= 16 * 1024 * 1024, "Archive size mismatch")
    data = path.read_bytes()
    require(sha(data) == ARCHIVE_SHA, "Archive file checksum mismatch")
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=256 * 1024 * 1024)
    unpacked = decoder.decompress(data, max_length=20 * 1024 * 1024)
    require(decoder.eof and not decoder.unused_data and len(unpacked) == archive["uncompressed_tar_bytes"], "Archive exceeds bound or has trailing streams")
    result = {}
    with tarfile.open(fileobj=io.BytesIO(unpacked), mode="r:") as stream:
        for member in stream:
            require(member.isfile() and member.name in EXPECTED_FILES and member.name not in result, "Unexpected archive member")
            size, expected = EXPECTED_FILES[member.name]
            require(member.size == size, "Archive member size mismatch")
            body = stream.extractfile(member).read(size + 1)
            require(len(body) == size and sha(body) == expected, "Original file checksum mismatch: " + member.name)
            result[member.name] = body
    require(set(result) == set(EXPECTED_FILES), "Archive member missing")
    return manifest, result


def _terms(text):
    return [term for term in re.findall(r"\w+", text.casefold()) if term not in _STOP]


def lexical_order(candidates, query, limit):
    frequencies = []
    for candidate in candidates:
        passage = candidate["passage"]
        words = Counter(_terms(passage["anchor"]["quote"]))
        for context in passage["scoring_context"]:
            words.update(_terms(context["anchor"]["quote"]))
        frequencies.append(words)
    count = len(frequencies)
    average = sum(sum(words.values()) for words in frequencies) / count
    df = Counter(term for words in frequencies for term in words)
    scored = []
    for index, words in enumerate(frequencies):
        score = 0.0
        for term in sorted(set(_terms(query))):
            frequency = words.get(term, 0)
            if frequency:
                idf = math.log(1 + (count - df[term] + 0.5) / (df[term] + 0.5))
                score += idf * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * sum(words.values()) / average))
        if score > 0:
            scored.append((score, index))
    scored.sort(key=lambda row: (-row[0], candidates[row[1]]["tie"]))
    return [index for _, index in scored[:limit]]


def vector(row, dimension, max_tokens):
    value = row["vector"]
    require(isinstance(value, list) and len(value) == dimension and
            all(type(number) in (int, float) and math.isfinite(number) for number in value), "Invalid embedding vector")
    require(abs(math.hypot(*value) - 1.0) <= 0.0001, "Embedding is not a unit vector")
    require(type(row["tokens"]) is int and 1 <= row["tokens"] <= max_tokens, "Invalid token count")
    return value


def replay(job, results, traces):
    candidates, reps = job["candidates"], job["representations"]
    documents = results["document_embeddings"]
    require(len(documents) == len(reps) == 102 and len(results["query_results"]) == len(traces) == len(job["queries"]) == 8, "Pilot counts changed")
    vectors = []
    counts = []
    for rep, row in zip(reps, documents, strict=True):
        require(set(row) == {"id", "vector", "tokens"} and row["id"] == rep["id"], "Document embedding ID/order mismatch")
        vectors.append(vector(row, job["profile"]["dimension"], job["profile"]["max_tokens"]))
        counts.append(row["tokens"])
    for query, row, trace in zip(job["queries"], results["query_results"], traces, strict=True):
        require(row["id"] == trace["query_id"] == query["id"] and trace["query"] == query["query"], "Query binding mismatch")
        query_vector = vector(row, job["profile"]["dimension"], job["profile"]["max_tokens"])
        counts.append(row["tokens"])
        lexical = lexical_order(candidates, query["query"], job["candidate_k"])
        require(query["lexical_block_indices"] == lexical, "Lexical ordering mismatch")
        dense = {}
        for rep, values in zip(reps, vectors, strict=True):
            similarity = sum(a * b for a, b in zip(query_vector, values, strict=True))
            block = rep["block_index"]
            dense[block] = max(dense.get(block, -math.inf), similarity)
        dense_order = sorted(dense, key=lambda index: (-dense[index], candidates[index]["tie"]))[:job["candidate_k"]]
        fused = {}
        for ordering in (lexical, dense_order):
            for rank, index in enumerate(ordering, 1):
                fused[index] = fused.get(index, 0.0) + 1 / (60 + rank)
        blocks = sorted(fused, key=lambda index: (-fused[index], candidates[index]["tie"]))[:job["candidate_k"]]
        pool = [rep for index in blocks for rep in reps if rep["block_index"] == index]
        require(row["pool_representation_ids"] == [rep["id"] for rep in pool] and len(row["rerank_scores"]) == len(pool), "Candidate pool mismatch")
        scores = {}
        for rep, score in zip(pool, row["rerank_scores"], strict=True):
            require(set(score) == {"id", "score", "tokens"} and score["id"] == rep["id"], "Rerank ID/order mismatch")
            require(type(score["score"]) in (int, float) and math.isfinite(score["score"]) and 0 <= score["score"] <= 1, "Invalid relevance score")
            require(type(score["tokens"]) is int and 1 <= score["tokens"] <= job["profile"]["max_tokens"], "Invalid rerank token count")
            counts.append(score["tokens"])
            block = rep["block_index"]
            scores[block] = max(scores.get(block, -math.inf), score["score"])
        ordering = sorted(scores, key=lambda index: (-scores[index], candidates[index]["tie"]))
        passages = [{"rank": rank, "score": scores[index], **candidates[index]["passage"]}
                    for rank, index in enumerate(ordering[:job["top_k"]], 1)]
        require(canonical(trace["passages"]) == canonical(passages), "Recorded ranks or own anchors contradict raw GPU results")
        require(trace["profile"] == job["profile"] and trace["source_manifest"] == job["source_manifest"]
                and trace["source_snapshot_sha256"] == job["source_snapshot_sha256"]
                and trace["job_sha256"] == JOB_SHA and trace["results_sha256"] == RESULTS_SHA
                and trace["answerability"] == "not_assessed" and trace["verification"] == "human_review_required"
                and trace["execution"] == "offline_import" and trace["scope"] == "included" and trace["top_k"] == 5,
                "Trace provenance or candidate-only boundary mismatch")
    require(results["runtime"]["max_input_tokens"] == max(counts) == 726, "Maximum recorded token count changed")


def grade(questions, traces, document_bindings):
    per_question = []
    for question, trace in zip(questions, traces, strict=True):
        require(question["id"] == trace["query_id"] and question["query"] == trace["query"], "Gold query binding mismatch")
        def covered(anchor):
            for passage in trace["passages"]:
                own = passage["anchor"]
                if (passage["document_id"] == document_bindings[anchor["source_id"]]
                        and own["block_id"] == anchor["block_id"]
                        and own["start"] <= anchor["start"] < anchor["end"] <= own["end"]
                        and own["quote"][anchor["start"] - own["start"]:anchor["end"] - own["start"]] == anchor["quote"]):
                    return True
            return False
        if question["answerable"]:
            groups = question["support_sets"]
            coverage = max(sum(covered(anchor) for anchor in group) / len(group) for group in groups)
            complete = any(all(covered(anchor) for anchor in group) for group in groups)
            per_question.append({"id": question["id"], "answerable": True, "coverage": coverage, "complete": complete})
        else:
            per_question.append({"id": question["id"], "answerable": False, "coverage": None, "complete": None,
                                 "context_covered": sum(covered(anchor) for anchor in question["context_anchors"]),
                                 "context_total": len(question["context_anchors"]), "returned_candidates": len(trace["passages"])})
    positives = [row for row in per_question if row["answerable"]]
    return {"metrics": {"answerable": len(positives), "complete_positives": sum(row["complete"] for row in positives),
                        "mean_support_coverage": sum(row["coverage"] for row in positives) / len(positives),
                        "nulls": [row for row in per_question if not row["answerable"]]}, "per_question": per_question}


def verify(directory=None, repository=None):
    directory = Path(directory) if directory is not None else Path(__file__).resolve().parent
    repository = Path(repository) if repository is not None else Path(__file__).resolve().parents[3]
    manifest, originals = read_files(directory)
    data = {name: read_json(body) for name, body in originals.items()}
    job = envelope(data["job.json"], JOB_SHA)
    results = envelope(data["results.json"], RESULTS_SHA)
    receipt = envelope(data["validation.receipt.json"])
    preparation, evaluation = data["preparation.json"], data["result.json"]
    freeze_bytes = (repository / "docs/qwen-kaggle-freeze-v2.json").read_bytes()
    require(sha(freeze_bytes) == FREEZE_SHA, "Prospective freeze bytes changed")
    freeze = read_json(freeze_bytes)
    gold_files = {}
    for relative in ("tests/fixtures/qwen_pilot_gold/questions.json", "tests/fixtures/qwen_pilot_gold/blocks.json",
                     "tests/fixtures/qwen_pilot_gold/manifest.json", "tests/fixtures/qwen_pilot_sources/manifest.json",
                     "tests/fixtures/qwen_pilot_sources/mammography.xml", "tests/fixtures/qwen_pilot_sources/breast_us.xml"):
        body = (repository / relative).read_bytes()
        require(len(body) == freeze["files"][relative]["size_bytes"] and sha(body) == freeze["files"][relative]["sha256"], "Frozen source/gold changed: " + relative)
        if relative.endswith(".json"):
            gold_files[relative] = read_json(body)
    questions = gold_files["tests/fixtures/qwen_pilot_gold/questions.json"]["questions"]
    blocks = gold_files["tests/fixtures/qwen_pilot_gold/blocks.json"]["blocks"]
    require(preparation["job_sha256"] == evaluation["job_sha256"] == JOB_SHA
            and evaluation["results_sha256"] == RESULTS_SHA and results["job_sha256"] == JOB_SHA,
            "Preparation/evaluation/result job bindings disagree")
    require(preparation["freeze"] == evaluation["freeze"] == {"sha256": FREEZE_SHA, "size_bytes": len(freeze_bytes)}, "Freeze record mismatch")
    require(canonical(job["profile"]) == canonical(freeze["profile"]) and job["profile_sha256"] == digest(job["profile"])
            and results["profile_sha256"] == job["profile_sha256"] and job["source_snapshot_sha256"] == digest(job["source_manifest"]), "Profile/source binding mismatch")
    require(job["top_k"] == 5 and job["candidate_k"] == 20 and job["scope"] == "included", "Frozen ranking configuration changed")
    bindings = preparation["document_bindings"]
    canonical_blocks = {(bindings[block["source_id"]], block["block_id"]): block for block in blocks}
    require(len(job["candidates"]) == len(canonical_blocks) == 102, "Canonical source snapshot count changed")
    for candidate in job["candidates"]:
        passage = candidate["passage"]
        block = canonical_blocks[(passage["document_id"], passage["anchor"]["block_id"])]
        require(passage["anchor"] == {"block_id": block["block_id"], "start": 0, "end": len(block["text"]), "quote": block["text"]}
                and passage["locator"] == block["locator"] and passage["full_text_state"] == "include", "Candidate own block differs from frozen gold source")
        for context in passage["scoring_context"]:
            own = context["anchor"]
            context_block = canonical_blocks[(passage["document_id"], own["block_id"])]
            require(context_block["text"][own["start"]:own["end"]] == own["quote"] and context["locator"] == context_block["locator"], "Scoring context is not an exact separate source span")
    require(receipt["kind"] == "qwen-kaggle-receipt-v1" and canonical(receipt["job"]) == canonical(data["job.json"])
            and canonical(receipt["results"]) == canonical(data["results.json"]), "Immutable receipt does not preserve original job/results")
    recomputed = receipt["recomputed"]
    require(canonical(recomputed["traces"]) == canonical(evaluation["traces"]) and recomputed["job_sha256"] == JOB_SHA
            and recomputed["results_sha256"] == RESULTS_SHA and recomputed["runtime"] == results["runtime"] == evaluation["runtime"], "Receipt/evaluation replay mismatch")
    replay(job, results, evaluation["traces"])
    candidate = grade(questions, evaluation["traces"], bindings)
    reference_traces = [{**trace, "query_id": question["id"]} for question, trace in zip(questions, preparation["reference"]["traces"], strict=True)]
    reference = grade(questions, reference_traces, bindings)
    require(candidate["metrics"] == evaluation["candidate"]["metrics"] and candidate["per_question"] == evaluation["candidate"]["per_question"], "Recorded candidate grade does not reproduce")
    require(reference["metrics"] == preparation["reference"]["metrics"] == evaluation["reference"]["metrics"]
            and reference["per_question"] == evaluation["reference"]["per_question"], "Reference grade does not reproduce")
    runtime = results["runtime"]
    require(runtime["backend"] == "kaggle-cuda-transformers" and runtime["gpu_name"] == "Tesla T4"
            and runtime["elapsed_seconds"]["total"] == 395.076408088 and runtime["paid_inference_calls"] == 0
            and runtime["truncated"] is False and runtime["peak_vram_bytes"] == 8167223296, "Recorded GPU runtime changed")
    metrics = candidate["metrics"]
    checks = {"support_coverage": metrics["mean_support_coverage"] >= freeze["gate"]["min_mean_support_coverage"],
              "complete_positives": metrics["complete_positives"] >= freeze["gate"]["min_complete_positives"],
              "coverage_nonregression": metrics["mean_support_coverage"] >= reference["metrics"]["mean_support_coverage"],
              "complete_nonregression": metrics["complete_positives"] >= reference["metrics"]["complete_positives"],
              "batch_time": runtime["elapsed_seconds"]["total"] <= freeze["gate"]["max_batch_seconds"],
              "paid_inference_calls": runtime["paid_inference_calls"] == 0, "exact_anchors_scope_replay_readonly": True}
    require(checks == evaluation["checks"] and evaluation["status"] == "failed" and not all(checks.values()), "The preserved failed gate was changed")
    require(metrics["mean_support_coverage"] == 0.8055555555555555 and metrics["complete_positives"] == 4
            and metrics["answerable"] == 6 and checks["support_coverage"] is False, "First actual failure summary changed")
    expected_summary = {"status": "failed", "mean_support_coverage": metrics["mean_support_coverage"],
                        "complete_positives": metrics["complete_positives"], "positive_questions": metrics["answerable"],
                        "support_coverage_gate": freeze["gate"]["min_mean_support_coverage"],
                        "batch_seconds": runtime["elapsed_seconds"]["total"], "paid_inference_calls": 0}
    require(canonical(manifest["grade"]) == canonical(expected_summary), "Archive manifest grade summary changed")
    return {"archive_verified": True, "files": len(originals), "status": "failed",
            "saved_script_version": 355104707, "job_sha256": JOB_SHA, "results_sha256": RESULTS_SHA,
            "metrics": metrics, "batch_seconds": runtime["elapsed_seconds"]["total"], "paid_inference_calls": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--repository", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.directory, args.repository), sort_keys=True, indent=2))
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError, lzma.LZMAError, tarfile.TarError) as error:
        parser.exit(1, "Archive verification failed: " + str(error) + "\n")


if __name__ == "__main__":
    main()
