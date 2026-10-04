# Component retrieval development: source-first truth

KR4B retains independently reconstructed own blocks and prospective compound research questions for the [selected development originals](../qwen_components_development_sources/README.md). The coordinator selected the split before acquisition and question construction. Retrieval read the complete original main XML first, including Methods, Results, tables, captions, limitations and contextual external-study passages. No lexical/model ranking informed these questions or support alternatives.

| Bound workload | Count |
| --- | ---: |
| Original articles | 2 |
| Questions / quantitative positives / source-scoped nulls | 8 / 6 / 2 |
| Explicit reviewer-request components | 19 |
| Necessary multi-block AND positives | 5 |
| Positives needing body Methods + Results in every OR alternative | 4 |
| Sufficient OR alternatives / own support spans | 9 / 20 |
| Separate no-answer context spans | 4 |
| All canonical own blocks / main tables | 126 / 6 |

Each question has two or three fixed requested components. Component text asks for information; it does not supply expected answer dates, counts, estimates, confidence bounds, anchors or preferred source paths. Components are reviewed before ranking. A sufficient alternative is an AND of exact own-source quote spans; alternatives are joined by OR. A repeated complete summary may be sufficient on its own, so a compound request does not automatically imply a multi-block AND. No alternative is added to accommodate a retrieval result.

All anchors bind original source ID, canonical block ID/hash, XML path, and half-open Unicode code-point offsets. Preserve every quoted quantitative qualifier and source discrepancy exactly. The source manifest records caveats; a research fixture must not silently repair published values or interpret ambiguous clinical terminology. Original articles and derivative passages retain the authors' [CC BY 4.0 attribution and notices](../qwen_components_development_sources/README.md).

Null questions ask for a population, reference, timepoint or outcome combination that the retained own main article does not report. Context anchors document limitations and plausible inapplicable evidence; they never count as positive sufficient support. Source-scoped absence does not establish that no related publication anywhere provides an answer. Supplements and related reports need independent acquisition before supplying evidence. This archive is a retrieval-fidelity test, not clinical guidance.

[manifest.json](manifest.json) binds every block/question file and acquisition manifest. [verify.py](verify.py) checks original XML reconstruction first, then stored canonical inventory, every own/context anchor, components, count floors, source identity and existing-parser reconciliation. Integrity checks do not replace independent semantic acceptance.

```sh
.venv/bin/python tests/fixtures/qwen_components_development_gold/verify.py --self-test
```

The checker rejects 28 truth tamper cases, including consistent rewritten file hashes, and accepts preservation of a historical parser-runtime label. The prospective comparison retains a 20-own-block global candidate budget, five unique returned own blocks, 1,800-second batch ceiling, at least 85% mean own-support coverage, at least four of six complete positives and no regression against matched whole-query lexical, whole-query Qwen and component-aware lexical baselines. Nulls receive no positive-support credit. No paid inference or automatic fallback is allowed.

Independent Evaluation accepted this source-first truth before any ranking, after adding sufficient OR alternatives found in original-source review. Runtime/hash freeze and actual GPU quality remain separate requirements. Never upload gold, expected answers or anchor selections to the Kaggle worker. Only original source content and the reviewed request/component text belong in its input job. Preserve the first comparison without changing thresholds or adding source-specific exceptions.

Development may inform later debugging only after the first comparison is preserved. Fix the method before opening the blind confirmation comparison; use fresh source-disjoint confirmation in any later tuned cycle.
