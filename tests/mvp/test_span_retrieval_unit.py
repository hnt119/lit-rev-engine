"""Pure span safety/geometry tests. Synthetic text is not medical evidence."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import math
import re
import threading

import pytest

from src.mvp.adapters import span_retrieval as module
from src.mvp.adapters.span_retrieval import LexicalSpanRetrieval, budget_token_count, span_retrieval_profile
from src.mvp.contracts import Block, PreparedSource
from src.mvp.ports import MvpError
from src.mvp.span_retrieval_contracts import SpanRequirement


def source(*texts, tags=None):
    return PreparedSource(id='fixture-source', paper_id='fixture-paper', status='abstract_only',
        source_type='abstract', provider='SYNTHETIC fixture', source_url='',
        blocks=[Block(id=f'b{index}', ordinal=index + 1, text=text,
                      locator={'type': 'xml_element', 'tag': tags[index] if tags else 'p', 'path': f'/article/sec/{index}'})
                for index, text in enumerate(texts)])


def test_late_unicode_offsets_are_exact_without_mutating_source():
    text = ('Background text.\r\n' * 130) + '女😀 e\u0301 marker outcome 42.\r\n'
    retained = source(text)
    before = deepcopy(retained.model_dump(mode='json'))
    result = LexicalSpanRetrieval().search('marker outcome', [retained], 'r')
    assert result.selections and any('marker outcome 42' in item.quote for item in result.selections)
    for item in result.selections:
        assert item.quote == text[item.start:item.end]
        assert item.end - item.start == len(item.quote) <= 1200
        assert len(re.findall(r'\w+|[^\w\s]', item.quote)) == item.budget_tokens <= 400
    assert retained.model_dump(mode='json') == before
    assert result.delivered_characters <= 3600 and result.delivered_tokens <= 1200
    assert result.unindexed_characters == 0


def test_score_matches_independent_bm25_of_delivered_text_only():
    retained = source('alpha alpha beta', 'beta gamma')
    result = LexicalSpanRetrieval().search('alpha', [retained], 'r')
    expected = math.log(1 + 1.5 / 1.5) * 2 * 2.2 / (2 + 1.2 * (.25 + .75 * 3 / 2.5))
    assert result.selections[0].quote == 'alpha alpha beta'
    assert result.selections[0].score == pytest.approx(expected)
    assert result.indexed_blocks == result.indexed_windows == 2
    assert result.matched_blocks == result.matched_windows == 1


def test_preceding_xml_paragraph_is_not_hidden_scoring_context():
    retained = source('alpha participant qualifier', 'beta 17 23', tags=['p', 'table-wrap'])
    result = LexicalSpanRetrieval().search('alpha', [retained], 'r')
    assert result.matched_block_ids == ['b0']
    assert [item.block_id for item in result.selections] == ['b0']


def test_bounded_nearby_population_and_negation_are_delivered_with_late_result():
    text = ('Background statement. ' * 100) + 'The validation cohort comprised women. The study did not demonstrate a marker benefit.'
    result = LexicalSpanRetrieval().search('marker benefit', [source(text)], 'r')
    assert result.selections
    assert any('validation cohort comprised women' in item.quote and 'did not demonstrate a marker benefit' in item.quote
               for item in result.selections)


def test_default_is_one_field_requirement_not_an_inferred_split():
    result = LexicalSpanRetrieval().search('population and outcome', [source('population outcome')], 'r')
    assert len(result.requirement_statuses) == 1
    assert result.requirement_statuses[0].requirement.id == 'field'
    assert result.requirement_statuses[0].requirement.query == 'population and outcome'
    assert result.requirement_statuses[0].meaning == 'lexical_potential_not_semantic_coverage'


def test_explicit_requirements_reserve_candidates_without_claiming_support():
    requirements = [SpanRequirement(id=name, label=name, query=name) for name in ('population', 'outcome', 'validation')]
    result = LexicalSpanRetrieval().search('Study fields', [source('population qualifier', 'outcome estimate', 'validation cohort')],
        'r', requirements=requirements)
    assert len(result.selections) == 3
    assert {key for item in result.selections for key in item.matched_requirement_ids} == {item.id for item in requirements}
    assert all(item.status == 'selected_lexical_match' for item in result.requirement_statuses)
    limited = LexicalSpanRetrieval().search('Study fields', [source('population qualifier', 'outcome estimate', 'validation cohort')],
        'r', top_k=1, requirements=requirements)
    assert [item.status for item in limited.requirement_statuses].count('matched_but_not_selected') == 2


@pytest.mark.parametrize('sources,top,requirements', [
    ([source('x'), source('y')], 3, None), ([source('x')], 4, None),
    ([source('x')], True, None), ([source('x')], 3, []),
    ([source('x')], 3, [dict(id='a', label='A', query='x')] * 2),
])
def test_invalid_pool_or_limits_rejected_before_scoring(sources, top, requirements, monkeypatch):
    monkeypatch.setattr(module, '_tokens', lambda value: pytest.fail('Invalid request reached scoring'))
    with pytest.raises(MvpError):
        LexicalSpanRetrieval().search('x', sources, 'r', top, requirements=requirements)


def test_block_and_character_omissions_are_explicit(monkeypatch):
    monkeypatch.setattr(module, 'MAX_INDEXED_BLOCKS', 2)
    retained = source('marker first', 'marker second', 'marker third')
    result = LexicalSpanRetrieval().search('marker', [retained], 'r')
    assert result.indexed_blocks == 2 and result.unindexed_blocks == 1
    assert result.unindexed_characters == len('marker third')
    assert 'span_source_block_limit' in {item.code for item in result.messages}
    assert result.requirement_statuses[0].index_incomplete


def test_character_cap_and_overlap_union_are_not_double_counted(monkeypatch):
    monkeypatch.setattr(module, 'MAX_INDEXED_CHARACTERS', 1800)
    text = 'marker. ' * 700
    result = LexicalSpanRetrieval().search('marker', [source(text)], 'r')
    assert result.indexed_windows == 2
    assert result.unindexed_characters == len(text) - 1800
    assert result.partially_indexed_blocks == 1
    assert 'span_source_character_limit' in {item.code for item in result.messages}


def test_window_cap_reports_exact_union_of_indexed_ranges(monkeypatch):
    monkeypatch.setattr(module, 'MAX_INDEXED_WINDOWS', 2)
    text = 'marker filler ' * 800
    result = LexicalSpanRetrieval().search('marker', [source(text)], 'r')
    assert result.indexed_windows == len(result.selections) == 2
    ranges = sorted((item.start, item.end) for item in result.selections)
    union = ranges[0][1] - ranges[0][0] + ranges[1][1] - max(ranges[0][1], ranges[1][0])
    assert result.unindexed_characters == len(text) - union
    assert 'span_window_limit' in {item.code for item in result.messages}


def test_blank_blocks_are_reported_separately_and_do_not_earn_indexed_characters():
    result = LexicalSpanRetrieval().search('marker', [source(' \r\n', 'marker')], 'r')
    assert result.total_source_blocks == 2 and result.indexed_blocks == 1
    assert result.unindexed_blocks == result.skipped_blank_blocks == 1
    assert result.unindexed_characters == 3


def test_budget_tokens_are_an_explicit_proxy_and_bound_punctuation_dense_text():
    assert budget_token_count('a,b 😀 e\u0301') == 6
    result = LexicalSpanRetrieval().search('marker', [source(('x!' * 700) + ' marker')], 'r')
    assert result.selections
    assert all(item.budget_tokens <= 400 and len(item.quote) <= 1200 for item in result.selections)


def test_long_token_fallback_and_table_clipping_are_disclosed():
    text = ('heading ' + 'x' * 2500 + ' marker 42 footnote')
    result = LexicalSpanRetrieval().search('marker', [source(text, tags=['table-wrap'])], 'r')
    assert result.selections
    assert result.selections[0].hard_boundary_clipped
    assert 'span_table_context_clipped' in {item.code for item in result.messages}
    assert len(result.messages) <= 20


def test_no_answer_unavailable_and_stopword_states_are_scope_limited():
    empty = LexicalSpanRetrieval().search('marker', [], 'r')
    assert not empty.selections and 'span_no_usable_source' in {item.code for item in empty.messages}
    missing = LexicalSpanRetrieval().search('marker', [source('unrelated text')], 'r')
    assert missing.requirement_statuses[0].status == 'no_lexical_match_in_indexed_text'
    stopped = LexicalSpanRetrieval().search('and the', [source('unrelated text')], 'r')
    assert stopped.requirement_statuses[0].status == 'no_query_tokens'


def test_profile_is_fresh_and_retrieval_ties_are_stable_across_runs():
    first = span_retrieval_profile()
    first['parameters']['stop_words'].append('marker')
    assert 'marker' not in span_retrieval_profile()['parameters']['stop_words']
    retained = source('marker alpha', 'marker bravo', 'marker delta')
    one = LexicalSpanRetrieval().search('marker', [retained], 'r1')
    two = LexicalSpanRetrieval().search('marker', [retained], 'r2')
    assert one.selections == two.selections
    assert [item.block_id for item in one.selections] == ['b0', 'b1', 'b2']


def test_cooperative_runtime_limit_is_visible():
    tick = [0]

    def clock():
        tick[0] += 1
        return tick[0]

    result = LexicalSpanRetrieval(_monotonic=clock).search('marker', [source('marker ' * 4000)], 'r')
    assert 'span_runtime_limit' in {item.code for item in result.messages}
    assert result.requirement_statuses[0].index_incomplete


def test_one_active_cpu_search_is_shared_across_instances():
    entered, release = threading.Event(), threading.Event()

    def clock():
        entered.set()
        assert release.wait(3)
        return 0

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(LexicalSpanRetrieval(_monotonic=clock).search, 'marker', [source('marker')], 'r')
        assert entered.wait(2)
        try:
            with pytest.raises(MvpError) as error:
                LexicalSpanRetrieval().search('marker', [source('marker')], 'r2')
            assert error.value.code == 'span_retrieval_busy'
        finally:
            release.set()
        assert pending.result(timeout=2).selections
