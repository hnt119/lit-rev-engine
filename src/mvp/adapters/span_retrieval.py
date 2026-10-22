"""Bounded lexical windows whose scored text is the exact delivered source span.

The derived index never rewrites canonical source text. A lexical match is a
retrieval candidate, not evidence of semantic support or whole-paper absence.
"""
from collections import Counter
import math
import re
import threading
import time

from src.review.retrieval import _B, _K1, _STOP_WORDS, _TOKENIZER, _tokens

from ..contracts import PreparedSource
from ..ports import MvpError
from ..span_budget import BUDGET_TOKENS as _BUDGET_TOKENS, budget_token_count
from ..span_retrieval_contracts import (
    BUDGET_TOKENIZER_ID, MAX_DELIVERED_BUDGET_TOKENS, MAX_DELIVERED_CHARACTERS,
    MAX_INDEXED_BLOCKS, MAX_INDEXED_CHARACTERS, MAX_INDEXED_WINDOWS,
    MAX_QUERY_CHARACTERS, MAX_RETRIEVAL_MESSAGES, MAX_SEARCH_SECONDS, MAX_SPAN_BUDGET_TOKENS, MAX_SPAN_CHARACTERS,
    MAX_SPAN_REQUIREMENTS, MAX_SPAN_SELECTIONS, MIN_SENTENCE_WINDOW_CHARACTERS,
    OVERLAP_CHARACTERS, OVERLAP_DEDUP_THRESHOLD, SPAN_METHOD, SPAN_METHOD_VERSION,
    SPAN_PROFILE_ID, TOKEN_BOUNDARY_LOOKBACK_CHARACTERS, SpanRequirement, SpanRequirementStatus, SpanRetrievalMessage,
    SpanRetrievalResult, SpanSelection,
)

_SENTENCE_END = re.compile(r'[.!?。！？]["\'”’\)\]]*\s+|\r\n|[\r\n]')
_CPU_GATE = threading.BoundedSemaphore(1)
INDEX_LIMIT_CODES = frozenset({'span_source_block_limit', 'span_source_character_limit',
                             'span_window_limit', 'span_runtime_limit'})


def span_retrieval_profile() -> dict:
    return dict(profile_id=SPAN_PROFILE_ID, method=SPAN_METHOD, method_version=SPAN_METHOD_VERSION,
        scope='one-paper-one-field', candidate_text_limit=MAX_SPAN_CHARACTERS,
        parameters=dict(tokenizer_id=_TOKENIZER, stop_words=sorted(_STOP_WORDS),
            k1=_K1, b=_B, passage_unit='exact-contiguous-unicode-span',
            budget_tokenizer_id=BUDGET_TOKENIZER_ID,
            max_span_characters=MAX_SPAN_CHARACTERS,
            max_span_budget_tokens=MAX_SPAN_BUDGET_TOKENS,
            max_selections=MAX_SPAN_SELECTIONS,
            max_delivered_characters=MAX_DELIVERED_CHARACTERS,
            max_delivered_budget_tokens=MAX_DELIVERED_BUDGET_TOKENS,
            max_requirements=MAX_SPAN_REQUIREMENTS,
            max_source_blocks=MAX_INDEXED_BLOCKS, max_windows=MAX_INDEXED_WINDOWS,
            max_source_characters=MAX_INDEXED_CHARACTERS, max_runtime_seconds=MAX_SEARCH_SECONDS,
            max_query_characters=MAX_QUERY_CHARACTERS, max_messages=MAX_RETRIEVAL_MESSAGES,
            token_boundary_lookback_characters=TOKEN_BOUNDARY_LOOKBACK_CHARACTERS,
            max_active_cpu_searches=1, overlap_characters=OVERLAP_CHARACTERS,
            overlap_dedup_threshold=OVERLAP_DEDUP_THRESHOLD,
            min_sentence_window_characters=MIN_SENTENCE_WINDOW_CHARACTERS,
            boundary_rule='sentence-linebreak-then-token-or-codepoint-cap.v1',
            overlap_rule='nearest-preceding-sentence-or-whitespace-with-bounded-overlap.v1',
            context_rule='inside-the-delivered-contiguous-span-only',
            query_rule='explicit-requirement-query-union-or-single-field-query',
            selection_rule='requirement-order-reservation-then-global-bm25.v1',
            tie_rule='canonical-block-ordinal-order-start-end',
            character_accounting='exact-union-of-indexed-window-ranges',
            index_policy='bounded-canonical-source-prefix-explicit-omissions',
            score_meaning='lexical-potential-not-semantic-support'))


def _windows(text, limit):
    """Generate bounded overlapping source ranges without a whole-text token list."""
    start, start_clipped = 0, False
    while start < limit:
        hard_limit = min(limit, start + MAX_SPAN_CHARACTERS)
        tokens = []
        for token in _BUDGET_TOKENS.finditer(text, start, hard_limit):
            tokens.append(token)
            if len(tokens) > MAX_SPAN_BUDGET_TOKENS:
                hard_limit = tokens[MAX_SPAN_BUDGET_TOKENS - 1].end()
                break
        if hard_limit <= start:
            break
        boundaries = [item.end() for item in _SENTENCE_END.finditer(text, start, hard_limit)]
        at_real_end = hard_limit == len(text)
        eligible = [value for value in boundaries if value - start >= MIN_SENTENCE_WINDOW_CHARACTERS]
        end = hard_limit if at_real_end or not eligible else eligible[-1]
        # A source-boundary end is complete even without punctuation. A hard
        # limit inside a sentence (including a long token/table) is disclosed.
        clipped = start_clipped or (end < len(text) and end not in boundaries)
        if text[start:end].strip():
            yield start, end, budget_token_count(text[start:end]), clipped
        if end >= limit:
            break
        overlap = min(OVERLAP_CHARACTERS, max(1, (end - start) // 4))
        target = end - overlap
        eligible_starts = [value for value in boundaries if max(start + 1, end - 2 * overlap) <= value <= target]
        if eligible_starts:
            next_start = eligible_starts[-1]
            start_clipped = False
        else:
            # Keep a nearby complete token and its preceding local context when
            # possible. A very long word has an explicit codepoint fallback.
            nearby = [item.end() for item in re.finditer(r'\s+', text[max(start + 1, target - TOKEN_BOUNDARY_LOOKBACK_CHARACTERS):target])]
            next_start = max(start + 1, target - TOKEN_BOUNDARY_LOOKBACK_CHARACTERS) + nearby[-1] if nearby else target
            start_clipped = True
        start = max(start + 1, min(next_start, end))


def _overlaps(first, second):
    if first['block_id'] != second['block_id']:
        return False
    intersection = max(0, min(first['end'], second['end']) - max(first['start'], second['start']))
    return intersection / min(first['end'] - first['start'], second['end'] - second['start']) >= OVERLAP_DEDUP_THRESHOLD


def _union_size(ranges):
    total, left, right = 0, None, None
    for start, end in sorted(ranges):
        if left is None:
            left, right = start, end
        elif start > right:
            total += right - left
            left, right = start, end
        else:
            right = max(right, end)
    return total + (0 if left is None else right - left)


class LexicalSpanRetrieval:
    method, method_version, profile_id = SPAN_METHOD, SPAN_METHOD_VERSION, SPAN_PROFILE_ID

    def __init__(self, *, _monotonic=time.monotonic):
        self._monotonic = _monotonic

    @staticmethod
    def profile():
        return span_retrieval_profile()

    def search(self, question, sources, run_id, top_k=3, *, requirements=None) -> SpanRetrievalResult:
        if (not isinstance(question, str) or not question.strip() or len(question) > MAX_QUERY_CHARACTERS
            or not isinstance(run_id, str) or not 1 <= len(run_id) <= 200
            or type(top_k) is not int or not 1 <= top_k <= MAX_SPAN_SELECTIONS
            or not isinstance(sources, (list, tuple)) or len(sources) > 1
            or any(not isinstance(source, PreparedSource) for source in sources)):
            raise MvpError('span_retrieval_input', 'Use one bounded field query, at most one retained paper source and one to three selections.')
        if requirements is None:
            required = [SpanRequirement(id='field', label='Field question', query=question)]
        else:
            if not isinstance(requirements, (list, tuple)) or not 1 <= len(requirements) <= MAX_SPAN_REQUIREMENTS:
                raise MvpError('span_retrieval_requirements', 'Use one to three explicitly approved field requirements, without inferred decomposition.')
            try:
                required = [item if isinstance(item, SpanRequirement) else SpanRequirement.model_validate(item) for item in requirements]
            except ValueError:
                raise MvpError('span_retrieval_requirements', 'Use valid bounded explicit field requirements.') from None
        if len({item.id for item in required}) != len(required):
            raise MvpError('span_retrieval_requirements', 'Each explicit field requirement needs a unique ID.')
        if not _CPU_GATE.acquire(blocking=False):
            raise MvpError('span_retrieval_busy', 'One lexical span search is already active. Retry this local operation explicitly.', True)
        try:
            return self._search(question, sources, run_id, top_k, required)
        finally:
            _CPU_GATE.release()

    def _search(self, question, sources, run_id, top_k, required):
        started = self._monotonic()
        messages, message_codes = [], set()

        def message(code, text, severity='warning'):
            if code not in message_codes and len(messages) < MAX_RETRIEVAL_MESSAGES:
                message_codes.add(code)
                messages.append(SpanRetrievalMessage(code=code, message=text, severity=severity))

        def expired():
            if self._monotonic() - started >= MAX_SEARCH_SECONDS:
                message('span_runtime_limit', 'The bounded CPU retrieval deadline was reached. The indexed/ranked scope is incomplete; inspect the recorded omissions.')
                return True
            return False

        requirement_tokens = {item.id: set(_tokens(item.query)) for item in required}
        query_tokens = set().union(*requirement_tokens.values())
        source = sources[0] if sources else None
        blocks = source.blocks if source is not None else []
        if source is not None and source.source_type == 'none' and blocks:
            raise MvpError('span_retrieval_source', 'An unavailable source cannot supply retained canonical text.')
        if len({block.id for block in blocks}) != len(blocks):
            raise MvpError('span_retrieval_source', 'Canonical block IDs must be unambiguous within the selected source.')
        total_characters = sum(len(block.text) for block in blocks)
        indexed, windows, ranges, skipped_blank = set(), [], {}, 0
        scanned_characters = 0
        for block_order, block in enumerate(blocks):
            if block_order >= MAX_INDEXED_BLOCKS:
                message('span_source_block_limit', 'The source block bound was reached; remaining blocks were not indexed.')
                break
            if expired():
                break
            remaining = MAX_INDEXED_CHARACTERS - scanned_characters
            if remaining <= 0:
                message('span_source_character_limit', 'The canonical source character bound was reached; remaining source text was not indexed.')
                break
            limit = min(len(block.text), remaining)
            if limit == len(block.text) and not block.text.strip():
                skipped_blank += 1
                scanned_characters += limit
                continue
            if source is None or source.source_type == 'none':
                continue
            last_end = 0
            for start, end, budget, clipped in _windows(block.text, limit):
                if len(windows) >= MAX_INDEXED_WINDOWS:
                    message('span_window_limit', 'The derived window bound was reached; remaining source windows were not indexed.')
                    break
                if expired():
                    break
                quote = block.text[start:end]
                frequencies = Counter(_tokens(quote))
                matches = [item.id for item in required if requirement_tokens[item.id].intersection(frequencies)]
                windows.append(dict(source_id=source.id, paper_id=source.paper_id, block_id=block.id,
                    start=start, end=end, quote=quote, frequencies=frequencies,
                    length=sum(frequencies.values()), budget_tokens=budget,
                    hard_boundary_clipped=clipped, matched_requirement_ids=matches,
                    tie=(block.ordinal, block_order, start, end)))
                indexed.add(block.id)
                ranges.setdefault(block.id, []).append((start, end))
                last_end = max(last_end, end)
            scanned_characters += last_end or limit
            if 'span_runtime_limit' in message_codes or 'span_window_limit' in message_codes:
                break
            if limit < len(block.text):
                message('span_source_character_limit', 'The canonical source character bound was reached; the remaining block suffix was not indexed.')
                break

        covered = {key: _union_size(value) for key, value in ranges.items()}
        unindexed_characters = total_characters - sum(covered.values())
        partial = sum(0 < covered.get(block.id, 0) < len(block.text) for block in blocks)
        matched = [window for window in windows if window['matched_requirement_ids']]
        matched_ids = {window['block_id'] for window in matched}
        matched_block_ids = [block.id for block in blocks if block.id in matched_ids]
        # Same BM25 constants/formula as the frozen lexical helper, evaluated
        # over exact window text only. Checks between bounded windows keep the
        # new CPU deadline cooperative; no old scorer is modified.
        df, score_statistics_complete = Counter(), True
        for window in windows:
            if expired():
                score_statistics_complete = False
                break
            df.update(query_tokens.intersection(window['frequencies']))
        average = sum(window['length'] for window in windows) / len(windows) if windows else 0
        ranked = []
        for window in matched if score_statistics_complete else []:
            if expired():
                break
            score = 0.0
            for token in sorted(query_tokens.intersection(window['frequencies'])):
                frequency = window['frequencies'][token]
                idf = math.log(1 + (len(windows) - df[token] + .5) / (df[token] + .5))
                score += idf * frequency * (_K1 + 1) / (frequency + _K1 * (1 - _B + _B * window['length'] / average))
            if score > 0:
                ranked.append(dict(window, score=score))
        ranked.sort(key=lambda item: (-item['score'], item['tie']))
        selected = []

        def add(window):
            if len(selected) >= top_k or any(_overlaps(old, window) for old in selected):
                return False
            if (sum(len(item['quote']) for item in selected) + len(window['quote']) > MAX_DELIVERED_CHARACTERS
                or sum(item['budget_tokens'] for item in selected) + window['budget_tokens'] > MAX_DELIVERED_BUDGET_TOKENS):
                return False
            selected.append(window)
            return True

        for requirement in required:
            if any(requirement.id in item['matched_requirement_ids'] for item in selected):
                continue
            for window in ranked:
                if requirement.id in window['matched_requirement_ids'] and add(window):
                    break
        for window in ranked:
            add(window)
            if len(selected) >= top_k:
                break
        selected.sort(key=lambda item: (-item['score'], item['tie']))
        selections = [SpanSelection(**{key: window[key] for key in SpanSelection.model_fields}) for window in selected]
        if any(item.hard_boundary_clipped for item in selections):
            message('span_hard_boundary_clipped', 'A delivered span reaches a hard sentence/token/character boundary; surrounding qualifiers may be omitted.')
        table_ids = {block.id for block in blocks if block.locator.get('tag') == 'table-wrap'}
        if any(item.block_id in table_ids and (item.start > 0 or item.end < len(next(block.text for block in blocks if block.id == item.block_id))) for item in selections):
            message('span_table_context_clipped', 'A selected table span omits part of its canonical table; headings, row labels or footnotes may be outside the delivered quotation. Inspect the full retained table before interpreting values.')
        if unindexed_characters:
            message('span_unindexed_source_text', 'Some canonical characters are outside the exact union of indexed windows; unindexed counts include intentionally skipped whitespace-only blocks.')
        if not query_tokens:
            message('span_no_query_tokens', 'The explicit field requirements contain no usable lexical ranking tokens.')
        if not sources or source.source_type == 'none':
            message('span_no_usable_source', 'No usable retained source text is available for this paper/field.')
        if query_tokens and not matched:
            message('span_no_lexical_match', 'No lexical match was found in the indexed text. This does not establish that the paper lacks the requested information.')
        message('span_context_scope', 'Scores and requirement labels describe lexical potential in the delivered contiguous spans; they do not establish semantic support, inspected evidence or whole-paper coverage.', 'info')
        incomplete = bool(unindexed_characters or INDEX_LIMIT_CODES.intersection(message_codes))
        statuses = []
        for requirement in required:
            matching = sum(requirement.id in item['matched_requirement_ids'] for item in matched)
            chosen = sum(requirement.id in item.matched_requirement_ids for item in selections)
            status = ('no_query_tokens' if not requirement_tokens[requirement.id] else 'selected_lexical_match' if chosen
                      else 'matched_but_not_selected' if matching else 'no_lexical_match_in_indexed_text')
            statuses.append(SpanRequirementStatus(requirement=requirement, status=status,
                matched_windows=matching, selected_spans=chosen, index_incomplete=incomplete))
        return SpanRetrievalResult(run_id=run_id, selections=selections,
            indexed_blocks=len(indexed), matched_blocks=len(matched_block_ids),
            indexed_windows=len(windows), matched_windows=len(matched), matched_block_ids=matched_block_ids,
            total_source_blocks=len(blocks), total_source_characters=total_characters,
            unindexed_blocks=len(blocks) - len(indexed), partially_indexed_blocks=partial,
            skipped_blank_blocks=skipped_blank, unindexed_characters=unindexed_characters,
            delivered_characters=sum(len(item.quote) for item in selections),
            delivered_tokens=sum(item.budget_tokens for item in selections),
            requirement_statuses=statuses, messages=messages,
            elapsed_seconds=max(0.0, self._monotonic() - started))
