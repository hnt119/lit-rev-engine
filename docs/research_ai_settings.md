# Research & AI Settings — Local beta 0.3.0-beta.2

This is the browser/source distribution, **setup required**. The existing private launch file remains supported. Opening or saving Settings makes no external provider request. The saved public example, lexical passage retrieval, exact-source inspection, manual comparison, drafts and exports need no generative model.

## Three separate kinds of configuration

- **Application/session preferences:** research contact, enabled PubMed, optional generation provider/model, feature switches and default preview sort/count. Non-secret preferences live in a private versioned JSON store under the selected external application data directory, separately from research SQLite. Changing defaults does not revise earlier searches, plans, captures, boards or sources.
- **Per-search specification:** question, reviewed concepts, exact executable query, publication dates, ordering and maximum preview records stay beside the search and in its existing history. A preview is exploratory, not a complete library capture or an eligibility decision. Sparse results do not establish a research gap. No automatic geography, outcome, language or study-type constraint is added.
- **Credentials/authorization:** optional NCBI and cloud generation keys exist only in backend process memory for the current authenticated application session. They must be re-entered after backend restart. GET returns presence only. Key-entry fields clear after submission, including failure. Keys are not ordinary drafts, research exports, URLs or browser storage.

## Configure a research source

Open **Research & AI Settings → Research sources**. PubMed requires your actual contact email, but an NCBI API key is optional. Save, then explicitly choose **Test PubMed connection** if desired. The test transmits the displayed contact and a tiny fixed diagnostic query to NCBI; it checks connectivity, not relevance/completeness. Saving contact fields alone does not mean Connected.

Europe PMC retains the current identity/permission-checked full-text or clearly labeled abstract fallback. DOI/Crossref resolve metadata, not unrestricted full text. Local CSV, RIS and supported identifier parsing does not send network/model requests; explicit metadata resolution remains separate. Changing the LLM cannot enable a paper provider, alter retrieval ranking or move embeddings to a cloud provider.

## Optional local generation

Choose **Local model server**, enter its explicit model identifier and configured revision, and the existing literal HTTP loopback `/v1/chat/completions` endpoint with a port. Enable planning and/or cell proposals separately. The application does not install/start the server or download weights. Loopback describes the destination, not a guarantee about how a separately operated server handles data.

The pinned BGE map runtime/weights remain separate. Use the existing optional setup and private `--config` path documented in OPTIONAL_FEATURES.md to install dependencies and select the external cache. A cache preference in Settings is descriptive until that operator launch configuration is updated; restarting alone does not apply an inactive preference. Saved map artifacts remain usable without a model and are never refitted by filters or navigation.

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

Read the successor validation report for exact executed commands and results. Offline/mocked provider checks are separate from actual provider calls and genuine model execution. **Real LLM planning/proposals, live PubMed and new embedding execution are NOT_RUN for this successor unless an explicitly disclosed later report records them.** Software checks do not validate research usefulness, independent review, eligibility or a complete systematic review.
