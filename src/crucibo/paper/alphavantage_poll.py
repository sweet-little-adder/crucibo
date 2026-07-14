"""Poll Alpha Vantage for new US equity bars → TradeTick stream for paper trading."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime

import httpx

from crucibo.alphavantage.bars import fetch_daily_bars, fetch_intraday_bars
from crucibo.models import TradeTick
from crucibo.settings import alpha_vantage_api_key

OnPoll = Callable[[dict[str, object]], Awaitable[None] | None]

VALID_INTRADAY_INTERVALS = ("1min", "5min", "15min", "30min", "60min")


def _fetch_bars_sync(*, api_key: str, symbol: str, interval: str) -> list[TradeTick]:
    sym = symbol.upper()
    with httpx.Client(timeout=60.0) as client:
        if interval == "daily":
            return fetch_daily_bars(client, api_key=api_key, symbol=sym)
        if interval not in VALID_INTRADAY_INTERVALS:
            raise ValueError(
                f"interval must be daily or one of {VALID_INTRADAY_INTERVALS}, got {interval!r}"
            )
        return fetch_intraday_bars(client, api_key=api_key, symbol=sym, interval=interval)


def seed_seen_bars(ticks: list[TradeTick]) -> set[int]:
    """Mark existing bars as seen so paper trading starts forward from the next new bar."""
    return {tick.ts_event_ns for tick in ticks}


def _bar_label(ts_event_ns: int) -> str:
    dt = datetime.fromtimestamp(ts_event_ns / 1_000_000_000, tz=UTC)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def latest_tick(ticks: list[TradeTick]) -> TradeTick | None:
    if not ticks:
        return None
    return max(ticks, key=lambda t: t.ts_event_ns)


async def _emit_poll(on_poll: OnPoll | None, payload: dict[str, object]) -> None:
    if on_poll is None:
        return
    maybe = on_poll(payload)
    if inspect.isawaitable(maybe):
        await maybe


def select_new_ticks(*, seen: set[int], ticks: list[TradeTick]) -> list[TradeTick]:
    fresh: list[TradeTick] = []
    for tick in sorted(ticks, key=lambda t: t.ts_event_ns):
        if tick.ts_event_ns in seen:
            continue
        seen.add(tick.ts_event_ns)
        fresh.append(tick)
    return fresh


async def stream_new_alphavantage_bars(
    *,
    symbol: str,
    interval: str = "5min",
    poll_seconds: float = 300.0,
    api_key: str | None = None,
    on_poll: OnPoll | None = None,
) -> AsyncIterator[TradeTick]:
    """Yield newly closed Alpha Vantage bars as they appear on subsequent polls.

    The first poll seeds historical bars without yielding them, so the session only
    trades forward from the next unseen bar. Free tier data is ~15 minutes delayed.
    """
    if poll_seconds <= 0:
        raise ValueError("poll_seconds must be > 0")

    key = api_key or alpha_vantage_api_key()
    seen: set[int] = set()
    seeded = False
    poll_index = 0

    while True:
        poll_index += 1
        ticks = await asyncio.to_thread(
            _fetch_bars_sync,
            api_key=key,
            symbol=symbol,
            interval=interval,
        )
        last = latest_tick(ticks)
        if not seeded:
            seen = seed_seen_bars(ticks)
            seeded = True
            await _emit_poll(
                on_poll,
                {
                    "type": "poll",
                    "phase": "seed",
                    "poll_index": poll_index,
                    "seeded_bars": len(seen),
                    "new_bars": 0,
                    "latest_price": None if last is None else last.price,
                    "latest_bar_label": None if last is None else _bar_label(last.ts_event_ns),
                    "poll_seconds": poll_seconds,
                    "message": (
                        f"seeded {len(seen)} historical bars; "
                        "paper trading starts on the next unseen bar"
                    ),
                },
            )
        else:
            fresh = select_new_ticks(seen=seen, ticks=ticks)
            await _emit_poll(
                on_poll,
                {
                    "type": "poll",
                    "phase": "check",
                    "poll_index": poll_index,
                    "seeded_bars": len(seen),
                    "new_bars": len(fresh),
                    "latest_price": None if last is None else last.price,
                    "latest_bar_label": None if last is None else _bar_label(last.ts_event_ns),
                    "poll_seconds": poll_seconds,
                    "message": (
                        f"poll #{poll_index}: {len(fresh)} new bar(s); sleeping {poll_seconds:.0f}s"
                        if fresh
                        else f"poll #{poll_index}: no new bars yet; sleeping {poll_seconds:.0f}s"
                    ),
                },
            )
            for tick in fresh:
                yield tick
        await asyncio.sleep(poll_seconds)