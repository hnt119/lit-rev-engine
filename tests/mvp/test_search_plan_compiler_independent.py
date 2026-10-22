"""Independent intent/compiler invariants, with no provider or model execution."""
import socket

import pytest
from pydantic import ValidationError

from src.mvp.search_plan_compiler import compile_search_plan
from src.mvp.search_plan_contracts import (PlanExpression, QuestionSpan, SearchConcept, SearchDateFilter,
    SearchPlanDraft, SearchTerm, SearchVariant)

QUESTION = "Does gut microbiome affect reproductive longevity in women originating from Asia? Southeast Asia is preferred. Exclude animals."


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Search intent compilation attempted network access")
    monkeypatch.setattr(socket, "create_connection", denied)


def ref(identifier):
    return PlanExpression(op="concept_ref", concept_id=identifier)


def all_of(*children):
    return PlanExpression(op="all_of", children=list(children))


def concept(identifier, text, role, requirement="required", retrieval_use="query", question=QUESTION):
    start = question.index(text)
    span = QuestionSpan(start=start, end=start + len(text), text=text)
    return SearchConcept(id=identifier, label=text, role=role, requirement=requirement, retrieval_use=retrieval_use, source_span=span,
        terms=[SearchTerm(id=identifier + "-term", text=text, field="title_abstract", origin="verbatim", state="approved", source_span=span)])


def draft():
    concepts = [concept("topic", "gut microbiome", "topic"), concept("outcome", "reproductive longevity", "outcome"),
        concept("women", "women", "population"), concept("origin", "Asia", "geography"),
        concept("sea", "Southeast Asia", "geography", "preferred", "rank_only"), concept("animals", "animals", "study_design", "excluded")]
    expression = all_of(ref("topic"), ref("outcome"), ref("women"), ref("origin"), PlanExpression(op="not", children=[ref("animals")]))
    return SearchPlanDraft(original_question=QUESTION, concepts=concepts,
        variants=[SearchVariant(id="focused", label="Focused", kind="focused", expression=expression)])


def candidate(value, identifier="focused"):
    result = compile_search_plan(value)
    return next(item for item in result.candidates if item.id == identifier)


def test_raw_specialist_strategy_preserves_every_crlf_and_space_with_separate_filters():
    raw = ' \r\n(("gut microbiota"[tiab]) AND (women[MeSH Terms] OR female*[tiab]))\r\n NOT animals[MeSH Terms]  \r\n'
    value = SearchPlanDraft(original_question="Researcher-authored specialist strategy", input_mode="manual_strategy", manual_strategy=raw,
        date_filter=SearchDateFilter(date_from="2010-01-01", date_to="2025-12-31"), sort="pub_date")
    result = compile_search_plan(value)
    assert len(result.candidates) == 1
    result = result.candidates[0]
    assert result.query.encode("utf-8") == raw.encode("utf-8")
    assert (result.date_from, result.date_to, result.sort) == ("2010-01-01", "2025-12-31", "pub_date")
    assert result.unparsed_constraints, "Preserving a raw specialist strategy must not claim structured intent/MeSH validation"


def test_raw_strategy_can_use_the_full_twenty_thousand_character_query_budget():
    raw = "\r\n" + " OR ".join(f"topic{index}[tiab]" for index in range(700)) + "  \r\n"
    assert 10000 < len(raw) < 20000
    result = compile_search_plan(SearchPlanDraft(original_question="Specialist input", input_mode="manual_strategy", manual_strategy=raw))
    assert result.candidates[0].query == raw


def test_required_asian_origin_population_is_retained_and_sea_preference_is_not_mandatory():
    result = candidate(draft())
    assert result.status == "ready_for_approval"
    assert {"topic", "outcome", "women", "origin", "animals"} <= set(result.included_concept_ids)
    assert "southeast asia" not in result.query.casefold()
    assert "women" in result.query.casefold() and "asia" in result.query.casefold() and " NOT " in result.query
    assert result.deferred_required_ids == result.deferred_excluded_ids == []


def test_merely_mentioning_two_required_groups_under_or_does_not_guarantee_either():
    value = draft()
    expression = all_of(ref("topic"), ref("outcome"), PlanExpression(op="any_of", children=[ref("women"), ref("origin")]),
        PlanExpression(op="not", children=[ref("animals")]))
    value = value.model_copy(update={"variants": [value.variants[0].model_copy(update={"expression": expression})]})
    result = candidate(value)
    assert result.status == "blocked"
    assert {"women", "origin"} <= set(result.deferred_required_ids) or any(issue.severity == "error" for issue in result.issues)


def test_or_of_conjunctive_branches_retains_only_their_shared_guarantees():
    value = draft()
    common = all_of(ref("topic"), ref("women"), ref("origin"), ref("outcome"), PlanExpression(op="not", children=[ref("animals")]))
    expression = PlanExpression(op="any_of", children=[common, common])
    result = candidate(value.model_copy(update={"variants": [value.variants[0].model_copy(update={"expression": expression})]}))
    assert result.status == "ready_for_approval" and result.deferred_required_ids == []


def test_each_variant_uses_its_own_expression_and_all_deferred_constraints_are_explicit():
    value = draft()
    broad = SearchVariant(id="broad", label="Broad", kind="broad", expression=all_of(ref("topic"), ref("women")),
        deferred_concept_ids=["origin", "outcome", "animals"], deferral_reason="These eligibility constraints require explicit screening after broader retrieval.")
    value = value.model_copy(update={"variants": [value.variants[0], broad]})
    focused, broader = candidate(value), candidate(value, "broad")
    assert focused.status == broader.status == "ready_for_approval"
    assert focused.query != broader.query and "asia" in focused.query.casefold() and "asia" not in broader.query.casefold()
    assert set(broader.deferred_required_ids) == {"origin", "outcome"}
    assert broader.deferred_excluded_ids == ["animals"] and broader.deferred_constraints
    unacknowledgeable = broad.model_copy(update={"deferred_concept_ids": ["origin", "outcome"]})
    assert candidate(value.model_copy(update={"variants": [unacknowledgeable]}), "broad").status == "blocked"


def test_subquestion_requires_an_explanation_and_separate_split_approval():
    value = draft()
    sub = SearchVariant(id="sub", label="Subquestion", kind="subquestion", expression=all_of(ref("topic"), ref("women")),
        deferred_concept_ids=["origin", "outcome", "animals"], deferral_reason="Explicitly deferred to screening.")
    assert candidate(value.model_copy(update={"variants": [sub]}), "sub").status == "blocked"
    explained = sub.model_copy(update={"split_explanation": "Researcher must decide whether this separated question still answers the intended joint relationship."})
    result = candidate(value.model_copy(update={"variants": [explained]}), "sub")
    assert result.status == "ready_for_approval" and result.requires_split_approval


def test_preference_needs_explicit_promotion_and_reason_to_become_a_filter():
    value = draft()
    expression = all_of(*value.variants[0].expression.children, ref("sea"))
    variant = value.variants[0].model_copy(update={"expression": expression})
    assert candidate(value.model_copy(update={"variants": [variant]})).status == "blocked"
    promoted = [group.model_copy(update={"promoted_to_query": True, "promotion_reason": "Researcher explicitly restricts this focused variant.",
        "retrieval_use": "query"}) if group.id == "sea" else group for group in value.concepts]
    result = candidate(value.model_copy(update={"concepts": promoted, "variants": [variant]}))
    assert result.status == "ready_for_approval" and "southeast asia" in result.query.casefold()


def test_structured_mesh_is_not_validated_by_human_term_approval():
    value = draft()
    groups = [group.model_copy(update={"terms": [group.terms[0].model_copy(update={"field": "mesh", "state": "approved"})]})
        if group.id == "topic" else group for group in value.concepts]
    result = compile_search_plan(value.model_copy(update={"concepts": groups}))
    assert result.terminology_status == "no_server_mesh_registry"
    assert result.candidates[0].status == "blocked"
    assert any(issue.severity == "error" for issue in result.candidates[0].issues)
    with pytest.raises(ValidationError):
        SearchTerm.model_validate({**groups[0].terms[0].model_dump(), "mesh_validated": True})


def test_unicode_spans_use_original_codepoints_and_are_not_normalized_before_validation():
    question = "🧬 Does sérotonin affect women’s sleep?"
    group = concept("sleep", "women’s sleep", "outcome", question=question)
    value = SearchPlanDraft(original_question=question, concepts=[group], variants=[SearchVariant(id="one", label="One", kind="focused", expression=ref("sleep"))])
    assert candidate(value, "one").status == "ready_for_approval"
    wrong = group.source_span.model_copy(update={"start": group.source_span.start + 3, "end": group.source_span.end + 3})
    invalid = value.model_copy(update={"concepts": [group.model_copy(update={"source_span": wrong})]})
    result = candidate(invalid, "one")
    assert result.status == "blocked" and any(issue.severity == "error" for issue in result.issues)


@pytest.mark.parametrize("problem", ["duplicate_concept", "unknown_reference", "negated_required", "unapproved_term", "unresolved_comparison"])
def test_ambiguous_or_unreviewed_intent_cannot_silently_compile(problem):
    from src.mvp.search_plan_contracts import PlanAmbiguity
    value = draft()
    if problem == "duplicate_concept": value = value.model_copy(update={"concepts": [*value.concepts, value.concepts[0]]})
    elif problem == "unknown_reference": value = value.model_copy(update={"variants": [value.variants[0].model_copy(update={"expression": ref("unknown")})]})
    elif problem == "negated_required": value = value.model_copy(update={"variants": [value.variants[0].model_copy(update={"expression": PlanExpression(op="not", children=[ref("women")])})]})
    elif problem == "unapproved_term": value = value.model_copy(update={"concepts": [group.model_copy(update={"terms": [term.model_copy(update={"state": "proposed"}) for term in group.terms]}) for group in value.concepts]})
    else: value = value.model_copy(update={"ambiguities": [PlanAmbiguity(id="comparison", message="A head-to-head comparator relationship remains unresolved.", concept_ids=["topic", "outcome"])]})
    result = compile_search_plan(value)
    assert result.candidates[0].status == "blocked"


def test_compound_not_shape_and_excessive_ast_depth_are_explicitly_rejected():
    with pytest.raises(ValidationError):
        PlanExpression(op="not", children=[all_of(ref("women"), ref("origin"))])
    value = draft()
    expression = value.variants[0].expression
    for _ in range(10):
        expression = all_of(ref("topic"), expression)
    result = candidate(value.model_copy(update={"variants": [value.variants[0].model_copy(update={"expression": expression})]}))
    assert result.status == "blocked"


@pytest.mark.parametrize("text", ["women OR men", "women[All Fields]", "women) OR (men", "women\nmen"])
def test_structured_terms_cannot_inject_syntax_outside_the_explicit_expression(text):
    value = draft()
    groups = [group.model_copy(update={"terms": [group.terms[0].model_copy(update={"text": text, "field": "text", "origin": "manual", "source_span": None})]})
        if group.id == "topic" else group for group in value.concepts]
    result = candidate(value.model_copy(update={"concepts": groups}))
    assert result.status == "blocked" and any(issue.code == "structured_term_contains_syntax" for issue in result.issues)


def test_empty_intent_is_explicitly_invalid_and_large_queries_are_not_truncated():
    empty = compile_search_plan(SearchPlanDraft(original_question=""))
    assert not empty.candidates and any(issue.severity == "error" for issue in empty.issues)
    groups = [SearchConcept(id=f"c{index}", label=f"Manual concept {index}", role="other", requirement="required", retrieval_use="query",
        terms=[SearchTerm(id=f"t{term}", text="a" * 1000, origin="manual", state="approved") for term in range(8)]) for index in range(12)]
    value = SearchPlanDraft(original_question="Explicitly authored bounded software test concepts", concepts=groups,
        variants=[SearchVariant(id="large", label="Large", kind="focused", expression=all_of(*(ref(group.id) for group in groups)))])
    result = candidate(value, "large")
    assert result.status == "blocked" and len(result.query) > 20000
    assert set(result.included_concept_ids) == {group.id for group in groups}


def test_unfamiliar_joint_exposure_and_comparison_plan_has_explicit_distinct_variants():
    question = "Does satellite aerosol monitoring and traffic noise affect sleep among city nurses compared with rural nurses? Exclude shift workers."
    def group(identifier, text, role="other", requirement="required", retrieval_use="query"):
        start = question.index(text)
        span = QuestionSpan(start=start, end=start + len(text), text=text)
        return SearchConcept(id=identifier, label=text, role=role, requirement=requirement, retrieval_use=retrieval_use,
            source_span=span, terms=[SearchTerm(id=identifier, text=text, field="title_abstract", origin="verbatim", state="approved", source_span=span)])
    groups = [group("aerosol", "satellite aerosol monitoring", "exposure"), group("noise", "traffic noise", "exposure"),
        group("sleep", "sleep", "outcome"), group("nurses", "city nurses", "population"),
        group("comparison", "rural nurses", "comparator", retrieval_use="screen_later"),
        group("excluded", "shift workers", requirement="excluded")]
    negative = PlanExpression(op="not", children=[ref("excluded")])
    focused = SearchVariant(id="joint", label="Joint exposures", kind="focused",
        expression=all_of(ref("aerosol"), ref("noise"), ref("sleep"), ref("nurses"), negative),
        deferred_concept_ids=["comparison"], deferral_reason="Comparison eligibility is checked during screening.")
    broad = SearchVariant(id="alternatives", label="Explicit alternative exposure discovery", kind="broad",
        expression=all_of(PlanExpression(op="any_of", children=[ref("aerosol"), ref("noise")]), ref("sleep"), ref("nurses"), negative),
        deferred_concept_ids=["aerosol", "noise", "comparison"], deferral_reason="This explicitly relaxes the joint exposure and leaves comparator eligibility to screening.")
    split = SearchVariant(id="split", label="Aerosol subquestion", kind="subquestion",
        expression=all_of(ref("aerosol"), ref("sleep"), ref("nurses"), negative), deferred_concept_ids=["noise", "comparison"],
        deferral_reason="The other exposure and comparator are deferred.", split_explanation="Researcher must accept studying an exposure separately from the original joint relationship.")
    result = compile_search_plan(SearchPlanDraft(original_question=question, concepts=groups, variants=[focused, broad, split]))
    joint, alternatives, separated = result.candidates
    assert all(item.status == "ready_for_approval" for item in result.candidates)
    assert joint.query != alternatives.query != separated.query and " OR " not in joint.query and " OR " in alternatives.query
    assert joint.deferred_required_ids == ["comparison"] and set(alternatives.deferred_required_ids) == {"aerosol", "noise", "comparison"}
    assert separated.requires_split_approval and set(separated.deferred_required_ids) == {"noise", "comparison"}


@pytest.mark.parametrize("start,end", [("2025-01-01", "2010-12-31"), ("2010-01-01", "not-a-date")])
def test_date_restrictions_are_validated_instead_of_rewritten(start, end):
    with pytest.raises(ValidationError):
        SearchDateFilter(date_from=start, date_to=end)
