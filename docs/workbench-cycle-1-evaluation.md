# Workbench cycle 1: software acceptance

Date: 2026-10-15. Scope: local reviewer software using already exposed, saved confirmation evidence. This cycle contains **zero real human assessments, zero new model inference, and zero paid inference calls**. Ratings in the acceptance tests are synthetic software fixtures confined to test temporary directories; they are not review evidence.

The workbench passed **68 independent acceptance checks**. This establishes the tested behavior below. It does not establish that a reviewer finds the tool useful, that a model answers questions correctly, or that one retrieval method is more effective for a new task.

## Implemented

- A saved receipt is opened only with an externally supplied SHA-256 of its entire file. The frozen component code validates the job/results and reconstructs all four methods; the loader compares the complete saved recomputation before producing a packet.
- The packet retains questions, components, exact passage anchors and full canonical source blocks. It declares source answerability `not_assessed`, current ledger state `not_checked`, and independent verification `NOT_RUN`.
- Passage and component ratings retain null for unknown judgments. Bundle support, missing components, supporting passages, contradictions, source inspection and declared review duration are explicit fields. Passage grades do not infer a bundle's support status.
- The local assessment store appends checksum-bound records, preserves previous bytes, requires explicit replacement of the current record, and rejects stale receipt/question/trace bindings.
- Anonymous method labels are the default. Revealing methods, scores and selection reasons is explicit and the saved record includes its display mode. Labels are deterministic and do not guarantee that a familiar reviewer is blind.
- The server binds to `127.0.0.1`, has exact routes, requires the exact local Host and mutation Origin, requires `X-Workbench-CSRF`, bounds request/file sizes, and supplies a restrictive CSP and no-store responses. Source and review text are rendered as inert text by the UI. This is a local development server, not a public hosting service.
- Evaluation reports describe current human records and preserve superseded history. Observed useful/strict passage proportions divide only by rated passages. Useful Precision@5 counts grades 2 or 3; strict Precision@5 counts grade 3. Both require all five displayed passages to be explicitly rated. Missing or null ratings cannot become zero grades or enter either Precision@5 denominator.

## Independently tested

Test source: [test_review_workbench_acceptance.py](../tests/test_review_workbench_acceptance.py). Exact command from the repository root:

```sh
.venv/bin/python -m pytest tests/test_review_workbench_acceptance.py -q --disable-warnings
```

Observed final result: **68 passed in 10.35s**, exit 0. HTTP tests required permission to bind temporary loopback sockets because the restricted filesystem execution sandbox rejects socket binding. They did not use remote networking.

| Area | Checked behavior |
| --- | --- |
| Saved evidence identity | Original archive and whole receipt digest; 8 questions, 32 bundles, 160 displayed passages, 2 sources and 100 canonical blocks; exact displayed quote spans and source digests |
| Receipt rejection | Wrong whole-file hash, envelope-hash substitution, changed bytes, changed trace with a recomputed outer checksum, duplicate JSON keys and nonfinite JSON |
| Default blindness | No method keys, scores, query scores or selection reasons in default public bundles; explicit reveal; no mutation of the underlying packet |
| Assessment contracts | Invalid status/types, booleans masquerading as numeric grades/durations, nonfinite values, unknown/duplicate passage references, inexact component keys, foreign support/components, undeclared claim fields |
| Persistence | Null ratings survive reload; immutable original bytes; explicit supersession; stale replacement rejection; cross-reviewer/bundle replacement rejection; record checksum and packet/trace tampering rejected on reload |
| Filesystem | Symlink receipt, ancestor directory, assessment directory and record rejection; parent traversal rejection; demo output reuse refusal; immutable evaluation output |
| Human metrics | Zero records yield unknown means; omitted ratings count as unknown; observed grade proportions use 4 or 5 explicit grades in the arithmetic fixtures; incomplete bundles yield null Precision@5; a fully rated `[3, 2, 1, 0, 2]` fixture yields useful 3/5 and strict 1/5; only the current revision contributes |
| Local HTTP | Loopback binding; session/page loading; exact route rejection; Origin/Host/token rejection including duplicate Origin/token; content-type, content-length, size, nonfinite JSON and transfer-encoding rejection; save/reload and server-bound revealed mode; markup-like reason remains text data |
| Offline boundary | A separate Python audit-hook process rejects `.env` or repository `data/` reads, model-library imports, database opens, socket use and child processes while exercising demo → receipt load → empty summary; it completes successfully |

The demo test selects only the pinned original `validation.receipt.json` from the bounded committed archive into an explicit new temporary directory. It creates no assessment and extracts no archive tree. The CLI evaluation test starts with no records, writes an unknown-valued report, and verifies that a second invocation cannot overwrite that report.

## Integration and browser checks

The coordinator exported only staged files with `git checkout-index --all --prefix=/private/tmp/lre-workbench-clean-cycle1/`, excluding unrelated working-tree experiments, private data and `.env`. From that clean directory:

```sh
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /Users/hunt/Desktop/lit-rev-engine/.venv/bin/python -m pytest -q
```

Result: **1,950 passed, 1 skipped, 31 subtests passed in 158.73 seconds**, exit 0. The existing skip is the bootstrap test whose retained verified pip wheel is unavailable; it has no download fallback. Five PyMuPDF/SWIG deprecation warnings were reported. Subsequent changes were documentation and CSS formatting; Python/JavaScript implementation bytes remained the same.

The actual local page was exercised in the Codex in-app browser against a temporary loopback server:

- “Inspect source” highlighted the exact saved anchor.
- A sufficient judgment without support was rejected while preserving the draft.
- A synthetic `software_smoke_only` uncertain record saved and survived reload, with all 20 visible whole-question/component grades still unassessed.
- Explicit revision appended a second immutable record; the page showed one current and one superseded record after reload.
- Default rendered text contained no Qwen/BM25 method names, reranker scores or selection reasons. No browser warning/error logs were observed.
- CLI export of those temporary synthetic records retained two historical records, one current record, unknown grades and null P@5. Source answerability remained unassessed and independent verification `NOT_RUN`.

The synthetic browser records live only in the coordinator's temporary test directory and are not committed or real review decisions. These checks demonstrate save/navigation behavior; they do not constitute a human usability pilot.

The reusable [UI event harness](../tests/workbench_ui_smoke.cjs) also passed with Node 18+:

```sh
node --check src/review_workbench/static/workbench.js
node tests/workbench_ui_smoke.cjs
```

It exercises the actual JavaScript against a small synthetic DOM/event shim: null defaults, Unicode code-point highlights, save payload/CSRF, history reload, explicit supersession, draft preservation after an error, question switching, diagnostic disclosure and inert hostile strings. This is separate from the real-browser evidence above; no npm dependencies or network calls are required. The [core tests](../tests/test_review_workbench_core.py) add 16 implementation checks, including a two-process save race. Together with the 68 independent cases, all **84 workbench Python tests** passed within the full suite.

## Preserved baseline checks

The selected original receipt has 8,597,476 bytes and whole-file SHA-256 `3ba4da317d497cc021a90e9dcc9f88b3667bbdba85e7f94b633f7427dc7a9c80`. Its saved job SHA-256 is `46cdb4be34507d170d656eeba19478bf493acdfe6315a352ae37bc941d0b19e5`; saved results payload SHA-256 is `8867d3da507dd32802f083be963e4799eca101a2f4d8afa47cf22f95688d3fbc`. These identities bind existing evidence; they are not a new retrieval run.

This command also completed with exit 0:

```sh
.venv/bin/python tests/fixtures/qwen_components_confirmation_run_v1/verify.py
```

It reported `status: verified`, `quality_status: passed`, 14 archive members, `database_opened: false`, and `paid_inference_calls: 0`. It reproduced the **existing** 94.4444% candidate mean support coverage and 5/6 complete positives. It used no database, GPU or inference. Remote execution and the original ledger-readonly provenance remain preserved claims, as stated by that verifier.

All file bindings in the three historical manifests were independently rehashed: confirmation **75/75**, development **72/72**, Kaggle v2 **35/35**. Exact command:

```sh
.venv/bin/python - <<'PY'
import hashlib, json
from pathlib import Path
for name in (
    'qwen-components-confirmation-freeze-v1.json',
    'qwen-components-development-freeze-v1.json',
    'qwen-kaggle-freeze-v2.json',
):
    value = json.loads((Path('docs') / name).read_bytes())
    for relative, binding in value['files'].items():
        body = Path(relative).read_bytes()
        assert {'sha256': hashlib.sha256(body).hexdigest(),
                'size_bytes': len(body)} == binding, relative
    print(f'{name}: {len(value["files"])}/{len(value["files"])} file bindings match')
PY
```

The current work does not revise those retrieval results, gates, profiles or frozen sources.

## NOT_RUN and practical limits

- **Real reviewer pilot: NOT_RUN.** No human has supplied relevance, component support or bundle judgments for this cycle. Review duration and source inspection fields are self-reported and are not evidence of actual inspection.
- **Source-first reference annotation: NOT_RUN.** The retained canonical text is not the original PDF/XML byte stream or a current-ledger check. A retrieved-bundle judgment cannot establish whether the source itself answers the question.
- **Independent human verification: NOT_RUN.** A checksum verifies integrity relative to a known identity; it does not independently validate clinical meaning or factual conclusions.
- **Fresh confirmation, competitive effectiveness and answer accuracy: NOT_RUN.** Two already exposed articles and eight fixed questions are useful regression material. They cannot establish generalization, a clinical outcome, or the performance of a new human team.
- **nDCG: NOT_RUN.** No independently annotated common candidate universe and ideal ranking are available. The tool does not manufacture one from the displayed passages.
- **New model inference and method tuning: NOT_RUN.** No new embeddings, reranking, paid calls or remote jobs were used.
- The independent suite tests HTTP behavior; separate source inspection found inert `textContent` rendering. These checks do not replace an interactive browser accessibility/usability pilot or a deployment security assessment.

## Proposed next evidence step

If the team authorizes a human pilot, freeze its reviewer protocol, eligibility and rubric first. Use real reviewers and new source-first references, preserve blind/revealed exposure, and report judgment coverage and reviewer denominators before comparing methods. Keep that pilot's records separate from synthetic tests and from this exposed regression demonstration. No such pilot was started in cycle 1.
