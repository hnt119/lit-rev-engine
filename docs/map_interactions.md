# Semantic map interactions

The map explores a persisted saved search. Hovering, focusing, clicking, filtering
and switching views do not rebuild its embeddings or coordinates.

- Hover or focus a point to show its title, year and authors immediately in the
  compact preview above the plot. The preview updates locally before linked-list
  highlighting; it does not wait for a browser tooltip, API call or debounce.
- Paper targets have an invisible minimum **14 CSS px radius**, independent of
  responsive sizing and zoom. Visible dot radii and styles are unchanged. At
  high zoom, the entire painted marker and stroke remain interactive if larger.
- Overlapping targets choose the nearest screen-space paper center. Exact ties
  use stable paper-ID order; coincident papers remain individually accessible
  through the keyboard and paper list without coordinate jitter.
- Cursors are `pointer` over paper targets, `grab` on empty canvas, and `grabbing`
  only during an active pan. Paper-origin gestures never pan. Only a primary
  pointer starting on empty canvas can pan, after moving more than 4 CSS px;
  releasing a pan over a paper does not activate it.
- Full metadata remains in the fixed-height, keyboard-accessible scroll region
  after the pointer leaves. Long titles/authors do not move the plot.
- Click a point, or activate it with Enter/Space, to highlight and focus its paper
  in **Papers & source selection**. This does not select its checkbox.
- On desktop, only the paper panel scrolls. The page, map view and zoom stay put.
  Repeating an activation reveals the same paper again.
- On mobile, activation opens **Papers** and reveals the row. Sticky Map/Papers
  controls stay available. **Map** returns to the existing map view.
- **Inspect paper** explicitly opens the full inspector below the two panels.
- Neighbor navigation uses the same paper-row target. If a local filter hides
  that paper, navigation clears the filter with a visible status message. An
  ordinary point click preserves the filter because its matching row is visible.

Saved map/build controls sit below the map. Initial build actions and jobs that
need attention remain visible above it. Selected marker fills and selection
counts still update when checkboxes change. Review source provenance, preparation,
assessment and export contracts are unchanged.

## Earlier hover/navigation correction

Changed application files for this interaction correction:

| File | Responsibility |
| --- | --- |
| `apps/web/components/semantic-map.tsx` | Immediate local preview, deferred linked highlighting, complete metadata, explicit point action |
| `apps/web/components/map-explorer.tsx` | Saved controls below plot; initial/attention states retained |
| `apps/web/components/discover.tsx` | Separate paper reveal and full inspection; stable row targets; hidden-neighbor filter handling |
| `apps/web/components/exploration-panels.tsx` | Revision-like reveal sequence, committed mobile view changes, pane scrolling and focus |
| `apps/web/app/globals.css` | Compact stable preview, toolbar spacing, sticky mobile controls and scroll offsets |

`apps/web/tests/map-navigation.test.tsx` adds synthetic component/DOM regressions
for immediate metadata, deferred parent updates, rapid hover exit, desktop and
mobile navigation, repeated activation, explicit inspection and hidden neighbors.
Existing selection, coordinate, zoom, draft and query-proposal checks also run.
The existing map-build/cancellation test in
`apps/web/tests/map-component.test.tsx` now waits for its synthetic POST receipts
and always cleans up polling; the final concurrent test/build run exposed its
previous reliance on the timing of a void click callback.

From `apps/web`:

```sh
/Users/hunt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --import tsx --test tests/*.test.ts tests/*.test.tsx
NEXT_TELEMETRY_DISABLED=1 /Users/hunt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node node_modules/next/dist/bin/next build
```

These tests establish event/state behavior; they do not measure a millisecond
pointer-to-paint latency. Actual browser acceptance is recorded privately under
`.mvp-web-state/ui-checks/map-hover-navigation-2026-10-21/`, including desktop
and mobile screenshots. Browser checks use an existing persisted map and make
no search, source preparation or model-build submissions. No embedding or live
PubMed rerun is needed for this presentation change. Local startup remains the
[existing checkpoint procedure](mvp_v0_3.md).

Final local results on 2026-10-21: **31 frontend tests passed, zero skipped**;
production build including TypeScript passed; `git diff --check` passed. Python
tests were not rerun for this frontend-only correction.

Actual browser checks at 1280×720 confirmed that the complete plot fits its pane,
keyboard focus updates metadata, visible-point clicks reveal a paper far down
the list, and native pointer clicks leave both document and map scroll positions
unchanged. Repeated click/Enter, unchanged selection/coordinates, and retained
zoom/pan were checked. At 390×844, paper activation, sticky navigation, return to
Map and explicit inspection worked without horizontal overflow or covered
headings. Temporary viewport overrides were reset. No millisecond hover latency
was measured.

The saved research snapshot, original selection draft, map coordinates and saved
map/job counts matched their pre-check bindings. The local app was left running
at `http://127.0.0.1:3000/`. No commit, push, merge or deployment was performed.

## Paper targets and gesture ownership — 2026-10-21

Inspection confirmed custom **React + native SVG**, with no visualization library.
Previously, the root SVG captured pointer-down immediately unless the exact target
was a visible circle. Near-dot presses therefore belonged to panning. SVG `:active`
also showed `grabbing` during paper presses. Enlarging dots or changing cursor CSS
alone would not resolve this event-ownership defect.

The SVG now arbitrates centrally. It projects paper centers through the transformed
group's `getScreenCTM()` and chooses the nearest eligible center in screen CSS
pixels. This avoids transparent-circle overlap being resolved by paint order.
The high-zoom fallback checks the entire transformed painted circle/stroke,
including nonuniform transforms. Panning converts screen movement through the
inverse root SVG transform, accounting for responsive scaling and letterboxing.

Each gesture records its initial paper/canvas owner and pointer ID. Pointer capture
retains that owner. A small, same-paper release activates; slipping more than the
threshold cancels the paper action and cannot turn into panning. Empty-origin
gestures cross the threshold into pan and cannot select papers on release.
Cancellation and lost capture clean up state; other pointer IDs cannot steal the
gesture. Ordinary click events cannot duplicate release activation. Keyboard
Enter/Space and assistive click remain available.

### Changed files for this correction

| File | Change |
| --- | --- |
| `apps/web/components/semantic-map.tsx` | Central hit testing, gesture ownership, capture cleanup and immediate preview. |
| `apps/web/lib/map-interactions.ts` | New pure nearest-hit and coordinate helpers; 14 px target and 4 px pan threshold. |
| `apps/web/app/globals.css` | Cursor follows interaction state; removes unconditional `:active` grabbing. |
| `apps/web/tests/map-hit-interactions.test.tsx` | Eight independent geometry/event tests against the real component. |
| `apps/web/tests/map-navigation.test.tsx` | Existing tests drive root SVG pointer events and geometry instead of removed circle handlers. |
| `docs/map_interactions.md` | Usage, limits and verification evidence. |

One visible circle per paper, `data-map-point`, accessible labels, selected fill,
normal/hover/inspected radii, saved coordinates and public props are preserved.
The map-view helper, backend, retrieval, providers, embedding profiles, source and
assessment contracts were not changed.

### Verification

From `apps/web`:

```sh
/Users/hunt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --import tsx --test tests/*.test.ts tests/*.test.tsx
# 41 passed in 603.00ms; zero failed or skipped.
# Existing React test-renderer deprecation notices remain.

NEXT_TELEMETRY_DISABLED=1 /Users/hunt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node node_modules/next/dist/bin/next build
# Production compilation, TypeScript and page generation passed.
```

The eight new tests cover the radius boundary, affine geometry/letterboxing,
nearest overlap independent of event target/order, immediate title preview,
unchanged visible sizes, responsive zoom/pan, high-zoom marker extent, paper slip,
pan release, cursor state, capture/cancellation, foreign pointers, touch
deduplication, keyboard and assistive activation. Existing navigation, selection,
draft, map-preservation and offline-example checks still pass. The first legacy
navigation run called removed circle handlers; the updated drivers exercise the
real SVG handlers and all four navigation cases pass.

Native browser checks used the existing 30-paper saved map:

- At 1280 × 900, a click outside every visible dot fell inside overlapping targets
  for PMIDs `38684759` and `42117900`, approximately 9.83 and 11.87 px from their
  centers. The nearer paper won despite occurring earlier in paint order. Its
  title appeared and its row received focus; the transform and document scroll
  stayed unchanged, with computed cursor `pointer`.
- A drag starting in that paper target left the transform unchanged and activated
  no other paper. A 45 × 18 CSS px background drag panned the view, retained the
  inspected paper, and returned to `grab`. Mid-gesture `grabbing` is covered by
  event-state tests and CSS; no mid-drag browser screenshot was captured.
- After panning and zooming to 130%, clicking 12 px from PMID `37554965` activated
  that paper and retained the view transform.
- At 390 × 844, a 12 px near-dot click opened Papers and focused the matching row.
  Returning to Map retained its view. Body/document width remained 390 px;
  temporary viewport overrides were reset. This was a narrow browser viewport;
  touch ownership is tested synthetically, not on physical touch hardware.

Private screenshots, before/after bindings and browser receipts remain ignored in
`.mvp-web-state/ui-checks/map-hit-targets-2026-10-21/`. Ten research/request/draft/map
table bindings matched exactly before/after; 684 unrelated file hashes were
unchanged. No new searches, preparations, assessments or map builds were submitted.
No frame-rate or hover-latency benchmark was performed.

`git diff --check` passed. Python suites were not rerun for this frontend-only
correction. Live PubMed and real embedding/model checks: **NOT_RUN**. No provider
or paid inference calls were needed. The existing app was rebuilt and restarted
at `http://127.0.0.1:3000/`; startup uses the [existing procedure](mvp_v0_3.md).
Branch remains `codex/mvp-v0-3`, HEAD `404b002`, local main `a506ae0`, and staging
is empty. Nothing was committed, pushed, merged or deployed.
