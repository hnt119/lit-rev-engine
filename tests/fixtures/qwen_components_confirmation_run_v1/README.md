# First frozen component confirmation run

This archive preserves the first saved confirmation execution, private Kaggle version **4**, script version **355309491**, named **Components confirmation v1 pinned bootstrap**. The original method was selected unchanged after development and before confirmation questions were read or ranked. The [confirmation freeze](../../../docs/qwen-components-confirmation-freeze-v1.json), [method selection](../../../docs/qwen-components-method-selection-v1.json) and [prospective transport](../qwen_components_confirmation_bootstrap_v1/deployment.json) remain unchanged.

The first local [result.json](result.json) is an exact **565,658-byte** copy, SHA-256 `8f35e67859df014f2cf7cdf600faaa6c965568ddc5fe20fc703967ae62c2944d`. It **passes all eleven frozen confirmation gates**. Independent source and numeric review accepted the original result. These eight fixed questions over two articles establish retrieval evidence for bounded human assistance; a real team still needs its protocol-defined pilot. The confirmation result was not used to tune the method.

| Method | Mean own-support coverage | Complete positives |
| --- | ---: | ---: |
| Component Qwen | 94.4444% | 5/6 |
| Whole-question Qwen | 86.1111% | 4/6 |
| Whole-question lexical | 61.1111% | 2/6 |
| Component lexical | 77.7778% | 3/6 |

The remaining miss is `components-confirm-thyroid-01`: the clinical study period **January 2021 to January 2022**, at `xml:/article[1]/body[1]/sec[2]/sec[1]/p[1]` (zero-based candidate block index 10), was available at study-period component hybrid rank 16 and lexical rank 14 but omitted from both pools of 20. Its global component pool and displayed candidates each cover two of three required anchors. The selected July 2020 passage at `sec[2]/sec[2]/p[1]` describes reader training. This is a candidate allocation omission; no positive loses support between its available pool and displayed selection. It remains a limitation of the unchanged method.

Both null questions return five candidates and one of two annotated context anchors. The engine does not assess answerability or abstention. Component and whole-question Qwen display zero foreign-source candidates. Each lexical comparator displays one COPCOV abstract candidate for thyroid-01, with no source support credit. People must inspect the returned passages and original article.

Runtime and quality are separate records. The saved UI reports **983.1 seconds**; the bootstrap reports **963.5613 seconds**, including **11.6660 seconds** of setup; the worker reports **942.7591 seconds**. It recorded Tesla T4 device 0 of two, CUDA 12.8, Torch 2.11.0+cu128, the four pinned Hugging Face packages, 100 document vectors, 27 query vectors and 549 distinct rerank pairs. The maximum input was 1,607 tokens, no truncation occurred, peak allocated VRAM was 8,237,180,928 bytes, and paid inference calls were zero. These clocks have different boundaries.

The exact submission timestamp was not observed; the first observed running time was **2026-10-05T01:27:52Z**. A preceding rejected Save was a UI concurrency event with no saved version, ranking or grade. The editor selected “Pin to original environment (2026-10-03)”, while the saved Logs page linked “Latest Container Image” to `gcr.io/kaggle-gpu-images/python@sha256:2757e0c7d1e0a9cb43da657b97e223c321a98f5014bdf64f44f2f6b083ad2b2f`. That link is observed UI provenance, not cryptographic execution attestation. [run.log](run.log) and [imported-draft.ipynb](imported-draft.ipynb) preserve the exact original log and authoritative persisted notebook; its one code cell equals the pinned 4,619-byte prospective launch script.

[artifacts.tar.xz](artifacts.tar.xz) contains fourteen byte-exact, flat regular files: the eleven downloaded outputs, original job, original preparation receipt and original validation receipt. It is a deterministic USTAR archive with sorted members, zero owner/time metadata and mode 0644, compressed with XZ/LZMA2. [manifest.json](manifest.json) pins every member, plain evidence file, original freeze, selection and transport. It identifies original software base `85b5df4` and published transport commit `74d8157756a7ee5a74b0e6af117e05a556b99e81`; additions are separately pinned. No ledger, raw gold fixture, weights, wheel, cache, credentials, account state or screenshots are included.

The passages derive from two CC BY 4.0 articles: Alfuraih et al., [thyroid TI-RADS agreement](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0312121), and Schilling et al. and the COPCOV Collaborative Group, [COVID-19 prophylaxis trial](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1004428). Canonical text normalizes whitespace and tables. Complete author, copyright, license and original-byte provenance remain in the [confirmation source archive](../qwen_components_confirmation_sources/README.md). Linked supplements and underlying patient data are excluded.

From the repository root, run:

```sh
.venv/bin/python tests/fixtures/qwen_components_confirmation_run_v1/verify.py
```

The bounded verifier reads the compressed archive in memory, checks hashes/envelopes, original executable and installer bindings, all six setup stages, worker audit, checkpoint and numeric results. It reuses the frozen component core, trace builder and evaluation functions to reproduce all four methods and compare the complete first grade and receipt. It never extracts files, opens a database, writes a grade or receipt, executes the notebook, installs packages, accesses the network or runs models. Exit zero means preserved evidence verifies and reports its actual quality status; the same acceptance logic represents either PASS or FAIL. Remote execution and the original ledger-readonly claim cannot be re-observed from this portable archive alone.
