"""Binance USD-M futures kline WebSocket → TradeTick for paper trading."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import websockets

from crucibo.models import TradeTick, utc_now_ns

BINANCE_FUTURES_WS = "wss://fstream.binance.com/ws"


def kline_stream_url(*, symbol: str, interval: str) -> str:
    sym = symbol.lower()
    return f"{BINANCE_FUTURES_WS}/{sym}@kline_{interval}"


def closed_kline_to_tick(payload: dict) -> TradeTick | None:
    if payload.get("e") != "kline":
        return None
    k = payload.get("k")
    if not isinstance(k, dict) or not k.get("x"):
        return None
    close_ms = int(k["T"])
    return TradeTick(
        ts_event_ns=close_ms * 1_000_000,
        ts_ingest_ns=utc_now_ns(),
        symbol=str(k["s"]),
        price=float(k["c"]),
        size=max(1, int(float(k["v"]))),
        conditions=f"binance:paper-kline-{k.get('i', '')}",
    )


async def stream_closed_klines(
    *,
    symbol: str,
    interval: str,
) -> AsyncIterator[TradeTick]:
    url = kline_stream_url(symbol=symbol, interval=interval)
    async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
        async for raw in ws:
            payload = json.loads(raw)
            tick = closed_kline_to_tick(payload)
            if tick is not None:
                yield tick


async def collect_klines(
    *,
    symbol: str,
    interval: str,
    max_ticks: int,
) -> list[TradeTick]:
    ticks: list[TradeTick] = []
    async for tick in stream_closed_klines(symbol=symbol, interval=interval):
        ticks.append(tick)
        if len(ticks) >= max_ticks:
            break
    return ticks
