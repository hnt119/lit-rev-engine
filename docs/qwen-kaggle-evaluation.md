# Free GPU batch evaluation

The Kaggle export, runner, import and prospective grading workflow passes independent offline acceptance. Actual GPU memory fit, model retrieval quality and execution time are still unmeasured. This evidence permits preparing the frozen GPU batch; it does not qualify the Qwen workflow for the human review pilot.

## Independent evidence

Evaluation ran on 4 October 2026 using Python 3.12.7, without cloud inference, model downloads, CUDA execution or credentials. The focused command was:

```bash
.venv/bin/python -m pytest tests/test_qwen_batch.py tests/test_qwen_kaggle_pilot.py tests/test_qwen_cloud_acceptance.py tests/test_qwen_pilot_evaluation.py -q
```

Result: **305 passed in 11.59 seconds**. The new batch and Kaggle pilot tests account for 173 cases. The previous cloud and pilot acceptance contributes 132 cases and remains passing. All returned vectors and scores used in these tests are programmed synthetic fixtures. The two licensed medical source files and fixed eight-question truth are used to check preparation and metric integrity, without running either Qwen model.

The first full-suite run exposed a test-order assumption: the preparation test incorrectly required that no earlier test had imported Torch. The test now guards model-package imports during preparation itself, preserving the intended acceptance criterion. All **305 focused tests pass in 11.93 seconds with Torch already loaded**. This repair changes evaluation code only; the source truth, model execution code, profile and acceptance thresholds are unchanged. The original prospective test snapshot is preserved and the repaired tests require a new prospective freeze before GPU ranking.

| Boundary | Evidence |
| --- | --- |
| Source selection | Export includes only the selected current source versions and screening scope. The local ledger contents remain identical. An explicit all-attached export differs from the included-only export. Empty corpora fail. |
| Immutable inputs | Exports are deterministic for the same source, profile and queries. Trusted job and result hashes, strict JSON, exact envelope fields, model revision pins and profile hashes are checked. Duplicate JSON keys, nonfinite values, malformed schemas and Boolean aliases for numeric fields fail. |
| Returned numbers | Missing, extra, duplicate, reordered and foreign document/query/representation rows fail. Vectors must contain 2,560 finite numeric values and be unit length. Zero vectors, invalid token counts and relevance scores outside 0–1 fail. |
| Hybrid ranking | Evaluation independently recomputes cosine order, maximum span score per block, RRF with constant 60 and source-order ties. Both the notebook runner and local importer match the independent calculation. Local import rejects a returned candidate pool that differs from the calculation. |
| Exact grounding | Returned passages retain their complete canonical own blocks and locators. Long Unicode blocks are represented by exact bounded within-block spans; import returns the complete original block. Context never becomes an answer or a verified finding. |
| Stale work | Replacement sources, changed full-text eligibility, study links, canonical metadata and added eligible sources invalidate the saved job. No receipt is published on failure. |
| File protection | Export/import reject ledger, WAL and shared-memory paths, artifact aliases, existing source files, symlinks and receipt overwrites. The runner rejects output/checkpoint aliases and existing files before importing model packages. |
| Offline replay | Reimporting saved results with the original job hash and pinned result hash reproduces the same traces without credentials, network access or ledger events. Optional validation receipts are immutable. |
| Model execution contract | Fake tokenizers verify exact document and query encoding and complete reranker prefix/body/suffix tokenization. Overlong complete inputs fail before CUDA allocation. Notebook cells compile, and importing the runner or batch adapter on CPU does not import Torch or Transformers. Static review confirms sequential model loading, FP16, SDPA, disabled caches, last-token embedding pooling with float32 normalization, and yes/no logit scoring. |
| No paid fallback | A configured dummy DeepInfra key cannot enable legacy paid inference without the explicit opt-in flag. The CLI rejects the call before opening the ledger or loading credentials. Batch export/import and ordinary command delegation remain offline. |
| Prospective grading | Freeze tests reject previous rankings, missing code/source/truth pins, changed files, altered gates/profiles, Boolean aliases and path escapes. Preparation exports the job and runner without gold answers or the review ledger. Grading checks saved result hashes, prepared ledger integrity and replay, recomputes the lexical reference, keeps six positive questions and two nulls separate, and records an over-time batch as failed. |

Evaluation identified and verified repairs for the grading tool's elapsed-time field, strict canonical comparison of JSON profile/job data, and the notebook's prepared-input filename. These repairs changed plumbing only; the original medical truth and quality thresholds were preserved.

## Outstanding GPU gate

Run the prospective batch on an actual available Kaggle GPU, save its results and printed result hash, then grade locally using the original freeze and job hash. Required quality remains mean own-source support coverage at least 85%, at least four of six complete positive questions, and no regression against the freshly recomputed lexical reference. Exact anchors, scope, replay and read-only ledger behavior must hold; the recorded batch must finish within 1,800 seconds with zero paid inference calls. Null questions remain candidate-only and receive no positive-answer credit.

The saved runtime records model revisions, package versions, CUDA version, GPU identity, complete input token counts, stage times and peak Torch allocated GPU memory. These are recorded observations, not cryptographic hardware attestation. Peak Torch allocation excludes other GPU users, CUDA context overhead and total reserved/device memory. CPU fakes cannot establish that the 4B models fit the actual GPU, that downloads and dependencies work in that session, or that retrieval quality passes.

The notebook is a finite batch workflow. Its checkpoint preserves partial outputs but does not silently resume them or turn an incomplete run into a successful result. Account-specific GPU availability, quota, Internet access and the saved notebook execution must be verified in Kaggle. Until the actual GPU run passes, the human review pilot remains pending.
