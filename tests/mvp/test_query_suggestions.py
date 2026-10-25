"""Offline parser regressions, not validation of retrieval quality or recall."""

import socket

import pytest

from src.mvp.contracts import CreateWorkspaceRequest, QuerySuggestionRequest, WorkspaceHandle
from src.mvp.ports import MvpError
from src.mvp.query_suggestions import suggest_pubmed_query


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Query suggestions must not make network calls")
    monkeypatch.setattr(socket, "create_connection", denied)


def test_actual_default_extracts_minimum_concepts_instead_of_question_framing():
    result = suggest_pubmed_query(
        "What does this source report about diet, gut microbiota, and gestational diabetes "
        "among the studied Chinese pregnant women?"
    )
    assert result.query == "diet AND (gut microbiota) AND (gestational diabetes) AND Chinese AND (pregnant women)"
    assert "Keywords retained" in result.explanation
    assert "Question framing was removed" in result.explanation
    assert "has not been validated" in result.explanation
    assert "no live PubMed call" in result.explanation
    assert result.method == "transparent-template-v1"
    assert '"' not in result.query and "[" not in result.query


@pytest.mark.parametrize(("question", "query"), [
    ("How does gut microbiota affect reproductive longevity in Asian women?",
     "(gut microbiota) AND (reproductive longevity) AND Asian AND women"),
    ("Diet, intestinal microbiome and healthy aging in Southeast Asian women",
     "Diet AND (intestinal microbiome) AND (healthy aging) AND (Southeast Asian) AND women"),
    ("Gut flora in females originating from Southeast Asia",
     "(Gut flora) AND females AND (Southeast Asia)"),
    ("Gastrointestinal microbiota in an Asian woman",
     "(Gastrointestinal microbiota) AND Asian AND woman"),
    ("The gut-microbiome in women from Asia", "(gut microbiome) AND women AND Asia"),
    ("  Can exercise improve sleep after surgery?\n", "exercise AND sleep AND surgery"),
    ("Gut microbiota in Chinese women", "(Gut microbiota) AND Chinese AND women"),
    ("Gut microbiome among women recruited in Singapore", "(Gut microbiome) AND women AND Singapore"),
    ("Microbiome in Asian women", "Microbiome AND Asian AND women"),
    ("Gut flora in Asia", "(Gut flora) AND Asia"),
    ("What is the association between bruxism and sleep apnea in Southeast Asian women?",
     "bruxism AND (sleep apnea) AND (Southeast Asian) AND women"),
    ("How does β glucan affect gut microbiota in Japanese women?",
     "(β glucan) AND (gut microbiota) AND Japanese AND women"),
    ("What diet best promotes healthy aging?", "diet AND (healthy aging)"),
    ("Asian women’s reproductive health", "Asian AND women AND (reproductive health)"),
    ("Asian women's reproductive health", "Asian AND women AND (reproductive health)"),
])
def test_minimum_keywords_retain_explicit_concepts_without_inventing_expansions(question, query):
    result = suggest_pubmed_query(question)
    assert result.query == query
    assert "No synonyms, countries, or MeSH terms were added" in result.explanation
    assert "not a complete systematic-review strategy" in result.explanation
    assert '"' not in result.query and "[" not in result.query


def test_original_broad_question_keeps_outcomes_and_exposures_and_soft_regional_preference():
    result = suggest_pubmed_query(
        "How does the gut microbiome relate to reproductive longevity, healthy aging and "
        "gynecological disease in women originating from Asia, and what roles do diet and "
        "other exposome factors have? Southeast Asian studies are preferred."
    )
    assert result.query == (
        "(gut microbiome) AND ((reproductive longevity) OR (healthy aging) OR "
        "(gynecological disease)) AND women AND Asia AND (diet OR exposome)"
    )
    assert "Southeast Asian studies are preferred" in result.explanation
    assert "not mandatory search restrictions" in result.explanation
    assert "Southeast" not in result.query


def test_explicit_or_and_same_role_lists_are_alternatives_not_separate_mandatory_words():
    result = suggest_pubmed_query("Could diet or exposome affect ovarian aging or ovarian ageing in Chinese or Japanese women?")
    assert result.query == "(diet OR exposome) AND ((ovarian aging) OR (ovarian ageing)) AND (Chinese OR Japanese) AND women"
    assert "OR joins nearby listed alternatives" in result.explanation
    assert suggest_pubmed_query("bruxism or sleep apnea in women").query == "(bruxism OR (sleep apnea)) AND women"


def test_longest_phrases_protect_nested_terms_and_hyphens():
    result = suggest_pubmed_query("Does gut–microbiome affect healthy ageing and gestational diabetes in pregnant women?")
    assert result.query == "(gut microbiome) AND ((healthy ageing) OR (gestational diabetes)) AND (pregnant women)"


def test_repeated_concepts_are_deduplicated_case_insensitively():
    assert suggest_pubmed_query("gut microbiota and Gut Microbiota in women and WOMEN").query == "(gut microbiota) AND women"


def test_does_not_drop_unknown_medical_concepts_or_apply_arbitrary_word_cap():
    terms = [f"biomarker{index}" for index in range(25)]
    query = suggest_pubmed_query("What is the relationship of " + ", ".join(terms) + " in women?").query
    assert query == " AND ".join([*terms, "women"])


def test_overlong_expansion_refuses_whole_proposal_instead_of_silently_dropping_concepts():
    question = ",".join(chr(0x4E00 + index) for index in range(3500))
    assert len(question) < 10000
    result = suggest_pubmed_query(question)
    assert result.query == ""
    assert "20,000-character search limit" in result.explanation
    assert "Reduce or split" in result.explanation
    assert "no concepts were silently truncated" in result.explanation


@pytest.mark.parametrize("question", [
    "", "   ", "What does this source report about?", "Can you please tell me about the research question?",
])
def test_filler_only_proposal_is_empty_and_explained(question):
    result = suggest_pubmed_query(question)
    assert result.query == ""
    assert "No substantive keywords" in result.explanation
    assert "No live PubMed call" in result.explanation


@pytest.mark.parametrize("question", [
    "Gut microbiota in Asian women; Southeast Asian studies are preferred",
    "Gut microbiota in Asian women, preferably Southeast Asian",
])
def test_trailing_geographic_preference_does_not_harden_into_mandatory_restriction(question):
    result = suggest_pubmed_query(question)
    assert result.query == "(Gut microbiota) AND Asian AND women"
    assert "Southeast Asian" in result.explanation
    assert "Preference notes" in result.explanation


def test_required_specific_region_is_retained_without_broadening():
    result = suggest_pubmed_query("Gut microbiota in Southeast Asian women")
    assert result.query == "(Gut microbiota) AND (Southeast Asian) AND women"
    assert "Chinese" not in result.query


@pytest.mark.parametrize("question", [
    "Gut microbiota in women without diabetes", "Gut microbiota in non-Asian women",
    "Whether or not diet affects gut microbiota in women without diabetes",
])
def test_natural_negation_does_not_silently_become_not_or_positive_filler(question):
    result = suggest_pubmed_query(question)
    assert "NOT" not in result.query
    assert "non AND" not in result.query
    assert "Negation was not translated into NOT" in result.explanation


def test_whether_or_not_idiom_alone_is_not_mistaken_for_an_exclusion():
    result = suggest_pubmed_query("Whether or not diet affects gut microbiota in women")
    assert result.query == "diet AND (gut microbiota) AND women"
    assert "Negation was not translated" not in result.explanation


def test_comparison_is_not_presented_as_a_semantic_search_translation():
    result = suggest_pubmed_query("Are probiotics better than metformin for polycystic ovary syndrome in women?")
    assert result.query == "probiotics AND metformin AND (polycystic ovary syndrome) AND women"
    assert "Comparison direction was not encoded" in result.explanation


@pytest.mark.parametrize("question", [
    '  ("gut microbiota"[tiab] OR estrobolome[Title/Abstract])\nAND "Asian People"[MeSH Terms]  ',
    'gut microbiome AND women OR equol',
    'gut microbiome NOT mice',
    '  "Female"[ mh ]\n',
    'gut microbiome[All Fields]',
    '2020:2026[dp]',
    'gut microbiota women Asian[mh:noexp]',
    'gut microbiota women Asian[Journal]',
    'gut microbiota women Asian[MeSH Major Topic]',
    '"gut microbiome women Asian"[Title/Abstract:~3]',
    'gut microbiota women Asian[custom unvalidated field]',
])
def test_structured_query_preserved_byte_for_byte(question):
    suggestion = suggest_pubmed_query(question)
    assert suggestion.query.encode("utf-8") == question.encode("utf-8")
    assert "preserved exactly" in suggestion.explanation
    assert "has not been validated" in suggestion.explanation
    assert "no live PubMed call" in suggestion.explanation


def test_service_preserves_workspace_authorization_and_does_not_call_providers(tmp_path):
    from src.mvp.adapters.storage import SQLiteWorkspaceStorage
    from src.mvp.service import MVPService

    class NoProviderCalls:
        def search(self, request):
            pytest.fail("Query suggestion invoked discovery")

        def prepare(self, paper):
            pytest.fail("Query suggestion invoked source preparation")

    storage = SQLiteWorkspaceStorage(tmp_path / "private" / "workspaces.sqlite3")
    service = MVPService(storage, NoProviderCalls(), NoProviderCalls())
    handle = service.create_workspace(CreateWorkspaceRequest(question="Original workspace question"))
    before = service.get_workspace(handle)
    suggestion = service.suggest_query(handle, QuerySuggestionRequest(question="Gut microbiota in Asian women"))
    assert suggestion == suggest_pubmed_query("Gut microbiota in Asian women")
    assert service.get_workspace(handle) == before
    with pytest.raises(MvpError):
        service.suggest_query(WorkspaceHandle(workspace_id=handle.workspace_id, token="wrong-token"),
                              QuerySuggestionRequest(question="Gut microbiota in Asian women"))
