# Use the question-to-evidence workbench

This guide describes the **unreleased development branch**, not the contents of the existing beta.4 download. It extends the same local Next.js/FastAPI application. Follow [the current installation/start/stop guide](user_manual.md) for prerequisites, private external data, loopback access, cookies and recovery limits. No model is required for this workflow.

## Try this development branch without opening existing research data

From this feature checkout on macOS, use the existing setup/launcher with a **new** external directory:

```sh
python3.12 scripts/local_preview.py setup
python3.12 scripts/local_preview.py launch --data-dir "$HOME/Library/Application Support/LiteratureReviewEngine-workbench-preview" --web-port 3118 --api-port 8918
```

Use a directory that does not contain your browser-beta or Track B data. Setup requires the normal Python/JavaScript dependency installation; it does not install weights or run research. Stop with Ctrl-C or the same launcher's authenticated stop workflow. Cookies still identify local access; clearing them does not provide workspace recovery. These are the existing supported launcher commands, not a claim of a newly tested installer. The Core workbench passed actual Windows x64 CI at source `bda0803`; physical Windows 11 and native executable validation remain NOT_RUN. No new native executable is supplied.

## 1. Design a search without losing your question

In Discover, enter your question. In guided mode, use **Define the search yourself** and **Add search concept**. Give each concept a scientific role, importance and intended use. Synonyms within a concept are OR alternatives; review AND/OR and explicit exclusions in the relationship editor before compiling.

- **Search concepts** restrict the database query.
- **Eligibility to check later** records conditions for later reading. It does not screen or exclude records.
- **Preferences and notes** stay outside the query unless explicitly promoted with a reason. They do not automatically rerank results.
- **Needs clarification** keeps undecided definitions visible.
- **Questions to extract after reading** are separate revision-bound design notes. They are not findings or automatically created comparison fields.

Recruitment geography, reported identity and availability of a relevant subgroup can be separate concepts. Do not assume that every microbiome question is about gut samples, that diet is mandatory, or that a location defines participants' ancestry. Broad/focused variants require explicit relationships and visible deferrals. A simpler query does not erase the scientific conditions recorded for later review.

**Paste my own query** retains a specialist strategy exactly. Switching to guided editing is explicit; unsupported syntax stays unparsed expert text. A new executable revision requires renewed approval. Save and review the exact candidate before **Approve this candidate**. Optional AI can propose a plan only through the configured adapter and explicit consent; it does not approve or execute it.

## 2. Understand checks and results

PubMed is the tested compiler target. **Check matches** is an explicit, bounded provider diagnostic: count, translated query, warnings, small identifier sample and optional known-paper checks. Opening or editing a plan does not run it. The current budget remains three approved seeds and at most two calls. A provider error is different from zero matches.

Known-paper **query membership** is different from appearing in the displayed capped preview. A paper absent from a top preview may still match the query. A DOI without an established PMID remains unresolved. Construction seeds used to tune the query are not held-out validation. Neither a diagnostic nor a bounded preview proves complete recall, relevance or an exhaustive review.

**Search papers** deliberately executes the approved candidate in a configured live workspace. A saved offline example does not execute supplied PubMed queries; its existing curated records are labeled separately. This checkpoint's real PubMed execution remains NOT_RUN unless separately authorized and observed.

Use **Download readable strategy** or **Download strategy JSON** to retain the exact candidate, question, concepts, dates/limits, approval, actual receipts, unresolved issues and design notes. Export makes no provider or AI call. An unrun operation stays unrun in the document. Terminology notes and researcher approval are not authoritative MeSH verification; no terminology registry is provided here.

For a search run outside the app, import its bibliography first. Add an **externally executed strategy** in design notes and select that imported collection's snapshot. Record the actual database, platform, exact query, date, limits and known count. It remains a researcher-recorded, unvalidated execution; the PubMed compiler does not validate another database's syntax.

## 3. Compare a working subset

Choose and prepare retained reports, then create a comparison board. Three papers and five fields fit the current limits. A 30-report board is a working subset, not the library or review limit. Reports are not automatically independent studies. Selection for exploration is not eligibility.

Keep the established editor: open a cell → find or browse excerpts → inspect exact retained source → explicitly use an excerpt → comment/judge → review/save. Draft-only notes, inspected scope, missing information and submitted entries remain separate. See [the detailed editor instructions](user_manual.md#select-an-excerpt-comment-and-save).

## 4. Add explicit typed attributes

Open **Paper profile & explicit classification** in a report row. Bind a dimension to an existing scientific field deliberately; labels and free text are not parsed into facts. Available dimensions distinguish reported population/identity, recruitment setting/geography, specimen/sample site, design and outcome/focus. Each dimension has an editable definition and revision.

Normalize values from the exact current submitted cell, with one value per input. Multiple specimen sites stay multiple values. Keep unknown, not assessed and not found in inspected material distinct; none means “No” or whole-paper absence. Add a reason and save the typed revision. Confirmation requires an explicit source-bound human-supported cell and a deliberate confirmation action. It is still self-declared research judgment, not independent verification. A proposal or unassessed origin stays unreviewed.

Use **Inspect or revise the original source-linked cell** to check or correct the underlying entry. Classification forms have their own durable drafts. They do not edit cell support, attach evidence or submit an entry automatically. Changing a source, field binding or cell head makes old classification outdated. Historical source-bound forms remain readable, with scientific editing disabled. History retains earlier attribute and view revisions.

No same-cohort relationship is inferred. If a report mentions two specimens and two outcomes, those values do not establish which specimen produced which outcome. Report-level co-occurrence is labeled explicitly; no same-cohort filter is offered.

## 5. Find, save and reopen a view

Use **Overview**, **Methods** or **Needs review** over the same board. Adjust **Filters, columns and order**. Multiple choices in one facet mean OR; different facets mean AND. Unknown has its own facet. Scientific filters use confirmed values by default. **Include explicitly typed unreviewed suggestions/classifications** is deliberate and changes which values can match; raw AI prose is not split into facets.

Choose visible fields, sorting and optional grouping. Grouping multiple specimen sites can repeat a report occurrence, so the interface shows unique reports separately from grouped occurrences. A filtered-out active paper or hidden field is reported explicitly; it does not silently select another paper. **Open any original comparison cell** remains available. View changes do not revise board definitions, invalidate saved cells, retrieve, index or call a model.

Save a named view to reopen its settings. Draft saving and saving a named view are different acknowledgments. Competing tabs use version checks; inspect the latest saved view and explicitly rebase or restore only view controls. Research cell drafts remain separate. Reopening must retain the base version rather than silently absorbing another tab's save.

## 6. Retrieve a passage and return safely

Use **Search passages for this comparison**, or **Open passage search for this field** from the existing cell's additional tools. The exact board revision, preparation, paper scope and pinned profile are carried forward. The question is prefilled; navigation alone does not search.

Edit the query and choose 5–30 results, then explicitly retrieve. Inspect a result's exact source and use **Open in comparison cell** / **Back to cell**. The original cell draft and view stay retained. Returning opens the inspector only; it never attaches, overwrites, marks support or saves. An excerpt from another report cannot be attached to this cell. Stale bindings fail visibly rather than switching to current workspace sources.

## 7. Export and understand access limits

**Download board CSV / board audit JSON** retain the existing scientific cell/history schemas. **Download current-view CSV / JSON** are separately labeled typed projections with the filter, order, source scope and classifications. A filtered export excludes hidden reports. To include all typed report profiles, clear the view filters deliberately first; an ordinary board export alone does not contain the new classification layer. Keep private exports local unless you choose to share them.

Citation CSV/RIS/identifier imports do not include PDF attachment bundles. The current web app has no supported attach-PDF-to-report path. Full-text acquisition, abstract-only status, unavailable evidence, local-file permission and cloud transmission consent are distinct. Use your own normal browser/library tools for access; do not supply publisher cookies or institutional passwords to the app. Local retention is not permission to send a source to a cloud model.

The [blank evaluation kit](question_evidence_evaluation/README.md) defines matched search-design and three-paper/five-field tasks. It contains no participant results, reference answers, competitor measurements or demonstrated model gains. Platform and actual software checks belong in the separate checkpoint validation report.
