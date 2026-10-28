"""Versioned, offline concept starting points. Never execute or approve a query.

This reuses the Core phrase extractor, retaining code-point spans in the original
question. The small wording table offers explicitly added candidates, not a
terminology service, scientific interpretation or validated MeSH mapping.
"""
from hashlib import sha256
import re
import unicodedata
from typing import Literal

from pydantic import Field, field_validator

from .contracts import Model
from .query_suggestions import _Concept, _extract, _FIELD_TAG, _BOOLEAN, _NEGATION, _separate_preferences
from .search_plan_contracts import MAX_CONCEPTS, QuestionSpan, SearchConcept, SearchPlanDraft, SearchTerm

GENERATOR_VERSION = 'mvp.core-concept-suggestions.v1'


class CoreConceptSuggestionRequest(Model):
    original_question: str = Field(min_length=1, max_length=10000)

    @field_validator('original_question')
    @classmethod
    def unicode(cls, value):
        value.encode('utf-8')
        return value


class ProposedConceptRole(Model):
    concept_id: str
    proposed_role: Literal['topic', 'population', 'exposure', 'intervention', 'comparator',
                           'outcome', 'specimen_site', 'geography', 'study_design',
                           'investigation_focus', 'unresolved']
    explanation: str


class CoreConceptSuggestion(Model):
    schema_version: Literal['mvp.core-concept-suggestion.v1'] = 'mvp.core-concept-suggestion.v1'
    generator_version: Literal['mvp.core-concept-suggestions.v1'] = GENERATOR_VERSION
    question_sha256: str
    draft: SearchPlanDraft
    proposed_roles: list[ProposedConceptRole] = Field(default_factory=list, max_length=MAX_CONCEPTS)
    notices: list[str]
    meaning: Literal['deterministic_suggestions_need_review'] = 'deterministic_suggestions_need_review'


# These are lexical patterns, not medical classifications. Unknown entities are
# retained as residual phrases with an unresolved role instead of being guessed.
_EXTRA = {
    'intervention': (r'(?:hormone|hormonal)\s+(?:replacement\s+)?therapy', r'cognitive\s+behavio[u]?ral\s+therapy',
                     r'probiotic\s+(?:supplementation|intervention)', r'prebiotic\s+supplementation'),
    'comparator': (r'placebo', r'usual\s+care', r'standard\s+(?:care|treatment)', r'untreated\s+controls?'),
    'specimen_site': (r'(?:fecal|faecal|stool|plasma|serum|blood|saliva|salivary|vaginal|urine)\s+(?:samples?|specimens?)',
                      r'(?:gut|intestinal|oral|vaginal)\s+(?:tissue|samples?)'),
    'study_design': (r'randomi[sz]ed\s+(?:controlled\s+)?trials?', r'(?:prospective|retrospective|longitudinal)\s+cohort\s+stud(?:y|ies)',
                     r'case[- ]control\s+stud(?:y|ies)', r'cross[- ]sectional\s+stud(?:y|ies)',
                     r'observational\s+stud(?:y|ies)', r'systematic\s+reviews?', r'meta[- ]analys(?:is|es)'),
    'investigation_focus': (r'dose[- ]response', r'biological\s+mechanisms?', r'mechanisms?', r'metabolic\s+pathways?',
                           r'adverse\s+(?:events?|effects?)', r'follow[- ]up\s+duration', r'long[- ]term\s+effects?'),
}
_EXTRA_PATTERNS = [(role, re.compile(r'(?<!\w)(?:' + pattern + r')(?!\w)', re.I))
                   for role, patterns in _EXTRA.items() for pattern in patterns]
_WORDING = {
    'gut microbiome': ('gut microbiota',), 'gut microbiota': ('gut microbiome',),
    'intestinal microbiome': ('intestinal microbiota',), 'intestinal microbiota': ('intestinal microbiome',),
    'ovarian aging': ('ovarian ageing',), 'ovarian ageing': ('ovarian aging',),
    'reproductive aging': ('reproductive ageing',), 'reproductive ageing': ('reproductive aging',),
    'fiber intake': ('fibre intake',), 'fibre intake': ('fiber intake',),
    'high fiber diet': ('high fibre diet',), 'high fibre diet': ('high fiber diet',),
    'randomized controlled trial': ('randomised controlled trial',),
    'randomised controlled trial': ('randomized controlled trial',),
    'fecal samples': ('faecal samples',), 'faecal samples': ('fecal samples',),
}
_ROLE_MAP = {'keyword': 'unresolved', 'intervention': 'exposure', 'specimen_site': 'other', 'investigation_focus': 'other'}


def _phrases(question):
    extra = [_Concept(m.group(), role, m.start(), m.end()) for role, pattern in _EXTRA_PATTERNS
             for m in pattern.finditer(question)]
    # Mask extra phrases before calling the existing extractor. Offsets stay in
    # the original string; no Unicode or whitespace normalization is performed.
    chosen = []
    for item in sorted(extra, key=lambda x: (-(x.end-x.start), x.start)):
        if not any(item.start < old.end and old.start < item.end for old in chosen): chosen.append(item)
    chars = list(question)
    for item in chosen: chars[item.start:item.end] = ' ' * (item.end-item.start)
    found = sorted([*chosen, *_extract(''.join(chars))], key=lambda x: x.start)
    merged = []
    for item in found:
        end = item.end
        while end < len(question) and unicodedata.category(question[end]).startswith('M'):
            end += 1
        item = _Concept(question[item.start:end], item.kind, item.start, end)
        if merged and item.kind == merged[-1].kind == 'keyword' and re.fullmatch(r'(?:\s+|[\-‐‑‒–—/])', question[merged[-1].end:item.start]):
            previous = merged.pop()
            merged.append(_Concept(question[previous.start:item.end], 'keyword', previous.start, item.end))
        else:
            merged.append(item)
    return merged


def suggest_core_concepts(question: str) -> CoreConceptSuggestion:
    question = CoreConceptSuggestionRequest(original_question=question).original_question
    notices = ['Core uses a small deterministic phrase and wording table. Suggested roles and synonyms are not scientifically or terminologically validated.',
               'Review every concept and term. Required concepts are joined only after you explicitly build the Boolean strategies; exact-query approval is separate.']
    draft = SearchPlanDraft(original_question=question)
    result = CoreConceptSuggestion(question_sha256=sha256(question.encode('utf-8')).hexdigest(), draft=draft, notices=notices)
    # Preserve structured text as a whole. In particular, do not strip quote,
    # field-tag, Boolean grouping, whitespace or Unicode semantics to extract it.
    if _FIELD_TAG.search(question) or _BOOLEAN.search(question) or '"' in question or '“' in question or '”' in question:
        result = result.model_copy(update={'draft': SearchPlanDraft(original_question=question, input_mode='manual_strategy', manual_strategy=question)})
        result.notices.append('Quoted phrases or specialist syntax were detected. The entire text is preserved exactly as an unparsed specialist strategy; edit question framing yourself if this was a natural-language question.')
        return result
    if _NEGATION.search(re.sub(r'\bwhether\s+or\s+not\b', '', question, flags=re.I)):
        result.notices.append('Negation was detected. No exclusion, NOT operator or positive replacement is inferred. Review the wording explicitly in the concept editor before building a strategy.')
    masked, preferences = _separate_preferences(question)
    found = _phrases(question)
    if len(found) > MAX_CONCEPTS or any(len(question[x.start:x.end]) > 200 for x in found):
        result.notices.append('The extracted question exceeds the bounded concept editor. No concepts were silently discarded. Shorten or split the question, or preserve a specialist strategy.')
        return result
    if not found:
        result.notices.append('No substantive concepts were identified. Add a topic or explicit objective, or use the manual concept editor.')
        return result
    negated = bool(_NEGATION.search(re.sub(r'\bwhether\s+or\s+not\b', '', question, flags=re.I)))
    for index, item in enumerate(found):
        text = question[item.start:item.end]
        span = QuestionSpan(start=item.start, end=item.end, text=text)
        concept_id = f'core-concept-{index+1}'
        optional = any(masked[i] != question[i] for i in range(item.start, item.end))
        role = _ROLE_MAP.get(item.kind, item.kind)
        proposed_role = 'unresolved' if item.kind == 'keyword' else item.kind
        explanation = ('Unfamiliar phrase retained; choose its role explicitly.' if item.kind == 'keyword'
                       else f'Lexical suggestion: {proposed_role.replace("_", " ")}. Review this role in the context of your question.')
        if item.kind in _ROLE_MAP and role == 'other': explanation += ' Stored as Other in the existing intent contract.'
        term_note = f'Exact question phrase. Proposed role: {proposed_role}. {explanation}'
        terms = [SearchTerm(id=f'{concept_id}-term-1',text=text,field='text',origin='verbatim',state='proposed',source_span=span,provenance_note=term_note)]
        for term_index, alternative in enumerate(_WORDING.get(text.casefold(), ())):
            terms.append(SearchTerm(id=f'{concept_id}-term-{term_index+2}',text=alternative,field='text',origin='terminology',state='proposed',
                provenance_note=f'Added wording suggestion from {GENERATOR_VERSION}; not present in the question, not a validated synonym or MeSH mapping. Review or remove explicitly.'))
        # Optional and study-design intent is retained outside retrieval by
        # default. Other requirements remain unresolved until researcher choice.
        screening = optional or item.kind == 'study_design' or negated
        concept = SearchConcept(id=concept_id,label=text,role=role,source_span=span,
            requirement='preferred' if optional else 'unresolved',retrieval_use='screen_later' if screening else 'unresolved',terms=terms)
        result.draft.concepts.append(concept)
        result.proposed_roles.append(ProposedConceptRole(concept_id=concept_id,proposed_role=proposed_role,explanation=explanation))
    if preferences:
        result.notices.append('Preference wording retained for later review, not inserted as mandatory retrieval: ' + '; '.join(preferences))
    if negated:
        from .search_plan_contracts import PlanAmbiguity
        result.draft.ambiguities.append(PlanAmbiguity(id='core-negation-review',message='Resolve the negated or exclusion wording explicitly. No NOT or required positive condition was inferred.',concept_ids=[x.id for x in result.draft.concepts]))
    return result
