# User manual — evidence-first local research

**Applies to the published Source Beta v0.3.0-beta.4.** This is a clearer guide to that unchanged application, not a new executable release. Choose the papers, inspect their retained evidence, write your interpretation and explicitly save your assessment. Your first comparison needs no API key, generative model or neural download.

[Download and release notes](https://github.com/hnt119/lit-rev-engine/releases/tag/v0.3.0-beta.4) · [Rendered installation guide](https://github.com/hnt119/lit-rev-engine/blob/v0.3.0-beta.4/docs/local_preview.md) · [Windows setup](https://github.com/hnt119/lit-rev-engine/blob/v0.3.0-beta.4/docs/windows_source.md) · [Saved website demo](https://hnt119.github.io/projects/literature-review-engine/#saved-evidence)

## Choose how to start

- **Understand the idea without installing:** Try the website's saved, read-only demonstration. It does not save your work or connect to a local workspace.
- **Compare your own papers:** Install the source beta, then import references or configure PubMed.
- **Learn without keys or models:** Use **Saved example · offline** in the installed source app.
- **Install a Mac app or Windows Setup.exe:** Native installers are not publicly released. Use the source setup instructions.

The website shows ten papers from a saved public collection; the installed offline example contains thirty. These are demonstration reports, not formally included independent studies. The protocol pilot, phone prototype and question-to-evidence development branch are outside this guide. The development-only [Evidence Gap Navigator v0.1 guide](evidence_gap_navigator.md) describes targeted follow-up searches; that feature is not in the published releases.

**On this page:** [Install](#install-on-your-os) · [First comparison](#start-with-the-offline-example) · [Add papers](#add-and-prepare-your-own-papers) · [Edit a cell](#select-an-excerpt-comment-and-save) · [Passage search and return](#investigate-a-cell-with-passage-search) · [Missing information](#keep-a-note-or-record-missing-information) · [Corrections](#correct-an-entry-or-resolve-a-conflict) · [Retrieval choices](#choose-core-qwen-or-medcpt) · [Export and backup](#export-back-up-and-replace-the-app) · [Troubleshooting](#troubleshoot-a-task)

## Install on your OS

The public download is **setup required**, not a bundled native installer. It needs **Python 3.12, Node.js 24 and pnpm 10.20.0**. Download the purpose-built ZIP, manifest and SHA256SUMS from the release page's **Assets**. GitHub's automatic source archive is not the tested distribution.

### macOS Apple Silicon

Follow the [version-matched installation guide](https://github.com/hnt119/lit-rev-engine/blob/v0.3.0-beta.4/docs/local_preview.md). For beta.4, keep the downloaded ZIP and integrity files together and verify them before extracting:

```sh
shasum -a 256 -c lit-rev-engine-0.3.0-beta.4.SHA256SUMS
unzip lit-rev-engine-0.3.0-beta.4.zip
cd lit-rev-engine-0.3.0-beta.4
python3.12 scripts/local_preview.py setup
python3.12 scripts/local_preview.py launch
```

**Expected result:** setup creates the app-owned environment and production interface; launch opens the browser only after both local services are ready. Setup installs dependencies, so it needs their downloads. It does not search, infer, download model weights or migrate existing research. Fix reported prerequisites or TLS problems rather than bypassing them.

### Windows x64

Use the [Windows source guide](https://github.com/hnt119/lit-rev-engine/blob/v0.3.0-beta.4/docs/windows_source.md). It provides checksum verification and an isolated bootstrap with the Windows security prerequisite. Use that bootstrap Python for setup, launch, status and stop. No global pip installation, activation or execution-policy change is required; do not substitute the macOS commands.

Published checks cover macOS Apple Silicon and Windows x64 source workflows in the recorded environments. **Physical Windows 11 is NOT_RUN; Linux installation is unverified; Intel Mac and Windows ARM are unqualified.** See the release's [validation record](https://github.com/hnt119/lit-rev-engine/releases/download/v0.3.0-beta.4/VALIDATION.md) for exact scope. No OS-protection bypass is part of installation.

## Start, stop and reopen

Keep the source application's launch terminal open. On macOS, run these from the extracted app folder; on Windows, substitute the guide's bootstrap Python:

```sh
python3.12 scripts/local_preview.py launch
python3.12 scripts/local_preview.py status
python3.12 scripts/local_preview.py stop
```

Use **Ctrl-C** or `stop` for a controlled shutdown. Wait for **Draft: saved** before stopping. Reopen the printed application URL with the same browser profile, hostname and data directory, then open your workspace and saved board. This preserves access through the existing local session cookie; it is not a named researcher account.

Cleared or expired cookies can lose access. A workspace ID or surviving database alone cannot restore authorization. If ports are occupied, identify the other application or deliberately choose unused `--web-port` / `--api-port` values. Do not kill an unknown listener, delete active locks or modify credential records. Force-killing the source controller can leave owned services running; use the [installation recovery instructions](https://github.com/hnt119/lit-rev-engine/blob/v0.3.0-beta.4/docs/local_preview.md#launch-and-stop).

## Start with the offline example

**Goal:** create a three-paper comparison, save source-linked entries, export them and reopen the same work.

### 1. Open the public example

Enter a **Research question**, keep **Discovery mode → Saved example · offline**, and choose **Create workspace**, then **Open saved example**.

**Expected result:** thirty saved public papers and their saved semantic map appear. Opening the example needs no contact, key or new model execution. A point's position is approximate semantic similarity, not scientific quality. Opening the paper inspector does not select its checkbox.

### 2. Select three reports and prepare sources

Check **Select for exploration** for three reports, then choose **Prepare & compare (3)**. Read the preparation outcomes. If preparation finishes on its receipt, choose **Continue to comparison (3)** or **Open ready comparison (3)**, as offered.

- **Full text:** Retained full-text material is available to inspect; preparation does not mean you read it.
- **Abstract only:** Only the retained abstract can support this preparation's inspection. Missing details may exist in the full paper.
- **Unavailable:** No inspectable text was retained. Citation metadata cannot establish an answer.

Source availability is not an eligibility decision. A board is a working subset of up to thirty reports, not a limit on an entire review library.

### 3. Create three comparison questions

In **Create a manual board**, review **Board research question**, the retained preparation and the selected reports. Edit each **Field … label** and **Field … retrieval subquestion**, then choose **Create comparison board**.

For practice, use *Population and setting*, *Study design* and *Relevant outcome* as your own extraction questions; they are not predefined eligibility rules. Make each subquestion describe the information you want to find.

**Expected result:** a table with reports as rows and questions as columns. **Paper 1 of 3 · Field 2 of 3** means the second question about the first paper. Several unfinished cells can belong to the same report; the next-cell message says whether you are moving to another field or another paper.

### 4. Complete a cell, then export

Follow [Select an excerpt, comment and save](#select-an-excerpt-comment-and-save) below. Try three fields for one report before moving to another. Export the table using [the board's export actions](#export-back-up-and-replace-the-app), stop normally and reopen it. Reopening an existing board does not require creating a duplicate.

## Add and prepare your own papers

### Import references

In **Discover & explore → Import papers**, choose a supported CSV/RIS citation file or DOI/PMID identifier input, then **Parse and preview citations**. Review the records, column mapping, warnings and duplicate/conflicting identities. Accept the intended rows, enter a **Collection name**, and choose **Commit … accepted records**.

**Expected result:** a retained collection with import provenance and accounting for accepted and uncommitted rows. **Accept all eligible records** refers to rows acceptable for this import; it does not decide scientific review eligibility. Local parsing does not call an LLM or metadata provider. **Resolve selected identifiers** is a separate explicit network action.

Importing citations does not import full text or transfer subscription rights. The beta.4 web interface has no general PDF-attachment upload workflow; an older parser in the repository does not provide that UI feature.

### Search PubMed

In **Research & AI Settings → Research sources**, enter your actual **NCBI contact email** and enable live PubMed for explicit searches. Its API key is optional. **Save settings** makes no provider request; **Test PubMed connection** is a separate network action and checks connectivity, not relevance.

Create a workspace in **Live PubMed** when the connection is available. In **Search papers**, review the exact executable query, dates, sort order and maximum records. The question-to-search planner offers its available manual/concept and optional proposal paths; inspect and approve a proposed strategy before execution. An editable suggestion is not an executed search. Expert Boolean text should remain your deliberate query.

**Expected result:** a saved, bounded search preview and its recorded specification. A capped preview is not a complete systematic-review capture; a small count does not establish a research gap. Application defaults only prefill new work. Search, exploration selection, eligibility and extraction remain distinct decisions.

For either input route, select reports and explicitly prepare them. The application attempts permitted, identity-checked source acquisition or an explicitly labeled fallback. A historical board keeps its original preparation; it does not silently switch to newer sources.

## Select an excerpt, comment and save

Open a comparison cell. Check its paper title, field/subquestion, **Paper … of … · Field … of …**, and source availability before writing.

1. In **1. Select evidence**, choose **Find excerpts in this paper**. Open a candidate with **Read in source · passage 1** (or another numbered result). If candidates are unhelpful, choose **Browse this source**.
2. Read **Exact retained source**. Check participants, sample type, comparisons, outcomes and timepoint yourself. The display covers up to 4,000 Unicode code points, not necessarily the whole block or paper. Use **Next block range**, **Previous block range** or the source-block controls to inspect omitted material.
3. Choose **I have read this excerpt — use it** only after reading the selected range. This explicitly attaches it and records your declaration of inspection. Wait for acknowledgement; the comment field receives focus and **Selected evidence** stays beside it. **Mark inspected without attaching** declares only an inspected range.
4. In **2. Comment & judge**, enter **Manual cell value**. Review **Human support judgment** and **Inspected scope result**. The starting states are **Unassessed** and **Not assessed**; change them only when your assessment warrants it. Supply **Reason** and **Missing information** where required.
5. Choose **Review entry before saving**. Read the summary and any **Before saving** requirements, then **Save reviewed entry**. Wait for **Saved to comparison.** before **Next unfinished cell** or **Back to table**.

- **Open/highlight a candidate:** A possible match is displayed; no inspection, attachment or support is declared.
- **Use the excerpt:** The valid range is attached and declared inspected.
- **Draft: saved:** Editable input was acknowledged; no table entry was submitted.
- **Save reviewed entry:** An immutable entry, its references and your declared state are recorded. It can remain unassessed.
- **Human-supported · self-declared:** Your support judgment, not independent verification.

Exact source ownership, versions, hashes and quotation boundaries are checked mechanically. A matching quotation can still fail to support the interpretation. Use **Add or change evidence** within the same editor; removing evidence preserves your typed text but may introduce a new save requirement.

## Investigate a cell with passage search

Use the inline editor for ordinary work. For the broader view, expand **Comparison tools and revision history → Search passages for this comparison**, or a cell's **More evidence tools, proposals and history → Open passage search for this field**.

**Expected result:** the existing passage-search screen shows the comparison, exact retained paper scope and field where relevant. Its question is prefilled; opening it runs no search. Edit **Evidence question** and choose **Maximum passages for next search** from **5–30**, then explicitly choose **Retrieve passages** for Core. Fewer matches may return fewer passages.

Use **Inspect source for passage … ↓** to read context. A cell-origin search offers **Open in comparison cell · passage …**; **Back to cell** or **Back to comparison** returns without choosing a result. Returning opens inspection only: it does not attach evidence, replace your value, mark support or submit. Continue with the explicit use/save steps.

Your edited query, result count, selected run and cell draft are retained across navigation/refresh within this comparison scope, separately from a workspace-wide search draft. Wait for **Draft: saved** before leaving. Read stale or wrong-source messages instead of changing bindings to force a result. A passage from another paper cannot be attached to this cell.

## Keep a note or record missing information

A new unassessed note without selected evidence can remain an autosaved draft. It is separate from submitted table values and does not become a finding because **Draft: saved** appears. Do not add an irrelevant quotation to make Save available.

Choose **Continue with notes or missing information** when the answer is unresolved:

- **You inspected material but did not find the detail:** Leave **Manual cell value** blank (stored as null). Declare the actual range using **Mark inspected without attaching**, select **Not found in inspected material**, and complete both **Reason** and **Missing information**. This is not whole-paper absence.
- **The source is unavailable:** Leave the value blank and scope **Not assessed**. Complete both **Reason** and **Missing information**; do not invent a range.
- **You have not inspected enough:** Keep the judgment unassessed and retain the draft, browse more context or explain the limitation truthfully.

Read the displayed requirement if Save is disabled. Choosing a stronger support state to pass validation is not a substitute for inspection.

## Correct an entry or resolve a conflict

Open the saved cell and choose **Edit saved cell**. Revise the draft and its evidence, then **Review entry before saving → Save revision**. The original entry remains in immutable history. To inspect it, expand **More evidence tools, proposals and history → Load immutable cell history**, then use the offered historical-reference action.

Changes to papers, fields, sources or retrieval profile require an explicit board-definition revision. Old definitions and their source-bound judgments remain historical/read-only; they are not silently rewritten.

If another tab changed the draft or saved entry, keep your work and inspect the current version. **Rebase retained edits on latest saved cell** is an explicit reconciliation action, not permission to overwrite blindly. Editor-position conflicts have their own restore action and do not make a research draft a submitted entry. After a connection timeout, reopen/retry the same save to reconcile its retained request rather than assuming failure and duplicating it.

## Choose Core, Qwen or MedCPT

All three are choices in the same application; **Core lexical** is enough for the first comparison.

- **Core lexical:** BM25 / versioned lexical spans over retained text; no neural weights or generation key.
- **Qwen hybrid + reranking:** Optional `Qwen/Qwen3-Embedding-0.6B` and `Qwen/Qwen3-Reranker-0.6B`, combined with lexical retrieval.
- **Biomedical / MedCPT hybrid + reranking:** Optional `ncbi/MedCPT-Query-Encoder`, `ncbi/MedCPT-Article-Encoder` and `ncbi/MedCPT-Cross-Encoder`; an experimental passage adaptation.

Stop the source app before changing its runtime. On macOS:

```sh
python3.12 scripts/local_preview.py setup --with-retrieval
```

On Windows use its bootstrap Python. This installs optional libraries, not model weights. Then use **Research & AI Settings → Evidence retrieval** for explicit pack installation and device/runtime checks, and the selected board/cell's explicit source-index action. Follow [retrieval setup](https://github.com/hnt119/lit-rev-engine/blob/v0.3.0-beta.4/docs/hybrid_retrieval.md) and [model references/notices](https://github.com/hnt119/lit-rev-engine/blob/v0.3.0-beta.4/docs/hybrid_model_references.md).

Dependencies, weights, runtime checks and source indexes are different steps. Opening a page downloads none of them. Both packs can coexist outside the app. Missing or incompatible components fail visibly; there is no hidden fallback. Choose a supported Core profile explicitly if you want to retry without models. Indexing can take time; refresh does not guarantee recovery of an active job. Re-running setup rebuilds the app-owned environment, so preserve the intended optional flags.

A default changes future work. An existing board keeps its pinned profile until an explicit definition revision. Qwen/MedCPT remain experimental; execution checks do not demonstrate superiority over Core or scientific usefulness. **BGE paper-map embeddings are separate**: the saved map requires no new computation, while fitting a new map requires its optional dependencies, weights and private launch configuration. See [optional-feature setup](https://github.com/hnt119/lit-rev-engine/blob/v0.3.0-beta.4/docs/local_beta_optional_features.md).

## Configure optional generation

Core manual research works without an LLM. In **Research & AI Settings → AI assistance**, explicitly select a local model server, OpenAI or DeepSeek, its model/profile and desired proposal switches. Paper-provider configuration is separate. Saving settings does not test or call a provider.

Your supplied keys remain in backend-process memory for that session and need re-entry after restart. Each generation action requires its own bounded data/cost disclosure and consent. Cloud calls transmit the disclosed input; local storage does not grant permission to send an article elsewhere. Timeouts may still cost money and resource limits are not guaranteed dollar caps. No provider fallback is automatic.

Cell suggestions are labeled **AI suggestion — needs review**. Inspect their sources, edit and explicitly **Use in draft** or **Dismiss**. Adoption does not set human support, independent verification or submission. Continue through the same manual save workflow. See [settings, consent and provider boundaries](https://github.com/hnt119/lit-rev-engine/blob/v0.3.0-beta.4/docs/research_ai_settings.md); actual model/provider checks are disclosed separately in the release validation.

## Export, back up and replace the app

### Export submitted research

On the board, use **Download board CSV** or **Download board audit JSON**. JSON includes the selected definition's immutable cell revisions, source anchors and candidate audit. **Include earlier board definitions in audit JSON** adds those definitions too. A corrected cell has a new revision; the original remains historical. Draft-only notes are not submitted findings in these table exports.

The workspace's **History & export** page has separate existing workspace/assessment exports. These are different records; select the export that matches your task. Check nulls, judgment/scope states, paper identity and history after opening the file.

### Back up access and state

Export while your access session is available. CSV/JSON files are research outputs, not complete application backups or portable browser authorization.

Stop all application services before backing up. On Windows follow the guide's protected `backup` / `restore` commands; restore only to a new location. On macOS preserve the complete external data directory privately, with browser-profile/cookie access state protected separately. Do not assume a copy of a live SQLite file is consistent. Preserve the original before testing a restore; the app does not promise account transfer or recovery after cookie loss.

To replace application files, stop the old version, leave external research untouched, extract into a new app folder and run fresh setup. Do not migrate the only copy or run two versions against the same active store. Models/caches are separate. See [storage and recovery limits](https://github.com/hnt119/lit-rev-engine/blob/v0.3.0-beta.4/docs/local_preview.md#data-location-reopening-and-upgrades).

## Troubleshoot a task

- **A comment will not submit:** Read **Before saving**. Check evidence/ranges, reason and truthful missing-information state. Keep the autosaved draft.
- **No candidate answers the question:** Browse retained context, investigate with scoped passage search or record uncertainty. A missed candidate does not establish absence.
- **Cells appear to describe different papers:** Check the paper title and **Paper … of … · Field … of …**. Multiple fields can concern the same report.
- **Another tab changed work:** Inspect the saved version and reconcile explicitly; do not overwrite or discard blindly.
- **A model is unavailable or indexing is slow:** Read pack/runtime/index status. Use explicit installation, cancellation/retry or profile selection; do not expect silent fallback.
- **A draft is not saved:** Keep the page open, read its error/conflict and retry or reconcile before leaving.
- **Workspace access is lost:** Use the documented recovery limits. Do not delete locks, edit credentials or treat an ID as authorization.

For help, [report an issue](https://github.com/hnt119/lit-rev-engine/issues) with version, OS, reproduction steps and a public/synthetic example. Remove personal notes, private source text, keys, cookies and secret-bearing URLs first.

## Understand the four tools and their limits

Paper discovery/import supplies bibliography and available sources. Passage retrieval ranks possible evidence. Maps arrange paper-level representations. Generation proposes text. None of these decides review eligibility, equates reports with independent studies or verifies a scientific claim.

The original engine code uses [MIT](https://github.com/hnt119/lit-rev-engine/blob/v0.3.0-beta.4/LICENSE). Articles, dependencies, weights and research retain their own [terms/notices](https://github.com/hnt119/lit-rev-engine/blob/v0.3.0-beta.4/THIRD_PARTY_NOTICES.md). Software checks are separate from researcher usefulness, independent review and systematic-review completeness.

[Application architecture and model roles](application_architecture.md) · [Documentation index](README.md) · [Original immutable beta.4 manual](https://github.com/hnt119/lit-rev-engine/blob/v0.3.0-beta.4/docs/user_manual.md) · [Release validation](https://github.com/hnt119/lit-rev-engine/releases/download/v0.3.0-beta.4/VALIDATION.md)
