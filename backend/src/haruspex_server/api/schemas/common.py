"""Shared response shapes."""

from pydantic import BaseModel


class Page[ItemT](BaseModel):
    items: list[ItemT]
    next_cursor: str | None = None
