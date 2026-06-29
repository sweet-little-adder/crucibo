"""Minimal tick row — column-compatible with crucibo silver Parquet."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Tick(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ts_event_ns: int = Field(..., ge=0)
    ts_ingest_ns: int | None = Field(default=None, ge=0)
    symbol: str = Field(..., min_length=1)
    price: float = Field(...)
    size: int = Field(..., ge=1)
    conditions: str | None = None

    @field_validator("price")
    @classmethod
    def price_nonzero(cls, value: float) -> float:
        if value == 0:
            raise ValueError("price must be non-zero")
        return value
