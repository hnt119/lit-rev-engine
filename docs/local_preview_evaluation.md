# Local preview evaluation — 24 October 2026

This is the retained **preview .1** evaluation. The later comparison/passage
workflow and working-tree **preview .2** have their own historical results in
[comparison_passage_roundtrip.md](comparison_passage_roundtrip.md).
The committed source freeze and new release artifacts are documented in
[the preview .2 release notes](releases/v0.3.0-local-preview.2.md).

The prepared **0.3.0-local-preview.1** source package passed fresh macOS setup,
production startup, public-example API checks, application-folder replacement,
and immediate controlled restart. Actual browser checks separately confirmed
saved question drafts, the same workspace, and the public thirty-paper map.
The static portfolio overlay also passed an isolated export and browser check.
No release was committed, pushed, published or deployed in this checkpoint.

This is a **local preview — setup required**. Python, Node, model weights and
private research data are not bundled. Setup downloads locked dependencies and
builds the application. These are software and interaction checks; no human
usefulness study or scientific/clinical validity assessment was performed.

## Review files and startup

The task changes exactly these nineteen paths; the preexisting README and
`.gitignore` user changes are excluded:

| Status | Paths |
| --- | --- |
| Modified | `scripts/run_web.py`; `apps/web/lib/bridge.ts`; `apps/web/tests/boundaries.test.ts` |
| New packaging scripts | `scripts/local_preview.py`; `scripts/build_local_preview.py` |
| New guides | `docs/local_preview.md`; `docs/local_preview_evaluation.md` |
| New evaluation/tests | `tests/local_preview/test_launcher.py`; `tests/local_distribution/check_installed_preview.py`; `tests/local_distribution/audit_source_archive.py` |
| New overlay sources | `showcase/portfolio/README.md`; `showcase/portfolio/scripts/build_public_demo.py`; `showcase/portfolio/src/components/LiteratureShowcase.tsx`; `showcase/portfolio/src/components/LiteratureShowcase.module.css`; `showcase/portfolio/src/content/projects/literature-review-engine.mdx`; `showcase/portfolio/src/data/literature-showcase.json` |
| New prepared download copies | `showcase/portfolio/public/downloads/lit-rev-engine-0.3.0-local-preview.1.zip`; `showcase/portfolio/public/downloads/lit-rev-engine-0.3.0-local-preview.1.manifest.json`; `showcase/portfolio/public/downloads/lit-rev-engine-0.3.0-local-preview.1.SHA256SUMS` |

The local review application is running at `http://localhost:3088/`; the isolated
static export is at
`http://localhost:3099/projects/literature-review-engine/`. These are loopback
review servers, not published services. Follow `docs/local_preview.md` to set up
and launch an extracted download; retain the external data directory when
replacing application files.

## Artifact and environment

| Item | Observed value |
| --- | --- |
| ZIP | `lit-rev-engine-0.3.0-local-preview.1.zip` |
| SHA-256 | `787fa16fde6b7a6def62488f4ca0342cec7f4e8a4514b1d90b1420b219ad1c98` |
| Size | 1,724,730 bytes; 211 files; 7,597,989 uncompressed bytes |
| Source provenance | Baseline `02fa59fc9fafb8550354d64b696d1c7262d3924f` plus reviewed, uncommitted working-tree changes identified by file hashes |
| Actual installation platform | macOS 26.6.2, arm64; Python 3.12.7; Node 24.19.0; pnpm 10.20.0 |
| Installed application | Extracted source package, private `.venv-preview`, production Next.js build |
| Fresh QA origins | Browser `http://localhost:3088`; API `http://127.0.0.1:8798` |
| QA data | A new external directory under `/private/tmp`, never an original research store |

The independent archive audit verified safe ordinary-file paths, exact manifest
and sidecar contents, all file lengths/hashes, the source snapshot digest, and
67 approved public-example files representing thirty papers. No runtime,
`node_modules`, build output, environment file, database, browser state, private
export, model weight or observed credential was distributed. A separate
synthetic-canary check created three unique untracked files under `src/mvp`
(environment, private-key marker, arbitrary JSON); a throwaway build excluded
all three, and the canaries were removed without replacing existing files.
This is an allowlisted source package, not a publisher-signed binary. A final
rebuild in a separate ignored output directory reproduced the exact ZIP bytes;
`shasum -a256 -c` also passed for the ZIP and manifest sidecar.

Earlier candidates and reports remain historical. The current ZIP is the hash
above; the prior `db8bb7…` candidate predates the immediate-restart fix.

A final independent extraction of the exact `787fa16f…` ZIP into another empty
application folder passed setup in **14.544 seconds**. There was no existing
virtual environment, `node_modules` or frontend build in that folder. Deliberately
invalid inherited hosted settings were present; setup still selected local
mode. Normal dependency caches were available. This setup did not launch a
second application, migrate research data or call a provider/model. Its raw
result is retained as `exact-final-fresh-setup.json` in ignored QA evidence.

## Installed workflow and access checks

The independent opt-in harness used its own two cookie jars, separate from
actual browser QA. The create phase passed **65 requests in 1.879 seconds**:

- Loaded the attributed public thirty-paper saved example and its existing
  thirty-point map, including saved-map neighbors. No embedding was computed.
- Prepared three papers and created three editable comparison fields: nine
  cells, ten explicitly submitted revisions, and an additional unsubmitted
  draft. All semantic judgments stayed `unassessed` software-fixture values.
- Retrieved twenty-one per-paper/per-field candidates, inspected seven exact
  candidate quotations and canonical source bindings, and ran lexical passage
  retrieval returning five passages. Candidates remained distinct from manual
  support judgments.
- Retained explicit null/partial-context missing-information states for two
  cells without candidates. These do not assert absence from a whole paper.
- Recorded exact draft, revision/history, map, retained-source, saved-run, CSV
  and JSON digests for later comparison.
- Confirmed thirteen denial checks: another session could not read the known
  workspace, drafts, map, board, exports or source context, or edit its draft;
  wrong CSRF, API Host and Origin were refused; a declared request size of
  1 MiB + 1 was rejected with 413 before uploading its body.

The local cookie was host-only, HttpOnly, `SameSite=strict`, `Path=/`, and
persisted with `Max-Age`; it correctly lacks `Secure` on loopback HTTP. These
checks exercise local browser/workspace ownership, not hosted user accounts
or protection from another process using the same operating-system account.

Three verification phases passed with the original cookie jars:

| Phase | Result | Requests | Time |
| --- | --- | ---: | ---: |
| Fresh application-folder replacement with the same external data | PASS | 26 | 0.321 s |
| Rehydration after setup from the final restart-fixed ZIP | PASS | 26 | 0.328 s |
| Immediate controlled stop/relaunch of that final installation | PASS | 26 | 0.313 s |

Each compared the original UI/cell drafts, ten submitted revisions and history,
exact CSV/JSON, source bindings, saved run, map and neighbors, and repeated the
thirteen denial checks. Candidate/inspection totals in verification reports
refer to the create phase; verification does not regenerate the board. The
external directory's twelve research/control files remained byte-identical
before and after replacement setup, including the final setup. No research
files were copied into the replacement application directory.

## Launcher and lifecycle checks

Fresh setup and launch were run with synthetic hostile inherited hosted,
provider and model settings. The children reported local mode, unavailable live
retrieval and disabled new map fitting; model/provider calls were zero. Launch
starts production servers on loopback and waits for both real child-owned
listeners and readiness endpoints. An actual occupied API port was refused
without terminating or attaching to the existing listener. Controlled stop
returned zero and stopped the owned servers.

Independent read-only `ps`/`lsof` inspection confirmed that the actual API and
Next.js children inherited both the installation and external-data owner lock
file descriptors. A separate launcher test kills a synthetic controller and
checks that surviving owned children keep those locks, so another-port launch
and setup are refused. The actual research application was not force-killed
for this check. Automatic stale-PID killing is intentionally absent; orphan
recovery remains a documented manual operation.

Review found and corrected external-path traversal handling and descendant
cleanup, with focused regressions. A later actual immediate restart initially
failed with a port-unavailable message after a successful controlled stop.
An isolated TCP active-close fixture reproduced the old preflight's plain-bind
failure and the fix's success. Port preflight now uses `SO_REUSEADDR`; a real
foreign listener still causes refusal. No sleep workaround or `SO_REUSEPORT`
was added. The exact TCP state during the earlier installed-app failure was
not captured. The final installation subsequently passed actual immediate
stop/relaunch without an intentional waiting period.

## Software tests and commands

The final affected Python suite passed **77 tests, 1 intentional opt-in Docker
skip, 2 inherited deprecation warnings, in 4.30 seconds**. This includes the
26 launcher tests. All **157 existing frontend tests passed**, with no skips;
the focused local/hosted bridge tests also passed. The bridge change only adds
exact `localhost` support to the local HTTP-origin parser. Hosted policy was
not relaxed. The broader engine/PubMed/model evaluations were not rerun for
this packaging checkpoint.

Commands used, from the applicable checkout or extracted application folder:

```sh
.venv-map/bin/python -m pytest tests/local_preview tests/deployment -q
# In apps/web, using the selected Node runtime:
node --import tsx --test tests/*.test.ts tests/*.test.tsx

python3.12 scripts/local_preview.py setup --node "$NODE" --pnpm "$PNPM"
python3.12 scripts/local_preview.py launch --data-dir "$QA_DATA" \
  --api-port 8798 --web-port 3088 --browser-host localhost --no-browser
python3.12 scripts/local_preview.py status --data-dir "$QA_DATA"
python3.12 scripts/local_preview.py stop --data-dir "$QA_DATA"

python3.12 tests/local_distribution/audit_source_archive.py \
  --archive .mvp-web-state/releases/0.3.0-local-preview.1/lit-rev-engine-0.3.0-local-preview.1.zip \
  --report /private/tmp/local-preview-archive-audit.json
python3.12 tests/local_distribution/check_installed_preview.py verify \
  --origin http://localhost:3088 --api-origin http://127.0.0.1:8798 \
  --qa-root /private/tmp/lre-local-preview-api-20261024 --confirm-public-qa \
  --report /private/tmp/local-preview-reopen-verification.json
.venv-map/bin/python showcase/portfolio/scripts/build_public_demo.py --check
```

`NODE`, `PNPM` and `QA_DATA` identify the explicitly selected runtimes and fresh
external QA directory; their actual local paths and setup logs are retained in
ignored evidence. The API harness `create` phase requires a fresh private QA
state file; subsequent `verify` phases reuse it. Its original-application port
blocklist prevents accidentally targeting 3000, 3005, 8765 or 8769. Neither
independent harness launches or stops application services.

The first API attempt hit a test-client `BrokenPipeError` when urllib continued
sending an oversized body after early server rejection. Its failed report is
retained. The corrected probe reads the early 413 after declaring the oversized
length; it does not claim a completed megabyte upload or request-rate testing.

## Actual browser and static-demo checks

Actual in-app browser checks, recorded separately from API software checks,
created a saved-example workspace, edited a question until the saved indicator
appeared, opened thirty papers and the precomputed map, and closed/reopened the
tab. Refreshes using the same cookie after application replacement and final
immediate restart retained the same workspace, exact question draft and map.
The observed desktop viewport was 1280 × 720 with no horizontal overflow.
Automatic OS browser opening was tested only through mocked sequencing; QA
opened the browser after readiness with `--no-browser`. Mobile was not tested.

The overlay is confined to `showcase/portfolio`; the actual website checkout
was not modified. Independent checks verified three retained public CC BY 4.0
papers, nine unique exact canonical quotation anchors, attribution/source
hashes, and three explicit partial-context missing-information cells in a
17,810-byte static projection. No backend calls, browser storage or raw HTML
rendering were observed in the overlay source.

An isolated website checkout with fresh locked dependencies passed its final
static build in **5.231 seconds**, including TypeScript checking. Export checks
passed **21 public routes, 138 files, 527 local references and 28 fragments**;
eight external targets were explicitly skipped. Actual local HTTP requests
returned 200 and byte-identical final ZIP, manifest and checksum assets. The
exported HTML showed the final hash and omitted the previous candidate hash.

Actual static browser interactions checked filtering to one of three papers,
selecting a diet cell and its exact quotation/context/offsets/source hash, and
keyboard Return on a missing-information cell. The current download metadata
and links were visible. Browser-triggered file saving was not tested; actual
HTTP download bytes were checked separately.

Earlier static-build attempts are retained: an unexplained Turbopack stall,
a webpack fallback failure on baseline MDX metadata, and an export rejected
for missing `SITE_URL`. A fresh locked install and correctly configured
`NEXT_STATIC_EXPORT=true SITE_URL=https://hnt119.github.io` build passed; the
final checksum-only refresh was rebuilt and checked again. No cause is claimed
for the initial stall.

## Preservation and remaining limits

The final read-only preservation audit passed: all **148 original unrelated
files**, four original SQLite file hashes and all **46 tables / 1,467 row
digests** were unchanged. Immutable query-only reads created no WAL/SHM files.
Of 46 protected hosted/operator artifacts, **45 remained byte-identical**; the
sole authorized exception is the exact two-line local-origin bridge change.
Dockerfile, operator-home changes, inactive Render drafts and maintenance
payload remained unchanged. README, existing user hunks, refs and Git index
were unchanged. Feature HEAD/origin remain `02fa59f`; main/origin remain
`a506ae0`. The actual website is clean on main at `3a03ea54`, with all 81 tracked
file hashes and its index unchanged. Original applications on 3005/8769 were
not used as QA targets.

Use a stable browser hostname/profile for reopening: cookies are host-scoped,
not port-scoped. Independent data directories need distinct browser profiles
or a deliberate hostname boundary. Clearing/expiring cookies loses workspace
access; a workspace ID alone is not recovery. No cross-device accounts or
automatic recovery is provided. Replacing files with the same preview version
was checked; future-version migrations were not. Fresh Linux installation is
unverified and Windows is unsupported. No live literature search, new embedding,
generation, paid inference, Render resource, hosted deployment, publication or
human usefulness validation was run. The Docker image opt-in test was skipped
in this local checkpoint; its earlier operator-home results remain historical.

Raw reports, setup/build/test logs, browser observations/screenshots, candidate
history and private-data-preserving hashes are retained locally under
`.mvp-web-state/ui-checks/local-preview-2026-10-24/`. Key final records are
`archive-final-current-audit.json`, `api-create-final.json`,
`api-after-portfix-replacement.json`, `api-after-immediate-restart.json`,
`final-installed-preview.json`, `final-local-and-hosted-tests.log`,
`frontend-tests.log`, `browser-verification.json`,
`overlay-final-current-audit.json`,
`website-static-updated-final-validation.json` and `preservation-final.json`.
Cookie/CSRF state stays in a separate private `/private/tmp` directory and is
not part of the source package or showcase.
