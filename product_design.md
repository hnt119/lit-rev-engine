# Literature Review Engine — Product Design

**Design contract:** 1.0 · **Prepared:** 27 October 2026 · **Owner:** Yixuan Huang

**Purpose:** Define who this product serves, the experience it should deliver, and the trade-offs that guide development. This is a design standard for adoption, not a declaration that every capability below is shipped. Verify implementation and distribution status from the actual checkout, published release, and its acceptance record.

## 1. Product in one sentence

**Turn a research question or paper collection into a comparison you can explain, inspect, correct, and keep.**

Literature Review Engine is an open-source, local-first research workspace. It helps a researcher formulate an explainable search, understand what selected papers studied, and build a source-linked evidence table. AI may propose and retrieve; the researcher decides what the evidence supports.

The product promise is not “automatic systematic reviews” or “a model better than every alternative.” It is **less friction between a question, a source passage, and a defensible comparison**. Competitive advantage and research usefulness remain hypotheses until evaluated on real tasks.

### Decisions we have made

| Decision | Consequence |
| --- | --- |
| Local ownership, optional computation | Research records remain under the user's control; external search/model operations are explicit. Local-first does not mean every operation is offline. |
| One application and one research engine | Browser/source and desktop distributions reuse the interface, services, and evidence contracts. |
| Evidence before submitted interpretation | The ordinary path is inspect → select → comment → review/save, in one editor. |
| Core works without AI | Models, keys, neural indexing, and paid services are not prerequisites for a useful saved-example comparison. |
| Free, open-source distribution | Original engine code is MIT. Third-party code, binaries, articles, and models retain their own terms. |
| Native downloads are the intended main entry | macOS Apple Silicon DMG and Windows x64 Setup.exe become primary only when their exact artifacts are qualified and public. Source downloads remain available. |
| No paid Apple membership requirement | An honestly labeled unnotarized Mac beta is acceptable after applicable redistribution and actual downloaded-launch checks. Do not require a signing purchase as a product-policy gate. |
| Mobile and formal-review work are separate | The phone companion is a saved prototype; Track B is not the default application workflow. Resume either only through a scoped request. |

## 2. Target users, jobs, and exclusions

### Primary user

A biomedical postgraduate student or research assistant preparing a thesis section, supervisor discussion, or evidence comparison. They may already use Zotero, library subscriptions, PDFs, a spreadsheet, and an LLM. The application should cooperate with these tools rather than require replacing all of them.

A working comparison often uses a selected subset of papers. This subset is not necessarily the full library, the full search result, or the final included-study set.

### Jobs to be done

| Situation | Desired outcome | Product response |
| --- | --- | --- |
| “My question is broad and my query returns the wrong material.” | An editable, explainable strategy and useful diagnostics. | Concept-based planning, exact query preview, explicit approval, database feedback, recorded revisions. |
| “I cannot quickly tell what each paper actually studied.” | A consistent account of population, design, specimen, focus, and findings. | Researcher-defined fields, source inspection, typed attributes where supported. |
| “My spreadsheet value has lost its context.” | Return to the exact source and understand the interpretation. | Source-bound cells, visible quotations, versions, explicit corrections. |
| “AI produced a table, but checking it is laborious.” | Inspect and correct proposals without redoing the whole task. | Suggestions separated from accepted entries; evidence and interpretation visible together. |
| “I need to return to this work later.” | Durable, understandable research records and portable outputs. | Saved drafts/revisions, clear save states, exports, documented backup/access limits. |

These are working hypotheses, not demonstrated market demand. Assess them through observed use by several researchers, not only the developer's own workflow.

### Not the initial target

Large institutional collaboration platforms, autonomous medical decision tools, complete replacements for reference managers, or an all-purpose AI chat client. Do not claim clinical validity, regulatory compliance, independent verification, or exhaustive review completeness from software tests.

## 3. Success: useful work, not feature count

**Primary outcome:** effort required to produce a source-checked comparison at a stated answer coverage and error level.

A useful session ends when the researcher can explain their entries, identify unresolved information, export the result, and resume it later. A large generated table with unsupported values is not success.

| Measure | Collection method |
| --- | --- |
| First-use completion | Can a new user install/open the supported artifact and complete one saved-example entry without developer intervention? |
| Search-design quality | Time, assistance, unintended scope changes, syntax errors, and known-paper recovery on a disclosed test set. |
| Evidence quality | Correct-field coverage, correct source/cohort, sufficient context, and appropriate unresolved values. |
| Correction burden | Time and edits needed to inspect, correct, and submit an entry. |
| Reliability | Acknowledged work survives supported restart/replacement; conflicts do not overwrite research silently. |
| Continued use | Researchers voluntarily return for their own task. |

**Proposed evaluation targets, not measured claims:** at least four of five pilot users complete a three-paper/three-field task without step-by-step coaching; investigate a 25% reduction in checked-table time against their ordinary workflow without additional critical errors at comparable coverage. Revise targets before a new evaluation, not after seeing the results. Small samples guide design; they do not establish general superiority.

Compare with a spreadsheet/source-reading workflow and a capable LLM using the same permitted documents. Use an established research product when access allows. Record task order, source access, model configuration, and setup time; do not manufacture competitor failures.

## 4. Product surfaces and information architecture

| Surface | Role | Boundary |
| --- | --- | --- |
| Desktop application | Primary intended research experience on qualified Mac/Windows platforms. | Bundled core runtimes; private external data; optional models; exact artifact-specific validation. |
| Source distribution | Advanced/developer route and fallback. | Explicit setup requirements; never labeled a native installer. |
| Website and README | Explain, demonstrate, download, and teach. | Verified release links; saved public example; no private-workspace backend or API-key entry. |
| Phone companion | Short offline evidence-task prototype. | Paused; no public product/synchronization promise. |
| Track B | Protocol-defined review experimentation. | Separate ledger authority and readiness rules; not silently included in Track A. |

### Primary navigation

Within a workspace, prioritize **Find papers → Compare → History & export**. Provide **Research & AI Settings** and **Help** as supporting destinations. Broader passage search remains available, but ordinary cell review must not require leaving Compare.

Reuse the implemented terminology when it is already clear. Naming improvements are scoped UI changes, not permission to rename internal contracts.

## 5. Golden path and onboarding

The first successful journey is:

```text
Open app → Try saved example → Choose three papers → Prepare & compare
→ Open one field → Inspect excerpt → Use excerpt → Comment and judge
→ Save reviewed entry → Export → Close normally → Reopen the same work
```

The native welcome screen offers **Try the saved example** and **Set up my research workspace**. Optional setup covers research connections, retrieval, and generative assistance. Every optional step offers **Set up later**, and returning users are not repeatedly interrupted.

Core use must not require a model, API key, account with the developer, Terminal window, or runtime installation after installing a qualified native build. The source distribution remains explicitly setup-required.

Configuration state is not readiness evidence. Distinguish Disabled, Setup required, Configured/not tested, Installed, Runtime checked, Sources need indexing, Ready, and Failed as relevant. Explain the next useful action.

Saving settings or visiting a page does not search, infer, download models, or send a diagnostic request. Explicit network/computation actions may provide progress and cancellation without hiding their cost or effect. Configure a feature from the task that needs it and return without losing the draft.

## 6. Search design and paper intake

### Search experience

A question becomes editable concepts, relationships, and uncertainties before it becomes an executable query. Distinguish:

- database-search requirements;
- eligibility conditions to inspect later;
- preferences or notes;
- extraction questions;
- unresolved definitions.

Synonyms within an approved concept are alternatives. Concepts are not all blindly joined with AND. An LLM may propose structure and terms; a deterministic compiler renders supported syntax. The researcher approves the exact candidate. Preserve expert-pasted strategies without an automatic rewrite.

Show actual provider count, translation, warnings, date/limits, and the distinction between an API failure and zero matches. Explain that absence from a capped preview does not mean a known paper fails the query. Construction seeds are not held-out evaluation labels. Never silently relax a required population, outcome, or exclusion to increase the match count.

A readable strategy export retains actual approvals/executions and unresolved issues. A lint check is not specialist peer review; a complete executed-query capture is not proof of a comprehensive search design.

### Intake and access

Search, local reference import, metadata resolution, and source preparation are separate actions. Preserve every intake's origin, identifier conflicts, and exact source version. Metadata alone is not inspected evidence.

Use existing Zotero CSV/RIS/identifier capabilities. Work with the user's normal institutional browser access; do not collect publisher passwords, copy login cookies, automate paywall avoidance, or imply that a subscription permits redistribution/cloud transmission.

A general user-PDF attachment flow is not assumed to exist merely because legacy parser code exists. When absent, state the limitation and scope a separate end-to-end implementation if observed user needs justify it.

## 7. Comparison: evidence and interpretation stay together

### Standard cell layout

Always show **Paper i/N**, **Field j/M**, the field question, and source availability. A new empty cell opens at evidence selection, not an unexplained comment box.

| Step | Required interaction |
| --- | --- |
| 1. Select evidence | Retrieve candidates or browse the retained source. Open exact context inline. Nothing is attached or marked read automatically. |
| 2. Comment and judge | After explicit “I have read this excerpt — use it,” retain the quote visibly and focus the answer field. The researcher chooses scope and support. |
| 3. Review and save | Show the value, references, limitations, and unmet prerequisites. Explicit save creates an immutable submitted revision. |
| Continue | Acknowledge success; offer Next unfinished cell and Back to table, preserving focus/position. |

Keep evidence and interpretation side by side when width permits and stacked in that order when it does not. Ordinary completion must not require a different browser tab or page. Keep detailed hashes, offsets, scores, and revision records available under secondary controls.

The broader passage-search route retains the board revision, paper scope, query, requested count, source bindings, and originating cell. Returning opens the relevant inspector; it does not attach, judge, or submit automatically.

### Drafts and uncertainty

Allow exploratory draft notes before selecting evidence. Clearly distinguish **Draft saved** from **Saved to comparison**. Do not present an unsubmitted draft as a reviewed table value.

Evidence-backed submission needs the relevant explicit inspection/reference conditions. A missing-information record has a separate honest path: null value, reason, actual inspected scope or unavailable-source state. Never require an irrelevant quotation to record a limitation.

Keep these concepts separate: metadata available; full text retained; excerpt displayed; user-declared inspection; exact reference validated; semantic support assessed; independent verification. A checked quotation proves text/location, not the claim's meaning.

A partial excerpt is labeled partial. Missing text in retrieved or displayed material does not establish absence from the whole paper. Show more-context/range controls and an explicit unresolved outcome.

### Changes and conflicts

Removal of an excerpt keeps the typed text and reveals any unmet submission requirement. Source/preparation changes never silently replace historical bindings. Two-tab conflicts retain edits and require explicit resolution. Revision editing preserves the prior entry and declared producer; a generation proposal does not become a human judgment by adoption alone.

## 8. Multidimensional evidence without a complicated screen

Use one table and several views, not a 3D interface or a new copy of the dataset for each filter. The intended views are **Overview**, **Methods**, and **Needs review**, when implemented in the selected release.

Typed dimensions may cover population, recruitment geography, specimen/site, design, outcomes/focus, and evidence/progress state. Preserve multiple values and distinguish unknown, unassessed, unavailable, and not found in inspected material.

A scientific classification links to its field definition and source-bound submitted entry. A tag such as “read later” is organizational and is not scientific evidence. Suggested, confirmed, outdated, and disputed values remain distinguishable.

Report-level co-occurrence is not a same-cohort/result relationship. A report mentioning vaginal samples and menopause does not establish that its menopause result came from those samples. Do not offer relationship-specific filtering until those relations are explicitly represented.

Changing filters, groups, columns, or sort order does not revise research entries, run inference, or reindex. Retain the selected paper/field, and explain when a filter hides it. Grouped occurrences and unique-report counts are different. Mark filtered exports as filtered; retain an explicit all-record export.

Do not create a universal study-quality score or infer study independence from publication identity. Formal eligibility and report/study linking remain separate authorities.

## 9. AI and computation choices

These are design choices, not a promise that every profile or provider exists in every branch or released artifact. Check the selected checkout, its manifests, and the release acceptance record.

| Capability | Design choice | Product boundary |
| --- | --- | --- |
| Core evidence search | BM25 and versioned lexical/span profiles | Immediately usable without neural weights or generation. |
| Qwen hybrid | BM25 + Qwen3-Embedding-0.6B → rank fusion → Qwen3-Reranker-0.6B | Optional local pack; experimental. |
| Biomedical hybrid | BM25 + MedCPT Query/Article Encoders → rank fusion → MedCPT Cross Encoder | Optional local pack; passage adaptation, not proven biomedical superiority. |
| Paper map | BAAI/bge-small-en-v1.5, saved coordinates | Separate metadata representation; not a passage index or scientific-quality map. |
| Generative assistance | Compatible user-configured local/OpenAI/DeepSeek adapter | Proposes search plans/values; never owns eligibility or human support. |

Exact revisions, artifact sizes, tokenizer/scoring rules, profile IDs, and licenses belong to the implemented manifests, not a competing registry in this document. New models/profiles require explicit compatibility and evaluation; do not inherit another profile's benchmark claims.

Hybrid retrieval applies authorized scope before ranking, independently searches lexical and dense candidates, fuses ranks, and reranks a bounded set. Preserve exact Unicode source anchors. Do not silently truncate evidence, normalize incompatible score meanings, or replace a failed selected profile with BM25. Offer an explicit separate retry/profile choice.

Generation consumes only the approved question/evidence needed for that operation. Model output and source text are untrusted input. Validate references, identity, schema, and freshness before creating a proposal. Keep unknown values unknown.

Installation, model checks, source indexing, and retrieval are different states. Keep weights/caches outside application files and provide real progress, bounded work, cancellation limitations, and honest restart behavior. Do not claim continuous background work when the implementation uses bounded requests.

## 10. Local ownership and system boundaries

```text
Desktop shell / local browser
          ↓
Existing React/Next.js UI → same-origin bridge → FastAPI
          ↓
Python application services and evidence validation
          ↓
Private research records, retained sources, versioned runs and exports
          ↘ optional pinned local compute
          ↘ explicitly approved paper-source requests
          ↘ explicitly approved generation-provider requests
```

The website serves saved public data; it is not the private research backend. Legacy ledger/CLI, historical Chroma/Agnes and Qwen4B/Kaggle experiments, hosted preparation, and Track B retain separate contracts. Do not add a cloud platform, global corpus, second research engine, or new vector database just to improve presentation.

Keep the research directory external to app installs. Source-derived indexes and excerpts are private research data, not redistributable model caches. Model removal must not erase saved reviewed entries or their sources. App upgrades/uninstall preserve data unless a separate informed deletion action explicitly says otherwise.

Session-only keys do not enter URLs, logs, drafts, exports, browser storage, or published artifacts. Explain outbound data, provider/model, permitted scope, and possible charges before a billable operation. No hidden fallback or billed retry. Timeouts can still incur charges; token limits are not guaranteed monetary caps.

The current browser-cookie access/recovery limitation is real technical debt. A persistent desktop profile does not make it disappear. Surface limitations and prioritize safe recovery before encouraging users to rely on the app as their sole research record. Do not bypass authorization by workspace ID or copy cookies as a migration shortcut.

## 11. Visual language, accessibility, and performance

Reuse the existing paper/ink/olive tokens, typography, restrained borders, and source-first reading order. Avoid a competing design system. Make primary actions clear without giving every control equal visual emphasis.

Design requirements: visible keyboard focus; meaningful labels and headings; non-color-only states; readable source text; practical touch targets around 44 CSS pixels where feasible; sensible 320/390-pixel layouts; table scrolling contained inside the table; reduced-motion support for any animation. These are implementation criteria, not a claim of audited accessibility conformance.

Do not encode “bad science” with a red badge based solely on a retrieval score. Use plain-language states such as Needs review, Partial context, and Source unavailable.

Keep core interactions responsive and acknowledge saves only after persistence. Do not run model loads or provider I/O while holding research mutation locks. Measure startup, first result, indexing progress, repeat-query latency, and correction effort on actual hardware. Publish cold/warm and runtime details; no universal speed promises from one machine.

## 12. Downloads, website, and documentation

The desired public front door is **Download for Mac**, **Download for Windows**, **Try the demo**, and **User guide**, with source/setup instructions secondary. Enable only downloads that actually exist and have passed their own acceptance checks. Until native release, label the available source ZIP accurately.

A release record identifies exact source commit, artifact version, OS/architecture, bytes/hash, dependency notices, source-delivery obligations, signing/notarization status, test environment, and remaining limitations. Preserve old tags, hashes, and assets. A docs commit is not a new tested application build.

### Free unnotarized Mac policy

Paid Apple enrollment is not a prerequisite chosen by this project. A free unnotarized/ad-hoc-signed Mac beta may be published when authorized, with clear warning and actual downloaded/quarantined-app testing using Apple's documented per-app Open Anyway route where available. This is an informed user exception, not Apple verification. Managed Macs may refuse exceptions. A malware/tampering/damaged-bundle alert requires investigation; do not tell users to disable Gatekeeper globally or strip quarantine. Redistribution obligations remain independent of notarization. [R6]

Windows qualification separately records installer execution, installed workflows, and signing/reputation behavior. Do not imply a signature guarantees no warnings. Do not carry Mac-only acceptance over to Windows.

The static demonstration uses at most ten approved public papers, genuine saved coordinates, and prepared source-resolvable excerpts. Label saved results and illustrative notes. The ten-paper website limit does not reduce application capacity. Browser history, source-return focus, filters, and keyboard access should work without live APIs or models.

Keep the README compact and task-oriented. Maintain a canonical, release-matched manual and a version-bound website projection. Installation guides open as readable pages; direct files/checksums remain accessible. Model methods, experiments, and development history live one click deeper. Never change version labels without updating and verifying the actual asset bindings.

## 13. Scope control and delivery priorities

Choose work in this order:

1. Prevent research loss, incorrect source attachment, security problems, and broken downloads.
2. Remove observed friction in installing, searching, selecting evidence, saving, and returning.
3. Make export, recovery, model readiness, and documentation understandable.
4. Evaluate whether a proposed model/view actually improves real tasks.
5. Expand surfaces or workflows only with specific user evidence and a scoped decision.

Do not treat this design as a request to implement everything at once. Mobile sync, team accounts, hosted infrastructure, MCP distribution, automatic narrative reviews, fine-tuning, and new model families are deferred unless explicitly prioritized. Preserve existing prototypes rather than merging them into the main workflow by accident.

For any feature, name the user problem, smallest change, success observation, data implications, and non-goals. Prefer changing an existing component/service over adding a framework. A justified native dependency is different from a gratuitous platform rewrite.

## 14. Definition of done and evidence standard

A feature is complete for its stated scope when its affected tests pass, the intended user journey is actually exercised, failures preserve work, documentation matches behavior, and the change has the required review/authorization. An artifact is public-ready only after its own distribution checks; a UI is useful only after appropriate observed use.

Report these categories independently: implemented; mocked/offline tested; actual model/provider execution; browser/native-platform acceptance; downloaded-artifact acceptance; human usefulness; not run. Report skips and initial failures honestly. Do not add counts from overlapping reruns or imply that old tests ran on a new commit.

Retest the main bottleneck with a researcher: can they find an excerpt, understand its scope, write a defensible entry, save it, and resume without coaching? If the more complex workflow performs worse, simplify it rather than requiring more training.

## 15. Document maintenance and reference basis

Update this file when an owner-approved product decision changes. Keep its rationale brief. Release readiness belongs in the corresponding version/acceptance record, not a permanently stale “latest version” claim here. Agent execution rules live in [AGENTS.md](AGENTS.md).

**Basis:** repository main was inspected at `138bfc91d85cbe45730dd439e77f518fdbfed41d`. Local desktop/prototype reports and the owner's free-distribution decision informed the target experience; they were not independently rerun. Unmerged work is not asserted to be public. Primary users, success targets, and prioritization are product recommendations.

- [R1 — Current application/model boundaries](https://github.com/hnt119/lit-rev-engine/blob/138bfc91d85cbe45730dd439e77f518fdbfed41d/docs/application_architecture.md)
- [R2 — Published-version workflow](https://github.com/hnt119/lit-rev-engine/blob/v0.3.0-beta.4/docs/user_manual.md)
- [R3 — Implemented hybrid profile behavior](https://github.com/hnt119/lit-rev-engine/blob/138bfc91d85cbe45730dd439e77f518fdbfed41d/docs/hybrid_retrieval.md)
- [R4 — Separate workbench development guide](https://github.com/hnt119/lit-rev-engine/blob/ec7897f82005eba924475848164782848d8a1708/docs/question_evidence_user_guide.md)
- [R5 — Settings and provider boundaries](https://github.com/hnt119/lit-rev-engine/blob/138bfc91d85cbe45730dd439e77f518fdbfed41d/docs/research_ai_settings.md)
- [R6 — Apple's documented per-app approval and security alerts](https://support.apple.com/en-us/102445)

**Initial decision log:** retain local ownership/optional compute; prioritize the evidence-first comparison and explainable search; deliver one app with optional model packs; permit clearly labeled free unnotarized Mac distribution under explicit acceptance; keep mobile/Track B separate; preserve release/source/evaluation identity.
