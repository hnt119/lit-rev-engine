# Local reviewer workbench — Cycle 1

The workbench opens a saved component validation receipt, replays its four retrieval methods, and lets a reviewer inspect source text and record what each returned bundle supports. It runs locally using Python's standard library. It makes no inference calls and does not open or change the review database.

The implementation is separate from the frozen Qwen engine: `review_workbench.py` and `src/review_workbench/`. See [the evaluation report](workbench-cycle-1-evaluation.md) for tested behavior and [the workflow plans](../workflow/lit_review_markdown_pack/README.md) for priorities and later proposals.

## Try the offline public demo

Run from the repository root with Python 3.12 on macOS or Linux (the local storage lock uses `fcntl`). Pick an **absent, absolute directory**; the example fails safely if it already exists. Paths and their ancestors must be real directories, not symlinks. On macOS use `/private/tmp` rather than its `/tmp` symlink.

```bash
python3 review_workbench.py demo --output /private/tmp/lit-review-workbench-demo
python3 review_workbench.py serve \
  --receipt /private/tmp/lit-review-workbench-demo/validation.receipt.json \
  --receipt-sha256 3ba4da317d497cc021a90e9dcc9f88b3667bbdba85e7f94b633f7427dc7a9c80 \
  --assessments /private/tmp/lit-review-workbench-demo/assessments \
  --port 0
```

Open the printed `http://127.0.0.1:<port>/` address. Port `0` selects an available port; a fixed unused port also works. Stop the server with Ctrl+C. No API key, `.env`, packages, review database, downloaded model or GPU is required. The server binds only to `127.0.0.1` and uses same-origin requests and a per-session CSRF token. Use it as a local single-user tool; authenticated collaboration is future work.

`demo` checks the pinned committed archive and all its members, then copies only its original `validation.receipt.json`. It creates **zero assessment records**. These are eight historical questions over two public articles; they are exposed software regression material, not your microbiome review or a new blind quality study. Keep any experimental judgments clearly separate from actual review decisions. `/private/tmp` is temporary storage; choose a private persistent directory outside the Git checkout for a real project.

## Use the reviewer page

1. Read the question and its required components. Inspect the retained source text before comparing bundles where possible. Source links, block locators, document versions and hashes identify the saved material.
2. Choose an anonymous bundle. Each question has four saved methods, with up to five exact candidate passages per bundle. The page preserves original passage order and marks title/navigation candidates. “Inspect in source” navigates to the canonical block.
3. Rate each passage for the **whole question**, and optionally for each component. Leave unknown ratings unassessed. Use `0` for inapplicable/wrong population or time concept, `1` for background, `2` for partial support and `3` for direct support. Training dates receive `0` when the requested component is the clinical study period.
4. Select supporting passages, state bundle sufficiency and give a reason. Partial/insufficient judgments must identify missing components; sufficient requires support and no missing components. Contradiction is a separate flag. Declare source inspection explicitly; opening a block does not automatically assert it.
5. Enter your reviewer label and save. The page shows the saved record and history. To revise, load the current record and explicitly select its replacement in **Assessment history action**. The server appends a new record; it never overwrites the old one. Reloading the page retains saved judgments.

A bundle can be `not_assessed`, `sufficient`, `partial`, `insufficient` or `uncertain`. These statuses describe **the retrieved bundle**. Missing support may still exist elsewhere in the source. The workbench keeps source answerability `not_assessed`, live ledger state `not_checked`, review basis `single_human` and independent verification `NOT_RUN`.

The source view contains the **complete retained canonical text blocks** from the saved job, checked against their block digest. It does not render original PDF layout, load supplements, re-fetch original files or revalidate live source eligibility. Use the original source separately when a table, figure or formatting detail matters.

Methods, scores and selection reasons are hidden by default. Anonymous labels and ordering are deterministic; a knowledgeable reviewer may recognize results. Start with `--show-methods` only for diagnostic inspection; saved records then say `display_mode: revealed`. This mode is not a calibrated probability display. Repeated sources, reviewer familiarity and prior exposure remain limitations even with anonymous labels.

## Export descriptive evaluation

Use the same receipt, trusted hash and dedicated assessment directory:

```bash
python3 review_workbench.py evaluate \
  --receipt /private/tmp/lit-review-workbench-demo/validation.receipt.json \
  --receipt-sha256 3ba4da317d497cc021a90e9dcc9f88b3667bbdba85e7f94b633f7427dc7a9c80 \
  --assessments /private/tmp/lit-review-workbench-demo/assessments \
  --output /private/tmp/lit-review-workbench-demo/evaluation-01.json
```

The output must be a **new file**. It binds the report to the packet, receipt, source snapshot and all assessment record hashes. It retains history but aggregates only each reviewer's current record for a bundle. It reports per-method counts, observed passage/component grades, missing judgments, human-declared bundle support and assessment seconds with observed denominators. Precision uses whole-question grades ≥2; strict precision uses grade 3. P@5 requires exactly five displayed passages and all five rated. Null ratings are never scored as zero, and complete support is never inferred from an average.

These are **descriptive reviewer judgments**, not measured accuracy. No independent source-first gold, answerability calibration, nDCG, new confirmation, clinical validation, Rayyan comparison or independent human verification is supplied. The saved Kaggle runtime is labeled a shared historical batch; it is not a measured runtime for each method. Reviewer seconds describe the saved assessment session, not independently verified extraction time.

## Open your own saved receipt

Replace the demo path/hash with a receipt produced by the existing component workflow. Obtain the trusted **whole-file SHA-256** from its preserved handoff or independent capture. This differs from the receipt's internal canonical `payload_sha256`. Hashing a file you have just received measures its identity; it does not independently establish its provenance.

Use one dedicated assessment directory per exact receipt. A different receipt or source snapshot cannot silently reuse old judgments: bindings must match or loading fails. Retain earlier directories for history. The loader supports complete canonical source blocks in the current component receipt contract and reconstructs all four methods and diagnostics using frozen pure helpers. It does not import results into a ledger.

A script can also submit an assessment using `python3 review_workbench.py assess` with the same receipt/hash/assessment-directory arguments and `--input /absolute/path/draft.json`. The exact draft fields are:

```json
{
  "packet_id": "from-api-session",
  "bundle_id": "from-api-session",
  "reviewer": "reviewer_1",
  "status": "uncertain",
  "reason": "Example only: further source inspection needed.",
  "ratings": [],
  "supporting_passage_ids": [],
  "missing_components": [],
  "contradiction": false,
  "source_inspected": false,
  "supersedes": null,
  "review_seconds": null
}
```

If supplying a rating row, use `{"passage_id":"...","rating":null,"component_ratings":{"actual_component_id":null}}`, with every actual component represented; values must be null or integer 0–3. Component IDs, support references and packet/bundle IDs must exist in the loaded packet. A question without components uses `whole_question` when declaring missing support. The page handles these fields without manual JSON editing.

The saved record adds UUID, UTC time, immutable record hash, display mode, trusted receipt/job/results/profile/source/question/trace bindings and fixed trust labels. History uses explicit `supersedes` links for the same reviewer and bundle; duplicate, branching or stale replacements fail. Files are atomically created under a cross-process directory lock. The store is bounded to 10,000 records and 64 MiB of total record bytes; each record is at most 1 MiB, and a reason is at most 20,000 UTF-8 bytes. Hashes detect inconsistent edits, but they are not signatures or authenticated proof of who made a judgment. Reviewer labels and inspection declarations are self-reported.

## Public source attribution

The demo derives normalized canonical text from two CC BY 4.0 main articles:

- Abdulrahman M. Alfuraih et al., [Evaluating diagnostic accuracy and agreement of TI-RADS scoring in thyroid nodules](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0312121), PLOS ONE, 2024-10-11.
- William H. K. Schilling et al. and the COPCOV Collaborative Group, [Evaluation of hydroxychloroquine or chloroquine for the prevention of COVID-19 (COPCOV)](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1004428), PLOS Medicine, 2024-09-12.

Canonicalization normalizes whitespace and tables. The [source archive](../tests/fixtures/qwen_components_confirmation_sources/README.md) retains complete authorship, original license/copyright notices and provenance; linked supplements and patient-level data are excluded. License: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

## Next human pilot

The sole reviewer can use this page for a usability pilot after the microbiome review protocol, source rights and eligibility criteria are fixed. Save single-reviewed assessments and proposals; a second identifier or AI does not constitute an independent human review. Canonical finding creation and the existing distinct-reviewer verification remain separate ledger operations. The coordinator should review actual pilot errors and burden before deciding on retrieval repair, Rayyan staging or model expansion.
