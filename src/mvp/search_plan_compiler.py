"""Pure, conservative PubMed intent compilation. It performs no terminology I/O."""
import re

from .contracts import digest
from .search_plan_contracts import (
    COMPILER_VERSION, MAX_AST_DEPTH, MAX_AST_NODES, CompiledSearchCandidate,
    CompiledSearchPlan, PlanValidationIssue, SearchPlanDraft,
)


def compile_search_plan(draft: SearchPlanDraft) -> CompiledSearchPlan:
    """Compile explicit intent only; approval and provider diagnostics are separate."""
    if not isinstance(draft, SearchPlanDraft):
        draft = SearchPlanDraft.model_validate(draft)
    plan_sha = digest(draft.model_dump(mode='json'))
    common = []

    def issue(code, message, *, concept_id=None, variant_id=None, severity='error'):
        return PlanValidationIssue(code=code, message=message, concept_id=concept_id,
                                   variant_id=variant_id, severity=severity)

    dates = {'date_from': draft.date_filter.date_from if draft.date_filter else None,
             'date_to': draft.date_filter.date_to if draft.date_filter else None,
             'sort': draft.sort}

    def candidate(variant_id, label, kind, query, included, deferred_required,
                  deferred_excluded, issues, *, split=False, manual=False):
        concepts = {item.id: item for item in draft.concepts}
        deferred = [f'{concepts[key].requirement}: {concepts[key].label} ({concepts[key].retrieval_use})'
                    for key in [*deferred_required, *deferred_excluded] if key in concepts]
        unparsed = (['The manual strategy is preserved exactly. Its intent, eligibility constraints, Boolean semantics and terminology have not been parsed or validated.']
                    if manual else [])
        differences = [f'Deferred to explicit researcher review: {text}' for text in deferred]
        if split:
            differences.append('This is a separate subquestion, requiring explicit acceptance of the split.')
        if manual:
            differences.append('Manual strategy: exact original bytes within the Unicode string; filters remain separate request parameters.')
        payload = dict(id=variant_id, label=label, kind=kind, query=query, **dates,
            plan_sha256=plan_sha, included_concept_ids=included,
            deferred_required_ids=deferred_required, deferred_excluded_ids=deferred_excluded,
            deferred_constraints=deferred, unparsed_constraints=unparsed,
            requires_split_approval=split, differences=differences, issues=issues,
            status='blocked' if any(item.severity == 'error' for item in issues) else 'ready_for_approval')
        sha = digest({'compiler_version': COMPILER_VERSION, **payload,
                      'issues': [item.model_dump(mode='json') for item in issues]})
        return CompiledSearchCandidate(candidate_sha256=sha, **payload)

    if draft.input_mode == 'manual_strategy':
        query = draft.manual_strategy or ''
        if not query.strip():
            common.append(issue('empty_manual_strategy', 'Enter a nonempty manual PubMed strategy.'))
        required = [item.id for item in draft.concepts if item.requirement == 'required']
        excluded = [item.id for item in draft.concepts if item.requirement == 'excluded']
        common.append(issue('manual_strategy_unparsed', 'The specialist strategy is preserved without semantic or MeSH validation.', severity='warning'))
        value = candidate('manual_strategy', 'Manual PubMed strategy', 'manual_strategy', query,
                          [], required, excluded, common, manual=True)
        return CompiledSearchPlan(plan_sha256=plan_sha, candidates=[value], issues=common)

    if not draft.original_question.strip():
        common.append(issue('empty_question', 'Enter the original research question.'))
    if draft.manual_strategy is not None:
        common.append(issue('unexpected_manual_strategy', 'Switch to manual strategy mode or remove the separate strategy.'))
    if not draft.concepts:
        common.append(issue('missing_concepts', 'Define the question concepts before compiling a query.'))
    if not draft.variants:
        common.append(issue('missing_variants', 'Define at least one explicit Boolean query variant.'))
    concepts = {item.id: item for item in draft.concepts}
    if len(concepts) != len(draft.concepts):
        common.append(issue('duplicate_concept_id', 'Each concept needs a unique ID.'))
    if len({item.id for item in draft.variants}) != len(draft.variants):
        common.append(issue('duplicate_variant_id', 'Each query variant needs a unique ID.'))
    if len({item.id for item in draft.ambiguities}) != len(draft.ambiguities):
        common.append(issue('duplicate_ambiguity_id', 'Each ambiguity needs a unique ID.'))

    def check_span(span, concept_id, *, term=None):
        if span is not None and (span.end > len(draft.original_question)
                or draft.original_question[span.start:span.end] != span.text):
            common.append(issue('source_span_mismatch', 'Source spans must match the exact original question using half-open Unicode codepoints.', concept_id=concept_id))
        if term is not None and term.origin == 'verbatim' and (span is None or term.text != span.text):
            common.append(issue('verbatim_term_mismatch', 'A verbatim term must equal its exact question span; mark edited terms as manual.', concept_id=concept_id))

    for ambiguity in draft.ambiguities:
        if any(key not in concepts for key in ambiguity.concept_ids):
            common.append(issue('unknown_ambiguity_concept', 'An ambiguity refers to an unknown concept.'))
        if not ambiguity.resolved or not ambiguity.resolution.strip():
            common.append(issue('unresolved_ambiguity', ambiguity.message))
    rendered = {}
    for concept in draft.concepts:
        check_span(concept.source_span, concept.id)
        if concept.source_span is None:
            common.append(issue('manual_concept_without_question_span', 'This concept has no literal question span; review its manually added provenance.', concept_id=concept.id, severity='warning'))
        if concept.requirement == 'unresolved' or concept.retrieval_use == 'unresolved' or concept.role == 'unresolved':
            common.append(issue('unresolved_concept', 'Resolve this concept requirement, role and retrieval use before execution.', concept_id=concept.id))
        if len({term.id for term in concept.terms}) != len(concept.terms):
            common.append(issue('duplicate_term_id', 'Term IDs must be unique within each concept.', concept_id=concept.id))
        if concept.promoted_to_query and (concept.requirement != 'preferred' or not concept.promotion_reason.strip()):
            common.append(issue('invalid_preference_promotion', 'Only a preferred concept can be explicitly promoted, with a recorded reason.', concept_id=concept.id))
        values = []
        for term in concept.terms:
            check_span(term.source_span, concept.id, term=term)
            if term.state != 'approved':
                common.append(issue('unapproved_term', 'Review, edit or remove every proposed term before execution.', concept_id=concept.id))
            if not term.text.strip():
                common.append(issue('empty_term', 'Search terms must contain text.', concept_id=concept.id))
            if term.field == 'mesh':
                common.append(issue('mesh_registry_unavailable', 'No server MeSH registry is configured. Change this term explicitly to text or use a reviewed manual strategy; approval does not validate MeSH.', concept_id=concept.id))
            if (any(ord(char) < 32 or ord(char) == 127 for char in term.text)
                or any(char in term.text for char in '()[]"\\:{}')
                or (term.field == 'text' and re.search(r'\b(?:AND|OR|NOT)\b', term.text, re.I))):
                common.append(issue('structured_term_contains_syntax', 'Keep Boolean syntax and field tags in the explicit expression; use manual strategy mode for specialist syntax.', concept_id=concept.id))
            text = f'"{term.text}"[Title/Abstract]' if term.field == 'title_abstract' else term.text
            values.append(text)
        if not values and concept.retrieval_use == 'query':
            common.append(issue('missing_query_terms', 'A query concept needs at least one reviewed term.', concept_id=concept.id))
        rendered[concept.id] = '(' + ' OR '.join(values) + ')' if values else ''

    candidates = []
    for variant in draft.variants:
        issues = list(common)
        refs = set()
        node_count = 0

        def walk(node, depth=1):
            nonlocal node_count
            node_count += 1
            if node_count > MAX_AST_NODES or depth > MAX_AST_DEPTH:
                issues.append(issue('expression_bound', 'The explicit expression exceeds its node or depth bound.', variant_id=variant.id))
                return '', set(), set()
            if node.op in {'concept_ref', 'not'}:
                negative = node.op == 'not'
                if negative:
                    node_count += 1  # The explicit concept_ref child is a node too.
                    if node_count > MAX_AST_NODES or depth + 1 > MAX_AST_DEPTH:
                        issues.append(issue('expression_bound', 'The explicit expression exceeds its node or depth bound.', variant_id=variant.id))
                        return '', set(), set()
                key = node.children[0].concept_id if negative else node.concept_id
                if key not in concepts:
                    issues.append(issue('unknown_concept', 'The expression refers to an unknown concept.', variant_id=variant.id))
                    return '', set(), set()
                refs.add(key)
                concept = concepts[key]
                if concept.retrieval_use != 'query':
                    issues.append(issue('non_query_concept', 'Rank-only and screen-later concepts cannot restrict the compiled query.', concept_id=key, variant_id=variant.id))
                if negative != (concept.requirement == 'excluded'):
                    issues.append(issue('invalid_negation', 'NOT requires one explicitly excluded concept, and excluded concepts require NOT.', concept_id=key, variant_id=variant.id))
                if concept.requirement == 'preferred' and not (concept.promoted_to_query and concept.promotion_reason.strip()):
                    issues.append(issue('preferred_query_restriction', 'A preference can restrict retrieval only after explicit promotion with a reason.', concept_id=key, variant_id=variant.id))
                return rendered[key], set() if negative else {key}, {key} if negative else set()
            parts = [walk(child, depth + 1) for child in node.children]
            if node.op == 'any_of':
                if any(child.op == 'not' for child in node.children):
                    issues.append(issue('unanchored_exclusion', 'Place each NOT within an AND group containing a positive retrieval condition.', variant_id=variant.id))
                positive = set.intersection(*(part[1] for part in parts))
                negative = set.intersection(*(part[2] for part in parts))
                text = '(' + ' OR '.join(part[0] for part in parts) + ')'
            else:
                positive = set.union(*(part[1] for part in parts))
                negative = set.union(*(part[2] for part in parts))
                normal = [part[0] for child, part in zip(node.children, parts) if child.op != 'not']
                negatives = [part[0] for child, part in zip(node.children, parts) if child.op == 'not']
                if not normal:
                    issues.append(issue('unanchored_exclusion', 'An exclusion needs a positive retrieval condition in its AND group.', variant_id=variant.id))
                text = '(' + ' AND '.join(normal) + ''.join(' NOT ' + value for value in negatives) + ')'
            return text, positive, negative

        query, guaranteed, guaranteed_excluded = walk(variant.expression)
        if variant.expression.op == 'not':
            issues.append(issue('unanchored_exclusion', 'A query cannot consist only of an exclusion.', variant_id=variant.id))
        deferred_required = [item.id for item in draft.concepts if item.requirement == 'required' and item.id not in guaranteed]
        deferred_excluded = [item.id for item in draft.concepts if item.requirement == 'excluded' and item.id not in guaranteed_excluded]
        required_query_missing = [key for key in deferred_required if concepts[key].retrieval_use == 'query']
        if variant.kind == 'focused' and required_query_missing:
            issues.append(issue('focused_missing_required_concepts', 'Every required query concept must be guaranteed across every focused-query Boolean branch.', variant_id=variant.id))
        expected_deferrals = set(deferred_required + deferred_excluded)
        declared = set(variant.deferred_concept_ids)
        if len(declared) != len(variant.deferred_concept_ids) or declared != expected_deferrals:
            issues.append(issue('undeclared_or_inconsistent_deferral', 'Declare exactly all required and excluded concepts that are not guaranteed by this variant, including non-query constraints.', variant_id=variant.id))
        if expected_deferrals and not variant.deferral_reason.strip():
            issues.append(issue('deferral_reason_required', 'Explain why these required or excluded constraints are deferred.', variant_id=variant.id))
        if variant.kind == 'subquestion' and not variant.split_explanation.strip():
            issues.append(issue('split_explanation_required', 'Explain this explicit subquestion split before approval.', variant_id=variant.id))
        if len(query) > 20000 or not query.strip():
            issues.append(issue('compiled_query_bound', 'The compiled query must contain at most 20,000 characters.', variant_id=variant.id))
        candidates.append(candidate(variant.id, variant.label, variant.kind, query,
            [item.id for item in draft.concepts if item.id in refs], deferred_required,
            deferred_excluded, issues, split=variant.kind == 'subquestion'))
    return CompiledSearchPlan(plan_sha256=plan_sha, candidates=candidates, issues=common)
