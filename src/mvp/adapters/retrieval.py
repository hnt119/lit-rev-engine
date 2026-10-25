"""Reuse existing pure lexical ranking without formal review eligibility."""

from collections import Counter

from src.review.retrieval import _B, _CONTEXT_RULE, _CONTEXT_WORDS, _K1, _STOP_WORDS, _TOKENIZER, _contexts, _score, _tokens

from ..contracts import Anchor, Passage, digest


class LexicalRetrieval:
    method = "bm25_context_blocks"
    parameters = {"tokenizer_id": _TOKENIZER, "stop_words": sorted(_STOP_WORDS),
                  "passage_unit": "block", "k1": _K1, "b": _B,
                  "context_rule": _CONTEXT_RULE, "context_max_words": _CONTEXT_WORDS}

    def search(self, question, sources, run_id, top_k=5):
        candidates = []
        for source_order, source in enumerate(sources):
            if source.source_type == "none":
                continue
            blocks = [block.model_dump(mode="json") for block in source.blocks]
            contexts = _contexts(blocks, "jats_xml" if source.source_type == "full_text" else "txt")
            for block_index, block in enumerate(source.blocks):
                if not block.text.strip():
                    continue
                frequencies = Counter(_tokens(block.text))
                context = contexts.get(block.id)
                if context is not None:
                    frequencies.update(_tokens(context["anchor"]["quote"]))
                passage = Passage(
                    id="passage:" + digest([run_id, source.id, block.id, 0, len(block.text)]),
                    rank=0, paper_id=source.paper_id, source_id=source.id,
                    source_version=source.version, source_sha256=source.source_sha256,
                    blocks_sha256=source.blocks_sha256, source_type=source.source_type,
                    anchor=Anchor(block_id=block.id, start=0, end=len(block.text), quote=block.text),
                    locator=block.locator,
                    surrounding_text="\n\n".join(neighbor.text for neighbor in source.blocks[max(0, block_index - 1):block_index + 2]),
                    score=0.0)
                candidates.append({"passage": passage, "frequencies": frequencies,
                                   "length": sum(frequencies.values()),
                                   "tie": (source_order, block.ordinal, 0, len(block.text))})
        ranked = _score(candidates, sorted(set(_tokens(question))), self.method)
        passages = [candidate["passage"].model_copy(update={"rank": rank, "score": score})
                    for rank, (score, candidate) in enumerate(ranked[:top_k], 1)]
        return passages, len(candidates), len(ranked)
