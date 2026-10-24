"""Bounded additive local-pilot requests; no exploration or board contract changes."""
from typing import Annotated, Any, Literal

from pydantic import Field, field_validator, model_validator

from src.mvp.board_contracts import BoardFieldInput
from src.mvp.contracts import Model
from src.mvp.usability_draft_contracts import _bounded_json

MAX_PILOT_REQUEST_BYTES = 16 * 1024 * 1024
Identifier = Annotated[str, Field(min_length=1, max_length=200)]


class PilotCreateRequest(Model):
    request_id: Identifier
    title: str = Field(min_length=1, max_length=300)
    question: str = Field(min_length=1, max_length=10000)
    review_type: Literal['systematic', 'scoping'] = 'systematic'
    purpose: Literal['research_pilot', 'software_usability'] = 'research_pilot'
    protocol: dict[str, Any] = Field(default_factory=dict)
    reviewer: str = Field(default='', max_length=200)
    reason: str = Field(default='', max_length=2000)

    @field_validator('protocol')
    @classmethod
    def bounded(cls, value):
        _bounded_json(value)
        return value


class PilotMutation(Model):
    @field_validator('*', mode='after')
    @classmethod
    def valid_unicode(cls, value):
        if isinstance(value, str):
            value.encode('utf-8')
        return value

    request_id: Identifier
    expected_protocol_id: Identifier
    expected_ledger_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    reviewer: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator('reviewer', 'reason')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Declare a reviewer label and a reason')
        return value


class PilotProtocolRequest(PilotMutation):
    content: dict[str, Any]

    @field_validator('content')
    @classmethod
    def bounded(cls, value):
        _bounded_json(value)
        return value


class PilotFileRequest(PilotMutation):
    filename: str = Field(min_length=1, max_length=200)
    content_utf8: str = Field(max_length=8 * 1024 * 1024)
    format: Literal['json', 'ris', 'pubmed_xml']
    source: str = Field(min_length=1, max_length=300)
    query: str | None = Field(default=None, max_length=30000)
    searched_at: str | None = Field(default=None, max_length=100)
    filters: dict[str, Any] = Field(default_factory=dict)
    reported_count: int | None = Field(default=None, ge=0, strict=True)
    scope: Literal['supplied_file', 'exploratory_subset'] = 'supplied_file'

    @field_validator('filters')
    @classmethod
    def bounded(cls, value):
        _bounded_json(value)
        return value


class PilotCaptureRequest(PilotMutation):
    artifacts: dict[str, str] = Field(min_length=1, max_length=100)


class PilotDecisionRequest(PilotMutation):
    record_id: Identifier
    stage: Literal['title_abstract', 'full_text']
    decision: Literal['include', 'exclude', 'uncertain']
    adjudication: bool = False


class PilotRetrievalRequest(PilotMutation):
    record_id: Identifier
    status: Literal['requested', 'retrieved', 'not_retrieved']


class PilotSourceRequest(PilotMutation):
    record_id: Identifier
    kind: Literal['public_jats', 'supplied_jats', 'abstract']
    content_utf8: str | None = Field(default=None, max_length=8 * 1024 * 1024)
    license: str = Field(default='', max_length=1000)
    attribution: str = Field(default='', max_length=4000)
    source_url: str = Field(default='', max_length=4096)
    permission_note: str = Field(default='', max_length=2000)


class PilotHandoffSource(Model):
    record_id: Identifier
    document_id: Identifier
    source_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class PilotHandoffRequest(PilotMutation):
    sources: list[PilotHandoffSource] = Field(min_length=1, max_length=30)
    question: str = Field(min_length=1, max_length=10000)
    fields: list[BoardFieldInput] = Field(min_length=1, max_length=6)
    acknowledge_provisional: bool = False
    expected_source_revision: int = Field(ge=0, strict=True)
    expected_preparation_id: Identifier | None = None

    @model_validator(mode='after')
    def unique(self):
        if len({item.record_id for item in self.sources}) != len(self.sources):
            raise ValueError('Select each report once')
        if len({item.id for item in self.fields}) != len(self.fields):
            raise ValueError('Select unique comparison fields')
        return self


class PilotEditorDraft(Model):
    title: str = Field(default='', max_length=300)
    question: str = Field(default='', max_length=10000)
    purpose: Literal['research_pilot', 'software_usability'] = 'research_pilot'
    protocol_label: str = Field(default='', max_length=200)
    reference: str = Field(default='', max_length=2000)
    content: str = Field(default='', max_length=20000)
    unresolved_text: str = Field(default='', max_length=10000)
    declared_ready: bool = False
    reviewer: str = Field(default='', max_length=200)
    reason: str = Field(default='', max_length=2000)
    record_id: str = Field(default='', max_length=200)
    stage: Literal['title_abstract', 'full_text'] = 'title_abstract'
    decision: Literal['include', 'exclude', 'uncertain'] = 'uncertain'
    status: Literal['requested', 'retrieved', 'not_retrieved'] = 'requested'
    source_choices: dict[str, str] = Field(default_factory=dict, max_length=30)
    expected_protocol_id: str | None = Field(default=None, max_length=200)
    expected_event_sha256: str | None = Field(default=None, max_length=64)
    offset: int = Field(default=0, ge=0, strict=True)

    @field_validator('source_choices')
    @classmethod
    def bounded_choices(cls, value):
        if any(not key or len(key) > 200 or not item or len(item) > 200 for key, item in value.items()):
            raise ValueError('Use bounded source identifiers')
        return value
