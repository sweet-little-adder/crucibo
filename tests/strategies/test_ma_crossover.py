"""MA crossover strategy signals."""

from __future__ import annotations

import pytest

from crucibo.core.bar import Bar
from crucibo.core.types import Vendor
from crucibo.strategies.ma_crossover import MaCrossoverStrategy


def _bars(closes: list[float]) -> list[Bar]:
    ts_base = 1_700_000_000_000_000_000
    return [
        Bar(
            ts_close_ns=ts_base + i,
            symbol="TST",
            interval="daily",
            vendor=Vendor.ALPHAVANTAGE,
            open=c,
            high=c + 1.0,
            low=c - 1.0,
            close=c,
            volume=1.0,
        )
        for i, c in enumerate(closes)
    ]


def test_ma_crossover_long_on_uptrend() -> None:
    closes = [float(i) for i in range(1, 31)]
    bars = _bars(closes)
    strat = MaCrossoverStrategy(fast=3, slow=5, target_shares=50)
    strat.prepare(bars)

    last_signal = strat._signals[-1]
    assert last_signal == 50


def test_ma_crossover_rejects_fast_ge_slow() -> None:
    with pytest.raises(ValueError, match="fast period"):
        MaCrossoverStrategy(fast=10, slow=10)