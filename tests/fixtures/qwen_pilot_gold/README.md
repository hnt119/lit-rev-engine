# Fresh Qwen pilot truth

Ticket R-Q2 authors a fixed, source-first pilot against the two licensed snapshots in [the source archive](../qwen_pilot_sources/README.md). The set contains eight questions: six quantitative positives and two article-scoped nulls, four questions per source. Four positives require distinct canonical blocks in every identified sufficient alternative. The corpus has 102 canonical blocks and nine main tables; gold contains nine sufficient alternatives, 36 support quotation spans, and four separately labeled context spans.

`manifest.json` pins the acquisition manifest, both raw XML files, and the canonical/question JSON files. `blocks.json` contains every canonical block with original XML path, ordinal, locator, source ID, full text and SHA-256. `questions.json` contains the agent-authored queries, requested factual answers, source IDs, alternatives and exact half-open Unicode code-point quote spans. No previous QA, results or ranking performance were used to author this set.

Support alternatives are OR: satisfying any one complete alternative is sufficient. All necessary quote spans within that alternative are AND. Distinct-block counts deduplicate by `(source_id, block_id)`; multiple spans from one block do not make an AND question. All 102 canonical blocks were scanned for identified alternatives. Structural verification cannot itself prove semantic completeness; independent original-XML review must accept every alternative and null scope before Root's freeze and first quality run.

`context_anchors` are contextual observations, never positive sufficient-support credit. Nulls are article-scoped nonreporting labels; they may still return retrieval candidates. They do not establish automatic abstention or a model answering correctly. Human-readable expected answers guide semantic review; support scoring uses exact original-source anchors rather than answer string matching.

Questions separate own-cohort facts from cited studies, and qualify regions where the source contains inconsistent numbers or prose. Table row/column headers, units and needed notes are included in support spans. Source caveats remain in the acquisition manifest; expected answers contain requested facts, without silently correcting printed values or substituting source context for sufficient support.

Run offline:

```sh
python3 tests/fixtures/qwen_pilot_gold/verify.py --self-test
```

The checker first validates the raw acquisition pins and independently reconstructs original XML blocks. It then reconciles every path/text/locator/ordinal with the accepted JATS parser and verifies all source bindings, whole-block hashes, Unicode quotes and offsets, alternatives, null/context rules, and actual counts. It rejects 20 gold tamper negatives, including consistently rewritten gold hashes against changed raw bytes, and accepts one historical-runtime positive. Synthetic tamper copies contain only the two fresh sources and their new manifest/checker, never a legacy mixed archive.

This is an agent-authored, nonexhaustive two-source/eight-question pilot, with no model-call or retrieval-quality outcome during curation. Provider compatibility, frozen prospective quality comparison, cost/latency evidence and any human pilot are separate stages. Root owns `freeze.json` or its equivalent, candidate policy, quality gates, execution receipts and release decisions. No freeze file is authored here.

Final gold files are `manifest.json`, `blocks.json`, `questions.json`, `verify.py`, and this README.
