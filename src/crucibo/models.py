"""Typed row schemas (versioned).

These mirror docs/DATA.md; bump ``schema_version`` when columns meaning changes.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field


def utc_now_ns() -> int:
    return int(datetime.now(UTC).timestamp() * 1_000_000_000)


class TradeTick(BaseModel):
    """Single trade-ish event at the bronze/silver boundary (illustrative)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ts_event_ns: int = Field(
        ...,
        description="Nanoseconds since Unix epoch, exchange/vendor event time (UTC).",
        ge=0,
    )
    ts_ingest_ns: int | None = Field(
        default=None,
        description="When crucibo persisted the row (UTC ns); None if unknown.",
        ge=0,
    )
    symbol: str = Field(..., min_length=1)
    price: float = Field(..., gt=0)
    size: int = Field(..., ge=1)
    conditions: str | None = Field(
        default=None,
        description="Vendor-specific trade conditions / sale codes if available.",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def schema_version(self) -> int:
        return 1


def ticks_to_polars_rows(ticks: list[TradeTick]) -> dict[str, list]:
    """Build column dict for Polars without depending on row order elsewhere."""
    return {
        "ts_event_ns": [t.ts_event_ns for t in ticks],
        "ts_ingest_ns": [t.ts_ingest_ns for t in ticks],
        "symbol": [t.symbol for t in ticks],
        "price": [t.price for t in ticks],
        "size": [t.size for t in ticks],
        "conditions": [t.conditions for t in ticks],
        "schema_version": [t.schema_version for t in ticks],
    }


class NewsEvent(BaseModel):
    """Single news headline at the silver boundary (RSS/Atom)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ts_event_ns: int = Field(
        ...,
        description="Nanoseconds since Unix epoch, published/updated time (UTC).",
        ge=0,
    )
    ts_ingest_ns: int | None = Field(
        default=None,
        description="When crucibo persisted the row (UTC ns).",
        ge=0,
    )
    source: str = Field(..., min_length=1, description="Feed id, e.g. fed-press.")
    guid: str = Field(..., min_length=1, description="Stable dedup key from feed.")
    url: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    summary: str | None = Field(default=None, description="Snippet or description.")
    author: str | None = Field(default=None)
    symbols: str | None = Field(
        default=None,
        description="Optional comma-separated tickers mentioned (enrichment pass).",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def schema_version(self) -> int:
        return 1


def news_events_to_polars_rows(events: list[NewsEvent]) -> dict[str, list]:
    return {
        "ts_event_ns": [e.ts_event_ns for e in events],
        "ts_ingest_ns": [e.ts_ingest_ns for e in events],
        "source": [e.source for e in events],
        "guid": [e.guid for e in events],
        "url": [e.url for e in events],
        "title": [e.title for e in events],
        "summary": [e.summary for e in events],
        "author": [e.author for e in events],
        "symbols": [e.symbols for e in events],
        "schema_version": [e.schema_version for e in events],
    }
