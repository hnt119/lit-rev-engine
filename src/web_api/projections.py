"""Transport views exclude retained XML and unrelated historical source blocks."""
from .contracts import (
    AssessmentSummary, CollectionPreparationSummary, CollectionPreparationView,
    CollectionRunSummary, PreparationSummary, PreparationView, RunSummary,
    SearchSummary, SourceMetadata, WorkspaceSummary,
)


def source_metadata(source):
    return SourceMetadata(**source.model_dump(exclude={"blocks", "retained_content_utf8"}), block_count=len(source.blocks))


def preparation_view(preparation):
    model = CollectionPreparationView if hasattr(preparation, 'collection_ref') else PreparationView
    return model(**preparation.model_dump(include=set(model.model_fields) - {'sources'}), sources=[source_metadata(item) for item in preparation.sources])


def preparation_summary(preparation):
    model = CollectionPreparationSummary if hasattr(preparation, 'collection_ref') else PreparationSummary
    return model(**preparation.model_dump(include=set(model.model_fields)))


def run_summary(run, state, current_preparation):
    from src.mvp.contracts import BoardPassageScope
    from src.mvp.ports import MvpError
    from pydantic import ValidationError
    model = CollectionRunSummary if hasattr(run, 'collection_ref') else RunSummary
    context = run.parameters.get('board_passage_context')
    try:
        scope = (BoardPassageScope.model_validate({key: context[key] for key in BoardPassageScope.model_fields})
                 if isinstance(context, dict) else None)
        if context is not None and scope is None:
            raise ValueError('Invalid retained scope')
    except (ValidationError, ValueError, KeyError):
        raise MvpError('source_integrity_error', 'The retained comparison passage scope is unsupported or invalid.') from None
    return model(**run.model_dump(include={'id', 'search_id', 'collection_ref', 'preparation_id', 'source_revision', 'question', 'created_at'}),
        board_context=scope, passage_count=len(run.passages), current=run.source_revision == state.source_revision and current_preparation is not None and run.preparation_id == current_preparation.id)


def workspace_summary(state, mode):
    current_preparation = state.preparations[-1] if state.preparations else None
    return WorkspaceSummary(
        id=state.id, question=state.question, mode=mode, created_at=state.created_at,
        source_revision=state.source_revision, current_preparation_id=current_preparation.id if current_preparation else None,
        selected_paper_ids=state.selected_paper_ids, current_run_id=state.current_run_id,
        current_assessment_ids=state.current_assessment_ids,
        searches=[SearchSummary(**search.model_dump(include={"id", "query", "research_question", "searched_at", "mode", "provider", "total_reported", "fetched_count", "truncated", "warnings"}), distinct_count=len(search.papers)) for search in state.searches],
        preparations=[preparation_summary(preparation) for preparation in state.preparations],
        runs=[run_summary(run, state, current_preparation) for run in state.runs],
        assessments=[AssessmentSummary(id=item.id, run_id=item.run_id, supersedes_id=item.supersedes_id, status=item.bundle.status, created_at=item.created_at) for item in state.assessments],
    )
