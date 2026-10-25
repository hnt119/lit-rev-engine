import pytest

from src.mvp.search_plan_compiler import compile_search_plan
from src.mvp.search_plan_contracts import SearchPlanDraft


def draft():
    return SearchPlanDraft.model_validate(dict(original_question='gut microbiome in Asian women; preferably Southeast Asia', concepts=[
        dict(id='microbiome', label='gut microbiome', role='topic', requirement='required', retrieval_use='query',
             source_span=dict(start=0, end=14, text='gut microbiome'), terms=[dict(id='t1', text='gut microbiome', state='approved')]),
        dict(id='women', label='Asian women', role='population', requirement='required', retrieval_use='query',
             source_span=dict(start=18, end=29, text='Asian women'), terms=[dict(id='t2', text='Asian women', state='approved')]),
        dict(id='sea', label='Southeast Asia', role='geography', requirement='preferred', retrieval_use='screen_later',
             terms=[dict(id='t3', text='Southeast Asia', state='approved')])], variants=[
        dict(id='focused', label='Focused', kind='focused', expression=dict(op='all_of', children=[
            dict(op='concept_ref', concept_id='microbiome'), dict(op='concept_ref', concept_id='women')]))]))


def test_compilation_is_deterministic_without_blanket_field_tags():
    compiled = compile_search_plan(draft())
    value = compiled.candidates[0]
    assert value.status == 'ready_for_approval'
    assert value.query == '((gut microbiome) AND (Asian women))'
    assert '[Title/Abstract]' not in value.query
    assert value.candidate_sha256 == compile_search_plan(draft()).candidates[0].candidate_sha256


@pytest.mark.parametrize('syntax', ['x OR y', '"women"', 'x[MeSH Terms]', 'x\n', 'x:y', 'x(y)'])
def test_structured_terms_cannot_smuggle_syntax(syntax):
    value = draft().model_dump(mode='json')
    value['concepts'][0]['terms'][0]['text'] = syntax
    compiled = compile_search_plan(SearchPlanDraft.model_validate(value))
    assert compiled.candidates[0].status == 'blocked'
    assert 'structured_term_contains_syntax' in {item.code for item in compiled.candidates[0].issues}


def test_explicit_field_does_not_change_preferred_constraints():
    value = draft().model_dump(mode='json')
    value['concepts'][0]['terms'][0]['field'] = 'title_abstract'
    compiled = compile_search_plan(SearchPlanDraft.model_validate(value))
    assert '"gut microbiome"[Title/Abstract]' in compiled.candidates[0].query
    assert 'Southeast Asia' not in compiled.candidates[0].query


def test_required_nonquery_constraint_is_visible_and_acknowledgeable():
    value = draft().model_dump(mode='json')
    value['concepts'][1]['retrieval_use'] = 'screen_later'
    value['variants'][0].update(expression=dict(op='concept_ref', concept_id='microbiome'),
                               deferred_concept_ids=['women'], deferral_reason='Explicitly assess ancestry during screening')
    compiled = compile_search_plan(SearchPlanDraft.model_validate(value)).candidates[0]
    assert compiled.status == 'ready_for_approval'
    assert compiled.deferred_required_ids == ['women']
    assert 'Asian women' in compiled.deferred_constraints[0]


def test_edited_ambiguity_and_term_provenance_invalidate_candidate_hash():
    old = draft()
    value = old.model_dump(mode='json')
    value['concepts'][0]['terms'][0]['provenance_note'] = 'Researcher reviewed local terminology'
    assert compile_search_plan(old).candidates[0].candidate_sha256 != compile_search_plan(SearchPlanDraft.model_validate(value)).candidates[0].candidate_sha256


def test_manual_strategy_stays_exact_with_separate_filters():
    query = '  ("x"[tiab] OR y[MeSH Terms])\r\n AND z  '
    plan = SearchPlanDraft(original_question='', input_mode='manual_strategy', manual_strategy=query,
                           sort='pub_date', date_filter=dict(date_from='2020-01-01', date_to='2024-12-31'))
    candidate = compile_search_plan(plan).candidates[0]
    assert candidate.query == query
    assert candidate.date_from == '2020-01-01' and candidate.sort == 'pub_date'
    assert candidate.unparsed_constraints
    assert candidate.status == 'ready_for_approval'
