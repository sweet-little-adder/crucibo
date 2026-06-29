"""Date-based tick splits for walk-forward training."""

from __future__ import annotations

from datetime import UTC, datetime

from morning_star.ticks import Tick


def date_to_ns_start(day: str) -> int:
    dt = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC)
    return int(dt.timestamp() * 1_000_000_000)


def date_to_ns_end(day: str) -> int:
    dt = datetime.strptime(day, "%Y-%m-%d").replace(
        hour=23,
        minute=59,
        second=59,
        microsecond=999_000,
        tzinfo=UTC,
    )
    return int(dt.timestamp() * 1_000_000_000)


def split_ticks_by_date(
    ticks: list[Tick],
    *,
    train_end: str,
    oos_start: str,
) -> tuple[list[Tick], list[Tick]]:
    train_end_ns = date_to_ns_end(train_end)
    oos_start_ns = date_to_ns_start(oos_start)
    if oos_start_ns <= train_end_ns:
        raise ValueError(
            f"oos_start {oos_start!r} must be after train_end {train_end!r} "
            "(no overlap between train and OOS windows)"
        )
    train_ticks = [t for t in ticks if t.ts_event_ns <= train_end_ns]
    oos_ticks = [t for t in ticks if t.ts_event_ns >= oos_start_ns]
    if len(train_ticks) < 2:
        raise ValueError("train window has too few ticks")
    if len(oos_ticks) < 1:
        raise ValueError("OOS window has no ticks — widen date range or check data")
    return train_ticks, oos_ticks
