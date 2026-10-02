# Independent synthetic review fixtures

These records are invented acceptance data; identifiers do not assert that a real paper exists.

`medical_records.json` has eight database occurrences representing six distinct reports. The renal report appears twice with normalized matching DOI/PMID but conflicting metadata. The two hip reports share all title/author/year fields yet have different DOI values. Two complete no-ID oxygen entries match after whitespace/case normalization; the oxygen entry lacking an author must remain distinct, as must the entry with a PMID.

`medical_followup.json` adds two occurrences: one PMID duplicate of the renal report and one new remote-follow-up report. After both runs the independent ground truth is ten occurrences, three duplicates, and seven unique reports. The first populated title/authors/year/abstract for the renal report must survive conflicting later metadata, with all versions retained in occurrences.

`medical_exports.ris` and `medical_exports.xml` describe equivalent title/year/abstract concepts while deliberately differing in source identifier authority. RIS maps numeric AN to PMID only for explicit PubMed metadata; its local-archive AN is a source ID. XML supplies both PMIDs explicitly. XML nested title/abstract formatting, a collective author, an external DTD reference, and MedlineDate exercise offline parsing.

## Screening fixture ground truth

`screening_records.json` contains 13 distinct reports. Evaluation imports r01–r07 and a duplicate r01 from PubMed (8 occurrences; 7 new; 1 duplicate), then r08–r13 and a duplicate r09 from Embase (7 occurrences; 6 new; 1 duplicate), plus an empty search. Thus totals are 15 identified, 2 duplicates, and 13 unique reports. Reported source totals are preserved separately.

The independent final scenario assigns: r01 pending title/abstract; r02 excluded; r03 uncertain; r04 conflict; r05 included but not requested; r06 requested and awaiting retrieval; r07 not retrieved; r08 retrieved and awaiting assessment; r09 full-text included; r10 full-text excluded; r11 full-text uncertain; r12 full-text conflict; r13 title/abstract excluded with agreeing reviewers and a revised reason. All r05–r12 have title/abstract inclusion.

Hand-computed flow counts:

- Title/abstract: 1 awaiting screening; 12 screened = 2 excluded + 8 included for full text + 2 unresolved.
- Retrieval: 8 title/abstract inclusions = 1 awaiting request + 7 sought; 7 sought = 5 retrieved + 1 not retrieved + 1 awaiting retrieval.
- Full text: 5 retrieved = 1 awaiting assessment + 4 assessed; 4 assessed = 1 included + 1 excluded + 2 unresolved.
- Included studies are unavailable/null because no study linkage exists.

Historical exclusion reasons remain in decision history; the exclusions export contains only current active reasons. Formula-like cells are synthetic input for CSV safety evaluation and their original strings must survive in JSON.
