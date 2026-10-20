"""The reusable synchronous application boundary; no Streamlit or live setup."""

import hashlib
import json
import re

from src.review.documents import parse_source_bytes
from src.review.exporters import _csv
from src.review.identity import normalize_doi, normalize_pmid

from .adapters.retrieval import LexicalRetrieval
from .contracts import (
    Assessment, Block, BoundRetrieveEvidenceRequest, ClearResult, CreateWorkspaceRequest, EvidenceRun, PassageJudgment,
    PreparationResult, PreparedSource, QuerySuggestion, QuerySuggestionRequest,
    PrepareSourcesRequest, RetrieveEvidenceRequest, SaveAssessmentRequest, SearchPreview,
    SearchRequest, SourceContext, SourceContextRequest, StructuredError, WorkspaceExport,
    WorkspaceHandle, WorkspaceSnapshot, digest, new_id, now,
)
from .ports import DiscoveryProvider, MvpError, ProviderFailure, SourceProvider, WorkspaceStorage


def _find(items, identifier, kind):
    result = next((item for item in items if item.id == identifier), None)
    if result is None:
        raise MvpError("unknown_" + kind, "The requested " + kind.replace("_", " ") + " does not belong to this workspace.")
    return result


def _manifest(sources):
    return [{"source_id": source.id, "paper_id": source.paper_id, "version": source.version,
             "source_sha256": source.source_sha256, "blocks_sha256": source.blocks_sha256,
             "parser_id": source.parser_id, "source_type": source.source_type}
            for source in sources]


def _assert_source_integrity(sources):
    for source in sources:
        if source.blocks_sha256 != digest([block.model_dump(mode="json") for block in source.blocks]):
            raise MvpError("source_integrity_error", "Retained canonical source blocks failed their hash check.")
        if source.retained_content_utf8 is not None and hashlib.sha256(source.retained_content_utf8.encode("utf-8")).hexdigest() != source.source_sha256:
            raise MvpError("source_integrity_error", "Retained source bytes failed their hash check.")


def _deduplicate(preview):
    papers, warnings = [], list(preview.warnings)
    removed = 0
    for paper in preview.papers:
        duplicate = None
        for existing in papers:
            same_pmid = paper.pmid is not None and paper.pmid == existing.pmid
            same_doi = paper.doi is not None and paper.doi == existing.doi
            # A DOI shared by distinct PubMed reports does not merge those reports.
            compatible = not (paper.pmid and existing.pmid and paper.pmid != existing.pmid)
            if same_pmid or (same_doi and compatible):
                duplicate = existing
                break
        if duplicate is not None:
            if paper.doi and duplicate.doi and paper.doi != duplicate.doi:
                warnings.append("Conflicting DOI metadata for PMID " + str(paper.pmid) + "; first record retained.")
            removed += 1
            continue
        if any(existing.id == paper.id for existing in papers):
            raise MvpError("discovery_identity_conflict", "Discovery returned ambiguous publication identities.")
        papers.append(paper)
    if removed:
        warnings.append(f"Removed {removed} duplicate fetched record(s) by PMID/compatible DOI. Fetched count and ordered provider identifiers are preserved.")
    return preview.model_copy(update={"papers": papers, "warnings": warnings})


def _abstract(paper, *, status="abstract_only", error=None):
    if paper.abstract.strip():
        parsed = parse_source_bytes(paper.abstract.encode("utf-8"), "txt")
        blocks = [Block.model_validate(block) for block in parsed["blocks"]]
        return PreparedSource(
            paper_id=paper.id, status=status, source_type="abstract", provider="pubmed_abstract",
            source_url=paper.url or ("https://pubmed.ncbi.nlm.nih.gov/" + paper.pmid + "/" if paper.pmid else ""),
            version=hashlib.sha256(paper.abstract.encode("utf-8")).hexdigest(),
            source_sha256=hashlib.sha256(paper.abstract.encode("utf-8")).hexdigest(),
            blocks_sha256=digest([block.model_dump(mode="json") for block in blocks]),
            parser_id=parsed["parser_id"], parser_metadata=parsed["parser_metadata"],
            source_identifiers={key: value for key, value in (("pmid", paper.pmid), ("doi", paper.doi)) if value},
            blocks=blocks, warnings=["Abstract only; full text was not retained."], error=error)
    return PreparedSource(paper_id=paper.id, status=status if status != "abstract_only" else "no_usable_text",
                          source_type="none", provider="pubmed_abstract", source_url=paper.url,
                          warnings=["No usable full text or abstract is available."], error=error)


def _validated_source(source, paper):
    conflict = source.paper_id != paper.id
    for key, normalize in (("pmid", normalize_pmid), ("doi", normalize_doi)):
        value, expected = source.source_identifiers.get(key), getattr(paper, key)
        if value and expected and normalize(value) != expected:
            conflict = True
    if source.source_identifiers.get("pmcid") and paper.pmcid:
        conflict = conflict or source.source_identifiers["pmcid"].upper() != paper.pmcid.upper()
    if conflict:
        return _abstract(paper, status="identity_mismatch", error=StructuredError(
            code="source_identity_mismatch", message="Retrieved source identity did not match the selected paper; that source was discarded.", paper_id=paper.id))
    blocks = [block.model_dump(mode="json") for block in source.blocks]
    if len({block.id for block in source.blocks}) != len(source.blocks):
        raise ProviderFailure("invalid_source", "Source returned duplicate canonical block identifiers.")
    if source.source_type == "none" and blocks:
        raise ProviderFailure("invalid_source", "Unavailable source unexpectedly contained canonical text.")
    if source.source_type != "none" and not any(block.text.strip() for block in source.blocks):
        raise ProviderFailure("invalid_source", "Usable source did not contain canonical text.")
    if source.status == "full_text_retrieved" and source.source_type != "full_text":
        raise ProviderFailure("invalid_source", "Full-text status did not match the retained text type.")
    if source.source_type == "full_text" and source.status != "full_text_retrieved":
        raise ProviderFailure("invalid_source", "Full text cannot be retained under an unavailable-source status.")
    if source.source_type == "full_text" and not source.license:
        raise ProviderFailure("permission_unresolved", "Retained full text requires explicit reuse permission.")
    expected_blocks_hash = digest(blocks)
    if source.blocks_sha256 and source.blocks_sha256 != expected_blocks_hash:
        raise ProviderFailure("source_integrity_error", "Canonical source blocks failed their hash check.")
    if source.retained_content_utf8 is not None:
        if source.source_type != "full_text" or not source.license:
            raise ProviderFailure("permission_unresolved", "Source retention requires permitted full text and license attribution.")
        original = source.retained_content_utf8.encode("utf-8")
        if source.source_sha256 and hashlib.sha256(original).hexdigest() != source.source_sha256:
            raise ProviderFailure("source_integrity_error", "Retained source bytes failed their hash check.")
        parsed = parse_source_bytes(original, "jats_xml")
        if digest(parsed["blocks"]) != expected_blocks_hash:
            raise ProviderFailure("source_integrity_error", "Canonical blocks did not match retained source bytes.")
        for key, own_value in parsed["source_identifiers"].items():
            expected = getattr(paper, key, None)
            if expected is not None and own_value != expected:
                return _abstract(paper, status="identity_mismatch", error=StructuredError(
                    code="source_identity_mismatch", message="Retained XML's own identifiers did not match the selected paper; that source was discarded.", paper_id=paper.id))
    source_hash = source.source_sha256
    metadata = dict(source.parser_metadata)
    if not source_hash and source.source_type != "none":
        source_hash = digest(blocks)
        metadata["source_hash_basis"] = "canonical-block-json-v1; original source bytes not retained"
    if source_hash and not re.fullmatch(r"[0-9a-f]{64}", source_hash):
        raise ProviderFailure("source_integrity_error", "Source digest was not a SHA-256 digest.")
    return source.model_copy(update={"blocks_sha256": expected_blocks_hash, "source_sha256": source_hash,
                                     "parser_metadata": metadata})


class MVPService:
    def __init__(self, storage: WorkspaceStorage, discovery: DiscoveryProvider,
                 sources: SourceProvider, retrieval: LexicalRetrieval | None = None):
        self._storage, self._discovery, self._sources = storage, discovery, sources
        self._retrieval = retrieval or LexicalRetrieval()

    def create_workspace(self, request: CreateWorkspaceRequest | None = None) -> WorkspaceHandle:
        request = request or CreateWorkspaceRequest()
        return self._storage.create(request.question)

    def get_workspace(self, handle: WorkspaceHandle) -> WorkspaceSnapshot:
        return self._storage.read(handle)

    def create_reserved_workspace(self, handle: WorkspaceHandle, request: CreateWorkspaceRequest) -> WorkspaceHandle:
        """Complete a trusted server-side reservation without creating another ID."""
        return self._storage.create_reserved(handle, request.question)

    def with_workspace_state(self, handle, callback):
        """Run a short auxiliary-state operation under the existing research lock."""
        return self._storage.read_serialized(handle, callback)

    def suggest_query(self, handle: WorkspaceHandle, request: QuerySuggestionRequest) -> QuerySuggestion:
        self._storage.read(handle)
        words = {word.casefold() for word in re.findall(r"\w+", request.question)}
        if {"gut", "microbiome", "asian", "women"}.issubset(words):
            query = '("gut microbiome"[Title/Abstract] OR "gut microbiota"[Title/Abstract]) AND (women[Title/Abstract] OR female[MeSH Terms]) AND (Asia[MeSH Terms] OR Asian[Title/Abstract])'
            explanation = "Editable sample concept groups for microbiome, women, and Asia. Search terms do not establish a paper's population or findings."
        else:
            stop = {"a", "an", "and", "are", "do", "does", "how", "in", "is", "of", "on", "or", "the", "to", "what", "which", "with"}
            terms = list(dict.fromkeys(word for word in re.findall(r"\w+", request.question) if word.casefold() not in stop))
            query = " AND ".join('"' + term + '"[Title/Abstract]' for term in terms[:12]) or request.question
            explanation = "Transparent starting template: the first twelve distinct non-stop words, each searched in title/abstract and joined by AND. Edit concepts and synonyms before searching. No filters are relaxed automatically."
        return QuerySuggestion(query=query, explanation=explanation)

    def _operate(self, handle, operation, request, result_model, callback):
        def execute(state):
            updated, result = callback(state)
            return updated, result.model_dump(mode="json")
        result = self._storage.transact(handle, operation, request.request_id,
                                       digest(request.model_dump(mode="json")), execute)
        return result_model.model_validate(result)

    def search_literature(self, handle: WorkspaceHandle, request: SearchRequest) -> SearchPreview:
        def execute(state):
            try:
                preview = self._discovery.search(request)
            except ProviderFailure:
                raise
            except Exception:
                raise MvpError("discovery_failed", "Publication discovery failed. Retry the search explicitly.", True) from None
            preview = SearchPreview.model_validate(preview)
            if len(preview.papers) > request.max_results or preview.fetched_count > request.max_results:
                raise MvpError("discovery_limit_exceeded", "Discovery exceeded the requested exploratory sample limit.")
            preview = _deduplicate(preview)
            question = request.research_question if request.research_question is not None else state.question
            preview = preview.model_copy(update={"research_question": question})
            if any(search.id == preview.id for search in state.searches):
                # A saved example/provider result may be reused, but an explicit refresh is a new search record.
                preview = preview.model_copy(update={"id": new_id()})
            return state.model_copy(update={"question": question, "searches": [*state.searches, preview]}), preview
        return self._operate(handle, "search", request, SearchPreview, execute)

    def prepare_sources(self, handle: WorkspaceHandle, request: PrepareSourcesRequest) -> PreparationResult:
        def execute(state):
            search = _find(state.searches, request.search_id, "search")
            papers = [_find(search.papers, identifier, "paper") for identifier in request.paper_ids]
            sources, errors = [], []
            for paper in papers:
                try:
                    source = _validated_source(PreparedSource.model_validate(self._sources.prepare(paper)), paper)
                except ProviderFailure as error:
                    safe_error = StructuredError(code=error.code, message=error.message, retryable=error.retryable, paper_id=paper.id)
                    source = _abstract(paper, status="permission_unresolved" if error.code == "permission_unresolved" else "fetch_failed", error=safe_error)
                except Exception:
                    source = _abstract(paper, status="fetch_failed", error=StructuredError(
                        code="source_preparation_failed", message="Source preparation failed; available abstract retained where possible.", retryable=True, paper_id=paper.id))
                sources.append(source)
                if source.error is not None:
                    errors.append(source.error)
            result = PreparationResult(search_id=search.id, source_revision=state.source_revision + 1,
                                       selected_paper_ids=request.paper_ids, sources=sources, errors=errors)
            updated = state.model_copy(update={"source_revision": result.source_revision,
                                              "selected_paper_ids": request.paper_ids, "sources": sources,
                                              "preparations": [*state.preparations, result], "current_run_id": None,
                                              "current_assessment_ids": {}})
            return updated, result
        result = self._operate(handle, "prepare", request, PreparationResult, execute)
        self._ensure_current_revision(handle, result.source_revision)
        return result

    def retrieve_evidence(self, handle: WorkspaceHandle, request: RetrieveEvidenceRequest) -> EvidenceRun:
        return self._retrieve_evidence(handle, request, "retrieve")

    def retrieve_evidence_bound(self, handle: WorkspaceHandle, request: BoundRetrieveEvidenceRequest) -> EvidenceRun:
        return self._retrieve_evidence(handle, request, "retrieve_bound_v1")

    def _retrieve_evidence(self, handle, request, operation):
        def execute(state):
            if not state.preparations:
                raise MvpError("sources_not_prepared", "Select and prepare sources before passage search.")
            preparation = state.preparations[-1]
            # This executes under the same workspace lock as retrieval/commit,
            # rather than an API preflight that could race with preparation.
            if isinstance(request, BoundRetrieveEvidenceRequest) and (
                request.expected_preparation_id != preparation.id
                or request.expected_source_revision != state.source_revision
            ):
                raise MvpError("stale_preparation", "Prepared sources changed since this form was loaded. Keep your question and reload the current preparation.")
            _assert_source_integrity(state.sources)
            run_id = new_id()
            passages, indexed, matched = self._retrieval.search(request.question, state.sources, run_id, request.top_k)
            result = EvidenceRun(id=run_id, search_id=preparation.search_id, preparation_id=preparation.id,
                                 source_revision=state.source_revision, source_snapshot_sha256=digest(_manifest(state.sources)),
                                 question=request.question, passages=passages, indexed_passages=indexed,
                                 matched_passages=matched, parameters=self._retrieval.parameters)
            return state.model_copy(update={"runs": [*state.runs, result], "current_run_id": result.id}), result
        result = self._operate(handle, operation, request, EvidenceRun, execute)
        self._current_run(self._storage.read(handle), result.id)
        return result

    def _ensure_current_revision(self, handle, source_revision):
        if source_revision != self._storage.read(handle).source_revision:
            raise MvpError("stale_source_revision", "This request belongs to an older source selection. Submit a new request for the current sources; history is preserved.")

    @staticmethod
    def _current_run(state, run_id):
        run = _find(state.runs, run_id, "run")
        _assert_source_integrity(state.sources)
        if run.source_revision != state.source_revision or run.source_snapshot_sha256 != digest(_manifest(state.sources)):
            raise MvpError("stale_source_revision", "Selected or prepared sources changed. Run passage search again; your existing judgments remain in history.")
        return run

    def get_source_context(self, handle: WorkspaceHandle, request: SourceContextRequest) -> SourceContext:
        state = self._storage.read(handle)
        run = self._current_run(state, request.run_id)
        return self._source_context(state, run, state.sources, request.passage_id)

    def get_historical_source_context(self, handle: WorkspaceHandle, request: SourceContextRequest) -> SourceContext:
        """Read an original run/preparation/search without relaxing current guards."""
        state = self._storage.read(handle)
        run = _find(state.runs, request.run_id, "run")
        preparation = _find(state.preparations, run.preparation_id, "preparation")
        if (preparation.search_id != run.search_id
                or preparation.source_revision != run.source_revision
                or digest(_manifest(preparation.sources)) != run.source_snapshot_sha256):
            raise MvpError("source_integrity_error", "Archived run did not match its original preparation.")
        _assert_source_integrity(preparation.sources)
        return self._source_context(state, run, preparation.sources, request.passage_id)

    @staticmethod
    def _source_context(state, run, sources, passage_id):
        passage = _find(run.passages, passage_id, "passage")
        source = _find(sources, passage.source_id, "source")
        block = _find(source.blocks, passage.anchor.block_id, "block")
        anchor = passage.anchor
        if (passage.paper_id != source.paper_id
                or passage.source_version != source.version or passage.source_sha256 != source.source_sha256
                or passage.blocks_sha256 != source.blocks_sha256
                or source.blocks_sha256 != digest([item.model_dump(mode="json") for item in source.blocks])
                or not 0 <= anchor.start < anchor.end <= len(block.text)
                or block.text[anchor.start:anchor.end] != anchor.quote):
            raise MvpError("source_integrity_error", "Retained quotation did not match its canonical source snapshot.")
        paper = _find(_find(state.searches, run.search_id, "search").papers, passage.paper_id, "paper")
        return SourceContext(run_id=run.id, passage=passage, source=source, paper=paper, block=block)

    def save_assessment(self, handle: WorkspaceHandle, request: SaveAssessmentRequest) -> Assessment:
        def execute(state):
            run = self._current_run(state, request.run_id)
            current = state.current_assessment_ids.get(run.id)
            if request.supersedes_id != current:
                raise MvpError("stale_assessment", "A newer assessment exists. Reload its committed version before revising; keep your draft for comparison.")
            passage_ids = {passage.id for passage in run.passages}
            judgments = {judgment.passage_id: judgment for judgment in request.passages}
            if len(judgments) != len(request.passages) or not judgments.keys() <= passage_ids:
                raise MvpError("invalid_passage_judgment", "Passage judgments must uniquely reference this run's passages.")
            if not set(request.bundle.supporting_passage_ids) <= passage_ids:
                raise MvpError("invalid_bundle_support", "Supporting passages must belong to this evidence run.")
            result = Assessment(run_id=run.id, source_revision=run.source_revision,
                                source_snapshot_sha256=run.source_snapshot_sha256,
                                supersedes_id=current, passages=[judgments.get(passage.id, PassageJudgment(passage_id=passage.id)) for passage in run.passages],
                                bundle=request.bundle, feedback=request.feedback)
            current_ids = {**state.current_assessment_ids, run.id: result.id}
            return state.model_copy(update={"assessments": [*state.assessments, result], "current_assessment_ids": current_ids}), result
        result = self._operate(handle, "assess", request, Assessment, execute)
        state = self._storage.read(handle)
        self._current_run(state, result.run_id)
        if state.current_assessment_ids.get(result.run_id) != result.id:
            raise MvpError("stale_assessment", "This request returned a superseded assessment. Reload the current committed assessment and keep your draft for comparison.")
        return result

    def export_workspace(self, handle: WorkspaceHandle) -> WorkspaceExport:
        state = self._storage.read(handle)
        rows = []
        for run in state.runs:
            search = _find(state.searches, run.search_id, "search")
            preparation = _find(state.preparations, run.preparation_id, "preparation")
            # Old assessments remain exportable after source changes clear the current pointers.
            assessment_id = next((item.id for item in reversed(state.assessments) if item.run_id == run.id), None)
            assessment = _find(state.assessments, assessment_id, "assessment") if assessment_id else None
            judgments = {judgment.passage_id: judgment for judgment in assessment.passages} if assessment else {}
            for passage in run.passages:
                paper = _find(search.papers, passage.paper_id, "paper")
                source = _find(preparation.sources, passage.source_id, "source")
                judgment = judgments.get(passage.id, PassageJudgment(passage_id=passage.id))
                rows.append({
                    "workspace_id": state.id, "question": run.question, "search_id": search.id, "search_query": search.query,
                    "search_mode": search.mode, "run_id": run.id, "passage_id": passage.id,
                    "citation": "; ".join(paper.authors) + (f" ({paper.year}) " if paper.year else " ") + paper.title,
                    "title": paper.title, "pmid": paper.pmid, "doi": paper.doi, "pmcid": paper.pmcid,
                    "source_type": passage.source_type, "source_status": source.status, "source_url": source.source_url,
                    "quotation": passage.anchor.quote, "locator": passage.locator, "block_id": passage.anchor.block_id,
                    "start": passage.anchor.start, "end": passage.anchor.end, "source_id": source.id,
                    "source_version": passage.source_version, "source_sha256": passage.source_sha256, "blocks_sha256": passage.blocks_sha256,
                    "method": run.method, "method_version": run.method_version, "decision": judgment.decision,
                    "notes": judgment.notes, "assessment_id": assessment_id, "bundle_judgment": assessment.bundle.status if assessment else "not_assessed",
                    "bundle_reason": assessment.bundle.reason if assessment else "", "supporting_passage_ids": assessment.bundle.supporting_passage_ids if assessment else [],
                    "missing_information": assessment.bundle.missing_information if assessment else "", "contradiction": assessment.bundle.contradiction if assessment else False,
                    "review_state": assessment.review_state if assessment else "unreviewed", "feedback": assessment.feedback if assessment else "",
                    "source_revision": run.source_revision, "source_binding_current": run.source_revision == state.source_revision,
                    "searched_at": search.searched_at, "retrieved_at": source.retrieved_at, "run_created_at": run.created_at,
                    "assessed_at": assessment.created_at if assessment else "",
                })
        fields = list(rows[0]) if rows else ["workspace_id", "question", "search_id", "run_id", "passage_id", "citation", "pmid", "doi", "source_type", "quotation", "locator", "source_version", "source_sha256", "method", "decision", "notes", "assessed_at"]
        audit = {"schema_version": "mvp.audit-bundle.v1", "exported_at": now(),
                 "offset_convention": "half-open-unicode-codepoints", "workspace": state.model_dump(mode="json"),
                 "limitations": ["Exploratory samples are not comprehensive captures or formal inclusion decisions.",
                                 "Judgments are self-declared by one human and not independently verified.",
                                 "Insufficient means this retrieved bundle lacks support, not that an article or the literature lacks an answer."]}
        # Keep the shared exporter, with a narrow extra guard for spreadsheets
        # that trim leading whitespace before interpreting a formula. JSON keeps
        # every original character and remains the canonical audit record.
        safe_rows = [{key: "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value
                      for key, value in row.items()} for row in rows]
        return WorkspaceExport(csv_text=_csv(safe_rows, fields), json_text=json.dumps(audit, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n")

    def clear_workspace(self, handle: WorkspaceHandle) -> ClearResult:
        self._storage.clear(handle)
        return ClearResult()

    def clear_workspace_if_present(self, handle: WorkspaceHandle) -> ClearResult:
        """For an authorized server-side deletion reservation, never UUID recovery."""
        self._storage.clear_if_present(handle)
        return ClearResult()
