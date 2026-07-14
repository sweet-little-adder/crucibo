"""Shared enums and parsers for vendors and bar intervals."""

from __future__ import annotations

from enum import StrEnum


class Vendor(StrEnum):
    ALPHAVANTAGE = "alphavantage"
    BINANCE = "binance"
    POLYGON = "polygon"


# US equities (Alpha Vantage) intervals — primary path.
AV_DAILY = "daily"
AV_INTRADAY_INTERVALS = ("1min", "5min", "15min", "30min", "60min")

# Crypto (Binance USD-M) intervals — secondary path.
BINANCE_INTERVALS = (
    "1m",
    "3m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "8h",
    "12h",
    "1d",
    "3d",
    "1w",
    "1M",
)


def normalize_av_interval(interval: str) -> str:
    key = interval.strip().lower()
    if key in {"d", "1d", "day", "daily"}:
        return AV_DAILY
    if key in AV_INTRADAY_INTERVALS:
        return key
    raise ValueError(
        f"unsupported US equity interval {interval!r} "
        f"(try daily | {' | '.join(AV_INTRADAY_INTERVALS)})"
    )


def is_daily_interval(interval: str) -> bool:
    return normalize_av_interval(interval) == AV_DAILY