"""Versioned instruction snapshots for explicitly selected Library Skills."""

from pydantic import BaseModel, ConfigDict, Field


WHEN_TO_USE_MAX = 500


def clean_when_to_use(value: object) -> str:
    """One line, bounded: it is listed for every Skill during discovery."""
    return " ".join(value.split())[:WHEN_TO_USE_MAX] if isinstance(value, str) else ""


class SkillSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    uuid: str
    title: str
    version: str
    instructions: str = Field(min_length=1, max_length=32000)
    # The author's own line on which tasks the Skill is for. Empty on Skills
    # saved before the field existed, and on snapshots pinned before it.
    when_to_use: str = Field(default="", max_length=WHEN_TO_USE_MAX)


class SelectSkillRequest(BaseModel):
    skill_uuid: str | None = Field(min_length=1, max_length=200)
