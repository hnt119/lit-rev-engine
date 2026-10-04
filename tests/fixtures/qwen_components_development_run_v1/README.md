# First actual component development result

This archive preserves the first numeric grade of private Kaggle saved version **355187018 (version 3)**, submitted at **2026-10-04 14:16:50 UTC** from software commit `85b5df4`. The original [prospective development freeze](../../../docs/qwen-components-development-freeze-v1.json) and [separately pinned bootstrap deployment](../qwen_components_development_bootstrap_v2/deployment.json) remain unchanged. The [earlier ensurepip setup failure](../qwen_components_development_setup_v1/README.md) remains preserved separately.

The first local [result.json](result.json) is an exact **532,051-byte** copy, SHA-256 `fb1697b165c9a3d9323193a0bb233208b65363f24a1ba635afd063567c6a5043`. It **passes all eleven development gates**. These are software retrieval results from eight fixed questions over two published articles, rather than clinical validation or human-pilot acceptance. Independent semantic review against the original article XML is complete; the separate frozen confirmation stage and protocol-defined human pilot remain necessary.

| Method | Mean own-support coverage over six positives | Complete positives |
| --- | ---: | ---: |
| Component Qwen candidate | 100% | 6/6 |
| Whole-query Qwen | 86.1111% | 4/6 |
| Whole-query lexical | 44.4444% | 1/6 |
| Component lexical | 55.5556% | 2/6 |

No positive loses support between its candidate pool and displayed selection. The component-Qwen candidate output for both source-scoped null questions still returns five candidates with zero annotated context coverage and zero other-article candidates. Both lexical comparators cover one of two context anchors per null question. Answerability and evidence completeness remain unassessed by the engine; people must review its candidates.

The saved UI reports **1,108.3 seconds**. The unchanged bootstrap audit records **1,085.841999744 seconds**, including **10.548421309 seconds** of setup; the original numeric worker records **1,063.704828704 seconds**. These clocks have different boundaries. The run used Tesla T4 device zero, CUDA 12.8, Torch 2.11.0+cu128 and the original four pinned Hugging Face packages, producing 126 source embeddings, 27 query embeddings and 549 distinct rerank scores. Its maximum input was 1,138 tokens, with no truncation and zero paid inference calls. Runtime and image links are recorded provenance claims, not cryptographic execution attestation. The manifest labels the saved-page container link separately from the editor's selected environment setting.

`artifacts.tar.xz` is a deterministic regular-file archive of the eleven downloaded outputs plus the exact original job, local preparation and validation receipt: fourteen flat members, **2,618,364 compressed bytes**, SHA-256 `ff3e3ca5b8f54e5256066ae8db32e3c9986793dc89a2121cdbc9d07a3ed6d40d`. The original log and imported unexecuted notebook source are separate exact files. [manifest.json](manifest.json) binds every original file. No ledger, gold source files, credentials, model weights, downloaded pip wheel, cache, screenshots or browser authentication are included.

The job passages derive from the two [licensed original development sources](../qwen_components_development_sources/README.md): John T. Murchison et al., [PLOS ONE, DOI 10.1371/journal.pone.0266799](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0266799), and Dilan Giguruwa Gamage et al., [PLOS Medicine, DOI 10.1371/journal.pmed.1002997](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1002997). Both grant [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); the untouched source XML and source manifest retain their full attribution, copyright and license notices. Canonical passages preserve within-block text with whitespace and table normalization. Project/document identifiers are synthetic evaluation identifiers.

From an installed repository checkout, run:

```sh
.venv/bin/python tests/fixtures/qwen_components_development_run_v1/verify.py
```

The checker reads bounded archive members without extraction, checks original digests and all six bootstrap stages, validates complete model matrices/runtime/helper bindings, replays the candidate and three comparators through frozen pure functions, and reconstructs the original grade from the frozen development sources/truth. It opens no database and writes no grade or receipt. An exit code of zero means preserved evidence was verified; the printed `quality_status` reports the actual grade, including a failure if that is what an archive records. The original ledger-readonly check is preserved evidence and cannot be repeated without the deliberately omitted ledger.
