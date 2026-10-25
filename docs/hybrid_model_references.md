# Experimental hybrid model input and artifact references

Inspected 25 October 2026. These are publisher conventions and resolved artifact
metadata, not proof of engine retrieval quality. CPU and MPS outcomes belong in
separate observed runtime receipts. The model stack is optional; importing the
lexical core or opening settings does not import it or download model files.

| Component | Immutable Hugging Face revision |
| --- | --- |
| Qwen/Qwen3-Embedding-0.6B | `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` |
| Qwen/Qwen3-Reranker-0.6B | `e61197ed45024b0ed8a2d74b80b4d909f1255473` |
| ncbi/MedCPT-Query-Encoder | `d83a36cc6b8e3a5c5e9d9d6ba156808c1643dcbc` |
| ncbi/MedCPT-Article-Encoder | `d05a736da4bb84ee4057b7f7999485be6ed85465` |
| ncbi/MedCPT-Cross-Encoder | `71caf65d4927987813984f54c284405a13fcca49` |

The [Qwen embedding example](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B/blob/97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3/README.md)
uses last-valid-token pooling, L2 normalization and instructed queries. Documents
receive no query instruction. The adapter keeps all 1,024 dimensions and handles
left/right padding. The [reranker example](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B/blob/e61197ed45024b0ed8a2d74b80b4d909f1255473/README.md)
uses its system/user/assistant prefix and suffix and final-token yes/no logits.
This implementation retains the normalized yes/no relevance score, which is not
an evidence-support probability. Complete inputs are checked before inference;
the local v1 profile declares 1,024 total tokens and 256 instructed query tokens.
These conservative engine limits are not the architecture's advertised limits.

The [MedCPT query example](https://huggingface.co/ncbi/MedCPT-Query-Encoder/blob/d83a36cc6b8e3a5c5e9d9d6ba156808c1643dcbc/README.md)
uses CLS representations and a 64-token query policy. The [article example](https://huggingface.co/ncbi/MedCPT-Article-Encoder/blob/d05a736da4bb84ee4057b7f7999485be6ed85465/README.md)
encodes title/abstract as two segments, producing 768-dimensional vectors. Native
dense scoring is raw inner product without L2 normalization. The [Cross Encoder](https://huggingface.co/ncbi/MedCPT-Cross-Encoder/blob/71caf65d4927987813984f54c284405a13fcca49/README.md)
receives a query/document pair and returns raw relevance logits, including
negative values. The article title and exact retained passage replace native
title/abstract input in this engine: this is an experimental passage adaptation.
The cross-encoder document concatenates title, `. ` and exact passage. It reserves
the full 64-token query policy plus pair special tokens before window admission.
Auxiliary title metadata is never quoted as retained passage evidence. A query,
title or passage exceeding its full input policy is rejected, never truncated.

All models use explicit float32, eager attention, evaluation/inference mode,
small document batches and sequential component loading/unloading. No CUDA,
FlashAttention, vLLM, quantization, remote code or generation API is required.
MPS is selected explicitly and fails if unavailable; it never substitutes CPU.
The native Qwen implementation requires Transformers 4.51 or later; the optional
runtime must be pinned and actually tested rather than inferred from that floor.

## Artifact formats and notices

The two Qwen models and MedCPT query/article encoders offer official safetensors.
At the pinned revision the official MedCPT Cross Encoder offers only
`pytorch_model.bin` (437,998,062 bytes; SHA-256
`61d5ccd48869e03500544525fc231641d7daa9ba267b202c82724750038dc1e0`).
The adapter requires Torch 2.6 or later, verifies the installed artifact through
the pack manager, then uses explicit `torch.load(weights_only=True,
map_location='cpu')`, checks a plain tensor state dictionary, and strictly loads
the native BERT classification architecture. It does not add pickle globals,
execute uploaded code, call unsafe generic loaders or fetch conversion artifacts.

Qwen model cards declare Apache-2.0 but those two repositories contain no separate
LICENSE file. The retained [Apache notice](notices/QWEN_APACHE_LICENSE.txt) comes
from the declared official base model
[Qwen/Qwen3-0.6B-Base at da87bfb608c14b7cf20ba1ce41287e8de496c0cd](https://huggingface.co/Qwen/Qwen3-0.6B-Base/blob/da87bfb608c14b7cf20ba1ce41287e8de496c0cd/LICENSE),
11,343 bytes, SHA-256
`832dd9e00a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e`.
This provenance must remain distinct from the embedding/reranker weight manifests.

All MedCPT model cards declare public-domain. Query/article repositories contain
a public-domain notice; Cross Encoder's pinned LICENSE is empty (zero bytes).
Preserve that fact rather than inventing missing license content. The retained
[NCBI notice](notices/MEDCPT_PUBLIC_DOMAIN_NOTICE.txt) is the official
[MedCPT code repository notice at 11e129be74102c98d16a11c310b0b5ce74c1db5e](https://github.com/ncbi/MedCPT/blob/11e129be74102c98d16a11c310b0b5ce74c1db5e/LICENSE),
1,240 bytes, SHA-256
`455605fa53ddcfbfc59bae8a097c4b0452f7a45810519dbed9be57c6dd370289`.
Retain the model card declarations and applicable notices with any later pack;
this release does not authorize publishing or mirroring packs.
