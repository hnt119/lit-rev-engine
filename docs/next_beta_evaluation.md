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

Implementation and independent execution are still in progress. Do not read the acceptance tables as passed checks. Exact commands, outcomes, failures, skips and extracted-package/runtime measurements are appended when executed.

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

At this point extracted-successor installation, actual browser walkthrough and desktop bundle/runtime measurements are still pending. The final root report must record them separately and must retain unsupported/not-run labels where applicable.

### Follow-up checks after the identified repairs

- `python -m pytest tests/web_api/test_collection_workflow_independent.py::test_collection_map_in_http_uses_explicit_origin_and_keeps_saved_map_hashes tests/web_api/test_cloud_transport_independent.py tests/web_api/test_runtime_settings_independent.py tests/web_api/test_generation_consent_independent.py -q -p no:cacheprovider`: **58 passed, 0 skipped, 4.96 s**. This includes all 57 new independent tests plus the affected retained-map regression. The fresh environment now has the existing pinned numerical dependencies; no model weights were downloaded and the map test uses software vectors.
- An earlier full HTTP-suite run, started before the final new tests existed, completed **339 passed / 1 failed in 276.03 s**. Its only failure was the retained collection-map test before those optional numerical dependencies were installed. The targeted rerun above resolves that failure. It is not represented as a fresh final full-suite pass.
- `node --import tsx --test tests/research-settings.test.tsx tests/settings-navigation.test.ts` from `apps/web`: independently rerun **10 passed, 0 failed, 0 skipped, 0.304 s**. This covers no provider calls on form activity, key clearing, CAS rebase, disable-AI independence, exact cloud scope/consent, new-search defaults versus retained drafts, explicit fresh attempt after failure and opaque settings return navigation. These are rendered component/contract tests, not actual browser usability observations.

The HTTP suite emits existing Starlette/httpx and AnyIO deprecation warnings; component tests emit the existing React test-renderer deprecation warning. No dependency upgrade was performed to suppress them.
