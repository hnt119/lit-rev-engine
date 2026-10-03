# Free GPU Qwen batch gate before the human pilot

On 4 October 2026 the user declined paid DeepInfra inference and selected Kaggle as a possible free GPU solution. No further paid calls are authorized. The earlier [DeepInfra setup attempts](qwen-live-setup-v1.json) produced no model replies or ranked results. Its original freeze remains a historical record, superseded before any quality grade. The new prospective Kaggle freeze preserves the same still-ungraded source/gold bytes and quality thresholds while pinning the different serving implementation.

## Architecture and interfaces

The Mac owns review state and prepares an immutable, hashed source snapshot. A finite Kaggle GPU notebook embeds source representations and queries, unloads the embedding model, then reranks fixed hybrid pools. The Mac reconstructs the pools/ranks and validates the current source, eligibility and profile before returning exact own quotations. Model execution never opens a ledger transaction or records a screening decision, extraction or verification.

`qwen-export PROJECT --queries JSON --job PATH` accepts only a list of `{id, query}` questions. Its immutable job contains the selected canonical source representations, separate lexical scoring context, model revisions, encoding rules and deterministic candidate metadata. `qwen-import PROJECT --job PATH --job-sha256 SHA --results PATH --receipt PATH` requires the locally retained export digest and rechecks source/scope/profile, complete vector and score identities, finite values and runtime metadata. Supplying `--results-sha256` reproduces a saved run locally. A checksum provides integrity and binding; it does not authenticate that an untrusted machine actually used a GPU.

Use the private notebook/dataset workflow in [the guide](qwen-cloud.md). No inference API key, paid provider fallback, public tunnel or permanently running service is required. Public Hugging Face weights download inside Kaggle only. GPU quota and availability are account specific; see the [provider contract](kaggle-provider-contract.md).

## Tickets and acceptance

| Ticket / owner | Files / changed facts | Acceptance criteria |
| --- | --- | --- |
| K1 Implementation | `src/review/qwen_batch.py`, `tools/qwen_kaggle_runner.py`, `notebooks/qwen_kaggle.ipynb` | Immutable source job/result interface; pinned 4B revisions; CUDA FP16 SDPA, one model at a time, measured token lengths with no truncation; preserved own anchors; locally recomputed ranks; no ledger writes, local weights or paid calls. |
| KR1 Retrieval | `docs/kaggle-provider-contract.md` | Current official GPU/session/output facts, exact author model conventions, immutable revisions, resource uncertainties and private upload instructions. No inference or gold tuning. |
| KE1 Evaluation | `tests/test_qwen_batch.py`, `tests/test_qwen_kaggle_pilot.py`, `docs/qwen-kaggle-evaluation.md` | Independent CPU artifact/schema/integrity/scope/path/replay tests and notebook static checks. Fakes establish operational behavior only. |
| K2 Coordinator | CLI, guide, `tools/evaluate_qwen_kaggle.py`, prospective freeze | Paid calls opt-in only; fresh export contains sources/questions without gold answers or the ledger. Complete inputs and thresholds pinned before actual GPU ranking. |
| KE2 Evaluation | Actual Kaggle saved run, result receipts and independent evidence review | Validate recorded GPU/model/dependencies/tokens/elapsed/peak memory and regrade exact own support; disclose failures, null context and incomplete positives. |
| KD Coordinator | Release and next decision | Accept software and GPU quality separately. Proceed to human pilot only after observed evidence passes; missing GPU access remains an explicit pending gate. |

## Prospective quality and engineering gate

The fixed candidate is `qwen_kaggle_hybrid`: top five whole canonical blocks, pool of twenty blocks, BM25/context plus dense max-span cosine with RRF constant 60, then maximum representation relevance per block. Reference: unchanged `bm25_context_blocks`. Embedding and reranker use the pinned 4B models. A smaller model or quantization is a new recorded profile requiring a separate prospective comparison; there is no automatic substitution after failure.

The eight fixed main-article questions contain six quantitative positives, four necessary multi-block AND questions and two source-scoped nulls. Sufficient support sets are OR alternatives; all quotations in one alternative are necessary AND support. Scoring context supplies no own-support credit. Required: at least 85% mean own-support coverage, at least four of six complete positives, and no lower coverage or complete-positive count than the same-source lexical reference. Own/context anchors, active project/source scope, unchanged-state replay and read-only state must all pass exactly. Nulls receive no answerable credit; report their declared no-answer context recovery and remaining candidates.

The batch engineering ceiling is 1,800 recorded wall-clock seconds including model loading/downloads and inference (package installation is separate), with zero paid inference calls. Record actual GPU, pinned model/tokenizer revisions, runtime dependency versions, dtype, attention backend, token lengths, elapsed time and peak Torch-allocated GPU memory. This measures a finite batch; it does not promise HTTP warm-query latency. Queue time, account allocation and an interrupted Kaggle session are separate availability facts. A failed or missing run cannot pass from model-card benchmarks or programmed responses.

Preserve the first GPU result and fail/pass decision. Review demonstrated failures before choosing the next ticket. Existing medical v1/v2/v3 sources, truth, selection and results remain unchanged. The human team's topic, protocol and screening/extraction judgments remain separate inputs to the [human pilot](pilot-milestone.md).
