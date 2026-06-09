"""API key management schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from haruspex_server.core.security import ALL_SCOPES


class KeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    scopes: list[str] = Field(min_length=1)

    @field_validator("scopes")
    @classmethod
    def _known_scopes(cls, scopes: list[str]) -> list[str]:
        unknown = set(scopes) - ALL_SCOPES
        if unknown:
            raise ValueError(f"unknown scopes: {sorted(unknown)}")
        return sorted(set(scopes))


class KeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    key_prefix: str
    scopes: list[str]
    revoked_at: datetime | None
    created_at: datetime


class KeyCreated(KeyOut):
    key: str = Field(description="Plaintext API key — shown exactly once.")
