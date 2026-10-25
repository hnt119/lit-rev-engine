"""Independent offline acceptance probes for the editable keyword proposal.

These verify retained concepts and safe proposal behavior, not search relevance.
"""

import re
import socket

import pytest

from src.mvp.query_suggestions import suggest_pubmed_query


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*_args, **_kwargs):
        pytest.fail("Keyword proposal unexpectedly attempted a network connection")

    monkeypatch.setattr(socket, "create_connection", denied)


def test_full_research_question_retains_every_named_research_concept():
    question = (
        "gut microbiome in Asian women and how it affects reproductive longevity, "
        "healthy aging, gynecological diseases and whether or not diet or exposome "
        "affects their gut microbiome"
    )
    result = suggest_pubmed_query(question)
    query = result.query.casefold()
    for concept in (
        "gut microbiome", "asian", "women", "reproductive longevity", "healthy aging",
        "gynecological diseases", "diet", "exposome",
    ):
        assert concept in query
    assert query.count("gut microbiome") == 1
    assert "(diet or exposome)" in query
    assert "not" not in query.split()
    assert all(token not in query for token in ("chinese", "japanese", "thai", "[", '"'))
    assert len(query) < 300
    assert "no live pubmed call" in result.explanation.casefold()


@pytest.mark.parametrize("possessive", ["women's", "women’s"])
def test_possessive_population_does_not_create_a_mandatory_s_keyword(possessive):
    result = suggest_pubmed_query(
        f"How does the gut microbiome affect Asian {possessive} reproductive health?"
    )
    assert "women" in result.query.casefold()
    assert "reproductive health" in result.query.casefold()
    assert not re.search(r"(?:\bAND\s+|\()s(?:\s+AND\b|\)|$)", result.query)


@pytest.mark.parametrize("preference", [
    "; Southeast Asian studies are preferred",
    ", preferably Southeast Asia",
    " with a preference for Southeast Asian studies",
    ", Southeast Asian studies preferred",
    " (prefer Southeast Asia)",
])
def test_regional_preference_does_not_harden_the_broader_population(preference):
    result = suggest_pubmed_query("Gut microbiome in Asian women" + preference)
    # Keeping a preference as an editable OR alternative is acceptable; a new
    # mandatory regional group silently changes the question's scope.
    query = result.query.casefold()
    assert not re.search(r"\band\s+\(?southeast asia", query)
    assert "prefer" in result.explanation.casefold()


@pytest.mark.parametrize(("question", "retained", "forbidden"), [
    (
        "Can exercise improve sleep after surgery?",
        ("exercise", "sleep", "surgery"),
        ("can", "improve", "after"),
    ),
    (
        "How does bruxism affect sleep?",
        ("bruxism", "sleep"),
        ("how", "does", "affect"),
    ),
    (
        "What diet best promotes healthy aging?",
        ("diet", "healthy aging"),
        ("what", "best", "promotes"),
    ),
    (
        "Gut microbiome among women recruited in Singapore",
        ("gut microbiome", "women", "singapore"),
        ("among", "recruited", "asian"),
    ),
])
def test_general_keywords_without_question_framing(question, retained, forbidden):
    query = suggest_pubmed_query(question).query.casefold()
    for concept in retained:
        assert concept in query
    words = set(re.findall(r"\w+", query))
    assert not words.intersection(forbidden)


def test_explicit_alternatives_are_not_separate_mandatory_groups():
    query = suggest_pubmed_query(
        "Does diet or exposome affect ovarian aging or ovarian ageing "
        "in Southeast Asian women?"
    ).query.casefold()
    assert "(diet or exposome)" in query
    assert "(ovarian aging) or (ovarian ageing)" in query
    assert "southeast asian" in query
    assert "central asian" not in query


def test_raw_or_is_preserved_for_unfamiliar_or_different_role_concepts():
    query = suggest_pubmed_query("Exercise for sleep or surgery").query.casefold()
    assert "(sleep or surgery)" in query


def test_negative_population_scope_has_an_explicit_limitation():
    result = suggest_pubmed_query("Gut microbiota in non-Asian women")
    assert "negation" in result.explanation.casefold()
    assert "manually" in result.explanation.casefold()


@pytest.mark.parametrize("question", [
    "What is the evidence?", "Please find research studies", "How does it affect them?",
])
def test_insufficient_input_does_not_create_a_filler_query(question):
    result = suggest_pubmed_query(question)
    assert result.query == ""
    assert "no substantive keywords" in result.explanation.casefold()


@pytest.mark.parametrize("query", [
    '  ("gut microbiota"[tiab] OR diet[Title/Abstract])\nAND women[MeSH Terms]  ',
    "  bruxism AND sleep OR headache\n",
    '"gut microbiome women Asian"[Title/Abstract:~3]',
])
def test_explicit_strategy_stays_byte_identical(query):
    assert suggest_pubmed_query(query).query.encode() == query.encode()


def test_output_is_deterministic_with_balanced_operator_groups():
    question = "Diet, intestinal microbiome and healthy aging in Southeast Asian women"
    first = suggest_pubmed_query(question)
    assert suggest_pubmed_query(question) == first
    assert first.query.count("(") == first.query.count(")")
    assert not re.search(r"\(\s*\)|\b(?:AND|OR)\s*\)|\b(?:AND|OR)\s*$", first.query)
