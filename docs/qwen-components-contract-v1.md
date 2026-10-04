# Component retrieval: prospective implementation contract

Selected on 4 October 2026 before implementation or new model rankings. This contract addresses the demonstrated missing Methods companions in the preserved [first Qwen failure](qwen-kaggle-run-v2.md). It also replaces shared-environment package installation for new runs. The original v2 freeze, notebook, runtime, source/gold and failed results remain byte-identical. This is a new experimental profile, not a revision of the historical acceptance decision.

## Roles and files

The coordinator owns this interface, priorities, prospective selection and review of evaluation evidence. Implementation owns new `src/review_components/`, `review_components.py`, `tools/qwen_components_kaggle_runner.py`, `tools/qwen_kaggle_environment.py` and `notebooks/qwen_components_kaggle.ipynb`. Evaluation owns new `tests/test_qwen_components*.py`, `tools/evaluate_qwen_components.py` and independent evaluation documentation. Retrieval owns the new development/confirmation source/gold archives and environment research. No existing frozen file may be edited. The new entry point delegates existing commands to the existing review entry adapter.

Implementation first completes operational behavior and synthetic checks. Retrieval acquires source-first truth; Evaluation independently checks it. The coordinator can inspect development questions/results, but receives only confirmation counts, hashes and licensing before prospective method selection. One first comparison is preserved per split; inspected questions become development evidence and cannot supply fresh confirmation after tuning.

## Inputs and profile

The new named profile is `kaggle-cuda-qwen4b-components-v1`, with distinct job, result and receipt kinds. Retain both pinned 4B model revisions, four pinned Hugging Face packages, 2,560 dimensions, author query/document/reranker encoding, FP16/SDPA, batch one, float32 L2 normalization, and measured complete inputs with no truncation. The local adapter loads no model or key, makes no network request, and never writes review events.

Input question:

```json
{"id":"q1","query":"Original reviewer request","components":[
  {"id":"population","query":"Requested population and reference method, retaining the subject"},
  {"id":"outcome","query":"Requested outcome and comparison, retaining the subject"}
]}
```

A question may have zero, two or three components. An omitted components field normalizes to an empty list; zero components retains whole-question allocation/selection semantics. All rows reject unexpected fields, empty or overlength text, invalid or duplicate IDs. Question IDs are globally unique; component IDs are unique within each question. IDs use the existing safe 80-character syntax. Component text states a request and must not contain expected answer values derived from gold. No generated decomposition is used.

At most 25 questions and 100 encoded whole/component queries; each query at most 2,000 UTF-8 bytes. Retain at most 1,000 source representations and 6,000 UTF-8 bytes per within-block representation, complete token limit 8,192. The fixed global candidate budget is 20 blocks per question and final reviewer budget is five unique own blocks across all source groups. Representations do not join different blocks. Scope, eligibility, source/version/linkage manifest, stable source ties and separate scoring-context anchors follow the existing snapshot contract. The importer rebuilds the exact job from current state and rejects stale or inconsistent snapshots.

## Deterministic candidate generation

1. Embed source representations once. Embed the whole query and each component separately in declared order. Identify query rows structurally by question ID and component ID (`null` means whole), rather than concatenated IDs.
2. For each query, compute BM25/context block order and max-span dense cosine order; take at most 20 of each. Combine those two lists using RRF with constant 60 and stable source ties, retaining the first 20 hybrid blocks. This matches the existing whole-query hybrid rule.
3. Reserve the first **two blocks from each component's hybrid list**, in declared component order. Union/deduplicate the exact first-two sets; shared blocks count for all components that reserved them. Do not replace shared blocks with extra distinct candidates. With three components this reserves at most six unique blocks.
4. Fill the remaining global 20 places using RRF constant 60 over the whole and component **hybrid top-20 lists**, one equally weighted list per query. Exclude already reserved blocks, break ties by stable source order, and retain explicit reserved/fill reasons. The pool order is reserved union first, then deterministic fill order. Fewer eligible blocks produces a smaller pool.

Rerank the same global pool separately for the whole query and every component; retain the complete representation-score matrix. Each block score is the maximum of its representation probabilities for that query. The importer recomputes all identities, pools, aggregation, ordering and selection from complete numeric results. Missing, duplicate, extra, reordered, nonfinite or out-of-range matrix/vector rows fail closed. Actual tokenizer lengths accompany every embedding/pair.

## Selection and attribution

For each component in declared order, select its highest-scoring block in the global pool, using stable source ties. A block already selected is reused and attributed to both components; it does not consume another display place and does not trigger another reserved choice. Fill the remaining places up to five by descending whole-query probability and stable source ties, excluding selected blocks. No probability threshold or posthoc title exclusion is introduced. Zero components simply returns whole-query top five.

Final display order is component reservations followed by whole-query fill, and therefore need not descend by whole-query score. Each own passage keeps its exact source/version/locator/quotation and records selection reasons and separate whole/component scores. Attribution means candidate selection, not proven support. Group these same five unique passages within report/source version for display; a bundle cannot append extra passages, imply report/study linkage, or reconcile population/timepoint qualifiers. Keep titles/navigation context explicit. Every result remains `candidate_passages`, `answerability: not_assessed`, `support_completeness: not_assessed`, and `verification: human_review_required`. Missing candidate selection is reported explicitly; selected candidates never establish semantic completeness or source answerability.

## Comparator and compute binding

Record a whole-query Qwen comparator using its original hybrid pool of 20 and whole-query reranking/top-five rule. Reuse the same source/whole-query vectors and whole-query scores for overlapping representations. Whole-query pairs needed by the union of target/comparator pools are computed once and bound separately to each pool. Component score rows cover only the target's global pool. The comparator's independent pool does not enlarge the target's twenty-block pool or its five-block output.

Also compute unchanged whole-question BM25/context and component-aware lexical comparators locally. The latter uses the same reservation/fill/selection policy with lexical lists/scores and no dense vectors. All comparisons share exact sources, original/component texts and final five-own-block budget. Record pool support separately from selection loss; do not call improved first-hit rank complete evidence recovery.

Bound actual distinct rerank pairs to 4,000 per job before loading the reranker. Account for comparator pairs and multi-span blocks. A larger job fails explicitly and requires a newly exported smaller batch; no partial result or automatic substitution can pass. Preserve checkpoints and first failure logs. Record total batch/model loading/download/inference time, peak Torch allocation on the selected device, actual CUDA/Torch/Python/dependencies and token maxima. Zero paid inference calls; no paid fallback. The prospective batch ceiling remains 1,800 seconds, with setup/queue time reported separately.

## Kaggle environment repair

The supplied log matches the preserved v2 result payload exactly and contains no model traceback. Its pip conflicts result from downgrading the shared environment's Hub/Safetensors, while notebook conversion warnings originate in Kaggle's installed tools. Neither establishes the cause of missing evidence.

For new runs, create a temporary default virtual environment without system site packages solely as an isolated pip installer. Install the four pinned retrieval packages **without dependencies** into a dedicated temporary target directory. Keep Kaggle's existing transitive packages and CUDA Torch untouched. Launch a fresh base-Python worker with isolated mode and explicitly prepend that overlay before any model-library import. This is a scoped overlay, not a claim of complete dependency isolation.

Preflight must verify active, non-extra dependency requirements for the four packages against the actual worker environment; record resolved dependency versions and package import locations. The four retrieval modules must originate in the overlay, while Torch originates outside it. Perform a CUDA allocation/operation smoke check before model downloads. Missing/incompatible dependencies stop the worker with a useful diagnostic; do not suppress warnings or silently upgrade global packages. A needed transitive adjustment requires an explicit recipe change and new prospective pins. Record the installer report and environment audit; do not record credentials or unrelated environment variables.

The notebook uploads explicit job, shared core, environment helper and runner files. Retain trusted hashes locally and check all executable helper/core bytes before loading them. Model caches/overlay live outside saved working output. Run a finite saved version with the interactive draft off; save results, checkpoint, environment audit and printed payload hash. The worker never imports the repository ledger or gold.

## Fresh evaluation and gates

Development and confirmation each use two newly licensed, source-disjoint articles, six compound positive questions and two source-scoped nulls. At least four positives require distinct Methods/Results own blocks; components are specified from the request before ranking. Preserve sufficient OR alternatives of necessary AND quotation spans, quantitative qualifiers, source limitations and separate no-answer context. Development uses DOIs `10.1371/journal.pone.0266799` and `10.1371/journal.pmed.1002997`; confirmation uses `10.1371/journal.pone.0312121` and `10.1371/journal.pmed.1004428`. Acquisition/permissions and original-source truth require independent acceptance.

Before any real development ranking, pin runtime/core/environment/notebook, profile, this contract, harness, tests and development source/truth. Keep the selected rule fixed through the first development comparison. Before the first confirmation ranking, record the selection and all confirmation input hashes, with zero prior confirmation rankings. Root remains blind to confirmation QA until selection is recorded.

Required on confirmation: mean own-support coverage at least 85%, at least four of six complete positives, no lower coverage or complete-positive count than each matched whole-query lexical, whole-query Qwen and component-aware lexical comparator; exact own/context/source-scope validation, read-only state and unchanged-result replay; five unique own blocks per question; zero paid calls; batch at most 1,800 seconds. Report each null's returned candidates/context/hard negatives and all partial positives. No-answer relevance never receives positive-support credit. Preserve the first pass/fail; no relaxed threshold, larger display list or source-specific exception follows a failure.

Software acceptance and actual GPU quality acceptance are separate. Only an accepted fresh comparison permits the requested human protocol pilot. That pilot still requires the team's topic, database strategy, eligibility and independent screening/extraction judgments.
