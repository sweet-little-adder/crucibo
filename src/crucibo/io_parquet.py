"""Parquet helpers (silver layer — local dev only)."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from crucibo.models import NewsEvent, TradeTick, news_events_to_polars_rows, ticks_to_polars_rows


def ticks_to_parquet(ticks: list[TradeTick], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pl.DataFrame(ticks_to_polars_rows(ticks))
    df.write_parquet(path)
    return path


def read_ticks_parquet(path: Path) -> pl.DataFrame:
    return pl.read_parquet(path)


def parquet_to_ticks(path: Path) -> list[TradeTick]:
    """Load ticks written by :func:`ticks_to_parquet`."""
    df = read_ticks_parquet(path)
    ticks: list[TradeTick] = []
    for row in df.iter_rows(named=True):
        ingest = row.get("ts_ingest_ns")
        ticks.append(
            TradeTick(
                ts_event_ns=int(row["ts_event_ns"]),
                ts_ingest_ns=None if ingest is None else int(ingest),
                symbol=str(row["symbol"]),
                price=float(row["price"]),
                size=int(row["size"]),
                conditions=row.get("conditions"),
            )
        )
    return ticks


def news_to_parquet(events: list[NewsEvent], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pl.DataFrame(news_events_to_polars_rows(events))
    df.write_parquet(path)
    return path


def read_news_parquet(path: Path) -> pl.DataFrame:
    return pl.read_parquet(path)


def parquet_to_news_events(path: Path) -> list[NewsEvent]:
    df = read_news_parquet(path)
    events: list[NewsEvent] = []
    for row in df.iter_rows(named=True):
        ingest = row.get("ts_ingest_ns")
        events.append(
            NewsEvent(
                ts_event_ns=int(row["ts_event_ns"]),
                ts_ingest_ns=None if ingest is None else int(ingest),
                source=str(row["source"]),
                guid=str(row["guid"]),
                url=str(row["url"]),
                title=str(row["title"]),
                summary=row.get("summary"),
                author=row.get("author"),
                symbols=row.get("symbols"),
            )
        )
    return events
