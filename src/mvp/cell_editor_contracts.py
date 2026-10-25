"""Bounded navigation hints, separate from evidence and scientific cell state."""
from typing import Literal
from pydantic import Field, model_validator
from .contracts import Model


class CellEditorStep(Model):
    paper_id: str = Field(min_length=1, max_length=1000)
    field_id: str = Field(min_length=1, max_length=100)
    step: Literal['evidence', 'comment', 'review']


class BoardEditorViewDraft(Model):
    schema_version: Literal['mvp.board-editor-view.v1'] = 'mvp.board-editor-view.v1'
    board_id: str = Field(min_length=1, max_length=200)
    board_revision_id: str = Field(min_length=1, max_length=200)
    cells: list[CellEditorStep] = Field(default_factory=list, max_length=180)

    @model_validator(mode='after')
    def unique_cells(self):
        identities = [(item.paper_id, item.field_id) for item in self.cells]
        if len(set(identities)) != len(identities):
            raise ValueError('Keep one navigation hint per exact comparison cell.')
        return self
