# MVP v0.3 evaluation

Evaluation started **21 October 2026**, from the actual v0.2 implementation at
`404b002cd5feb7c847841135bdd383370e738c04`. This is an execution record for the
current local development cycle. Prior v0.2 results are historical context and
are not counted as fresh v0.3 evidence.

**Checkpoint 0 engineering acceptance: PASS** for the implemented readiness
audit and the real capped multi-paper case described below. Live discovery,
permitted source retention, explicit local model execution, original-source
inspection and actual browser reopening were exercised. Scientific relevance,
semantic-map quality, formal eligibility and human usefulness remain
**NOT_ASSESSED / NOT_RUN**. The comparison board is **NOT_IMPLEMENTED** and
optional extraction is **NOT_IMPLEMENTED**; this checkpoint is not the complete
v0.3 release.

## Baseline and preservation

The initial checkout was `codex/mvp-v0-2` at `404b002`. Local `main` and the
locally stored `origin/main` reference both resolved to
`a506ae05fc19c21a1d80beabc26bfc831582441d`. These local ref checks do not establish
the remote state without a separate network check. The coordinator owns the new
branch and publication decisions.

Initial unrelated local changes included mixed `.gitignore` and `README.md`
edits, research/data/benchmark/report directories, a lexical-retrieval experiment,
its tests, workflow assets, and untracked supplied milestone briefs. The
evaluation did not edit, stage or publish those files. Private source data,
operational contact details and credentials must remain local.

The frozen confirmation, development and Kaggle v2 manifests were read without
modification. Fresh size and SHA-256 checks matched **75 + 72 + 35 = 182 file
bindings**. This count is bindings across the three manifests, not necessarily
182 distinct paths.

## Fresh baseline checks

All commands below ran in `/Users/hunt/Desktop/lit-rev-engine`, except the
frontend commands, which ran in `apps/web`. Provider tests used injected
fixtures. Mapping tests use explicitly synthetic inputs; they do not establish
real model execution or semantic quality.

| Command | Fresh result | Limits |
|---|---|---|
| `/private/tmp/lre-mvp-venv/bin/python -m pytest tests/mvp -q` | **122 passed in 6.08 s** | No skips; offline fixtures and Streamlit AppTest |
| `.venv-map/bin/python -m pytest tests/mapping tests/web_api -q` | **109 passed in 24.22 s** | No skips; two existing dependency deprecation warnings |
| `.venv/bin/python -m pytest tests/test_project_retrieval.py tests/test_project_retrieval_acceptance.py tests/test_project_retrieval_v3_acceptance.py tests/test_review_exports.py tests/test_review_documents_acceptance.py -q` | **220 passed in 6.00 s** | No skips; five existing PyMuPDF/SWIG deprecation warnings |
| Bundled Node `--import tsx --test tests/*.test.ts tests/*.test.tsx` | **17 passed in 435.63 ms** | No skips; existing `react-test-renderer` deprecation notices |
| Bundled Node `node_modules/typescript/bin/tsc --noEmit` | **PASS**, exit 0 | Static types, not browser evidence |
| `NEXT_TELEMETRY_DISABLED=1` bundled Node `node_modules/next/dist/bin/next build` | **PASS**, exit 0 | Production compilation and static generation, not browser evidence |

The bundled Node executable was
`/Users/hunt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node`.
Its directory was prepended to `PATH` for frontend commands. Later checkpoint
results are recorded below when complete. Repeated
runs and subset totals are never added together.

## Ordered checkpoint gates

### Checkpoint 0: real-case readiness

Status: **ENGINEERING PASS**, with the real-case evidence and remaining human
gates recorded below. The baseline tests alone did not establish a live
multi-paper case. At the start of this cycle, fresh live PubMed execution, real
embeddings, real-case map reopening and human source assessments were **NOT_RUN**.

The fixture-backed research-case audit is implemented in `src/mvp/research_case.py`
and `scripts/mvp_research_case.py`. Independent tests live in
`tests/mvp/test_research_case_independent.py`; they use deliberately synthetic
records and never access providers or models. The latest independent command
was:

```sh
/private/tmp/lre-mvp-venv/bin/python -m pytest tests/mvp/test_research_case_independent.py -q
```

Result: **13 passed in 0.24 s**, no skips. The cases check exact original query,
question, sort and dates; preview cap and ordered selection; corrupted canonical
hash rejection; current versus historical preparation with original bibliography;
candidate versus reviewer-approved held-out denominators; missing outcomes;
Unicode block ranges; exclusion of abstract/source/error text, capabilities and
environment values; explicit live opt-in prerequisites; persisted-map reads and
wrong-map binding rejection; and exclusive private manifest writes with symlink
rejection. A fixed synthetic vector is software input, not a real embedding run.

Independent evaluation found that unavailable sources were initially reported
with a generic passing source-hash label. The implementation now separates
canonical-block integrity from retained original-byte verification, using
`NOT_RETAINED` or `NOT_APPLICABLE` where appropriate. These mechanical checks
remain separate from semantic inspection. Two intermediate full-suite attempts
had 147 passes and one evaluation-stub failure while the map audit interface
gained embedding/vector validation; the stub was updated to the stronger
interface. This was a test-harness mismatch, not evidence of a provider failure.

After that correction, the fresh full focused MVP command
`/private/tmp/lre-mvp-venv/bin/python -m pytest tests/mvp -q` passed **148 tests in
5.15 s**, no skips. This includes the original 122 cases, 13 implementation case
tests and 13 independent case tests. It supersedes the intermediate attempts;
the totals are not added to the baseline.

The audit records private metadata provenance. It is not an anonymization or
redistribution tool: query, question, source URL and license labels remain private
fields. SQLite reader initialization can create missing auxiliary schema or
adjust local permissions; no provider/model operation or research-snapshot
mutation is part of the audit.

The evaluator also executed the actual readiness CLI:

```sh
/private/tmp/lre-mvp-venv/bin/python scripts/mvp_research_case.py check --protocol examples/mvp/research_case_protocol.example.json --output /private/tmp/lre-v03-evaluator-readiness-20261021
```

It exited **0** and reported `LIVE_NOT_RUN`, `MODEL_NOT_RUN`, human usefulness
`NOT_RUN`, and publication `NOT_REVIEWED_DO_NOT_PUBLISH`. This validates the
explicit no-execution readiness path; it does not create a multi-paper research
case. The proposed workbook metadata replay was stopped before search, source
preparation or model execution and is not counted as a successful execution.

#### Real multi-paper case executed and independently inspected

The coordinator subsequently executed the approved workbook `U_A` query through
the actual browser and the existing single API process. The real capture is
separate from the stopped workbook metadata replay and the synthetic test
fixtures. Private protocols, capture/model receipts, source captures and browser
screenshots remain under `.mvp-web-state/research-cases/workbook-2026-10-21/`;
they are not public redistributable examples. No abstract or source quotation is
included in this report.

| Evidence | Observed result | Interpretation |
|---|---|---|
| Live PubMed capture | **514 reported / 30 fetched / 30 distinct**, no search errors | One capped exploratory preview, not complete discovery |
| Request/protocol/saved-search binding | Exact UTF-8 query hash, question, sort and dates match | No query broadening or silent query substitution found |
| Provider warnings | One application exploratory-preview caveat; no PubMed warning-list entries | Query translation is retained, not treated as a relevance judgment |
| Observed capture time | **44.909339 s upper bound** | Includes UI/orchestration delay; not isolated provider latency |
| Explicit source selection | **7 retained reports: 2 full text / 5 abstract / 0 no-text** | No substitution or manufactured unavailable outcome |
| Five abstract fallbacks | All retain `permission_unresolved`; one explicit source error of that code | Reuse permission remains distinct from usable abstract text |
| Real local map | **30 embeddings / 30 points / 0 exclusions**, UMAP cosine | Coordinator executed the existing CPU BGE adapter explicitly |
| Map job interval | **18.932202 s**, attempt 1 succeeded | Queue, weight loading, embeddings, UMAP and persistence combined |
| Retained token manifests | **11,818 tokens / 36 windows**, six multi-window papers; max 510 content tokens | All recorded window weights sum to each paper's token count |
| Existing passage retrieval | **5 displayed / 87 matched / 157 indexed**, drawn from **2 of 7 reports** | Supports the need for separate per-paper board retrieval; existing profile remains unchanged |

The pinned real model is `BAAI/bge-small-en-v1.5` at revision
`5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`; all retained vectors have 384 dimensions.
The coordinator's receipt records CPU execution, existing local weights, offline
runtime flags and observed weight loading. There were zero paid inference calls.
Model network-attempt instrumentation was **NOT_RUN**; offline/local-files-only
configuration must not be described as a measured zero-network-attempt result.
The map does not establish semantic layout quality or evidence support.

The evaluator independently inspected the saved records using SQLite `mode=ro`
and `PRAGMA query_only=ON`, without initializing/migrating the databases or calling
providers/models. These checks passed:

- Ordered saved PMIDs match all 30 bibliography records; the exact executed
  query hash is `b4b3354d6767b775f7f83b385217efc5c1372f2d0108909a66d6c6d9b34229d9`.
- Original search, preparation and map bindings reconcile. The map was read twice
  without refitting; profile/input/vector/coordinate digests validate. Its
  coordinate hash remains
  `3c9b7e9479e8c8740864ec320c4cfc36801cd4a1a776afb9148cc50001690f25`.
- All seven source identities match the original bibliography. Both full-text
  byte hashes and fresh JATS reparsing match the retained canonical blocks. All
  five abstract fallbacks exactly match the original saved PubMed abstracts.
- All **157 canonical blocks** reconcile. All **five retrieved passage anchors**
  reconstruct the exact original half-open Unicode code-point quotation, source
  hash and original bibliography. No private quotation was printed or published.
- The workspace snapshot did not change during independent inspection. There
  are zero human assessments; semantic support and formal eligibility remain
  **NOT_ASSESSED / NOT_RUN**.

The independent full-case command was:

```sh
/private/tmp/lre-web-venv/bin/python /private/tmp/lre-v03-independent-case-audit.py
```

It exited **0** and wrote
`independent-full-case-audit-01/manifest.json` inside the private case directory.
The earlier search/map-only independent audit is separately retained as
`independent-search-map-audit/manifest.json`. These receipts label evaluator
provider/model execution **NOT_RUN**; the coordinator's actual browser/process
receipts supply the live/model execution evidence. Saved-artifact validation
alone is not independent proof that a particular model was executed.

#### Final browser acceptance and regressions fixed

The coordinator performed the actual browser walkthrough in the persistent local
session, against the rebuilt production app. The private receipt is
`browser-acceptance.json`; `browser-source-check.png` and
`browser-map-check.png` remain private because they show research content. The
evaluator reviewed that receipt and independently reconciled its persisted
research counts, ordered selection draft, map/job counts and coordinate digest
using read-only SQLite. The evaluator did not perform a second independent
browser walkthrough.

Two real pointer failures were retained in the acceptance history and corrected:

1. Rapid native pointer selections initially lost changes because handlers used
   a stale rendered selection. Functional draft updates now preserve all choices
   in a batch, including deselection and the existing ten-paper limit.
2. Pointer selection still failed when hover/selected borders shifted controls
   horizontally and long author metadata expanded the map area vertically.
   Reserved paper-row border geometry and a bounded scrollable metadata region
   removed that movement. Complete metadata remains in a named keyboard-focusable
   region rather than being truncated or lost when focus moves away from a point.

The final actual browser checks passed:

- Rapid pointer deselection **7 → 0** and reselection **0 → 7** registered every
  choice; keyboard selection also worked. The original ordered seven-paper
  selection was restored exactly in its durable draft.
- Hover-region height stayed **112 px before and after** highlighting. The
  actual long metadata had **144 px scroll height**, and its region was keyboard
  focusable with `tabIndex=0`.
- Filtering `Japanese` displayed **four papers and four points**; clearing it
  returned **30 papers and 30 points**. Filter/navigation did not build or refit.
- After process restart and page reload, the same workspace, saved map and source
  preparation reopened. There remained **one map job and one map**, with the
  unchanged coordinate digest above.
- Passage 2 opened the original PMID/source and exact Unicode range **[0, 473)**.
  This was mechanical source inspection, not a human semantic judgment.

Independent post-browser reconciliation confirmed **one search, one preparation,
one evidence run and zero assessments**; no additional provider capture or map
job was created by those checks. The prepared protocol and durable selection
draft contain the same exact ordered report IDs.

After the last configuration-scope test and UI fixes, the coordinator reported a
fresh `/private/tmp/lre-mvp-venv/bin/python -m pytest tests/mvp -q` run of **148
passed in 5.40 s**, no skips. The frontend implementation agent's final locked
runtime commands `pnpm test`, `pnpm typecheck` and
`NEXT_TELEMETRY_DISABLED=1 pnpm build` produced **20 passed / PASS / PASS**. The
three added frontend cases exercise rapid selection/limit behavior and retained
keyboard-accessible complete hover metadata. These component checks complement,
and do not replace, the actual browser geometry checks above. Root also reported
`git diff --check` passing and all **145 preexisting preservation hashes** still
matching. These final results supersede their earlier subset runs; totals are
not added together.

No scientific relevance, population eligibility, map usefulness or human pilot
success is inferred from these mechanical checks. Human-supported comparison
cells, board-specific retrieval, revision-safe board review and board exports
remain the next implementation checkpoint.

Independent acceptance requires:

1. An explicit exact query and protocol approval state, the existing 30/50 cap,
   sort/date settings, execution time, provider translation, ordered identifiers,
   reported count, fetched count and errors. A capped preview remains an
   exploratory preview even if all reported matches fit.
2. An explicit 5–10-paper selection where available, preserving actual full-text,
   abstract-only and unavailable outcomes and reasons. Missing outcomes must not
   be silently replaced with more convenient papers. Citation identity and exact
   canonical ranges must be checked independently from semantic relevance.
3. A saved-map binding to the exact metadata snapshot, pinned embedding profile,
   exclusions and coordinate digest. Reopening/filtering must read the saved
   artifact without refitting. Model execution must be labeled separately from
   synthetic vector tests, and runtime alone does not establish usefulness.
4. A small reviewer-defined known-paper set with approval and provenance. Report
   each recovered/not-recovered PMID, denominator and cap. Recovery within the
   preview is **not recall of all relevant literature**. A candidate set inferred
   by software is not a reviewer-approved relevance gold set.
5. Private local capture must be separate from public fixtures. A metadata-only
   report must not leak abstracts, quotations, source text, capabilities, email
   addresses or credentials. Per-field rights/privacy review is required before
   distributing a real example.
6. Missing live prerequisites must produce **LIVE_NOT_RUN**. The fixture-backed
   readiness path remains useful and must not fabricate provider/model success.
   Opening, filtering or auditing saved data must not initiate providers or model
   computation.

### Checkpoint 1: source-linked comparison board

Status: **NOT_IMPLEMENTED / NOT_RUN**. Evaluation will distinguish source
availability, reference integrity, semantic judgment, inspected scope and
freshness. Minimum independent cases are wrong-paper/hash/Unicode anchors;
quoted-but-non-supporting text; abstract-only and empty sources; duplicate
reports; question/field/source revision changes; concurrent human edits; draft
retention after rejected saves; historical citation reconstruction; credential
isolation; and current/history export safety. Existing global top-five passage
retrieval and audit exports must retain their current contracts.

### Checkpoint 2: optional structured extraction

Status: **NOT_IMPLEMENTED / NOT_RUN; gated on the working manual board**. No model configuration
must leave manual review functional. Later acceptance requires malformed output,
wrong IDs/quotes, prompt injection, explicit call/token/context/runtime limits,
incomplete inspection, stale publication, cancellation and no paid fallback.
Neither model proposals nor exact quotation checks constitute human semantic
verification.

## Human usefulness

Participant recruitment, reviewer relevance labels, comparative task timing,
supported-field adjudication and return use are **NOT_RUN**. Software test passes
must not be relabeled as scientific validation, study independence, comprehensive
discovery, research usefulness or competitive superiority.
