# Component retrieval: prospective independent evaluation

This is the immutable source and software evaluation record selected before the first component-profile GPU ranking on 4 October 2026. Actual saved runs, operational errors, comparisons and coordinator decisions belong in [the separate run record](qwen-components-runs-v1.md). Updating that record must not change this document or any frozen implementation, source or truth byte.

The [selected contract](qwen-components-contract-v1.md) is `kaggle-cuda-qwen4b-components-v1`: two or three reviewer-supplied request components, exact first-two shared pool reservations, one shared candidate selection per component, a global twenty-block pool and five unique displayed own blocks. A zero-component request retains the historical whole-query rule. All output is an unverified candidate requiring human review. Component attribution is a selection reason; it is not a support-completeness or source-answerability judgment.

The [preserved first Qwen run](qwen-kaggle-live-evaluation.md) remains a failure: 80.5556% own-support coverage against the unchanged 85% floor, with four of six complete positives. Its thirty-five frozen input files, original XML/gold, saved vectors/scores and actual first grade remain unchanged. The new profile is a prospective experiment with fresh articles and queries.

## Independent original-source acceptance

Both splits were independently reviewed from original publisher XML before any new lexical or model ranking. Each split contains two CC BY 4.0 main articles, six quantitative positives and two article-scoped nulls. The four article DOIs are disjoint from one another and from the previous fixture DOI inventories. Original designs, populations and settings were inspected; no reused primary cohort was observed in these main articles. This is an archive-level check rather than a complete literature-wide cohort-linkage claim.

The independent evaluator reconstructed all canonical blocks directly from XML elements, section ancestry, tables and original text before checking the saved inventories and reconciling the accepted parser. The resulting own-path, locator, Unicode quotation, half-open code-point bounds and block/source digests agree with 126 development blocks and 100 confirmation blocks. Original source inconsistencies remain in the archive; numerical anomalies are preserved rather than corrected.

Development has nine sufficient OR alternatives comprising twenty own support spans and four context spans. Confirmation has ten alternatives comprising twenty-four own spans and four context spans. Five development positives and six confirmation positives require distinct-block AND support. Four development positives and five confirmation positives necessarily require both body Methods and body Results blocks across **every** sufficient alternative. Abstract-based alternatives do not falsely inflate the body Methods/Results floor.

Source review identified and corrected two missing sufficient alternatives before freezing or ranking. One development component also had an extra restriction absent from its whole request; it was aligned with the original reviewer request. Explicit analysis qualifiers were retained when accepting alternate numerical passages. Confirmation question text, expected values and individual support paths were withheld from the coordinator during this acceptance stage.

Each acquisition verifier passed thirteen source-tamper negatives and a preserved historical-runtime positive. Each truth verifier passed twenty-eight gold-tamper negatives and a historical-runtime positive. The evaluator additionally checked sufficient component/qualifier coverage, alternate passages, article-scoped no-answer rationales and separation of context from support. The accepted gold-manifest hashes are:

| Split | Accepted gold manifest SHA-256 |
| --- | --- |
| Development | `db5e9fb6db983691658312eeeb4e7f9fce119ce38f60b0bc5071700633f99157` |
| Confirmation | `598f39d70b91dcd796ad5821d4b43405d813677229525e9d7ff72b0635c8719e` |

This acceptance establishes source fidelity and a prospectively reviewable truth set. It does not establish model retrieval quality or clinical validity.

## Software acceptance and evidence boundaries

[Independent core checks](../tests/test_qwen_components.py) recompute BM25/context scores, max-span cosine, per-query hybrid RRF and global RRF without using the implementation's ranking helpers. They exercise exact shared reservation sets without replacement, shared selected-block reuse, stable ties, whole-score versus component display order, complete matrix identities, comparator pair reuse, multi-span Unicode bounds, the actual distinct-pair ceiling and unchanged-result replay. Exact historical BM25 scores and zero-component pool semantics are compared with the frozen implementation.

Malformed, duplicate, reordered, extra, missing, nonfinite, nonunit or out-of-range vector/score rows are rejected. Job/profile/question/source/helper identities are bound to trusted hashes. Source eligibility/version changes and existing ledger transactions reject import. Ledger, WAL/SHM, job, result and already-written receipt paths are protected. Logical ledger fingerprints remain unchanged through export, import and replay. Package/runtime audit tests reject contradictory metadata, incomplete active dependency rows and paths escaping the declared overlay.

[Environment checks](../tests/test_qwen_components_environment.py) and [worker checks](../tests/test_qwen_components_worker.py) use CPU dependency/CUDA fakes. They verify the reviewed upload bindings, isolated installer commands, complete active wheel requirements, imported library locations, base Torch separation and CUDA preflight ordering. Worker checks cover author prompt/token formatting, complete non-truncated lengths, last-token unit pooling, sequential model release, yes/no probabilities, distinct-pair validation before reranker loading and immutable artifacts/checkpoints. These fakes establish plumbing, not the availability or quality of a real Kaggle GPU environment.

The environment repair uses a disposable installer virtual environment and a private no-dependencies overlay for four exact Hugging Face packages. A fresh base-Python isolated worker uses that overlay and Kaggle's existing CUDA Torch/transitive dependencies. This is scoped package separation, not complete transitive isolation. Missing or incompatible active dependencies fail before model weights; global package upgrades or warning suppression are not a repair. Recorded installation/runtime metadata is not cryptographic execution attestation.

## Prospective preparation and grading

[The local harness](../tools/evaluate_qwen_components.py) requires the selected contract/profile/gates, complete critical code/test/source/truth pins, accepted pre-ranking source review and the exact historical first-failure freeze. It reconstructs original truth before creating a new evaluation ledger. The four-file zip contains `job.json`, the shared component core, the environment helper and the standalone runner. Its separately configured notebook embeds the local job hash; only the private dataset `BUNDLE` path remains user-specific. Gold answers, support/context anchors, source-truth inventories, review ledgers and credentials are excluded from the upload.

The development freeze precedes the first real ranking. Confirmation additionally requires a method-selection receipt made after review of the preserved first development grade and before the coordinator reads confirmation QA or performs confirmation ranking. That receipt binds the exact development freeze and a portable copy of the first actual grade, factual status, trusted job/result digests and unchanged profile. It records zero prior confirmation rankings and coordinator blindness. Confirmation preparation validates those bindings before parsing its questions.

[Harness attack checks](../tests/test_qwen_components_evaluation.py) use separate authored synthetic XML/questions, so they do not rank either real medical split before its prospective freeze. They cover altered freezes, code/source/truth paths, accepted review state, method-selection receipts, upload bytes/notebook compilation, preparation/current-ledger bindings, saved-result hashes, candidate/comparator/pool corruption, exact anchors and immutable first grades. Preparing a batch loads no model library or cloud credential and makes no inference request.

Grading imports complete numeric results, recomputes the target and matched whole-query Qwen, whole-query lexical and component-aware lexical comparisons, validates exact eligible own blocks and replays unchanged results. It uses sufficient OR-of-AND quotation spans from displayed own passages only. Scoring context and component labels receive no support credit. Each null reports returned candidates, own no-answer context and other-article candidates; no-answer context receives no positive-support or abstention credit. Pool support and subsequent display loss are reported separately. Other-article candidate counts do not automatically establish semantic irrelevance.

The first validated pass or fail is saved once. A changed result, larger list or relaxed threshold cannot relabel that grade. Invalid bindings fail before publishing a receipt. Operational failures without a complete result remain preserved logs/checkpoints rather than a fabricated quality grade.

## Fixed acceptance criteria

For each frozen split, the harness records these unchanged checks:

- Mean own-support coverage at least 85% across six positives, with at least four complete positives.
- Coverage and complete-positive count at least as high as **each** matched whole-query lexical, whole-query Qwen and component-aware lexical comparison.
- Exact original anchors/source scope, immutable saved-result replay and unchanged review ledger.
- At most twenty target own blocks in a pool and five unique own blocks displayed per question.
- At most 4,000 actual distinct rerank representation/query pairs, full inputs within 8,192 tokens, zero truncation and zero paid inference calls.
- Measured batch time at most 1,800 seconds, including model downloads/loading, inference and checkpoint work. Setup and notebook/queue timing are reported separately; peak Torch allocation is not total device memory use.

Only accepted fresh actual GPU evidence can permit the requested protocol-defined human review pilot. CPU acceptance alone, a relevant first hit, or an attribution label cannot open that gate. A changed method after development requires new prospective pins and a fresh ungraded confirmation set.
