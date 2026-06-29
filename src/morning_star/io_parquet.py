"""Read crucibo-compatible silver Parquet without depending on crucibo."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from morning_star.ticks import Tick


def parquet_to_ticks(path: Path) -> list[Tick]:
    df = pl.read_parquet(path)
    ticks: list[Tick] = []
    for row in df.iter_rows(named=True):
        ingest = row.get("ts_ingest_ns")
        ticks.append(
            Tick(
                ts_event_ns=int(row["ts_event_ns"]),
                ts_ingest_ns=None if ingest is None else int(ingest),
                symbol=str(row["symbol"]),
                price=float(row["price"]),
                size=int(row["size"]),
                conditions=row.get("conditions"),
            )
        )
    return ticks


def sorted_ticks(ticks: list[Tick]) -> list[Tick]:
    return sorted(ticks, key=lambda t: (t.ts_event_ns, t.symbol))


def filter_price_bars(ticks: list[Tick]) -> list[Tick]:
    """Keep OHLCV klines; drop funding and mark-price rows from Binance silver."""
    out: list[Tick] = []
    for tick in ticks:
        cond = tick.conditions or ""
        if cond == "binance:funding-rate":
            continue
        if cond.startswith("binance:") and not cond.startswith("binance:futures-"):
            continue
        if tick.price <= 0:
            continue
        out.append(tick)
    return out
