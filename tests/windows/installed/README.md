# Issue 18 — actual hosted Windows trial

**Result: BLOCKED. Three of three authorized attempts completed.** The published
Setup.exe ran twice on real Windows, but refused before its agreement page.
Nothing was installed and the application never launched. A native regression
confirmed a packaging defect. Its proposed repair remains unqualified because
candidate compilation hit a second Windows build-path failure. No candidate EXE
or checksum was produced. No further runs, merge, release, tag or issue closure.

[Draft PR #31](https://github.com/hnt119/lit-rev-engine/pull/31) ·
[Issue #18](https://github.com/hnt119/lit-rev-engine/issues/18).
One Codex Cloud implementer and a fresh independent native agent reviewed exact
source, actual streamed installer bytes, real job logs, assertions and artifacts.
Independent review is source/evidence review, not a separate Windows execution.

## Exact identities and access

| Identity | Value |
| --- | --- |
| Current main / infrastructure base | `abd529dbb6dabc94312ebb5e7d4a7909d44d629d` |
| Accepted Core MVP ancestor, preserved | `1c6744de2ae0149f96f2063120b629a1f0eb17c7` |
| Published application source / release tag commit | `664b86d4ed510c3d16982b5813b27e6bd1150129` |
| Published version / native build | `0.3.0-windows-experimental-beta.2` / 3003 |
| Published Setup.exe bytes | 195492146 |
| Published Setup.exe SHA-256 | `75595d013fbdf4694301a00dd0e233a6b53e47c6cf5fb3713d0d0e7aa1e58359` |
| Published installed-file manifest SHA-256 | `7c6a2627831f1082a9163e599415c1f1f239036a3713912609fd95e5a68e5e34` |
| Declared bundled runtimes | Electron 45.0.0 Windows x64; Python 3.12.15+20261021 x86_64-pc-windows-msvc |
| Actual bundled runtime execution | NOT_RUN |
| Attempted replacement installer identity | `issue18-installer-root-rc1`; build FAIL, no final hash |

[Published release and companions](https://github.com/hnt119/lit-rev-engine/releases/tag/v0.3.0-windows-experimental-beta.2).
Actual anonymous installer GET/hash, annotated tag, SOURCE_AND_BUILD.json,
WINDOWS_BUILD_METADATA.json and repository release records agree. Issue #18's
historical “no public EXE” statement is obsolete. Current main's desktop sources
differ materially: **these installer observations do not qualify current main**.
Licensing texts, agreement and published assets were not changed.

Codex is Debian 13 x86_64, Linux 6.18.57. Native commands ran only on standard
GitHub-hosted windows-2025. No Mac, Wine, Linux GUI substitute or paid VM.
Repository read/write, workflow push, actual Actions trigger, status and logs:
PASS. Actions settings endpoint returns integration 403, but no settings change
was needed. CLI log redirect returns 403; GitHub connector job-log access works.
No credentials were printed or requested. Runtime policy was enforced unrestricted.

## Completed runs

| Run / job | Infrastructure SHA | Actual result | Job duration |
| --- | --- | --- | --- |
| [1: 41782543569](https://github.com/hnt119/lit-rev-engine/actions/runs/41782543569) / [126417197788](https://github.com/hnt119/lit-rev-engine/actions/runs/41782543569/job/126417197788) | `afb1a439a9316e7ef5b02656a1918cb4bf8c0ebf` | FAIL: automation expected Next on an installer refusal dialog | 110s |
| [2: 41782980639](https://github.com/hnt119/lit-rev-engine/actions/runs/41782980639) / [126418580980](https://github.com/hnt119/lit-rev-engine/actions/runs/41782980639/job/126418580980) | `4a788d6e866ae23167cf2d4540d7def544bd2419` | BLOCKED/Actions failure: reproduced `unrecognized_root`, installer exit 2 | 103s |
| [3: 41783896262](https://github.com/hnt119/lit-rev-engine/actions/runs/41783896262) / [126421475782](https://github.com/hnt119/lit-rev-engine/actions/runs/41783896262/job/126421475782) | `62767ddc037b381e63f87ae784fff3d9f66cc155` | FAIL: native path regression PASS, candidate compile exit 1; installed trial skipped | 122s |

Controlled evidence: [run-1.json](run-1.json), [run-2.json](run-2.json),
[run-3.json](run-3.json). Run 3 JSON is a sanitized transcription of reviewed
build logs, not a nonexistent application report. All were push event attempt 1;
no automatic PR run, dispatch, retry or parallel Windows job was triggered.

Observed Windows: **Server 2025 Datacenter 24H2, 10.0.26100.33674**, AMD64,
image windows-2025-vs2026 `20261030.294.1`, runner `2.338.2`. Native architecture
9 and RtlGetVersion `[10,0,26100]`/status 0. Python platform.platform incorrectly
labels the server Windows-2022Server; registry and runner image identify 2025.
Account elevated; interactive input desktop `Default`, session 2, real checkbox
click/readback PASS. Developer tools were present. Non-admin behavior is unproven.

## Defects, repairs and exact limits

1. **Automation defect:** attempt 1 treated a refusal modal as the wizard and
   looked for Next (ElementNotFoundError). Attempt 2 added fixed refusal enums,
   acknowledged the real OK button and recorded installer exit 2. That diagnostic
   correction worked; decline/acceptance was never exercised.
2. **Confirmed packaging defect:** on a fresh absent installation directory,
   the published installer reports an unrecognized existing folder. NSIS 3.13
   [EW_GETFULLPATHNAME](https://github.com/kichik/nsis/blob/v313/Source/exehead/exec.c#L466)
   clears its result for a missing final path component. Release RootGuard lets
   two empty paths compare equal and sets empty INSTDIR; `IfFileExists "$INSTDIR\*"`
   then examines a drive-root wildcard. Attempt 3 natively reproduced the empty
   result and verified GetFullPathNameW for missing and existing directories.
   [installer-root.patch](installer-root.patch) checks Windows API error/length,
   empty output and equality while preserving all reparse/ACL/agreement guards.
   **The API regression passed; the complete repaired installer did not run.**
3. **Toolchain/setup / Windows build-path portability failure:** attempt 3's
   exact-release builder failed to resolve `...desktop/windows-license-page.nsh`
   at installer.nsi line 5. Candidate compilation stopped with exit 1. After the
   budget ended, the patch was extended to use `!addincludedir "${__FILEDIR__}"`
   and the plain include filename. This proposed correction is **NOT_RUN** on
   Windows; no claim that it fixes the compiler failure.

The attempted build reused the release's `make_windows_installer`, official
Windows NSIS 3.13 ZIP SHA-256
`ba63dffc4410ee89193e1cb5a41989991bd77c61068da17e3156d136b7b0b3d8`, and all
verified original application payload files. Extraction was only a build input;
no extracted application was launched. Payload assertions completed before the
compile error. This was intended as an installer-only candidate, with unchanged
application version/source, **not** an upgrade or current-main application build.

## Acceptance matrix

| Requested item | Actual result |
| --- | --- |
| Published bytes/source identity; real installer launch/visible controls | PASS |
| Native desktop control | PASS on hosted Server |
| Agreement default-unchecked, decline/cancel, affirmative acceptance | BLOCKED before agreement; NOT_RUN interactions |
| Per-user install/files, Start shortcut, uninstall registration | BLOCKED; nothing installed |
| Ordinary non-elevated installation/execution | NOT_RUN; runner elevated |
| Bundled runtimes, Start launch, Electron driver compatibility | NOT_RUN |
| Saved example; 3 public papers/3 fields; exact excerpt/attach/interpretation | NOT_RUN |
| Draft save versus explicit submit; legitimate missing-information case | NOT_RUN |
| Actual native CSV/JSON dialogs, file parsing and source/value/limitation readback | NOT_RUN |
| Normal quit, owned runtime cleanup, relaunch, drafts/submissions/history | NOT_RUN |
| Installed reinstall/uninstall preservation; two-version upgrade | NOT_RUN |
| Installed Unicode/space paths, foreign ports, permissions, single instance | NOT_RUN |
| Installed parent interruption, optional setup interruption, cleared cookies | NOT_RUN |
| Five current-source native ACL/lock/Unicode/job/listener/parent-crash checks | PASS each run, separately from installed acceptance |
| Native NSIS missing/existing-path mechanics regression | PASS in attempt 3 |
| Repaired installer build and exact-artifact retest | FAIL build / NOT_RUN retest |
| Consumer Windows 11, non-ASCII username, physical device, human usefulness | NOT_RUN |
| Ordinary browser download, SmartScreen/Defender warning experience | NOT_RUN |

Scripted original downloads had no Zone.Identifier; none was removed. This is
not browser-download trust evidence. No protections, security fuses, Host/Origin,
CSRF, ACL, UAC, Defender or Chromium sandbox settings were disabled. Neural/model,
live PubMed and generation paths were off. Existing source-workflow model defaults
were inspected and that workflow was never dispatched.

## Reproduction, storage and next decision

The exact [workflow](../../../.github/workflows/windows-installed-trial.yml)
contains all commands. Python 3.12.7 x64 and Node 24.19.0 availability were checked
before running; pywinauto 0.6.9, pywin32 312, psutil 7.2.2, pytest 9.1.0 and
Playwright 1.62.1 installed successfully. Native control used pywinauto win32.
Planned CDP flags `--remote-debugging-address=127.0.0.1` and
`--remote-debugging-port=49228` were **never used**, since no app launched.
Playwright's Electron launcher is deliberately not used.

Core executed commands (PowerShell workflow supplies absolute task-tool paths):

```text
python tests/windows/installed/trial.py --tools <task-node> --output <task-report>
python tests/windows/installed/build_candidate.py release-source
python -m pytest -q -p no:cacheprovider -p tests.windows.native_fixtures <five explicitly named native tests in workflow>
```

The cloud parser regressions passed **6 tests**, independently rerun; Python/JS
syntax and workflow YAML checks passed. The same five native source tests passed
in each Windows job (1.07s, 0.98s, 0.84s); these are **five unique cases**, not 15
new coverage items. No real app/export regression passed.

Total observed Windows job time **335 seconds (5m35s)**, sequential standard
public runners, each limited to 60 minutes. Account billing was not queried.
All three run artifact counts are **0**; no cache/artifact upload, video, profile,
cookies, credentials, database or research payload was retained in GitHub artifacts.
Only small sanitized reports and source are committed. Runs 1–2 observed zero
installed bytes/processes; run 2 confirmed zero owned child processes after cleanup.
Run 3 launched only a completed no-install regression executable; no application
ran. Hosted checkout/orphan cleanup completed; temporary downloads/extracted build
inputs remain subject to ephemeral runner disposal, not an asserted secure erase.
Peak RAM/disk and network totals were not instrumented. No live monitor remains.

**Recommendation: Windows qualification BLOCKED; repair packet ready for source
review.** Smallest owner decision: authorize one additional bounded hosted-Windows
build/install attempt after reviewing the include-path correction. No new token,
Mac access, paid infrastructure or merge is currently needed. Do not rerun a job
or push any numbered execution branch without renewed run authorization. Current
PR-branch documentation pushes do not trigger Windows jobs. Keep all historical
failure records; start from the final PR head and the immutable release source.

## Additional authorization: run 4 preparation

The owner authorized exactly one further standard hosted Windows job, 60 minutes,
following focused independent review. Earlier run records and their failures are
unchanged. PR head at resumption was `7051b3663db6f200a364aee46122080e67a44ec7`.

The current workflow triggers only creation of `codex/issue-18-windows-run-4`
and permits attempt 1 only. Release checkout, candidate build and `--candidate`
selection are unconditional: no run-3 selector or published-installer fallback.
The candidate receipt must bind this run/attempt/infrastructure SHA, exact patch,
source, original installer, compiler ZIP, payload manifest and actual new EXE
bytes. Missing/invalid/stale metadata stops before launch.

Compiler preprocessor and full build use the exact release helper's defines and
`-NOCD`, NSISDIR and `apps/desktop` working directory; preprocessing adds `-PPO`.
The include file is compared with committed bytes before compilation. Build
reports are emitted even on failure. Candidate identity is now
`issue18-installer-root-rc2` (no build success claimed by this preparation).

Actual Setup guard cases precede installation: fresh absent path/cancel, unknown
folder, known marker without registration, alternate destination, and junction.
Only disposable sentinel fixtures are created, after the initial fresh-path
check, and removed before affirmative installation. No pre-created final root
hides the missing-leaf defect. Same-version rejection after normal quit is
followed by a complete installed-file and retained-data hash check. Success then
continues the existing installed research/export/persistence sequence.

Pre-execution checks: 18 receipt/parser regressions, Python/Node syntax, workflow
structure, patch application to exact release files, actual agreement include,
and official compiler ZIP integrity. These checks do not establish compilation
or Windows acceptance. The independent reviewer checked NSIS include resolution,
compiler flags/working directory and failed-install page button behavior against
upstream source. All final native outcomes remain pending the one authorized run.
