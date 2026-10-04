# First saved Kaggle GPU evaluation

**The free GPU workflow executes successfully, but the frozen retrieval quality gate fails.** Qwen improves own-source support coverage from 72.22% to 80.56% and complete positive questions from two to four of six. Coverage remains below the prospectively required 85%. The human review pilot remains pending.

This is the first actual Qwen ranking run against the frozen Kaggle v2 job. The source bytes, eight questions, model profile, top-five limit, candidate-pool limit and acceptance thresholds were preserved throughout execution and grading. The failed result is retained; its thresholds were not changed after observing rankings.

## Saved run and integrity

The private [saved Kaggle notebook version](https://www.kaggle.com/code/yixuanhuangethan/qwen-kaggle?scriptVersionId=355104707) completed successfully. Kaggle displayed **439.6 seconds** for the complete notebook. The runner recorded **395.076408088 seconds** for its measured batch, including model loading/downloads and inference. These are separate measurements. The local saved-run log observation contains the model preflight and printed results checksum.

```text
Freeze: docs/qwen-kaggle-freeze-v2.json
Freeze file SHA-256: 04f0a961eb0f7d91626a72e93f68c5d4f8cc77f4ff0f78fbb72063219d878b62
Job payload SHA-256: ab6e06ca37d89f95800fc09100f2c8a41c595f3b76c0497fb9f2679850672a8f
Results payload SHA-256: 0f5aa688f5382ddbfae3260bc1d832ba6d81aa2222a716feae07395887ea42be
Downloaded results file SHA-256: 5e6a7e5b3da9dc541298a2b409bdf3cd200440be85b190a598c37b29f30c1874
```

The payload checksum matches the checksum printed by that saved notebook run. The complete downloaded file includes the enclosing artifact envelope, so its file checksum differs from its payload checksum. The prepared source ledger and job match their retained prospective hashes. Both source articles were reread from the original frozen XML for independent quotation and locator checks.

Local retained artifacts are under `data/qwen-kaggle-pilot-v2/`: the original preparation and job, `run-evidence/results.json`, the saved-run log observation and screenshots, `result.json`, and `validation.receipt.json`. The first grader returned exit code **2** and status **failed**, preserving its result and immutable validation receipt. These local runtime files are not the source of the prospective truth.

The [portable run archive](../tests/fixtures/qwen_kaggle_run_v2/README.md) retains the five original job, preparation, raw results, grade and validation-receipt JSON files in 2,033,240 bytes of compressed storage. Independent inspection verified every original byte count and file checksum, exact agreement with the local originals, and the receipt's job/result/trace bindings. It contains no ledger, credential files or private UI observations. Its archive SHA-256 is `87c3dff55b968f4f91e9e8f5598854a4d8dd5418f9c134026953861f57e0f101`.

The archive's standalone verifier reproduces the failed grade using only the standard library and frozen evidence, without importing the current retrieval implementation. Evaluation found that its first version did not reject contradictory grade-summary metadata in the manifest; that checker was repaired before acceptance. Independent checks now reject a forged successful summary, Boolean schema/paid-call aliases, a noninteger script version and an incorrect preservation status. The original archive bytes and model run remain unchanged. Verifier exit code zero means the preserved failure is intact, not that Qwen passed its quality gate.

## Independent quality assessment

Evaluation independently reconstructed BM25 ordering, cosine ordering, RRF with constant 60, maximum representation relevance per block and final source-order ties from the saved raw vectors and scores. It recomputed own-source OR-of-AND support metrics separately from the grading tool and reproduced the grader's result. Import and exact saved-result replay were also run through a SQLite connection with `mode=ro` and `query_only=ON`; the ledger's logical hash remained unchanged.

The batch contains two documents, 102 source representations, eight question embeddings and 160 rerank pairs. Each returned passage retains its complete original own block and exact locator. Context contributes no quotation support, and every result remains a candidate requiring human verification.

| Acceptance criterion | Recorded result | Outcome |
| --- | --- | --- |
| Mean own-source support coverage ≥85% | 80.56% | Fail |
| Complete positive questions ≥4 of 6 | 4 of 6 | Pass |
| Coverage does not regress against lexical reference | 80.56% versus 72.22% | Pass |
| Complete positives do not regress against lexical reference | 4 versus 2 | Pass |
| Exact anchors, source/screening scope, replay and read-only ledger | Independently reproduced | Pass |
| Measured batch ≤1,800 seconds | 395.076 seconds | Pass |
| Paid inference calls | 0 | Pass |

Coverage counts the exact required quotation spans present in the top five own passages. Each positive question takes the best permitted support alternative; complete coverage requires every quotation in at least one alternative. The final coverage is the mean over the six positive questions. Null questions are excluded from that denominator.

| Fixed positive question | Lexical coverage | Qwen coverage | Qwen complete |
| --- | --- | --- | --- |
| qwen-mammography-01 | 83.33% | 100% | Yes |
| qwen-mammography-02 | 50% | 50% | No |
| qwen-mammography-03 | 66.67% | 100% | Yes |
| qwen-breast-us-01 | 33.33% | 33.33% | No |
| qwen-breast-us-02 | 100% | 100% | Yes |
| qwen-breast-us-03 | 100% | 100% | Yes |

Both null questions returned zero of their two annotated own context spans; the lexical reference returned one of two for each. This context regression is recorded separately. The engine makes no answerability claim and receives no positive-answer credit for nulls. Zero recovered null context does not demonstrate correct abstention.

## Where required companions were lost

For `qwen-mammography-02`, the required acquisition-period Methods block `xml:/article[1]/body[1]/sec[2]/sec[1]/p[2]` was absent from the twenty-block hybrid candidate pool. The required ICC Results block ranked first. This is a candidate-generation miss for one component of a compound question.

For `qwen-breast-us-01`, the required cohort-period and diagnostic-reference Methods block `xml:/article[1]/body[1]/sec[2]/sec[1]/p[1]` reached the candidate pool but ranked sixth, outside the fixed top five. The required Results block ranked second. The article title ranked first, and a supplementary-material caption occupied another top-five slot. This is a final-selection miss for a required companion, despite its presence in the pool.

The next retrieval experiment should explicitly preserve component coverage when building candidate pools and selecting final own passages. Every companion must remain a separately grounded own block. These observed questions can now support diagnosis and development; an adjusted policy needs prospective confirmation on fresh, ungraded questions. Raising the top-k limit or removing particular passages after this run cannot convert the frozen v2 result into a pass.

## Runtime observations and limits

The runner loaded Qwen3-Embedding-4B revision `5cf2132abc99cad020ac570b19d031efec650f2b` and Qwen3-Reranker-4B revision `22e683669bc0f0bd69640a1354a6d0aebcfeede5` sequentially on `cuda:0`. The session offered two Tesla T4 devices; this runner used one. It recorded FP16 and SDPA, CUDA 12.8, Torch 2.11.0+cu128, Python 3.13.15, Transformers 4.51.3, Tokenizers 0.21.1, Safetensors 0.5.3 and Hugging Face Hub 0.30.2. The declared dependency and model pins match the frozen profile.

The maximum complete input was **726 tokens**, below the 8,192-token bound, with no truncation. Peak Torch allocated GPU memory was **8,167,223,296 bytes**, below the selected device's recorded **15,636,037,632 bytes**. Torch allocation excludes other GPU users, CUDA context overhead and total reserved/device memory; it is not a measure of all GPU memory consumption. This run demonstrates memory fit for this source batch, not the maximum configured input size.

The notebook log reported dependency conflicts with preinstalled Gradio and Diffusers. The pinned retrieval dependencies loaded, both models executed, valid results were saved, and the notebook completed. The warnings do not establish compatibility for those unrelated packages in that session.

Eight fixed questions from two main articles are a software retrieval check, not clinical validation or evidence of general recall. Recorded runtime metadata is not cryptographic hardware attestation. The immutable failure and exact source truth remain the evidence for the next architecture decision.
