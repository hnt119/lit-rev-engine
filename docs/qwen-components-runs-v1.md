# Component retrieval: first saved runs and coordinator decisions

This record tracks actual cloud evidence separately from the immutable [prospective source/software evaluation](qwen-components-evaluation.md), [selected interface](qwen-components-contract-v1.md) and first historical [failed Qwen run](qwen-kaggle-run-v2.md). The supplied [log diagnosis](qwen-kaggle-log-review.md) found shared-environment package conflicts, while both original models completed successfully. Neither the original quality grade nor its frozen inputs changed.

## Current stage

The component implementation and independent original-source acceptance are complete. The reviewed staged checkout passed **1,771 tests and 31 subtests in 153.76 seconds**, including 226 new independent cases. Five existing PyMuPDF SWIG warnings remain. The checkout excluded unrelated local experiments and `.env`; inference credentials were removed and model/network downloads disabled. All thirty-five historical frozen input files remain exact.

Worker/environment checks account for fifty of the new cases and use CPU fakes. The default installer virtual environment was created locally, while package installation, registry resolution, CUDA and model inference were simulated. Actual package compatibility, memory fit, runtime and retrieval quality require the first saved Kaggle run. No paid inference or Mac model weights are used.

The [development freeze](qwen-components-development-freeze-v1.json) pins seventy-two critical files before export, including the accepted blind confirmation source/truth bytes. Its file SHA-256 is `a70cfd4a4a1526e2e8da72f1b34ef1586ce6be430e9474892cf76a9b45d5ade0`. The first development upload job is prepared locally with trusted payload SHA-256 `4de843130af3727968e1a0f7bfd150c5743fcfb521d820a5c0fe0fd9c3bc3ce2`. It contains original passages and twenty-seven encoded whole/part requests. Its four-file zip and configured notebook are retained under `data/qwen-components-development-v1/`; this generated evaluation ledger contains no human pilot decisions.

The signed-in Kaggle editor showed the original environment, Internet enabled, T4×2 selected and the draft off. Submission then stopped because the Mac was locked. The coordinator requested manual unlock and performed no new GPU invocation, dataset upload or grading. The environment repair is software-tested; real cloud compatibility and quality are still unobserved for this new profile.

Development and confirmation each retain two separate licensed articles, six quantitative compound positives and two source-scoped nulls. Confirmation questions and answers remain withheld from the coordinator until development is reviewed and a method-selection receipt is recorded. The fixed twenty-candidate/five-display budget, 85% mean support floor, four complete-positive floor and nonregression against three matched comparators remain unchanged.

This stage has not established human-pilot readiness. The first validated development and confirmation results, including failures, will be preserved here and in portable artifacts. A quality failure cannot be relabelled by changing truth, thresholds or display limits.

## Reproduction

Use the [component workflow guide](qwen-components-guide.md) for a real project. The separate evaluation harness prepares only original source passages and reviewer requests for the cloud; gold and the review ledger remain local. Each run must retain its prospective freeze, original job hash, exact executable bindings, saved notebook version, output digest, installer/environment audit and first local grade. Saved numeric results reconstruct selection offline without GPU or ledger writes.

To reproduce preparation in a fresh directory:

```sh
.venv/bin/python tools/evaluate_qwen_components.py \
  --freeze docs/qwen-components-development-freeze-v1.json prepare \
  --output /absolute/path/to/new-development-batch
```

Each fresh preparation generates new project/document identities and its own trusted job digest. Upload only the returned four-file zip to a private dataset, import the returned notebook and set its actual `BUNDLE` directory. Save one finite GPU version and preserve its first output. Grade against this exact freeze with the trusted original job and printed saved-result digests; never substitute the original failed v2 job or loosen its quality gate.
