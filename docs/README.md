# Documentation

Start with the published **[source beta.4](https://github.com/hnt119/lit-rev-engine/releases/tag/v0.3.0-beta.4)** and the **[practical user manual](user_manual.md)**. The revised manual explains that unchanged release; it does not replace or rebuild its ZIP. Immutable release guides remain available below; development material has its own scope. The [saved public demo](https://hnt119.github.io/projects/literature-review-engine/#saved-evidence) is read-only and makes no live search/model calls.

## Use the published application

| Task | Guide |
| --- | --- |
| Verify, install and launch | [Rendered installation guide](https://github.com/hnt119/lit-rev-engine/blob/v0.3.0-beta.4/docs/local_preview.md) · [Windows x64 bootstrap](https://github.com/hnt119/lit-rev-engine/blob/v0.3.0-beta.4/docs/windows_source.md) · [Offline guide download](https://github.com/hnt119/lit-rev-engine/releases/download/v0.3.0-beta.4/INSTALL.md) |
| Make a first comparison | [Practical first-comparison walkthrough](user_manual.md#start-with-the-offline-example) · [Original release manual](https://github.com/hnt119/lit-rev-engine/blob/v0.3.0-beta.4/docs/user_manual.md) · [Download original manual](https://github.com/hnt119/lit-rev-engine/releases/download/v0.3.0-beta.4/USER_MANUAL.md) |
| Choose Core, Qwen or MedCPT | [Retrieval choices and setup](user_manual.md#choose-core-qwen-or-medcpt) |
| Configure optional local/OpenAI/DeepSeek generation | [AI settings, consent and limits](user_manual.md#configure-optional-generation) |
| Reopen, troubleshoot or protect research | [Start/stop/reopen](user_manual.md#start-stop-and-reopen) · [Exports, backups and recovery limits](user_manual.md#export-back-up-and-replace-the-app) · [Troubleshooting](user_manual.md#troubleshoot-a-task) · [Report an issue](https://github.com/hnt119/lit-rev-engine/issues) |
| Understand the stack and model roles | [Application architecture](application_architecture.md) |

The download requires setup: macOS Apple Silicon tested; Windows x64 source workflows tested on CI. Physical Windows 11 is NOT_RUN; Linux installation is unverified, Intel Mac/Windows ARM unqualified. No public native executable. The release's [validation record](https://github.com/hnt119/lit-rev-engine/releases/download/v0.3.0-beta.4/VALIDATION.md) states exact software/model scope, not scientific usefulness.

## Current source and development/reference

- [Canonical practical manual for beta.4](user_manual.md), [Research & AI Settings](research_ai_settings.md) and [optional-feature setup](local_beta_optional_features.md).
- [Hybrid retrieval contracts and boundaries](hybrid_retrieval.md), [model references/notices](hybrid_model_references.md) and [passage-search return to comparison](comparison_passage_roundtrip.md).
- [Manual comparison contracts](manual_comparison_board.md), [optional cell proposals](cell_proposals.md) and [source inspection](source-documents.md).
- [Observed beta.4 download diagnosis and entry-point repair](releases/v0.3.0-beta.4-download-diagnosis.md).
- [Software/model validation](source_beta4_validation.md), [hybrid execution evidence and limits](hybrid_validation.md), [scientific retrieval evaluation](evidence-evaluation.md). These are distinct reports with their own scopes.
- **Feature branch only, absent from beta.4 and inspected main:** [question-to-evidence user guide](https://github.com/hnt119/lit-rev-engine/blob/ec7897f82005eba924475848164782848d8a1708/docs/question_evidence_user_guide.md) and [Windows Core evidence](https://github.com/hnt119/lit-rev-engine/blob/ec7897f82005eba924475848164782848d8a1708/docs/question_evidence_windows_validation.md). A main merge and a release are separate events.
- **Legacy/research paths:** [ledger/CLI architecture](architecture.md), [research starter guide](getting-started.md), [PubMed complete-capture contract](pubmed-search.md), [archived CLI/install/contribution history](legacy-cli-and-history.md). These do not replace the current application guide.
- **Separate/deferred distributions:** [private desktop prototype](desktop_preview.md) and [deferred hosted implementation](deployment.md); neither is the public source download or an active hosting claim.

[MIT license](../LICENSE) · [Third-party, article and model notices](../THIRD_PARTY_NOTICES.md) · [Repository entry point](../README.md)
