# Qwen software release and pending free GPU run

Release decision on **4 October 2026, Asia/Singapore**: accept the optional Kaggle batch software integration. Actual Qwen GPU retrieval quality, memory fit and runtime remain pending. The human review pilot cannot be declared Qwen-ready until that observed gate passes.

## Evidence reviewed

The independently authored focused suite passed 305 checks: 173 batch/pilot cases and 132 earlier cloud/pilot cases. The evaluator then repaired one test-order assumption, verified all 305 cases with Torch preloaded, and documented the cause. The original test and harness snapshots, v1 freeze, prepared batch and repair receipt remain preserved. The [active v2 freeze](qwen-kaggle-freeze-v2.json) changes only the evaluator test and default freeze path; model, sources, gold, thresholds and production ranking are identical. Zero actual GPU rankings preceded either freeze.

The final isolated checkout passed **1,545 tests and 31 subtests in 92.14 seconds**, with five existing PyMuPDF SWIG warnings. That checkout contains reviewed release files and excludes unrelated local experiments and credentials. Model downloads were disabled and inference keys removed from the test environment. All nine licensed-source/gold checkers passed, including the two new Qwen archives. No medical model ranking was performed by these checks.

The two-source software-pilot bundle contains 102 canonical blocks, 102 exact scoring representations and eight questions. Its local [preparation receipt](qwen-kaggle-preparation-v2.json) is `prepared_not_ranked`; no files were uploaded and no GPU job was submitted. A fresh prepare command reproduces the frozen inputs with new project/document IDs and therefore a different job digest. The earlier paid-provider setup failed before any valid reply and remains [archived](qwen-setup-archive-v1.json). No further paid inference call occurred.

The original frozen ledger CLI, store, source parser and lexical retrieval modules remain byte-identical to the accepted foundation release. The `.env` credential file, unrelated retrieval experiments, generated data and foreign README section remain local and outside this commit. The optional entry-point adapter exposes batch export/import and blocks paid CLI calls without explicit opt-in.

## Next decision

Import the [notebook](../notebooks/qwen_kaggle.ipynb) into a private Kaggle notebook, attach the prepared job/runner through a private dataset, verify free GPU allocation and run the batch. Save its output and runtime log, then perform the local grade using the original job hash and saved result hash. The [guide](qwen-cloud.md) gives the exact sequence; the [prospective milestone](qwen-kaggle-milestone.md) fixes quality and resource criteria.

Review the actual support coverage, complete positives, null-context behavior, tokenizer lengths, model/runtime revisions, elapsed time and peak Torch allocation before selecting another implementation ticket. If the 4B run fails, preserve its first result and diagnose that failure. A smaller model needs a separately frozen profile and comparison. No automatic paid fallback, threshold relaxation or human-pilot promotion follows a failed or missing run.
