# Next retrieval ticket: companion evidence for compound questions

## Decision evidence

The first frozen Kaggle run **failed the predeclared 85% support-coverage gate**: Qwen returned 80.5556% mean own-support coverage and 4/6 complete positive questions, compared with the lexical reference's 72.2222% and 2/6. Its improvement is useful evidence for continuing development, not pilot acceptance. Preserve this run, its questions and its failed result. [Recorded evaluation](qwen-kaggle-live-evaluation.md).

Inspection of the retained XML, exported candidate identities and actual rerank scores identifies two distinct losses:

| Diagnostic question | Evidence retained | Companion evidence lost | Failure location |
| --- | --- | --- | --- |
| `qwen-mammography-02` | The Results paragraph giving average-measures ICC estimates and intervals ranks first. | The acquisition-period paragraph in Methodology → Study design. | Its own block is absent from the 20-block hybrid pool, so reranking cannot recover it. |
| `qwen-breast-us-01` | The Results paragraph giving the cutoff-specific estimates and literal intervals ranks second. | The Materials and methods → Study population paragraph contains both sampling period and the final cohort/reference breakdown. | That own block enters the pool but ranks sixth, below the five returned blocks. Its score is approximately 0.01554; the article title ranks first at approximately 0.82783. |

These identities are diagnostic examples only. They must not become lookup rules, preferred block paths, model prompts or exceptions in the next runtime. The [frozen job and actual model scores](../tests/fixtures/qwen_kaggle_run_v2/README.md) are preserved in the exact compressed run archive.

The XML places qualifiers and results in different major sections. The mammography outcome paragraph references a table and figure, but neither is a link to the acquisition-period paragraph. The ultrasound outcome paragraph has no XML cross-reference to its population paragraph. The missing qualifiers are also not immediate neighbors of the outcome blocks. **Nearest-neighbor or explicit-cross-reference expansion alone does not address this failure pattern.** [Mammography source](../tests/fixtures/qwen_pilot_sources/mammography.xml), [ultrasound source](../tests/fixtures/qwen_pilot_sources/breast_us.xml).

Own evidence and scoring context remain separate. A neighboring excerpt, heading, article title or supplementary-file caption may help navigation but does not supply an absent source quotation. The ultrasound supplementary caption describes enrolled-patient information without itself giving the missing quantities; the retained main article is not the supplementary data file. Moving a block from context into an own-evidence list requires its own source/version/hash/locator and full exact anchor, not a relabelled scoring string.

## Proposed generic mechanism

Prioritize **component-aware candidate selection** before larger models or a wider undifferentiated final list. Compound reviewer questions can ask for several different things: population, timing, reference method, outcome, comparison or follow-up. A single whole-question relevance score can favor one distinctive outcome while missing a less distinctive qualifier. The proposed mechanism retrieves and scores the declared components separately, then presents a bounded set of original blocks grouped by report. This is an untested design hypothesis.

Use explicit reviewer/protocol-declared components initially. Do not add a generative decomposition dependency for this ticket. Components describe what must be inspected, not expected answers; freeze their text before inference. A question with no components follows the existing single-question method.

Proposed input contract:

```json
{
  "id": "question-id",
  "query": "Original compound reviewer question",
  "components": [
    {"id": "part-a", "query": "First requested information, with subject and comparison retained"},
    {"id": "part-b", "query": "Second requested information, with subject and comparison retained"}
  ]
}
```

Allow at most three nonempty, unique components per question in the first version. Additional components require splitting the task explicitly. No question ID, disease, date, result value or XML ordinal determines retrieval behavior.

Reuse document vectors across component queries within the same frozen batch. For each component, compute lexical and dense candidates against the same eligible snapshot. Reserve a small declared number of candidate places per component before filling the remaining **global 20-block pool** by deterministic fusion. Retain the full query as an additional ranking signal; it must not overwrite component-reserved candidates. Record per-component candidates, inclusion reasons and tie order so the importer can reconstruct the pool.

Rerank the bounded pool per component, retaining a score matrix rather than collapsing everything immediately into one maximum score. Select one candidate for each component before filling remaining places, deduplicating repeated source blocks. Every selected block must identify which components caused its selection; these labels mean **candidate relevance**, not demonstrated support. Preserve scores/ranks for displaced candidates for evaluation.

Keep the first experiment's final reviewer budget at **five unique own blocks per question across all groups**, equal to the current final block budget. A block relevant to several components occupies one place. A source bundle is a grouping of those blocks by the same report/source version, not permission to append an unbounded Methods section. Display the report title as navigation metadata; retain title candidates and their ranks in the trace. Do not globally delete titles because one title ranked highly in this failed run. Questions explicitly seeking bibliographic information can require a title as own evidence.

Proposed output extension:

```json
{
  "bundles": [{
    "document_id": "existing-document-id",
    "document_version": 1,
    "members": [{"passage_id": "existing-block-identity", "component_ids": ["part-a"]}]
  }],
  "candidate_limit": 20,
  "own_block_limit": 5,
  "support_completeness": "not_assessed",
  "verification": "human_review_required"
}
```

Members refer to ordinary full canonical own-block anchors returned with the trace. Bundle membership does not establish the same population, timepoint or analysis within a report. The reviewer still checks those qualifiers. Start with within-report grouping only; do not infer report-to-study associations or combine external-study discussion values into the article's own cohort evidence. Missing or low-scoring component candidates are explicit limitations, not proof that the article lacks an answer.

Section ancestry, table references and adjacency are useful additional navigation metadata. They should remain explicit provenance edges and optional bounded suggestions, rather than substitute for component retrieval across distant sections. Any later automatic companion expansion must declare its extra own-block budget and be compared against an equally large baseline.

## Small handoff tickets

| Ticket / owner | Deliverable | Acceptance criteria |
| --- | --- | --- |
| I-N1 Implementation | New versioned batch profile and optional component-query interface; deterministic reserved pool and score-matrix selection. | Bound three components, 20 pooled blocks and five unique returned own blocks; exact IDs/anchors and explicit selection reasons; reconstructable import/replay; stale-source/scope rejection; no database decisions or paid fallback. Preserve the frozen v2 runtime and results. |
| R-N1 Retrieval | Source-disjoint prospective support set with component text specified before ranking. | Include compound AND requirements across distant Methods/Results blocks, alternative valid support, tables and nulls; verify full source qualifiers and separate context. No reuse of these diagnostic IDs/values as new acceptance truth. Record licensing and acquisition hashes. |
| E-N1 Evaluation | Independent comparison of component-aware Qwen, whole-query Qwen and component-aware lexical retrieval. | Use identical source scope and final five-own-block budget. Report pool recall separately from selection loss, complete own support, quantitative qualifiers, null behavior, actual unique blocks/read burden, GPU time and peak memory. Malformed or stale inputs fail closed. |

Before fresh inference, the architecture owner must freeze the new profile, component formulation, allocation rules, final block budget and quality thresholds. Keep the 85% coverage requirement and baseline nonregression; define the complete-support requirement against the new positive-question denominator. Offline programmed scores can test allocation behavior but cannot claim retrieval improvement. The existing eight questions now provide diagnosis/development evidence; acceptance requires the new prospective held-out set.

No runtime, gold source, gate or prior result was changed for this diagnosis, and no further model execution was performed.
