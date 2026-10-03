# Qwen cloud integration: independent acceptance

E-Q1 prospective contract recorded on 3 October 2026 before observing implementation rankings. This is a software readiness check for an optional Qwen3-Embedding-4B / Qwen3-Reranker-4B cloud path in `review.py`. It uses newly authored synthetic source text, fake responses and offline replay. It makes no live Qwen quality, medical validity, latency, availability or cost claim. No paid inference, model download or existing frozen medical evaluation is part of this check.

## Bounded support truth and acceptance

`tests/test_qwen_cloud_acceptance.py` authors one eight-block synthetic XML source. Two answerable questions and two nulls are fixed before cloud execution:

| Case | Required own-source support | Limit |
| --- | --- | --- |
| Adult 12-month estimate | Adult randomized population/timepoint/analysis paragraph AND result table with −3.1 and its 95% CI −4.8 to −1.4 | The separate 6-week uncontrolled sample is a distractor. The population paragraph must be an own candidate even if it also occurs as table scoring context. |
| Severe adverse events | Complete singleton with count and denominator OR the separate denominator AND count paragraphs | A hit on one member of the two-block alternative is incomplete. |
| Pediatric estimate | No sufficient support set; explicit no-pediatric estimate paragraph is context | Overall adult estimate is a hard negative for the requested pediatric result. |
| Work productivity effect | No sufficient support set; explicit unmeasured-outcome paragraph is context | A symptom result cannot supply the requested unmeasured outcome. |

Scripted ideal responses must produce 2/2 complete own-support at five and perfect canonical own/context anchors. Deliberately omitting a required companion must fail completeness. Candidate-pool support and final support are distinct: a reranker cannot recover a block absent from its recorded pool. Nulls have no answerable-denominator credit; their nonempty candidates, context recovery and misleading estimates are reported separately. The cloud result remains `candidate_passages` and creates no answer, finding, screening decision or verification.

## Interface gates

The operational path must preserve exact complete canonical own blocks and typed locators, active source/version/record ownership, source/blocks/parser hashes, eligibility and manual study-link projections. Same-project and requested-scope selection must hold for both the index and returned candidates. Search is read-only; provider calls occur after the local snapshot closes, and the current source/eligibility/linkage manifest is revalidated before publication. Selected-source corruption, identity contradiction or a change during cloud work fails closed.

The embedding profile separates query instruction from unprefixed document encoding and records an explicit reranker instruction. Profile provenance includes model, dimension, encoding/normalization/similarity and bounded representation rules. Returned embeddings require exactly one finite nonzero vector of the declared dimension per requested text. The native embedding adapter sends one document per request, eliminating reliance on an unspecified embedding batch order. Reranking requires one finite score per declared input pair in the provider's documented document order. Both requests explicitly select the default service tier and fail fast. A returned model field must match the requested alias when present; absent immutable model/revision metadata remains an explicit limitation. Malformed numbers, invalid metadata, count mismatches, provider errors and timeouts must raise an explicit failure; they cannot return an apparent successful cloud result through an implicit lexical fallback.

Long scoring representations remain traceable to exact source bounds. They cannot replace a full source quote with normalized, truncated or stitched model-input text. Query byte ceilings include the instruction and formatting; document ceilings apply to each exact scoring representation. These local byte limits do not expose actual server tokenization or prove the server never truncates. The index is rebuildable and separate from the ledger; a changed source or document profile invalidates it. Query/profile changes are explicit and receipts bind the actual selected configuration.

A receipt binds query, project, scope, source manifest, profiles, representations/candidate pool, nonsecret requests and actual responses. Offline replay uses these recorded responses and independently reconstructs ranks and anchors. It rejects changed current sources/scope, response/schema tampering and request-binding mismatch, even if a saved result is superficially plausible. Replay runs with networking denied and uses the original receipt digest supplied separately from the receipt. Receipt hashes detect accidental or partial tampering; a locally consistent rewrite is not cryptographic proof of provider authenticity.

## Reporting boundary

The checked paths are the existing lexical reference, cloud rerank over its bounded lexical pool, and cloud hybrid union followed by reranking. Fake-provider scores exercise those paths; they are not measured Qwen retrieval quality. Existing v1/v2/v3 sources, questions, results and thresholds remain unchanged and are never reused as new tuning or held-out data. Existing local BGE collection and lexical defaults stay explicit baselines.

A live pilot still requires a configured permitted deployment, actual provider/model/revision limitations, source-disjoint prospective support truth and measured latency/token/cost budgets. No latency/cost threshold can pass from these offline tests. Human inspection, manual proposal and independent evidence verification remain required.

## Execution result

The independent command `.venv/bin/python -m pytest tests/test_qwen_cloud_acceptance.py -q` passed **81 tests in 1.78 seconds**. This passes the bounded software gate above. It includes both cloud modes through the facade and `review.py retrieve-qwen` offline replay through a subprocess with networking, real sleep and local model imports denied. A loader stub prevents credential-file access in those subprocesses.

| Scripted path | Complete own support at five | Null behavior |
| --- | --- | --- |
| `qwen_rerank` | 2/2 answerable questions | Both nulls return their declared context and an adult/symptom estimate hard negative; no answerability or verification is inferred. |
| `qwen_hybrid` | 2/2 answerable questions | Same explicit null limits. |

The checks separately establish full candidate-pool coverage and demonstrate incomplete final support when a required own companion is omitted. They verify complete padded Unicode quotes, typed XML table locators, bounded exact scoring spans, read-only ledger behavior, active-version/project/scope selection, selected-source corruption rejection and provider-call execution outside a database transaction. Source replacement, screening, study linkage and scope addition during each of document encoding, query encoding and reranking reject publication without creating index/receipt artifacts.

Cold fake execution uses ten calls for eight blocks, one query and one rerank batch; a valid cache uses two calls. Explicit rebuilding works after source/profile changes or malformed vector storage; stale/corrupt caches fail without a hidden rebuild. Replay performs zero actual provider calls, retains ten recorded calls, reconstructs the same passages and rejects changed query/scope/mode/limits/profile/current source state, missing trusted digest and partial receipt tampering even with a recomputed internal checksum. Output collisions preserve ledger/WAL files and existing receipts. Token/cost/time accounting distinguishes actual calls from recorded replay; the fake zero costs and 0.01-second timings are test inputs, not measurements of cloud inference.

One independently discovered implementation defect was repaired before this pass: the embedding query ceiling initially checked raw text only, allowing formatted instruction text to exceed the declared limit. The retained test now requires rejection before any provider call. The replay call-count report was also corrected to distinguish actual calls from recorded calls. No thresholds or synthetic support truth changed in response to rankings.

## E-Q2 pre-live independent acceptance

The separate `tests/test_qwen_pilot_evaluation.py` adds **51** harness/source checks. The combined independent command `.venv/bin/python -m pytest tests/test_qwen_cloud_acceptance.py tests/test_qwen_pilot_evaluation.py -q --tb=short` passes **132 tests in 2.24 seconds**, before the first live pilot ranking. This remains software and truth acceptance; no actual Qwen quality result has been observed by Evaluation.

The prospective harness now excludes scoring context and ranks beyond five from own-support credit, uses OR alternatives and AND quotation requirements, and rejects empty support denominators. It validates current included scope, complete manifest and source/blocks/parser/record/linkage provenance, full own blocks, typed locators, exact context bounds, integer offsets/ranks and finite scores. All eight questions and their source quotations are validated before constructing a provider client. Freeze checks require complete implementation/evaluation/source/gold pins, exact profile identity and contained paths; each negative test first establishes a valid complete freeze, so a missing unrelated prerequisite cannot make the negative pass accidentally.

Observed cost/status validation precedes further budgeted calls. Invalid or absent cost, provider failure, a cost overrun, or a cold/warm deadline stops the client and preserves the last observed request/response. The stopped state cannot be cleared by starting another query. The deadline checks run both before HTTP and after the response; an unknown failed-call charge is recorded explicitly. Tests use scripted clocks and responses, so they establish stopping/accounting behavior without measuring real service performance. The quality, cost and latency thresholds in `docs/qwen-milestone.md` remain fixed.

Evaluation independently reconstructs every accepted block directly from retained original XML without calling the source parser or either acquisition/gold checker. All **102 blocks, nine tables, 36 support spans and four context spans** match exact source paths, order, typed locators, literal Unicode text and hashes. Raw byte hashes/lengths, own DOI/title/license URLs and all recorded discrepancy fragments reconcile. Metadata-only checks confirm DOI disjointness from all four earlier source archives. The final source and gold checkers additionally pass **13 source tamper negatives**, **20 gold tamper negatives**, and one historical-runtime-preservation positive each.

The publisher pages independently match the acquired identity, authors and publication dates, and their copyright links identify CC BY 4.0: [mammography reader study](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0322925), [ultrasound non-mass-lesion study](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0278299), [license deed](https://creativecommons.org/licenses/by/4.0/). This is a limited publisher-page and retained-XML observation, not a comprehensive correction/retraction or latest-version audit. Separate datasets, images and supplements were not acquired.

All eight questions and nine sufficient alternatives received independent semantic review. The six positives are genuinely quantitative, and four require at least two distinct canonical blocks in every identified alternative:

| Source question | Semantic facts checked |
| --- | --- |
| Mammography 01 | R3 experience six years; six-week washout; dense-breast Table 5 PPV 52.2/68.9 and NPV 88.0/90.9. Both identified experience/washout alternatives supply the requested setup and table results. |
| Mammography 02 | January 2021–May 2022 acquisition period; average-measures ICC 0.910 (0.894–0.924) and 0.931 (0.920–0.941), explicitly reported as 95% intervals. |
| Mammography 03 | R2 sensitivity 86.5/88.0 and specificity 60.5/59.2; the specifically requested Statistical-analysis rule considers unbiopsied stable cases benign after up-to-two-year follow-up. All three table/abstract/reader-identity alternatives are complete. |
| Ultrasound 01 | January 2017–December 2021; final 59 women/lesions; reference diagnoses 52 surgical excisions and seven core biopsies; BI-RADS 4B sensitivity 82.98 (69.19–92.35) and specificity 41.67 (15.17–72.33), preserving intervals without inventing a confidence level. |
| Ultrasound 02 | Table 4 malignant/benign denominators 47/12; microcalcifications 32 (68.1%)/2 (16.7%), P=0.001; shadowing 19 (40.4%)/1 (8.3%), P=0.036. |
| Ultrasound 03 | Literal Table 3 entries for 4B and 5, including 9(19.2), 19(40.4) and the inconsistent Total 59(100.0); no corrected denominator or within-category risk is substituted. |

The two nulls are sound within the retained main articles: a five-year mortality reduction is absent from the retrospective mammography reader study, and male-specific accuracy is absent from the final ultrasound cohort of women. Own-cohort and cited/comparator findings remain distinct. The source's conflicting prose/table descriptions, follow-up wording and total entries are preserved. These eight agent-authored questions and their identified alternatives remain small and nonexhaustive; source truth acceptance does not establish clinical validity, model accuracy or automatic abstention.
