"""Live dry-run path and risk guards (no network)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from bar_ticks import make_price_series_ticks
from crucibo.live.broker import DryRunBroker
from crucibo.live.execution import DryRunLiveBackend
from crucibo.live.risk import validate_live_safety
from crucibo.paper.engine import PaperConfig, PaperState
from crucibo.paper.session import run_paper_session_tracked, write_paper_manifest
from crucibo.replay.strategies import BuyAndHold


def test_validate_live_safety_requires_guard() -> None:
    with pytest.raises(ValueError, match="max-loss-usd"):
        validate_live_safety(max_loss_usd=None, max_notional_usd=None, allow_no_kill=False)
    validate_live_safety(max_loss_usd=100.0, max_notional_usd=None, allow_no_kill=False)
    validate_live_safety(max_loss_usd=None, max_notional_usd=None, allow_no_kill=True)


def test_dry_run_live_backend_logs_orders() -> None:
    ticks = make_price_series_ticks(n=2, start_price=100.0, step=0.0)
    cfg = PaperConfig(
        initial_cash=50_000.0,
        slip_bps=0.0,
        fee_per_share=0.0,
        max_loss_usd=5_000.0,
    )
    broker = DryRunBroker(slip_bps=0.0, fee_per_share=0.0)
    backend = DryRunLiveBackend(cfg=cfg, broker=broker)
    strat = BuyAndHold(target_shares=3)
    state = PaperState(cash=cfg.initial_cash, equity_peak=cfg.initial_cash)
    for i, tick in enumerate(ticks):
        state = backend.on_tick(
            strategy=strat,
            tick=tick,
            index=i,
            n_ticks=len(ticks),
            state=state,
        )
    assert state.shares == 3
    assert len(broker.order_log) == 1
    assert broker.order_log[0]["side"] == "BUY"
    assert broker.order_log[0]["mode"] == "live_dry_run"


def test_session_tracked_writes_bundle(tmp_path: Path) -> None:
    ticks = make_price_series_ticks(n=2, start_price=50.0, step=1.0)

    async def _stream():
        for t in ticks:
            yield t

    cfg = PaperConfig(
        initial_cash=20_000.0,
        slip_bps=0.0,
        fee_per_share=0.0,
        max_notional_usd=10_000.0,
    )
    strat = BuyAndHold(target_shares=2)

    async def _run():
        return await run_paper_session_tracked(
            strategy=strat,
            cfg=cfg,
            tick_stream=_stream(),
            mode="paper",
        )

    result = asyncio.run(_run())
    assert result.tick_count == 2
    path = write_paper_manifest(
        run_id="paper_sess_1",
        runs_parent=tmp_path,
        symbol="TEST",
        interval="1m",
        feed="synthetic",
        strategy_name="buy_hold",
        model_path=None,
        cfg=cfg,
        state=result.state,
        tick_count=result.tick_count,
        mode="paper",
    )
    assert path.is_file()
    assert (tmp_path / "runs" / "paper_sess_1" / "equity_curve.parquet").is_file()
