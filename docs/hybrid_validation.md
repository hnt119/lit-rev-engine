# Optional hybrid retrieval: local validation and limits

Observed 25 October 2026 on macOS 26.6.2 arm64. This is an additive Track A
successor change set. The published beta, original Track B checkout/pilot,
paper-map artifacts and frozen Qwen 4B experiments are separate and unchanged.
No website, public model-pack publication, deployment, merge or paid usage is
part of these checks. Core lexical retrieval remains the default and imports
without the neural stack. Both hybrid profiles remain experimental.

## Installed artifacts

The explicit bounded installer fetched these official pinned payloads and
verified every selected file's SHA-256 before atomic installation. These are
actual verified payload lengths, including each selected tokenizer/config/model
card, rather than parameter-count estimates. The complete file list, pinned URLs
and hashes are in `src/mvp/retrieval_pack_manifest.json`.

| Pack | Verified download bytes | Installed regular-file bytes, including marker | Allocated filesystem bytes at observation |
| --- | ---: | ---: | ---: |
| Qwen, two components | 2,414,972,344 | 2,414,972,493 | 2,429,931,520 |
| MedCPT, three components | 1,316,720,932 | 1,316,721,083 | 1,365,000,192 |

Filesystem allocation is the sum of observed regular-file `st_blocks × 512` on
this machine. It excludes directory metadata, indexes and future cache growth;
it is not a promised free-space requirement on another filesystem.

Pack manifest hashes:

- Qwen: `81f0d2135855cdd7ce15ee98e292e6bb6dfb0523d2685091b80e5a3a2cf5bf6f`.
- MedCPT: `464d60ab9d38261484388421be0663ca2ed50496da93d6c97eacaa355517b515`.

| Official model | Immutable revision | Weight SHA-256 |
| --- | --- | --- |
| Qwen/Qwen3-Embedding-0.6B | `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` | `0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd` |
| Qwen/Qwen3-Reranker-0.6B | `e61197ed45024b0ed8a2d74b80b4d909f1255473` | `27cd75a405b9c1b46b59abfd88aaa209e6fed2a1972cde9b70e7659537c5e65b` |
| ncbi/MedCPT-Query-Encoder | `d83a36cc6b8e3a5c5e9d9d6ba156808c1643dcbc` | `19d78c0d5eaee2f81e6c47c5425bbadcc0c6af016cbb5da4a000d64e59d6e342` |
| ncbi/MedCPT-Article-Encoder | `d05a736da4bb84ee4057b7f7999485be6ed85465` | `a5d5ffe4d8666c1d0aa15f371b94fc3492ca8f927e5621abd4b3ee9fc845b0f3` |
| ncbi/MedCPT-Cross-Encoder | `71caf65d4927987813984f54c284405a13fcca49` | `61d5ccd48869e03500544525fc231641d7daa9ba267b202c82724750038dc1e0` |

The first four weights use safetensors. The pinned official MedCPT Cross Encoder
provides only a `.bin` state dictionary. It is restricted to explicit
`torch.load(weights_only=True, map_location='cpu')` with Torch 2.6 or later,
plain tensor validation, strict native architecture loading and no added pickle
globals or remote code. Upstream license declarations and retained notice
provenance, including the Cross Encoder's empty upstream LICENSE, are recorded
in [hybrid_model_references.md](hybrid_model_references.md).

## Actual native model execution

Each final check independently loaded verified local files and executed one real
query encoding, two real document encodings and two real reranker pairs. The
input was synthetic: one blood-pressure treatment passage and one forest-canopy
passage. These checks establish integration, not medical retrieval quality.

All four used Torch 2.12.0, Transformers 5.12.0 and Tokenizers 0.22.2; explicit
float32, eager attention, document batches of two and sequential component
loading/unloading. Qwen computed only the final-token vocabulary logits and
disabled unused KV caching. No precision, model or device fallback was enabled.
Model calls used local files only and disabled remote code.

| Pack | Selected device | Encoder and reranker | Entire runtime check, seconds | Whole-process peak RSS, bytes |
| --- | --- | --- | ---: | ---: |
| Qwen | CPU | PASS | 12.172 | 4,484,694,016 |
| Qwen | Apple MPS | PASS | 16.602 | 3,850,731,520 |
| MedCPT | CPU | PASS | 8.505 | 1,354,596,352 |
| MedCPT | Apple MPS | PASS | 8.134 | 1,442,267,136 |

Entire-check time includes local artifact verification, tokenizer construction,
component loads and forward passes. RSS is the process high-water mark converted
to bytes; it is neither incremental model RAM nor measured GPU allocation.
These are single observations on this host. CPU here means the CPU backend on
this arm64 Mac; Linux, Windows and Intel CPU execution were not exercised. No
cold-versus-warm, sustained throughput or universal macOS requirement is inferred
from these checks.

For the same two reranker pairs, Qwen CPU scores were approximately
`[0.999742806, 0.0000306361]`; MedCPT CPU raw logits were approximately
`[11.0445862, -15.9815989]`. Maximum absolute CPU/MPS score differences were
`9.05857e-10` and `1.71661e-5`, respectively. Both devices retained the same order
for this fixture. This is a small integration comparison, not a general parity or
retrieval-quality guarantee. Qwen scores are normalized yes/no relevance values;
MedCPT logits can be negative. Neither is calibrated evidence-support probability.

The Qwen profile keeps 1,024 dimensions, last-valid-token pooling, L2
normalization and native query/reranker instructions. Its conservative local
limits are 256 instructed query tokens and 1,024 complete input tokens. MedCPT
uses separate 768-dimensional query/article CLS encoders, raw inner product and
the native cross-encoder query/document pair. Its 64-token query policy includes
special tokens; complete article/pair inputs must fit 512 tokens. Window sizing
reserves the entire query budget. Evidence/title/query text is never silently
truncated. The title/passage representation remains an experimental adaptation
of MedCPT's title/abstract application.

## Offline safety and application checks

Independently executed focused suites:

| Suite | Observed result | Evidence boundary |
| --- | --- | --- |
| `tests/test_neural_retrieval_native.py` | 17 passed | Synthetic tensor/tokenizer parity and boundary tests; not model-quality evidence |
| `tests/web_api/test_hybrid_packet_independent.py` | 15 passed | Synthetic API adapter evidence and real packet contracts; no generator calls |

The native suite checks core import without Torch/Transformers, Qwen instruction
and pooling rules, full query/pair budgets, encoder roles, normalization,
negative MedCPT logits, yes/no-only scoring, explicit safe local loaders,
cancellation and stable runtime signatures. The packet suite checks exact
Unicode/combining-character quotations, negative-score candidates, cross-field
anchor reuse, source/revision/profile bindings, primary-field reservation,
whole-candidate omission and unapproved query-change rejection.

Earlier focused coordinator, pack and profile-binding checks reported 18, 20
and 7 passing tests, respectively. Full regression and extracted-package results
are recorded separately when completed; these earlier counts must not be added
together as a claim that all application paths were exercised with real models.

The first packet-suite attempt used the neural-only environment and could not
collect because FastAPI was absent. Running the same unchanged suite in the
existing web test environment passed all 15 tests. This was an environment
selection issue, not evidence that the suite passed in the neural-only runtime.
The web test environment emitted upstream TestClient deprecation notices; a
restricted pytest cache write produced a cache warning without test failures.

## Controlled development comparison

The opt-in `scripts/evaluate_hybrid_retrieval.py` compares:

- A: the existing lexical exact-span profile.
- B: BM25 over the new common source-anchored windows.
- C/D: Qwen BM25+dense RRF, without/with actual reranker execution.
- E/F: MedCPT BM25+dense RRF, without/with actual cross-encoder execution.

It preserves the frozen development manifest hash
`437888582ab4fb82ee647b24b4e40f9a2c1ca9b4ff34a5bd6120fa28fb81390e`, exact
source versions and original label provenance. The default subset contains nine
synthetic cases from eight synthetic sources; `--include-public` adds three
already saved public development cases. These are regressions and agent-authored
labels, not a fresh study-level held-out or human-gold evaluation.

B–F use the same query-independent inventory, validated by both pinned model
families. All cell lanes use identical explicit component queries and the same
actual maximum of three quotations, 3,600 characters and 1,200 proxy budget
tokens; branch and reranker work is bounded to 20 candidates/pairs per operation.
C/D and E/F share identical real query vectors and indexes to isolate the
reranker effect. A/B expose the window change. No model or threshold is selected
on the basis of these development results.

Search mode separately allows ten displayed candidates and 50 candidates/pairs.
A retains its historical three-result span limit and is explicitly excluded from
common-budget search-depth comparisons. Exact-anchor recall and nDCG proxies at
5/10 are recorded only for actual B–F search output. The per-span nDCG grade is
the count of frozen exact anchors, with shared-anchor windows possible; it is
not human graded relevance or semantic entailment.

The completed CPU cell run covered all 12 development cases from 11 sources,
with 223 common windows. Each real model family encoded all 223 documents and
23 component queries, then executed 93 reranker pairs. It completed in
296.182 seconds with a whole-process peak RSS of 4,703,551,488 bytes. Total
observed explicit indexing time was 109.501 seconds for Qwen and 28.017 seconds
for MedCPT across these 11 sources; corpus sizes and warm filesystem effects
vary, so these are aggregate observations, not per-paper performance promises.

| Cell lane | Exact anchors / fixed 21 | All expected components, answerable cases / 10 | Mean fixed-anchor nDCG proxy at 3 | Attributed retrieval seconds, excluding indexing |
| --- | ---: | ---: | ---: | ---: |
| A Existing lexical spans | 21 / 21 | 10 / 10 | Not comparable: different inventory | 0.022 |
| B Common-window BM25 | 21 / 21 | 10 / 10 | 0.976536 | 0.013 |
| C Qwen RRF, no reranker | 21 / 21 | 10 / 10 | 0.970392 | 11.431 |
| D Qwen hybrid and reranker | 21 / 21 | 10 / 10 | 0.926186 | 83.859 |
| E MedCPT RRF, no reranker | 20 / 21 | 9 / 10 | 0.946928 | 8.527 |
| F MedCPT hybrid and reranker | 21 / 21 | 10 / 10 | 0.939629 | 66.283 |

The MedCPT no-reranker ablation missed one of two fixed anchors in
`public-cheonggukjang-enrollment-dose`; the reranked lane recovered it. Both
full hybrid lanes retained all expected development anchors, while their rank
proxies were lower than common-window BM25. This provides no basis to claim
hybrid superiority or change the lexical default. Each lane returned candidates
for both insufficient-context questions (2 / 2); nearest-candidate output must
not be interpreted as evidence that those questions were answerable.

Matched ablation/reranked lanes reuse the exact same observed query vectors;
query-encoding cost is attributed to both lane timings. The row times therefore
must not be summed to estimate wall time. Model loading and filesystem state
were not independently randomized, and no sustained warm-latency comparison
was performed. Evaluation adapters/tokenizers were constructed once; these
per-case retrieval times exclude that startup pack-verification cost. They are
not complete application-request or browser-interaction latency measurements.

The retained JSON receipt SHA-256 is
`8077fe13c144dcc22ff13320450cb586cb98957bc4d3670f48109306aa9119ab`.
It records the base checkout commit
`db4735b11b7b588f740aaf1de38d9732aa15df72` plus a full SHA-256 map of the actual
uncommitted measured code. This is not a claim that the base commit contains
the hybrid implementation. Relevant measured hashes were:

- Native adapter: `cee2a9b7c6e8e62094b60d92b47bd46e7908e32fcd8e7e4c8079b15f566beeb8`.
- Coordinator: `23283d7b3c974f9502f9940528da86a077de86e2fa8c08cf5fe521df1615f4c8`.
- Windowizer: `076d209818dc7917b066f5a37015d81914f2351d86c83fa9f20cc7a81bd38d01`.

After this completed cell run, a leading-whitespace handling edge in the
windowizer was identified for over-budget windows and repaired separately.
The cell receipt remains historical evidence for its recorded code hashes;
it is not silently relabeled as a run against the repaired final windowizer.
The subsequent full search comparison and final package validation record
their own exact code and source bindings.

### Completed search comparison on repaired windowizer

A separate CPU run completed all 12 development cases against the repaired
windowizer, again with 223 common windows and 23 actual encoded component
queries per model family. Each family executed 183 reranker pairs. B–F used the
same real ten-candidate output budget and 50-candidate/pair operation bounds.
A retained its native maximum of three cell candidates; no A search-depth
metric or common-budget A-versus-B search claim is made.

| Search lane | Macro exact-anchor recall at 5 | At 10 | Macro fixed-anchor nDCG proxy at 5 | At 10 |
| --- | ---: | ---: | ---: | ---: |
| B Common-window BM25 | 1.000 | 1.000 | 0.994690 | 0.994690 |
| C Qwen RRF, no reranker | 1.000 | 1.000 | 0.985293 | 0.985293 |
| D Qwen hybrid and reranker | 1.000 | 1.000 | 0.926186 | 0.926186 |
| E MedCPT RRF, no reranker | 0.950 | 1.000 | 0.946928 | 0.963644 |
| F MedCPT hybrid and reranker | 1.000 | 1.000 | 0.939629 | 0.955272 |

Recall is calculated within each answerable case as the fraction of its frozen
exact anchors fully contained in the actual first 5/10 quotations, then averaged
equally across the ten answerable cases. The table reports this macro average,
not a pooled 21-anchor micro recall. The two insufficient-context cases have no
positive fixed anchors and are excluded from recall/nDCG means. nDCG is averaged
over cases with nonzero common-inventory ideal gain. It grades a quotation by
its exact-anchor count and does not measure human semantic relevance.

All B–F lanes covered all 21 expected anchors within ten candidates. There was
no total-anchor regression at ten, but both full reranked profiles had lower
rank proxies than common-window BM25. MedCPT's no-reranker lane reached only
0.950 macro anchor recall at five; it recovered all expected anchors by ten.
All six lanes still returned candidates for both insufficient-context cases
(2 / 2). These results do not establish answerability, entailment, scientific
usefulness or hybrid superiority. Core lexical remains the default.

The search run took 361.853 seconds with a whole-process peak RSS of
4,744,298,496 bytes. Observed aggregate indexing time was 91.603 seconds for
Qwen and 24.408 seconds for MedCPT. As in the cell run, no claim about cold/warm
or sustained browser request latency follows from this one controlled run.

The completed search receipt SHA-256 is
`1c7ac42defb65ce00da0cc79f461dc8988a202fcb2bd071185e8764169e53bef`.
Its metadata records the core checkpoint
`127a14a1d22e191d2b1475a6f2933583799a0127`, committed during evaluation; the full
measured-code SHA-256 map remains authoritative rather than implying that this
checkpoint contains every final application edit. The repaired windowizer hash
is `4060ffc9c72379efafbef3bc07af59a844d33c5a0cd4586b3f37b22181fad653`.
Native adapter, coordinator, contracts, lexical adapter and evaluator hashes
match the earlier cell receipt. The evaluator checks these code bytes at both
start and completion, and final artifact validation must match the reviewed
commit to the retained measured code explicitly.

## Remaining quality and release limits

Human-inspected gold cases, fresh held-out studies, sufficient-support retrieval
at 5/10, semantic entailment, wrong-cohort/numeric-error adjudication and human
correction time are **NOT_RUN**. The evaluation records exact-anchor proxies and
source-scope integrity separately from these unmeasured questions. No fixed
generator experiment or fresh PubMed search is part of retrieval validation.
Scientific usefulness and superiority over lexical retrieval remain unproven.

Neither optional profile inherits an accuracy label from the frozen Qwen 4B
experiments. Runtime success does not promote a default, approve screening,
include a report, set a human cell judgment or independently verify a claim.
A failed selected hybrid profile must return an explicit failure; a lexical retry
requires an explicit profile selection. Saved results remain readable without
installed weights. Desktop-shell success is not a retrieval prerequisite.

## Application and packaging regression checkpoint

The final source builds the production Next.js UI and regenerates TypeScript from
OpenAPI, including the new result and proposal-packet discriminators. Full UI
regression: **181 passed**, 0 failed/skipped. The complete HTTP suite passed
**383 tests** in 298.94 seconds; the final optional-cache/profile/packet suite
then passed **40 tests** in 11.18 seconds after the startup-cache repair. These
are offline synthetic/software checks, separate from the real model runs above.

Launcher and independent source-archive checks passed **90 tests** in 38.71
seconds after adding explicit `setup --with-retrieval`, an external cache flag
and model notices. The affected packaging/configuration subset passed **64
checks** again after excluding `.bin` weights. A fresh isolated environment
successfully installed the exact core and optional retrieval requirements; no
existing project/model environment was modified.

The first combined Python invocation failed collection because this repository
uses duplicate test module names across suites. Separate processes resolved it.
Two initial HTTP assertions referenced a wrong failure-code field; their corrected
forms pass in the final full suite. The independent archive audit initially
rejected the newly added retrieval guide/notices; its explicit allowlist and
source translations now cover the additive files and all payload bytes remain
checked against the selected source commit. The first production build used an
external development dependency symlink, which Turbopack rejects; a local private
copy resolved it. A subsequent invocation used the wrong working directory for
the pre-existing license page; building from `apps/web` passed. No application
security or inference fallback was added for any failed check.

Hybrid proposal preparation and generation consume already saved, exact cell
candidate receipts. They perform no hidden encoding/reranking and retain existing
generation budgets. Missing saved cell candidates require explicit retrieval.
New hybrid receipt/job tables use the existing comparison database and shared
quota; no new research database or orchestration framework is introduced.
An unsafe or unwritable optional cache reports an unavailable hybrid state while
core lexical/manual research remains usable.

The extracted successor walkthrough and artifact hashes are recorded separately
in the final private review packet, after freezing an exact source commit. This
source document does not pre-claim those later observations or authorize publication.

The final complete core rerun passed **736 tests**, with **13 optional Streamlit
skips**, in 26.75 seconds. The final complete frontend rerun passed **181 tests**
in 3.43 seconds. Existing Starlette/AnyIO and React test-renderer deprecation
warnings remain; dependencies were not changed to suppress them.
