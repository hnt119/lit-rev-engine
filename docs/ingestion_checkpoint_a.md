# Checkpoint A — inspector navigation and selection policy

Baseline: `codex/mvp-v0-3` at `551068a16741820fe316b5027b5b181f4e0c9770`.
Executed 21 October 2026. No commit, push, deployment, live provider call or model
inference was performed. Existing research databases have private safety copies;
no historical sources, cell revisions, maps or frozen retrieval profiles changed.

## Delivered

Native Previous/Next controls sit immediately below the inspector selection
control, follow the filtered displayed order, do not wrap and announce position
and title. Filtering out the current paper retains its inspector and disables
sequence navigation. Navigation keeps stable controls, keyboard focus and map
transform, and does not select or prepare papers.

`src/mvp/limits.py` is the Python selection authority. API validation, capability
projections, React and Streamlit accept a maximum of 30 distinct owned papers;
selection drafts allow an empty selection and use existing compare-and-swap
writes. Rejection preserves a previous valid draft. The legacy synchronous
preparation path remains bounded at ten. Preparing more than ten stays gated
until checkpoint B passes; discovery, board and proposal budgets are separate.
No dependency or version changes were needed.

## Fresh execution evidence

| Command/check | Actual result |
|---|---|
| `/private/tmp/lre-mvp-venv/bin/python -m pytest tests/mvp -q -rs` | 402 passed, one old eleven-selection rejection assertion failed. Updated that assertion to the new 31 boundary. |
| Same Python, `-m pytest tests/mvp/test_acceptance.py::test_search_and_selection_caps_are_validated_before_provider_calls tests/mvp/test_selection_limits_independent.py -q -rs` | 15 passed; covers the corrected assertion and all 14 independent selection tests. 403 unique MVP tests now pass across these runs. |
| `.venv-map/bin/python -m pytest tests/web_api -q -rs` | 74 passed, zero skips; two existing dependency deprecation warnings. |
| Bundled Node, `--import tsx --test tests/*.test.ts tests/*.test.tsx`, from `apps/web` | 67 passed, zero skips. Includes three independent inspector interaction tests. |
| Bundled Node, `node_modules/typescript/bin/tsc --noEmit --incremental false` | Passed. A test capability typing issue was corrected before this passing check. |
| Bundled Node, `node_modules/next/dist/bin/next build`, isolated frontend copy with existing theme tokens and installed dependencies | Passed. The first isolated copy omitted the shared theme file; including that existing file fixed the setup failure without an application change. |

An evaluator's initial HTTP fixture omitted required `truncated=False`; fixing
that synthetic fixture resolved its setup failures. These are software checks,
not scientific relevance, retrieval quality or human-usefulness validation.

## Actual browser checks

An isolated loopback UI/API, temporary data directory and distinct session cookie
protected the existing research browser session. The UI opened the existing
public thirty-paper example, with no live capture or model execution.

- Desktop 1280 × 720: first boundary disabled; click and Enter advanced papers;
  Space advanced through a six-paper Japanese filter in displayed order.
- Filtering out the inspected paper retained its title/context and disabled both
  sequence buttons with an explicit notice.
- Keyboard focus stayed on Next; its viewport position across differently sized
  abstracts stayed within 0.2 px. Selected count stayed zero and the saved map
  transform stayed unchanged.
- Mobile 390 × 844: keyboard advancement worked, the controls stayed inside the
  viewport, focus and selection stayed intact. The viewport override was reset.

Private screenshots/receipts are excluded from versioned source. Empty/singleton,
rapid batched navigation, 31st selection, draft conflicts and map preservation
also have automated coverage. This checkpoint does not enable thirty-source
provider execution; its durability and storage gates belong to B.

## Changed files

```text
apps/streamlit/app.py
apps/web/app/globals.css
apps/web/components/discover.tsx
apps/web/lib/generated-api.ts
apps/web/lib/openapi.json
apps/web/lib/paper-selection.ts
apps/web/tests/discover-selection.test.tsx
apps/web/tests/inspector-navigation-independent.test.tsx
apps/web/tests/map-navigation.test.tsx
apps/web/tests/map-selection-integration.test.tsx
apps/web/tests/offline-example.test.tsx
apps/web/tests/paper-selection.test.ts
apps/web/tests/query-suggestions.test.tsx
docs/ingestion_checkpoint_a.md
docs/ingestion_rag_checkpoints.md
src/mvp/contracts.py
src/mvp/limits.py
src/mvp/service.py
src/web_api/app.py
src/web_api/contracts.py
tests/mvp/test_acceptance.py
tests/mvp/test_selection_limits_independent.py
tests/web_api/test_selection_limits_independent.py
```

## Startup and limits

Follow the [existing local web startup](mvp_v0_3.md#run-locally); rebuild the
frontend and restart the API to load changes. Streamlit remains available with
the existing installation. Use one provider-owning local process. No paid
inference is configured, and the older engine/board/proposal behavior remains
available. README, supplied briefs, private captures and unrelated experiments
were left untouched.
