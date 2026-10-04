# Run Qwen on a free Kaggle GPU

The recommended Qwen path is a finite **Kaggle batch notebook**. Your Mac keeps the review ledger and validates results; Kaggle runs Qwen3-Embedding-4B and Qwen3-Reranker-4B sequentially. No inference API key or paid calls are needed. The [first saved GPU run](qwen-kaggle-run-v2.md) completed successfully, but its 80.6% own-support coverage missed the fixed 85% quality gate. Qwen remains experimental and the human pilot remains gated. The existing offline ledger and lexical retrieval remain available.

## First run: the reproducible software pilot

The original v2 run and first failed grade are preserved. To reproduce preparation, use a new output directory; existing preparations and grades are immutable. Preparation performs no inference and downloads no model weights:

```sh
python tools/evaluate_qwen_kaggle.py prepare --output data/qwen-kaggle-reproduction
```

The command prints the absolute notebook path and the trusted `job_sha256`. Preserve that digest locally. In `data/qwen-kaggle-reproduction/kaggle-upload/`, `job.json` contains paper representations and questions; `qwen_kaggle_runner.py` contains the runtime; `qwen_kaggle.ipynb` is the notebook to import. New project IDs produce a new job digest. The review ledger, gold quotations and expected answers remain on your Mac. Repeating this already-inspected set is reproduction, not fresh confirmation of a changed retrieval method.

1. Sign in to Kaggle and import `notebooks/qwen_kaggle.ipynb` into a new notebook. Keep the notebook private.
2. Create a private Kaggle dataset containing the prepared `job.json` and `qwen_kaggle_runner.py`, then attach that dataset to the notebook.
3. Select an available GPU accelerator and enable Internet for model/package downloads. Check your account's remaining GPU allocation. The notebook targets a single GPU and loads the two models in sequence; hardware fit is checked by the actual run.
4. Set the dataset file paths and the trusted job digest in the notebook's configuration cell. Keep the interactive draft session off, choose **Save Version → Save & Run All (Commit)**, and confirm **Run with GPU for this session** in the version settings. Inspect that saved version's logs and output after it finishes. Preserve the run log and resulting `results.json` plus its printed payload digest. If you instead use an interactive session, stop it when finished.
5. Download the saved `results.json` to the Mac and grade it using the digest printed by that saved run:

```sh
python tools/evaluate_qwen_kaggle.py grade \
  --prepared data/qwen-kaggle-reproduction \
  --results /absolute/path/to/results.json \
  --results-sha256 REPLACE_WITH_SAVED_RUN_PAYLOAD_SHA256
```

`result.json` reports own-support coverage, complete positives, the lexical comparison, null-context recovery and runtime checks. A completed grade that fails a gate exits with status 2 and still preserves its result and validation receipt. The printed `results_sha256` binds the canonical payload; the complete JSON envelope has a separate file digest. Preserve both and retain failed results as well as passed results. [Independent live evaluation](qwen-kaggle-live-evaluation.md) records the first model run; [CPU evaluation](qwen-kaggle-evaluation.md) records integration checks.

## Use an existing review project

First complete the normal [project/import/screening steps](getting-started.md) and [source attachment](source-documents.md). Default `included` scope requires current title/abstract inclusion, retrieved full text and full-text inclusion. Explicit `all_attached` also includes attached pending/excluded reports and retains their states in traces. Qwen searches retained sources, rather than unattached citation abstracts.

Create a questions JSON file with a list such as `[{"id":"q001","query":"Your source-review question"}]`. Set actual paths and project IDs:

```sh
REVIEW_DB="/absolute/path/to/review.sqlite3"
REVIEW_PROJECT_ID="replace-with-actual-project-uuid"
python review.py --db "$REVIEW_DB" qwen-export "$REVIEW_PROJECT_ID" \
  --queries /absolute/path/to/questions.json \
  --job /absolute/path/to/new-job.json --scope included \
  --top-k 5 --candidate-k 20
```

Retain the returned `job_sha256` separately from the uploaded job. Run the same notebook with that job and runtime. Upload only selected source/question data in the private dataset. Then import the returned results locally:

```sh
python review.py --db "$REVIEW_DB" qwen-import "$REVIEW_PROJECT_ID" \
  --job /absolute/path/to/new-job.json \
  --job-sha256 REPLACE_WITH_LOCAL_EXPORT_DIGEST \
  --results /absolute/path/to/results.json \
  --results-sha256 REPLACE_WITH_SAVED_RUN_PAYLOAD_SHA256 \
  --receipt /absolute/path/to/new-validation-receipt.json
```

The importer makes no network calls and loads no model or key. It reconstructs the dense/lexical hybrid pools and ranks from recorded vectors/scores, checks the current source/eligibility/linkage manifest, and returns full original blocks with exact Unicode anchors. Scoring context stays separate from own evidence quotations. Repeating the import with the same trusted job and result digests and a new receipt path provides offline replay. These digests detect changed bytes/bindings, rather than proving the remote hardware's identity.

## Resource and reproducibility boundaries

The pinned 4B pair uses 2,560-dimensional normalized embeddings, separate query/document encoding, bounded source representations and a fixed hybrid pool. The notebook uses FP16 and SDPA, batch size one and one model at a time. It records tokenizer lengths and rejects overlength input instead of truncating it. Model caches belong in temporary scratch; only checkpoints/results belong in saved output. The [provider contract](kaggle-provider-contract.md) records official GPU options, session/output constraints and author model conventions. Account quota, queues and actual peak Torch allocation must be observed; a free notebook is a batch worker, not an always-on service.

A changed source, scope, eligibility, study association or profile invalidates an old job. Export a new job explicitly. Keep old jobs/results/receipts with the ledger snapshot they describe. Back up external artifacts separately; ordinary ledger exports do not include them. The current batch protocol does not reuse document vectors across different jobs; this is a later efficiency improvement after the first measured run.

Every result remains `candidate_passages`, `answerability: not_assessed` and `verification: human_review_required`. Inspect original sources, create manual findings/appraisals with exact quotations and obtain independent verification. Relevance scores are not clinical confidence or screening decisions.

## Historical paid adapter

The native DeepInfra adapter and its [provider contract](qwen-provider-contract.md) remain available for historical response replay. Paid `retrieve-qwen` and the old live evaluation CLI require explicit `--allow-paid-inference`; a configured `DEEPINFRA_API_KEY` alone cannot trigger a paid call. No further DeepInfra calls are being made. The earlier TLS/HTTP-402 setup attempts yielded no valid model replies or quality result; [their record](qwen-live-setup-v1.json) is preserved. The user-selected free workflow supersedes that setup plan before any ranking.
