"""Typed configuration models."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class LoggingConfig(BaseModel):
    level: str = "INFO"


class IngestDefaults(BaseModel):
    default_vendor: str = "alphavantage"


class BacktestDefaults(BaseModel):
    initial_cash: float = 1_000_000.0
    fee_bps: float = 4.0
    slippage_bps: float = 2.0
    latency_bars: int = 0


class CruciboConfig(BaseModel):
    data_root: Path = Path("data")
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    ingest: IngestDefaults = Field(default_factory=IngestDefaults)
    backtest: BacktestDefaults = Field(default_factory=BacktestDefaults)