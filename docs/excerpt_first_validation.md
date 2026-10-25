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

A subsequent final-gate run exposed three evaluation-fixture races (192/195): void UI handlers had not completed their draft/fingerprint/action work when the tests immediately asserted response or save state. The original failed log is retained. The tests now wait for actual enabled editor controls, rendered candidate/error results and immutable save acknowledgements, and settle fixture work before unmount. The first complete run after this test-only correction passed all 195 tests; TypeScript passed. Application code and reviewer data were unchanged. This is distinct from the earlier extracted-browser harness readiness issue.

## Optional retrieval clarity

Settings distinguish installed weights from metadata-only dependency availability; checking availability imports no model stack and executes no inference. Existing hybrid jobs expose sanitized phases and actual completed batch/item/window counts. Progress/cancel/retry is visible in Passage search and the comparison cell; retry is an explicit new request after failure. A completing batch cannot erase acknowledged cancellation intent. Restart marks unfinished work interrupted while retaining its last counters. Computation stays outside mutation locks; deleted/stale inputs still cannot publish.

The same retrieval algorithms, manifest/profile bindings, model input policy, receipt/export formats and 600-second product budget remain. Native/profile/pack/pipeline regressions: 57 passed with the optional tensor runtime installed, no skips. These use synthetic inputs/test doubles; no trained model weights, live providers or generation were executed by that suite. A first invocation found pytest absent from this disposable runtime; it ran after adding the same pinned test runner. An earlier invocation from the wrong directory could not find TypeScript; the correct frontend-directory invocation and production build passed.

The previous one-article Qwen CPU attempt (33,942 code points) exceeded its 180-second QA deadline and remains a recorded failure. That is not the product's 600-second budget. This checkpoint adds observability/cancellation, not a latency or quality claim; a fresh full-text real-model diagnosis was NOT_RUN at that checkpoint; subsequent observed results follow below. Historical successful CPU/MPS encoder/reranker checks are retained in HISTORICAL_RETRIEVAL_VALIDATION.md with their earlier source identity. They are not relabeled as fresh beta.3 executions.

Progress is associated with the current synchronous request, not a guaranteed background service. Full refresh does not rediscover its prior job identifier automatically; server records remain retained. Active forwards may take time before cooperative cancellation. Core lexical remains independent of optional runtimes, weights and generation credentials.

## Fresh extracted candidate (separate from earlier working-tree checks)

Clean candidate `35f38bf27ea15dbc16f99eb537de87f3102523d0` was built and independently audited: all 259 packaged files, per-file hashes, source snapshot, MIT license, attribution and package exclusions passed. A header still showing beta.2 was found before this candidate, corrected to read package metadata, rebuilt and verified as beta.3. A mistyped requested source ID was also refused before an archive was created; superseded local candidate archives are not publication inputs.

On macOS arm64, Python 3.12.7 and Node 24.19.0, a new extracted ZIP, private temporary data and separate Chrome context passed 10 orchestration checks: fresh default setup without Torch/Transformers/weights/research state; production startup overriding inherited hosted/generation settings; 30 public sources and 3×3 comparison/API history/CAS/exact return; actual browser workflow and Settings; both existing lexical profiles and explicit missing-pack/index errors without fallback; occupied-port refusal; genuine restart; fresh application replacement/setup with external data preserved byte-for-byte; reopened authorization/drafts/exact sources and exports.

The actual browser workflow passed 9 checks (three excerpt cells, notes/null path, real conflict barrier, exact passage round trip, refresh/Back, keyboard/narrow layout, Settings return and exports); Settings passed 9 checks. These counts overlap the orchestration result, not additional user trials. The first restart browser harness read the disabled initial query prefill before its asynchronous draft was ready. Retained server data was correct. The failed harness record is preserved; after waiting for the acknowledged enabled state, a completely fresh full run passed without a product change. QA services were stopped. Reviewer data/window remained untouched.

The packaged application-input digest for that candidate is `7d11aa3ca4195eaef7c154facf246a7507040558227d705db58156588c871c80` (source, web, scripts, requirements, configuration and public fixture entries; documentation/release metadata are separate). Final publication must rebuild from the exact merged SHA, compare these application inputs and repeat extracted acceptance. Use the final release identity/integrity files and release notes; this candidate record does not itself claim a later ZIP passed.

## Subsequent cached-model execution (separate from software mocks)

At exact source `c4f57c557fe20ab45a4031c849cff2b3c15c5783`, the same 33,942-code-point / 34-block retained public full-text report produced 52 source-bound windows. Actual Qwen CPU indexing completed in 39.81 seconds: 26 two-item batches, 52 document encodings, 11,473 document tokens, visible progress and a final completed job. Manual cells stayed unchanged. The 180-second QA cutoff and 600-second product budget were unchanged; cancellation was NOT_TRIGGERED and full-text query/reranking was NOT_RUN by this index check. The old failure report is preserved. The earlier timeout was not reproduced; its cause remains unresolved. This one completion is not evidence of a general latency fix or an uncontended benchmark.

Four separate tiny cached checks actually executed one query encoding, two document encodings and two reranker pairs each:

| Profile | Device | Observed seconds | Result |
| --- | --- | ---: | --- |
| Qwen | CPU | 9.94 | PASS |
| Qwen | Apple MPS | 14.11 | PASS |
| MedCPT | CPU | 6.36 | PASS |
| MedCPT | Apple MPS | 6.14 | PASS |

Checks ran serially at lower process priority on macOS arm64 with the existing pinned runtime and cached manifests. Whole-process peak RSS for the full-text case was 2,654,339,072 bytes; this is not isolated model/GPU allocation. All 46 original/clone model files matched hashes, originals retained inode/mtime, clone inodes were distinct, code was unchanged and all owned diagnostic processes exited. No network attempt, download, provider/generation call or reviewer-data access occurred. Windows/model quality/scientific usefulness are not established. The sanitized report has SHA256 `c24bed59445335dc2cd5098b3e3046ce61fca27dedb316075250f8a4728e8e97`; the release supplement preserves its actual source identity rather than relabeling a later documentation-only source.

## Reviewer retest

Status at beta.3 publication: PREPARED; feedback pending. A dedicated browser profile and fresh temporary data contain three blank cells (Participants, Dietary intervention, Longer-term follow-up) using Core lexical retrieval on one retained public abstract. No answers, support decisions or submitted entries were prefilled. Public attribution is retained as unmapped CSV metadata so this isolated import remains honestly abstract-only rather than resolving to full text. This is a disclosed usability fixture, not a protocol pilot or identity-resolution benchmark.

Ask the reviewer to open each cell, find/read/select an excerpt, comment/judge and save, then record help needed, any cross-page detour, draft/submitted understanding and missing-information clarity. Correction, reopening and exports count only if actually tried. Availability is not completion or approval. No timing, research accuracy or independent human review is claimed.

## Platform and release boundaries

This checkpoint does not qualify Windows or a native executable. Windows portability, runtime/model execution and signing are separate gates. Existing source beta.1/beta.2 assets remain immutable. New release assets must be built from the final reviewed commit, audited and exercised after extraction; earlier archives do not contain this change. Real generation, live PubMed/provider calls and independent scientific quality evaluation are NOT_RUN here.

## Post-publication owner-reported navigation retest — 26 October 2026

The owner reported that the reviewer completed the three-cell excerpt → comment → save task entirely inside the comparison editor without help. The rest of the interface was described as clear/fine, but the reviewer initially did not recognize that the three cells were different fields of the same paper (confirmed clarification). This was the isolated pre-release UX1 production session, not a relabeled human execution of the published ZIP. It is one qualitative report, not an independently observed/authenticated trial, scientific relevance judgment or accuracy benchmark.

The follow-up source displays persistent Paper i/N and Field j/M, the same-report relationship and whether the next unfinished cell changes fields within the paper or moves to another paper. These are read-only projections of the existing board; retrieval, source bindings, drafts, contracts and navigation barriers are unchanged. The new cue has software/browser checks, not a further human retest.

Some excerpts were reportedly not found. Empty candidate results versus inability to open a displayed quotation remains unclarified; no retrieval change or whole-paper absence conclusion is inferred. Specific correction, reopening/export, missing-information interpretation and draft-versus-submitted observations were not separately reported. No timings or independent/dual-review claim are made. The reviewer session/data and published beta.3 assets remain intact; their feedback-pending snapshot was accurate at publication.
