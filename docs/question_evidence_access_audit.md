# Access and reuse audit — question-to-evidence checkpoint

Inspected source: `265b291aaf0a2a60ac9aa89862dc531a78207874`, a clean reviewed descendant of source beta.4 `d52e5e35c80ef435abaec0c0a6f4ed236cba9356`. Its changes since beta.4 are `README.md` and `config/public_release.json`; the implementation inspected here is unchanged. This is a source audit, not a fresh browser, provider, model, institutional-access or participant test. Those activities are **NOT_RUN** in this audit. No original research database, Track B data, browser state or credentials were read.

This document records the **pre-implementation baseline**. A/B additions may close the gaps below; use [the workbench guide](question_evidence_workbench.md) for the implemented checkpoint and its actual validation status. The PDF attachment finding is a separate access boundary.

## What can be reused

| Area | Implemented boundary | Reuse and limit |
| --- | --- | --- |
| Citation intake | `src/mvp/import_contracts.py`, `import_parsing.py`, `collections.py`; `src/web_api/collection_routes.py`; `apps/web/components/import-papers.tsx` | CSV, RIS and explicit DOI/PMID intake; preview, manual repair, deliberate metadata resolution, duplicate decisions and reviewed collection commit. Up to 500 rows / 5 MiB per import; pagination is separate from the 30-paper prepared subset. |
| Import provenance | `src/mvp/adapters/collection_storage.py`, `collection_contracts.py`, `collection_exports.py` | Protected original bytes/hash, parser/mapping versions, row/source-key origins, metadata versions, resolution receipts and uncommitted accounting. Bibliographic projections omit notes and attachment paths. Raw import bytes can still contain private columns and remain private; an ordinary export excludes them. |
| Search planning | `search_plan_contracts.py`, `search_plan_compiler.py`, `search_plans.py`; `components/search-planner.tsx` | Typed concepts, requirement/preference/deferred distinctions, explicit Boolean relationships, variants, exact manual query, approval and versioned receipts. Improve this interface instead of introducing another planner. |
| Query diagnostics | `src/mvp/adapters/search_diagnostics.py` | At most three approved seeds, one main request and one seed-membership request, five sample PMIDs, 12-second maximum. Query membership, displayed-preview recovery, provider error and zero count are distinct. Diagnostics create no search capture. |
| Search exports | `planning_exports.py`, `collection_exports.py` | Persisted planning and execution provenance is already included in audit exports. A concise, readable strategy document is an additional projection, not a new search engine. |
| Prepared evidence | `src/mvp/service.py`, `adapters/europe_pmc.py`, collection/preparation job modules | Exact-identity Europe PMC JATS acquisition with conservative CC BY/CC0 gate; original UTF-8 XML/hash, canonical blocks/hash, parser, source identifiers and attribution. Source outcomes explicitly distinguish usable full text, abstract, missing text and failures. |
| Comparison | `board_contracts.py`, `evidence_board.py`, `adapters/board_storage.py`; `components/compare.tsx` | Same-page excerpt-first editing, exact paper/field/source bindings, candidate versus inspection versus judgment, drafts, explicit submissions/revisions, historical views, CAS and CSV/JSON exports. Five fields fit the existing six-field limit. |
| Paper access | `components/ui.tsx`, `lib/helpers.ts`; existing desktop external-link handler | Deliberate DOI/PubMed and approved source links. The browser UI uses a new tab; the desktop shell has its existing system-browser policy. No institutional SSO/cookie collection. A configurable library resolver or arbitrary publisher-link UI is not established by this source audit. |

## Confirmed gap: PDF attachment is legacy-only

The current web MVP does **not** support uploading a searchable PDF onto an existing report end-to-end.

- The web file input accepts CSV/RIS only (`components/import-papers.tsx`). Its upload route permits exactly `csv`, `ris` and `identifiers` (`collection_routes.py`). A Zotero CSV is a bibliography, not an attachment bundle; private attachment columns are deliberately excluded and never opened.
- The modern source contract has `retained_content_utf8`, not a binary attachment store. `service._validated_source` reparses retained full text as `jats_xml`; simply setting a PDF parser label would not create a valid source path.
- A reusable pure PDF parser exists in `src/review/documents.py` and is exposed by legacy `ReviewStore.attach_document` / `review.py attach-source`. It stores immutable bytes, hashes and versioned canonical blocks in the legacy review ledger. PDF locators are extracted page numbers, not layout coordinates. Encrypted, corrupt and textless PDFs are rejected; OCR is unavailable. This is not a modern web upload, permission, preparation or board handoff.
- `tests/test_review_documents.py` and `test_review_documents_acceptance.py` cover that legacy mechanism. Their success must not be described as modern browser attachment coverage.

Do not expose a decorative upload button or route new attachments into a second screening database. Defer implementation until actual pilot access problems justify it. A separate attachment checkpoint would need a bounded, authorized upload; explicit association/identity confirmation; immutable binary/format/parser provenance; a truthful local-use permission record distinct from redistribution licensing; usable-text checks; exact source-version preparation/board binding; and reopen/revision/export tests. Keep original historical bindings. A private subscribed PDF must never acquire a fabricated CC BY label or enter public fixtures.

## Baseline gaps relevant to A and B

1. **Terminology:** current compilation explicitly reports `no_server_mesh_registry`. Approved model/manual terms are not verified MeSH. Show unavailable status until an authoritative entry, version and verification date are actually resolved.
2. **Externally executed strategy:** imported collection commits retain file/row provenance but do not accept an external database/platform/query/date/limits execution record. Add a small typed provenance record only if included in the approved slice; never fabricate a PubMed search or validate another database's syntax.
3. **Scientific dimensions:** current `BoardCellData.value` is a free-text manual value. There is no `DimensionDefinition`, typed attribute revision or saved evidence-view contract. Collection filtering currently searches title/authors. Do not infer scientific attributes by parsing prose, model scores or selection state.
4. **Source versus cloud permission:** current conservative provider reuse status and existing one-run generation disclosures are reusable. They do not model every local-file entitlement. A locally retained source is not automatically authorized for cloud processing. Keep acquisition, local permission, cloud disclosure/consent and human review separate.
5. **View safety:** filtering/sorting/grouping must leave board definitions, retrieval profiles, source manifests, submitted cell revisions and historical receipts intact. Unknowns and suggestions need explicit states; report co-occurrence cannot imply same-cohort linkage.

## Public-fixture and evaluation boundary

Reuse the hash-bound CC BY/CC0 XML and citation metadata in `examples/mvp/offline_microbiome_30_v1/`, retaining its manifest, attribution and curation warnings. It is a saved Europe PMC example, not a complete PubMed capture or a relevance benchmark. No new acquisition is needed for software tests.

Use explicitly synthetic small sources for known wrong-cohort, numeric/negation, Unicode, multi-site, missing-text and conflict traps. They can define mechanical expected behavior; never present synthetic findings as real human gold. For participant tasks, use the same approved original documents in every condition and obtain a real adjudicated reference independently. Candidate document selection, protocol definitions, comparator access, external-provider execution and participant results remain unresolved until actually approved and performed. See [the blank kit](question_evidence_evaluation/README.md).
