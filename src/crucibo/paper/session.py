"""Async paper-trading sessions on live bar streams."""

from __future__ import annotations

import inspect
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import asdict
from pathlib import Path

from crucibo.models import TradeTick
from crucibo.paper.alphavantage_poll import OnPoll, stream_new_alphavantage_bars
from crucibo.paper.binance_ws import stream_closed_klines
from crucibo.paper.engine import PaperConfig, PaperState, apply_tick
from crucibo.replay.strategies import TickStrategy

OnTick = Callable[[TradeTick, PaperState], Awaitable[None] | None]


async def run_paper_session(
    *,
    strategy: TickStrategy,
    cfg: PaperConfig,
    tick_stream: AsyncIterator[TradeTick],
    max_ticks: int | None = None,
    on_tick: OnTick | None = None,
) -> PaperState:
    state = PaperState(cash=cfg.initial_cash, equity_peak=cfg.initial_cash)
    index = 0
    async for tick in tick_stream:
        state = apply_tick(
            strategy=strategy,
            tick=tick,
            index=index,
            n_ticks=index + 1,
            cfg=cfg,
            state=state,
        )
        if on_tick is not None:
            maybe = on_tick(tick, state)
            if inspect.isawaitable(maybe):
                await maybe
        index += 1
        if state.killed:
            break
        if max_ticks is not None and index >= max_ticks:
            break
    return state


async def run_paper_binance_session(
    *,
    strategy: TickStrategy,
    symbol: str,
    interval: str,
    cfg: PaperConfig,
    max_ticks: int | None = None,
    on_tick: OnTick | None = None,
) -> PaperState:
    stream = stream_closed_klines(symbol=symbol, interval=interval)
    return await run_paper_session(
        strategy=strategy,
        cfg=cfg,
        tick_stream=stream,
        max_ticks=max_ticks,
        on_tick=on_tick,
    )


async def run_paper_alphavantage_session(
    *,
    strategy: TickStrategy,
    symbol: str,
    interval: str,
    cfg: PaperConfig,
    poll_seconds: float = 300.0,
    max_ticks: int | None = None,
    on_tick: OnTick | None = None,
    on_poll: OnPoll | None = None,
) -> PaperState:
    stream = stream_new_alphavantage_bars(
        symbol=symbol,
        interval=interval,
        poll_seconds=poll_seconds,
        on_poll=on_poll,
    )
    return await run_paper_session(
        strategy=strategy,
        cfg=cfg,
        tick_stream=stream,
        max_ticks=max_ticks,
        on_tick=on_tick,
    )


def write_paper_manifest(
    *,
    out_dir: Path,
    symbol: str,
    interval: str,
    feed: str,
    strategy_name: str,
    model_path: str | None,
    cfg: PaperConfig,
    state: PaperState,
    tick_count: int,
    poll_seconds: float | None = None,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "paper_manifest.json"
    payload = {
        "feed": feed,
        "symbol": symbol,
        "interval": interval,
        "strategy": strategy_name,
        "model_path": model_path,
        "tick_count": tick_count,
        "killed": state.killed,
        "kill_reason": state.kill_reason,
        "final_cash": state.cash,
        "final_shares": state.shares,
        "fills_count": len(state.fills),
        "paper_config": asdict(cfg),
    }
    if poll_seconds is not None:
        payload["poll_seconds"] = poll_seconds
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path