# First actual Kaggle Qwen run: preserved failure

This archive preserves the first completed GPU ranking of the frozen Qwen3
Embedding-4B / Reranker-4B candidate on the two licensed source articles and eight
fixed questions. The result is **failed**: mean own-anchor support coverage was
**80.56%**, below the prospective **85%** gate. Four of six answerable questions
had complete support. The baseline covered 72.22%, with two complete positives.
An improvement over the baseline does not change the failed acceptance result.

The saved Kaggle script version was **355104707**. Its recorded Tesla T4 run used
one device (`cuda:0`) from a two-device allocation, with sequential FP16 models
and SDPA. Total recorded runtime was **395.076408088 seconds**, peak Torch GPU
allocation was **8,167,223,296 bytes**, the largest complete input was **726
tokens**, no input was truncated, and paid inference calls were **zero**. GPU
metadata is reported runtime evidence rather than cryptographic attestation.

## Exact retained artifacts

`artifacts.tar.xz` holds these five original JSON files, byte-for-byte:

| Archive member | Original local artifact |
| --- | --- |
| `job.json` | `data/qwen-kaggle-pilot-v2/kaggle-upload/job.json` |
| `results.json` | `data/qwen-kaggle-pilot-v2/run-evidence/results.json` |
| `preparation.json` | `data/qwen-kaggle-pilot-v2/preparation.json` |
| `result.json` | `data/qwen-kaggle-pilot-v2/result.json` |
| `validation.receipt.json` | `data/qwen-kaggle-pilot-v2/validation.receipt.json` |

The JSON originals total 12,895,976 bytes. A deterministic USTAR archive with
solid XZ compression reduces this to 2,033,240 bytes and preserves both the
original GPU results and the complete immutable validation receipt while
compressing their duplicated vectors together. The originals
remain untouched. `manifest.json` records every original file's byte count and
SHA-256, plus the compressed archive's digest.

Trusted canonical payload digests:

- Job: `ab6e06ca37d89f95800fc09100f2c8a41c595f3b76c0497fb9f2679850672a8f`
- GPU results: `0f5aa688f5382ddbfae3260bc1d832ba6d81aa2222a716feae07395887ea42be`
- Prospective freeze file: `04f0a961eb0f7d91626a72e93f68c5d4f8cc77f4ff0f78fbb72063219d878b62`

The source bytes and fixed gold live in the existing
[`qwen_pilot_sources`](../qwen_pilot_sources/README.md) and
[`qwen_pilot_gold`](../qwen_pilot_gold/README.md) archives. Their license and
attribution records are preserved there. Source-derived excerpts in this run
inherit those source terms. No review database, private browser or account
logs, screenshots, authentication data, or API credentials are included.

## Read-only offline verification

From the repository root:

```sh
python3 tests/fixtures/qwen_kaggle_run_v2/verify.py
```

The verifier uses only the Python standard library. It checks exact archived
bytes, strict JSON and envelope checksums, trusted job/result/freeze bindings,
frozen source and gold digests, full own anchors and separate scoring context.
It independently recomputes BM25 ordering, dense cosine ranking, RRF candidate
pools, maximum span rerank scores, final ranks, and the AND/OR support grade.
It checks the immutable receipt against the raw job/results and reproduces the
failed gate and recorded runtime. It performs no extraction, writes, network
requests, model loading, GPU inference or ledger operations.

A zero process exit code means **the failed run was verified**, not that Qwen
passed the pilot gate. The output deliberately retains `"status": "failed"`.
The verifier reads the frozen evidence files directly and does not import the
current retrieval implementation, so later implementation changes cannot
silently replace this historical ranking or grade.
