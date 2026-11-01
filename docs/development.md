# Source development and workspace care

This guide describes the source checkout. Published apps and source downloads keep their own [versioned installation guides](README.md#use-the-published-application). Read [product design](../product_design.md) and the [repository agent guide](../AGENTS.md) before changing behavior.

## Install, run and reopen

The source launcher uses Python **3.12**, Node.js **24** and pnpm **10.20.0**. Inspect the checked-out requirements, lockfiles and launcher before setup. Reuse a compatible, verified environment when one is available; do not create a copy for each agent.

From the repository root, the standard source setup is:

```sh
python3.12 scripts/local_preview.py setup
python3.12 scripts/local_preview.py launch
python3.12 scripts/local_preview.py status
python3.12 scripts/local_preview.py stop
```

Setup downloads pinned runtime dependencies and builds the web UI. It creates ignored `.venv-preview/`, `apps/web/node_modules/`, `apps/web/.next/` and setup metadata. Optional models and cloud providers have separate [configuration and consent boundaries](research_ai_settings.md); Core manual research does not require them. These instructions do not authorize model downloads or paid calls.

The launcher stores research outside the checkout: on macOS in `~/Library/Application Support/LiteratureReviewEngine`, on Linux under `$XDG_DATA_HOME/lit-rev-engine` (or `~/.local/share/lit-rev-engine`), and on Windows under `%LOCALAPPDATA%/LiteratureReviewEngine`. A custom private `--data-dir` must be supplied consistently for launch, status and stop. Platform-specific acceptance remains as recorded in the relevant guides; a source command is not native qualification.

Reopen through the same supported launcher, host name and browser profile. Session expiry or cleared cookies can prevent access even while saved data remains; a workspace ID is not a recovery credential. [Scholarly exports, a stopped full-directory backup/restore, and authorization recovery](user_manual.md#export-back-up-and-replace-the-app) are separate operations. Do not test against the owner's original research directory.

For frontend/backend development, consult [local source operation](local_preview.md) and [application architecture](application_architecture.md). The lower-level `scripts/run_web.py` launcher has its own development defaults, including `.mvp-web-state/`; do not confuse that state with the distribution launcher's external directory.

## Folder guide

| Path | Responsibility |
| --- | --- |
| `apps/web/` | Next.js/React interface and same-origin bridge. |
| `apps/desktop/` | Electron shell, lifecycle and desktop security behavior. |
| `apps/streamlit/` | Streamlit surfaces and shared visual tokens. |
| `src/mvp/` | Research services, source preparation, retrieval, comparison and persistence. |
| `src/web_api/` | Typed HTTP contracts, authorization, validation and capability reporting. |
| `src/review/` and other research modules | Distinct research/legacy contracts; inspect scope before reuse. |
| `config/` | Checked-in settings and release identities, never private credentials. |
| `scripts/`, `tools/` | Existing launch, audit, test, packaging and supporting utilities. Inspect side effects before running. |
| `tests/`, `tests/fixtures/` | Automated checks and scoped recorded/public/synthetic fixtures. Frozen evidence keeps its identity. |
| `examples/`, `notebooks/` | Example workflows and exploratory research. These are not new scientific or human validation. |
| `docs/`, `docs/releases/` | Current navigation and technical guides; immutable version-bound release history. |
| `workflow/` | Research workflow, architecture and interoperability planning material. |
| `showcase/` | Prepared public projections. The live portfolio is maintained in a separate repository. |

Locally installed agent skills/configuration may also live in `.agents/` or `.codex/`. Inspect their actual instructions; they are not application runtime dependencies or permission to publish. Keep one authoritative private project ledger rather than copying it into each worktree or public documentation.

## Focused checks

Use the existing verified development environment first. If dependencies are genuinely missing, the Python web development requirements are `requirements-web-dev.txt`, constrained by `requirements-web-lock.txt`; frontend dependencies use `apps/web/pnpm-lock.yaml`. The source runtime setup alone does not install every development/test dependency. Respect the task's installation and network permissions.

Choose checks for the boundary changed, from the repository root:

```sh
# Research services; use a narrower test file when possible.
python -m pytest -q tests/mvp

# Frontend changes, after its locked dependencies are installed.
pnpm --dir apps/web typecheck
pnpm --dir apps/web test
pnpm --dir apps/web build
```

For HTTP changes, select the relevant `tests/web_api/` contract tests. Regenerate contracts only when affected:

```sh
python scripts/export_web_openapi.py
pnpm --dir apps/web generate:api
```

Do not hand-edit the generated client. For documentation changes, check links, fragments and affected version-bound metadata tests; do not repeat unrelated builds or model runs. Read CI workflows and test markers before invoking packaging, native, browser or live-provider tests. Record source SHA, environment, command, results and limitations. Software tests do not establish browser, native, scientific or observed human acceptance. Existing deferred investigations stay deferred unless separately authorized.

## Branches, pull requests and agent work

1. Inspect status, current head, recent history, all worktrees and the relevant PR before edits. Preserve dirty trees and unique commits.
2. Reuse a suitable clean checkout. When concurrent writers need separation, use the existing managed worktree workflow and one integration owner. Prefer `codex/` branch names for agent tasks.
3. Keep a bounded diff and stage owned paths explicitly. Preserve published ancestry; do not reset, force-push, silently stash or discard work to obtain a clean tree.
4. Use a draft PR for reviewable work. Record the exact base/head, changed behavior, checks and known limits. Required checks and independent review apply to the actual final head. Merge, release and deployment require their own applicable authorization.
5. The Project Engineer owns decomposition and the authoritative private ledger. Managers delegate bounded tasks with explicit role/model settings and permissions. A nonauthor verifier reviews substantive changes; routine deterministic operations need no extra agents. Preserve the established routing and concurrency limit rather than starting a new framework.

## Workspace retention and cleanup

- **Keep source small.** Store research, credentials, databases, browser profiles, models and private QA records outside tracked source. Use the existing ignored runtime directories only where the tools require them. The root `.litrev-engineering-state/` is private and ignored. Check ignore rules before writing sensitive state; an ignore rule is not permission to publish it.
- **Reuse resources.** Share an existing verified compatible environment, locked dependencies and caches where safe. Do not duplicate environments, source archives or builds for each agent. Virtual environments can contain absolute paths; do not relocate one merely to tidy a folder. Avoid unnecessary background processes and parallel builds.
- **Retain compact evidence.** Keep essential commands, source/dependency/fixture identities, verdicts, failures, corrections and hashes with required artifacts in the existing private ledger. Prefer summaries over copied transcripts. Keep referenced evidence, frozen fixtures, release records and historical provenance until dependencies are reviewed.
- **Give scratch an owner.** Use one clearly named task directory in the system temporary area or an approved external location. Record its purpose and required retained outputs. Remove owned disposable test outputs after evidence is retained. Never purge another task's files based only on age or a temporary-looking name.
- **Check before removal.** Inventory disk usage before and after; avoid double-counting nested directories. Confirm ownership, inactivity, no private/unique contents, no active task or PR dependency, and no authoritative evidence reference. Preserve lockfiles/recipes and at least one needed verified environment before deleting a redundant regenerable copy. If uncertain, retain it and escalate the specific proposed deletion.
- **Protect Git history.** Remove a redundant local branch only after verifying its exact head is preserved in the integration history and no worktree or ongoing task uses it; use ordinary safe deletion. Remote branch deletion requires approval. Archive an eligible managed worktree through the app's recoverable archive operation after checking untracked and ignored contents. Do not remove active worktrees, prune remote history, or use blanket `git clean`/reset commands.
- **Bound growth.** Measure new persistent outputs and reuse existing resources. For this workspace, obtain approval before creating more than 1 GB of additional persistent artifacts, excluding already-approved required dependencies. Record retained resources and reasons so the next agent can avoid another broad scan.

Cleanup preserves accepted source identities and the existing pilot handoff/checklist. It does not expand the Core milestone or authorize a pilot, recruitment, infrastructure provisioning, publication or changes to access recovery.
