"""Bounded recoverable UI inputs, separate from executable research records.

An editor draft deliberately permits incomplete intent. These contracts never
compile a query, approve a plan, prepare sources, or create a comparison board.
"""
import math
import re
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, Field, field_validator

from .collection_contracts import CollectionInputRef
from .contracts import Model
from .limits import MAX_PREPARED_SOURCES
from .ports import MvpError
from .search_plan_contracts import MAX_AST_DEPTH, MAX_AST_NODES, MAX_CONCEPTS, MAX_TERMS, MAX_VARIANTS

def _unicode(value):
    value.encode('utf-8')
    return value


Identifier = Annotated[str, Field(min_length=1, max_length=200, strict=True), AfterValidator(_unicode)]
MAX_EDITOR_DEPTH = 24
MAX_EDITOR_NODES = 8192
MAX_EDITOR_STRING = 20000


def usability_scope(scope):
    """Return the additive scope kind/identity, or None for existing scopes."""
    if scope == 'import-intake':
        return 'import-intake', None
    for kind in ('search-plan-editor', 'comparison-handoff'):
        prefix = kind + ':'
        if scope.startswith(prefix):
            identifier = scope[len(prefix):]
            if (not identifier or len(identifier) > 200 or
                    kind == 'comparison-handoff' and not re.fullmatch(
                        r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', identifier)):
                raise MvpError('invalid_draft_scope', 'Choose a bounded editor scope or a comparison handoff UUID.')
            try:
                identifier.encode('utf-8')
            except UnicodeError:
                raise MvpError('invalid_draft_scope', 'Choose a valid text draft scope.') from None
            return kind, identifier
    return None


def _bounded_json(value):
    pending, count = [(value, 0)], 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if depth > MAX_EDITOR_DEPTH or count > MAX_EDITOR_NODES:
            raise ValueError('Editor draft exceeds its structural bound')
        if isinstance(item, dict):
            if len(item) > 32:
                raise ValueError('Editor objects contain at most 32 fields')
            for key, child in item.items():
                if not isinstance(key, str) or len(key) > 100:
                    raise ValueError('Use bounded text field names')
                key.encode('utf-8')
                pending.append((child, depth + 1))
        elif isinstance(item, list):
            if len(item) > 128:
                raise ValueError('Editor arrays contain at most 128 items')
            pending.extend((child, depth + 1) for child in item)
        elif isinstance(item, str):
            if len(item) > MAX_EDITOR_STRING:
                raise ValueError('Editor text exceeds its character bound')
            item.encode('utf-8')
        elif item is None or isinstance(item, bool):
            pass
        elif isinstance(item, (int, float)):
            if abs(item) > 10**12 or not math.isfinite(item):
                raise ValueError('Use bounded finite numeric editor values')
        else:
            raise ValueError('Use JSON editor values')


def _array(value, key, limit, *, objects=False):
    if key not in value:
        return []
    items = value[key]
    if not isinstance(items, list) or len(items) > limit or objects and any(not isinstance(item, dict) for item in items):
        raise ValueError(f'Use a bounded {key} array')
    return items


def _text_fields(value, bounds):
    for key, limit in bounds.items():
        if key in value and value[key] is not None and (not isinstance(value[key], str) or len(value[key]) > limit):
            raise ValueError(f'Use bounded text for {key}')


def _editor_shape(value):
    # Only structural limits apply. Blank labels/terms/dates, incomplete Boolean
    # groups, unresolved references, invalid spans and absent fields survive.
    _bounded_json(value)
    _text_fields(value, {'original_question': 10000, 'manual_strategy': 20000})
    for concept in _array(value, 'concepts', MAX_CONCEPTS, objects=True):
        _text_fields(concept, {'id': 100, 'label': 200, 'promotion_reason': 2000})
        for term in _array(concept, 'terms', MAX_TERMS, objects=True):
            _text_fields(term, {'id': 100, 'text': 1000, 'provenance_note': 2000})
    for variant in _array(value, 'variants', MAX_VARIANTS, objects=True):
        _text_fields(variant, {'id': 100, 'label': 200, 'deferral_reason': 2000, 'split_explanation': 2000})
        _array(variant, 'deferred_concept_ids', MAX_CONCEPTS)
        pending, nodes = [(variant['expression'], 1)] if 'expression' in variant else [], 0
        while pending:
            expression, depth = pending.pop()
            nodes += 1
            if not isinstance(expression, dict) or depth > MAX_AST_DEPTH or nodes > MAX_AST_NODES:
                raise ValueError('Use a bounded expression object')
            pending.extend((child, depth + 1) for child in _array(expression, 'children', MAX_CONCEPTS, objects=True))
    for ambiguity in _array(value, 'ambiguities', 20, objects=True):
        _text_fields(ambiguity, {'id': 100, 'message': 2000, 'resolution': 2000})
        _array(ambiguity, 'concept_ids', MAX_CONCEPTS)
    if value.get('date_filter') is not None:
        if not isinstance(value['date_filter'], dict):
            raise ValueError('Use a date editor object')
        _text_fields(value['date_filter'], {'date_from': 20, 'date_to': 20})
    return value


class SearchPlanEditorDraft(Model):
    draft: dict[str, Any]
    plan_id: Identifier | None
    base_revision_id: Identifier | None

    @field_validator('draft')
    @classmethod
    def bounded_incomplete_intent(cls, value):
        return _editor_shape(value)


class ImportIntakeDraft(Model):
    format: Literal['csv', 'ris', 'identifiers']
    identifiers: str = Field(max_length=20000, strict=True)

    @field_validator('identifiers')
    @classmethod
    def exact_bounded_text(cls, value):
        return _unicode(value)


class ComparisonSearchOrigin(Model):
    kind: Literal['search'] = 'search'
    search_id: Identifier


class ComparisonHandoffDraft(Model):
    question: str = Field(max_length=10000, strict=True)
    origin: Annotated[ComparisonSearchOrigin | CollectionInputRef, Field(discriminator='kind')]
    selected_paper_ids: list[Identifier] = Field(min_length=1, max_length=MAX_PREPARED_SOURCES)
    expected_source_revision: int = Field(ge=0, strict=True)
    expected_preparation_id: Identifier | None
    job_id: Identifier | None
    preparation_id: Identifier | None

    @field_validator('question')
    @classmethod
    def valid_unicode(cls, value):
        value.encode('utf-8')
        return value

    @field_validator('selected_paper_ids')
    @classmethod
    def unique_ordered_selection(cls, value):
        if len(value) != len(set(value)):
            raise ValueError('Select each paper once')
        return value

    @field_validator('origin')
    @classmethod
    def bounded_collection_ref(cls, value):
        if isinstance(value, CollectionInputRef):
            value.collection_id.encode('utf-8')
            if not 1 <= len(value.collection_id) <= 200 or not re.fullmatch('[0-9a-f]{64}', value.collection_snapshot_sha256):
                raise ValueError('Use an exact bounded collection snapshot reference')
        return value

    def clicked_inputs(self):
        return self.model_dump(mode='json', exclude={'job_id', 'preparation_id'})


def validate_handoff_update(prior, value):
    """The captured click cannot be repurposed by a later autosave or tab."""
    if prior.clicked_inputs() != value.clicked_inputs() or any(
            getattr(prior, key) is not None and getattr(prior, key) != getattr(value, key)
            for key in ('job_id', 'preparation_id')):
        raise MvpError('comparison_handoff_changed', 'This handoff retains the exact clicked selection. Start a new handoff for changed inputs or preparation.')


def validate_handoff_state(state, value, *, collection_paper_ids=None, job=None, retained_sync_acknowledgement=False):
    """Check owned immutable records; current mutable selection is irrelevant."""
    def find(items, identifier, kind):
        item = next((item for item in items if item.id == identifier), None)
        if item is None:
            raise MvpError('unknown_' + kind, 'The requested resource does not belong to this workspace.')
        return item

    if value.origin.kind == 'search':
        papers = {paper.id for paper in find(state.searches, value.origin.search_id, 'search').papers}
    else:
        papers = set(collection_paper_ids or ())
    if set(value.selected_paper_ids) - papers:
        raise MvpError('invalid_comparison_handoff', 'Every selected paper must belong to the exact handoff origin.')
    if value.expected_preparation_id is None:
        valid_base = value.expected_source_revision == 0
    else:
        base = find(state.preparations, value.expected_preparation_id, 'preparation')
        valid_base = base.source_revision == value.expected_source_revision
    if not valid_base:
        raise MvpError('invalid_comparison_handoff', 'The captured source revision must match its retained preparation.')
    if job is not None:
        origin_matches = (getattr(job, 'search_id', None) == value.origin.search_id if value.origin.kind == 'search'
                          else getattr(job, 'collection_ref', None) == value.origin)
        if (not origin_matches or job.selected_paper_ids != value.selected_paper_ids or
                job.expected_source_revision != value.expected_source_revision or
                job.expected_preparation_id != value.expected_preparation_id):
            raise MvpError('invalid_comparison_handoff', 'The acknowledged job must match the exact clicked inputs and ordered papers.')
    if value.preparation_id is not None:
        preparation = find(state.preparations, value.preparation_id, 'preparation')
        origin_matches = (preparation.search_id == value.origin.search_id if value.origin.kind == 'search'
                          else getattr(preparation, 'collection_ref', None) == value.origin)
        if job is None:
            reused = (preparation.id == value.expected_preparation_id and
                      preparation.source_revision == value.expected_source_revision)
            synchronous_publication = (preparation.source_revision == value.expected_source_revision + 1 and
                                      (retained_sync_acknowledgement or
                                       state.source_revision == preparation.source_revision and
                                       bool(state.preparations) and state.preparations[-1].id == preparation.id))
            revision_matches = reused or synchronous_publication
        else:
            revision_matches = (job.status == 'succeeded' and job.result_preparation_id == preparation.id and
                                job.result_source_revision == preparation.source_revision)
        if not origin_matches or preparation.selected_paper_ids != value.selected_paper_ids or not revision_matches:
            raise MvpError('invalid_comparison_handoff', 'The acknowledged preparation must match the exact handoff and job result, reuse the captured preparation, or be the immediately published current result.')
