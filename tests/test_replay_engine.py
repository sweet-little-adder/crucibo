"""Deterministic naive replay sanity checks."""

from __future__ import annotations

import pytest

from crucibo.models import TradeTick
from crucibo.replay.engine import ReplayConfig, replay_ticks, summarize_pnl
from crucibo.replay.strategies import AlwaysFlat, BuyAndHold


def _ticks_three(prices: list[float]) -> list[TradeTick]:
    ts_base = 1_700_000_000_000_000_000
    ticks: list[TradeTick] = []
    for i, px in enumerate(prices):
        t = ts_base + i * 1_000_000
        ticks.append(
            TradeTick(
                ts_event_ns=t,
                ts_ingest_ns=t,
                symbol="TST",
                price=px,
                size=1,
            )
        )
    return ticks


def test_replay_empty() -> None:
    cfg = ReplayConfig()
    out = replay_ticks(AlwaysFlat(), [], cfg)
    assert out.equity_curve == []
    assert summarize_pnl(cfg, out)["pnl_cash_approx"] == 0.0


def test_flat_no_fills() -> None:
    ticks = _ticks_three([10.0, 10.5, 9.8])
    cfg = ReplayConfig()
    out = replay_ticks(AlwaysFlat(), ticks, cfg)
    assert out.fills == []
    assert out.final_shares == 0
    assert out.final_cash == pytest.approx(cfg.initial_cash)


def test_buy_hold_one_fill() -> None:
    ticks = _ticks_three([50.0, 51.0, 52.0])
    out = replay_ticks(
        BuyAndHold(10),
        ticks,
        ReplayConfig(slip_bps=0.0, fee_per_share=0.0),
    )
    assert len(out.fills) == 1
    assert out.final_shares == 10
