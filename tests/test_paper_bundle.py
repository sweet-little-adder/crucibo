"""Paper run bundle under data/runs/."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from bar_ticks import make_price_series_ticks
from crucibo.paper.bundle import write_paper_run_bundle
from crucibo.paper.engine import PaperConfig, PaperState, apply_tick
from crucibo.replay.strategies import BuyAndHold


def test_write_paper_run_bundle(tmp_path: Path) -> None:
    ticks = make_price_series_ticks(n=3, start_price=100.0, step=1.0)
    strat = BuyAndHold(target_shares=2)
    cfg = PaperConfig(initial_cash=50_000.0, slip_bps=0.0, fee_per_share=0.0, max_loss_usd=10_000.0)
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

    out = write_paper_run_bundle(
        run_id="paper_TEST_flat_1",
        symbol="TEST",
        interval="1m",
        feed="synthetic",
        strategy_name="buy_hold",
        model_path=None,
        cfg=cfg,
        state=state,
        tick_count=3,
        mode="paper",
        runs_parent=tmp_path,
    )
    assert out == tmp_path / "runs" / "paper_TEST_flat_1"
    assert (out / "run_manifest.json").is_file()
    assert (out / "sim_fills.parquet").is_file()
    assert (out / "equity_curve.parquet").is_file()

    manifest = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["mode"] == "paper"
    assert manifest["tick_count"] == 3
    assert manifest["fills_count"] >= 1
    assert "latency" in manifest

    eq = pl.read_parquet(out / "equity_curve.parquet")
    assert eq.height == 3
    fills = pl.read_parquet(out / "sim_fills.parquet")
    assert fills.height >= 1
