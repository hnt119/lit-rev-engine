# Optional local evidence retrieval — additive Track A successor

This capability is integrated with the Track A Research & AI Settings application for source beta.2.
It preserves the published beta, historical lexical profiles, source preparations,
board definitions, paper-map artifacts and frozen Qwen 4B evaluations. Track B and
its private pilot environment are separate and are not inputs to this package.

One application exposes Core lexical, Qwen hybrid + reranking, and Biomedical
hybrid + reranking. Both neural profiles are experimental. MedCPT's retained-source
passage use is an adaptation of its title/abstract article task; execution does not
establish a biomedical advantage or semantic evidence support.

## Explicit setup and actions

Core lexical needs no Torch, Transformers, weights, cloud key or generation server.
Use `python3.12 scripts/local_preview.py setup --with-retrieval` in an extracted
package to install the pinned optional runtime into the application environment.
Core setup omits it. This action installs dependencies and builds the UI, without
downloading model weights.
The two packs share that optional runtime; their weights remain separately selected.
No setup, startup, Settings read/save, navigation, or source inspection downloads or
executes a model. There is no automatic cloud request, paid fallback or remote model
code. Missing or failed hybrid models raise a visible error with the pinned profile;
the researcher may explicitly select lexical for a separate attempt.

Use Evidence retrieval in Research & AI Settings or the explicit command-line tool:

```sh
.venv-preview/bin/python scripts/retrieval_pack.py status
.venv-preview/bin/python scripts/retrieval_pack.py manifest --profile hybrid_qwen3_06b_rrf_rerank_v1
.venv-preview/bin/python scripts/retrieval_pack.py install --profile hybrid_qwen3_06b_rrf_rerank_v1
.venv-preview/bin/python scripts/retrieval_pack.py check --profile hybrid_qwen3_06b_rrf_rerank_v1 --device cpu
```

Use `hybrid_medcpt_passage_rrf_rerank_v1` for the three-component biomedical pack.
Select MPS explicitly for a separate runtime check. Float32/eager attention and the
recorded backend are fixed; no precision or device fallback occurs. A runtime check
executes query and document encoding and reranking over two synthetic passages. It
is an integration check, not a retrieval-quality test.

The default owned cache is `~/.cache/litrev-evidence-retrieval`, outside replaceable
application files. The extracted launcher accepts `launch --retrieval-cache PATH` for an owned
mode-0700 absolute external directory. A developer launcher may use the explicit
`LITREV_RETRIEVAL_CACHE` environment setting. A CLI invocation may use `--cache`.
Model files and indexes are private local artifacts and are excluded from scholarly
exports and source packages. Pack removal retains saved results and exact references.

The allowlisted manifest records immutable revisions, every artifact's bytes and
SHA-256, official origin and license declarations. Install streams only those files,
checks lengths and hashes, supports verified resume, and publishes atomically.
Cancellation/interruption leaves an uninstalled partial pack; retry installation
explicitly. Read model cards and `MODEL_REFERENCES.md` with the retained model notices.
MedCPT Cross has an empty upstream LICENSE and only a PyTorch tensor state file at
the selected revision; the other upstream public-domain notices and model-card
statement are retained. Its loader requires modern restricted `weights_only=True`,
strict tensor keys and no remote or additional executable globals.

## Search, scope and history

Choosing a default affects future explicit operations. Research-source providers,
paper-map configuration and generative assistance remain independent. Existing
boards retain their profile. Switching a board requires an explicit definition
revision and retains historical cells under the existing revision rules.

First choose Index these sources for the exact preparation/board/cell snapshot.
Index state is separate from pack and runtime state. Searching never creates an
index implicitly. The source scope is applied before windowing, BM25, dense search,
fusion and reranking. A cell sees its one bound source; a board-wide request sees
its bound papers. A newer workspace preparation cannot replace historical bindings.

The query-independent sentence windows retain half-open Unicode code-point offsets.
They cover eligible source text within explicit quotas, including text without a
lexical hit. Each whole title, passage and model template must fit the tokenizer
budget. Long sentences split with exact offsets; full titles and negations are not
silently shortened. Quotas, split boundaries and table-context limitations are
recorded. Metadata titles are not citeable proof of passage claims.

Both independent branches search the inventory, then equal-weight RRF with c=60
fuses candidate identities. Search uses at most 50 candidates per branch and 50
rerank pairs, with 5–30 final selections; a cell uses at most 20 per branch/20 pairs
and at most 3 selections. Explicit components share the total operation caps.
Cell quotations retain the existing 3,600-character/1,200-proxy-token aggregate
budget. No LLM rewrites a question. A MedCPT query above its declared 64-token policy
requires explicit shortening or researcher-declared components. Actual complete
pair token lengths are validated, without truncation.

Qwen uses the native last-valid-token representation, L2 normalization and 1,024
coordinates, instructed queries and the documented reranker yes/no template.
MedCPT uses distinct query/article encoders, CLS 768-dimensional raw inner products
and the cross-encoder's signed relevance logits. Model and reranker scores remain
retrieval relevance, never calibrated evidence-support probabilities.

Hybrid results use `mvp.hybrid-retrieval.v1`, with null missing stages, original
branch membership, per-component ranks, exact source/model/window bindings, usage,
timings and explicit coverage. Lexical DTOs are unchanged. Saved hybrid history
and exports retain their own discriminators. The source inspector and return to
cell use the same reference validation and explicit inspect/attach/submit flow.
Optional proposals use `mvp.hybrid-proposal-packet.v1`; generation consumes
already saved exact cell candidates and requires explicit retrieval first for
each selected cell. Its existing call, byte, character, output and time budgets
remain unchanged, with no automatic neural fan-out during generation.

Indexing and retrieval serialize local neural work, compute outside source/SQLite
mutation locks, and revalidate scope before publication. Jobs expose failure,
cancellation and interruption; deletion fences late results. Local HTTP operations
are synchronous requests with durable status, not a background orchestration system.
Cancellation is cooperative between model loads/batches; it cannot interrupt an
individual native forward call. Restart does not automatically resume research work.

## Evaluation and publication boundary

Run `scripts/evaluate_hybrid_retrieval.py` only after explicit installation. It
compares existing lexical spans, BM25 common windows, each family's dense fusion
ablation and full reranking, on pinned common sources/windows and fixed budgets.
The existing saved public and synthetic cases are development regressions with
agent-authored anchors. They are not fresh held-out studies or human gold. Search
mode measures exact-anchor recall at 5/10; cell mode preserves the 3-excerpt budget.
Neither metric establishes semantic support, independent verification or clinical
usefulness. Human relevance, wrong-cohort/numeric adjudication and correction time
remain distinct release gates. Actual commands and outcomes are in the validation
report, including regressions and unperformed checks.

The source beta includes this optional capability without bundling model weights or changing beta.1. Publishing the source does not publish/mirror a model pack, deploy a service or authorize paid usage. The private desktop binary is withheld separately; it is not needed to run the browser application. See VALIDATION.md in the release for combined tests and actual-versus-mocked evidence.
