# Medical retrieval milestone: coordinator preparation

Status: R10 source acquisition accepted, parallel to study linkage. Coordinator reviewed attribution, metadata, hashes, and the offline checker, and independently verified all three exact publisher snapshots. The optional topic preference has no answer yet; coordinator uses a mixed medical corpus. Existing concurrent neural-network benchmarks are outside this gate and must remain untouched. Three papers make a small software pilot, not a representative medical retrieval benchmark or clinical validation.

## R10 licensed source acquisition ticket

Retrieval owns only `tests/fixtures/medical_sources/` for this ticket. Acquire exact publisher full-article XML for these peer-reviewed research articles, with a source manifest and README. No PDFs/images, participant-level datasets, existing benchmark edits, embedding/index/model initialization, clinical claims, or gold questions yet. Use source URLs exposed by the publisher's XML download link, not an invented mirror. Network access for these three openly licensed public sources is authorized by the research/evaluation task.

| Alias | Publisher article | Published version |
| --- | --- | --- |
| coach | [Chen et al., integrated depression/hypertension care cluster trial](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1004019) | PLOS Medicine, 24 October 2022 |
| whitehall | [Sabia et al., sleep and multimorbidity cohort](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1004109) | PLOS Medicine, 18 October 2022 |
| raptor | [Fanshawe et al., RAPTOR-C19 diagnostic accuracy study](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0329611) | PLOS One, 7 August 2025 |

Coordinator and Retrieval checked the copyright statements and linked license. All three identify [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/). Preserve author/title/source attribution, copyright, license URL, and indicate any transformations. Source files must remain exact downloaded bytes; no XML rewriting or stripping. Freeze SHA-256 and byte length, permanent publisher download URL, final URL scheme/host/path (omit temporary signed query parameters and state the omission), acquisition UTC time, DOI, publication date, source format, and version statement. An acquisition timestamp/checksum pins the downloaded version; it does not establish that no corrections exist. Do not describe it as the latest version without checking publisher update notices.

Validate each file offline: parse supported article XML without entity expansion/network, confirm its own DOI/title/license/publication metadata, and verify size/hash. Reject HTML error pages and cross-article mismatches. Report exact URLs, files, sizes, version caveats, and verification command/results. If publisher XML is unavailable, report the exact limitation and propose an alternative primary source rather than silently changing the corpus. A small standalone fixture verification script is allowed; no operational review/retrieval code in this ticket.

## Next gates, not yet implementation tickets

R11 will define source-anchored quantitative, population, follow-up, negation, multi-report, and no-answer questions only after the frozen source bytes exist. Separate development and held-out questions before retrieval changes. Evaluation independently checks every gold anchor against source bytes and evaluates ranking/support coverage plus no-answer behavior. Gold authorship and a small corpus remain explicit limits.

The source-document/extraction gate must support real source locators without pretending XML paragraphs are PDF page numbers. Retrieval must return stable document/version/block/character anchors and retained source hashes. Medical evaluation runs in temporary indexes, uses no Agnes calls, and cannot modify a user's live collection. Coordinator will freeze the operational retrieval interface and metric acceptance after source/extraction interfaces are accepted.
