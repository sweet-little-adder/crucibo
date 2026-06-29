"""Paper engine unit tests (no network)."""

from __future__ import annotations

from bar_ticks import make_price_series_ticks
from crucibo.paper.engine import PaperConfig, PaperState, apply_tick
from crucibo.replay.strategies import BuyAndHold


def test_paper_kill_switch_max_loss() -> None:
    ticks = make_price_series_ticks(n=3, start_price=100.0, step=-30.0)
    strat = BuyAndHold(target_shares=10)
    cfg = PaperConfig(initial_cash=100_000.0, slip_bps=0.0, fee_per_share=0.0, max_loss_usd=500.0)
    state = PaperState(cash=cfg.initial_cash, equity_peak=cfg.initial_cash)
    for i, tick in enumerate(ticks):
        state = apply_tick(
            strategy=strat,
            tick=tick,
            index=i,
            n_ticks=len(ticks),
            cfg=cfg,
            state=state,
        )
    assert state.killed
    assert state.kill_reason is not None
