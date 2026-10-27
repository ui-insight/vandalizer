"""Bounded, visible transcript input shared by all downloadable chat formats."""

import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ExportMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=500_000)
    tools: list[str] = Field(default_factory=list, max_length=1000)
    evidence: str = Field(default="", max_length=500_000)


class ChatExportRequest(BaseModel):
    format: Literal["html", "docx", "xlsx"]
    messages: list[ExportMessage] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def bounded_content(self):
        texts = [text for m in self.messages for text in [m.content, m.evidence, *m.tools]]
        if sum(map(len, texts)) > 500_000:
            raise ValueError("Export is too large. Export fewer messages (maximum 500,000 characters).")
        if any(re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]", text) for text in texts):
            raise ValueError("Export contains unsupported control characters.")
        return self
