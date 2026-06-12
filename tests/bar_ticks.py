"""Minimal TradeTick helpers for unit tests."""

from __future__ import annotations

from crucibo.models import TradeTick


def make_price_series_ticks(
    *,
    symbol: str = "TST",
    n: int,
    start_price: float = 100.0,
    step: float = 0.05,
    ts_start_ns: int = 1_700_000_000_000_000_000,
    dt_ns: int = 86_400_000_000_000,
) -> list[TradeTick]:
    ticks: list[TradeTick] = []
    price = start_price
    for i in range(n):
        ts = ts_start_ns + i * dt_ns
        ticks.append(
            TradeTick(
                ts_event_ns=ts,
                ts_ingest_ns=ts,
                symbol=symbol,
                price=price,
                size=1_000_000,
                conditions="test:fixture",
            )
        )
        price += step
    return ticks
