# Optional local cell-proposal adapter

This adapter is part of the additive comparison-board proposal checkpoint. It produces untrusted model text for the proposal service to validate; it never writes drafts, submits cells, marks inspection or assigns human support. The manual board remains available without a model.

## Default and configuration

Generation is **disabled by default**. Importing the adapter, constructing it, building packets, listing boards and ordinary navigation make no inference requests and download no models. No OpenAI, DeepInfra or other provider credential is read. There is one configured adapter and no provider fallback or automatic retry.

Only an explicitly operated OpenAI-compatible **local HTTP server** is supported in this checkpoint. Configuration is process environment, not a client request:

```sh
MVP_PROPOSALS_ENABLED=1
MVP_PROPOSALS_URL=http://127.0.0.1:8000/v1/chat/completions
MVP_PROPOSALS_MODEL=your-explicit-local-model-name
MVP_PROPOSALS_MODEL_REVISION=your-explicit-model-revision
MVP_PROPOSALS_SPEND_CAP_USD=0
```

The alternate literal address `http://[::1]:8000/v1/chat/completions` is accepted. The port must be explicit. `localhost`, other addresses, HTTPS, user credentials, query strings, fragments, redirects and other paths are rejected. Standard-library `http.client` opens the loopback connection directly; proxy environment variables are not used. Positive spend caps are unsupported. Setting provider keys alone does not enable generation. The model profile also binds the actual system instruction and output schema with SHA-256 digests, in addition to the prompt version.

These variables do not install or start a model server. Do not configure a local forwarding proxy to a paid or remote provider: the application cannot attest an independently operated endpoint's backend, billing or weights. The saved profile identifies the model and revision **as configured**, with `revision_status: configured_not_weight_verified`; it is not proof of the loaded weights. Connecting a free GPU elsewhere would require a separately authorized arrangement and is not implemented or demonstrated here.

No real endpoint was configured or called for the adapter checks recorded below. Existing startup and local research storage remain as described in the [manual board guide](manual_comparison_board.md).

## Packet and model contract

`build_packet(definition, paper_id, field_candidates)` takes existing `BoardCandidates` results for one retained paper and selected fields. It checks board, revision, preparation, paper, field revision, source/hash and retrieval-profile bindings. The publication service separately reconstructs the canonical retained source ranges; packet membership alone is not evidence integrity or support.

Identical canonical anchors are included once across fields. Evidence IDs bind the paper and source anchor through a deterministic SHA-256 digest. Each field receives only its own allowed IDs. Equal-looking evidence in another paper is not interchangeable. Packet fields also retain candidate-run IDs, retrieval counts and omissions. Each evidence item states its canonical block length and omitted characters, so the model sees when a retained full-text block was only excerpted. Source availability is explicit, including `abstract` and `none`.

Each included quotation stays complete. When a budget would be exceeded, the helper omits whole candidates and records omissions. It does not shorten a quotation and pretend its original anchor still applies. An oversized question or field definition that cannot fit even without evidence is rejected before inference. Candidate omission and missing lexical matches establish no whole-paper absence.

The static system instruction treats every research question, title, field and source string as **untrusted data**. The request contains only system/user messages, model identity, temperature zero, output-token limit and `json_object` response format. It supplies no action tools, credentials or execution capabilities. This instruction reduces a prompt-injection route; it does not establish model obedience or scientific reliability.

The model returns one object conforming to `ProposalModelOutput`, with exactly the requested fields enforced by the publication service. Each suggested nonnull value cites an allowed evidence ID and an exact quotation substring. Null values require a reason and explicit missing information. `context_scope` is always `retrieved_context_only`.

The adapter rejects malformed JSON, duplicate keys, non-JSON numeric constants, Markdown wrappers, truncated completions, unexpected model identity, action-bearing messages and malformed token counts. The domain then validates the typed output, field ownership, exact unambiguous quotation reconstruction and publication freshness. An exact but irrelevant quotation remains mechanically matched and **unassessed**; no component upgrades it to human-supported or independently verified.

## Hard bounds and accounting

| Resource | Bound |
| --- | ---: |
| Candidate retrieval per field | Existing maximum of 3 matches |
| Candidate quotation | Existing maximum of 1,200 code points |
| Evidence in one paper packet | 12,000 code points |
| Serialized packet | 20,000 UTF-8 bytes |
| Complete HTTP request body, including instructions/schema | 24,000 bytes |
| HTTP response body | 32,768 bytes |
| Requested output tokens | 2,048 |
| One adapter call | At most 10 seconds |
| Proposal run | At most 3 calls and 35 seconds, enforced by the service |
| Automatic retries | 0 |
| Configurable spend cap | 0 only; paid calls unsupported |

A monotonic deadline, decreasing socket timeouts and a socket shutdown watchdog bound slow response headers and fragmented bodies. Non-200 responses, redirects, compression, oversized or incomplete bodies fail without a fallback. Error messages omit provider response bodies, private source text and credentials.

Usage is the endpoint's reported prompt, completion and total tokens when present; `measured` means endpoint counts were supplied, not independently tokenized. Missing usage stays null rather than becoming zero. Zero token counts remain distinct from missing counts. Cost stays null: no price is inferred and local compute is not represented as free electricity or a measured zero-dollar cost. The run service records elapsed time, outcomes and output digests separately.

## Software evidence and limits

Executed from the repository root:

```sh
/private/tmp/lre-mvp-venv/bin/python -m pytest tests/mvp/test_cell_generation.py -q -rs
# 63 passed, no failures or skips, in 0.27s
```

All 63 checks use typed synthetic evidence and injected HTTP connection/response doubles. They cover source/run binding errors, cross-field deduplication, distinct IDs for identical quotations in different papers, conflicting anchor text, explicit excerpt coverage, whole-candidate omission, default disablement, explicit configuration, endpoint restrictions, no authorization/tools/fallback, unknown versus zero usage, malformed outputs (including nonfinite numbers and unpaired Unicode surrogates), response budgets, sanitized failures and a fragmented-response deadline. They make **no real model, provider or network calls**. The deadline check uses a short delayed response double, not a throughput benchmark.

Real-model quality, instruction adherence, token usage, latency and cost are **NOT_RUN** in this checkpoint unless a separate authorized evaluation record explicitly says otherwise. Passing these software checks does not establish scientific support, retrieval completeness or human usefulness. Proposal-service, HTTP, browser and whole-workflow results belong in the checkpoint's evaluation document.
