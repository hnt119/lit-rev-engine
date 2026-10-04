# First actual Kaggle Qwen run and coordinator decision

Observed on **4 October 2026, Asia/Singapore**. The private [saved notebook version **355104707**](https://www.kaggle.com/code/yixuanhuangethan/qwen-kaggle?scriptVersionId=355104707), named “Qwen4B frozen pilot v2”, completed once on GPU T4 ×2. Execution uses only `cuda:0` and loads the two pinned 4B models sequentially. The local first grade and independent evaluation both report **failed quality / passed engineering and integrity**. Qwen remains experimental; the protocol-defined human pilot remains gated.

## Fixed comparison

| Measure | Qwen hybrid | Lexical reference | Prospective requirement |
| --- | --- | --- | --- |
| Mean own-support coverage, six positives | 80.5556% | 72.2222% | At least 85%, and no regression |
| Complete positives at five blocks | 4/6 | 2/6 | At least 4/6, and no regression |
| Own/context anchors, source scope, read-only state and replay | Pass | Pass | Exact |
| Recorded batch wall time | 395.076 s | — | At most 1,800 s |
| Paid inference calls | 0 | — | 0 |

The quality improvement is 8.3333 percentage points and two additional complete positives. The coverage criterion still fails. The six positive coverages are 1, 1/2, 1, 1/3, 1, 1. Each of the two source-scoped nulls returns five candidates and recovers **0/2** declared no-answer context quotations, compared with lexical retrieval's **1/2** each. Nulls receive no positive-support credit. The engine does not infer answerability from relevance scores.

Kaggle reports successful full notebook execution in **439.6 seconds**; the batch's 395.076 seconds includes loading/downloads, inference and intermediate checkpoints, while excluding notebook package installation and final output serialization. Observed runtime: Tesla T4, two visible GPUs, Python 3.13.15, Torch 2.11.0+cu128, CUDA 12.8, FP16/SDPA. The four frozen package versions and both immutable model revisions match. Peak **Torch-allocated** memory on device zero was 8,167,223,296 bytes against 15,636,037,632 visible device bytes. This is not a total reserved/device-memory measurement. Maximum input was 726 tokens; no input was truncated. The unrelated preinstalled Gradio/Diffusers dependency warnings did not prevent this run.

## First-run integrity and preservation

The [v2 freeze](qwen-kaggle-freeze-v2.json), original source/gold and quality criteria were unchanged before and after this first GPU ranking. The printed saved-run digest was obtained from its execution log before the local grade. It matches the downloaded JSON's canonical payload. These hashes bind artifacts; runtime metadata and the saved page provide observed GPU provenance, not cryptographic hardware attestation.

| Artifact | SHA-256 |
| --- | --- |
| Active freeze file | `04f0a961eb0f7d91626a72e93f68c5d4f8cc77f4ff0f78fbb72063219d878b62` |
| Trusted job payload | `ab6e06ca37d89f95800fc09100f2c8a41c595f3b76c0497fb9f2679850672a8f` |
| Printed result payload | `0f5aa688f5382ddbfae3260bc1d832ba6d81aa2222a716feae07395887ea42be` |
| Original result JSON envelope file | `5e6a7e5b3da9dc541298a2b409bdf3cd200440be85b190a598c37b29f30c1874` |

The grade exited with status 2 because coverage failed, while preserving `result.json` and `validation.receipt.json`. The original prepared ledger, input bundle, saved result and UI observations remain local under `data/qwen-kaggle-pilot-v2/`. The [portable archive](../tests/fixtures/qwen_kaggle_run_v2/README.md) retains exact job, preparation, result and receipt bytes without the ledger, credentials or private UI observations. Its offline verifier and [independent evaluation](qwen-kaggle-live-evaluation.md) allow inspection without another model call. No second GPU run or model/parameter sweep followed this grade.

## Evidence review and next interface

The independent evaluator reconstructed lexical and dense rankings, RRF fusion, block relevance aggregation and final ordering from the recorded vectors/scores. It checked each support quotation against original XML and used read-only SQLite access for import/replay. Its result agrees with the first local grade.

Two compound requests remain incomplete. In the mammography question requesting acquisition period and inter-reader agreement, the acquisition Methods paragraph never entered the twenty-block pool, while the agreement Results paragraph ranked first. In the ultrasound question requesting cohort period, reference and performance, the Methods paragraph entered the pool but ranked sixth, while its Results paragraph ranked second. The original XML supplies no direct cross-reference from these outcome paragraphs to their missing Methods companions. Simple adjacent-paragraph or table-reference expansion would not address both failures.

The next architecture hypothesis is **explicit question components**: a reviewer supplies a bounded list of requested parts before retrieval; candidate generation combines component candidates within a global twenty-block pool, and final selection reserves bounded own-block evidence for components. A component is a request, not a gold answer. Each selected companion retains its own original quotation, locator and source identity. Scoring context never supplies own-support credit. No component label or model score declares an answer complete or a finding verified. The ledger and existing v1 batch import/replay remain compatible; an implementation with changed job/result shape gets a separately named profile and prospective freeze. The [retrieval proposal](qwen-kaggle-next-retrieval.md) details the source diagnosis and proposed score matrix.

The proposed starting contract is `question {id, query, components:[{id, query}]}`, with two or three reviewer-declared components, stable unique IDs, and a total five-block reviewer display budget. Questions without components retain the existing single-question route. The next design must specify component pool/score bindings, deterministic deduplication/ties, selection attribution and uncovered-component indicators before implementation. Five displayed blocks remains a prospective constraint; any extra reviewer expansion must be labeled and measured separately. This mechanism is untested, and the failed v2 set is now development evidence.

## Small next-cycle tickets

| Owner / ticket | Owned change | Acceptance |
| --- | --- | --- |
| Coordinator K4 | New versioned component interface and fixed selection rule | Freeze component/pool/budget/attribution rules before coding; preserve all old profiles/results, model revisions, own anchors and no-spend constraints. |
| Implementation KI4 | New component export/runner/import adapter and synthetic fixtures | Bounded component counts and pools, complete numeric identities, stable union/selection, exact separate own/context anchors, old replay compatibility, offline local operation and no ledger writes. No source-specific rules. |
| Retrieval KR4 | Fresh licensed, source-disjoint development and confirmation inputs | Original-source-first compound questions, exact sufficient AND/OR quotations and null context. Components fixed before ranking and contain no answer values. Confirmation sources/questions do not enter implementation tuning. |
| Evaluation KE4 | Independent operational checks and new prospective quality gate | Recompute component math and original-source support; preserve first comparison; at least 85% own coverage, at least two-thirds complete positives and nonregression on matched lexical reference; exact scope/anchors/read-only replay, zero paid calls and declared runtime/burden budget. Compare whole-query Qwen and component-aware lexical retrieval at the same final block budget to isolate the source of improvement. Explicitly report null behavior and partial positives. |

Run fresh confirmation only after operational checks, development review and prospective selection. A passed eight-question result would remain bounded retrieval evidence, requiring the separate human protocol pilot before broader deployment. The coordinator will review each cycle's independent results and choose the next step.
