from typing import Self

from pydantic import BaseModel, Field, model_validator


class TemplateSource(BaseModel):
    artifact_uuid: str | None = Field(default=None, max_length=64)
    revision: str | None = Field(default=None, max_length=64)
    preview_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode='after')
    def one_source(self) -> Self:
        if bool(self.artifact_uuid) == bool(self.preview_id) or (self.artifact_uuid and not self.revision):
            raise ValueError('Choose one saved Page version or chat preview.')
        return self


class SaveTemplate(BaseModel):
    draft_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=1000)
    guidance: str = Field(default='', max_length=4000)
    field_labels: dict[str, str] = Field(default_factory=dict, max_length=500)


class TemplateAccess(BaseModel):
    team_id: str | None = Field(default=None, max_length=200)


class TemplateValue(BaseModel):
    field_id: str = Field(min_length=1, max_length=40)
    value: str = Field(min_length=1, max_length=2000)
    quote: str = Field(min_length=1, max_length=6000)


class TemplateCell(BaseModel):
    value: str = Field(min_length=1, max_length=2000)
    quote: str = Field(min_length=1, max_length=6000)


class TemplateTable(BaseModel):
    table_id: str = Field(min_length=1, max_length=40)
    rows: list[list[TemplateCell | None]] = Field(default_factory=list, max_length=500)
