"""Paper engine unit tests (no network)."""

from __future__ import annotations

from bar_ticks import make_price_series_ticks
from crucibo.paper.engine import PaperConfig, PaperState, apply_tick, latency_summary
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
    assert len(state.equity_curve) >= 1


def test_max_notional_clamps_position() -> None:
    ticks = make_price_series_ticks(n=2, start_price=100.0, step=0.0)
    strat = BuyAndHold(target_shares=1000)
    cfg = PaperConfig(
        initial_cash=1_000_000.0,
        slip_bps=0.0,
        fee_per_share=0.0,
        max_notional_usd=500.0,
    )
    state = PaperState(cash=cfg.initial_cash, equity_peak=cfg.initial_cash)
    state = apply_tick(strategy=strat, tick=ticks[0], index=0, n_ticks=2, cfg=cfg, state=state)
    assert state.shares == 5  # 500 / 100
    assert not state.killed


def test_flatten_on_kill() -> None:
    ticks = make_price_series_ticks(n=3, start_price=100.0, step=-40.0)
    strat = BuyAndHold(target_shares=10)
    cfg = PaperConfig(
        initial_cash=100_000.0,
        slip_bps=0.0,
        fee_per_share=0.0,
        max_loss_usd=100.0,
        flatten_on_kill=True,
    )
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
    assert state.shares == 0


def test_latency_samples_recorded() -> None:
    ticks = make_price_series_ticks(n=1, start_price=50.0, step=0.0)
    # make_price_series_ticks may not set ts_ingest; set explicitly
    tick = ticks[0].model_copy(update={"ts_ingest_ns": ticks[0].ts_event_ns + 1_000_000})
    strat = BuyAndHold(target_shares=1)
    cfg = PaperConfig(initial_cash=10_000.0, slip_bps=0.0, fee_per_share=0.0)
    state = PaperState(cash=cfg.initial_cash, equity_peak=cfg.initial_cash)
    state = apply_tick(strategy=strat, tick=tick, index=0, n_ticks=1, cfg=cfg, state=state)
    assert state.latency_samples_ns == [1_000_000]
    assert state.decision_latencies_ns
    summary = latency_summary(state)
    assert summary["feed_lag"]["count"] == 1
