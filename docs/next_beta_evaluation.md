# Next Track A beta: acceptance and evaluation record

This record belongs to the isolated successor to `105d98f87ced3e415f77d36305dba7244fc3cf7f` on `codex/next-local-beta`. The published `v0.3.0-beta.1` source and downloads remain frozen. Track B, the public portfolio and Render are outside this evaluation.

## Evidence labels

- **Offline software check:** deterministic test clients, synthetic responses, or a local bounded HTTP fixture. It establishes the behavior exercised, not provider compatibility or research usefulness.
- **Real provider check:** an actual external authenticated call with disclosed consent, model, bounded input and returned usage. None is authorized for this increment.
- **Real model check:** actual model execution, distinct from a typed mock and from reuse of retained embeddings. None is implied by normal tests.
- **Human usefulness:** research judgments and researcher observation. No software test is evidence of this.

Live authenticated OpenAI/DeepSeek checks, real LLM planning/proposals, live PubMed, optional model downloads and independent research validation are **NOT_RUN** unless an explicit subsequent entry documents authorization and execution. Unknown provider usage or cost must remain unknown.

## Increment 1: settings and per-search specification

| Contract | Required evidence |
| --- | --- |
| No requests on open, key entry or save | External transport trap around local settings GET/PUT and frontend navigation; only explicit test/operation may call a provider |
| Paper-provider and LLM independence | PubMed readiness with contact and no API key; saved/manual research with generation disabled; changing LLM must not alter map/cache/retrieval profile |
| Scientific scope per search | Dates, sort, record bound, original question, reviewed exact query and approved concepts persist in search/plan history; defaults cannot revise historical plans |
| Secret ownership | Separate authenticated browser sessions cannot observe/use each other's credentials; GET reveals presence only; no key in files, research SQLite, exports, drafts or logs |
| Configuration lifecycle | Saved/effective version shown; two-tab compare-and-swap conflict; no environment mutation; next operation snapshots exact version |
| Draft-safe settings navigation | Existing draft flush barrier, correct return destination, browser refresh and conflict behavior; no unrelated draft overwrites |

## Increment 2: optional generation adapters

| Contract | Required evidence |
| --- | --- |
| Fixed transport | Local literal-loopback endpoints only; cloud fixed HTTPS endpoint per provider; redirects/TLS bypass/arbitrary URLs/proxy credential forwarding rejected |
| Explicit one-run consent | Provider, model, task, data categories/amount and possible account charges shown; consent bound to exact input/configuration/session; replay does not repeat a billed call |
| Bounded execution | Request/context/output/time/concurrency limits, no automatic billed retry and no fallback; provider failure never silently activates a second adapter |
| Application-level validation | Empty/refused/truncated/action-bearing/malformed/duplicate-key JSON rejected; unknown IDs, wrong papers and ambiguous/mismatching quotations rejected by existing source gates |
| Human review unchanged | Suggestions separate from drafts/submissions; adoption cannot set support/independent verification or submit automatically; stale board/settings publication rejected |
| Secrets removed/restart | Future operations fail closed after removal/restart; in-flight limitation disclosed; no durable key recovery or silent launch-config import |

## Increment 3: same-UI Electron packaging experiment

The browser successor is evaluated before this packaging increment. The prototype must disclose its actual included runtime paths and architecture; copying a developer virtual environment does not prove a relocatable Python distribution.

| Contract | Required evidence |
| --- | --- |
| Same production application | Next.js production server and existing FastAPI services; exact UI components/CSS; no static rewrite or second research engine |
| Bundled runtime proof | Installed package inspected; process executable paths inside bundle; developer Node/Python/pnpm unavailable; no first-run installer/build/download for core saved/manual workflow |
| Local isolation | Dedicated persistent renderer partition and separate Desktop Preview data root; no cookie/database import from browser beta or Track B |
| Process ownership | Single instance/store; occupied port rejection; readiness checks identify owned children; close/reopen/crash recovery; never kill arbitrary listener |
| Renderer boundary | Sandbox, context isolation, no renderer Node integration, unchanged origin/CSRF/Host policy; external links opened only through a validated system-browser path |
| Research parity | Saved example, import, board → saved passage results → exact source → original cell, drafts, exports and restart with fresh temporary state |
| Measurements | Compressed/installed size, cold readiness time, idle/working process memory, shutdown, upgrade/non-overwrite, signature/notarization status |

A passing development launch is not a standalone installer. An unsigned internal app is not a trusted public macOS release. No Gatekeeper bypass, signing purchase, new platform claim or automatic updater is part of this increment.

## Documentation checks informing the tests

Current official documentation was inspected on 25 October 2026:

- [DeepSeek JSON output](https://api-docs.deepseek.com/guides/json_mode/) requires JSON instructions and permits empty output; the application must validate received content.
- [DeepSeek chat completion](https://api-docs.deepseek.com/api/create-chat-completion/) publishes provider-specific parameters. A model/API profile cannot be inferred solely from an OpenAI-compatible path.
- [Electron utility process](https://www.electronjs.org/docs/latest/api/utility-process) supplies a separate Node-enabled process; it is a suitable candidate for the Next.js runtime rather than executing the server on the UI/main event loop.
- [Electron security](https://www.electronjs.org/docs/latest/tutorial/security) requires explicit renderer and navigation boundaries. A loopback URL alone does not establish child ownership.
- [Next.js standalone output](https://nextjs.org/docs/app/api-reference/config/next-config-js/output) traces runtime dependencies but does not automatically copy `public` or `.next/static`; it does not bundle Python or establish Node compatibility.
- [python-build-standalone distributions](https://gregoryszorc.com/docs/python-build-standalone/main/distributions.html) describe target-specific self-contained runtime archives and metadata. Runtime attribution and actual relocatability must be evaluated for the chosen artifact.

## Actual results

Implementation and execution are complete for the review candidate below. Acceptance tables describe intended contracts; only the recorded executions establish which checks passed. Published beta.1 remains unchanged.

### Independent offline checks executed on 25 October 2026

Test runtime: fresh temporary Python 3.12 environment containing the locked application HTTP dependencies plus pytest/httpx. All data roots were pytest temporary directories. No authenticated provider, model, PubMed or private workspace was used.

| Command (from the successor checkout) | Observed result | Scope |
| --- | --- | --- |
| `python -m pytest tests/web_api/test_board_passage_flow.py tests/web_api/test_proposal_config.py tests/web_api/test_search_plans_independent.py tests/web_api/test_proposals_independent.py tests/web_api/test_hosted_security.py -q` | 87 passed in 13.71 s | Existing targeted baseline before runtime-route integration; this is historical within this implementation cycle, not a final whole-tree claim |
| `python -m pytest tests/web_api/test_cloud_transport_independent.py tests/web_api/test_runtime_settings_independent.py tests/web_api/test_generation_consent_independent.py -q -p no:cacheprovider` | 56 passed in 4.21 s | Independent new settings, transport, consent, stale publication and deletion checks after the hard-deadline repair; before the additional serialization test below |
| `python -m pytest tests/web_api/test_runtime_settings_independent.py::test_optional_runtime_metadata_preserves_historical_capture_and_receipt_bytes -q -p no:cacheprovider` | 1 passed in 0.40 s | Old capture/receipt dictionaries serialize without newly absent metadata; explicit new metadata remains available |

The independent suite traps external socket creation for settings/API checks. Cloud HTTPS is replaced with deterministic connection/response fixtures, not a live provider. It covers fixed credential destinations, no redirects/retry/fallback, 65,536-byte bounds, compression/truncation, malformed/refused/action-bearing JSON, wrong-model output, unknown usage, per-session key isolation, safe validation errors, key removal/restart, private file modes, CAS conflicts, consent expiry/input/session binding/replay, publication after concurrent settings edits, and workspace deletion during generation.

### Failures found and disposition

- **Cloud absolute-deadline defect:** an independently blocked pre-socket connect phase took 0.355 s despite a 0.05 s deadline. Closing a socket could not interrupt a connect/DNS phase without a socket. The transport now bounds caller time with a daemon queue and retains one global call lease until the underlying worker actually exits. The regression passes, including rejection of a second provider while that timed-out worker still runs. This is mocked connect behavior, not an actual cloud/network timeout experiment.
- **OpenAI request contract:** independent documentation review identified a shared `max_tokens` payload. It was changed to provider-specific OpenAI `max_completion_tokens` and DeepSeek `max_tokens`. Mock payload checks pass; real account/model compatibility remains NOT_RUN.
- **Settings UI disable path:** changing the provider to No generative AI originally retained enabled feature flags while hiding their controls. The frontend now clears both switches on that explicit selection. Its focused UI regression passed as reported by the implementation agent; the independent evaluator did not perform a browser click for that report.
- **Planning retry recovery:** review identified that a retained failed request key could cause a new consent to replay the same failed operation indefinitely. The frontend now requires a separate explicit new-attempt action, creates a fresh request ID and prepares a renewed one-run consent. The independent affected UI run below passes its failure/new-attempt regression. Refresh/replay still does not automatically execute a new attempt.
- Initial independent fixtures incorrectly assumed an uncreated base directory, a 204 workspace-delete response, and an omitted historical receipt schema version. These were test-fixture mistakes corrected to the existing contracts; they are not application failures.
- A separate initial packaging regression reported by the root agent used a placeholder license-policy module in a synthetic source tree, causing a syntax error. The root owns its fixture correction and final rerun; this record does not convert that report into an independently rerun result.

At that intermediate checkpoint extracted installation, browser and desktop checks were pending. Their final executions are recorded below; the earlier results keep their original scope.

### Follow-up checks after the identified repairs

- `python -m pytest tests/web_api/test_collection_workflow_independent.py::test_collection_map_in_http_uses_explicit_origin_and_keeps_saved_map_hashes tests/web_api/test_cloud_transport_independent.py tests/web_api/test_runtime_settings_independent.py tests/web_api/test_generation_consent_independent.py -q -p no:cacheprovider`: **58 passed, 0 skipped, 4.96 s**. This includes all 57 new independent tests plus the affected retained-map regression. The fresh environment now has the existing pinned numerical dependencies; no model weights were downloaded and the map test uses software vectors.
- An earlier full HTTP-suite run, started before the final new tests existed, completed **339 passed / 1 failed in 276.03 s**. Its only failure was the retained collection-map test before those optional numerical dependencies were installed. The targeted rerun above resolves that failure. It is not represented as a fresh final full-suite pass.
- `node --import tsx --test tests/research-settings.test.tsx tests/settings-navigation.test.ts` from `apps/web`: independently rerun **10 passed, 0 failed, 0 skipped, 0.304 s**. This covers no provider calls on form activity, key clearing, CAS rebase, disable-AI independence, exact cloud scope/consent, new-search defaults versus retained drafts, explicit fresh attempt after failure and opaque settings return navigation. These are rendered component/contract tests, not actual browser usability observations.

The HTTP suite emits existing Starlette/httpx and AnyIO deprecation warnings; component tests emit the existing React test-renderer deprecation warning. No dependency upgrade was performed to suppress them.

### Final browser increment checks executed by the coordinator

These results are separate from the independent selected runs above.

| Check | Actual result |
| --- | --- |
| `python -m pytest tests/mvp -q` | 717 passed, 13 optional Streamlit skips, 24.88 s |
| `python -m pytest tests/web_api -q` after pinned numerical prerequisites | 345 passed, 0 failed/skipped, 269.72 s; existing deprecation warnings only |
| Full `node --import tsx --test tests/*.test.ts tests/*.test.tsx` from apps/web | 177 passed, 0 failed/skipped (implementation agent execution) |
| TypeScript no-emit plus generated OpenAPI/client | Passed; pinned existing dependencies |
| `python -m pytest tests/local_preview tests/local_distribution/test_release_packager.py -q` | 88 passed, 36.62 s; corrected synthetic license-policy fixture |
| Production `pnpm build` using pinned pnpm10.20.0/Node24.19.0 | Passed, Next16.4.2; telemetry disabled on final run |
| Actual isolated Google Chrome against production servers | 8 checks passed; 0 external browser requests, 0 connection/generation tests, no page errors |

The browser checks exercised settings open/save/key-input clearing, presence-only credential responses, no key in browser storage, independent contact-only PubMed configuration, two-tab conflict/explicit rebase, originating-task return/refresh/draft retention, defaults for a new search versus retained specifications, and key removal. They used a fresh browser context and synthetic non-account keys. They did not replace the owner's browser-beta cookie.

An initial coordinator UI locator waited for a nonexistent heading/link, then a production server still serving an earlier build produced a missing chunk after files were rebuilt. The coordinator stopped only its QA-owned servers and restarted the final production build; the actual isolated browser run above then passed. No application security exception or provider fallback was introduced.

The browser/provider implementation checkpoint is local commit `42b0cbc178442164f6fa348dfa66c7077327268b`. Later packaging/documentation commits are reviewed descendants, not changes to the published beta.1. Extracted-source and desktop artifact results follow. The release files remain bound to the exact code candidate, separately from later report-only commits.


## Final extracted source candidate — d2ae854

Artifact source: `d2ae854f9626ac2a3f7f38cbcd358d5519cdd562`; source version `0.3.0-beta.2`. These are review assets, not a published successor release. The source ZIP has 233 files including generated metadata; its manifest hashes 232 entries and excludes itself. All 231 application payload files are byte-identical to the fully extracted, freshly installed and workflow-tested `565e0766dda042227dd906863098685363ec09dd` package and the freshly installed/smoke-tested `f812e5a188b8d0c9f1f15c904847d14b3d74dca4` package. Only RELEASE.json and MANIFEST.json changed their recorded source binding. The independent final clean-checkout rebuild reproduced all three d2ae854 source release files byte for byte. We did not relabel earlier full installation/unit executions as fresh d2 executions.

Fresh source setup used Python 3.12.7, Node 24.19.0, pnpm 10.20.0, a new virtual environment and new temporary research state; ordinary package download caches were reused. `scripts/local_preview.py setup`, production `launch --no-browser`, `status`, `stop`, `tests/local_distribution/check_installed_preview.py`, `check_comparison_roundtrip.py` and external settings/provider-configuration QA clients exercised the extracted application. The older check_beta_optional.py client is not claimed as a successor execution. The installed checker made 65 local manual-workflow requests: the public 30-paper example/saved map, three papers × three fields, ten explicit software-QA submitted revisions, seven exact inspections and thirteen privacy-denial probes. Settings and optional-feature checks added nine and ten configuration requests respectively. Optional provider profile checks configured local/OpenAI/DeepSeek with dummy keys; they made no model call. The full round-trip check made 38 local requests, including scoped results, wrong-paper/stale rejection, empty results and save conflicts.

A restart with deliberately inherited hosted/AI environment settings kept local mode, removed those inherited permissions and cleared memory-only keys. Preferences, drafts, source/map identity and export content persisted. Occupied-port rejection and controlled shutdown passed. Exact source integrity/MIT/notice/all-30-public-source attribution audits passed. None of these checks involved original research databases or Track B.

## Final extracted desktop execution — d2ae854

The actual ZIP was extracted into a new location. The production app executed using only its bundled Electron/Node and standalone Python; developer Node, Python, pnpm and provider settings were removed from the app environment. Test drivers are external instruments, not application runtime dependencies.

| Execution | Actual result |
| --- | --- |
| Desktop builder/notice unit checks | `python -m pytest tests/local_distribution/test_desktop_packager.py tests/local_distribution/test_desktop_notices.py -q`: 23 passed |
| Desktop boundary unit checks | `node --test tests/desktop/security.test.cjs`: 4 passed |
| Actual Electron production UI | 10 checks passed, 103 local API requests, zero page errors and zero model/provider executions |
| Saved/manual workflow | 30-paper saved example/map; actual public RIS parsing/acceptance without metadata resolution; local API preparation of a three-paper/three-field board; UI cell draft → explicit scoped 20-result passage search → exact source → return to original cell; draft unassessed/unsubmitted, no automatic attachment/support/submission |
| Navigation/parity | Keyboard return/focus at original table cell; Settings return; refresh/reopen; MIT/About return preserves the cell. Chrome/Electron at 1440 × 968 and DPR 2 matched sampled theme, typography, heading and navigation contracts; paired screenshots inspected, pixel identity not claimed |
| Native export dialogs | Actual macOS CSV and JSON Save panels succeeded; CSV parsed as header plus nine cells, JSON parsed as an object. Separate HTTP/download automation also passed |
| Native citation navigation | A public PMID citation opened in Safari while the desktop retained its cell/draft. This was an ordinary citation-page check, not a PubMed API search or connection test |
| Native quit | Menu Quit exited normally and released both service ports. One automated Cmd-Q attempt did not close the app; keyboard Quit is not claimed as verified |
| Single instance | Second launch handed off in 0.233 s; original parent/services unchanged |
| Crash cleanup | Forced termination of the owned parent released owned service ports in 0.315 s |
| Application replacement | Fresh extraction at another path reopened the same isolated QA root in 5.560 s; same cookie authorization, research records and drafts. Board JSON/both CSV exports stayed byte-identical; only workspace JSON's generated exported_at was normalized for content comparison, with raw hashes retained |
| Foreign occupied port | Failed closed; zero requests to the foreign listener; no API started; unrelated listener left alive |
| Post-workflow integrity | Both original and replacement app: 4,100 file/link entries, zero additions/removals/modifications; zero added/missing directories; deep/strict code-signature verification passed |

All QA services were stopped and ports 43000/48765 released. Tests used only the approved public example and isolated temporary software-QA drafts. Research judgments were not supplied by a human researcher and do not constitute usefulness validation.

### Observed desktop size, timing and memory

- ZIP: **163,840,256 bytes** (156.250 MiB); installed files: **390,961,851 bytes** (372.850 MiB). File/link manifest: 4,100 entries, 52 safe internal symlinks.
- Actual first instrumented UI launch: window 6.288 s including driver attachment; app reported readiness 1.935 s and visible window 2.210 s. Reopen: driver 2.855 s, app readiness 2.373 s and visible window 2.584 s.
- Separate owned-process lifecycle measurement: first ready 2.503 s, replacement ready 5.560 s. These are single-machine samples; filesystem/runtime caches may be warm. They are not cold-machine benchmarks or performance guarantees.
- Sampled process RSS sum: **667.31 MiB idle / 827.42 MiB working**. Shared pages are not deduplicated; this is not unique memory or a peak bound.
- Packaged versions actually observed: Electron 45.0.0 / utility-process Node 24.22.0; CPython 3.12.15+20261021; Next.js 16.4.2. Interpreter/framework executable paths were inside the extracted bundle.

### Packaging failures and their final disposition

Earlier internal archives are superseded and must not be distributed as this candidate. Actual inspection/launch found and repaired: generated build-machine paths/non-relocatable unused console scripts; Electron's unpackaged identity caused by the unchanged Electron executable name; a broad filter dropping required next/dist/trace runtime code; signed-bundle route-cache writes after license navigation; and omitted standalone dependency notices. These repairs are separately committed. The final UI/native/lifecycle and independent immutable-bundle checks exercised the corrected d2ae854 artifact. The unchanged packaged-app/security guards remain enabled.

Two lifecycle harness assumptions also failed before correction: treating Next's rewritten process title as its executable path, and comparing generated workspace export timestamps byte-for-byte. Actual executable paths are now measured through the operating system; only the known exported_at field is normalized for that one comparison. These were test-driver corrections and did not change the application.

### Remaining gates and explicit NOT_RUN

- Actual authenticated OpenAI/DeepSeek/local generation, real planning/proposal outputs, live PubMed API search/test, new embeddings, model downloads and scientific/human usefulness validation: **NOT_RUN** for this release. Saved-map reuse and software vectors are not new embedding execution.
- Physical OS sleep/wake: **NOT_RUN**. A resume handler exists, but its presence is not an observed sleep/wake pass.
- Source beta: macOS arm64 tested; Linux installation unverified; Windows unsupported. Desktop prototype: macOS arm64 only; no cross-platform claim.
- Desktop base includes the core runtimes, not BGE/optional ML packages, weights or an optional-ML installer. New maps require the source beta's explicit optional setup/configuration route; saved maps work in both.
- Desktop signatures are ad-hoc, not Developer ID or notarization. Downloaded/quarantined-device installation, complete binary/transitive SBOM and source obligations remain unverified. Seven upstream full-notice gaps remain explicit public-desktop distribution blockers; see the desktop guide.
- Existing cookie/profile/expiry and access-recovery limitations remain. No OS keychain, authenticated transfer, account recovery or automatic updater is claimed.
- No push, tag, release publication, deployment, website change or paid resource/call was performed. Detailed private QA reports remain local; only normalized non-private summaries accompany review assets.

See [candidate identities, hashes, capability matrix and review gates](releases/v0.3.0-beta.2-review.md). All later documentation-only commits describe these exact assets rather than silently rebinding them.


### Final preservation check

Read-only local ref/status and GitHub checks confirmed main `a506ae05fc19c21a1d80beabc26bfc831582441d`, frozen MVP/preview `cb98e3ef843982ebe0cfb65631d8f923a1a4007b`, published Track A `105d98f87ced3e415f77d36305dba7244fc3cf7f` and paused Track B `ce56f9107e9c786ed2fc72b5fd737e6586409a09` unchanged. The original working checkout's 153 baseline status entries were preserved; an additional unrelated untracked document appeared during this work and was not read or edited. Clean published-A/paused-B worktrees remained clean. This is ref/status preservation evidence, not a whole-disk private-database hash audit.

All three local beta.1 artifact hashes matched their frozen values; GitHub's stored asset digests and original published prerelease/tag/source also matched. Published binaries were not downloaded again. Successor beta.2 and desktop-preview tags were absent. No remote write, research-database read, Track B launch, website change or Render operation was involved in this preservation check.
