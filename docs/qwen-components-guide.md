# Companion evidence with the new Qwen component workflow

This new experimental workflow targets questions that need evidence from separate sections, such as population/reference details in Methods and a quantitative comparison in Results. It keeps the review ledger on the Mac and runs the pinned Qwen 4B pair in a finite free Kaggle batch. The [selected contract](qwen-components-contract-v1.md) fixes the rules before implementation and new ranking; [independent evaluation](qwen-components-evaluation.md) will distinguish software checks from actual GPU quality.

The supplied first-run [log review](qwen-kaggle-log-review.md) identified shared-environment package conflicts. The new notebook installs four pinned retrieval packages into a temporary overlay and runs them in a fresh worker process. It checks required dependencies and CUDA before downloading weights. Kaggle's shared tools and CUDA Torch are retained. Existing Qwen jobs, the first failed result and the old [reproduction guide](qwen-cloud.md) remain available.

The [first actual component run](qwen-components-runs-v1.md) reached its trusted input but failed in Python 3.13's `ensurepip` while creating the installer. It produced no rankings or quality grade. A separately pinned bootstrap repair is being validated before another saved run. Use that run record to check the current cloud-validation status; the original notebook alone has not demonstrated compatibility with this Kaggle environment.

## Questions and original sources

Use the normal [project guide](getting-started.md) to import, screen and attach source versions first. Write an original question and two or three short component requests. Each component retains the subject and relevant comparison, but contains no expected answer. For example:

```json
[
  {
    "id": "q001",
    "query": "Which population and reference method were used, and what performance was reported?",
    "components": [
      {"id": "population", "query": "Which population and reference method were used in this report's own cohort?"},
      {"id": "performance", "query": "What performance estimates were reported for this report's own cohort?"}
    ]
  }
]
```

These are reviewer requests, not evidence assertions. The engine selects a candidate for each part before filling the remaining places. One passage selected for multiple parts occupies one display place. Parts do not certify completeness; review the original passages and their qualifiers. A question without components uses whole-question selection. The question file above is a top-level list; omit components or use an empty list for whole-question retrieval. A single component is rejected.

The current finite-batch limits are 25 questions, 100 encoded whole/part queries, 1,000 source representations and 4,000 rerank pairs including the whole-query comparator. Questions are bounded to 2,000 UTF-8 bytes; each source representation is at most 6,000 bytes. Long blocks retain exact within-block spans. Every model input is counted with its formatting and must fit 8,192 tokens without truncation. Oversized jobs stop explicitly; reduce the question batch when its score matrix exceeds the limit.

## Export and finite Kaggle execution

The new `review_components.py` entry point delegates ordinary ledger and historical Qwen commands to their existing implementations. New commands are `components-export` and `components-import`; they use the same saved database and project ID.

```sh
REVIEW_DB="/absolute/path/to/review.sqlite3"
REVIEW_PROJECT_ID="replace-with-actual-project-uuid"
python review_components.py --db "$REVIEW_DB" components-export "$REVIEW_PROJECT_ID" \
  --queries /absolute/path/to/component-questions.json \
  --job /absolute/path/to/new-component-job.json --scope included
```

Preserve the returned job payload digest locally. The command returns an absolute `files_to_upload` list; copy each listed file using its declared filename into a new upload folder. In particular, `src/review_components/core.py` becomes `component_core.py`. The four-file bundle contains `job.json`, `component_core.py`, `qwen_kaggle_environment.py` and `qwen_components_kaggle_runner.py`; the job binds the three executable files' exact bytes. Import `notebooks/qwen_components_kaggle.ipynb` into a private notebook and attach the four files through a private dataset. Set `BUNDLE` to its actual Kaggle input directory and `JOB_SHA256` to the locally retained payload digest. The review ledger and gold answers remain on the Mac.

Set the notebook's input paths and locally retained job digest. Select an available GPU and Internet access, keep the interactive draft off, and save **Save & Run All (Commit)** with GPU enabled. Inspect that saved version's preflight, progress and output. A missing dependency, mismatched helper hash, overlength input or oversized pair matrix stops explicitly; the worker does not truncate inputs, substitute another model or call a paid provider.

Download the saved result and its printed payload hash. Retain the checkpoint, installer/environment audit and log with the job. Model weights and the temporary package overlay stay in Kaggle scratch rather than saved output.

## Local import and review

```sh
python review_components.py --db "$REVIEW_DB" components-import "$REVIEW_PROJECT_ID" \
  --job /absolute/path/to/new-component-job.json \
  --job-sha256 REPLACE_WITH_LOCAL_JOB_PAYLOAD_DIGEST \
  --results /absolute/path/to/saved-component-results.json \
  --results-sha256 REPLACE_WITH_SAVED_RESULT_PAYLOAD_DIGEST \
  --receipt /absolute/path/to/new-component-validation-receipt.json
```

The importer validates the current source/eligibility/linkage snapshot, exact vectors and matrix identities, candidate pools and selection. It returns five unique own blocks at most, component selection reasons, grouped report references, and separate scoring-context anchors. Display order reflects component reservations followed by whole-question fill; it need not descend by whole-question score. Relevance probabilities are not clinical confidence.

Matched whole-query Qwen, whole-query lexical and component-aware lexical traces make the contribution of the new method inspectable. Pool diagnostics distinguish an absent companion from one displaced during final selection. Save the complete result/receipt for offline replay. Repeating a saved import uses no GPU or inference call and changes no ledger decisions.

Only reviewers enter findings, screening decisions, report/study associations and independent verification. A retrieved companion may still refer to a different population, timepoint, external study or supplementary file. Component labels alone do not resolve those relationships.

## Prospective pilot sequence

Prepare and grade development first. Preserve its first comparison and review any demonstrated defect. Select the method before inspecting confirmation questions, freeze confirmation inputs, then perform its first saved GPU comparison. Both splits contain six positives and two source-scoped nulls from different licensed papers. The fixed quality requirements include at least 85% own-support coverage, four complete positives, and nonregression against all three matched comparators at five own blocks. Operational integrity, exact source scope, read-only replay, zero paid calls and the 1,800-second batch ceiling are separate requirements.

Human-pilot readiness must follow an observed accepted confirmation result. Software checks, model-card benchmarks and rerunning already-inspected questions cannot establish that result.
