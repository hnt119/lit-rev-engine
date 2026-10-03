# Kaggle Qwen batch compute contract

Checked **4 October 2026, Asia/Singapore** against primary documentation. The user declined paid inference. Kaggle is the proposed free GPU worker for a finite retrieval batch; the Mac keeps the review ledger and validates downloaded results. No DeepInfra request, paid fallback, model download or GPU inference was performed during this research.

## What Kaggle currently documents

Kaggle documents free GPU notebooks, limited availability and possible queues. Its notebook documentation lists CPU/GPU sessions of up to 12 hours, 20 GB of saved output in `/kaggle/working`, additional temporary disk outside that directory, and approximately 29 GB of host RAM for P100/T4 configurations. `Save & Run All` starts a clean session. Internet must be enabled for online package installation. These are published platform specifications, not a guarantee about this account's available quota or allocation. [Kaggle notebook documentation](https://www.kaggle.com/docs/notebooks).

The current NVIDIA guide names **GPU T4 ×2 and GPU P100** as example available options under Settings → Accelerator. Starting a GPU session consumes Kaggle GPU quota; stop the session after collecting output. Check the actual accelerator and remaining quota in the user's account before scheduling a batch. A universal number of free weekly hours was not verified. [NVIDIA Kaggle guide](https://docs.nvidia.com/datascience/deployment/latest/platforms/kaggle/).

Kaggle's official CLI metadata supports `is_private`, `enable_gpu`, `enable_internet`, `machine_shape` and `dataset_sources`. Private notebooks are the default; set privacy explicitly in generated metadata. `NvidiaTeslaT4` identifies the T4 ×2 configuration in that API, subject to account availability. [Notebook metadata contract](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels_metadata.md).

The CLI supports notebook push, run-status checks and saved output downloads. Select the exact `owner/notebook-slug/version` when downloading results, and use a fresh local directory. The `--accelerator` option selects the requested accelerator for a run. Uploading a dataset through `datasets create` defaults to private; do not pass `--public` for review jobs. Authentication is needed for the user's private resources. The generated batch needs neither a DeepInfra key nor a Hugging Face access token for these public, ungated models. [Notebook CLI](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels.md), [dataset CLI](https://github.com/Kaggle/kaggle-cli/blob/main/docs/datasets.md).

## Model revisions and scoring

Both model repositories were public, ungated and Apache-2.0 at inspection. Freeze the following immutable revisions for both tokenizer and model loading; do not resolve `main` during a graded run:

| Role | Model | Revision |
| --- | --- | --- |
| Embedding | `Qwen/Qwen3-Embedding-4B` | `5cf2132abc99cad020ac570b19d031efec650f2b` |
| Reranking | `Qwen/Qwen3-Reranker-4B` | `22e683669bc0f0bd69640a1354a6d0aebcfeede5` |

The official API reports 4,021,774,336 embedding parameters and 4,021,784,576 reranker parameters, stored as BF16. The two models are distinct checkpoints. [Embedding metadata](https://huggingface.co/api/models/Qwen/Qwen3-Embedding-4B), [reranker metadata](https://huggingface.co/api/models/Qwen/Qwen3-Reranker-4B).

Embedding uses `AutoModel`, last attended token pooling and L2 normalization. Apply the recorded task instruction to queries and leave documents unprefixed. The author card uses `Instruct: {instruction}\nQuery:{query}`; if this engine declares a space after `Query:`, retain that exact declared encoding in its prospective profile and receipts. Its full output dimension is 2,560. The card advertises 32K context, while its example uses a smaller cap; the notebook must enforce its own recorded token cap, including query formatting. Reject an overlength scoring representation rather than silently truncate it. [Embedding usage](https://huggingface.co/Qwen/Qwen3-Embedding-4B#transformers-usage).

Reranking uses `AutoModelForCausalLM` and the author's explicit system prefix, instruction/query/document body and assistant suffix. Reproduce the Transformers example's three separately encoded components with `add_special_tokens=False` and left padding. Score the final token's `no` and `yes` logits with a two-class softmax; retain the `yes` probability. It is a relevance score, not evidence verification. Generic chat generation and the CrossEncoder default raw logit difference are different contracts. Keep the exact prefix/suffix and score conversion in the frozen runtime. [Reranker usage](https://huggingface.co/Qwen/Qwen3-Reranker-4B#using-transformers).

## Proposed cloud runtime

The model cards require Transformers 4.51.0 or later. A conservative, explicit starting set is `transformers==4.51.3`, `tokenizers==0.21.1`, `safetensors==0.5.3` and `huggingface-hub==0.30.2`. These satisfy the selected Transformers release's dependency bounds. Keep Kaggle's CUDA-enabled PyTorch installation and record its exact version, CUDA version, Python version and device properties in results; this set has not yet been tested in the user's notebook. [Transformers 4.51.3 dependencies](https://github.com/huggingface/transformers/blob/v4.51.3/setup.py).

That release's Qwen3 implementation explicitly supports SDPA and `logits_to_keep=1`, allowing reranking to compute only final-token vocabulary logits. Use inference mode, `use_cache=False`, batch size one and FP16 initially. [Qwen3 implementation](https://github.com/huggingface/transformers/blob/v4.51.3/src/transformers/models/qwen3/modeling_qwen3.py).

The standard FlashAttention-2 CUDA implementation targets Ampere, Ada and Hopper; its documentation directs T4 users to a separate implementation. Therefore the notebook should use PyTorch SDPA rather than install the card's optional FlashAttention-2 example on T4/P100. Do not assume hardware-native BF16 on these older accelerators. [FlashAttention hardware support](https://github.com/Dao-AILab/flash-attention#nvidia-cuda-support), [NVIDIA precision support](https://docs.nvidia.com/cuda/ampere-tuning-guide/index.html).

T4 has 16 GB of GPU memory; NVIDIA's P100 whitepaper also describes a 16 GB configuration. Two T4 devices do not automatically behave as one 32 GB device. **Inference planning estimate:** each 4B checkpoint requires roughly 8.04 GB for FP16 parameters alone, before activations, temporary buffers and allocator overhead. Load the embedding model, finish document/query encoding, release it, then load the reranker on one GPU. Sequential loading is a plausible starting configuration, not proof that the selected token cap fits. Measure peak memory and actual batch completion. [T4 datasheet](https://www.nvidia.com/content/dam/en-zz/Solutions/Data-Center/tesla-t4/t4-tensor-core-datasheet.pdf), [P100 whitepaper](https://images.nvidia.com/content/pdf/tesla/whitepaper/pascal-architecture-whitepaper.pdf).

Store only result artifacts and useful checkpoints in `/kaggle/working`; place downloaded model caches in temporary storage outside it. The supplied notebook sets `HF_HOME=/kaggle/temp/huggingface`, reads `JOB_PATH` and `RUNNER_PATH` from the attached private dataset under `/kaggle/input/YOUR_PRIVATE_DATASET/`, and writes `qwen-results.json` and `qwen-checkpoint.json` under `/kaggle/working`. Set `JOB_SHA256` to the trusted checksum printed by the local export. Preserve embedding output before unloading the first model. A saved output or downloaded checkpoint must be bound to the original job hash before reuse. Session scratch storage is not the review engine's durable source archive.

## Engine boundary and pilot acceptance

The local export contains selected canonical source passages, exact representation IDs/spans, declared query IDs, a frozen model profile and deterministic lexical candidates. Its `source_manifest` and candidates also include current eligibility labels and study linkage metadata (`study_link_state` and `study_ids`) so the importer can detect changed scope or associations. The job excludes reviewer identities, screening event histories, extracted findings, verification histories, credentials, the database itself and gold answers. The local engine remains authoritative for eligible sources, full quotation anchors and candidate-pool reconstruction.

On return, validate the original trusted job hash, model revisions, dimensions, exact IDs, finite values, token counts and completed stages. Recheck the source/scope snapshot before publishing traces. Reconstruct ranking from recorded vectors and scores; never accept notebook-supplied quotation text or a fabricated final ranking as source truth. Failed or partial batches must remain explicit and cannot invoke a paid service.

The existing fresh source/support set remains ungraded. Kaggle's different runtime and scoring profile need a prospective freeze before the first GPU ranking. Offline tests demonstrate software behavior; only actual GPU results can establish model quality, runtime and memory readiness for the human pilot.

If the 4B pair cannot complete within the account's free resources, the author also provides a **0.6B embedding/reranker pair**, with a 1,024-dimensional embedding. Treat it as a separately frozen and graded contingency, never substitute it silently into a 4B job or reuse the 4B acceptance result. [Qwen author model list](https://github.com/QwenLM/Qwen3-Embedding#qwen3-embedding-series-model-list).

Remaining account-specific unknowns are available quota, verification/access requirements, actual accelerator allocation, Internet access, CUDA/PyTorch compatibility, download time, peak memory and end-to-end retrieval quality. None is established by general model-card benchmark results.
