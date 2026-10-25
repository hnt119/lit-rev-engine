# Combined Track A source beta.2 — validation

This record distinguishes execution on the combined application from earlier branch-only results. The generated RELEASE.json identifies the exact source commit for a downloadable ZIP; its complete MANIFEST.json binds application files, dependency lock/specifications, the pinned retrieval-pack manifests and notices. The public release validation attachment additionally records final merged SHA, archive hashes and post-merge extracted-package verification. Never substitute either earlier branch-specific beta.2 archive or its checksums.

## Integration and compatibility

Published beta.1 source is `105d98f87ced3e415f77d36305dba7244fc3cf7f`. Settings/AI documentation head is `1e87a6ea41f9b41c0a64f41d49cb1363b9774393`, with its prior artifact source `d2ae854f9626ac2a3f7f38cbcd358d5519cdd562`. Hybrid retrieval head is `82dc6794eed288273723262c663f401890fda4b4`. Both share `db4735b11b7b588f740aaf1de38d9732aa15df72`; settings and AI already belong to that shared history and were not replayed. Their post-base changed-file sets are disjoint. Existing main `a506ae05fc19c21a1d80beabc26bfc831582441d` is an ancestor. Clean merge `170046b02f321d27ff589419a75815cd8d7f0bdb` combines the accepted branches with no conflict resolutions or replacement of shared files.

Core lexical behavior, original block/span profiles, source preparations/hashes/locators, manual draft/inspection/support/submission rules, map artifacts, old receipts and frozen Qwen4B experiments remain separate from new versioned hybrid runs. Track B is excluded. Models and research state are external, optional and never in the source ZIP.

## Combined acceptance status

Combined software, real cached-model and extracted-package checks are recorded here before publication. A pending item is not a pass. Earlier branch counts are historical and are not summed into these results.

| Execution | Status |
| --- | --- |
| Combined frontend tests | 181 passed, zero failures/skips |
| Combined production build, TypeScript, OpenAPI/client regeneration | Passed; generated files byte-match tracked contracts |
| Core/API/ledger/frozen/launcher/source tests | RUNNING; final results required before merge/publication |
| Real Qwen encoder/reranker, CPU and Apple MPS | RUNNING using approved local caches only |
| Real MedCPT query/article/cross encoders, CPU and Apple MPS | RUNNING using approved local caches only |
| Combined extracted source setup/manual/configuration/retrieval/round trip/restart/export | PENDING exact candidate artifact |
| Final merged source deterministic rebuild, independent payload audit, extracted verification | PENDING merge and final archive |
| Real local/OpenAI/DeepSeek generation; actual planning/proposals | NOT_RUN; normal adapter checks use mocks |
| Live PubMed/Europe PMC/Crossref retrieval or connection tests | NOT_RUN |
| New BGE embeddings/map fit | NOT_RUN; saved map reused and mock vectors distinguished |
| Human-gold relevance, independent research review, systematic-review completion | NOT_RUN |

## Scientific and model boundaries

Qwen and MedCPT remain experimental. Native encoder/reranker execution proves the exercised integration, not clinical validity or improved retrieval quality. Earlier controlled development proxies did not demonstrate superiority over common-window BM25; core lexical remains default. Candidate quotations can be exact but non-supporting, and insufficient-context questions may still return candidates. Researchers must inspect and judge support explicitly. MedCPT passage use is an adaptation of its title/abstract task. No old frozen Qwen4B accuracy label transfers to these profiles.

Model selection, installation, indexing, device and retrieval are explicit. Missing/corrupt/incompatible packs/indexes fail visibly without lexical/model/device fallback. Generative assistance remains independently selected, uses memory-only own-key credentials and exact one-run data/cost consent, and cannot auto-submit a cell or mark verification. Real retrieval tests do not imply a real generation test.

## Distribution and preservation

Original code and documentation are MIT. Thirty approved CC BY public article sources retain original attribution, license/permission and transformation metadata. Optional model cards and retained Apache/NCBI notice provenance remain separate, including the pinned MedCPT Cross Encoder's empty upstream LICENSE. No weight mirror is distributed. The source ZIP contains dependency specifications and original code, not Electron/Node/Python/native/vendor packages; the seven notice gaps in the earlier private desktop binary are not source payloads. Public desktop distribution remains blocked separately on notices/SBOM/source obligations, Developer ID signing, notarization and quarantined-device tests.

Setup is required. macOS arm64 is tested; Linux installation is unverified and Windows unsupported. Keep hostname/browser profile stable; clearing or expiring access cookies can lose workspace access. There is no new account recovery, authenticated transfer or automatic migration. Research is stored outside replaceable app files. Force-killed source launchers may leave positively identified child services requiring controlled operator recovery; do not kill arbitrary listeners or delete active locks.

Beta.1/frozen archives keep their original bytes. Original research, unrelated working trees, Track B and the website remain untouched. No cloud generation, live literature-provider call, model download, paid service, Render deployment or public desktop upload is part of this source release.
