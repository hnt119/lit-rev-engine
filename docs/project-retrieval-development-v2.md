# Development-only retrieval proposal v2

Status: **proposal awaiting coordinator freeze; no implementation or new ranking**. This investigation used only the saved [v1 development evidence](medical-retrieval-development-v1.json), development questions/support labels, and the relevant pinned RAPTOR source elements. It did not read/rank v1 held-out questions, traces, or failures. The v1 default selection and failed quality evidence remain unchanged.

## Observed development cause

`dev-raptor-02` asks for measured SARS-CoV-2 sensitivity/specificity, intervals, and numerators/denominators against PCR in the primary analysis. Its frozen sufficient alternatives are the diagnostic-results paragraph or matching table. Both alternatives receive zero exact required-quote coverage at five under both v1 methods.

| Body support | Structural path below `/article[1]/body[1]` | Canonical size |
| --- | --- | --- |
| Measured paragraph | `/sec[3]/sec[2]/p[2]` | 391 characters, 61 whitespace-delimited words |
| Diagnostic table | `/sec[3]/sec[2]/table-wrap[1]` | 822 characters, 124 words |

Both fit entirely within a 200-word window. Their source text and exact gold substrings are present: this failure is not missing extraction or quotation cropping. The measured paragraph states sensitivity 70.4% (19/27, 49.8–86.2%) and specificity 99.3% (451/454, 98.1–99.9%). Its immediately preceding sibling paragraph `/sec[3]/sec[2]/p[1]` supplies “primary analysis” and “PCR” context. The required paragraph itself contains neither `PCR` nor `primary analysis`.

Saved BM25 ranks for this development query are statistical-analysis methods (22.1524), manufacturer comparison (21.9119), article title (20.8560), measured abstract (20.0437), and Introduction (16.9536). Token overlap ranks the preceding diagnostic-results paragraph second and manufacturer comparison third, while still omitting the necessary measured paragraph/table. The lexical ordering favors context-rich blocks and short title/abstract text over the approved body/table support.

The abstract returned at BM25 rank four **does contain measured accuracy**, so “no measured results retrieved” would overstate the failure. It reports the sensitivity interval lower bound as 49.6, whereas the approved body/table text reports 49.8. Preserve that source discrepancy and frozen support choice; do not normalize the values, add the abstract as gold, or reclassify manufacturer claims as primary results.

This supports a bounded hypothesis: individual-block scoring loses relevant study/analysis context declared immediately before the result. No scores for unseen windows, new candidate ranks, or improvement claims were computed.

## One proposed candidate: preceding-paragraph scoring context

Propose `bm25_context` with method ID `lit-rev-engine.project-retrieval.v2.bm25_context`. It keeps v1 candidate windows and exact own-block anchors, but lets each window's scoring representation include bounded text from the nearest preceding paragraph under the same immediate XML parent. This rule applies to every eligible XML source without article, question, clinical term, answer value, or result-heading special cases.

Prospective parameters for coordinator review:

| Rule | Proposed fixed value |
| --- | --- |
| Candidate windows | Existing 200 words, 40-word overlap; exact substrings within one block |
| Tokenizer/stop words | Exact v1 `unicode-casefold-word-v1` and stop-word list; sorted distinct query tokens |
| BM25 | k1=1.2, b=0.75; existing IDF formula |
| Context | At most one preceding `p` block, with the exact same immediate structural parent path |
| Context bound | Last at most 80 whitespace-delimited words, using original character boundaries |
| Eligible targets | XML paragraph/table windows; no context for title, TXT, PDF, or a target with no eligible preceding paragraph |
| Scoring representation | Own-window tokens followed by context tokens, each once; term counts/length/DF/average length use that representation |
| Retrieval count | top_k=5; existing positive-score filtering and deterministic tie order |

Context is chosen from the accepted selected source blocks, not reparsed files, cited references, peer-review sub-articles, another section/report, or an older document. A paragraph cannot borrow from itself. For tables, the nearest preceding paragraph may supply narrative context; no row-span or clinical-value inference is added.

The candidate's `anchor` remains exactly its own block/start/end/quote, directly reusable in a manual proposal. Additional trace metadata would identify `scoring_context` as a separate list of zero/one exact context anchors with typed locators, plus the context rule/bound in parameters. Do not concatenate different blocks into a purported source quotation or automatically include context as verified finding support. Preserve source/parser/full-block hashes and project/current-document scope checks.

This is a general lexical-context hypothesis, not a result detector. Nearby paragraphs can describe different analyses/populations, so context may introduce false matches. Independent review must check support and context attribution, while metrics still require the candidate's own exact gold quotes. No answerability threshold, clinical recommendation, or automatic entailment judgment is introduced.

## Freeze and evaluation sequence

1. Coordinator freezes or rejects this single candidate contract before implementation/ranking. Any parameter change later needs a new development-only ticket/version; v1 evidence remains immutable.
2. Implementation adds only the reviewed candidate; Evaluation reruns the existing nine development questions and the unchanged BM25 reference. No v1 held-out ranking or tuning occurs.
3. Proposed development acceptance: recover all seven answerable questions' complete frozen support at five without losing exact-anchor validity; retain at least the previously covered one of two no-answer context quotes. Report MRR, each rank, hard-negative retrieval, and all regressions. This strict development target is proposed, not yet authorized. If it fails, stop before fresh held-out ranking.
4. Coordinator selects one candidate and pins its source/code/parameter/development-result receipts before authorizing a fresh held-out run. The software default does not change through this proposal alone.

## Fresh held-out plan before any v2 ranking

Use three newly selected, openly licensed publisher sources with DOIs disjoint from v1. The coordinator selected their acquisition scope before v2 ranking: `10.1371/journal.pmed.1004026`, `10.1371/journal.pmed.1004422`, and `10.1371/journal.pone.0340276`. Exact acquisition/attribution/hash/version checks are a separate ticket; this proposal contains no new gold labels or clinical interpretation of those sources.

Propose twelve fresh questions, four per article: nine answerable and three explicit no-answer items. Include quantitative estimates/intervals/denominators, population/timepoint/analysis distinctions, necessary multiple passages, and adjacent-paragraph context contrasts. These categories are general review requirements; questions must be written from the new source bytes before any ranking and independently reviewed, not selected from v1 held-out failures.

Retrieval authors source paths/text and complete sufficient-support alternatives; Evaluation independently verifies exact canonical block/character anchors, values/context, and no-answer scope. Coordinator freezes question text, support, split membership, source/parser/block hashes, metrics, thresholds, and authorship limits before ranking. Keep the fresh set out of implementation feedback until the default receipt is fixed. Previously seen v1 documents/questions cannot be presented as fresh held-out evidence.

Proposed fresh gate: mean best-alternative support coverage at five ≥0.75, complete support for at least 6/9 answerable questions, 100% exact valid anchors, deterministic current-source/project isolation, and no model/network dependency. Report no-answer candidate/context behavior separately; lexical candidates never count as answers. These denominators/thresholds require coordinator approval before gold authoring/ranking. Preserve a failed result and use another fresh held-out set for any later quality claim; do not tune on this set after evaluation.

The plan is a small software pilot with independently checked manual support labels. Fresh documents reduce the v1 shared-document limitation but do not establish clinical quality or a validated cross-report benchmark.
