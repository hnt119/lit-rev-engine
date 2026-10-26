"""Additive report-level classifications/views; scientific board DTOs stay frozen."""
from typing import Annotated, Literal
from pydantic import Field, model_validator
from .contracts import Model, new_id, now
from .board_contracts import BoardReferenceSummary

DimensionId = Literal['population', 'recruitment_geography', 'specimen', 'design', 'focus']
DIMENSIONS = ('population', 'recruitment_geography', 'specimen', 'design', 'focus')
Text = Annotated[str, Field(min_length=1, max_length=200, strict=True)]

class DimensionPut(Model):
    request_id: Text
    expected_head_id: str | None = Field(default=None, max_length=200)
    dimension_id: DimensionId
    field_id: Text
    label: Text
    definition: str = Field(min_length=1, max_length=2000)

class DimensionDefinition(Model):
    schema_version: Literal['mvp.evidence-dimension.v1'] = 'mvp.evidence-dimension.v1'
    id: str = Field(default_factory=new_id)
    workspace_id: str
    board_id: str
    board_revision_id: str
    dimension_id: DimensionId
    field_id: str
    field_revision_id: str
    label: str
    definition: str
    kind: Literal['multi_value'] = 'multi_value'
    supersedes_id: str | None = None
    created_at: str = Field(default_factory=now)

class AttributePut(Model):
    request_id: Text
    expected_head_id: str | None = Field(default=None, max_length=200)
    dimension_revision_id: Text
    paper_id: Text
    origin_kind: Literal['cell', 'proposal']
    origin_id: Text
    values: list[Text] = Field(default_factory=list, max_length=20)
    value_state: Literal['value', 'unknown', 'not_assessed', 'not_found_in_inspected_material'] = 'value'
    review_state: Literal['confirmed', 'unreviewed'] = 'unreviewed'
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode='after')
    def typed_values(self):
        if any(not value.strip() or value != value.strip() or value.casefold() == 'unknown' for value in self.values):
            raise ValueError('Use explicit nonblank values; unknown is a separate state.')
        if len(set(value.casefold() for value in self.values)) != len(self.values):
            raise ValueError('Each normalized value must be distinct.')
        if bool(self.values) != (self.value_state == 'value'):
            raise ValueError('A value needs typed values; unknown and missing states have none.')
        if not self.reason.strip():
            raise ValueError('Record an explicit classification reason.')
        if self.origin_kind == 'proposal' and self.value_state == 'not_found_in_inspected_material':
            raise ValueError('A proposal cannot declare human-inspected absence.')
        if self.origin_kind == 'proposal' and self.review_state != 'unreviewed':
            raise ValueError('A proposal cannot confer confirmation.')
        return self

class AttributeRevision(AttributePut):
    schema_version: Literal['mvp.evidence-attribute.v1'] = 'mvp.evidence-attribute.v1'
    id: str = Field(default_factory=new_id)
    workspace_id: str
    board_id: str
    board_revision_id: str
    dimension_id: DimensionId
    field_id: str
    field_revision_id: str
    source_manifest_sha256: str
    references: list[BoardReferenceSummary]
    supersedes_id: str | None = None
    scope: Literal['report_cooccurrence_only'] = 'report_cooccurrence_only'
    created_at: str = Field(default_factory=now)

class FacetFilter(Model):
    dimension: Literal['population', 'recruitment_geography', 'specimen', 'design', 'focus', 'availability', 'review_status']
    values: list[Text] = Field(min_length=1, max_length=30)

class EvidenceViewConfig(Model):
    columns: list[Text] = Field(default_factory=list, max_length=13)
    filters: list[FacetFilter] = Field(default_factory=list, max_length=7)
    sort_by: Literal['report_order', 'title', 'year', 'review_status'] = 'report_order'
    descending: bool = Field(default=False, strict=True)
    group_by: DimensionId | None = None
    include_unreviewed: bool = Field(default=False, strict=True)

    @model_validator(mode='after')
    def unique(self):
        if len(set(self.columns)) != len(self.columns) or len({f.dimension for f in self.filters}) != len(self.filters):
            raise ValueError('Use distinct visible columns and one OR facet per dimension.')
        return self

class SavedViewPut(Model):
    request_id: Text
    version: int = Field(ge=0, strict=True)
    name: Text
    config: EvidenceViewConfig

class SavedEvidenceView(Model):
    schema_version: Literal['mvp.saved-evidence-view.v1'] = 'mvp.saved-evidence-view.v1'
    revision_id: str = Field(default_factory=new_id)
    id: str
    workspace_id: str
    board_id: str
    board_revision_id: str
    version: int
    name: str
    config: EvidenceViewConfig
    basis_sha256: str | None = None
    paper_ids: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=now)

class EvidenceViewDraft(Model):
    schema_version: Literal['mvp.evidence-view-draft.v1'] = 'mvp.evidence-view-draft.v1'
    board_id: Text
    board_revision_id: Text
    view_id: str | None = None
    base_view_version: int = Field(default=0, ge=0, strict=True)
    config: EvidenceViewConfig

class AttributeProjection(Model):
    dimension_id: DimensionId
    values: list[str] = Field(default_factory=list)
    value_state: str = 'unknown'
    state: Literal['confirmed', 'unreviewed', 'outdated', 'unknown'] = 'unknown'
    reason: str = 'No explicit typed classification exists.'
    revision: AttributeRevision | None = None

class PaperProfileView(Model):
    paper_id: str
    title: str
    year: int | None
    availability: str
    attributes: list[AttributeProjection]
    review_status: list[str]
    pending_proposal_ids: list[str]

class EvidenceProfileSet(Model):
    board_id: str
    board_revision_id: str
    freshness: str
    basis_sha256: str
    dimensions: list[DimensionDefinition]
    papers: list[PaperProfileView]
    scope: Literal['report_cooccurrence_only_not_same_cohort'] = 'report_cooccurrence_only_not_same_cohort'

class EvidenceViewResult(Model):
    config: EvidenceViewConfig
    profiles: EvidenceProfileSet
    paper_ids: list[str]
    groups: dict[str, list[str]]
    unique_report_count: int
    group_occurrences: int
    facets: dict[str, list[str]]
    filter_summary: str

class ProfileDraft(Model):
    schema_version: Literal['mvp.evidence-profile-draft.v1'] = 'mvp.evidence-profile-draft.v1'
    board_id: Text
    board_revision_id: Text
    paper_id: Text
    baseline_initialized: bool = Field(default=False, strict=True)
    base_dimension_head_id: str | None = Field(default=None, max_length=200)
    base_attribute_head_id: str | None = Field(default=None, max_length=200)
    origin_cell_head_id: str | None = Field(default=None, max_length=200)
    dimension_id: DimensionId = 'population'
    field_id: Text
    definition: str = Field(default='', max_length=2000)
    values: list[Annotated[str, Field(max_length=200, strict=True)]] = Field(default_factory=lambda:[''], min_length=1, max_length=20)
    value_state: Literal['value', 'unknown', 'not_assessed', 'not_found_in_inspected_material'] = 'value'
    confirm: bool = Field(default=False, strict=True)
    origin: str = Field(default='cell', min_length=1, max_length=200)
    reason: str = Field(default='', max_length=2000)

class AttributeHistory(Model):
    items: list[AttributeRevision]
    dimension_definitions: list[DimensionDefinition]
    offset: int
    total: int
    limit: int

class SavedViewHistory(Model):
    items: list[SavedEvidenceView]
    offset: int
    total: int
    limit: int
