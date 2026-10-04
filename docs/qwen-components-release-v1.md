# Component workflow: bounded release audit

Independent evaluation accepted the software release and prepared development bundle on 4 October 2026, before the first component-profile GPU invocation. This audit changes no frozen implementation, tests, original sources or gold. Actual cloud results and subsequent decisions belong in [the separate run record](qwen-components-runs-v1.md).

## Evidence accepted

The coordinator's clean staged checkout passed **1,771 tests and 31 subtests in 153.76 seconds**, with five existing PyMuPDF warnings. Independent focused evaluation had passed 226 new core/import, harness, installer and worker cases, plus the historical Qwen regression checks. The staged checkout excludes unrelated local experiments and `.env`; model and network downloads were disabled. This audit verified that all seventy-two development-freeze file pins match both the working repository and that reviewed checkout. It did not repeat the full test suite or perform a new medical ranking.

The [development freeze](qwen-components-development-freeze-v1.json) is 14,755 bytes, SHA-256 `a70cfd4a4a1526e2e8da72f1b34ef1586ce6be430e9474892cf76a9b45d5ade0`. It preserves the selected contract, profile, fixed gates, critical code/tests, accepted development truth and confirmation bytes selected while the coordinator remained blind. Confirmation QA was not disclosed by this audit.

The first prepared job has trusted payload SHA-256 `4de843130af3727968e1a0f7bfd150c5743fcfb521d820a5c0fe0fd9c3bc3ce2`. Its eight original questions produce twenty-seven whole/component query rows over 126 original own blocks and 126 representations. It uses included sources, a twenty-block candidate pool and five displayed own blocks. The job source/profile/helper bindings, preparation's freeze pin and canonical payload hash match.

The upload zip is 80,534 bytes, SHA-256 `c5ad1ea40db7528ffcdf4b1c98fe936bcac8bbfb9a3a3df51bd64f6e27477a81`. Its exact file set is:

- `job.json`
- `component_core.py`
- `qwen_kaggle_environment.py`
- `qwen_components_kaggle_runner.py`

Every archived byte matches the prepared upload file; all three executable byte/size pins agree with the trusted job. The separate configured notebook has SHA-256 `644d271cf75e90c96d7a4f613b3da1c6438620666c8c8cad2774cae615af5581`, compiles successfully and contains the correct original job digest. Its trusted-hash placeholder is absent; the actual private dataset `BUNDLE` path remains to be supplied. The upload contains no gold support/context annotations, expected-answer fields, review ledger or credential fields. Original passages naturally retain their source text.

The prepared ledger was inspected with SQLite `mode=ro` and `query_only=ON`. Its logical fingerprint matches preparation. No first component result or validation receipt exists at this audit stage, and no GPU-quality grade is claimed. Generated local preparation files remain separate from the published source release; a fresh preparation produces fresh identities and its own job hash.

## Documentation and preservation

Local Markdown links resolve across the README, architecture, model strategy, roadmap, selected contract, environment research, workflow guide, source/software evaluation and current run record. CLI help confirms the documented export/import flags and evaluation grade inputs. The [guide](qwen-components-guide.md) explains the exact four-file bundle, private Kaggle execution, local result import and human-review boundary. The [run record](qwen-components-runs-v1.md) provides the prospective preparation command. Documentation distinguishes software acceptance from actual environment compatibility, GPU quality and human-pilot readiness.

All thirty-five [historical v2 input pins](qwen-kaggle-freeze-v2.json) remain byte-exact. The independent portable [first-run verifier](../tests/fixtures/qwen_kaggle_run_v2/README.md) again verifies the original result as **failed**: 80.5556% own-support coverage, four of six complete positives, 395.076408088 measured batch seconds and zero paid calls. A successful archive-verification exit means the recorded failure was reproduced; it does not change that acceptance decision. The supplied unchanged log retains its 5,412-byte size and SHA-256 `51c04983cf550747ece5125daadd4a2451aed3e297e37c15a050798031590aa8`.

The initial forty-four staged files are entirely within the coordinator's explicit owned-file whitelist. No `.env`, local generated data, SQLite ledger/WAL/SHM or unrelated experiment path is staged. The saved foreign-file hashes match, and the unchanged 884-byte foreign README section is present in the working file but excluded from the staged README. Root-owned documentation updates and this unpinned release report still require the coordinator's final explicit restage; the coordinator alone publishes the commit.

## Current limit and next acceptance step

No release defect was found in this bounded audit. At the observed stage, cloud submission awaits manual Mac unlock; no new dataset upload, component GPU invocation or grading has occurred. The audit uses local files and supplied coordinator execution evidence, without UI access or another model call. It does not establish real Kaggle dependency compatibility, memory fit, runtime or retrieval quality.

The next acceptance step is one finite saved development GPU run with these unchanged bytes, preservation and independent review of its first result, then factual method selection before confirmation QA is opened. Confirmation must satisfy the unchanged 85% support floor, four-of-six complete-positive floor, nonregression against all three matched comparisons, exact scope/anchors/read-only replay, twenty/five budgets, complete token/pair bounds, zero paid calls and the 1,800-second batch ceiling. Human-pilot readiness remains pending that accepted fresh evidence.
