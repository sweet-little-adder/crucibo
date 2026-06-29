"""Async paper-trading session on live Binance kline closes."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from crucibo.paper.binance_ws import stream_closed_klines
from crucibo.paper.engine import PaperConfig, PaperState, apply_tick
from crucibo.replay.strategies import TickStrategy


async def run_paper_session(
    *,
    strategy: TickStrategy,
    symbol: str,
    interval: str,
    cfg: PaperConfig,
    max_ticks: int | None = None,
    on_tick=None,
) -> PaperState:
    state = PaperState(cash=cfg.initial_cash, equity_peak=cfg.initial_cash)
    index = 0
    async for tick in stream_closed_klines(symbol=symbol, interval=interval):
        state = apply_tick(
            strategy=strategy,
            tick=tick,
            index=index,
            n_ticks=index + 1,
            cfg=cfg,
            state=state,
        )
        if on_tick is not None:
            on_tick(tick, state)
        index += 1
        if state.killed:
            break
        if max_ticks is not None and index >= max_ticks:
            break
    return state


def write_paper_manifest(
    *,
    out_dir: Path,
    symbol: str,
    interval: str,
    strategy_name: str,
    model_path: str | None,
    cfg: PaperConfig,
    state: PaperState,
    tick_count: int,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "paper_manifest.json"
    payload = {
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
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
