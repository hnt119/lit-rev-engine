# Source beta 0.3.0-beta.4 — validation record

## Release identity and current gate

This is the next Track A **setup-required source beta**, with the existing
Next.js/FastAPI app, excerpt-first comparison, explicit paper/field context,
optional local retrieval and reviewed Windows x64 security/launcher boundary.
It contains no native installer, Python/Node runtime, model weights, credentials
or private research workspace. MIT covers original code; retained third-party
notices/article/model boundaries stay separate. Track B is excluded.

Preparation began at integrated source
`5bb09fb2f8880cba811593887f3b4574f0ece873`. The final exact commit is recorded in
the generated RELEASE.json, and every packaged byte is bound by MANIFEST.json
and the supplied integrity files. This preparation record does **not** say the
combined source or final archive has passed by inheritance. Existing published
beta.3 and older assets remain immutable; a previous archive/hash is not a
beta.4 artifact or download URL.

| Exact beta.4 gate | Status at documentation preparation |
| --- | --- |
| Package/license/link | Preparation working tree: 44 offline tests PASS; final reviewed commit gate pending |
| Independent source archive audit | PENDING for final clean commit/archive |
| Combined frontend/typecheck/production build | PENDING; earlier tests retain their exact source identity |
| Fresh extracted macOS arm64 setup, production/browser, drafts, source round trip, exports, restart/replacement | PENDING for final archive |
| Combined Windows x64 source and final extracted archive | PENDING; earlier baseline run below is separate |
| Physical Windows 11 machine | NOT_RUN |
| Linux installation, Intel Mac, Windows ARM | Unverified / unqualified; Windows ARM unsupported |
| Fresh Windows BGE semantic-map fitting | NOT_RUN; saved maps/Core require no new fit |
| Real LLM planning/proposals, live provider/PubMed calls | NOT_RUN; mocked adapter checks are not live execution |
| Scientific quality, independent retrieval accuracy, authenticated/dual review | NOT_RUN / not established by software checks |

Preparation command: `python -m pytest -q tests/local_distribution/test_release_packager.py tests/local_distribution/test_license_policy.py tests/local_distribution/test_release_links.py` — 44 passed, no failures/skips (27.63 seconds), in disposable synthetic repositories. This does not execute the application or qualify a final archive. `git diff --check` passed. No build, Windows execution, model/provider call or live PubMed check was run by this packaging/documentation task.

The release owner must append observed final command/results, failures/skips,
source identity and extraction checks before treating this as a passed release
gate. A successful source build alone does not exercise installation or browser
behavior. No new provider/model execution is implied by preparing this guide.

## Historical Windows baseline — actually executed, different source

[Actions run 40214350818](https://github.com/hnt119/lit-rev-engine/actions/runs/40214350818)
passed at `aec9277d8cf2199026ff933da86ca3c8d3ea7b52` on the standard public
Windows Server 2025 x64 runner, Python 3.12.7, Node 24.19.0 and pnpm 10.20.0.
This was actual Windows execution, not macOS mocks or a physical Windows 11 test.

- 33 native boundary/policy/API tests and two Node signal-adapter tests passed.
- A fresh clean source package and independent audit, isolated prerequisite/setup,
  production startup and actual sandboxed Chromium workflow passed.
- The 30-paper public example, three prepared reports/nine cells, explicit cell
  revisions, retained exact sources, drafts/reopening and CSV/JSON exports were
  exercised. Host/Origin/CSRF and separate-session denials were checked.
- Single-instance/foreign-listener refusal, authenticated terminal shutdown,
  owned-child crash cleanup, restart, app replacement with external data,
  stopped backup and new-directory restore passed. This run had an existing terminal console (four console processes),
  so no test-fixture console was allocated. Both recorded normal stops
  sent two console breaks, reported child exit codes 0/143, forced no primary
  process, and closed the owned job. Missing-console termination remains a
  separate fallback, not relabeled graceful shutdown.
- Actual pinned Qwen and MedCPT CPU checks each executed one query encoding,
  two document encodings and two reranker pairs. This is tiny synthetic runtime
  execution, not a human-gold relevance benchmark, full-text throughput guarantee
  or biomedical advantage. No Windows BGE fit or generation was run.
- No runtime state, models, cookies, research database, browser evidence or binary
  was uploaded by that job. Live providers, generation and research usefulness
  remained NOT_RUN.

The sanitized baseline acceptance report records 459.343 seconds total, including
82.813 seconds fresh setup, 2.203 seconds production readiness and 0.5 seconds
authenticated shutdown. Tiny model-check execution took 10.266 seconds for Qwen
and 7.0 seconds for MedCPT; download-plus-check took 40.828 and 28.297 seconds
respectively. These are one runner’s observations, not promised desktop latency.
The report source is the exact baseline above; its package had 263 files and is
not the new beta.4 artifact.

These results do not automatically qualify the later union/conflict resolution,
new paper-context UI or final beta.4 archive. Combined/final checks must use
fresh temporary state and the new source binding.

## Historical macOS and human observations — retain original scope

HISTORICAL_EXCERPT_VALIDATION.md keeps beta.3 software/candidate/final evidence,
its real cached Mac CPU/MPS executions and qualitative reviewer observations with
their original identities. HISTORICAL_RETRIEVAL_VALIDATION.md keeps the earlier
beta.2 evidence. They are packaged as historical records rather than overwritten
with beta.4 labels. Earlier macOS arm64 checks used Python 3.12.7 and Node 24.19.0;
other Mac versions/architectures are not implied.

The owner reported completion of the three-cell comparison task without help,
and initial confusion about multiple fields belonging to one paper. It was one
qualitative report from an isolated UX1 session, not a relabeled published-ZIP
trial or independent/authenticated review. The source now makes Paper i/N,
Field j/M and same-paper/next-paper transitions explicit. Further human retesting
of those cues is not established. The report that some excerpts were not found
remains unclarified; it does not justify changing ranking or declaring absence.
Do not infer scientific support, timing, full interface validation or review
completeness from these observations.

The earlier Qwen full-article attempt exceeded a 180-second QA cutoff; a later
52-window cached Mac CPU index at source c4f57c5 completed in 39.81 seconds.
The old failure remains retained, its cause unresolved, and the 600-second
product budget/ranking/profile contracts remain unchanged. Neither observation
is a fresh beta.4 run or a general latency claim.

## Optional capabilities, security and remaining limits

Core lexical/manual research and the public saved map need no neural runtime,
weights or generation key. Optional dependencies, explicit pinned-pack install,
runtime checks and indexing remain separate actions. Models are never downloaded
by normal navigation/setup; saved historical results remain readable when a pack
is unavailable. UI Settings is the normal session route; the optional private
operator file uses the existing OS security facade. Windows requires protected
current-user ACLs on fixed local NTFS, not POSIX chmod pretending to secure a file.
No execution-policy, TLS, SmartScreen or antivirus bypass is part of setup.

Per-action generation consent, bounded calls/context/time, no provider fallback,
source integrity and explicit human support/adoption/submission remain. Exact
quotation verification is not support verification. Retained cookie/profile/
hostname limitations and lack of automatic access recovery remain documented in
README.md / WINDOWS_SOURCE.md; workspace IDs are not authorization. Research and
model caches stay outside replaceable app files; no only-copy migration occurs.

The native desktop prototype remains withheld. Its separate collector retains
five exact-version hash-bound supplements; client-only notice/attribution and
libvips/native corresponding-source/relink obligations remain unresolved.
A complete transitive SBOM, trusted signing/notarization and separately installed
external optional ML runtime are also open gates. Neither those notice checks
nor source-app Windows tests qualify a public desktop executable. No native
build/signing/publication or hosted deployment is part of this source release.
