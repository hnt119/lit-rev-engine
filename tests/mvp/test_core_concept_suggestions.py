"""Offline source-bound Core concepts; these tests make no scientific claims."""
from hashlib import sha256

import pytest
from pydantic import ValidationError

from src.mvp.core_concept_suggestions import CoreConceptSuggestionRequest, suggest_core_concepts
from src.mvp.search_plan_compiler import compile_search_plan


def test_multiword_entities_preferences_and_added_wording_are_unapproved():
    q='How does diet affect the gut microbiome in pregnant women, preferably Chinese participants?'
    result=suggest_core_concepts(q)
    assert result.generator_version=='mvp.core-concept-suggestions.v1'
    assert result.question_sha256==sha256(q.encode()).hexdigest()
    concepts={c.label:c for c in result.draft.concepts}
    assert {'diet','gut microbiome','pregnant women','Chinese'} <= concepts.keys()
    assert concepts['Chinese'].requirement=='preferred'
    assert concepts['Chinese'].retrieval_use=='screen_later'
    assert concepts['gut microbiome'].requirement=='unresolved'
    terms=concepts['gut microbiome'].terms
    assert terms[0].origin=='verbatim' and terms[0].source_span.text=='gut microbiome'
    assert terms[1].text=='gut microbiota' and terms[1].origin=='terminology' and terms[1].source_span is None
    assert all(t.state=='proposed' for c in concepts.values() for t in c.terms)
    assert not result.draft.variants, 'AND relationships need a separate researcher review action'
    compiled=compile_search_plan(result.draft)
    assert not compiled.candidates
    assert 'unapproved_term' in {i.code for i in compiled.issues}


def test_unicode_source_spans_are_never_nfkc_or_utf16_normalized():
    q='🧬 How does 日本 lichen’s pigments affect ovarian ageing in women?'
    result=suggest_core_concepts(q)
    assert result.draft.original_question==q
    for c in result.draft.concepts:
        assert q[c.source_span.start:c.source_span.end]==c.source_span.text==c.label
        for t in c.terms:
            if t.origin=='verbatim':assert q[t.source_span.start:t.source_span.end]==t.text
    assert any('日本' in c.label for c in result.draft.concepts)
    assert not any(i.code=='source_span_mismatch' for i in compile_search_plan(result.draft).issues)


@pytest.mark.parametrize('q',[
 '  ("gut microbiome"[tiab] OR 日本[Title/Abstract])\r\nAND women[tiab] NOT mice[MeSH Terms]  ',
 'What is known about "ovarian ageing"?',
 '  αβ[tiab] OR (γ[tiab] AND δ[tiab])\r  ',
])
def test_specialist_grouping_fields_quotes_unicode_and_whitespace_are_preserved(q):
    result=suggest_core_concepts(q)
    assert result.draft.input_mode=='manual_strategy'
    assert result.draft.manual_strategy==q
    assert not result.draft.concepts
    assert compile_search_plan(result.draft).candidates[0].query==q
    assert 'unparsed' in ' '.join(result.notices)


def test_supported_specialized_roles_are_suggestions_with_compatible_draft_roles():
    q='Compare hormone replacement therapy versus placebo using plasma samples and metabolic pathways in randomized controlled trials.'
    result=suggest_core_concepts(q)
    roles={c.proposed_role for c in result.proposed_roles}
    assert {'intervention','comparator','specimen_site','investigation_focus','study_design'} <= roles
    actual={c.label:c for c in result.draft.concepts}
    assert actual['hormone replacement therapy'].role=='exposure'
    assert actual['plasma samples'].role=='other'
    assert actual['randomized controlled trials'].retrieval_use=='screen_later'
    assert 'not scientifically or terminologically validated' in result.notices[0]


def test_negation_cannot_be_silently_reinterpreted_as_positive_or_not():
    result=suggest_core_concepts('Find gut microbiome evidence without antibiotics in women.')
    assert not result.draft.variants
    assert all(c.requirement!='excluded' and c.retrieval_use=='screen_later' for c in result.draft.concepts)
    assert result.draft.ambiguities and not result.draft.ambiguities[0].resolved
    assert 'unresolved_ambiguity' in {i.code for i in compile_search_plan(result.draft).issues}


def test_unknown_terms_and_bounds_are_honest_and_not_silently_truncated():
    unknown=suggest_core_concepts('How does quasarfilin signaling affect women?')
    assert any(c.role=='unresolved' and c.label=='quasarfilin signaling' for c in unknown.draft.concepts)
    excessive=suggest_core_concepts(' and '.join('unfamiliarterm'+str(i) for i in range(14)))
    assert not excessive.draft.concepts
    assert any('No concepts were silently discarded' in note for note in excessive.notices)
    empty=suggest_core_concepts('What does this source report about?')
    assert not empty.draft.concepts
    with pytest.raises(ValidationError):CoreConceptSuggestionRequest(original_question='x'*10001)


def test_repeated_suggestions_are_deterministic():
    q='How do diet and exercise affect gut microbiome in older women?'
    assert suggest_core_concepts(q).model_dump()==suggest_core_concepts(q).model_dump()


def test_unfamiliar_hyphenated_scientific_entities_remain_whole_with_uncertain_role():
    q='How does β-catenin signaling affect IL-6 in women?'
    result=suggest_core_concepts(q)
    labels={c.label:c for c in result.draft.concepts}
    assert 'β-catenin signaling' in labels and 'IL-6' in labels
    assert labels['β-catenin signaling'].role=='unresolved'
    assert all(q[c.source_span.start:c.source_span.end]==c.label for c in labels.values())


def test_combining_mark_entities_keep_exact_non_normalized_unicode():
    q='How does cafe\u0301 signaling affect women?'
    result=suggest_core_concepts(q)
    concept=next(c for c in result.draft.concepts if c.role=='unresolved')
    assert concept.label=='cafe\u0301 signaling'
    assert concept.terms[0].text==q[concept.source_span.start:concept.source_span.end]
    assert 'café' not in concept.label
