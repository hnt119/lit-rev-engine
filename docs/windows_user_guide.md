# Windows user guide — your first evidence comparison

For **Windows Experimental Beta.2** (`0.3.0-windows-experimental-beta.2`, build 3003).

**Windows 11 x64 · Experimental · Unsigned · Not tested on Windows.** Actual Windows installation, application execution, security behavior, exports and reopening remain **NOT_RUN**. The steps below describe the existing application's intended workflow, not a successful Windows installation observation. See the [Windows validation record](releases/v0.3.0-windows-experimental-beta.2/VALIDATION.md).

Start with the saved example: choose three papers, read an exact excerpt, add your interpretation and save a source-linked comparison. Core use is intended to need no separate Python, Node.js, pnpm or Docker installation, API key or model download.

[Download and install](#download-and-install) · [First research session](#your-first-research-session) · [Optional features](#optional-features) · [Saving and reopening](#saving-reopening-and-backups) · [Troubleshooting](#if-something-does-not-work)

This complements the [general user manual](user_manual.md). That manual's installation, terminal commands and distribution-status text are scoped to **Source Beta.4**. Use this guide and the Windows release instructions for this desktop installer; use the manual's linked research sections for more detail.

## Download and install

1. **Check your computer.** This installer targets **Windows 11 x64**, using an ordinary Windows user account. Windows 10, Windows on ARM and 32-bit Windows are outside this release's target and are rejected by the installer configuration.
2. **Download the official installer:** [Download Windows Setup.exe](https://github.com/hnt119/lit-rev-engine/releases/download/v0.3.0-windows-experimental-beta.2/lit-rev-engine-0.3.0-windows-experimental-beta.2-windows-x64-Setup.exe). Save it somewhere you can find again. The file is about **195.5 MB**. The [release page](https://github.com/hnt119/lit-rev-engine/releases/tag/v0.3.0-windows-experimental-beta.2) contains its matching checksums, notices and release notes; the [installation instructions](releases/v0.3.0-windows-experimental-beta.2/INSTALL_WINDOWS.md#verify-this-exact-download) give the exact size and SHA-256. Verify the download before running it. A matching checksum does not establish a trusted publisher or Windows compatibility.
3. **Open the downloaded Setup.exe only if your normal security policy permits it.** It is unsigned. No particular Defender, SmartScreen or download-warning sequence has been verified. Stop if Windows refuses the file or reports malware, damage or an integrity problem. Do not disable security protections or remove download markings to continue.
4. **Read the “Microsoft components only” agreement.** It covers the bundled Microsoft components, with the applicable license texts available before the choice. The checkbox begins unchecked: accept only if you agree; declining cancels installation. Original engine code remains [MIT-licensed](../LICENSE), and dependency terms remain separate. The complete displayed terms are retained with the installed files, as described in [Files, terms and data](releases/v0.3.0-windows-experimental-beta.2/INSTALL_WINDOWS.md#files-terms-and-data).
5. **Follow the installer, then open Start → Literature Review Engine.** Installation is configured for the current user, with a Start menu entry and uninstall support, without an administrator-elevation request. Use that same Start menu entry to open it again later. These are configured behaviors; installation and Start-menu launch have not been exercised on Windows.

You do not need to configure optional research connections or AI to try the saved example. Windows installation and execution remain **NOT_RUN**, even though host-side build and integrity checks are recorded in the release.

## Your first research session

### 1. Open the application

Use **Start → Literature Review Engine**. At Welcome, choose **Try the saved example**. If you have already left Welcome, **Help & setup** reopens the setup guide. Optional setup can wait; its optional steps offer **Set up later**.

### 2. Explore the saved papers

The desktop example action opens a separate workspace containing **thirty saved public papers** and their saved map. It does not run a live search, prepare sources or call a model. Read titles and inspect papers to understand the collection; map proximity is not evidence quality.

If you are creating an example from the regular workspace screen instead, enter a **Research question**, choose **Discovery mode → Saved example · offline**, then **Create workspace → Open saved example**. You do not need to create another workspace if the Welcome action already opened one.

### 3. Select three papers

Check **Select for exploration** for three reports. Opening a paper or clicking a map point does not select its checkbox. These are papers for a working comparison, not a formal review-inclusion decision or three proven independent studies.

### 4. Prepare their sources

Choose **Prepare & compare (3)** and read the preparation outcomes. Continue with **Continue to comparison (3)** or **Open ready comparison (3)** when offered.

| Source status | What you can use |
| --- | --- |
| Full text | The retained full-text material; preparation does not mean you have read it. |
| Abstract only | The retained abstract. Details missing here may exist in the full paper. |
| Unavailable | No inspectable text was retained; citation details alone cannot support an answer. |

### 5. Define the comparison questions

In **Create a manual board**, review **Board research question** and the selected papers/preparation. Edit each **Field … label** and **Field … retrieval subquestion**, then choose **Create comparison board**.

For practice, try *Population and setting*, *Study design* and *Relevant outcome*. Write a focused subquestion for each, such as “Who participated and where were they recruited?” These are your comparison questions, not eligibility rules.

The table has papers as rows and fields as columns. **Paper 1 of 3 · Field 2 of 3** means the second question about the first paper. Several cells can refer to the same paper. Reopen an existing board rather than making a duplicate if one is already available.

### 6. Find an excerpt for one cell

Open a cell and check its paper title, field question and source availability. Under **1. Select evidence**, choose **Find excerpts in this paper**, then **Read in source · passage 1** or another numbered result. Choose **Browse this source** if the candidates are not helpful.

### 7. Inspect the exact context

Read **Exact retained source**, including the context needed to interpret the excerpt. A displayed range may cover only part of a source block. Use **Next block range**, **Previous block range** or the source-block controls where available to read beyond it.

Opening a candidate does not declare that you inspected it, attach it or judge its support. If you need the broader passage-search screen, follow the manual's [passage search and return instructions](user_manual.md#investigate-a-cell-with-passage-search); returning to a cell still requires explicit attachment and saving.

### 8. Attach evidence and write your interpretation

After reading the range, choose **I have read this excerpt — use it**. Wait for acknowledgement. **Selected evidence** stays visible beside the comment.

Under **2. Comment & judge**, enter your interpretation in **Manual cell value**. Review **Human support judgment** and **Inspected scope result**; they begin as **Unassessed** and **Not assessed**. Change them only to reflect what you actually checked. Complete **Reason** and **Missing information** where required.

An exact quotation proves where the text came from, not that it supports your interpretation. A self-declared human support judgment is not independent verification.

### 9. Explicitly save the entry

Choose **Review entry before saving**, read the summary and any **Before saving** requirements, then choose **Save reviewed entry**. Wait for **Saved to comparison.** before **Next unfinished cell** or **Back to table**.

**Draft: saved** means editable work has been saved as a draft. It does not mean the entry has been submitted to the comparison. See the [complete editing walkthrough](user_manual.md#select-an-excerpt-comment-and-save) for more detail.

### 10. Export and return later

Use **Download board CSV** for the table or **Download board audit JSON** for its revision/source audit. **Include earlier board definitions in audit JSON** adds those earlier definitions. Keep the files privately and check the paper identities, values and unresolved states. Draft-only notes are not submitted findings in these exports.

Before closing the app normally, wait for **Draft: saved** and, for a submitted entry, **Saved to comparison.** Reopen through the same Windows account's Start menu entry, then open the existing workspace and board. Do not start a new example to resume the old one. Windows exports, restart and persistence have not been execution-tested; read the saving limits below.

## Optional features

Keep **Core lexical** for your first session. You can explore the other choices later in **Research & AI Settings**.

| Feature | What to know before using it |
| --- | --- |
| PubMed and imports | **Research sources** configures an actual NCBI contact email and explicit live PubMed access. **Discover & explore → Import papers** accepts supported CSV/RIS references or DOI/PMID input. Imports do not supply full text automatically. See [Add and prepare your own papers](user_manual.md#add-and-prepare-your-own-papers). |
| Core BM25 retrieval | Searches retained text without a neural model or AI key. It returns candidates for your inspection, not verified answers. |
| Qwen/MedCPT retrieval | Optional and experimental. **Neural libraries and model weights are not included in the public desktop installer; a matching desktop library package is not publicly offered or qualified for Windows.** Settings alone cannot make these profiles ready. The general manual's source-runtime setup commands are not instructions to modify this installed app. |
| Local/cloud AI | **AI assistance** is disabled by default. It can be separately configured for a user-run local model server or own-key OpenAI/DeepSeek access. Keys are session-scoped and need re-entry after restart. Cloud requests send the disclosed research inputs and may cost money; permissions to store a paper locally do not grant permission to transmit it. Each generation action requires explicit data/cost consent. See [optional generation](user_manual.md#configure-optional-generation). |

Saving settings is separate from testing a connection, installing weights, indexing sources or executing a search/model call. No provider fallback is automatic. The saved map needs no new model execution; fitting a new map has separate optional requirements. Real neural, PubMed and generation checks were not run for this Windows release.

## Saving, reopening and backups

- **Drafts versus entries:** Wait for the relevant acknowledgement. Only an explicit reviewed save submits an entry. If saving fails, keep the editor open and read the error before leaving.
- **Corrections:** Open the saved cell, choose **Edit saved cell**, then **Review entry before saving → Save revision**. Earlier entries remain in history. If another window changed the cell, reconcile explicitly instead of overwriting it. See [corrections and conflicts](user_manual.md#correct-an-entry-or-resolve-a-conflict).
- **Existing work:** Use the same Windows account and desktop profile. Research/profile data is outside the installed application at `%LOCALAPPDATA%\LiteratureReviewEngineDesktop`. Browser-beta work is not automatically imported into this desktop profile.
- **Exports versus backups:** CSV/JSON are research outputs, not a complete workspace or authorization backup. Close the app before backing up its complete external data directory; do not assume a live database copy is consistent. Protect profile/access state too. A surviving database or workspace ID alone cannot restore access after cookie/profile loss.
- **Replacement or uninstall:** The installer is configured to retain research data by default, but Windows replacement/uninstall/persistence checks are **NOT_RUN**. Follow the existing [version policy and storage notes](releases/v0.3.0-windows-experimental-beta.2/INSTALL_WINDOWS.md#files-terms-and-data), preserve private backups and do not delete the research folder as a troubleshooting step.

The general manual's [export and backup discussion](user_manual.md#export-back-up-and-replace-the-app) explains the distinction further; its source-launcher commands apply to the source distribution.

## If something does not work

| Problem | Next step |
| --- | --- |
| No useful excerpt, or only an abstract | Browse the retained context or use scoped passage search. Missing retrieval results do not prove whole-paper absence. Use **Continue with notes or missing information** when appropriate. Leave the value blank for a missing-information entry, record **Reason** and **Missing information**, and declare only the material actually inspected. See [missing-information instructions](user_manual.md#keep-a-note-or-record-missing-information). |
| Full text is unavailable | Do not invent an excerpt. Keep the answer unresolved and describe the source limitation. Importing a citation does not unlock publisher content; no general PDF-attachment upload workflow is documented for this release. |
| An entry will not save | Read **Before saving**. Check the selected evidence, inspected scope and required reasons. Do not choose a stronger support judgment merely to enable Save. |
| Optional AI or retrieval setup fails | Read its reported setup/runtime/index state. Keep Core/manual research available by explicitly choosing Core for new work; existing boards retain their pinned profile. Do not expect a hidden fallback or install libraries into the application files. |
| Setup or startup is blocked | Stop at security refusals or integrity errors. Recheck the release/version requirements and documented checksum; do not disable protections, edit credentials or delete locks. Windows startup remains untested; no guaranteed repair sequence is available. |
| The workspace cannot be reopened | Preserve the data and profile. Cookie/profile loss can prevent authorization even when files remain. Do not treat the workspace ID as a recovery key. |

For help, [open an issue](https://github.com/hnt119/lit-rev-engine/issues) with **Windows Experimental Beta.2 / build 3003**, your Windows version, the exact error and steps to reproduce. Use a public example; remove private excerpts, notes, keys, cookies and secret-bearing URLs. The [Windows installation guide](releases/v0.3.0-windows-experimental-beta.2/INSTALL_WINDOWS.md), [validation record](releases/v0.3.0-windows-experimental-beta.2/VALIDATION.md) and [general manual](user_manual.md#troubleshoot-a-task) provide the existing limits and task guidance.
