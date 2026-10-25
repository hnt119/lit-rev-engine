"""Pure historical bibliography resolution from authorized workspace state."""
from dataclasses import dataclass

from .collection_contracts import CollectionInputRef, SearchInputRef
from .collection_preparation_contracts import CollectionPreparationResult
from .contracts import Paper, digest
from .ports import MvpError


@dataclass(frozen=True)
class PreparedBibliography:
    origin: SearchInputRef | CollectionInputRef
    papers: tuple[Paper, ...]


def resolve_preparation(state, preparation):
    if isinstance(preparation, CollectionPreparationResult):
        if digest([member.model_dump(mode='json') for member in preparation.member_snapshots]) != preparation.member_snapshot_sha256:
            raise MvpError('source_integrity_error', 'The retained collection paper snapshots changed.')
        papers = tuple(member.paper for member in preparation.member_snapshots)
        if [paper.id for paper in papers] != preparation.selected_paper_ids:
            raise MvpError('source_integrity_error', 'The retained collection paper order changed.')
        return PreparedBibliography(preparation.collection_ref, papers)
    search = next((item for item in state.searches if item.id == preparation.search_id), None)
    if search is None:
        raise MvpError('unknown_search', 'The original retained search is unavailable.')
    indexed = {paper.id: paper for paper in search.papers}
    if any(identifier not in indexed for identifier in preparation.selected_paper_ids):
        raise MvpError('source_integrity_error', 'The original selected search papers changed.')
    return PreparedBibliography(SearchInputRef(search_id=search.id, search_snapshot_sha256=digest(search.model_dump(mode='json'))),
        tuple(indexed[identifier] for identifier in preparation.selected_paper_ids))


def resolve_run(state, run):
    preparation = next((item for item in state.preparations if item.id == run.preparation_id), None)
    if preparation is None or preparation.source_revision != run.source_revision:
        raise MvpError('source_integrity_error', 'The evidence run no longer matches its original preparation.')
    if not hasattr(run, 'collection_ref') and preparation.search_id != run.search_id:
        raise MvpError('source_integrity_error', 'The evidence run no longer matches its original preparation.')
    bibliography = resolve_preparation(state, preparation)
    if hasattr(run, 'collection_ref'):
        if bibliography.origin != run.collection_ref or preparation.member_snapshot_sha256 != run.member_snapshot_sha256:
            raise MvpError('source_integrity_error', 'The evidence run collection/metadata binding changed.')
    elif bibliography.origin.kind != 'search' or bibliography.origin.search_id != run.search_id:
        raise MvpError('source_integrity_error', 'The evidence run search binding changed.')
    return preparation, bibliography
