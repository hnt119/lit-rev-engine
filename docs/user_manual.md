# User manual — evidence-first local research

Use the normal application for this guide. Track B's protocol pilot, the legacy CLI and the private desktop prototype are separate. This manual describes the beta.4 source checkpoint; use the exact release's installation guide and VALIDATION.md to identify the downloadable interface and its actual checks. Earlier published downloads remain bound to their own guides. Start with the permitted offline example before entering private research.

## Install on your OS

The source app is setup-required: Python 3.12 (venv/pip), Node 24 and pnpm 10.20.0. macOS 26.6.2 arm64 passed fresh extracted candidate 8cf4379 checks. Windows x64 candidate c27aea0 passed Core/browser and bounded Qwen/MedCPT CPU production-API cases on public abstracts. Observed OS values were `2022Server` / `10.0.26100` on a runner labeled `windows-2025`. Earlier failures stay in VALIDATION.md; the final merged archive still needs its separate external RELEASE_ACCEPTANCE.json after the build. These software demonstrations do not establish research quality. Physical Windows 11 is NOT_RUN. Linux installation, Intel Mac and Windows ARM are unqualified. No public desktop installer is available. Do not disable Gatekeeper/SmartScreen or execute a package that claims those untested capabilities.

On Windows, follow WINDOWS_SOURCE.md instead of the macOS shell examples below. It verifies checksums, creates an isolated `.venv-bootstrap` with the pinned Windows security prerequisite, and uses that Python for setup/launch/status/stop. No activation, execution-policy change or global pip install is required.

Get the purpose-built ZIP, manifest and SHA256SUMS from the exact pre-release linked in the repository README. GitHub's automatic source archive is not the tested distribution. Keep those three files together in the download folder and verify them there:

```sh
shasum -a 256 -c lit-rev-engine-<version>.SHA256SUMS
unzip lit-rev-engine-<version>.zip
cd lit-rev-engine-<version>
python3.12 scripts/local_preview.py setup
```

Replace `<version>` with the downloaded version. The first command runs beside the downloaded ZIP and sidecar files; setup runs inside the extracted application folder. Setup creates its own runtime/build files, installs pinned dependencies and builds the production interface. It does not search, infer, download weights or migrate research. Missing tools/version errors explain the prerequisite to fix. Do not bypass TLS errors. Keep this app folder writable; research and models live outside it.

## Start, stop and reopen

```sh
python3.12 scripts/local_preview.py launch
python3.12 scripts/local_preview.py status
python3.12 scripts/local_preview.py stop
```

Launch waits for both owned loopback services before opening the browser. Keep that terminal open, or use Ctrl-C for a controlled stop. Run status/stop from the same extracted application folder. Use the printed URL and the same browser profile and hostname when reopening; cookies identify local access, not a named researcher account. Clearing or expiring cookies can lose access. Knowing a workspace UUID is not authorization and there is no new account-transfer/recovery system.

If ports are occupied, close only the positively identified other application or deliberately choose unused ports with `--web-port` and `--api-port`; never kill an unknown listener. Force-killing the source controller can leave owned children running. Do not delete active locks to bypass them; follow the extracted README.md / release INSTALL.md recovery instructions or restart the computer before relaunching.

## Start with the offline example

Create a workspace in **Saved example · offline**, then **Open saved example**. It loads 30 permitted public papers and saved map coordinates. No contact, key, weight or model execution is needed. This is a curated exploration example, not formal eligibility, a complete search capture or independent studies. Map neighbors and selections do not establish evidence quality.

Select reports and **Prepare & compare**. Keep the source availability labels: full text, abstract only or unavailable. Create a board with questions relevant to your review; reports are rows, editable fields/subquestions are columns. Three papers and three fields are a useful first table, not a library limit.

## Add and prepare your own papers

Use Discover/Add papers to parse supported CSV, RIS or DOI/PMID identifiers. Local parsing makes no provider/model call. Metadata resolution is a separate explicit action and may reveal identity conflicts requiring your decision. PubMed search requires your actual contact; its API key is optional. Review the executable query, dates, ordering and result bound beside each search. Application defaults only prefill new work. A bounded preview is not a complete review capture.

Choose reports and explicitly prepare sources. Identity/permissions determine permitted full text or a labeled abstract fallback; never treat metadata as evidence you read. Preparation jobs retain outcomes; they do not silently replace a historical board's sources. Avoid creating duplicate boards just to reopen existing work.

## Select an excerpt, comment and save

Open an unfinished comparison cell. It stays inside the comparison view with paper, field/subquestion and source availability visible. **Paper i/N** and **Field j/M** identify whether the next unfinished cell is another field of the same report or another paper. These labels do not group reports into independent studies.

1. **Select evidence.** Choose **Find excerpts in this paper**, or **Browse this source** if candidates are empty/unhelpful. A candidate is only a possible match. Opening/highlighting it does not mark inspection, attach evidence or judge support.
2. Read its exact retained context. **I have read this excerpt — use it** explicitly attaches the valid range and declares that you read it. Wait for acknowledgement; the comment input then receives focus. The chosen excerpt/citation stays visible beside it.
3. **Comment & judge.** Enter your manual value/comment, support judgment and scope result deliberately. No support choice is preselected by retrieval or source matching. Explain the judgment where requested. Add/change/remove excerpts within this editor; removing one keeps typed text/judgment and reveals any new requirement.
4. **Review & save.** Review the summary and visible save requirements. **Save reviewed entry** acknowledges an immutable human entry in the table. It is your self-declared assessment, not independent verification. Choose **Next unfinished cell** or **Back to table**; table position/focus is retained.

A display range is limited to 4,000 Unicode code points, not the whole paper. Use adjacent ranges/blocks to read omitted text. Advanced exact start/end controls are optional; attach only a valid displayed range that you inspected. Server checks source ownership, version, hashes, offsets, draft version and saved revision. Exact quotation matching does not prove that a claim is supported.

## Keep a note or record missing information

**Draft saved** means editable input was acknowledged; it is not a submitted table entry. New note-only text without evidence remains an unsubmitted/unassessed draft. It survives navigation/reopening but is separate from scientific exports. Do not invent a quotation to make a note look supported.

Choose **Continue with notes or missing information**. Leave **Manual cell value** blank (null), explain the limitation in **Reason** and **Missing information**, and set **Inspected scope result** truthfully. **Not found in inspected material** requires an explicitly declared inspection range and does not establish whole-paper absence. For an unavailable source, keep **Inspected scope result → Not assessed** and record why no text could be read; do not invent an inspected range. Read the visible requirement if Save is disabled. Historical unassessed entries remain historical; they are not rewritten by this guidance.

## Correct an entry or resolve a conflict

Open the saved cell and explicitly choose its revision/edit action. The original value, references, source binding and history remain retained. **Save revision** creates the next immutable entry rather than editing old evidence. Historical definitions/sources are read-only; choose an explicit new definition revision for changed dependencies.

Two tabs may conflict. A rejected save keeps local text/evidence; compare the saved version and explicitly rebase/restore using the offered action. Retry is not permission to overwrite another tab. Editor-step hints are separate UI drafts and cannot mark evidence or submission; a position conflict can restore the latest hints without erasing the research draft. If a network timeout follows a completed save, reopening/retrying reconciles the retained request identifier rather than duplicating it.

## Choose Core, Qwen or MedCPT

All are choices in one app. **Core lexical** needs no neural package, key or index installation. **Qwen hybrid + reranking** uses Qwen3-Embedding-0.6B plus Qwen3-Reranker-0.6B; **Biomedical/MedCPT hybrid + reranking** uses query/article encoders and a cross encoder, as an experimental passage adaptation.

For the source app, stop before changing its runtime, then explicitly run (Windows: use the bootstrap Python shown in WINDOWS_SOURCE.md):

```sh
python3.12 scripts/local_preview.py setup --with-retrieval
```

This installs optional dependencies, not weights. Re-running ordinary setup replaces the app-owned environment with the base runtime; external research/models remain. In **Research & AI Settings → Evidence retrieval**, explicitly install the chosen pinned pack, check its selected device/runtime, then index the exact retained sources for the selected board/cell. The UI shows model bytes/revisions/licenses; Qwen's official payload is 2,414,972,344 bytes and MedCPT's 1,316,720,932 bytes, before indexes/runtime overhead. Both packs can coexist outside replaceable app files. No model download happens merely by opening a page.

Changing defaults affects future work. An existing board changes profile only by an explicit definition revision, preserving old cells and receipts. Missing/corrupt/incompatible models or indexes fail visibly; choose a new explicit attempt/profile rather than expecting fallback. Indexing can be slow. The current request shows model/loading/windowing/batch progress and explicit cancellation/retry; cancellation is cooperative between native operations. A full page refresh does not automatically rediscover the prior job identifier. This is not a durable background-work guarantee. Historical real CPU/MPS tests on Mac and the separate tiny baseline Windows CPU checks do not establish sustained latency or superiority over BM25. Read VALIDATION.md for whether this exact source/archive was checked. Read RETRIEVAL.md and MODEL_REFERENCES.md in the source download.

## Configure optional generation

Core research works without an LLM. In **Research & AI Settings → AI assistance**, explicitly choose local/OpenAI/DeepSeek, model/profile and planning/proposal switches. Only the backend uses your own session-scoped key; GET returns presence only and restart requires re-entry. Nothing connects because you typed/saved a key. Each actual operation needs its own bounded data/cost consent; timeouts can still incur provider charges and budgets are not guaranteed dollar caps. There is no automatic retry/provider fallback or bundled developer key.

Suggestions remain separate from drafts/submissions. Inspect their exact sources before explicit adoption; support and Save stay human actions. Models receive untrusted source data and no action tools. Real generation/provider compatibility remains separately disclosed in VALIDATION.md, rather than inferred from mocked tests.

## Export, back up and replace the app

Use History & export for the existing CSV/JSON formats and retained histories; inspect which values are submitted versus draft-only. Export while your access session is available. Exports are scholarly records, not a complete backup of browser authorization, original sources and all runtime state.

On Windows, use the stopped `backup` / `restore` path in WINDOWS_SOURCE.md; it creates protected private archives and restores only to a new sibling directory. For macOS, stop the app cleanly, confirm its controller/services are stopped, then copy the complete external data directory privately. Keep the browser profile/cookies separately under their own OS/browser privacy controls; the app does not promise portable authentication recovery. Do not copy a running SQLite database as a consistent backup. Do not put backups, cookies, keys, source files or private exports in GitHub/public issues. Retain the original copy before any restore and use a separate test location; knowing a data path does not recover expired/lost authorization.

Replacing/extracting application files must leave the data directory untouched; run fresh setup in the replacement app before launch. Do not migrate the only data copy or change research/profile bindings silently. Models/caches are separate from both the app and scholarly exports.

## Understand the four tools and their limits

- Paper search finds bibliography candidates; a preview is bounded and does not decide eligibility.
- Evidence retrieval ranks exact retained passages; scores are not evidence-support probabilities.
- Semantic maps use paper-level embeddings and saved layouts; filtering/navigation does not refit them.
- Generation proposes editable text using separately consented model calls; it does not verify claims or conduct human review.

MIT covers original code. Dependencies, public articles, private research and optional weights keep their own notices/terms. The browser beta is local-first, with no new hosted service or automatic updater. Human research usefulness, independent review and systematic-review completeness are separate from software checks. For troubleshooting give version/source identity, OS and reproduction steps with synthetic/permitted data; remove private text, URLs with secrets and credentials before filing an issue.
