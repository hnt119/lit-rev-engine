# Qwen cloud integration before the human pilot

The user moved cloud integration ahead of the human review pilot on 3 October 2026. The coordinator owns interfaces, priorities, acceptance and the release decision. Qwen3-Embedding-4B and Qwen3-Reranker-4B are an optional candidate-assistance path; source verification, eligibility, extraction and reconciliation remain local human work.

## Small tickets and stable interfaces

| Ticket / owner | Files and changed facts | Acceptance |
| --- | --- | --- |
| R-Q1 Retrieval | `docs/qwen-provider-contract.md`; current primary schemas/serving facts | Distinct query/document formatting, explicit instruction ownership, metadata/order/token/revision limitations and billing behavior recorded before inference. |
| C-Q1 Implementation | `src/review/qwen.py` | Stdlib native HTTPS adapter; finite nonzero vectors, exact dimensions/counts, one input per embedding call, explicit rerank pairs/instruction, finite scores, sanitized fail-closed errors, no retries or local weights. |
| C-Q2 Implementation | `src/review/cloud_retrieval.py`, `qwen_cli.py`, `review.py` | Separate index/profile provenance, released SQLite snapshot during inference, current-source revalidation, whole own quotations, explicit scoring spans, fixed candidate pool, offline response replay and unchanged ledger/frozen methods. |
| E-Q1 Evaluation | `tests/test_qwen_cloud_acceptance.py`, `docs/qwen-cloud-evaluation.md` | Independently authored support truth and operational adversarial checks; fake responses establish plumbing only. |
| R-Q2 Retrieval | New `tests/fixtures/qwen_pilot_sources/` and `qwen_pilot_gold/` | Licensed source-disjoint originals, source-first exact support alternatives and article-scoped nulls; no ranking before freeze. |
| E-Q2 Evaluation | New prospective live result and receipt checks | Independently validate new truth and source mapping; compare the fixed candidate with the whole-block lexical reference, inspect null failures, usage/latency and offline replay. |
| Coordinator Q-D | Freeze, evidence review and release decision | Accept software and live quality separately; disclose any failed or unavailable gate. No automatic model selection from old held-out data. |

The implementation agent could not start because its thread limit was reached. The coordinator implements C-Q1/C-Q2; the Evaluation agent independently checks that work. Retrieval remains separately delegated. Earlier frozen CLI/store/documents/retrieval files are unchanged; a new entry-point adapter exposes `retrieve-qwen` alongside existing `review.py` commands.

## Prospective live gate

Freeze the fresh source/gold bytes, implementation, default profile, harness and thresholds before the first real ranking. The production candidate is fixed as `qwen_hybrid`, top five returned blocks, twenty pooled blocks and RRF constant 60. The reference is `bm25_context_blocks`. Rerank-only is available for bounded diagnostic comparison, not an after-the-fact replacement if the selected candidate fails.

The eight-question set must contain six quantitative positives (at least three necessary multi-block ANDs) and two sound main-article-scoped nulls. Sufficient support sets are OR alternatives; every quotation within a set is necessary AND support. Scoring context never substitutes for an own quotation. Acceptance requires at least 85% mean own-support coverage, at least four of six complete positives, and no lower mean coverage or complete-positive count than the lexical reference. Exact own/context anchors, same-project active-source scope, read-only state and unchanged-state offline replay must all be perfect.

Nulls receive no answerable credit. Report their explicit no-answer context recovery and misleading candidates. Returned candidates do not assert answerability; the workflow requires source inspection and independent verification. This gate does not validate clinical conclusions or automatic extraction.

For this bounded evaluation, the provisional engineering budgets are reported inference cost at most USD 0.25, cold indexing within 900 seconds and warm query P95 within 60 seconds. Check a conservative workload estimate before live calls and stop further calls when observed limits are exceeded. Provider estimates and missing/unknown charges remain explicit. No deployments, model downloads, implicit retries or hidden fallback are part of this ticket.

Without actual credentials and observed provider results, only the software gate can pass. The human pilot cannot be declared Qwen-ready from scripted responses or model-card benchmarks.
