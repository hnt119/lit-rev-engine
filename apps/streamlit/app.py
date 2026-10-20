"""Replaceable Streamlit presentation; research state and rules live in src.mvp."""
from datetime import date
from html import escape
from pathlib import Path
import json
import os
import sys
from urllib.parse import urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from pydantic import ValidationError

from src.mvp.bootstrap import build_service, public_runtime_info
from src.mvp.contracts import (
    BundleJudgment, CreateWorkspaceRequest, PassageJudgment, PrepareSourcesRequest,
    QuerySuggestionRequest, RetrieveEvidenceRequest, SaveAssessmentRequest,
    SearchRequest, SourceContextRequest, WorkspaceHandle,
)
from src.mvp.ports import MvpError
from apps.streamlit.navigation import scroll_reset_html
from apps.streamlit.theme import load_theme

SAMPLE_QUESTION = "How is the gut microbiome associated with diet and reproductive health in Asian women?"
SCREENS = ("Discover", "Prepare sources", "Evidence & export")
DECISIONS = {"unreviewed": "Unreviewed", "useful": "Useful", "not_useful": "Not useful", "uncertain": "Uncertain"}
STATUSES = {"not_assessed": "Not assessed", "sufficient": "Sufficient", "partial": "Partial", "insufficient": "Insufficient", "uncertain": "Uncertain"}


def key_for(operation, payload):
    """Keep the same submission key on an ambiguous retry; refresh is explicit."""
    fingerprint = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    key = "pending_" + operation
    pending = st.session_state.get(key)
    if pending is None or pending[0] != fingerprint:
        pending = (fingerprint, str(uuid4()))
        st.session_state[key] = pending
    return pending[1]


def show_error(error):
    if isinstance(error, MvpError):
        st.error(error.message)
    elif isinstance(error, ValidationError):
        messages = [str(row.get("msg", "Invalid form value")) for row in error.errors(include_input=False)]
        st.error("Please check the form: " + "; ".join(messages))
    else:
        st.error("This operation could not finish. Your form is preserved; try again or export your saved work.")


def original_link(url, label="Open original source"):
    try:
        parsed = urlsplit(url)
        allowed = {"pubmed.ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov", "europepmc.org", "www.ebi.ac.uk", "doi.org"}
        if parsed.scheme == "https" and parsed.hostname in allowed and not parsed.username and not parsed.password:
            st.link_button(label, url)
    except ValueError:
        pass


def citation(paper):
    st.text(paper.title)
    authors = ", ".join(paper.authors[:4]) or "Authors not supplied"
    if len(paper.authors) > 4:
        authors += " et al."
    st.caption(f"{authors} · {paper.year or 'Year unknown'}")
    identifiers = [f"PMID {paper.pmid}" if paper.pmid else "", f"DOI {paper.doi}" if paper.doi else ""]
    st.caption(" · ".join(item for item in identifiers if item))


def choose_screen(screen):
    st.session_state["navigate_to"] = screen
    st.rerun()


def retain_control_drafts():
    """Keep session drafts independent of whether their widgets are rendered.

    Incoming widget values take precedence. Explicit reassignment detaches the
    keys from Streamlit's hidden-widget cleanup; the non-widget dictionary can
    restore them if a screen has already removed its widget state. This does
    not provide recovery after the anonymous Streamlit session ends.
    """
    drafts = dict(st.session_state.get("_control_drafts", {}))
    for name in ("research_question", "pubmed_query", "passage_question"):
        if name in st.session_state:
            drafts[name] = st.session_state[name]
        if name in drafts:
            st.session_state[name] = drafts[name]
    st.session_state["_control_drafts"] = drafts


def finish_screen_navigation(screen):
    """Reset the browser viewport only when the workflow screen has changed."""
    previous = st.session_state.get("_rendered_workflow_screen")
    st.session_state["_rendered_workflow_screen"] = screen
    if previous is None or previous == screen:
        return
    revision = st.session_state.get("_workflow_navigation_revision", 0) + 1
    st.session_state["_workflow_navigation_revision"] = revision
    # This contains only a trusted local script and an internal integer marker.
    # Source quotations continue to use escaped, non-executable HTML separately.
    st.html(scroll_reset_html(revision), unsafe_allow_javascript=True)


def discover(service, handle, snapshot, mode, info):
    st.header("1. Discover literature")
    if st.button("Use gut microbiome sample", disabled=mode == "saved_example"):
        st.session_state["research_question"] = SAMPLE_QUESTION
        try:
            result = service.suggest_query(handle, QuerySuggestionRequest(question=SAMPLE_QUESTION))
            st.session_state["pubmed_query"] = result.query
        except (MvpError, ValidationError) as error:
            show_error(error)
    question = st.text_area("Research question", key="research_question", height=100)
    if mode == "saved_example":
        example = info.get("saved_example", {})
        st.info("Saved example · offline. Opens one real, licensed article from a preserved Europe PMC search. These are historical example records, not a new PubMed search.")
        query = example.get("query", "")
        st.text_area("Saved discovery query", value=query, disabled=True, height=100)
        st.caption("Edit the question above to search passages in the saved article. Switch to Live PubMed in a new workspace to discover other topics.")
    else:
        if st.button("Propose editable query"):
            try:
                result = service.suggest_query(handle, QuerySuggestionRequest(question=question))
                st.session_state["pubmed_query"] = result.query
                st.session_state["query_explanation"] = result.explanation
            except (MvpError, ValidationError) as error:
                show_error(error)
        st.caption(st.session_state.get("query_explanation", "The initial query uses explicit concepts. Review and edit it before searching; no model is used."))
    with st.form("discovery_form", clear_on_submit=False, enter_to_submit=False, border=False):
        if mode == "live":
            query = st.text_area("PubMed query", key="pubmed_query", height=120)
        maximum, sort, use_dates, date_from, date_to, refresh = 30, "relevance", False, None, None, False
        if mode == "live":
            col1, col2 = st.columns(2)
            maximum = col1.number_input("Maximum records", min_value=1, max_value=50, value=30, step=1)
            sort = col2.selectbox("Sort", ("relevance", "pub_date"), format_func=lambda value: "Relevance" if value == "relevance" else "Newest publication")
            use_dates = st.checkbox("Restrict publication dates")
            st.caption("Date restrictions require both From and Through; otherwise leave the restriction unchecked.")
            d1, d2 = st.columns(2)
            date_from = d1.date_input("From", value=date(2020, 1, 1), disabled=not use_dates)
            date_to = d2.date_input("Through", value=None, disabled=not use_dates)
            refresh = st.checkbox("Explicit refresh — create a new search run", help="Ordinary reruns and identical retries reuse the saved request. Check this to run the same search again.")
        submitted = st.form_submit_button("Search literature", type="primary", disabled=mode == "live" and not info["live_available"])
    if submitted:
        payload = {"query": query, "max_results": int(maximum), "sort": sort, "research_question": question,
                   "date_from": date_from.isoformat() if use_dates and date_from else None,
                   "date_to": date_to.isoformat() if use_dates and date_to else None}
        if refresh:
            st.session_state.pop("pending_search", None)
        try:
            with st.spinner("Finding publications…"):
                result = service.search_literature(handle, SearchRequest(request_id=key_for("search", payload), **payload))
            st.session_state["selected_search_id"] = result.id
            st.success(f"Saved {len(result.papers)} distinct paper records. Review the search provenance below.")
            snapshot = service.get_workspace(handle)
        except (MvpError, ValidationError) as error:
            show_error(error)
    if snapshot.searches:
        searches = list(reversed(snapshot.searches))
        ids = [item.id for item in searches]
        selected = st.selectbox("Saved search run", ids, format_func=lambda value: next(item.searched_at[:19] + " · " + item.provider for item in searches if item.id == value), key="selected_search_id")
        result = next(item for item in searches if item.id == selected)
        st.subheader(f"Showing {result.fetched_count} of {result.total_reported} reported matches")
        st.caption(f"{len(result.papers)} distinct displayed records · {'Capped/curated sample' if result.truncated else 'Returned membership'} · {result.provider} · {result.mode}")
        for warning in result.warnings:
            st.warning(warning)
        for issue in result.errors:
            st.warning(issue.message)
        with st.expander("Exact query, translation and search provenance"):
            st.text(result.query)
            st.text(result.query_translation or "Query translation not supplied")
            st.json({"search_id": result.id, "searched_at": result.searched_at, "sort": result.sort,
                     "ordered_identifiers": result.ordered_identifiers, "truncated": result.truncated, "schema": result.schema_version})
        for paper in result.papers:
            with st.container():
                citation(paper)
                original_link(paper.url, "PubMed / original record")
                with st.expander("Abstract"):
                    st.text(paper.abstract or "No abstract supplied.")
            st.divider()
        if result.papers and st.button("Continue to source selection", type="primary"):
            st.session_state["prepare_search_id"] = selected
            choose_screen("Prepare sources")
    else:
        st.caption("Searches are exploratory samples. The app does not determine formal study eligibility or whether a cohort represents Asian women.")


def prepare(service, handle, snapshot):
    st.header("2. Select and prepare sources")
    st.caption("Select up to 10 papers for exploration. Selection is not a screening decision, formal inclusion or independent verification.")
    if not snapshot.searches:
        st.info("Discover publications first.")
        return
    search_ids = [item.id for item in reversed(snapshot.searches)]
    selected_search = st.session_state.get("selected_search_id")
    if selected_search not in search_ids:
        selected_search = search_ids[0]
    if st.session_state.get("prepare_search_id") not in search_ids:
        st.session_state["prepare_search_id"] = selected_search
    search_id = st.selectbox("Search to select from", search_ids, key="prepare_search_id", format_func=lambda value: next(item.searched_at[:19] + " · " + item.provider for item in snapshot.searches if item.id == value))
    search = next(item for item in snapshot.searches if item.id == search_id)
    papers = {paper.id: paper for paper in search.papers}
    with st.form("prepare_form", clear_on_submit=False, border=False):
        selected = st.multiselect("Papers for exploration (maximum 10)", list(papers), default=[item for item in snapshot.selected_paper_ids if item in papers], max_selections=10,
                                  format_func=lambda value: papers[value].title, key="paper_selection_" + search_id)
        refresh = st.checkbox("Refresh sources — create a new source revision", help="Changed selections or source refresh invalidate the current evidence run.")
        submitted = st.form_submit_button("Prepare selected papers", type="primary", disabled=not papers)
    if submitted:
        payload = {"search_id": search_id, "paper_ids": selected}
        if refresh:
            st.session_state.pop("pending_prepare", None)
        try:
            with st.spinner("Checking permitted open-access XML; preparing explicit abstract fallbacks…"):
                result = service.prepare_sources(handle, PrepareSourcesRequest(request_id=key_for("prepare", payload), **payload))
            st.success(f"Prepared {len(result.sources)} sources. Evidence will use source revision {result.source_revision}.")
            snapshot = service.get_workspace(handle)
        except (MvpError, ValidationError) as error:
            show_error(error)
    if snapshot.sources:
        st.subheader("Current prepared sources")
        st.caption("Passage search uses these committed sources. Changes in the selection form take effect when you prepare them.")
        prepared_search = next(search for search in snapshot.searches if search.id == snapshot.preparations[-1].search_id)
        latest = {paper.id: paper for paper in prepared_search.papers}
        for source in snapshot.sources:
            with st.container():
                citation(latest[source.paper_id])
                st.markdown(f"**{source.source_type.replace('_', ' ').title()}** · {source.status.replace('_', ' ')}")
                for warning in source.warnings:
                    st.warning(warning)
                if source.error:
                    st.warning(source.error.message)
                st.caption(f"Provider: {source.provider} · Retrieved: {source.retrieved_at} · Version: {source.version}")
                st.text("License: " + (source.license or "Not supplied / reuse unresolved"))
                if source.attribution:
                    st.text(source.attribution)
                original_link(source.source_url)
            st.divider()
        if any(source.blocks for source in snapshot.sources) and st.button("Continue to passage search", type="primary"):
            choose_screen("Evidence & export")


def assessment_editor(service, handle, snapshot, run, papers):
    """Keep every passage and its judgment in the same responsive layout row."""
    current_id = snapshot.current_assessment_ids.get(run.id)
    current = next((item for item in snapshot.assessments if item.id == current_id), None)
    draft_key = "assessment_draft_" + run.id
    if draft_key not in st.session_state:
        st.session_state[draft_key] = {"supersedes_id": None, "base": {}}
    draft = st.session_state[draft_key]
    if current:
        st.success("A single-user assessment is saved for this run. It is not independently verified.")
        if st.button("Revise saved assessment", key="revise_" + run.id):
            st.session_state[draft_key] = {"supersedes_id": current.id, "base": current.model_dump(mode="json")}
            # New widget keys load the chosen immutable revision while retaining earlier drafts.
            st.session_state["edit_generation_" + run.id] = st.session_state.get("edit_generation_" + run.id, 0) + 1
            st.rerun()
    generation = st.session_state.get("edit_generation_" + run.id, 0)
    suffix = run.id + "_" + str(generation)
    base = draft.get("base", {})
    saved_passages = {item["passage_id"]: item for item in base.get("passages", [])}
    bundle = base.get("bundle", {})
    if draft["supersedes_id"]:
        st.caption("This submission will explicitly supersede the selected saved assessment and preserve its history.")
    with st.form("assessment_" + suffix, clear_on_submit=False, enter_to_submit=False, border=False):
        decisions = []
        for index, passage in enumerate(run.passages):
            old = saved_passages.get(passage.id, {})
            selected = old.get("decision", "unreviewed")
            with st.container(key="passage-row-" + passage.id):
                left, right = st.columns([1, 1], gap="large")
                with left, st.container(key="passage-evidence-" + passage.id):
                    st.markdown(f"**Passage {passage.rank} · {passage.source_type.replace('_', ' ').title()}**")
                    citation(papers[passage.paper_id])
                    st.text(passage.anchor.quote)
                    st.caption("Locator: " + json.dumps(passage.locator, ensure_ascii=False))
                    # A form submit sends the current draft widgets without saving an
                    # assessment. Only the explicit Save assessment button does that.
                    if st.form_submit_button("Inspect source", key="inspect_" + run.id + passage.id):
                        st.session_state["context_" + run.id] = passage.id
                    if st.session_state.get("context_" + run.id) == passage.id:
                        st.markdown("[Read selected source context ↓](#verifiable-source-context)")
                with right, st.container(key="passage-judgment-" + passage.id):
                    st.markdown(f"**Passage {passage.rank}**")
                    decision = st.selectbox("Passage decision", list(DECISIONS), index=list(DECISIONS).index(selected), format_func=DECISIONS.get, key="decision_" + passage.id + suffix)
                    note = st.text_area("Notes", value=old.get("notes", ""), key="notes_" + passage.id + suffix, height=70)
                if index < len(run.passages) - 1:
                    st.divider()
            decisions.append({"passage_id": passage.id, "decision": decision, "notes": note})
        _, bundle_column = st.columns([1, 1], gap="large")
        with bundle_column, st.container(key="bundle-judgment"):
            status = st.selectbox("Bundle support", list(STATUSES), index=list(STATUSES).index(bundle.get("status", "not_assessed")), format_func=STATUSES.get, key="status_" + suffix)
            reason = st.text_area("Reason for bundle judgment", value=bundle.get("reason", ""), key="reason_" + suffix)
            missing = st.text_area("Missing information", value=bundle.get("missing_information", ""), key="missing_" + suffix,
                                   help="Required for partial or insufficient. Describes gaps in the retrieved bundle, not absence from the article or literature.")
            ids = [passage.id for passage in run.passages]
            supporting = st.multiselect("Supporting passages", ids, default=bundle.get("supporting_passage_ids", []), format_func=lambda value: "Passage " + str(next(p.rank for p in run.passages if p.id == value)), key="support_" + suffix)
            contradiction = st.checkbox("Contradictory evidence is present", value=bundle.get("contradiction", False), key="contradiction_" + suffix)
            feedback = st.text_area("Optional usefulness / feedback", value=base.get("feedback", ""), key="feedback_" + suffix, height=70)
            submitted = st.form_submit_button("Save assessment", type="primary")
    if submitted:
        payload = {"run_id": run.id, "supersedes_id": draft["supersedes_id"], "passages": decisions,
                   "bundle": {"status": status, "reason": reason, "missing_information": missing,
                              "supporting_passage_ids": supporting, "contradiction": contradiction}, "feedback": feedback}
        try:
            request = SaveAssessmentRequest(request_id=key_for("assess_" + run.id, payload), **payload)
            record = service.save_assessment(handle, request)
            st.success("Assessment saved. Ordinary reruns retain it. Use Revise saved assessment for a correction.")
            st.caption("Saved at " + record.created_at)
        except (MvpError, ValidationError) as error:
            show_error(error)
    records = [item for item in service.get_workspace(handle).assessments if item.run_id == run.id]
    if records:
        with st.expander(f"Immutable assessment history ({len(records)} records)"):
            for item in reversed(records):
                st.text(f"{item.created_at} · {item.bundle.status} · {'revision' if item.supersedes_id else 'first submission'}")
                st.text(item.bundle.reason or "Bundle not assessed")


def evidence(service, handle, snapshot):
    st.header("3. Evidence and export")
    st.caption("Passage search · BM25 lexical baseline · No generated scientific answer. Relevance scores are not confidence percentages.")
    if not snapshot.sources:
        st.info("Select and prepare papers first.")
        exports(service, handle)
        return
    with st.form("passage_form", clear_on_submit=False, enter_to_submit=False, border=False):
        question = st.text_area("Question for selected sources", value=st.session_state.get("research_question", snapshot.question), key="passage_question", height=100)
        refresh = st.checkbox("Explicit refresh — create a new passage run")
        submitted = st.form_submit_button("Search passages", type="primary")
    if submitted:
        payload = {"question": question, "top_k": 5, "source_revision": snapshot.source_revision}
        if refresh:
            st.session_state.pop("pending_retrieve", None)
        try:
            with st.spinner("Searching retained source passages…"):
                request = RetrieveEvidenceRequest(request_id=key_for("retrieve", payload), question=question, top_k=5)
                service.retrieve_evidence(handle, request)
            snapshot = service.get_workspace(handle)
        except (MvpError, ValidationError) as error:
            show_error(error)
    run = next((item for item in snapshot.runs if item.id == snapshot.current_run_id), None)
    if not run:
        st.info("No current passage run. Changing selected sources invalidates previous results; search the current source revision.")
        exports(service, handle)
        return
    st.text(run.question)
    st.caption(f"Source revision {run.source_revision} · {len(run.passages)} displayed passages · Single-user judgments · Not independently verified")
    if not run.passages:
        st.info("No matching passages. Try a more specific term or inspect the selected sources. The app has not established source answerability.")
        exports(service, handle)
        return
    run_search = next(search for search in snapshot.searches if search.id == run.search_id)
    papers = {paper.id: paper for paper in run_search.papers}
    with st.container(key="evidence-columns"):
        left, right = st.columns([1, 1], gap="large")
        with left, st.container(key="retrieved-passages"):
            st.subheader("Retrieved passages")
        with right, st.container(key="reviewer-judgments"):
            st.subheader("Record your judgments")
        assessment_editor(service, handle, snapshot, run, papers)
    with st.container(key="source-context-section"):
        st.subheader("Verifiable source context")
        st.caption("Inspect a passage above or choose one below to read its exact quotation in the retained source.")
        ids = [passage.id for passage in run.passages]
        context_key = "context_" + run.id
        if st.session_state.get(context_key) not in ids:
            st.session_state[context_key] = ids[0]
        passage_id = st.selectbox("Inspect passage", ids, format_func=lambda value: "Passage " + str(next(p.rank for p in run.passages if p.id == value)), key=context_key)
        try:
            context = service.get_source_context(handle, SourceContextRequest(run_id=run.id, passage_id=passage_id))
            citation(context.paper)
            st.caption(context.source.source_type.replace("_", " ").title() + " · " + context.source.provider)
            original_link(context.paper.url, "Publication record")
            original_link(context.source.source_url)
            anchor = context.passage.anchor
            text = context.block.text
            # Service validates the half-open Unicode code-point anchor; all text is escaped.
            marked = escape(text[:anchor.start]) + "<mark>" + escape(text[anchor.start:anchor.end]) + "</mark>" + escape(text[anchor.end:])
            st.markdown('<div class="source-context">' + marked + '</div>', unsafe_allow_html=True)
            st.text("Locator: " + json.dumps(context.block.locator, ensure_ascii=False))
            st.caption("Source version " + context.source.version + " · SHA-256 " + context.source.source_sha256)
            if context.source.license:
                st.text("License: " + context.source.license)
            if context.source.attribution:
                st.text(context.source.attribution)
            with st.expander("Surrounding retained source blocks"):
                for block in context.source.blocks:
                    st.caption("Block " + str(block.ordinal))
                    st.text(block.text)
        except (MvpError, ValidationError) as error:
            show_error(error)
    exports(service, handle)


def exports(service, handle):
    st.divider()
    st.subheader("Export your evidence")
    st.caption("Includes unreviewed passages, search provenance, exact citations, source hashes and assessment history. A single-user judgment is not independently verified.")
    try:
        result = service.export_workspace(handle)
        col1, col2 = st.columns(2)
        col1.download_button("Download evidence CSV", data=result.csv_text, file_name="evidence-table.csv", mime="text/csv", on_click="ignore")
        col2.download_button("Download audit JSON", data=result.json_text, file_name="review-workspace-v1.json", mime="application/json", on_click="ignore")
    except (MvpError, ValidationError) as error:
        show_error(error)


def main():
    st.set_page_config(page_title="Literature Review Engine", layout="wide")
    st.markdown("<style>" + load_theme() + "</style>", unsafe_allow_html=True)
    info = public_runtime_info()
    retain_control_drafts()
    if "navigate_to" in st.session_state:
        st.session_state["screen"] = st.session_state.pop("navigate_to")
    mode_default = os.environ.get("MVP_MODE", "saved_example")
    if mode_default not in {"live", "saved_example"}:
        mode_default = "saved_example"
    st.session_state.setdefault("provider_mode", mode_default)
    st.session_state.setdefault("research_question", SAMPLE_QUESTION)
    st.session_state.setdefault("pubmed_query", '("gastrointestinal microbiome"[MeSH Terms] OR "gut microbiome"[Title/Abstract] OR "gut microbiota"[Title/Abstract]) AND (women[Title/Abstract] OR female[MeSH Terms]) AND (Asia[MeSH Terms] OR Asian[Title/Abstract] OR China[Title/Abstract] OR Singapore[Title/Abstract] OR Malaysia[Title/Abstract] OR Thailand[Title/Abstract] OR Vietnam[Title/Abstract])')
    try:
        effective_mode = st.session_state["provider_mode"]
        if effective_mode == "live" and not info["live_available"]:
            effective_mode = "saved_example"  # Storage remains available; live search stays disabled.
        service = build_service(mode=effective_mode)
        if "workspace_handle" not in st.session_state:
            handle = service.create_workspace(CreateWorkspaceRequest(question=st.session_state["research_question"]))
            st.session_state["workspace_handle"] = handle.model_dump()
        handle = WorkspaceHandle.model_validate(st.session_state["workspace_handle"])
        snapshot = service.get_workspace(handle)
    except (MvpError, ValidationError, OSError):
        st.error("The private workspace is unavailable. Check the server configuration or start a new local session.")
        st.stop()
    with st.sidebar:
        st.caption("LITERATURE REVIEW ENGINE")
        st.title("Research workspace")
        st.caption("Local · exploratory · no paid inference")
        current_mode = st.selectbox("Discovery source", ("saved_example", "live"), index=(0 if st.session_state["provider_mode"] == "saved_example" else 1), format_func=lambda value: "Saved example (offline)" if value == "saved_example" else "Live PubMed", disabled=bool(snapshot.searches))
        if current_mode != st.session_state["provider_mode"] and not snapshot.searches:
            st.session_state["provider_mode"] = current_mode
            st.rerun()
        if st.session_state["provider_mode"] == "live" and not info["live_available"]:
            st.warning("Live discovery is not configured on this server. Use the saved example or follow the setup guide.")
        st.radio("Workflow", SCREENS, key="screen")
        st.divider()
        st.caption("Saved work persists across ordinary reruns. Anonymous sessions have no cross-device recovery. Export before clearing or closing your session.")
        confirm = st.checkbox("I have exported anything I want to keep")
        if st.button("Clear session and local workspace", disabled=not confirm):
            try:
                service.clear_workspace(handle)
                st.session_state.clear()
                st.rerun()
            except MvpError as error:
                show_error(error)
        st.caption("Study location and reported ethnicity are different. Population details remain unknown unless you inspect the source.")
    screen = st.session_state["screen"]
    with st.container(key="landing" if screen == "Discover" else "workspace"):
        st.caption("EVIDENCE YOU CAN INSPECT · MVP 0.1")
        st.title("Follow the evidence.")
        st.write("Discover publications, inspect source passages and build an evidence table.")
        st.caption("Exploratory research assistance. No automated screening, synthesis or clinical validation.")
        st.divider()
        if screen == "Discover":
            discover(service, handle, snapshot, st.session_state["provider_mode"], info)
        elif screen == "Prepare sources":
            prepare(service, handle, snapshot)
        else:
            evidence(service, handle, snapshot)
    finish_screen_navigation(screen)


if __name__ == "__main__":
    main()
