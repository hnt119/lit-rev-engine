# Protocol pilot — disclosed software usability evaluation

Baseline: `cb98e3ef843982ebe0cfb65631d8f923a1a4007b`. Evaluation date:
2026-10-24. This report records the pre-commit evaluation of the Track B implementation,
separate from the frozen local-preview `.2` release. It is not a new release
qualification, a completed systematic review or a retrieval-accuracy benchmark.

## Sample and provenance

The one disclosed 30-record sample contains **all 30 approved public sources in
the existing manifest order** under `examples/mvp/offline_microbiome_30_v1`.
No embedding, model score, clinical judgment or benchmark result selected them.
The original Europe PMC query reported 194 matches and returned 100 metadata
records; rights and identity checks retained 30. This evaluates complete intake
of the supplied 30-record set, **not a complete query capture**. Generic intake
cannot assert the dedicated complete-capture flag.

Two of those same records were explicitly reimported to test original
occurrence retention and deduplication. The sample therefore has 32 imported
occurrences, 2 duplicate occurrences and 30 canonical records. The duplicate
input's exact whitespace-preserving UTF-8 bytes were retained before deleting
only that evaluator-created original file. No original research input or user
database was selected or removed.

Two permitted public JATS documents and one explicitly abstract-only document
were attached. The abstract-only case is a deliberate restriction of available
coverage: its full text exists in the public bundle. It does not establish that
full text is absent, unobtainable or negative for any question. Source checks
retain the original hashes, canonical blocks, permission and attribution.

## What was actually run

`tools/evaluate_review_pilot.py --exercise-public-sample NEW_STATE_DIRECTORY`
used the actual FastAPI adapter, ReviewStore ledger, existing collection/source
preparation services and comparison board through an in-process HTTP test
client. Its data directory was new and isolated. External socket creation was
denied; new maps, search planning and AI proposals were disabled. Provider/model
calls were zero. No cookie was transferred to a browser or another user.

Every screening action used an explicitly scripted software-QA label and
reason. Actions cover state transitions, including 14 exclusion branches; they
are **not real eligibility findings about the papers**. Actual human screening,
the proposed sole reviewer's usefulness assessment, independent/dual review and
reviewer identity authentication are **NOT_RUN / not established**. Local
session ownership and origin/CSRF protection remain implemented and tested.

The final sample run used 113 HTTP requests in **3.957 seconds**. This is one
local software run, not a reviewer time estimate or performance benchmark.

| Sample stage | Observed time | Requests through stage |
| --- | ---: | ---: |
| Protocol revisions and intake of supplied subset | 0.405 s | 11 |
| Scripted screening history and source/status actions | 2.340 s | 96 |
| Explicit provisional handoff and exact inspection | 0.510 s | 110 |
| Retained export, original-input removal and adapter reopening | 0.246 s | 113 |

The raw final report is retained locally at
`.mvp-web-state/ui-checks/protocol-pilot-2026-10-24/independent-sample-final-v2.json`.
The fresh QA state and export remain in the corresponding new
`independent-sample-final-v2` directory. They are not release/package inputs.

## Independently reconciled results

The evaluator folds original ordered decisions, latest decisions per declared
label, later adjudications and retrieval events. It derives identified counts
from occurrences, not search-provider totals, and never calls
`ReviewStore.counts()` to obtain its expected answers. It checks projected states
and reported counts against this independent event fold.

| Partition | Count |
| --- | ---: |
| Imported occurrences / duplicates / unique records | 32 / 2 / 30 |
| Scripted title/abstract screened / pending | 30 / 0 |
| Title/abstract excluded / advanced / unresolved | 14 / 6 / 10 |
| Advanced reports awaiting request / sought | 2 / 4 |
| Sought reports retrieved / not retrieved / awaiting retrieval | 2 / 1 / 1 |
| Retrieved reports assessed / awaiting assessment | 2 / 0 |
| Assessed reports included / excluded / unresolved | 1 / 0 / 1 |
| Independent studies | **null — explicit linkage not completed** |

There were 34 original screening events, 4 retrieval/status events and 3 source
attachments, bound by 41 protocol/event records. Two protocol revisions were
retained with unresolved choices explicit. No report ID was counted as an
independent study ID.

One explicit provisional handoff created a **3-paper × 3-field board** over the
exact selected source versions. It did not change formal screening counts or
decisions. Board cells remained unsubmitted and unassessed. Exact inspection
matched the first three canonical blocks from each bound ledger source through
the existing comparison-source endpoint. Opening a source did not claim human
inspection, attach support or submit a value.

The audit verified 35 retained intake assets, 3 original source files and their
canonical block hashes, protocol revision hashes, event bindings and the
source-bound comparison JSON/CSV embedded in the pilot ZIP. Export member bytes
were identical after removing the evaluator-created duplicate input and
recreating the adapter with the same private software test session. The final
QA ZIP SHA-256 is
`865c1ece1b8d182f97068efc9bca2917120f22ca17c62777a94408ed8042ce09`.
Fresh ledgers have different UUIDs/timestamps; this hash is not an across-ledger
determinism or publisher-signature claim.

## Independent acceptance tests

Final command:

```sh
.venv-map/bin/python -m pytest tests/web_api/test_review_pilot_independent.py -q
```

Result: **9 passed, 0 failed, 0 skipped, 2 inherited Starlette deprecation
warnings in 9.94 seconds**. The test interpreter was reused; all data fixtures
were new temporary state. These checks are separate from broader regression
suites and the root coordinator's actual production-browser walkthrough.

Coverage includes:

- Existing session, origin and CSRF rules; valid known IDs do not authorize
  another session; deleted workspaces become inaccessible.
- Append-only protocol revisions, exact retries, stale protocol/library writes,
  explicit unresolved choices and blocked real-purpose screening before readiness.
- A separate 40-record synthetic library with 2 duplicate occurrences, paging,
  exact original intake bytes and unchanged exports after adapter reopening.
  This tests a library larger than a board; it is not another human sample.
- The existing five-invented-record complete PubMed fixture, source-response
  retention after its own original directory is removed, and atomic rejection
  of missing batches/changed membership. This is an offline verifier test, not
  a new live PubMed capture or part of the 30-paper sample.
- Reasons and original decision history, full-text/source prerequisites,
  unsupported reopening/status downgrade and explicit uncertain states.
- Exact permitted JATS and abstract-only handoff, wrong-paper and wrong-hash
  rejection, superseded-source rejection, and unchanged formal decisions.
- Protocol changes preserve historical counts/events but mark active old votes
  as needing review. New handoffs fail until explicit current-protocol
  title/abstract and full-text re-review; existing boards remain historical.
- Completed exact handoff retries replay the original immutable receipt after
  source replacement; changed inputs under the same ID fail. A new request
  using the old source still fails.
- An injected failure after preparation publication records its partial IDs;
  an exact retry reuses that preparation and creates one board. This is a
  caught software interruption, not an actual machine/process crash test.
- Independent arithmetic covers every unresolved partition and explicit study
  linkage. Deliberately altered counts, projected states or source bytes are
  detected by the independent audit.

The standalone audit can be repeated without provider/model access:

```sh
.venv-map/bin/python tools/evaluate_review_pilot.py \
  --audit-export RETAINED_PILOT_EXPORT.zip --report NEW_AUDIT_REPORT.json
```

Keep private exports local. The audit report records arithmetic/integrity, not
scientific support or methodological completeness.

## Problems observed and corrected during this cycle

The first public-example intake attempt exposed a real adapter defect: its
internal `SearchRequest` omitted the existing required `request_id` and raised
an uncaught validation error. The adapter was corrected and the same path now
passes the independent tests and final sample.

Independent code review also found completed handoff retries were checked only
after current sources were revalidated. That could reject an original completed
request after a later source replacement. The adapter now checks the owned
completed external-request fingerprint first, while new stale requests still
fail; the independent regression demonstrates both outcomes.

Early test assumptions were corrected to the actual existing contracts:
unavailable pilot views include a limitations message; API library pages are
bounded to 50; the capture receipt uses `fetched_count`; the unchanged board
source endpoint returns at most 3 blocks per request. A synthetic JATS fixture
without the supported own-PMCID/CC BY/CC0 policy was correctly rejected; that
status test now uses the existing approved source. These were test corrections,
not relaxed product checks or additional platform support.

## Observed workflow costs and remaining limits

The software sequence requires a reason and expected revision for each explicit
mutation. Acquisition/attachment, retrieval status, screening and handoff remain
separate actions. This protects provenance but increases steps; whether the
reviewer finds that burden acceptable is unknown until an actual session.

The provisional acknowledgment is necessary for the mixed full-text/abstract
working subset. Reconciled library counts and a small comparison subset have
different denominators. Current-protocol alignment warnings must be read
alongside historical ledger counts after a protocol revision.

TXT/PDF full-text handoff is unsupported. The current JATS policy requires a
single own PMCID and supported CC BY/CC0 reuse permission. Larger/malformed
uploads and unsupported capture sizes fail explicitly; no partial intake is
promoted as complete. Complete PubMed verification remains bounded to 10,000
matches, without automatic segmentation or resume. Source hashes demonstrate
internal integrity, not an NCBI signature or clinical validity.

Real protocol choices remain unresolved, including age ranges, mixed-population
rules, study designs, search dates/limits/coverage, appraisal and disagreement
procedure. The proposed sole reviewer has not completed this evaluation. Her
identity is not authenticated by a typed reviewer label, and no second human
review or independent key-outcome extraction has occurred. No actual review
readiness is inferred from the software-purpose fixture.

The displayed public library contains titles referring to reviews, study
protocols and animal studies as well as human reports. This is another reason
not to treat the rights-filtered example as an eligibility-screened library or
a retrieval-quality benchmark. No automatic topic/design exclusions were added.

Actual production-browser evidence is recorded separately by the coordinator;
it must not be inferred from this in-process API run. Live searches, real model
inference, retrieval-accuracy evaluation, publication and deployment were not
performed by this evaluator. Frozen release assets, profiles, original research
databases and the actual portfolio were outside the test inputs.

## Coordinator review and actual production-browser check

The coordinator reviewed the independent arithmetic/source evidence and kept
the next step focused on the complete browser journey. A separate copy of the
current uncommitted application was built with the existing locked dependencies
and launched in production mode on temporary loopback ports with a new external
temporary data directory. Original application build files and user databases
were not selected. The final reviewed production build passed in **3.704 s**;
this reused installed dependencies and was not a fresh installation or release
archive qualification.

Actual browser actions created a separately owned software-purpose project,
saved two protocol versions with real methodological choices still unresolved,
and imported the same disclosed 30-record set. Only three reports were
scriptedly advanced in this browser case; 27 stayed pending. Two public JATS
sources and one intentionally abstract-only source were selected explicitly.
The browser rejected an attempt to declare the abstract-only report retrieved.
It retained one scripted included report and one unresolved full-text assessment;
the independent study total remained null. This is distinct from the evaluator's
30 scripted decisions and **must not be summed into another sample size**.

An explicitly acknowledged provisional handoff opened the existing 3 × 3 board.
All cells stayed unsubmitted, unassessed and without checked references. An
explicit lexical search for `Cheonggukjang tablets daily` requested/returned ten
passages from the exact selected trial source. Returning passage 1 to the cell
showed the exact highlight and preserved a pending software-QA draft. It did not
attach a reference, set support or submit a value.

A controlled shutdown, application-file update and production restart against
the same test data preserved the protocol history, screening counts, source
choices, pending cell draft, edited passage query, count and selected run. The
same exact source was reopened. Keyboard testing verified that selecting a
report focuses its editor, Back to library position returns to the original row,
and Return reopens the report. A separate empty research-purpose project retained
the owner's scope with all methodological choices unresolved and no screening;
its empty range displayed `0–0`. Both projects are new test-state projects, not
existing original research databases.

The browser observed the protected audit-export link. Its download was not
repeated through browser control; actual ZIP bytes, contents and determinism were
tested through the independent HTTP/API runner. The temporary browser tab and
both owned test servers were closed after the checks. Existing app/static-demo
servers and the actual portfolio remained unchanged.

Two observed UI defects were fixed during this check: the empty range had shown
`1–0`, and selecting a report left focus in a long table. Code review also found
that a write response from the first library page could replace a later page;
the adapter page is now reloaded without silently rebasing the write token, with
a dedicated second-page regression. Early browser selector assumptions about
native disclosures and exact nested-label names were corrected to the actual
rendered controls; they were tool-selector issues, not relaxed product checks.

Final frontend command (`apps/web` working directory):

```sh
node --import tsx --test tests/*.test.ts tests/*.test.tsx
```

Result: **178 passed, 0 failed/skipped, 3.856 s**, with inherited
react-test-renderer deprecation warnings. This includes eleven new pilot UI/bridge
tests for no implicit research mutations, protocol choices, draft conflicts,
exact handoff, narrow body/query boundaries, later-page retention, exact UTF-8/BOM
retention, invalid-byte rejection and late source-response protection. Production
build includes TypeScript validation.

Other affected regressions were run separately, without summing overlapping
suites:

- Existing ledger/document/evidence/study tests plus new pilot ledger tests:
  **237 passed**, 5 inherited PyMuPDF warnings, 2.35 s, using the existing
  `.venv` interpreter. Initial `.venv-map` execution lacked PyMuPDF and failed
  two existing PDF tests; no dependency installation/upgrade was used to resolve
  this. Initial OpenAPI generation under `.venv` lacked FastAPI; generation
  succeeded using the existing `.venv-map` environment instead.
- Existing API, comparison passage and collection tests: **59 passed**, two
  inherited Starlette warnings, 25.12 s, using `.venv-map` and temporary state.
- Independent pilot acceptance: **9 passed**, described above.
- Semantic OpenAPI comparison with `cb98e3e`: **zero removed or changed existing
  paths/schemas**; eleven new pilot route paths and ten request schemas only.
- `git diff --check` passed. Full historical repository/model/live/hosted build
  suites were not rerun; no Linux/Windows, mobile or real-model checks are claimed.

Detailed local evidence is in
`.mvp-web-state/ui-checks/protocol-pilot-2026-10-24/`, including
`browser-results.json`, source screenshots and the separate independent report.
Software results do not establish usefulness to the proposed reviewer.

## Remaining decision

Protocol versions, sources and event histories are retained; the original
project's legacy protocol fields intentionally remain its initial snapshot.
Full-text decisions are declared events bound to the protocol and ledger digest,
not authenticated proof that a person read a particular source. Replacing a
source preserves declared screening history/counts; the next handoff binds the
exact active source, while historical boards retain their own sources. No
per-decision read attestation or independent verification is claimed.

Cross-store publication is journalled, not a distributed atomic transaction. The
caught-failure retry is demonstrated; hard process/machine-crash recovery is not.
Study linkage still uses the existing ledger/CLI; no new web linkage editor was
built. Reviewer burden, protocol suitability and actual topic relevance remain
unmeasured by these scripted checks.

The next highest-value step is to settle the still-open protocol choices, then
have the proposed sole reviewer perform and time an actual small session in a
new research-purpose project. Capture confusion and errors before extending
features. A complete review search, independent key-data review and a retrieval
accuracy benchmark are separate work. Publication Track A remains blocked on
the owner's terms decision and separate approval; this pilot does not rebuild
or replace the frozen `.2` release.


Final independent UI review found and resolved a source-context race: a late
response for report A could previously reopen beside a newly selected report B.
The inspector now invalidates pending reads on selection/close/unmount, checks
its request and current report before display, and verifies returned document
identity/hash. A delayed-response A-to-B regression passes. A final production
browser check confirmed switching reports clears the old inspector and displays
only the new exact source (trial SHA `a734f911…` followed by intentionally
abstract-only SHA `86b39875…`). This browser check did not simulate network delay;
the deterministic delayed-response test supplies that evidence. The final
independent read-only review confirmed the original finding resolved.

The final UTF-8 tests preserve original BOM/Unicode bytes through the browser
intake payload and reject invalid byte sequences before intake. No replacement
characters are silently substituted. Browser selection/query text is still not
placed in URLs. Oversized-capture messaging explicitly says the standalone CLI
does not automatically attach its results to this browser-owned pilot.

Final preservation audit passed: 65 protected files (including the frozen
release assets and original research state) and 81 actual portfolio files were
unchanged. Main and the frozen feature branch remain at their original commits;
the index was empty at that pre-commit audit. Track B is maintained separately on
`codex/protocol-review-pilot`. All 24 intended source/documentation/test changes
are listed in the local `changed-files.txt` evidence. Existing API paths/schemas
are semantically unchanged. No release archive was rebuilt, old hash assigned
to new code, license selected, source pushed or portfolio/deployment published.
