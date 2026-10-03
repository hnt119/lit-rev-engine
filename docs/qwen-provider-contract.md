# Qwen 4B cloud provider contract

Provider research checked on 2026-10-03. The requested cloud profile is `Qwen/Qwen3-Embedding-4B` plus `Qwen/Qwen3-Reranker-4B` on DeepInfra. This document separates observed public schemas from adapter policy and unresolved serving behavior. No authenticated request, inference, deployment, model download, or quality ranking was performed for provider research or source/truth curation. A subsequently authorized R-Q2 ticket acquired the first two proposed XML sources into a new [source archive](../tests/fixtures/qwen_pilot_sources/README.md) and authored fresh [pilot truth](../tests/fixtures/qwen_pilot_gold/README.md).

## Routes and identity

| Operation | Exact HTTPS POST endpoint | Primary specification |
| --- | --- | --- |
| Native embedding | `https://api.deepinfra.com/v1/inference/Qwen/Qwen3-Embedding-4B` | [Public model schema](https://api.deepinfra.com/models/Qwen/Qwen3-Embedding-4B/schema/default), [native API guide](https://docs.deepinfra.com/apis/deepinfra-native) |
| Native reranking | `https://api.deepinfra.com/v1/inference/Qwen/Qwen3-Reranker-4B` | [Public model schema](https://api.deepinfra.com/models/Qwen/Qwen3-Reranker-4B/schema/default), [reranking guide](https://docs.deepinfra.com/apis/reranker) |
| Alternative embedding interface | `https://api.deepinfra.com/v1/openai/embeddings` | [4B model API page](https://deepinfra.com/Qwen/Qwen3-Embedding-4B/api), [embedding guide](https://docs.deepinfra.com/apis/embeddings) |

Use JSON and `Content-Type: application/json`, with `Authorization: Bearer <token>` supplied at runtime. The official SDK's [embedding adapter](https://github.com/deepinfra/deepinfra-node/blob/main/src/lib/models/base/embeddings.ts) passes the body to its [JSON POST client](https://github.com/deepinfra/deepinfra-node/blob/main/src/clients/deep-infra.ts); its [route constant](https://github.com/deepinfra/deepinfra-node/blob/main/src/lib/constants/client.ts) is the native inference prefix. This supplies primary-code evidence for JSON embedding transport, although no live compatibility call was made here. The native guide also shows a multipart embedding example. Reranker JSON transport is explicitly shown on the [4B API page](https://deepinfra.com/Qwen/Qwen3-Reranker-4B/api). Credentials must never enter receipts, URLs, request-body archives, or exception text. [Authentication documentation](https://docs.deepinfra.com/account/authentication).

Both author cards identify Apache-2.0 weights, 4B parameters, and 32K context; the embedding model has a native 2560-dimensional representation. These are author/model claims, rather than a measurement of DeepInfra's implementation. [Embedding author card](https://huggingface.co/Qwen/Qwen3-Embedding-4B), [reranker author card](https://huggingface.co/Qwen/Qwen3-Reranker-4B).

Native responses do not require a model identifier or weight revision. Bind identity to the configured URL and receipt, without inventing an echoed model or immutable revision. The generic native API offers an optional `version` query parameter, but this research did not establish a valid immutable 4B serving version or its mapping to an author weight hash. Record the requested alias, `provider_revision: null`, and that limitation. [Inference API reference](https://docs.deepinfra.com/api-reference/inference/inference-model).

## Embedding request and prompt

The native embedding schema has these relevant fields:

| Field | Provider schema |
| --- | --- |
| `inputs` | Array of strings, at most 1024; default empty array, marked soft-required |
| `custom_instruction` | String, at most 512 characters; prepended to each input; an empty string disables it |
| `normalize` | Boolean; default `false` |
| `dimensions` | Integer 32–8192; omitted uses the model default; values above the default are zero-padded |
| `service_tier` | `default`, `priority`, or `flex`; priority is premium, flex discounted and capacity-dependent |
| `fail_fast` | Boolean, default `false`; `true` rejects unavailable capacity with 429 instead of queueing |

These are directly observed in the [4B native schema](https://api.deepinfra.com/models/Qwen/Qwen3-Embedding-4B/schema/default). The selected adapter accepts text only, caps outer input groups at 16, and sends singleton native embedding requests. It requests `service_tier: "default"` and `fail_fast: true`. Do not use generic image, multimodal, webhook, or dimension-padding capabilities in this profile.

For explicit prompt ownership, send `custom_instruction: ""` and format each query once on the client using the author-card `Instruct:/Query:` pattern below. The instruction literal is the project's prospectively selected task, not a provider default or quality result. Send document representations without the query prefix, bound to exact canonical source spans. Keep the instruction literal in the profile and hash the exact transmitted strings. This choice avoids relying on an undocumented OpenAI-route default instruction. [Author query-format pattern](https://huggingface.co/Qwen/Qwen3-Embedding-4B).

```text
Instruct: Retrieve source passages relevant to the research question.
Query: <original query>
```

Example request shape, with placeholder query text:

```json
{
  "inputs": ["Instruct: Retrieve source passages relevant to the research question.\nQuery: <original query>"],
  "custom_instruction": "",
  "normalize": false,
  "dimensions": 2560,
  "service_tier": "default",
  "fail_fast": true
}
```

Apply one explicit local L2-normalization step after validating the returned vector. Persist this policy, including the raw-response vector and resulting normalized vector digest. Reject an empty/zero-norm vector, nonfinite component, boolean masquerading as a number, wrong dimension, or nonfinite normalized result. Do not silently pad, reduce dimensions, substitute a vector, or change models. These are local acceptance rules, not provider guarantees.

Native output requires `embeddings` (array of numeric arrays) and `input_tokens` (integer). It optionally includes `request_id` and `inference_status`; there are no per-vector IDs or indices. The schema describes an embedding for each input, but does not explicitly guarantee array order. Position-based binding is therefore an interface inference. A singleton request removes this ambiguity; batching requires an explicit recorded assumption and an authorized batch-versus-singleton compatibility check before relying on it for source binding. Synthetic tests alone cannot establish server ordering. [Native schema](https://api.deepinfra.com/models/Qwen/Qwen3-Embedding-4B/schema/default).

The alternative OpenAI route documents `model`, string-or-array `input`, and float output. Its response has `object: "list"`, `data` entries with `index`, `object: "embedding"`, and `embedding`, a model alias, and `usage.prompt_tokens`/`usage.total_tokens`. If that route is used later, validate a complete unique index permutation, reorder by index, and reject a mismatched model. The generic API reference additionally exposes `dimensions`, `fail_fast`, and base64 encoding; the simpler tutorial lists only float. Neither establishes OpenAI-route `custom_instruction` behavior. Do not forward native-only options to it without verification. [Model example](https://deepinfra.com/Qwen/Qwen3-Embedding-4B/api), [tutorial](https://docs.deepinfra.com/apis/embeddings), [generic reference](https://docs.deepinfra.com/api-reference/embeddings/openai-embeddings).

## Reranker request and binding

Send raw query text and declared exact-span representations of candidate blocks, with one fixed explicit instruction. Do not send the embedding `Instruct:/Query:` prefix or the author's low-level chat/yes-no template: DeepInfra's reranking interface accepts separate fields. The exact internal renderer and yes/no computation are not exposed by the provider schema. [Provider guide](https://docs.deepinfra.com/apis/reranker), [author model card](https://huggingface.co/Qwen/Qwen3-Reranker-4B).

```json
{
  "queries": ["<original query>"],
  "documents": ["<canonical block A>", "<canonical block B>"],
  "instruction": "Retrieve source passages relevant to the research question.",
  "service_tier": "default",
  "fail_fast": true
}
```

The guide explicitly allows one query to broadcast across documents; otherwise the lengths must agree. The native schema caps each array at 1024 and `instruction` at 2048 characters. Its default is “Given a web search query, retrieve relevant passages that answer the query”; the selected adapter explicitly overrides it with the project task shown above. The generic schema also accepts multimodal document objects for other models; this Qwen adapter should reject them. [Reranking guide](https://docs.deepinfra.com/apis/reranker), [4B schema](https://api.deepinfra.com/models/Qwen/Qwen3-Reranker-4B/schema/default).

Required output is `scores` (numeric array) and `input_tokens` (integer). The guide states that scores are in [0,1] and preserve document order. Map score position back to the locally retained candidate identity and whole-block hash. Require exactly one finite nonboolean score per submitted document; reject partial, extra, out-of-range, or malformed scores. Sort descending with a persisted deterministic tie rule. A relevance score is not answer correctness or calibrated clinical confidence. [Provider ordering/range guarantee](https://docs.deepinfra.com/apis/reranker).

The model-page sample sends one document but displays three illustrative scores, `request_id: null`, and status `unknown`. That sample is not a successful-call receipt and cannot override cardinality checks. The required response fields are settled by the schema and guide; optional request ID may be absent/null, or a nonempty string. [4B model-page example](https://deepinfra.com/Qwen/Qwen3-Reranker-4B/api).

## Metadata, limits, errors, and cost

Both native output schemas optionally include `inference_status`. Its fields are `status` (choices unknown/queued/running/succeeded/failed; default succeeded), `runtime_ms`, `cost`, `tokens_generated`, `tokens_input`, and `output_length`. Only `cost` is required inside that optional object; it is an estimated USD charge. Preserve received fields without fabricating absent values. Locally require nonnegative integer token counts (excluding booleans), finite nonnegative cost, and, if a status is explicitly supplied, `succeeded` before consuming results. Never treat unknown/queued/running/failed as synchronous success. [Embedding schema](https://api.deepinfra.com/models/Qwen/Qwen3-Embedding-4B/schema/default), [reranker schema](https://api.deepinfra.com/models/Qwen/Qwen3-Reranker-4B/schema/default).

DeepInfra advertises 32768 context on both 4B pages. Neither observed schema exposes a truncation flag, truncation side, exact tokenizer revision, per-item token usage, or proof that oversize input is rejected rather than truncated. Token usage is aggregate after inference and cannot prove that every original block was consumed. The selected adapter uses explicitly bounded exact-span document representations of at most 6000 UTF-8 bytes, returns whole canonical quotations, and separately records the representation's source offsets/hash. It does not alter the canonical block. A representation cannot be mislabeled as the model having read omitted content, nor can scoring context receive sufficient-support credit. Freeze query/pair/request byte limits too, including prefix/instruction and an allowance for unexposed template overhead; reject over-budget inputs before sending. Byte limits are resource policy, not exact token counts. Do not claim measured full-context behavior until separately tested. [Embedding API page](https://deepinfra.com/Qwen/Qwen3-Embedding-4B/api), [reranker API page](https://deepinfra.com/Qwen/Qwen3-Reranker-4B/api).

| Failure | Adapter action |
| --- | --- |
| Non-2xx, invalid JSON, invalid vector/score/metadata | Reject result; retain sanitized status and response evidence |
| 400/401/403/404/422/423 | Stop the attempt; require a corrected request, permission, availability, or explicit method decision |
| 429 or 500/502/503 | Potentially transient; retry only under an explicit bounded retry/budget policy |
| Connection loss/read timeout | Outcome and charge may be unknown; do not silently resubmit |

Use zero automatic retries for the first acceptance profile, including any SDK's retries. The official Node SDK defines five retries and broadly retries caught failures; avoid inheriting that behavior. [SDK retry constant](https://github.com/deepinfra/deepinfra-node/blob/main/src/lib/constants/client.ts), [retry loop](https://github.com/deepinfra/deepinfra-node/blob/main/src/clients/deep-infra.ts). No idempotency or free-failed-request guarantee was found for these routes. If retries are later enabled, log each attempt separately, honor a bounded valid Retry-After when present, use bounded backoff, and never silently switch to another model. Provider documentation distinguishes malformed/auth failures from availability failures; its blog's fallback example is not a requirement to change this engine's selected method. [Error guidance](https://deepinfra.com/blog/model-deprecation-llm-apps).

The documented default concurrency limit is 200 active requests per model per account, rather than requests per minute. A 429 can also occur below that limit when the model is busy. Use a much smaller explicit client concurrency budget. [Rate limits](https://docs.deepinfra.com/account/rate-limits).

Current listed rates are $0.020 per million embedding tokens and $0.025 per million reranker tokens; priority/flex can change the applicable rate. Use `service_tier: "default"` for a stable requested tier, record date/rate/tier, and treat token-derived cost as an estimate. Reranking may bill the query/instruction again across pairs; the exact accounting breakdown is not documented. Record aggregate usage and returned estimated cost separately. A missing response is unknown cost, not zero. [Embedding price](https://deepinfra.com/Qwen/Qwen3-Embedding-4B/api), [reranker price](https://deepinfra.com/Qwen/Qwen3-Reranker-4B/api).

When a provider request ID exists, the separately authenticated request-cost endpoint can return `costNanoUsd` for specified IDs. This research did not call it, and the retrieval adapter need not make an extra billing request. [Request-cost reference](https://docs.deepinfra.com/api-reference/logs-%26-metrics/get-request-costs).

For later authorized public-source calls, archive raw response bytes locally before interpretation, with their hash, request-body hash, source/block bindings, model URL, profile hash, UTC timing, HTTP status, sanitized request ID, usage/cost fields, and final validated outcome. Keep profile/dimension/prompt/normalization/source-block identities distinct from the old BGE collection; model-name-only equality is insufficient. Receipts prove observed requests/responses, not immutable hosted weights or unreported server preprocessing.

DeepInfra says ordinary inference inputs/outputs stay in memory, are deleted afterward, and request content is not logged or used for training; it retains debugging metadata. Its bulk inference policy has a longer encrypted retention exception. These are provider statements, not an audit or authorization to send private research data. The proposed acceptance corpus contains licensed public article text only. [Data privacy policy](https://docs.deepinfra.com/account/data-privacy).

## Fresh source proposals for later acceptance

These candidates were chosen before any Qwen quality outcome, by routine noninfectious imaging design, quantitative results, and inspectable main tables. Initial research inspected publisher HTML and license links. R-Q2 subsequently acquired the first two unchanged main XML sources and checked their direct metadata/bytes/tables/caveats; independent source/truth review and Root's prospective freeze remain separate requirements. The third candidate remains a proposal. Each page offers an XML download. The article license does not automatically license external datasets or patient images, which are outside the proposed corpus.

| Candidate and publisher page | Publication and design | Main-text retrieval value |
| --- | --- | --- |
| [Ramli Hamid et al., Comparative analysis of diagnostic performance in mammography: A reader study on the impact of AI assistance](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0322925), DOI `10.1371/journal.pone.0322925` | 2025-05-07; retrospective study of 434 mammograms, four readers, interpretations with/without AI; five main tables | Tables 4/5 separate overall/dense-breast accuracy; methods identify readers, washout and reference standard. The abstract's broad improvement claim accompanies a numerical specificity decrease; preserve region-specific claims rather than correcting them. |
| [Lin and Wu, Ultrasound classification of non-mass breast lesions following BI-RADS presents high positive predictive value](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0278299), DOI `10.1371/journal.pone.0278299` | 2022-11-30; retrospective cross-sectional study, 59 women/59 ultrasound-detected lesions; four main tables | Population filtering, BI-RADS thresholds, malignancy denominators and numerical accuracy; distinctions between own non-mass cohort and cited breast-mass performance. |
| [Fu et al., Carpal Tunnel Syndrome Assessment with Ultrasonography: Value of Inlet-to-Outlet Median Nerve Area Ratio in Patients versus Healthy Volunteers](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0116777), DOI `10.1371/journal.pone.0116777` | 2015-01-24; blinded ultrasound assessment, 46 patient wrists and 44 healthy-volunteer wrists; five main tables | Table 5 distinguishes cutoff-specific sensitivity/specificity/likelihood ratios; own-study results, reference standards and comparison-study thresholds appear in separate regions. |

All three publisher copyright notices link [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Preserve author attribution, title, DOI, publisher URL, license link, unchanged-source/version notices, and derivative notices if later parsed or redistributed. The research shortlist is nonexhaustive and is not clinical validation.

The three candidate DOIs differ from the known prior/source exclusions `10.1371/journal.pmed.1004019`, `1004109`, `1004026`, `1004422`, `1004510`, `1004629`, and `10.1371/journal.pone.0329611`, `0340276`, `0188679`. The abbreviated suffixes here inherit their preceding journal prefix. R-Q2 additionally checked the selected first two DOI identifiers against all four existing `medical_sources*/manifest.json` files with no overlap; metadata manifest pins are recorded in the new archive. It did not use old question/gold content or open legacy source XML. Fresh article identities alone do not establish unseen model-training content or broad domain generalization.

Freeze source acquisition, independently authored truth, candidate pool/top-k, prompts, byte limits, retries, metrics, latency/cost limits, and failure handling before the later quality comparison. Preserve every necessary distinct canonical block and every identified sufficient alternative; include quantitative and genuine nonreporting cases. Compare the selected cloud method with the fixed lexical baseline on the same new sources, with exact-anchor verification and literal full-support scoring. Do not reuse old gold to tune this profile or describe synthetic/provider-schema success as medical retrieval acceptance. Root and Evaluation own that prospective gate.

## Public schema observation pins

These fingerprints describe public schema documents, not model weights. They were read with unauthenticated HTTPS GET and were not saved as new source fixtures.

| Schema | UTC observation | Byte length | SHA-256 |
| --- | --- | --- | --- |
| [Embedding native default](https://api.deepinfra.com/models/Qwen/Qwen3-Embedding-4B/schema/default) | 2026-10-03T02:50:05.707435+00:00 | 7146 | `6fbe4605a29fcb00b5b934a10a565592ac9eec1285a34a6a4bf32114a8b6504a` |
| [Reranker native default](https://api.deepinfra.com/models/Qwen/Qwen3-Reranker-4B/schema/default) | 2026-10-03T02:50:06.453066+00:00 | 8143 | `57da19256d39b46228ef164e1b4030f44aeaf062fc5028fc3b9840dee709069a` |
