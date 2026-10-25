# Excerpt-first comparison checkpoint

## Scope and baseline

Implemented above published source beta.2 (`21096d706b014c7cb0a4eb15ae04c6059743af1c`). The normal comparison path now stays in one focused editor: select evidence, comment/judge, review/save. Standalone passage search and exact scoped return remain optional. Retrieval algorithms/profiles, scientific cell contracts, source bindings, immutable submissions, exports and Track B are unchanged.

The earlier route was reproduced in the actual baseline browser: three competing evidence actions and the standalone search detour left the user to reconcile attachment and submission prerequisites. Inline service functionality already existed; the problem was discoverability and ordering.

Navigation hints reuse one bounded workspace UI draft per exact board revision (at most 180 paper/field steps). They contain no value, quotation or judgment, cannot satisfy inspection/support and use existing version conflicts. Python validates owned board/paper/field identities and current writable bindings. Historical views cannot persist new hints.

## Observed software checks (macOS arm64)

- TypeScript check and production Next.js build: PASS.
- Integrated frontend suite: 195 passed, zero failed/skipped, including independent excerpt/progress integration tests. Earlier checkpoints reported 189, 191 and 194; these counts overlap and must not be added.
- Combined focused API regressions: 95 passed (two existing Starlette/anyio deprecation warnings), including the 14 editor-navigation tests and 24 hybrid progress/ownership tests. These counts overlap. Earlier separate focused MVP regressions: 50 passed.
- Source packaging/license/link gate: 44 passed, including 9 published-link metadata tests. These checks are offline; a metadata flag does not itself verify public publication.
- Actual isolated production Chrome workflow: seven checks passed: exact inline source with no automatic attachment/judgment; explicit excerpt acknowledgement and comment focus; explicit submission; draft-only note plus refreshed step/text; 390px stacking and keyboard table return; explicit missing-information entry; existing CSV/JSON exports with two submitted entries and a separate unsent note. No page errors, external requests, provider or model calls were observed.
- Independent component cases include delayed acknowledgement, Unicode/4,000-code-point clipping, missing/unavailable sources, multi-reference removal, empty/provider failures, navigation conflict preserving research text, historical views and wrong-paper bindings. They are software checks, not human usefulness evidence.

The initial combined API/MVP pytest collection hit duplicate module basenames before running tests. Separate test processes passed. The independent computer-control tool could not attach reliably to the dedicated Chrome profile; that observation was NOT_RUN, not an application failure. A separate actual-browser harness completed the checks above.

## Optional retrieval clarity

Settings distinguish installed weights from metadata-only dependency availability; checking availability imports no model stack and executes no inference. Existing hybrid jobs expose sanitized phases and actual completed batch/item/window counts. Progress/cancel/retry is visible in Passage search and the comparison cell; retry is an explicit new request after failure. A completing batch cannot erase acknowledged cancellation intent. Restart marks unfinished work interrupted while retaining its last counters. Computation stays outside mutation locks; deleted/stale inputs still cannot publish.

The same retrieval algorithms, manifest/profile bindings, model input policy, receipt/export formats and 600-second product budget remain. Native/profile/pack/pipeline regressions: 57 passed with the optional tensor runtime installed, no skips. These use synthetic inputs/test doubles; no trained model weights, live providers or generation were executed by that suite. A first invocation found pytest absent from this disposable runtime; it ran after adding the same pinned test runner. An earlier invocation from the wrong directory could not find TypeScript; the correct frontend-directory invocation and production build passed.

The previous one-article Qwen CPU attempt (33,942 code points) exceeded its 180-second QA deadline and remains a recorded failure. That is not the product's 600-second budget. This checkpoint adds observability/cancellation, not a latency or quality claim; a fresh full-text real-model diagnosis is still NOT_RUN. Historical successful CPU/MPS encoder/reranker checks are retained in HISTORICAL_RETRIEVAL_VALIDATION.md with their earlier source identity. They are not relabeled as fresh beta.3 executions.

Progress is associated with the current synchronous request, not a guaranteed background service. Full refresh does not rediscover its prior job identifier automatically; server records remain retained. Active forwards may take time before cooperative cancellation. Core lexical remains independent of optional runtimes, weights and generation credentials.

## Reviewer retest

Status: PREPARED; feedback pending. A dedicated browser profile and fresh temporary data contain three blank cells (Participants, Dietary intervention, Longer-term follow-up) using Core lexical retrieval on one retained public abstract. No answers, support decisions or submitted entries were prefilled. Public attribution is retained as unmapped CSV metadata so this isolated import remains honestly abstract-only rather than resolving to full text. This is a disclosed usability fixture, not a protocol pilot or identity-resolution benchmark.

Ask the reviewer to open each cell, find/read/select an excerpt, comment/judge and save, then record help needed, any cross-page detour, draft/submitted understanding and missing-information clarity. Correction, reopening and exports count only if actually tried. Availability is not completion or approval. No timing, research accuracy or independent human review is claimed.

## Platform and release boundaries

This checkpoint does not qualify Windows or a native executable. Windows portability, runtime/model execution and signing are separate gates. Existing source beta.1/beta.2 assets remain immutable. New release assets must be built from the final reviewed commit, audited and exercised after extraction; earlier archives do not contain this change. Real generation, live PubMed/provider calls and independent scientific quality evaluation are NOT_RUN here.
