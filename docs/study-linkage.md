# Linking reports to studies

The review ledger keeps citation deduplication, report eligibility, and study identity separate. Different publications about one study remain separate reports; one report can describe multiple studies. Manual study associations preserve these relationships and reconcile the count of studies behind currently included reports. [Cochrane's study/report guidance](https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-04) explains why secondary reports can remain useful sources.

Create studies with a label, reviewer, reason, and optional registry/source metadata. These identifiers are retained exactly, including nested JSON. They do not trigger registry lookup or automatic association, merging, or deduplication. Repeating a label or identifier creates another stable study ID. Study metadata is immutable in this version; there is no study merge/delete operation.

## Association decisions and counts

Every `link-studies` vote replaces that reviewer's **complete association set** for one report. Repeat `--study-id` for a report describing several studies. `--clear` explicitly records an empty set; omitting both modes is an error. IDs must be distinct and belong to the same project. A later vote does not union its IDs with an earlier vote. Reviewer and nonempty reason are required for every vote and adjudication.

| Current linkage state | Meaning |
| --- | --- |
| `pending` | No linkage events for the report. |
| `linked` | Latest reviewer sets agree on the same nonempty set, or an active adjudication establishes that set. |
| `unlinked` | Latest sets agree on an empty set, or an active empty adjudication clears the association. |
| `conflict` | Latest reviewer sets disagree, including empty versus nonempty. No union or majority is inferred. |

`adjudicate-links` requires an existing review event and supersedes prior votes. Any later review invalidates that adjudication; another adjudication may resolve the new state. All events remain in append-only history, with `active_event_ids` identifying the votes/adjudication currently used. A single review can produce `linked`; the review protocol remains responsible for its required reviewer quorum.

Linkage can be recorded before or after screening and never changes eligibility or retrieval status. Only currently full-text-included, linked reports contribute study IDs to the count. Several included reports of A count A once; a report linked to B and C contributes both. Excluded, unresolved, and pending reports and unused inventory entries do not establish included studies.

A project opts into linkage when it contains a study or linkage event. `linked_included_studies` is the observed distinct total, including while linkage is incomplete. `included_studies` remains **null** until every currently included report is linked; `study_linkage_complete` then becomes true. Pending/empty links contribute to `reports_included_awaiting_linkage`, while conflicts contribute to `reports_included_linkage_unresolved`. The partition always reconciles:

```text
reports_included = reports_included_linked
                 + reports_included_awaiting_linkage
                 + reports_included_linkage_unresolved
```

Incomplete linkage is a pending state, not an arithmetic error. A complete linkage total describes current confirmed inclusions; other reports may still await screening. Projects without studies/events retain `study_linkage_available=false` and `included_studies=null`.

## Reproduce six included reports and three studies offline

The independent [fixture README](../tests/fixtures/studies/README.md) and [manifest](../tests/fixtures/studies/manifest.json) describe eight invented reports. There are no real publications, trial registrations, or clinical findings. Their distinct invented DOIs retain eight canonical reports. Screening marks r1/r2/r3/r4/r5/r8 included, r6 excluded at full text, and r7 pending at title/abstract.

| Report | Initial association | Final association |
| --- | --- | --- |
| r1, r2 | A | A |
| r3 | B and C | B and C |
| r4 | Pending | B |
| r5 | Conflict between A and B | C by adjudication |
| r6, excluded | D | D; excluded from included-study totals |
| r7, unscreened | Pending | Pending |
| r8 | Empty set | A by reviewer revision |

Run from the repository root with the existing Python environment activated. Choose a fresh demonstration database:

```sh
STUDY_DEMO_DB="data/study-linkage-demo.sqlite3"
python review.py --db "$STUDY_DEMO_DB" create \
  --title "Synthetic study linkage demonstration" --type scoping \
  --question "Can eight invented reports retain their study relationships?"
```

Copy the returned project `id` UUID, then import the fixture and list its record IDs:

```sh
STUDY_PROJECT_ID="COPY_PROJECT_ID_FROM_CREATE_OUTPUT"
python review.py --db "$STUDY_DEMO_DB" import "$STUDY_PROJECT_ID" \
  tests/fixtures/studies/records.json --source "Synthetic study linkage fixture" \
  --import-key study-linkage-demo-v1
python review.py --db "$STUDY_DEMO_DB" records "$STUDY_PROJECT_ID"
```

Copy each record's `id` according to its DOI suffix `study-link-r1`, etc. r7 remains pending, so no write command needs its ID:

```sh
STUDY_R1="COPY_RECORD_ID_FOR_R1"
STUDY_R2="COPY_RECORD_ID_FOR_R2"
STUDY_R3="COPY_RECORD_ID_FOR_R3"
STUDY_R4="COPY_RECORD_ID_FOR_R4"
STUDY_R5="COPY_RECORD_ID_FOR_R5"
STUDY_R6="COPY_RECORD_ID_FOR_R6"
STUDY_R8="COPY_RECORD_ID_FOR_R8"
```

Set up the seven screened/retrieved reports. These states are invented software-fixture setup, not actual full-text acquisition:

```sh
for STUDY_REPORT_ID in "$STUDY_R1" "$STUDY_R2" "$STUDY_R3" "$STUDY_R4" "$STUDY_R5" "$STUDY_R6" "$STUDY_R8"; do
  python review.py --db "$STUDY_DEMO_DB" screen "$STUDY_PROJECT_ID" "$STUDY_REPORT_ID" \
    --stage title_abstract --decision include --reviewer fixture-screener
  python review.py --db "$STUDY_DEMO_DB" fulltext "$STUDY_PROJECT_ID" "$STUDY_REPORT_ID" \
    --status retrieved --reviewer fixture-screener --reason "Synthetic fixture setup only."
done
for STUDY_REPORT_ID in "$STUDY_R1" "$STUDY_R2" "$STUDY_R3" "$STUDY_R4" "$STUDY_R5" "$STUDY_R8"; do
  python review.py --db "$STUDY_DEMO_DB" screen "$STUDY_PROJECT_ID" "$STUDY_REPORT_ID" \
    --stage full_text --decision include --reviewer fixture-screener
done
python review.py --db "$STUDY_DEMO_DB" screen "$STUDY_PROJECT_ID" "$STUDY_R6" \
  --stage full_text --decision exclude --reviewer fixture-screener \
  --reason "Synthetic eligibility rule excludes this invented source."
```

Create five inventory entries. A's registry-like value is invented metadata; B–E show the optional metadata default. `--identifiers-json` requires a finite object and rejects duplicate keys, including nested objects:

```sh
python review.py --db "$STUDY_DEMO_DB" study-create "$STUDY_PROJECT_ID" \
  --label "Synthetic Study A" --reviewer fixture-curator --reason "Invented source grouping for r1, r2, r8." \
  --identifiers-json '{"registry":{"namespace":"SOFTWARE_FIXTURE_ONLY","accession":"SYNTHETIC-A"}}'
python review.py --db "$STUDY_DEMO_DB" study-create "$STUDY_PROJECT_ID" \
  --label "Synthetic Study B" --reviewer fixture-curator --reason "Invented B cohort in r3 and r4."
python review.py --db "$STUDY_DEMO_DB" study-create "$STUDY_PROJECT_ID" \
  --label "Synthetic Study C" --reviewer fixture-curator --reason "Invented C cohort in r3 and r5."
python review.py --db "$STUDY_DEMO_DB" study-create "$STUDY_PROJECT_ID" \
  --label "Synthetic Study D" --reviewer fixture-curator --reason "Retain identity of excluded r6."
python review.py --db "$STUDY_DEMO_DB" study-create "$STUDY_PROJECT_ID" \
  --label "Synthetic Study E" --reviewer fixture-curator --reason "Unused inventory entry."
python review.py --db "$STUDY_DEMO_DB" studies "$STUDY_PROJECT_ID"
```

Copy each returned study `id`; E stays unused:

```sh
STUDY_A="COPY_STUDY_A_ID"
STUDY_B="COPY_STUDY_B_ID"
STUDY_C="COPY_STUDY_C_ID"
STUDY_D="COPY_STUDY_D_ID"
```

Record the initial association votes, including deliberately conflicting proposals for r5 and an explicit empty set for r8:

```sh
python review.py --db "$STUDY_DEMO_DB" link-studies "$STUDY_PROJECT_ID" "$STUDY_R1" \
  --study-id "$STUDY_A" --reviewer linker-one --reason "Invented primary source names A."
python review.py --db "$STUDY_DEMO_DB" link-studies "$STUDY_PROJECT_ID" "$STUDY_R2" \
  --study-id "$STUDY_A" --reviewer linker-one --reason "Invented follow-up describes the same A cohort."
python review.py --db "$STUDY_DEMO_DB" link-studies "$STUDY_PROJECT_ID" "$STUDY_R3" \
  --study-id "$STUDY_C" --study-id "$STUDY_B" --reviewer linker-one --reason "One invented report describes B and C."
python review.py --db "$STUDY_DEMO_DB" link-studies "$STUDY_PROJECT_ID" "$STUDY_R5" \
  --study-id "$STUDY_A" --reviewer linker-one --reason "Scripted incorrect A proposal; source truth remains C."
python review.py --db "$STUDY_DEMO_DB" link-studies "$STUDY_PROJECT_ID" "$STUDY_R5" \
  --study-id "$STUDY_B" --reviewer linker-two --reason "Scripted incorrect B proposal disagrees with A."
python review.py --db "$STUDY_DEMO_DB" link-studies "$STUDY_PROJECT_ID" "$STUDY_R6" \
  --study-id "$STUDY_D" --reviewer linker-one --reason "Excluded r6 retains its D association."
python review.py --db "$STUDY_DEMO_DB" link-studies "$STUDY_PROJECT_ID" "$STUDY_R8" \
  --clear --reviewer linker-one --reason "Initial review establishes no association."
python review.py --db "$STUDY_DEMO_DB" links "$STUDY_PROJECT_ID"
python review.py --db "$STUDY_DEMO_DB" counts "$STUDY_PROJECT_ID"
```

Expected: six included reports partition into **3 linked + 2 awaiting + 1 unresolved**. Observed study union is A/B/C, so `linked_included_studies=3`, `included_studies=null`, and `study_linkage_complete=false`. D is associated only with excluded r6; E is unused. Arithmetic reconciliation passes.

Complete the three outstanding associations:

```sh
python review.py --db "$STUDY_DEMO_DB" link-studies "$STUDY_PROJECT_ID" "$STUDY_R4" \
  --study-id "$STUDY_B" --reviewer linker-one --reason "Companion source establishes B."
python review.py --db "$STUDY_DEMO_DB" adjudicate-links "$STUDY_PROJECT_ID" "$STUDY_R5" \
  --study-id "$STUDY_C" --reviewer fixture-adjudicator --reason "Resolve A/B proposals using the invented C source."
python review.py --db "$STUDY_DEMO_DB" link-studies "$STUDY_PROJECT_ID" "$STUDY_R8" \
  --study-id "$STUDY_A" --reviewer linker-one --reason "Replace this reviewer's empty set with A."
python review.py --db "$STUDY_DEMO_DB" links "$STUDY_PROJECT_ID" --record-id "$STUDY_R5"
python review.py --db "$STUDY_DEMO_DB" counts "$STUDY_PROJECT_ID"
```

Expected: **6 linked + 0 awaiting + 0 unresolved**, `included_studies=3`, and `study_linkage_complete=true`. A counts once across r1/r2/r8; r3 retains both B and C. The ten linkage events preserve all original votes. r7 still awaits screening.

## Revise, clear, inspect, and export

A later r5 review invalidates its earlier adjudication. Here linker-one's latest C set disagrees with linker-two's B set, making the final total null again. A new adjudication resolves it:

```sh
python review.py --db "$STUDY_DEMO_DB" link-studies "$STUDY_PROJECT_ID" "$STUDY_R5" \
  --study-id "$STUDY_C" --reviewer linker-one --reason "Later review reopens the prior adjudication."
python review.py --db "$STUDY_DEMO_DB" counts "$STUDY_PROJECT_ID"
python review.py --db "$STUDY_DEMO_DB" adjudicate-links "$STUDY_PROJECT_ID" "$STUDY_R5" \
  --study-id "$STUDY_C" --reviewer fixture-adjudicator --reason "Confirm C after the later review."
```

Clear r3's entire set, then replace it with C only. B is not restored by union; it remains observed through included r4:

```sh
python review.py --db "$STUDY_DEMO_DB" link-studies "$STUDY_PROJECT_ID" "$STUDY_R3" \
  --clear --reviewer linker-one --reason "Explicitly clear the complete B/C set."
python review.py --db "$STUDY_DEMO_DB" counts "$STUDY_PROJECT_ID"
python review.py --db "$STUDY_DEMO_DB" link-studies "$STUDY_PROJECT_ID" "$STUDY_R3" \
  --study-id "$STUDY_C" --reviewer linker-one --reason "Replace the cleared set with C only."
python review.py --db "$STUDY_DEMO_DB" links "$STUDY_PROJECT_ID" --record-id "$STUDY_R3"
python review.py --db "$STUDY_DEMO_DB" counts "$STUDY_PROJECT_ID"
python review.py --db "$STUDY_DEMO_DB" export "$STUDY_PROJECT_ID" "data/study-linkage-demo-export"
```

The clear step gives five linked inclusions and one awaiting linkage; C-only replacement restores six linked reports and three included studies. There are now fourteen linkage events. Eligibility revisions also change the contributing report/study union without deleting any associations; the fixture manifest contains a separate r6 inclusion/exclusion probe.

`links` returns `{"links": [...], "events": [...]}` in one read snapshot, optionally restricted to a record. `studies` returns the stable inventory including unused E. These commands and exports are offline; success stdout contains JSON, and invalid inputs produce contextual nonzero errors on stderr. Study/link writes are atomic and cannot reference another project's study/report.

For projects using linkage, `project.json` adds `studies`, `study_links`, and `study_link_events`; export adds `studies.csv`, `study_links.csv`, and `study_link_events.csv`. They preserve metadata, current states, complete event sets, reviewer/reason/time, and history. CSV text is formula-safe while JSON retains exact values. Counts, associations, events, and any retained PubMed artifacts come from one SQLite snapshot. Generic projects without linkage retain their existing nine-file export shape.

## Python API

Use these `ReviewStore` methods with actual project/report/study UUIDs. All calls are offline; they require explicit manual decisions and initialize no model, registry lookup, or network request.

| Method | Input/result |
| --- | --- |
| `create_study(project_id, label, reviewer, reason, identifiers=None)` | Create immutable study metadata; returns its new stable `id` and supplied metadata. |
| `list_studies(project_id)` | Return studies in creation order, including unused entries. |
| `record_study_links(project_id, record_id, study_ids, reviewer, reason)` | Append a review event with a complete replacement list; `[]` explicitly clears that reviewer's associations. |
| `adjudicate_study_links(project_id, record_id, study_ids, reviewer, reason)` | Append adjudication after an existing review; `[]` can explicitly clear associations. |
| `list_study_links(project_id, record_id=None)` | Return current `state`, sorted `study_ids`, and `active_event_ids` for reports in creation order. |
| `list_study_link_events(project_id, record_id=None)` | Return append-only event history with reviewer/reason/kind/time and complete association sets. |

`counts(project_id)` and `export_project(project_id, directory)` expose the same reconciliation/provenance as the CLI. Reopen the same database to continue; rerunning vote commands appends new events rather than overwriting history. Report inclusion, manual study identity, and a complete biomedical search remain separate review responsibilities.
