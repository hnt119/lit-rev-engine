# Issue 18: installed Windows acceptance trial

## Resumed execution — 4 November 2026

The prior preparation below is retained as history. API access now works with
Codex Cloud's authorized network permission. Repository read/write is reported;
Actions run/status reads work, and actual historical job logs were read through
the GitHub connector. The CLI log redirect receives 403; use the connector.
The Actions settings endpoint alone returns integration 403; no settings change
is required. A numbered branch push will establish actual trigger permission.
No Windows attempt has yet been triggered at this checkpoint.

Current main remains `abd529dbb6dabc94312ebb5e7d4a7909d44d629d`. Independent
verifier re-streamed and hashed the published Setup.exe and checked annotated
tag/source/manifests. Official Python 3.12.7 win32 x64 manifest entry, Node
24.19.0 win-x64 release, Playwright 1.62.1 registry entry and CPython 3.12 x64
pywin32/psutil wheels were checked before execution. The installer OS gate accepts
AMD64 NT 10 build >=22000; actual Server 2025 behavior still needs the run.
No old workflow is dispatched: its model defaults are unsafe for this task.
The existing three numbered push routes prevent automatic PR-trigger duplicates.
Bounded native control diagnostics were added; no application code was changed.

## Historical preparation record — execution was blocked

Goal: test the published installer on standard public GitHub-hosted x64 Windows;
no Mac, Linux substitute GUI, paid infrastructure, model download, live PubMed,
generation, release publication, tag, merge, or issue closure.

Integration owner: Codex Cloud implementer. A separate native Codex agent has
independently checked release/source identities and reviewed the harness.
Its review is **source review**, not an independent Windows execution.
The verifier independently rehashed the actual downloaded Setup.exe, reran the
six parser tests, and found a failure-status mapping bug in the unexecuted
harness; that mapping was corrected before any Windows attempt.

| Identity | Observed value |
| --- | --- |
| Infrastructure base/current main at start | `abd529dbb6dabc94312ebb5e7d4a7909d44d629d` |
| Accepted Core MVP ancestor, preserved | `1c6744de2ae0149f96f2063120b629a1f0eb17c7` |
| Published installer application source/tag commit | `664b86d4ed510c3d16982b5813b27e6bd1150129` |
| Published version | `0.3.0-windows-experimental-beta.2`, build 3003 |
| Setup.exe size | 195492146 bytes |
| Setup.exe SHA-256, actual anonymous download verified on Linux | `75595d013fbdf4694301a00dd0e233a6b53e47c6cf5fb3713d0d0e7aa1e58359` |
| Declared bundled Electron | 45.0.0, Windows x64 |
| Declared bundled Python | 3.12.15+20261021, x86_64-pc-windows-msvc |
| Codex execution machine | Linux 6.18.57, x86_64; not Windows |
| Remote Windows OS/image/account/desktop/runtime execution | NOT_RUN |
| Windows attempts used | **0 of 3**; no execution branch pushed |
| Workflow/run/job links | NOT_RUN; no run ID exists for this trial |

Installer:
<https://github.com/hnt119/lit-rev-engine/releases/download/v0.3.0-windows-experimental-beta.2/lit-rev-engine-0.3.0-windows-experimental-beta.2-windows-x64-Setup.exe>

Source-bound release instructions:
[installation](../../../docs/releases/v0.3.0-windows-experimental-beta.2/INSTALL_WINDOWS.md),
[historical validation](../../../docs/releases/v0.3.0-windows-experimental-beta.2/VALIDATION.md).
Downloaded SOURCE_AND_BUILD.json and WINDOWS_BUILD_METADATA.json agree with the
installer identity. The tag resolves to the stated source. Current main has a
different desktop source tree: **a test of this installer is not a test of main**.
Any application repair must reuse the release branch/tag's existing Windows
build path and receive a distinct candidate identity/hash; no repair binary
has been built here.

## Access and blocker evidence

- Repository read/fetch and new feature-branch push: PASS using injected HTTPS
  Git authentication. No token values inspected or printed.
- Issue #18 and its visible comment, published release assets, current branch
  refs and public PR listing: read through GitHub's public pages/Git transport.
  Historical issue statement that no public EXE exists is superseded by the
  actual downloadable beta.2 release. No duplicate open Windows trial PR was
  visible in the public PR listing.
- GitHub API, Actions authorization/trigger/log access, draft PR creation and
  issue comment: BLOCKED. `gh api repos/hnt119/lit-rev-engine` and the issues,
  Actions and permission endpoints receive proxy CONNECT 403, before a GitHub
  authorization decision. This does not establish missing token scopes.
- Runtime network status: enforced restricted policy, revision 1, package-manager
  preset, no custom domains; `api.github.com` absent. Owner reported enabling
  public Internet; a retry still observed the old active policy and CONNECT 403.
- Saving the specific `api.github.com` addition through the environment draft
  tool failed with `stale_base` / CONFLICT. Persistence is unconfirmed; rereading
  and resubmitting the same stale draft is explicitly unsupported.
- Public historical run pages require sign-in for step logs. No blind trial
  was launched without a usable route to inspect real logs/results.

Minimum external action: apply Internet/API access to **this running task**, or
reconnect it from the updated environment. Retry the existing integration after
that change; request only any permission actually denied by GitHub. Do not paste
tokens into chat, extract Git-proxy credentials, bypass the proxy, or use the Mac.

## Harness and commands

The new workflow is [windows-installed-trial.yml](../../../.github/workflows/windows-installed-trial.yml).
It runs only when one of these dedicated execution branches is pushed:
`codex/issue-18-windows-run-1`, `codex/issue-18-windows-run-2`,
`codex/issue-18-windows-run-3`. Each branch must be created **once**, sequentially.
The PR/preparation branch `codex/issue-18-windows-trial` does not trigger it.
There is no workflow_dispatch registration dependency, PR trigger,
pull_request_target, automatic merge, or automatic model step.

Before spending a run, verify repository public status, Actions permission,
real run/log read access, official pinned dependencies, the exact infrastructure
commit, and absence of the chosen numbered branch/run. Establish a focused draft
PR through the authorized integration once API access works.

```sh
# Read-only access checks; never dump credentials.
gh api repos/hnt119/lit-rev-engine --jq '{private,permissions}'
gh api repos/hnt119/lit-rev-engine/actions/permissions
gh api repos/hnt119/lit-rev-engine/actions/runs --jq '.total_count'
git ls-remote --heads origin 'codex/issue-18-windows-run-*'

# Only after reviewing access, diff and run budget; push the selected run branch ONCE.
git push origin HEAD:refs/heads/codex/issue-18-windows-run-1
gh run list --repo hnt119/lit-rev-engine --branch codex/issue-18-windows-run-1
# Record the returned run ID immediately. Follow to completion, inspect job
# summary and real logs, then update this record with exact SHA/run/job URLs.
gh run view RUN_ID --repo hnt119/lit-rev-engine --log
```

Workflow commands use official setup-python 3.12.7 x64, Node 24.19.0, isolated
pywinauto 0.6.9 / pywin32 312 / psutil 7.2.2 / pytest 9.1.0 and Playwright 1.62.1.
Windows CPython 3.12 x64 driver wheels and official setup-python manifest entry
were checked before proposing a hosted job. The job repeats availability checks.
It does **not** install Chromium or use Playwright's Electron launcher: that
launcher was inspected and rejected because it injects weaker browser switches.

`trial.py` performs native desktop control/readback; checksum/download-origin
observation; real interactive NSIS decline/accept; exact installed-file hash and
terms/source verification; shortcut/registry checks; installed launch; runtime
path inspection; single-instance; normal quit/reopen; same-version uninstall and
reinstall preservation; owned occupied-port refusal. `journey.cjs` attaches via
explicit loopback CDP, performs UI actions and uses native Save dialogs through
the Python helper. No API performs the research actions under test. Independent
parsing compares submitted values, unresolved limitations, source bindings and
Unicode ranges to source responses actually read by the UI. Draft data is never
treated as submitted evidence.

Five existing native **source** boundary tests run independently even when GUI
acceptance fails. These are separately labeled and cannot qualify the installed
binary. Critical steps left unexecuted are NOT_RUN, never a complete pass.

## Actual checks so far

| Check | Result |
| --- | --- |
| Exact installer anonymous full download, bytes and SHA-256 | PASS on Linux; not execution |
| Source/tag/main/Core ancestry and release/runtime metadata binding | PASS, independently reviewed |
| Python harness syntax / Node driver syntax / workflow YAML parse | PASS on Linux only |
| Independent export parser including Unicode range, wrong-source, leaked-draft, invented-value and revision-count rejection | 6 passed on Linux |
| Native desktop preflight and installer agreement behavior | NOT_RUN |
| Per-user/non-elevated install, installed files, shortcut/registry | NOT_RUN |
| Installed saved example, 3 papers/3 fields, exact source, attach, draft/submit, missing information | NOT_RUN |
| Native CSV/JSON dialogs and parsing of actual app exports | NOT_RUN |
| Normal quit/process cleanup, relaunch/history, reinstall/uninstall preservation | NOT_RUN |
| Paths with spaces/non-ASCII; ports, permissions, single instance, interrupted-operation recovery | NOT_RUN |
| Non-ASCII Windows username, cleared-cookie recovery, two-version upgrade | NOT_RUN; not established by directory/reopen/reinstall checks |
| Consumer Windows 11, browser MOTW/SmartScreen experience, physical device, human usefulness | NOT_RUN |

No application defect has been observed or repaired. This is preparatory
automation, not a replacement qualification result. The harness does not yet
implement every interrupted-operation case: permission failure, parent failure,
optional setup interruption and cleared-cookie recovery remain explicit
NOT_RUN until a focused implementation and real artifact retest establish them.

## Evidence retention and cleanup

Only allowlisted JSON/Markdown summaries reach job logs/summary. No artifact or
cache upload is configured. No profiles, cookies, tokens, research databases,
raw traces, video, environment dumps or private documents are uploaded. Installer
and retained public fixture data stay on the ephemeral runner. Cleanup stops
only owned installed-path processes and child processes; forced cleanup remains
distinct from a normal quit pass. No Windows compute/storage has been consumed
by this trial yet. Prepared Linux installer download is 195492146 bytes.

After access is restored: inspect independent review findings, record exact
infrastructure commit, establish the draft PR, execute initial run, inspect its
actual logs, classify failures, and use at most two justified focused repair runs
(60 minutes each). Do not repeat an unchanged failure or mark a critical skip as
passed. Update issue #18 factually; do not close it or publish anything.

## Attempt 1 — actual Windows result

Infrastructure `afb1a439a9316e7ef5b02656a1918cb4bf8c0ebf`;
[run 41782543569](https://github.com/hnt119/lit-rev-engine/actions/runs/41782543569),
[job 126417197788](https://github.com/hnt119/lit-rev-engine/actions/runs/41782543569/job/126417197788).
Completed FAILURE in 110 seconds; trial itself 11.9 seconds. Raw controlled
summary preserved in [run-1.json](run-1.json). Independent verifier read real logs.

Windows Server 2025 Datacenter build 26100, image windows-2025-vs2026
20261030.294.1, runner 2.338.2; AMD64 elevated account, Default desktop session 2.
Python platform.platform() mislabels it Windows-2022Server; runner OS identity
is Server 2025. PASS: pinned tools, actual download/hash, native checkbox control,
installer-visible. FAIL: automation expected Next but a blocking modal had only
OK (control 2); ElementNotFoundError. Agreement/installation BLOCKED, subsequent
installed-app paths NOT_RUN. No application defect is established yet.

Five independent native source boundary checks PASS (1.07s): current SID ACL,
LockFileEx, Unicode path/arguments, owned job/listener, parent-crash cleanup.
These test current main's inherited source, not installed beta.2. Zero installed
bytes/processes; scripted download had no Zone.Identifier (not browser trust).
No artifact/cache upload. A second run adds fixed installer-refusal enums and
independent native OS/architecture readback, repairing the automation's failure
to handle a refusal dialog. It will not bypass any installer/security guard.
