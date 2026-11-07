"""Versioned instruction snapshots for explicitly selected Library Skills."""

from pydantic import BaseModel, ConfigDict, Field


class SkillSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    uuid: str
    title: str
    version: str
    instructions: str = Field(min_length=1, max_length=32000)


class SelectSkillRequest(BaseModel):
    skill_uuid: str | None = Field(min_length=1, max_length=200)
