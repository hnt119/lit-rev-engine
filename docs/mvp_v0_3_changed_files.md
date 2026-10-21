# MVP v0.3 checkpoint changed files

Local branch: `codex/mvp-v0-3`, based on actual v0.2 commit
`404b002cd5feb7c847841135bdd383370e738c04`. The user authorized committing and
pushing this reviewed checkpoint on 21 October 2026. Main remains at `a506ae0`;
merging, deployment and private research publication are outside scope.

The table below records the original checkpoint 0 work. Later reviewed additions
include the public thirty-paper offline pack and saved-map import
([manifest](offline_example.md)), compact query extraction
([manifest](query_suggestions.md)), and nearest-paper interaction fixes
([manifest](map_interactions.md)). The comparison board remains planned.

| File | Change |
| --- | --- |
| `src/mvp/research_case.py` | New strict protocol, exact approval binding, read-only case audit, honest execution categories and private manifests |
| `scripts/mvp_research_case.py` | New explicit `check` / named saved-case `audit` CLI |
| `tests/mvp/test_research_case.py` | New offline implementation acceptance cases |
| `tests/mvp/test_research_case_independent.py` | New independent provenance, privacy, history and reporting cases |
| `examples/mvp/research_case_protocol.example.json` | Generic pending-approval protocol; no private workbook text |
| `apps/web/components/discover.tsx` | Functional draft update retains rapid selections and enforces the ten-paper cap |
| `apps/web/components/semantic-map.tsx` | Keyboard-accessible, stable hover metadata retaining the last displayed record |
| `apps/web/app/globals.css` | Fixed-height scrollable hover metadata and reserved paper-row highlight geometry |
| `apps/web/tests/discover-selection.test.tsx` | Real component/hook regression for batched selections, cap and replacement |
| `apps/web/tests/map-component.test.tsx` | Long-author metadata and keyboard-region regression |
| `docs/mvp_v0_3.md` | Current checkpoint startup, case locations, audit use and limitations |
| `docs/mvp_v0_3_case_protocol.md` | Exact case preparation, audit semantics and rights boundaries |
| `docs/mvp_v0_3_evaluation.md` | Fresh baseline, software checks, real capture/model/source evidence and outstanding human evaluation |
| `docs/mvp_v0_3_board_plan.md` | Proposed comparison-board interfaces, tickets and acceptance criteria; not implemented |
| `docs/mvp_v0_3_changed_files.md` | This scoped manifest |

The existing research engine, Qwen interfaces/profiles, ledger, source contracts,
retrieval profile and original export schemas were not edited. The historical
one-paper fixture and existing map coordinates are unchanged. A new public
offline bundle extends the saved-example provider; its import uses the existing
SQLite/map storage. The map UI fixes affect presentation and input handling.

Only the current-MVP README sections belong to this checkpoint. Its preexisting
retrieval-experiment section and the `.gitignore` edit, supplied workbook/briefs,
data/benchmark/report directories, retrieval experiments and workflow assets are
outside this change list. A private preservation inventory records 145 existing
files for hash comparison. The local `.env` contact was configured at the user's
request without printing or publishing its value; unrelated configuration was
preserved. Actual captures, protocols, SQLite credentials and screenshots remain
ignored private state and are excluded from publication.

See [the evaluation report](mvp_v0_3_evaluation.md) for exact executed commands,
results and distinctions between offline software, live provider execution,
local model execution and human judgments. See [the checkpoint guide](mvp_v0_3.md)
for startup instructions and [the board plan](mvp_v0_3_board_plan.md) for the next
implementation cycle.

## Consolidated publication manifest

The authorized checkpoint contains 111 files: the 44 paths below and the 67-file
public offline source/map bundle under `examples/mvp/offline_microbiome_30_v1/`.
The bundle README and manifest enumerate article identities, permissions and
file hashes. Private runtime captures and the supplied workbook are excluded.

```text
README.md
apps/web/app/globals.css
apps/web/components/discover.tsx
apps/web/components/exploration-panels.tsx
apps/web/components/map-explorer.tsx
apps/web/components/semantic-map.tsx
apps/web/lib/map-interactions.ts
apps/web/tests/discover-selection.test.tsx
apps/web/tests/map-component.test.tsx
apps/web/tests/map-hit-interactions.test.tsx
apps/web/tests/map-navigation.test.tsx
apps/web/tests/map-selection-integration.test.tsx
apps/web/tests/offline-example.test.tsx
apps/web/tests/query-suggestions.test.tsx
docs/map_interactions.md
docs/mvp_v0_3.md
docs/mvp_v0_3_board_plan.md
docs/mvp_v0_3_case_protocol.md
docs/mvp_v0_3_changed_files.md
docs/mvp_v0_3_evaluation.md
docs/offline_example.md
docs/query_suggestions.md
examples/mvp/research_case_protocol.example.json
scripts/build_saved_example_map.py
scripts/capture_offline_example.py
scripts/mvp_research_case.py
src/mvp/adapters/map_storage.py
src/mvp/adapters/saved_example_map.py
src/mvp/adapters/saved_examples.py
src/mvp/map_jobs.py
src/mvp/query_suggestions.py
src/mvp/research_case.py
src/mvp/service.py
src/web_api/app.py
tests/mvp/test_offline_example_30.py
tests/mvp/test_providers.py
tests/mvp/test_query_suggestions.py
tests/mvp/test_query_suggestions_independent.py
tests/mvp/test_research_case.py
tests/mvp/test_research_case_independent.py
tests/web_api/test_api.py
tests/web_api/test_long_query.py
tests/web_api/test_offline_example_map.py
tests/web_api/test_query_suggestions.py
```

Fresh pre-publication software checks: 227 MVP tests passed in 9.08 seconds;
130 mapping/API tests passed in 34.52 seconds; no skips. The unchanged frontend
passed 41 tests and production compilation in the preceding map checkpoint.
No live provider or embedding rerun was performed for publication.

The exact staged files were also exported without unrelated working-tree files.
That isolated tree passed 227 MVP tests and 41 frontend tests. Mapping/API checks
passed 129 cases there; the historical baseline-reader case initially lacked a
Git object database, then passed with explicit `GIT_DIR` and `GIT_WORK_TREE`
pointing to the existing object database and isolated tree. No test was skipped
or weakened. The full mapping/API suite also passed all 130 cases in the original
checkout before export.

The staged whitespace check passes for software, tests, documentation and JSON.
Raw provider XML is excluded from whitespace normalization: its original trailing
spaces are retained so source hashes and provenance remain exact. The full staged
check reports those source-formatting notices; bundle integrity tests pass.
