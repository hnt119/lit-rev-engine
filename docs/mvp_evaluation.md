# MVP v0.1 evaluation

The acceptance suite in `tests/mvp/test_acceptance.py` exercises the application
service with temporary private storage and synthetic software fixtures. Synthetic
papers and judgments in these tests are never saved examples or publication
evidence. The suite denies network access. It tests software behavior, not
scientific answer quality, clinical validity, population eligibility, or human
reviewer agreement.

## Scope and commands

From the repository root, in the focused MVP environment:

```sh
python -m pytest -q tests/mvp
```

The cases cover the headless search → selection → passage inspection →
assessment → export workflow; Unicode code-point anchors; deterministic empty
retrieval; request idempotency; workspace capability isolation; persisted
assessments; explicit supersession and stale revision rejection; changed-source
invalidation; judgment requirements; CSV formula escaping; versioned JSON;
UI-independent imports; and unchanged historical file bindings.

The provider gates also cover exact query/date/cap preservation; count versus
fetched membership; fetch reordering; identifier-based duplicates and conflicting
reports; missing abstracts; malformed XML and entity declarations; bounded HTTP
errors/timeouts/retries; shared rate limits and `Retry-After`; oversized responses;
redirect and arbitrary-URL rejection; and permitted full-text versus abstract
fallback. Full-text identity checks use the article's own PMID/DOI/PMCID metadata,
not references. Tests check that a UTF-8 BOM survives byte retention and hashing.

On 19 October 2026, the focused MVP environment produced **107 passed** for
`tests/mvp`, including **60 independent acceptance cases** in
`test_acceptance.py`. The other cases exercise adapter details, storage
concurrency, stale request replay, and rollback at workspace size limits.

The UI smoke uses Streamlit `AppTest` against the actual three screens and the
real, rights-checked saved example. It searches, selects a paper, prepares the
source, searches passages, saves a note, and exposes both downloads. Ordinary
reruns and screen changes leave the counted provider operations at **one search
and one preparation**, and retain the committed assessment. A rejected edit and
a revision made stale by a simulated second tab preserve the user's draft and
assessment history. This is a software smoke, not a human usability pilot. In an
environment without Streamlit this one test explicitly skips; run it in the
focused MVP environment to obtain UI coverage.

## Existing behavior and historical preservation

The initial focused legacy run passed 409 cases; its sandbox could not bind sockets for 22 old workbench HTTP cases. The subsequent clean-snapshot regression used the unchanged original engine environment with scoped permission for loopback tests, resolving that execution restriction:

```sh
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /Users/hunt/Desktop/lit-rev-engine/.venv/bin/python -m pytest -q
```

Result: **2,053 passed, 2 skipped, 31 subtests passed in 150.34 seconds**, exit 0. The two skips were the Streamlit smoke (Streamlit is deliberately absent from the original installation) and the pre-existing retained-pip-wheel test with no download fallback. Five existing PyMuPDF/SWIG deprecation warnings were reported. The snapshot was `git archive` of baseline `a506ae05fc19c21a1d80beabc26bfc831582441d` plus 24 explicitly allowed MVP code/test/fixture files. It excluded `.env`, unrelated untracked experiments and private review data.

The later UI citation fix and configuration tests were then checked in the separate CPU-only MVP environment: **107 passed in 2.83 seconds**, including actual Streamlit AppTest and the new citation regression. The regression was independently shown to fail both original UI mappings when those old mappings were restored only in memory: a later search with changed metadata for the same PMID must not alter the citation attached to an earlier preparation/run. Current passage cards, source context and CSV remain bound to the original search. The existing engine environment was not upgraded or modified.

All bindings in the existing confirmation, development, and Kaggle v2 manifests
were independently rehashed: **75/75**, **72/72**, and **35/35**, respectively.
The new product contract is separate from complete PubMed capture, formal review
screening, and the receipt-bound Qwen workbench. None of these historical results
is a validation of the new MVP's scientific usefulness.

## Actual browser and headless checks

A local Streamlit server on `127.0.0.1:8502` was exercised through the in-app browser with a separate temporary workspace directory and the real saved example. The browser completed discovery → selection → XML preparation → five-passage search → exact source navigation → synthetic assessment save → explicit revision → CSV and JSON downloads. Source navigation changed the highlighted canonical passage; there were no invented page numbers or generated answers.

The downloaded CSV was read back and checked: five rows, PMID 42051515, exact source references, unreviewed passage decisions and an explicitly synthetic uncertain bundle judgment. The downloaded JSON was read back: one search, one preparation, one passage run and two immutable synthetic assessment revisions with the correct supersession link. All five quotations matched their canonical half-open block offsets; neither capability token nor API key appeared in the audit export. These are temporary software-test records, not a human pilot or scientific assessment.

The headless command also completed with a fresh temporary store:

```sh
/private/tmp/lre-mvp-venv/bin/python scripts/mvp_smoke.py \
  --output /private/tmp/lre-mvp-smoke-final --save-example-judgment
```

It reported one real saved source, five passages, a clearly synthetic test judgment, `streamlit_imported: false` and `paid_inference_calls: 0`. Exports used a new output directory. The focused environment's `pip check` found no broken requirements. Only the CPU-only group was installed in this separate environment; no model weights were downloaded.

## Portfolio identity and evidence layout — 20 October 2026

This presentation-only cycle inspected the actual portfolio repository at
`64f04ed5ff3186e6340fc381e95a60ea6830bc6a` before implementing the theme. The
[theme guide](mvp_theme.md) records source paths, portable tokens and migration
instructions. The portfolio checkout remained clean and was not redeployed.

The focused offline MVP suite passed **110 tests** (107 existing plus three
presentation regressions). New checks exercise actual sibling columns for
passages/judgments, source context after both columns and before exports, source
selection without provider reruns, escaped Unicode quotations, and portable
palette/native-theme agreement. Existing assessment save/revise/stale-draft tests
continue to pass. All **182** historical manifest bindings still match.

Browser checks used a separate temporary saved-example workspace on loopback
port 8502. At a 1440px viewport, both panel headings had identical vertical
positions and the source inspector spanned the frame below them. At 390px the
panels stacked in reading order, with 24px side padding and no main/document
horizontal overflow. The lower inspector retained its exact highlighted text,
citation, source hash and license. The selected-passage link navigated to the
lower inspector. Native keyboard radio navigation and a visible 2px olive focus
outline were exercised. Computed styles confirmed the paper background, Arial
reading text and neutral alert backgrounds/text. The native blue alert interior
found during browser testing was corrected in the adapter.

Olive hover selectors and reduced-motion rules were reviewed in CSS; this cycle
did not emulate an operating-system reduced-motion setting or perform an
independent accessibility audit. No engine/model/provider behavior was changed,
no live PubMed or inference requests were made, and no human relevance pilot was
run. Local operation remains the supported MVP mode; no hosted deployment was created.

A separate UI follow-up was identified: an edited research-question widget can
revert to the sample after navigating away and back because Streamlit cleans up
hidden widget state. AppTest reproduced this in both the preserved pre-theme UI
and the current UI. It is not caused by this layout change; a later draft-state
fix should use durable non-widget keys and cover the query/question fields.

The subsequent passage-alignment revision passed **111 tests**. Each passage and
its decision/notes now share a native row within one assessment form, and the
rule below the judgment heading is removed. Browser measurements at 1440px
confirmed **0px vertical difference for all five matching passage labels**. At
390px, each passage was followed by its own judgment before the next pair, with
no horizontal overflow. Browser and AppTest checks confirmed that Inspect source
retains unsaved notes without saving an assessment; existing save/revise checks
continue to pass. No engine or model behavior changed.

A workflow-navigation fix then passed **114 tests**. Three new AppTest cases
cover sidebar and Continue transitions, post-render reset placement, preserved
workspace/history, and no reset on ordinary reruns or assessment actions. Actual
browser checks followed the source-context link, returned to Prepare sources,
and continued back to Evidence and export twice: each return cleared the stale
fragment and left the main container at **scrollTop 0**. Explicit source-context
links still reached `#verifiable-source-context` at a nonzero scroll position.
No page reload or workspace recreation is used by the fix.

## Bounded live acquisition

Normal tests deny network and use mocked providers. Separately, constructing the real example used **one Europe PMC metadata search and one permitted full-text XML fetch** on 19 October 2026. The recorded search reported nine matches and returned two metadata records; the one CC BY article was retained and the CC BY-NC candidate was excluded by policy. The unchanged XML is 119,491 bytes with SHA-256 `5995273b1ec0f90910375b24ace3856f4a7bdf974e0fcaca68e9d4f00f336404`. Its own PMID, PMCID and DOI and its CC BY license were checked. Actual times, attribution, transformations and selection limits are in [the fixture manifest](../tests/fixtures/mvp/manifest.json) and [README](../tests/fixtures/mvp/README.md).

**Live PubMed search and a live PubMed-to-Europe-PMC end-to-end run are NOT_RUN.** The server environment has no configured NCBI contact email. Implemented ESearch/EFetch behavior passed mocked query, cap, date, ordering, identity, retry and failure cases. That is not a current-provider availability claim.

## Evidence status

- **IMPLEMENTED:** independent acceptance cases listed above.
- **TESTED:** the current 114 offline MVP cases, the Streamlit smoke, historical
  file bindings, the earlier broad clean-snapshot regression and actual browser
  checks recorded above.
- **NOT_RUN:** live PubMed end-to-end acceptance, new model inference,
  human pilot, independent scientific verification, comparative accuracy, and
  hosted deployment/security assessment.
- **PROPOSED:** a later usefulness pilot may collect explicit user feedback with
  a fixed protocol and appropriate publication evidence. No such pilot was run.

Any bounded live smoke is opt-in and must be reported separately from the normal
offline suite. Passing mocked transport cases cannot establish current provider
availability, rights for a different source, or comprehensive discovery.
