# E — exact lexical spans and a controlled development comparison

Baseline: the locally frozen D checkpoint (122 owned files), branch
`codex/mvp-v0-3`, HEAD `551068a`. Preserve unrelated files, all original research,
legacy retrieval, the public thirty-paper pack, maps, assessments and cell history.

## Interfaces and ownership

| Ticket | Owner | Files / contract | Acceptance |
|---|---|---|---|
| E1 exact windows | Retrieval agent | `span_retrieval_contracts.py`, `adapters/span_retrieval.py`, pure budget helper, own unit tests | One paper/field; exact original Unicode offsets; score only delivered spans; bounded sentence/token windows; explicit index/context omissions; stable ties; no model or map-vector reuse. |
| E2 board integration | Implementation agent | `evidence_board.py`, `adapters/board_storage.py`, Compare/profile UI, owned tests | Explicit new definition/revision selects B1; legacy defaults/fingerprints/records unchanged; CPU work outside guards; stale/deleted inputs cannot publish; exact inspection, manual draft/submission and export still work. |
| E3 evidence and adversarial checks | Evaluation agent | New frozen source-first fixtures, `span_evaluation.py`, evaluation CLI and independent tests | Fixed manifests and denominators; matched sources/budgets; distinguish question-only span gains from extra explicit queries; report failures, overlap, omissions and non-answerable cases; no human or competitive claims. |
| E4 contracts, packets, acceptance | Root | `span_board_contracts.py`, API/generated types, `adapters/span_packets.py`, proposal dispatch/tests, checkpoint records | Typed additive receipts; canonical ownership/count/token checks; deliberate exact-primary-anchor projection into existing packet v1; fair field allocation within unchanged generation budgets; review evaluation before adding complexity. |

## Preserved and new contracts

`BoardCreateRequest`, `BoardReviseRequest`, legacy `BoardCandidates` and their
serialized defaults remain unchanged. New `ProfiledBoardCreateRequest` and
`ProfiledBoardReviseRequest` explicitly select `legacy_block_prefix_v1` or
`lexical_spans_v1`. Existing routes accept either request. The new request type
avoids changing historical idempotency fingerprints. Revising a B1 board through
an old implicit-profile request is rejected.

The existing board-definition shape retains a versioned retrieval-profile dict
and digest. A B1 profile also records every field's effective component queries,
which fields had explicit components, and packet policy
`primary-spans-round-robin.v1`. Defaults follow the exact approved field
subquestion; optional components are explicit retrieval inputs, not a hidden
question decomposition or new extraction instructions. They do not change the
field question or establish semantic coverage.

New `mvp.board-candidates.spans.v2` receipts contain exact primary references,
omitted-before/after counts, lexical component matches and separate block/window
and index statistics. Canonical source text and reference locators are never
rewritten. Old and new candidate receipts dispatch by schema in replay,
inspection and audit exports. Cell, assessment and existing export schemas remain
unchanged; their nested new receipts identify their own version.

Each primary span is contiguous, at most 1,200 Unicode code points / 400 declared
word-or-punctuation budget tokens. At most three spans / 3,600 characters / 1,200
budget tokens are delivered per paper/field. The proxy tokenizer is recorded and
is not a model-token measurement. All scored qualifier/negation context is inside
those delivered quotations. No separate invisible context contributes to scores.
Index limits and cooperative CPU deadlines are recorded; incomplete indexing
never establishes whole-paper absence. Tables with clipped labels/context are
flagged for exact inspection.

## Proposal compatibility

Keep the existing context-only prompt, model adapter, packet-v1 data meaning,
call/output/runtime budgets and adoption/submission lifecycle. A new explicit
builder projects only validated exact primary anchors into packet v1. New window
diagnostics remain in the referenced v2 candidate runs and profile digest; there
are no hidden additional context references to discard. Candidate overlap,
lexical component matches and intact quotations do not confer support.

Reserve one available candidate per selected field before filling extra anchors
in round-robin order. Deduplicate shared exact anchors and keep all associated
fields. Fail before generation if the initial field-coverage set cannot fit.
Omit extra candidates whole at the existing bounds. Keep the old packet builder
unchanged for legacy profiles. All model execution tests use mocks; real local
proposal evaluation requires separate authorization.

## Evaluation design and decisions

The evaluator froze eleven sources / twelve cases before reading B1 ranks:
eight synthetic and three licensed public-pack sources, ten answerable
paper-fields, twenty-one exact anchors and eleven related-study groups.
Manifest SHA-256:
`437888582ab4fb82ee647b24b4e40f9a2c1ca9b4ff34a5bd6120fa28fb81390e`.
These are synthetic or agent-authored development labels. Human adjudication and
held-out evaluation are `NOT_RUN`; a blank adjudication template and split manifest
are provided. Do not tune on these cases and then call them unseen evidence.

Compare three named lanes under the same available sources and output budgets:

1. Unchanged B0 block ranking, delivered prefix.
2. B1 exact windows with the identical full field question.
3. B1 exact windows with additional frozen explicit component queries.

The third lane has additional retrieval structure. Its gains cannot be attributed
solely to fixing windowing. Record any native budget violation or evaluator-only
transport clipping explicitly; never silently drop cases or change denominators.

Mandatory gates are exact ownership/quote integrity and declared budgets, the
late-block regression, stable offsets and honest source/index scope. Reject exact
duplicate anchors and overlap at least half the shorter span; report smaller
overlap and duplicated characters. Report component-anchor coverage, complete
answerable paper-fields, all per-case regressions, insufficient-context nonempty
candidate counts, latency and delivered sizes. Do not call any of these
supported-cell completion, unsupported-claim rate, calibrated confidence or
human usefulness without the corresponding generation/human evaluation.

The first development run recovered the mandatory late anchors. Question-only
B0/B1 exact-anchor coverage was 12/21 versus 15/21; complete answerable packets
were 5/10 versus 6/10, with no per-case regression. Explicit component queries
reached 21/21 anchors and 10/10 packets. Both insufficient-context fields still
returned candidates in all lanes. These are preliminary engineering observations;
final code hashes and rerun evidence belong in the completion receipt.

Decision: finish the inexpensive span, board and packet integration, retain an
explicit profile choice, and report remaining population/table/public-source
misses. Do not add dense retrieval, reranking, model calls or competitive claims
on this evidence. Human-reviewed held-out sources and real authorized model
measurement are the next validation work after software/browser acceptance.
