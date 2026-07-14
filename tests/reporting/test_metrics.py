"""Portfolio metric calculations."""

from __future__ import annotations

import pytest

from crucibo.reporting.metrics import (
    compute_metrics,
    equity_returns,
    round_trip_pnls,
    sharpe_ratio,
    sortino_ratio,
    trade_stats,
)


def test_equity_returns() -> None:
    assert equity_returns([100.0, 110.0, 99.0]) == pytest.approx([0.1, -0.1])


def test_sharpe_positive_on_uptrend() -> None:
    rets = [0.01 + (i % 3) * 0.001 for i in range(30)]
    sharpe = sharpe_ratio(rets, periods_per_year=252)
    assert sharpe is not None
    assert sharpe > 0


def test_round_trip_pnls_buy_sell() -> None:
    fills = [
        {"side": "BUY", "notional": 1000.0, "fee_cash": 4.0},
        {"side": "SELL", "notional": 1100.0, "fee_cash": 4.4},
    ]
    pnls = round_trip_pnls(fills)
    assert len(pnls) == 1
    assert pnls[0] == pytest.approx(1100.0 - 4.4 - 1000.0 - 4.0)


def test_trade_stats_win_rate() -> None:
    stats = trade_stats([100.0, -50.0, 80.0])
    assert stats["trades_count"] == 3
    assert stats["win_rate_pct"] == pytest.approx(200 / 3)
    assert stats["profit_factor"] == pytest.approx(180.0 / 50.0)
    assert stats["expectancy"] is not None


def test_sortino_with_downside_volatility() -> None:
    rets = [0.01, -0.02, 0.015, -0.01, 0.02, -0.005, 0.012]
    assert sortino_ratio(rets, periods_per_year=252) is not None


def test_compute_metrics_full_curve() -> None:
    equity_curve = [
        {"equity_marked": 1_000_000.0 + i * 500.0, "drawdown": 0.0}
        for i in range(40)
    ]
    fills = [
        {"side": "BUY", "notional": 100_000.0, "fee_cash": 40.0},
        {"side": "SELL", "notional": 105_000.0, "fee_cash": 42.0},
    ]
    metrics = compute_metrics(equity_curve=equity_curve, fills=fills, interval="daily")
    assert metrics["return_pct"] > 0
    assert metrics["fills_count"] == 2
    assert metrics["trades_count"] == 1
    assert metrics["win_rate_pct"] == pytest.approx(100.0)
    assert metrics["expectancy"] is not None
    assert metrics["expectancy"] > 0