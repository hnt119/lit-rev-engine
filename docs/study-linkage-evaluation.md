# Study linkage: independent evaluation

Coordinator commit gate: exported the reviewed Git index into a fresh temporary checkout, verified all three licensed medical source hashes/metadata with the offline fixture checker, then ran the full suite with `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`. Actual result: **616 passed**, five existing SWIG warnings, 37.07 seconds. This includes all 40 independent API and 63 independent CLI cases and excludes five unrelated concurrent retrieval cases. Coordinator accepted both gates after reviewing implementation, literal fixture truth, acceptance tests and the ten-block documentation proof. This is an actual staged-checkout execution, not arithmetic subtraction from the shared 621-case result.

## E5 API gate

Status: accepted by the coordinator after code and independent evidence review. Evaluation owns `tests/test_study_linkage_acceptance.py` and this report. Operational implementation is owned separately. No operational files, existing data, environment settings, or concurrent retrieval work were changed during evaluation.

The source truth is Retrieval's invented bibliography and manifest in `tests/fixtures/studies/`. Assertions freeze hand-computed literal totals rather than deriving expectations from the linkage implementation. All eight fixture reports have distinct DOIs and retained raw metadata. Source descriptions identify five manual inventory entries A–E, but those descriptions do not establish associations until a review event is recorded.

| Current state | Included reports | Linked | Awaiting linkage | Link conflict | Observed distinct studies | Final current study total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Initial seven linkage events | 6 | 3 | 2 | 1 | 3 | null |
| Final ten linkage events | 6 | 6 | 0 | 0 | 3 | 3 |
| New review invalidates r5 adjudication | 6 | 5 | 0 | 1 | 3 | null |
| New adjudication resolves r5 | 6 | 6 | 0 | 0 | 3 | 3 |
| Clear r3's whole two-study set | 6 | 5 | 1 | 0 | 3 | null |
| Replace r3 set with C only | 6 | 6 | 0 | 0 | 3 | 3 |
| Eligibility revision includes r6/D | 7 | 7 | 0 | 0 | 4 | 4 |
| Eligibility revision excludes r6/D | 6 | 6 | 0 | 0 | 3 | 3 |

The initial three linked reports are r1/A, r2/A, and r3/B+C: overlap counts A once and the two-study report contributes both B and C. r4 is pending, r8 explicitly unlinked, and r5 has A/B disagreement. r6 retains its D link while excluded; unused E is retained in the inventory. Final associations resolve r4/B, r5/C, and r8/A. The eight reports, screening history, and retrieval history remain unchanged by linkage operations. The initial and final complete count dictionaries match the literal oracle, including all eight reconciliation identities.

The acceptance gate additionally proves:

- Latest complete sets replace earlier sets without union; disagreeing sets cannot produce a majority or combined result. Empty versus nonempty votes conflict, agreeing empty votes are unlinked, and empty adjudication clears an association. Equal timestamps retain insertion order, the active event IDs match the current votes or adjudication, later review invalidates adjudication, and history survives reopening.
- Inventory labels and registry metadata are preserved immutable values; identical labels/identifiers create separate manual identities. Pending or unresolved eligibility cannot contribute a study, and a confirmed report can legitimately contribute two distinct study identities.
- Both review and adjudication reject invalid lists, repeated IDs, blank IDs, unknown/cross-project targets, missing reviewer/reason, and unsupported report/project references without partial history or count changes. Nested nonstring JSON keys and nonfinite values are rejected without inventory changes.
- A reconstructed prior ledger schema opens compatibly, retaining generic keyed import results, search history, occurrence provenance, the exact old count dictionary, and nine-file export shape. Empty linkage history alone does not enable linkage. Explicit inventory or an empty review enables linkage; zero current inclusions then reports zero studies with complete current linkage.
- Opted-in exports contain 12 files, exact JSON studies/current associations/full events, ordered JSON ID lists in CSV, all event identity/kind/time fields, linkage metrics, safely escaped formula-like text, quoted multiline reasons, and unchanged raw occurrences. Unrelated destination notes are preserved and an unchanged snapshot exports identical bytes.
- A deterministic SQLite WAL second writer changes r1 from A to D after the reader captures records. Both `counts` and `export` retain the old complete version; the next read observes four studies and the extra event. The export keeps counts, current links, and append-only history consistent without timing-based waits.
- A verified five-record PubMed capture remains six exact hashed source assets plus its receipt in the 18-file linkage export; the exported capture verifies offline. A separate process uses the APIs and exports from a different directory without importing model libraries, settings, or dotenv or opening a network connection.

Commands and observed evidence:

```text
.venv/bin/python -m pytest tests/test_study_linkage_acceptance.py -q
34 passed in 0.93s  (initial independent coverage)
40 passed in 0.99s  (added narrowly missing contract cases)
40 passed in 1.01s  (final old-schema/export-field assertions)
```

The final 40-case run also strengthens old-schema reopening and exported field/metric assertions. No failing result required an operational fix or relaxed expectation. No evaluator expectation was corrected in E5. The full regression is intentionally deferred to the coordinator's staged gate after I5b, as instructed; prior PubMed/ledger acceptance remains separately documented.

Limits: these tests establish software state/count/provenance behavior using invented evidence. Manual identity accuracy and reviewer quorum remain protocol inputs. At the API handoff, I5b command-line acceptance and documented subprocess examples were the next gate; no live medical retrieval or inference is part of E5.

## E5b command-line gate

Status: independent acceptance passed; coordinator acceptance is pending. Evaluation owns `tests/test_study_cli_acceptance.py` and this report update. The API gate's 40 cases and existing PubMed evaluation files were preserved.

The primary workflow executes the absolute `review.py` path as fresh subprocesses from a different directory, against a temporary database and source/export paths containing spaces. It creates a project, imports the eight reports with a stable key, creates the five manual study identities with exact nested metadata, records screening/retrieval, and issues the frozen `study-create`, `studies`, `link-studies`, `adjudicate-links`, and `links` commands. Complete initial and final count dictionaries match the literal totals above. The six further source-fixture revisions match independent literal partitions, retain 14 linkage events, and finish at six included reports and three studies. Reopening through each command preserves chronology, earlier reviewer proposals, immutable source occurrences, and eligibility/retrieval histories. Keyed source retry leaves the entire final ledger state unchanged.

Additional command acceptance covers:

- Both association commands require either repeatable `--study-id` or explicit `--clear`. Missing/both modes, duplicate/blank/unknown IDs, late cross-project targets, foreign/unknown reports, blank reviewer/reason, and adjudication without a prior review produce contextual nonzero stderr, clean stdout, and no partial changes. Invalid association cases compare snapshots of both projects. Explicit clear appends an auditable empty review or adjudication; optional record filtering validates project membership.
- Identifiers reject malformed/nonobject JSON, NaN/Infinity constants, numeric overflow `1e309`, and duplicate keys at the top level, in nested objects, and inside arrays. Shared eligibility and filter parsing rejects the same ambiguous metadata without a project/import side effect. Valid JSON containing duplicate-looking text within a string remains exact; omitted identifiers default to `{}`.
- `links` captures current states and full history in one explicit snapshot. A deterministic WAL second writer clears an association immediately after current states are read; both unfiltered and record-filtered output retain the old matching state/history, and the next read exposes the new event and unlinked state. No real delays or timing assumptions are used.
- Export retains the complete inventory, current links, all 14 events, literal final counts, nested identifiers, and formula-shaped labels. JSON keeps the exact label while CSV escapes it. A fresh-process CLI workflow loads no model libraries, settings, or dotenv and opens no network connection.

Observed focused evidence:

```text
.venv/bin/python -m pytest tests/test_study_cli_acceptance.py -q
63 passed in 12.27s

.venv/bin/python -m pytest -q
621 passed, 5 warnings in 36.84s
```

The shared full suite includes 103 independent study cases (40 API + 63 CLI), 27 implementation study cases (13 API + 14 CLI), and the previous 491-case shared baseline. Five of those baseline cases belong to concurrent external retrieval work and remain outside this milestone's ownership. The five SWIG deprecation warnings are existing warnings. All prior ledger and PubMed acceptance passed unchanged.

No failed result required an operational change or relaxed assertion; no evaluator expectation was corrected in E5b. The 63-case file is frozen after this gate. The coordinator's clean staged regression and commit remain pending. Retrieval's separately reported ten-block documentation proof is independent evidence, not a test executed by Evaluation.
