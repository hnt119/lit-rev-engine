# Research & AI Settings — source application

This guide describes the source application, including the Semantic Maps setup change. It does not add capabilities to an already installed desktop release. The published macOS desktop beta.2 excludes the mapping runtime and needs a separately qualified map-capable build/runtime. Source use is **setup required**. The existing private launch file remains supported. Opening or saving Settings makes no external provider request. The saved public example, lexical passage retrieval, exact-source inspection, manual comparison, drafts and exports need no generative model.

## Three separate kinds of configuration

- **Application/session preferences:** research contact, enabled PubMed, optional generation provider/model, feature switches and default preview sort/count. Non-secret preferences live in a private versioned JSON store under the selected external application data directory, separately from research SQLite. Changing defaults does not revise earlier searches, plans, captures, boards or sources.
- **Per-search specification:** question, reviewed concepts, exact executable query, publication dates, ordering and maximum preview records stay beside the search and in its existing history. A preview is exploratory, not a complete library capture or an eligibility decision. Sparse results do not establish a research gap. No automatic geography, outcome, language or study-type constraint is added.
- **Credentials/authorization:** optional NCBI and cloud generation keys exist only in backend process memory for the current authenticated application session. They must be re-entered after backend restart. GET returns presence only. Key-entry fields clear after submission, including failure. Keys are not ordinary drafts, research exports, URLs or browser storage.

## Configure a research source

Open **Research & AI Settings → Research sources**. PubMed requires your actual contact email, but an NCBI API key is optional. Save, then explicitly choose **Test PubMed connection** if desired. The test transmits the displayed contact and a tiny fixed diagnostic query to NCBI; it checks connectivity, not relevance/completeness. Saving contact fields alone does not mean Connected.

Europe PMC retains the current identity/permission-checked full-text or clearly labeled abstract fallback. DOI/Crossref resolve metadata, not unrestricted full text. Local CSV, RIS and supported identifier parsing does not send network/model requests; explicit metadata resolution remains separate. Changing the LLM cannot enable a paper provider, alter retrieval ranking or move embeddings to a cloud provider.

## Optional local generation

Choose **Local model server**, enter its explicit model identifier and configured revision, and the existing literal HTTP loopback `/v1/chat/completions` endpoint with a port. Enable planning and/or cell proposals separately. The application does not install/start the server or download weights. Loopback describes the destination, not a guarantee about how a separately operated server handles data.

BGE paper maps remain separate from generation and Qwen passage retrieval. Configure them in the dedicated **Semantic Maps** section below. Saved map artifacts remain usable without a model and are never refitted by filters or navigation.

## Semantic Maps

**From a collection:** open its Semantic map and choose **Set up semantic maps**. Settings keeps the collection, paper/map route and saved selection draft. Four indicators report independent observations:

| Indicator | What it establishes |
| --- | --- |
| Mapping runtime | Whether this backend contains the pinned mapping packages; metadata alone does not test their imports or native libraries. |
| BGE model weights | Whether the required files are present in the applied local cache. Explicit verification/calculation validates their hashes. |
| Applied configuration | The effective startup or saved session enablement and cache choice. |
| Computation check | The result of the explicit synthetic CPU BGE/projection test for these settings. Not tested is not Ready. |

1. Select **Enable local semantic maps** and **Save settings**. This changes the adapter used by future explicit map operations in this session. It does not mutate process environment variables, select a Qwen profile, download or compute anything. The default **Keep startup choice** preserves existing operator opt-in until you make a choice.
2. If weights are missing and this runtime supports maps, choose **Review BGE download**. The application shows `BAAI/bge-small-en-v1.5`, its immutable revision, official Hugging Face source, exact byte count and local destination. Approve the displayed files and separately click **Download approved BGE weights**, or cancel without downloading. Only pinned, hash-verified BGE files are installed. Existing Qwen installations remain separate.
3. If the pinned BGE snapshot already exists in the effective Hugging Face cache, it is reused in place. You normally do not need to choose a directory. **Use a different existing BGE cache** is an optional recovery path; its saved path now affects the actual adapter. Invalid paths are rejected without replacing your form edits.
4. Choose **Verify readiness · local BGE computation**. It encodes a few synthetic titles and tests small-collection and UMAP projections. No workspace paper text leaves the computer and no research map is created. A failed check remains visible; resolve the reported prerequisite and retry explicitly. A successful check establishes local integration, not scientific usefulness.
5. Choose **Return to research** after verification (or **Back to research**). Your original collection, selected papers and drafts are retained. Choose **Build map of this saved collection** to authorize the actual calculation on that immutable collection. Follow its job status; failure retains the collection and earlier maps. A new retry is explicit.
6. Reopen the collection and its saved map. **Saved map & build controls** selects retained artifacts; the saved manifest retains model/input/projection identity. Opening, filtering and choosing papers do not refit coordinates. The paper list remains available independently of the map.

### Missing runtime and desktop limits

The Settings indicators inspect the backend that is actually running, not every Python environment on the computer. The application cannot safely install packages into its running Python process or a signed desktop bundle. If mapping packages are missing or incompatible, the runtime indicator explains the supported source setup and restart, or the need for a separately qualified desktop build. Downloads stay unavailable until the runtime prerequisite is met.

For an extracted source installation, save your work and stop its launcher. The existing explicit setup command is:

```sh
python3.12 scripts/local_preview.py setup --with-maps --with-retrieval
```

This installs pinned optional libraries and rebuilds the source preview environment/UI; it does **not** download model weights. Keeping `--with-retrieval` retains optional retrieval runtime support when rebuilding. Relaunch with the same external data directory and browser profile/hostname, then return to Settings. Do not delete research data to repair optional computation. Existing session credentials must be re-entered after backend restart; research drafts and saved maps remain retained. Runtime setup may require network access and the source distribution's existing Python/Node/pnpm prerequisites.

The published macOS desktop beta.2 bundles neither BGE mapping dependencies nor a map-capable optional runtime. Its launcher strips inherited environment and forces maps off, so setting `MVP_MAP_ENABLED=1` in a shell cannot enable that installed build. Its Qwen/MedCPT runtime capsule is a separate capability. Do not install packages into the app or change its bundle. This PR does not publish or qualify a replacement installer.

### Recovery and retained work

Settings use the existing session ownership and revision checks. On a two-tab conflict, keep your edits, inspect the latest revision, and explicitly choose your next save basis. Changing settings invalidates the old computation check; verify the applied settings again. Setup failures do not fall back to Qwen or lexical coordinates. Incomplete or invalid pre-existing BGE snapshots are preserved; the message offers an explicit alternate cache and retry. A bounded interrupted download installs no complete snapshot. The local worker may resume previously explicitly submitted queued/interrupted map jobs after a backend restart; startup does not submit a new map. Saved maps reopen even after mapping is disabled or weights are unavailable.

## Optional own-key cloud generation

Choose exactly one primary provider, OpenAI or DeepSeek. Enter your own provider key; there is no developer key, billing proxy, automatic fallback or silent import of launch-file secrets. Only the local backend transmits model requests, to fixed HTTPS endpoints:

| Provider profile | Destination | Output contract |
| --- | --- | --- |
| `openai.chat-json.v1` | `https://api.openai.com/v1/chat/completions` | JSON-object chat output, bounded `max_completion_tokens`, then existing typed application validation |
| `deepseek.chat-json-nonthinking.v1` | `https://api.deepseek.com/chat/completions` | JSON-object chat output with thinking disabled and bounded `max_tokens`, then existing typed application validation |

Supply an explicit supported model identifier and profile/revision. Arbitrary base URLs are unsupported. These profiles do not imply every model supports the parameters or that your account has access. The response must identify the configured model; unsupported models and model-identity mismatches fail closed. This increment has **not** live-tested either provider. Configure a model whose API contract matches the selected profile; compatibility is not inferred from a provider label or populated field.

OpenAI's [Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) and DeepSeek's [Chat Completions reference](https://api-docs.deepseek.com/api/create-chat-completion/) describe the provider-specific interfaces. Responses are still untrusted suggestions; valid JSON alone does not establish scientific support.

Each explicit planning/proposal action first prepares a local disclosure: provider/model, task, question/evidence categories and amount, bounded calls/output/time, and possible account charges. Confirming authorizes that exact operation/session/settings revision for a short period. Preparing or canceling the disclosure makes no model call. A new attempt needs a new explicit authorization; no automatic billed retry or fallback runs. Acknowledged/replayed requests do not issue a second call.

The safeguards bound context, request/response size, calls, runtime and concurrency. They are **not a guaranteed dollar cap**. Prices are unavailable unless a known model/rate/date is supplied; returned usage is recorded when present, otherwise unknown. A timeout/failure can still have incurred provider charges. Removing keys/disabling a feature prevents future operations and rejects stale publication, but cannot retract already transmitted data.

No authentication or schema test runs automatically. The explicit research operation is the first generation attempt; a failed model response is not shown as a successful connection. Normal software validation uses mocks and local fixtures. Real authenticated tests and spending require separate consent.

## Human review and access

Cell proposals stay separate from drafts and submitted revisions. Inspect the exact retained source before using a proposal in a draft, recording support and submitting. Adoption never marks independent verification, support or submission automatically. Unknown/wrong-paper/ambiguous quotations and stale board/source/settings revisions are rejected. Null/insufficient-evidence outputs do not prove whole-paper absence.

Settings navigation uses the current draft-save barrier and returns to the originating research task. Unsaved settings must be saved or explicitly discarded; two-tab edits use revision checks. The existing same-browser/profile/hostname/cookie access and recovery limitations still apply. There is no account vault, credential recovery or automatic workspace transfer.

## Validation status

For this Semantic Maps source change, 152 focused mapping/settings/collection/retrieval backend tests and 203 web tests passed. Type checking, the production web build and regenerated API byte parity passed. These software suites use synthetic adapters and mocked downloads, separately from the real local BGE execution below. One intermediate full web run exposed a pre-existing asynchronous board-test wait; the wait now observes the expected second revision and the final suite passes. Existing deprecation warnings remain.

The real production-browser walkthrough used an isolated workspace with the bundled 30 public papers: create an immutable collection → select two papers → **Set up semantic maps** → enable and save with startup maps disabled → verify genuine CPU BGE/PCA/UMAP → return with selection retained → explicitly build the 30-paper BGE/UMAP map → reopen after refresh and backend restart. Missing weights, review/cancel without downloading, cache recovery, keyboard disclosures, browser Back/Forward and 390/320-pixel layouts were exercised. Running the same source with read-only bundled core Python demonstrated real missing-runtime guidance and saved-map reopening. This is source-app validation, not installed-desktop qualification.

Actual external model downloads, real LLM planning/proposals, live PubMed, native installer qualification, human comprehension and scientific usefulness are **NOT_RUN**. Qwen model files were not changed; Qwen regression coverage here is software-level, not a new encoder/reranker execution. Software checks do not validate research usefulness, independent review, eligibility or a complete systematic review.


## Evidence retrieval remains independent

The Evidence retrieval section selects defaults for future explicit passage searches and manages separately installed pinned local Qwen/MedCPT packs. Existing board definitions retain their retrieval profile; switching requires an explicit definition revision. Neither pack needs a generation key, changes paper providers, replaces BGE paper-map embeddings or supplies a human support judgment. Core lexical remains default. Both neural profiles are experimental and need explicit runtime/index readiness. See RETRIEVAL.md in the source package and the combined VALIDATION.md; actual neural retrieval is distinct from unperformed real LLM generation.
