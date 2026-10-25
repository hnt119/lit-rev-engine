# Combined Track A source beta.2 — validation

This record distinguishes execution on the combined application from earlier branch-only results. The generated RELEASE.json identifies the exact source commit for a downloadable ZIP; its complete MANIFEST.json binds application files, dependency lock/specifications, the pinned retrieval-pack manifests and notices. The release-time public validation attachment will additionally record final merged SHA, archive hashes and post-merge extracted-package verification. Never substitute either earlier branch-specific beta.2 archive or its checksums.

## Integration and compatibility

Published beta.1 source is `105d98f87ced3e415f77d36305dba7244fc3cf7f`. Settings/AI documentation head is `1e87a6ea41f9b41c0a64f41d49cb1363b9774393`, with its prior artifact source `d2ae854f9626ac2a3f7f38cbcd358d5519cdd562`. Hybrid retrieval head is `82dc6794eed288273723262c663f401890fda4b4`. Both share `db4735b11b7b588f740aaf1de38d9732aa15df72`; settings and AI already belong to that shared history and were not replayed. Their post-base changed-file sets are disjoint. Existing main `a506ae05fc19c21a1d80beabc26bfc831582441d` is an ancestor. Clean merge `170046b02f321d27ff589419a75815cd8d7f0bdb` combines the accepted branches with no conflict resolutions or replacement of shared files.

Core lexical behavior, original block/span profiles, source preparations/hashes/locators, manual draft/inspection/support/submission rules, map artifacts, old receipts and frozen Qwen4B experiments remain separate from new versioned hybrid runs. Track B is excluded. Models and research state are external, optional and never in the source ZIP.

## Combined acceptance status

The following results were executed on the combined code at 170046b and the clean f98efac source candidate (documentation/source-package-only descendant). The eventual final main merge must have the accepted tree, and its separate release validation attachment records final-commit rebuild/extracted/download observations. Earlier branch counts are historical and are not summed into these results.

| Execution | Status |
| --- | --- |
| Combined frontend tests | 181 passed, zero failures/skips |
| Combined production build, TypeScript, OpenAPI/client regeneration | Passed; generated files byte-match tracked contracts |
| Combined core / HTTP tests | 736 passed, 13 optional Streamlit skips / 385 passed, zero skips; 29.40 s / 472.84 s |
| Launcher/source-distribution and desktop boundary unit checks | 128 passed, zero skips / 4 passed |
| Legacy ledger/CLI/frozen compatibility | 1,881 passed, one optional retained-wheel skip, 31 subtests passed; 140.17 s after the documented test-harness correction |
| Real Qwen encoder/reranker, CPU and Apple MPS | Both passed independently using approved cached weights only |
| Real MedCPT query/article/cross encoders, CPU and Apple MPS | Both passed independently using approved cached weights only |
| Combined extracted source setup/manual/configuration/round trip/restart/export/replacement | Passed against exact f98efac source ZIP; base install has no Torch/Transformers and setup downloads no model weights |
| Actual isolated Chrome | Nine settings/session/key-isolation checks; six manual round-trip checks plus reopening verification passed |
| Actual scoped hybrid HTTP workflow | Both CPU profiles passed on an explicit retained public abstract: index, passage/cell retrieval, exact inspection/return, wrong-paper rejection, history/replay/export and disposable pack removal |
| Clean source build / independent audit | f98efac candidate rebuilt byte-for-byte; all 253 files/manifest/source binding, 30 public-source attributions, MIT/notices/private exclusions passed |
| Final merged source and public-download verification | Release-time results belong in the separate SHA-bound VALIDATION.md release attachment; this pre-merge document does not pre-claim them |
| Real local/OpenAI/DeepSeek generation; actual planning/proposals | NOT_RUN; normal adapter checks use mocks |
| Live PubMed/Europe PMC/Crossref retrieval or connection tests | NOT_RUN |
| New BGE embeddings/map fit | NOT_RUN; saved map reused and mock vectors distinguished |
| Human-gold relevance, independent research review, systematic-review completion | NOT_RUN |

## Actual local retrieval, scope and limits

Each standalone check loaded the exact pinned local component files, encoded one synthetic query and two documents and reranked two pairs. Versions were Torch 2.12.0, Transformers 5.12.0 and Tokenizers 0.22.2; float32/eager and sequential component loading remained fixed. Backend/device selection was explicit, with no fallback.

| Pack / device | Whole check seconds | Whole-process peak RSS bytes |
| --- | ---: | ---: |
| Qwen / CPU | 13.935 | 4,008,591,360 |
| Qwen / Apple MPS | 15.407 | 2,315,436,032 |
| MedCPT / CPU | 6.547 | 1,255,686,144 |
| MedCPT / Apple MPS | 6.345 | 1,319,780,352 |

These are single observations on this arm64 Mac, not unique model memory, GPU allocation, warmed throughput or another platform's qualification. All 46 files in the two shared approved model-pack directories retained identical contents, inode, modification time, mode and link count; that inventory excludes cache-root state/indexes. All test writes/removals were in disposable copies. New model downloads and network attempts were zero.

The real application case prepared three public reports (PMIDs 42051515, 42683105 and 42196995), then restricted the board/cell index **before ranking** to PMID 42051515's explicitly retained 2,271-character abstract, producing three windows. Qwen indexing/passage/cell operations took 17.778/18.260/29.077 seconds; MedCPT took 10.091/6.272/5.909 seconds. Actual encoder and reranker execution was verified. Matching exact quotation inspection/return, wrong-paper denial, unchanged manual drafts/judgments and historical replay/export passed before removal. After removing only the disposable model copy, saved-run/source inspection/export remained readable; new requests failed visibly without lexical fallback. Replay after removal is not claimed as an actual check.

An earlier Qwen CPU attempt on a 33,942-character full text did **not** complete within the QA harness's explicit 180-second deadline. Only its owned test subprocess was stopped; no completed index or fallback was published. This was not the product's 600-second cooperative runtime bound, and the abstract successes are not relabeled as full-text successes. Long-source/30-paper neural usability and sustained latency are unverified. There is no promise of interactive latency from these runtime checks.

Separate offline software subsets passed 57 native/core/pack/downloader checks (including all 17 native tensor/policy tests), 40 hybrid HTTP checks and one controlled concurrent-interleaving check. Another independent model-free native subset had eight explicit Torch-unavailable skips; the synthetic-tensor tests were separately run with the pinned runtime, without weights. These overlapping subsets are not added to whole-suite totals. Failure, wrong/ambiguous or exact-but-non-supporting references, abstract/empty context, stale inputs, concurrent settings/index/query/deletion, missing/corrupt pack/profile/index mismatch and no-fallback behavior remain software checks, distinct from scientific quality.

## Extracted application and failure disclosure

An initial abstract-case QA client expected full source blocks in the deliberately small summary API projection and failed before model work; the client was corrected to use the existing detailed source projection. A hybrid HTTP mock-suite collection initially used the neural-only environment without FastAPI; the same unchanged suite passed 40 cases in the API environment. Neither required application changes.

Fresh setup used Python 3.12.7, Node 24.19.0 and pnpm 10.20.0 in a new application environment/data directory. The default setup omitted Torch/Transformers and stripped deliberately inherited hosted/AI settings. Existing package caches were reused; no model weights or live literature were downloaded. The source workflow checker made 65 requests for the public 30-paper case, three-by-three manual board, ten explicitly submitted software-QA revisions, seven exact source inspections and thirteen privacy denials. The 38-request round-trip checker covered scoped candidates, wrong-paper/stale/empty responses and conflicts. Both original block-prefix and lexical-span profiles were exercised. Restart/replacement verification retained drafts, sources/map/profile/history and exports; memory-only dummy keys disappeared while non-secret settings survived. Port conflicts failed with an actionable error without disturbing the existing owned instance.

Original environment attempts failed because the model-free QA environment lacked the already-pinned PyMuPDF 1.27.2.3, and some tool invocations could not bind loopback. The pinned dependency was obtained from the existing wheel cache and local bind permission was used for reruns. These attempts are retained, not counted as passes. Existing dependency deprecation warnings remain.

A pre-existing nondeterministic legacy test fixture patched global time.sleep to fail even when CPython's subprocess._wait polled a just-exited child. Its test-only correction permits the exact stdlib wait frame and still rejects every application/direct-test sleep; the network prohibition stays unchanged. Two deterministic regressions and the 182-case focused CLI/schema group passed, including 31 subtests. Product CLI/source code did not change to address this harness race. Earlier 61 environment failures and two remaining race failures remain disclosed. No application security boundary, network allowance or model fallback was introduced to obtain a passing result.

## Scientific and model boundaries

Qwen and MedCPT remain experimental. Native encoder/reranker execution proves the exercised integration, not clinical validity or improved retrieval quality. Earlier controlled development proxies did not demonstrate superiority over common-window BM25; core lexical remains default. Candidate quotations can be exact but non-supporting, and insufficient-context questions may still return candidates. Researchers must inspect and judge support explicitly. MedCPT passage use is an adaptation of its title/abstract task. No old frozen Qwen4B accuracy label transfers to these profiles.

Model selection, installation, indexing, device and retrieval are explicit. Missing/corrupt/incompatible packs/indexes fail visibly without lexical/model/device fallback. Generative assistance remains independently selected, uses memory-only own-key credentials and exact one-run data/cost consent, and cannot auto-submit a cell or mark verification. Real retrieval tests do not imply a real generation test.

## Distribution and preservation

Original code and documentation are MIT. Thirty approved CC BY public article sources retain original attribution, license/permission and transformation metadata. Optional model cards and retained Apache/NCBI notice provenance remain separate, including the pinned MedCPT Cross Encoder's empty upstream LICENSE. No weight mirror is distributed. The source ZIP contains dependency specifications and original code, not Electron/Node/Python/native/vendor packages; the seven notice gaps in the earlier private desktop binary are not source payloads. Public desktop distribution remains blocked separately on notices/SBOM/source obligations, Developer ID signing, notarization and quarantined-device tests.

Setup is required. macOS arm64 is tested; Linux installation is unverified and Windows unsupported. Keep hostname/browser profile stable; clearing or expiring access cookies can lose workspace access. There is no new account recovery, authenticated transfer or automatic migration. Research is stored outside replaceable app files. Force-killed source launchers may leave positively identified child services requiring controlled operator recovery; do not kill arbitrary listeners or delete active locks.

Beta.1/frozen archives keep their original bytes. Original research, unrelated working trees, Track B and the website remain untouched. No cloud generation, live literature-provider call, model download, paid service, Render deployment or public desktop upload is part of this source release.


Independent frozen medical source/anchor audits v1/v2/v3 passed; the v3 audit rejected 18 specified tamper cases and accepted one disclosed runtime-preservation case. These are provenance checks, not new ranking/model tests. The separately exercised integrated ReviewStore provenance-chain/CLI acceptance passed two tests. An additional original-engine CLI/RAG/PDF/vectorstore regression run passed 62 tests using mocks/temporary state. These selected executions overlap parts of broader suites and are not added into a total. Legacy review/retrieval/embedding/RAG/search code and frozen artifacts were byte-unchanged from beta.1.
