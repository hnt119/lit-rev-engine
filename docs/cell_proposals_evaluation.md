# Optional cell-proposal evaluation

Date: 21 October 2026. The inspected branch is `codex/mvp-v0-3`, with Git HEAD `60f8aa96a4e3ea6dcced805e2158bf5aeafa5923` and the completed **uncommitted local manual-board implementation** present. This checkpoint extends that working tree; HEAD alone does not contain its baseline board. The earlier manual-board evidence remains in [its evaluation record](manual_board_evaluation.md).

Publication note: the user subsequently authorized committing and pushing both implemented checkpoints to `codex/mvp-v0-3`, with main unchanged. The baseline and execution-time status below are historical evaluation evidence. Private receipts, source text, databases, supplied research materials and unrelated local work are excluded from the publication scope.

Publication verification used the 45-file staged scope, exported without private or unrelated files. All 532 Python tests and 60 frontend tests passed, with zero skips; TypeScript checking and the production Next.js build passed. Two snapshot setup failures were resolved without application changes: the existing storage compatibility test needed read-only access to Git history, and Turbopack needed an in-snapshot copy of the installed dependencies instead of an external symlink. The affected test and build passed on rerun. The staged patch check also found and removed one trailing blank line in a new test. Existing dependency deprecation warnings remain. No live retrieval or real-model inference was run for publication, and these checks do not validate human usefulness.

## Evidence status

| Evidence | Actual result and scope |
| --- | --- |
| Independent proposal domain checks | **PASS: 39 tests, zero skips.** Synthetic retained full text, an abstract and an unavailable source. Mock generation only, with network connections denied. |
| Independent proposal HTTP checks | **PASS: 6 tests, zero skips; 2 dependency warnings.** Public offline saved sources and a mock adapter. Session ownership, CSRF, persistence, inspection and state transitions. |
| Final full MVP regression suite | **PASS: 389 tests, zero skips.** Coordinator execution after final refinements; the earlier independent run passed 385 tests. Focused counts overlap these totals. |
| Final mapping / HTTP suite | **PASS: 143 tests, zero skips; 2 existing dependency warnings.** |
| Final frontend / production build | **PASS: 60 tests, zero skips; TypeScript and production build passed.** |
| Actual browser workflow | **PASS for the bounded software walkthrough below.** Real research board remained generation-disabled; a separate synthetic/mock application exercised proposal review. |
| Adapter/service integration | **PASS within the independent domain suite.** The actual configured HTTP adapter uses a mocked transport, exercising successful output, malformed JSON, transport timeout and HTTP failure. This is not a real local server or model run. |
| Real model execution, model quality and actual token consumption | **NOT_RUN.** No authorization for real inference was assumed. Mock usage fields test accounting behavior and do not describe actual model consumption. |
| Live PubMed/source acquisition or embedding execution | **NOT_RUN in this checkpoint.** Existing discovery evidence is neither repeated nor upgraded. |
| Scientific entailment, human relevance and usefulness | **NOT_RUN.** Software assertions and agent-entered walkthroughs do not establish these outcomes. |

Actual browser and final frontend/build results are recorded separately below. Generation remains disabled by default, and no paid endpoint, credentials, remote fallback, deployment or publication was used by these tests. The final broad suites total **532 Python tests and 60 frontend tests**; focused counts are not additional tests.

## Commands executed by the independent evaluator

From the repository root:

```sh
/private/tmp/lre-mvp-venv/bin/python -m pytest tests/mvp/test_proposals_independent.py -q -rs
# 39 passed in 2.52s; no skips

.venv-map/bin/python -m pytest tests/web_api/test_proposals_independent.py -q -rs
# 6 passed, 2 warnings in 4.34s; no skips

/private/tmp/lre-mvp-venv/bin/python -m pytest tests/mvp -q -rs
# 385 passed in 13.30s; no skips
```

The HTTP warnings concern Starlette's deprecated `httpx` TestClient integration and the `anyio.abc.BlockingPortal` alias. They are not assertion failures or skips. These suites make no network/model calls; a patched socket boundary fails an attempted connection.

## What the independent checks establish

- Disabled generation performs no candidate retrieval, starts no adapter call and leaves the manual board available. GET/list/context operations do not trigger generation.
- The existing per-paper/per-field lexical ranker supplies candidate runs. A paper packet deduplicates shared canonical anchors, retaining each field's allowed evidence IDs and its distinct retrieval audit. Three source types can yield nine separate proposals without confusing abstract-only or unavailable evidence with full-paper absence.
- Every proposal retains board and field revisions, paper/source bindings, retrieval and packet digests, prompt version and model profile. Exact Unicode quotations are reconstructed at canonical code-point offsets. Unknown, wrong-paper, wrong-field, mismatching and ambiguously repeated references are rejected before any proposals from that run are published.
- Exact source matching does not establish semantic support. A deliberately non-entailing synthetic value with an exact quotation remains `unassessed`, labeled as an AI suggestion requiring review, and never becomes independently verified.
- Typed output rejects unknown fields, omitted or duplicated requested fields, extra verification claims, blank values, unexplained nulls, malformed or fenced JSON, duplicate JSON keys, non-JSON numbers and excessive output. A second-paper failure publishes no first-paper suggestions. Failed receipts retain the available usage metadata; unknown tokens or cost remain null rather than fabricated zeros.
- The actual configured adapter and service agree on a maximum ten-second call deadline. HTTP errors, malformed output and transport timeout retain distinct safe failure categories. Tests inspect the outgoing request and find no model action tools.
- Generation holds no workspace, lifecycle or sidecar mutation lock during the delayed mock call. Concurrent selected-cell draft saves, submissions, board-definition revisions, source preparations and workspace deletion complete while that mock is blocked. Changed inputs reject all stale publication. Deleted proposal state remains deleted after late completion.
- A timed-out adapter call cannot publish later. Its call lease prevents another overlapping call until it finishes. Concurrent duplicate request keys reuse the persisted running receipt; a new request is rejected while another run is active. Twenty completed runs exhaust the workspace quota and a twenty-first makes no call. No implicit retry occurs.
- “Use in draft” performs explicit CAS and writes only an empty current draft, using the researcher's edited value. It preserves manual producer state, sets neither support nor inspection, and requires the existing manual workflow before submission. Existing draft content and stale submitted heads are not overwritten; an explicit current-head revision retains immutable submitted history.
- Dismissal is a separate persisted review action. Dismissed/adopted status, exact inspection, draft state and the separate proposal audit survive reopening. Historical proposals retain original context and remain read-only. Existing board table/history and research export schemas remain unchanged; proposals do not become submitted rows.
- Another browser session cannot access proposal capabilities, runs, suggestions, context, adoption, dismissal or audit. Mutations retain the existing exact Origin and CSRF requirements. Clients cannot add authoritative support/inspection claims to the adoption request.

## Findings and corrections

| Finding | Evidence and disposition |
| --- | --- |
| Overlapping exact quotation occurrences were mistakenly treated as unique | **Reproduced as one failing independent regression.** In `aaaa`, the quote `aaa` matches canonical offsets 0 and 1, while Python's non-overlapping `str.count` reports one. The service now finds a second occurrence starting one code point after the first. The regression passes. |
| The initial service could pass the entire remaining run budget to an adapter capped at ten seconds per call | **Found by coordinator review and corrected before the independent integration run.** Four tests exercise the actual adapter through the service with a mocked HTTP transport, including success, invalid output, timeout and provider failure. Every connection/socket timeout is at most ten seconds. |
| A new packet test assumed the lexical ranker would return a single matching block | **Test assumption corrected.** The retained ranker legitimately includes neighboring context blocks. The test now checks unique canonical anchors against the union of actual field candidates, rather than changing retrieval behavior. |
| A historical-export test expected its current freshness label to remain unchanged | **Test assumption corrected.** CSV and JSON correctly change only the applicable freshness dimension to historical after a definition revision. Tests compare the preserved table content separately from that intentional status change. |
| A patch placed unknown-usage assertions in a measured-usage quota test | **Evaluator test error corrected.** The mock explicitly returns 13 input tokens and 11 output tokens. Those measured fields must be retained; unknown-usage assertions belong to the provider-failure case. No product change was made for this error. |

## Browser and coordinator verification

The coordinator ran the final integrated suites after the quota, coverage, model-profile and replay refinements. Focused counts above overlap these suites and are not additional tests:

```sh
/private/tmp/lre-mvp-venv/bin/python -m pytest tests/mvp -q -rs
# 389 passed in 14.28s; no skips

.venv-map/bin/python -m pytest tests/mapping tests/web_api -q -rs
# 143 passed, 2 existing dependency warnings in 45.60s; no skips

cd apps/web
/Users/hunt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --import tsx --test tests/*.test.ts tests/*.test.tsx
# 60 passed, 0 failed, 0 skipped; 860.433833ms

NEXT_TELEMETRY_DISABLED=1 /Users/hunt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node node_modules/next/dist/bin/next build
# PASS, including TypeScript
```

OpenAPI was regenerated with `.venv-map/bin/python scripts/export_web_openapi.py`, then `node node_modules/openapi-typescript/bin/cli.js lib/openapi.json -o lib/generated-api.ts` in `apps/web`, using the bundled Node path shown above. An explicit `tsc --noEmit --incremental false` also passed. `git diff --check` passed. Existing manual-board frontend checks remained passing. A new application-level check verifies invalid optional generation configuration disables AI while manual workspace creation and reopening still work.

### Actual browser evidence

The real research application was started on loopback ports 3000/8765 with generation explicitly disabled. Its existing retained board reopened with the original nine cells and eleven cell revisions. Opening the optional controls showed **GENERATION DISABLED** and a disabled generation button. No model ran on private retained sources.

A separate application on loopback ports 3001/8766 used synthetic full-text, abstract-only and unavailable sources and an injected **SOFTWARE_MOCK_NOT_A_MODEL** adapter. Its private harness and receipts are under the ignored `.mvp-web-state/ui-checks/cell-proposals-2026-10-21/` directory. The harness uses a distinct test cookie and separate databases. These are actual browser actions against the new application, but generation and scientific content are mocked:

| Action | Observed result |
| --- | --- |
| Create three-report / three-field board and explicitly generate | One successful run, three mock calls and nine separate proposals. No cells were submitted automatically. |
| Inspect a proposal's exact reference and generation packet | Canonical Unicode source context opened; field-specific matched/indexed/supplied/omitted counts were visible. Inspection remained undeclared until explicitly marked. |
| Edit a proposed value and use it in a draft | Researcher-edited text appeared in the manual draft; human support stayed unassessed, scope not assessed, inspected ranges empty. |
| Attempt manual submission before declaring inspection | **Expected rejection (422):** a cited range must lie within declared inspected material. No submission was created. |
| Mark the reference inspected, choose scope and explicitly submit | One immutable manual cell revision was created with human support still unassessed. The deliberately generic mock value was not certified as scientifically supported. |
| Enter existing manual text in an abstract-only cell, then inspect and dismiss its proposal | Use in draft became disabled; dismissal preserved the manual text and did not declare inspection. |
| Adopt a null proposal for unavailable material, explicitly submit and reload | Missing information persisted, scope stayed not assessed, no range was invented and no whole-paper absence was asserted. |
| Download board CSV and separate proposal audit | CSV had nine cells with only two explicit submissions. Audit had nine proposals, three calls and three events (two adoptions, one dismissal). Unknown token counts/cost were null, `measured=false`. |
| Inspect responsive display and console | At 390 px, body width remained 390 px. Browser console errors were empty; temporary viewport override was reset. |

Screenshots, downloaded artifacts and `checkpoint-receipt.json` remain private. The board's prior real-source browser demonstration remains in the historical manual-board report; it is not reclassified as real-model validation. Concurrent-edit, deletion, stale-publication, failure, historical-definition and timeout behavior have software-test evidence here, not an additional browser walkthrough of every case.

### Test setup failure and repair

The first isolated browser server mistakenly used the research server's hostname and session-cookie name. Browser cookies do not isolate by TCP port, so it replaced this browser's research cookie and interrupted access. The coordinator backed up the private credential database and restored the same browser's nine existing workspace ownership bindings to its current session. The isolated harness now uses a distinct test cookie. Actual browser reopening confirmed restored access. No workspace payload, source, draft, cell revision, board head, candidate or existing board request row changed during this repair. Credential-session metadata did change; it is not included in the unchanged-data claim below. No product authentication bypass or account-recovery endpoint was added.

One browser download/control call took unexpectedly long; the files ultimately downloaded and were validated. Initial new frontend checks also exposed asynchronous test timing: callbacks were made awaitable, and the checks reran successfully. Adoption additionally uses the existing navigation barrier and temporarily locks manual editing while its acknowledged draft baseline is restored; a delayed-adoption regression confirms navigation waits. These checks do not establish model latency or human usefulness.

## Changed files and preservation

The checkpoint changes **26 files relative to its actual starting working tree**, not relative to Git HEAD (which lacks the earlier local manual-board checkpoint):

| Area | Files |
| --- | --- |
| New proposal contracts/service/storage | `src/mvp/proposal_contracts.py`, `src/mvp/cell_proposals.py`, `src/mvp/adapters/proposal_storage.py` |
| One generation adapter and packet builder | `src/mvp/adapters/cell_generation.py` |
| Additive existing storage integration | `src/mvp/adapters/board_storage.py` |
| API integration | `src/web_api/proposal_routes.py`, `src/web_api/app.py` |
| Browser integration | `apps/web/components/cell-proposals.tsx`, `apps/web/components/compare.tsx`, `apps/web/app/globals.css`, `apps/web/lib/bridge.ts` |
| Generated contracts | `apps/web/lib/openapi.json`, `apps/web/lib/generated-api.ts` |
| New domain/adapter checks | `tests/mvp/test_proposals.py`, `tests/mvp/test_cell_generation.py`, `tests/mvp/test_proposals_independent.py` |
| New HTTP checks | `tests/web_api/test_proposals_independent.py`, `tests/web_api/test_proposal_config.py` |
| New frontend checks | `apps/web/tests/cell-proposals.test.tsx`, `apps/web/tests/proposal-boundaries.test.ts` |
| Guides and evaluation | `docs/cell_proposals.md`, `docs/cell_proposals_adapter.md`, `docs/cell_proposals_evaluation.md`, `docs/manual_comparison_board.md`, `docs/mvp_v0_3.md`, `docs/mvp_v0_3_board_plan.md` |

The coordinator recorded 706 starting file hashes: 696 remain unchanged and the ten changed existing files are listed above; sixteen files are new. Pre-existing README and `.gitignore` changes, research experiments, supplied materials and unrelated files are preserved. The original board service, manual cell contracts and existing manual tests were not rewritten.

All eleven original research/board table contents matched their starting row hashes: twenty research snapshots, eleven submitted cell revisions, nine cell heads, nine candidate runs, the original definition, drafts and request receipts remain intact. Proposal tables are additive in the existing private sidecar; a private backup of the starting manual-board database was retained. Removing only new proposal paths and schemas from generated OpenAPI reproduces the starting OpenAPI file exactly. Existing export contracts and map/retrieval code were preserved; no refit or new source capture was requested.

At evaluation time Git was on `codex/mvp-v0-3`, HEAD `60f8aa96a4e3ea6dcced805e2158bf5aeafa5923`, with the prior manual board and this checkpoint still local. Main was `a506ae05fc19c21a1d80beabc26bfc831582441d`. No commit, push, merge, deployment or private-data publication had occurred during that evaluation.

## Remaining limits

- No real model has been evaluated for correctness, latency, context handling or research usefulness. A configured model revision is an operator declaration, not a verified weights checksum. A real evaluation requires separate authorization and must report its actual usage, failures and evidence limits.
- A proposal sees bounded retrieved candidate context, including candidate omissions and explicit retrieved-context scope. Even a `full_text` source type does not mean the model saw the full paper. Exact quotations and null values do not establish completeness, entailment, whole-paper absence or absence from the literature.
- The local adapter accepts one explicit loopback endpoint with zero configured spend and no automatic fallback. The checkpoint does not supply a model server or prove that a given local model fits available hardware.
- Transport or invalid-envelope failures may not expose usable token counts; those remain unknown. This checkpoint has no authorized real-model accounting result.
- Failed or interrupted attempts remain auditable and consume the bounded run quota. A process interruption can retain a running receipt with a recovery note; reopening must not automatically repeat inference. If the shared storage quota prevents even a failure-receipt update, a retained running receipt can remain, with no partially published proposals.
- Current adoption preserves the existing `producer: manual` cell contract. Separate proposal audit events link the suggested origin and edited draft digest; the old submitted-cell and export schemas were not replaced. Researchers must still inspect sources and explicitly record support, scope and submission.

The independent evaluator owned the two independent test files and the initial evaluation record; the coordinator added the final browser, build, preservation and changed-file evidence above. No software or browser result here establishes scientific entailment or human usefulness.
