"""Analyst chat schemas. History is client-held and resent each turn."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)
    context: dict[str, Any] = Field(default_factory=dict)


class CopilotStatus(BaseModel):
    enabled: bool
    model: str | None = None
