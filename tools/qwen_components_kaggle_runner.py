"""Fresh isolated worker for the prospective component retrieval experiment.

Importing this module performs no installation, model import or GPU work. It
loads only verified explicit bundle files when run_job is called.
"""

import argparse
import gc
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import tempfile
import time


def _bootstrap(job_path, job_sha256, core_path, helper_path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    path = Path(job_path)
    if path.stat().st_size > 100 * 1024 * 1024:
        raise ValueError("Component job exceeds 100 MiB")
    envelope = json.loads(path.read_bytes(), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
    if not isinstance(envelope, dict) or set(envelope) != {"payload", "payload_sha256"}:
        raise ValueError("Invalid component job envelope")
    encoded = json.dumps(envelope["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if hashlib.sha256(encoded).hexdigest() != envelope["payload_sha256"] or envelope["payload_sha256"] != job_sha256:
        raise ValueError("Use the trusted component job checksum from local export")
    files = {"component_core.py": Path(core_path), "qwen_kaggle_environment.py": Path(helper_path),
             "qwen_components_kaggle_runner.py": Path(__file__)}
    if set(envelope["payload"].get("execution_files", {})) != set(files):
        raise ValueError("Component executable bindings are incomplete")
    for name, executable in files.items():
        if executable.name != name or not executable.resolve().is_relative_to(path.resolve().parent):
            raise ValueError("Executable must be contained in the explicit upload bundle: " + name)
        data = executable.read_bytes()
        if {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)} != envelope["payload"]["execution_files"][name]:
            raise ValueError("Executable bytes differ from the trusted job: " + name)
    def load(name, location):
        spec = importlib.util.spec_from_file_location(name, location)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    core = load("verified_component_core", core_path)
    job = core.validate_job(envelope, job_sha256)
    helper = load("verified_qwen_environment", helper_path)
    return core, helper, job


def _write(core, path, payload, *, checkpoint=False):
    path = Path(path)
    encoded = core.canonical({"payload": payload, "payload_sha256": core.digest(payload)}).encode("utf-8")
    core.require(len(encoded) <= 100 * 1024 * 1024, "Component output exceeds 100 MiB")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".qwen-components-", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        if checkpoint and path.exists():
            core.require(not path.is_symlink(), "Component checkpoint cannot be a symlink")
            held = core.read_artifact(path)["payload"]
            core.require(held.get("kind") == "qwen-components-checkpoint-v1" and held.get("job_sha256") == payload["job_sha256"]
                         and held.get("profile_sha256") == payload["profile_sha256"], "Checkpoint belongs to another job")
            temporary.replace(path)
        else:
            try:
                os.link(temporary, path)
            except FileExistsError:
                raise ValueError("Component artifacts are immutable; choose new output paths") from None
    finally:
        temporary.unlink(missing_ok=True)


def tokenize(core, tokenizer, text, torch, *, rerank=False):
    if rerank:
        ids = (tokenizer.encode(core.RERANK_PREFIX, add_special_tokens=False)
               + tokenizer.encode(text, add_special_tokens=False)
               + tokenizer.encode(core.RERANK_SUFFIX, add_special_tokens=False))
    else:
        ids = tokenizer.encode(text, add_special_tokens=True)
    core.token_count(len(ids))
    return {"input_ids": torch.tensor([ids], dtype=torch.long, device="cuda:0"),
            "attention_mask": torch.ones((1, len(ids)), dtype=torch.long, device="cuda:0")}, len(ids)


def run_job(job_path, *, job_sha256, core_path, environment_helper_path, overlay_path, installer_report_path,
            output_path, checkpoint_path, environment_audit_path, setup_seconds=0.0):
    paths = [Path(path) for path in (job_path, core_path, environment_helper_path, installer_report_path,
                                   output_path, checkpoint_path, environment_audit_path)]
    if len({path.resolve() for path in paths}) != len(paths):
        raise ValueError("Component input/output paths must be distinct")
    for path in paths[4:]:
        if os.path.lexists(path):
            raise ValueError("Preserve existing component artifacts and choose new paths")
    started = time.monotonic()
    core, helper, job = _bootstrap(job_path, job_sha256, core_path, environment_helper_path)
    print("Auditing pinned overlay, active dependencies and original CUDA Torch before model weights", flush=True)
    audit = helper.audit_environment(overlay_path, installer_report_path, job["execution_files"],
                                     active_requirements=core.ACTIVE_REQUIREMENTS, setup_seconds=setup_seconds)
    _write(core, environment_audit_path, audit)
    import torch
    from transformers import AutoModel, AutoModelForCausalLM, AutoTokenizer
    profile = core.PROFILE
    torch.manual_seed(0)
    torch.cuda.set_device(0)
    torch.cuda.reset_peak_memory_stats(0)
    stages = {"embedding_load": 0.0, "embedding_inference": 0.0, "reranker_load": 0.0, "reranker_inference": 0.0}
    documents, queries, scores = [], [], []
    def save_checkpoint(phase):
        _write(core, checkpoint_path, {"schema_version": 1, "kind": "qwen-components-checkpoint-v1",
                                      "job_sha256": job_sha256, "profile_sha256": job["profile_sha256"], "phase": phase,
                                      "document_embeddings": documents, "query_embeddings": queries, "score_rows": scores,
                                      "elapsed_seconds": {**stages, "total": time.monotonic() - started}}, checkpoint=True)
    print("Loading pinned embedding model on CUDA device zero", flush=True)
    begin = time.monotonic()
    tokenizer = AutoTokenizer.from_pretrained(profile["embedding_model"], revision=profile["embedding_revision"], padding_side="left", trust_remote_code=False, token=False)
    model = AutoModel.from_pretrained(profile["embedding_model"], revision=profile["embedding_revision"], torch_dtype=torch.float16,
                                     attn_implementation="sdpa", use_safetensors=True, trust_remote_code=False, token=False).to("cuda:0").eval()
    torch.cuda.synchronize()
    stages["embedding_load"] = time.monotonic() - begin
    def embed(text):
        inputs, count = tokenize(core, tokenizer, text, torch)
        with torch.inference_mode():
            hidden = model(**inputs, use_cache=False).last_hidden_state
            values = torch.nn.functional.normalize(hidden[:, -1, :].float(), p=2, dim=1)[0].cpu().tolist()
        return core.unit_vector(values), count
    try:
        for rep in job["representations"]:
            begin = time.monotonic()
            values, count = embed(rep["text"])
            torch.cuda.synchronize()
            stages["embedding_inference"] += time.monotonic() - begin
            documents.append({"id": rep["id"], "vector": values, "tokens": count})
            save_checkpoint("embedding_sources")
            if len(documents) % 16 == 0 or len(documents) == len(job["representations"]):
                print("Embedded sources " + str(len(documents)) + "/" + str(len(job["representations"])) + "; total seconds " + str(round(time.monotonic() - started, 3)), flush=True)
        print("Embedding original questions and declared components", flush=True)
        for row in job["query_rows"]:
            begin = time.monotonic()
            values, count = embed(core.embedding_query(row["query"]))
            torch.cuda.synchronize()
            stages["embedding_inference"] += time.monotonic() - begin
            queries.append({"question_id": row["question_id"], "component_id": row["component_id"], "vector": values, "tokens": count})
            save_checkpoint("embedding_queries")
    finally:
        del model, tokenizer
        gc.collect()
        torch.cuda.empty_cache()
    computed = core.compute(job, [row["vector"] for row in documents], [row["vector"] for row in queries])
    print("Validated distinct rerank pairs before reranker load: " + str(len(computed["pair_inputs"])), flush=True)
    save_checkpoint("pairs_validated")
    print("Loading pinned reranker after releasing embedding weights", flush=True)
    begin = time.monotonic()
    tokenizer = AutoTokenizer.from_pretrained(profile["reranker_model"], revision=profile["reranker_revision"], padding_side="left", trust_remote_code=False, token=False)
    model = AutoModelForCausalLM.from_pretrained(profile["reranker_model"], revision=profile["reranker_revision"], torch_dtype=torch.float16,
                                              attn_implementation="sdpa", use_safetensors=True, trust_remote_code=False, token=False).to("cuda:0").eval()
    torch.cuda.synchronize()
    stages["reranker_load"] = time.monotonic() - begin
    yes, no = tokenizer.convert_tokens_to_ids("yes"), tokenizer.convert_tokens_to_ids("no")
    core.require(type(yes) is int and type(no) is int and yes != no and yes >= 0 and no >= 0, "Reranker yes/no tokens are invalid")
    texts = {(row["question_id"], row["component_id"]): row["query"] for row in job["query_rows"]}
    representations = {row["id"]: row for row in job["representations"]}
    try:
        for pair in computed["pair_inputs"]:
            begin = time.monotonic()
            body = core.rerank_body(texts[(pair["question_id"], pair["component_id"])], representations[pair["representation_id"]]["text"])
            inputs, count = tokenize(core, tokenizer, body, torch, rerank=True)
            with torch.inference_mode():
                logits = model(**inputs, use_cache=False, logits_to_keep=1).logits[0, -1, :]
                value = torch.softmax(torch.stack([logits[no], logits[yes]]).float(), dim=0)[1].item()
            core.require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1, "Invalid reranker relevance")
            torch.cuda.synchronize()
            stages["reranker_inference"] += time.monotonic() - begin
            scores.append({**pair, "score": value, "tokens": count})
            save_checkpoint("reranking")
            if len(scores) % 25 == 0 or len(scores) == len(computed["pair_inputs"]):
                print("Reranked pairs " + str(len(scores)) + "/" + str(len(computed["pair_inputs"])) + "; total seconds " + str(round(time.monotonic() - started, 3)), flush=True)
    finally:
        del model, tokenizer
        gc.collect()
        torch.cuda.empty_cache()
    counts = [row["tokens"] for row in documents] + [row["tokens"] for row in queries] + [row["tokens"] for row in scores]
    runtime = {"backend": "kaggle-cuda-transformers", "device": "cuda:0", "gpu_name": audit["torch"]["gpu_name"],
               "device_count": audit["torch"]["device_count"], "total_memory_bytes": audit["torch"]["total_memory_bytes"],
               "cuda_version": audit["torch"]["cuda_version"], "dtype": "float16", "attention_implementation": "sdpa",
               "packages": {**profile["packages"], "torch": audit["torch"]["version"], "python": audit["python_version"]},
               "model_revisions": {"embedding": profile["embedding_revision"], "reranker": profile["reranker_revision"]},
               "elapsed_seconds": {**stages, "total": time.monotonic() - started}, "peak_vram_bytes": torch.cuda.max_memory_allocated(0),
               "max_input_tokens": max(counts), "truncated": False, "paid_inference_calls": 0}
    payload = {"schema_version": 1, "kind": "qwen-components-results-v1", "job_sha256": job_sha256,
               "profile_sha256": job["profile_sha256"], "execution_files": job["execution_files"],
               "document_embeddings": documents, "query_embeddings": queries, "score_rows": scores,
               "runtime": runtime, "environment_audit": audit}
    core.validate_results(job, payload, job_sha256)
    save_checkpoint("complete")
    _write(core, output_path, payload)
    report = {"status": "completed", "results_sha256": core.digest(payload), "distinct_rerank_pairs": len(scores), "runtime": runtime}
    print(core.canonical(report), flush=True)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("job", "job-sha256", "core", "environment-helper", "overlay", "installer-report", "output", "checkpoint", "environment-audit"):
        parser.add_argument("--" + option, required=True)
    parser.add_argument("--setup-seconds", type=float, default=0.0)
    args = parser.parse_args(argv)
    run_job(args.job, job_sha256=args.job_sha256, core_path=args.core, environment_helper_path=args.environment_helper,
            overlay_path=args.overlay, installer_report_path=args.installer_report, output_path=args.output,
            checkpoint_path=args.checkpoint, environment_audit_path=args.environment_audit, setup_seconds=args.setup_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
