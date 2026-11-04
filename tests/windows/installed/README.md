# Issue 18 — consolidated hosted Windows result

**BLOCKED. All four authorized attempts are complete; no further run is authorized.**
The fourth attempt passed real NSIS preprocessing but failed full compilation.
No completed repaired Setup.exe, candidate receipt or installer SHA-256 exists.
No application has been installed or launched by this trial.

[Draft PR #31](https://github.com/hnt119/lit-rev-engine/pull/31) ·
[Issue #18](https://github.com/hnt119/lit-rev-engine/issues/18).
One implementer and a non-author verifier independently reviewed the frozen
execution source, exact release identities, real logs and assertions. The verifier
performed no implementation or extra Windows execution.

## Latest authorized run and exact identities

[Run 41796027624](https://github.com/hnt119/lit-rev-engine/actions/runs/41796027624)
/ [job 126460230840](https://github.com/hnt119/lit-rev-engine/actions/runs/41796027624/job/126460230840),
push event, attempt 1, **FAILURE**, 07:59:00–08:02:04 UTC on 4 November 2026:
**184 seconds**. There was exactly one run on the new execution branch.

| Identity | Value |
| --- | --- |
| Frozen infrastructure / repair execution SHA | `b79e9164b46e4e85e4782e07ec448d6f6bf7eebf` |
| PR head at resumption | `7051b3663db6f200a364aee46122080e67a44ec7` |
| Main / infrastructure base, preserved | `abd529dbb6dabc94312ebb5e7d4a7909d44d629d` |
| Accepted Core MVP ancestor, preserved | `1c6744de2ae0149f96f2063120b629a1f0eb17c7` |
| Immutable application source | `664b86d4ed510c3d16982b5813b27e6bd1150129` |
| Published application version / native build | `0.3.0-windows-experimental-beta.2` / 3003 |
| Original Setup.exe bytes / SHA-256 | 195492146 / `75595d013fbdf4694301a00dd0e233a6b53e47c6cf5fb3713d0d0e7aa1e58359` |
| Verified installed-file manifest SHA-256 | `7c6a2627831f1082a9163e599415c1f1f239036a3713912609fd95e5a68e5e34` |
| Exact installer repair patch SHA-256 | `e585168f66ce97e2d51626eb308b345b5249313a3d14c22c86c29a9a7abed807` |
| Compiler | Official NSIS **3.13**, Windows portable ZIP |
| Compiler ZIP bytes / SHA-256 | 2363925 / `ba63dffc4410ee89193e1cb5a41989991bd77c61068da17e3156d136b7b0b3d8` |
| Attempted candidate identity | `issue18-installer-root-rc2` |
| Completed repaired installer size / SHA-256 | **NOT_AVAILABLE — full compilation failed** |

The [published release](https://github.com/hnt119/lit-rev-engine/releases/tag/v0.3.0-windows-experimental-beta.2)
and its original assets remain unchanged. Source/tag/manifests and actual original
installer bytes were independently verified. The payload declares Electron45.0.0
and Python3.12.15+20261021; their application execution is NOT_RUN. This is strictly
an installer-only repair of that payload, **not current-main/Core-MVP acceptance**.

## Run 4: expected versus actual

| Stage | Actual evidence |
| --- | --- |
| Immutable source, original installer, pinned compiler | PASS |
| Native missing/existing-path mechanics regression | PASS |
| Unchanged application payload | PASS: all **7451 files**, sizes/hashes and complete manifest file set |
| Retained agreement include and displayed terms | PASS: actual include equals git bytes; full terms hash matches release |
| Actual compiler preprocessing with include/guard assertions | **PASS** |
| Complete installer compilation | **FAIL**, process exit 1, diagnostic `compiler_error` |
| Fresh run-bound candidate receipt and checksum | NOT_RUN; no receipt produced |
| Candidate selection / installed trial | BLOCKED; skipped without fallback to the published installer |
| Five independent current-source Windows boundary tests | PASS, 0.92s; not installed-payload credit |
| Always-run sanitized build and skipped-trial reports | PASS |

[run-4-build.json](run-4-build.json) is the actual allowlisted build report from
job logs. [run-4-trial.json](run-4-trial.json) transcribes the actual skipped trial
and BLOCKED/NOT_RUN fallback into an explicit acceptance matrix; it is not an
application-generated acceptance report. The build stage lasted83.7s.

**Known evidence defect:** `build_candidate.py` captured compiler output but
retained only an error category and exit code. The failing source line/message
was discarded and cannot be recovered from this job's logs or nonexistent
artifacts. The new full-compile root cause is therefore **unresolved**. It must
not be attributed to the earlier include error, which actual preprocessing now
passed. This over-redaction is an automation/diagnostic defect, not an application
failure or proof that the installer repair works. No speculative repair or fifth
attempt was made after this result.

## Full acceptance status

| Requested acceptance | Run 4 result |
| --- | --- |
| Full RootGuard at fresh absent final directory | NOT_RUN |
| Protect unrelated directory / marker without registration | NOT_RUN |
| Reject alternate destination and junction/reparse path | NOT_RUN |
| Existing-installation / same-version policy and preservation | NOT_RUN |
| Agreement initially unchecked, decline/cancel, affirmative acceptance | NOT_RUN |
| Per-user installation, all installed files, shortcut, uninstall registration | NOT_RUN |
| Installed executable/Start launch and bundled runtimes | NOT_RUN |
| Offline example, three public papers and three fields | NOT_RUN |
| Exact source inspection/attachment, interpretation, draft/submission | NOT_RUN |
| Legitimate unresolved case; drafts distinct from submissions | NOT_RUN |
| Native CSV/JSON dialogs and independent output parsing | NOT_RUN |
| Normal quit, owned-process cleanup, reopen/history/state | NOT_RUN |
| Reinstall/uninstall data retention, installed failure/recovery cases | NOT_RUN |
| Non-admin install, non-ASCII username, upgrade, cleared-cookie recovery | NOT_RUN |
| Consumer Windows11, ordinary browser/SmartScreen trust, human usefulness | NOT_RUN |

The native path regression tests API mechanics, not the complete repaired guard.
Source ACL/lock/Unicode/job/listener/parent-crash tests also cannot qualify an
installed application. Installation or application success is not claimed.

## Preserved historical evidence and bounded repair

| Run / infrastructure | Actual result | Duration |
| --- | --- | --- |
| [1:41782543569](https://github.com/hnt119/lit-rev-engine/actions/runs/41782543569), `afb1a439a9316e7ef5b02656a1918cb4bf8c0ebf` | Native GUI and published installer launch PASS; automation expected Next on a refusal modal | 110s |
| [2:41782980639](https://github.com/hnt119/lit-rev-engine/actions/runs/41782980639), `4a788d6e866ae23167cf2d4540d7def544bd2419` | Published installer refused absent root: `unrecognized_root`, exit2, before agreement | 103s |
| [3:41783896262](https://github.com/hnt119/lit-rev-engine/actions/runs/41783896262), `62767ddc037b381e63f87ae784fff3d9f66cc155` | Native bug reproduction PASS; compiler failed agreement include resolution; no candidate | 122s |

Original sanitized reports remain [run-1.json](run-1.json),
[run-2.json](run-2.json), [run-3.json](run-3.json). No historical failure was replaced.

Confirmed packaging defect: NSIS3.13
[GetFullPathName implementation](https://github.com/kichik/nsis/blob/v313/Source/exehead/exec.c#L466)
clears output for a missing final directory. The original RootGuard allowed two
empty outputs to compare equal, assigned empty INSTDIR and checked a drive-root
wildcard, producing the false existing-folder refusal. Native regressions in
runs3–4 reproduce this mechanism.

[installer-root.patch](installer-root.patch) targets the exact release source.
It uses checked Windows GetFullPathNameW calls with error/truncation/empty-output
checks and preserves equality, reparse, ownership and agreement protections.
The include correction uses an explicit include directory and plain filename.
Run4 proves preprocessing/include resolution; **complete compilation and full
repaired-installer execution remain unverified**. No application behavior changed.

## Execution controls and preflight review

The [workflow](../../../.github/workflows/windows-installed-trial.yml) triggers only
creation of `codex/issue-18-windows-run-4`, attempt1, one standard public Windows
job, timeout60minutes. Release checkout, candidate build and `--candidate` are
unconditional. The old run-3 conditions are gone. Missing, stale, wrong-run,
wrong-source, wrong-patch or wrong-checksum candidate receipts fail closed.

Both preprocessor and full builder use the existing release helper's options:
`-V2 -NOCD -DPRODUCT_VERSION=... -DPAYLOAD_MANIFEST_SHA=... -DPAYLOAD=... -DOUTPUT_FILE=... installer.nsi`,
with NSISDIR set to the pinned SDK and cwd `release-source/apps/desktop`.
Preprocessing adds `-PPO`. The actual include bytes are checked against git first.
The full compile calls the release's existing `make_windows_installer` in a bounded
child. Extracted application files are build inputs only and are never launched.

Frozen-source review covered patch application, include file/compiler behavior,
all workflow selectors, receipt validation, actual Setup guard fixtures, native
failed-install controls, cleanup and assertions. **18** Cloud receipt/parser
regressions passed (including independent rerun), as did Python/Node syntax,
workflow structure and exact-release patch application. Official compiler ZIP
integrity and pinned Python3.12.7/Node24.19.0/GUI driver availability were checked;
actual tool setup succeeded. Static review did not prove full compilation.

## Environment, cleanup and remaining requirements

Codex Cloud is Debian13/Linux6.18.57 x86_64. Windows job4 reports **Server2025
Datacenter 10.0.26100**, image windows-2025-vs2026 `20261030.294.1`, runner2.338.2.
Developer tools were present. Earlier runs observed elevated user and controllable
Default desktop/session2; run4 skipped that trial preflight, so those observations
are historical rather than new non-admin/GUI evidence.

Original scripted download in run4 had no Zone.Identifier. None was removed.
No browser-download trust claim follows. No UAC, Defender, SmartScreen, sandbox,
Host/Origin/CSRF or ownership/ACL protection was disabled. No models, live PubMed,
generation, Mac, paid VM, release/tag/asset change, merge, deployment or issue
closure. Planned Electron CDP flags were never used because no app launched.

Run4 used **184s**; cumulative four-job time **519s (8m39s)**. Exactly one additional
run was triggered; all jobs completed. Run4 artifact count0; no cache/artifact,
profile, cookie, credential, database, screenshot, video or raw trace upload.
The no-install native regression child completed and hosted checkout/orphan
cleanup completed. No installer/application ran in run4. Temporary compiler,
download and extracted build files are subject to ephemeral runner disposal;
per-file erasure and peak RAM/disk were not measured. Account billing was not queried.
Only small sanitized evidence is committed. No background monitor remains.

**Recommendation: BLOCKED; keep PR31 draft and issue18 open.** Full compiler
cause, successfully built identified candidate, every full guard/installation
criterion and all installed-app stages remain open. Preserve bounded compiler
filename/line/diagnostic evidence before any future execution. The single renewed
run authorization is exhausted; no further branch push/retry may execute Windows
without a new owner decision. No new token, Mac or paid infrastructure is needed.
