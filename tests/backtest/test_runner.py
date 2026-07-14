"""Event-driven backtest runner."""

from __future__ import annotations

import pytest

from crucibo.backtest.economics import EconomicsConfig
from crucibo.backtest.runner import run_backtest, summarize_backtest
from crucibo.core.bar import Bar
from crucibo.core.types import Vendor
from crucibo.strategies.ma_crossover import MaCrossoverStrategy


def _daily_bars(closes: list[float]) -> list[Bar]:
    ts_base = 1_700_000_000_000_000_000
    bars: list[Bar] = []
    for i, close in enumerate(closes):
        bars.append(
            Bar(
                ts_close_ns=ts_base + i * 86_400_000_000_000,
                symbol="TST",
                interval="daily",
                vendor=Vendor.ALPHAVANTAGE,
                open=close,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=1_000_000.0,
            )
        )
    return bars


def test_run_backtest_ma_crossover_produces_fills() -> None:
    # Uptrend: fast MA stays above slow MA after warmup.
    closes = [float(100 + i) for i in range(40)]
    bars = _daily_bars(closes)
    strat = MaCrossoverStrategy(fast=5, slow=10, target_shares=10)
    cfg = EconomicsConfig(initial_cash=1_000_000.0, fee_bps=0.0, slippage_bps=0.0)

    outcome = run_backtest(strategy=strat, bars=bars, cfg=cfg)
    assert len(outcome.equity_curve) == len(bars)
    assert outcome.fills_count >= 1
    assert outcome.final_shares == 10

    metrics = summarize_backtest(cfg, outcome)
    assert metrics["fills_count"] >= 1
    assert metrics["equity_end"] > metrics["equity_start"]


def test_latency_one_fills_on_next_bar_open() -> None:
    closes = [100.0] * 5 + [110.0] * 35
    bars = _daily_bars(closes)
    strat = MaCrossoverStrategy(fast=3, slow=5, target_shares=5)
    cfg = EconomicsConfig(
        initial_cash=1_000_000.0,
        fee_bps=0.0,
        slippage_bps=0.0,
        latency_bars=1,
    )

    outcome = run_backtest(strategy=strat, bars=bars, cfg=cfg)
    buy_fills = [f for f in outcome.fills if f["side"] == "BUY"]
    assert buy_fills
    first_buy_idx = int(buy_fills[0]["signal_bar_index"])
    exec_bar = bars[first_buy_idx + 1]
    assert buy_fills[0]["exec_price"] == pytest.approx(exec_bar.open)


def test_run_backtest_empty_raises() -> None:
    with pytest.raises(ValueError, match="no bars"):
        run_backtest(
            strategy=MaCrossoverStrategy(fast=2, slow=3, target_shares=1),
            bars=[],
            cfg=EconomicsConfig(),
        )