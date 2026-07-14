"""Canonical OHLCV bar — primary data unit for backtests (v2)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from crucibo.core.types import Vendor
from crucibo.models import TradeTick


class Bar(BaseModel):
    """Single OHLCV bar at the silver layer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ts_close_ns: int = Field(..., ge=0, description="Bar close time (UTC ns).")
    ts_ingest_ns: int | None = Field(default=None, ge=0)
    symbol: str = Field(..., min_length=1)
    interval: str = Field(..., min_length=1)
    vendor: Vendor
    open: float
    high: float
    low: float
    close: float
    volume: float = Field(..., ge=0)
    session: str | None = Field(default=None, description="e.g. RTH, UTC.")

    @model_validator(mode="after")
    def ohlc_sane(self) -> Bar:
        if self.high < self.low:
            raise ValueError(f"high {self.high} < low {self.low}")
        if not (self.low <= self.open <= self.high and self.low <= self.close <= self.high):
            raise ValueError(
                f"open/close outside [low, high]: "
                f"o={self.open} h={self.high} l={self.low} c={self.close}"
            )
        return self

    @property
    def schema_version(self) -> int:
        return 1

    def to_trade_tick(self) -> TradeTick:
        """Legacy adapter for existing replay/paper paths."""
        return TradeTick(
            ts_event_ns=self.ts_close_ns,
            ts_ingest_ns=self.ts_ingest_ns,
            symbol=self.symbol,
            price=self.close,
            size=max(int(self.volume), 1),
            conditions=f"{self.vendor.value}:{self.interval}",
        )


def bars_to_polars_rows(bars: list[Bar]) -> dict[str, list]:
    return {
        "ts_close_ns": [b.ts_close_ns for b in bars],
        "ts_ingest_ns": [b.ts_ingest_ns for b in bars],
        "symbol": [b.symbol for b in bars],
        "interval": [b.interval for b in bars],
        "vendor": [b.vendor.value for b in bars],
        "open": [b.open for b in bars],
        "high": [b.high for b in bars],
        "low": [b.low for b in bars],
        "close": [b.close for b in bars],
        "volume": [b.volume for b in bars],
        "session": [b.session for b in bars],
        "schema_version": [b.schema_version for b in bars],
    }