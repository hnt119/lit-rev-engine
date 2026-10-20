"""Presentation regressions using synthetic source text and an offline workspace.

These checks verify layout structure and canonical source rendering. They do not
measure publication relevance, reviewer agreement, or live PubMed behavior.
"""

from hashlib import sha256
from html import escape
from html.parser import HTMLParser
from pathlib import Path
import re
import socket
import tomllib

import pytest

from src.mvp.contracts import (
    Block, CreateWorkspaceRequest, Paper, PreparedSource, PrepareSourcesRequest,
    RetrieveEvidenceRequest, SearchPreview, SearchRequest, SourceContextRequest,
    digest,
)

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_TOKENS = {
    "--paper": "#f7f6f2",
    "--ink": "#272923",
    "--muted": "#6b6e64",
    "--line": "#e1e2da",
    "--accent": "#667358",
    "--mono": "'SFMono-Regular', Consolas, 'Liberation Mono', monospace",
}
SOURCE_TEXTS = (
    'Microbiome fixture α <script>window.__unsafe = true</script> & "quoted" text.',
    'Microbiome fixture 女人 😀 <img src=x onerror="unsafe()"> & second context.',
)


@pytest.fixture
def presentation(tmp_path, monkeypatch):
    pytest.importorskip("streamlit.testing.v1", reason="UI checks require focused MVP dependencies")
    from streamlit.testing.v1 import AppTest
    import src.mvp.bootstrap as bootstrap
    from src.mvp.adapters.storage import SQLiteWorkspaceStorage
    from src.mvp.service import MVPService

    def denied(*args, **kwargs):
        pytest.fail("Presentation regression attempted network access")

    monkeypatch.setattr(socket, "create_connection", denied)

    class SyntheticProvider:
        searches = 0
        preparations = 0
        record = Paper(
            title="Synthetic UI fixture; not publication evidence",
            authors=["Software fixture"], year=2020, pmid="99999999",
            abstract="\n\n".join(SOURCE_TEXTS),
            url="https://pubmed.ncbi.nlm.nih.gov/99999999/",
        )

        def search(self, request):
            self.searches += 1
            return SearchPreview(
                query=request.query, total_reported=1, fetched_count=1,
                ordered_identifiers=[self.record.pmid], papers=[self.record],
                truncated=False, mode="test", provider="synthetic-ui-fixture",
            )

        def prepare(self, record):
            self.preparations += 1
            blocks = [Block(
                id=f"abstract:{number}", ordinal=number, text=text,
                locator={"type": "abstract", "ordinal": number},
            ) for number, text in enumerate(SOURCE_TEXTS, 1)]
            return PreparedSource(
                paper_id=record.id, status="abstract_only", source_type="abstract",
                provider="synthetic-ui-fixture", source_url=record.url,
                source_sha256=sha256(record.abstract.encode()).hexdigest(),
                blocks_sha256=digest([block.model_dump(mode="json") for block in blocks]),
                parser_id="synthetic-ui-fixture.v1", blocks=blocks,
                source_identifiers={"pmid": record.pmid},
                warnings=["Synthetic software fixture; not publication evidence"],
            )

    provider = SyntheticProvider()
    service = MVPService(SQLiteWorkspaceStorage(tmp_path / "presentation.sqlite3"), provider, provider)
    handle = service.create_workspace(CreateWorkspaceRequest(question="Microbiome fixture"))
    search = service.search_literature(handle, SearchRequest(request_id="search", query="microbiome"))
    service.prepare_sources(handle, PrepareSourcesRequest(
        request_id="prepare", search_id=search.id, paper_ids=[provider.record.id],
    ))
    run = service.retrieve_evidence(handle, RetrieveEvidenceRequest(request_id="retrieve", question="microbiome"))
    assert len(run.passages) == 2
    monkeypatch.setenv("MVP_MODE", "saved_example")
    monkeypatch.setattr(bootstrap, "build_service", lambda **kwargs: service)
    app = AppTest.from_file(str(ROOT / "apps/streamlit/app.py"), default_timeout=20)
    app.session_state["workspace_handle"] = handle.model_dump(mode="json")
    app.session_state["screen"] = "Evidence & export"
    app.run()
    assert not app.exception
    return app, service, handle, run, provider


def test_each_passage_and_its_judgment_share_one_row_before_source_context(presentation):
    app, _, _, run, _ = presentation
    workspace = app.main.get_by_key("evidence-columns")
    evidence_heading = workspace.get_by_key("retrieved-passages")
    judgment_heading = workspace.get_by_key("reviewer-judgments")
    assert [heading.value for heading in evidence_heading.subheader] == ["Retrieved passages"]
    assert [heading.value for heading in judgment_heading.subheader] == ["Record your judgments"]
    assert not evidence_heading.button and not judgment_heading.text_area
    assert not judgment_heading.divider
    forms = [form for form in workspace.form if form.key.startswith("assessment_")]
    assert len(forms) == 1
    form = forms[0]
    assert len([button for button in form.button if button.label == "Save assessment"]) == 1
    ordered = list(app.main)
    previous_row = None
    for passage in run.passages:
        row = form.get_by_key("passage-row-" + passage.id)
        assert len(row.columns) == 2
        left, right = row.columns
        evidence = left.get_by_key("passage-evidence-" + passage.id)
        judgment = right.get_by_key("passage-judgment-" + passage.id)
        assert passage.anchor.quote in [item.value for item in evidence.text]
        assert any(item.value.startswith(f"**Passage {passage.rank} · ") for item in evidence.markdown)
        assert f"**Passage {passage.rank}**" in [item.value for item in judgment.markdown]
        assert len(evidence.button) == 1 and evidence.button[0].label == "Inspect source"
        assert len(judgment.selectbox) == 1 and judgment.selectbox[0].label == "Passage decision"
        assert judgment.selectbox[0].key.startswith("decision_" + passage.id)
        assert len(judgment.text_area) == 1 and judgment.text_area[0].label == "Notes"
        assert judgment.text_area[0].key.startswith("notes_" + passage.id)
        assert not evidence.text_area and not judgment.button
        if previous_row is not None:
            assert ordered.index(previous_row) < ordered.index(row)
        previous_row = row
    context = app.main.get_by_key("source-context-section")
    assert [heading.value for heading in context.subheader] == ["Verifiable source context"]
    assert not any(node is context for node in workspace)
    assert ordered.index(form) < ordered.index(previous_row) < ordered.index(context)
    export_heading = next(item for item in app.subheader if item.value == "Export your evidence")
    assert ordered.index(context) < ordered.index(export_heading)


def test_inspecting_source_keeps_unsaved_row_judgments_without_saving(presentation):
    app, service, handle, run, provider = presentation
    first = run.passages[0]
    first_judgment = app.main.get_by_key("passage-judgment-" + first.id)
    first_judgment.text_area[0].set_value("Unsaved note for the first matching passage")
    first_judgment.selectbox[0].set_value("useful")
    # Inspection submits the shared form's values but is a distinct action from
    # saving an assessment. The other passage's inspector must keep this draft.
    passage = run.passages[1]
    app.button(key="inspect_" + run.id + passage.id).click().run()
    assert not app.exception
    inspector = next(item for item in app.selectbox if item.label == "Inspect passage")
    assert inspector.value == passage.id
    first_judgment = app.main.get_by_key("passage-judgment-" + first.id)
    assert first_judgment.text_area[0].value == "Unsaved note for the first matching passage"
    assert first_judgment.selectbox[0].value == "useful"
    assert provider.searches == provider.preparations == 1
    snapshot = service.get_workspace(handle)
    assert snapshot.runs == [run] and snapshot.assessments == []


class _RenderedSource(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)

    def handle_data(self, data):
        self.text.append(data)


def test_lower_source_inspector_preserves_exact_escaped_unicode_text(presentation):
    app, service, handle, run, _ = presentation
    for passage in run.passages:
        inspector = next(item for item in app.selectbox if item.label == "Inspect passage")
        inspector.set_value(passage.id).run()
        assert not app.exception
        section = app.main.get_by_key("source-context-section")
        rendered = [item.value for item in section.markdown if 'class="source-context"' in item.value]
        assert len(rendered) == 1
        context = service.get_source_context(handle, SourceContextRequest(run_id=run.id, passage_id=passage.id))
        parsed = _RenderedSource()
        parsed.feed(rendered[0])
        assert parsed.tags == ["div", "mark"]
        assert "".join(parsed.text) == context.block.text
        assert "<mark>" + escape(passage.anchor.quote) + "</mark>" in rendered[0]


def test_portable_theme_matches_requested_identity_and_native_colors():
    tokens = (ROOT / "apps/streamlit/theme/tokens.css").read_text()
    declarations = dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", tokens))
    assert {name: declarations.get(name) for name in EXPECTED_TOKENS} == EXPECTED_TOKENS
    assert re.search(r"font-family\s*:\s*Arial,\s*Helvetica,\s*sans-serif\s*;", tokens)
    config = tomllib.loads((ROOT / ".streamlit/config.toml").read_text())["theme"]
    assert config["primaryColor"].lower() == declarations["--accent"]
    assert config["backgroundColor"].lower() == declarations["--paper"]
    assert config["textColor"].lower() == declarations["--ink"]
