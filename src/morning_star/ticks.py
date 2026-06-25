"""Minimal tick row — column-compatible with crucibo silver Parquet."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Tick(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ts_event_ns: int = Field(..., ge=0)
    ts_ingest_ns: int | None = Field(default=None, ge=0)
    symbol: str = Field(..., min_length=1)
    price: float = Field(..., gt=0)
    size: int = Field(..., ge=1)
    conditions: str | None = None
