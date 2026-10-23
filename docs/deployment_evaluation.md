# Hosted preparation — executed checks

Date: 23 October 2026. Baseline: `codex/mvp-v0-3` at
`4aa28790c25e419b78be70f57ffebd690a391ba1`. Main remains
`a506ae05fc19c21a1d80beabc26bfc831582441d`. This report records local
implementation checks before source release. Subsequent clean-checkout checks of
the committed revision are reported separately. No provisioning, paid service,
cloud deployment, DNS change, portfolio publication or local research upload was
performed. See the
[operator guide](deployment.md) and [portfolio handoff](deployment_portfolio_handoff.md).
The temporary Docker container, TLS ingress and isolated browser were stopped
after verification. Protected QA volumes, backups and ignored evidence remain;
the original local applications were left running and unchanged.

## Evidence boundaries

| Evidence | Actual result |
| --- | --- |
| Existing MVP tests | 730 passed, 0 failed/skipped; 39.66 s |
| Full API + deployment collection | 305 passed, 0 failed/skipped; 238.04 s |
| Post-backup-fix deployment rerun | 50 passed, 0 failed/skipped; 4.10 s; overlaps 49 tests above and adds one WAL regression |
| Final frontend | 157 passed, 0 failed/skipped; 2.737 s |
| TypeScript | PASS |
| Production Docker builds | PASS for local `linux/arm64` and `linux/amd64`; final successor is amd64 |
| Real local HTTPS production-container workflow | PASS; details below |
| Isolated actual Chrome over local HTTPS | PASS for admission, cookies, question draft, renewal, logout/relogin and refresh |
| Actual hosted Render execution | NOT_RUN |
| Live PubMed / Europe PMC | NOT_RUN |
| Real model / new embedding computation | NOT_RUN; hosted capability disabled |
| Human usefulness / scientific support validation | NOT_RUN |

The last backup regression was added after the full API collection began. It was
run in the focused deployment rerun; the expensive populated-capacity test was
not repeated for an operations-only fix. Counts above are not additive without
deduplicating that overlap. Two inherited TestClient deprecation warnings and
frontend react-test-renderer deprecation warnings remain.

## Actual production process and HTTPS checks

The test ingress terminates real TLS for the reserved local test origin
`https://litrev.example.test:9443`, then forwards to production Next inside Docker.
The client verifies the fixture CA and maps only that `.test` name to loopback.
No OS trust/hosts changes or actual public application URL are involved.
The ingress strips supplied forwarding headers and supplies its own HTTPS
confirmation. Its streaming implementation permits an honest slow-body check;
it does not buffer the entire request first.

All test data came from the attributed public saved example or explicitly
synthetic, unassessed values. The developer's research state was never mounted.
Two private cookie jars emulate separate HTTP clients; they are not a claim of
actual browser cookie/UI validation.

The initial HTTPS create walkthrough passed in **97.313 s / 432 requests**:

- Admission denied anonymous session/capability/workspace requests. Correct
  invitations admitted two independent sessions without shared workspace access.
- Thirty actual retained public full texts were prepared; one six-field board
  received 180 manual, explicitly unassessed cell submissions, one explicit
  revision (181 revisions total), and an unfinished cell/UI draft.
- Exact source inspection, source/history binding, 180-row CSV and audit JSON
  were checked. Audit JSON measured 1,322,381 bytes.
- Thirty requested passages returned 30 exact retained results; a precomputed
  30-point map remained distinct from new embedding/fitting.
- Sixteen access-denial checks covered other-session resources, Host, Origin,
  research CSRF and private exports. Invite login/logout rely on exact Origin,
  not the later research CSRF token; those are separate gates.

Restart verification passed in **1.598 s**, preserving the same research cookie,
CSRF/session registry, exact audit export, source history, pending drafts, map
digest, completed job and passage run. Replacement by an amd64 successor image
and restoration to a **separate** directory passed in **2.651 s** with those same
bindings. The original temporary QA directory was retained.

The final frozen-image HTTPS verification passed in **20.316 s / 38 requests**:

- All saved-state/reopening/export checks and the sixteen access denials passed.
- Public health returned 200; a direct-page request returned the admission shell.
- Five saved-map neighbors loaded using retained vectors in the focused runtime;
  the map digest did not change and no new model was invoked.
- A small synthetic raw CSV import returned 200; another session's read returned
  404. Five MiB plus one byte returned 413; unsupported media returned 415. No
  rejected import record was created and no identifier/provider resolution ran.
- An anonymous POST delivered its second byte after sixteen seconds and received
  **408** (16.014 s), verifying the bridge's fifteen-second body deadline through
  streaming HTTPS. No admission or research operation began for that request.

An isolated **Chrome 155.0.8059.85** browser also passed against the final image.
It used a temporary profile, exact test-host resolver rule and per-process
certificate SPKI pin, with no OS hosts/CA or user-browser profile changes.
Unauthenticated direct refresh showed the admission shell without requesting a
research session. Chrome stored both separate cookies as Secure/HttpOnly/Strict
and host-only. In one fresh public QA workspace, renewal preserved the identical
mounted question editor DOM node, its edited value and URL. Ending admission
removed only the admission cookie; relogin and direct refresh reopened the same
workspace and durable edit. This was a question-draft browser journey, not a new
180-cell browser walkthrough. The dedicated browser/profile was cleaned up;
sanitized screenshots and `browser-verification.json` remain ignored locally.

Actual process checks additionally refused missing mount and duplicate instance
startup (exit 2), refused backup while the app held its lock (exit 2), stopped on
SIGTERM with exit 0 and reaped both groups, and converted API SIGKILL into
supervisor exit 1 while stopping Next. Restart after that forced failure retained
the acknowledged research state. The independent job test simulates an abandoned
lease and proves stage retention/recovery, stale-owner rejection and deletion
fences; it is not a claim that a provider call was interrupted exactly once by
the process-kill check.
Actual deletion of the CLI-owned public QA workspace then passed in **0.658 s**:
its workspace, board, map and preparation job returned 404, its workspace list
was empty and the separate browser's workspace remained unaffected.

## Packaging, durability and resource observations

The final deny-by-default build-context audit admitted **210 files / 7,538,323
bytes**, including 67 explicitly allowlisted public corpus/map/attribution files.
It admitted zero local env/database/Git/research-state/cache/test/unrelated paths.
Runtime uses UID/GID 10001, one API process, internal loopback only, and a verified
mounted data root. A fresh Docker volume inherited the correct directory owner;
another platform's root-owned mount still needs an authorized initialization.

Node 24.19.0 and Python 3.12.12 official image manifests are digest-pinned; pnpm
10.20.0 installs the frozen existing application lock. No JavaScript package or
lock change was required. The new Python production list selects already pinned
HTTP runtime packages; Streamlit, model weights and GPU libraries are absent.

The frozen amd64 image has local image ID
`sha256:ea75a82b8d57918ed82ff22b1d7cea3cbd05ef99c2412350c1f111f269fd8e05`.
Docker image inspection measured **921,357,579 bytes**. Runtime inspection found
approximately 344 MiB production node_modules, 31 MiB Next output, 31 MiB Python
environment, 1.3 MiB Python source and 5.3 MiB public examples. The Next build
output includes about 25 MiB cache that could be optimized separately. An earlier
predecessor/cache size observation is not used as the final image size.

Ten Docker samples during the **arm64** 30-paper/180-cell create workload observed
**239.8–277.4 MiB** combined container memory and **94.70–117%** CPU. These are
local Docker Desktop observations, not a Render minimum, concurrency estimate,
model-server measurement or performance SLO. The amd64 successor was run through
local emulation. No cheapest-plan or production-hardware sufficiency is claimed.

The stopped-state backup/restore checked **10 files / 41,738,240 bytes**, `0600`
archive permissions, a new `0700` restore directory, exact source/history bindings
and preservation of the original QA copy. WAL-bearing databases have a focused
regression: integrity checking happens on the private snapshot copy and cannot
create journals in the source tree. Both the protected local operator backup and
QA volume are separate from the original research stores. Off-service remote
retention, encryption policy and operational recovery scheduling remain operator
work; nothing was uploaded.

## Commands actually exercised

Commands below use portable variables for machine-specific test interpreter,
Node, fixture certificate and private test-state paths. The exact executed paths,
logs, image/context evidence and reports remain under the ignored
`.mvp-web-state/ui-checks/hosted-2026-10-23/` directory. Never publish the private
cookie state or invitation file.

```sh
# Repository root, with live/provider credentials stripped and local defaults.
MVP_DEPLOYMENT_MODE=local MVP_PROPOSALS_ENABLED=0 MVP_SEARCH_PLANNER_ENABLED=0 \
  MVP_MAP_ENABLED=0 "$MVP_TEST_PYTHON" -m pytest tests/mvp -q
.venv-map/bin/python -m pytest tests/web_api tests/deployment -q
.venv-map/bin/python -m pytest tests/deployment -q

# apps/web
"$NODE_BIN" --import tsx --test tests/*.test.ts tests/*.test.tsx
"$NODE_BIN" node_modules/typescript/bin/tsc --noEmit --incremental false

# Repository root; actual production build also runs inside these images.
docker build --platform linux/arm64 -t litrev-hosted:local .
docker build --platform linux/amd64 -t litrev-hosted:local .

# Existing API contracts regenerated without live/model configuration.
.venv-map/bin/python scripts/export_web_openapi.py
# apps/web
"$NODE_BIN" node_modules/openapi-typescript/bin/cli.js lib/openapi.json -o lib/generated-api.ts

# Repository root, local TLS fixture and FRESH public-example test state only.
.venv-map/bin/python scripts/hosted_smoke.py create \
  --origin https://litrev.example.test:9443 --ca-file "$TEST_CA" \
  --invite-file "$TEST_INVITE_FILE" --state-file "$PRIVATE_TEST_STATE" \
  --report "$CREATE_REPORT"
.venv-map/bin/python scripts/hosted_smoke.py verify \
  --origin https://litrev.example.test:9443 --ca-file "$TEST_CA" \
  --state-file "$PRIVATE_TEST_STATE" --report "$VERIFY_REPORT" \
  --check-imports --check-slow-body
```

Production backup and restore commands were run via Docker entrypoint override
with the stopped application's fresh QA volume and a separate operator backup
volume. Their implemented command forms are in the operator guide. They are not
an instruction to run against the only local research copy.

## Failures, corrections and remaining gates

- The first Docker build caught a header-test TypeScript inference error; the
  test's header records were typed explicitly and later builds/typecheck passed.
- An early context rule admitted host node_modules. Local env/DB/research files
  were excluded; context rules were corrected and the full final context audited.
- Two existing frontend tests initially asserted before asynchronous hashing and
  acknowledged UI updates completed during parallel load. They now wait for
  bounded observable acknowledgments, preserving their actual assertions. The
  final 157-test run passed; no product behavior was changed to hide the failures.
- Independent review found the slow-body deadline gap, then a real TLS timeout
  check confirmed its correction. Backup validation's SQLite-journal side effect
  was fixed and given a WAL regression before the final restore checks.
- The isolated Chrome launch initially failed inside the execution sandbox.
  A scoped process elevation succeeded without changing browser or OS security
  settings. An initial refresh assertion raced reload; waiting for the rendered
  page corrected the test. The initial browser NOT_RUN record is explicitly
  superseded by the final browser report.
- No actual Render ingress/domain/disk/restart has been exercised. The template
  assumes Render's managed network boundary; alternate proxies need review.
- Actual browser checks are recorded separately from HTTP cookie-jar/React tests.
  Browser upload UI, full keyboard traversal, concurrent researcher load and a
  human research pilot are not inferred from these software checks.
- New maps/generation are disabled; live discovery still requires an operator's
  private contact configuration and separately authorized provider smoke.
- No paid service or application URL exists. Instance/disk cost approval,
  deployment, actual-domain smoke, protected off-service backup retention and
  only then the portfolio link remain separate operator actions.

## Preservation and changed-file scope

The preservation baseline recorded 150 preexisting local files and four original
SQLite databases. README's current-MVP introductory section was intentionally
updated to remove stale planned-board claims and describe deployment preparation;
its preexisting unrelated retrieval-experiment paragraph is retained. The
`.gitignore` task changes allow the hosted configuration template and exclude
private keys/certificates, runtime databases, backup archives, model caches,
browser session exports and private runtime directories. The user's unrelated cache exclusion is preserved outside the
release staging scope. The other
**148 baseline files** remain byte-identical. All four original SQLite file
hashes and **1,467 logical rows / 46 tables** remain unchanged at the implementation checkpoint, as do HEAD, branch
and main. Supplied briefs and private snapshots were preserved. No existing
research schema, retrieval profile, source anchor, assessment, saved map or export
schema was migrated.

The implementation adds deployment boundary/operations and UI admission only;
it retains Next.js, FastAPI, SQLite and the original research services. The
complete changed-file manifest is recorded below and with the ignored local
preservation evidence. README and `.gitignore` contain preexisting unrelated
hunks: release staging includes only the task hunks in those two files,
not their complete working-tree diff.

## Exact changed files

40 task-touched paths: 38 fully task-owned files and the two coedited files
identified above. Supplied briefs, private state, build outputs and unrelated
assets are excluded.

- `.dockerignore`
- `.env.hosted.example`
- `.gitignore`
- `Dockerfile`
- `README.md`
- `apps/web/app/api/v1/[...path]/route.ts`
- `apps/web/app/healthz/route.ts`
- `apps/web/app/layout.tsx`
- `apps/web/app/page.tsx`
- `apps/web/components/admission-gate.tsx`
- `apps/web/components/workspace-app.tsx`
- `apps/web/lib/api.ts`
- `apps/web/lib/bridge.ts`
- `apps/web/lib/deployment.ts`
- `apps/web/lib/generated-api.ts`
- `apps/web/lib/openapi.json`
- `apps/web/tests/hosted-admission.test.tsx`
- `apps/web/tests/hosted-boundaries.test.ts`
- `apps/web/tests/usability-discovery.test.tsx`
- `apps/web/tests/usability-passage-count.test.tsx`
- `docs/deployment.md`
- `docs/deployment_evaluation.md`
- `docs/deployment_portfolio_handoff.md`
- `requirements-hosted.txt`
- `scripts/hosted_backup.py`
- `scripts/hosted_smoke.py`
- `scripts/run_hosted.py`
- `src/web_api/app.py`
- `src/web_api/deployment.py`
- `src/web_api/hosted_admission.py`
- `src/web_api/hosted_operations.py`
- `src/web_api/map_routes.py`
- `src/web_api/proposal_routes.py`
- `src/web_api/search_plan_routes.py`
- `tests/deployment/https_test_ingress.py`
- `tests/deployment/test_hosted_boundary_independent.py`
- `tests/deployment/test_hosted_operations.py`
- `tests/deployment/test_hosted_supervisor.py`
- `tests/deployment/test_packaging_manifest.py`
- `tests/web_api/test_hosted_security.py`
