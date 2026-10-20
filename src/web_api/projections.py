"""Transport views exclude retained XML and unrelated historical source blocks."""
from .contracts import (
    AssessmentSummary, PreparationSummary, PreparationView, RunSummary,
    SearchSummary, SourceMetadata, WorkspaceSummary,
)


def source_metadata(source):
    return SourceMetadata(**source.model_dump(exclude={"blocks", "retained_content_utf8"}), block_count=len(source.blocks))


def preparation_view(preparation):
    return PreparationView(**preparation.model_dump(exclude={"sources"}), sources=[source_metadata(item) for item in preparation.sources])


def workspace_summary(state, mode):
    current_preparation = state.preparations[-1] if state.preparations else None
    return WorkspaceSummary(
        id=state.id, question=state.question, mode=mode, created_at=state.created_at,
        source_revision=state.source_revision, current_preparation_id=current_preparation.id if current_preparation else None,
        selected_paper_ids=state.selected_paper_ids, current_run_id=state.current_run_id,
        current_assessment_ids=state.current_assessment_ids,
        searches=[SearchSummary(**search.model_dump(include={"id", "query", "research_question", "searched_at", "mode", "provider", "total_reported", "fetched_count", "truncated", "warnings"}), distinct_count=len(search.papers)) for search in state.searches],
        preparations=[PreparationSummary(**preparation.model_dump(include=set(PreparationSummary.model_fields))) for preparation in state.preparations],
        runs=[RunSummary(**run.model_dump(include={"id", "search_id", "preparation_id", "source_revision", "question", "created_at"}), passage_count=len(run.passages), current=run.source_revision == state.source_revision and current_preparation is not None and run.preparation_id == current_preparation.id) for run in state.runs],
        assessments=[AssessmentSummary(id=item.id, run_id=item.run_id, supersedes_id=item.supersedes_id, status=item.bundle.status, created_at=item.created_at) for item in state.assessments],
    )
