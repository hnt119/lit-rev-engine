# Qwen software release and first GPU decision

Software release decision on **4 October 2026, Asia/Singapore**: accept the optional Kaggle batch integration. The subsequent first GPU run completed successfully and passed resource/integrity checks, but **failed** the fixed 85% coverage gate at 80.6%, with 4/6 complete positives. Qwen remains experimental and the human review pilot remains gated. The [actual run decision](qwen-kaggle-run-v2.md) and [independent evaluation](qwen-kaggle-live-evaluation.md) preserve evidence separately from software tests.

## Evidence reviewed

The independently authored focused suite passed 305 checks: 173 batch/pilot cases and 132 earlier cloud/pilot cases. The evaluator then repaired one test-order assumption, verified all 305 cases with Torch preloaded, and documented the cause. The original test and harness snapshots, v1 freeze, prepared batch and repair receipt remain preserved. The [active v2 freeze](qwen-kaggle-freeze-v2.json) changes only the evaluator test and default freeze path; model, sources, gold, thresholds and production ranking are identical. Zero actual GPU rankings preceded either freeze.

The final isolated checkout passed **1,545 tests and 31 subtests in 92.14 seconds**, with five existing PyMuPDF SWIG warnings. That checkout contains reviewed release files and excludes unrelated local experiments and credentials. Model downloads were disabled and inference keys removed from the test environment. All nine licensed-source/gold checkers passed, including the two new Qwen archives. No medical model ranking was performed by these checks.

The two-source software-pilot bundle contains 102 canonical blocks, 102 exact scoring representations and eight questions. The [preparation receipt](qwen-kaggle-preparation-v2.json) records the earlier `prepared_not_ranked` state before any upload or GPU submission. The user then attached the prepared files to a private Kaggle notebook/dataset; saved version 355104707 ran the unchanged frozen models and job. A fresh prepare command reproduces the inputs with new project/document IDs and therefore a different job digest. The earlier paid-provider setup failed before any valid reply and remains [archived](qwen-setup-archive-v1.json). No further paid inference call occurred.

The original frozen ledger CLI, store, source parser and lexical retrieval modules remain byte-identical to the accepted foundation release. The `.env` credential file, unrelated retrieval experiments, generated data and foreign README section remain local and outside this commit. The optional entry-point adapter exposes batch export/import and blocks paid CLI calls without explicit opt-in.

## Next decision

The first saved run and local grade are complete. Batch time was 395.076 seconds, full notebook execution 439.6 seconds, peak Torch allocation 8,167,223,296 bytes, and the largest input 726 tokens with no truncation. Pinned revisions/packages and zero paid calls passed. Independent analysis located one missing Methods block outside the twenty-block pool and another ranked sixth inside it; both supplied necessary companion evidence for compound questions. Each null returned five candidates and recovered zero of two declared no-answer context quotes.

The next ticket is generic component-aware candidate generation and bounded own-block selection, followed by a fresh, prospectively frozen comparison. [The coordinator decision](qwen-kaggle-run-v2.md) records interfaces and acceptance. The [guide](qwen-cloud.md) explains reproduction. The original first failure, model profile, gold, thresholds and result remain unchanged.
