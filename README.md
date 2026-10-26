# Literature Review Engine

A local research app for comparing retained papers, selecting exact evidence excerpts and exporting a table you can verify. The source beta requires setup; original engine code is MIT.

<!-- published-release:start -->
**[Read-only demo](https://hnt119.github.io/projects/literature-review-engine/#saved-evidence) · [Published source beta 0.3.0-beta.4](https://github.com/hnt119/lit-rev-engine/releases/tag/v0.3.0-beta.4) · [Download ZIP](https://github.com/hnt119/lit-rev-engine/releases/download/v0.3.0-beta.4/lit-rev-engine-0.3.0-beta.4.zip) · [Quick start](https://github.com/hnt119/lit-rev-engine/releases/download/v0.3.0-beta.4/INSTALL.md)**
<!-- published-release:end -->

## Start locally

Install Python 3.12, Node 24 and pnpm 10.20.0. Download the purpose-built ZIP and its matching manifest/checksums, verify them and extract it. The commands below use macOS syntax. **Windows x64: follow the [Windows bootstrap/setup guide](docs/windows_source.md)** instead; use its isolated Windows security prerequisite before running the launcher. Run the macOS commands in the extracted folder:

```sh
python3.12 scripts/local_preview.py setup
python3.12 scripts/local_preview.py launch
```

Setup installs dependencies and builds the production interface; it does not download models or search papers. The launcher opens the browser after readiness checks. Keep the terminal open; Ctrl-C stops it. Start with **Saved example · offline**, then open its 30-paper example. Read the [task-based user manual](docs/user_manual.md) for reopening, imports, preparation, revisions, exports and safe backups.

| Platform | Source application | Desktop executable |
| --- | --- | --- |
| macOS Apple Silicon | Tested; setup required | Private prototype; unavailable publicly |
| Windows x64 | Core and bounded Qwen/MedCPT CPU workflows tested on CI; setup required | Unavailable |

Linux installation is unverified. Physical Windows 11 is NOT_RUN; Intel Mac and Windows ARM are not qualified. See [Windows source instructions and exact evidence scope](docs/windows_source.md). A source download is not a bundled desktop installer.

## Workbench development checkpoint

This feature branch adds explainable search strategies and source-bound evidence views. These changes are **unreleased**; beta.4 downloads remain unchanged. Use the [task guide](docs/question_evidence_user_guide.md), [validation report](docs/question_evidence_validation.md) and [blank evaluation kit](docs/question_evidence_evaluation/README.md). The new checkpoint passed macOS software/browser checks and [Core-only Windows CI](docs/question_evidence_windows_validation.md) at source `bda0803`. The platform table above describes published beta.4 evidence. No participant or model-quality result is implied.

## Choose retrieval in the same app

| Choice | Setup |
| --- | --- |
| Core lexical | Default; no neural models or generation key |
| Qwen hybrid + reranking | Optional pinned Qwen3-Embedding-0.6B and Qwen3-Reranker-0.6B |
| Biomedical/MedCPT hybrid + reranking | Optional query/article encoders and cross encoder; experimental passage adaptation |

Use **Research & AI Settings → Evidence retrieval**. Installation, runtime checks and source indexing are explicit. Both packs can coexist. Changing defaults affects future work; existing boards retain their profiles until an explicit definition revision. Both neural profiles remain experimental; no superiority over BM25 or scientific validity is established.

## Review an entry

1. Open a comparison cell and **Find excerpts in this paper** or **Browse this source**.
2. Read the exact context and choose **I have read this excerpt — use it**.
3. Comment and judge support, then **Review entry before saving → Save reviewed entry**.
4. Choose **Next unfinished cell**, or return to the table; correct saved entries through explicit revisions.

The excerpt stays beside your comment in the same editor. Draft-only notes remain unsubmitted. Missing information uses an explicit limitation, not a fabricated quotation or a claim of whole-paper absence.

Research stays in a separate local data folder. Preserve browser cookies/profile/hostname; clearing them can lose access, and recovery is limited. Models are separate downloads. Optional generation uses your own session-only credentials and per-action data/cost consent; no automatic provider fallback runs. [Privacy, models and limits](docs/user_manual.md#understand-the-four-tools-and-their-limits).

[MIT](LICENSE) applies to original code; [third-party/article/model terms](THIRD_PARTY_NOTICES.md) remain separate. Report reproducible problems through [Issues](https://github.com/hnt119/lit-rev-engine/issues). Contributors can use the [architecture](docs/architecture.md), [research documentation](docs/getting-started.md) and [archived CLI/history/contribution guide](docs/legacy-cli-and-history.md).

<a id="requirements-and-installation"></a>
<a id="update-main-and-contribute"></a>
Previous CLI installation/contribution links now continue in the [archived guide](docs/legacy-cli-and-history.md#requirements-and-installation).
